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

SCHEMA = "lmdj.incremental-batch.v1"
OUTCOMES = {"passed", "failed", "blocked", "cancelled", "infrastructure", "missing"}
DEBT_OUTCOMES = OUTCOMES - {"passed", "failed"}


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


def make_request(policy, *, request_id, kind, base_sha, target_sha, control_sha,
                 selection, origin_run, bound=True):
    require(isinstance(request_id, str) and bool(request_id), "missing request identity")
    require(kind in {"auto", "bootstrap", "node", "candidate"}, "unknown request kind")
    if base_sha is not None:
        exact_sha(base_sha)
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
    return {"id": request_id, "kind": kind, "base": base_sha,
            "target": exact_sha(target_sha), "control": exact_sha(control_sha),
            "policy": policy.digest, "selection": selection, "origin_run": identity(origin_run)}


def _request(policy, request):
    require(isinstance(request, dict) and set(request) == {
        "id", "kind", "base", "target", "control", "policy", "selection", "origin_run"},
        "request schema is not closed")
    rebuilt = make_request(policy, request_id=request["id"], kind=request["kind"],
                           base_sha=request["base"], target_sha=request["target"],
                           control_sha=request["control"], selection=request["selection"],
                           origin_run=request["origin_run"], bound=False)
    require(request == rebuilt, "request policy or canonical representation differs")


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
        require(data["kind"] in {"node", "candidate"}, "only explicit requests enter the fair queue")
        if data["id"] in result["requests"]:
            require(result["requests"][data["id"]] == data, "request ID reused with different target or scope")
        else:
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
        explicit = request["kind"] in {"node", "candidate"}
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
                else:
                    result["debts"].pop(suite, None)
                if outcome == "failed":
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
