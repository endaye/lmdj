#!/usr/bin/env python3
"""Typed GitHub REST boundary for the LMDJ Integration Queue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import io
import json
import re
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
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


Transport = Callable[[HttpRequest], tuple[int, Mapping[str, str], bytes]]


def _urllib_transport(request: HttpRequest) -> tuple[int, Mapping[str, str], bytes]:
    urllib_request = Request(
        request.url,
        data=request.body,
        headers=dict(request.headers),
        method=request.method,
    )
    try:
        with urlopen(urllib_request, timeout=30) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


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
            return parse_queue_validation_json(_json(archive.read(names[0])))
    except zipfile.BadZipFile as error:
        raise ValueError("queue validation artifact is not a zip archive") from error


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
        request = HttpRequest(method, self._url(path), headers, body)
        attempts = 3 if method == "GET" else 1
        status, response_headers, response_body = 0, {}, b""
        for attempt in range(attempts):
            try:
                status, response_headers, response_body = self._transport(request)
            except (OSError, TimeoutError):
                if method != "GET" or attempt == attempts - 1:
                    raise
                self._sleeper(float(2 ** attempt))
                continue
            retryable = status >= 500 or status == 429 or (
                status == 403 and any(
                    key.lower() == "retry-after" for key in response_headers
                )
            )
            if not retryable or attempt == attempts - 1:
                break
            self._sleeper(float(2 ** attempt))
        if status not in expected:
            message = "unexpected response"
            try:
                document = _object(_json(response_body), "error response")
                if isinstance(document.get("message"), str):
                    message = document["message"]
            except ValueError:
                pass
            raise GitHubApiError(status, method, request.url, message)
        return status, response_headers, response_body

    def _get_object(self, path: str) -> dict[str, Any]:
        return _object(_json(self._request("GET", path)[2]), path)

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

    def get_pull(self, number: int) -> PullRequest:
        document = self._get_object(f"/pulls/{number}")
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

    def get_main_sha(self) -> str:
        document = self._get_object("/git/ref/heads/main")
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

    def is_ancestor(self, base: str, head: str) -> bool:
        document = self._get_object(f"/compare/{base}...{head}")
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

    def get_tree(self, sha: str) -> str:
        document = self._get_object(f"/git/commits/{sha}")
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
        for value in artifacts:
            artifact = _object(value, "artifact")
            if (
                isinstance(artifact.get("name"), str)
                and artifact["name"].startswith("queue-validation-")
                and artifact.get("expired") is False
            ):
                candidates.append(artifact)
        if len(candidates) != 1 or not isinstance(candidates[0].get("id"), int):
            raise ValueError("exactly one live queue validation artifact is required")
        _, _, artifact_body = self._request(
            "GET", f"/actions/artifacts/{candidates[0]['id']}/zip"
        )
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
            ticket=str(validation["queue_ticket"]),
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
            expected=(204,),
        )

    def create_review_comment(self, number: int, body: str) -> None:
        self._request(
            "POST", f"/pulls/{number}/reviews", {"body": body, "event": "COMMENT"},
            expected=(200,),
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
        values = self._get_pages(f"/pulls/{number}/reviews?per_page=100")
        bodies: list[str] = []
        for value in values:
            body = _object(value, "pull review").get("body")
            if isinstance(body, str):
                bodies.append(body)
        return tuple(bodies)
