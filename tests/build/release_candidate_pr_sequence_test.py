#!/usr/bin/env python3
"""Real temporary Git branch plus durable PR/HTTP fixture composition."""
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

import release_candidate_branch_test as branch_fixture
import release_candidate_pr_test as pr_fixture
from tools.release.candidate_branch import CandidateBranch
from tools.release.candidate_pr import pr_document
from tools.release.candidate_pr_sequence import CandidatePrSequence, CandidateSequenceError
from tools.release.model import canonical_json
from tools.release.evidence_pr import EvidencePrError
from tools.release.orchestration import JournalError, RequestJournal


class SequenceFixture(unittest.TestCase):
    def setUp(self):
        self.b = branch_fixture.CandidateBranchTest()
        self.b.setUp()
        self.addCleanup(self.b.doCleanups)
        self.p = pr_fixture.CandidatePrTest()
        self.p.setUp()
        self.addCleanup(self.p.doCleanups)
        self.root = self.b.root / "sequence"
        self.b.journal, self.p.root = self.root / "branch", self.root / "pr"
        self.p.spec = deepcopy(self.b.spec)
        self.p.document = pr_document(self.p.spec)
        self.sequence = self.new_sequence()
        self.parent_authorized = True

    def new_sequence(self):
        branch = CandidateBranch(self.b.journal, self.b.repo, token="SECRET-TOKEN", authorize=self.b.authorize)
        branch.api = self.b.api
        return CandidatePrSequence(self.root, branch=branch, pr=self.p.new_controller())

    def call(self, method, **kwargs):
        if method == "advance":
            kwargs.setdefault("before_write", self.parent_guard)
        with patch.object(branch_fixture.fixture.module.subprocess, "run", side_effect=self.b.transport):
            return getattr(self.sequence, method)(self.b.spec, **kwargs)

    def parent_guard(self):
        if not self.parent_authorized:
            raise CandidateSequenceError("SECRET-PARENT-AUTH")


class SequenceTest(SequenceFixture):
    def test_initialize_branch_pr_merge_and_cold_observation(self):
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertFalse(self.p.calls)
        self.assertEqual(self.call("observe", initialize=True)["status"], "absent")
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.writes())
        result = self.call("advance")
        self.assertEqual(result["status"], "merged")
        self.assertEqual(self.b.remote_sha(), self.b.spec["head_sha"])
        self.assertEqual(self.b.pushes, 1)
        self.assertEqual([row[0] for row in self.p.writes()], ["POST", "PUT"])
        self.sequence = self.new_sequence()
        self.assertEqual(self.call("observe"), result)
        self.assertEqual(self.call("advance"), result)
        self.assertEqual(self.b.pushes, 1)
        self.assertEqual(len(self.p.writes()), 2)

    def test_unknown_branch_stops_pr_and_adopts_late_effect(self):
        self.call("observe", initialize=True)
        self.b.mode = "before"
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.b.mode = None
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertFalse(self.p.calls)
        self.b.git("-C", str(self.b.repo), "push", str(self.b.remote), self.b.spec["head_sha"] + ":" + self.b.ref)
        self.assertEqual(self.call("advance")["status"], "merged")
        self.assertEqual(self.b.pushes, 1)

    def test_missing_started_branch_cannot_be_reenrolled(self):
        self.call("observe", initialize=True)
        (self.b.journal / "branch-state.json").unlink()
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertEqual(self.call("observe", initialize=True)["status"], "unknown")
        self.assertFalse((self.b.journal / "branch-state.json").exists())
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.calls)

    def test_missing_started_pr_cannot_be_reenrolled(self):
        self.call("observe", initialize=True)
        self.p.review_state = "pending"
        self.assertEqual(self.call("advance")["status"], "pending")
        (self.p.root / "pr-state.json").unlink()
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertEqual(self.call("observe", initialize=True)["status"], "unknown")
        self.assertFalse((self.p.root / "pr-state.json").exists())
        self.assertEqual(len(self.p.writes()), 1)
        self.assertEqual(self.b.pushes, 1)

    def test_pending_review_resumes_same_pr_without_another_branch_write(self):
        self.call("observe", initialize=True)
        self.p.review_state = "pending"
        self.assertEqual(self.call("advance")["status"], "pending")
        self.assertEqual(self.call("advance")["status"], "pending")
        self.assertEqual(len(self.p.writes()), 1)
        self.p.review_state = "verified"
        self.assertEqual(self.call("advance")["status"], "merged")
        self.assertEqual(self.b.pushes, 1)

    def test_process_death_after_branch_before_pr_initialization_resumes_next_leg(self):
        self.call("observe", initialize=True)
        original = CandidatePrSequence._save
        def stop(journal, state, phase):
            original(journal, state, phase)
            if phase == "pr-initializing": os._exit(33)
        pid = os.fork()
        if pid == 0:
            with patch.object(CandidatePrSequence, "_save", side_effect=stop):
                self.call("advance")
            os._exit(99)
        _, child_status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(child_status), 33)
        self.assertEqual(self.b.remote_sha(), self.b.spec["head_sha"])
        self.sequence = self.new_sequence()
        self.assertEqual(self.call("advance")["status"], "merged")
        self.assertEqual(self.b.pushes, 0)  # Original write occurred in the child.
        self.assertEqual([row[0] for row in self.p.writes()], ["POST", "PUT"])

    def test_rebound_or_corrupt_parent_never_recreates_state(self):
        self.call("observe", initialize=True)
        filename = self.root / "candidate-pr-sequence.json"
        before = filename.read_bytes()
        self.b.spec["task_evidence_sha256"] = "f" * 64
        with self.assertRaises(CandidateSequenceError):
            self.call("observe", initialize=True)
        self.assertEqual(filename.read_bytes(), before)
        filename.write_bytes(b"{broken SECRET}")
        self.assertEqual(self.call("observe", initialize=True)["status"], "unknown")
        self.assertEqual(filename.read_bytes(), b"{broken SECRET}")
        self.assertEqual(self.b.pushes, 0)

    def test_merged_api_without_far_side_proof_is_not_completion(self):
        self.call("observe", initialize=True)
        self.p.merged_state = "unknown"
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertTrue(self.p.row["merged"])
        self.p.merged_state = "verified"
        self.assertEqual(self.call("observe")["status"], "merged")
        self.assertEqual(len(self.p.writes()), 2)

    def test_missing_parent_cannot_be_reenrolled(self):
        self.call("observe", initialize=True)
        filename = self.root / "candidate-pr-sequence.json"
        filename.unlink()
        with self.assertRaisesRegex(CandidateSequenceError, "enrolled.*state is missing"):
            self.call("observe", initialize=True)
        self.assertFalse(filename.exists())
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.calls)

    def test_oversized_document_cannot_enroll_parent(self):
        self.b.spec["product_build"] = "1" * 20000 + ".0.0.0"
        with self.assertRaises(EvidencePrError):
            self.call("observe", initialize=True)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.calls)

    def test_parent_binding_rejects_equal_numeric_value_with_changed_type(self):
        self.call("observe", initialize=True)
        filename = self.root / "candidate-pr-sequence.json"
        state = json.loads(filename.read_bytes())
        state["spec"]["repository_id"] = float(state["spec"]["repository_id"])
        before = canonical_json(state)
        filename.write_bytes(before)
        with self.assertRaises(CandidateSequenceError):
            self.call("advance")
        self.assertEqual(filename.read_bytes(), before)
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.calls)


class BoundaryTest(SequenceFixture):
    def test_parent_state_is_rechecked_after_outer_guard(self):
        self.call("observe", initialize=True)
        filename = self.root / "candidate-pr-sequence.json"
        self.assertEqual(self.call("advance", before_write=filename.unlink)["status"], "unknown")
        self.assertFalse(filename.exists())
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.calls)
        with self.assertRaisesRegex(CandidateSequenceError, "enrolled.*state is missing"):
            self.call("observe", initialize=True)

    def test_parent_guard_is_mandatory(self):
        with self.assertRaisesRegex(CandidateSequenceError, "final parent guard"):
            self.call("advance", before_write=None)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.calls)

    def test_death_after_parent_enrollment_does_not_reinitialize(self):
        pid = os.fork()
        if pid == 0:
            with patch.object(CandidatePrSequence, "_save", side_effect=lambda *_: os._exit(35)):
                self.call("observe", initialize=True)
            os._exit(99)
        _, wait_status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(wait_status), 35)
        self.assertEqual((self.root / "sequence-enrolled").read_bytes(), b"")
        self.assertFalse((self.root / "candidate-pr-sequence.json").exists())
        with self.assertRaisesRegex(CandidateSequenceError, "enrolled.*state is missing"):
            self.call("observe", initialize=True)
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.calls)

    def test_existing_parent_requires_enrollment_marker(self):
        self.call("observe", initialize=True)
        filename = self.root / "candidate-pr-sequence.json"
        original = filename.read_bytes()
        (self.root / "sequence-enrolled").unlink()
        with self.assertRaisesRegex(CandidateSequenceError, "enrollment marker is missing"):
            self.call("advance")
        self.assertEqual(filename.read_bytes(), original)
        self.assertEqual(self.b.pushes, 0)

    def test_corrupt_parent_enrollment_marker_refused(self):
        self.call("observe", initialize=True)
        (self.root / "sequence-enrolled").write_bytes(b"bad")
        with self.assertRaisesRegex(CandidateSequenceError, "enrollment marker is corrupt"):
            self.call("advance")
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.calls)

    def test_public_parent_enrollment_marker_refused(self):
        self.call("observe", initialize=True)
        (self.root / "sequence-enrolled").chmod(0o644)
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.calls)

    def test_oversized_parent_state_preserves_original(self):
        self.call("observe", initialize=True)
        filename = self.root / "candidate-pr-sequence.json"
        original = filename.read_bytes()
        inventory = sorted(p.name for p in self.root.iterdir())
        state = json.loads(original)
        state["spec"]["product_build"] = "1" * 65536 + ".0.0.0"
        with RequestJournal(self.root) as journal:
            with self.assertRaisesRegex(CandidateSequenceError, "state exceeds"):
                CandidatePrSequence._save(journal, state, "pr")
        self.assertEqual(state["phase"], "branch")
        self.assertEqual(filename.read_bytes(), original)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), inventory)

    def _lost_parent(self, boundary, fault):
        self.call("observe", initialize=True)
        faulted = False
        def invalidate():
            nonlocal faulted
            faulted = True
            if fault == "authority":
                self.parent_authorized = False
            else:
                (self.root / "writer.lock").rename(self.root / "retained.lock")
                fd = os.open(self.root / "writer.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
        if boundary == "push":
            real = self.sequence.branch._authorize
            def authorize(spec):
                real(spec)
                state = json.loads((self.b.journal / "branch-state.json").read_bytes())
                if not faulted and state["claimed"]:
                    invalidate()
            self.sequence.branch._authorize = authorize
        else:
            real = self.sequence.pr._request
            def request(method, route, document=None):
                result = real(method, route, document)
                filename = self.p.root / "pr-state.json"
                if not faulted and method == "GET" and route == "/branches/main" and filename.exists():
                    state = json.loads(filename.read_bytes())
                    if state[boundary + "_intent"]:
                        invalidate()
                return result
            self.sequence.pr._request = request
        try:
            self.assertEqual(self.call("advance")["status"], "unknown")
        except JournalError:
            pass  # A replaced live writer can also refuse context exit.
        self.assertTrue(faulted)
        expected = ["POST"] if boundary == "merge" else []
        self.assertEqual([row[0] for row in self.p.writes()], expected)
        self.assertEqual(self.b.pushes, 0 if boundary == "push" else 1)
        filename = (self.b.journal / "branch-state.json" if boundary == "push"
                    else self.p.root / "pr-state.json")
        original = filename.read_bytes()
        self.assertTrue(json.loads(original)["claimed" if boundary == "push" else boundary + "_intent"])
        self.parent_authorized = True
        self.sequence = self.new_sequence()
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertEqual(filename.read_bytes(), original)
        self.assertEqual([row[0] for row in self.p.writes()], expected)
        self.assertEqual(self.b.pushes, 0 if boundary == "push" else 1)

    def test_lost_authority_before_push(self):
        self._lost_parent("push", "authority")

    def test_lost_authority_before_post(self):
        self._lost_parent("create", "authority")

    def test_lost_authority_before_put(self):
        self._lost_parent("merge", "authority")

    def test_replaced_writer_before_push(self):
        self._lost_parent("push", "writer")

    def test_replaced_writer_before_post(self):
        self._lost_parent("create", "writer")

    def test_replaced_writer_before_put(self):
        self._lost_parent("merge", "writer")


if __name__ == "__main__":
    unittest.main()
