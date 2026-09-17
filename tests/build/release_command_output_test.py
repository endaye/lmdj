#!/usr/bin/env python3
"""Actual child output; no synthetic verifier receipt or release acceptance."""
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.orchestration import JournalError, RequestJournal
from tools.release.task_verification import PublicationTaskVerifier, TaskVerificationError


class OutputTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="lmdj-command-output-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.executor = PublicationTaskVerifier(None, self.root,
            authorize=lambda _: self.fail("executor must not invent authorization"),
            path=os.environ["PATH"])

    def execute(self, script, *, limit=1024, timeout=5):
        with RequestJournal(self.root / "journal") as journal:
            return self.executor._execute_capture(journal, (sys.executable, "-c", script),
                                                 timeout, limit=limit)

    def assert_result(self, result, code, raw):
        self.assertEqual(result, (code, sha256(raw).hexdigest(), len(raw)))

    def test_complete_binary_stdout_and_stderr_are_not_decoded(self):
        raw = b'{"status":"verified"}\n\x00\xffwarning\n'
        result, captured = self.execute(
            "import os; os.write(1, b'{\"status\":\"verified\"}\\n\\x00\\xff'); os.write(2, b'warning\\n')")
        self.assert_result(result, 0, raw)
        self.assertEqual(captured, raw)

    def test_nonzero_exit_keeps_actual_output_and_exit(self):
        result, captured = self.execute("import os; os.write(1, b'failed'); raise SystemExit(23)")
        self.assert_result(result, 23, b"failed")
        self.assertEqual(captured, b"failed")

    def test_exact_maximum_limit_is_complete(self):
        result, captured = self.execute("import os; os.write(1, b'x' * 65536)", limit=65536)
        self.assert_result(result, 0, b"x" * 65536)
        self.assertEqual(captured, b"x" * 65536)

    def test_empty_output_is_not_overflow(self):
        result, captured = self.execute("pass", limit=1)
        self.assert_result(result, 0, b"")
        self.assertEqual(captured, b"")

    def test_one_byte_overflow_never_returns_valid_json_prefix(self):
        raw = b'{"ok":true}\nx'
        result, captured = self.execute(f"import os; os.write(1, {raw!r})", limit=len(raw) - 1)
        self.assert_result(result, 0, raw)
        self.assertIsNone(captured)

    def test_multichunk_overflow_still_hashes_all_bytes(self):
        raw = b"x" * (2 * 1024 * 1024) + b"last"
        result, captured = self.execute(
            "import os; os.write(1, b'x' * (2 * 1024 * 1024)); os.write(2, b'last')",
            limit=65536)
        self.assert_result(result, 0, raw)
        self.assertIsNone(captured)

    def test_invalid_limits_refuse_before_launch(self):
        with patch("tools.release.task_verification.subprocess.Popen") as launch:
            for limit in (None, True, False, 0, -1, 65537, 1.5, "1024"):
                with self.subTest(limit=limit):
                    with self.assertRaisesRegex(TaskVerificationError, "why:.*capture.*remedy:"):
                        self.execute("raise SystemExit(99)", limit=limit)
            launch.assert_not_called()

    def test_legacy_execution_returns_only_three_fields(self):
        with RequestJournal(self.root / "journal") as journal:
            result = self.executor._execute(journal,
                (sys.executable, "-c", "import os; os.write(1, b'original')"), 5)
        self.assert_result(result, 0, b"original")

    def test_capture_uses_scrubbed_environment(self):
        blocked = ("GITHUB_TOKEN", "DEEPSEEK_API_KEY", "NODE_OPTIONS", "PYTHONPATH",
                   "GNUPGHOME", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")
        script = (f"import os; assert not any(k in os.environ for k in {blocked!r}); "
                  "assert os.environ['GIT_CONFIG_GLOBAL'] == os.devnull; "
                  "assert os.environ['GIT_ALLOW_PROTOCOL'] == 'file'; print('isolated')")
        with patch.dict(os.environ, {key:"fixture-secret" for key in blocked}):
            result, captured = self.execute(script)
        self.assert_result(result, 0, b"isolated\n")
        self.assertEqual(captured, b"isolated\n")

    def test_child_inherits_exact_writer_descriptor(self):
        with RequestJournal(self.root / "journal") as journal:
            info = os.fstat(journal.lock)
            script = (f"import os, json; s=os.fstat({journal.lock}); "
                      "print(json.dumps([s.st_dev, s.st_ino]))")
            result, captured = self.executor._execute_capture(journal,
                (sys.executable, "-c", script), 5, limit=1024)
        self.assertEqual(result[0], 0)
        self.assertEqual(json.loads(captured), [info.st_dev, info.st_ino])
        self.assert_result(result, 0, captured)

    def test_closed_writer_cannot_launch(self):
        with RequestJournal(self.root / "journal") as journal:
            pass
        with patch("tools.release.task_verification.subprocess.Popen") as launch:
            with self.assertRaises(JournalError):
                self.executor._execute_capture(journal, (sys.executable, "-c", "pass"),
                                               5, limit=1024)
            launch.assert_not_called()

    def test_timeout_returns_no_partial_receipt(self):
        with self.assertRaisesRegex(TaskVerificationError, "execution budget"):
            self.execute("import os, time; os.write(1, b'partial'); time.sleep(10)", timeout=0.1)
        with RequestJournal(self.root / "journal"):
            pass


if __name__ == "__main__":
    unittest.main()
