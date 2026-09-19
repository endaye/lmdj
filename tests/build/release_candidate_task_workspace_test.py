#!/usr/bin/env python3
"""Real Git checkout/executor; install entrypoint fixture is not npm acceptance."""
from copy import deepcopy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_fixture_interpreter as interpreter
sys.path.insert(0, str(ROOT / "tests/build"))
import release_candidate_witness_test as fixture
from tools.release.candidate_task_workspace import CandidateTaskWorkspace, CandidateTaskWorkspaceError
from tools.release.candidate_witness_task import CandidateWitnessTask


class WorkspaceFixture(fixture.WitnessFixture):
    install_script = "printf 'install\\n' >> .fixture-install-calls"

    def _prepare_seed(self):
        script = fixture.SCRIPT.replace("*) exit 64 ;;", "install) " + self.install_script + " ;;\n*) exit 64 ;;")
        with patch.object(fixture, "SCRIPT", script):
            super()._prepare_seed()

    def setUp(self):
        super().setUp()
        self.receipt = self.run_witness()
        self.destination = self.root.parent / "owned-witness"
        self.workspace_journal = self.root.parent / "workspace-operation"
        self.task = CandidateWitnessTask(self.destination, self.witness)
        self.workspace = self.new_workspace()
        self.inputs = dict(request=self.request, source=self.source, cut=self.cut_receipt,
            frozen=self.fixture.frozen, merge_revision=self.merged)

    def new_workspace(self, **changes):
        settings = dict(authorize=lambda scope: None, control_revision=self.fixture.base,
                        path=interpreter.fixture_path())
        settings.update(changes)
        return CandidateTaskWorkspace(self.workspace_journal, self.task, **settings)

    def prepare_workspace(self, **changes):
        settings = dict(receipt=self.receipt, base_revision=self.merged, before_write=lambda: None, **self.inputs)
        settings.update(changes)
        return self.workspace.prepare(**settings)

    def observe(self):
        return self.workspace.observe(receipt=self.receipt, base_revision=self.merged, **self.inputs)

    def install_calls(self):
        filename = self.destination / ".fixture-install-calls"
        return filename.read_text().splitlines() if filename.exists() else []

    def workspace_state(self):
        return json.loads((self.workspace_journal / self.workspace.STATE).read_bytes())


class WorkspaceTest(WorkspaceFixture):
    def _lose_history_in_source_guard(self, *, installed):
        if installed:
            self.prepare_workspace()
        original_state = self.workspace._state
        original_artifact = self.witness.verified_artifact
        reads, lost = 0, False
        def state(*args, **kwargs):
            nonlocal reads
            value = original_state(*args, **kwargs)
            reads += 1
            return value
        @contextmanager
        def artifact(*args, **kwargs):
            with original_artifact(*args, **kwargs) as (emitted, raw, original_guard):
                def guard():
                    nonlocal lost
                    main = original_guard()
                    # Arm only after actual closed-history reads, not before
                    # enrollment. The old last source callback could remove
                    # that already checked history just before save/success.
                    if not lost and reads >= (3 if installed else 2):
                        (self.workspace_journal / self.workspace.STATE).unlink()
                        lost = True
                    return main
                yield emitted, raw, guard
        with patch.object(self.workspace, "_state", state), patch.object(self.witness, "verified_artifact", artifact):
            with self.assertRaisesRegex(CandidateTaskWorkspaceError, "history|state"):
                self.observe() if installed else self.prepare_workspace()
        self.assertTrue(lost)
        self.assertFalse((self.workspace_journal / self.workspace.STATE).exists())
        self.assertEqual(self.install_calls(), ["install"] if installed else [])
        if not installed:
            self.assertFalse(self.destination.exists())

    def test_late_source_guard_cannot_recreate_workspace_history(self):
        self._lose_history_in_source_guard(installed=False)

    def test_late_source_guard_cannot_accept_missing_installed_history(self):
        self._lose_history_in_source_guard(installed=True)

    def test_observation_does_not_create_worktree_or_install(self):
        self.assertEqual(self.observe(), dict(status="absent", evidence=None))
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.workspace_journal / self.workspace.MARKER).exists())
        self.assertEqual(self.install_calls(), [])

    def test_real_owned_checkout_install_and_cold_recovery(self):
        original = self.tool.git("show-ref")
        result = self.prepare_workspace()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.task.revision("HEAD"), self.merged)
        self.assertTrue((self.destination / "apps/docs-site/versioned_provenance").is_symlink())
        state = self.workspace_state()
        self.assertEqual(state["install"]["arguments"], ["bash", "scripts/docs-site.sh", "install"])
        self.assertEqual(state["install"]["result"][0], 0)
        self.assertEqual(state["install"]["status"], "verified")
        raw = (self.workspace_journal / self.workspace.STATE).read_bytes()
        self.witness = self.new_runner()
        self.task = CandidateWitnessTask(self.destination, self.witness)
        self.workspace = self.new_workspace()
        self.assertEqual(self.observe(), result)
        self.assertEqual(self.prepare_workspace(), result)
        self.assertEqual(self.install_calls(), ["install"])
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        self.assertEqual((self.workspace_journal / self.workspace.STATE).read_bytes(), raw)
        # Only the one owned witness branch was added; the source stayed put.
        self.assertTrue(all(row in self.tool.git("show-ref").splitlines() for row in original.splitlines()))
        self.assertEqual(self.tool.revision("HEAD"), self.cut_receipt["commit"])

    def test_unowned_existing_path_is_not_adopted_or_overwritten(self):
        self.destination.mkdir()
        (self.destination / "user-file").write_bytes(b"retain me")
        with self.assertRaisesRegex(CandidateTaskWorkspaceError, "already exists before owned creation"):
            self.prepare_workspace()
        self.assertFalse(self.workspace_state()["create_intent"])
        self.assertEqual((self.destination / "user-file").read_bytes(), b"retain me")
        self.assertEqual(self.install_calls(), [])

    def test_process_death_after_checkout_recovers_exact_creation_once(self):
        pid = os.fork()
        if pid == 0:
            original = self.tool.git
            def crash(*args, **kwargs):
                result = original(*args, **kwargs)
                if "worktree" in args and "add" in args:
                    os._exit(41)
                return result
            self.tool.git = crash
            try:
                self.prepare_workspace()
            except BaseException:
                os._exit(42)
            os._exit(43)
        _, returned = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(returned), 41)
        self.assertTrue(self.workspace_state()["create_intent"])
        self.assertFalse(self.workspace_state()["created"])
        self.assertEqual(self.install_calls(), [])
        self.workspace = self.new_workspace()
        # Observe can confirm the far-side creation, but cannot install.
        self.assertEqual(self.observe()["status"], "pending")
        self.assertTrue(self.workspace_state()["created"])
        self.assertEqual(self.prepare_workspace()["status"], "verified")
        self.assertEqual(self.install_calls(), ["install"])

    def test_process_death_after_install_never_replays_unknown_command(self):
        pid = os.fork()
        if pid == 0:
            original = self.workspace.executor._execute
            def crash(*args, **kwargs):
                original(*args, **kwargs)
                os._exit(41)
            self.workspace.executor._execute = crash
            try:
                self.prepare_workspace()
            except BaseException:
                os._exit(42)
            os._exit(43)
        _, returned = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(returned), 41)
        self.assertEqual(self.workspace_state()["install"]["status"], "started")
        self.assertIsNone(self.workspace_state()["install"]["result"])
        raw = (self.workspace_journal / self.workspace.STATE).read_bytes()
        self.workspace = self.new_workspace()
        self.assertEqual(self.observe()["status"], "unknown")
        self.assertEqual(self.prepare_workspace()["status"], "unknown")
        self.assertEqual(self.install_calls(), ["install"])
        self.assertEqual((self.workspace_journal / self.workspace.STATE).read_bytes(), raw)

    def test_missing_enrolled_state_is_not_recreated(self):
        self.prepare_workspace()
        (self.workspace_journal / self.workspace.STATE).unlink()
        with self.assertRaisesRegex(CandidateTaskWorkspaceError, "missing, corrupt or rebound"):
            self.prepare_workspace()
        self.assertFalse((self.workspace_journal / self.workspace.STATE).exists())
        self.assertEqual(self.install_calls(), ["install"])

    def test_authority_loss_at_install_intent_stops_child(self):
        def guard():
            filename = self.workspace_journal / self.workspace.STATE
            if filename.exists() and self.workspace_state()["install"] is not None:
                raise RuntimeError("PRIVATE-AUTHORITY")
        with self.assertRaisesRegex(CandidateTaskWorkspaceError, "parent authority is unavailable") as failure:
            self.prepare_workspace(before_write=guard)
        self.assertNotIn("PRIVATE-AUTHORITY", "".join(traceback.format_exception(failure.exception)))
        self.assertEqual(self.workspace_state()["install"]["status"], "started")
        self.assertEqual(self.install_calls(), [])
        self.assertEqual(self.prepare_workspace()["status"], "unknown")
        self.assertEqual(self.install_calls(), [])


class InstallFailureTest(WorkspaceFixture):
    install_script = "printf 'install\\n' >> .fixture-install-calls; exit 23"

    def test_nonzero_install_is_retained_and_never_replayed(self):
        with self.assertRaisesRegex(CandidateTaskWorkspaceError, "dependency installation exited 23"):
            self.prepare_workspace()
        self.assertEqual(self.workspace_state()["install"]["result"][0], 23)
        self.workspace = self.new_workspace()
        self.assertEqual(self.observe()["status"], "conflict")
        self.assertEqual(self.prepare_workspace()["status"], "conflict")
        self.assertEqual(self.install_calls(), ["install"])


if __name__ == "__main__":
    unittest.main()
