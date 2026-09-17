#!/usr/bin/env python3
"""The verification carrier proves exact batch evidence for the candidate target."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "build"))
sys.path.insert(0, str(ROOT / "scripts" / "ci"))

import incremental_batch_journal as journal_module  # noqa: E402
from tools.release.batch_evidence import BatchEvidenceConsumer, BatchEvidenceError  # noqa: E402
from tools.release.model import canonical_sha256  # noqa: E402
from tools.release.orchestration_driver import Observation  # noqa: E402
from tools.release.verification import BatchVerification  # noqa: E402

WITNESS = "e" * 40


def batch_reference_document(run_id, target):
    return {"schema": "lmdj.ci-batch-release-reference.v1",
            "request": {"id": "batch-request", "kind": "candidate", "base": None,
                        "target": target, "control": "a" * 40, "policy": "2" * 64,
                        "selection": {"kind": "full", "suites": ["suite-a"], "reasons": []},
                        "origin_run": {"run_id": run_id, "attempt": 1}},
            "executor_control_revision": "a" * 40, "executor_event": "push",
            "run_attempt": 1, "origin_record_digest": "3" * 64,
            "admission_record_digest": "4" * 64, "evidence_digest": "5" * 64}


class MemoryTransport:
    def __init__(self):
        self.comments = []
        self.body = {"checkpoint": {"head": None, "pending": None}, "provenance": "trusted-run"}

    def read_body(self, issue_id):
        return deepcopy(self.body)

    def write_body(self, issue_id, checkpoint):
        self.body = {"checkpoint": deepcopy(checkpoint), "provenance": "trusted-run"}

    def append(self, issue_id, envelope):
        self.comments.append({"id": len(self.comments) + 1, "edited": False,
                              "envelope": deepcopy(envelope), "provenance": "trusted-run"})

    def page(self, issue_id, cursor):
        start = int(cursor or 0)
        end = start + 1
        return {"comments": deepcopy(self.comments[start:end]),
                "next": str(end) if end < len(self.comments) else None}

    def last(self, issue_id):
        if not self.comments:
            return None
        return deepcopy(self.comments[-1])


class RecordingConsumer(BatchEvidenceConsumer):
    """Same type the real composition uses; records the verified run."""

    def __init__(self, *, accept=True):
        self.accept = accept
        self.verified = None

    def verify_run(self, reference, *, run_id, target_revision, published=False):
        self.verified = (run_id, target_revision)
        if not self.accept:
            raise BatchEvidenceError("conflict", "retained evidence contradicts")


class BatchVerificationTest(unittest.TestCase):
    def setUp(self):
        self.transport = MemoryTransport()
        self.authenticate = lambda record, issue: issue == 7 and record["provenance"] == "trusted-run"
        anchor = journal_module.IssueBodyAnchor(7, self.transport, self.authenticate, lambda: True)
        self.journal = journal_module.Journal(7, self.transport, anchor, self.authenticate, lambda: True)
        self.consumer = RecordingConsumer()
        self.receipts = [dict(witness_revision=WITNESS)]
        self.carrier = BatchVerification(
            journal_load=self.journal.load, consumer=self.consumer,
            fresh_receipts=lambda state: self.receipts[0])

    def result_event(self, *, run_id=4242, target=WITNESS, terminal=True,
                     outcomes=None, reference=None):
        from scripts.ci.batch_runtime import encode_reference
        if reference is None:
            reference = encode_reference(batch_reference_document(run_id, target))
        return {"id": f"result-{run_id}", "epoch": "one", "generation": 1, "type": "result",
                "data": {"request_id": "batch-request", "run": {"id": 99, "attempt": 1},
                         "target": target, "policy": "2" * 64,
                         "outcomes": outcomes or {"suite-a": "passed"},
                         "reference": reference, "terminal": terminal}}

    def test_verified_result_yields_authenticated_evidence_for_the_exact_target(self):
        self.journal.append(self.result_event())
        observed = self.carrier.observe({}, {})
        self.assertEqual(observed.status, "verified")
        self.assertEqual(self.consumer.verified, (4242, WITNESS))
        self.assertEqual(observed.evidence["sha256"],
                         canonical_sha256(batch_reference_document(4242, WITNESS)))
        self.assertEqual(observed.evidence["reference"], f"batch-result:4242:{WITNESS}")

    def test_absent_result_is_pending_work_and_never_absence(self):
        self.assertEqual(self.carrier.observe({}, {}).status, "pending")
        self.assertIsNone(self.consumer.verified)

    def test_unreadable_journal_is_unknown_without_negative_proof(self):
        self.journal.append(self.result_event())
        self.carrier.journal_load = lambda: (_ for _ in ()).throw(OSError("state unavailable"))
        self.assertEqual(self.carrier.observe({}, {}).status, "unknown")

    def test_failed_or_focused_result_conflicts(self):
        self.journal.append(self.result_event(outcomes={"suite-a": "failed"}))
        self.assertEqual(self.carrier.observe({}, {}).status, "conflict")
        self.setUp()
        self.journal.append(self.result_event(reference="batch-verdict-v1:zlib-base64:bogus"))
        # A malformed durable reference fails closed as a conflict, never as
        # an outage: the journal result is authenticated, only its payload is bad.
        self.assertEqual(self.carrier.observe({}, {}).status, "conflict")

    def test_reference_bound_to_another_target_conflicts(self):
        from scripts.ci.batch_runtime import encode_reference
        other = encode_reference(batch_reference_document(4242, "f" * 40))
        self.journal.append(self.result_event(reference=other))
        # The journal result was selected for WITNESS, so a document naming a
        # different target must fail closed even though decode succeeds.
        self.assertEqual(self.carrier.observe({}, {}).status, "conflict")

    def test_receipts_without_a_witness_revision_conflict(self):
        self.receipts[0] = {}
        self.assertEqual(self.carrier.observe({}, {}).status, "conflict")

    def test_duplicate_results_for_one_target_are_refused(self):
        self.journal.append(self.result_event(run_id=4242))
        self.journal.append(self.result_event(run_id=4243))
        self.assertEqual(self.carrier.observe({}, {}).status, "conflict")


if __name__ == "__main__":
    unittest.main()
