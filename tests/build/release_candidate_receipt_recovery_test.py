#!/usr/bin/env python3
"""Passive producer receipts for the candidate parent; no live GitHub proof."""
from copy import deepcopy
from pathlib import Path
import sys
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/build"))
import release_evidence_pr_test as pr_fixture
import release_candidate_witness_test as witness_fixture
from tools.release.candidate_witness import CandidateWitnessError
from tools.release.evidence_pr import EvidencePrError


class MergeReceiptTest(unittest.TestCase):
    def setUp(self):
        self.pr = pr_fixture.PrTest()
        self.pr.setUp()
        self.addCleanup(self.pr.doCleanups)

    def test_absent_observation_never_enrolls_or_exposes_a_target(self):
        self.assertEqual(self.pr.controller.observe_merge(self.pr.spec),
                         dict(status="unknown", evidence=None, merge=None))
        self.assertFalse((self.pr.root / "pr-state.json").exists())
        self.assertEqual(self.pr.writes(), [])

    def test_cold_verified_observation_binds_actual_numeric_pr_and_squash(self):
        self.pr.advance()
        raw = (self.pr.root / "pr-state.json").read_bytes()
        writes = deepcopy(self.pr.writes())
        cold = self.pr.new_controller()
        result = cold.observe_merge(self.pr.spec)
        self.assertEqual(result, dict(status="verified", evidence=dict(sha256="5" * 64,
            reference="merged:fixture"), merge=dict(id=101, number=99,
                head_sha=self.pr.spec["head_sha"], merge_sha="e" * 40)))
        self.assertNotEqual(result["merge"]["head_sha"], result["merge"]["merge_sha"])
        self.assertEqual(cold.observe(self.pr.spec), {k:v for k,v in result.items() if k != "merge"})
        self.assertEqual((self.pr.root / "pr-state.json").read_bytes(), raw)
        self.assertEqual(self.pr.writes(), writes)

    def test_api_merge_without_verified_gate_never_exposes_a_target(self):
        self.pr.advance()
        self.pr.merged_state = "conflict"
        self.assertEqual(self.pr.controller.observe_merge(self.pr.spec),
                         dict(status="conflict", evidence=None, merge=None))

    def test_numeric_identity_change_during_gate_is_refused(self):
        self.pr.advance()
        original = self.pr.controller.verify_merged
        def changed(*args):
            result = original(*args)
            self.pr.row["id"] += 1
            return result
        self.pr.controller.verify_merged = changed
        with self.assertRaisesRegex(EvidencePrError, "merged identity changed"):
            self.pr.controller.observe_merge(self.pr.spec)
        self.assertEqual([row[0] for row in self.pr.writes()], ["POST", "PUT"])

    def test_private_state_deleted_by_gate_is_not_a_verified_merge(self):
        self.pr.advance()
        original = self.pr.controller.verify_merged
        def lost(*args):
            result = original(*args)
            (self.pr.root / "pr-state.json").unlink()
            return result
        self.pr.controller.verify_merged = lost
        with self.assertRaisesRegex(EvidencePrError, "enrolled PR state is missing"):
            self.pr.controller.observe_merge(self.pr.spec)
        self.assertFalse((self.pr.root / "pr-state.json").exists())


class WitnessReceiptTest(witness_fixture.WitnessFixture):
    def observe(self):
        return self.witness.observe(request=self.request, source=self.source, cut=self.cut_receipt,
            frozen=self.fixture.frozen, merge_revision=self.merged)

    def test_absence_is_passive_and_does_not_create_a_marker(self):
        self.assertEqual(self.observe(), dict(status="absent", receipt=None))
        self.assertFalse((self.journal / "witness-operation.json").exists())
        self.assertFalse((self.journal / "witness-state.json").exists())
        self.assertEqual(self.witness_calls(), [])

    def test_authority_exception_cannot_leak_through_full_traceback(self):
        def authority(scope):
            raise CandidateWitnessError("PRIVATE-AUTHORITY")
        self.witness = self.new_runner(authorize=authority)
        with self.assertRaises(CandidateWitnessError) as failure:
            self.observe()
        self.assertNotIn("PRIVATE-AUTHORITY", "".join(traceback.format_exception(failure.exception)))
        self.assertFalse((self.journal / "witness-operation.json").exists())
        self.assertEqual(self.witness_calls(), [])

    def test_cold_success_needs_no_extra_verification_even_at_budget_limit(self):
        self.witness = self.new_runner(verification_limit=1)
        receipt = self.run_witness()
        raw = (self.journal / "witness-state.json").read_bytes()
        self.main = self.commit_tree(self.changed_tree(self.merged, "docs/plans/later.md", b"later"), self.merged)
        self.witness = self.new_runner(verification_limit=1)
        self.assertEqual(self.observe(), dict(status="verified", receipt=receipt))
        self.assertEqual(self.observe(), dict(status="verified", receipt=receipt))
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        self.assertEqual((self.journal / "witness-state.json").read_bytes(), raw)

    def test_unconfirmed_command_output_is_pending_without_reexecution(self):
        self.crash_after("verification")
        raw = (self.journal / "witness-state.json").read_bytes()
        self.witness = self.new_runner()
        self.assertEqual(self.observe(), dict(status="pending", receipt=None))
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        self.assertEqual((self.journal / "witness-state.json").read_bytes(), raw)

    def test_changed_actual_artifact_cannot_recover_a_success_bit(self):
        self.run_witness()
        self.artifact.write_bytes(self.artifact.read_bytes() + b" ")
        with self.assertRaisesRegex(CandidateWitnessError, "confirmed artifacts changed"):
            self.observe()
        self.assertEqual(self.witness_calls(), ["generate", "verify"])

    def test_missing_enrolled_history_is_not_absence(self):
        self.run_witness()
        (self.journal / "witness-state.json").unlink()
        with self.assertRaisesRegex(CandidateWitnessError, "state disappeared"):
            self.observe()
        self.assertFalse((self.journal / "witness-state.json").exists())
        self.assertEqual(self.witness_calls(), ["generate", "verify"])

    def test_artifact_changed_by_final_authority_check_is_refused(self):
        self.run_witness()
        calls = 0
        def authority(scope):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.artifact.write_bytes(self.artifact.read_bytes() + b" ")
        self.witness = self.new_runner(authorize=authority)
        with self.assertRaisesRegex(CandidateWitnessError, "observation artifacts changed"):
            self.observe()
        self.assertEqual(calls, 2)
        self.assertEqual(self.witness_calls(), ["generate", "verify"])


if __name__ == "__main__":
    unittest.main()
