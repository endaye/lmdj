#!/usr/bin/env python3
"""Read-only merged-PR mapping producer; no AI, labels, issues or merge calls."""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import zipfile

import change_scope
import review_pipeline as pipeline
import review_scope
import review_scope_codec as codec
import self_test_report
import test_scope

SCHEMA = "lmdj.ci-review-merge-map.v1"
KEYS = {"schema", "repository", "repository_id", "pr_number", "head_sha", "merge_sha", "control_sha",
        "run_id", "run_attempt", "workflow_id", "changed_paths", "changed_path_digest", "scope_records", "complete", "gaps", "digest"}


def require(condition, why):
    review_scope.require(condition, why, "retain a full fallback or explicitly reconcile complete authenticated merge evidence")


def build_map(*, repository, repository_id, pr_number, head_sha, merge_sha, control_sha, run_id, run_attempt,
              workflow_id, changed_paths, scope_records, complete, gaps):
    identity = dict(repository=repository, pr_number=pr_number, head_sha=head_sha, base_sha=merge_sha,
                    control_sha=control_sha, backend="deterministic", run_id=run_id, run_attempt=run_attempt)
    test_scope._identity(identity)
    require(type(repository_id) is int and repository_id > 0 and type(workflow_id) is int and workflow_id > 0, "invalid API numeric identity")
    paths = test_scope._paths(changed_paths)
    require(type(complete) is bool and isinstance(gaps, list) and all(isinstance(g, str) and g for g in gaps), "invalid completeness declaration")
    require(isinstance(scope_records, list), "scope record inventory is missing")
    for item in scope_records:
        require(isinstance(item, dict) and set(item) == {"record", "review_id", "artifact_id"}, "invalid scope reference")
        require(all(type(item[k]) is int and item[k] > 0 for k in ("review_id", "artifact_id")), "scope reference lacks numeric receipts")
        record = item["record"]
        require(isinstance(record, dict) and set(record) == test_scope.RECORD_KEYS
                and record.get("repository") == repository and record.get("pr_number") == pr_number
                and record.get("head_sha") == head_sha, "scope reference describes another PR head")
        test_scope._identity({key: record[key] for key in test_scope.IDENTITY_KEYS})
        require(record["record_digest"] == test_scope.self_test.digest_of({key: value for key, value in record.items() if key != "record_digest"}),
                "nested scope record digest mismatch")
    require(not complete or (bool(scope_records) and not gaps), "complete mapping needs authenticated scope records without gaps")
    require(complete or bool(gaps), "incomplete mapping must explain its full fallback")
    document = {"schema": SCHEMA, "repository": repository, "repository_id": repository_id, "pr_number": pr_number,
                "head_sha": head_sha, "merge_sha": merge_sha, "control_sha": control_sha, "run_id": run_id,
                "run_attempt": run_attempt, "workflow_id": workflow_id, "changed_paths": paths,
                "changed_path_digest": test_scope.self_test.digest_of(paths), "scope_records": scope_records,
                "complete": complete, "gaps": sorted(set(gaps))}
    document["digest"] = test_scope.self_test.digest_of(document)
    return document


def validate_map(document):
    """Internal consistency only; consumer independently authenticates map run."""
    require(isinstance(document, dict) and set(document) == KEYS, "mapping schema is not closed")
    arguments = {key: document[key] for key in KEYS - {"schema", "changed_path_digest", "digest"}}
    require(document == build_map(**arguments), "mapping schema, digest or canonical fields disagree")
    return document


def requires_full(document):
    """Incomplete mapping never authorizes focused or none selection."""
    return not validate_map(document)["complete"]


def review_record(body):
    """Reuse publisher codec; unavailable evidence can only widen to full."""
    require(not codec.unavailable_identities(body), "publisher scope was unavailable; use full")
    # Validate the digest-bound v2 marker even though the scope record remains
    # the map's public projection.  A historical v1 scope record is still
    # readable, but it cannot make a v2 review appear complete by itself.
    codec.decode_history(body)
    return codec.decode(body)


def policy_at(control):
    documents = [json.loads(pipeline.git("show", control + ":scripts/ci/" + name),
                            object_pairs_hook=change_scope.reject_duplicates)
                 for name in ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json")]
    return test_scope.parse_policy(*documents)


def authenticated_record(record, *, repository_id, workflow_id, download):
    """Historical identity checks deliberately do not require an open PR."""
    repo, run_id, attempt = record["repository"], record["run_id"], record["run_attempt"]
    identity = {key: record[key] for key in test_scope.IDENTITY_KEYS}
    test_scope._identity(identity)
    run = pipeline.api(f"/repos/{repo}/actions/runs/{run_id}/attempts/{attempt}")
    require(run.get("id") == run_id and run.get("run_attempt") == attempt and run.get("workflow_id") == workflow_id,
            "historical review run identity mismatch")
    require(run.get("repository", {}).get("id") == repository_id and run.get("repository", {}).get("full_name") == repo,
            "historical run repository mismatch")
    require(run.get("status") == "completed" and run.get("conclusion") == "success", "review publication is not terminal successful evidence")
    if run.get("event") == "workflow_dispatch":
        require(run.get("head_branch") == "main" and run.get("head_sha") == record["control_sha"], "untrusted manual review source")
    else:
        # GitHub may erase this association after merge. It does not erase the
        # exact-attempt head. Caller has bound the record to the live merged
        # PR's bot COMMENT; source/jobs/policy and actual artifact still verify
        # below. Empty association is neither a rejection nor proof by itself.
        associated = run.get("pull_requests")
        require(run.get("event") == "pull_request" and run.get("head_sha") == record["head_sha"]
                and isinstance(associated, list) and (not associated or any(p.get("number") == record["pr_number"]
                and p.get("head", {}).get("sha") == record["head_sha"] for p in associated)),
                "historical PR event does not bind reviewed head")
    jobs = pipeline.pages(f"/repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs", "jobs")
    for name in ("Review fallback", "Publish review and scope"):
        matches = [j for j in jobs if j.get("name") == name]
        require(len(matches) == 1 and matches[0].get("run_id") == run_id and matches[0].get("run_attempt") == attempt
                and matches[0].get("status") == "completed" and matches[0].get("conclusion") == "success",
                "historical producer or publisher is not complete")
    pipeline.fetch(run["head_sha"], record["control_sha"])
    require(pipeline.git("merge-base", record["control_sha"], "origin/main").decode().strip() == record["control_sha"],
            "historical control is not main ancestry")
    require(pipeline.git("show", run["head_sha"] + ":.github/workflows/pr-review.yml")
            == pipeline.git("show", record["control_sha"] + ":.github/workflows/pr-review.yml"), "historical workflow source differs from trusted control")
    test_scope.validate_record(record, policy_at(record["control_sha"]), identity)
    name = f"pr-test-scope-{record['head_sha']}-{run_id}-{attempt}"
    artifacts = [a for a in pipeline.pages(f"/repos/{repo}/actions/runs/{run_id}/artifacts", "artifacts") if a.get("name") == name]
    require(len(artifacts) == 1 and artifacts[0].get("expired") is False, "historical scope artifact is missing or expired")
    with zipfile.ZipFile(io.BytesIO(download(artifacts[0]["id"]))) as archive:
        require(archive.namelist() == ["scope.json"] and archive.getinfo("scope.json").file_size <= 1000000,
                "scope artifact has unexpected members or size")
        artifact_record = json.loads(archive.read("scope.json"), object_pairs_hook=change_scope.reject_duplicates)
    require(artifact_record == record, "immutable review scope differs from actual publisher artifact")
    return artifacts[0]["id"]


def produce(repository, number, expected_head, expected_merge):
    pull = pipeline.api(f"/repos/{repository}/pulls/{number}")
    require(pull.get("number") == number and pull.get("state") == "closed" and pull.get("merged") is True
            and pull.get("base", {}).get("ref") == "main" and pull.get("head", {}).get("sha") == expected_head
            and pull.get("merge_commit_sha") == expected_merge, "closed event does not match live merged PR")
    repo = pipeline.api(f"/repos/{repository}")
    require(pull.get("base", {}).get("repo", {}).get("id") == repo["id"], "merged PR base repository mismatch")
    workflow = pipeline.api(f"/repos/{repository}/actions/workflows/pr-review.yml")
    require(workflow.get("path") == ".github/workflows/pr-review.yml", "mapping workflow identity mismatch")
    control = pipeline.git("rev-parse", "HEAD").decode().strip()
    pipeline.fetch("main", expected_merge)
    main_history = pipeline.git("rev-list", "--first-parent", "origin/main").decode().splitlines()
    require(expected_merge in main_history and control in main_history, "merge or trusted control is not main first-parent history")
    parent = pipeline.git("show", "-s", "--format=%P", expected_merge).decode().split()[0]
    interval = test_scope.collect_interval(pipeline.ROOT, parent, expected_merge)
    records, gaps = [], []
    bot = pipeline.api("/users/github-actions%5Bbot%5D")
    download = self_test_report.UrllibGitHubApi(repository, os.environ["GITHUB_TOKEN"]).download_artifact
    reviews = pipeline.pages(f"/repos/{repository}/pulls/{number}/reviews")
    for posted in reviews:
        if posted.get("commit_id") != expected_head or posted.get("user", {}).get("id") != bot.get("id"):
            continue
        body = posted.get("body", "")
        if "<!-- lmdj-test-scope-" not in body:
            continue
        try:
            require(posted.get("state") == "COMMENTED", "scope review is not a submitted COMMENT")
            record = review_record(body)
            require(record is not None, "scope-bearing review lacks supported metadata")
            require(record["repository"] == repository and record["pr_number"] == number and record["head_sha"] == expected_head,
                    "review marker head mismatch")
            artifact_id = authenticated_record(record, repository_id=repo["id"], workflow_id=workflow["id"], download=download)
            records.append({"record": record, "review_id": posted["id"], "artifact_id": artifact_id})
        except Exception:
            gaps.append("a scope-bearing review could not be authenticated; use full")
    # A terminal map cannot assume that a still-running review will add no
    # scope. PR-head query plus conservative active manual-run scan cover both
    # automatic and explicit review paths without trusting display titles.
    runs = pipeline.pages(f"/repos/{repository}/actions/workflows/pr-review.yml/runs?head_sha={expected_head}", "workflow_runs")
    manual = []
    for status in ("queued", "in_progress", "waiting", "requested", "pending"):
        manual.extend(pipeline.pages(f"/repos/{repository}/actions/workflows/pr-review.yml/runs?event=workflow_dispatch&status={status}", "workflow_runs"))
    known = {(item["record"]["run_id"], item["record"]["run_attempt"]) for item in records}
    for run in runs + manual:
        if run.get("id") == int(os.environ["GITHUB_RUN_ID"]):
            continue
        if run.get("status") != "completed" or (run.get("conclusion") == "success" and (run.get("id"), run.get("run_attempt")) not in known):
            gaps.append("review run lacks complete mapped publisher evidence; use full")
    if not records:
        gaps.append("no authenticated scope records; use full")
    return build_map(repository=repository, repository_id=repo["id"], pr_number=number, head_sha=expected_head,
                     merge_sha=expected_merge, control_sha=control, run_id=int(os.environ["GITHUB_RUN_ID"]),
                     run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]), workflow_id=workflow["id"], changed_paths=interval["paths"],
                     scope_records=records, complete=not gaps, gaps=gaps)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = produce(os.environ["GITHUB_REPOSITORY"], int(os.environ["PR_NUMBER"]), os.environ["HEAD_SHA"], os.environ["MERGE_SHA"])
        pipeline.save(args.output, document)
        return 0
    except Exception:
        print("why: merged PR mapping is unavailable; remedy: preserve full fallback and reconcile authenticated history")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
