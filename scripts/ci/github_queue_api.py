#!/usr/bin/env python3
"""Typed GitHub REST boundary for the LMDJ Integration Queue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import io
import json
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from merge_queue import (
    DispatchContractError,
    MergeResult,
    PullRequest,
    REQUIRED_CHECKS,
    RequiredCheck,
    UpdateResult,
    ValidationResult,
)
from change_scope import load_policy, reject_duplicates, validate_manifest


API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
QUEUE_VALIDATION_KEYS = {
    "schema",
    "classification",
    "queue_ticket",
    "queue_pr_number",
    "queue_base_sha",
    "queue_head_sha",
    "observed_base_sha",
    "observed_head_sha",
    "manifest_mode",
    "trusted_head",
}
QUEUE_CLASSIFICATIONS = {
    "valid", "queue-base-drift", "queue-head-drift", "invalid",
}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_REDIRECT_HOST = re.compile(
    r"productionresultssa[0-9]+\.blob\.core\.windows\.net"
)


class GitHubApiError(RuntimeError):
    def __init__(self, status: int, method: str, url: str, message: str):
        super().__init__(f"GitHub API {method} {url} returned {status}: {message}")
        self.status = status


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None
    timeout_seconds: float = 30.0


Transport = Callable[[HttpRequest], tuple[int, Mapping[str, str], bytes]]


def _urllib_transport(request: HttpRequest) -> tuple[int, Mapping[str, str], bytes]:
    urllib_request = Request(
        request.url,
        data=request.body,
        headers=dict(request.headers),
        method=request.method,
    )
    try:
        with build_opener(_NoRedirect()).open(
            urllib_request, timeout=request.timeout_seconds
        ) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as error:
        try:
            return error.code, dict(error.headers.items()), error.read()
        finally:
            error.close()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _header(headers: Mapping[str, str], name: str) -> str | None:
    return next(
        (value for key, value in headers.items() if key.lower() == name.lower()),
        None,
    )


def _trusted_artifact_redirect(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        port = parsed.port
        signatures = parse_qs(parsed.query, keep_blank_values=True).get("sig", [])
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and isinstance(parsed.hostname, str)
        and _ARTIFACT_REDIRECT_HOST.fullmatch(parsed.hostname) is not None
        and port is None
        and parsed.username is None
        and parsed.password is None
        and not parsed.params
        and not parsed.fragment
        and bool(parsed.path)
        and len(signatures) == 1
        and bool(signatures[0])
    )


def _json(body: bytes) -> object:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("GitHub API response is not UTF-8 JSON") from error


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase 40-character SHA")
    return value


def _next_link(headers: Mapping[str, str]) -> str | None:
    value = next((value for key, value in headers.items() if key.lower() == "link"), "")
    for part in value.split(","):
        match = re.fullmatch(r'\s*<([^>]+)>;\s*rel="([^"]+)"\s*', part)
        if match and match.group(2) == "next":
            return match.group(1)
    return None


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("run timestamp must be a string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_queue_validation_json(value: object) -> dict[str, object]:
    document = _object(value, "queue validation")
    if set(document) != QUEUE_VALIDATION_KEYS:
        raise ValueError("queue validation key set mismatch")
    if document["schema"] != "lmdj.queue-validation.v1":
        raise ValueError("unsupported queue validation schema")
    if document["classification"] not in QUEUE_CLASSIFICATIONS:
        raise ValueError("unknown queue validation classification")
    if not isinstance(document["queue_ticket"], str) or not re.fullmatch(
        r"mq:[1-9][0-9]*:[1-3]", document["queue_ticket"]
    ):
        raise ValueError("invalid queue ticket")
    if not isinstance(document["queue_pr_number"], int) or isinstance(
        document["queue_pr_number"], bool
    ) or document["queue_pr_number"] <= 0:
        raise ValueError("invalid queue PR number")
    for name in (
        "queue_base_sha", "queue_head_sha", "observed_base_sha", "observed_head_sha"
    ):
        _sha(document[name], name)
    if document["manifest_mode"] not in {None, "full"}:
        raise ValueError("queue manifest mode must be null or full")
    if not isinstance(document["trusted_head"], bool):
        raise ValueError("queue trusted head must be boolean")
    return document


def parse_queue_validation_zip(payload: bytes) -> dict[str, object]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [name for name in archive.namelist() if name.endswith("queue-validation.json")]
            if names != ["queue-validation.json"]:
                raise ValueError("queue validation archive must contain one root document")
            try:
                document = json.loads(
                    archive.read(names[0]).decode("utf-8"),
                    object_pairs_hook=reject_duplicates,
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("queue validation is not UTF-8 JSON") from error
            return parse_queue_validation_json(document)
    except zipfile.BadZipFile as error:
        raise ValueError("queue validation artifact is not a zip archive") from error


def parse_scope_manifest_zip(
    payload: bytes, expected_head_sha: str
) -> dict[str, object]:
    expected_head_sha = _sha(expected_head_sha, "expected scope head SHA")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [name for name in archive.namelist() if name.endswith("ci-scope.json")]
            if names != ["ci-scope.json"]:
                raise ValueError("scope archive must contain one root document")
            try:
                parsed = json.loads(
                    archive.read(names[0]).decode("utf-8"),
                    object_pairs_hook=reject_duplicates,
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("scope manifest is not UTF-8 JSON") from error
            document = _object(parsed, "scope manifest")
    except zipfile.BadZipFile as error:
        raise ValueError("scope artifact is not a zip archive") from error
    policy = load_policy(Path(__file__).with_name("scope_policy.json"))
    validate_manifest(document, policy)
    if "queue" in document:
        raise ValueError("pull request scope must not contain dispatch queue metadata")
    if document.get("head_sha") != expected_head_sha:
        raise ValueError("scope manifest head does not match workflow run")
    if document.get("mode") != "full" or document.get("trusted_head") is not True:
        raise ValueError("synchronized validation requires trusted full scope")
    return document


class GitHubQueueClient:
    def __init__(
        self,
        repository: str,
        token: str,
        *,
        api_version: str = API_VERSION,
        transport: Transport = _urllib_transport,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("repository must be owner/name")
        if not token:
            raise ValueError("GitHub token is required")
        self.repository = repository
        self._token = token
        self._api_version = api_version
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper

    def _url(self, path: str) -> str:
        if path.startswith("https://"):
            return path
        return f"{API_ROOT}/repos/{self.repository}{path}"

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
        *,
        expected: Sequence[int] = (200,),
        timeout_seconds: float | None = None,
    ) -> tuple[int, Mapping[str, str], bytes]:
        body = None if payload is None else json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": self._api_version,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        url = self._url(path)
        deadline = (
            None if timeout_seconds is None else self._clock() + timeout_seconds
        )
        attempts = 3 if method == "GET" else 1
        status, response_headers, response_body = 0, {}, b""
        for attempt in range(attempts):
            request_timeout = 30.0
            if deadline is not None:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise TimeoutError(f"GitHub API {method} {url} exceeded its deadline")
                request_timeout = min(request_timeout, remaining)
            request = HttpRequest(method, url, headers, body, request_timeout)
            try:
                status, response_headers, response_body = self._transport(request)
            except (OSError, TimeoutError):
                if method != "GET" or attempt == attempts - 1:
                    raise
                delay = float(2 ** attempt)
                if deadline is not None:
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"GitHub API {method} {url} exceeded its deadline"
                        )
                    delay = min(delay, remaining)
                self._sleeper(delay)
                continue
            retryable = status >= 500 or status == 429 or (
                status == 403 and any(
                    key.lower() == "retry-after" for key in response_headers
                )
            )
            if not retryable or attempt == attempts - 1:
                break
            delay = float(2 ** attempt)
            if deadline is not None:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise TimeoutError(
                        f"GitHub API {method} {url} exceeded its deadline"
                    )
                delay = min(delay, remaining)
            self._sleeper(delay)
        if status not in expected:
            raise GitHubApiError(status, method, url, "unexpected response")
        return status, response_headers, response_body

    def _get_object(
        self, path: str, *, timeout_seconds: float | None = None
    ) -> dict[str, Any]:
        return _object(
            _json(self._request("GET", path, timeout_seconds=timeout_seconds)[2]),
            path,
        )

    def _get_pages(self, path: str, key: str | None = None) -> list[object]:
        values: list[object] = []
        next_path: str | None = path
        while next_path:
            _, headers, body = self._request("GET", next_path)
            document = _json(body)
            if key is not None:
                document = _object(document, next_path).get(key)
            if not isinstance(document, list):
                raise ValueError(f"paginated {key or 'response'} must be an array")
            values.extend(document)
            next_path = _next_link(headers)
        return values

    def get_permission(self, actor: str) -> str:
        document = self._get_object(
            f"/collaborators/{quote(actor, safe='')}/permission"
        )
        permission = document.get("permission")
        if not isinstance(permission, str):
            raise ValueError("collaborator permission is missing")
        return permission

    def get_pull(
        self, number: int, *, timeout_seconds: float | None = None
    ) -> PullRequest:
        document = self._get_object(
            f"/pulls/{number}", timeout_seconds=timeout_seconds
        )
        base = _object(document.get("base"), "pull base")
        head = _object(document.get("head"), "pull head")
        head_repo = _object(head.get("repo"), "pull head repository")
        labels = document.get("labels")
        if not isinstance(labels, list):
            raise ValueError("pull labels must be an array")
        label_names: list[str] = []
        for value in labels:
            name = _object(value, "pull label").get("name")
            if not isinstance(name, str):
                raise ValueError("pull label name is missing")
            label_names.append(name)
        mergeable = document.get("mergeable")
        if mergeable not in {True, False, None}:
            raise ValueError("pull mergeable must be boolean or null")
        return PullRequest(
            number=int(document["number"]),
            state=str(document["state"]),
            merged=bool(document["merged"]),
            draft=bool(document["draft"]),
            base_ref=str(base["ref"]),
            base_sha=_sha(base["sha"], "pull base SHA"),
            head_repository=str(head_repo["full_name"]),
            head_sha=_sha(head["sha"], "pull head SHA"),
            title=str(document["title"]),
            labels=tuple(label_names),
            mergeable=mergeable,
            merge_commit_sha=(
                _sha(document["merge_commit_sha"], "merge commit SHA")
                if document.get("merge_commit_sha") is not None else None
            ),
            head_ref=str(head["ref"]),
        )

    def get_main_sha(self, *, timeout_seconds: float | None = None) -> str:
        document = self._get_object(
            "/git/ref/heads/main", timeout_seconds=timeout_seconds
        )
        if document.get("ref") != "refs/heads/main":
            raise ValueError("canonical main ref identity mismatch")
        return _sha(_object(document.get("object"), "git ref object").get("sha"), "main SHA")

    def list_changed_paths(self, number: int) -> tuple[str, ...]:
        files = self._get_pages(f"/pulls/{number}/files?per_page=100")
        paths: list[str] = []
        for value in files:
            filename = _object(value, "pull file").get("filename")
            if not isinstance(filename, str) or not filename:
                raise ValueError("pull filename is missing")
            paths.append(filename)
        return tuple(paths)

    def is_ancestor(
        self, base: str, head: str, *, timeout_seconds: float | None = None
    ) -> bool:
        document = self._get_object(
            f"/compare/{base}...{head}", timeout_seconds=timeout_seconds
        )
        return document.get("status") in {"ahead", "identical"}

    def update_branch(
        self, number: int, expected_head_sha: str, timeout_seconds: int
    ) -> UpdateResult:
        try:
            status, _, _ = self._request(
                "PUT",
                f"/pulls/{number}/update-branch",
                {"expected_head_sha": expected_head_sha},
                expected=(202, 409, 422),
            )
        except Exception:
            return UpdateResult("uncertain", None)
        if status == 422:
            return UpdateResult("drift", None)
        if status == 409:
            return UpdateResult("conflict", None)
        deadline = self._clock() + timeout_seconds
        while self._clock() <= deadline:
            pull = self.get_pull(number)
            if pull.head_sha != expected_head_sha:
                return UpdateResult("accepted", pull.head_sha)
            self._sleeper(5)
        return UpdateResult("timeout", None)

    def authorize_sync_validation(
        self, number: int, base_sha: str, head_sha: str, timeout_seconds: int
    ) -> int:
        _sha(base_sha, "synchronized base SHA")
        _sha(head_sha, "synchronized head SHA")
        deadline = self._clock() + timeout_seconds
        while True:
            values = self._get_pages(
                "/actions/workflows/ci.yml/runs?event=pull_request&per_page=100",
                "workflow_runs",
            )
            candidates: list[dict[str, Any]] = []
            for value in values:
                run = _object(value, "workflow run")
                pull_numbers = {
                    _object(pull, "workflow run pull").get("number")
                    for pull in run.get("pull_requests", [])
                }
                if (
                    run.get("event") == "pull_request"
                    and run.get("path") == ".github/workflows/ci.yml"
                    and run.get("head_sha") == head_sha
                    and _object(run.get("actor"), "workflow run actor").get("login")
                    == "github-actions[bot]"
                    and number in pull_numbers
                ):
                    candidates.append(run)
            if len(candidates) > 1:
                raise ValueError("multiple synchronized validation runs matched")
            if candidates:
                run = candidates[0]
                run_id = run.get("id")
                if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
                    raise ValueError("synchronized validation run ID is missing")
                if run.get("conclusion") == "action_required":
                    try:
                        self._request(
                            "POST", f"/actions/runs/{run_id}/approve", expected=(201,)
                        )
                    except Exception:
                        pass
                    while self._clock() <= deadline:
                        reconciled = self._get_object(f"/actions/runs/{run_id}")
                        if reconciled.get("conclusion") != "action_required":
                            return run_id
                        self._sleeper(1)
                    raise GitHubApiError(
                        403,
                        "POST",
                        self._url(f"/actions/runs/{run_id}/approve"),
                        "synchronized validation still requires approval",
                    )
                if run.get("status") in {"queued", "in_progress", "completed"}:
                    return run_id
                raise ValueError("synchronized validation run has an unexpected state")
            if self._clock() >= deadline:
                raise TimeoutError("synchronized validation run was not created")
            self._sleeper(5)

    def get_tree(self, sha: str, *, timeout_seconds: float | None = None) -> str:
        document = self._get_object(
            f"/git/commits/{sha}", timeout_seconds=timeout_seconds
        )
        return _sha(_object(document.get("tree"), "commit tree").get("sha"), "tree SHA")

    def dispatch_validation(
        self, number: int, head_ref: str, inputs: Mapping[str, str]
    ) -> int:
        del number
        _, _, body = self._request(
            "POST",
            "/actions/workflows/ci.yml/dispatches",
            {"ref": head_ref, "inputs": dict(inputs)},
            expected=(200,),
        )
        document = _object(_json(body), "workflow dispatch response")
        run_id = document.get("workflow_run_id")
        if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
            raise DispatchContractError("workflow dispatch response has no numeric workflow_run_id")
        return run_id

    def cancel_validation(self, run_id: int) -> None:
        self._request(
            "POST",
            f"/actions/runs/{run_id}/cancel",
            expected=tuple(range(200, 300)),
        )

    def _required_checks(
        self, jobs: list[object], checks: list[object]
    ) -> tuple[RequiredCheck, ...]:
        job_results = {
            str(_object(job, "job").get("name")): _object(job, "job").get("conclusion")
            for job in jobs
        }
        parsed: list[RequiredCheck] = []
        for value in checks:
            check = _object(value, "check run")
            name = check.get("name")
            if name not in REQUIRED_CHECKS or name not in job_results:
                continue
            app_id = _object(check.get("app"), "check app").get("id")
            conclusion = check.get("conclusion")
            if not isinstance(name, str) or not isinstance(app_id, int) or not isinstance(conclusion, str):
                raise ValueError("required check identity is incomplete")
            if job_results[name] != conclusion:
                raise ValueError("job/check conclusion mismatch")
            parsed.append(RequiredCheck(name, app_id, conclusion))
        return tuple(sorted(parsed, key=lambda item: item.name))

    def _download_validation_artifact(self, artifact_id: int) -> bytes:
        status, headers, _ = self._request(
            "GET",
            f"/actions/artifacts/{artifact_id}/zip",
            expected=(302, 307),
        )
        location = _header(headers, "location")
        if not _trusted_artifact_redirect(location):
            raise GitHubApiError(
                status,
                "GET",
                f"{API_ROOT}/repos/{self.repository}/actions/artifacts/{artifact_id}/zip",
                "untrusted artifact redirect",
            )
        try:
            redirected_status, redirected_headers, redirected_body = self._transport(
                HttpRequest(
                    "GET",
                    location,
                    {
                        "Accept": "application/zip",
                        "User-Agent": "lmdj-merge-queue",
                    },
                    None,
                )
            )
        except (OSError, TimeoutError):
            raise GitHubApiError(
                0, "GET", "trusted artifact redirect", "download unavailable"
            ) from None
        content_type = _header(redirected_headers, "content-type")
        if (
            redirected_status != 200
            or content_type is None
            or content_type.split(";", 1)[0].strip().lower() != "application/zip"
        ):
            raise GitHubApiError(
                redirected_status,
                "GET",
                "trusted artifact redirect",
                "unexpected response",
            )
        return redirected_body

    def wait_validation(self, run_id: int, timeout_seconds: int) -> ValidationResult:
        deadline = self._clock() + timeout_seconds
        while True:
            run = self._get_object(f"/actions/runs/{run_id}")
            if run.get("status") == "completed":
                break
            if self._clock() >= deadline:
                return ValidationResult(
                    "timeout", run_id, str(run.get("status")), None,
                    str(run.get("event")), str(run.get("path")),
                    str(run.get("head_sha")), None, False, None, None, (), 0, 0,
                )
            self._sleeper(15)
        jobs = self._get_pages(f"/actions/runs/{run_id}/jobs?per_page=100", "jobs")
        suite_id = run.get("check_suite_id")
        if not isinstance(suite_id, int) or isinstance(suite_id, bool):
            raise ValueError("workflow run check_suite_id is missing")
        checks = self._get_pages(f"/check-suites/{suite_id}/check-runs?per_page=100", "check_runs")
        artifacts = self._get_pages(f"/actions/runs/{run_id}/artifacts?per_page=100", "artifacts")
        candidates = []
        artifact_prefix = (
            "queue-validation-"
            if run.get("event") == "workflow_dispatch"
            else f"ci-scope-{run.get('head_sha')}"
        )
        for value in artifacts:
            artifact = _object(value, "artifact")
            if (
                isinstance(artifact.get("name"), str)
                and (
                    artifact["name"].startswith(artifact_prefix)
                    if run.get("event") == "workflow_dispatch"
                    else artifact["name"] == artifact_prefix
                )
                and artifact.get("expired") is False
            ):
                candidates.append(artifact)
        if len(candidates) != 1 or not isinstance(candidates[0].get("id"), int):
            raise ValueError("exactly one live validation artifact is required")
        artifact_body = self._download_validation_artifact(candidates[0]["id"])
        if run.get("event") == "pull_request":
            manifest = parse_scope_manifest_zip(artifact_body, str(run.get("head_sha")))
            validation = {
                "classification": "valid",
                "queue_ticket": None,
                "queue_base_sha": manifest["base_sha"],
                "manifest_mode": manifest["mode"],
                "trusted_head": manifest["trusted_head"],
            }
        else:
            validation = parse_queue_validation_zip(artifact_body)
        created = _instant(run["created_at"])
        started = _instant(run["run_started_at"])
        updated = _instant(run["updated_at"])
        return ValidationResult(
            classification=str(validation["classification"]),
            run_id=run_id,
            run_status=str(run["status"]),
            run_conclusion=(str(run["conclusion"]) if run.get("conclusion") is not None else None),
            run_event=str(run["event"]),
            workflow_path=str(run["path"]),
            head_sha=_sha(run["head_sha"], "workflow run head SHA"),
            manifest_mode=(
                str(validation["manifest_mode"])
                if validation["manifest_mode"] is not None else None
            ),
            trusted_head=bool(validation["trusted_head"]),
            ticket=(
                str(validation["queue_ticket"])
                if validation["queue_ticket"] is not None else None
            ),
            base_sha=str(validation["queue_base_sha"]),
            required_checks=self._required_checks(jobs, checks),
            queue_seconds=(started - created).total_seconds(),
            execution_seconds=(updated - started).total_seconds(),
        )

    def merge_pull(self, number: int, payload: Mapping[str, str]) -> MergeResult:
        try:
            _, _, body = self._request(
                "PUT", f"/pulls/{number}/merge", dict(payload), expected=(200, 405, 409)
            )
        except Exception as error:
            return MergeResult(False, None, uncertain=True, message=type(error).__name__)
        document = _object(_json(body), "merge response")
        merged = document.get("merged") is True
        sha = document.get("sha")
        return MergeResult(
            merged,
            _sha(sha, "merge SHA") if merged else None,
            uncertain=False,
            message=str(document.get("message", "")),
        )

    def remove_label(self, number: int, label: str) -> None:
        self._request(
            "DELETE",
            f"/issues/{number}/labels/{quote(label, safe='')}",
            expected=(200,),
        )

    def create_review_comment(self, number: int, body: str) -> None:
        self._request(
            "POST", f"/issues/{number}/comments", {"body": body}, expected=(201,),
        )

    def list_labeled_pulls(self, label: str) -> tuple[PullRequest, ...]:
        values = self._get_pages(
            f"/pulls?state=open&base=main&sort=created&direction=asc&per_page=100"
        )
        pulls: list[PullRequest] = []
        for value in values:
            number = _object(value, "pull list item").get("number")
            if not isinstance(number, int) or isinstance(number, bool):
                raise ValueError("pull list item number is missing")
            pull = self.get_pull(number)
            if label in pull.labels:
                pulls.append(pull)
        return tuple(pulls)

    def latest_label_event(self, number: int, label: str):
        from merge_queue_watchdog import LabelEvent

        values = self._get_pages(f"/issues/{number}/events?per_page=100")
        events: list[LabelEvent] = []
        for value in values:
            event = _object(value, "issue event")
            label_document = event.get("label")
            if event.get("event") != "labeled" or not isinstance(label_document, dict):
                continue
            if label_document.get("name") != label:
                continue
            event_id = event.get("id")
            if not isinstance(event_id, int) or isinstance(event_id, bool):
                raise ValueError("label event ID is missing")
            events.append(
                LabelEvent(event_id, _instant(event.get("created_at")).timestamp())
            )
        return max(events, key=lambda item: (item.created_at, item.event_id), default=None)

    def has_active_queue_run(self, number: int, since: float) -> bool:
        for status in ("queued", "in_progress"):
            values = self._get_pages(
                "/actions/workflows/merge-queue.yml/runs"
                f"?event=pull_request_target&status={status}&per_page=100",
                "workflow_runs",
            )
            for value in values:
                run = _object(value, "queue workflow run")
                created = _instant(run.get("created_at")).timestamp()
                pulls = run.get("pull_requests")
                if created < since or not isinstance(pulls, list):
                    continue
                if any(
                    _object(pull, "workflow pull request").get("number") == number
                    for pull in pulls
                ):
                    return True
        return False

    def list_review_comments(self, number: int) -> tuple[str, ...]:
        values = self._get_pages(f"/issues/{number}/comments?per_page=100")
        bodies: list[str] = []
        for value in values:
            body = _object(value, "pull review").get("body")
            if isinstance(body, str):
                bodies.append(body)
        return tuple(bodies)
