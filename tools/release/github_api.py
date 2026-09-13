"""Typed, secret-safe GitHub REST projections used by release tooling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import io
import json
import os
import re
from typing import Any, Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from .self_test_protocol import protocol as self_test


class GitHubApiError(RuntimeError):
    """A GitHub release projection or request is unavailable or malformed."""


def valid_release_pr_document(document) -> bool:
    """Pure POST preflight shared by the producer and the actual transport."""
    return _valid_task_pr_document(document, r"docs/release-evidence-[0-9a-f]{64}")


def valid_candidate_pr_document(document) -> bool:
    """Same bounded document contract, with a disjoint candidate branch scope."""
    return _valid_task_pr_document(document, r"feat/release-candidate-[0-9a-f]{64}")


def valid_witness_pr_document(document) -> bool:
    """Witness-only follow-up; never reuse allocation/publication branches."""
    return _valid_task_pr_document(document, r"docs/release-witness-[0-9a-f]{64}")


def _valid_task_pr_document(document, branch) -> bool:
    return (type(document) is dict
            and set(document) == {"title", "body", "head", "base", "draft", "maintainer_can_modify"}
            and type(document.get("head")) is str
            and re.fullmatch(branch, document["head"]) is not None
            and document.get("base") == "main" and document.get("draft") is False
            and document.get("maintainer_can_modify") is False
            and all(type(document.get(k)) is str and 0 < len(document[k]) <= 20000
                    for k in ("title", "body")))


class CiScopeUnavailableError(GitHubApiError):
    """The exact run retains no readable scope manifest for its head SHA.

    Actions artifacts expire, so absence is an evidence-lifetime fact rather
    than a conflict: callers classify it as unverifiable, never as a pass.
    """


class CiScopeConflictError(GitHubApiError):
    """A retained scope manifest exists but its identity or content conflicts."""


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
    head_branch: str
    workflow_name: str
    status: str
    conclusion: str | None


@dataclass(frozen=True)
class SelfTestRunProjection(RunProjection):
    """Stable workflow identity resolved independently of dynamic run.name."""
    run_attempt: int
    repository_id: int = 0


@dataclass(frozen=True)
class WorkflowRunProjection:
    """One run addressed by numeric ID, bound to its workflow file path."""
    id: int
    event: str
    head_sha: str
    head_branch: str
    path: str
    status: str
    conclusion: str | None


@dataclass(frozen=True)
class RunJobProjection:
    id: int
    run_id: int
    name: str
    status: str
    conclusion: str | None
    workflow_name: str
    head_sha: str


@dataclass(frozen=True)
class ActionsArtifactProjection:
    id: int
    name: str
    size_in_bytes: int
    api_url: str
    archive_download_url: str
    expired: bool
    run_id: int
    repository_id: int
    head_repository_id: int
    head_branch: str
    head_sha: str
    expires_at: str


@dataclass(frozen=True)
class CiScopeProjection:
    schema: str
    base_sha: str
    head_sha: str
    mode: str
    trusted_head: bool
    selected_lanes: tuple[str, ...]
    required_jobs: tuple[str, ...]


@dataclass(frozen=True)
class GitHubAsset:
    id: int
    name: str
    size: int
    api_url: str
    browser_download_url: str
    release_id: int
    label: str | None
    content_type: str
    state: str


@dataclass(frozen=True)
class DeploymentBranchPolicy:
    id: int
    name: str
    type: str


@dataclass(frozen=True)
class GitHubEnvironment:
    name: str
    required_reviewer_count: int
    prevent_self_review: bool | None
    protected_branches: bool
    custom_branch_policies: bool
    branch_policies: tuple[DeploymentBranchPolicy, ...]


@dataclass(frozen=True)
class GitHubRelease:
    id: int
    tag_name: str
    name: str
    body: str
    draft: bool
    prerelease: bool
    make_latest: bool | None
    html_url: str
    upload_url: str
    assets: tuple[GitHubAsset, ...]
    target_commitish: str
    published_at: str | None = None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


HttpTransport = Callable[[str, str, Mapping[str, str], bytes | None], HttpResponse]

_CI_SCOPE_ARTIFACT_PREFIX = "ci-scope-"
_CI_SCOPE_MEMBER = "ci-scope.json"
_CI_SCOPE_SCHEMA = "lmdj.ci-scope.v2"
_CI_SCOPE_SIZE_CAP = 1024 * 1024
_CI_SCOPE_MODES = frozenset(("draft", "focused", "full", "requested"))
_CI_SCOPE_KEYS = frozenset((
    "schema", "base_sha", "head_sha", "mode", "reasons", "changed_files",
    "lanes", "required_jobs", "trusted_head",
))
# The closed v2 lane set is restated here on purpose. Release authority must be
# able to reject a manifest that claims `full` while carrying a different lane
# inventory, and it must do so without reading CI's own policy file, which is
# exactly the document an attacker or a mistake would change alongside it.
CI_SCOPE_LANES = frozenset((
    "docs_static", "portal", "ci_contract", "core_ubuntu", "core_asan",
    "core_coverage", "core_macos", "web_toolchain", "web_runtime_host",
    "creator", "web_runtime_lab", "deploy_contract", "chameleon_lab", "package",
))
# GitHub redirects an authenticated artifact download to this closed Azure
# storage host family with a signed query. Anything else fails closed rather
# than being followed with or without credentials.
_ARTIFACT_REDIRECT_HOST = re.compile(
    r"productionresultssa[0-9]+\.blob\.core\.windows\.net"
)


class GitHubClient:
    """Small typed REST client with exact mutation and complete pagination APIs."""

    def __init__(
        self,
        *,
        http_transport: HttpTransport | None = None,
        token: str | None = None,
        page_cap: int = 100,
    ) -> None:
        self._http_transport = http_transport or _http_request
        self._token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        if type(page_cap) is not int or page_cap <= 0:
            raise GitHubApiError("GitHub pagination page cap is invalid")
        self._page_cap = page_cap

    def get_branch(self, repository: str, branch: str) -> BranchProjection:
        _require_repository(repository)
        if not isinstance(branch, str) or not branch:
            raise GitHubApiError("GitHub branch identity is invalid")
        response = self._request(
            "GET", f"/repos/{repository}/branches/{quote(branch, safe='')}",
        )
        document = _json_response(response, {200})
        if not isinstance(document, dict):
            raise GitHubApiError("GitHub branch projection is invalid")
        commit = document.get("commit")
        name, protected = document.get("name"), document.get("protected")
        sha = commit.get("sha") if isinstance(commit, dict) else None
        if not isinstance(name, str) or not isinstance(protected, bool) or not _sha(sha):
            raise GitHubApiError("GitHub branch projection is invalid")
        return BranchProjection(name, protected, sha)

    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]:
        _require_repository(repository)
        if not _sha(sha):
            raise GitHubApiError("GitHub run target is invalid")
        endpoint = f"/repos/{repository}/actions/runs"
        required_query = {"head_sha": sha, "per_page": "100"}
        next_path: str | None = f"{endpoint}?{urlencode(required_query)}"
        visited: set[str] = set()
        raw_runs: list[object] = []
        parsed: list[RunProjection] = []
        workflows: dict[int, tuple[str, str]] = {}
        total_count: int | None = None
        while next_path is not None:
            if next_path in visited or len(visited) >= self._page_cap:
                raise GitHubApiError("GitHub run pagination is invalid")
            visited.add(next_path)
            response = self._request("GET", next_path)
            document = _json_response(response, {200})
            runs = document.get("workflow_runs") if isinstance(document, dict) else None
            page_total = document.get("total_count") if isinstance(document, dict) else None
            if not isinstance(runs, list) or type(page_total) is not int or page_total < 0:
                raise GitHubApiError("GitHub run projection is invalid")
            if total_count is None:
                total_count = page_total
            elif page_total != total_count:
                raise GitHubApiError("GitHub run pagination is invalid")
            raw_runs.extend(runs)
            next_path = _next_link(
                response.headers, endpoint, required_query, subject="run",
            )
        if total_count != len(raw_runs):
            raise GitHubApiError("GitHub run pagination is incomplete")
        for run in raw_runs:
            if not _is_workflow_file_run(run):
                continue
            workflow_id, workflow_path = _run_workflow_reference(run)
            cached = workflows.get(workflow_id)
            if cached is None:
                workflow_name = self._get_workflow_name(
                    repository, workflow_id, workflow_path,
                )
                workflows[workflow_id] = (workflow_path, workflow_name)
            else:
                cached_path, workflow_name = cached
                if cached_path != workflow_path:
                    raise GitHubApiError("GitHub run workflow identity is invalid")
            parsed.append(_parse_run(run, workflow_name))
        identifiers = [run.id for run in parsed]
        if len(identifiers) != len(set(identifiers)):
            raise GitHubApiError("GitHub run pagination returned duplicate IDs")
        return parsed

    def _get_workflow_name(
        self, repository: str, workflow_id: int, expected_path: str,
    ) -> str:
        response = self._request(
            "GET", f"/repos/{repository}/actions/workflows/{workflow_id}",
        )
        document = _json_response(response, {200})
        if not isinstance(document, dict):
            raise GitHubApiError("GitHub workflow projection is invalid")
        identifier, name, path = (
            document.get("id"), document.get("name"), document.get("path"),
        )
        if (
            identifier != workflow_id or not isinstance(name, str) or not name
            or path != expected_path
        ):
            raise GitHubApiError("GitHub run workflow identity is invalid")
        return name

    def get_self_test_run(self, repository: str, run_id: int, *, run_attempt: int | None = None) -> SelfTestRunProjection:
        _require_repository(repository)
        _require_id(run_id, "run")
        endpoint = f"/repos/{repository}/actions/runs/{run_id}"
        if run_attempt is not None:
            _require_id(run_attempt, "attempt")
            endpoint += f"/attempts/{run_attempt}"
        document = _json_response(self._request("GET", endpoint), {200})
        if not isinstance(document, dict):
            raise GitHubApiError("self-test run projection is malformed")
        workflow_id, path = _run_workflow_reference(document)
        if path != ".github/workflows/ci.yml":
            raise CiScopeConflictError("self-test run is from another workflow path")
        # A second stable lookup prevents accepting a retired/replaced workflow
        # ID merely because a run self-identifies with the expected file path.
        workflow = _json_response(self._request("GET", f"/repos/{repository}/actions/workflows/ci.yml"), {200})
        if not isinstance(workflow, dict) or workflow.get("id") != workflow_id or workflow.get("path") != path or workflow.get("name") != "Core CI":
            raise CiScopeConflictError("self-test stable workflow identity conflicts")
        repo, head_repo = document.get("repository"), document.get("head_repository")
        if (not isinstance(repo, dict) or not isinstance(head_repo, dict)
                or repo.get("full_name") != repository or head_repo.get("full_name") != repository
                or not _positive_id(repo.get("id")) or repo["id"] != head_repo.get("id")):
            raise CiScopeConflictError("self-test run is not from the canonical repository")
        parsed = _parse_run(document, workflow["name"])
        attempt = document.get("run_attempt")
        if parsed.id != run_id or not _positive_id(attempt) or (run_attempt is not None and attempt != run_attempt):
            raise CiScopeConflictError("self-test run/attempt identity conflicts")
        return SelfTestRunProjection(**parsed.__dict__, run_attempt=attempt, repository_id=repo["id"])

    def verify_self_test_provenance(self, repository: str, run: SelfTestRunProjection, target_revision: str) -> str:
        """Both control and target must be in main; target need not equal control."""
        _require_repository(repository)
        if not _sha(target_revision):
            raise CiScopeConflictError("self-test target is not an exact SHA")
        main = self.get_branch(repository, "main")
        if main.name != "main" or not main.protected:
            raise CiScopeConflictError("self-test authority is not protected main")
        # PR #757 introduced the trusted producer. Pre-deployment code cannot
        # mint new evidence, even if an old control is rerun at a later date.
        producer = "22247897e9163a3f34e15f564bec133419d1f177"
        for base, head, subject in ((producer, run.head_sha, "control predates or diverges from trusted producer"),
                                    (run.head_sha, main.commit_sha, "control is outside main history"),
                                    (target_revision, main.commit_sha, "target is outside main history")):
            document = _json_response(self._request("GET", f"/repos/{repository}/compare/{base}...{head}"), {200})
            if not isinstance(document, dict) or document.get("status") not in ("ahead", "identical"):
                raise CiScopeConflictError(f"self-test ancestry conflicts: {subject}")
        return main.commit_sha

    def get_self_test_policy(self, repository: str, revision: str):
        _require_repository(repository)
        if revision != "main" and not _sha(revision):
            raise GitHubApiError("self-test policy revision is invalid")
        document = _json_response(self._request("GET", f"/repos/{repository}/contents/scripts/ci/self_test_policy.json?{urlencode({'ref': revision})}"), {200})
        try:
            if not isinstance(document, dict) or document.get("type") != "file" or document.get("encoding") != "base64" or document.get("path") != "scripts/ci/self_test_policy.json":
                raise ValueError("invalid policy projection")
            encoded = document["content"]
            if not isinstance(encoded, str) or len(encoded) > _CI_SCOPE_SIZE_CAP:
                raise ValueError("invalid policy size")
            payload = base64.b64decode("".join(encoded.split()), validate=True)
            return self_test.parse_policy(json.loads(payload, object_pairs_hook=_reject_duplicate_keys))
        except (ValueError, KeyError, TypeError):
            raise CiScopeConflictError("trusted self-test policy document is malformed") from None

    def get_self_test_verdict(self, repository: str, run: SelfTestRunProjection, target_revision: str) -> dict:
        _require_repository(repository)
        if not _sha(target_revision):
            raise CiScopeConflictError("self-test target is not an exact SHA")
        jobs = self.list_run_jobs(repository, run.id, run_attempt=run.run_attempt)
        selected = [job for job in jobs if job.name == "Self-test verdict"]
        if (len(selected) != 1 or selected[0].status != "completed" or selected[0].conclusion != "success"
                or any(job.run_id != run.id or job.head_sha != run.head_sha for job in jobs)):
            raise CiScopeConflictError("self-test verdict job did not succeed in this exact attempt")
        name = f"self-test-verdict-{target_revision}-{run.id}-{run.run_attempt}"
        matching = [a for a in self.list_run_artifacts(repository, run.id) if a.name == name]
        if not matching:
            raise CiScopeUnavailableError("self-test verdict artifact is absent")
        if len(matching) != 1:
            raise CiScopeConflictError("self-test verdict artifacts are ambiguous")
        artifact = matching[0]
        try:
            expires = datetime.strptime(artifact.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            raise CiScopeConflictError("self-test artifact retention timestamp is invalid") from None
        if artifact.expired or expires <= datetime.now(timezone.utc):
            raise CiScopeUnavailableError("self-test verdict artifact expired")
        if (artifact.run_id != run.id or artifact.head_sha != run.head_sha or artifact.head_branch != run.head_branch
                or artifact.repository_id != run.repository_id or artifact.head_repository_id != run.repository_id
                or artifact.size_in_bytes > _CI_SCOPE_SIZE_CAP):
            raise CiScopeConflictError("self-test artifact control/repository identity conflicts")
        try:
            with zipfile.ZipFile(io.BytesIO(self._download_artifact(artifact))) as archive:
                members = archive.infolist()
                if len(members) != 1 or members[0].filename != "verdict.json" or members[0].is_dir() or members[0].file_size > _CI_SCOPE_SIZE_CAP:
                    raise ValueError("invalid verdict archive")
                document = json.loads(archive.read(members[0]), object_pairs_hook=_reject_duplicate_keys)
            if not isinstance(document, dict):
                raise ValueError("invalid verdict JSON")
            return document
        except (ValueError, OSError, RuntimeError, zipfile.BadZipFile):
            raise CiScopeConflictError("self-test verdict archive is malformed") from None

    def list_run_jobs(self, repository: str, run_id: int, *, run_attempt: int | None = None) -> list[RunJobProjection]:
        """Return every latest-attempt job of one run bound to that run's identity."""
        _require_repository(repository)
        _require_id(run_id, "run")
        endpoint = f"/repos/{repository}/actions/runs/{run_id}/jobs"
        if run_attempt is not None:
            _require_id(run_attempt, "attempt")
            endpoint = f"/repos/{repository}/actions/runs/{run_id}/attempts/{run_attempt}/jobs"
        required_query = {"per_page": "100"} if run_attempt is not None else {"filter": "latest", "per_page": "100"}
        next_path: str | None = f"{endpoint}?{urlencode(required_query)}"
        visited: set[str] = set()
        jobs: list[RunJobProjection] = []
        total_count: int | None = None
        while next_path is not None:
            if next_path in visited or len(visited) >= self._page_cap:
                raise GitHubApiError("GitHub run job pagination is invalid")
            visited.add(next_path)
            response = self._request("GET", next_path)
            document = _json_response(response, {200})
            items = document.get("jobs") if isinstance(document, dict) else None
            page_total = document.get("total_count") if isinstance(document, dict) else None
            if not isinstance(items, list) or type(page_total) is not int or page_total < 0:
                raise GitHubApiError("GitHub run job projection is invalid")
            if total_count is None:
                total_count = page_total
            elif page_total != total_count:
                raise GitHubApiError("GitHub run job pagination is invalid")
            jobs.extend(_parse_run_job(item, run_id) for item in items)
            next_path = _next_link(
                response.headers, endpoint, required_query, subject="run job",
            )
        identifiers = [job.id for job in jobs]
        if len(identifiers) != len(set(identifiers)):
            raise GitHubApiError("GitHub run job pagination returned duplicate IDs")
        if total_count != len(jobs):
            raise GitHubApiError("GitHub run job pagination is incomplete")
        return jobs

    def list_run_artifacts(
        self, repository: str, run_id: int,
    ) -> list[ActionsArtifactProjection]:
        """Return every artifact of one run with its embedded run identity bound."""
        _require_repository(repository)
        _require_id(run_id, "run")
        endpoint = f"/repos/{repository}/actions/runs/{run_id}/artifacts"
        required_query = {"per_page": "100"}
        next_path: str | None = f"{endpoint}?{urlencode(required_query)}"
        visited: set[str] = set()
        artifacts: list[ActionsArtifactProjection] = []
        total_count: int | None = None
        while next_path is not None:
            if next_path in visited or len(visited) >= self._page_cap:
                raise GitHubApiError("GitHub artifact pagination is invalid")
            visited.add(next_path)
            response = self._request("GET", next_path)
            document = _json_response(response, {200})
            items = document.get("artifacts") if isinstance(document, dict) else None
            page_total = document.get("total_count") if isinstance(document, dict) else None
            if not isinstance(items, list) or type(page_total) is not int or page_total < 0:
                raise GitHubApiError("GitHub artifact projection is invalid")
            if total_count is None:
                total_count = page_total
            elif page_total != total_count:
                raise GitHubApiError("GitHub artifact pagination is invalid")
            artifacts.extend(
                _parse_artifact(item, repository, run_id) for item in items
            )
            next_path = _next_link(
                response.headers, endpoint, required_query, subject="artifact",
            )
        identifiers = [artifact.id for artifact in artifacts]
        if len(identifiers) != len(set(identifiers)):
            raise GitHubApiError("GitHub artifact pagination returned duplicate IDs")
        if total_count != len(artifacts):
            raise GitHubApiError("GitHub artifact pagination is incomplete")
        return artifacts

    def get_ci_scope_manifest(
        self, repository: str, run: RunProjection,
    ) -> CiScopeProjection:
        """Project the one retained scope manifest of an exact run's head SHA."""
        _require_repository(repository)
        if not isinstance(run, RunProjection) or not _sha(run.head_sha):
            raise GitHubApiError("GitHub run projection is invalid")
        artifacts = self.list_run_artifacts(repository, run.id)
        expected = f"{_CI_SCOPE_ARTIFACT_PREFIX}{run.head_sha}"
        matching = [artifact for artifact in artifacts if artifact.name == expected]
        if len(matching) > 1:
            raise CiScopeConflictError("retained CI scope evidence is ambiguous")
        if not matching:
            raise CiScopeUnavailableError("retained CI scope evidence is absent")
        artifact = matching[0]
        if artifact.expired:
            raise CiScopeUnavailableError("retained CI scope evidence has expired")
        if (
            artifact.run_id != run.id or artifact.head_sha != run.head_sha
            or artifact.head_branch != run.head_branch
            or artifact.repository_id != artifact.head_repository_id
        ):
            raise CiScopeConflictError("retained CI scope evidence identity conflicts")
        if artifact.size_in_bytes > _CI_SCOPE_SIZE_CAP:
            raise CiScopeConflictError("retained CI scope evidence exceeds its size cap")
        return _parse_ci_scope(self._download_artifact(artifact))

    def get_run(self, repository: str, run_id: int) -> WorkflowRunProjection:
        """Project one run by numeric ID with its workflow path as identity."""
        _require_repository(repository)
        _require_id(run_id, "run")
        response = self._request("GET", f"/repos/{repository}/actions/runs/{run_id}")
        document = _json_response(response, {200})
        if not isinstance(document, dict):
            raise GitHubApiError("GitHub run projection is invalid")
        identifier, event, head_sha, head_branch, path, status, conclusion = (
            document.get("id"), document.get("event"), document.get("head_sha"),
            document.get("head_branch"), document.get("path"), document.get("status"),
            document.get("conclusion"),
        )
        if (
            identifier != run_id or not isinstance(event, str) or not event
            or not _sha(head_sha) or not isinstance(head_branch, str) or not head_branch
            or not isinstance(path, str) or not path.startswith(".github/workflows/")
            or not isinstance(status, str) or not status
            or (conclusion is not None and not isinstance(conclusion, str))
        ):
            raise GitHubApiError("GitHub run projection is invalid")
        return WorkflowRunProjection(run_id, event, head_sha, head_branch, path, status, conclusion)

    def get_run_artifact_member(
        self, repository: str, run_id: int, artifact_name: str, member: str, *, size_cap: int,
    ) -> bytes:
        """Return one named file from one exactly-named, unexpired artifact of a run."""
        _require_repository(repository)
        _require_id(run_id, "run")
        if not artifact_name or not member or "/" in member or member.startswith("."):
            raise GitHubApiError("GitHub artifact member selection is invalid")
        matching = [a for a in self.list_run_artifacts(repository, run_id) if a.name == artifact_name]
        if len(matching) > 1:
            raise GitHubApiError("retained run artifact is ambiguous")
        if not matching:
            raise GitHubApiError("retained run artifact is absent")
        artifact = matching[0]
        if artifact.expired:
            raise GitHubApiError("retained run artifact has expired")
        if artifact.run_id != run_id or artifact.repository_id != artifact.head_repository_id:
            raise GitHubApiError("retained run artifact identity conflicts")
        if artifact.size_in_bytes > size_cap:
            raise GitHubApiError("retained run artifact exceeds its size cap")
        payload = self._download_artifact(artifact)
        if not isinstance(payload, (bytes, bytearray)):
            raise GitHubApiError("GitHub artifact download is invalid")
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = [info.filename for info in archive.infolist() if not info.is_dir()]
                if names.count(member) != 1:
                    raise GitHubApiError(f"retained run artifact does not contain exactly one {member}")
                info = archive.getinfo(member)
                if info.file_size > size_cap:
                    raise GitHubApiError("retained run artifact member exceeds its size cap")
                return archive.read(member)
        except (zipfile.BadZipFile, OSError, ValueError, RuntimeError):
            raise GitHubApiError("retained run artifact archive is unreadable") from None

    def _download_artifact(self, artifact: ActionsArtifactProjection) -> bytes:
        """Download one artifact archive without forwarding credentials onward."""
        return self._download_artifact_archive(artifact.archive_download_url, _CI_SCOPE_SIZE_CAP)

    def get_release_review_page(self, number, kind, cursor=None, thread_id=None) -> object:
        """Fixed read-only GraphQL inventory queries; no caller query/mutation."""
        from .review_inventory import query_document
        document = query_document(number, kind, cursor, thread_id)
        response = self._request("POST", "/graphql", json.dumps(document).encode("utf-8"),
                                 content_type="application/json")
        if len(response.body) > 16 * 1024 * 1024:
            raise GitHubApiError("GitHub release review page exceeds read limit")
        value = _json_response(response, {200})
        # A duplicated JSON identity must not silently become last-key-wins.
        def unique(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise GitHubApiError("GitHub release review page has duplicate JSON fields")
                result[key] = item
            return result
        json.loads(response.body, object_pairs_hook=unique)
        return value

    def release_pr_request(self, method: str, suffix: str, document=None) -> object:
        """Narrow evidence-PR transport; no admin, auto-merge or branch writes."""
        return self._task_pr_request(method, suffix, document, r"docs/release-evidence-[0-9a-f]{64}")

    def candidate_pr_request(self, method: str, suffix: str, document=None) -> object:
        """Candidate-only PR routes; publication branch scope stays unchanged."""
        return self._task_pr_request(method, suffix, document, r"feat/release-candidate-[0-9a-f]{64}")

    def witness_pr_request(self, method: str, suffix: str, document=None) -> object:
        """Closed witness PR routes; no new kind of mutation is authorized."""
        return self._task_pr_request(method, suffix, document, r"docs/release-witness-[0-9a-f]{64}")

    def _task_pr_request(self, method, suffix, document, branch):
        if type(method) is not str or type(suffix) is not str:
            raise GitHubApiError("why: release PR request identity is invalid; remedy: use the exact evidence PR controller")
        number = r"[1-9][0-9]*"
        page = r"(?:[1-9]|[1-9][0-9]|100)"
        valid = False
        if method == "GET" and document is None:
            valid = (suffix in ("", "/branches/main", "/user")
                     or re.fullmatch(rf"/git/ref/heads/{branch}", suffix)
                     or re.fullmatch(rf"/pulls/{number}", suffix)
                     or re.fullmatch(rf"/pulls\?state=all&head=endaye:{branch}&base=main&per_page=100&page={page}", suffix))
        elif method == "POST" and suffix == "/pulls" and type(document) is dict:
            valid = _valid_task_pr_document(document, branch)
        elif method == "PUT" and re.fullmatch(rf"/pulls/{number}/merge", suffix) and type(document) is dict:
            valid = set(document) == {"sha", "merge_method"} and _sha(document.get("sha")) and document.get("merge_method") == "squash"
        if not valid:
            raise GitHubApiError("why: release PR route or mutation is outside the closed interface; remedy: use the exact evidence PR controller")
        url = "/user" if suffix == "/user" else "/repos/endaye/lmdj" + suffix
        response = self._request(method, url, None if document is None else json.dumps(document).encode(),
                                 content_type=None if document is None else "application/json")
        return _json_response(response, {201} if method == "POST" else {200})

    def dispatch_release(self, spec, *, before_post):
        """One exact main dispatch, called only after durable intent persistence.

        No retry, run-name correlation or ACK-as-completion. Main may advance
        after this read: the receipt consumer refuses a different control SHA.
        Publication/deployment workflows retain their own protected gates.
        """
        from .durable_dispatch import validate_spec
        validate_spec(spec)
        if not callable(before_post):
            raise GitHubApiError("why: dispatch write guard is missing; remedy: use the durable controller")
        workflow,inputs,repository_id,actor_id,workflow_id,control_revision=(spec[key] for key in
            ("workflow","inputs","repository_id","actor_id","workflow_id","control_revision"))
        prefix="/repos/endaye/lmdj"
        actor=_json_response(self._request("GET","/user"),{200})
        repo=_json_response(self._request("GET",prefix),{200})
        selected=_json_response(self._request("GET",prefix+"/actions/workflows/"+workflow),{200})
        main=_json_response(self._request("GET",prefix+"/branches/main"),{200})
        if not (type(actor) is dict and type(actor.get("id")) is int and actor["id"]==actor_id
                and type(repo) is dict and type(repo.get("id")) is int and repo["id"]==repository_id and repo.get("full_name")=="endaye/lmdj"
                and type(selected) is dict and type(selected.get("id")) is int and selected["id"]==workflow_id
                and selected.get("path")==".github/workflows/"+workflow and selected.get("state")=="active"
                and type(main) is dict and main.get("name")=="main" and main.get("protected") is True
                and type(main.get("commit")) is dict and main["commit"].get("sha")==control_revision):
            raise GitHubApiError("why: dispatch actor, workflow or main scope changed; remedy: reconcile the original operation without retry")
        before_post()
        response=self._request("POST",prefix+"/actions/workflows/"+workflow+"/dispatches",
                               json.dumps({"ref":"main","inputs":inputs}).encode(),content_type="application/json")
        if response.status != 204:
            raise GitHubApiError("why: dispatch result is unconfirmed; remedy: reconcile the original durable intent without another POST")

    def get_dispatch_evidence(self, path: str, *, raw: bool = False) -> object:
        """GET-only exact-run release correlation; no dispatch route."""
        prefix = "/repos/endaye/lmdj"
        if type(path) is not str or not path.startswith(prefix) or type(raw) is not bool:
            raise GitHubApiError("why: dispatch evidence route is not canonical; remedy: use the closed exact-run reader")
        suffix = path[len(prefix):]
        identifier, page = r"[1-9][0-9]*", r"(?:[1-9]|[1-9][0-9]|100)"
        if raw:
            if re.fullmatch(rf"/actions/artifacts/{identifier}/zip", suffix) is None:
                raise GitHubApiError("why: dispatch archive route is invalid; remedy: select the authenticated numeric artifact")
            return self._download_artifact_archive(path, 2 * 1024 * 1024)
        workflows = ("publish-release.yml", "deploy-web-runtime-host.yml", "deploy-creator-web.yml")
        if not (suffix == "/branches/main" or suffix in ("/actions/workflows/"+w for w in workflows)
                or any(re.fullmatch(rf"/actions/workflows/{re.escape(w)}/runs\?per_page=100&page={page}", suffix) for w in workflows)
                or re.fullmatch(rf"/actions/runs/{identifier}(?:/attempts/1)?", suffix)
                or re.fullmatch(rf"/actions/runs/{identifier}/(?:attempts/1/jobs|artifacts)\?per_page=100&page={page}", suffix)):
            raise GitHubApiError("why: dispatch JSON route is outside the allowlist; remedy: use the exact first-attempt read interface")
        return _json_response(self._request("GET", path), {200})

    def get_changelog_site_evidence(self, path: str, *, raw: bool = False) -> object:
        """Closed read-only transport for exact Portal deployment evidence."""
        prefix = "/repos/endaye/lmdj"
        if type(path) is not str or not path.startswith(prefix) or type(raw) is not bool:
            raise GitHubApiError("why: Portal evidence route is not canonical; remedy: use the exact read-only consumer")
        suffix = path[len(prefix):]
        identifier = r"[1-9][0-9]*"
        page = r"(?:[1-9]|[1-9][0-9]|100)"
        if raw:
            if re.fullmatch(rf"/actions/artifacts/{identifier}/zip", suffix) is None:
                raise GitHubApiError("why: Portal archive route is invalid; remedy: select the authenticated numeric artifact")
            return self._download_artifact_archive(path, 2 * 1024 * 1024)
        if not (suffix in ("/branches/main", "/actions/workflows/deploy-cloudflare-portal.yml")
                or re.fullmatch(rf"/actions/runs/{identifier}(?:/attempts/1)?", suffix)
                or re.fullmatch(rf"/actions/runs/{identifier}/(?:attempts/1/jobs|artifacts)\?per_page=100&page={page}", suffix)):
            raise GitHubApiError("why: Portal JSON route is outside the allowlist; remedy: use exact run, first attempt and bounded inventories")
        return _json_response(self._request("GET", path), {200})

    def get_batch_evidence(self, path: str, *, raw: bool = False) -> object:
        """Closed GET-only transport for the inactive full-batch consumer.

        No consumer import: orchestration owns this callback, avoiding a
        github_api -> batch_evidence -> github_api dependency cycle.
        """
        prefix = "/repos/endaye/lmdj"
        if not isinstance(path, str) or not path.startswith(prefix) or type(raw) is not bool:
            raise CiScopeConflictError("why: batch evidence route is not canonical; remedy: use the closed read-only candidate consumer")
        suffix = path[len(prefix):]
        identifier = r"[1-9][0-9]*"
        page = r"(?:[1-9]|[1-9][0-9]|100)"
        if raw:
            if re.fullmatch(rf"/actions/artifacts/{identifier}/zip", suffix) is None:
                raise CiScopeConflictError("why: raw batch route is not an exact artifact ZIP; remedy: download only the authenticated artifact ID")
            # Three individually bounded files, not the legacy one-file cap.
            from .batch_reference import MAX_DOCUMENT
            return self._download_artifact_archive(path, 3 * MAX_DOCUMENT)
        allowed = (suffix in ("/branches/main", "/actions/workflows/self-test-report.yml")
                   or re.fullmatch(rf"/actions/runs/{identifier}(?:/attempts/1)?", suffix)
                   or re.fullmatch(rf"/actions/runs/{identifier}/(?:attempts/1/jobs|artifacts)\?per_page=100&page={page}", suffix))
        if not allowed:
            raise CiScopeConflictError("why: batch JSON route is outside the evidence allowlist; remedy: use exact run/attempt and bounded inventory pages")
        return _json_response(self._request("GET", path), {200})

    def _download_artifact_archive(self, url: str, size_cap: int) -> bytes:
        """Shared transfer policy; callers own independently checked identity."""
        response = self._request(
            "GET", url, accept="application/vnd.github+json",
        )
        if response.status in (302, 307):
            location = _header(response.headers, "location")
            if not _trusted_artifact_redirect(location):
                # The signed URL is never echoed: it is a bearer credential.
                raise CiScopeConflictError("GitHub artifact redirect is not trusted")
            try:
                response = self._http_transport("GET", location, {
                    "Accept": "application/zip",
                    "User-Agent": "lmdj-release-pipeline",
                }, None)
            except Exception:
                raise GitHubApiError("GitHub artifact download is unavailable") from None
            if not isinstance(response, HttpResponse):
                raise GitHubApiError("GitHub release response is invalid")
        if response.status != 200:
            raise GitHubApiError("GitHub artifact download is unavailable")
        content_type = _header(response.headers, "content-type")
        if content_type is None or content_type.split(";", 1)[0].strip() != "application/zip":
            raise CiScopeConflictError("GitHub artifact content type is invalid")
        payload = response.body
        if not isinstance(payload, bytes) or len(payload) > size_cap:
            raise CiScopeConflictError("GitHub artifact archive exceeds its size cap")
        if not payload.startswith(b"PK\x03\x04"):
            raise CiScopeConflictError("GitHub artifact archive is not a ZIP archive")
        return payload

    def get_release_by_tag(self, repository: str, tag: str) -> GitHubRelease | None:
        """Find a published Release or Draft through the complete authenticated inventory."""
        _require_repository(repository)
        if not isinstance(tag, str) or not tag:
            raise GitHubApiError("GitHub release tag is invalid")
        matches = [release for release in self.list_releases(repository) if release.tag_name == tag]
        if len(matches) > 1:
            raise GitHubApiError("GitHub Release inventory is ambiguous")
        return matches[0] if matches else None

    def get_release(self, repository: str, release_id: int) -> GitHubRelease | None:
        _require_repository(repository)
        _require_id(release_id, "release")
        response = self._request("GET", f"/repos/{repository}/releases/{release_id}")
        if response.status == 404:
            return None
        return _parse_release(
            _json_response(response, {200}), repository, release_id,
        )

    def get_latest_release(self, repository: str) -> GitHubRelease | None:
        """Return GitHub's authoritative public latest-Release projection."""
        _require_repository(repository)
        response = self._request("GET", f"/repos/{repository}/releases/latest")
        if response.status == 404:
            return None
        return _parse_release(
            _json_response(response, {200}), repository,
        )

    def get_release_environment(self, repository: str) -> GitHubEnvironment | None:
        """Project the protected `release` Environment and its complete branch policy."""
        _require_repository(repository)
        endpoint = f"/repos/{repository}/environments/release"
        response = self._request("GET", endpoint)
        if response.status == 404:
            return None
        document = _json_response(response, {200})
        if not isinstance(document, dict):
            raise GitHubApiError("GitHub release Environment projection is invalid")
        name = document.get("name")
        rules = document.get("protection_rules")
        prevent_self_review = document.get("prevent_self_review")
        branch_policy = document.get("deployment_branch_policy")
        if (
            name != "release" or not isinstance(rules, list)
            or (
                prevent_self_review is not None
                and not isinstance(prevent_self_review, bool)
            )
            or not isinstance(branch_policy, dict)
        ):
            raise GitHubApiError("GitHub release Environment projection is invalid")
        reviewer_rules = [rule for rule in rules if isinstance(rule, dict) and rule.get("type") == "required_reviewers"]
        if len(reviewer_rules) > 1:
            raise GitHubApiError("GitHub release Environment projection is invalid")
        reviewers = reviewer_rules[0].get("reviewers", []) if reviewer_rules else []
        protected = branch_policy.get("protected_branches")
        custom = branch_policy.get("custom_branch_policies")
        if (
            not isinstance(reviewers, list) or not isinstance(protected, bool)
            or not isinstance(custom, bool)
        ):
            raise GitHubApiError("GitHub release Environment projection is invalid")
        branch_policies = self._list_deployment_branch_policies(repository) if custom else ()
        return GitHubEnvironment(
            name, len(reviewers), prevent_self_review, protected, custom,
            tuple(branch_policies),
        )

    def list_releases(self, repository: str) -> list[GitHubRelease]:
        """Return the complete typed Release inventory through strict pagination."""
        _require_repository(repository)
        endpoint = f"/repos/{repository}/releases"
        required_query = {"per_page": "100"}
        next_path: str | None = f"{endpoint}?{urlencode(required_query)}"
        visited: set[str] = set()
        releases: list[GitHubRelease] = []
        while next_path is not None:
            if next_path in visited or len(visited) >= self._page_cap:
                raise GitHubApiError("GitHub Release pagination is invalid")
            visited.add(next_path)
            response = self._request("GET", next_path)
            document = _json_response(response, {200})
            if not isinstance(document, list):
                raise GitHubApiError("GitHub Release projection is invalid")
            releases.extend(_parse_release(item, repository) for item in document)
            next_path = _next_link(
                response.headers, endpoint, required_query, subject="Release",
            )
        identifiers = [release.id for release in releases]
        tags = [release.tag_name for release in releases]
        if len(identifiers) != len(set(identifiers)) or len(tags) != len(set(tags)):
            raise GitHubApiError("GitHub Release pagination returned duplicate identities")
        return releases

    def create_draft_release(
        self,
        repository: str,
        *,
        tag: str,
        name: str,
        body: str,
        prerelease: bool,
        make_latest: bool,
    ) -> GitHubRelease:
        _require_repository(repository)
        if not all(isinstance(item, str) and item for item in (tag, name, body)):
            raise GitHubApiError("GitHub Draft metadata is invalid")
        if not isinstance(prerelease, bool) or not isinstance(make_latest, bool):
            raise GitHubApiError("GitHub Draft metadata is invalid")
        payload = json.dumps({
            "tag_name": tag,
            "name": name,
            "body": body,
            "draft": True,
            "prerelease": prerelease,
            "make_latest": "true" if make_latest else "false",
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        response = self._request(
            "POST", f"/repos/{repository}/releases", payload,
            content_type="application/json",
        )
        return _parse_release(
            _json_response(response, {201}), repository,
        )

    def publish_release(
        self, repository: str, release_id: int, *, prerelease: bool, make_latest: bool,
    ) -> GitHubRelease:
        """Publish exact policy state; callers must re-read to detect concurrent drift."""
        _require_repository(repository)
        _require_id(release_id, "release")
        if not isinstance(prerelease, bool) or not isinstance(make_latest, bool):
            raise GitHubApiError("GitHub Release publication metadata is invalid")
        payload = json.dumps({
            "draft": False,
            "prerelease": prerelease,
            "make_latest": "true" if make_latest else "false",
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        response = self._request(
            "PATCH", f"/repos/{repository}/releases/{release_id}", payload,
            content_type="application/json",
        )
        release = _parse_release(
            _json_response(response, {200}), repository, release_id,
        )
        if release.draft:
            raise GitHubApiError("GitHub Release publication did not change Draft state")
        return release

    def list_release_assets(self, repository: str, release_id: int) -> list[GitHubAsset]:
        _require_repository(repository)
        _require_id(release_id, "release")
        endpoint = f"/repos/{repository}/releases/{release_id}/assets"
        required_query = {"per_page": "100"}
        next_path: str | None = f"{endpoint}?{urlencode(required_query)}"
        visited: set[str] = set()
        assets: list[GitHubAsset] = []
        while next_path is not None:
            if next_path in visited or len(visited) >= self._page_cap:
                raise GitHubApiError("GitHub asset pagination is invalid")
            visited.add(next_path)
            response = self._request("GET", next_path)
            document = _json_response(response, {200})
            if not isinstance(document, list):
                raise GitHubApiError("GitHub asset projection is invalid")
            assets.extend(_parse_asset(item, repository, release_id) for item in document)
            next_path = _next_link(
                response.headers, endpoint, required_query, subject="asset",
            )
        identifiers = [asset.id for asset in assets]
        if len(identifiers) != len(set(identifiers)):
            raise GitHubApiError("GitHub asset pagination returned duplicate IDs")
        return assets

    def upload_release_asset(
        self, repository: str, release_id: int, upload_url: str, name: str, payload: bytes,
    ) -> GitHubAsset:
        _require_repository(repository)
        _require_id(release_id, "release")
        if not isinstance(name, str) or not name or "/" in name or "\\" in name:
            raise GitHubApiError("GitHub asset name is invalid")
        if not isinstance(payload, bytes):
            raise GitHubApiError("GitHub asset payload is invalid")
        upload_identity = _release_upload_identity(upload_url)
        if upload_identity != (repository, release_id):
            raise GitHubApiError("GitHub asset upload URL is invalid")
        base = upload_url.split("{", 1)[0]
        url = f"{base}?name={quote(name, safe='')}"
        response = self._request("POST", url, payload, content_type="application/octet-stream")
        return _parse_asset(_json_response(response, {201}), repository, release_id)

    def download_asset(
        self, repository: str, release_id: int, asset: GitHubAsset,
    ) -> bytes:
        _require_repository(repository)
        _require_id(release_id, "release")
        _require_id(asset.id, "asset")
        if type(asset.release_id) is not int or asset.release_id != release_id:
            raise GitHubApiError("GitHub asset Release ownership is invalid")
        identity = _asset_api_identity(asset.api_url)
        if (
            identity != (repository, asset.id)
            or not _repository_url(asset.browser_download_url, "github.com", repository)
        ):
            raise GitHubApiError("GitHub asset API URL is invalid")
        response = self._request(
            "GET", asset.api_url, accept="application/octet-stream",
        )
        if response.status in (302, 307):
            location = _header(response.headers, "location")
            if not _trusted_asset_redirect(location):
                raise GitHubApiError("GitHub asset redirect is invalid")
            headers = {
                "Accept": "application/octet-stream",
                "User-Agent": "lmdj-release-pipeline",
            }
            try:
                response = self._http_transport("GET", location, headers, None)
            except Exception:
                raise GitHubApiError("GitHub asset download is unavailable") from None
            if not isinstance(response, HttpResponse):
                raise GitHubApiError("GitHub release response is invalid")
            content_type = _header(response.headers, "content-type")
            if content_type is not None and content_type.split(";", 1)[0].strip() != "application/octet-stream":
                raise GitHubApiError("GitHub asset download content type is invalid")
        if response.status != 200:
            raise GitHubApiError("GitHub asset download is unavailable")
        return response.body

    def delete_release(self, repository: str, release_id: int) -> None:
        _require_repository(repository)
        _require_id(release_id, "release")
        response = self._request("DELETE", f"/repos/{repository}/releases/{release_id}")
        if response.status != 204:
            raise GitHubApiError("GitHub Draft deletion is unavailable")

    def _list_deployment_branch_policies(
        self, repository: str,
    ) -> tuple[DeploymentBranchPolicy, ...]:
        endpoint = f"/repos/{repository}/environments/release/deployment-branch-policies"
        required_query = {"per_page": "100"}
        next_path: str | None = f"{endpoint}?{urlencode(required_query)}"
        visited: set[str] = set()
        policies: list[DeploymentBranchPolicy] = []
        total_count: int | None = None
        while next_path is not None:
            if next_path in visited or len(visited) >= self._page_cap:
                raise GitHubApiError("GitHub Environment pagination is invalid")
            visited.add(next_path)
            response = self._request("GET", next_path)
            document = _json_response(response, {200})
            items = document.get("branch_policies") if isinstance(document, dict) else None
            page_total = document.get("total_count") if isinstance(document, dict) else None
            if not isinstance(items, list) or type(page_total) is not int or page_total < 0:
                raise GitHubApiError("GitHub release Environment projection is invalid")
            if total_count is None:
                total_count = page_total
            elif total_count != page_total:
                raise GitHubApiError("GitHub Environment pagination is invalid")
            for item in items:
                if not isinstance(item, dict):
                    raise GitHubApiError("GitHub release Environment projection is invalid")
                identifier, name = item.get("id"), item.get("name")
                if not _positive_id(identifier) or not isinstance(name, str) or not name:
                    raise GitHubApiError("GitHub release Environment projection is invalid")
                detail = _json_response(
                    self._request("GET", f"{endpoint}/{identifier}"), {200},
                )
                if not isinstance(detail, dict):
                    raise GitHubApiError("GitHub release Environment projection is invalid")
                detail_id, detail_name, kind = (
                    detail.get("id"), detail.get("name"), detail.get("type"),
                )
                if (
                    detail_id != identifier or detail_name != name
                    or kind not in ("branch", "tag")
                ):
                    raise GitHubApiError("GitHub release Environment projection is invalid")
                policies.append(DeploymentBranchPolicy(identifier, name, kind))
            next_path = _next_link(
                response.headers, endpoint, required_query, subject="Environment",
            )
        identifiers = [policy.id for policy in policies]
        if len(identifiers) != len(set(identifiers)):
            raise GitHubApiError("GitHub release Environment projection is ambiguous")
        if total_count != len(policies):
            raise GitHubApiError("GitHub Environment pagination is incomplete")
        return tuple(policies)

    def _request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        *,
        accept: str = "application/vnd.github+json",
        content_type: str | None = None,
    ) -> HttpResponse:
        headers = {"Accept": accept, "User-Agent": "lmdj-release-pipeline"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if content_type is not None:
            headers["Content-Type"] = content_type
        try:
            response = self._http_transport(method, url, headers, body)
        except GitHubApiError:
            raise
        except Exception:
            raise GitHubApiError("GitHub release request is unavailable") from None
        if not isinstance(response, HttpResponse):
            raise GitHubApiError("GitHub release response is invalid")
        return response


def _http_request(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> HttpResponse:
    selected_url = f"https://api.github.com{url}" if url.startswith("/") else url
    request = Request(selected_url, data=body, headers=dict(headers), method=method)
    try:
        with build_opener(_NoRedirect()).open(request, timeout=30) as response:
            return HttpResponse(response.status, dict(response.headers.items()), response.read())
    except HTTPError as error:
        try:
            payload = error.read()
        except OSError:
            payload = b""
        return HttpResponse(error.code, dict(error.headers.items()) if error.headers else {}, payload)
    except Exception:
        raise GitHubApiError("GitHub release request is unavailable") from None


def _json_response(response: HttpResponse, allowed: set[int]) -> object:
    if response.status not in allowed:
        raise GitHubApiError("GitHub release request was rejected")
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GitHubApiError("GitHub release response is invalid") from None


def _run_workflow_reference(run: object) -> tuple[int, str]:
    if not isinstance(run, dict):
        raise GitHubApiError("GitHub run projection is invalid")
    workflow_id, workflow_path = run.get("workflow_id"), run.get("path")
    if (
        not _positive_id(workflow_id) or not isinstance(workflow_path, str)
        or not workflow_path.startswith(".github/workflows/")
        or workflow_path.endswith("/")
    ):
        raise GitHubApiError("GitHub run workflow identity is invalid")
    return workflow_id, workflow_path


def _is_workflow_file_run(run: object) -> bool:
    """Report whether a run was produced by a workflow file in this repository.

    GitHub also reports runs that name no workflow file at all — Dependabot's
    dependency-graph runs carry paths like `dynamic/dependabot/update-graph`.
    They can never be release evidence, and they are immutable history on any
    SHA they touch, so treating them as malformed would permanently void the
    run projection for that release target.
    """
    if not isinstance(run, dict):
        return False
    workflow_path = run.get("path")
    return (
        isinstance(workflow_path, str)
        and workflow_path.startswith(".github/workflows/")
        and not workflow_path.endswith("/")
    )


def _parse_run(run: object, stable_workflow_name: str) -> RunProjection:
    if not isinstance(run, dict):
        raise GitHubApiError("GitHub run projection is invalid")
    identifier, event, head_sha, head_branch, run_name, status, conclusion = (
        run.get("id"), run.get("event"), run.get("head_sha"), run.get("head_branch"),
        run.get("name"), run.get("status"), run.get("conclusion"),
    )
    if (
        not _positive_id(identifier) or not isinstance(event, str)
        or not _sha(head_sha) or not isinstance(head_branch, str)
        or not isinstance(run_name, str) or not run_name
        or not isinstance(stable_workflow_name, str) or not stable_workflow_name
        or not isinstance(status, str)
        or (conclusion is not None and not isinstance(conclusion, str))
    ):
        raise GitHubApiError("GitHub run projection is invalid")
    return RunProjection(
        identifier, event, head_sha, head_branch, stable_workflow_name, status, conclusion,
    )


def _parse_run_job(job: object, run_id: int) -> RunJobProjection:
    if not isinstance(job, dict):
        raise GitHubApiError("GitHub run job projection is invalid")
    identifier, observed_run, name = job.get("id"), job.get("run_id"), job.get("name")
    status, conclusion = job.get("status"), job.get("conclusion")
    workflow_name, head_sha = job.get("workflow_name"), job.get("head_sha")
    if (
        not _positive_id(identifier) or observed_run != run_id
        or not isinstance(name, str) or not name
        or not isinstance(status, str) or not status
        or (conclusion is not None and not isinstance(conclusion, str))
        or not isinstance(workflow_name, str) or not workflow_name
        or not _sha(head_sha)
    ):
        raise GitHubApiError("GitHub run job projection is invalid")
    return RunJobProjection(
        identifier, observed_run, name, status, conclusion, workflow_name, head_sha,
    )


def _parse_artifact(
    document: object, repository: str, run_id: int,
) -> ActionsArtifactProjection:
    if not isinstance(document, dict):
        raise GitHubApiError("GitHub artifact projection is invalid")
    identifier, name = document.get("id"), document.get("name")
    size, expired = document.get("size_in_bytes"), document.get("expired")
    api_url, archive_url = document.get("url"), document.get("archive_download_url")
    expires_at, run = document.get("expires_at"), document.get("workflow_run")
    if (
        not _positive_id(identifier) or not isinstance(name, str) or not name
        or "/" in name or "\\" in name
        or type(size) is not int or size < 0
        or not isinstance(expired, bool) or not isinstance(expires_at, str)
        or not expires_at or not isinstance(run, dict)
        or _artifact_api_identity(api_url) != (repository, identifier)
        or archive_url != f"{api_url}/zip"
    ):
        raise GitHubApiError("GitHub artifact projection is invalid")
    observed_run, repository_id = run.get("id"), run.get("repository_id")
    head_repository_id, head_branch = run.get("head_repository_id"), run.get("head_branch")
    head_sha = run.get("head_sha")
    if (
        observed_run != run_id or not _positive_id(repository_id)
        or not _positive_id(head_repository_id)
        or not isinstance(head_branch, str) or not head_branch
        or not _sha(head_sha)
    ):
        raise GitHubApiError("GitHub artifact run identity is invalid")
    return ActionsArtifactProjection(
        identifier, name, size, api_url, archive_url, expired, observed_run,
        repository_id, head_repository_id, head_branch, head_sha, expires_at,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise CiScopeConflictError("CI scope manifest has a duplicate key")
        document[key] = value
    return document


def _parse_ci_scope(payload: bytes) -> CiScopeProjection:
    """Parse the one closed v2 manifest inside a retained scope archive."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise CiScopeConflictError("CI scope archive member inventory is not closed")
            member = members[0]
            if (
                member.filename != _CI_SCOPE_MEMBER or member.is_dir()
                or member.file_size > _CI_SCOPE_SIZE_CAP
                or member.compress_size > _CI_SCOPE_SIZE_CAP
                or (member.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise CiScopeConflictError("CI scope archive member is not the exact manifest")
            contents = archive.read(member)
    except CiScopeConflictError:
        raise
    except (zipfile.BadZipFile, OSError, ValueError, RuntimeError):
        raise CiScopeConflictError("CI scope archive is unreadable") from None
    try:
        document = json.loads(
            contents.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys,
        )
    except CiScopeConflictError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CiScopeConflictError("CI scope manifest is not valid JSON") from None
    return _project_ci_scope(document)


def _project_ci_scope(document: object) -> CiScopeProjection:
    if not isinstance(document, dict) or set(document) != _CI_SCOPE_KEYS:
        raise CiScopeConflictError("CI scope manifest schema is not closed")
    schema, mode = document["schema"], document["mode"]
    base_sha, head_sha = document["base_sha"], document["head_sha"]
    trusted_head, lanes = document["trusted_head"], document["lanes"]
    required_jobs, reasons = document["required_jobs"], document["reasons"]
    if (
        schema != _CI_SCOPE_SCHEMA or mode not in _CI_SCOPE_MODES
        or not _sha(base_sha) or not _sha(head_sha)
        or type(trusted_head) is not bool
        or not isinstance(reasons, list)
        or not all(isinstance(reason, str) for reason in reasons)
        or not isinstance(document["changed_files"], list)
    ):
        raise CiScopeConflictError("CI scope manifest identity is invalid")
    if (
        not isinstance(lanes, dict) or set(lanes) != CI_SCOPE_LANES
        or not all(type(value) is bool for value in lanes.values())
    ):
        raise CiScopeConflictError("CI scope manifest lanes are not closed")
    selected = tuple(sorted(lane for lane, enabled in lanes.items() if enabled))
    if mode == "full" and set(selected) != CI_SCOPE_LANES:
        raise CiScopeConflictError("full CI scope manifest does not select every lane")
    # The required-job inventory is only checked for closed shape here: the
    # same-run Gate is the authority that binds jobs to lanes, and duplicating
    # the CI lane/job table in release tooling would make release authority
    # depend on a second, silently drifting copy of it.
    if (
        not isinstance(required_jobs, list) or not required_jobs
        or not all(
            isinstance(job, str) and job and "/" not in job for job in required_jobs
        )
        or len(set(required_jobs)) != len(required_jobs)
        or list(required_jobs) != sorted(required_jobs)
    ):
        raise CiScopeConflictError("CI scope manifest required jobs are not closed")
    return CiScopeProjection(
        schema, base_sha.lower(), head_sha.lower(), mode, trusted_head,
        selected, tuple(required_jobs),
    )


def _parse_release(
    document: object, repository: str, expected_id: int | None = None,
) -> GitHubRelease:
    if not isinstance(document, dict):
        raise GitHubApiError("GitHub Release projection is invalid")
    identifier = document.get("id")
    api_url = document.get("url")
    tag, name, body = document.get("tag_name"), document.get("name"), document.get("body")
    draft, prerelease = document.get("draft"), document.get("prerelease")
    html_url, upload_url, assets = document.get("html_url"), document.get("upload_url"), document.get("assets")
    if name is None:
        name = ""
    if body is None:
        body = ""
    if (
        not _positive_id(identifier) or not isinstance(tag, str) or not tag
        or (expected_id is not None and identifier != expected_id)
        or _release_api_identity(api_url) != (repository, identifier)
        or not isinstance(name, str) or not isinstance(body, str)
        or not isinstance(draft, bool) or not isinstance(prerelease, bool)
        or not _repository_url(html_url, "github.com", repository)
        or _release_upload_identity(upload_url) != (repository, identifier)
        or not isinstance(assets, list)
    ):
        raise GitHubApiError("GitHub Release projection is invalid")
    target_commitish = document.get("target_commitish")
    if not isinstance(target_commitish, str) or not target_commitish:
        raise GitHubApiError("GitHub Release projection is invalid")
    latest_value = document.get("make_latest")
    # GitHub's Release response does not consistently include the update-only
    # make_latest field. None explicitly means "not projected"; when present,
    # preserve only its documented bool/string representations.
    if type(latest_value) is bool and latest_value:
        make_latest: bool | None = True
    elif type(latest_value) is bool and not latest_value:
        make_latest = False
    elif latest_value == "true":
        make_latest = True
    elif latest_value == "false":
        make_latest = False
    elif latest_value is None:
        make_latest = None
    else:
        raise GitHubApiError("GitHub Release projection is invalid")
    published_at = document.get("published_at")
    if published_at is not None:
        if type(published_at) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", published_at) is None:
            raise GitHubApiError("why: GitHub Release publication timestamp is not canonical UTC; remedy: reconcile the numeric Release API response; do not substitute a local date")
        try:
            datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            raise GitHubApiError("why: GitHub Release publication timestamp is not a valid calendar time; remedy: reconcile the numeric Release API response; do not substitute a local date") from None
    return GitHubRelease(
        identifier, tag, name, body, draft, prerelease, make_latest, html_url, upload_url,
        tuple(_parse_asset(item, repository, identifier) for item in assets), target_commitish, published_at,
    )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _header(headers: Mapping[str, str], name: str) -> str | None:
    return next((value for key, value in headers.items() if key.lower() == name), None)


def _trusted_asset_redirect(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname in {
            "objects.githubusercontent.com", "release-assets.githubusercontent.com",
        }
        and port is None and parsed.username is None and parsed.password is None
        and not parsed.params and not parsed.fragment and bool(parsed.path)
    )


def _trusted_artifact_redirect(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and isinstance(parsed.hostname, str)
        and _ARTIFACT_REDIRECT_HOST.fullmatch(parsed.hostname) is not None
        and port is None and parsed.username is None and parsed.password is None
        and not parsed.params and not parsed.fragment and bool(parsed.path)
        and bool(parsed.query)
    )


def _artifact_api_identity(value: object) -> tuple[str, int] | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    match = re.fullmatch(
        r"/repos/([^/]+/[^/]+)/actions/artifacts/([1-9][0-9]*)", parsed.path,
    )
    if (
        parsed.scheme != "https" or parsed.netloc != "api.github.com"
        or parsed.params or parsed.query or parsed.fragment or match is None
    ):
        return None
    return match.group(1), int(match.group(2))


def _parse_asset(document: object, repository: str, release_id: int) -> GitHubAsset:
    _require_id(release_id, "release")
    if not isinstance(document, dict):
        raise GitHubApiError("GitHub asset projection is invalid")
    identifier, name, size = document.get("id"), document.get("name"), document.get("size")
    label, content_type, state = (
        document.get("label"), document.get("content_type"), document.get("state"),
    )
    api_url, download_url = document.get("url"), document.get("browser_download_url")
    media_type = _media_type(content_type)
    if (
        not _positive_id(identifier) or not isinstance(name, str) or not name
        or "/" in name or "\\" in name or type(size) is not int or size < 0
        or (label is not None and not isinstance(label, str))
        or media_type is None
        or re.fullmatch(r"[^\s/]+/[^\s/]+", media_type) is None
        or not isinstance(state, str) or not state
        or _asset_api_identity(api_url) != (repository, identifier)
        or not _repository_url(download_url, "github.com", repository)
    ):
        raise GitHubApiError("GitHub asset projection is invalid")
    return GitHubAsset(
        identifier, name, size, api_url, download_url, release_id,
        label, media_type, state,
    )


def _media_type(value: object) -> str | None:
    """Reduce a Content-Type to the bare type/subtype it identifies.

    A media type may carry RFC 9110 parameters, and GitHub returns them: the
    legacy `v0.2.0` Release serves `text/markdown; charset=utf-8`. A parameter
    describes an encoding, never the asset's identity, so it is dropped before
    the closed type/subtype pattern decides. Everything the pattern rejected
    before it still rejects, because only parameters are removed.
    """
    if not isinstance(value, str):
        return None
    return value.split(";", 1)[0].strip()


def _next_link(
    headers: Mapping[str, str],
    expected_path: str,
    required_query: Mapping[str, str],
    *,
    subject: str,
) -> str | None:
    value = next((item for key, item in headers.items() if key.lower() == "link"), None)
    if value is None:
        return None
    next_urls: list[str] = []
    for item in value.split(","):
        match = re.fullmatch(r'\s*<([^>]+)>\s*;\s*rel="([^"]+)"\s*', item)
        if match is None:
            raise GitHubApiError(f"GitHub {subject} pagination is invalid")
        if match.group(2) == "next":
            next_urls.append(match.group(1))
    if len(next_urls) > 1:
        raise GitHubApiError(f"GitHub {subject} pagination is invalid")
    if not next_urls:
        return None
    parsed = urlparse(next_urls[0])
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    query = dict(query_items)
    if (
        parsed.scheme != "https" or parsed.netloc != "api.github.com"
        or parsed.path != expected_path or len(query) != len(query_items)
        or any(query.get(key) != value for key, value in required_query.items())
        or set(query) != set(required_query) | {"page"}
        or re.fullmatch(r"[1-9][0-9]*", query.get("page", "")) is None
    ):
        raise GitHubApiError(f"GitHub {subject} pagination is invalid")
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _require_id(value: object, subject: str) -> None:
    if not _positive_id(value):
        raise GitHubApiError(f"GitHub {subject} ID must be numeric")


def _positive_id(value: object) -> bool:
    return type(value) is int and value > 0


def _require_repository(repository: object) -> None:
    if not isinstance(repository, str) or re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?/[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?",
        repository,
    ) is None:
        raise GitHubApiError("GitHub repository identity is invalid")


def _repository_url(value: object, hostname: str, repository: str) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return (
        parsed.scheme == "https" and parsed.netloc == hostname
        and parsed.path.startswith(f"/{repository}/") and not parsed.params
        and not parsed.query and not parsed.fragment
    )


def _release_upload_identity(value: object) -> tuple[str, int] | None:
    if not isinstance(value, str):
        return None
    base, separator, template = value.partition("{")
    if separator != "{" or template != "?name,label}":
        return None
    parsed = urlparse(base)
    match = re.fullmatch(r"/repos/([^/]+/[^/]+)/releases/([1-9][0-9]*)/assets", parsed.path)
    if (
        parsed.scheme != "https" or parsed.netloc != "uploads.github.com"
        or parsed.params or parsed.query or parsed.fragment or match is None
    ):
        return None
    return match.group(1), int(match.group(2))


def _release_api_identity(value: object) -> tuple[str, int] | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    match = re.fullmatch(r"/repos/([^/]+/[^/]+)/releases/([1-9][0-9]*)", parsed.path)
    if (
        parsed.scheme != "https" or parsed.netloc != "api.github.com"
        or parsed.params or parsed.query or parsed.fragment or match is None
    ):
        return None
    return match.group(1), int(match.group(2))


def _asset_api_identity(value: object) -> tuple[str, int] | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    match = re.fullmatch(r"/repos/([^/]+/[^/]+)/releases/assets/([1-9][0-9]*)", parsed.path)
    if (
        parsed.scheme != "https" or parsed.netloc != "api.github.com"
        or parsed.params or parsed.query or parsed.fragment or match is None
    ):
        return None
    return match.group(1), int(match.group(2))


def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)
