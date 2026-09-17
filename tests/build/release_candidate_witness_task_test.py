#!/usr/bin/env python3
"""Actual emitted witness -> separate Git Task, no remote review authority."""
import sys
from pathlib import Path
import unittest
from copy import deepcopy
from hashlib import sha256
import json
import os
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.candidate_witness import CandidateWitnessRun
from tools.release.candidate_source import CandidateSourceVerifier
from tools.release.candidate_witness_task import CandidateWitnessTask, WitnessTaskError
from tools.release.model import canonical_json, canonical_sha256
from tools.release.orchestration import RequestJournal
import release_candidate_witness_test as fixture


class TaskFixture(fixture.WitnessFixture):
    def _prepare_seed(self):
        super()._prepare_seed()
        self.verifier = CandidateSourceVerifier(self.cut)
        self.merged = self.commit_tree(self.cut_receipt_seed()["tree"], self.fixture.base)
        self.cut_receipt = self.cut_receipt_seed()
        self.main, self.auth_calls = self.merged, []
        self.witness = self.new_runner()
        type(self).seed_witness_receipt = self.run_witness()
        type(self).seed_merged = self.merged

    def cut_receipt_seed(self):
        return deepcopy(type(self).seed_cut_receipt)

    def setUp(self):
        # Independent copies of a real completed producer. No positive receipt
        # is manufactured, and the consumer under test always runs per case.
        fixture.source_fixture.SourceFixture.setUp(self)
        self.merged = self.seed_merged
        self.main, self.auth_calls = self.merged, []
        self.witness = self.new_runner()
        self.receipt = deepcopy(self.seed_witness_receipt)
        self.witness_name = self.receipt["receipt"]["witness"]["path"]
        self.artifact = self.root / self.witness_name
        self.base = self.commit_tree(self.changed_tree(self.merged, "docs/plans/later.md", b"preserve later main"), self.merged)
        self.main = self.base
        self.operation = canonical_sha256({"request":canonical_sha256(self.request), "step":"candidate-witness"})
        self.task_branch = "docs/release-witness-" + self.operation
        self.destination = self.fixture.container / "witness-task"
        self.tool.git("-c", "core.symlinks=true", "worktree", "add", "-b", self.task_branch, str(self.destination), self.base)
        self.task = CandidateWitnessTask(self.destination, self.witness)
        self.task_journal = Path(self.task.git("rev-parse", "--absolute-git-dir").decode().strip()) / self.task.JOURNAL_NAME
        self.phases = []

    def verify_task(self, root, phase, binding):
        # This contract fixture checks actual Git/blob identities, not full
        # Portal content. The retained Portal journey runs the three real gates.
        self.assertEqual(root, self.destination)
        self.assertEqual((root / self.witness_name).read_bytes(), self.artifact.read_bytes())
        self.assertEqual(self.task.revision_from_index(), binding["tree"])
        self.assertEqual(self.task.revision("HEAD"), self.base if phase == "staged" else binding["commit"])
        self.assertEqual(self.task.git("diff-tree", "--no-commit-id", "--name-only", "-r", self.base, binding["tree"]),
                         (self.witness_name + "\n").encode())
        self.phases.append(phase)

    def prepare_task(self, **changes):
        args = dict(receipt=self.receipt, base_revision=self.base, request=self.request,
            source=self.source, cut=self.cut_receipt, frozen=self.fixture.frozen,
            merge_revision=self.merged, author_name="Fixture", author_email="fixture@example.invalid",
            timestamp=2100000000, verify=self.verify_task)
        args.update(changes)
        return self.task.prepare(**args)

    def cold_task(self):
        self.witness = self.new_runner()
        self.task = CandidateWitnessTask(self.destination, self.witness)

    def crash(self, stage):
        child = os.fork()
        if child == 0:
            if stage == "marker":
                original = RequestJournal._write
                def write(journal, name, raw):
                    original(journal, name, raw)
                    if name == "task-operation.json": os._exit(28)
                patch.object(RequestJournal, "_write", write).start()
            elif stage == "install":
                original = self.task._install
                def install(*args):
                    original(*args)
                    os._exit(28)
                self.task._install = install
            else:
                original = self.task.git
                def git(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if args[0] == "update-ref": os._exit(28)
                    return result
                self.task.git = git
            self.prepare_task()
            os._exit(99)
        _, wait_status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(wait_status), 28)


class TaskLifecycleTest(TaskFixture):
    def test_exact_bytes_commit_and_cold_resume_preserve_candidate_and_later_main(self):
        before = self.tool.revision("HEAD"), (self.journal / "witness-state.json").read_bytes(), self.artifact.read_bytes()
        first = self.prepare_task()
        self.assertEqual(first["target_revision"], self.merged)
        self.assertEqual(self.task.revision("HEAD^"), self.base)
        self.assertEqual(first["witness"], self.receipt["receipt"]["witness"])
        self.assertEqual(self.task.git("cat-file", "blob", first["commit"] + ":" + self.witness_name), before[2])
        self.assertEqual((self.destination / "docs/plans/later.md").read_bytes(), b"preserve later main")
        self.cold_task()
        with patch.object(self.task, "git", wraps=self.task.git) as git:
            self.assertEqual(self.prepare_task(), first)
        self.assertFalse(any(call.args[0] == "update-ref" for call in git.call_args_list))
        self.assertEqual(self.phases, ["staged", "committed", "committed"])
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        self.assertEqual((self.tool.revision("HEAD"), (self.journal / "witness-state.json").read_bytes(), self.artifact.read_bytes()), before)
        self.assertEqual(self.task.git("status", "--porcelain"), b"")

    def test_failed_staged_check_retains_bytes_and_resumes_same_commit(self):
        def fail(*unused): raise ValueError("fixture-secret")
        with self.assertRaises(WitnessTaskError) as caught:
            self.prepare_task(verify=fail)
        self.assertNotIn("fixture-secret", str(caught.exception))
        self.assertEqual(self.task.revision("HEAD"), self.base)
        bound = json.loads((self.task_journal / "binding.json").read_bytes())
        self.cold_task()
        self.assertEqual(self.prepare_task()["commit"], bound["commit"])

    def test_failed_committed_check_is_not_rollback_or_success(self):
        def fail(root, phase, binding):
            self.verify_task(root, phase, binding)
            if phase == "committed": raise ValueError("fixture")
        with self.assertRaises(WitnessTaskError): self.prepare_task(verify=fail)
        committed = self.task.revision("HEAD")
        self.assertNotEqual(committed, self.base)
        self.cold_task()
        self.assertEqual(self.prepare_task()["commit"], committed)
        self.assertEqual(self.phases, ["staged", "committed", "committed"])

    def test_actual_process_death_after_ref_update_keeps_same_commit(self):
        self.crash("ref")
        committed = self.task.revision("HEAD")
        self.assertNotEqual(committed, self.base)
        self.cold_task()
        self.assertEqual(self.prepare_task()["commit"], committed)
        self.assertEqual(self.phases, ["committed"])


class TaskBoundaryTest(TaskFixture):
    def test_changed_receipt_is_rejected_before_enrollment(self):
        changed = deepcopy(self.receipt)
        changed["command_history_sha256"] = "a" * 64
        with self.assertRaises(WitnessTaskError): self.prepare_task(receipt=changed)
        self.assertFalse((self.task_journal / "task-operation.json").exists())
        self.assertFalse((self.destination / self.witness_name).exists())

    def test_unconfirmed_last_command_is_not_consumed(self):
        state = self.state()
        state["confirmed"] = 0
        with RequestJournal(self.journal) as journal: self.witness._save(journal, state)
        with self.assertRaises(WitnessTaskError): self.prepare_task()
        self.assertFalse((self.destination / self.witness_name).exists())

    def test_unrelated_dirty_destination_is_preserved(self):
        filename = self.destination / "docs/plans/later.md"
        filename.write_bytes(b"keep dirty")
        with self.assertRaises(WitnessTaskError): self.prepare_task()
        self.assertEqual(filename.read_bytes(), b"keep dirty")
        self.assertEqual(self.task.revision("HEAD"), self.base)
        self.assertFalse((self.task_journal / "task-operation.json").exists())

    def test_preexisting_wrong_witness_is_not_overwritten(self):
        filename = self.destination / self.witness_name
        filename.write_bytes(b"keep wrong")
        with self.assertRaises(WitnessTaskError): self.prepare_task()
        self.assertEqual(filename.read_bytes(), b"keep wrong")
        self.assertFalse((self.task_journal / "task-operation.json").exists())

    def test_base_metadata_drift_is_not_accepted(self):
        name = self.receipt["receipt"]["metadata"]["path"]
        altered = self.commit_tree(self.changed_tree(self.base, name, b"changed"), self.base)
        self.task.git("update-ref", "refs/heads/" + self.task_branch, altered, self.base)
        self.task.git("read-tree", "--reset", "-u", altered)
        self.base = self.main = altered
        with self.assertRaisesRegex(WitnessTaskError, "immutable snapshot bytes changed"):
            self.prepare_task()
        self.assertFalse((self.task_journal / "task-operation.json").exists())


class TaskAuthorityTest(TaskFixture):
    def lost_enrollment(self, name):
        before_index = self.task.revision_from_index()
        original = self.witness.authorize
        removed = []
        def lose(scope):
            original(scope)
            filename = self.task_journal / name
            if not removed and filename.exists() and (self.task_journal / "binding.json").exists():
                filename.unlink()
                removed.append(True)
        self.witness.authorize = lose
        with self.assertRaises(WitnessTaskError): self.prepare_task()
        self.assertEqual(removed, [True])
        self.assertEqual(self.task.revision("HEAD"), self.base)
        self.assertEqual(self.task.revision_from_index(), before_index)
        self.assertFalse((self.destination / self.witness_name).exists())

    def test_lost_binding_at_final_guard_prevents_checkout_writes(self):
        self.lost_enrollment("binding.json")

    def test_lost_marker_at_final_guard_prevents_checkout_writes(self):
        self.lost_enrollment("task-operation.json")

    def test_source_artifact_drift_during_check_blocks_commit(self):
        def change(*args):
            self.verify_task(*args)
            self.artifact.write_bytes(self.artifact.read_bytes() + b"\n")
        with self.assertRaises(WitnessTaskError): self.prepare_task(verify=change)
        self.assertEqual(self.task.revision("HEAD"), self.base)

    def test_original_authority_loss_during_check_blocks_commit(self):
        def lose(*args):
            self.verify_task(*args)
            self.witness.authorize = lambda _: (_ for _ in ()).throw(PermissionError("fixture-secret"))
        with self.assertRaises(WitnessTaskError): self.prepare_task(verify=lose)
        self.assertEqual(self.task.revision("HEAD"), self.base)

    def test_missing_binding_after_enrollment_cannot_reenroll(self):
        self.prepare_task()
        (self.task_journal / "binding.json").unlink()
        self.cold_task()
        with self.assertRaisesRegex(WitnessTaskError, "binding disappeared"):
            self.prepare_task()
        self.assertFalse((self.task_journal / "binding.json").exists())

    def test_index_hidden_by_callback_blocks_commit(self):
        def hide(*args):
            self.verify_task(*args)
            self.task.git("update-index", "--assume-unchanged", "docs/plans/later.md")
        with self.assertRaises(WitnessTaskError): self.prepare_task(verify=hide)
        self.assertEqual(self.task.revision("HEAD"), self.base)


class TaskCrashTest(TaskFixture):
    def test_actual_process_death_after_installation_recovers_exact_bytes(self):
        self.crash("install")
        self.assertEqual(self.task.revision("HEAD"), self.base)
        before = (self.destination / self.witness_name).read_bytes()
        self.cold_task()
        self.prepare_task()
        self.assertEqual((self.destination / self.witness_name).read_bytes(), before)
        self.assertEqual(self.phases, ["staged", "committed"])

    def test_actual_process_death_after_marker_refuses_reenrollment(self):
        self.crash("marker")
        self.cold_task()
        with self.assertRaisesRegex(WitnessTaskError, "binding disappeared"):
            self.prepare_task()
        self.assertEqual(self.task.revision("HEAD"), self.base)
        self.assertFalse((self.destination / self.witness_name).exists())

    def test_scope_change_after_failure_is_not_a_new_task(self):
        def fail(*unused): raise ValueError("fixture")
        with self.assertRaises(WitnessTaskError): self.prepare_task(verify=fail)
        bound = (self.task_journal / "binding.json").read_bytes()
        with self.assertRaisesRegex(WitnessTaskError, "enrollment changed"):
            self.prepare_task(timestamp=2100000001)
        self.assertEqual((self.task_journal / "binding.json").read_bytes(), bound)


class ArtifactCaptureTest(unittest.TestCase):
    def test_capture_keeps_the_official_upper_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with (root / "witness").open("wb") as stream:
                stream.truncate(64 * 1024 * 1024 + 1)
            with self.assertRaises(fixture.CandidateWitnessError):
                CandidateWitnessRun._read_artifact(root, "witness", capture=True)

    def test_capture_preserves_full_bytes_above_publication_file_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            raw = b"w" * (8 * 1024 * 1024 + 1)
            (root / "witness").write_bytes(raw)
            fact, captured = CandidateWitnessRun._read_artifact(root, "witness", capture=True)
            self.assertEqual(captured, raw)
            self.assertEqual(fact, {"path":"witness", "bytes":len(raw), "sha256":sha256(raw).hexdigest()})

    def test_capture_refuses_links_instead_of_reading_their_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "target").write_bytes(b"keep")
            (root / "witness").symlink_to("target")
            with self.assertRaises(OSError):
                CandidateWitnessRun._read_artifact(root, "witness", capture=True)
            self.assertEqual((root / "target").read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
