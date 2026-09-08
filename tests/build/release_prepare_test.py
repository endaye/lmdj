#!/usr/bin/env python3
"""Contract tests for local-only signed release preparation."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr
from dataclasses import dataclass, replace
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def current_product_build() -> str:
    version = json.loads(
        (ROOT / "products/lmdj/version.json").read_text(encoding="utf-8")
    )
    return ".".join(
        str(version[field])
        for field in ("milestone", "minor", "build", "patch")
    )


CURRENT_PRODUCT_BUILD = current_product_build()

from tools.release.commands import CommandError, CommandRunner, sanitize_diagnostic  # noqa: E402
from tools.release.github_api import (  # noqa: E402
    BranchProjection,
    CiScopeConflictError,
    CiScopeProjection,
    CiScopeUnavailableError,
    GitHubClient,
    HttpResponse,
    RunJobProjection,
    RunProjection,
)
from tools.release.git_repository import GitRepository  # noqa: E402
from tools.release.target_validation import (  # noqa: E402
    TargetValidationError,
    validate_release_target,
)
from tools.release.model import (  # noqa: E402
    Disposition,
    HistoricalException,
    ReleaseIntent,
    ReleaseKind,
    ReleaseLedger,
    canonical_json,
    load_ledger_document,
    load_policy,
)
from tools.release.prepare import (  # noqa: E402
    LocalTag,
    PrepareContext,
    PrepareError,
    ProductProof,
    prepare,
    read_product_snapshot_proof,
    _verify_profile_assets,
)
from tools.release.profiles import (  # noqa: E402
    AssetBuild,
    ProfileBuild,
    ProfileError,
    ProfileRuntime,
    WEB_RUNTIME_SPEC,
    _create_dist_zip,
    _stage_web_bundle,
    _stage_and_sign,
    _verify_checksum,
    build_profile,
    verify_existing_profile,
)
from tools.release.commands import CommandRunner  # noqa: E402
from tools.release import cli  # noqa: E402


class FakeGit:
    def __init__(self, target: str, signer: str) -> None:
        self.target = target
        self.signer = signer
        self.main_contains_target = True
        self.remote_tag: LocalTag | None = None
        self.local_tag: LocalTag | None = None
        self.calls: list[str] = []
        self.remote_mutations: list[str] = []
        self.target_validation_error: Exception | None = None

    def fetch_authority(self, *arguments: str) -> None:
        self.calls.append(f"fetch:{':'.join(arguments)}")

    def main_revision(self) -> str:
        return self.target

    def is_main_ancestor(self, target: str) -> bool:
        self.calls.append(f"ancestor:{target}")
        return self.main_contains_target and target == self.target

    def is_revision_ancestor(self, ancestor: str, descendant: str) -> bool:
        self.calls.append(f"revision-ancestor:{ancestor}:{descendant}")
        return self.main_contains_target and descendant == self.target

    def validate_release_target(self, worktree: Path, intent: ReleaseIntent) -> None:
        self.calls.append(f"validate-target:{intent.kind.value}:{intent.identity}")
        if self.target_validation_error is not None:
            raise self.target_validation_error

    def remote_tag_state(self, tag: str) -> LocalTag | None:
        self.calls.append(f"remote-tag:{tag}")
        return self.remote_tag

    def local_tag_state(self, tag: str) -> LocalTag | None:
        self.calls.append(f"local-tag:{tag}")
        return self.local_tag

    @contextmanager
    def detached_worktree(self, target: str):
        self.calls.append(f"worktree:{target}")
        with tempfile.TemporaryDirectory(prefix="lmdj-release-worktree-") as directory:
            yield Path(directory)

    def create_local_tag(self, tag: str, target: str, signer: str, message: str) -> LocalTag:
        self.calls.append(f"create-local-tag:{tag}")
        self.local_tag = LocalTag("b" * 40, target, signer)
        return self.local_tag


# The closed v2 lane and full job identities, written independently of the CI
# policy file and of the release modules under test.
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


class FakeGitHub:
    def __init__(self, target: str, run_id: int) -> None:
        self.branch = BranchProjection("main", True, target)
        self.runs = [RunProjection(run_id, "push", target, "main", "Core CI", "completed", "success")]
        self.jobs = [
            RunJobProjection(1, run_id, "Change Scope", "completed", "success", "Core CI", target),
            RunJobProjection(2, run_id, "PR Gate", "completed", "success", "Core CI", target),
        ]
        self.scope = CiScopeProjection(
            schema="lmdj.ci-scope.v2", base_sha="b" * 40, head_sha=target,
            mode="full", trusted_head=True,
            selected_lanes=tuple(sorted(LANES)),
            required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
        )
        self.scope_error: Exception | None = None
        self.remote_mutations: list[str] = []
        self.run_queries = 0
        self.scope_queries = 0

    def get_branch(self, repository: str, branch: str) -> BranchProjection:
        return self.branch

    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]:
        self.run_queries += 1
        return self.runs

    def list_run_jobs(self, repository: str, run_id: int) -> list[RunJobProjection]:
        return list(self.jobs)

    def get_ci_scope_manifest(self, repository: str, run: RunProjection) -> CiScopeProjection:
        self.scope_queries += 1
        if self.scope_error is not None:
            raise self.scope_error
        return self.scope


@dataclass(frozen=True)
class DetailedRun:
    id: int
    event: str
    head_sha: str
    status: str
    conclusion: str | None
    head_branch: str
    workflow_name: str


class RecordingVerifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def sign_detached(self, home: Path, payload: Path, signature: Path, fingerprint: str) -> None:
        self.calls.append(("sign", home.stat().st_mode & 0o777))
        signature.write_text("signature", encoding="ascii")

    def import_public_key(self, home: Path, key_path: Path, fingerprint: str) -> None:
        self.calls.append(("import", home.stat().st_mode & 0o777))

    def verify_detached(self, home: Path, signature: Path, payload: Path, fingerprint: str) -> None:
        self.calls.append(("verify", home.stat().st_mode & 0o777))


class ReleasePrepareTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-release-prepare-")
        self.root = Path(self.temporary.name)
        self.target_sha = "a" * 40
        self.tag = "lmdj-v1.0.21.0"
        # Exercise the pre-cutover scope protocol in this legacy regression
        # matrix; release_self_test_evidence_test covers current policy.
        self.policy = replace(load_policy(ROOT / "tools/release/policy.json"), prospective_ci_protocol="ci-scope-v2")
        self.ledger = self.ledger_fixture()
        self.git = FakeGit(self.target_sha, self.policy.product_fingerprint)
        self.github = FakeGitHub(self.target_sha, 123)
        self.remote_mutations: list[str] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def ledger_fixture(self, disposition: str = "releasable") -> ReleaseLedger:
        document = {
            "schema": "lmdj.release-intents.v1",
            "entries": [{
                "tag": self.tag,
                "kind": "product",
                "identity": "1.0.21.0",
                "target_revision": self.target_sha,
                "channel": "canary",
                "disposition": disposition,
                "profile": "web-runtime-host",
                "snapshot": "1.0.21.0",
                "merged_main_run_id": 123,
                "evidence_paths": ["docs/quality/example-proof.md"],
            }],
            "historical_exceptions": [],
        }
        return load_ledger_document(document, self.policy)

    def profile_builder(self, profile: str, worktree: Path, output: Path, intent) -> ProfileBuild:
        self.assertEqual(profile, "web-runtime-host")
        return self.profile_build_with_signature(output, b"signature")

    def profile_build_with_signature(self, output: Path, signature: bytes) -> ProfileBuild:
        output.mkdir(parents=True, exist_ok=True)
        assets = []
        for name, payload in (
            ("lmdj-web-runtime-host-1.1.2-product-1.0.21.0.zip", b"zip"),
            ("lmdj-web-runtime-host-1.1.2-product-1.0.21.0.zip.sha256", b"checksum"),
            ("lmdj-web-runtime-host-1.1.2-product-1.0.21.0.zip.sha256.asc", signature),
        ):
            path = output / name
            path.write_bytes(payload)
            assets.append(AssetBuild(path, name, len(payload), hashlib.sha256(payload).hexdigest()))
        return ProfileBuild(tuple(assets))

    def proof_reader(self, worktree: Path, intent) -> ProductProof:
        return ProductProof(
            source_branch="main",
            target_revision=self.target_sha,
            product_build="1.0.21.0",
            snapshot="1.0.21.0",
            snapshot_revision=self.target_sha,
        )

    def context(self) -> PrepareContext:
        return PrepareContext(
            repo_root=self.root,
            policy=self.policy,
            ledger=self.ledger,
            git=self.git,
            github=self.github,
            profile_builder=self.profile_builder,
            profile_verifier=lambda profile, worktree, assets_root, intent, assets: None,
            proof_reader=self.proof_reader,
            tag_signer_fingerprint=self.policy.product_fingerprint,
            checksum_signer_fingerprint=self.policy.checksum_fingerprint,
            authority_reader=lambda worktree: (self.policy, self.ledger),
        )

    def test_prepare_stops_at_local_plan(self) -> None:
        prepared = prepare(self.tag, self.context())
        self.assertEqual(prepared.plan.target_revision, self.target_sha)
        self.assertEqual(len(prepared.plan.assets), 3)
        self.assertEqual(self.git.remote_mutations, [])
        self.assertEqual(self.github.remote_mutations, [])
        document = json.loads((prepared.output_root / "release-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(document["tag"], self.tag)
        self.assertEqual(document["target_revision"], self.target_sha)
        self.assertEqual(document["assets"], [
            {"name": item.name, "bytes": item.bytes, "sha256": item.sha256}
            for item in prepared.plan.assets
        ])
        self.assertEqual((prepared.output_root / "release-plan.sha256").read_text(encoding="ascii"), prepared.digest + "\n")

    def test_prepare_reuses_admitted_ci_projection_after_local_tag_creation(self) -> None:
        prepare(self.tag, self.context())
        self.assertEqual(self.github.run_queries, 1)

    def test_prepare_reconciles_an_identical_local_output(self) -> None:
        first = prepare(self.tag, self.context())
        second = prepare(self.tag, self.context())
        self.assertEqual(second.output_root, first.output_root)
        self.assertTrue(second.reused_local_tag)

    def test_prepare_reconciles_existing_output_without_rebuilding_or_resigning(self) -> None:
        signer_calls = 0

        def nondeterministic_builder(profile: str, worktree: Path, output: Path, intent) -> ProfileBuild:
            nonlocal signer_calls
            self.assertEqual(profile, "web-runtime-host")
            signer_calls += 1
            if signer_calls > 1:
                raise AssertionError("retry must not rebuild or re-sign existing release output")
            return self.profile_build_with_signature(output, b"signature-created-at-first-prepare")

        context = self.context()
        context.profile_builder = nondeterministic_builder
        context.profile_verifier = lambda profile, worktree, output, intent, assets: None
        first = prepare(self.tag, context)
        second = prepare(self.tag, context)
        self.assertEqual(second.output_root, first.output_root)
        self.assertEqual(signer_calls, 1)

    def test_prepare_rejects_changed_existing_signature_without_rebuilding(self) -> None:
        builds = 0

        def builder(profile: str, worktree: Path, output: Path, intent) -> ProfileBuild:
            nonlocal builds
            builds += 1
            if builds > 1:
                raise AssertionError("retry must not rebuild after existing signature changes")
            return self.profile_build_with_signature(output, b"signature-before-change")

        context = self.context()
        context.profile_builder = builder
        context.profile_verifier = lambda profile, worktree, output, intent, assets: None
        first = prepare(self.tag, context)
        (first.output_root / "assets" / "lmdj-web-runtime-host-1.1.2-product-1.0.21.0.zip.sha256.asc").write_bytes(
            b"changed-signature"
        )
        with self.assertRaisesRegex(PrepareError, "existing release output"):
            prepare(self.tag, context)
        self.assertEqual(builds, 1)

    def test_prepare_rejects_changed_existing_archive_without_rebuilding(self) -> None:
        builds = 0

        def builder(profile: str, worktree: Path, output: Path, intent) -> ProfileBuild:
            nonlocal builds
            builds += 1
            if builds > 1:
                raise AssertionError("retry must not rebuild after existing asset changes")
            return self.profile_build_with_signature(output, b"signature-before-archive-change")

        context = self.context()
        context.profile_builder = builder
        context.profile_verifier = lambda profile, worktree, output, intent, assets: None
        first = prepare(self.tag, context)
        (first.output_root / "assets" / "lmdj-web-runtime-host-1.1.2-product-1.0.21.0.zip").write_bytes(
            b"changed-archive"
        )
        with self.assertRaisesRegex(PrepareError, "existing release output"):
            prepare(self.tag, context)
        self.assertEqual(builds, 1)

    def test_prepare_rejects_malformed_existing_signature_before_rebuild(self) -> None:
        builds = 0

        def builder(profile: str, worktree: Path, output: Path, intent) -> ProfileBuild:
            nonlocal builds
            builds += 1
            if builds > 1:
                raise AssertionError("retry must not rebuild malformed existing output")
            return self.profile_build_with_signature(output, b"malformed-signature")

        def reject_malformed(profile, worktree, output, intent, assets) -> None:
            raise RuntimeError("malformed detached signature")

        context = self.context()
        context.profile_builder = builder
        context.profile_verifier = reject_malformed
        prepare(self.tag, context)
        with self.assertRaisesRegex(PrepareError, "existing release profile assets"):
            prepare(self.tag, context)
        self.assertEqual(builds, 1)

    def test_prepare_rejects_a_branch_projection_that_does_not_bind_scratch_main(self) -> None:
        self.github.branch = BranchProjection("main", True, "b" * 40)
        with self.assertRaisesRegex(PrepareError, "canonical main revision"):
            prepare(self.tag, self.context())

    def test_prepare_rejects_feature_branch_or_wrong_workflow_ci(self) -> None:
        self.github.runs = [DetailedRun(
            123, "push", self.target_sha, "completed", "success", "feature/release", "Core CI",
        )]
        with self.assertRaisesRegex(PrepareError, "merged-main"):
            prepare(self.tag, self.context())
        self.github.runs = [DetailedRun(
            123, "push", self.target_sha, "completed", "success", "main", "Other workflow",
        )]
        with self.assertRaisesRegex(PrepareError, "merged-main"):
            prepare(self.tag, self.context())

    def test_prepare_requires_a_full_exact_main_scope_manifest(self) -> None:
        cases = {
            "focused": CiScopeProjection(
                schema="lmdj.ci-scope.v2", base_sha="b" * 40, head_sha=self.target_sha,
                mode="focused", trusted_head=True,
                selected_lanes=("docs_static",), required_jobs=("docs-static",),
            ),
            "requested": CiScopeProjection(
                schema="lmdj.ci-scope.v2", base_sha="b" * 40, head_sha=self.target_sha,
                mode="requested", trusted_head=True,
                selected_lanes=tuple(sorted(LANES)),
                required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
            ),
            "other head": CiScopeProjection(
                schema="lmdj.ci-scope.v2", base_sha="b" * 40, head_sha="c" * 40,
                mode="full", trusted_head=True,
                selected_lanes=tuple(sorted(LANES)),
                required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
            ),
            "untrusted head": CiScopeProjection(
                schema="lmdj.ci-scope.v2", base_sha="b" * 40, head_sha=self.target_sha,
                mode="full", trusted_head=False,
                selected_lanes=tuple(sorted(LANES)),
                required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
            ),
        }
        for name, scope in cases.items():
            with self.subTest(name=name):
                self.github = FakeGitHub(self.target_sha, 123)
                self.github.scope = scope
                with self.assertRaisesRegex(PrepareError, "merged-main"):
                    prepare(self.tag, self.context())
                self.assertIsNone(self.git.local_tag)

    def test_prepare_requires_a_successful_same_run_gate(self) -> None:
        cases = {
            "missing gate": [self.github.jobs[0]],
            "failed gate": [
                self.github.jobs[0],
                RunJobProjection(2, 123, "PR Gate", "completed", "failure", "Core CI", self.target_sha),
            ],
            "duplicate gate": [
                *self.github.jobs,
                RunJobProjection(3, 123, "PR Gate", "completed", "success", "Core CI", self.target_sha),
            ],
        }
        for name, jobs in cases.items():
            with self.subTest(name=name):
                self.github = FakeGitHub(self.target_sha, 123)
                self.github.jobs = jobs
                with self.assertRaisesRegex(PrepareError, "merged-main"):
                    prepare(self.tag, self.context())

    def test_prepare_separates_absent_evidence_from_a_transport_outage(self) -> None:
        for error, expected in (
            (CiScopeUnavailableError("retained scope evidence is absent"), "retained"),
            (CiScopeConflictError("scope artifact identity conflicts"), "merged-main"),
            (TimeoutError("fixture outage"), "unavailable"),
        ):
            with self.subTest(error=type(error).__name__):
                self.github = FakeGitHub(self.target_sha, 123)
                self.github.scope_error = error
                with self.assertRaisesRegex(PrepareError, expected):
                    prepare(self.tag, self.context())

    def test_prepare_uses_canonical_authority_documents_instead_of_caller_ledger(self) -> None:
        authority_ledger = self.ledger_fixture("allocated")
        context = self.context()
        context.authority_reader = lambda worktree: (self.policy, authority_ledger)
        with self.assertRaisesRegex(PrepareError, "releasable"):
            prepare(self.tag, context)

    def test_prepare_rejects_wrong_sha_and_non_main_target(self) -> None:
        self.github.runs[0] = RunProjection(123, "push", "b" * 40, "main", "Core CI", "completed", "success")
        with self.assertRaisesRegex(PrepareError, "successful"):
            prepare(self.tag, self.context())
        self.github.runs[0] = RunProjection(123, "push", self.target_sha, "main", "Core CI", "completed", "success")
        self.git.main_contains_target = False
        with self.assertRaisesRegex(PrepareError, "main ancestry"):
            prepare(self.tag, self.context())
        self.assertEqual(self.git.local_tag, None)

    def test_prepare_rejects_red_ci_and_branch_proof(self) -> None:
        self.github.runs[0] = RunProjection(123, "push", self.target_sha, "main", "Core CI", "completed", "failure")
        with self.assertRaisesRegex(PrepareError, "successful"):
            prepare(self.tag, self.context())
        self.github.runs[0] = RunProjection(123, "push", self.target_sha, "main", "Core CI", "completed", "success")
        self.proof_reader = lambda worktree, intent: ProductProof("feature/release", self.target_sha, "1.0.21.0", "1.0.21.0")
        with self.assertRaisesRegex(PrepareError, "merged-main Proof"):
            prepare(self.tag, self.context())

    def test_prepare_rejects_snapshot_drift(self) -> None:
        self.proof_reader = lambda worktree, intent: ProductProof("main", self.target_sha, "1.0.21.0", "1.0.20.0")
        with self.assertRaisesRegex(PrepareError, "snapshot"):
            prepare(self.tag, self.context())

    def test_prepare_requires_kind_specific_exact_target_validation(self) -> None:
        self.git.target_validation_error = RuntimeError("assembly provenance mismatch")
        with self.assertRaisesRegex(PrepareError, "exact release target"):
            prepare(self.tag, self.context())

    def test_failed_target_command_reports_a_sanitized_reason(self) -> None:
        def executor(vector, **kwargs):
            if vector[0] != "node":
                return subprocess.CompletedProcess(vector, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(
                vector, 1, stdout="",
                stderr=(
                    "snapshot introducing commit cannot be resolved: "
                    "GITHUB_TOKEN=ghs_fixturesecret000111222333 "
                    "https://token:ghs_fixturesecret000111222333@github.com/endaye/lmdj "
                    "at /home/runner/work/lmdj/lmdj\n"
                ),
            )

        intent = ReleaseIntent(
            "fixture", ReleaseKind.PRODUCT, CURRENT_PRODUCT_BUILD, "a" * 40,
            Disposition.RELEASABLE, "web-runtime-host", ("evidence.md",),
            "canary", CURRENT_PRODUCT_BUILD, 1,
        )
        with self.assertRaises(TargetValidationError) as raised:
            validate_release_target(ROOT, intent, runner=CommandRunner(executor=executor))
        message = str(raised.exception)
        self.assertIn("Product Portal snapshot provenance is invalid", message)
        self.assertIn("snapshot introducing commit cannot be resolved", message)
        self.assertIn("GITHUB_TOKEN=[redacted]", message)
        self.assertNotIn("ghs_fixturesecret000111222333", message)
        self.assertNotIn("/home/runner", message)

    def _product_target_tree(self, root: Path) -> None:
        for relative in (
            "products/lmdj/version.json",
            "products/lmdj/assembly.json",
            "products/lmdj/assembly.lock.json",
            f"apps/architecture-portal/versioned_metadata/version-{CURRENT_PRODUCT_BUILD}.json",
        ):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)

    def test_missing_npm_package_is_not_invalid_snapshot_provenance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lmdj-target-glob-") as directory:
            root = Path(directory)
            self._product_target_tree(root)
            script = root / "apps/docs-site/scripts/check-release-docs.mjs"
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text("import {glob} from 'glob';\n", encoding="utf-8")

            def executor(vector, **kwargs):
                if vector[0] == "python3":
                    return subprocess.CompletedProcess(vector, 0, stdout="", stderr="")
                return subprocess.run(vector, **kwargs)

            intent = ReleaseIntent(
                "fixture", ReleaseKind.PRODUCT, CURRENT_PRODUCT_BUILD, "a" * 40,
                Disposition.RELEASABLE, "web-runtime-host", ("evidence.md",),
                "canary", CURRENT_PRODUCT_BUILD, 1,
            )
            validate_release_target(root, intent, runner=CommandRunner(executor=executor))

    def test_portal_provenance_command_failure_stays_invalid(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lmdj-target-provenance-") as directory:
            root = Path(directory)
            self._product_target_tree(root)
            script = root / "apps/docs-site/scripts/check-release-docs.mjs"
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(
                "console.error("
                "'source projection is neither direct-parent nor squash-equivalent'"
                ");\nprocess.exit(1);\n",
                encoding="utf-8",
            )

            def executor(vector, **kwargs):
                if vector[0] == "python3":
                    return subprocess.CompletedProcess(vector, 0, stdout="", stderr="")
                return subprocess.run(vector, **kwargs)

            intent = ReleaseIntent(
                "fixture", ReleaseKind.PRODUCT, CURRENT_PRODUCT_BUILD, "a" * 40,
                Disposition.RELEASABLE, "web-runtime-host", ("evidence.md",),
                "canary", CURRENT_PRODUCT_BUILD, 1,
            )
            with self.assertRaises(TargetValidationError) as raised:
                validate_release_target(root, intent, runner=CommandRunner(executor=executor))
            message = str(raised.exception)
            self.assertIn("Product Portal snapshot provenance is invalid", message)
            self.assertIn("source projection is neither direct-parent nor squash-equivalent", message)

    def test_sanitized_diagnostics_drop_credentials_and_bound_length(self) -> None:
        self.assertEqual(
            sanitize_diagnostic("fatal: https://x-access-token:secret@github.com/o/r denied"),
            "fatal: <redacted>@github.com/o/r denied",
        )
        self.assertEqual(
            sanitize_diagnostic("AUTHORIZATION: basic QUJDOjEyMw=="),
            "AUTHORIZATION: basic [redacted]",
        )
        self.assertEqual(
            sanitize_diagnostic("token github_pat_11ABCDEFG0123456789abc rejected"),
            "token [redacted] rejected",
        )
        self.assertEqual(sanitize_diagnostic("  a\n\n  b  "), "a b")

    def test_sanitized_diagnostics_keep_flags_and_both_ends(self) -> None:
        self.assertEqual(
            sanitize_diagnostic("Command failed: git archive --format=tar --output=/tmp/a.tar HEAD"),
            "Command failed: git archive --format=tar --output=<path> HEAD",
        )
        self.assertEqual(
            sanitize_diagnostic("gh --token=ghs_fixturesecret000111222 run"),
            "gh --token=[redacted] run",
        )
        self.assertEqual(
            sanitize_diagnostic("GITHUB_TOKEN=ghs_fixturesecret000111222 git"),
            "GITHUB_TOKEN=[redacted] git",
        )
        bounded = sanitize_diagnostic("head " + "x" * 400 + " fatal: the real reason", limit=60)
        self.assertLessEqual(len(bounded), 60)
        self.assertTrue(bounded.startswith("head"))
        self.assertTrue(bounded.endswith("the real reason"))
        self.assertIn(" ... ", bounded)

    def test_product_snapshot_validator_imports_without_portal_packages(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-node-loader-") as directory:
            loader = Path(directory) / "builtins-only.mjs"
            loader.write_text(
                """export async function resolve(specifier, context, nextResolve) {
  if (!(specifier.startsWith('node:') || specifier.startsWith('.') ||
        specifier.startsWith('/') || specifier.startsWith('file:'))) {
    throw new Error(`external package import denied: ${specifier}`);
  }
  return nextResolve(specifier, context);
}
""",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "node", "--experimental-loader", loader.as_uri(),
                    "--input-type=module", "--eval",
                    f"import({json.dumps((ROOT / 'apps/docs-site/scripts/lib/repo-facts.mjs').as_uri())})",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

    def test_prepare_rejects_forbidden_disposition_and_historical_exception(self) -> None:
        self.ledger = self.ledger_fixture("allocated")
        with self.assertRaisesRegex(PrepareError, "releasable"):
            prepare(self.tag, self.context())
        self.ledger = self.ledger_fixture()
        authority_ledger = ReleaseLedger(
            self.ledger.entries,
            (HistoricalException(
                self.tag, self.target_sha, "2026-08-12T23:59:59Z",
                "pre-pipeline-ci-evidence", "audit only",
                ("docs/quality/example-proof.md",),
            ),),
        )
        context = self.context()
        context.authority_reader = lambda worktree: (self.policy, authority_ledger)
        with self.assertRaisesRegex(PrepareError, "historical exception"):
            prepare(self.tag, context)

    def test_prepare_rejects_remote_or_conflicting_local_tag(self) -> None:
        self.git.remote_tag = LocalTag("b" * 40, self.target_sha, self.policy.product_fingerprint)
        with self.assertRaisesRegex(PrepareError, "remote tag"):
            prepare(self.tag, self.context())
        self.git.remote_tag = None
        self.git.local_tag = LocalTag("c" * 40, "c" * 40, self.policy.product_fingerprint)
        with self.assertRaisesRegex(PrepareError, "local tag conflict"):
            prepare(self.tag, self.context())

    def test_prepare_rejects_key_role_substitution(self) -> None:
        context = self.context()
        context = PrepareContext(
            **{**context.__dict__, "tag_signer_fingerprint": self.policy.checksum_fingerprint}
        )
        with self.assertRaisesRegex(PrepareError, "Product signer"):
            prepare(self.tag, context)
        context = PrepareContext(
            **{**self.context().__dict__, "checksum_signer_fingerprint": self.policy.product_fingerprint}
        )
        with self.assertRaisesRegex(PrepareError, "checksum signer"):
            prepare(self.tag, context)

    def test_exact_profiles_have_closed_asset_inventories(self) -> None:
        source = build_profile("source-only", self.root, self.root / "source", None)
        self.assertEqual(source.assets, ())
        with self.assertRaisesRegex(ProfileError, "Product intent"):
            build_profile("web-hosts", self.root, self.root / "web-hosts", None)
        with self.assertRaisesRegex(ValueError, "unknown release profile"):
            build_profile("source-and-binary", self.root, self.root / "invalid", None)

    def test_dual_web_host_profile_accepts_exactly_two_signed_triplets(self) -> None:
        output = self.root / "dual-assets"
        output.mkdir()
        names = (
            "lmdj-creator-web-2.1.1-product-1.0.21.0.zip",
            "lmdj-creator-web-2.1.1-product-1.0.21.0.zip.sha256",
            "lmdj-creator-web-2.1.1-product-1.0.21.0.zip.sha256.asc",
            "lmdj-web-runtime-host-2.1.1-product-1.0.21.0.zip",
            "lmdj-web-runtime-host-2.1.1-product-1.0.21.0.zip.sha256",
            "lmdj-web-runtime-host-2.1.1-product-1.0.21.0.zip.sha256.asc",
        )
        assets = []
        for name in names:
            path = output / name
            path.write_bytes(name.encode("utf-8"))
            assets.append(
                AssetBuild(
                    path,
                    name,
                    path.stat().st_size,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
        intent = ReleaseIntent(
            self.tag,
            ReleaseKind.PRODUCT,
            "1.0.21.0",
            self.target_sha,
            Disposition.RELEASABLE,
            "web-hosts",
            ("evidence.md",),
            "canary",
            "1.0.21.0",
            123,
        )

        verified = _verify_profile_assets(intent, ProfileBuild(tuple(assets)))

        self.assertEqual(tuple(asset.name for asset in verified), names)

    def test_dual_web_host_builder_emits_the_exact_six_asset_inventory(self) -> None:
        for host, version in (("creator-web", "2.1.1"), ("web-runtime-host", "2.1.1")):
            module = self.root / f"apps/{host}/module.json"
            module.parent.mkdir(parents=True)
            module.write_text(json.dumps({"version": version}), encoding="utf-8")
            adapter = module.parent / "tools/release_bundle.py"
            adapter.parent.mkdir()
            adapter.write_text(
                "def stage_release_bundle(**arguments):\n"
                "    arguments['output_root'].mkdir(parents=True)\n",
                encoding="utf-8",
            )
        key = self.root / ".github/release-signing-keys/lmdj-release-checksum.asc"
        key.parent.mkdir(parents=True)
        key.write_text("fixture", encoding="ascii")
        calls: list[tuple[str, ...]] = []

        def executor(vector, **kwargs):
            calls.append(vector)
            if vector[:2] == ("bash", "scripts/creator-web.sh") and vector[2] == "proof":
                dist = self.root / "build/web/creator/dist"
                dist.mkdir(parents=True)
                (dist / "host-manifest.json").write_text(
                    '{"host_version":"2.1.1","product_build":"1.0.21.0"}',
                    encoding="utf-8",
                )
            if vector[:2] == ("bash", "scripts/web-runtime-host.sh") and vector[2] == "proof":
                dist = self.root / "build/web/host/dist"
                dist.mkdir(parents=True)
                (dist / "host-manifest.json").write_text(
                    '{"host_version":"2.1.1","product_build":"1.0.21.0"}',
                    encoding="utf-8",
                )
            return subprocess.CompletedProcess(vector, 0, stdout="", stderr="")

        runtime = ProfileRuntime(
            runner=CommandRunner(executor=executor),
            checksum_verifier=RecordingVerifier(),
            checksum_home=self.root,
            checksum_fingerprint=self.policy.checksum_fingerprint,
        )
        intent = ReleaseIntent(
            self.tag,
            ReleaseKind.PRODUCT,
            "1.0.21.0",
            self.target_sha,
            Disposition.RELEASABLE,
            "web-hosts",
            ("evidence.md",),
            "canary",
            "1.0.21.0",
            123,
        )

        build = build_profile(
            "web-hosts",
            self.root,
            self.root / "release-assets",
            intent,
            runtime=runtime,
        )

        self.assertEqual(
            tuple(asset.name for asset in build.assets),
            (
                "lmdj-creator-web-2.1.1-product-1.0.21.0.zip",
                "lmdj-creator-web-2.1.1-product-1.0.21.0.zip.sha256",
                "lmdj-creator-web-2.1.1-product-1.0.21.0.zip.sha256.asc",
                "lmdj-web-runtime-host-2.1.1-product-1.0.21.0.zip",
                "lmdj-web-runtime-host-2.1.1-product-1.0.21.0.zip.sha256",
                "lmdj-web-runtime-host-2.1.1-product-1.0.21.0.zip.sha256.asc",
            ),
        )
        self.assertEqual(
            calls[:2],
            [
                ("npm", "--prefix", "tests/platform/web", "ci"),
                ("npm", "--prefix", "apps/creator-web", "ci"),
            ],
        )
        verify_existing_profile(
            "web-hosts",
            self.root,
            self.root / "release-assets",
            intent,
            build.assets,
            runtime,
        )
        with self.assertRaisesRegex(ProfileError, "inventory"):
            verify_existing_profile(
                "web-hosts",
                self.root,
                self.root / "release-assets",
                intent,
                build.assets[:-1],
                runtime,
            )

    def test_web_profile_installs_locked_dependencies_before_configuring(self) -> None:
        dependencies_ready = False

        def executor(vector, **kwargs):
            nonlocal dependencies_ready
            if vector == ("npm", "--prefix", "tests/platform/web", "ci"):
                dependencies_ready = (
                    kwargs["env"]["PATH"].split(os.pathsep)[0]
                    == "/locked/node/bin"
                )
                return subprocess.CompletedProcess(vector, 0, stdout="", stderr="")
            if vector == ("bash", "scripts/web-runtime-host.sh", "configure"):
                detail = (
                    "diagnostic stop after dependency bootstrap"
                    if dependencies_ready
                    else "locked Web dependencies are absent"
                )
                return subprocess.CompletedProcess(vector, 2, stdout="", stderr=detail)
            return subprocess.CompletedProcess(
                vector, 70, stdout="", stderr="unexpected release builder command",
            )

        runtime = ProfileRuntime(
            runner=CommandRunner(executor=executor),
            checksum_verifier=RecordingVerifier(),
            checksum_home=self.root,
            checksum_fingerprint=self.policy.checksum_fingerprint,
        )
        with (
            mock.patch.dict(
                os.environ,
                {"EMSDK_NODE": "/locked/node/bin/node", "PATH": "/host/bin"},
            ),
            self.assertRaises(CommandError) as raised,
        ):
            build_profile(
                "web-runtime-host", self.root, self.root / "web-output",
                self.ledger.entries[0], runtime=runtime,
            )
        self.assertEqual(
            raised.exception.detail,
            "diagnostic stop after dependency bootstrap",
        )

    def test_default_proof_reader_parses_the_tracked_immutable_snapshot(self) -> None:
        intent = next(
            entry for entry in load_ledger_document(
                {
                    "schema": "lmdj.release-intents.v1",
                    "entries": [{
                        "tag": "lmdj-v1.0.20.0", "kind": "product", "identity": "1.0.20.0",
                        "target_revision": "f4674ada631d6af7ad8b9dd9f440671c2736d293",
                        "channel": "canary", "disposition": "releasable", "profile": "web-runtime-host",
                        "snapshot": "1.0.20.0", "merged_main_run_id": 123,
                        "evidence_paths": ["docs/release-evidence/example.md"],
                    }],
                    "historical_exceptions": [],
                }, self.policy
            ).entries
        )
        proof = read_product_snapshot_proof(ROOT, intent)
        self.assertEqual(proof.product_build, "1.0.20.0")
        self.assertEqual(proof.snapshot, "1.0.20.0")

    def test_cli_context_uses_canonical_authority_and_real_snapshot_reader(self) -> None:
        context = cli.build_context(
            self.root,
            git=self.git,
            github=self.github,
            authority_reader=lambda worktree: (self.policy, self.ledger),
        )
        self.assertIs(context.proof_reader, read_product_snapshot_proof)
        self.assertEqual(context.policy.repository, "endaye/lmdj")
        self.assertIn("fetch:endaye/lmdj:main", self.git.calls)
        self.assertTrue(callable(context.profile_verifier))

    def test_cli_context_keeps_checksum_keyring_distinct_from_product_keyring(self) -> None:
        captured: list[ProfileRuntime] = []

        def capture_builder(runtime: ProfileRuntime):
            captured.append(runtime)
            return mock.Mock()

        with (
            mock.patch.dict(
                os.environ,
                {"GNUPGHOME": "/operator/product-keyring"},
            ),
            mock.patch.object(cli, "default_profile_builder", side_effect=capture_builder),
        ):
            cli.build_context(
                self.root,
                git=self.git,
                github=self.github,
                authority_reader=lambda worktree: (self.policy, self.ledger),
            )

        self.assertEqual(len(captured), 1)
        self.assertEqual(
            captured[0].checksum_home,
            Path.home() / ".gnupg-lmdj-release",
        )

    def test_cli_context_uses_logged_in_gh_credentials_when_token_env_is_empty(self) -> None:
        token = "ghp_LOCAL_CREDENTIAL_FIXTURE"
        requests: list[tuple[str, str, dict[str, str]]] = []

        def executor(arguments, **kwargs):
            self.assertEqual(tuple(arguments), ("gh", "auth", "token"))
            return subprocess.CompletedProcess(arguments, 0, stdout=token + "\n", stderr="")

        def transport(method, url, headers, body):
            requests.append((method, url, dict(headers)))
            return HttpResponse(200, {}, json.dumps({
                "name": "main",
                "protected": True,
                "commit": {"sha": self.target_sha},
            }).encode("utf-8"))

        def client_factory(*, token=None):
            return GitHubClient(http_transport=transport, token=token)

        self.git.runner = CommandRunner(executor=executor)
        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "", "GH_TOKEN": ""}),
            mock.patch.object(cli, "GitHubClient", side_effect=client_factory),
        ):
            context = cli.build_context(
                self.root,
                git=self.git,
                authority_reader=lambda worktree: (self.policy, self.ledger),
            )
            branch = context.github.get_branch("endaye/lmdj", "main")

        self.assertEqual(branch.commit_sha, self.target_sha)
        self.assertEqual(
            requests[0][2].get("Authorization"),
            f"Bearer {token}",
        )

    def test_cli_normalizes_usage_and_verification_failures(self) -> None:
        self.assertEqual(cli.main(["prepare"]), 64)
        self.assertEqual(cli.main(["--repo-root", str(self.root), "prepare", "bad-tag"]), 2)

    def test_cli_reports_the_sanitized_subprocess_reason(self) -> None:
        diagnostic = "Web Runtime Host error: EMSDK is not configured"
        output = io.StringIO()
        with (
            mock.patch.object(cli, "build_context", return_value=object()),
            mock.patch.object(
                cli, "prepare",
                side_effect=CommandError(
                    "release command failed: bash (exit 2)", detail=diagnostic,
                ),
            ),
            redirect_stderr(output),
        ):
            status = cli.main([
                "--repo-root", str(self.root), "prepare", self.tag,
            ])
        self.assertEqual(status, 2)
        self.assertIn(diagnostic, output.getvalue())

    def test_core_profile_verifies_the_fresh_signature_before_returning_assets(self) -> None:
        archive = self.root / "core.zip"
        checksum = self.root / "core.zip.sha256"
        key = self.root / "checksum.asc"
        archive.write_bytes(b"archive")
        checksum.write_text(
            hashlib.sha256(b"archive").hexdigest() + "  core.zip\n", encoding="ascii"
        )
        key.write_text("public", encoding="ascii")
        verifier = RecordingVerifier()
        runtime = ProfileRuntime(
            runner=CommandRunner(), checksum_verifier=verifier, checksum_home=self.root,
            checksum_fingerprint=self.policy.checksum_fingerprint,
        )
        _stage_and_sign((archive, checksum), self.root / "staged", runtime, key)
        self.assertEqual([name for name, _ in verifier.calls], ["sign", "import", "verify"])
        self.assertEqual(verifier.calls[1][1], verifier.calls[2][1])
        self.assertEqual(verifier.calls[1][1], 0o700)

    def test_web_profile_loads_an_exact_target_verifier_that_uses_dataclasses(self) -> None:
        worktree = self.root / "worktree"
        tool = worktree / "apps/web-runtime-host/tools/release_bundle.py"
        tool.parent.mkdir(parents=True)
        tool.write_text(
            """from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class LoadedVerifier:
    identity: str

def stage_release_bundle(**arguments):
    LoadedVerifier("exact-target")
    Path(arguments["repo_root"], "verifier-loaded").write_text("yes", encoding="ascii")
    arguments["output_root"].mkdir(parents=True)
""",
            encoding="utf-8",
        )
        output = self.root / "output"
        output.mkdir()
        paths = tuple(output / name for name in ("host.zip", "host.zip.sha256", "host.zip.sha256.asc"))
        for path in paths:
            path.write_bytes(b"fixture")
        build = ProfileBuild(tuple(
            AssetBuild(path, path.name, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in paths
        ))
        runtime = ProfileRuntime(
            runner=CommandRunner(), checksum_verifier=RecordingVerifier(), checksum_home=self.root,
            checksum_fingerprint=self.policy.checksum_fingerprint,
        )
        previous_module = sys.modules.pop("lmdj_release_bundle", None)

        def restore_module() -> None:
            sys.modules.pop("lmdj_release_bundle", None)
            if previous_module is not None:
                sys.modules["lmdj_release_bundle"] = previous_module

        self.addCleanup(restore_module)

        try:
            _stage_web_bundle(
                WEB_RUNTIME_SPEC,
                worktree,
                build,
                output,
                self.ledger.entries[0],
                "1.2.3",
                runtime,
            )
        except Exception as error:
            self.fail(f"exact-target release verifier import failed: {type(error).__name__}: {error}")

        self.assertEqual((worktree / "verifier-loaded").read_text(encoding="ascii"), "yes")
        self.assertFalse((output / ".verified").exists())

    def test_existing_core_profile_assets_are_reverified_in_a_fresh_keyring(self) -> None:
        assets_root = self.root / "existing-assets"
        assets_root.mkdir()
        archive = assets_root / "core.zip"
        checksum = assets_root / "core.zip.sha256"
        signature = assets_root / "core.zip.sha256.asc"
        manifest = assets_root / "core.build-manifest.json"
        key = self.root / ".github/release-signing-keys/lmdj-release-checksum.asc"
        key.parent.mkdir(parents=True)
        archive.write_bytes(b"persisted archive")
        checksum.write_text(
            hashlib.sha256(archive.read_bytes()).hexdigest() + "  core.zip\n", encoding="ascii"
        )
        signature.write_text("persisted detached signature", encoding="ascii")
        manifest.write_text(json.dumps({
            "contract": "lmdj.build-manifest.v1",
            "product": {"id": "lmdj", "version": "1.0.21.0"},
            "git_revision": self.target_sha,
        }), encoding="utf-8")
        key.write_text("public", encoding="ascii")
        assets = tuple(
            AssetBuild(path, path.name, len(path.read_bytes()), hashlib.sha256(path.read_bytes()).hexdigest())
            for path in (archive, checksum, signature, manifest)
        )
        verifier = RecordingVerifier()
        runtime = ProfileRuntime(
            runner=CommandRunner(), checksum_verifier=verifier, checksum_home=self.root,
            checksum_fingerprint=self.policy.checksum_fingerprint,
        )
        intent = self.ledger.entries[0]
        verify_existing_profile("core-package", self.root, assets_root, intent, assets, runtime)
        self.assertEqual([name for name, _ in verifier.calls], ["import", "verify"])
        self.assertEqual(verifier.calls[0][1], verifier.calls[1][1])
        self.assertEqual(verifier.calls[0][1], 0o700)

    def test_existing_core_profile_requires_the_detached_manifest(self) -> None:
        assets_root = self.root / "existing-assets"
        assets_root.mkdir()
        archive = assets_root / "core.zip"
        checksum = assets_root / "core.zip.sha256"
        signature = assets_root / "core.zip.sha256.asc"
        key = self.root / ".github/release-signing-keys/lmdj-release-checksum.asc"
        key.parent.mkdir(parents=True)
        archive.write_bytes(b"persisted archive")
        checksum.write_text(
            hashlib.sha256(archive.read_bytes()).hexdigest() + "  core.zip\n", encoding="ascii"
        )
        signature.write_text("persisted detached signature", encoding="ascii")
        key.write_text("public", encoding="ascii")
        assets = tuple(
            AssetBuild(path, path.name, len(path.read_bytes()), hashlib.sha256(path.read_bytes()).hexdigest())
            for path in (archive, checksum, signature)
        )
        runtime = ProfileRuntime(
            runner=CommandRunner(), checksum_verifier=RecordingVerifier(), checksum_home=self.root,
            checksum_fingerprint=self.policy.checksum_fingerprint,
        )
        with self.assertRaisesRegex(ProfileError, "detached Build Manifest"):
            verify_existing_profile(
                "core-package", self.root, assets_root, self.ledger.entries[0], assets, runtime
            )

    def test_existing_core_profile_rejects_a_manifest_for_another_build(self) -> None:
        assets_root = self.root / "existing-assets"
        assets_root.mkdir()
        archive = assets_root / "core.zip"
        checksum = assets_root / "core.zip.sha256"
        signature = assets_root / "core.zip.sha256.asc"
        manifest = assets_root / "core.build-manifest.json"
        key = self.root / ".github/release-signing-keys/lmdj-release-checksum.asc"
        key.parent.mkdir(parents=True)
        archive.write_bytes(b"persisted archive")
        checksum.write_text(
            hashlib.sha256(archive.read_bytes()).hexdigest() + "  core.zip\n", encoding="ascii"
        )
        signature.write_text("persisted detached signature", encoding="ascii")
        key.write_text("public", encoding="ascii")
        runtime = ProfileRuntime(
            runner=CommandRunner(), checksum_verifier=RecordingVerifier(), checksum_home=self.root,
            checksum_fingerprint=self.policy.checksum_fingerprint,
        )
        for document, message in (
            ({"contract": "other", "product": {"id": "lmdj", "version": "1.0.21.0"},
              "git_revision": self.target_sha}, "contract identity"),
            ({"contract": "lmdj.build-manifest.v1", "product": {"id": "lmdj", "version": "1.0.22.0"},
              "git_revision": self.target_sha}, "Product identity"),
            ({"contract": "lmdj.build-manifest.v1", "product": {"id": "lmdj", "version": "1.0.21.0"},
              "git_revision": "b" * 40}, "Git revision"),
        ):
            with self.subTest(message=message):
                manifest.write_text(json.dumps(document), encoding="utf-8")
                assets = tuple(
                    AssetBuild(
                        path, path.name, len(path.read_bytes()), hashlib.sha256(path.read_bytes()).hexdigest()
                    )
                    for path in (archive, checksum, signature, manifest)
                )
                with self.assertRaisesRegex(ProfileError, message):
                    verify_existing_profile(
                        "core-package", self.root, assets_root, self.ledger.entries[0], assets, runtime
                    )

    def test_checksum_record_requires_exact_canonical_bytes(self) -> None:
        archive = self.root / "archive.zip"
        checksum = self.root / "archive.zip.sha256"
        archive.write_bytes(b"archive")
        digest = hashlib.sha256(b"archive").hexdigest()
        for record in (
            f"{digest} *archive.zip\n",
            f"{digest}  archive.zip",
            f"{digest.upper()}  archive.zip\n",
            f"{digest}   archive.zip\n",
        ):
            with self.subTest(record=record):
                checksum.write_text(record, encoding="ascii")
                with self.assertRaisesRegex(Exception, "checksum"):
                    _verify_checksum(checksum, archive)

    def test_release_prepare_output_root_is_ignored(self) -> None:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", "build/release/"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_web_archive_builder_keeps_one_dist_tree_without_directory_entries(self) -> None:
        dist = self.root / "dist"
        assets = dist / "assets"
        assets.mkdir(parents=True)
        (dist / "index.html").write_text("host", encoding="utf-8")
        (assets / "runtime.mjs").write_text("runtime", encoding="utf-8")
        (dist / "index.html").chmod(0o600)
        (assets / "runtime.mjs").chmod(0o755)
        archive = self.root / "host.zip"
        _create_dist_zip(dist, archive)
        with zipfile.ZipFile(archive) as opened:
            self.assertEqual(
                opened.namelist(),
                ["dist/assets/runtime.mjs", "dist/index.html"],
            )
            self.assertEqual(
                [item.external_attr >> 16 & 0o777 for item in opened.infolist()],
                [0o644, 0o644],
            )


class ReleaseTargetValidationIntegrationTest(unittest.TestCase):
    def test_real_exact_target_validator_accepts_all_supported_identity_kinds(self) -> None:
        repository = GitRepository(ROOT)
        target = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.strip()
        cases = (
            (
                ReleaseKind.PRODUCT, CURRENT_PRODUCT_BUILD,
                "web-runtime-host", "canary", CURRENT_PRODUCT_BUILD,
            ),
            (ReleaseKind.MODULE, "core-cli@3.1.0", "source-only", None, None),
            (ReleaseKind.CONTRACT, "lmdj.capability.v2@2.0.0", "source-only", None, None),
            (ReleaseKind.PROVIDER, "local.proof.success@1.0.5", "source-only", None, None),
        )
        for kind, identity, profile, channel, snapshot in cases:
            with self.subTest(kind=kind.value):
                intent = ReleaseIntent(
                    "fixture", kind, identity, target, Disposition.RELEASABLE, profile,
                    ("evidence.md",), channel, snapshot, 1,
                )
                repository.validate_release_target(ROOT, intent)


if __name__ == "__main__":
    unittest.main()
