"""Closed internal data records, not authentication or storage side effects.

Digests prove consistency only. Callers must authenticate progress/receipt
sources independently. Pure operation transitions require an external durable
CAS/lock before any executor may consume them; a fence here is not a lease.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Protocol

MAX_BYTES = 1024 * 1024
SITES = ("creator", "docs", "runtime")
PROGRESS_SCHEMA = "lmdj.canary-progress.v1"
OPERATION_SCHEMA = "lmdj.canary-operation.v1"


class CanaryError(ValueError):
    """Incomplete or inconsistent input; never interpret as no pending work."""


def require(condition, why, remedy="restore complete authenticated inputs and reconcile"):
    if not condition:
        raise CanaryError(f"why: {why}; remedy: {remedy}")


def exact_sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value),
            "revision is not an exact lowercase commit SHA")
    return value


def exact_digest(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
            "digest is not an exact lowercase SHA-256")
    return value


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value),
            "operation ID is missing or invalid")
    return value


def canonical(document):
    try:
        return json.dumps(document, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise CanaryError("why: record cannot be encoded as finite JSON; remedy: regenerate valid records") from None


def digest(document):
    return hashlib.sha256(canonical(document)).hexdigest()


def seal(document):
    require(isinstance(document, dict), "record must be an object")
    payload = deepcopy(document)
    payload.pop("digest", None)
    return {**payload, "digest": digest(payload)}


def verify_seal(document):
    require(isinstance(document, dict) and "digest" in document, "record lacks digest")
    exact_digest(document["digest"])
    require(document["digest"] == seal(document)["digest"], "record digest mismatch")


def _pairs(pairs):
    document = {}
    for key, value in pairs:
        require(key not in document, "duplicate JSON key")
        document[key] = value
    return document


def decode(raw):
    require(isinstance(raw, (str, bytes)), "record payload is not JSON text")
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        require(len(encoded) <= MAX_BYTES, "record exceeds byte limit")
        return json.loads(encoded.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: require(False, "nonfinite JSON number"))
    except CanaryError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise CanaryError("why: record JSON is malformed; remedy: restore the complete original record") from None


def _repository(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value),
            "repository identity is malformed")


def _pointer(pointer):
    if pointer is None:
        return
    require(isinstance(pointer, dict) and set(pointer) == {"revision", "receipt_digest"},
            "progress pointer is incomplete or has unknown fields")
    exact_sha(pointer["revision"])
    exact_digest(pointer["receipt_digest"])


def validate_progress(document, *, repository):
    _repository(repository)
    require(isinstance(document, dict) and set(document) == {
        "schema", "repository", "channel", "version_accounted", "deployments", "formal", "digest"
    }, "progress schema is not closed")
    require(document["schema"] == PROGRESS_SCHEMA and document["repository"] == repository
            and document["channel"] == "canary", "progress identity mismatch")
    require(isinstance(document["deployments"], dict) and set(document["deployments"]) == set(SITES),
            "deployment site inventory is incomplete or unknown")
    for pointer in [document["version_accounted"], document["formal"], *document["deployments"].values()]:
        _pointer(pointer)
    verify_seal(document)
    require(len(canonical(document)) <= MAX_BYTES, "record exceeds byte limit")
    return deepcopy(document)


def initial_progress(repository):
    """Explicit bootstrap only; never call in an unavailable-storage handler."""
    _repository(repository)
    return seal({"schema": PROGRESS_SCHEMA, "repository": repository, "channel": "canary",
                 "version_accounted": None, "deployments": dict.fromkeys(SITES), "formal": None})


def parse_progress(raw, *, repository):
    return validate_progress(decode(raw), repository=repository)


class ProgressReader(Protocol):
    """Caller-owned authenticated read port. No writer is exposed by T1."""

    def read(self) -> bytes: ...


def load_progress(source: ProgressReader, *, repository):
    try:
        raw = source.read()
    except Exception:
        raise CanaryError("why: progress storage unavailable; remedy: restore authenticated storage and retry") from None
    return parse_progress(raw, repository=repository)


_TRANSITIONS = {
    "planned": {"running", "failed"},
    "running": {"unknown", "succeeded", "failed"},
    "unknown": {"succeeded", "failed"},
    "succeeded": set(),
    "failed": set(),
}


def validate_operation(document):
    require(isinstance(document, dict) and set(document) == {
        "schema", "id", "input_digest", "plan_digest", "fence", "state", "digest"
    }, "operation schema is not closed")
    require(document["schema"] == OPERATION_SCHEMA, "operation schema is unsupported")
    identifier(document["id"])
    exact_digest(document["input_digest"])
    exact_digest(document["plan_digest"])
    require(type(document["fence"]) is int and document["fence"] > 0, "operation fence is invalid")
    require(isinstance(document["state"], str) and document["state"] in _TRANSITIONS,
            "operation state is unknown")
    verify_seal(document)
    return deepcopy(document)


def new_operation(request_id, input_digest, plan_digest):
    return validate_operation(seal({"schema": OPERATION_SCHEMA, "id": request_id,
                                    "input_digest": input_digest, "plan_digest": plan_digest,
                                    "fence": 1, "state": "planned"}))


def reconcile_operation(document, request_id, input_digest):
    operation = validate_operation(document)
    identifier(request_id)
    exact_digest(input_digest)
    require(operation["id"] == request_id, "operation ID mismatch")
    require(operation["input_digest"] == input_digest, "operation ID reused with different inputs",
            "reconcile the original request or use a new explicit operation ID")
    return operation


def transition_operation(document, *, expected_fence, state):
    """Propose new bytes for a future CAS writer; never persist or execute them.

Unknown outcomes can only be reconciled terminal, never reissued as running.
External receipt verification is a required precondition of terminal proposals.
"""
    operation = validate_operation(document)
    require(type(expected_fence) is int and expected_fence == operation["fence"],
            "operation fence is stale or invalid", "reload and reconcile the latest durable operation")
    require(isinstance(state, str) and state in _TRANSITIONS, "operation state is unknown")
    if state == operation["state"]:
        return operation
    require(state in _TRANSITIONS[operation["state"]], "unsafe operation transition",
            "reconcile external receipts; never rerun an unknown or terminal effect")
    operation.update(state=state, fence=operation["fence"] + 1)
    return seal(operation)
