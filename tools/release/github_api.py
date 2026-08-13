"""Read-only GitHub branch and Actions-run projections for release preparation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GitHubApiError(RuntimeError):
    """A GitHub read projection is unavailable or malformed."""


@dataclass(frozen=True)
class BranchProjection:
    name: str
    protected: bool
    commit_sha: str


@dataclass(frozen=True)
class RunProjection:
    id: int
    event: str
    head_sha: str
    status: str
    conclusion: str | None


Transport = Callable[[str], object]


class GitHubClient:
    """A minimal read-only REST client; release mutations belong to Task 3."""

    def __init__(self, *, transport: Transport | None = None) -> None:
        self._transport = transport or _get_json

    def get_branch(self, repository: str, branch: str) -> BranchProjection:
        document = self._get(f"/repos/{repository}/branches/{branch}")
        if not isinstance(document, dict):
            raise GitHubApiError("GitHub branch projection is invalid")
        commit = document.get("commit")
        name, protected = document.get("name"), document.get("protected")
        sha = commit.get("sha") if isinstance(commit, dict) else None
        if not isinstance(name, str) or not isinstance(protected, bool) or not _sha(sha):
            raise GitHubApiError("GitHub branch projection is invalid")
        return BranchProjection(name, protected, sha)

    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]:
        if not _sha(sha):
            raise GitHubApiError("GitHub run target is invalid")
        document = self._get(f"/repos/{repository}/actions/runs?{urlencode({'head_sha': sha, 'per_page': 100})}")
        runs = document.get("workflow_runs") if isinstance(document, dict) else None
        if not isinstance(runs, list):
            raise GitHubApiError("GitHub run projection is invalid")
        parsed: list[RunProjection] = []
        for run in runs:
            if not isinstance(run, dict):
                raise GitHubApiError("GitHub run projection is invalid")
            identifier, event, head_sha, status, conclusion = (
                run.get("id"), run.get("event"), run.get("head_sha"), run.get("status"), run.get("conclusion"),
            )
            if (
                type(identifier) is not int or identifier <= 0 or not isinstance(event, str)
                or not _sha(head_sha) or not isinstance(status, str)
                or (conclusion is not None and not isinstance(conclusion, str))
            ):
                raise GitHubApiError("GitHub run projection is invalid")
            parsed.append(RunProjection(identifier, event, head_sha, status, conclusion))
        return parsed

    def _get(self, path: str) -> object:
        try:
            return self._transport(path)
        except GitHubApiError:
            raise
        except Exception:
            raise GitHubApiError("GitHub release preflight is unavailable") from None


def _get_json(path: str) -> object:
    request = Request(
        f"https://api.github.com{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "lmdj-release-prepare"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except Exception:
        raise GitHubApiError("GitHub release preflight is unavailable") from None


def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)
