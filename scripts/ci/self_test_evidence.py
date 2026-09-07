"""Validate a retained self-test verdict without inventing another policy.

This checks the document contract, not GitHub provenance. Callers must first
authenticate the producing workflow/run/attempt and obtain its trusted policy;
a self-asserted digest is not proof of who produced an artifact.
"""

from __future__ import annotations

from copy import deepcopy
import re

import self_test as protocol


class SelfTestEvidenceError(ValueError):
    """A retained document cannot be consumed as self-test evidence."""


def _require(condition: bool, why: str) -> None:
    if not condition:
        raise SelfTestEvidenceError(
            f"why: {why}; remedy: retain a complete verdict from the trusted "
            "self-test producer for this exact run and policy; do not repair evidence by hand"
        )


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_verdict_document(
    document: object,
    *,
    policy: protocol.Policy,
    expected_identity: protocol.Identity | None = None,
) -> dict[str, object]:
    """Return a validated copy, or raise a diagnostic naming why and remedy.

    Invalid and superseded batches remain non-passing observations. Failed
    batches still enumerate every required suite, including missing jobs.
    Exact identity matching is available to the caller that has independently
    resolved the expected run and target; never derive that expectation only
    from the untrusted document being checked.
    """
    _require(isinstance(document, dict), "self-test verdict is not an object")
    assert isinstance(document, dict)
    _require(set(document) == {
        "evidence_schema", "identity", "status", "superseded_by",
        "suites", "diagnostics", "evidence_digest",
    }, "self-test verdict has missing or unknown fields")
    _require(document["evidence_schema"] == policy.evidence_schema == protocol.EVIDENCE_SCHEMA,
             "self-test verdict schema does not match its policy")
    identity = document["identity"]
    _require(isinstance(identity, dict), "self-test identity is not an object")
    assert isinstance(identity, dict)
    _require(set(identity) == {
        "evidence_schema", "request_kind", "control_revision", "target_revision",
        "run_id", "run_attempt", "policy_revision",
    }, "self-test identity has missing or unknown fields")
    _require(identity["evidence_schema"] == protocol.EVIDENCE_SCHEMA,
             "self-test identity schema differs from the verdict")
    _require(isinstance(identity["request_kind"], str)
             and identity["request_kind"] in protocol.REQUEST_KINDS,
             "self-test request kind is unknown")
    for field in ("control_revision", "target_revision"):
        _require(isinstance(identity[field], str)
                 and re.fullmatch(r"[0-9a-f]{40}", identity[field]) is not None,
                 f"self-test {field} is not an exact revision")
    for field in ("run_id", "run_attempt"):
        _require(type(identity[field]) is int and identity[field] > 0,
                 f"self-test {field} is not a positive integer")
    _require(identity["policy_revision"] == policy.revision,
             "self-test verdict was produced under a different policy")
    if expected_identity is not None:
        _require(identity == expected_identity.as_document(),
                 "self-test verdict identity differs from the independently resolved batch")
    _require(_strings(document["diagnostics"]), "batch diagnostics are not strings")
    _require(isinstance(document["evidence_digest"], str)
             and re.fullmatch(r"[0-9a-f]{64}", document["evidence_digest"]) is not None,
             "self-test evidence digest is not a canonical SHA-256")
    payload = {key: value for key, value in document.items() if key != "evidence_digest"}
    try:
        digest = protocol.digest_of(payload)
    except (TypeError, ValueError) as error:
        raise SelfTestEvidenceError(
            "why: verdict is not canonical JSON; remedy: use the self-test producer's JSON artifact"
        ) from error
    _require(digest == document["evidence_digest"], "self-test evidence digest does not match its contents")
    status = document["status"]
    _require(isinstance(status, str) and status in {
        protocol.BATCH_PASSED, protocol.BATCH_FAILED,
        protocol.BATCH_INVALID, protocol.BATCH_SUPERSEDED,
    }, "self-test batch status is unknown")
    suites = document["suites"]
    _require(isinstance(suites, list), "self-test suites are not a list")
    assert isinstance(suites, list)
    if status == protocol.BATCH_SUPERSEDED:
        replacement = document["superseded_by"]
        _require(identity["request_kind"] in protocol.DEDUPLICATED_KINDS,
                 "an explicit candidate or node request cannot be superseded")
        _require(isinstance(replacement, str)
                 and re.fullmatch(r"[0-9a-f]{40}", replacement) is not None
                 and replacement != identity["target_revision"],
                 "supersession does not identify a different exact target")
        _require(not suites and bool(document["diagnostics"]),
                 "superseded batches must retain diagnostics and no suite proof")
        return deepcopy(document)
    _require(document["superseded_by"] is None, "a non-superseded batch names a replacement")
    if status == protocol.BATCH_INVALID:
        _require(not suites and bool(document["diagnostics"]),
                 "invalid batches must retain diagnostics and no suite proof")
        return deepcopy(document)

    expected_suites = {suite.id: suite for suite in policy.suites}
    seen: set[str] = set()
    passed = True
    allowed_statuses = {
        protocol.SUITE_PASSED, protocol.SUITE_TEST_FAILURE,
        protocol.SUITE_INFRASTRUCTURE_FAILURE, protocol.SUITE_BLOCKED,
        protocol.SUITE_MISSING,
    }
    for result in suites:
        _require(isinstance(result, dict), "a suite result is not an object")
        assert isinstance(result, dict)
        _require(set(result) == {"id", "status", "jobs", "diagnostics"},
                 "a suite result has missing or unknown fields")
        suite_id = result["id"]
        _require(isinstance(suite_id, str) and suite_id in expected_suites and suite_id not in seen,
                 "self-test verdict has an unknown or duplicate suite")
        seen.add(suite_id)
        suite = expected_suites[suite_id]
        _require(isinstance(result["status"], str) and result["status"] in allowed_statuses,
                 f"suite {suite_id} has an unknown status")
        _require(_strings(result["diagnostics"]), f"suite {suite_id} diagnostics are not strings")
        jobs = result["jobs"]
        _require(isinstance(jobs, dict) and set(jobs) == set(suite.jobs),
                 f"suite {suite_id} does not enumerate exactly its required jobs")
        assert isinstance(jobs, dict)
        for job, conclusion in jobs.items():
            alternatives = {
                f"skipped (alternative {alternative} succeeded)"
                for alternative in suite.alternatives.get(job, ())
            }
            _require(isinstance(conclusion, str)
                     and conclusion in protocol.JOB_CONCLUSIONS | {"missing"} | alternatives,
                     f"suite {suite_id}/{job} has an unknown result or alternative")
            if result["status"] == protocol.SUITE_PASSED:
                _require(conclusion == "success" or conclusion in alternatives,
                         f"passed suite {suite_id} contains non-passing job {job}")
        if result["status"] != protocol.SUITE_PASSED:
            passed = False
            _require(bool(result["diagnostics"]), f"non-passing suite {suite_id} has no diagnostic")
    _require(seen == set(expected_suites), "self-test verdict omits required suites")
    _require((status == protocol.BATCH_PASSED) == passed,
             "batch status disagrees with the complete suite results")
    if not passed:
        _require(bool(document["diagnostics"]), "failed batch has no diagnostic")
    return deepcopy(document)
