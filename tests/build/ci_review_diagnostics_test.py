"""Controlled rehearsal diagnostics never publish raw model/API messages."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/review_diagnostics.py"
spec = importlib.util.spec_from_file_location("review_diagnostics", SCRIPT)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


class DiagnosticTest(unittest.TestCase):
    def test_closed_error_categories_without_raw_response(self):
        for message, expected in (
            ("API Error: 401 token=TOP_SECRET", "authentication"),
            ("API Error: 403 bearer TOP_SECRET", "permission"),
            ("API Error: 429 insufficient quota TOP_SECRET", "quota"),
            ("API Error: 429 TOP_SECRET", "rate_limit"),
            ("API Error: 400 model_not_found TOP_SECRET", "model_not_found"),
            ("API Error: 400 invalid_request_error TOP_SECRET", "request_invalid"),
            ("API Error: 503 TOP_SECRET", "upstream"),
            ("Connection error TOP_SECRET", "network"),
            ("Request timed out TOP_SECRET", "timeout"),
            ("arbitrary TOP_SECRET", "unknown"),
        ):
            with self.subTest(message=message):
                value = diagnostics.summarize([{"type": "result", "is_error": True, "result": message}])
                self.assertEqual(value["category"], expected)
                self.assertNotIn("TOP_SECRET", json.dumps(value))
                self.assertEqual(set(value), {"category", "reason", "http_status"})

    def test_ordinary_conversation_cannot_invent_an_api_failure(self):
        value = diagnostics.summarize([
            {"type": "assistant", "message": {"content": [{"text": "API Error: 401"}]}},
            {"type": "result", "is_error": True, "result": "unknown"},
        ])
        self.assertEqual(value["category"], "unknown")

    def test_marked_api_error_and_explicit_status_are_supported(self):
        value = diagnostics.summarize([
            {"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit",
             "message": {"content": [{"type": "text", "text": "API Error: 429 SECRET"}]}},
            {"type": "result", "is_error": True, "api_error_status": 429},
        ])
        self.assertEqual((value["category"], value["http_status"]), ("rate_limit", 429))

    def test_conflicting_status_or_oversized_input_is_unknown(self):
        value = diagnostics.summarize([{"type": "result", "is_error": True,
                                        "api_error_status": 401, "result": "API Error: 500"}])
        self.assertEqual(value["reason"], "conflicting_status")
        self.assertIsNone(value["http_status"])

    def invoke(self, directory, **overrides):
        env = {**os.environ, "RUNNER_TEMP": str(directory), "GITHUB_REPOSITORY": "endaye/lmdj",
               "GITHUB_RUN_ID": "34133275617", "GITHUB_RUN_ATTEMPT": "1",
               "REVIEW_HEAD_SHA": "a" * 40, "REVIEW_BACKEND": "glm", **overrides}
        return subprocess.run([sys.executable, "-I", str(SCRIPT)], env=env,
                              text=True, capture_output=True)

    def test_cli_emits_only_safe_identity_and_closed_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / diagnostics.FILENAME).write_text(json.dumps([
                {"type": "result", "is_error": True, "result": "API Error: 401 SECRET"}]))
            result = self.invoke(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(result.stdout)
            self.assertEqual(document["category"], "authentication")
            self.assertEqual(document["head_sha"], "a" * 40)
            self.assertNotIn("SECRET", result.stdout + result.stderr)
            self.assertNotIn("pass", document.values())

    def test_missing_invalid_duplicate_symlink_and_oversize_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / diagnostics.FILENAME
            self.assertEqual(json.loads(self.invoke(root).stdout)["reason"], "execution_missing")
            for content in ("TOP_SECRET", '[{"type":"result","type":"assistant"}]'):
                path.write_text(content)
                result = self.invoke(root)
                self.assertEqual(json.loads(result.stdout)["reason"], "execution_unreadable")
                self.assertNotIn("TOP_SECRET", result.stdout + result.stderr)
            path.write_text("x" * (diagnostics.MAX_BYTES + 1))
            self.assertEqual(json.loads(self.invoke(root).stdout)["reason"], "execution_unreadable")
            path.unlink()
            path.symlink_to(root / "absent")
            self.assertEqual(json.loads(self.invoke(root).stdout)["reason"], "execution_unreadable")

    def test_invalid_identity_never_echoed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.invoke(Path(tmp), REVIEW_BACKEND="SECRET\n::error::spoof")
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("SECRET", result.stdout + result.stderr)
            self.assertIn("remedy:", result.stderr)

    def test_workflow_is_never_merge_rehearsal_and_keeps_model_inputs(self):
        source = (ROOT / ".github/workflows/pr-review.yml").read_text()
        self.assertIn("NEVER MERGE", source)
        self.assertIn("github.ref == 'refs/heads/fix/ci-review-controlled-diagnostics'", source)
        self.assertIn("github.event_name == 'pull_request' && vars.PR_REVIEW_ENTRY == 'standalone'", source)
        self.assertNotIn("--model", source)
        self.assertNotIn("show_full_output:", source)
        self.assertIn("steps.review.outcome == 'failure'", source)
        self.assertIn("python3 -I .ci-diagnostics/scripts/ci/review_diagnostics.py", source)
        self.assertIn("ref: ${{ github.sha }}", source)
        self.assertIn("path: .ci-diagnostics", source)
        self.assertNotIn("path: ${{ steps.review.outputs.execution_file }}", source)


if __name__ == "__main__":
    unittest.main()
