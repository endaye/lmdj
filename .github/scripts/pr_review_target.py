#!/usr/bin/env python3
"""Resolve the Pull Request head a standalone review run is bound to.

`pr-review.yml` reviews a Pull Request outside `ci.yml`, so nothing hands it a
`pull_request` payload it can trust to be current: a `workflow_dispatch` names
only a number, and a `pull_request` event may describe a head that has since
moved. This reads the live Pull Request once, publishes the facts the review
jobs need as step outputs, and -- when told what head the caller believes it is
reviewing -- refuses to continue if the live head is a different commit. A
review posted against a head nobody can see any more is the "stale head
passing as current" case the plan forbids (spec §4.1).

`urllib`, not `gh`: the self-hosted `ci-general` runners do not install `gh`.
The token is read from `GITHUB_TOKEN`; the endpoint is read-only.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
import uuid

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"

EXIT_OK = 0
EXIT_UNREADABLE = 2
EXIT_STALE_HEAD = 3
EXIT_NOT_OPEN = 4

Request = Callable[[str], object]


class TargetUnavailable(RuntimeError):
    """The Pull Request could not be read; nothing about it is known."""


def github_request(
    method: str,
    url: str,
    token: str,
    payload: Mapping[str, object] | None = None,
) -> object:
    """One authenticated GitHub REST call; only the trusted publisher uses writes."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "lmdj-pr-review",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub {method} {url} failed: {error.code} {detail[:2000]}") from error
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _api(path: str) -> object:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise TargetUnavailable(
            "why: GITHUB_TOKEN is unset, so the Pull Request head cannot be read; "
            "remedy: pass secrets.GITHUB_TOKEN to the step"
        )
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "lmdj-pr-review-target",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError) as error:
        detail = getattr(error, "code", None) or str(error)
        raise TargetUnavailable(
            f"why: reading {path} failed ({detail}); remedy: restore API access "
            "for the runner (token scope, rate limit, network) and rerun"
        ) from error


def resolve_target(repository: str, pr_number: int, *, api: Request | None = None) -> dict[str, str]:
    """The review-relevant facts of one Pull Request, as flat string outputs.

    `review` is the single condition the review jobs key on: an open, same-
    repository, non-draft Pull Request. `reason` says why not otherwise, so the
    run summary can state what was not reviewed rather than leaving a green
    nothing.
    """
    api = api or _api  # resolved at call time so a test can stand in for the API
    payload = api(f"/repos/{repository}/pulls/{pr_number}")
    if not isinstance(payload, Mapping):
        raise TargetUnavailable(
            f"why: the Pull Request endpoint for #{pr_number} returned no object; "
            "remedy: check the number and rerun"
        )
    head = payload.get("head") or {}
    base = payload.get("base") or {}
    head_repo = (head.get("repo") or {}).get("full_name") or ""
    same_repository = head_repo == repository
    draft = bool(payload.get("draft"))
    state = str(payload.get("state") or "")
    labels = ",".join(
        str(label.get("name") or "") for label in (payload.get("labels") or [])
        if isinstance(label, Mapping) and label.get("name")
    )
    if state != "open":
        reason = f"pull request is {state or 'not open'}"
    elif not same_repository:
        reason = "fork pull request; repository secrets are not used on forks"
    elif draft:
        reason = "draft pull request"
    elif base.get("ref") != "main":
        reason = "pull request does not target main"
    elif not re.fullmatch(r"[0-9a-f]{40}", str(head.get("sha") or "")):
        reason = "invalid pull request head identity"
    else:
        reason = ""
    return {
        "number": str(pr_number),
        "state": state,
        "head_sha": str(head.get("sha") or ""),
        "base_sha": str(base.get("sha") or ""),
        "head_ref": str(head.get("ref") or ""),
        "base_ref": str(base.get("ref") or ""),
        "title": str(payload.get("title") or ""),
        "html_url": str(payload.get("html_url") or ""),
        "draft": "true" if draft else "false",
        "same_repository": "true" if same_repository else "false",
        "labels": labels,
        "review": "true" if not reason else "false",
        "reason": reason,
        "body": str(payload.get("body") or ""),
    }


def stale_head_diagnostic(expected: str, live: str, pr_number: int) -> str | None:
    """None when `live` is the head the caller meant; otherwise why/remedy."""
    if expected.lower() == live.lower():
        return None
    return (
        f"why: #{pr_number} now points at {live[:12]}, not the {expected[:12]} this run "
        "was started for -- a review posted now would describe a head nobody can see; "
        "remedy: let the run for the new head review it (dispatch pr-review.yml again with "
        "the Pull Request number if none is running)"
    )


def _write_outputs(path: Path, target: Mapping[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in target.items():
            if key == "body":
                continue
            # Titles carry arbitrary text; the heredoc form keeps newlines out
            # of the key=value grammar.
            delimiter = "LMDJ_" + uuid.uuid4().hex
            handle.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def review_identity(repository: str, number: int, head: str, run: str,
                    attempt: str, backend: str, *, history_digest: str | None = None) -> str:
    if (not re.fullmatch(r"[0-9a-f]{40}", head) or not run.isdigit()
            or not attempt.isdigit() or backend not in {"glm", "kimi", "grok", "deepseek"}
            or number < 1 or not re.fullmatch(r"[\w.-]+/[\w.-]+", repository)):
        raise TargetUnavailable("why: invalid review identity; remedy: use trusted resolver outputs")
    if history_digest is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", history_digest):
            raise TargetUnavailable("why: invalid v2 history digest; remedy: use the complete authenticated history")
        return f"<!-- lmdj-review-v2 {repository} {number} {head} {run} {attempt} {backend} sha256={history_digest} -->"
    return f"<!-- lmdj-review-v1 {repository} {number} {head} {run} {attempt} {backend} -->"


def validate_review(payload: object, *, coverage: Mapping | None = None) -> dict:
    """Validate model data, never treat it as a command or merge decision."""
    if not isinstance(payload, dict) or set(payload) != {"summary", "findings"}:
        raise TargetUnavailable("why: missing structured review; remedy: inspect the model output or review manually")
    summary, findings = payload["summary"], payload["findings"]
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 12000:
        raise TargetUnavailable("why: empty or oversized review summary; remedy: rerun or review manually")
    if not isinstance(findings, list) or len(findings) > 30:
        raise TargetUnavailable("why: invalid findings array; remedy: rerun or review manually")
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {"path", "line", "body"}:
            raise TargetUnavailable("why: invalid finding fields; remedy: rerun or review manually")
        path, line, body = finding["path"], finding["line"], finding["body"]
        if (not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/")
                or not isinstance(line, int) or isinstance(line, bool) or line < 1
                or not isinstance(body, str) or not body.strip() or len(body) > 12000):
            raise TargetUnavailable("why: invalid inline finding; remedy: rerun or review manually")
        if coverage is not None:
            right = {(hunk.get("path"), item)
                     for hunk in coverage.get("observed_hunks", [])
                     for item in hunk.get("right_lines", [])}
            if (path, line) not in right:
                raise TargetUnavailable("why: inline finding is outside observed changed RIGHT-side lines; remedy: emit a clean review or cite an observed line")
    return payload


def review_payload(repository: str, number: int, head: str, run: str, attempt: str,
                   backend: str, payload: object, *, coverage: Mapping | None = None,
                   history_digest: str | None = None, history_marker: str | None = None) -> dict:
    """Pure canonical payload for publication and historical artifact verification."""
    model = validate_review(payload, coverage=coverage)
    identity = review_identity(repository, number, head, run, attempt, backend,
                               history_digest=history_digest)
    marker = "<!-- lmdj-grok-review -->" if backend == "grok" else f"<!-- lmdj-review: {backend} -->"
    if history_marker is not None:
        if not history_marker.startswith("<!-- lmdj-review-history-v2 ") or not history_marker.endswith(" -->"):
            raise TargetUnavailable("why: invalid v2 history marker; remedy: encode the complete authenticated history")
        history_marker = "\n" + history_marker
    else:
        history_marker = (f"\n<!-- lmdj-review-history-digest-v2 sha256={history_digest} -->"
                          if history_digest is not None else "")
    body = (f"{marker}\n{identity}{history_marker}\n## {backend} advisory review\n\n"
            + model["summary"] + "\n\nHuman takeover: inspect this exact revision and reply to or resolve each finding. "
            "This COMMENT review does not approve, reject or merge the PR.")
    comments = [{"path": item["path"], "line": item["line"], "side": "RIGHT",
                 "body": f"{marker}\n{identity}\n{item['body']}"} for item in model["findings"]]
    return {"commit_id": head, "event": "COMMENT", "body": body, "comments": comments}


def publish_review(repository: str, number: int, head: str, run: str, attempt: str,
                   backend: str, payload: object, *, api: Request | None = None,
                   write: Callable[[str, dict], object] | None = None,
                   coverage: Mapping | None = None, history_digest: str | None = None,
                   history_marker: str | None = None) -> str:
    """Only trusted publisher holds PR write permission; reject stale before mutation.

    COMMENT reviews (not APPROVE/REQUEST_CHANGES) keep model text advisory.
    A clean summary has no inline comments, so creates no blocking thread (#707).
    Each attempt gets its own immutable review; later runs cannot rewrite evidence.
    """
    data = review_payload(repository, number, head, run, attempt, backend, payload,
                          coverage=coverage, history_digest=history_digest, history_marker=history_marker)
    identity = review_identity(repository, number, head, run, attempt, backend, history_digest=history_digest)
    target = resolve_target(repository, number, api=api)
    if target["review"] != "true" or target["base_ref"] != "main":
        raise TargetUnavailable("why: target is no longer reviewable; remedy: inspect the PR and take over manually")
    diagnostic = stale_head_diagnostic(head, target["head_sha"], number)
    if diagnostic:
        raise TargetUnavailable(diagnostic)
    if write is None:
        write = lambda path, data: github_request("POST", f"{API_ROOT}{path}",
                                                   os.environ["GITHUB_TOKEN"], data)
    write(f"/repos/{repository}/pulls/{number}/reviews",
          data)
    # An unavoidable API race may leave a correctly attached historical review.
    # Never describe it as current; the job fails and the new head needs its own run.
    live = resolve_target(repository, number, api=api)
    diagnostic = stale_head_diagnostic(head, live["head_sha"], number)
    if diagnostic:
        raise TargetUnavailable(diagnostic)
    return identity


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repository", default="")
    parser.add_argument("--pr-number", type=int, default=0)
    parser.add_argument("--capture-output", type=Path)
    parser.add_argument("--expect-head", default="",
                        help="the head SHA the caller is reviewing; a different live head exits 3")
    parser.add_argument("--body-out", type=Path, default=None)
    parser.add_argument("--github-output", type=Path, default=None)
    parser.add_argument("--publish-file", type=Path)
    parser.add_argument("--backend", default="")
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    args = parser.parse_args(argv)

    try:
        if args.capture_output:
            data = validate_review(json.loads(os.environ.get("REVIEW_JSON", "")))
            args.capture_output.parent.mkdir(parents=True, exist_ok=True)
            args.capture_output.write_text(json.dumps(data), encoding="utf-8")
            return EXIT_OK
        if not args.repository or args.pr_number < 1:
            raise TargetUnavailable("why: repository and positive PR number required; remedy: pass resolver inputs")
        if args.publish_file:
            if args.publish_file.stat().st_size > 400000:
                raise TargetUnavailable("why: oversized review artifact; remedy: inspect output and rerun")
            identity = publish_review(args.repository, args.pr_number, args.expect_head,
                                      args.run_id, args.run_attempt, args.backend,
                                      json.loads(args.publish_file.read_text(encoding="utf-8")))
            print(identity)
            return EXIT_OK
        target = resolve_target(args.repository, args.pr_number)
    except (TargetUnavailable, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_UNREADABLE

    if args.body_out is not None:
        args.body_out.write_text(target["body"], encoding="utf-8")
    if args.github_output is not None:
        _write_outputs(args.github_output, target)

    for key in ("number", "state", "head_sha", "base_sha", "review", "reason"):
        print(f"{key}={target[key]}")

    if args.expect_head:
        stale = stale_head_diagnostic(args.expect_head, target["head_sha"], args.pr_number)
        if stale:
            print(stale, file=sys.stderr)
            return EXIT_STALE_HEAD
    if target["state"] != "open":
        print(f"why: #{args.pr_number} is {target['state']}, so there is no head to review; "
              "remedy: nothing -- a closed Pull Request needs no review run", file=sys.stderr)
        return EXIT_NOT_OPEN
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
