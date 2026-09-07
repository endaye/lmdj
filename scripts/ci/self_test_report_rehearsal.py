#!/usr/bin/env python3
"""Opt-in real-API drill of apply_report, never a self-test verdict producer.

Default is a no-network plan. Execution needs a genuine Actions GITHUB_TOKEN
with issues:write; a PAT/gh user's identity is NOT the reporter bot identity.
Only the dedicated label/key namespace is visible through IsolatedApi.
No production marker-author predicate or retry implementation is patched.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import time

REPOSITORY = "endaye/lmdj"
REPORTER_SHA256 = "7e1bae282bfcb1183873428c0b2de92ecb01ff707cca4539b5be9aa8db6b0a7b"
WARNING = "SYNTHETIC REPORTER DRILL — NOT A PRODUCT FAILURE OR SELF-TEST VERDICT"


def require(condition, message):
    if not condition:
        raise RuntimeError(f"why: {message}; remedy: stop this drill, inspect its isolated evidence and correct the reviewed invocation")


def emit(stage, **facts):
    print(json.dumps({"stage": stage, **facts}, sort_keys=True), flush=True)


class IsolatedApi:
    """Real endpoint adapter, constrained to exactly this drill namespace.

    list_issues routes the reporter's normal label to a unique drill label;
    it does not rewrite users, markers, bodies returned by GitHub, or outcomes.
    Writes require exact key+label ownership checked with a fresh GET.
    Faults below are explicitly local injection, not GitHub outages.
    """
    def __init__(self, rep, client, drill_id):
        self.rep, self.client = rep, client
        self.label = f"self-test-drill-{drill_id}"
        self.keys = {f"reporter-drill-{drill_id}", f"reporter-drill-{drill_id}-create-loss"}
        self.fault = None
        self.writes = []
        self.sleeps = []

    def request(self, method, suffix, body=None):
        return self.client._request(method, self.client._repo(suffix), body=body)

    def owned(self, issue):
        labels = {item["name"] for item in issue.get("labels", [])}
        body = str(issue.get("body") or "")
        markers = [self.rep._KEY_MARKER.format(key=key) for key in self.keys]
        require("pull_request" not in issue and self.label in labels
                and "self-test" not in labels and WARNING in body
                and sum(marker in body for marker in markers) == 1
                and str(issue.get("title", "")).startswith("[REPORTER DRILL] "),
                "Refusing to touch an issue outside exact drill ownership")
        return issue

    def get_issue(self, number):
        return self.owned(self.request("GET", f"/issues/{int(number)}"))

    def list_issues(self, *, label, state):
        require(label == self.rep.REPORT_LABEL and state == "all", "Unexpected reporter query")
        issues = self.client.list_issues(label=self.label, state=state)
        return [self.owned(issue) for issue in issues]

    def list_comments(self, number):
        self.get_issue(number)
        return self.client.list_comments(number)

    def create_issue(self, *, title, body, labels, assignees):
        require(tuple(labels) == (self.label,) and title.startswith("[REPORTER DRILL] ")
                and WARNING in body and any(self.rep._KEY_MARKER.format(key=key) in body
                                           for key in self.keys), "Unsafe create_issue input")
        # Two planned buckets only. This does not mask a duplicate: any third
        # create is an explicit failure, while final assertions require two.
        require(sum(w[0] == "create_issue" for w in self.writes) < 2, "Issue write budget exceeded")
        result = self.client.create_issue(title=title, body=f"> **{WARNING}**\n\n" + body,
                                          labels=labels, assignees=assignees)
        self.writes.append(("create_issue", result["number"]))
        self.owned(result)
        require(self.rep._trusted_marker_author(result),
                "Real author is not github-actions[bot]/Bot; stop, never rewrite its identity")
        emit("real-create-issue", number=result["number"], url=result.get("html_url"),
             author=result.get("user", {}).get("login"))
        if self.fault == "create-response-lost":
            self.fault = None
            emit("injected-response-loss", operation="create_issue", persisted=True)
            raise self.rep.GitHubApiError(0, "DRILL: locally discarded successful issue response")
        return result

    def create_comment(self, number, body):
        self.get_issue(number)
        require(WARNING in body, "Comment lacks synthetic warning")
        if self.fault == "refuse-comment":
            self.fault = None
            emit("injected-refusal", status=403, request_sent=False)
            raise self.rep.GitHubApiError(403, "DRILL: locally refused before HTTP POST")
        result = self.client.create_comment(number, body)
        self.writes.append(("create_comment", number, result["id"]))
        require(self.rep._trusted_marker_author(result), "Comment author is not trusted Actions bot")
        emit("real-create-comment", issue=number, comment_id=result["id"], url=result.get("html_url"))
        if self.fault == "comment-response-lost":
            self.fault = None
            emit("injected-response-loss", operation="create_comment", persisted=True)
            raise self.rep.GitHubApiError(0, "DRILL: locally discarded successful comment response")
        return result

    def set_issue_state(self, number, state):
        self.get_issue(number)
        result = self.client.set_issue_state(number, state)
        self.writes.append(("set_issue_state", number, state))
        emit("real-issue-state", number=number, state=state)
        return result

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        emit("real-retry-backoff", seconds=seconds)
        time.sleep(seconds)

    def cleanup(self):
        # Recover by dedicated label too, in case a genuine POST response was
        # lost before its issue number reached this process. Never delete.
        for issue in self.list_issues(label=self.rep.REPORT_LABEL, state="all"):
            if issue["state"] != "closed":
                self.set_issue_state(issue["number"], "closed")
        require(all(issue["state"] == "closed" for issue in
                    self.list_issues(label=self.rep.REPORT_LABEL, state="all")), "Cleanup not verified")
        emit("cleanup-verified", label=self.label, action="closed-only-label-retained")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--drill-id", required=True, help="fresh reviewed 12 lowercase hex characters")
    parser.add_argument("--run-id", type=int, required=True, help="actual Actions rehearsal run id, not a self-test run")
    parser.add_argument("--execute", action="store_true", help="explicitly permit real issue/label writes")
    parser.add_argument("--cleanup", action="store_true", help="close only this exact drill's issues")
    parser.add_argument("--confirm-repository", default="")
    args = parser.parse_args()
    require(re.fullmatch(r"[0-9a-f]{12}", args.drill_id), "Invalid drill id")
    require(args.run_id > 0, "Actual rehearsal run id must be positive")
    source = args.checkout / "scripts/ci/self_test_report.py"
    require(hashlib.sha256(source.read_bytes()).hexdigest() == REPORTER_SHA256,
            "Reporter source differs from reviewed main; stop and re-review")
    sys.path.insert(0, str(source.parent.resolve()))
    rep = importlib.import_module("self_test_report")
    emit("plan", repository=REPOSITORY, label=f"self-test-drill-{args.drill_id}", run_id=args.run_id,
         reporter_sha256=REPORTER_SHA256, remote_writes=args.execute,
         max_planned_issues=2, max_planned_comments=4,
         evidence_boundary="synthetic Report inputs only; no verdict, artifact, CI result or release evidence")
    if not args.execute:
        return 0
    require(args.confirm_repository == REPOSITORY, "Exact repository confirmation required")
    # Refuse the anticipated local-human-identity trap BEFORE reading a token
    # or doing any network call. No gh auth token command exists in this script.
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_RUN_ID") == str(args.run_id)
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1",
            "Needs the real repository Actions context; local gh user is not the trusted reporter bot")
    client = rep.UrllibGitHubApi(REPOSITORY, os.environ.get("GITHUB_TOKEN", ""))
    api = IsolatedApi(rep, client, args.drill_id)
    require(api.request("GET", "").get("full_name") == REPOSITORY,
            "Repository read must succeed before interpreting an absent label")
    if args.cleanup:
        api.cleanup()
        return 0
    try:
        api.request("GET", f"/labels/{api.label}")
    except rep.GitHubApiError as error:
        require(error.status == 404, "Label preflight failed; no writes authorized after ambiguous read")
    else:
        raise RuntimeError("Drill label already exists; use --cleanup or a fresh id, never overwrite")
    api.request("POST", "/labels", {"name": api.label, "color": "D4C5F9",
                                   "description": "Isolated synthetic reporter drill; not self-test evidence"})
    emit("real-label-created", label=api.label)

    def report(sequence, *, create_loss=False):
        key = f"reporter-drill-{args.drill_id}" + ("-create-loss" if create_loss else "")
        return rep.Report(key=key, title=f"[REPORTER DRILL] {args.drill_id}",
                          observation=f"{args.run_id}/1/drill-{args.drill_id}/{sequence}",
                          severity="low", labels=(api.label,), summary=WARNING,
                          detail=f"Rehearsal run: https://github.com/{REPOSITORY}/actions/runs/{args.run_id}\n"
                                 "No self-test run/target/policy is asserted. This tests reporting transport only.")

    def apply(item, expected):
        result = rep.apply_report(api, item, assignee="endaye", sleep=api.sleep)
        emit("reporter-outcome", expected=expected, actual=result.action, issue=result.issue_number)
        require(result.action == expected, f"Expected {expected}, got {result.action}")
        return result.issue_number

    def duplicate(item):
        before = list(api.writes)
        apply(item, "duplicate")
        require(api.writes == before, "Duplicate observation performed a write")

    try:
        first = report(1)
        number = apply(first, "created")
        duplicate(first)
        second = report(2)
        require(apply(second, "commented") == number, "Recurrence escaped bucket")
        api.set_issue_state(number, "closed")
        require(apply(report(3), "reopened") == number, "Closed recurrence escaped bucket")
        fourth = report(4)
        before_writes, before_sleeps = list(api.writes), list(api.sleeps)
        api.fault = "refuse-comment"
        try:
            apply(fourth, "commented")
        except rep.GitHubApiError as error:
            require(error.status == 403, "Unexpected API failure instead of injected refusal")
        else:
            raise RuntimeError("Injected 403 did not propagate")
        require(api.writes == before_writes and api.sleeps == before_sleeps,
                "403 performed a write or was retried")
        require(len(api.list_comments(number)) == 2, "Refusal changed persisted comments")
        apply(fourth, "commented")
        duplicate(fourth)
        fifth = report(5)
        api.fault = "comment-response-lost"
        apply(fifth, "duplicate")
        duplicate(fifth)
        require(len(api.list_comments(number)) == 4, "Lost response caused missing/duplicate comment")
        api.fault = "create-response-lost"
        lost_create = report(1, create_loss=True)
        apply(lost_create, "duplicate")
        duplicate(lost_create)
        issues = api.list_issues(label=rep.REPORT_LABEL, state="all")
        require(len(issues) == 2, "Expected exactly two drill buckets")
        for item in [report(i) for i in range(1, 6)] + [lost_create]:
            issue = next(issue for issue in issues if item.key_marker in issue["body"])
            texts = [issue["body"], *(c["body"] for c in api.list_comments(issue["number"]))]
            require(sum(text.count(item.observation_marker) for text in texts) == 1,
                    "Persisted observation marker is missing or duplicated")
        emit("drill-assertions-passed", issues=[i["number"] for i in issues],
             fault_scope="injected 403 before HTTP; injected response loss after real persisted POST",
             proves="apply_report plus real API persistence under original bot-author checks",
             does_not_prove="actual GitHub outage, product self-test verdict, permissions denial or full workflow execution")
    finally:
        api.cleanup()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Never print request headers, credentials or arbitrary API body text.
        print(json.dumps({"stage": "drill-failed", "error_type": type(error).__name__,
                          "message": str(error) if isinstance(error, RuntimeError) else "See stage log; no credentials logged"}),
              file=sys.stderr)
        raise SystemExit(1)
