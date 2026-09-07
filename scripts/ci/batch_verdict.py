#!/usr/bin/env python3
"""Scoped observations, never legacy complete-test or release authority.

The caller independently authenticates control/run identity and frozen scope.
This module verifies structure and recomputes results, not provenance. It never
constructs a smaller self-test policy or fills unselected jobs with fake passes.
"""
from __future__ import annotations

from copy import deepcopy
import re

import self_test
import test_scope

SCHEMA = "lmdj.ci-batch-verdict.v1"
IDENTITY_KEYS = {"request_id", "request_kind", "base_sha", "target_sha", "control_sha",
                 "policy_digest", "run_id", "run_attempt"}
REQUIRED_OBSERVATION_KEYS = {"suite", "job", "run_id", "run_attempt", "target_revision", "conclusion"}
OPTIONAL_OBSERVATION_KEYS = {"artifact", "blocked_by", "started_at", "completed_at", "infrastructure_failure"}


class VerdictError(ValueError):
    pass


def require(condition, why):
    if not condition:
        raise VerdictError(f"why: {why}; remedy: rebuild from authenticated frozen request and exact-run job observations")


def _identity(policy, identity):
    require(isinstance(identity, dict) and set(identity) == IDENTITY_KEYS, "identity schema is not closed")
    require(isinstance(identity["request_id"], str) and bool(identity["request_id"]), "missing request ID")
    require(isinstance(identity["request_kind"], str)
            and identity["request_kind"] in {"auto", "bootstrap", "node", "candidate"}, "unknown request kind")
    for key in ("target_sha", "control_sha"):
        require(isinstance(identity[key], str) and re.fullmatch(r"[0-9a-f]{40}", identity[key]),
                f"{key} is not an exact revision")
    base = identity["base_sha"]
    require(base is None or isinstance(base, str) and re.fullmatch(r"[0-9a-f]{40}", base), "invalid baseline")
    require(identity["request_kind"] != "auto" or base is not None, "automatic interval requires a baseline")
    require(identity["policy_digest"] == policy.digest, "scope policy digest differs")
    require(type(identity["run_id"]) is int and identity["run_id"] > 0, "run ID must be a positive integer")
    require(type(identity["run_attempt"]) is int and identity["run_attempt"] == 1, "only a fresh first run attempt is accepted")


def _observations(observations):
    require(isinstance(observations, list), "observations must be a complete list")
    rows = []
    for document in observations:
        require(isinstance(document, dict) and REQUIRED_OBSERVATION_KEYS <= set(document)
                and set(document) <= REQUIRED_OBSERVATION_KEYS | OPTIONAL_OBSERVATION_KEYS,
                "observation schema is not closed")
        for key in ("suite", "job", "target_revision", "conclusion"):
            require(isinstance(document[key], str) and bool(document[key]), f"invalid observation {key}")
        for key in ("run_id", "run_attempt"):
            require(type(document[key]) is int and document[key] > 0, f"invalid observation {key}")
        if "artifact" in document:
            require(isinstance(document["artifact"], str), "artifact state must be a string")
        if "infrastructure_failure" in document:
            require(type(document["infrastructure_failure"]) is bool, "infrastructure flag must be boolean")
            require(not document["infrastructure_failure"] or document["conclusion"] == "failure",
                    "infrastructure failure contradicts job conclusion")
        for key in ("blocked_by", "started_at", "completed_at"):
            require(document.get(key) is None or isinstance(document[key], str) and bool(document[key]),
                    f"invalid optional observation {key}")
        require(not document.get("blocked_by") or document["conclusion"] == "skipped", "blocked dependency contradicts job conclusion")
        rows.append(self_test.Observation(**document))
    return rows


def _debt(suite, by_job):
    """Keep uncovered work even when another required job has a test failure."""
    outcomes = []
    for job in suite.jobs:
        row = by_job.get(job)
        if row is None:
            outcomes.append("missing")
        elif row.conclusion == "cancelled":
            outcomes.append("cancelled")
        elif row.conclusion == "timed_out" or row.infrastructure_failure or row.artifact == "failed":
            outcomes.append("infrastructure")
        elif row.conclusion == "skipped":
            witnesses = [by_job[alt] for alt in suite.alternatives.get(job, ())
                         if alt in by_job and by_job[alt].conclusion == "success"]
            if witnesses and any(witness.artifact != "failed" for witness in witnesses):
                continue
            outcomes.append("blocked" if row.blocked_by else "infrastructure")
    for outcome in ("infrastructure", "cancelled", "missing", "blocked"):
        if outcome in outcomes:
            return outcome
    return None


def build(policy, identity, selection, observations):
    """Build new-schema evidence from strictly typed original observations.

Only selected-suite rows are accepted. A needs-context adapter must omit rows
for unselected jobs, not convert their skips into success. All policy suites
still appear in the report. Missing selected rows become uncovered obligations.
"""
    _identity(policy, identity)
    try:
        normalized = test_scope.union_selections(policy, [selection])
        require(selection == normalized, "frozen selection omits transitive consumers")
        selection = normalized
    except test_scope.ScopeError as error:
        raise VerdictError(str(error)) from error
    if identity["request_kind"] in {"bootstrap", "node", "candidate"}:
        require(selection["kind"] == "full", "explicit and bootstrap requests require full selection")
    rows = _observations(observations)
    selected = set(selection["suites"])
    require(all(row.suite in selected for row in rows), "observation belongs to an unselected or unknown suite")
    # Keep the complete authoritative policy. This temporary identity is not
    # serialized as legacy evidence and uses the NEW schema even internally.
    aggregate_identity = self_test.Identity(SCHEMA, identity["request_kind"], identity["control_sha"],
                                            identity["target_sha"], identity["run_id"], 1,
                                            policy.inventory.revision)
    if rows:
        judged = self_test.aggregate(aggregate_identity, policy.inventory, rows)
        require(judged.status != self_test.BATCH_INVALID, "; ".join(judged.diagnostics))
        results = {result.id: result for result in judged.suites}
    else:
        # aggregate rejects an empty *complete* batch. No fake observation is
        # supplied to evade it: its same per-suite judge records true missing.
        results = {suite.id: self_test._judge_suite(suite, {}) for suite in policy.inventory.suites}
    by_job = {row.job: row for row in rows}
    suites = []
    for suite in sorted(policy.inventory.suites, key=lambda item: item.id):
        if suite.id not in selected:
            suites.append({"id": suite.id, "selected": False, "status": "not-selected",
                           "scheduler_outcome": None, "verification_debt": False, "failures": [],
                           "jobs": {}, "diagnostics": ["outside this frozen request's selected scope; not a pass"]})
            continue
        result = results[suite.id]
        debt = _debt(suite, by_job)
        failures = sorted(row.job for row in rows if row.suite == suite.id and row.conclusion == "failure"
                          and not row.infrastructure_failure)
        status = result.status
        if debt and status == "passed":
            status = "infrastructure_failure"  # alternative's failed evidence is not reusable success
        outcome = debt or ("passed" if status == "passed" else "failed")
        diagnostics = list(result.diagnostics)
        if debt:
            diagnostics.append(f"why: selected work remains uncovered ({debt}); remedy: preserve verification debt and repair its cause")
        suites.append({"id": suite.id, "selected": True, "status": status,
                       "scheduler_outcome": outcome, "verification_debt": debt is not None,
                       "failures": failures, "jobs": dict(sorted(result.jobs.items())), "diagnostics": diagnostics})
    status = "not-required" if not selected else (
        "passed" if all(suite["status"] == "passed" for suite in suites if suite["selected"]) else "failed")
    document = {"evidence_schema": SCHEMA, "identity": deepcopy(identity), "selection": selection,
                "inventory_digest": policy.inventory.revision, "status": status, "suites": suites,
                "observations": deepcopy(sorted(observations, key=lambda row: (row["suite"], row["job"])))}
    document["evidence_digest"] = self_test.digest_of(document)
    return document


def validate(document, policy, expected_identity, expected_selection):
    """Exact independently supplied identity/scope, then full semantic replay.

Rehashing edited statuses cannot make them valid. Replacing observations with
invented results is prevented by caller provenance verification, not this hash.
"""
    require(isinstance(document, dict) and set(document) == {
        "evidence_schema", "identity", "selection", "inventory_digest", "status", "suites",
        "observations", "evidence_digest"}, "verdict schema is not closed")
    require(document["evidence_schema"] == SCHEMA, "unsupported scoped verdict schema")
    require(document["identity"] == expected_identity, "verdict differs from independently resolved executor identity")
    require(document["selection"] == expected_selection, "verdict differs from frozen request scope")
    rebuilt = build(policy, expected_identity, expected_selection, document["observations"])
    try:
        matches = self_test.canonical_json(document) == self_test.canonical_json(rebuilt)
    except (TypeError, ValueError):
        matches = False
    require(matches, "verdict differs from recomputed original job observations")
    return deepcopy(rebuilt)


def scheduler_outcomes(document, policy, expected_identity, expected_selection):
    """Project selected-only outcomes after validation; debt wins over failure.

Reporter must separately retain each suite's failures list: a mixed suite can
have both a real product failure and uncovered jobs. Historical candidates must
still be isolated by the scheduler's request kind, not inferred here.
"""
    checked = validate(document, policy, expected_identity, expected_selection)
    return {suite["id"]: suite["scheduler_outcome"] for suite in checked["suites"] if suite["selected"]}
