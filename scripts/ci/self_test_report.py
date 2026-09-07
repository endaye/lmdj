#!/usr/bin/env python3
"""Collect self-test observations in deduplicated suite/class failure buckets.

The reporter runs from the default branch after a `Core CI` run completes.
Current-attempt request, skip and verdict artifacts distinguish explicit
self-tests from compatibility runs. Missing selected-batch evidence is an
infrastructure problem, never an implicit pass. The shared evidence consumer
validates the verdict against its trusted control revision policy.

Reporting uses positively observed write receipts, not an assumption that
negative lists are immediately consistent. An Issue is addressed by a stable
dedupe key (`suite id` + failure class; never a SHA or a date), carried as a
hidden marker in its body, and an observation by `run/attempt/suite/
fingerprint`, carried as a marker in the comment that recorded it. The same
observation re-sent -- a retry, a reconcile pass, a duplicate webhook -- finds
its marker and adds nothing. A closed Issue that recurs is reopened with the
new observation; a green batch closes nothing. The fingerprint describes job
conclusions, not extracted test IDs or log errors: one bucket may contain
different defects and maintainers may split them during triage.

Each POST is attempted only once. Unknown write outcomes get read-only
reconciliation, never another POST. An unresolved write stops this process.
In-process receipts prevent list regression from causing replacement writes;
they cannot provide cross-process exactly-once after a crash. An operator must
resolve an unknown write before starting another process to retry it.

The verdict is never altered by anything here. When the GitHub API refuses
(403, 429, 5xx past a bounded retry) the reporter exits non-zero with a
visible `reporting-error` and the failure report is retained for an explicit
retry; a red batch does not become a green summary because the reporter was
the thing that failed.

Everything that reaches GitHub goes through one small client so a test can
stand a strict fake in its place. The retry sleeps through an injected
callable; nothing here reads a clock.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import html
import io
import json
import os
import re
import sys
from typing import Protocol
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import self_test
from self_test_evidence import validate_verdict_document


# ---------------------------------------------------------------------------
# Configuration -- the small block the plan asks for, in the script.
# ---------------------------------------------------------------------------

#: The workflow whose completed runs may carry a self-test verdict.
WORKFLOW_NAME = "Core CI"
WORKFLOW_FILE = "ci.yml"
# Verified first deployed producer: PR #757's immutable squash commit. Use its
# committer time as a conservative scan floor (12:20:36Z); PR merged_at became
# visible at 12:20:37Z and is not the earliest possible main-ref observation.
# Time narrows recovery scans only; every run must also prove its control
# revision descends from this commit. Recent reruns cannot promote old code.
PRODUCER_REVISION = "22247897e9163a3f34e15f564bec133419d1f177"
PRODUCER_SCAN_SINCE = "2026-09-07T12:20:36Z"
#: Events a self-test batch may have. A pull_request or push run never carries
#: a verdict artifact today, and if one did it would not be a fixed-target
#: self-test, so it is refused rather than reported.
ALLOWED_EVENTS = frozenset({"schedule", "workflow_dispatch"})
#: Label every reporter-owned Issue carries; the reporter searches by it.
REPORT_LABEL = "self-test"
#: Who a new Issue is assigned to until a person triages it.
DEFAULT_ASSIGNEE = "endaye"
#: Suite failure classes the verdict may carry for a suite that did not pass.
FAILURE_CLASSES = ("test_failure", "infrastructure_failure", "blocked", "missing")
#: Batch-level keys that are not a suite.
BATCH_INVALID_KEY = "self-test-batch-invalid"
MISSING_KEY = "self-test-missing"
#: Bound on any log or diagnostic text copied into an Issue. The text is data
#: from a test run, not prose written for the Issue.
TEXT_LIMIT = 1200
#: Retry budget for a refused API call. Three tries with the injected sleep;
#: the delays are seconds and the caller may pass a no-op.
RETRY_DELAYS = (5.0, 20.0)
# Positive list visibility is the condition; elapsed time is never success.
WRITE_VISIBILITY_DELAYS = (1.0, 4.0, 10.0)
#: Bounded recovery within the producer's 30-day retention window. Every
#: entry point rechecks recent runs; reaching the cap is a visible error,
#: never a claim that all older observations have been reported.
RECONCILE_RUNS = 100
#: Artifact name the batch writes. The SHA is the fixed target, not the run's
#: head, so a manual batch for an older main revision is addressable by it.
VERDICT_ARTIFACT = re.compile(r"^self-test-verdict-(?P<target>[0-9a-f]{40})-(?P<run>[1-9][0-9]*)-(?P<attempt>[1-9][0-9]*)$")
SKIP_ARTIFACT = re.compile(r"^self-test-skip-(?P<target>[0-9a-f]{40})-(?P<run>[1-9][0-9]*)-(?P<attempt>[1-9][0-9]*)$")
VERDICT_FILE = "verdict.json"
VERDICT_LIMIT_BYTES = 1 << 20
EVIDENCE_SCHEMA = "lmdj.ci-self-test.v1"

_SHA = re.compile(r"^[0-9a-f]{40}$")
_KEY = re.compile(r"^[a-z][a-z0-9_-]*$")
_KEY_MARKER = "<!-- lmdj-self-test: key={key} -->"
_OBS_MARKER = "<!-- lmdj-self-test: key={key} obs={obs} -->"
_MARKER_SCAN = re.compile(r"<!-- lmdj-self-test: key=(?P<key>[a-z0-9_-]+)(?: obs=(?P<obs>[^ >]+))? -->")

#: Which suites carry a candidate-blocking severity when they fail as tests.
#: Everything else is medium; infrastructure and blocked are never high on
#: their own, because they say nothing about the product.
HIGH_SEVERITY_SUITES = frozenset({
    "core_ubuntu", "core_asan", "core_coverage", "core_macos", "package",
    "core_tsan_stress", "core_release_stress", "web_runtime_host", "creator",
})


def _diagnostic(why: str, remedy: str) -> str:
    return f"why: {why}; remedy: {remedy}"


class ReportingError(RuntimeError):
    """The reporter could not do its job. The verdict it was reporting stands."""


class WriteVisibilityError(ReportingError):
    """Stop the whole reporter: a write or its identity remains unresolved."""


class GitHubApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub API {status}: {message}")
        self.status = status


# ---------------------------------------------------------------------------
# The GitHub surface the reporter touches, and its real implementation.
# ---------------------------------------------------------------------------


class GitHubApi(Protocol):
    def get_run(self, run_id: int) -> Mapping[str, object]: ...
    def get_workflow(self) -> Mapping[str, object]: ...
    def get_policy(self, revision: str) -> Mapping[str, object]: ...
    def compare(self, base: str, head: str) -> Mapping[str, object]: ...
    def list_jobs(self, run_id: int, attempt: int) -> Sequence[Mapping[str, object]]: ...
    def list_runs(self, workflow_file: str, *, event: str, created: str | None,
                  per_page: int, status: str | None = "completed") -> Sequence[Mapping[str, object]]: ...
    def list_artifacts(self, run_id: int) -> Sequence[Mapping[str, object]]: ...
    def download_artifact(self, artifact_id: int) -> bytes: ...
    def list_issues(self, *, label: str, state: str) -> Sequence[Mapping[str, object]]: ...
    def list_comments(self, number: int) -> Sequence[Mapping[str, object]]: ...
    def create_issue(self, *, title: str, body: str, labels: Sequence[str],
                     assignees: Sequence[str]) -> Mapping[str, object]: ...
    def create_comment(self, number: int, body: str) -> Mapping[str, object]: ...
    def set_issue_state(self, number: int, state: str) -> Mapping[str, object]: ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class SafeDownloadRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ReportingError("artifact redirect must use HTTPS")
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header("Authorization")
        return redirected


class UrllibGitHubApi:
    """The one client. Every method is one documented REST endpoint."""

    def __init__(self, repository: str, token: str, *, api_root: str = "https://api.github.com") -> None:
        if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repository):
            raise ReportingError(_diagnostic(f"repository {repository!r} is not owner/name",
                                             "pass github.repository"))
        if not token:
            raise ReportingError(_diagnostic("GITHUB_TOKEN is empty",
                                             "the workflow passes secrets.GITHUB_TOKEN to the reporter step"))
        self.repository = repository
        self._token = token
        self._root = api_root.rstrip("/")

    def _request(self, method: str, path: str, *, body: object | None = None,
                 raw: bool = False) -> object:
        url = path if path.startswith("http") else f"{self._root}{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "lmdj-self-test-report",
            **({"Cache-Control": "no-cache"} if method == "GET" else {}),
            **({"Content-Type": "application/json"} if data is not None else {}),
        })
        try:
            # Never let an API redirect forward the issues-write token.
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                payload = response.read(VERDICT_LIMIT_BYTES * 8 + 1)
        except urllib.error.HTTPError as error:
            if raw and error.code in (301, 302, 303, 307, 308):
                location = error.headers.get("Location", "")
                if urllib.parse.urlsplit(location).scheme != "https":
                    raise ReportingError("artifact download Location must use HTTPS") from error
                download = urllib.request.Request(location, headers={"User-Agent": "lmdj-self-test-report"})
                try:
                    with urllib.request.build_opener(SafeDownloadRedirect()).open(download, timeout=30) as response:
                        payload = response.read(VERDICT_LIMIT_BYTES * 8 + 1)
                except (urllib.error.URLError, TimeoutError, OSError) as failure:
                    raise GitHubApiError(0, "artifact download failed") from failure
                if len(payload) > VERDICT_LIMIT_BYTES * 8:
                    raise ReportingError("artifact download exceeds size limit")
                return payload
            raise GitHubApiError(error.code, error.reason or "") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise GitHubApiError(0, "GitHub request transport failure") from error
        if len(payload) > VERDICT_LIMIT_BYTES * 8:
            raise ReportingError("GitHub response exceeds size limit")
        if raw:
            return payload
        return json.loads(payload.decode("utf-8")) if payload else {}

    def _repo(self, path: str) -> str:
        return f"/repos/{self.repository}{path}"

    def get_run(self, run_id: int) -> Mapping[str, object]:
        document = self._request("GET", self._repo(f"/actions/runs/{int(run_id)}"))
        assert isinstance(document, dict)
        return document

    def get_workflow(self) -> Mapping[str, object]:
        return self._request("GET", self._repo("/actions/workflows/ci.yml"))

    def get_policy(self, revision: str) -> Mapping[str, object]:
        document = self._request("GET", self._repo(
            f"/contents/scripts/ci/self_test_policy.json?ref={revision}"))
        return json.loads(base64.b64decode(document["content"]).decode("utf-8"))

    def compare(self, base: str, head: str) -> Mapping[str, object]:
        return self._request("GET", self._repo(f"/compare/{base}...{head}"))

    def list_jobs(self, run_id: int, attempt: int) -> Sequence[Mapping[str, object]]:
        jobs = []
        for page in range(1, 11):
            document = self._request("GET", self._repo(
                f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}"))
            batch = document.get("jobs", [])
            jobs.extend(batch)
            if len(batch) < 100:
                return jobs
        raise ReportingError("job pagination limit reached; explicit investigation required")

    def list_runs(self, workflow_file: str, *, event: str, created: str | None,
                  per_page: int, status: str | None = "completed") -> Sequence[Mapping[str, object]]:
        query = {"event": event, "per_page": str(int(per_page)), "branch": "main"}
        if status:
            query["status"] = status
        if created:
            query["created"] = created
        document = self._request(
            "GET", self._repo(f"/actions/workflows/{workflow_file}/runs?{urllib.parse.urlencode(query)}"))
        assert isinstance(document, dict)
        runs = document.get("workflow_runs")
        return list(runs) if isinstance(runs, list) else []

    def list_artifacts(self, run_id: int) -> Sequence[Mapping[str, object]]:
        document = self._request("GET", self._repo(f"/actions/runs/{int(run_id)}/artifacts?per_page=100"))
        assert isinstance(document, dict)
        artifacts = document.get("artifacts")
        return list(artifacts) if isinstance(artifacts, list) else []

    def download_artifact(self, artifact_id: int) -> bytes:
        payload = self._request("GET", self._repo(f"/actions/artifacts/{int(artifact_id)}/zip"), raw=True)
        assert isinstance(payload, bytes)
        return payload

    def list_issues(self, *, label: str, state: str) -> Sequence[Mapping[str, object]]:
        issues: list[Mapping[str, object]] = []
        for page in range(1, 11):
            query = urllib.parse.urlencode({"labels": label, "state": state, "per_page": "100", "page": str(page)})
            document = self._request("GET", self._repo(f"/issues?{query}"))
            if not isinstance(document, list) or any(not isinstance(item, dict) for item in document):
                raise ReportingError(_diagnostic("issue list response is malformed", "inspect the API response; do not treat it as an empty dedupe set"))
            if not document:
                return issues
            issues.extend(item for item in document if isinstance(item, dict) and "pull_request" not in item)
            if len(document) < 100:
                return issues
        raise ReportingError("issue pagination limit reached; refusing an incomplete dedupe lookup")

    def list_comments(self, number: int) -> Sequence[Mapping[str, object]]:
        comments: list[Mapping[str, object]] = []
        for page in range(1, 11):
            document = self._request(
                "GET", self._repo(f"/issues/{int(number)}/comments?per_page=100&page={page}"))
            if not isinstance(document, list) or any(not isinstance(item, dict) for item in document):
                raise ReportingError(_diagnostic("comment list response is malformed", "inspect the API response; do not treat it as an empty observation set"))
            if not document:
                return comments
            comments.extend(item for item in document if isinstance(item, dict))
            if len(document) < 100:
                return comments
        raise ReportingError("comment pagination limit reached; refusing an incomplete dedupe lookup")

    def create_issue(self, *, title: str, body: str, labels: Sequence[str],
                     assignees: Sequence[str]) -> Mapping[str, object]:
        document = self._request("POST", self._repo("/issues"), body={
            "title": title, "body": body, "labels": list(labels), "assignees": list(assignees)})
        assert isinstance(document, dict)
        return document

    def create_comment(self, number: int, body: str) -> Mapping[str, object]:
        document = self._request("POST", self._repo(f"/issues/{int(number)}/comments"), body={"body": body})
        assert isinstance(document, dict)
        return document

    def set_issue_state(self, number: int, state: str) -> Mapping[str, object]:
        if state not in ("open", "closed"):
            raise ValueError(f"issue state {state!r}")
        document = self._request("PATCH", self._repo(f"/issues/{int(number)}"), body={"state": state})
        assert isinstance(document, dict)
        return document


def with_retry(call: Callable[[], object], *, sleep: Callable[[float], None],
               delays: Sequence[float] = RETRY_DELAYS) -> object:
    """Retry a refused call on 429 and 5xx only. 403 and 404 are answers."""
    attempt = 0
    while True:
        try:
            return call()
        except GitHubApiError as error:
            retryable = error.status == 429 or error.status >= 500 or error.status == 0
            if not retryable or attempt >= len(delays):
                raise
            sleep(delays[attempt])
            attempt += 1


# ---------------------------------------------------------------------------
# Reading a verdict out of a run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunView:
    id: int
    attempt: int
    event: str
    workflow_path: str
    display_name: str
    head_sha: str
    status: str
    conclusion: str | None
    html_url: str
    repository: str
    workflow_id: int
    head_branch: str


def parse_run(document: Mapping[str, object]) -> RunView:
    repository = document.get("repository")
    full_name = repository.get("full_name") if isinstance(repository, dict) else None
    return RunView(
        id=int(document["id"]),  # type: ignore[arg-type]
        attempt=int(document.get("run_attempt", 1)),  # type: ignore[arg-type]
        event=str(document.get("event", "")),
        workflow_path=str(document.get("path", "")),
        display_name=str(document.get("name", "")),
        head_sha=str(document.get("head_sha", "")),
        status=str(document.get("status", "")),
        conclusion=(str(document["conclusion"]) if document.get("conclusion") else None),
        html_url=str(document.get("html_url", "")),
        repository=str(full_name or ""),
        workflow_id=int(document.get("workflow_id", 0)),
        head_branch=str(document.get("head_branch", "")),
    )


def classify_run(run: RunView, *, repository: str) -> str | None:
    """Why this run is not a self-test candidate, or None when it may be one."""
    if run.repository != repository:
        return f"run {run.id} belongs to {run.repository}, not {repository}"
    # REST run.name may be the dynamic run-name, not workflow metadata name.
    # Display text has no authority; report_run binds the stable workflow ID
    # and path through the workflow endpoint after these candidate checks.
    if run.workflow_path != f".github/workflows/{WORKFLOW_FILE}":
        return f"run {run.id} uses {run.workflow_path}, not .github/workflows/{WORKFLOW_FILE}"
    if run.event not in ALLOWED_EVENTS:
        return f"run {run.id} was a {run.event} run; self-tests are {sorted(ALLOWED_EVENTS)}"
    if run.status != "completed":
        return f"run {run.id} is {run.status}, not completed"
    if run.head_branch != "main" or not _SHA.fullmatch(run.head_sha):
        return f"run {run.id} does not identify trusted main control code"
    return None


def find_verdict_artifact(artifacts: Iterable[Mapping[str, object]], *, run: RunView,
                          pattern: re.Pattern = VERDICT_ARTIFACT) -> tuple[int, str] | None:
    """The (artifact id, target SHA) of the verdict artifact, or None."""
    matches = []
    for artifact in artifacts:
        name = str(artifact.get("name", ""))
        match = pattern.fullmatch(name)
        if (match and int(match["run"]) == run.id and int(match["attempt"]) == run.attempt
                and not artifact.get("expired", False)):
            matches.append((int(artifact["id"]), match["target"]))
    if len(matches) > 1:
        raise ReportingError("multiple artifacts claim the same run/attempt; refuse ambiguous evidence")
    return matches[0] if matches else None


def read_verdict_zip(payload: bytes, *, filename: str = VERDICT_FILE) -> Mapping[str, object]:
    """Extract verdict.json from an artifact zip without trusting its names."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as error:
        raise ReportingError(_diagnostic(f"verdict artifact is not a zip ({error})",
                                         "the batch uploads verdict.json with actions/upload-artifact")) from error
    with archive:
        entries = archive.infolist()
        if len(entries) != 1 or entries[0].filename != filename:
            raise ReportingError(f"unsafe path or unexpected artifact entries; expected exactly {filename}")
        for info in entries:
            name = info.filename
            parts = name.replace("\\", "/").split("/")
            if name.startswith("/") or ".." in parts or any(part == "" for part in parts[:-1]):
                raise ReportingError(_diagnostic(
                    f"verdict artifact contains an unsafe path {name!r}",
                    "the batch writes verdict.json at the artifact root; refuse anything else"))
            if parts[-1] != filename:
                continue
            if info.file_size > VERDICT_LIMIT_BYTES:
                raise ReportingError(_diagnostic(
                    f"{VERDICT_FILE} is {info.file_size} bytes",
                    f"a verdict is a small JSON document; refuse anything over {VERDICT_LIMIT_BYTES} bytes"))
            data = archive.read(info)
            try:
                document = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ReportingError(_diagnostic(f"{VERDICT_FILE} is not JSON ({error})",
                                                 "the batch writes the aggregate document verbatim")) from error
            if not isinstance(document, dict):
                raise ReportingError(_diagnostic(f"{VERDICT_FILE} is not an object", "write the verdict document"))
            return document
    raise ReportingError(_diagnostic(f"verdict artifact has no {VERDICT_FILE}",
                                     "the batch names the file verdict.json at the artifact root"))


@dataclass(frozen=True)
class SuiteView:
    id: str
    status: str
    jobs: Mapping[str, str]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class VerdictView:
    status: str
    target_revision: str
    run_id: int
    run_attempt: int
    request_kind: str
    policy_revision: str
    evidence_digest: str
    suites: tuple[SuiteView, ...]
    diagnostics: tuple[str, ...]
    superseded_by: str | None

    @property
    def failed_suites(self) -> tuple[SuiteView, ...]:
        return tuple(suite for suite in self.suites if suite.status != "passed")

    @property
    def not_run(self) -> tuple[str, ...]:
        return tuple(suite.id for suite in self.suites if suite.status in ("blocked", "missing"))


def document_digest(document: object) -> str:
    return self_test.digest_of(document)


def validate_identity(identity: object, *, run: RunView, target: str) -> Mapping[str, object]:
    if not isinstance(identity, dict):
        raise ReportingError("verdict carries no identity")
    if (identity.get("evidence_schema") != EVIDENCE_SCHEMA
            or identity.get("control_revision") != run.head_sha
            or identity.get("target_revision") != target or not _SHA.fullmatch(target)
            or identity.get("run_id") != run.id or identity.get("run_attempt") != run.attempt
            or type(identity.get("run_id")) is not int or type(identity.get("run_attempt")) is not int
            or identity.get("request_kind") not in ({"schedule"} if run.event == "schedule" else {"node", "candidate"})):
        raise ReportingError("verdict identity is not bound to the trusted control/target/run/attempt/event")
    return identity


def parse_verdict(document: Mapping[str, object], *, run: RunView, target: str,
                  policy: Mapping[str, object] | None = None) -> VerdictView:
    """Accept only a verdict that is evidence for exactly this run and target."""
    identity = validate_identity(document.get("identity"), run=run, target=target)
    if policy is None:
        raise ReportingError("the trusted control revision policy is required")
    try:
        parsed_policy = self_test.parse_policy(policy)
        expected = self_test.Identity(
            EVIDENCE_SCHEMA, identity["request_kind"], run.head_sha, target,
            run.id, run.attempt, parsed_policy.revision)
        validate_verdict_document(document, policy=parsed_policy, expected_identity=expected)
    except ValueError as error:
        raise ReportingError(str(error)) from error
    # The shared validator above owns the schema and full-suite contract;
    # this layer only projects its validated document for issue rendering.
    suites = tuple(SuiteView(raw["id"], raw["status"], raw["jobs"], tuple(raw["diagnostics"]))
                   for raw in document["suites"])
    return VerdictView(
        status=document["status"], target_revision=target, run_id=run.id, run_attempt=run.attempt,
        request_kind=identity["request_kind"], policy_revision=identity["policy_revision"],
        evidence_digest=document["evidence_digest"], suites=suites,
        diagnostics=tuple(document["diagnostics"]), superseded_by=document["superseded_by"],
    )


# ---------------------------------------------------------------------------
# From a verdict to the reports it owes
# ---------------------------------------------------------------------------


def sanitize(text: str, limit: int = TEXT_LIMIT) -> str:
    """Log text as data: control characters out, HTML escaped, bounded."""
    cleaned = "".join(ch if ch == "\n" or ch == "\t" or ord(ch) >= 32 else " " for ch in text)
    cleaned = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", cleaned)
    cleaned = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "[REDACTED]", cleaned)
    cleaned = cleaned.replace("`", "ˋ")  # a fence cannot be closed from inside the text
    if len(cleaned) > limit:
        cleaned = cleaned[:limit] + f"\n… [{len(text) - limit} more characters truncated]"
    return html.escape(cleaned, quote=False)


def fingerprint(suite_id: str, failure_class: str, jobs: Mapping[str, str]) -> str:
    material = json.dumps([suite_id, failure_class, sorted(jobs.items())], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def severity_of(suite_id: str, failure_class: str) -> str:
    if failure_class == "test_failure" and suite_id in HIGH_SEVERITY_SUITES:
        return "high"
    if failure_class == "test_failure":
        return "medium"
    if failure_class == "infrastructure_failure":
        return "medium"
    return "low"


@dataclass(frozen=True)
class Report:
    key: str
    title: str
    observation: str
    severity: str
    labels: tuple[str, ...]
    summary: str
    detail: str

    @property
    def key_marker(self) -> str:
        return _KEY_MARKER.format(key=self.key)

    @property
    def observation_marker(self) -> str:
        return _OBS_MARKER.format(key=self.key, obs=self.observation)

    def issue_body(self, assignee: str) -> str:
        return "\n".join([
            self.key_marker,
            f"## {self.title}",
            "",
            "Filed by `self-test-report.yml` from a self-test verdict. This Issue is a suite/class failure bucket:",
            "later batches in the same suite and failure class add observations here, including potentially different defects.",
            "Real test IDs and log-error fingerprints are not yet extracted; a maintainer may split this bucket into defect Issues.",
            f"Default assignee `@{assignee}` until triaged. Severity **{self.severity}** — high severity affects",
            "release-candidate eligibility for the targets it was observed on; it never blocks ordinary Pull Request merges.",
            "",
            "### Triage",
            "",
            "- [ ] product regression / test flake / infrastructure — pick one and relabel",
            "- [ ] reproduce with a new dispatch for the same target; after fixing, explicitly dispatch the fixed SHA",
            "",
            self.comment_body(first=True),
        ])

    def comment_body(self, *, first: bool = False) -> str:
        heading = "### First observation" if first else "### New observation"
        return "\n".join([self.observation_marker, heading, "", self.summary, "", self.detail])


def _run_link(run: RunView) -> str:
    suffix = f"/attempts/{run.attempt}" if run.attempt > 1 else ""
    return f"{run.html_url}{suffix}" if run.html_url else f"run {run.id} attempt {run.attempt}"


def plan_reports(verdict: VerdictView, run: RunView) -> tuple[Report, ...]:
    """Every Issue-level report a verdict owes. Passed and superseded owe none."""
    if verdict.status in ("passed", "superseded"):
        return ()
    observation_base = f"{verdict.run_id}/{verdict.run_attempt}"
    link = _run_link(run)
    common = [
        f"- Target: `{verdict.target_revision}` ({verdict.request_kind} request)",
        f"- Run: {link} (run {verdict.run_id}, attempt {verdict.run_attempt})",
        f"- Policy revision: `{verdict.policy_revision[:12]}` · evidence digest: `{verdict.evidence_digest[:12]}`",
    ]
    if verdict.status == "invalid":
        detail = "\n".join(["```text", *(sanitize(d) for d in verdict.diagnostics), "```"])
        summary = "\n".join([
            *common,
            "- Classification: **infrastructure** — the batch's evidence was not evidence for its own identity",
            "- Not run: the whole batch counts as not proven",
            f"- Severity: {severity_of('batch', 'infrastructure_failure')}",
            "- Next step: read the diagnostics; after fixing the producer, start a new dispatch for the same target (not a run rerun)",
        ])
        return (Report(
            key=BATCH_INVALID_KEY,
            title="self-test: batch verdict invalid",
            observation=f"{observation_base}/batch/{fingerprint('batch', 'invalid', {})}",
            severity=severity_of("batch", "infrastructure_failure"),
            labels=(REPORT_LABEL, "type:bug", "area:ci-release"),
            summary=summary, detail=detail,
        ),)

    reports: list[Report] = []
    not_run = ", ".join(verdict.not_run) or "none"
    for suite in verdict.failed_suites:
        failure_class = suite.status
        key = f"self-test-{suite.id}-{failure_class}".replace("_", "-")
        print_class = failure_class.replace("_", " ")
        severity = severity_of(suite.id, failure_class)
        jobs = "\n".join(f"| `{job}` | {sanitize(status, 80)} |" for job, status in sorted(suite.jobs.items()))
        detail = "\n".join([
            "| job | conclusion |", "|---|---|", jobs, "",
            "```text", *(sanitize(d) for d in suite.diagnostics), "```",
        ])
        summary = "\n".join([
            *common,
            f"- Suite: `{suite.id}` · class: **{print_class}**",
            f"- Not run in this batch: {not_run}",
            f"- Severity: {severity}",
            "- Next step: " + {
                "test_failure": "reproduce on the target SHA; decide product regression vs flake before relabeling",
                "infrastructure_failure": "check the host or artifact path named in the diagnostics; start a new dispatch for the same target (not a run rerun)",
                "blocked": "fix the job this one waited on; this suite has no result of its own yet",
                "missing": "find out whether the job ran at all; a missing result is never a pass",
            }[failure_class],
        ])
        area = "area:ci-release" if failure_class != "test_failure" else "area:core"
        reports.append(Report(
            key=key,
            title=f"self-test: {suite.id} {print_class}",
            observation=f"{observation_base}/{suite.id}/{fingerprint(suite.id, failure_class, suite.jobs)}",
            severity=severity,
            labels=(REPORT_LABEL, "type:bug", area),
            summary=summary, detail=detail,
        ))
    return tuple(reports)


# ---------------------------------------------------------------------------
# Applying a report against the Issue tracker, idempotently
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    key: str
    action: str  # created | commented | reopened | duplicate
    issue_number: int | None


def _trusted_marker_author(document: Mapping[str, object]) -> bool:
    """Only the workflow's GITHUB_TOKEN bot can publish reporter state.

    A user may quote our hidden markers in an Issue or comment. Those bytes
    are not evidence that this reporter wrote the bucket or observation.
    """
    user = document.get("user")
    return (isinstance(user, dict) and user.get("login") == "github-actions[bot]"
            and user.get("type") == "Bot")


def _find_issue(api: GitHubApi, key: str, *, sleep: Callable[[float], None]) -> Mapping[str, object] | None:
    marker = _KEY_MARKER.format(key=key)
    issues = with_retry(lambda: api.list_issues(label=REPORT_LABEL, state="all"), sleep=sleep)
    if not isinstance(issues, list) or any(not isinstance(issue, dict) for issue in issues):
        raise ReportingError("why: malformed issue list; remedy: inspect the API response before deduplication")
    matching = [issue for issue in issues if _trusted_marker_author(issue)
                and marker in str(issue.get("body") or "")]
    if not matching:
        return None
    if len(matching) != 1 or not _positive_id(matching[0].get("number")):
        raise WriteVisibilityError(_diagnostic(f"ambiguous or invalid trusted issue bucket for {key}",
                                              "manually reconcile duplicate buckets; never silently select one"))
    return matching[0]


def _positive_id(value: object) -> bool:
    return type(value) is int and value > 0


def _observation_receipt(api: GitHubApi, issue: Mapping[str, object], report: Report,
                         *, sleep: Callable[[float], None]) -> tuple[int, int | None] | None:
    """Return the unique trusted (issue number, comment ID or issue-body None)."""
    matches: list[int | None] = []
    if _trusted_marker_author(issue) and report.observation_marker in str(issue.get("body") or ""):
        if str(issue["body"]).count(report.observation_marker) != 1:
            raise WriteVisibilityError("why: duplicate issue observation markers; remedy: manually reconcile this bucket")
        matches.append(None)
    comments = with_retry(lambda: api.list_comments(int(issue["number"])), sleep=sleep)  # type: ignore[arg-type]
    if not isinstance(comments, list) or any(not isinstance(comment, dict) for comment in comments):
        raise ReportingError("why: malformed comment list; remedy: inspect the API response before deduplication")
    for comment in comments:
        if _trusted_marker_author(comment) and report.observation_marker in str(comment.get("body") or ""):
            if (not _positive_id(comment.get("id"))
                    or str(comment["body"]).count(report.observation_marker) != 1):
                raise WriteVisibilityError("why: invalid trusted comment receipt; remedy: inspect its exact ID and marker")
            matches.append(comment["id"])
    if len(matches) > 1:
        raise WriteVisibilityError("why: duplicate trusted observation receipts; remedy: manually reconcile the duplicate comments")
    return (int(issue["number"]), matches[0]) if matches else None


def _observation_recorded(api: GitHubApi, issue: Mapping[str, object], report: Report,
                          *, sleep: Callable[[float], None]) -> bool:
    return _observation_receipt(api, issue, report, sleep=sleep) is not None


@dataclass
class _WriteState:
    buckets: dict[str, int] = field(default_factory=dict)
    observations: dict[tuple[str, str], tuple[int, int | None]] = field(default_factory=dict)
    unresolved: str | None = None


def _write_state(api: GitHubApi) -> _WriteState:
    state = getattr(api, "_self_test_write_state", None)
    if state is None:
        state = _WriteState()
        setattr(api, "_self_test_write_state", state)
    return state


def _wait_for_receipt(api: GitHubApi, report: Report, *, state: _WriteState,
                      expected: tuple[int, int | None] | None,
                      sleep: Callable[[float], None]) -> tuple[int, int | None]:
    """Only reads here. A negative or stale read never authorizes another POST."""
    for delay in (0.0, *WRITE_VISIBILITY_DELAYS):
        if delay:
            sleep(delay)
        issue = _find_issue(api, report.key, sleep=sleep)
        if issue is None:
            continue
        known_bucket = state.buckets.get(report.key)
        if known_bucket is not None and issue["number"] != known_bucket:
            raise WriteVisibilityError("why: trusted bucket changed after receipt; remedy: reconcile exact issue IDs manually")
        receipt = _observation_receipt(api, issue, report, sleep=sleep)
        if receipt is None:
            continue
        if expected is not None and receipt != expected:
            raise WriteVisibilityError("why: visible observation differs from the acknowledged write ID; remedy: inspect exact issue/comment receipts")
        state.buckets[report.key] = receipt[0]
        state.observations[(report.key, report.observation)] = receipt
        return receipt
    raise WriteVisibilityError(_diagnostic(
        f"write visibility unresolved for key={report.key} obs={report.observation}; expected={expected}",
        "stop automatic reporting; inspect the exact run, issue/comment IDs and markers before an operator retries; "
        "a negative list is not proof that the POST failed and no second POST was sent"))


def _post_once(api: GitHubApi, report: Report, *, state: _WriteState,
               issue_number: int | None, assignee: str,
               sleep: Callable[[float], None]) -> tuple[int, bool]:
    """POST once, then require an actual unique receipt in the dedupe read path."""
    state.unresolved = f"key={report.key} obs={report.observation}"
    expected = None
    acknowledged = False
    try:
        try:
            response = (api.create_issue(title=report.title, body=report.issue_body(assignee),
                                         labels=report.labels, assignees=(assignee,))
                        if issue_number is None else api.create_comment(issue_number, report.comment_body()))
            id_key = "number" if issue_number is None else "id"
            if (isinstance(response, dict) and _positive_id(response.get(id_key))
                    and _trusted_marker_author(response)
                    and str(response.get("body") or "").count(report.observation_marker) == 1
                    and (issue_number is not None or report.key_marker in str(response.get("body") or ""))):
                expected = ((response["number"], None) if issue_number is None else (issue_number, response["id"]))
                state.buckets[report.key] = expected[0]
                acknowledged = True
        except GitHubApiError as error:
            if error.status != 0 and error.status < 500:
                state.unresolved = None  # explicit refusal, still no POST retry
                raise
            # Unknown outcome: a read-only lookup may recover it, never re-POST.
        except (ValueError, TypeError, KeyError, AssertionError):
            # Malformed successful response may follow a persisted write.
            pass
        receipt = _wait_for_receipt(api, report, state=state, expected=expected, sleep=sleep)
        state.unresolved = None
        return receipt[0], acknowledged
    except (ReportingError, GitHubApiError, ValueError, TypeError, KeyError) as error:
        if state.unresolved is not None:
            if isinstance(error, WriteVisibilityError):
                raise
            raise WriteVisibilityError(_diagnostic(
                f"unresolved write {state.unresolved}: {error}",
                "halt this reporter/reconcile process; manually verify persisted markers before any new-process retry")) from error
        raise


def apply_report(api: GitHubApi, report: Report, *, assignee: str,
                 sleep: Callable[[float], None]) -> Outcome:
    try:
        return _apply_report(api, report, assignee=assignee, sleep=sleep)
    except (ReportingError, GitHubApiError, ValueError, TypeError, KeyError) as error:
        state = _write_state(api)
        if isinstance(error, WriteVisibilityError) or state.unresolved is not None:
            state.unresolved = state.unresolved or f"unsafe bucket key={report.key} obs={report.observation}"
            if isinstance(error, WriteVisibilityError):
                raise
            raise WriteVisibilityError(_diagnostic(str(error),
                                                  "stop all reporting; manually verify this write/bucket before retry")) from error
        raise


def _apply_report(api: GitHubApi, report: Report, *, assignee: str,
                  sleep: Callable[[float], None]) -> Outcome:
    state = _write_state(api)
    if state.unresolved is not None:
        raise WriteVisibilityError(_diagnostic(f"prior write remains unresolved: {state.unresolved}",
                                              "stop; manually reconcile it before any new-process retry"))
    issue = _find_issue(api, report.key, sleep=sleep)
    if issue is None and report.key in state.buckets:
        state.unresolved = f"known bucket disappeared: {report.key} issue={state.buckets[report.key]}"
        for delay in WRITE_VISIBILITY_DELAYS:
            sleep(delay)
            issue = _find_issue(api, report.key, sleep=sleep)
            if issue is not None:
                break
        if issue is None:
            raise WriteVisibilityError("why: known issue remains invisible in dedupe list; remedy: inspect its exact ID; never create a replacement")
        state.unresolved = None
    if issue is None:
        number, acknowledged = _post_once(api, report, state=state, issue_number=None,
                                         assignee=assignee, sleep=sleep)
        return Outcome(report.key, "created" if acknowledged else "duplicate", number)
    number = int(issue["number"])  # type: ignore[arg-type]
    if report.key in state.buckets and state.buckets[report.key] != number:
        raise WriteVisibilityError("why: bucket ID changed within this process; remedy: reconcile exact issue IDs")
    state.buckets[report.key] = number
    observed = _observation_receipt(api, issue, report, sleep=sleep)
    known = state.observations.get((report.key, report.observation))
    if observed is not None:
        if known is not None and known != observed:
            raise WriteVisibilityError("why: observation ID changed within this process; remedy: reconcile exact comment IDs")
        state.observations[(report.key, report.observation)] = observed
        return Outcome(report.key, "duplicate", number)
    if known is not None:
        state.unresolved = f"known observation disappeared: {report.key} obs={report.observation}"
        _wait_for_receipt(api, report, state=state, expected=known, sleep=sleep)
        state.unresolved = None
        return Outcome(report.key, "duplicate", number)
    action = "commented"
    if str(issue.get("state")) == "closed":
        with_retry(lambda: api.set_issue_state(number, "open"), sleep=sleep)
        action = "reopened"
    number, acknowledged = _post_once(api, report, state=state, issue_number=number,
                                     assignee=assignee, sleep=sleep)
    return Outcome(report.key, action if acknowledged else "duplicate", number)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class RunReport:
    run_id: int
    skipped: str | None = None
    verdict_status: str | None = None
    target: str | None = None
    outcomes: list[Outcome] = field(default_factory=list)
    error: str | None = None


def _batch_problem(run: RunView, why: str) -> tuple[RunReport, tuple[Report, ...]]:
    report = Report(
        key="self-test-batch-incomplete", title="self-test: batch evidence incomplete",
        observation=f"{run.id}/{run.attempt}/batch/incomplete", severity="medium",
        labels=(REPORT_LABEL, "type:bug", "area:ci-release"),
        summary=f"- Run: {_run_link(run)}\n- Control revision: `{run.head_sha}`\n"
                "- Target: unproven; no candidate result is inferred from the control revision\n"
                "- Classification: infrastructure failure\n- Not run: suite coverage is unproven\n"
                "- Next step: inspect resolver, job and artifact failures; dispatch a fresh exact-target batch",
        detail="```text\n" + sanitize(why) + "\n```",
    )
    result = RunReport(run.id, verdict_status="incomplete")
    return result, (report,)


def report_run(api: GitHubApi, run_id: int, *, repository: str, assignee: str,
               sleep: Callable[[float], None]) -> RunReport:
    """Legacy writer retained until the atomic T5 workflow cutover."""
    result, planned = _plan_run(api, run_id, repository=repository, sleep=sleep)
    for report in planned:
        result.outcomes.append(apply_report(api, report, assignee=assignee, sleep=sleep))
    return result


def plan_run(api: GitHubApi, run_id: int, *, attempt: int, repository: str,
             sleep: Callable[[float], None]) -> tuple[RunReport, tuple[Report, ...]]:
    """Read one exact completed legacy attempt; never perform a business write.

    The live workflow still uses report_run until T5. New callers must persist
    these reports through report_outbox, not invoke apply_report directly.
    """
    if type(run_id) is not int or run_id <= 0 or type(attempt) is not int or attempt <= 0:
        raise ReportingError(_diagnostic("legacy report lacks an exact run/attempt", "supply positive integer run-id and attempt"))
    return _plan_run(api, run_id, repository=repository, sleep=sleep, attempt=attempt)


def _plan_run(api: GitHubApi, run_id: int, *, repository: str,
              sleep: Callable[[float], None], attempt: int | None = None) -> tuple[RunReport, tuple[Report, ...]]:
    result = RunReport(run_id)
    run_document = with_retry(lambda: api.get_run(run_id), sleep=sleep)
    assert isinstance(run_document, dict)
    run = parse_run(run_document)
    if run.id != run_id or (attempt is not None and run.attempt != attempt):
        raise ReportingError(_diagnostic("legacy run/attempt differs from the requested identity", "inspect the exact completed attempt; never combine a later rerun with older artifacts"))
    reason = classify_run(run, repository=repository)
    if reason is not None:
        result.skipped = reason
        return result, ()
    workflow = with_retry(api.get_workflow, sleep=sleep)
    if (workflow.get("id") != run.workflow_id or workflow.get("path") != run.workflow_path):
        result.skipped = "run workflow identity does not match the trusted Core CI workflow"
        return result, ()
    control_history = with_retry(lambda: api.compare(run.head_sha, "main"), sleep=sleep)
    if control_history.get("status") not in ("ahead", "identical"):
        result.skipped = "control revision is not in main history"
        return result, ()
    producer_history = with_retry(lambda: api.compare(PRODUCER_REVISION, run.head_sha), sleep=sleep)
    if producer_history.get("status") == "behind":
        result.skipped = f"control revision predates self-test producer {PRODUCER_REVISION[:12]}"
        return result, ()
    if producer_history.get("status") not in ("ahead", "identical"):
        result.error = _diagnostic(
            "control revision has no verified ancestry from the deployed self-test producer "
            f"(compare status={producer_history.get('status')!r})",
            "verify the producer boundary and GitHub ancestry response, then retry this run's report")
        return result, ()
    artifacts = with_retry(lambda: api.list_artifacts(run.id), sleep=sleep)
    assert isinstance(artifacts, list)
    found = find_verdict_artifact(artifacts, run=run)
    if found is None:
        skipped = find_verdict_artifact(artifacts, run=run, pattern=SKIP_ARTIFACT)
        if skipped:
            payload = with_retry(lambda: api.download_artifact(skipped[0]), sleep=sleep)
            skip = read_verdict_zip(payload, filename="skip.json")
            validate_identity(skip.get("identity"), run=run, target=skipped[1])
            if run.event != "schedule" or skip.get("action") != "skip":
                raise ReportingError("only a scheduled batch can carry an expected skip record")
            ancestry = with_retry(lambda: api.compare(skipped[1], "main"), sleep=sleep)
            if ancestry.get("status") not in ("ahead", "identical"):
                raise ReportingError("skip target is not in current main history")
            result.skipped = "verified unchanged-target schedule skip"
            return result, ()
        requests = [artifact for artifact in artifacts
                    if artifact.get("name") == f"self-test-request-{run.id}-{run.attempt}"
                    and not artifact.get("expired", False)]
        if len(requests) > 1:
            raise ReportingError("ambiguous request artifacts for this attempt")
        if requests:
            request_payload = with_retry(lambda: api.download_artifact(int(requests[0]["id"])), sleep=sleep)
            request = read_verdict_zip(request_payload, filename="request.json")
            if (request.get("evidence_schema") != "lmdj.ci-self-test-request.v1"
                    or request.get("control_revision") != run.head_sha
                    or request.get("run_id") != run.id or request.get("run_attempt") != run.attempt
                    or request.get("request_kind") not in ("schedule", "node", "candidate")
                    or request.get("target_verified") is not False):
                raise ReportingError("request metadata does not identify this trusted run/attempt")
            requested_target = str(request.get("target_revision", ""))
            why = "The selected self-test retained its request but no current-attempt verdict or skip."
            if _SHA.fullmatch(requested_target):
                ancestry = with_retry(lambda: api.compare(requested_target, "main"), sleep=sleep)
                why += (f" Requested main-history target: {requested_target}." if
                        ancestry.get("status") in ("ahead", "identical") else
                        " Requested target is not in main history; resolver failed closed.")
            else:
                why += " Requested target is invalid; resolver failed closed."
            return _batch_problem(run, why)
        jobs = with_retry(lambda: api.list_jobs(run.id, run.attempt), sleep=sleep)
        verdict_jobs = [job for job in jobs if job.get("name") == "Self-test verdict"]
        # Compatibility schedules and dispatches do not select the new
        # self-test job. Do not fabricate a missing daily self-test during the
        # manual-only rollout. An entirely unstarted failed run is visible as
        # unclassified control failure rather than silently labelled tested.
        if not verdict_jobs or all(j.get("conclusion") == "skipped" for j in verdict_jobs):
            resolver_failed = any(job.get("name") == "Change Scope"
                                  and job.get("conclusion") not in ("success", "skipped") for job in jobs)
            if run.conclusion not in ("success", "neutral") and (not jobs or resolver_failed):
                result.error = "control run never produced request/job evidence; inspect this unclassified startup failure"
                return result, ()
            result.skipped = "compatibility run did not select self-test execution"
            return result, ()
        return _batch_problem(run, "No current-attempt verdict or verified skip artifact; "
                              f"run conclusion={run.conclusion}")
    artifact_id, target = found
    payload = with_retry(lambda: api.download_artifact(artifact_id), sleep=sleep)
    assert isinstance(payload, bytes)
    ancestry = with_retry(lambda: api.compare(target, "main"), sleep=sleep)
    if ancestry.get("status") not in ("ahead", "identical"):
        raise ReportingError("verdict target is not in current main history")
    policy = with_retry(lambda: api.get_policy(run.head_sha), sleep=sleep)
    verdict = parse_verdict(read_verdict_zip(payload), run=run, target=target, policy=policy)
    result.verdict_status = verdict.status
    result.target = target
    return result, plan_reports(verdict, run)


def reconcile_recent(api: GitHubApi, *, repository: str, assignee: str, sleep: Callable[[float], None],
                     exclude: Iterable[int] = (), limit: int = RECONCILE_RUNS,
                     created: str | None = None) -> list[RunReport]:
    """Revisit recent completed batches so a dropped trigger loses nothing.

    Markers make this safe to run after every trigger: an observation already
    recorded is a `duplicate` outcome and writes nothing.
    """
    excluded = set(exclude)
    results: list[RunReport] = []
    seen: set[int] = set()
    for event in sorted(ALLOWED_EVENTS):
        runs = with_retry(lambda event=event: api.list_runs(
            WORKFLOW_FILE, event=event, created=created, per_page=limit), sleep=sleep)
        assert isinstance(runs, list)
        for document in runs:
            run_id = int(document.get("id", 0))  # type: ignore[arg-type]
            if run_id in excluded or run_id in seen or run_id <= 0:
                continue
            seen.add(run_id)
            try:
                results.append(report_run(api, run_id, repository=repository, assignee=assignee, sleep=sleep))
            except WriteVisibilityError:
                raise  # a later batch must not turn an uncertain write into another POST
            except (ReportingError, GitHubApiError, ValueError, TypeError, KeyError) as error:
                results.append(RunReport(run_id, error=sanitize(str(error))))
        if len(runs) >= limit:
            results.append(RunReport(0, error=f"reconciliation window reached {limit} {event} runs; "
                                     "older observations may be unreported; use explicit run-id retries"))
    return results


def check_missing(api: GitHubApi, *, date: str, assignee: str,
                  sleep: Callable[[float], None]) -> Outcome | None:
    """File `self-test-missing` when no scheduled Core CI run exists for ``date``.

    This check runs on Actions itself. It can say "the schedule fired and no
    batch appeared"; it cannot say anything on a day Actions did not run it,
    so a maintainer still checks that this workflow ran (its own run list) --
    the Issue text says so.
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ReportingError(_diagnostic(f"date {date!r} is not YYYY-MM-DD", "pass the UTC date to check"))
    runs = with_retry(lambda: api.list_runs(WORKFLOW_FILE, event="schedule", created=date, per_page=5,
                                          status=None), sleep=sleep)
    assert isinstance(runs, list)
    if runs:
        return None
    report = Report(
        key=MISSING_KEY,
        title="self-test: daily batch did not start",
        observation=f"missing/{date}",
        severity="medium",
        labels=(REPORT_LABEL, "type:bug", "area:ci-release"),
        summary="\n".join([
            f"- Date (UTC): {date}",
            f"- Expected: a `{WORKFLOW_NAME}` run with event `schedule` (the 16:00 UTC sweep)",
            "- Observed: none completed or in progress by the time this check ran",
            "- Classification: **infrastructure** — nothing was tested, so nothing is known about today's `main`",
            "- Next step: check the workflow's schedule trigger and the runners; dispatch a node self-test manually",
        ]),
        detail="\n".join([
            "This check runs on GitHub Actions. It observed that the schedule did not produce a batch;",
            "it cannot observe a day on which Actions did not run this check either. A maintainer who does",
            "not see a `self-test-report.yml` schedule run for a date should treat that date as unchecked.",
        ]),
    )
    return apply_report(api, report, assignee=assignee, sleep=sleep)


def render_summary(reports: Sequence[RunReport], missing: Outcome | None, *, error: str | None) -> str:
    lines = ["## Self-test report", ""]
    if error:
        lines += [f"**reporting-error**: {error}", ""]
    for result in reports:
        if result.error:
            lines.append(f"- run {result.run_id}: **reporting-error**: {result.error}")
            continue
        if result.skipped:
            lines.append(f"- run {result.run_id}: skipped — {result.skipped}")
            continue
        lines.append(f"- run {result.run_id}: verdict **{result.verdict_status}** for `{(result.target or '')[:12]}`")
        for outcome in result.outcomes:
            number = f"#{outcome.issue_number}" if outcome.issue_number else ""
            lines.append(f"  - {outcome.key}: {outcome.action} {number}")
        if not result.outcomes:
            lines.append("  - nothing to file")
    if missing is not None:
        lines.append(f"- daily batch missing: {missing.action} #{missing.issue_number}")
    return "\n".join(lines) + "\n"


def _write_summary(path: str | None, text: str) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
    sys.stdout.write(text)


def recovery_created_filter(now: datetime) -> str:
    """Query optimization, not run authority: retain post-deployment history."""
    if now.tzinfo is None:
        raise ValueError("recovery time must include a timezone")
    deployed = datetime.fromisoformat(PRODUCER_SCAN_SINCE.replace("Z", "+00:00"))
    lower_bound = max(now.astimezone(timezone.utc) - timedelta(days=30), deployed)
    return ">=" + lower_bound.strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repository", required=True)
    parser.add_argument("--assignee", default=DEFAULT_ASSIGNEE)
    parser.add_argument("--summary", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="report one completed run, then reconcile recent ones")
    rep.add_argument("--run-id", type=int, required=True)
    rep.add_argument("--no-reconcile", action="store_true")
    mis = sub.add_parser("missing", help="file self-test-missing when no scheduled batch exists for a date")
    mis.add_argument("--date", required=True)
    args = parser.parse_args(argv)

    import time  # the only wall-clock use, and only for retry back-off
    sleep = time.sleep
    try:
        api = UrllibGitHubApi(args.repository, os.environ.get("GITHUB_TOKEN", ""))
        recovery_window = recovery_created_filter(datetime.now(timezone.utc))
        reports: list[RunReport] = []
        missing: Outcome | None = None
        if args.command == "report":
            try:
                reports.append(report_run(api, args.run_id, repository=args.repository,
                                          assignee=args.assignee, sleep=sleep))
            except WriteVisibilityError:
                raise  # outer handler records the error and stops before reconciliation
            except (ReportingError, GitHubApiError, ValueError, TypeError, KeyError) as error:
                reports.append(RunReport(args.run_id, error=sanitize(str(error))))
            if not args.no_reconcile:
                reports.extend(reconcile_recent(api, repository=args.repository, assignee=args.assignee,
                                                sleep=sleep, exclude=(args.run_id,), created=recovery_window))
        else:
            missing = check_missing(api, date=args.date, assignee=args.assignee, sleep=sleep)
            reports.extend(reconcile_recent(api, repository=args.repository, assignee=args.assignee,
                                            sleep=sleep, created=recovery_window))
    except (ReportingError, GitHubApiError, ValueError, TypeError, KeyError) as error:
        text = render_summary([], None, error=str(error))
        _write_summary(args.summary, text)
        print(f"::error::reporting-error: {error}", file=sys.stderr)
        return 2
    _write_summary(args.summary, render_summary(reports, missing, error=None))
    return 2 if any(report.error for report in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
