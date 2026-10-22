#!/usr/bin/env python3
"""Pure incremental scheduler. No credentials, GitHub writes or test execution.

Callers authenticate events, hold the short writer lock and persist the returned
state BEFORE acting on it. Booleans describing Git/run observations are trusted
adapter assertions, never fields accepted directly from PR/model input.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

import test_scope
import daily_verification

SCHEMA = "lmdj.incremental-batch.v1"
DEBT_OUTCOMES = {"blocked", "cancelled", "infrastructure", "missing"}
OUTCOMES = DEBT_OUTCOMES | {"passed", "failed", "quick-passed", "quick-failed", "deferred"}
KINDS = {"auto", "bootstrap", "node", "candidate", "retry"}
EXPLICIT_KINDS = {"node", "candidate", "retry"}
# A `failed` suite qualifies for a retry only when every failing job ended
# with one of these authenticated API conclusions: the platform stopped the
# job, no test failed. A `failure` conclusion is a test failure and never
# qualifies (#2422 item 8, #2404 item 2).
ENVIRONMENTAL_CONCLUSIONS = {"timed_out", "cancelled"}


class BatchError(ValueError):
    pass


def require(condition, why, remedy="reconcile authenticated state before admitting another batch"):
    if not condition:
        raise BatchError(f"why: {why}; remedy: {remedy}")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def exact_sha(value):
    require(isinstance(value, str) and re.fullmatch("[0-9a-f]{40}", value), "invalid exact SHA")
    return value


def identity(value):
    require(isinstance(value, dict) and set(value) == {"run_id", "attempt"}, "invalid run identity")
    require(all(type(v) is int and v > 0 for v in value.values()), "run identity must be positive integers")
    require(value["attempt"] == 1, "partial Actions reruns are not fresh requests",
            "create a new recorded request and workflow run")
    return deepcopy(value)


def new_state(epoch):
    require(isinstance(epoch, str) and bool(epoch), "missing recovery epoch")
    return {"schema": SCHEMA, "epoch": epoch, "generation": 0, "processed": None,
            "pending": None, "active": None, "queue": [], "requests": {},
            "results": {}, "debts": {}, "failures": [], "events": {},
            "history_unknown": True, "blocked": None, "recovery_requested": False}


def _retry_of(retry_of, selection):
    """Validate the frozen proof shape of a retry request; the reducer and the
    release consumer cross-check it against the original result and the API."""
    require(isinstance(retry_of, dict) and set(retry_of) == {"request", "environmental"}
            and isinstance(retry_of["request"], str) and bool(retry_of["request"])
            and isinstance(retry_of["environmental"], dict), "retry proof schema is not closed")
    environmental = retry_of["environmental"]
    require(set(environmental) == set(selection["suites"]) and bool(environmental),
            "retry proof must name exactly the retried suites")
    for suite, proof in environmental.items():
        require(isinstance(proof, dict) and set(proof) == {"outcome", "jobs"}
                and proof["outcome"] in DEBT_OUTCOMES | {"failed"} and isinstance(proof["jobs"], dict),
                f"retry proof for {suite} is not closed")
        jobs = proof["jobs"]
        require(all(isinstance(job, str) and bool(job) and isinstance(conclusion, str)
                    for job, conclusion in jobs.items()), f"retry proof for {suite} names invalid jobs")
        require(all(conclusion != "failure" for conclusion in jobs.values()),
                f"a test failure never qualifies for a retry ({suite})")
        require(all(conclusion in ENVIRONMENTAL_CONCLUSIONS for conclusion in jobs.values()),
                f"retry proof for {suite} names a non-environmental job conclusion")
        if proof["outcome"] == "failed":
            require(bool(jobs), f"a failed suite needs its failing jobs' environmental conclusions ({suite})")
        else:
            require(not jobs, f"a {proof['outcome']} suite carries no job proof ({suite})")
    return deepcopy(retry_of)


def make_request(policy, *, request_id, kind, base_sha, target_sha, control_sha,
                 selection, origin_run, bound=True, verification=None, retry_of=None):
    require(isinstance(request_id, str) and bool(request_id), "missing request identity")
    require(kind in KINDS, "unknown request kind")
    require((kind == "retry") == (retry_of is not None), "only a retry request carries retry_of")
    if base_sha is not None:
        exact_sha(base_sha)
    if kind == "retry":
        # A retry re-runs lanes; it is not a change, so no dependency closure.
        require(isinstance(selection, dict) and set(selection) == {"kind", "suites", "reasons"},
                "selection schema is not closed")
        selection = test_scope._selection(policy, selection["suites"], selection["reasons"])
    else:
        selection = test_scope.union_selections(policy, [selection])
    if bound:
        # Construction bounds the explanation here, whatever produced the
        # selection: the auto interval, bootstrap, explicit debt recovery or an
        # operator command. Validation below passes bound=False: rebuilding a
        # STORED request must reproduce exactly what was written, including a
        # record from before this bound existed, or replay would fail closed on
        # its own history. The bound is idempotent, so a request constructed
        # here still rebuilds to itself under bound=False.
        selection = test_scope._selection(policy, selection["suites"],
                                          test_scope.bounded_reasons(selection["reasons"]))
    if kind in {"bootstrap", "node", "candidate"}:
        require(selection["kind"] == "full", "bootstrap and explicit requests require full scope")
    if kind == "retry":
        require(bool(selection["suites"]), "retry selects no suite")
    request = {"id": request_id, "kind": kind, "base": base_sha,
            "target": exact_sha(target_sha), "control": exact_sha(control_sha),
            "policy": policy.digest, "selection": selection, "origin_run": identity(origin_run)}
    if verification is not None:
        require(kind == "auto", "only automatic requests may use daily workloads")
        request["verification"] = daily_verification.validate(verification, selection["suites"])
    if retry_of is not None:
        request["retry_of"] = _retry_of(retry_of, selection)
    return request


def missing_outcomes(request):
    workloads = request.get("verification", {})
    return {suite: "deferred" if workloads.get(suite) == "deferred" else "missing"
            for suite in request["selection"]["suites"]}


def _request(policy, request):
    keys = {"id", "kind", "base", "target", "control", "policy", "selection", "origin_run"}
    require(isinstance(request, dict) and set(request) in (keys, keys | {"verification"}, keys | {"retry_of"}),
        "request schema is not closed")
    rebuilt = make_request(policy, request_id=request["id"], kind=request["kind"],
                           base_sha=request["base"], target_sha=request["target"],
                           control_sha=request["control"], selection=request["selection"],
                           origin_run=request["origin_run"], bound=False, verification=request.get("verification"),
                           retry_of=request.get("retry_of"))
    require(request == rebuilt, "request policy or canonical representation differs")


def _retry_admissible(state, request):
    """Journal truth a retry must agree with: its original candidate's result."""
    retry_of = request["retry_of"]
    original = state["requests"].get(retry_of["request"])
    require(original is not None and original["kind"] == "candidate", "retry names no candidate request")
    require(original["target"] == request["target"], "retry must target the same target as its candidate")
    require(original["policy"] == request["policy"], "retry must share its candidate's scope policy")
    result = state["results"].get(original["id"])
    require(result is not None, "original candidate has no durable result")
    not_passed = {suite for suite, outcome in result["outcomes"].items() if outcome != "passed"}
    require(set(request["selection"]["suites"]) == not_passed,
            "retry must cover exactly the suites the candidate did not pass")
    for suite, proof in retry_of["environmental"].items():
        require(proof["outcome"] == result["outcomes"][suite], f"retry proof for {suite} differs from the candidate result")
    require(not any(other["kind"] == "retry" and other["retry_of"]["request"] == original["id"]
                    for other in state["requests"].values()), "a candidate is retried at most once")


def required_selection(state, policy, selection):
    """Add executable debt, not paused debt. Invoke only for actual new changes.

Newly selected suites remain selected even if their previous debt is paused.
No-change retry requires an explicit resume, never a clock tick.
"""
    debt = [suite for suite, record in state["debts"].items() if not record["paused"]]
    extra = test_scope._selection(policy, debt, ["carry executable verification debt"] if debt else [])
    return test_scope.union_selections(policy, [selection, extra])


def reduce(state, event, policy):
    """Return a new state; exceptions leave the input untouched.

Events are version-fenced by epoch and generation. Exact event replay is a
no-op even after newer events. Reusing an event ID with different data fails.
Result and advance are separate durable transitions. The adapter must never
publish this returned state as committed if journal/anchor persistence fails.
"""
    require(isinstance(state, dict) and state.get("schema") == SCHEMA, "unknown scheduler state")
    require(isinstance(event, dict) and {"id", "epoch", "generation", "type", "data"} == set(event),
            "event schema is not closed")
    require(isinstance(event["id"], str) and bool(event["id"]), "missing event ID")
    fingerprint = digest(event)
    if event["id"] in state["events"]:
        require(state["events"][event["id"]] == fingerprint, "event ID reused with different content")
        return deepcopy(state)
    require(event["epoch"] == state["epoch"], "old recovery epoch attempted a write")
    require(type(event["generation"]) is int and event["generation"] == state["generation"],
            "stale generation attempted a write")
    data, kind = event["data"], event["type"]
    require(isinstance(data, dict), "event data must be an object")
    result = deepcopy(state)
    if kind == "observe":
        require(set(data) == {"target", "descends_pending"}, "invalid main observation")
        exact_sha(data["target"])
        require(data["descends_pending"] is True, "main observation is stale or ancestry is unknown",
                "reread actual main and verify ancestry; do not trust event ordering")
        result["pending"] = data["target"]
    elif kind == "enqueue":
        _request(policy, data)
        require(data["kind"] in EXPLICIT_KINDS, "only explicit requests enter the fair queue")
        if data["id"] in result["requests"]:
            require(result["requests"][data["id"]] == data, "request ID reused with different target or scope")
        else:
            if data["kind"] == "retry":
                _retry_admissible(result, data)
            result["requests"][data["id"]] = deepcopy(data)
            result["queue"].append(data["id"])
    elif kind == "admit":
        require(set(data) == {"request", "executor_run", "history_complete", "ancestor", "old_runs_terminal"},
                "invalid admission observations")
        executor = identity(data["executor_run"])
        request = data["request"]
        _request(policy, request)
        require(result["active"] is None, "a batch already owns the heavy budget")
        require(result["blocked"] is None, "admission is explicitly blocked")
        require(data["history_complete"] is True, "complete target history was not verified")
        require(data["ancestor"] is True, "baseline is not a verified target ancestor")
        if result["processed"] is None:
            require(data["old_runs_terminal"] is True, "old controlled runs may still execute",
                    "verify every old controlled run is terminal before any reconstructed-state admission")
        explicit = request["kind"] in EXPLICIT_KINDS
        if explicit:
            require(result["queue"] and result["queue"][0] == request["id"],
                    "explicit requests must follow the durable fair queue")
            require(result["requests"][request["id"]] == request, "queued request changed")
            result["queue"].pop(0)
        else:
            require(not result["queue"], "an explicit request is waiting at this batch boundary")
            require(request["id"] not in result["requests"], "completed request cannot be readmitted")
            require(request["target"] == result["pending"], "request does not freeze the observed main tip")
            require(request["base"] == result["processed"], "request interval does not start at processed cursor")
            if request["kind"] == "bootstrap":
                require(result["processed"] is None, "bootstrap cannot overwrite an existing cursor")
                require(data["old_runs_terminal"] is True, "old controlled runs may still execute",
                        "verify every old controlled run is terminal before bootstrap")
            else:
                require(result["processed"] is not None, "missing baseline requires full bootstrap")
                require(request["target"] != result["processed"] or result["recovery_requested"],
                        "no new main changes require no automatic batch")
            needed = required_selection(result, policy, request["selection"])
            require(set(needed["suites"]) <= set(request["selection"]["suites"]),
                    "request omitted executable verification debt")
            require(all(record["paused"] or request.get("verification", {}).get(suite, "full") == "full"
                        for suite, record in result["debts"].items()),
                    "executable full verification debt requires complete workload")
            result["requests"][request["id"]] = deepcopy(request)
            result["recovery_requested"] = False
        result["active"] = {"request_id": request["id"], "executor_run": executor, "claim": None}
    elif kind == "claim":
        require(set(data) == {"request_id", "run"}, "invalid execution claim")
        active = result["active"]
        require(active is not None and active["request_id"] == data["request_id"], "claim targets no active request")
        run = identity(data["run"])
        require(run == active["executor_run"], "DAG execution must use the admitted executor run")
        require(active["claim"] in (None, run), "another execution owns this request")
        active["claim"] = run
    elif kind == "result":
        require(set(data) == {"request_id", "run", "target", "policy", "outcomes", "reference", "terminal"},
                "result schema is not closed")
        active = result["active"]
        require(active is not None and active["request_id"] == data["request_id"], "result is not for the active request")
        request = result["requests"][data["request_id"]]
        require(identity(data["run"]) == active["claim"], "result does not belong to the claimed run")
        require(data["target"] == request["target"] and data["policy"] == request["policy"],
                "result target or policy differs from frozen request")
        require(data["terminal"] is True, "run is not proven terminal")
        require(isinstance(data["reference"], str) and bool(data["reference"]), "missing durable result reference")
        require(isinstance(data["outcomes"], dict) and set(data["outcomes"]) == set(request["selection"]["suites"]),
                "result does not enumerate every selected suite")
        require(all(isinstance(value, str) and value in OUTCOMES for value in data["outcomes"].values()),
                "unknown suite outcome")
        for suite, outcome in data["outcomes"].items():
            mode = request.get("verification", {}).get(suite, "full")
            allowed = ({"deferred"} if mode == "deferred" else
                       DEBT_OUTCOMES | ({"passed", "failed"} if mode == "full" else
                                        {"quick-passed", "quick-failed"}))
            require(outcome in allowed, "suite outcome contradicts frozen verification workload")
        previous = result["results"].get(data["request_id"])
        require(previous is None or previous == data, "terminal result cannot be rewritten")
        result["results"][data["request_id"]] = deepcopy(data)
    elif kind == "advance":
        require(set(data) == {"request_id"}, "invalid advance event")
        active = result["active"]
        require(active is not None and active["request_id"] == data["request_id"], "advance is not for the active request")
        request = result["requests"][data["request_id"]]
        observation = result["results"].get(data["request_id"])
        require(observation is not None, "result must be persisted before advancing")
        if request["kind"] in {"auto", "bootstrap"}:
            result["processed"] = request["target"]
            for suite, outcome in observation["outcomes"].items():
                if outcome in DEBT_OUTCOMES:
                    attempts = result["debts"].get(suite, {}).get("attempts", 0) + 1
                    result["debts"][suite] = {"target": request["target"], "attempts": attempts,
                                              "paused": attempts >= 2, "outcome": outcome,
                                              "reference": observation["reference"]}
                elif request.get("verification", {}).get(suite, "full") == "full":
                    result["debts"].pop(suite, None)
                if outcome in {"failed", "quick-failed"}:
                    result["failures"].append({"suite": suite, "target": request["target"],
                                               "reference": observation["reference"]})
        result["active"] = None
    elif kind == "resume":
        require(set(data) == {"suites", "reason"} and isinstance(data["suites"], list)
                and isinstance(data["reason"], str) and bool(data["reason"]), "resume needs suites and an explicit reason")
        require(all(suite in result["debts"] for suite in data["suites"]), "resume names unknown debt")
        for suite in data["suites"]:
            result["debts"][suite]["paused"] = False
            result["debts"][suite]["attempts"] = 0
        require(bool(data["suites"]), "empty resume cannot authorize a new no-change batch")
        result["recovery_requested"] = True
    elif kind == "block":
        require(set(data) == {"why", "remedy"} and all(isinstance(v, str) and v for v in data.values()),
                "block must explain why and remedy")
        result["blocked"] = deepcopy(data)
    elif kind == "unblock":
        require(set(data) == {"reconciled"} and data["reconciled"] is True, "unblock requires verified reconciliation")
        result["blocked"] = None
    else:
        require(False, "unknown scheduler event")
    result["events"][event["id"]] = fingerprint
    result["generation"] += 1
    return result
