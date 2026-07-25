#!/usr/bin/env python3
"""Plan one immutable staging product version and render its release notes."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


VERSION_RE = re.compile(
    r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
COMMIT_RE = re.compile(
    r"^(?P<kind>[a-z][a-z0-9-]*)"
    r"(?:\((?P<scope>[^()\r\n]+)\))?"
    r"(?P<breaking>!)?: (?P<description>.+)$"
)
PR_RE = re.compile(r"\s+\(#(?P<number>[1-9][0-9]*)\)$")
BREAKING_RE = re.compile(r"(?m)^BREAKING CHANGE:\s*\S")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

CATEGORY_ORDER = (
    "Features",
    "Fixes",
    "Performance",
    "Documentation",
    "Maintenance",
    "Other",
)
CATEGORIES = {
    "feat": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "docs": "Documentation",
    "refactor": "Maintenance",
    "test": "Maintenance",
    "build": "Maintenance",
    "ci": "Maintenance",
    "chore": "Maintenance",
    "style": "Maintenance",
}


class ReleaseError(RuntimeError):
    """Raised when Git history cannot produce one safe product release."""


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @property
    def tag(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    def bump_patch(self) -> "Version":
        return Version(self.major, self.minor, self.patch + 1)

    def bump_minor(self) -> "Version":
        return Version(self.major, self.minor + 1, 0)

    def bump_major(self) -> "Version":
        return Version(self.major + 1, 0, 0)


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str
    kind: str | None
    scope: str | None
    description: str
    breaking: bool
    pull_request: int | None


@dataclass(frozen=True)
class ReleasePlan:
    tag: str
    previous_tag: str | None
    existing: bool
    target_sha: str
    commits: tuple[Commit, ...]


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ReleaseError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def parse_version_tag(tag: str) -> Version | None:
    match = VERSION_RE.fullmatch(tag)
    if match is None:
        return None
    return Version(*(int(part) for part in match.groups()))


def parse_commit(sha: str, subject: str, body: str) -> Commit:
    pr_match = PR_RE.search(subject)
    pull_request = int(pr_match.group("number")) if pr_match else None
    conventional_subject = PR_RE.sub("", subject)
    commit_match = COMMIT_RE.fullmatch(conventional_subject)
    if commit_match is None:
        kind = None
        scope = None
        description = conventional_subject
        bang = False
    else:
        kind = commit_match.group("kind")
        scope = commit_match.group("scope")
        description = commit_match.group("description")
        bang = commit_match.group("breaking") == "!"
    return Commit(
        sha=sha,
        subject=subject,
        body=body,
        kind=kind,
        scope=scope,
        description=description,
        breaking=bang or BREAKING_RE.search(body) is not None,
        pull_request=pull_request,
    )


def _product_tags(repo: Path) -> list[tuple[Version, str, str]]:
    tags: list[tuple[Version, str, str]] = []
    for tag in _git(repo, "tag", "--list").splitlines():
        version = parse_version_tag(tag)
        if version is None:
            continue
        object_type = _git(repo, "cat-file", "-t", f"refs/tags/{tag}")
        if object_type != "tag":
            raise ReleaseError(f"product tag {tag} must be annotated")
        commit_sha = _git(repo, "rev-parse", f"{tag}^{{commit}}")
        tags.append((version, tag, commit_sha))
    return sorted(tags)


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _read_commits(
    repo: Path, target_sha: str, previous_tag: str | None
) -> tuple[Commit, ...]:
    revision = f"{previous_tag}..{target_sha}" if previous_tag else target_sha
    shas = _git(repo, "rev-list", "--reverse", revision).splitlines()
    commits: list[Commit] = []
    for sha in shas:
        raw = _git(repo, "show", "-s", "--format=%H%x00%s%x00%b", sha)
        commit_sha, subject, body = raw.split("\0", 2)
        commits.append(parse_commit(commit_sha, subject, body))
    return tuple(commits)


def _next_version(previous: Version, commits: tuple[Commit, ...]) -> Version:
    if not commits:
        raise ReleaseError("target has no commits after the latest product tag")
    if any(commit.breaking for commit in commits):
        return previous.bump_major()
    if any(commit.kind == "feat" for commit in commits):
        return previous.bump_minor()
    return previous.bump_patch()


def plan_release(repo: Path, target_sha: str) -> ReleasePlan:
    repo = repo.resolve()
    if SHA_RE.fullmatch(target_sha) is None:
        raise ReleaseError("target SHA must be 40 lowercase hexadecimal characters")
    resolved_target = _git(repo, "rev-parse", f"{target_sha}^{{commit}}")
    if resolved_target != target_sha:
        raise ReleaseError(f"target SHA does not resolve exactly: {target_sha}")

    tags = _product_tags(repo)
    target_tags = [
        (version, tag)
        for version, tag, commit_sha in tags
        if commit_sha == target_sha
    ]
    if len(target_tags) > 1:
        names = ", ".join(tag for _, tag in target_tags)
        raise ReleaseError(f"target SHA has multiple product tags: {names}")

    if target_tags:
        version, tag = target_tags[0]
        previous = [(item_version, item_tag) for item_version, item_tag, _ in tags
                    if item_version < version]
        previous_tag = max(previous)[1] if previous else None
        if previous_tag and not _is_ancestor(repo, previous_tag, target_sha):
            raise ReleaseError(
                f"previous product tag {previous_tag} is not an ancestor of {target_sha}"
            )
        return ReleasePlan(
            tag=tag,
            previous_tag=previous_tag,
            existing=True,
            target_sha=target_sha,
            commits=_read_commits(repo, target_sha, previous_tag),
        )

    if not tags:
        origin_main = _git(repo, "rev-parse", "refs/remotes/origin/main^{commit}")
        if origin_main != target_sha:
            raise ReleaseError(
                "initial release target must equal origin/main; "
                f"target={target_sha} origin/main={origin_main}"
            )
        return ReleasePlan(
            tag="v0.2.0",
            previous_tag=None,
            existing=False,
            target_sha=target_sha,
            commits=_read_commits(repo, target_sha, None),
        )

    previous_version, previous_tag, _ = tags[-1]
    if not _is_ancestor(repo, previous_tag, target_sha):
        raise ReleaseError(
            f"latest product tag {previous_tag} is not an ancestor of {target_sha}"
        )
    commits = _read_commits(repo, target_sha, previous_tag)
    next_version = _next_version(previous_version, commits)
    return ReleasePlan(
        tag=next_version.tag,
        previous_tag=previous_tag,
        existing=False,
        target_sha=target_sha,
        commits=commits,
    )


def _entry(commit: Commit, repository_url: str) -> str:
    label = f"**{commit.scope}:** " if commit.scope else ""
    breaking = "**BREAKING:** " if commit.breaking else ""
    commit_link = (
        f"[`{commit.sha[:8]}`]({repository_url}/commit/{commit.sha})"
    )
    links = [commit_link]
    if commit.pull_request is not None:
        links.append(
            f"[#{commit.pull_request}]"
            f"({repository_url}/pull/{commit.pull_request})"
        )
    return (
        f"- {breaking}{label}{commit.description} "
        f"({', '.join(links)})"
    )


def render_notes(
    plan: ReleasePlan,
    repository: str,
    run_url: str,
    deployed_at: str,
) -> str:
    if REPOSITORY_RE.fullmatch(repository) is None:
        raise ReleaseError("repository must use owner/name format")
    repository_url = f"https://github.com/{repository}"
    sections: dict[str, list[str]] = {category: [] for category in CATEGORY_ORDER}
    for commit in plan.commits:
        category = CATEGORIES.get(commit.kind or "", "Other")
        sections[category].append(_entry(commit, repository_url))

    lines = [
        f"# {plan.tag}",
        "",
        "- Environment: staging",
        f"- Commit: [`{plan.target_sha}`]"
        f"({repository_url}/commit/{plan.target_sha})",
        f"- Deployed at: {deployed_at}",
        f"- Workflow: [GitHub Actions run]({run_url})",
    ]
    for category in CATEGORY_ORDER:
        entries = sections[category]
        if not entries:
            continue
        lines.extend(("", f"## {category}", "", *entries))
    return "\n".join(lines) + "\n"


def _valid_utc_timestamp(value: str) -> bool:
    if not value.endswith("Z"):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan a staging product release and render its Changelog."
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--deployed-at", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)

    if not _valid_utc_timestamp(args.deployed_at):
        parser.error("--deployed-at must be UTC ISO 8601 like 2026-07-26T10:11:12Z")
    try:
        plan = plan_release(args.repo, args.target_sha)
        notes = render_notes(
            plan,
            repository=args.repository,
            run_url=args.run_url,
            deployed_at=args.deployed_at,
        )
    except ReleaseError as error:
        print(f"release planning failed: {error}", file=sys.stderr)
        return 1

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    notes_file = output_dir / f"CHANGELOG-{plan.tag}.md"
    notes_file.write_text(notes, encoding="utf-8")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"tag={plan.tag}\n")
            output.write(f"previous_tag={plan.previous_tag or ''}\n")
            output.write(f"existing={str(plan.existing).lower()}\n")
            output.write(f"notes_file={notes_file}\n")
    print(plan.tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
