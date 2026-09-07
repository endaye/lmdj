#!/usr/bin/env python3
"""Closed classification contracts for full exact-main CI release evidence.

The verifier is read-only and must return exactly one closed result code for
every observable state of the recorded Actions run, its same-run jobs and its
retained scope manifest. The expected lane and job identities are written here
independently of both the CI policy file and the release modules under test.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.audit import AuditContext, audit  # noqa: E402
import tools.release.audit as audit_module  # noqa: E402
from tools.release.ci_evidence import (  # noqa: E402
    CHANGE_SCOPE_JOB,
    PR_GATE_JOB,
    CiEvidenceResult,
    verify_exact_main_ci,
)
from tools.release.github_api import (  # noqa: E402
    BranchProjection,
    CiScopeConflictError,
    CiScopeProjection,
    CiScopeUnavailableError,
    DeploymentBranchPolicy,
    GitHubApiError,
    GitHubEnvironment,
    GitHubRelease,
    RunJobProjection,
    RunProjection,
)
from tools.release.model import load_ledger_document, load_policy  # noqa: E402
from tools.release.prepare import LocalTag, ProductProof  # noqa: E402


REPOSITORY = "endaye/lmdj"
BRANCH = "main"
WORKFLOW = "Core CI"
TARGET = "a" * 40
BASE = "b" * 40
RUN_ID = 123
PRODUCT = "2B5EE362F058800036AD4FB5116ECE156F954D29"
CHECKSUM = "CB928A6E89DE498851688EF1AAC3E7019FC1478B"

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


def full_scope(**overrides: object) -> CiScopeProjection:
    fields: dict[str, object] = {
        "schema": "lmdj.ci-scope.v2",
        "base_sha": BASE,
        "head_sha": TARGET,
        "mode": "full",
        "trusted_head": True,
        "selected_lanes": tuple(sorted(LANES)),
        "required_jobs": tuple(sorted(FULL_REQUIRED_JOBS)),
    }
    fields.update(overrides)
    return CiScopeProjection(**fields)  # type: ignore[arg-type]


def gate_jobs(*, sha: str = TARGET, gate: str = "success") -> list[RunJobProjection]:
    return [
        RunJobProjection(1, RUN_ID, CHANGE_SCOPE_JOB, "completed", "success", WORKFLOW, sha),
        RunJobProjection(2, RUN_ID, PR_GATE_JOB, "completed", gate, WORKFLOW, sha),
    ]


class EvidenceGitHub:
    """Serve exactly one typed projection per read and record every call."""

    def __init__(self) -> None:
        self.runs = [RunProjection(RUN_ID, "push", TARGET, BRANCH, WORKFLOW, "completed", "success")]
        self.jobs = gate_jobs()
        self.scope: CiScopeProjection | None = full_scope()
        self.run_error: Exception | None = None
        self.job_error: Exception | None = None
        self.scope_error: Exception | None = None
        self.calls: list[str] = []

    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]:
        self.calls.append(f"runs:{sha}")
        if self.run_error is not None:
            raise self.run_error
        return list(self.runs)

    def list_run_jobs(self, repository: str, run_id: int) -> list[RunJobProjection]:
        self.calls.append(f"jobs:{run_id}")
        if self.job_error is not None:
            raise self.job_error
        return list(self.jobs)

    def get_ci_scope_manifest(self, repository: str, run: RunProjection) -> CiScopeProjection:
        self.calls.append(f"scope:{run.id}")
        if self.scope_error is not None:
            raise self.scope_error
        assert self.scope is not None
        return self.scope


class CiEvidenceVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.github = EvidenceGitHub()

    def verify(self, *, require_full_scope: bool = True, run_id: int | None = RUN_ID) -> CiEvidenceResult:
        return verify_exact_main_ci(
            self.github,
            repository=REPOSITORY,
            branch=BRANCH,
            workflow=WORKFLOW,
            target_revision=TARGET,
            run_id=run_id,
            require_full_scope=require_full_scope,
        )

    def test_valid_full_push_evidence_is_ok(self) -> None:
        result = self.verify()
        self.assertEqual(result.code, "ok")
        self.assertIsNotNone(result.run)
        self.assertEqual(result.run.id, RUN_ID)
        self.assertEqual(
            self.github.calls, [f"runs:{TARGET}", f"jobs:{RUN_ID}", f"scope:{RUN_ID}"],
        )

    def test_valid_full_workflow_dispatch_evidence_is_ok(self) -> None:
        self.github.runs = [
            RunProjection(RUN_ID, "workflow_dispatch", TARGET, BRANCH, WORKFLOW, "completed", "success"),
        ]
        self.assertEqual(self.verify().code, "ok")

    def test_dynamic_job_run_name_does_not_replace_stable_workflow_identity(self) -> None:
        self.github.jobs = [
            RunJobProjection(
                1, RUN_ID, CHANGE_SCOPE_JOB, "completed", "success",
                "Core CI / main", TARGET,
            ),
            RunJobProjection(
                2, RUN_ID, PR_GATE_JOB, "completed", "success",
                "Core CI / main", TARGET,
            ),
        ]
        self.assertEqual(self.verify().code, "ok")

    def test_focused_mode_is_a_conflict(self) -> None:
        self.github.scope = full_scope(mode="focused", selected_lanes=("docs_static",), required_jobs=("docs-static",))
        result = self.verify()
        self.assertEqual(result.code, "conflict")
        self.assertIn("full", result.message)

    def test_untrusted_or_mismatched_scope_manifest_is_a_conflict(self) -> None:
        for name, scope in (
            ("wrong head sha", full_scope(head_sha="c" * 40)),
            ("untrusted head", full_scope(trusted_head=False)),
            ("wrong schema", full_scope(schema="lmdj.ci-scope.v1")),
            ("draft mode", full_scope(mode="draft")),
            ("requested mode", full_scope(mode="requested")),
            ("incomplete lane set", full_scope(selected_lanes=tuple(sorted(LANES))[:-1])),
        ):
            with self.subTest(name=name):
                self.github.scope = scope
                self.assertEqual(self.verify().code, "conflict")

    def test_wrong_run_identity_is_a_conflict(self) -> None:
        for name, run in (
            ("wrong sha", RunProjection(RUN_ID, "push", "c" * 40, BRANCH, WORKFLOW, "completed", "success")),
            ("wrong branch", RunProjection(RUN_ID, "push", TARGET, "feature", WORKFLOW, "completed", "success")),
            ("wrong workflow", RunProjection(RUN_ID, "push", TARGET, BRANCH, "Nightly", "completed", "success")),
            ("wrong event", RunProjection(RUN_ID, "pull_request", TARGET, BRANCH, WORKFLOW, "completed", "success")),
            ("incomplete", RunProjection(RUN_ID, "push", TARGET, BRANCH, WORKFLOW, "in_progress", None)),
            ("failed", RunProjection(RUN_ID, "push", TARGET, BRANCH, WORKFLOW, "completed", "failure")),
            ("cancelled", RunProjection(RUN_ID, "push", TARGET, BRANCH, WORKFLOW, "completed", "cancelled")),
        ):
            with self.subTest(name=name):
                self.github.runs = [run]
                result = self.verify()
                self.assertEqual(result.code, "conflict")

    def test_absent_or_duplicate_recorded_run_is_missing(self) -> None:
        for name, runs in (
            ("absent", []),
            ("other run only", [RunProjection(999, "push", TARGET, BRANCH, WORKFLOW, "completed", "success")]),
            ("duplicate", [
                RunProjection(RUN_ID, "push", TARGET, BRANCH, WORKFLOW, "completed", "success"),
                RunProjection(RUN_ID, "push", TARGET, BRANCH, WORKFLOW, "completed", "success"),
            ]),
        ):
            with self.subTest(name=name):
                self.github.runs = runs
                self.assertEqual(self.verify().code, "missing")

    def test_intent_without_a_recorded_run_is_unverifiable(self) -> None:
        result = self.verify(run_id=None)
        self.assertEqual(result.code, "unverifiable")
        self.assertEqual(self.github.calls, [])

    def test_expired_or_absent_scope_artifact_is_unverifiable(self) -> None:
        self.github.scope_error = CiScopeUnavailableError("retained scope evidence is absent")
        result = self.verify()
        self.assertEqual(result.code, "unverifiable")
        self.assertIn("scope", result.message)

    def test_malformed_scope_artifact_identity_is_a_conflict(self) -> None:
        self.github.scope_error = CiScopeConflictError("scope artifact identity conflicts")
        self.assertEqual(self.verify().code, "conflict")

    def test_missing_duplicate_or_failed_gate_is_a_conflict(self) -> None:
        cases = {
            "missing gate": [gate_jobs()[0]],
            "missing change scope": [gate_jobs()[1]],
            "failed gate": gate_jobs(gate="failure"),
            "skipped gate": gate_jobs(gate="skipped"),
            "duplicate gate": [*gate_jobs(), RunJobProjection(3, RUN_ID, PR_GATE_JOB, "completed", "success", WORKFLOW, TARGET)],
            "incomplete gate": [
                gate_jobs()[0],
                RunJobProjection(2, RUN_ID, PR_GATE_JOB, "in_progress", None, WORKFLOW, TARGET),
            ],
            "gate from another run": [
                gate_jobs()[0],
                RunJobProjection(2, RUN_ID + 1, PR_GATE_JOB, "completed", "success", WORKFLOW, TARGET),
            ],
            "gate on another sha": gate_jobs(sha="c" * 40),
        }
        for name, jobs in cases.items():
            with self.subTest(name=name):
                self.github.jobs = jobs
                result = self.verify()
                self.assertEqual(result.code, "conflict")

    def test_api_outage_is_an_external_error(self) -> None:
        for name, attribute in (
            ("runs", "run_error"),
            ("jobs", "job_error"),
            ("scope", "scope_error"),
        ):
            with self.subTest(name=name):
                self.github = EvidenceGitHub()
                setattr(self.github, attribute, GitHubApiError("fixture outage"))
                result = self.verify()
                self.assertEqual(result.code, "external-error")
                self.assertNotIn("fixture outage", result.message)
                self.assertTrue(result.sources)

    def test_run_level_verification_reads_no_ephemeral_evidence(self) -> None:
        self.github.job_error = AssertionError("terminal audit must not read run jobs")
        self.github.scope_error = AssertionError("terminal audit must not read the artifact")
        result = self.verify(require_full_scope=False)
        self.assertEqual(result.code, "ok")
        self.assertEqual(self.github.calls, [f"runs:{TARGET}"])


class ReadOnlyGit:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.tags: dict[str, LocalTag] = {}

    def fetch_authority(self, repository: str, branch: str) -> None:
        return None

    def main_revision(self) -> str:
        return TARGET

    def is_main_ancestor(self, target: str) -> bool:
        return target == TARGET

    def validate_release_target(self, worktree: Path, intent) -> None:
        return None

    def local_tag_state(self, tag: str) -> LocalTag | None:
        return None

    def list_remote_tags(self) -> dict[str, LocalTag]:
        return dict(self.tags)

    @contextmanager
    def detached_worktree(self, target: str):
        yield self.root


class ProspectiveAuditGitHub(EvidenceGitHub):
    def __init__(self) -> None:
        super().__init__()
        self.branch = BranchProjection(BRANCH, True, TARGET)
        self.environment = GitHubEnvironment(
            "release", 0, None, False, True, (DeploymentBranchPolicy(1, BRANCH, "branch"),),
        )

    def get_branch(self, repository: str, branch: str) -> BranchProjection:
        return self.branch

    def list_releases(self, repository: str) -> list[GitHubRelease]:
        return []

    def get_latest_release(self, repository: str) -> GitHubRelease | None:
        return None

    def get_release_environment(self, repository: str) -> GitHubEnvironment | None:
        return self.environment


class ProspectiveReleaseAuditTest(unittest.TestCase):
    """A releasable intent is not audit-clean before its CI evidence is read."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-release-ci-evidence-")
        self.root = Path(self.temporary.name)
        (self.root / "evidence.md").write_text("fixture\n", encoding="utf-8")
        # This suite pins legacy scope semantics, not current candidate policy.
        self.policy = replace(load_policy(ROOT / "tools/release/policy.json"), prospective_ci_protocol="ci-scope-v2")
        self.git = ReadOnlyGit(self.root)
        self.github = ProspectiveAuditGitHub()
        self.tag = "module/application-facade/v1.0.1"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def context(self) -> AuditContext:
        ledger = load_ledger_document({
            "schema": "lmdj.release-intents.v1",
            "entries": [{
                "tag": self.tag,
                "kind": "module",
                "identity": "application-facade@1.0.1",
                "target_revision": TARGET,
                "disposition": "releasable",
                "profile": "source-only",
                "merged_main_run_id": RUN_ID,
                "evidence_paths": ["evidence.md"],
            }],
            "historical_exceptions": [],
        }, self.policy)
        return AuditContext(
            repo_root=self.root,
            policy=self.policy,
            ledger=ledger,
            git=self.git,
            github=self.github,
            profile_verifier=lambda *args: None,
            proof_reader=lambda worktree, intent: ProductProof(
                BRANCH, TARGET, intent.identity, intent.identity, TARGET,
            ),
            tag_signer_fingerprint=PRODUCT,
            checksum_signer_fingerprint=CHECKSUM,
        )

    def finding(self):
        report = audit(self.context(), remote=True, tag=self.tag)
        return next(item for item in report.findings if item.subject == self.tag)

    def test_releasable_intent_without_a_remote_tag_still_requires_full_evidence(self) -> None:
        self.github.scope = full_scope(mode="focused", selected_lanes=("docs_static",), required_jobs=("docs-static",))
        finding = self.finding()
        self.assertEqual(finding.code, "conflict")
        self.assertIn(f"scope:{RUN_ID}", self.github.calls)

    def test_releasable_intent_with_full_evidence_reports_the_prospective_state(self) -> None:
        finding = self.finding()
        self.assertEqual(finding.code, "ok")
        self.assertIn("no remote publication state", finding.message)

    def test_ci_problem_accepts_only_full_exact_main_evidence(self) -> None:
        context = self.context()
        intent = context.ledger.intent_for_tag(self.tag)
        self.assertIsNone(audit_module._ci_problem(context, intent))
        for mode, sha, gate in (
            ("focused", TARGET, "success"),
            ("full", "c" * 40, "success"),
            ("full", TARGET, "skipped"),
        ):
            with self.subTest(mode=mode, sha=sha, gate=gate):
                self.github.scope = full_scope(mode=mode, head_sha=sha)
                self.github.jobs = gate_jobs(gate=gate)
                problem = audit_module._ci_problem(context, intent)
                self.assertIsNotNone(problem)
                self.assertNotEqual(problem.code, "ok")


if __name__ == "__main__":
    unittest.main()
