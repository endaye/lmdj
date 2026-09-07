#!/usr/bin/env python3
"""C2 diagnostic readiness after a real claim; does not cancel or run products.

The independent workflow waiter may use only the authenticated diagnostic_ready
boolean. This record is neither a scheduler execution action nor test evidence.
An operator separately authorizes cancellation of the exact parent run.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re

import batch_runtime
import o1_execution_claim_probe as claim

SCHEMA = "lmdj.o1-cancel-diagnostic.v1"
OPERATION = "executor-cancellation"


def require(ok, why):
    if not ok:
        raise ValueError("why: " + why + "; remedy: stop C2, inspect the exact isolated claim and use ordinary settlement only")


def parse_intent(value):
    require(isinstance(value, dict) and set(value) in ({"operation"}, {"operation", "enabled"})
            and value.get("operation") == OPERATION, "C2 intent is not closed")
    enabled = value.get("enabled", False)
    require(type(enabled) is bool, "C2 enabled must be an explicit boolean")
    return enabled


def record(status, identity=None):
    return {"schema": SCHEMA, "status": status,
            "diagnostic_ready": status == "ready", "identity": deepcopy(identity)}


class CancellationProbe:
    def __init__(self, config, *, root, environment=None, api=None):
        self.claim = claim.ClaimProbe(config, root=root, environment=environment, api=api)

    def execute(self, intent):
        if not parse_intent(intent):
            return record("disabled")
        runtime = self.claim.runtime
        # A separately reviewed fixed-role migration must assign new storage.
        # Old C1/A/B storage is never silently reused or reset by this adapter.
        require(re.fullmatch(r"o1-claim-cancel-[a-z0-9-]{1,80}", runtime.config["epoch"]) is not None,
                "C2 requires its separately assigned cancellation claim epoch")
        request = {"operation": claim.OPERATION, "fault": claim.FAULT}
        try:
            self.claim.execute(self.claim.prepare(request))
        except claim.ControlledExit as stopped:
            expected = {"run_id", "attempt", "control_sha", "request_id", "journal_head", "issue_number", "epoch"}
            identity = stopped.identity
            require(stopped.code == 87 and isinstance(identity, dict) and set(identity) == expected,
                    "claim completion diagnostic is malformed")
            require(type(identity["run_id"]) is int and identity["run_id"] == runtime.current["run_id"]
                    and type(identity["attempt"]) is int and identity["attempt"] == 1
                    and identity["control_sha"] == runtime.control
                    and type(identity["issue_number"]) is int and identity["issue_number"] == runtime.config["issue_number"]
                    and identity["epoch"] == runtime.config["epoch"]
                    and isinstance(identity["request_id"], str) and bool(identity["request_id"])
                    and isinstance(identity["journal_head"], str)
                    and re.fullmatch(r"[0-9a-f]{64}", identity["journal_head"]) is not None,
                    "claim completion does not bind this controller and storage")
            return record("ready", identity)
        require(False, "claim returned without the verified durable-claim boundary")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "request", "root", "diagnostic", "summary"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    # Exclusive creation happens before API admission. A stale ready record
    # cannot survive a reused path and cannot be overwritten to conceal a claim.
    try:
        stream = args.diagnostic.open("x")
    except OSError:
        print("why: C2 diagnostic path is unavailable or already exists; remedy: use a fresh private diagnostic path and inspect any prior claim")
        return 1
    answer, code = record("error"), 1
    with stream:
        stream.write(json.dumps(answer, sort_keys=True) + "\n")
        stream.flush()
        try:
            probe = CancellationProbe(batch_runtime.strict_json(args.config.read_bytes()), root=args.root)
            answer = probe.execute(batch_runtime.strict_json(args.request.read_bytes()))
            code = 0
        except Exception:
            # Never repair, reset, retry or expose raw HTTP/Git error content.
            answer = record("error")
        stream.seek(0)
        stream.truncate()
        stream.write(json.dumps(answer, sort_keys=True) + "\n")
    with args.summary.open("a") as summary:
        summary.write("O1 C2 diagnostic: " + json.dumps(answer, sort_keys=True)
                      + "; readiness is not cancellation or test evidence\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
