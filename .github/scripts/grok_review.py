#!/usr/bin/env python3
"""Advisory Grok pull-request review for GitHub Actions.

The workflow posts a sticky comment. Findings never fail the job. Missing
credentials, an empty diff, an oversized diff, or the skip label exit 0.
Infra failures after credentials are present exit non-zero.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.parse import quote
import urllib.error
import urllib.request


COMMENT_MARKER = "<!-- lmdj-grok-review -->"
ISSUE_TRACKING_ID = "lmdj-grok-review-pr-{pr_number}"
ISSUE_MARKER = "<!-- {tracking_id} -->"
SKIP_LABEL = "skip-grok-review"
MAX_DIFF_BYTES = 400_000
PINNED_GROK_VERSION = "1.0.13"
READ_ONLY_TOOLS = "read_file,grep,list_dir"
GROK_TIMEOUT_SECONDS = 720
API_VERSION = "2022-11-28"
ACTIONABLE_SEVERITIES = ("critical", "important")
FINDING_HEADING = re.compile(
    r"^###\s*\[(critical|important|nit)\]\s+(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
VERDICT_LINE = re.compile(
    r"^##\s*Verdict\s*\n([\s\S]*?)(?=^##\s|\Z)",
    re.IGNORECASE | re.MULTILINE,
)
CLOSING_KEYWORD = re.compile(
    r"\b(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+#\d+",
    re.IGNORECASE,
)

REVIEW_INSTRUCTIONS = """\
You are reviewing a pull request for LMDJ New Headless Core.

This is an advisory review. Do not apply patches, edit files, run builds, or
claim you will fix anything. Read only what you need.

Report only defects you can point to in the diff or a nearby file. Skip style
nits, speculative refactors, and issues already proven by tests in the diff
unless the test itself is wrong.

Look for:

- Hosts using Application Facade only; they must not parse Project bundles.
- Project Truth as authoring state; Runtime Snapshot is immutable derived
  state and is never persisted as Project Truth.
- Pattern events referencing Pad Slots, never Assets directly.
- Provider selection in Workspace/Host settings, not Project Truth.
- Provider failure in Attempt state, never Project Truth.
- Provider code receiving Artifact inputs and an Artifact output sink, never
  a mutable Project or Project bundle path.
- Product-specific wiring only in Product Assembly.
- New code restoring, wrapping, translating, or emitting retired
  `lmdj.patch.v1` or `lmdj.materials.v1`.
- Missing tests for a behavior change, incorrect CI scope, or a documentation
  impact declaration that does not match the diff.
- Security, correctness, and concurrency defects.

Write GitHub-flavored markdown:

## Verdict
`clean` if you have no findings, otherwise `issues`.

## Findings
For each finding:

### [critical|important|nit] short title
- Path: `file:line` when known
- Why: one or two sentences
- Remedy: the smallest correction

If there are no findings, say `No findings.` under Findings and do not invent
work. End with a one-paragraph summary of what the diff does.
"""


def skip_reason(
    *,
    draft: bool,
    labels: Sequence[str] | None = None,
    auth_json: str,
    api_key: str,
    diff: bytes,
    same_repository: bool,
) -> str | None:
    if draft:
        return "draft pull request"
    if not same_repository:
        return "fork pull request; repository secrets are not used on forks"
    label_set = {label.strip() for label in (labels or []) if label.strip()}
    if SKIP_LABEL in label_set:
        return f"{SKIP_LABEL} label"
    if not auth_json.strip() and not api_key.strip():
        return "no GROK_AUTH_JSON or XAI_API_KEY secret"
    if not diff.strip():
        return "empty diff"
    if len(diff) > MAX_DIFF_BYTES:
        return f"diff exceeds {MAX_DIFF_BYTES} bytes"
    return None


def parse_labels(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def build_prompt(
    *,
    title: str,
    body: str,
    base_ref: str,
    head_ref: str,
    pr_url: str,
    diff: str,
) -> str:
    body_text = body.strip() or "(empty)"
    return (
        f"{REVIEW_INSTRUCTIONS}\n"
        f"## Pull request\n"
        f"- Title: {title.strip() or '(untitled)'}\n"
        f"- URL: {pr_url.strip() or '(none)'}\n"
        f"- Base: {base_ref.strip() or '(unknown)'}\n"
        f"- Head: {head_ref.strip() or '(unknown)'}\n\n"
        f"## Description\n{body_text}\n\n"
        f"## Diff\n```diff\n{diff.rstrip()}\n```\n"
    )


def tracking_id(pr_number: int) -> str:
    return ISSUE_TRACKING_ID.format(pr_number=pr_number)


def parse_verdict(text: str) -> str:
    match = VERDICT_LINE.search(text or "")
    if match is None:
        return ""
    body = match.group(1)
    if re.search(r"\bclean\b", body, re.IGNORECASE):
        return "clean"
    if re.search(r"\bissues\b", body, re.IGNORECASE):
        return "issues"
    return ""


def parse_findings(text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    matches = list(FINDING_HEADING.finditer(text or ""))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        findings.append({
            "severity": match.group(1).lower(),
            "title": match.group(2).strip(),
            "body": text[start:end].strip(),
        })
    return findings


def actionable_findings(findings: Sequence[Mapping[str, str]]) -> list[Mapping[str, str]]:
    return [item for item in findings if item.get("severity") in ACTIONABLE_SEVERITIES]


def should_open_issue(*, verdict: str, findings: Sequence[Mapping[str, str]]) -> bool:
    if actionable_findings(findings):
        return True
    return verdict == "issues" and not findings


def issue_priority(findings: Sequence[Mapping[str, str]]) -> str:
    if any(item.get("severity") == "critical" for item in findings):
        return "priority:p1"
    return "priority:p2"


def format_issue_body(
    *,
    pr_number: int,
    pr_url: str,
    text: str,
    findings: Sequence[Mapping[str, str]],
) -> str:
    marker = ISSUE_MARKER.format(tracking_id=tracking_id(pr_number))
    source = pr_url.strip() or f"pull request {pr_number}"
    actionable = actionable_findings(findings)
    if actionable:
        blocks = []
        for item in actionable:
            block = f"### [{item['severity']}] {item['title']}"
            if item.get("body"):
                block += f"\n{item['body']}"
            blocks.append(block)
        findings_md = "\n\n".join(blocks)
    else:
        findings_md = text.strip() or "_Grok reported issues but returned no structured findings._"
    body = (
        f"{marker}\n"
        f"Tracking id: `{tracking_id(pr_number)}`\n\n"
        "Opened by the advisory Grok review. Merge is not blocked.\n\n"
        f"Source pull request: {source}\n\n"
        "## Actionable findings\n\n"
        f"{findings_md}\n\n"
        "Nit findings stay on the pull request comment and are not copied here.\n"
    )
    if CLOSING_KEYWORD.search(body):
        raise RuntimeError("issue body contains a GitHub closing keyword")
    return body


def format_comment(
    *,
    text: str,
    grok_payload: Mapping[str, Any] | None,
    tracking_issue: str = "",
) -> str:
    body = text.strip() or "_Grok returned an empty review._"
    footer_parts = []
    if grok_payload:
        model_usage = grok_payload.get("modelUsage") or {}
        if isinstance(model_usage, dict) and model_usage:
            footer_parts.append("models: " + ", ".join(sorted(model_usage)))
        usage = grok_payload.get("usage") or {}
        if isinstance(usage, dict) and usage.get("total_tokens") is not None:
            footer_parts.append(f"tokens: {usage['total_tokens']}")
        if grok_payload.get("total_cost_usd") is not None:
            footer_parts.append(f"cost: ${grok_payload['total_cost_usd']}")
    footer = ""
    if footer_parts:
        footer = "\n\n---\n" + " · ".join(footer_parts)
    tracking = ""
    if tracking_issue:
        tracking = (
            f"\nTracking Issue {tracking_issue}. Merge is still not blocked.\n"
        )
    return (
        f"{COMMENT_MARKER}\n"
        "# Grok advisory review\n\n"
        "This comment is **advisory**. It is not a required check and does "
        "not block merge. Core CI and the merge queue are unchanged.\n\n"
        f"{body}"
        f"{tracking}"
        f"{footer}\n"
    )


def write_auth_json(contents: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents if contents.endswith("\n") else contents + "\n", encoding="utf-8")
    path.chmod(0o600)


def grok_command(prompt_file: Path, cwd: Path) -> list[str]:
    # Do not pass --sandbox strict/read-only on GitHub-hosted Ubuntu: Grok's
    # Linux deny list resolves /run/podman/podman.sock, the runner socket is
    # unreadable, and bwrap refuses to start. Isolation is the read-only tool
    # allowlist plus credential path denies.
    return [
        "grok",
        "--prompt-file",
        str(prompt_file),
        "--output-format",
        "json",
        "--yolo",
        "--tools",
        READ_ONLY_TOOLS,
        "--disable-web-search",
        "--no-subagents",
        "--max-turns",
        "16",
        "--effort",
        "medium",
        "--no-auto-update",
        "--cwd",
        str(cwd),
        "--deny",
        "Read(**/.grok/**)",
        "--deny",
        "Read(**/auth.json)",
    ]


def run_grok(command: Sequence[str], env: Mapping[str, str]) -> dict[str, Any]:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        env=dict(env),
        timeout=GROK_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or "no grok output"
        raise RuntimeError(f"grok exited {completed.returncode}: {stderr[:4000]}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"grok stdout is not JSON: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("grok JSON payload is not an object")
    if payload.get("type") == "error":
        raise RuntimeError(payload.get("message") or "grok returned an error object")
    return payload


def github_request(
    method: str,
    url: str,
    token: str,
    payload: Mapping[str, Any] | None = None,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "lmdj-grok-review",
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


def upsert_sticky_comment(
    *,
    repository: str,
    pr_number: int,
    token: str,
    body: str,
    requester: Any = github_request,
) -> str:
    owner, name = repository.split("/", 1)
    list_url = f"https://api.github.com/repos/{owner}/{name}/issues/{pr_number}/comments?per_page=100"
    comments = requester("GET", list_url, token)
    if not isinstance(comments, list):
        raise RuntimeError("GitHub comment list is not an array")
    existing_id = None
    for comment in comments:
        if COMMENT_MARKER in str(comment.get("body") or ""):
            existing_id = comment.get("id")
            break
    if existing_id is not None:
        update_url = f"https://api.github.com/repos/{owner}/{name}/issues/comments/{existing_id}"
        requester("PATCH", update_url, token, {"body": body})
        return "updated"
    create_url = f"https://api.github.com/repos/{owner}/{name}/issues/{pr_number}/comments"
    requester("POST", create_url, token, {"body": body})
    return "created"


def find_tracking_issue(
    *,
    repository: str,
    pr_number: int,
    token: str,
    requester: Any = github_request,
) -> dict[str, Any] | None:
    query = quote(f'repo:{repository} "{tracking_id(pr_number)}" in:body')
    payload = requester("GET", f"https://api.github.com/search/issues?q={query}&per_page=5", token)
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        return None
    return items[0] if isinstance(items[0], dict) else None


def upsert_tracking_issue(
    *,
    repository: str,
    pr_number: int,
    pr_url: str,
    token: str,
    text: str,
    findings: Sequence[Mapping[str, str]],
    verdict: str,
    requester: Any = github_request,
) -> str:
    owner, name = repository.split("/", 1)
    existing = find_tracking_issue(
        repository=repository,
        pr_number=pr_number,
        token=token,
        requester=requester,
    )
    open_issue = should_open_issue(verdict=verdict, findings=findings)
    if open_issue:
        body = format_issue_body(
            pr_number=pr_number,
            pr_url=pr_url,
            text=text,
            findings=findings,
        )
        title = f"bug: Grok review findings on PR {pr_number}"
        labels = ["type:bug", "area:ci-release", issue_priority(actionable_findings(findings) or findings)]
        if existing and existing.get("number") is not None:
            number = int(existing["number"])
            requester(
                "PATCH",
                f"https://api.github.com/repos/{owner}/{name}/issues/{number}",
                token,
                {"title": title, "body": body, "state": "open", "labels": labels},
            )
            return f"updated #{number}"
        created = requester(
            "POST",
            f"https://api.github.com/repos/{owner}/{name}/issues",
            token,
            {"title": title, "body": body, "labels": labels},
        )
        number = (created or {}).get("number")
        return f"created #{number}" if number else "created"
    if existing and existing.get("state") == "open" and existing.get("number") is not None:
        number = int(existing["number"])
        requester(
            "POST",
            f"https://api.github.com/repos/{owner}/{name}/issues/{number}/comments",
            token,
            {
                "body": (
                    "Later Grok review found no remaining critical or important "
                    f"findings on pull request {pr_url.strip() or pr_number}."
                )
            },
        )
        requester(
            "PATCH",
            f"https://api.github.com/repos/{owner}/{name}/issues/{number}",
            token,
            {"state": "closed"},
        )
        return f"closed #{number}"
    return "skipped"


def notice(message: str) -> None:
    print(f"::notice::{message}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"{message}\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff-file", default=os.environ.get("DIFF_FILE", ""))
    parser.add_argument("--pr-number", default=os.environ.get("PR_NUMBER", ""))
    parser.add_argument("--title", default=os.environ.get("PR_TITLE", ""))
    parser.add_argument("--body-file", default=os.environ.get("PR_BODY_FILE", ""))
    parser.add_argument("--pr-url", default=os.environ.get("PR_URL", ""))
    parser.add_argument("--base-ref", default=os.environ.get("BASE_REF", ""))
    parser.add_argument("--head-ref", default=os.environ.get("HEAD_REF", ""))
    parser.add_argument("--repository", default=os.environ.get("REPOSITORY", ""))
    parser.add_argument("--cwd", default=os.environ.get("GITHUB_WORKSPACE", os.getcwd()))
    parser.add_argument("--labels", default=os.environ.get("PR_LABELS", ""))
    parser.add_argument("--draft", action="store_true", default=os.environ.get("PR_DRAFT") == "true")
    parser.add_argument(
        "--same-repository",
        action="store_true",
        default=os.environ.get("PR_SAME_REPOSITORY", "true") == "true",
    )
    parser.add_argument("--output", default=os.environ.get("REVIEW_OUTPUT", ""))
    parser.add_argument("--post-comment", action="store_true", default=os.environ.get("POST_COMMENT", "true") == "true")
    parser.add_argument("--no-post-comment", action="store_false", dest="post_comment")
    parser.add_argument("--post-issue", action="store_true", default=os.environ.get("POST_ISSUE", "true") == "true")
    parser.add_argument("--no-post-issue", action="store_false", dest="post_issue")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    auth_json = os.environ.get("GROK_AUTH_JSON", "")
    api_key = os.environ.get("XAI_API_KEY", "")
    diff_path = Path(args.diff_file) if args.diff_file else None
    diff = diff_path.read_bytes() if diff_path and diff_path.is_file() else b""
    reason = skip_reason(
        draft=bool(args.draft),
        labels=parse_labels(args.labels),
        auth_json=auth_json,
        api_key=api_key,
        diff=diff,
        same_repository=bool(args.same_repository),
    )
    if reason:
        notice(f"Grok advisory review skipped: {reason}")
        return 0

    body = ""
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    elif os.environ.get("PR_BODY"):
        body = os.environ["PR_BODY"]

    prompt = build_prompt(
        title=args.title,
        body=body,
        base_ref=args.base_ref,
        head_ref=args.head_ref,
        pr_url=args.pr_url,
        diff=diff.decode("utf-8", errors="replace"),
    )
    work = Path(os.environ.get("RUNNER_TEMP") or "/tmp")
    prompt_file = work / "grok-review-prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")

    if auth_json.strip():
        grok_home = Path(os.environ.get("GROK_HOME") or Path.home() / ".grok")
        write_auth_json(auth_json, grok_home / "auth.json")

    env = os.environ.copy()
    env["GROK_DISABLE_AUTOUPDATER"] = "1"
    if api_key.strip():
        env["XAI_API_KEY"] = api_key.strip()

    payload = run_grok(grok_command(prompt_file, Path(args.cwd)), env)
    text = str(payload.get("text") or "")
    findings = parse_findings(text)
    verdict = parse_verdict(text)
    token = os.environ.get("GITHUB_TOKEN", "")
    issue_action = "skipped"
    if args.post_issue and token and args.repository and args.pr_number:
        issue_action = upsert_tracking_issue(
            repository=args.repository,
            pr_number=int(args.pr_number),
            pr_url=args.pr_url,
            token=token,
            text=text,
            findings=findings,
            verdict=verdict,
        )
        notice(f"Grok advisory review issue {issue_action}")
    elif args.post_issue:
        notice("Grok advisory review issue skipped: missing GITHUB_TOKEN, repository, or PR number")

    tracking = ""
    if issue_action.startswith(("created", "updated")):
        tracking = issue_action
    comment = format_comment(text=text, grok_payload=payload, tracking_issue=tracking)
    notice("Grok advisory review completed")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(comment + "\n")
    if args.output:
        Path(args.output).write_text(comment, encoding="utf-8")

    if args.post_comment and token and args.repository and args.pr_number:
        action = upsert_sticky_comment(
            repository=args.repository,
            pr_number=int(args.pr_number),
            token=token,
            body=comment,
        )
        notice(f"Grok advisory review comment {action}")
    elif args.post_comment:
        notice("Grok advisory review comment skipped: missing GITHUB_TOKEN, repository, or PR number")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 — CI entrypoint must fail closed on infra errors
        print(f"::error::{error}", file=sys.stderr)
        raise SystemExit(1)
