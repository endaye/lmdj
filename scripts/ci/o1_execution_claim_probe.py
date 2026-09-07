#!/usr/bin/env python3
"""Isolated C1: real durable full claim, controlled exit before executable output.

No cancellation, dispatch, initialization, artificial baseline or product run.
Ordinary fresh settlement owns recovery. The fixed reviewed storage manifest,
not an empty checkpoint, binds the claim role and epoch.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re

import batch_runtime
import incremental_batch as batch
from incremental_batch_journal import Journal
import report_runtime

MANIFEST = "scripts/ci/o1_recovery_storage.json"
OPERATION = "claim-before-output"
FAULT = "after-durable-claim"
PROTECTED = {807, 817, 819}


def require(ok, why):
    if not ok:
        raise ValueError("why: " + why + "; remedy: stop C1 and verify the fixed claim role and actual journal/run; recover only with ordinary settlement")


class ControlledExit(SystemExit):
    def __init__(self, identity):
        self.identity = identity
        super().__init__(87)


def parse_intent(value):
    require(isinstance(value, dict) and set(value) in ({"operation"}, {"operation", "fault"})
            and value.get("operation") == OPERATION, "C1 intent is not closed")
    fault = value.get("fault", "disabled")
    require(fault in {"disabled", FAULT}, "unknown C1 fault; cancellation is not supported")
    return {"operation": OPERATION, "fault": fault}


def validate_manifest(value):
    require(isinstance(value, dict) and set(value) == {"scheduler", "outbox", "claim"}, "storage role map is not closed")
    fields = {"repository", "issue_number", "issue_node_id", "bot_node_id", "workflow_id", "epoch"}
    for role, item in value.items():
        require(isinstance(item, dict) and set(item) == fields, "role config is not six-field Runtime input")
        require(all(type(item[k]) is int and item[k] > 0 for k in ("issue_number", "workflow_id"))
                and item["issue_number"] not in PROTECTED, "role has invalid or protected numeric identity")
        require(all(isinstance(item[k], str) and bool(item[k]) for k in fields - {"issue_number", "workflow_id"}),
                "role has empty or malformed string identity")
        prefix = "o1-claim-" if role == "claim" else "o1-recovery-" + role + "-"
        require(re.fullmatch(re.escape(prefix) + r"[a-z0-9-]{1,100}", item["epoch"]), "role epoch has the wrong namespace")
    for key in ("issue_number", "issue_node_id", "epoch"):
        require(len({item[key] for item in value.values()}) == 3, "storage roles alias " + key)
    require(len({(i["repository"], i["bot_node_id"], i["workflow_id"]) for i in value.values()}) == 1,
            "storage roles disagree on existing writer authority")
    return deepcopy(value)


def readonly_history(runtime):
    source = runtime.journal()
    journal = Journal(source.issue_id, source.transport, report_runtime.ReadOnlyAnchor(source.anchor),
                      source.authenticate, source.lock_held)
    checkpoint = source.anchor.read()
    require(checkpoint["pending"] is None, "C1 cannot repair a pending append")
    return checkpoint, journal.load()


class ClaimProbe:
    def __init__(self, config, *, root, environment=None, api=None):
        self.runtime = batch_runtime.Runtime(config, root=root, environment=environment, api=api)

    def prepare(self, request):
        request = parse_intent(request)
        if request["fault"] == "disabled":
            return {"intent": request, "status": "disabled"}
        runtime = self.runtime
        # Read committed data only, never a working-tree file or operator path.
        require(runtime.git("rev-parse", "HEAD").decode().strip() == runtime.control,
                "checkout is not the exact controller revision")
        manifest = validate_manifest(batch_runtime.strict_json(runtime.git("show", f"{runtime.control}:{MANIFEST}")))
        require(runtime.config == manifest["claim"], "runtime config differs from the reviewed claim role")
        runtime.authenticate_current()
        require(runtime.read_main() == runtime.control, "main moved beyond the C1 controller")
        checkpoint, events = readonly_history(runtime)
        require(checkpoint == {"head": None, "pending": None} and events == [], "C1 requires its fresh empty assigned storage")
        require(runtime.old_runs_terminal() is True, "old controlled runs are active or unknown; C1 is not armed")
        return {"intent": request, "controller": {**runtime.current, "control_sha": runtime.control},
                "manifest": manifest, "checkpoint": checkpoint, "events": events}

    def execute(self, prepared):
        require(isinstance(prepared, dict) and "intent" in prepared, "prepared C1 request is missing")
        current = self.prepare(prepared["intent"])
        require(current == prepared, "prepared claim role or controller snapshot changed")
        if current.get("status") == "disabled":
            return {"status": "disabled", "remote_writes": 0}
        runtime = self.runtime
        # This is the real bootstrap/old-run audit, not a substituted selection
        # or a dispatch. A race can still return waiting after observe: no fault
        # is then claimed, and the nonempty state needs ordinary reconciliation.
        answer = runtime.reconcile(execute=True)
        require(answer["action"] == "execute", "real admission did not reach a new durable execution claim")
        checkpoint, events = readonly_history(runtime)
        state = report_runtime.scheduler_state(runtime)
        require(state == answer["state"] and checkpoint["head"] is not None,
                "returned state differs from authenticated committed history")
        require([e["type"] for e in events] == ["observe", "admit", "claim"], "C1 history is not exactly one new bootstrap claim")
        active, request = state["active"], answer["request"]
        require(isinstance(active, dict) and active["claim"] == runtime.current
                and active["executor_run"] == runtime.current and active["request_id"] == request["id"],
                "committed execution identity differs from current C1 run")
        require(state["requests"] == {request["id"]: request} and request["kind"] == "bootstrap"
                and request["base"] is None and request["target"] == request["control"] == runtime.control
                and state["processed"] is None and not state["results"] and not state["debts"] and not state["failures"],
                "bootstrap identity or pre-result state differs")
        policy = runtime.inputs.policy_at(runtime.control)
        require(request["policy"] == policy.digest and request["selection"]["kind"] == "full"
                and set(request["selection"]["suites"]) == set(policy.suite_ids), "bootstrap did not select complete canonical inventory")
        # No result.json, action/request/executor output or executable artifact.
        raise ControlledExit({"run_id": runtime.current["run_id"], "attempt": 1,
            "control_sha": runtime.control, "request_id": request["id"], "journal_head": checkpoint["head"],
            "issue_number": runtime.config["issue_number"], "epoch": runtime.config["epoch"]})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "request", "root", "summary"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    code = 0
    try:
        probe = ClaimProbe(batch_runtime.strict_json(args.config.read_bytes()), root=args.root)
        answer = probe.execute(probe.prepare(batch_runtime.strict_json(args.request.read_bytes())))
    except ControlledExit as stopped:
        answer = {"status": "controlled-claim-before-output-exit", "identity": stopped.identity,
                  "why": "durable claim verified; process deliberately exits before executable output, not GitHub cancellation",
                  "remedy": "confirm terminal no-heavy run and recover this exact claim with a fresh ordinary settle"}
        code = stopped.code
    except Exception:
        answer = {"status": "error", "why": "C1 not armed or original admission/storage outcome unresolved; no successful fault claimed",
                  "remedy": "inspect fixed manifest, actual old-run state and journal; never repeat an uncertain execution claim"}
        code = 1
    with args.summary.open("a") as stream:
        stream.write("O1 C1: " + json.dumps(answer, sort_keys=True) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
