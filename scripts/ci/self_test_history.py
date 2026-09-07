#!/usr/bin/env python3
"""Read-only, bounded same-target self-test history for routine daily dedup.

No merge, dispatch, cancellation or Issue calls. Missing, expired, untrusted or
unreadable history means run tests, never manufacture a skip. Explicit requests
do not call this module. The report consumer owns HTTP/provenance primitives;
the shared protocol validator owns the complete suite/digest contract.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import self_test as protocol
import self_test_report as report

RUNS_PER_EVENT = 20


def find_conclusion(api, *, repository: str, target: str, policy_document: dict,
                    main_history: set[str], current_run: int) -> dict | None:
    """Search a bounded recent window by target AND policy, not completion order.

    A late older A cannot hide B's retained conclusion. A history window miss
    merely costs another test; it cannot suppress one. Only attempt 1 records
    are accepted until the execution protocol supports complete fresh reruns.
    """
    if target not in main_history:
        raise report.ReportingError("requested target is not in verified main history")
    policy = protocol.parse_policy(policy_document)
    workflow = api.get_workflow()
    if (type(workflow.get("id")) is not int
            or workflow.get("path") != ".github/workflows/ci.yml"):
        raise report.ReportingError("Core CI workflow identity is unavailable")
    candidates = []
    for event in ("schedule", "workflow_dispatch"):
        candidates.extend(api.list_runs("ci.yml", event=event, created=None,
                                        per_page=RUNS_PER_EVENT, status="completed"))
    # Listing order/finish time has no authority. Examine every eligible run
    # until one exactly matches; never use "last run" as "last target".
    for raw in candidates:
        run = report.parse_run(raw)
        if (run.id == current_run or run.attempt != 1
                or report.classify_run(run, repository=repository) is not None
                or run.workflow_id != workflow["id"] or run.head_sha not in main_history):
            continue
        artifacts = api.list_artifacts(run.id)
        found = report.find_verdict_artifact(artifacts, run=run)
        if found is None or found[1] != target:
            continue
        if api.compare(report.PRODUCER_REVISION, run.head_sha).get("status") not in ("ahead", "identical"):
            continue
        producer_policy = api.get_policy(run.head_sha)
        if protocol.parse_policy(producer_policy).revision != policy.revision:
            continue
        document = report.read_verdict_zip(api.download_artifact(found[0]))
        verdict = report.parse_verdict(document, run=run, target=target, policy=producer_policy)
        if verdict.status not in protocol.COMPLETE_BATCH_STATUSES:
            continue
        return {"target_revision": target, "status": verdict.status,
                "evidence_digest": verdict.evidence_digest,
                "policy_revision": verdict.policy_revision,
                "source_run_id": run.id, "source_run_attempt": run.attempt,
                "source_url": run.html_url}
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--main-history", required=True, type=Path)
    parser.add_argument("--policy", type=Path, default=Path("scripts/ci/self_test_policy.json"))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    # Always replace the local output, including on an API error: no stale file
    # from a previous step may become today's skip authority.
    conclusion = None
    try:
        api = report.UrllibGitHubApi(args.repository, os.environ.get("GITHUB_TOKEN", ""))
        conclusion = find_conclusion(
            api, repository=args.repository, target=args.target,
            policy_document=json.loads(args.policy.read_text()),
            main_history=set(args.main_history.read_text().splitlines()),
            current_run=args.run_id)
    except (report.ReportingError, report.GitHubApiError, ValueError, KeyError, TypeError, OSError) as error:
        print(f"why: historical evidence could not be verified ({type(error).__name__}); "
              "remedy: this batch runs normally; inspect history/API access before expecting deduplication",
              file=sys.stderr)
    args.out.write_text(json.dumps(conclusion, sort_keys=True) + "\n")
    if conclusion:
        print(f"Reusing retained {conclusion['status']} observation: {conclusion['source_url']}; "
              "the original observation date and failure remain unchanged")
    else:
        print("No verified same-target/same-policy conclusion in the bounded history window; run all suites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
