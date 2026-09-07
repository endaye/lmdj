#!/usr/bin/env python3
"""Fixed-target DAG inputs and needs conversion; no admission or GitHub writes."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

import batch_verdict
import change_scope
import incremental_batch
import self_test
import test_scope

SCHEMA = "lmdj.ci-batch-execution.v1"


def require(condition, why):
    if not condition:
        raise ValueError(f"why: {why}; remedy: pass the authenticated frozen request to its admitted fresh-run DAG")


def git(repo, *args):
    result = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args],
                            capture_output=True, timeout=60)
    require(result.returncode == 0, "complete Git provenance could not be verified")
    return result.stdout.decode().strip()


def prepare(policy, request, executor, *, repo, run_id, run_attempt, control_sha, main_sha):
    """Verify local execution identity, never treating request data as authority.

The caller supplies its real run and checkout identity from trusted workflow
context. The controller owns authentication and durable admission/claim; this
function alone grants no permission to start a product job.
"""
    incremental_batch._request(policy, request)
    executor = incremental_batch.identity(executor)
    require(type(run_id) is int and type(run_attempt) is int
            and executor == {"run_id": run_id, "attempt": run_attempt}, "DAG is not the admitted executor")
    incremental_batch.exact_sha(control_sha)
    incremental_batch.exact_sha(main_sha)
    require(control_sha == request["control"], "control revision differs from frozen request")
    require(git(repo, "rev-parse", "HEAD") == control_sha, "checkout does not contain frozen control code")
    require(git(repo, "rev-parse", "--is-shallow-repository") == "false", "shallow history cannot verify the batch")
    require(git(repo, "cat-file", "-t", main_sha) == "commit", "main identity is not a commit object")
    require(git(repo, "cat-file", "-t", request["target"]) == "commit", "target identity is not a commit object")
    git(repo, "merge-base", "--is-ancestor", control_sha, main_sha)
    git(repo, "merge-base", "--is-ancestor", request["target"], main_sha)
    if request["kind"] == "auto":
        require(request["base"] is not None, "automatic request is missing its baseline")
        test_scope.collect_interval(repo, request["base"], request["target"])
    identity = {"request_id": request["id"], "request_kind": request["kind"],
                "base_sha": request["base"], "target_sha": request["target"],
                "control_sha": control_sha, "policy_digest": policy.digest,
                "run_id": run_id, "run_attempt": run_attempt}
    # Structural validation does not invent passing observations.
    batch_verdict.build(policy, identity, request["selection"], [])
    selected = set(request["selection"]["suites"])
    return {"schema": SCHEMA, "identity": identity, "selection": request["selection"],
            "lanes": {suite.scope_lane: suite.id in selected for suite in policy.inventory.suites
                      if suite.scope_lane is not None},
            "suites": {suite.id: suite.id in selected for suite in policy.inventory.suites}}


def from_needs(policy, identity, selection, needs, *, aliases=None, dependencies=None):
    """Use actual needs context, reject extra product execution, retain missing.

Unknown control jobs are ignored: they are not product-suite evidence. A
canonical product job outside selection may only be skipped, never executed.
"""
    batch_verdict.build(policy, identity, selection, [])
    aliases, dependencies = dict(aliases or {}), dict(dependencies or {})
    owners = dict(policy.inventory.job_owner)
    for suite in policy.inventory.suites:
        for alternatives in suite.alternatives.values():
            owners.update({name: suite.id for name in alternatives})
    require(set(aliases) <= set(owners) and all(isinstance(v, str) and v for v in aliases.values()),
            "unknown or malformed workflow job alias")
    mapped = [aliases.get(job, job) for job in owners]
    require(len(mapped) == len(set(mapped)), "multiple product jobs share one needs result")
    require(isinstance(needs, dict), "needs context is not an object")
    require(set(dependencies) <= set(owners)
            and all(isinstance(values, list) and all(isinstance(v, str) and v for v in values)
                    for values in dependencies.values()), "invalid dependency map")
    selected = set(selection["suites"])
    for job, suite in owners.items():
        key = aliases.get(job, job)
        if key not in needs:
            continue
        row = needs[key]
        require(isinstance(row, dict) and set(row) <= {"result", "outputs"}
                and isinstance(row.get("result"), str) and row["result"] in self_test.NEEDS_RESULTS,
                "invalid product job needs result")
        require(isinstance(row.get("outputs", {}), dict)
                and all(isinstance(k, str) and isinstance(v, str) for k, v in row.get("outputs", {}).items()),
                "invalid product job outputs")
        require(row.get("outputs", {}).get("infrastructure_failure", "") in {"", "true", "false"},
                "unknown infrastructure failure flag")
        require(suite in selected or row["result"] == "skipped", "unselected product job unexpectedly executed")
    legacy_identity = self_test.Identity(batch_verdict.SCHEMA, identity["request_kind"], identity["control_sha"],
                                        identity["target_sha"], identity["run_id"], identity["run_attempt"],
                                        policy.inventory.revision)
    rows, diagnostics = self_test.observations_from_needs(
        legacy_identity, policy.inventory, needs, aliases=aliases, dependencies=dependencies)
    require(not diagnostics, "needs observations are not valid terminal results")
    return batch_verdict.build(policy, identity, selection, [asdict(row) for row in rows if row.suite in selected])


def read(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=change_scope.reject_duplicates)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "verdict"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        policy, document = test_scope.load_policy(args.root), read(args.input)
        require(isinstance(document, dict), "adapter input is not an object")
        if args.command == "prepare":
            require(set(document) == {"request", "executor", "run_id", "run_attempt", "control_sha", "main_sha"},
                    "execution input schema is not closed")
            result = prepare(policy, repo=args.root, **document)
        else:
            require(set(document) == {"identity", "selection", "needs", "aliases", "dependencies"},
                    "verdict input schema is not closed")
            result = from_needs(policy, **document)
        args.output.write_text(self_test.canonical_json(result) + "\n")
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        # Input and subprocess exceptions may contain raw artifact content.
        print("why: fixed-target execution adapter rejected its inputs; remedy: verify frozen request, complete history and actual needs context")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
