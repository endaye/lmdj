#!/usr/bin/env python3
"""Read-only, one-shot current-head review eligibility; never merge authority."""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import zipfile

import change_scope
import review_failure_report as failure
import review_pipeline as pipeline
import self_test_report as reporting

SCHEMA = "lmdj.current-head-review.v1"
ATTESTATION = "lmdj.owner-review-attestation.v1"
MARKER = re.compile(r"^<!-- lmdj-review-v1 ([\w.-]+/[\w.-]+) ([1-9][0-9]*) ([0-9a-f]{40}) ([1-9][0-9]*) ([1-9][0-9]*) (glm|kimi|grok) -->$", re.M)
MARKER_V2 = re.compile(r"^<!-- lmdj-review-v2 ([\w.-]+/[\w.-]+) ([1-9][0-9]*) ([0-9a-f]{40}) ([1-9][0-9]*) ([1-9][0-9]*) (deepseek|glm|kimi|grok) sha256=([0-9a-f]{64}) -->$", re.M)
HISTORY_DIGEST_V2 = re.compile(r"^<!-- lmdj-review-history-digest-v2 sha256=([0-9a-f]{64}) -->$", re.M)


class Refused(ValueError):
    """Authored invariant diagnostics, never raw provider or API error text."""


def require(value, reason):
    if not value:
        raise Refused(reason)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


class Reader:
    """Per-observation read cache; PR boundary reads always bypass it."""
    def __init__(self, transport, repository):
        self.transport, self.repository = transport, repository
        self.cache = {}

    def get(self, path, *, fresh=False, raw=False):
        key = (path, raw)
        if fresh or key not in self.cache:
            value = self.transport._request("GET", path, raw=raw)
            if fresh:
                return value
            self.cache[key] = value
        return self.cache[key]

    def pages(self, path, key=None):
        result, total = [], None
        for page in range(1, 101):
            value = self.get(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            items = value.get(key) if key and isinstance(value, dict) else value
            require(isinstance(items, list) and all(isinstance(i, dict) for i in items), "incomplete inventory")
            if key:
                count = value.get("total_count")
                require(type(count) is int and count >= 0 and (total is None or total == count), "inventory count changed")
                total = count
            result.extend(items)
            if len(items) < 100:
                require(total is None or total == len(result), "truncated inventory")
                ids = [i.get("id") for i in result]
                require(all(type(i) is int and i > 0 for i in ids) and len(ids) == len(set(ids)), "duplicate or missing inventory identity")
                return result
        raise Refused("pagination budget exhausted")

    # Existing failure collector authenticates workflow source, control ancestry,
    # retained archive and complete model history. Supply complete inventories.
    def _request(self, method, path):
        require(method == "GET", "review reader cannot write")
        if path.endswith("/artifacts?per_page=100"):
            items = self.pages(path.removesuffix("?per_page=100"), "artifacts")
            return {"artifacts": items, "total_count": len(items)}
        return self.get(path)

    def compare(self, base, head):
        return self.get(f"/repos/{self.repository}/compare/{base}...{head}")

    def list_jobs(self, run, attempt):
        return self.pages(f"/repos/{self.repository}/actions/runs/{run}/attempts/{attempt}/jobs", "jobs")

    def download_artifact(self, artifact):
        return self.get(f"/repos/{self.repository}/actions/artifacts/{artifact}/zip", raw=True)


def manual(reader, comment, repo, head):
    body = comment.get("body", "")
    if ATTESTATION not in body:
        return None
    record = json.loads(body, object_pairs_hook=change_scope.reject_duplicates)
    require(isinstance(record, dict) and record.get("schema") == ATTESTATION, "invalid owner record")
    require(record.get("head_sha") == head, "stale owner record")
    owner = repo["owner"]
    require(owner.get("type") == "User" and type(owner.get("id")) is int
            and comment.get("user", {}).get("id") == owner["id"]
            and comment["user"].get("login") == owner["login"], "record is not authenticated repository owner comment")
    require(comment.get("created_at") == comment.get("updated_at") and nonempty(comment.get("created_at")), "edited owner record; append a fresh attestation")
    require(nonempty(record.get("reason")), "owner record needs reason")
    common = {"schema", "head_sha", "kind", "reason"}
    if record.get("kind") == "waiver":
        require(set(record) == common, "invalid waiver fields")
    else:
        require(record.get("kind") == "takeover" and set(record) == common | {"review"}, "invalid takeover fields")
        review = record["review"]
        require(isinstance(review, dict) and set(review) == {"reviewer_login", "reviewer_id", "author_session", "reviewer_session", "independent", "scope", "findings", "limitations"}, "invalid independent review fields")
        require(all(nonempty(review[k]) for k in ("reviewer_login", "author_session", "reviewer_session", "scope", "limitations"))
                and review["independent"] is True and review["author_session"] != review["reviewer_session"], "author self-review is not independent")
        require(re.fullmatch(r"[A-Za-z0-9-]+", review["reviewer_login"]), "invalid reviewer login")
        user = reader.get("/users/" + review["reviewer_login"])
        require(type(review["reviewer_id"]) is int and user.get("id") == review["reviewer_id"]
                and user.get("login") == review["reviewer_login"] and user.get("type") == "User", "reviewer identity unavailable")
        require(isinstance(review["findings"], list), "missing findings inventory")
        for finding in review["findings"]:
            require(isinstance(finding, dict) and set(finding) == {"finding", "disposition"}
                    and all(nonempty(v) for v in finding.values()), "finding needs actual disposition")
    return {"kind": record["kind"], "comment_id": comment["id"], "record": record}


def automated(reader, posted, repo, number, head, bot):
    matches = MARKER.findall(posted.get("body", ""))
    v2_matches = MARKER_V2.findall(posted.get("body", ""))
    require(len(matches) + len(v2_matches) == 1, "missing or ambiguous publisher identity")
    v2 = bool(v2_matches)
    if v2:
        repository, pr, sha, run, attempt, backend, history_digest = v2_matches[0]
    else:
        repository, pr, sha, run, attempt, backend = matches[0]
        history_digest = None
    run, attempt = int(run), int(attempt)
    require((repository, int(pr), sha) == (repo["full_name"], number, head), "publisher identity is stale or mismatched")
    require(posted.get("user", {}).get("id") == bot["id"] and bot.get("type") == "Bot"
            and posted.get("state") == "COMMENTED" and posted.get("commit_id") == head
            and nonempty(posted.get("submitted_at")), "review is not authentic submitted bot COMMENT")
    require(failure.collect(reader, repository, run, attempt) is None, "all review backends failed")
    run_data = reader.get(f"/repos/{repository}/actions/runs/{run}/attempts/{attempt}")
    require(run_data.get("conclusion") == "success", "review run failed or is unpublished")
    jobs = reader.list_jobs(run, attempt)
    for name in ("Review fallback", "Publish review and scope"):
        selected = [j for j in jobs if j.get("name") == name]
        require(len(selected) == 1 and selected[0].get("run_id") == run and selected[0].get("run_attempt") == attempt
                and selected[0].get("status") == "completed" and selected[0].get("conclusion") == "success", "producer or publisher not successful")
    artifacts = reader.pages(f"/repos/{repository}/actions/runs/{run}/artifacts", "artifacts")
    selected = [a for a in artifacts if a.get("name") == f"pr-review-result-{head}-{run}-{attempt}"]
    require(len(selected) == 1, "review artifact head mismatch")
    # The collector already bounded and validated this exact cached archive.
    with zipfile.ZipFile(io.BytesIO(reader.download_artifact(selected[0]["id"]))) as archive:
        context = json.loads(archive.read("context.json"))
        model = json.loads(archive.read("review.json"))
        history = json.loads(archive.read("history.json"))
        coverages = {}
        for name in archive.namelist():
            if name.startswith("coverage-") and name.endswith(".json"):
                receipt = json.loads(archive.read(name))
                coverages[pipeline.review_scope.coverage_digest(receipt)] = receipt
    attempts = history.get("attempts", []) if isinstance(history, dict) else history
    require(context["identity"]["pr_number"] == number and attempts[-1]["backend"] == backend, "review source targets another PR or backend")
    if v2:
        require(isinstance(history, dict) and pipeline.review_scope.history_digest(history) == history_digest,
                "publisher history digest differs from immutable artifact")
        policy = pipeline.test_scope.load_policy(pipeline.ROOT)
        pipeline.review_scope.validate_history_v2(policy, history, identity=context["identity"], coverages=coverages,
                                                 changed_paths=context["changed_paths"])
        require(any(a["status"] == "reviewed" and a["backend"] == backend for a in attempts),
                "v2 publisher marker does not identify the reviewed attempt")
        coverage = coverages[attempts[-1]["coverage_sha256"]]
    else:
        coverage = None
    history_marker = pipeline.codec.encode_history(history) if v2 else None
    payloads = []
    pipeline.pr_review_target.publish_review(repository, number, head, str(run), str(attempt), backend,
        {"summary": model["summary"], "findings": model["findings"]}, api=reader.get,
        coverage=coverage, history_digest=history_digest, history_marker=history_marker,
        write=lambda path, data: payloads.append(data))
    expected = payloads[0]
    require(posted["body"].startswith(expected["body"] + "\n\nScope "), "published summary differs from authentic model artifact")
    comments = reader.pages(f"/repos/{repository}/pulls/{number}/reviews/{posted['id']}/comments")
    require(len(comments) == len(expected["comments"]), "published findings inventory differs")
    for actual, wanted in zip(comments, expected["comments"]):
        require(actual.get("user", {}).get("id") == bot["id"] and actual.get("pull_request_review_id") == posted["id"]
                and actual.get("original_commit_id") == head and actual.get("path") == wanted["path"]
                and actual.get("original_line") == wanted["line"] and actual.get("body") == wanted["body"], "published finding differs from authentic model artifact")
    return {"kind": "automated", "review_id": posted["id"], "run_id": run, "run_attempt": attempt,
            "backend": backend, "findings": model["findings"]}


def check(reader, repository, number, head):
    result = {"schema": SCHEMA, "repository": repository, "pr_number": number, "head_sha": head,
              "status": "pending", "eligible": False, "evidence": [], "diagnostics": [],
              "conversation_protection": "not_evaluated", "merge_authorized": False}
    prefix = f"/repos/{repository}"
    try:
        require(re.fullmatch(r"[\w.-]+/[\w.-]+", repository) and type(number) is int and number > 0
                and re.fullmatch(r"[0-9a-f]{40}", head), "invalid target")
        before = reader.get(prefix + f"/pulls/{number}", fresh=True)
        if before.get("head", {}).get("sha") != head:
            result["status"] = "stale"
            return result
        require(before.get("number") == number and before.get("state") == "open" and before.get("draft") is False
                and before.get("merged") is False and before.get("base", {}).get("ref") == "main", "PR is not open and reviewable")
        repo = reader.get(prefix)
        require(repo.get("full_name") == repository and type(repo.get("id")) is int
                and before["base"].get("repo", {}).get("id") == repo["id"], "repository identity mismatch")
        bot = reader.get("/users/github-actions%5Bbot%5D")
        reviews = reader.pages(prefix + f"/pulls/{number}/reviews")
        comments = reader.pages(prefix + f"/issues/{number}/comments")
        for posted in reviews:
            if posted.get("commit_id") != head or "lmdj-review-v1" not in posted.get("body", ""):
                continue
            try:
                result["evidence"].append(automated(reader, posted, repo, number, head, bot))
            except Exception as error:
                result["diagnostics"].append({"review_id": posted["id"], "status": "invalid_or_unavailable",
                    "why": str(error) if isinstance(error, Refused) else "retained review source could not be authenticated",
                    "remedy": "inspect exact run/attempt and publisher artifact, or obtain owner-attested independent takeover"})
        for comment in comments:
            try:
                evidence = manual(reader, comment, repo, head)
                if evidence:
                    result["evidence"].append(evidence)
            except Exception as error:
                result["diagnostics"].append({"comment_id": comment["id"], "status": "invalid_or_stale_attestation",
                    "why": str(error) if isinstance(error, Refused) else "owner attestation could not be parsed or authenticated",
                    "remedy": "owner must append a fresh exact-head record using the documented closed JSON format"})
        # Retain current-head run failures even when an owner takes over.
        runs = reader.pages(prefix + f"/actions/workflows/pr-review.yml/runs?head_sha={head}", "workflow_runs")
        result["runs"] = [{k: r.get(k) for k in ("id", "run_attempt", "status", "conclusion")} for r in runs]
        after = reader.get(prefix + f"/pulls/{number}", fresh=True)
        if after.get("head", {}).get("sha") != head:
            result["status"] = "stale"
        elif (any(after.get(k) != before.get(k) for k in ("state", "draft", "merged"))
              or after.get("base", {}).get("ref") != "main"
              or after.get("base", {}).get("repo", {}).get("id") != repo["id"]):
            result["status"] = "invalid"
        elif result["evidence"]:
            result.update(status="eligible", eligible=True)
        elif result["diagnostics"]:
            result["status"] = "invalid"
    except Exception as error:
        result.update(status="invalid" if isinstance(error, Refused) else "unavailable", eligible=False)
        result["diagnostics"].append({"status": "incomplete_or_unavailable_API_evidence",
            "why": str(error) if isinstance(error, Refused) else "complete authenticated API evidence is unavailable",
            "remedy": "restore complete API visibility and rerun the read-only current-head check"})
    return result


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"schema": SCHEMA, "status": "invalid", "eligible": False, "merge_authorized": False,
                          "why": "invalid CLI target or arguments",
                          "remedy": "pass --repository owner/name --pr-number NUMBER --expect-head FULL_SHA"}))
        self.exit(2)


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--expect-head", required=True)
    args = parser.parse_args(argv)
    try:
        reader = Reader(reporting.UrllibGitHubApi(args.repository, os.environ.get("GITHUB_TOKEN", "")), args.repository)
        result = check(reader, args.repository, args.pr_number, args.expect_head)
    except Exception:
        result = {"schema": SCHEMA, "status": "unavailable", "eligible": False, "merge_authorized": False}
    explanations = {
        "eligible": ("current-head review evidence is eligible", "separately verify findings dispositions, live conversations, authority and protection before guarded merge"),
        "pending": ("no eligible published current-head review or owner record", "wait for a bounded interval or obtain an independent takeover; waiting does not grant approval"),
        "stale": ("live PR head differs from expected review head", "review the new exact head and rerun with its full SHA"),
        "invalid": ("review evidence or target violates an admission invariant", "inspect diagnostics and supply authentic current-head evidence"),
        "unavailable": ("complete authenticated API evidence is unavailable", "restore API access and rerun; unavailable does not mean approval"),
    }
    result["why"], result["remedy"] = explanations[result["status"]]
    print(json.dumps(result, sort_keys=True))
    return 0 if result["eligible"] else 1


if __name__ == "__main__":
    sys.exit(main())
