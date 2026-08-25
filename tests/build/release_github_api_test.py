#!/usr/bin/env python3
"""Transport contract tests for the Actions job, artifact and scope projections.

These tests bind the exact REST surface the release evidence verifier depends
on: complete pagination, closed identity binding to the selected run, the
authenticated artifact download, and the closed archive/manifest parser. The
expected identities are written here independently of the production module.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
import warnings
import zipfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.github_api import (  # noqa: E402
    ActionsArtifactProjection,
    CiScopeConflictError,
    CiScopeUnavailableError,
    GitHubApiError,
    GitHubClient,
    HttpResponse,
    RunJobProjection,
    RunProjection,
)


REPOSITORY = "endaye/lmdj"
RUN_ID = 4242
SECOND_RUN_ID = 4243
TARGET = "a" * 40
BASE = "b" * 40
TOKEN = "fixture-token"
WORKFLOW_ID = 313388832
WORKFLOW_PATH = ".github/workflows/ci.yml"
ARTIFACT_ID = 7001
BLOB_HOST = "productionresultssa12.blob.core.windows.net"
SIGNED_REDIRECT = f"https://{BLOB_HOST}/actions-results/fixture?sig=fixture&se=2026"

# The closed v2 lane set, written independently of the CI policy file and of
# the release module under test.
LANES = (
    "chameleon_lab", "ci_contract", "core_asan", "core_coverage", "core_macos",
    "core_ubuntu", "creator", "deploy_contract", "docs_static", "package",
    "portal", "web_runtime_host", "web_runtime_lab", "web_toolchain",
)
FULL_REQUIRED_JOBS = (
    "chameleon-lab", "ci-contract", "core-asan", "core-asan-macos",
    "core-coverage", "core-macos", "core-ubuntu", "creator-web",
    "deploy-contract", "docs-static", "macos-primary", "package", "portal",
    "select-macos-runner", "web-runtime-host", "web-runtime-lab",
    "web-toolchain-conformance",
)


def scope_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "lmdj.ci-scope.v2",
        "base_sha": BASE,
        "head_sha": TARGET,
        "mode": "full",
        "reasons": ["full event: workflow_dispatch"],
        "changed_files": [{"result": "modified", "paths": ["docs/guide.md"]}],
        "lanes": {lane: True for lane in LANES},
        "required_jobs": list(FULL_REQUIRED_JOBS),
        "trusted_head": True,
    }
    document.update(overrides)
    return document


def scope_archive(
    *,
    members: tuple[tuple[str, bytes], ...] | None = None,
    payload: bytes | None = None,
    external_attr: int | None = None,
) -> bytes:
    if members is None:
        selected = json.dumps(scope_document()).encode("utf-8") if payload is None else payload
        members = (("ci-scope.json", selected),)
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        # A duplicate member is one of the archives under test.
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, contents in members:
                info = zipfile.ZipInfo(name)
                if external_attr is not None:
                    info.external_attr = external_attr
                archive.writestr(info, contents)
    return buffer.getvalue()


def job_document(identifier: int, name: str, **overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "id": identifier,
        "run_id": RUN_ID,
        "name": name,
        "status": "completed",
        "conclusion": "success",
        "workflow_name": "Core CI / main",
        "head_sha": TARGET,
    }
    document.update(overrides)
    return document


def run_document(identifier: int = RUN_ID, **overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "id": identifier,
        "event": "workflow_dispatch",
        "head_sha": TARGET,
        "head_branch": "main",
        "name": "Core CI / main",
        "workflow_id": WORKFLOW_ID,
        "path": WORKFLOW_PATH,
        "status": "completed",
        "conclusion": "success",
    }
    document.update(overrides)
    return document


def workflow_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "id": WORKFLOW_ID,
        "name": "Core CI",
        "path": WORKFLOW_PATH,
        "state": "active",
    }
    document.update(overrides)
    return document


def artifact_document(**overrides: object) -> dict[str, object]:
    identifier = int(overrides.pop("id", ARTIFACT_ID))
    document: dict[str, object] = {
        "id": identifier,
        "name": f"ci-scope-{TARGET}",
        "size_in_bytes": 512,
        "url": f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{identifier}",
        "archive_download_url": (
            f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{identifier}/zip"
        ),
        "expired": False,
        "expires_at": "2026-08-30T00:00:00Z",
        "workflow_run": {
            "id": RUN_ID,
            "repository_id": 11,
            "head_repository_id": 11,
            "head_branch": "main",
            "head_sha": TARGET,
        },
    }
    document.update(overrides)
    return document


def run_projection() -> RunProjection:
    return RunProjection(RUN_ID, "push", TARGET, "main", "Core CI", "completed", "success")


class FakeTransport:
    """Serve exactly the recorded responses and record every request."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.responses: dict[str, list[HttpResponse]] = {}
        self.failures: dict[str, Exception] = {}

    def route(self, url: str, *responses: HttpResponse) -> None:
        self.responses[url] = list(responses)

    def json_route(self, url: str, document: object, link: str | None = None) -> None:
        headers = {"Content-Type": "application/json"}
        if link is not None:
            headers["Link"] = link
        self.route(url, HttpResponse(
            200, headers, json.dumps(document).encode("utf-8"),
        ))

    def __call__(self, method: str, url: str, headers, body) -> HttpResponse:
        self.requests.append((method, url, dict(headers)))
        if url in self.failures:
            raise self.failures[url]
        queued = self.responses.get(url)
        if not queued:
            raise AssertionError(f"unexpected request: {method} {url}")
        return queued.pop(0) if len(queued) > 1 else queued[0]


class ReleaseGitHubApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.client = GitHubClient(http_transport=self.transport, token=TOKEN)

    def jobs_url(self, page: int | None = None) -> str:
        base = f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}/jobs?filter=latest&per_page=100"
        return base if page is None else f"{base}&page={page}"

    def runs_url(self, page: int | None = None) -> str:
        base = f"/repos/{REPOSITORY}/actions/runs?head_sha={TARGET}&per_page=100"
        return base if page is None else f"{base}&page={page}"

    def workflow_url(self) -> str:
        return f"/repos/{REPOSITORY}/actions/workflows/{WORKFLOW_ID}"

    def artifacts_url(self, page: int | None = None) -> str:
        base = f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}/artifacts?per_page=100"
        return base if page is None else f"{base}&page={page}"

    def next_link(self, path: str) -> str:
        return f'<https://api.github.com{path}>; rel="next"'

    def route_jobs(self, *documents: dict[str, object]) -> None:
        self.transport.json_route(
            self.jobs_url(), {"total_count": len(documents), "jobs": list(documents)},
        )

    def route_artifacts(self, *documents: dict[str, object]) -> None:
        self.transport.json_route(
            self.artifacts_url(),
            {"total_count": len(documents), "artifacts": list(documents)},
        )

    def route_download(
        self,
        *,
        archive: bytes | None = None,
        location: str = SIGNED_REDIRECT,
        status: int = 200,
        content_type: str = "application/zip",
        identifier: int = ARTIFACT_ID,
    ) -> None:
        payload = scope_archive() if archive is None else archive
        self.transport.route(
            f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{identifier}/zip",
            HttpResponse(302, {"Location": location}, b""),
        )
        self.transport.route(
            location, HttpResponse(status, {"Content-Type": content_type}, payload),
        )

    def test_run_projection_resolves_stable_workflow_identity_once(self) -> None:
        self.transport.json_route(
            self.runs_url(),
            {
                "total_count": 2,
                "workflow_runs": [run_document(), run_document(SECOND_RUN_ID)],
            },
        )
        self.transport.json_route(self.workflow_url(), workflow_document())

        runs = self.client.list_runs_for_sha(REPOSITORY, TARGET)

        self.assertEqual(
            runs,
            [
                RunProjection(
                    RUN_ID, "workflow_dispatch", TARGET, "main", "Core CI",
                    "completed", "success",
                ),
                RunProjection(
                    SECOND_RUN_ID, "workflow_dispatch", TARGET, "main", "Core CI",
                    "completed", "success",
                ),
            ],
        )
        self.assertEqual(
            [url for _, url, _ in self.transport.requests if url == self.workflow_url()],
            [self.workflow_url()],
        )

    def test_run_and_workflow_metadata_identity_must_match(self) -> None:
        for name, run, workflow in (
            ("workflow id", run_document(), workflow_document(id=WORKFLOW_ID + 1)),
            ("workflow path", run_document(), workflow_document(path=".github/workflows/nightly.yml")),
            ("missing stable name", run_document(), workflow_document(name="")),
        ):
            with self.subTest(name=name):
                self.transport.responses.clear()
                self.transport.json_route(
                    self.runs_url(), {"total_count": 1, "workflow_runs": [run]},
                )
                self.transport.json_route(self.workflow_url(), workflow)
                with self.assertRaises(GitHubApiError):
                    self.client.list_runs_for_sha(REPOSITORY, TARGET)

    def test_run_jobs_require_complete_pagination(self) -> None:
        self.transport.json_route(
            self.jobs_url(),
            {"total_count": 2, "jobs": [job_document(1, "Change Scope")]},
            link=self.next_link(self.jobs_url(2)),
        )
        self.transport.json_route(
            self.jobs_url(2), {"total_count": 2, "jobs": [job_document(2, "PR Gate")]},
        )
        jobs = self.client.list_run_jobs(REPOSITORY, RUN_ID)
        self.assertEqual(
            jobs,
            [
                RunJobProjection(1, RUN_ID, "Change Scope", "completed", "success", "Core CI / main", TARGET),
                RunJobProjection(2, RUN_ID, "PR Gate", "completed", "success", "Core CI / main", TARGET),
            ],
        )

    def test_incomplete_job_pagination_is_rejected(self) -> None:
        self.transport.json_route(
            self.jobs_url(), {"total_count": 5, "jobs": [job_document(1, "PR Gate")]},
        )
        with self.assertRaises(GitHubApiError):
            self.client.list_run_jobs(REPOSITORY, RUN_ID)

    def test_duplicate_job_identities_are_rejected(self) -> None:
        self.route_jobs(job_document(1, "Change Scope"), job_document(1, "PR Gate"))
        with self.assertRaises(GitHubApiError):
            self.client.list_run_jobs(REPOSITORY, RUN_ID)

    def test_jobs_from_another_run_are_rejected(self) -> None:
        self.route_jobs(job_document(1, "PR Gate", run_id=RUN_ID + 1))
        with self.assertRaises(GitHubApiError):
            self.client.list_run_jobs(REPOSITORY, RUN_ID)

    def test_malformed_job_projection_is_rejected(self) -> None:
        for override in (
            {"id": 0}, {"status": 7}, {"head_sha": "short"}, {"name": ""},
            {"workflow_name": None}, {"conclusion": 3},
        ):
            with self.subTest(override=override):
                self.transport.responses.clear()
                self.route_jobs({**job_document(1, "PR Gate"), **override})
                with self.assertRaises(GitHubApiError):
                    self.client.list_run_jobs(REPOSITORY, RUN_ID)

    def test_run_artifacts_require_complete_pagination_and_unique_identities(self) -> None:
        self.transport.json_route(
            self.artifacts_url(),
            {"total_count": 2, "artifacts": [artifact_document()]},
            link=self.next_link(self.artifacts_url(2)),
        )
        self.transport.json_route(
            self.artifacts_url(2),
            {"total_count": 2, "artifacts": [artifact_document(id=ARTIFACT_ID + 1, name="other")]},
        )
        artifacts = self.client.list_run_artifacts(REPOSITORY, RUN_ID)
        self.assertEqual([item.id for item in artifacts], [ARTIFACT_ID, ARTIFACT_ID + 1])
        self.assertIsInstance(artifacts[0], ActionsArtifactProjection)

        self.transport.responses.clear()
        self.route_artifacts(artifact_document(), artifact_document())
        with self.assertRaises(GitHubApiError):
            self.client.list_run_artifacts(REPOSITORY, RUN_ID)

    def test_artifact_identity_must_bind_the_selected_run(self) -> None:
        for override in (
            {"workflow_run": {
                "id": RUN_ID + 1, "repository_id": 11, "head_repository_id": 11,
                "head_branch": "main", "head_sha": TARGET,
            }},
            {"url": f"https://api.github.com/repos/other/repo/actions/artifacts/{ARTIFACT_ID}"},
            {"archive_download_url": "https://api.github.com/repos/endaye/lmdj/actions/artifacts/1/zip"},
            {"expired": "false"},
            {"size_in_bytes": -1},
        ):
            with self.subTest(override=override):
                self.transport.responses.clear()
                self.route_artifacts(artifact_document(**override))
                with self.assertRaises(GitHubApiError):
                    self.client.list_run_artifacts(REPOSITORY, RUN_ID)

    def test_absent_or_expired_scope_artifact_is_unavailable(self) -> None:
        with self.subTest("absent"):
            self.route_artifacts(artifact_document(name="coverage"))
            with self.assertRaises(CiScopeUnavailableError):
                self.client.get_ci_scope_manifest(REPOSITORY, run_projection())
        with self.subTest("expired"):
            self.transport.responses.clear()
            self.route_artifacts(artifact_document(expired=True))
            with self.assertRaises(CiScopeUnavailableError):
                self.client.get_ci_scope_manifest(REPOSITORY, run_projection())
        with self.subTest("other head sha"):
            self.transport.responses.clear()
            self.route_artifacts(artifact_document(name="ci-scope-" + "c" * 40))
            with self.assertRaises(CiScopeUnavailableError):
                self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

    def test_scope_artifact_identity_must_bind_the_selected_run(self) -> None:
        for name, override in (
            ("fork head repository", {"workflow_run": {
                "id": RUN_ID, "repository_id": 11, "head_repository_id": 12,
                "head_branch": "main", "head_sha": TARGET,
            }}),
            ("other branch", {"workflow_run": {
                "id": RUN_ID, "repository_id": 11, "head_repository_id": 11,
                "head_branch": "feature", "head_sha": TARGET,
            }}),
        ):
            with self.subTest(name=name):
                self.transport.responses.clear()
                self.route_artifacts(artifact_document(**override))
                with self.assertRaises(CiScopeConflictError):
                    self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

    def test_multiple_matching_scope_artifacts_are_a_conflict(self) -> None:
        self.route_artifacts(
            artifact_document(), artifact_document(id=ARTIFACT_ID + 1),
        )
        with self.assertRaises(CiScopeConflictError):
            self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

    def test_scope_download_is_authenticated_once_and_never_forwards_the_token(self) -> None:
        self.route_artifacts(artifact_document())
        self.route_download()
        scope = self.client.get_ci_scope_manifest(REPOSITORY, run_projection())
        self.assertEqual(scope.schema, "lmdj.ci-scope.v2")
        self.assertEqual(scope.mode, "full")
        self.assertIs(scope.trusted_head, True)
        self.assertEqual(scope.head_sha, TARGET)
        self.assertEqual(scope.selected_lanes, tuple(sorted(LANES)))
        self.assertEqual(scope.required_jobs, tuple(sorted(FULL_REQUIRED_JOBS)))
        authenticated = [
            url for _, url, headers in self.transport.requests
            if headers.get("Authorization") == f"Bearer {TOKEN}"
        ]
        self.assertTrue(all(url.startswith("https://api.github.com") or url.startswith("/") for url in authenticated))
        redirect_headers = next(
            headers for _, url, headers in self.transport.requests if url == SIGNED_REDIRECT
        )
        self.assertNotIn("Authorization", redirect_headers)

    def test_untrusted_redirect_target_is_rejected(self) -> None:
        for location in (
            "http://productionresultssa12.blob.core.windows.net/x?sig=1",
            "https://evil.example.com/x?sig=1",
            "https://productionresultssa12.blob.core.windows.net.evil.test/x?sig=1",
            f"https://user:pass@{BLOB_HOST}/x?sig=1",
            f"https://{BLOB_HOST}:8443/x?sig=1",
            f"https://{BLOB_HOST}/x?sig=1#fragment",
            f"https://{BLOB_HOST}/x",
        ):
            with self.subTest(location=location):
                self.transport.responses.clear()
                self.route_artifacts(artifact_document())
                self.route_download(location=location)
                with self.assertRaises(CiScopeConflictError):
                    self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

    def test_download_status_content_type_and_magic_are_required(self) -> None:
        cases = (
            {"status": 500},
            {"content_type": "text/html"},
            {"archive": b"not a zip"},
            {"archive": b"PK\x03\x04" + b"\x00" * 32},
        )
        for case in cases:
            with self.subTest(case=case):
                self.transport.responses.clear()
                self.route_artifacts(artifact_document())
                self.route_download(**case)
                with self.assertRaises(GitHubApiError):
                    self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

    def test_oversized_archive_is_rejected_before_parsing(self) -> None:
        self.route_artifacts(artifact_document(size_in_bytes=2 * 1024 * 1024))
        with self.assertRaises(CiScopeConflictError):
            self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

        self.transport.responses.clear()
        self.route_artifacts(artifact_document())
        self.route_download(archive=scope_archive(
            payload=json.dumps(scope_document(
                reasons=["padding " * 200_000],
            )).encode("utf-8"),
        ))
        with self.assertRaises(CiScopeConflictError):
            self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

    def test_archive_member_inventory_is_closed(self) -> None:
        payload = json.dumps(scope_document()).encode("utf-8")
        cases = {
            "traversal": (("../ci-scope.json", payload),),
            "absolute": (("/ci-scope.json", payload),),
            "nested": (("run/ci-scope.json", payload),),
            "duplicate": (("ci-scope.json", payload), ("ci-scope.json", payload)),
            "extra": (("ci-scope.json", payload), ("extra.json", payload)),
            "wrong name": (("scope.json", payload),),
            "empty": (),
        }
        for name, members in cases.items():
            with self.subTest(name=name):
                self.transport.responses.clear()
                self.route_artifacts(artifact_document())
                self.route_download(archive=scope_archive(members=members))
                with self.assertRaises(CiScopeConflictError):
                    self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

    def test_symlink_member_is_rejected(self) -> None:
        self.route_artifacts(artifact_document())
        self.route_download(archive=scope_archive(
            members=(("ci-scope.json", b"../../etc/passwd"),),
            external_attr=(0o120777 << 16),
        ))
        with self.assertRaises(CiScopeConflictError):
            self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

    def test_manifest_content_is_closed(self) -> None:
        cases = {
            "duplicate JSON key": b'{"schema": "lmdj.ci-scope.v2", "schema": "other"}',
            "not an object": b'["lmdj.ci-scope.v2"]',
            "invalid JSON": b"{",
            "not UTF-8": b'{"schema": "\xff"}',
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                self.transport.responses.clear()
                self.route_artifacts(artifact_document())
                self.route_download(archive=scope_archive(payload=payload))
                with self.assertRaises(CiScopeConflictError):
                    self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

    def test_manifest_schema_lanes_and_trust_are_closed(self) -> None:
        broken = {
            "wrong schema": scope_document(schema="lmdj.ci-scope.v1"),
            "extra key": {**scope_document(), "injected": True},
            "missing key": {
                key: value for key, value in scope_document().items() if key != "reasons"
            },
            "non-boolean trust": scope_document(trusted_head="true"),
            "numeric trust": scope_document(trusted_head=1),
            "unknown mode": scope_document(mode="fast"),
            "short head sha": scope_document(head_sha="abc"),
            "missing lane": scope_document(
                lanes={lane: True for lane in LANES if lane != "package"},
            ),
            "unknown lane": scope_document(
                lanes={**{lane: True for lane in LANES}, "invented": True},
            ),
            "full with an unselected lane": scope_document(
                lanes={**{lane: True for lane in LANES}, "package": False},
            ),
            "non-boolean lane": scope_document(
                lanes={**{lane: True for lane in LANES}, "package": "true"},
            ),
            "unsorted required jobs": scope_document(
                required_jobs=list(reversed(FULL_REQUIRED_JOBS)),
            ),
            "duplicate required job": scope_document(
                required_jobs=[*FULL_REQUIRED_JOBS, FULL_REQUIRED_JOBS[-1]],
            ),
            "empty required jobs": scope_document(required_jobs=[]),
            "non-string required job": scope_document(required_jobs=[1]),
        }
        for name, document in broken.items():
            with self.subTest(name=name):
                self.transport.responses.clear()
                self.route_artifacts(artifact_document())
                self.route_download(archive=scope_archive(
                    payload=json.dumps(document).encode("utf-8"),
                ))
                with self.assertRaises(CiScopeConflictError):
                    self.client.get_ci_scope_manifest(REPOSITORY, run_projection())

    def test_focused_manifest_is_projected_faithfully(self) -> None:
        lanes = {lane: lane == "docs_static" for lane in LANES}
        self.route_artifacts(artifact_document())
        self.route_download(archive=scope_archive(
            payload=json.dumps(scope_document(
                mode="focused", lanes=lanes, required_jobs=["docs-static"],
                reasons=[],
            )).encode("utf-8"),
        ))
        scope = self.client.get_ci_scope_manifest(REPOSITORY, run_projection())
        self.assertEqual(scope.mode, "focused")
        self.assertEqual(scope.selected_lanes, ("docs_static",))
        self.assertEqual(scope.required_jobs, ("docs-static",))

    def test_transport_outage_stays_a_transport_error(self) -> None:
        self.transport.failures[self.artifacts_url()] = TimeoutError("fixture outage")
        with self.assertRaises(GitHubApiError) as captured:
            self.client.get_ci_scope_manifest(REPOSITORY, run_projection())
        self.assertNotIsInstance(captured.exception, CiScopeUnavailableError)
        self.assertNotIsInstance(captured.exception, CiScopeConflictError)
        self.assertNotIn("fixture outage", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
