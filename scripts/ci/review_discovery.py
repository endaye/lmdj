#!/usr/bin/env python3
"""PR Review discovery journal reducer, not an HTTP verifier or scheduler.

Replay only events independently authenticated by the existing journal transport.
An inventory's complete flag/digest and a disposition's receipt digest are
structural commitments, not proof of API pagination, workflow or source identity.
The future adapter must authenticate those facts before appending. No network,
Issue allocation, scheduler state or business POST is performed here.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re

SCHEMA = "lmdj.ci-review-discovery.v1"
TERMINAL = frozenset({"valid-review", "closed-mapping", "failure-queued"})
UNRESOLVED = frozenset({"pending", "unresolved", "retention-lost"})


def require(condition, why):
    if not condition:
        raise ValueError(f"why: {why}; remedy: reconcile the exact authenticated review inventory/receipt; never advance over a gap or fabricate review success")


def closed(value, keys):
    require(isinstance(value, dict) and set(value) == set(keys), "discovery object fields are not closed")


def text(value):
    require(isinstance(value, str) and bool(value.strip()), "required discovery text is empty")
    return value


def positive(value):
    require(type(value) is int and value > 0, "run/workflow identity must be a positive integer")
    return value


def hex_value(value, size):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % size, value) is not None,
            "source or receipt digest is not exact")
    return value


def timestamp(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value) is not None,
            "discovery time must be exact UTC seconds")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        require(False, "discovery time is invalid")
    return parsed


def canonical(value):
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()
    except (TypeError, ValueError):
        require(False, "discovery commitment is not finite JSON data")
    return encoded


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def identity(value):
    closed(value, {"run_id", "attempt"})
    positive(value["run_id"])
    positive(value["attempt"])
    return f"{value['run_id']}/{value['attempt']}"


def run_record(value):
    closed(value, {"identity", "created_at"})
    key = identity(value["identity"])
    timestamp(value["created_at"])
    return key


def new_state(*, epoch, repository, workflow_id, source_floor):
    text(epoch)
    require(isinstance(repository, str) and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is not None,
            "repository identity is invalid")
    positive(workflow_id)
    closed(source_floor, {"control_sha", "created_at"})
    hex_value(source_floor["control_sha"], 40)
    timestamp(source_floor["created_at"])
    return {"schema": SCHEMA, "epoch": epoch, "repository": repository,
            "workflow_id": workflow_id, "source_floor": deepcopy(source_floor),
            "generation": 0, "inventory_frontier": source_floor["created_at"],
            "windows": [], "gaps": [], "runs": {}, "seen_events": {}}


def _overlap(a, b):
    return a["start"] < b["end"] and b["start"] < a["end"]


def _prefix_known(state, end):
    cursor = state["inventory_frontier"]
    for interval in sorted([*state["windows"], *state["gaps"]], key=lambda x: x["start"]):
        if interval["start"] > cursor:
            break
        cursor = max(cursor, interval["end"])
    return cursor >= end


def _gap(state, data):
    closed(data, {"start", "end", "why", "remedy"})
    require(timestamp(data["start"]) < timestamp(data["end"]), "inventory gap is empty or reversed")
    text(data["why"])
    text(data["remedy"])
    require(data["start"] >= state["inventory_frontier"] and _prefix_known(state, data["start"]),
            "gap would hide an unregistered interval or downgrade completed history")
    require(not any(_overlap(data, w) for w in state["windows"]), "gap overlaps already complete inventory")
    # Canonical disjoint segments preserve every overlapping diagnostic origin.
    reason = deepcopy(data)
    intervals = [*state["gaps"], {"start": data["start"], "end": data["end"], "reasons": [reason]}]
    boundaries = sorted({i[k] for i in intervals for k in ("start", "end")})
    normalized = []
    for start, end in zip(boundaries, boundaries[1:]):
        reasons = {digest(r): r for i in intervals if i["start"] <= start < i["end"] for r in i["reasons"]}
        if not reasons:
            continue
        segment = {"start": start, "end": end, "reasons": [deepcopy(reasons[k]) for k in sorted(reasons)]}
        if normalized and normalized[-1]["end"] == start and normalized[-1]["reasons"] == segment["reasons"]:
            normalized[-1]["end"] = end
        else:
            normalized.append(segment)
    state["gaps"] = normalized


def _register(state, record):
    key = run_record(record)
    require(key not in state["runs"], "review attempt was already inventoried")
    for prior in state["runs"].values():
        if prior["identity"]["run_id"] == record["identity"]["run_id"]:
            require(prior["created_at"] == record["created_at"], "rerun changed the original run creation time")
    state["runs"][key] = {**deepcopy(record), "status": "pending", "proof": {
        "why": "inventoried review has no authenticated disposition",
        "remedy": "authenticate this exact attempt; do not substitute the latest attempt"}}


def _inventory(state, data):
    closed(data, {"start", "end", "runs", "total_count", "inventory_digest", "complete"})
    require(timestamp(data["start"]) < timestamp(data["end"]), "inventory window is empty or reversed")
    require(data["start"] >= state["inventory_frontier"] and _prefix_known(state, data["start"]),
            "inventory would overlap or jump an unlisted interval")
    require(not any(_overlap(data, w) for w in state["windows"]), "inventory overlaps a previously completed window")
    require(data["complete"] is True, "partial API inventory cannot advance the frontier")
    require(isinstance(data["runs"], list) and type(data["total_count"]) is int
            and data["total_count"] == len(data["runs"]), "inventory total does not match all supplied runs")
    require(hex_value(data["inventory_digest"], 64) == digest(data["runs"]), "inventory digest differs from complete objects")
    keys = [run_record(record) for record in data["runs"]]
    require(len(keys) == len(set(keys)), "duplicate exact review attempt in inventory")
    run_ids = [record["identity"]["run_id"] for record in data["runs"]]
    require(len(run_ids) == len(set(run_ids)), "initial inventory repeats a run with another attempt")
    for record in data["runs"]:
        require(record["identity"]["attempt"] == 1, "initial inventory must retain the original first attempt")
        require(data["start"] <= record["created_at"] < data["end"], "run creation time is outside its half-open window")
        _register(state, record)
    state["windows"].append(deepcopy(data))
    state["windows"].sort(key=lambda window: window["start"])
    remaining = []
    for gap in state["gaps"]:
        if not _overlap(gap, data):
            remaining.append(gap)
        else:
            if gap["start"] < data["start"]:
                remaining.append({**deepcopy(gap), "end": data["start"]})
            if gap["end"] > data["end"]:
                remaining.append({**deepcopy(gap), "start": data["end"]})
    state["gaps"] = remaining
    for window in state["windows"]:
        if window["start"] == state["inventory_frontier"]:
            state["inventory_frontier"] = window["end"]


def _attempt(state, data):
    # A late rerun does not belong to a new created-at scan window. Discovery
    # adapters must revisit known IDs/consume callbacks, even behind frontier.
    closed(data, {"identity", "created_at"})
    run_record(data)
    require(data["identity"]["attempt"] > 1, "late-attempt event cannot replace initial inventory")
    require(f"{data['identity']['run_id']}/1" in state["runs"], "late attempt lacks the inventoried original run")
    _register(state, data)
    state["runs"][identity(data["identity"])]["proof"] = {
        "why": "later attempt requires independent source admissibility",
        "remedy": "authenticate the exact attempt under the review protocol or retain an explicit source gap"}


def _disposition(state, data):
    closed(data, {"identity", "status", "proof"})
    key = identity(data["identity"])
    require(key in state["runs"], "disposition refers to an uninventoried attempt")
    status = data["status"]
    require(isinstance(status, str) and status in TERMINAL | UNRESOLVED, "unknown review disposition")
    proof = data["proof"]
    if status in UNRESOLVED:
        closed(proof, {"why", "remedy"})
        text(proof["why"])
        text(proof["remedy"])
    else:
        closed(proof, {"identity", "control_sha", "receipt_digest"} |
               ({"outbox_key"} if status == "failure-queued" else set()))
        require(identity(proof["identity"]) == key, "receipt does not resolve the original exact review attempt")
        hex_value(proof["control_sha"], 40)
        hex_value(proof["receipt_digest"], 64)
        if status == "failure-queued":
            hex_value(proof["outbox_key"], 64)
    prior = state["runs"][key]
    if prior["status"] in TERMINAL:
        require(prior["status"] == status and prior["proof"] == proof,
                "old or conflicting disposition would overwrite authenticated terminal evidence")
    if prior["status"] == "retention-lost":
        require(status == "retention-lost" or status in TERMINAL,
                "a lost-evidence obligation requires an exact positive receipt to resolve")
    prior.update(status=status, proof=deepcopy(proof))


def reduce(state, event):
    """Apply one already-authenticated journal event without mutating inputs.

    A duplicate identity requires the entire original event to match. Callers
    restore state by replay, not by trusting an arbitrary serialized checkpoint.
    """
    require(isinstance(state, dict) and state.get("schema") == SCHEMA, "unsupported discovery state")
    closed(event, {"id", "epoch", "generation", "type", "data"})
    text(event["id"])
    require(event["epoch"] == state["epoch"], "discovery event belongs to another epoch")
    if event["id"] in state["seen_events"]:
        # Python equality aliases False/0 and 1/1.0, including nested fields.
        # Canonical JSON preserves those types before this early replay return.
        require(canonical(state["seen_events"][event["id"]]) == canonical(event),
                "event identity was reused with different complete content")
        return deepcopy(state)
    require(type(event["generation"]) is int and event["generation"] == state["generation"], "discovery event generation is not next")
    handlers = {"inventory": _inventory, "inventory-gap": _gap, "attempt": _attempt, "disposition": _disposition}
    require(isinstance(event["type"], str) and event["type"] in handlers, "unknown discovery event type")
    result = deepcopy(state)
    handlers[event["type"]](result, event["data"])
    result["seen_events"][event["id"]] = deepcopy(event)
    result["generation"] += 1
    return result


def replay(config, events):
    closed(config, {"epoch", "repository", "workflow_id", "source_floor"})
    require(isinstance(events, list), "discovery journal must be a complete ordered event list")
    state = new_state(**config)
    for event in events:
        state = reduce(state, event)
    return state


def summary(state):
    unresolved = {key: deepcopy(value) for key, value in state["runs"].items()
                  if value["status"] in UNRESOLVED}
    return {"inventory_frontier": state["inventory_frontier"],
            "inventory_gaps": deepcopy(state["gaps"]),
            "latest_inventory_end": max([state["inventory_frontier"], *[w["end"] for w in state["windows"]]]),
            "unresolved": unresolved,
            "retention_lost": [key for key, value in unresolved.items() if value["status"] == "retention-lost"],
            "queued_failures": {key: value["proof"]["outbox_key"] for key, value in state["runs"].items()
                                if value["status"] == "failure-queued"},
            "inventoried_attempts_resolved": not unresolved,
            "coverage": "inventoried attempts only; later-attempt discovery and outbox delivery are separate"}
