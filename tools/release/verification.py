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
from .batch_reference import SCHEMA, parse_reference
from .model import canonical_sha256
from .orchestration_driver import Observation


class VerificationError(ValueError):
    pass


class EvidenceUnavailable(RuntimeError):
    """A run or attestation read failed: an outage, never contradictory evidence."""


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


def terminal_result(events, witness):
    """The unique terminal batch result for the candidate witness, or None."""
    results = [event["data"] for event in events
               if isinstance(event, dict) and event.get("type") == "result"
               and isinstance(event.get("data"), dict) and event["data"].get("target") == witness
               and event["data"].get("terminal") is True]
    if not results:
        return None
    if len(results) > 1:
        _fail("multiple batch results claim the same candidate target")
    return results[0]


def release_reference(events, result, witness, consumer):
    """The closed release batch reference behind one terminal journal result.

    The batch runtime records its verdict evidence as the journal reference,
    not the release reference. The release reference is assembled from facts
    the batch already retains: the frozen request and executor of the admit
    event for this request, the verdict's evidence digest, the executor run's
    control and event, and the digests of the origin and admission controller
    attestations. Assembly grants nothing: every field is then re-proven by
    `BatchEvidenceConsumer.verify_run`. A result that already carries a
    release reference is used as-is.
    """
    from scripts.ci.batch_runtime import decode_reference
    from scripts.ci.self_test import digest_of

    document = decode_reference(result.get("reference"))
    if isinstance(document, dict) and "schema" in document:
        return parse_reference(document)
    if not isinstance(document, dict):
        _fail("batch result reference is not a document")
    request_id = result.get("request_id")
    admits = [event["data"] for event in events
              if isinstance(event, dict) and event.get("type") == "admit"
              and isinstance(event.get("data"), dict)
              and isinstance(event["data"].get("request"), dict)
              and event["data"]["request"].get("id") == request_id]
    if len(admits) != 1:
        _fail("batch result has no unique admission for its request")
    request, executor = admits[0]["request"], admits[0].get("executor_run")
    if (request.get("target") != witness or not isinstance(executor, dict)
            or set(executor) != {"run_id", "attempt"} or executor["attempt"] != 1
            or result.get("run") != executor):
        _fail("batch admission does not bind the candidate target and executor")
    identity = document.get("identity")
    if (not isinstance(identity, dict) or identity.get("target_sha") != witness
            or identity.get("request_id") != request_id
            or identity.get("run_id") != executor["run_id"] or identity.get("run_attempt") != 1):
        _fail("batch verdict does not bind the admitted request and executor")
    if document.get("status") != "passed":
        _fail("batch verdict is not passed")
    origin = request.get("origin_run")
    origin_id = origin.get("run_id") if isinstance(origin, dict) else None
    if type(origin_id) is not int or origin_id <= 0:
        _fail("batch admission retains no exact origin run")
    try:
        executor_run = consumer.get(f"/actions/runs/{executor['run_id']}/attempts/1")
        origin_run = consumer.get(f"/actions/runs/{origin_id}/attempts/1")

        def attestation(run):
            return consumer.artifact(run, f"batch-controller-{run['id']}-1", ("result.json",))["result.json"]

        origin_record, admission_record = attestation(origin_run), attestation(executor_run)
    except BatchEvidenceError as error:
        if error.code == "external-error":
            raise EvidenceUnavailable("batch run or controller attestation could not be read") from error
        raise
    except OSError as error:
        raise EvidenceUnavailable("batch run or controller attestation could not be read") from error
    return parse_reference({
        "schema": SCHEMA,
        "request": request,
        "executor_control_revision": executor_run.get("head_sha"),
        "executor_event": executor_run.get("event"),
        "run_attempt": 1,
        "origin_record_digest": digest_of(origin_record),
        "admission_record_digest": digest_of(admission_record),
        "evidence_digest": document.get("evidence_digest"),
    })


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
        # The terminal check lives in terminal_result so both selections agree.
        results = [event["data"] for event in events
                   if isinstance(event, dict) and event.get("type") == "result"
                   and isinstance(event.get("data"), dict) and event["data"].get("target") == witness]
        if not results:
            return None
        if len(results) > 1:
            _fail("multiple batch results claim the same candidate target")
        result = terminal_result(events, witness)
        if result is None:
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
            result = terminal_result(events, witness)
            if result is None:
                return Observation("pending")
            document = release_reference(events, result, witness, self.consumer)
            request = document["request"]
            if request.get("target") != witness:
                _fail("decoded reference does not bind the candidate target")
            origin = request["origin_run"]["run_id"]
            if type(origin) is not int or origin <= 0:
                _fail("durable reference has no exact origin run")
            # The batch that ran the suites. A queued candidate is admitted by
            # one run and executed by a later one, so the executor is the
            # result's own run, not the origin that enqueued the request.
            executor = result.get("run")
            executor_id = executor.get("run_id") if isinstance(executor, dict) else None
            if type(executor_id) is not int or executor_id <= 0 or executor.get("attempt") != 1:
                _fail("batch result names no exact first-attempt executor run")
        except VerificationError:
            return Observation("conflict")
        except EvidenceUnavailable:
            # A run or attestation read failed: an outage to retry, not a
            # contradiction in the evidence.
            return Observation("unknown")
        except Exception:
            # Undecodable reference payloads fail closed with the journal
            # result they came from: conflict, never an outage.
            return Observation("conflict")
        try:
            self.consumer.verify_run(document, run_id=executor_id, target_revision=witness)
        except BatchEvidenceError:
            return Observation("conflict")
        except Exception:
            return Observation("unknown")
        return Observation("verified", {
            "sha256": canonical_sha256(document),
            "reference": f"batch-result:{executor_id}:{witness}",
        })
