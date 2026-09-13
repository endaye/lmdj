#!/usr/bin/env python3
"""Real retained producer/Task and passive squash proof; no live review."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import release_candidate_witness_task_test as fixture
from tools.release.model import canonical_json, canonical_sha256
from tools.release.witness_source import CandidateWitnessSourceVerifier, WitnessSourceError


class SourceFixture(fixture.TaskFixture):
    def setUp(self):
        super().setUp()
        self.task_receipt = self.prepare_task()
        task = self.task_receipt
        self.spec = dict(operation_id=task["operation_id"], request_sha256=task["request_sha256"],
            repository_id=12, actor_id=34, base_revision=task["base_revision"], head_sha=task["commit"],
            tree_sha=task["tree"], product_build=self.source["product_build"], target_revision=task["target_revision"],
            source_sha=self.source["commit"], witness_receipt_sha256=task["receipt_sha256"],
            task_binding_sha256=sha256((self.task_journal / "binding.json").read_bytes()).hexdigest(),
            task_evidence_sha256=canonical_sha256({"fixture_task_phases":self.phases}), witness=task["witness"])
        # Full Task command/review evidence remains an explicit fixture gap.
        self.consumer = CandidateWitnessSourceVerifier(self.task)

    def check(self, *, merge=None, **changes):
        args = dict(receipt=self.receipt, request=self.request, source=self.source, cut=self.cut_receipt,
                    frozen=self.fixture.frozen, main_revision=self.main, merge_revision=merge)
        args.update(changes)
        return self.consumer.verify(self.spec, **args)

    def merge(self, *, parent=None, tree=None):
        parent = self.base if parent is None else parent
        if tree is None:
            tree = self.changed_tree(parent, self.witness_name, self.artifact.read_bytes())
        merged = self.commit_tree(tree, parent)
        self.main = merged
        return merged

    def identities(self):
        return tuple(local.git(*args) for local in (self.tool, self.task)
                     for args in (("rev-parse", "HEAD"), ("ls-files", "--stage", "-z"), ("show-ref",))) + (
            (self.journal / "witness-state.json").read_bytes(),
            (self.task_journal / "binding.json").read_bytes(), self.artifact.read_bytes())


class SourceBindingTest(SourceFixture):
    def test_actual_receipt_and_task_cold_proof_do_not_reexecute_or_change_identity(self):
        before, commands = self.identities(), self.witness_calls()
        first = self.check()
        self.consumer = CandidateWitnessSourceVerifier(self.task)
        self.assertEqual(self.check(), first)
        self.assertIsNone(first["merge_sha"])
        self.assertEqual(first["head_sha"], self.task_receipt["commit"])
        self.assertEqual(first["witness"], self.receipt["receipt"]["witness"])
        self.assertEqual(self.identities(), before)
        self.assertEqual(self.witness_calls(), commands)

    def test_forged_binding_digest_is_rejected(self):
        self.spec["task_binding_sha256"] = "a" * 64
        with self.assertRaisesRegex(WitnessSourceError, "Task binding changed"): self.check()

    def test_missing_binding_is_not_recreated(self):
        filename = self.task_journal / "binding.json"
        filename.unlink()
        with self.assertRaisesRegex(WitnessSourceError, "why:.*remedy:"): self.check()
        self.assertFalse(filename.exists())

    def test_rebound_original_command_receipt_is_rejected(self):
        changed = deepcopy(self.receipt)
        changed["command_history_sha256"] = "b" * 64
        self.spec["witness_receipt_sha256"] = canonical_sha256(changed)
        with self.assertRaises(WitnessSourceError): self.check(receipt=changed)

    def test_consistently_rebound_task_cannot_include_an_extra_file(self):
        tree = self.changed_tree(self.task_receipt["tree"], "docs/plans/extra.md", b"not witness")
        head = self.commit_tree(tree, self.base)
        # Mutate only this disposable fixture, making every claimed Task
        # identity agree. The consumer must still check actual tree construction.
        self.task.git("read-tree", "--reset", "-u", head)
        self.task.git("update-ref", "HEAD", head, self.spec["head_sha"])
        bound = json.loads((self.task_journal / "binding.json").read_bytes())
        bound.update(tree=tree, commit=head)
        for name in ("binding.json", "task-operation.json"):
            (self.task_journal / name).write_bytes(canonical_json(bound))
        self.spec.update(tree_sha=tree, head_sha=head, task_binding_sha256=canonical_sha256(bound))
        with self.assertRaisesRegex(WitnessSourceError, "Task is not base plus only"):
            self.check()


class SourceMergeTest(SourceFixture):
    def test_real_squash_on_later_parent_and_later_main_keep_original_candidate(self):
        parent = self.commit_tree(self.changed_tree(self.base, "docs/plans/later-parent.md", b"keep parent"), self.base)
        merged = self.merge(parent=parent)
        self.main = self.commit_tree(self.changed_tree(merged, "docs/plans/later-main.md", b"keep main"), merged)
        before = self.identities()
        result = self.check(merge=merged)
        self.assertEqual(result["target_revision"], self.merged)
        self.assertEqual(result["merge_parent"], parent)
        self.assertEqual(result["observed_main"], self.main)
        self.assertEqual(result["merge_sha"], merged)
        self.assertEqual(self.identities(), before)

    def test_changed_merged_blob_is_rejected(self):
        merged = self.merge(tree=self.changed_tree(self.base, self.witness_name, self.artifact.read_bytes() + b" "))
        with self.assertRaisesRegex(WitnessSourceError, "squash differs"): self.check(merge=merged)

    def test_squash_dropping_actual_parent_file_is_rejected(self):
        parent = self.commit_tree(self.changed_tree(self.base, "docs/plans/keep.md", b"keep"), self.base)
        merged = self.merge(parent=parent, tree=self.task_receipt["tree"])
        with self.assertRaisesRegex(WitnessSourceError, "squash differs"): self.check(merge=merged)

    def test_two_parent_commit_is_not_witness_squash(self):
        merged = self.commit_tree(self.task_receipt["tree"], self.base, self.source["commit"])
        self.main = merged
        with self.assertRaisesRegex(WitnessSourceError, "distinct witness squash"): self.check(merge=merged)

    def test_unreachable_merge_is_not_accepted(self):
        merged = self.merge()
        self.main = self.base
        with self.assertRaises(WitnessSourceError): self.check(merge=merged)


class SourceHistoryTest(SourceFixture):
    def test_witness_edit_then_revert_is_rejected_even_with_matching_endpoint(self):
        merged = self.merge()
        edited = self.commit_tree(self.changed_tree(merged, self.witness_name, b"changed"), merged)
        self.main = self.commit_tree(self.task_receipt["tree"], edited)
        self.assertEqual(self.tool.git("cat-file", "blob", self.main + ":" + self.witness_name), self.artifact.read_bytes())
        with self.assertRaisesRegex(WitnessSourceError, "history changed"): self.check(merge=merged)

    def test_snapshot_edit_then_revert_before_witness_is_rejected(self):
        name = self.receipt["receipt"]["metadata"]["path"]
        edited = self.commit_tree(self.changed_tree(self.base, name, b"changed"), self.base)
        reverted = self.commit_tree(self.tool.revision(self.base + "^{tree}"), edited)
        merged = self.merge(parent=reverted)
        with self.assertRaisesRegex(WitnessSourceError, "history changed"): self.check(merge=merged)

    def test_later_version_addition_preserves_unique_candidate(self):
        merged = self.merge()
        name = "apps/architecture-portal/versions.json"
        versions = json.loads(self.tool.git("cat-file", "blob", merged + ":" + name))
        self.main = self.commit_tree(self.changed_tree(merged, name, canonical_json(["1.0.999.0", *versions])), merged)
        self.assertEqual(self.check(merge=merged)["merge_sha"], merged)

    def test_duplicate_candidate_version_is_rejected(self):
        merged = self.merge()
        name = "apps/architecture-portal/versions.json"
        versions = json.loads(self.tool.git("cat-file", "blob", merged + ":" + name))
        self.main = self.commit_tree(self.changed_tree(merged, name, canonical_json(versions * 2)), merged)
        with self.assertRaisesRegex(WitnessSourceError, "duplicated"): self.check(merge=merged)

    def test_same_snapshot_bytes_with_changed_committed_mode_are_rejected(self):
        merged = self.merge()
        name = self.receipt["receipt"]["metadata"]["path"]
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "index"
            self.tool.git("read-tree", merged, index=index)
            self.tool.git("update-index", "--chmod=+x", "--", name, index=index)
            self.main = self.commit_tree(self.tool.revision_from_index(index), merged)
        self.assertEqual(self.tool.git("cat-file", "blob", merged + ":" + name),
                         self.tool.git("cat-file", "blob", self.main + ":" + name))
        with self.assertRaisesRegex(WitnessSourceError, "committed mode changed"):
            self.check(merge=merged)


class SourceAuthorityTest(SourceFixture):
    def test_original_authority_loss_is_not_source_success(self):
        self.witness.authorize = lambda _: (_ for _ in ()).throw(PermissionError("SECRET"))
        with self.assertRaises(WitnessSourceError) as caught: self.check()
        self.assertNotIn("SECRET", str(caught.exception))

    def test_authority_callback_losing_task_binding_is_detected(self):
        original = self.witness.authorize
        removed = []
        def lose(scope):
            original(scope)
            if self.task._journal is not None and not removed:
                (self.task_journal / "binding.json").unlink()
                removed.append(True)
        self.witness.authorize = lose
        with self.assertRaises(WitnessSourceError): self.check()
        self.assertEqual(removed, [True])
        self.assertFalse((self.task_journal / "binding.json").exists())

    def test_hidden_index_change_is_not_verified(self):
        self.task.git("update-index", "--assume-unchanged", "docs/plans/later.md")
        with self.assertRaises(WitnessSourceError): self.check()

    def test_changed_main_observation_does_not_select_another_target(self):
        before = deepcopy(self.spec)
        newer = self.commit_tree(self.changed_tree(self.base, "docs/plans/new.md", b"new"), self.base)
        with patch.object(self.witness, "observe_main", return_value=newer):
            with self.assertRaisesRegex(WitnessSourceError, "main observation changed"): self.check()
        self.assertEqual(self.spec, before)


if __name__ == "__main__":
    unittest.main()
