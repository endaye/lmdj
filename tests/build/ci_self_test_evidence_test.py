#!/usr/bin/env python3
"""Read real producer documents through the retained-evidence boundary."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import self_test as protocol  # noqa: E402
from self_test_evidence import SelfTestEvidenceError, validate_verdict_document  # noqa: E402


class RetainedEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = protocol.load_policy(ROOT / "scripts/ci/self_test_policy.json")
        self.identity = protocol.Identity(protocol.EVIDENCE_SCHEMA, "node", "a" * 40,
                                          "b" * 40, 17, 1, self.policy.revision)
        self.rows = [
            protocol.Observation(suite.id, job, 17, 1, "b" * 40, "success")
            for suite in self.policy.suites for job in suite.jobs
        ]
        self.document = self.document_for(protocol.aggregate(self.identity, self.policy, self.rows))

    @staticmethod
    def document_for(verdict: protocol.Verdict) -> dict[str, object]:
        return {**verdict.as_document(), "evidence_digest": verdict.digest}

    @staticmethod
    def resign(document: dict[str, object]) -> None:
        document["evidence_digest"] = protocol.digest_of(
            {key: value for key, value in document.items() if key != "evidence_digest"})

    def validate(self, document: object) -> dict[str, object]:
        return validate_verdict_document(document, policy=self.policy, expected_identity=self.identity)

    def test_real_producer_complete_pass_and_defensive_copy(self) -> None:
        result = self.validate(self.document)
        self.assertEqual(result, self.document)
        result["suites"].clear()
        self.assertEqual(len(self.document["suites"]), len(self.policy.suites))

    def test_real_failed_missing_blocked_and_artifact_failure_documents(self) -> None:
        for conclusion, artifact, blocked_by in (
            ("failure", "none", None), ("cancelled", "none", None),
            ("skipped", "none", "build"), ("success", "failed", None),
        ):
            with self.subTest(conclusion=conclusion, artifact=artifact):
                row = self.rows[0]
                replacement = protocol.Observation(row.suite, row.job, 17, 1, "b" * 40,
                                                   conclusion, artifact, blocked_by)
                document = self.document_for(protocol.aggregate(
                    self.identity, self.policy, [replacement, *self.rows[1:]]))
                self.assertEqual(self.validate(document)["status"], "failed")
        document = self.document_for(protocol.aggregate(self.identity, self.policy, self.rows[1:]))
        self.assertEqual(self.validate(document)["status"], "failed")

    def test_real_invalid_and_schedule_supersession_remain_non_passes(self) -> None:
        document = self.document_for(protocol.aggregate(self.identity, self.policy, []))
        self.assertEqual(self.validate(document)["status"], "invalid")
        identity = protocol.Identity(protocol.EVIDENCE_SCHEMA, "schedule", "a" * 40,
                                     "b" * 40, 17, 1, self.policy.revision)
        document = self.document_for(protocol.supersede(identity, by_target="c" * 40))
        self.assertEqual(validate_verdict_document(document, policy=self.policy)["status"], "superseded")
        document["identity"]["request_kind"] = "candidate"
        self.resign(document)
        with self.assertRaisesRegex(SelfTestEvidenceError, "explicit candidate"):
            validate_verdict_document(document, policy=self.policy)

    def test_declared_mac_alternative_accepts_real_producer_output(self) -> None:
        rows = [row if row.job != "macos-primary" else protocol.Observation(
            row.suite, row.job, 17, 1, "b" * 40, "skipped") for row in self.rows]
        rows.append(protocol.Observation("core_macos", "macos-fallback", 17, 1, "b" * 40, "success"))
        self.assertEqual(self.validate(self.document_for(
            protocol.aggregate(self.identity, self.policy, rows)))["status"], "passed")

    def test_recomputed_digest_cannot_hide_missing_duplicate_or_failed_suites(self) -> None:
        mutations = [
            lambda d: d.update(suites=[]),
            lambda d: d["suites"].pop(),
            lambda d: d["suites"].append(deepcopy(d["suites"][0])),
            lambda d: d["suites"][0]["jobs"].clear(),
            lambda d: d["suites"][0]["jobs"].update({next(iter(d["suites"][0]["jobs"])): "failure"}),
            lambda d: d["suites"][0]["jobs"].update({next(iter(d["suites"][0]["jobs"])): "skipped (alternative invented succeeded)"}),
            lambda d: d.update(status="failed"),
            lambda d: d.update(unknown="field"),
            lambda d: d["identity"].update(run_attempt=True),
            lambda d: d["identity"].update(control_revision="main"),
            lambda d: d["identity"].update(policy_revision="0" * 64),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                document = deepcopy(self.document)
                mutate(document)
                self.resign(document)
                with self.assertRaisesRegex(SelfTestEvidenceError, "why:.*remedy:"):
                    self.validate(document)

    def test_wrong_run_attempt_control_target_and_tampering_are_rejected(self) -> None:
        for field, value in (("run_id", 18), ("run_attempt", 2),
                             ("target_revision", "c" * 40), ("control_revision", "c" * 40)):
            with self.subTest(field=field):
                document = deepcopy(self.document)
                document["identity"][field] = value
                self.resign(document)
                with self.assertRaisesRegex(SelfTestEvidenceError, "independently resolved"):
                    self.validate(document)
        self.document["diagnostics"].append("tampered")
        with self.assertRaisesRegex(SelfTestEvidenceError, "digest does not match"):
            self.validate(self.document)


if __name__ == "__main__":
    unittest.main(verbosity=2)
