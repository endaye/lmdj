#!/usr/bin/env python3
"""Real Git ref effects; fixture identity/authority, never a canonical push."""
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
from tools.release import evidence_branch as module
from tools.release.evidence_branch import EvidenceBranchError, PublicationBranch
from tools.release.evidence_pr import pr_document
from tools.release.model import canonical_json
from tools.release.orchestration import JournalError, RequestJournal


class BranchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lmdj-branch-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo, self.remote, self.journal = (self.root / p for p in ("source", "remote.git", "journal"))
        self.git("init", "--initial-branch=main", str(self.repo))
        self.git("init", "--bare", str(self.remote))
        self.git("-C", str(self.repo), "config", "user.name", "Fixture")
        self.git("-C", str(self.repo), "config", "user.email", "fixture@example.test")
        (self.repo / "evidence").write_text("base\n")
        self.git("-C", str(self.repo), "add", "evidence")
        self.git("-C", str(self.repo), "commit", "-m", "base")
        base = self.git("-C", str(self.repo), "rev-parse", "HEAD").strip()
        (self.repo / "evidence").write_text("published\n")
        self.git("-C", str(self.repo), "commit", "-am", "publication")
        head = self.git("-C", str(self.repo), "rev-parse", "HEAD").strip()
        tree = self.git("-C", str(self.repo), "rev-parse", "HEAD^{tree}").strip()
        self.spec = dict(operation_id="1" * 64, request_sha256="2" * 64, repository_id=12,
            actor_id=34, base_revision=base, head_sha=head, tree_sha=tree,
            tag="lmdj-v1.0.42.0", target_revision=base, task_evidence_sha256="3" * 64)
        self.ref = "refs/heads/" + pr_document(self.spec)["head"]
        self.pushes, self.auths, self.mode = 0, 0, None
        self.fail_auth = None
        self.real_run = subprocess.run
        remote_patch = patch.object(module, "REMOTE", self.remote.as_uri())
        remote_patch.start()
        self.addCleanup(remote_patch.stop)

    @staticmethod
    def git(*args):
        return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL, text=True)

    def authorize(self, spec):
        self.assertEqual(spec, self.spec)
        self.auths += 1
        if self.auths == self.fail_auth:
            raise RuntimeError("SECRET-AUTH-FAILURE")

    def api(self, method, route):
        self.assertEqual(method, "GET")
        return deepcopy({"": {"id": 12, "full_name": "endaye/lmdj"}, "/user": {"id": 34},
            "/branches/main": {"name": "main", "protected": self.mode != "unprotected"}}[route])

    def transport(self, command, **kwargs):
        if not command[1].startswith("--git-dir="):
            return self.real_run(command, **kwargs)
        env = kwargs["env"]
        self.assertEqual(env["GIT_ALLOW_PROTOCOL"], "https")
        self.assertEqual(env["GIT_CONFIG_COUNT"], "1")
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "http.https://github.com/.extraheader")
        self.assertNotIn("SECRET-TOKEN", " ".join(command))
        self.assertNotIn("GIT_TRACE", env)
        self.assertNotIn("GIT_SSH_COMMAND", env)
        self.assertEqual(len(kwargs["pass_fds"]), 1)
        self.assertIn("http.followRedirects=false", command)
        self.assertIn("http.sslVerify=true", command)
        # Only the fixture transport enables file://; production has no override.
        kwargs = deepcopy(kwargs)
        kwargs["env"]["GIT_ALLOW_PROTOCOL"] = "file"
        kwargs["env"].pop("GIT_CONFIG_VALUE_0")
        kwargs["env"]["GIT_CONFIG_COUNT"] = "0"
        is_push = "push" in command
        if is_push:
            self.pushes += 1
            state = json.loads((self.journal / "branch-state.json").read_text())
            self.assertTrue(state["claimed"])
            self.assertEqual(command[-1], self.spec["head_sha"] + ":" + self.ref)
            self.assertIn("--force-with-lease=" + self.ref + ":", command)
            if self.mode == "race":
                self.git("-C", str(self.repo), "push", str(self.remote), self.spec["base_revision"] + ":" + self.ref)
            if self.mode == "before":
                raise TimeoutError("SECRET-BEFORE")
            if self.mode == "death-before":
                os._exit(31)
        completed = self.real_run(command, **kwargs)
        if is_push and self.mode == "after":
            raise TimeoutError("SECRET-AFTER")
        if is_push and self.mode == "death-after":
            os._exit(32)
        return completed

    def advance(self, spec=None):
        controller = PublicationBranch(self.journal, self.repo, token="SECRET-TOKEN", authorize=self.authorize)
        controller.api = self.api
        with patch.object(module.subprocess, "run", side_effect=self.transport):
            return controller.advance(self.spec if spec is None else spec)

    def remote_sha(self):
        return self.git("--git-dir=" + str(self.remote), "rev-parse", self.ref).strip()

    def test_exact_create_and_repeat(self):
        first = self.advance()
        self.assertEqual(first["status"], "verified")
        self.assertEqual(self.remote_sha(), self.spec["head_sha"])
        self.assertEqual(self.advance(), first)
        self.assertEqual(self.pushes, 1)
        self.assertEqual(self.git("--git-dir=" + str(self.remote), "for-each-ref", "--format=%(refname)").splitlines(), [self.ref])

    def test_lost_ack_reconciles(self):
        self.mode = "after"
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual(self.pushes, 1)

    def test_missing_state_after_unknown_push_cannot_reinitialize(self):
        self.mode = "before"
        self.assertEqual(self.advance()["status"], "unknown")
        (self.journal / "branch-state.json").unlink()
        self.mode = None
        with self.assertRaisesRegex(EvidenceBranchError, "enrolled.*state is missing"):
            self.advance()
        self.assertEqual(self.pushes, 1)
        self.assertEqual(self.git("--git-dir=" + str(self.remote), "for-each-ref"), "")

    def test_oversized_state_does_not_replace_recoverable_journal(self):
        self.mode = "before"
        self.advance()
        filename = self.journal / "branch-state.json"
        original = filename.read_bytes()
        inventory = sorted(p.name for p in self.journal.iterdir())
        with RequestJournal(self.journal) as journal:
            value = json.loads(original)
            value["spec"]["tag"] = "lmdj-v" + "1" * 65536 + ".0.0.0"
            with self.assertRaisesRegex(EvidenceBranchError, "state exceeds"):
                PublicationBranch._save(journal, value)
        self.assertEqual(filename.read_bytes(), original)
        self.assertEqual(sorted(p.name for p in self.journal.iterdir()), inventory)

    def test_callback_local_error_type_does_not_expose_secret(self):
        with patch.object(self, "authorize", side_effect=EvidenceBranchError("SECRET-CALLBACK")):
            self.assertEqual(self.advance(), {"status": "unavailable", "evidence": None})
        self.assertEqual(self.pushes, 0)

    def test_unknown_never_repushes_and_late_result_adopted(self):
        self.mode = "before"
        self.assertEqual(self.advance()["status"], "unknown")
        self.mode = None
        self.assertEqual(self.advance()["status"], "unknown")
        self.assertEqual(self.pushes, 1)
        self.git("-C", str(self.repo), "push", str(self.remote), self.spec["head_sha"] + ":" + self.ref)
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual(self.pushes, 1)

    def test_existing_exact_ref_adopted_then_not_recreated(self):
        self.git("-C", str(self.repo), "push", str(self.remote), self.spec["head_sha"] + ":" + self.ref)
        self.assertEqual(self.advance()["status"], "verified")
        self.git("--git-dir=" + str(self.remote), "update-ref", "-d", self.ref)
        self.assertEqual(self.advance()["status"], "unknown")
        self.assertEqual(self.pushes, 0)

    def test_existing_conflict_not_updated(self):
        self.git("-C", str(self.repo), "push", str(self.remote), self.spec["base_revision"] + ":" + self.ref)
        with self.assertRaisesRegex(EvidenceBranchError, "remote ref conflicts"):
            self.advance()
        self.assertEqual(self.remote_sha(), self.spec["base_revision"])
        self.assertEqual(self.pushes, 0)

    def test_competing_create_is_atomically_preserved(self):
        self.mode = "race"
        with self.assertRaisesRegex(EvidenceBranchError, "remote ref conflicts"):
            self.advance()
        self.assertEqual(self.remote_sha(), self.spec["base_revision"])
        self.assertEqual(self.pushes, 1)

    def test_authority_failure_at_write_boundary_no_replay(self):
        self.fail_auth = 3
        self.assertEqual(self.advance()["status"], "unavailable")
        self.fail_auth = None
        self.assertEqual(self.advance()["status"], "unknown")
        self.assertEqual(self.pushes, 0)

    def test_unprotected_main_stops_before_push(self):
        self.mode = "unprotected"
        with self.assertRaisesRegex(EvidenceBranchError, "main is not protected"):
            self.advance()
        self.assertEqual(self.pushes, 0)

    def test_bad_identity_stops_before_push(self):
        changed = dict(self.spec, tree_sha="f" * 40)
        self.spec = changed
        with self.assertRaisesRegex(EvidenceBranchError, "local commit identity"):
            self.advance()
        self.assertEqual(self.pushes, 0)

    def test_death_after_enrollment_before_initial_state_stops_on_reopen(self):
        pid = os.fork()
        if pid == 0:
            with patch.object(PublicationBranch, "_save", side_effect=lambda *_: os._exit(33)):
                self.advance()
            os._exit(99)
        _, wait_status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(wait_status), 33)
        self.assertEqual((self.journal / "branch-enrolled").read_bytes(), b"")
        self.assertFalse((self.journal / "branch-state.json").exists())
        with self.assertRaisesRegex(EvidenceBranchError, "enrolled.*state is missing"):
            self.advance()
        self.assertEqual(self.pushes, 0)
        self.assertEqual(self.git("--git-dir=" + str(self.remote), "for-each-ref"), "")

    def test_existing_state_without_enrollment_refused(self):
        self.mode = "before"
        self.advance()
        original = (self.journal / "branch-state.json").read_bytes()
        (self.journal / "branch-enrolled").unlink()
        with self.assertRaisesRegex(EvidenceBranchError, "enrollment marker is missing"):
            self.advance()
        self.assertEqual((self.journal / "branch-state.json").read_bytes(), original)
        self.assertEqual(self.pushes, 1)

    def test_nonempty_enrollment_marker_refused(self):
        self.mode = "before"
        self.advance()
        (self.journal / "branch-enrolled").write_bytes(b"corrupt")
        with self.assertRaisesRegex(EvidenceBranchError, "enrollment marker is corrupt"):
            self.advance()
        self.assertEqual(self.pushes, 1)

    def test_public_enrollment_marker_refused(self):
        self.mode = "before"
        self.advance()
        (self.journal / "branch-enrolled").chmod(0o644)
        with self.assertRaises(JournalError):
            self.advance()
        self.assertEqual(self.pushes, 1)

    def test_scope_rebound_and_corruption_refused(self):
        self.assertEqual(self.advance()["status"], "verified")
        with self.assertRaises(EvidenceBranchError):
            self.advance(dict(self.spec, request_sha256="f" * 64))
        state_path = self.journal / "branch-state.json"
        state_path.write_bytes(b"{broken SECRET}")
        with self.assertRaisesRegex(EvidenceBranchError, "state is invalid"):
            self.advance()

    def test_state_permissions_and_other_writer_refused(self):
        self.assertEqual(self.advance()["status"], "verified")
        with RequestJournal(self.journal):
            with self.assertRaises(JournalError):
                self.advance()
        (self.journal / "branch-state.json").chmod(0o644)
        with self.assertRaises(JournalError):
            self.advance()

    def test_source_git_config_and_environment_cannot_redirect(self):
        self.git("-C", str(self.repo), "config", "url.file:///never/.insteadOf", self.remote.as_uri())
        with patch.dict(os.environ, {"GIT_TRACE": "/never/trace", "GIT_SSH_COMMAND": "false",
                                    "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "url.file:///never/.insteadOf",
                                    "GIT_CONFIG_VALUE_0": self.remote.as_uri()}):
            self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual(self.remote_sha(), self.spec["head_sha"])

    def test_real_controller_death_before_and_after_remote_effect(self):
        for mode, code in (("death-before", 31), ("death-after", 32)):
            with self.subTest(mode=mode):
                self.journal = self.root / mode
                self.spec["operation_id"] = ("4" if code == 31 else "5") * 64
                self.ref = "refs/heads/" + pr_document(self.spec)["head"]
                pid = os.fork()
                if pid == 0:
                    self.mode = mode
                    self.advance()
                    os._exit(99)
                _, wait_status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(wait_status), code)
                self.assertEqual(self.advance()["status"], "unknown" if code == 31 else "verified")
                self.assertEqual(self.pushes, 0)

    def test_orphaned_git_child_retains_writer_lock_until_remote_finishes(self):
        ready, release = self.root / "hook-ready", self.root / "hook-release"
        hook = self.remote / "hooks/pre-receive"
        hook.write_text(f"#!{interpreter.fixture_python()}\nfrom pathlib import Path\nimport time\n"
            f"Path({str(ready)!r}).touch()\n"
            f"for _ in range(400):\n if Path({str(release)!r}).exists(): break\n time.sleep(0.025)\n"
            f"else: raise SystemExit(1)\n")
        hook.chmod(0o755)
        pid = os.fork()
        if pid == 0:
            self.advance()
            os._exit(99)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.025)
            self.assertTrue(ready.exists(), "real remote hook did not start")
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            pid = None
            with self.assertRaises(JournalError):
                self.advance()
        finally:
            release.touch()
            if pid is not None:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
        deadline = time.monotonic() + 5
        while True:
            try:
                result = self.advance()
                break
            except JournalError:
                if time.monotonic() >= deadline:
                    self.fail("orphaned Git did not release its writer lock")
                time.sleep(0.025)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.remote_sha(), self.spec["head_sha"])
        self.assertEqual(self.pushes, 0)


if __name__ == "__main__":
    unittest.main()
