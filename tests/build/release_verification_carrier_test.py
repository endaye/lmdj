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

    def page(self, issue_id, cursor, authenticated_prefix=0):
        start = int(cursor or 0)
        end = start + 1
        rows = deepcopy(self.comments[start:end])
        return {"comments": rows,
                "next": str(end) if end < len(self.comments) else None,
                "cursor": str(end) if rows else None}

    def page_after(self, issue_id, cursor):
        start = int(cursor)
        end = start + 1
        rows = deepcopy(self.comments[start:end])
        return {"comments": rows,
                "next": str(end) if end < len(self.comments) else None,
                "cursor": str(end) if rows else None,
                "total": len(self.comments)}

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


class ComposingConsumer(RecordingConsumer):
    """Serves the run and controller-attestation reads the composer makes."""

    def __init__(self):
        super().__init__()
        self.reference = None

    def get(self, suffix, *, raw=False):
        run_id = int(suffix.split("/")[3])
        return {"id": run_id, "head_sha": "c" * 40, "event": "schedule"}

    def artifact(self, run, name, filenames, *, retention=None):
        assert name == f"batch-controller-{run['id']}-1" and filenames == ("result.json",)
        return {"result.json": {"attestation_of": run["id"]}}

    def verify_run(self, reference, *, run_id, target_revision, published=False):
        self.reference = reference
        return super().verify_run(reference, run_id=run_id, target_revision=target_revision)


class ComposedReferenceTest(unittest.TestCase):
    """Production shape: the journal result carries the batch verdict, not a release reference."""

    ORIGIN, EXECUTOR = 1111, 2222

    def setUp(self):
        self.transport = MemoryTransport()
        self.authenticate = lambda record, issue: issue == 7 and record["provenance"] == "trusted-run"
        anchor = journal_module.IssueBodyAnchor(7, self.transport, self.authenticate, lambda: True)
        self.journal = journal_module.Journal(7, self.transport, anchor, self.authenticate, lambda: True)
        self.consumer = ComposingConsumer()
        self.carrier = BatchVerification(journal_load=self.journal.load, consumer=self.consumer,
                                         fresh_receipts=lambda state: {"witness_revision": WITNESS})
        self.request = deepcopy(batch_reference_document(self.ORIGIN, WITNESS)["request"])

    def admit(self, *, executor=None, request=None):
        return {"id": "admit-1", "epoch": "one", "generation": 1, "type": "admit",
                "data": {"request": request or self.request,
                         "executor_run": executor or {"run_id": self.EXECUTOR, "attempt": 1}}}

    def result(self, *, identity=None, status="passed", terminal=True):
        from scripts.ci.batch_runtime import encode_reference
        verdict = {"identity": identity or {"target_sha": WITNESS, "request_id": "batch-request",
                                            "run_id": self.EXECUTOR, "run_attempt": 1,
                                            "request_kind": "candidate"},
                   "evidence_digest": "5" * 64, "status": status}
        return {"id": "result-1", "epoch": "one", "generation": 2, "type": "result",
                "data": {"request_id": "batch-request", "run": {"run_id": self.EXECUTOR, "attempt": 1},
                         "target": WITNESS, "policy": "2" * 64, "outcomes": {"suite-a": "passed"},
                         "reference": encode_reference(verdict), "terminal": terminal}}

    def observe(self):
        return self.carrier.observe({"request": {}}, {"step": "verification"})

    def test_a_verdict_result_composes_the_release_reference_from_retained_facts(self):
        from scripts.ci.self_test import digest_of
        self.journal.append(self.admit())
        self.journal.append(self.result())
        observed = self.observe()
        self.assertEqual(observed.status, "verified")
        self.assertEqual(observed.evidence["reference"], f"batch-result:{self.EXECUTOR}:{WITNESS}")
        reference = self.consumer.reference
        self.assertEqual(reference["request"], self.request)
        self.assertEqual((reference["executor_control_revision"], reference["executor_event"],
                          reference["run_attempt"], reference["evidence_digest"]),
                         ("c" * 40, "schedule", 1, "5" * 64))
        self.assertEqual(reference["origin_record_digest"], digest_of({"attestation_of": self.ORIGIN}))
        self.assertEqual(reference["admission_record_digest"], digest_of({"attestation_of": self.EXECUTOR}))
        # The evidence names the origin; the batch is verified at its executor.
        self.assertEqual(self.consumer.verified, (self.EXECUTOR, WITNESS))

    def test_a_non_passed_verdict_is_never_composed(self):
        self.journal.append(self.admit())
        self.journal.append(self.result(status="failed"))
        self.assertEqual(self.observe().status, "conflict")
        self.assertIsNone(self.consumer.reference)

    RETRY_ORIGIN, RETRY_EXECUTOR = 4444, 5555

    def retry_request(self, suites=("suite-a",), original="batch-request"):
        return {"id": "retry-request", "kind": "retry", "base": None, "target": WITNESS,
                "control": "a" * 40, "policy": "2" * 64,
                "selection": {"kind": "focused", "suites": sorted(suites), "reasons": ["retry"]},
                "origin_run": {"run_id": self.RETRY_ORIGIN, "attempt": 1},
                "retry_of": {"request": original, "environmental": {
                    suite: {"outcome": "cancelled", "jobs": {}} for suite in suites}}}

    def retry_admit(self, request=None):
        return {"id": "admit-2", "epoch": "one", "generation": 3, "type": "admit",
                "data": {"request": request or self.retry_request(),
                         "executor_run": {"run_id": self.RETRY_EXECUTOR, "attempt": 1}}}

    def retry_result(self, *, status="passed", outcomes=None, generation=4, request_id="retry-request"):
        from scripts.ci.batch_runtime import encode_reference
        verdict = {"identity": {"target_sha": WITNESS, "request_id": request_id,
                                "run_id": self.RETRY_EXECUTOR, "run_attempt": 1, "request_kind": "retry"},
                   "evidence_digest": "6" * 64, "status": status}
        return {"id": f"result-{generation}", "epoch": "one", "generation": generation, "type": "result",
                "data": {"request_id": request_id, "run": {"run_id": self.RETRY_EXECUTOR, "attempt": 1},
                         "target": WITNESS, "policy": "2" * 64,
                         "outcomes": {"suite-a": "passed"} if outcomes is None else outcomes,
                         "reference": encode_reference(verdict), "terminal": True}}

    def test_a_failed_candidate_composes_with_its_passed_retry(self):
        failed = self.result(status="failed")
        failed["data"]["outcomes"] = {"suite-a": "cancelled"}
        self.journal.append(self.admit())
        self.journal.append(failed)
        self.journal.append(self.retry_admit())
        self.journal.append(self.retry_result())
        observed = self.observe()
        self.assertEqual(observed.status, "verified", observed.diagnostic)
        self.assertEqual(observed.evidence["reference"],
                         f"batch-result:{self.EXECUTOR}:{WITNESS};retry:{self.RETRY_EXECUTOR}")
        reference = self.consumer.reference
        self.assertEqual(reference["schema"], "lmdj.ci-batch-release-reference.v2")
        self.assertEqual(reference["request"], self.request)
        self.assertEqual(len(reference["retries"]), 1)
        retry = reference["retries"][0]
        self.assertEqual((retry["request"]["id"], retry["executor_run_id"], retry["evidence_digest"]),
                         ("retry-request", self.RETRY_EXECUTOR, "6" * 64))
        # The consumer still verifies at the candidate's executor; the retry run is inside the document.
        self.assertEqual(self.consumer.verified, (self.EXECUTOR, WITNESS))

    def test_a_retry_that_does_not_cover_the_failed_suites_or_did_not_pass_is_a_conflict(self):
        failed = self.result(status="failed")
        failed["data"]["outcomes"] = {"suite-a": "cancelled"}
        for retry in (self.retry_result(status="failed", outcomes={"suite-a": "failed"}),
                      self.retry_result(outcomes={"suite-b": "passed"})):
            with self.subTest(outcomes=retry["data"]["outcomes"]):
                self.transport.comments.clear()
                self.transport.body = {"checkpoint": {"head": None, "pending": None}, "provenance": "trusted-run"}
                self.journal._verified = None
                self.journal.append(self.admit())
                self.journal.append(failed)
                self.journal.append(self.retry_admit())
                self.journal.append(retry)
                self.assertEqual(self.observe().status, "conflict")
                self.assertIsNone(self.consumer.reference)

    def test_a_retry_whose_frozen_selection_differs_from_the_failed_suites_is_a_conflict(self):
        # The result's outcomes happen to equal the failed set, but the frozen
        # request selected more; the carrier binds the request, not the outcomes.
        failed = self.result(status="failed")
        failed["data"]["outcomes"] = {"suite-a": "cancelled"}
        self.journal.append(self.admit())
        self.journal.append(failed)
        self.journal.append(self.retry_admit(self.retry_request(suites=("suite-a", "suite-b"))))
        self.journal.append(self.retry_result())
        self.assertEqual(self.observe().status, "conflict")
        self.assertIsNone(self.consumer.reference)

    def test_two_retry_results_for_one_candidate_are_a_conflict(self):
        from tools.release.verification import retry_result, VerificationError
        events = [self.admit(), self.retry_admit(), self.retry_result(),
                  self.retry_admit({**self.retry_request(), "id": "retry-two"}),
                  self.retry_result(generation=5, request_id="retry-two")]
        with self.assertRaises(VerificationError):
            retry_result(events, WITNESS, "batch-request")
        # A retry of another candidate never composes with this one.
        self.assertIsNone(retry_result([self.admit(), self.retry_admit(self.retry_request(original="other")),
                                        self.retry_result()], WITNESS, "batch-request"))

    def test_an_unreadable_run_or_attestation_is_unknown_not_conflict(self):
        self.journal.append(self.admit())
        self.journal.append(self.result())

        def outage(*args, **kwargs):
            raise BatchEvidenceError("external-error", "read-only GitHub evidence request failed")

        self.consumer.artifact = outage
        self.assertEqual(self.observe().status, "unknown")
        self.assertIsNone(self.consumer.reference)

    def test_a_malformed_attestation_or_missing_origin_conflicts(self):
        self.journal.append(self.admit())
        self.journal.append(self.result())
        self.consumer.artifact = lambda *a, **k: {}
        self.assertEqual(self.observe().status, "conflict")
        del self.consumer.artifact
        self.transport.comments.clear()
        self.transport.body = {"checkpoint": {"head": None, "pending": None}, "provenance": "trusted-run"}
        self.journal._verified = None
        request = deepcopy(self.request)
        del request["origin_run"]
        self.journal.append(self.admit(request=request))
        self.journal.append(self.result())
        self.assertEqual(self.observe().status, "conflict")
        self.assertIsNone(self.consumer.reference)

    def test_the_selector_requires_a_terminal_result(self):
        from tools.release.verification import terminal_result
        event = self.result(terminal=False)
        self.assertIsNone(terminal_result([event], WITNESS))
        self.assertEqual(terminal_result([self.result()], WITNESS)["target"], WITNESS)

    def test_a_node_diagnostic_result_never_collides_with_the_candidate_result(self):
        from tools.release.verification import terminal_result, VerificationError
        # complete-test-v2 admits exactly one passed candidate source; a
        # kind=node diagnostic acceptance for the same revision (observed
        # live: m4-macos-gates-acceptance beside t1-full-candidate) is not an
        # admissible source and must not make the target ambiguous.
        from tools.release.verification import terminal_result, VerificationError
        node = self.result(identity={"target_sha": WITNESS, "request_id": "m4-acceptance",
                                     "run_id": 3333, "run_attempt": 1, "request_kind": "node"})
        self.assertIsNone(terminal_result([node], WITNESS))
        self.assertEqual(terminal_result([node, self.result()], WITNESS)["request_id"], "batch-request")
        # Two candidate-kind results for one target remain a hard conflict.
        with self.assertRaises(VerificationError):
            terminal_result([self.result(), self.result()], WITNESS)

    def test_the_intent_batch_reference_ignores_a_main_result_for_the_witness(self):
        # When the witness merge is also main's head, the incremental main
        # batch records its own terminal result for the same revision (seen
        # live for 2.0.122.0: z1-full-candidate beside o1-incremental:1346).
        # The intent step must select the candidate result exactly as the
        # verification carrier does, not refuse the target as ambiguous.
        from unittest import mock
        from tools.release import entry_composition, verification
        main = self.result(identity={"target_sha": WITNESS, "request_id": "o1-incremental",
                                     "run_id": 3333, "run_attempt": 1, "request_kind": "node"})
        candidate = self.result()
        picked = []
        with mock.patch.object(verification, "release_reference",
                               lambda events, result, witness, consumer: picked.append(result) or "ref"):
            reference_for = entry_composition._batch_reference_for(lambda: [main, candidate], self.consumer)
            self.assertEqual(reference_for(WITNESS), "ref")
            self.assertEqual(picked[-1]["request_id"], "batch-request")
            # Two candidate-kind results for one target remain a hard refusal.
            with self.assertRaises(entry_composition.JournalError):
                entry_composition._batch_reference_for(
                    lambda: [candidate, self.result()], self.consumer)(WITNESS)
            # Only the main result: there is no admissible candidate result.
            with self.assertRaises(entry_composition.JournalError):
                entry_composition._batch_reference_for(lambda: [main], self.consumer)(WITNESS)

    def test_a_non_terminal_candidate_result_alongside_a_passed_one_still_refuses(self):
        # The kind filter must not silently skip a candidate result that has
        # not proven terminal: the observe path refuses it (multiplicity or
        # not-proven-terminal), exactly as the target-only selector did.
        unfinished = self.result(terminal=False)
        finished = self.result()
        finished["id"], finished["generation"] = "result-2", 3
        self.journal.append(self.admit())
        self.journal.append(unfinished)
        self.journal.append(finished)
        self.assertEqual(self.observe().status, "conflict")
        self.assertIsNone(self.consumer.reference)

    def test_a_kindless_legacy_verdict_is_inadmissible_and_conflicts(self):
        # A verdict shape older than the request-kind field can never prove
        # it was a candidate request; it conflicts rather than being selected
        # or silently skipped, and the refusal names the missing kind.
        from tools.release.verification import terminal_result, VerificationError
        legacy = self.result(identity={"target_sha": WITNESS, "request_id": "legacy",
                                       "run_id": self.EXECUTOR, "run_attempt": 1})
        with self.assertRaises(VerificationError):
            terminal_result([legacy], WITNESS)
        self.journal.append(self.admit())
        self.journal.append(legacy)
        self.assertEqual(self.observe().status, "conflict")

    def test_only_node_results_remain_pending_not_conflict(self):
        # A node diagnostic result for the witness is not admissible evidence
        # and never satisfies verification; with no candidate result yet the
        # honest status is pending work, exactly like no result at all.
        node = self.result(identity={"target_sha": WITNESS, "request_id": "m4-acceptance",
                                     "run_id": 3333, "run_attempt": 1, "request_kind": "node"})
        self.journal.append(self.admit())
        self.journal.append(node)
        self.assertEqual(self.observe().status, "pending")
        self.assertIsNone(self.consumer.reference)

    def test_a_result_without_its_unique_admission_conflicts(self):
        self.journal.append(self.result())
        self.assertEqual(self.observe().status, "conflict")
        self.assertIsNone(self.consumer.reference)

    def test_an_admission_for_another_executor_or_a_foreign_verdict_conflicts(self):
        self.journal.append(self.admit(executor={"run_id": 9999, "attempt": 1}))
        self.journal.append(self.result())
        self.assertEqual(self.observe().status, "conflict")
        self.transport.comments.clear()
        self.transport.body = {"checkpoint": {"head": None, "pending": None}, "provenance": "trusted-run"}
        self.journal._verified = None
        self.journal.append(self.admit())
        self.journal.append(self.result(identity={"target_sha": "f" * 40, "request_id": "batch-request",
                                                  "run_id": self.EXECUTOR, "run_attempt": 1,
                                                  "request_kind": "candidate"}))
        self.assertEqual(self.observe().status, "conflict")
        self.assertIsNone(self.consumer.reference)


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
                "data": {"request_id": "batch-request", "run": {"run_id": run_id, "attempt": 1},
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

    def test_a_result_without_an_exact_first_attempt_executor_conflicts(self):
        event = self.result_event()
        event["data"]["run"] = {"run_id": 4242, "attempt": 2}
        self.journal.append(event)
        self.assertEqual(self.carrier.observe({}, {}).status, "conflict")
        self.assertIsNone(self.consumer.verified)

    def test_contradicting_evidence_conflicts_and_unprovable_evidence_is_unknown(self):
        self.journal.append(self.result_event())
        self.consumer.accept = False
        self.assertEqual(self.carrier.observe({}, {}).status, "conflict")
        for code in ("unverifiable", "external-error"):
            def refuse(reference, *, run_id, target_revision, published=False, code=code):
                raise BatchEvidenceError(code, "local Git provenance cannot be verified")
            self.consumer.verify_run = refuse
            # A main commit this checkout has not fetched yet is not a
            # contradiction: never verified, but retryable.
            self.assertEqual(self.carrier.observe({}, {}).status, "unknown", code)

    def test_duplicate_results_for_one_target_are_refused(self):
        self.journal.append(self.result_event(run_id=4242))
        self.journal.append(self.result_event(run_id=4243))
        self.assertEqual(self.carrier.observe({}, {}).status, "conflict")


if __name__ == "__main__":
    unittest.main()
