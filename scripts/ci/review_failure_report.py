#!/usr/bin/env python3
"""Authenticate completed PR Review receipts before reporting backend failures.

No PR API or model calls. apply_report's uncertain-write fence is process-local;
cross-process retry requires the separately managed durable reporting outbox.
"""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import re
import time
import zipfile

import change_scope
import review_scope
import self_test_report as reporting
import test_scope

WORKFLOW = ".github/workflows/pr-review.yml"
LIMIT = 4_000_000


def require(condition, why):
    if not condition:
        raise reporting.ReportingError("why: " + why + "; remedy: reconcile authenticated review receipts before reporting; do not infer backend failure")


class ReviewFailureReport(reporting.Report):
    def issue_body(self, assignee):
        return "\n".join([self.key_marker, "## PR Review backends unavailable", "",
            "Filed from authenticated PR Review fallback receipts, not a product self-test verdict.",
            "This bucket tracks review infrastructure availability; it does not assert a product defect or block PR merge.",
            f"Default assignee: @{assignee}.", "",
            "- [ ] Restore an available review backend or record an authorized exact-head review takeover.",
            "- [ ] Retain original run receipts; do not treat missing review as a clean review.", "",
            self.comment_body(first=True)])


def _source(api, repository, revision, path):
    require(isinstance(revision, str) and re.fullmatch("[0-9a-f]{40}", revision), "source revision is not exact")
    value = api._request("GET", f"/repos/{repository}/contents/{path}?ref={revision}")
    require(isinstance(value, dict) and value.get("encoding") == "base64" and isinstance(value.get("content"), str),
            "trusted source content is missing")
    require(len(value["content"]) <= LIMIT * 2, "source content exceeds budget")
    raw = base64.b64decode(value["content"].replace("\n", ""), validate=True)
    require(len(raw) <= LIMIT, "decoded source exceeds budget")
    return raw


def _step(job, name, conclusion="success"):
    matches = [s for s in job.get("steps", []) if s.get("name") == name]
    require(len(matches) == 1 and matches[0].get("conclusion") == conclusion, "required review step is missing or incomplete")


def collect(api, repository, run_id, attempt):
    require(all(type(v) is int and v > 0 for v in (run_id, attempt)), "invalid exact run attempt")
    prefix = f"/repos/{repository}"
    repo = api._request("GET", prefix)
    workflow = api._request("GET", prefix + "/actions/workflows/pr-review.yml")
    run = api._request("GET", prefix + f"/actions/runs/{run_id}/attempts/{attempt}")
    require(repo.get("full_name") == repository and type(repo.get("id")) is int,
            "repository API identity differs")
    require(workflow.get("path") == WORKFLOW and type(workflow.get("id")) is int,
            "review workflow identity unavailable")
    require(run.get("id") == run_id and run.get("run_attempt") == attempt and run.get("workflow_id") == workflow["id"]
            and run.get("path") == WORKFLOW and run.get("repository", {}).get("id") == repo["id"]
            and run.get("repository", {}).get("full_name") == repository and run.get("status") == "completed"
            and run.get("event") in {"pull_request", "workflow_dispatch"}, "run is not the completed exact trusted review attempt")
    jobs = api.list_jobs(run_id, attempt)
    def job(name, conclusion):
        matches = [j for j in jobs if j.get("name") == name]
        require(len(matches) == 1 and matches[0].get("run_id") == run_id and matches[0].get("run_attempt") == attempt
                and matches[0].get("status") == "completed" and matches[0].get("conclusion") == conclusion,
                "review job identity or completion differs")
        return matches[0]
    producers = [j for j in jobs if j.get("name") == "Review fallback"]
    require(len(producers) == 1, "review producer inventory is incomplete")
    main = api._request("GET", prefix + "/branches/main")["commit"]["sha"]
    if producers[0].get("conclusion") == "skipped":
        job("Review fallback", "skipped")
        _step(job("Resolve review target", "success"), "Resolve the Pull Request head", "skipped")
        publishers = [j for j in jobs if j.get("name") == "Publish review and scope"]
        require(len(publishers) == 1 and publishers[0].get("conclusion") in {"success", "failure", "cancelled"},
                "closed mapping publisher receipt is incomplete")
        publisher = job("Publish review and scope", publishers[0]["conclusion"])
        maps = [s for s in publisher.get("steps", []) if s.get("name") == "Map merged PR without another AI call"]
        require(len(maps) == 1 and maps[0].get("conclusion") in {"success", "failure", "cancelled"},
                "skipped producer has no executed mapping step")
        require(run["event"] == "pull_request" and _source(api, repository, run["head_sha"], WORKFLOW)
                == _source(api, repository, main, WORKFLOW), "skipped producer is not a trusted closed mapping entry")
        return None
    producer = job("Review fallback", "success")
    for name in ("Collect complete fixed input without executing PR files", "Save honest final result", "Run actions/upload-artifact@v4"):
        _step(producer, name)
    # Explicit total_count check: the shared convenience artifact method reads
    # one page; truncation must not silently select an incomplete receipt set.
    inventory = api._request("GET", prefix + f"/actions/runs/{run_id}/artifacts?per_page=100")
    artifacts = inventory.get("artifacts")
    require(isinstance(artifacts, list) and inventory.get("total_count") == len(artifacts), "artifact inventory is truncated or unavailable")
    pattern = re.compile(rf"^pr-review-result-([0-9a-f]{{40}})-{run_id}-{attempt}$")
    matches = [a for a in artifacts if pattern.fullmatch(a.get("name", ""))]
    require(len(matches) == 1 and matches[0].get("expired") is False and matches[0].get("workflow_run", {}).get("id") == run_id,
            "review result artifact is missing, ambiguous, expired or belongs to another run")
    artifact = matches[0]
    head = pattern.fullmatch(artifact["name"]).group(1)
    payload = api.download_artifact(artifact["id"])
    require(isinstance(payload, bytes) and len(payload) <= LIMIT, "review archive exceeds budget")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and set(names) in (
            {"context.json", "history.json", "result.json", "failure.json"},
            {"context.json", "history.json", "result.json", "review.json"}), "review archive schema is not closed")
        require(sum(i.file_size for i in archive.infolist()) <= LIMIT, "expanded review archive exceeds budget")
        documents = {name: json.loads(archive.read(name), object_pairs_hook=change_scope.reject_duplicates) for name in names}
    context = documents["context.json"]
    require(isinstance(context, dict) and set(context) == {"identity", "changed_paths"}, "review context schema is not closed")
    identity = context["identity"]
    test_scope._identity(identity)
    require(identity["repository"] == repository and identity["run_id"] == run_id and identity["run_attempt"] == attempt
            and identity["head_sha"] == head and identity["backend"] == "deterministic", "context identity differs from actual artifact/run")
    control = identity["control_sha"]
    comparison = api.compare(control, main)
    require(comparison.get("status") in {"ahead", "identical"} and comparison.get("merge_base_commit", {}).get("sha") == control,
            "review control is not verified main ancestry")
    require(_source(api, repository, run["head_sha"], WORKFLOW) == _source(api, repository, control, WORKFLOW),
            "actual review workflow source differs from trusted control")
    if run["event"] == "workflow_dispatch":
        require(run.get("head_branch") == "main" and run["head_sha"] == control, "manual review source is not trusted main control")
    else:
        associated = run.get("pull_requests")
        require(run["head_sha"] == head and isinstance(associated, list) and (not associated or any(
            p.get("number") == identity["pr_number"] and p.get("head", {}).get("sha") == head for p in associated)),
            "review PR event does not bind actual head")
    policy = test_scope.parse_policy(*[json.loads(_source(api, repository, control, "scripts/ci/" + name),
                                               object_pairs_hook=change_scope.reject_duplicates)
        for name in ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json")])
    history = documents["history.json"]
    review_scope.validate_history(policy, history)
    require(bool(history), "review history is empty")
    final_identity = dict(identity)
    if history[-1]["status"] == "reviewed":
        final_identity["backend"] = history[-1]["backend"]
    expected = review_scope.prepare_result(policy, final_identity, changed_paths=context["changed_paths"], history=history)
    require(documents["result.json"] == expected, "saved review result differs from independent history/policy recomputation")
    if expected["status"] == "reviewed":
        require(documents.get("review.json") == history[-1]["review"] and "failure.json" not in documents,
                "valid review has conflicting failure evidence")
        return None
    failure = expected["failure"]
    require(documents.get("failure.json") == failure and "review.json" not in documents,
            "failure receipt differs from all-backend recomputation")
    detail = "\n".join(f"- {a['backend']}: `{a['error_class']}`" for a in failure["attempts"])
    return ReviewFailureReport(key="pr-review/backends-unavailable", title="[CI review] All review backends unavailable",
        observation=f"{identity['pr_number']}/{head}/{run_id}/{attempt}/{failure['request_id']}", severity="medium",
        labels=(reporting.REPORT_LABEL, "type:bug", "area:ci-release"),
        summary=f"PR #{identity['pr_number']} head `{head}` was **not reviewed**. "
                f"[Authenticated run](https://github.com/{repository}/actions/runs/{run_id}/attempts/{attempt}).",
        detail=detail + "\n\n" + failure["remedy"])


def report(api, repository, run_id, attempt, *, sleep=time.sleep):
    planned = collect(api, repository, run_id, attempt)
    return reporting.apply_report(api, planned, assignee=reporting.DEFAULT_ASSIGNEE, sleep=sleep) if planned else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        api = reporting.UrllibGitHubApi(args.repository, os.environ.get("GITHUB_TOKEN", ""))
        outcome = report(api, args.repository, args.run_id, args.attempt)
        message = "PR Review failure report: " + (outcome.action if outcome else "not applicable")
        with args.summary.open("a") as stream:
            stream.write(message + "\n")
        return 0
    except Exception:
        print("why: review failure evidence or reporting is unresolved; remedy: inspect authenticated receipts and reconcile any unknown write before retrying")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
