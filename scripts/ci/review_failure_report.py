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
import review_merge_map as mapping
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


def _first_parent_chain(api, prefix, base, head):
    """Prove actual parent links from a complete bounded compare inventory."""
    commits, total = {}, None
    for page in range(1, 101):
        response = api._request('GET', prefix + f'/compare/{base}...{head}?per_page=100&page={page}')
        count, items = response.get('total_commits'), response.get('commits')
        require(response.get('status') in {'ahead', 'identical'} and response.get('merge_base_commit', {}).get('sha') == base,
                'historical mapping control is not main ancestry')
        require(type(count) is int and 0 <= count <= 10000 and (total is None or total == count)
                and isinstance(items, list) and len(items) <= 100, 'compare inventory is incomplete or changed')
        total = count
        for item in items:
            sha, parents = item.get('sha'), item.get('parents')
            require(isinstance(sha, str) and re.fullmatch('[0-9a-f]{40}', sha) and sha not in commits
                    and isinstance(parents, list) and bool(parents)
                    and all(isinstance(p, dict) and isinstance(p.get('sha'), str)
                            and re.fullmatch('[0-9a-f]{40}', p['sha']) for p in parents), 'compare parent inventory is malformed or duplicated')
            commits[sha] = parents[0]['sha']
        require(len(commits) <= total, 'compare inventory exceeds its declared count')
        if len(commits) == total:
            chain, current = {base}, head
            while current != base:
                require(current in commits and current not in chain, 'first-parent main chain is incomplete or cyclic')
                chain.add(current)
                current = commits[current]
            return chain
        require(len(items) == 100, 'compare inventory truncated before its declared count')
    require(False, 'compare inventory exceeds bounded pagination')


def _merge_paths(api, prefix, merge):
    files, parents = {}, None
    # The commit API caps file inventory at 3000. Reject a full final page:
    # it cannot prove there was not a silently truncated next file.
    for page in range(1, 31):
        response = api._request('GET', prefix + f'/commits/{merge}?per_page=100&page={page}')
        current, entries = response.get('parents'), response.get('files')
        require(response.get('sha') == merge and isinstance(current, list) and len(current) == 1
                and isinstance(current[0], dict) and isinstance(current[0].get('sha'), str)
                and re.fullmatch('[0-9a-f]{40}', current[0]['sha'])
                and (parents is None or parents == current) and isinstance(entries, list) and len(entries) <= 100,
                'merge commit identity, single parent or file inventory differs')
        parents = current
        for entry in entries:
            name, status = entry.get('filename'), entry.get('status')
            require(isinstance(name, str) and name not in files and status in {'added', 'modified', 'removed', 'renamed', 'copied', 'changed'},
                    'merge file inventory is malformed or duplicated')
            paths = [name]
            if status == 'renamed':
                require(isinstance(entry.get('previous_filename'), str), 'rename origin is missing')
                paths.append(entry['previous_filename'])
            files[name] = test_scope._paths(paths)
        if len(entries) < 100:
            return sorted({p for paths in files.values() for p in paths})
    require(False, 'merge file inventory reaches the API truncation boundary')


def _historical_closed_map(api, repository, repo_id, workflow_id, run, publisher, main, actual_source):
    """No review was run: authenticate the historical map, never its AI scope."""
    require(type(run.get('run_attempt')) is int and run.get('conclusion') == 'success'
            and publisher.get('conclusion') == 'success', 'historical mapping did not succeed with an exact attempt')
    _step(publisher, 'Map merged PR without another AI call')
    _step(publisher, 'Publish exact-head review and scope', 'skipped')
    uploads = [i for i, s in enumerate(publisher.get('steps', [])) if s.get('name') == 'Run actions/upload-artifact@v4' and s.get('conclusion') == 'success']
    mapper = next(i for i, s in enumerate(publisher['steps']) if s.get('name') == 'Map merged PR without another AI call')
    require(len(uploads) == 1 and uploads[0] > mapper, 'historical map upload is missing or precedes mapping')
    prefix = f'/repos/{repository}'
    inventory = api._request('GET', prefix + f"/actions/runs/{run['id']}/artifacts?per_page=100")
    artifacts = inventory.get('artifacts')
    require(isinstance(artifacts, list) and type(inventory.get('total_count')) is int
            and inventory['total_count'] == len(artifacts), 'historical mapping artifact inventory is truncated')
    pattern = re.compile(rf"^pr-review-merge-map-([0-9a-f]{{40}})-{run['id']}-{run['run_attempt']}$")
    matches = [a for a in artifacts if isinstance(a, dict) and pattern.fullmatch(a.get('name', ''))]
    require(len(matches) == 1, 'historical mapping artifact is missing or ambiguous')
    artifact = matches[0]
    require(type(artifact.get('id')) is int and artifact['id'] > 0 and artifact.get('expired') is False
            and artifact.get('workflow_run', {}).get('id') == run['id'], 'historical mapping artifact identity or expiry differs')
    raw = api.download_artifact(artifact['id'])
    require(isinstance(raw, bytes) and len(raw) <= 8_000_000, 'mapping archive exceeds budget')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        require(archive.namelist() == ['map.json'] and archive.getinfo('map.json').file_size <= 8_000_000, 'mapping archive schema or expanded size differs')
        document = mapping.validate_map(json.loads(archive.read('map.json'), object_pairs_hook=change_scope.reject_duplicates))
    require(document['repository'] == repository and document['repository_id'] == repo_id
            and document['workflow_id'] == workflow_id and document['run_id'] == run['id']
            and document['run_attempt'] == run['run_attempt']
            and document['merge_sha'] == pattern.fullmatch(artifact['name']).group(1), 'historical mapping identity differs')
    require(run['head_sha'] in {document['head_sha'], document['merge_sha']}, 'historical mapping run head is unrelated')
    associated = run.get('pull_requests')
    require(isinstance(associated, list) and (not associated or any(p.get('number') == document['pr_number']
            and p.get('head', {}).get('sha') == document['head_sha'] for p in associated)), 'historical mapping names another PR')
    control, merge = document['control_sha'], document['merge_sha']
    chain = _first_parent_chain(api, prefix, control, main)
    if merge not in chain:
        _first_parent_chain(api, prefix, merge, control)
    require(actual_source == _source(api, repository, control, WORKFLOW), 'historical mapping source differs from trusted main control')
    require(document['changed_paths'] == _merge_paths(api, prefix, merge), 'historical mapping paths differ from its actual merge delta')
    # complete=False is valid *mapping-only* evidence, never a valid AI review.
    # No scope record, label, failure report or product selection is returned.


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
        require(run["event"] == "pull_request", "skipped producer is not a PR mapping entry")
        actual_source = _source(api, repository, run["head_sha"], WORKFLOW)
        if actual_source != _source(api, repository, main, WORKFLOW):
            try:
                _historical_closed_map(api, repository, repo['id'], workflow['id'], run, publisher, main, actual_source)
            except reporting.ReportingError:
                raise
            except Exception as error:
                raise reporting.ReportingError('why: historical mapping receipt or API shape cannot be authenticated; '
                    'remedy: restore the exact retained mapping evidence; do not infer a review or backend failure') from error
        return None
    conclusion = producers[0].get("conclusion")
    require(conclusion in {"success", "failure"}, "review producer did not retain a completed result")
    producer = job("Review fallback", conclusion)
    for name in ("Collect complete fixed input without executing PR files", "Run actions/upload-artifact@v4"):
        _step(producer, name)
    _step(producer, "Save honest final result", conclusion)
    if conclusion == "failure":
        # The current finalizer saves complete failure receipts before exiting 1.
        # A cancelled/otherwise broken producer is not an all-backend verdict.
        require(all(step.get("conclusion") in {"success", "skipped"}
                    for step in producer["steps"] if step.get("name") != "Save honest final result"),
                "failed review producer has an additional incomplete or failed step")
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
        history_document = (json.loads(archive.read("history.json"), object_pairs_hook=change_scope.reject_duplicates)
                            if "history.json" in names else None)
        v2_archive = isinstance(history_document, dict) and history_document.get("schema") == review_scope.HISTORY_SCHEMA_V2
        required = [{"context.json", "history.json", "result.json", "failure.json"},
                    {"context.json", "history.json", "result.json", "review.json"}]
        if v2_archive:
            required = [{*entry, "collector.json", "t2-config-witness.json"} for entry in required]
        base_names = {name for name in names if not name.startswith("coverage-")}
        coverage_names = {name for name in names if name.startswith("coverage-")}
        require(len(names) == len(set(names)) and base_names in required
                and all(name.endswith(".json") and name != "coverage-.json" for name in coverage_names),
                "review archive schema is not closed")
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
    coverages = {review_scope.coverage_digest(documents[name]): documents[name] for name in coverage_names}
    collector_witness = documents.get("collector.json") if isinstance(history, dict) else None
    trusted_config = documents.get("t2-config-witness.json") if isinstance(history, dict) else None
    if isinstance(history, dict) and history.get("schema") == review_scope.HISTORY_SCHEMA_V2:
        require(collector_witness is not None and trusted_config is not None,
                "v2 archive lacks the independently authenticated collector/config witnesses")
        review_scope.validate_collector(collector_witness, identity=identity)
        trusted_config = pipeline._trusted_config_witness(trusted_config)
    review_scope.validate_history(policy, history, identity=identity,
                                  coverages=coverages if isinstance(history, dict) else None,
                                  changed_paths=context["changed_paths"], collector=collector_witness,
                                  trusted_config=trusted_config)
    attempts = history.get("attempts", []) if isinstance(history, dict) else history
    require(bool(attempts), "review history is empty")
    final_identity = dict(identity)
    if attempts[-1]["status"] == "reviewed":
        final_identity["backend"] = attempts[-1]["backend"]
    expected = review_scope.prepare_result(policy, final_identity, changed_paths=context["changed_paths"], history=history,
                                           coverages=coverages if isinstance(history, dict) else None,
                                           collector=collector_witness, trusted_config=trusted_config)
    require(documents["result.json"] == expected, "saved review result differs from independent history/policy recomputation")
    require(conclusion != "failure" or expected["status"] == "not-reviewed",
            "failed review finalizer contradicts the recomputed review result")
    if expected["status"] == "reviewed":
        require(documents.get("review.json") == attempts[-1]["review"] and "failure.json" not in documents,
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
