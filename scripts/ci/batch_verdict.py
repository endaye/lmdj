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
COMMON_EVENT_SCHEMA = "lmdj.ci-batch-verdict.v2"
IDENTITY_KEYS = {"request_id", "request_kind", "base_sha", "target_sha", "control_sha",
                 "policy_digest", "run_id", "run_attempt"}
REQUIRED_OBSERVATION_KEYS = {"suite", "job", "run_id", "run_attempt", "target_revision", "conclusion"}
OPTIONAL_OBSERVATION_KEYS = {"artifact", "blocked_by", "started_at", "completed_at", "infrastructure_failure"}
COMMON_EVENT_KEYS = {"event_id", "kind", "request_id", "run_id", "run_attempt", "cause", "source", "blocked_suites"}
COMMON_SOURCE_KEYS = {"job", "result", "outputs", "digest"}


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


def _common_events(identity, selection, events):
    """Validate source-bound shared dependency events without inventing causes.

    The workflow producer supplies these from its real ``needs`` context. This
    validator checks the closed shape and exact request/run identity; the
    producer adapter additionally rebuilds the event from authenticated raw
    needs, so a rehashed or fixture-only event cannot become evidence.
    """
    require(isinstance(events, list), "common events must be a complete list")
    selected = set(selection["suites"])
    seen_causes = set()
    checked = []
    for event in events:
        require(isinstance(event, dict) and set(event) == COMMON_EVENT_KEYS,
                "common event schema is not closed")
        require(event["kind"] == "shared_dependency_failure",
                "unsupported common event kind")
        require(event["request_id"] == identity["request_id"]
                and type(event["run_id"]) is int and event["run_id"] == identity["run_id"]
                and type(event["run_attempt"]) is int and event["run_attempt"] == identity["run_attempt"],
                "common event identity differs from the exact request/run/attempt")
        require(isinstance(event["cause"], str) and bool(event["cause"])
                and event["cause"] not in seen_causes, "common event cause is missing or duplicated")
        source = event["source"]
        require(isinstance(source, dict) and set(source) == COMMON_SOURCE_KEYS
                and source["job"] == event["cause"] and source["result"] == "failure"
                and isinstance(source["outputs"], dict)
                and all(isinstance(key, str) and isinstance(value, str) for key, value in source["outputs"].items())
                and source["digest"] == self_test.digest_of({"result": source["result"], "outputs": source["outputs"]}),
                "common event source is not an exact authenticated failed dependency")
        blocked = event["blocked_suites"]
        require(isinstance(blocked, list) and bool(blocked) and blocked == sorted(set(blocked))
                and all(isinstance(suite, str) and suite in selected for suite in blocked),
                "common event has invalid selected blocked suites")
        expected_id = self_test.digest_of({"request_id": identity["request_id"],
                                           "run_id": identity["run_id"],
                                           "run_attempt": identity["run_attempt"],
                                           "cause": event["cause"]})
        require(event["event_id"] == expected_id, "common event ID is not keyed by exact request/run/attempt/cause")
        seen_causes.add(event["cause"])
        checked.append(deepcopy(event))
    return checked


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


def build(policy, identity, selection, observations, *, common_events=None):
    """Build new-schema evidence from strictly typed original observations.

Only selected-suite rows are accepted. A needs-context adapter must omit rows
for unselected jobs, not convert their skips into success. All policy suites
still appear in the report. Missing selected rows become uncovered obligations.
"""
    _identity(policy, identity)
    common_events = [] if common_events is None else _common_events(identity, selection, common_events)
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
    document = {"evidence_schema": COMMON_EVENT_SCHEMA if common_events else SCHEMA,
                "identity": deepcopy(identity), "selection": selection,
                "inventory_digest": policy.inventory.revision, "status": status, "suites": suites,
                "observations": deepcopy(sorted(observations, key=lambda row: (row["suite"], row["job"])))}
    if common_events:
        document["common_events"] = common_events
    document["evidence_digest"] = self_test.digest_of(document)
    return document


def validate(document, policy, expected_identity, expected_selection):
    """Exact independently supplied identity/scope, then full semantic replay.

Rehashing edited statuses cannot make them valid. Replacing observations with
invented results is prevented by caller provenance verification, not this hash.
"""
    base_keys = {"evidence_schema", "identity", "selection", "inventory_digest", "status", "suites",
                 "observations", "evidence_digest"}
    require(isinstance(document, dict) and base_keys <= set(document)
            and set(document) <= base_keys | {"common_events"}, "verdict schema is not closed")
    schema = document["evidence_schema"]
    require(schema in {SCHEMA, COMMON_EVENT_SCHEMA}, "unsupported scoped verdict schema")
    if schema == SCHEMA:
        require("common_events" not in document, "legacy verdict cannot carry common events")
    else:
        require("common_events" in document, "common-event verdict lacks its event list")
    require(document["identity"] == expected_identity, "verdict differs from independently resolved executor identity")
    require(document["selection"] == expected_selection, "verdict differs from frozen request scope")
    common_events = _common_events(expected_identity, expected_selection, document.get("common_events", []))
    require((schema == COMMON_EVENT_SCHEMA) == bool(common_events),
            "common-event schema does not match its event list")
    rebuilt = build(policy, expected_identity, expected_selection, document["observations"],
                    common_events=common_events)
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
