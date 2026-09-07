#!/usr/bin/env python3
"""Trusted review/fallback protocol; no model, GitHub writes or credentials.

Adapters supply process receipts, complete Git paths and independently fetched
GitHub identity. Model JSON is only data. T2b owns execution timeout enforcement,
API pagination, immutable artifact upload and guarded COMMENT/label writes.
"""
from __future__ import annotations

import json

import change_scope
import test_scope

BACKENDS = ("glm", "kimi", "grok")
REVIEW_SCHEMA = "lmdj.ci-review-output.v1"
FAILURE_SCHEMA = "lmdj.ci-review-failure.v1"
ERRORS = frozenset({"missing_credential", "rate_limited", "service_error", "timeout",
                    "invalid_output", "runtime_failure", "budget_exhausted"})
MAX_BACKEND_SECONDS = 300
MAX_TOTAL_SECONDS = MAX_BACKEND_SECONDS * len(BACKENDS)


class ReviewScopeError(ValueError):
    pass


def require(condition, why, remedy="regenerate review from the current trusted run and complete inputs"):
    if not condition:
        raise ReviewScopeError(f"why: {why}; remedy: {remedy}")


def validate_review(policy, payload):
    require(isinstance(payload, dict) and set(payload) == {"schema", "summary", "findings", "test_scope"},
            "review output schema is not closed")
    require(payload["schema"] == REVIEW_SCHEMA, "unsupported review output schema")
    require(isinstance(payload["summary"], str) and 0 < len(payload["summary"].strip()) <= 12000,
            "review summary is empty or oversized")
    findings = payload["findings"]
    require(isinstance(findings, list) and len(findings) <= 30, "invalid findings array")
    for finding in findings:
        require(isinstance(finding, dict) and set(finding) == {"path", "line", "body"},
                "finding schema is not closed")
        try:
            test_scope._paths([finding["path"]])
        except test_scope.ScopeError as error:
            raise ReviewScopeError(str(error)) from error
        require(type(finding["line"]) is int and finding["line"] > 0,
                "finding line is not a positive integer")
        require(isinstance(finding["body"], str) and 0 < len(finding["body"].strip()) <= 12000,
                "finding body is empty or oversized")
    advice = payload["test_scope"]
    require(isinstance(advice, dict) and set(advice) == {"labels", "reason"},
            "test_scope advice schema is not closed")
    require(isinstance(advice["labels"], list) and bool(advice["labels"]),
            "review must explicitly recommend test:none, test:full or suite labels")
    try:
        test_scope.labels_to_suites(policy, advice["labels"])
    except test_scope.ScopeError as error:
        raise ReviewScopeError(str(error)) from error
    require(isinstance(advice["reason"], str) and 0 < len(advice["reason"].strip()) <= 4000,
            "test scope reason is empty or oversized")
    return payload


def parse_review(policy, text):
    require(isinstance(text, (str, bytes)) and len(text) <= 400000, "review payload is missing or oversized")
    try:
        payload = json.loads(text, object_pairs_hook=change_scope.reject_duplicates)
    except (ValueError, UnicodeError) as error:
        # Never put arbitrary model output or backend stderr in diagnostics.
        raise ReviewScopeError("why: malformed review JSON; remedy: request a complete structured review") from error
    return validate_review(policy, payload)


def observe_attempt(policy, *, backend, returncode, output=None, error_class=None):
    """A trusted process adapter reports exit/timeout; JSON cannot certify itself.

    Findings are successful review completion, not a reason to change models.
    All returned errors are finite categories, never captured stderr or secrets.
    """
    require(backend in BACKENDS, "unknown backend")
    require(type(returncode) is int, "adapter must supply actual process return code")
    require(error_class is None or (isinstance(error_class, str) and error_class in ERRORS),
            "unknown backend error category")
    if error_class or returncode != 0:
        return {"backend": backend, "status": "failed", "error_class": error_class or "runtime_failure", "review": None}
    try:
        review = parse_review(policy, output)
    except ReviewScopeError:
        return {"backend": backend, "status": "failed", "error_class": "invalid_output", "review": None}
    return {"backend": backend, "status": "reviewed", "error_class": None, "review": review}


def validate_history(policy, history):
    require(isinstance(history, list) and len(history) <= len(BACKENDS), "invalid fallback history")
    for index, attempt in enumerate(history):
        require(isinstance(attempt, dict) and set(attempt) == {"backend", "status", "error_class", "review"},
                "attempt schema is not closed")
        require(attempt["backend"] == BACKENDS[index], "fallback order must be GLM then Kimi then Grok")
        if attempt["status"] == "reviewed":
            require(index == len(history) - 1 and attempt["error_class"] is None,
                    "a valid review must stop the fallback chain")
            validate_review(policy, attempt["review"])
        else:
            require(attempt["status"] == "failed" and isinstance(attempt["error_class"], str)
                    and attempt["error_class"] in ERRORS and attempt["review"] is None,
                    "failed attempt must retain a finite infrastructure error category")
    return history


def next_backend(policy, history):
    validate_history(policy, history)
    if len(history) == len(BACKENDS) or (history and history[-1]["status"] == "reviewed"):
        return None
    return BACKENDS[len(history)]


def failure_document(policy, identity, history):
    """Only the independent issues-capable reporter consumes this artifact.

    No finding text, backend stderr, token, PR body or diff enters the failure
    artifact. A failed review remains failed even when deterministic scope exists.
    """
    validate_history(policy, history)
    require(len(history) == len(BACKENDS) and all(a["status"] == "failed" for a in history),
            "failure artifact requires an actual failed or budget-blocked outcome for every backend")
    test_scope._identity(identity)
    require(identity["backend"] == "deterministic", "failed review has no successful model identity")
    core = {key: value for key, value in identity.items() if key != "backend"}
    request_id = test_scope.self_test.digest_of(core)
    return {"schema": FAILURE_SCHEMA, **core, "request_id": request_id,
            "policy_digest": policy.digest, "status": "not-reviewed",
            "attempts": [{"backend": a["backend"], "error_class": a["error_class"]} for a in history],
            "why": "all configured review backends are unavailable or returned invalid output",
            "remedy": "restore a backend or record authorized current-head human/agent review; keep deterministic test scope"}


def authenticate_context(identity, *, run, workflow, producer_job, pull,
                         repository_id, workflow_id, producer_job_name,
                         control_is_main_history, run_workflow_bytes, control_workflow_bytes):
    """Check API facts supplied independently of the downloaded model artifact.

    T2b must fetch the actual run attempt and workflow source bytes from trusted
    GitHub/Git endpoints. Display titles are never identities. Workflow code at
    the actual run SHA must equal the independently trusted control workflow;
    edited PR workflow code cannot mint scope authority even if it returns green.
    """
    test_scope._identity(identity)
    require(type(repository_id) is int and repository_id > 0 and type(workflow_id) is int and workflow_id > 0,
            "trusted repository and workflow numeric identities are required")
    require(isinstance(run, dict) and isinstance(workflow, dict) and isinstance(producer_job, dict)
            and isinstance(pull, dict), "independent API identity objects are missing")
    repository = run.get("repository")
    require(isinstance(repository, dict) and repository.get("id") == repository_id
            and repository.get("full_name") == identity["repository"], "run repository identity mismatch")
    require(run.get("id") == identity["run_id"] and run.get("run_attempt") == identity["run_attempt"],
            "run attempt identity mismatch")
    require(workflow.get("id") == workflow_id and run.get("workflow_id") == workflow_id
            and workflow.get("path") == ".github/workflows/pr-review.yml",
            "run is not the independently resolved review workflow")
    require(run.get("event") in {"pull_request", "workflow_dispatch"}, "unsupported review event")
    require(control_is_main_history is True, "control revision is not authenticated main history")
    require(isinstance(run_workflow_bytes, bytes) and bool(run_workflow_bytes)
            and run_workflow_bytes == control_workflow_bytes,
            "run workflow differs from trusted control code", "use the trusted main dispatch entry for this PR")
    require(producer_job.get("run_id") == identity["run_id"]
            and producer_job.get("run_attempt") == identity["run_attempt"]
            and producer_job.get("name") == producer_job_name
            and producer_job.get("status") == "completed" and producer_job.get("conclusion") == "success",
            "producer job did not complete under this exact run attempt")
    head, base = pull.get("head"), pull.get("base")
    require(isinstance(head, dict) and isinstance(base, dict), "PR head/base objects are missing")
    require(pull.get("number") == identity["pr_number"] and pull.get("state") == "open"
            and pull.get("draft") is False and pull.get("merged") is False
            and head.get("sha") == identity["head_sha"] and base.get("ref") == "main",
            "PR is stale or no longer reviewable")
    require(isinstance(head.get("repo"), dict) and head["repo"].get("id") == repository_id
            and head["repo"].get("full_name") == identity["repository"], "fork head cannot use repository review credentials")
    if run["event"] == "workflow_dispatch":
        require(run.get("head_branch") == "main" and run.get("head_sha") == identity["control_sha"],
                "manual review was not dispatched from exact trusted main control")
    else:
        pulls = run.get("pull_requests")
        require(isinstance(pulls, list) and any(isinstance(p, dict) and p.get("number") == identity["pr_number"]
                and isinstance(p.get("head"), dict) and p["head"].get("sha") == identity["head_sha"] for p in pulls),
                "PR event is not bound to the reviewed head")
    return dict(identity)


def _previous_labels(policy, identity, changed_paths, previous_records):
    """An unavailable new backend cannot erase already authenticated advice."""
    labels = set()
    for previous in previous_records:
        require(isinstance(previous, dict), "previous record is not an object")
        expected = {key: previous.get(key) for key in test_scope.IDENTITY_KEYS}
        for key in ("repository", "pr_number", "head_sha", "base_sha", "control_sha"):
            require(expected[key] == identity[key], "cannot combine reviews from different targets or controls")
        test_scope.validate_record(previous, policy, expected)
        require(previous["changed_paths"] == sorted(set(changed_paths)), "prior review diff inventory mismatch")
        labels.update(previous["ai_labels"])
    return labels


def prepare_publication(policy, identity, *, changed_paths, review, previous_records=()):
    """Create data for a separately guarded publisher, after authentication.

    previous_records are independently authenticated same-head records validated
    against their own retained policy by the caller. Revalidate current-policy
    records here; policy changes belong to the main interval consumer, not model
    evidence merging. Labels are only a display projection, never authority.
    """
    validate_review(policy, review)
    labels = _previous_labels(policy, identity, changed_paths, previous_records)
    labels.update(review["test_scope"]["labels"])
    record = test_scope.build_record(policy, changed_paths=changed_paths, ai_labels=sorted(labels), **identity)
    kind = record["effective"]["kind"]
    projection = [f"test:{kind}"] if kind in {"none", "full"} else [f"test:{s}" for s in record["effective"]["suites"]]
    # Legacy publisher remains summary/findings compatible during staging.
    legacy_review = {"summary": review["summary"], "findings": review["findings"]}
    return {"record": record, "labels": projection, "review": legacy_review}


def prepare_result(policy, identity, *, changed_paths, history, previous_records=()):
    """Bind the publisher result to the actual stopped fallback history."""
    validate_history(policy, history)
    require(bool(history) and next_backend(policy, history) is None,
            "fallback is not terminal", "finish the bounded backend chain before publishing")
    last = history[-1]
    if last["status"] == "reviewed":
        require(identity.get("backend") == last["backend"], "successful backend identity mismatch")
        return {"status": "reviewed", "failure": None,
                "publication": prepare_publication(policy, identity, changed_paths=changed_paths,
                                                     review=last["review"], previous_records=previous_records)}
    failure = failure_document(policy, identity, history)
    labels = _previous_labels(policy, identity, changed_paths, previous_records)
    fallback = test_scope.build_record(policy, changed_paths=changed_paths,
                                      ai_labels=sorted(labels), **identity)
    return {"status": "not-reviewed", "failure": failure,
            "publication": {"record": fallback, "labels": [], "review": None}}
