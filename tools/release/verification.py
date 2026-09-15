"""Verification carrier: authenticated batch evidence for the candidate target.

Composes the incremental batch controller's durable journal with the existing
batch evidence consumer. The composition root supplies `fresh_receipts(state)`
— the same trusted path the candidate transition exposes (`verified_candidate`)
— so the witness revision is never parsed from opaque evidence text.

Observation reads the journal and verifies the exact terminal result for that
revision; nothing here executes suites, posts to the journal or grants release
authority. No result after a complete authenticated read is pending work, not
absence; an unreadable journal is unknown, never a negative proof.
"""

from .batch_evidence import BatchEvidenceConsumer, BatchEvidenceError
from .batch_reference import parse_reference
from .model import canonical_sha256
from .orchestration_driver import Observation


class VerificationError(ValueError):
    pass


def _fail(reason):
    raise VerificationError(
        f"why: verification carrier {reason}; remedy: restore the authenticated "
        "batch journal and the candidate's exact evidence without executing "
        "another suite or inventing a reference")


def _decode(reference):
    from scripts.ci.batch_runtime import decode_reference
    document = decode_reference(reference)
    parse_reference(document)
    return document


class BatchVerification:
    def __init__(self, *, journal_load, consumer, fresh_receipts):
        """journal_load() -> authenticated event list.

        consumer: the concrete BatchEvidenceConsumer. fresh_receipts(state) ->
        the candidate receipt (with `witness_revision`) from the same trusted
        composition that owns the candidate transition.
        """
        if not callable(journal_load) or not callable(fresh_receipts) \
                or not isinstance(consumer, BatchEvidenceConsumer):
            _fail("requires the authenticated journal reader, the concrete "
                  "evidence consumer and the trusted candidate receipts")
        self.journal_load = journal_load
        self.consumer = consumer
        self.fresh_receipts = fresh_receipts

    def _result_for(self, events, witness):
        results = []
        for event in events:
            data = event.get("data") if isinstance(event, dict) else None
            if isinstance(data, dict) and event.get("type") == "result" \
                    and data.get("target") == witness:
                results.append(data)
        if not results:
            return None
        if len(results) > 1:
            _fail("multiple batch results claim the same candidate target")
        result = results[0]
        if result.get("terminal") is not True:
            _fail("batch result for the candidate is not proven terminal")
        outcomes = result.get("outcomes")
        if not isinstance(outcomes, dict) or not outcomes:
            _fail("batch result does not enumerate suite outcomes")
        if any(value != "passed" for value in outcomes.values()):
            _fail("batch result is not fully passed")
        reference = result.get("reference")
        if not isinstance(reference, str) or not reference:
            _fail("batch result has no durable reference")
        return reference

    def observe(self, state, operation):
        try:
            candidate = self.fresh_receipts(state)
        except Exception:
            return Observation("unknown")
        witness = candidate.get("witness_revision") if isinstance(candidate, dict) else None
        if not isinstance(witness, str) or len(witness) != 40:
            return Observation("conflict")
        try:
            events = self.journal_load()
        except Exception:
            return Observation("unknown")
        try:
            reference = self._result_for(events, witness)
        except VerificationError:
            return Observation("conflict")
        if reference is None:
            return Observation("pending")
        try:
            document = _decode(reference)
            request = document["request"]
            if request.get("target") != witness:
                _fail("decoded reference does not bind the candidate target")
            origin = request["origin_run"]["run_id"]
            if type(origin) is not int or origin <= 0:
                _fail("durable reference has no exact origin run")
        except VerificationError:
            return Observation("conflict")
        except Exception:
            # Undecodable reference payloads fail closed with the journal
            # result they came from: conflict, never an outage.
            return Observation("conflict")
        try:
            self.consumer.verify_run(document, run_id=origin, target_revision=witness)
        except BatchEvidenceError:
            return Observation("conflict")
        except Exception:
            return Observation("unknown")
        return Observation("verified", {
            "sha256": canonical_sha256(document),
            "reference": f"batch-result:{origin}:{witness}",
        })
