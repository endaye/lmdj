#!/usr/bin/env python3
"""Real source/snapshot journal -> private-index cut and interrupted ref update."""
import json
from copy import deepcopy
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_fixture_interpreter as interpreter
import release_candidate_snapshot_test as snapshot_fixture
from tools.release.candidate_cut import CandidateCutWorkspace, CandidateCutError

SCRIPT = snapshot_fixture.SCRIPT.replace(
    'printf complete > "apps/docs-site/versioned_metadata/version-$2.json"',
    '''printf '{"product_build":"%s","revision":"%s","channel":"canary","frozen_at_utc":"2026-09-13T00:00:00.000Z"}\\n' "$2" "$(git rev-parse HEAD)" > "apps/docs-site/versioned_metadata/version-$2.json"''').replace(
    'test "$(cat "apps/docs-site/versioned_metadata/version-$2.json")" = complete',
    'test -s "apps/docs-site/versioned_metadata/version-$2.json"')


class CutFixture(snapshot_fixture.SnapshotFixture):
    def _prepare_seed(self):
        with patch.object(snapshot_fixture, "SCRIPT", SCRIPT):
            super().setUp()
        self.receipt = self.run_snapshot()
        self.cut = CandidateCutWorkspace(self.runner)
        self.phases = []

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Each cut case starts at the same real producer's emitted pre-cut
        # boundary. All cut transitions and crashes still execute per case.
        # These classes run serially; never share this filesystem concurrently.
        seed = cls()
        cls.addClassCleanup(seed.doCleanups)
        seed._prepare_seed()
        assert seed.tool._journal is None
        with snapshot_fixture.RequestJournal(seed.journal) as journal:
            seed.runner.verified_state(journal, seed.request, seed.source, seed.receipt["sha256"])
        cls.seed_fields = {key:deepcopy(getattr(seed.fixture, key))
                           for key in ("container", "root", "state", "base", "frozen", "current")}
        cls.seed_request, cls.seed_source = deepcopy(seed.request), deepcopy(seed.source)
        cls.seed_receipt = deepcopy(seed.receipt)
        cls.seed_branch, cls.seed_root = seed.branch, seed.root
        backup = tempfile.TemporaryDirectory(prefix="lmdj-cut-seed-")
        cls.addClassCleanup(backup.cleanup)
        cls.seed_backup = Path(backup.name) / "container"
        shutil.copytree(seed.fixture.container, cls.seed_backup, symlinks=True)

    def setUp(self):
        # Restore only our original TemporaryDirectory at its original path;
        # no Git pointers, source/snapshot receipts or identities are rewritten.
        container = self.seed_fields["container"]
        shutil.rmtree(container)
        shutil.copytree(self.seed_backup, container, symlinks=True)
        self.fixture = snapshot_fixture.fixture_module.material_fixture.MaterialTest()
        for key, value in self.seed_fields.items():
            setattr(self.fixture, key, deepcopy(value))
        self.fixture.tool = snapshot_fixture.fixture_module.material_fixture.CandidateBuildMaterial(
            self.fixture.root, self.fixture.state)
        self.request, self.source = deepcopy(self.seed_request), deepcopy(self.seed_source)
        self.receipt = deepcopy(self.seed_receipt)
        self.branch, self.root = self.seed_branch, self.seed_root
        self.tool = snapshot_fixture.CandidateSourceWorkspace(self.root, self.fixture.tool)
        self.calls, self.authorities, self.phases = [], [], []
        self.runner = snapshot_fixture.CandidateSnapshotRun(
            self.tool, authorize=self.authorities.append, path=interpreter.fixture_path())
        self.journal = Path(self.tool.git("rev-parse", "--absolute-git-dir").decode().strip()) / self.tool.JOURNAL_NAME
        self.cut = CandidateCutWorkspace(self.runner)
        self.addCleanup(self.assert_writer_closed)

    def assert_writer_closed(self):
        self.assertIsNone(self.tool._journal)
        with snapshot_fixture.RequestJournal(self.journal):
            pass

    def verify_cut(self, root, phase, binding):
        self.verify(root)
        metadata = json.loads((root / f"apps/architecture-portal/versioned_metadata/version-{self.source['product_build']}.json").read_bytes())
        self.assertEqual(metadata["revision"], self.source["commit"])
        self.assertEqual(self.tool.revision_from_index(), binding["tree"])
        self.assertEqual(self.tool.revision("HEAD"), self.source["commit"] if phase == "staged" else binding["commit"])
        self.phases.append(phase)

    def prepare_cut(self, **changes):
        arguments = dict(request=self.request, source=self.source, snapshot_sha256=self.receipt["sha256"],
            author_name="Fixture", author_email="fixture@example.invalid", timestamp=2000000000,
            verify=self.verify_cut)
        arguments.update(changes)
        return self.cut.prepare(**arguments)


class CutRecoveryTest(CutFixture):
    def test_zero_exit_without_postcommand_authority_cannot_admit_cut(self):
        calls = 0
        def refuse_last(scope):
            nonlocal calls
            calls += 1
            if calls == 3: raise PermissionError("fixture")
        self.runner.authorize = refuse_last
        with self.assertRaises(snapshot_fixture.CandidateSnapshotError):
            self.run_snapshot()
        state = json.loads((self.journal / "snapshot-state.json").read_bytes())["state"]
        self.assertEqual(state["commands"][-1]["result"][0], 0)
        self.assertLess(state["verified_command_count"], len(state["commands"]))
        self.runner.authorize = self.authorities.append
        with self.assertRaises(CandidateCutError):
            self.prepare_cut()
        self.assertEqual(self.tool.revision("HEAD"), self.source["commit"])
        self.assertFalse((self.journal / "cut-binding.json").exists())

    def test_one_complete_cut_and_revalidation_preserve_source(self):
        first = self.prepare_cut()
        self.assertEqual(first["status"], "cut-committed")
        self.assertEqual(self.tool.revision("HEAD^"), self.fixture.base)
        self.assertEqual(self.tool.revision(first["source_retention_ref"]), self.source["commit"])
        self.assertEqual(self.tool.git("status", "--porcelain"), b"")
        self.assertEqual(set(first["files"]), snapshot_fixture.fixture_module.FILES | {
            "apps/architecture-portal/versions.json",
            f"apps/architecture-portal/versioned_metadata/version-{self.source['product_build']}.json"})
        self.assertEqual(self.phases, ["staged", "committed"])
        with patch.object(self.tool, "git", wraps=self.tool.git) as git:
            self.assertEqual(self.prepare_cut(), first)
        self.assertFalse(any(call.args[0] == "update-ref" for call in git.call_args_list))
        self.assertEqual(self.phases, ["staged", "committed", "committed"])
        self.assertEqual(self.commands(), ["version", "resume"])

    def test_failed_staged_verification_keeps_original_head_and_recovers(self):
        def fail(*args): raise RuntimeError("fixture-secret")
        with self.assertRaisesRegex(CandidateCutError, "Task verification failed") as caught:
            self.prepare_cut(verify=fail)
        self.assertNotIn("fixture-secret", str(caught.exception))
        self.assertEqual(self.tool.revision("HEAD"), self.source["commit"])
        staged = self.tool.revision_from_index()
        self.assertEqual(self.prepare_cut()["tree"], staged)
        self.assertEqual(self.commands(), ["version", "resume"])

    def _death(self, after_index):
        child = os.fork()
        if child == 0:
            original = self.tool.git
            def crash(*args, **kwargs):
                result = original(*args, **kwargs)
                if ((after_index and args[0] == "read-tree" and "index" not in kwargs)
                    or (not after_index and args[0] == "update-ref" and args[1].startswith("refs/heads/"))):
                    os._exit(26)
                return result
            with patch.object(self.tool, "git", side_effect=crash):
                self.prepare_cut()
            os._exit(99)
        _, child_status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(child_status), 26)

    def test_process_death_after_staging_resumes_same_tree(self):
        self._death(True)
        staged = self.tool.revision_from_index()
        self.assertEqual(self.tool.revision("HEAD"), self.source["commit"])
        self.assertEqual(self.prepare_cut()["tree"], staged)
        self.assertEqual(self.commands(), ["version", "resume"])

    def test_process_death_after_ref_update_revalidates_existing_commit(self):
        self._death(False)
        committed = self.tool.revision("HEAD")
        self.assertEqual(self.prepare_cut()["commit"], committed)
        self.assertEqual(self.phases, ["committed"])
        self.assertEqual(self.commands(), ["version", "resume"])


class CutSafetyTest(CutFixture):
    def test_legacy_snapshot_state_is_not_upgraded_into_cut_evidence(self):
        filename = self.journal / "snapshot-state.json"
        state = json.loads(filename.read_bytes())["state"]
        state["schema"] = "lmdj.candidate-snapshot-run.v1"
        del state["verified_command_count"]
        with snapshot_fixture.RequestJournal(self.journal) as journal:
            self.runner._save(journal, state)
        legacy = filename.read_bytes()
        with self.assertRaises(CandidateCutError):
            self.prepare_cut()
        self.assertEqual(filename.read_bytes(), legacy)
        self.assertEqual(self.tool.revision("HEAD"), self.source["commit"])
        self.assertEqual(self.tool.revision_from_index(), self.source["tree"])
        self.assertFalse((self.journal / "cut-binding.json").exists())
        self.assertEqual(self.commands(), ["version", "resume"])

    def test_snapshot_drift_is_preserved_without_staging(self):
        filename = self.root / "apps/architecture-portal/versions.json"
        filename.write_bytes(b"drift")
        with self.assertRaisesRegex(CandidateCutError, "snapshot bytes changed"):
            self.prepare_cut()
        self.assertEqual(filename.read_bytes(), b"drift")
        self.assertEqual(self.tool.revision_from_index(), self.source["tree"])

    def test_unrelated_untracked_file_is_not_committed_or_removed(self):
        filename = self.root / "unknown-file"
        filename.write_bytes(b"retained")
        with self.assertRaisesRegex(CandidateCutError, "unrelated untracked"):
            self.prepare_cut()
        self.assertEqual(filename.read_bytes(), b"retained")
        self.assertEqual(self.tool.revision("HEAD"), self.source["commit"])

    def test_backdated_cut_refuses_before_staging(self):
        with self.assertRaisesRegex(CandidateCutError, "precedes snapshot freeze"):
            self.prepare_cut(timestamp=1730000000)
        self.assertEqual(self.tool.revision_from_index(), self.source["tree"])

    def test_retention_collision_is_not_overwritten(self):
        retention = "refs/lmdj/release-sources/" + self.source["operation_id"]
        self.tool.git("update-ref", retention, self.fixture.base)
        with self.assertRaisesRegex(CandidateCutError, "retention ref changed"):
            self.prepare_cut()
        self.assertEqual(self.tool.revision(retention), self.fixture.base)
        self.assertEqual(self.tool.revision("HEAD"), self.source["commit"])

    def test_missing_cut_binding_after_staging_cannot_reenroll(self):
        def fail(*args): raise RuntimeError("fixture")
        with self.assertRaises(CandidateCutError): self.prepare_cut(verify=fail)
        (self.journal / "cut-binding.json").unlink()
        with self.assertRaisesRegex(CandidateCutError, "binding is missing after staging"):
            self.prepare_cut()
        self.assertEqual(self.tool.revision("HEAD"), self.source["commit"])

    def test_failed_postcommit_check_retains_commit_and_reverifies(self):
        def fail(root, phase, binding):
            self.verify_cut(root, phase, binding)
            if phase == "committed": raise RuntimeError("fixture")
        with self.assertRaisesRegex(CandidateCutError, "Task verification failed"):
            self.prepare_cut(verify=fail)
        committed = self.tool.revision("HEAD")
        self.assertNotEqual(committed, self.source["commit"])
        self.assertEqual(self.prepare_cut()["commit"], committed)
        self.assertEqual(self.commands(), ["version", "resume"])


if __name__ == "__main__":
    unittest.main()
