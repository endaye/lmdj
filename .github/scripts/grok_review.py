#!/usr/bin/env python3
"""Advisory Grok pull-request review for GitHub Actions.

Findings post the way the other advisory reviewers' do: `critical` and
`important` findings become inline review threads on the Pull Request, and a
sticky summary comment carries the whole review including nits. Threads are
what make a finding get read -- `main` requires conversations to be resolved,
so each one is acknowledged by a human, by fixing or by replying. The earlier
sink, a tracking Issue per Pull Request, produced four open Issues nobody had
read while the thread-posting lanes were producing findings that were acted on
the same day. An advisory finding that does not block also does not get seen.

Findings never fail the job. Missing credentials, an empty diff, an oversized
diff, or the skip label exit 0. Infra failures after credentials are present
exit non-zero.
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
import urllib.error
import urllib.request


COMMENT_MARKER = "<!-- lmdj-grok-review -->"
THREAD_MARKER = "<!-- lmdj-grok-review-thread -->"
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
# `- Path: `file:line`` or `file:start-end` or a bare `file`, as the prompt
# asks for. The location decides whether a finding can be an inline thread.
PATH_LINE = re.compile(
    r"^-\s*Path:\s*`([^`:\s]+)(?::(\d+)(?:-(\d+))?)?`",
    re.IGNORECASE | re.MULTILINE,
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


def parse_location(body: str) -> tuple[str, int | None, int | None] | None:
    """(path, start_line, end_line) from a finding's `- Path:` line, if any."""
    match = PATH_LINE.search(body or "")
    if not match:
        return None
    path, start, end = match.group(1), match.group(2), match.group(3)
    start_line = int(start) if start else None
    end_line = int(end) if end else start_line
    return path, start_line, end_line


def format_thread_body(finding: Mapping[str, str], *, head_sha: str) -> str:
    lines = [THREAD_MARKER, f"**[{finding['severity']}] {finding['title']}**"]
    body = (finding.get("body") or "").strip()
    if body:
        lines += ["", body]
    lines += ["", f"_Grok advisory review · `{head_sha[:9]}`_"]
    return "\n".join(lines)


def format_comment(
    *,
    text: str,
    grok_payload: Mapping[str, Any] | None,
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
    return (
        f"{COMMENT_MARKER}\n"
        "# Grok advisory review\n\n"
        "This lane is **advisory**: it is not a required check and Core CI and "
        "the merge queue are unchanged. `critical` and `important` findings are "
        "also posted as inline review threads, which `main`'s "
        "conversation-resolution rule holds until a human resolves each one -- "
        "by fixing it or by replying with the disagreement.\n\n"
        f"{body}"
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


def post_review(
    *,
    repository: str,
    pr_number: int,
    head_sha: str,
    token: str,
    findings: Sequence[Mapping[str, str]],
    verdict: str,
    requester: Any = github_request,
) -> str:
    """Post actionable findings as one review of inline threads.

    Nits stay on the summary comment: a thread has to be resolved before merge,
    and a style remark is not worth that. A verdict of `issues` with no
    structured findings still gets one thread, because the model saw something
    and the summary is where it said what.
    """
    owner, name = repository.split("/", 1)
    actionable = actionable_findings(findings)
    unstructured = verdict == "issues" and not findings
    if not actionable and not unstructured:
        return "skipped: no critical or important findings"

    inline: list[dict[str, Any]] = []
    loose: list[str] = []
    for item in actionable:
        text = format_thread_body(item, head_sha=head_sha)
        location = parse_location(item.get("body") or "")
        if location and location[1] is not None:
            path, start_line, end_line = location
            comment: dict[str, Any] = {
                "path": path, "line": end_line or start_line, "side": "RIGHT", "body": text,
            }
            if end_line and start_line and end_line != start_line:
                comment["start_line"] = start_line
                comment["start_side"] = "RIGHT"
            inline.append(comment)
        else:
            loose.append(text)
    if unstructured:
        loose.append(
            f"{THREAD_MARKER}\n**Grok reported `issues` without structured "
            f"findings.** The summary comment carries what it said.\n\n"
            f"_Grok advisory review · `{head_sha[:9]}`_"
        )

    url = f"https://api.github.com/repos/{owner}/{name}/pulls/{pr_number}/reviews"
    separator = "\n\n---\n\n"
    payload = {
        "commit_id": head_sha,
        "event": "COMMENT",
        "body": separator.join(loose),
        "comments": inline,
    }
    try:
        requester("POST", url, token, payload)
        return f"posted {len(inline)} inline, {len(loose)} in body"
    except RuntimeError as error:
        # An inline comment on a line the diff does not touch is rejected as
        # 422. The finding is still worth reading, so fold every inline
        # comment into the review body with its location and post once more.
        if "422" not in str(error) or not inline:
            raise
        folded = [
            f"`{comment['path']}:{comment.get('start_line', comment['line'])}`"
            f"\n\n{comment['body']}"
            for comment in inline
        ]
        requester("POST", url, token, {
            "commit_id": head_sha,
            "event": "COMMENT",
            "body": separator.join(folded + loose),
            "comments": [],
        })
        return f"posted 0 inline, {len(folded) + len(loose)} in body after 422"


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
    parser.add_argument("--head-sha", default=os.environ.get("HEAD_SHA", ""))
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
    parser.add_argument("--structured-output", default="",
                        help="Read-only standalone mode: write model data and never post to GitHub")
    parser.add_argument("--post-comment", action="store_true", default=os.environ.get("POST_COMMENT", "true") == "true")
    parser.add_argument("--no-post-comment", action="store_false", dest="post_comment")
    parser.add_argument("--post-review", action="store_true", default=os.environ.get("POST_REVIEW", "true") == "true")
    parser.add_argument("--no-post-review", action="store_false", dest="post_review")
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
        if args.structured_output:
            raise RuntimeError(f"why: Grok did not review ({reason}); remedy: fix the cause or review manually")
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
    if args.structured_output:
        # The standalone model job has no PR write permission. A separate
        # trusted publisher validates these data and the current head.
        from pr_review_target import TargetUnavailable, validate_review
        if not text.strip() or (verdict == "issues" and not findings):
            raise TargetUnavailable("why: Grok returned no actionable structured review; remedy: rerun or review manually")
        inline = []
        for item in actionable_findings(findings):
            location = parse_location(item.get("body") or "")
            if not location or not location[1]:
                raise TargetUnavailable("why: Grok finding has no exact inline location; remedy: review manually")
            inline.append({"path": location[0], "line": location[2] or location[1],
                           "body": f"**[{item['severity']}] {item['title']}**\n\n{item['body']}"})
        data = validate_review({"summary": text, "findings": inline})
        Path(args.structured_output).write_text(json.dumps(data), encoding="utf-8")
        return 0
    token = os.environ.get("GITHUB_TOKEN", "")
    if args.post_review and token and args.repository and args.pr_number and args.head_sha:
        review_action = post_review(
            repository=args.repository,
            pr_number=int(args.pr_number),
            head_sha=args.head_sha,
            token=token,
            findings=findings,
            verdict=verdict,
        )
        notice(f"Grok advisory review threads {review_action}")
    elif args.post_review:
        notice(
            "Grok advisory review threads skipped: missing GITHUB_TOKEN, "
            "repository, PR number, or head SHA"
        )

    comment = format_comment(text=text, grok_payload=payload)
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
