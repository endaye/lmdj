#!/usr/bin/env python3
"""Real local processes and byte-bound receipts, not actual product acceptance."""
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_fixture_interpreter as interpreter
from tools.release.task_verification import PublicationTaskVerifier, TaskVerificationError, task_scope
from tools.release import task_verification as module
from tools.release.evidence_pr import pr_document
from tools.release.model import canonical_json
from tools.release.orchestration import JournalError, RequestJournal


class VerificationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lmdj-task-verification-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo, self.store = self.root / "repo", self.root / "journal"
        self.git("init", "--initial-branch=main", str(self.repo))
        self.git("-C", str(self.repo), "config", "user.name", "Fixture")
        self.git("-C", str(self.repo), "config", "user.email", "fixture@example.test")
        (self.repo / "scripts").mkdir()
        (self.repo / "tests/build").mkdir(parents=True)
        (self.repo / ".gitignore").write_text(".task-count\n")
        (self.repo / "scripts/docs-site.sh").write_text("printf 'portal\\n'\nprintf 'run\\n' >> .task-count\n")
        (self.repo / "tests/build/ci_change_scope_test.py").write_text("print('ownership')\n")
        (self.repo / "evidence").write_text("base\n")
        self.git("-C", str(self.repo), "add", ".")
        self.git("-C", str(self.repo), "commit", "-m", "base")
        base = self.git("-C", str(self.repo), "rev-parse", "HEAD").strip()
        (self.repo / "evidence").write_text("published\n")
        self.git("-C", str(self.repo), "commit", "-am", "publication")
        self.spec = dict(operation_id="1" * 64, request_sha256="2" * 64, repository_id=12, actor_id=34,
            base_revision=base, head_sha=self.git("-C", str(self.repo), "rev-parse", "HEAD").strip(),
            tree_sha=self.git("-C", str(self.repo), "rev-parse", "HEAD^{tree}").strip(),
            tag="lmdj-v1.0.42.0", target_revision=base, task_evidence_sha256="0" * 64)
        self.git("-C", str(self.repo), "branch", "-m", pr_document(self.spec)["head"])
        self.control = "c" * 40
        self.scope = task_scope(self.spec, self.control)
        self.authorizations = 0
        self.fail_auth = False

    @staticmethod
    def git(*args):
        return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL, text=True)

    def authorize(self, scope):
        self.assertEqual(scope, self.scope)
        self.authorizations += 1
        if self.fail_auth:
            raise RuntimeError("SECRET-AUTH-FAILURE")

    def verifier(self):
        return PublicationTaskVerifier(self.store, self.repo, authorize=self.authorize, path=interpreter.fixture_path())

    def amend(self):
        self.git("-C", str(self.repo), "add", ".")
        self.git("-C", str(self.repo), "commit", "--amend", "--no-edit")
        self.spec["head_sha"] = self.git("-C", str(self.repo), "rev-parse", "HEAD").strip()
        self.spec["tree_sha"] = self.git("-C", str(self.repo), "rev-parse", "HEAD^{tree}").strip()
        self.scope = task_scope(self.spec, self.control)

    def state(self):
        return json.loads((self.store / "task-state.json").read_text())

    def test_actual_checks_receipt_and_reuse(self):
        verifier = self.verifier()
        result = verifier.run(self.scope)
        rows = self.state()["commands"]
        self.assertEqual([r["exit_code"] for r in rows], [0, 0, 0])
        self.assertEqual(rows[0]["output_bytes"], len(b"portal\n"))
        self.assertEqual(rows[-1]["arguments"][-1], self.spec["base_revision"])
        self.assertEqual(verifier.run(self.scope), result)
        self.assertEqual((self.repo / ".task-count").read_text(), "run\n")
        self.spec["task_evidence_sha256"] = result["sha256"]
        self.assertEqual(verifier.verify(self.spec, self.control), result)

    def test_missing_state_after_failed_command_cannot_reinitialize(self):
        (self.repo / "scripts/docs-site.sh").write_text("printf 'run\\n' >> .task-count\nexit 23\n")
        self.amend()
        with self.assertRaisesRegex(TaskVerificationError, "exited 23"):
            self.verifier().run(self.scope)
        (self.store / "task-state.json").unlink()
        with self.assertRaisesRegex(TaskVerificationError, "enrolled.*state is missing"):
            self.verifier().run(self.scope)
        self.assertEqual((self.repo / ".task-count").read_text(), "run\n")

    def test_oversized_state_preserves_existing_receipt_and_inventory(self):
        self.verifier().run(self.scope)
        filename = self.store / "task-state.json"
        original = filename.read_bytes()
        inventory = sorted(p.name for p in self.store.iterdir())
        value = json.loads(original)
        value["scope"]["tag"] = "lmdj-v" + "1" * 65536 + ".0.0.0"
        with RequestJournal(self.store) as journal:
            with self.assertRaisesRegex(TaskVerificationError, "receipt exceeds"):
                PublicationTaskVerifier._save(journal, value)
        self.assertEqual(filename.read_bytes(), original)
        self.assertEqual(sorted(p.name for p in self.store.iterdir()), inventory)

    def test_run_callback_local_error_type_does_not_expose_secret(self):
        verifier = self.verifier()
        verifier.authorize = lambda _: (_ for _ in ()).throw(TaskVerificationError("SECRET-CALLBACK"))
        with self.assertRaisesRegex(TaskVerificationError, "verification is unavailable") as caught:
            verifier.run(self.scope)
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertFalse((self.repo / ".task-count").exists())

    def test_verify_callback_local_error_type_does_not_expose_secret(self):
        result = self.verifier().run(self.scope)
        self.spec["task_evidence_sha256"] = result["sha256"]
        verifier = self.verifier()
        verifier.authorize = lambda _: (_ for _ in ()).throw(TaskVerificationError("SECRET-CALLBACK"))
        with self.assertRaisesRegex(TaskVerificationError, "receipt verification is unavailable") as caught:
            verifier.verify(self.spec, self.control)
        self.assertNotIn("SECRET", str(caught.exception))

    def test_death_after_enrollment_before_state_refuses_reopen(self):
        pid = os.fork()
        if pid == 0:
            with patch.object(PublicationTaskVerifier, "_save", side_effect=lambda *_: os._exit(34)):
                self.verifier().run(self.scope)
            os._exit(99)
        _, wait_status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(wait_status), 34)
        self.assertEqual((self.store / "task-enrolled").read_bytes(), b"")
        self.assertFalse((self.store / "task-state.json").exists())
        with self.assertRaisesRegex(TaskVerificationError, "enrolled.*state is missing"):
            self.verifier().run(self.scope)
        self.assertFalse((self.repo / ".task-count").exists())

    def test_missing_receipt_reader_does_not_enroll_attempt(self):
        with self.assertRaisesRegex(TaskVerificationError, "receipt is missing"):
            self.verifier().verify(self.spec, self.control)
        self.assertFalse((self.store / "task-enrolled").exists())
        self.assertFalse((self.store / "task-state.json").exists())
        self.assertFalse((self.repo / ".task-count").exists())

    def test_existing_receipt_without_marker_is_refused(self):
        result = self.verifier().run(self.scope)
        self.spec["task_evidence_sha256"] = result["sha256"]
        (self.store / "task-enrolled").unlink()
        with self.assertRaisesRegex(TaskVerificationError, "enrollment marker is missing"):
            self.verifier().verify(self.spec, self.control)
        self.assertEqual((self.repo / ".task-count").read_text(), "run\n")

    def test_nonempty_marker_is_refused(self):
        self.verifier().run(self.scope)
        (self.store / "task-enrolled").write_bytes(b"corrupt")
        with self.assertRaisesRegex(TaskVerificationError, "enrollment marker is corrupt"):
            self.verifier().run(self.scope)
        self.assertEqual((self.repo / ".task-count").read_text(), "run\n")

    def test_public_marker_is_refused(self):
        self.verifier().run(self.scope)
        (self.store / "task-enrolled").chmod(0o644)
        with self.assertRaises(JournalError):
            self.verifier().run(self.scope)
        self.assertEqual((self.repo / ".task-count").read_text(), "run\n")

    def test_nonzero_is_retained_and_no_successors_or_replay(self):
        (self.repo / "scripts/docs-site.sh").write_text("printf 'SECRET-OUTPUT\\n'\nprintf 'run\\n' >> .task-count\nexit 23\n")
        self.amend()
        with self.assertRaisesRegex(TaskVerificationError, "exited 23"):
            self.verifier().run(self.scope)
        self.assertEqual(len(self.state()["commands"]), 1)
        self.assertEqual(self.state()["commands"][0]["exit_code"], 23)
        with self.assertRaisesRegex(TaskVerificationError, "automatic replay"):
            self.verifier().run(self.scope)
        self.assertEqual((self.repo / ".task-count").read_text(), "run\n")
        self.assertNotIn("SECRET-OUTPUT", (self.store / "task-state.json").read_text())

    def test_postcommit_whitespace_is_not_an_empty_cached_check(self):
        (self.repo / "evidence").write_text("published  \n")
        self.amend()
        with self.assertRaisesRegex(TaskVerificationError, "git diff --cached --check exited 2"):
            self.verifier().run(self.scope)
        self.assertEqual([r["exit_code"] for r in self.state()["commands"]], [0, 0, 2])

    def test_local_whitespace_config_and_info_attributes_cannot_weaken_check(self):
        (self.repo / "evidence").write_text("published  \n")
        self.amend()
        plain = ["git", "-C", str(self.repo), "diff", "--cached", "--check", self.spec["base_revision"]]
        self.assertEqual(subprocess.run(plain, capture_output=True).returncode, 2)
        for mode in ("config", "attributes"):
            with self.subTest(mode=mode):
                self.store = self.root / ("journal-" + mode)
                if mode == "config":
                    self.git("-C", str(self.repo), "config", "core.whitespace", "-blank-at-eol")
                else:
                    self.git("-C", str(self.repo), "config", "--unset", "core.whitespace")
                    (self.repo / ".git/info/attributes").write_text("* -whitespace\n")
                self.assertEqual(subprocess.run(plain, capture_output=True).returncode, 0)
                with self.assertRaisesRegex(TaskVerificationError, "git diff --cached --check exited 2"):
                    self.verifier().run(self.scope)
                self.assertEqual(self.state()["commands"][-1]["exit_code"], 2)

    def test_masked_dirty_bytes_are_rejected(self):
        self.git("-C", str(self.repo), "update-index", "--assume-unchanged", "evidence")
        (self.repo / "evidence").write_text("malicious\n")
        self.assertEqual(self.git("-C", str(self.repo), "status", "--porcelain"), "")
        with self.assertRaisesRegex(TaskVerificationError, "tracked bytes"):
            self.verifier().run(self.scope)
        self.assertFalse((self.repo / ".task-count").exists())

    def test_mode_drift_rejected(self):
        (self.repo / "evidence").chmod(0o755)
        with self.assertRaisesRegex(TaskVerificationError, "mode changed"):
            self.verifier().run(self.scope)
        self.assertFalse((self.repo / ".task-count").exists())

    def test_symlink_drift_rejected(self):
        (self.repo / "link").symlink_to("evidence")
        self.amend()
        (self.repo / "link").unlink()
        (self.repo / "link").symlink_to("scripts/docs-site.sh")
        with self.assertRaisesRegex(TaskVerificationError, "tracked bytes"):
            self.verifier().run(self.scope)
        self.assertFalse((self.repo / ".task-count").exists())

    def test_branch_and_index_drift_rejected(self):
        self.git("-C", str(self.repo), "branch", "-m", "docs/wrong")
        with self.assertRaisesRegex(TaskVerificationError, "operation-bound"):
            self.verifier().run(self.scope)
        self.git("-C", str(self.repo), "branch", "-m", pr_document(self.spec)["head"])
        (self.repo / "evidence").write_text("another\n")
        self.git("-C", str(self.repo), "add", "evidence")
        with self.assertRaisesRegex(TaskVerificationError, "head or index"):
            self.verifier().run(self.scope)

    def test_env_injection_and_credentials_are_not_inherited(self):
        (self.repo / "tests/build/ci_change_scope_test.py").write_text(
            "import os\nfor key in ('GITHUB_TOKEN', 'DEEPSEEK_API_KEY', 'NODE_OPTIONS', 'PYTHONPATH', 'GNUPGHOME'):\n assert key not in os.environ, key\n"
            "assert os.environ['GIT_CONFIG_GLOBAL'] == os.devnull\n"
            "assert os.environ['GIT_ALLOW_PROTOCOL'] == 'file'\nprint('isolated')\n")
        self.amend()
        with patch.dict(os.environ, dict(GITHUB_TOKEN="SECRET-TOKEN", DEEPSEEK_API_KEY="SECRET-PROVIDER",
                    NODE_OPTIONS="--invalid", PYTHONPATH="/never", GNUPGHOME="/never",
                    GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.worktree", GIT_CONFIG_VALUE_0="/never")):
            self.verifier().run(self.scope)
        self.assertNotIn("SECRET", (self.store / "task-state.json").read_text())

    def test_changed_source_after_child_exit_cannot_be_receipted(self):
        verifier = self.verifier()
        execute = verifier._execute
        def changing(*args):
            result = execute(*args)
            (self.repo / "evidence").write_text("changed\n")
            return result
        verifier._execute = changing
        with self.assertRaisesRegex(TaskVerificationError, "tracked bytes"):
            verifier.run(self.scope)
        self.assertEqual(self.state()["commands"][0]["status"], "finished")
        (self.repo / "evidence").write_text("published\n")
        with self.assertRaisesRegex(TaskVerificationError, "automatic replay"):
            self.verifier().run(self.scope)

    def test_receipt_command_exit_and_binding_tampering_refused(self):
        result = self.verifier().run(self.scope)
        self.spec["task_evidence_sha256"] = result["sha256"]
        original = self.state()
        for change in (lambda s: s["commands"][0].update(exit_code=1),
                       lambda s: s["commands"][0].update(arguments=["true"]),
                       lambda s: s["scope"].update(control_revision="d" * 40)):
            value = deepcopy(original)
            change(value)
            (self.store / "task-state.json").write_bytes(canonical_json(value))
            with self.assertRaises(TaskVerificationError):
                self.verifier().verify(self.spec, self.control)
        (self.store / "task-state.json").write_bytes(canonical_json(original))
        with self.assertRaisesRegex(TaskVerificationError, "digest differs"):
            self.verifier().verify(dict(self.spec, task_evidence_sha256="f" * 64), self.control)

    def test_authority_and_private_writer_required(self):
        self.fail_auth = True
        with self.assertRaisesRegex(TaskVerificationError, "unavailable"):
            self.verifier().run(self.scope)
        self.assertFalse((self.repo / ".task-count").exists())
        self.fail_auth = False
        with RequestJournal(self.store):
            with self.assertRaises(JournalError):
                self.verifier().run(self.scope)
        self.verifier().run(self.scope)
        (self.store / "task-state.json").chmod(0o644)
        with self.assertRaises(JournalError):
            self.verifier().run(self.scope)

    def test_controller_death_after_real_command_is_unknown_not_replayed(self):
        pid = os.fork()
        if pid == 0:
            verifier = self.verifier()
            execute = verifier._execute
            def crash(*args):
                execute(*args)
                os._exit(33)
            verifier._execute = crash
            verifier.run(self.scope)
            os._exit(99)
        _, wait_status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(wait_status), 33)
        self.assertEqual(self.state()["commands"][0]["status"], "started")
        with self.assertRaisesRegex(TaskVerificationError, "automatic replay"):
            self.verifier().run(self.scope)
        self.assertEqual((self.repo / ".task-count").read_text(), "run\n")

    def test_receipt_reader_does_not_expose_authority_errors(self):
        result = self.verifier().run(self.scope)
        self.spec["task_evidence_sha256"] = result["sha256"]
        self.fail_auth = True
        with self.assertRaisesRegex(TaskVerificationError, "receipt verification is unavailable") as caught:
            self.verifier().verify(self.spec, self.control)
        self.assertNotIn("SECRET", str(caught.exception))

    def test_timeout_kills_command_group_and_preserves_unknown(self):
        (self.repo / "scripts/docs-site.sh").write_text("printf 'run\\n' >> .task-count\nsleep 10\n")
        self.amend()
        checks = ((module.CHECKS[0][0], module.CHECKS[0][1], 0.1), *module.CHECKS[1:])
        with patch.object(module, "CHECKS", checks):
            with self.assertRaisesRegex(TaskVerificationError, "execution budget"):
                self.verifier().run(self.scope)
        self.assertEqual(self.state()["commands"][0]["status"], "started")
        with self.assertRaisesRegex(TaskVerificationError, "automatic replay"):
            self.verifier().run(self.scope)

    def test_timeout_waits_for_the_killed_group_before_reporting(self):
        """The killed group holds the writer descriptor until it dies. Without
        the wait, the next attempt met "owned by another writer" instead of the
        refusal to replay an unknown command (batch run 35544024211)."""
        observed = []
        real = module._await_group_exit

        def recording(pid, **kwargs):
            observed.append(pid)
            return real(pid, **kwargs)

        (self.repo / "scripts/docs-site.sh").write_text(
            "printf 'run\\n' >> .task-count\nsleep 10 &\nsleep 10\n")
        self.amend()
        checks = ((module.CHECKS[0][0], module.CHECKS[0][1], 0.1), *module.CHECKS[1:])
        with patch.object(module, "CHECKS", checks), patch.object(module, "_await_group_exit", recording):
            with self.assertRaisesRegex(TaskVerificationError, "execution budget"):
                self.verifier().run(self.scope)
        self.assertEqual(len(observed), 1)
        # The lock is free the moment the budget error surfaces.
        with self.assertRaisesRegex(TaskVerificationError, "automatic replay"):
            self.verifier().run(self.scope)

    def test_group_that_outlives_the_wait_is_still_the_budget_failure(self):
        """A group that will not leave is reported, never silently retried."""
        self.assertFalse(module._await_group_exit(
            os.getpgid(0), timeout=0.0, clock=lambda: 0.0, sleep=lambda _: None))

    def test_live_orphan_command_keeps_writer_lock(self):
        (self.repo / ".gitignore").write_text(".task-count\n.ready\n.release\n")
        (self.repo / "scripts/docs-site.sh").write_text(
            "printf 'run\\n' >> .task-count\ntouch .ready\n"
            "for i in $(seq 1 200); do [ ! -f .release ] || exit 0; sleep 0.025; done\nexit 1\n")
        self.amend()
        pid = os.fork()
        if pid == 0:
            self.verifier().run(self.scope)
            os._exit(99)
        try:
            deadline = time.monotonic() + 3
            while not (self.repo / ".ready").exists() and time.monotonic() < deadline:
                time.sleep(0.025)
            self.assertTrue((self.repo / ".ready").exists())
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            pid = None
            with self.assertRaises(JournalError):
                self.verifier().run(self.scope)
        finally:
            (self.repo / ".release").touch()
            if pid is not None:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
        deadline = time.monotonic() + 3
        while True:
            try:
                with self.assertRaisesRegex(TaskVerificationError, "automatic replay"):
                    self.verifier().run(self.scope)
                break
            except JournalError:
                if time.monotonic() >= deadline:
                    self.fail("orphan command failed to release lock")
                time.sleep(0.025)
        self.assertEqual((self.repo / ".task-count").read_text(), "run\n")

    def test_orphaned_command_retains_both_original_writer_locks(self):
        source_store = self.root / "source-journal"
        script = ("printf 'run\\n' >> .task-count\ntouch .ready\n"
                  "for i in $(seq 1 200); do [ ! -f .release ] || exit 0; sleep 0.025; done\nexit 1\n")
        pid = os.fork()
        if pid == 0:
            with RequestJournal(source_store) as source, RequestJournal(self.store) as task:
                self.verifier()._execute(task, ("bash", "-c", script), 10, retained_locks=(source.lock,))
            os._exit(99)
        try:
            deadline = time.monotonic() + 3
            while not (self.repo / ".ready").exists() and time.monotonic() < deadline:
                time.sleep(0.025)
            self.assertTrue((self.repo / ".ready").exists(), "actual child must start before controller death")
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            pid = None
            for store in (source_store, self.store):
                with self.assertRaises(JournalError):
                    with RequestJournal(store): pass
        finally:
            (self.repo / ".release").touch()
            if pid is not None:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
        deadline = time.monotonic() + 3
        for store in (source_store, self.store):
            while True:
                try:
                    with RequestJournal(store): pass
                    break
                except JournalError:
                    if time.monotonic() >= deadline: self.fail("actual child did not release both writers")
                    time.sleep(0.025)
        self.assertEqual((self.repo / ".task-count").read_text(), "run\n")


if __name__ == "__main__":
    unittest.main()
