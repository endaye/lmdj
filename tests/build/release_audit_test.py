#!/usr/bin/env python3
"""Contract tests for read-only local and remote release audits."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.audit import (  # noqa: E402
    AuditContext, AuditReport, audit, format_report, write_report,
)
import tools.release.audit as audit_module  # noqa: E402
from tools.release.commands import CommandRunner  # noqa: E402
from tools.release.git_repository import GitRepositoryError  # noqa: E402
from tools.release.target_validation import (  # noqa: E402
    TargetValidationError,
    validate_release_target,
)
from tools.release.github_api import (  # noqa: E402
    BranchProjection,
    CiScopeConflictError,
    CiScopeProjection,
    CiScopeUnavailableError,
    DeploymentBranchPolicy,
    GitHubAsset,
    GitHubEnvironment,
    GitHubRelease,
    RunJobProjection,
    RunProjection,
)
from tools.release.model import load_ledger_document, load_policy  # noqa: E402
from tools.release.openpgp import OpenPgpError  # noqa: E402
from tools.release.prepare import LocalTag, ProductProof  # noqa: E402
from tools.release import cli  # noqa: E402
from tools.release import target_validation as target_validation_module  # noqa: E402


TARGET = "a" * 40
TAG_OBJECT = "b" * 40
PRODUCT = "2B5EE362F058800036AD4FB5116ECE156F954D29"
CHECKSUM = "CB928A6E89DE498851688EF1AAC3E7019FC1478B"
SYNTHETIC_PRODUCT_BUILD = "9.8.7.6"


def current_product_build(root: Path = ROOT) -> str:
    version = json.loads(
        (root / "products/lmdj/version.json").read_text(encoding="utf-8")
    )
    return ".".join(
        str(version[field])
        for field in ("milestone", "minor", "build", "patch")
    )


CURRENT_PRODUCT_BUILD = current_product_build()
CURRENT_PRODUCT_TAG = f"lmdj-v{CURRENT_PRODUCT_BUILD}"

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


class ReadOnlyGit:
    def __init__(self) -> None:
        self.tags: dict[str, LocalTag] = {}
        self.local_tags: dict[str, LocalTag] = {}
        self.fetches = 0
        self.remote_reads = 0
        self.local_reads = 0
        self.mutations: list[str] = []
        self.authority_root: Path | None = None
        self.detached_worktree_root: Path | None = None
        self.detached_worktree_error: Exception | None = None
        self.target_validation_error: Exception | None = None
        self.current_snapshot_validation_error: Exception | None = None
        self.current_snapshot_validator = None
        self.main_ancestor_targets = {TARGET}
        self.real_target_validation = False

    def fetch_authority(self, repository: str, branch: str) -> None:
        self.fetches += 1

    def main_revision(self) -> str:
        return TARGET

    def is_main_ancestor(self, target: str) -> bool:
        return target in self.main_ancestor_targets

    def is_revision_ancestor(self, ancestor: str, descendant: str) -> bool:
        return descendant == TARGET

    def validate_release_target(self, worktree: Path, intent) -> None:
        if self.target_validation_error is not None:
            raise self.target_validation_error
        if not self.real_target_validation:
            return

        def executor(vector, **kwargs):
            if vector and vector[0] == "python3":
                return subprocess.CompletedProcess(vector, 0, stdout="", stderr="")
            return subprocess.run(vector, **kwargs)

        try:
            validate_release_target(
                worktree, intent, runner=CommandRunner(executor=executor),
            )
        except TargetValidationError as error:
            raise GitRepositoryError(str(error)) from None

    def validate_current_product_snapshot(self, worktree: Path, identity: str) -> None:
        if self.current_snapshot_validation_error is not None:
            raise self.current_snapshot_validation_error
        if self.current_snapshot_validator is not None:
            self.current_snapshot_validator(worktree, identity)

    def remote_tag_state(self, tag: str) -> LocalTag | None:
        self.remote_reads += 1
        return self.tags.get(tag)

    def local_tag_state(self, tag: str) -> LocalTag | None:
        self.local_reads += 1
        return self.local_tags.get(tag)

    def list_remote_tags(self) -> dict[str, LocalTag]:
        return dict(self.tags)

    @contextmanager
    def detached_worktree(self, target: str):
        if self.detached_worktree_error is not None:
            raise self.detached_worktree_error
        selected_root = self.detached_worktree_root or self.authority_root
        if selected_root is None:
            raise RuntimeError("fixture canonical authority is unavailable")
        yield selected_root

    def create_local_tag(self, *args, **kwargs):
        self.mutations.append("create-local-tag")
        raise AssertionError("audit called a mutation method")

    def push_tag(self, *args, **kwargs):
        self.mutations.append("push-tag")
        raise AssertionError("audit called a mutation method")

    def delete_remote_tag(self, *args, **kwargs):
        self.mutations.append("delete-tag")
        raise AssertionError("audit called a mutation method")


class ReadOnlyGitHub:
    def __init__(self) -> None:
        self.branch = BranchProjection("main", True, TARGET)
        self.runs = [
            RunProjection(123, "push", TARGET, "main", "Core CI", "completed", "success")
        ]
        self.jobs = [
            RunJobProjection(1, 123, "Change Scope", "completed", "success", "Core CI", TARGET),
            RunJobProjection(2, 123, "PR Gate", "completed", "success", "Core CI", TARGET),
        ]
        self.scope = CiScopeProjection(
            schema="lmdj.ci-scope.v2", base_sha="a" * 40, head_sha=TARGET,
            mode="full", trusted_head=True,
            selected_lanes=tuple(sorted(LANES)),
            required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
        )
        self.scope_error: Exception | None = None
        self.releases: dict[str, GitHubRelease] = {}
        self.payloads: dict[int, bytes] = {}
        self.error: Exception | None = None
        self.reads = 0
        self.mutations: list[str] = []
        self.latest_release: GitHubRelease | None = None
        self.environment: GitHubEnvironment | None = GitHubEnvironment(
            "release", 0, None, False, True,
            (DeploymentBranchPolicy(1, "main", "branch"),),
        )

    def _read(self) -> None:
        self.reads += 1
        if self.error is not None:
            raise self.error

    def get_branch(self, repository: str, branch: str) -> BranchProjection:
        self._read()
        return self.branch

    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]:
        self._read()
        return list(self.runs)

    def list_run_jobs(self, repository: str, run_id: int) -> list[RunJobProjection]:
        self._read()
        return list(self.jobs)

    def get_ci_scope_manifest(self, repository: str, run: RunProjection) -> CiScopeProjection:
        self._read()
        if self.scope_error is not None:
            raise self.scope_error
        return self.scope

    def list_releases(self, repository: str) -> list[GitHubRelease]:
        self._read()
        return list(self.releases.values())

    def get_latest_release(self, repository: str) -> GitHubRelease | None:
        self._read()
        return self.latest_release

    def get_release_environment(self, repository: str) -> GitHubEnvironment | None:
        self._read()
        return self.environment

    def get_release_by_tag(self, repository: str, tag: str) -> GitHubRelease | None:
        self._read()
        return self.releases.get(tag)

    def list_release_assets(self, repository: str, release_id: int) -> list[GitHubAsset]:
        self._read()
        release = next(item for item in self.releases.values() if item.id == release_id)
        return list(release.assets)

    def download_asset(self, repository: str, release_id: int, asset: GitHubAsset) -> bytes:
        self._read()
        return self.payloads[asset.id]

    def create_draft_release(self, *args, **kwargs):
        self.mutations.append("create-release")
        raise AssertionError("audit called a mutation method")

    def upload_release_asset(self, *args, **kwargs):
        self.mutations.append("upload-asset")
        raise AssertionError("audit called a mutation method")

    def publish_release(self, *args, **kwargs):
        self.mutations.append("publish-release")
        raise AssertionError("audit called a mutation method")

    def delete_release(self, *args, **kwargs):
        self.mutations.append("delete-release")
        raise AssertionError("audit called a mutation method")


class ReleaseAuditFixture:
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-release-audit-")
        self.root = Path(self.temporary.name)
        (self.root / "evidence.md").write_text("fixture\n", encoding="utf-8")
        self.install_static_authority(self.root)
        # Legacy protocol regression; current prospective policy has its own
        # end-to-end verifier matrix in release_self_test_evidence_test.
        self.policy = replace(load_policy(ROOT / "tools/release/policy.json"), prospective_ci_protocol="ci-scope-v2")
        self.git = ReadOnlyGit()
        self.github = ReadOnlyGitHub()
        self.git.authority_root = self.root

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assert_audit_passes(self, report: AuditReport) -> None:
        """Fail with the audit's own rendered findings, not a bare `1 != 0`.

        `exit_code` collapses every reason into one integer, so
        `assertEqual(report.exit_code, 0)` names neither the failing subject
        nor the rule it broke; diagnosing one costs a separate local rerun of
        the whole audit. `format_report` is the same sanitized rendering the
        CLI emits, so the failure carries the reason at the point it is read.
        """
        if report.exit_code == 0:
            return
        if report.findings:
            observed = "at least one finding carries a non-success code"
            remedy = (
                "fix the subject named below, or -- when the finding is "
                "checkout-dependent rather than a real defect -- isolate it in "
                "the fixture, as "
                "test_repository_local_audit_does_not_assume_current_intent_count"
                " isolates the pre-squash intent target."
            )
        else:
            observed = "the audit produced no findings at all"
            remedy = (
                "an audit that reaches no conclusion is itself the defect: "
                "check that the fixture supplies the ledger, manifest, and "
                "intent projections this audit mode reads."
            )
        self.fail(
            f"why: release audit exit_code is {report.exit_code}, not 0. An "
            f"audit passes only when it has findings and every code is a "
            f"success code; here {observed}.\n"
            f"remedy: {remedy}\n"
            f"{format_report(report)}"
        )

    def entry(
        self,
        *,
        tag: str = "module/application-facade/v1.0.1",
        disposition: str = "published",
        kind: str = "module",
        identity: str = "application-facade@1.0.1",
        profile: str = "source-only",
    ) -> dict[str, object]:
        item: dict[str, object] = {
            "tag": tag,
            "kind": kind,
            "identity": identity,
            "target_revision": TARGET,
            "disposition": disposition,
            "profile": profile,
            "evidence_paths": ["evidence.md"],
        }
        if disposition not in ("abandoned", "superseded-unreleased", "allocated"):
            item["merged_main_run_id"] = 123
        if kind == "product":
            item["channel"] = "canary"
            if disposition == "published":
                item["snapshot"] = identity
        return item

    def active_entry(self) -> dict[str, object]:
        return {
            "tag": CURRENT_PRODUCT_TAG, "kind": "product",
            "identity": CURRENT_PRODUCT_BUILD,
            "target_revision": TARGET, "channel": "canary", "disposition": "allocated",
            "profile": "web-runtime-host", "snapshot": CURRENT_PRODUCT_BUILD,
            "evidence_paths": ["evidence.md"],
        }

    def install_static_authority(self, root: Path) -> None:
        paths = [
            ROOT / "products/lmdj/version.json",
            ROOT / "products/lmdj/assembly.json",
            ROOT / "products/lmdj/assembly.lock.json",
            ROOT / "apps/architecture-portal/versions.json",
            ROOT / (
                "apps/architecture-portal/versioned_metadata/"
                f"version-{CURRENT_PRODUCT_BUILD}.json"
            ),
            ROOT / ".github/release-signing-keys/lmdj-product.asc",
            ROOT / ".github/release-signing-keys/lmdj-release-checksum.asc",
            *ROOT.glob("packages/*/module.json"),
            *ROOT.glob("apps/*/module.json"),
            *ROOT.glob("providers/*/module.json"),
            *ROOT.glob("providers/*/include/**/factory.hpp"),
            *ROOT.glob("providers/*/src/provider.cpp"),
            *ROOT.glob("contracts/*/*.schema.json"),
        ]
        for source in paths:
            destination = root / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    def install_product_build(self, root: Path, identity: str) -> None:
        version_path = root / "products/lmdj/version.json"
        assembly_path = root / "products/lmdj/assembly.json"
        lock_path = root / "products/lmdj/assembly.lock.json"
        versions_path = root / "apps/architecture-portal/versions.json"
        source_snapshot_path = (
            root / "apps/architecture-portal/versioned_metadata"
            / f"version-{CURRENT_PRODUCT_BUILD}.json"
        )
        snapshot_path = (
            root / "apps/architecture-portal/versioned_metadata"
            / f"version-{identity}.json"
        )

        def write_document(path: Path, document: object) -> None:
            path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        milestone, minor, build, patch = (int(part) for part in identity.split("."))
        version = json.loads(version_path.read_text(encoding="utf-8"))
        version.update({
            "milestone": milestone,
            "minor": minor,
            "build": build,
            "patch": patch,
        })
        write_document(version_path, version)

        assembly = json.loads(assembly_path.read_text(encoding="utf-8"))
        assembly["product"]["version"] = identity
        write_document(assembly_path, assembly)

        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["product"]["version"] = identity
        lock["product_assembly"]["version"] = identity
        lock["assembly_sha256"] = hashlib.sha256(assembly_path.read_bytes()).hexdigest()
        write_document(lock_path, lock)

        snapshot = json.loads(source_snapshot_path.read_text(encoding="utf-8"))
        snapshot["product"]["version"] = identity
        snapshot["product_build"] = identity
        snapshot["assembly_lock_sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
        write_document(snapshot_path, snapshot)
        versions = json.loads(versions_path.read_text(encoding="utf-8"))
        write_document(versions_path, [identity, *versions])

    @contextmanager
    def repository_worktree(self, revision: str):
        with tempfile.TemporaryDirectory(prefix="lmdj-release-audit-repository-") as directory:
            worktree = Path(directory) / "target"
            subprocess.run(
                ["git", "-C", str(ROOT), "worktree", "add", "--detach", str(worktree), revision],
                check=True, capture_output=True, text=True,
            )
            try:
                yield worktree
            finally:
                subprocess.run(
                    ["git", "-C", str(ROOT), "worktree", "remove", "--force", str(worktree)],
                    check=True, capture_output=True, text=True,
                )

    def zero_intent_repository_context(self, root: Path, revision: str) -> AuditContext:
        assembly = json.loads((root / "products/lmdj/assembly.json").read_text(encoding="utf-8"))
        module = next(item for item in assembly["modules"] if item["id"] == "application-facade")
        identity = f"{module['id']}@{module['version']}"
        entry = self.entry(
            tag=f"module/{module['id']}/v{module['version']}",
            disposition="allocated",
            identity=identity,
        )
        entry["target_revision"] = revision
        entry["evidence_paths"] = ["AGENTS.md"]
        context = self.context(entries=[entry], ensure_current_product_intent=False)
        self.git.authority_root = root
        self.git.main_ancestor_targets.add(revision)
        self.git.current_snapshot_validator = (
            lambda worktree, product_build:
            target_validation_module.validate_current_product_snapshot(
                worktree, product_build,
            )
        )
        return replace(context, repo_root=root)

    def canonical_remote_context(self, context: AuditContext) -> AuditContext:
        def build_authority(root, policy, ledger):
            return replace(
                context,
                repo_root=root,
                policy=policy,
                ledger=ledger,
                tag_signer_fingerprint=policy.product_fingerprint,
                checksum_signer_fingerprint=policy.checksum_fingerprint,
                authority_reader=None,
                authority_context_builder=None,
            )

        return replace(
            context,
            authority_reader=lambda root: (self.policy, context.ledger),
            authority_context_builder=build_authority,
        )

    def install_glob_importing_release_docs(self) -> None:
        path = self.root / "apps/architecture-portal/scripts/check-release-docs.mjs"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("import {glob} from 'glob';\n", encoding="utf-8")

    def context(
        self,
        entries: list[dict[str, object]] | None = None,
        exceptions: list[dict[str, object]] | None = None,
        *,
        ensure_current_product_intent: bool = True,
    ) -> AuditContext:
        selected = list(entries if entries is not None else [self.entry()])
        if ensure_current_product_intent and not any(
            item.get("identity") == CURRENT_PRODUCT_BUILD
            for item in selected
        ):
            selected.append(self.active_entry())
        ledger = load_ledger_document({
            "schema": "lmdj.release-intents.v1",
            "entries": selected,
            "historical_exceptions": exceptions or [],
        }, self.policy)
        return AuditContext(
            repo_root=self.root,
            policy=self.policy,
            ledger=ledger,
            git=self.git,
            github=self.github,
            profile_verifier=lambda *args: None,
            proof_reader=lambda worktree, intent: ProductProof(
                "main", TARGET, intent.identity, intent.snapshot or intent.identity, TARGET,
            ),
            tag_signer_fingerprint=PRODUCT,
            checksum_signer_fingerprint=CHECKSUM,
        )

    def tag_state(self, *, target: str = TARGET, signer: str = PRODUCT) -> LocalTag:
        return LocalTag(TAG_OBJECT, target, signer)

    def release(
        self,
        tag: str,
        *,
        identifier: int = 17,
        draft: bool = False,
        prerelease: bool = False,
        name: str = "module application-facade@1.0.1",
        assets: tuple[GitHubAsset, ...] = (),
        target: str = TARGET,
        body: str | None = None,
        kind: str = "module",
        identity: str = "application-facade@1.0.1",
        profile: str = "source-only",
        channel: str | None = None,
    ) -> GitHubRelease:
        marker = {
            "schema": "lmdj.release-plan-marker.v1", "plan_schema": "lmdj.release-plan.v1",
            "plan_sha256": "0" * 64, "tag": tag, "tag_object": TAG_OBJECT,
            "target_revision": target,
            "intent": {"kind": kind, "identity": identity, "profile": profile},
        }
        if channel is not None:
            marker["intent"]["channel"] = channel
        if body is None:
            body = "<!-- lmdj.release-plan-marker.v1 " + json.dumps(
                marker, sort_keys=True, separators=(",", ":"),
            ) + " -->"
        return GitHubRelease(
            identifier, tag, name, body, draft, prerelease, False,
            f"https://github.com/endaye/lmdj/releases/tag/{tag}",
            f"https://uploads.github.com/repos/endaye/lmdj/releases/{identifier}/assets{{?name,label}}",
            assets, target,
        )


class ReleaseAuditTest(ReleaseAuditFixture, unittest.TestCase):
    def test_local_audit_has_no_remote_dependency_or_mutation(self) -> None:
        report = audit(self.context(), remote=False)
        self.assertEqual({item.code for item in report.findings}, {"ok"})
        self.assertEqual(self.git.fetches, 0)
        self.assertEqual(self.git.remote_reads, 0)
        self.assertEqual(self.git.local_reads, 2)
        self.assertEqual(self.github.reads, 0)
        self.assertEqual(self.git.mutations + self.github.mutations, [])

    def test_current_product_build_and_snapshot_do_not_require_release_intent(self) -> None:
        self.install_product_build(self.root, SYNTHETIC_PRODUCT_BUILD)
        context = self.context(
            entries=[self.entry()],
            ensure_current_product_intent=False,
        )
        context = replace(
            context,
            proof_reader=lambda *args: (_ for _ in ()).throw(
                AssertionError("Proof must not run without a current intent"),
            ),
        )
        self.git.target_validation_error = AssertionError(
            "exact-target validation must not run without a current intent",
        )
        report = audit(context, remote=False)
        self.assertEqual({item.code for item in report.findings}, {"ok"})

    def test_current_product_snapshot_is_required_without_release_intent(self) -> None:
        self.install_product_build(self.root, SYNTHETIC_PRODUCT_BUILD)
        snapshot = (
            self.root / "apps/architecture-portal/versioned_metadata"
            / f"version-{SYNTHETIC_PRODUCT_BUILD}.json"
        )
        snapshot.unlink()
        report = audit(
            self.context(
                entries=[self.entry()],
                ensure_current_product_intent=False,
            ),
            remote=False,
        )
        finding = next(item for item in report.findings if item.code == "unverifiable")
        self.assertIn("immutable Portal snapshot projection", finding.message)
        self.assertEqual(finding.sources, ("architecture-portal",))

    def test_multiple_current_product_intents_fail_closed(self) -> None:
        context = self.context()
        active_intent = context.ledger.intent_for_tag(CURRENT_PRODUCT_TAG)
        assert active_intent is not None
        finding = audit_module._local_repository_issue(
            context,
            [*context.ledger.entries, active_intent],
        )
        assert finding is not None
        self.assertEqual(finding.code, "unverifiable")
        self.assertIn("expected at most one", finding.message)

    def test_current_product_intent_exact_target_mismatch_fails_closed(self) -> None:
        self.git.target_validation_error = RuntimeError("current target mismatch")
        finding = audit(self.context(), remote=False).findings[0]
        self.assertEqual(finding.code, "unverifiable")
        self.assertIn("exact release target validation", finding.message)
        self.assertIn("current target mismatch", finding.message)

    def test_current_product_intent_proof_mismatch_fails_closed(self) -> None:
        context = replace(
            self.context(),
            proof_reader=lambda worktree, intent: ProductProof(
                "feature/pre-squash", TARGET, intent.identity,
                intent.snapshot or intent.identity, TARGET,
            ),
        )
        finding = audit(context, remote=False).findings[0]
        self.assertEqual(finding.code, "unverifiable")
        self.assertIn("merged-main Proof projection", finding.message)

    def test_local_audit_requires_every_non_abandoned_target_object(self) -> None:
        missing = self.entry(disposition="allocated")
        missing["target_revision"] = "d" * 40
        context = self.context(entries=[missing])
        (self.root / ".git").mkdir()

        def git_probe(command, **kwargs):
            missing_target = command[-1].startswith("d" * 40)
            return subprocess.CompletedProcess(command, 1 if missing_target else 0)

        with patch("tools.release.audit.subprocess.run", side_effect=git_probe):
            report = audit(context, remote=False, tag=CURRENT_PRODUCT_TAG)
        finding = next(item for item in report.findings if item.code == "unverifiable")
        self.assertIn("release intent target objects", finding.message)
        self.assertIn(str(missing["tag"]), finding.message)
        # The finding is the operator's only signal, so it carries both parts
        # docs/governance/pitfall-ledger.md requires: why the intent cannot be
        # verified, and the one command that repairs it.
        self.assertIn(str(missing["target_revision"]), finding.message)
        self.assertIn("cannot bind the intent to the commit it records", finding.message)
        self.assertIn("must not fetch it itself", finding.message)
        self.assertIn("remedy: run scripts/release.sh hydrate", finding.message)

    def test_explicit_unregistered_tag_is_unauthorized_in_both_modes(self) -> None:
        tag = "module/not-in-ledger/v9.9.9"
        for remote in (False, True):
            with self.subTest(remote=remote, tag=tag):
                report = audit(self.context(), remote=remote, tag=tag)
                self.assertEqual({item.code for item in report.findings}, {"unauthorized"})

        zero_product_intent = self.context(
            entries=[self.entry()], ensure_current_product_intent=False,
        )
        for remote in (False, True):
            with self.subTest(remote=remote, tag=CURRENT_PRODUCT_TAG):
                report = audit(
                    zero_product_intent, remote=remote, tag=CURRENT_PRODUCT_TAG,
                )
                self.assertEqual({item.code for item in report.findings}, {"unauthorized"})

    def test_local_audit_does_not_require_abandoned_target_objects(self) -> None:
        abandoned = self.entry(
            tag="lmdj-v1.0.16.6", disposition="abandoned", kind="product",
            identity="1.0.16.6", profile="web-runtime-host",
        )
        abandoned["target_revision"] = "d" * 40
        context = self.context(entries=[abandoned])
        (self.root / ".git").mkdir()

        def cat_file(command, **kwargs):
            return subprocess.CompletedProcess(
                command, 1 if command[-1].startswith("d" * 40) else 0,
            )

        with patch("tools.release.audit.subprocess.run", side_effect=cat_file):
            report = audit(context, remote=False, tag=CURRENT_PRODUCT_TAG)
        self.assertEqual({item.code for item in report.findings}, {"ok"})

    def test_local_same_name_tag_conflict_is_visible_but_diagnostic_only(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.local_tags[tag] = self.tag_state(target="c" * 40, signer=CHECKSUM)
        report = audit(self.context(), remote=False, tag=tag)
        diagnostic = next(item for item in report.findings if item.subject == f"local:{tag}")
        self.assertEqual(diagnostic.code, "conflict")
        self.assertIn("not authoritative", diagnostic.message)
        self.assertEqual(report.exit_code, 1)

    def test_remote_audit_requires_kind_specific_exact_target_validation(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        self.git.target_validation_error = RuntimeError("module manifest mismatch")

        report = audit(self.context(), remote=True, tag=tag)

        finding = next(item for item in report.findings if item.subject == tag)
        self.assertEqual(finding.code, "unverifiable")
        self.assertEqual(finding.subject, tag)
        self.assertEqual(finding.sources, ("exact-target",))
        self.assertIn("exact release target", finding.message)
        self.assertIn("RuntimeError: module manifest mismatch", finding.message)
        self.assertIn("module manifest mismatch", format_report(report))
        self.assertIn("module manifest mismatch", json.dumps(report.to_document(), sort_keys=True))

    def test_remote_exact_target_detail_is_sanitized_and_bounded(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        secret = "ghs_fixturesecret000111222333"
        self.git.target_validation_error = RuntimeError(
            "target rule failed "
            f"GITHUB_TOKEN={secret} "
            f"https://token:{secret}@github.com/endaye/lmdj "
            "at /home/runner/work/lmdj/lmdj "
            + ("middle " * 200)
            + "final exact-target rule"
        )

        report = audit(self.context(), remote=True, tag=tag)

        finding = next(item for item in report.findings if item.subject == tag)
        prefix = "exact release target identity or support metadata is invalid"
        self.assertEqual(finding.code, "unverifiable")
        self.assertEqual(finding.sources, ("exact-target",))
        self.assertTrue(finding.message.startswith(f"{prefix} (RuntimeError: target rule failed"))
        self.assertIn("GITHUB_TOKEN=[redacted]", finding.message)
        self.assertIn("<path>", finding.message)
        self.assertIn("final exact-target rule", finding.message)
        self.assertNotIn(secret, finding.message)
        self.assertNotIn("/home/runner", finding.message)
        self.assertLessEqual(
            len(finding.message),
            len(prefix) + 3 + len("RuntimeError: ") + audit_module._REASON_LIMIT,
        )

    def test_remote_exact_target_detail_neutralizes_terminal_and_format_controls(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        secret = "ghs_controlfixture000111222333"
        self.git.target_validation_error = RuntimeError(
            "terminal "
            "\x1b[31mred\x1b[0m "
            "\x1b]8;;mailto:test@example.invalid\x1b\\link\x1b]8;;\x1b\\ "
            "bell\x07 bidi\u202e "
            f"GITHUB_TOKEN={secret} "
            "at /home/runner/work/lmdj/lmdj "
            + ("\x1b[2Kfill " * 80)
            + "final exact-target control rule"
        )

        report = audit(self.context(), remote=True, tag=tag)

        finding = next(item for item in report.findings if item.subject == tag)
        prefix = "exact release target identity or support metadata is invalid"
        for rendered in (finding.message, format_report(report)):
            self.assertIn("\\u001b[31mred\\u001b[0m", rendered)
            self.assertIn(
                "\\u001b]8;;mailto:test@example.invalid\\u001b" + "\\",
                rendered,
            )
            self.assertIn("\\u0007", rendered)
            self.assertIn("\\u202e", rendered)
            self.assertIn("GITHUB_TOKEN=[redacted]", rendered)
            self.assertIn("<path>", rendered)
            self.assertNotIn("\x1b", rendered)
            self.assertNotIn("\x07", rendered)
            self.assertNotIn("\u202e", rendered)
            self.assertNotIn(secret, rendered)
            self.assertNotIn("/home/runner", rendered)
        self.assertLessEqual(
            len(finding.message),
            len(prefix) + 3 + len("RuntimeError: ") + audit_module._REASON_LIMIT,
        )

    def test_remote_exact_target_worktree_entry_failure_uses_authority_root(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        self.git.detached_worktree_error = RuntimeError(f"entry failed at {self.root}")

        report = audit(self.context(), remote=True, tag=tag)

        finding = next(item for item in report.findings if item.subject == tag)
        self.assertIn("RuntimeError: entry failed at <repo>", finding.message)
        self.assertNotIn("<path>", finding.message)
        self.assertNotIn(str(self.root), finding.message)

    def test_remote_exact_target_validation_failure_uses_exact_worktree_root(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        exact_root = self.root.parent / f"{self.root.name}-exact-target"
        self.git.detached_worktree_root = exact_root
        self.git.target_validation_error = RuntimeError(
            f"target {exact_root} authority {self.root}",
        )

        report = audit(self.context(), remote=True, tag=tag)

        finding = next(item for item in report.findings if item.subject == tag)
        self.assertIn("RuntimeError: target <repo> authority <path>", finding.message)
        self.assertNotIn(str(exact_root), finding.message)
        self.assertNotIn(str(self.root), finding.message)

    def test_remote_audit_does_not_treat_missing_portal_npm_package_as_invalid_provenance(self) -> None:
        self.install_glob_importing_release_docs()
        self.git.real_target_validation = True
        report = audit(self.context(entries=[]), remote=True, tag=CURRENT_PRODUCT_TAG)
        finding = next(item for item in report.findings if item.subject == CURRENT_PRODUCT_TAG)
        self.assertEqual(finding.code, "ok")
        self.assertNotIn("Cannot find package", finding.message)
        self.assertNotIn("provenance is invalid", finding.message)
        self.assertEqual(self.git.mutations + self.github.mutations, [])

    def test_remote_audit_reports_backfilled_product_name_instead_of_missing_glob(self) -> None:
        item = self.entry(
            tag=CURRENT_PRODUCT_TAG, disposition="published", kind="product",
            identity=CURRENT_PRODUCT_BUILD, profile="web-runtime-host",
        )
        tag = str(item["tag"])
        self.install_glob_importing_release_docs()
        self.git.real_target_validation = True
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(
            tag,
            name=f"LMDJ Product Build {CURRENT_PRODUCT_BUILD} · canary",
            prerelease=True,
            kind="product",
            identity=CURRENT_PRODUCT_BUILD,
            profile="web-runtime-host",
            channel="canary",
        )
        report = audit(self.context([item]), remote=True, tag=tag)
        finding = next(item for item in report.findings if item.subject == tag)
        self.assertEqual(finding.code, "conflict")
        self.assertEqual(finding.sources, ("github-release",))
        self.assertIn("GitHub Release name conflicts with intent identity", finding.message)
        self.assertNotIn("Cannot find package", finding.message)
        self.assertNotIn("provenance is invalid", finding.message)
        self.assertEqual(self.git.mutations + self.github.mutations, [])

    def test_remote_audit_still_reports_genuine_snapshot_lock_mismatch(self) -> None:
        metadata = (
            self.root / "apps/architecture-portal/versioned_metadata"
            / f"version-{CURRENT_PRODUCT_BUILD}.json"
        )
        document = json.loads(metadata.read_text(encoding="utf-8"))
        document["assembly_lock_sha256"] = "0" * 64
        metadata.write_text(json.dumps(document), encoding="utf-8")
        self.install_glob_importing_release_docs()
        self.git.real_target_validation = True
        report = audit(self.context(entries=[]), remote=True, tag=CURRENT_PRODUCT_TAG)
        finding = next(item for item in report.findings if item.subject == CURRENT_PRODUCT_TAG)
        self.assertEqual(finding.code, "unverifiable")
        self.assertEqual(finding.sources, ("exact-target",))
        self.assertIn("exact release target identity or support metadata is invalid", finding.message)
        self.assertIn("Product Portal snapshot does not match the exact Assembly lock", finding.message)
        self.assertNotIn("Cannot find package", finding.message)
        self.assertEqual(self.git.mutations + self.github.mutations, [])

    def test_remote_audit_still_reports_portal_provenance_command_failure(self) -> None:
        path = self.root / "apps/architecture-portal/scripts/check-release-docs.mjs"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "console.error("
            "'source projection is neither direct-parent nor squash-equivalent'"
            ");\nprocess.exit(1);\n",
            encoding="utf-8",
        )
        self.git.real_target_validation = True
        report = audit(self.context(entries=[]), remote=True, tag=CURRENT_PRODUCT_TAG)
        finding = next(item for item in report.findings if item.subject == CURRENT_PRODUCT_TAG)
        self.assertEqual(finding.code, "unverifiable")
        self.assertEqual(finding.sources, ("exact-target",))
        self.assertIn("Product Portal snapshot provenance is invalid", finding.message)
        self.assertIn("source projection is neither direct-parent nor squash-equivalent", finding.message)
        self.assertEqual(self.git.mutations + self.github.mutations, [])

    def test_remote_audit_reports_backfilled_module_release_name_as_conflict(self) -> None:
        item = self.entry()
        tag = str(item["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag, name="application-facade 1.0.1")
        report = audit(self.context([item]), remote=True, tag=tag)
        finding = next(item for item in report.findings if item.subject == tag)
        self.assertEqual(finding.code, "conflict")
        self.assertEqual(finding.sources, ("github-release",))
        self.assertIn("GitHub Release name conflicts with intent identity", finding.message)
        self.assertEqual(self.git.mutations + self.github.mutations, [])

    def test_published_remote_state_is_ok_and_read_only(self) -> None:
        tag = self.entry()["tag"]
        assert isinstance(tag, str)
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        report = audit(self.context(), remote=True)
        self.assertEqual({item.code for item in report.findings}, {"ok"})
        self.assertEqual(self.git.mutations + self.github.mutations, [])

    def test_nonpublished_intent_rejects_an_already_published_release(self) -> None:
        item = self.entry(disposition="releasable")
        tag = str(item["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag, draft=False)
        report = audit(self.context([item]), remote=True, tag=tag)
        finding = next(result for result in report.findings if result.subject == tag)
        self.assertEqual(finding.code, "unauthorized")
        self.assertIn("published", finding.message)

    def test_remote_audit_fails_closed_when_release_environment_is_absent_or_unsafe(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        cases = (
            (None, "external-error"),
            (GitHubEnvironment(
                "release", 1, True, False, True,
                (DeploymentBranchPolicy(1, "main", "branch"),),
            ), "conflict"),
            (GitHubEnvironment(
                "release", 0, None, True, False,
                (DeploymentBranchPolicy(1, "feature/*", "branch"),),
            ), "conflict"),
        )
        for environment, expected in cases:
            with self.subTest(environment=environment):
                self.github.environment = environment
                report = audit(self.context(), remote=True, tag=tag)
                finding = next(
                    item for item in report.findings if item.subject == "environment:release"
                )
                self.assertEqual(finding.code, expected)

    def test_remote_audit_accepts_solo_maintainer_release_environment(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        for prevent_self_review in (None, False):
            with self.subTest(prevent_self_review=prevent_self_review):
                self.github.environment = GitHubEnvironment(
                    "release", 0, prevent_self_review, False, True,
                    (DeploymentBranchPolicy(1, "main", "branch"),),
                )

                report = audit(self.context(), remote=True, tag=tag)

                self.assertNotIn(
                    "environment:release", {item.subject for item in report.findings},
                )

    def test_published_stable_release_requires_authoritative_latest_projection(self) -> None:
        item = self.entry(
            tag="lmdj-v1.0.21.0", disposition="published", kind="product",
            identity="1.0.21.0", profile="web-runtime-host",
        )
        item.update({"channel": "stable", "snapshot": "1.0.21.0", "make_latest": True})
        tag = str(item["tag"])
        self.git.tags[tag] = self.tag_state()
        release = self.release(
            tag, name="LMDJ 1.0.21.0", kind="product", identity="1.0.21.0",
            profile="web-runtime-host", channel="stable",
        )
        self.github.releases[tag] = GitHubRelease(**{**release.__dict__, "make_latest": None})
        report = audit(self.context([item]), remote=True, tag=tag)
        finding = next(result for result in report.findings if result.subject == tag)
        self.assertEqual(finding.code, "conflict")
        self.assertIn("latest Release projection", finding.message)

    def test_current_policy_release_requires_one_canonical_body_marker(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        canonical = self.release(tag).body
        incomplete = "<!-- lmdj.release-plan-marker.v1 " + json.dumps({
            "tag": tag, "target_revision": TARGET,
            "intent": {
                "kind": "module", "identity": "application-facade@1.0.1",
                "profile": "source-only",
            },
        }, sort_keys=True, separators=(",", ":")) + " -->"
        for body in (
            "", "arbitrary legacy body", "<!-- lmdj.release-plan-marker.v1 {} -->",
            incomplete, canonical + canonical,
        ):
            with self.subTest(body=body):
                self.github.releases[tag] = self.release(tag, body=body)
                report = audit(self.context(), remote=True, tag=tag)
                self.assertEqual(report.findings[0].code, "conflict")

    def test_pre_cutoff_exact_exception_remains_visible_success(self) -> None:
        tag = "v0.2.0"
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag, identifier=99, name="Legacy")
        exception = {
            "tag": tag,
            "target_revision": TARGET,
            "release_id": 99,
            "observed_before": "2026-08-12T23:59:59Z",
            "code": "pre-governance-tag-scheme",
            "reason": "fixture predates the closed tag policy",
            "evidence_paths": ["evidence.md"],
        }
        report = audit(self.context([], [exception]), remote=True, tag=tag)
        self.assertEqual([item.code for item in report.findings], ["ok-with-historical-exception"])
        self.assertIn("fixture predates", report.findings[0].message)
        self.assert_audit_passes(report)

    def test_linked_exception_marker_waiver_requires_exact_release_id(self) -> None:
        tag = str(self.entry()["tag"])
        exception = {
            "tag": tag,
            "target_revision": TARGET,
            "release_id": 17,
            "observed_before": "2026-08-12T23:59:59Z",
            "code": "pre-pipeline-ci-evidence",
            "reason": "fixture current-policy publication predates canonical markers",
            "evidence_paths": ["evidence.md"],
        }
        self.git.tags[tag] = self.tag_state()
        for identifier, expected in ((17, "ok-with-historical-exception"), (18, "conflict")):
            with self.subTest(identifier=identifier):
                self.github.releases[tag] = self.release(tag, identifier=identifier, body="")
                report = audit(self.context([self.entry()], [exception]), remote=True, tag=tag)
                self.assertEqual(report.findings[0].code, expected)

    def test_pre_pipeline_ci_exception_waives_only_the_recorded_cancelled_run(self) -> None:
        tag = str(self.entry()["tag"])
        exception = {
            "tag": tag,
            "target_revision": TARGET,
            "release_id": 17,
            "observed_before": "2026-08-12T23:59:59Z",
            "code": "pre-pipeline-ci-evidence",
            "reason": "fixture predates the canonical release pipeline",
            "evidence_paths": ["evidence.md"],
        }
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        self.github.runs = [
            RunProjection(123, "push", TARGET, "main", "Core CI", "completed", "cancelled"),
        ]
        accepted = audit(self.context([self.entry()], [exception]), remote=True, tag=tag)
        accepted_finding = next(item for item in accepted.findings if item.subject == tag)
        self.assertEqual(accepted_finding.code, "ok-with-historical-exception")
        for runs in (
            [],
            [RunProjection(123, "push", "c" * 40, "main", "Core CI", "completed", "cancelled")],
            [RunProjection(123, "workflow_dispatch", TARGET, "main", "Core CI", "completed", "cancelled")],
            [RunProjection(123, "push", TARGET, "feature", "Core CI", "completed", "cancelled")],
            [RunProjection(123, "push", TARGET, "main", "Other CI", "completed", "cancelled")],
            [RunProjection(123, "push", TARGET, "main", "Core CI", "in_progress", None)],
            [RunProjection(123, "push", TARGET, "main", "Core CI", "completed", "failure")],
        ):
            with self.subTest(runs=runs):
                self.github.runs = runs
                report = audit(self.context([self.entry()], [exception]), remote=True, tag=tag)
                finding = next(item for item in report.findings if item.subject == tag)
                self.assertIn(finding.code, {"missing", "conflict"})

    def releasable_intent(self) -> tuple[AuditContext, object]:
        item = self.entry(disposition="releasable")
        context = self.context([item])
        return context, context.ledger.intent_for_tag(str(item["tag"]))

    def test_release_accepts_only_full_exact_main_ci(self) -> None:
        self.github.scope = CiScopeProjection(
            schema="lmdj.ci-scope.v2", base_sha="a" * 40, head_sha=TARGET,
            mode="full", trusted_head=True,
            selected_lanes=tuple(sorted(LANES)),
            required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
        )
        self.github.jobs = [
            RunJobProjection(1, 123, "Change Scope", "completed", "success", "Core CI", TARGET),
            RunJobProjection(2, 123, "PR Gate", "completed", "success", "Core CI", TARGET),
        ]
        context, intent = self.releasable_intent()
        self.assertIsNone(audit_module._ci_problem(context, intent))

    def test_release_rejects_focused_or_wrong_sha_or_missing_gate(self) -> None:
        context, intent = self.releasable_intent()
        for mode, sha, gate in (
            ("focused", TARGET, "success"),
            ("full", "c" * 40, "success"),
            ("full", TARGET, "skipped"),
        ):
            with self.subTest(mode=mode, sha=sha, gate=gate):
                self.github.scope = CiScopeProjection(
                    schema="lmdj.ci-scope.v2",
                    base_sha="a" * 40,
                    head_sha=sha,
                    mode=mode,
                    trusted_head=True,
                    selected_lanes=tuple(sorted(LANES)),
                    required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
                )
                self.github.jobs = [
                    RunJobProjection(1, 123, "Change Scope", "completed", "success", "Core CI", sha),
                    RunJobProjection(2, 123, "PR Gate", "completed", gate, "Core CI", sha),
                ]
                problem = audit_module._ci_problem(context, intent)
                self.assertIsNotNone(problem)

    def test_full_dispatch_evidence_is_accepted_for_a_release_target(self) -> None:
        self.github.runs = [
            RunProjection(123, "workflow_dispatch", TARGET, "main", "Core CI", "completed", "success"),
        ]
        context, intent = self.releasable_intent()
        self.assertIsNone(audit_module._ci_problem(context, intent))

    def test_absent_scope_evidence_is_unverifiable_and_outage_is_external(self) -> None:
        context, intent = self.releasable_intent()
        for error, expected in (
            (CiScopeUnavailableError("retained scope evidence is absent"), "unverifiable"),
            (CiScopeConflictError("scope artifact identity conflicts"), "conflict"),
            (TimeoutError("fixture outage"), "external-error"),
        ):
            with self.subTest(error=type(error).__name__):
                self.github.scope_error = error
                problem = audit_module._ci_problem(context, intent)
                self.assertIsNotNone(problem)
                self.assertEqual(problem.code, expected)

    def test_published_audit_does_not_depend_on_expired_ephemeral_evidence(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        self.github.scope_error = CiScopeUnavailableError("retained scope evidence expired")
        self.github.jobs = []
        report = audit(self.context(), remote=True, tag=tag)
        self.assertEqual({item.code for item in report.findings}, {"ok"})

    def test_linked_null_id_exception_never_waives_current_release_marker(self) -> None:
        tag = str(self.entry()["tag"])
        exception = {
            "tag": tag,
            "target_revision": TARGET,
            "observed_before": "2026-08-12T23:59:59Z",
            "code": "pre-pipeline-ci-evidence",
            "reason": "fixture mirrors a current-policy exception without numeric Release identity",
            "evidence_paths": ["evidence.md"],
        }
        self.git.tags[tag] = self.tag_state()
        for identifier, body in ((17, ""), (18, "arbitrary recreated Release")):
            with self.subTest(identifier=identifier, body=body):
                self.github.releases[tag] = self.release(
                    tag, identifier=identifier, body=body,
                )
                report = audit(self.context([self.entry()], [exception]), remote=True, tag=tag)
                self.assertEqual(report.findings[0].code, "conflict")

    def test_missing_published_tag_and_release_is_missing(self) -> None:
        report = audit(self.context(), remote=True, tag=str(self.entry()["tag"]))
        self.assertEqual({item.code for item in report.findings}, {"missing"})

    def test_wrong_tag_target_is_conflict(self) -> None:
        tag = self.entry()["tag"]
        assert isinstance(tag, str)
        self.git.tags[tag] = self.tag_state(target="c" * 40)
        self.github.releases[tag] = self.release(tag)
        report = audit(self.context(), remote=True, tag=tag)
        self.assertEqual(report.findings[0].code, "conflict")

    def test_wrong_tag_signature_role_is_conflict(self) -> None:
        tag = self.entry()["tag"]
        assert isinstance(tag, str)
        self.git.tags[tag] = self.tag_state(signer=CHECKSUM)
        self.github.releases[tag] = self.release(tag)
        report = audit(self.context(), remote=True, tag=tag)
        self.assertEqual(report.findings[0].code, "conflict")

    def test_unknown_formal_remote_state_is_unauthorized(self) -> None:
        unknown = "lmdj-v9.9.9.9"
        self.git.tags[unknown] = self.tag_state()
        report = audit(self.context(), remote=True)
        self.assertIn("unauthorized", {item.code for item in report.findings})

    def test_post_cutoff_unknown_release_is_unauthorized(self) -> None:
        unknown = "module/foundation/v9.9.9"
        self.github.releases[unknown] = self.release(unknown, identifier=88, name="unknown")
        report = audit(self.context(), remote=True)
        finding = next(item for item in report.findings if item.subject == unknown)
        self.assertEqual(finding.code, "unauthorized")

    def test_unrelated_nonformal_tag_is_outside_the_audit_domain(self) -> None:
        self.git.tags["stage/1.0.0"] = self.tag_state(signer=CHECKSUM)
        report = audit(self.context(), remote=True)
        self.assertNotIn("stage/1.0.0", {item.subject for item in report.findings})

    def test_tag_only_superseded_entry_is_accepted(self) -> None:
        item = self.entry(disposition="superseded-unreleased")
        tag = item["tag"]
        assert isinstance(tag, str)
        self.git.tags[tag] = self.tag_state()
        report = audit(self.context([item]), remote=True, tag=tag)
        self.assertEqual([finding.code for finding in report.findings], ["ok"])

    def test_abandoned_remote_tag_is_unauthorized(self) -> None:
        item = self.entry(
            tag="lmdj-v1.0.18.0", disposition="abandoned", kind="product",
            identity="1.0.18.0", profile="web-runtime-host",
        )
        self.git.tags[item["tag"]] = self.tag_state()
        report = audit(self.context([item]), remote=True, tag="lmdj-v1.0.18.0")
        self.assertEqual(report.findings[0].code, "unauthorized")

    def test_abandoned_release_is_unauthorized(self) -> None:
        item = self.entry(
            tag="lmdj-v1.0.18.0", disposition="abandoned", kind="product",
            identity="1.0.18.0", profile="web-runtime-host",
        )
        tag = str(item["tag"])
        self.github.releases[tag] = self.release(tag, name="LMDJ 1.0.18.0")
        report = audit(self.context([item]), remote=True, tag=tag)
        self.assertEqual(report.findings[0].code, "unauthorized")

    def test_missing_evidence_is_unverifiable(self) -> None:
        context = self.context()
        (self.root / "evidence.md").unlink()
        report = audit(context, remote=False)
        self.assertEqual(report.findings[0].code, "unverifiable")

    def test_missing_active_product_identity_fails_closed_locally(self) -> None:
        (self.root / "products/lmdj/version.json").unlink()
        report = audit(self.context(), remote=False)
        self.assertIn("unverifiable", {item.code for item in report.findings})

    def test_remote_static_audit_uses_fetched_main_and_fails_on_its_drift(self) -> None:
        canonical = self.root / "canonical"
        canonical.mkdir()
        (canonical / "evidence.md").write_text("fixture\n", encoding="utf-8")
        self.install_static_authority(canonical)
        (canonical / "products/lmdj/version.json").unlink()
        context = self.context()
        self.git.authority_root = canonical
        def build_authority(root, policy, ledger):
            return replace(
                context, repo_root=root, policy=policy, ledger=ledger,
                tag_signer_fingerprint=policy.product_fingerprint,
                checksum_signer_fingerprint=policy.checksum_fingerprint,
                authority_reader=None, authority_context_builder=None,
            )
        context = replace(
            context,
            authority_reader=lambda root: (context.policy, context.ledger),
            authority_context_builder=build_authority,
        )
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        report = audit(context, remote=True, tag=tag)
        self.assertIn("unverifiable", {item.code for item in report.findings})

    def test_remote_authority_rebuild_ignores_stale_caller_policy_and_key_root(self) -> None:
        canonical = self.root / "canonical"
        canonical.mkdir()
        (canonical / "evidence.md").write_text("fixture\n", encoding="utf-8")
        self.install_static_authority(canonical)
        (self.root / ".github/release-signing-keys/lmdj-product.asc").write_text(
            "stale caller key\n", encoding="utf-8",
        )
        context = self.context()
        stale_policy = replace(
            context.policy,
            product_fingerprint=CHECKSUM,
            checksum_fingerprint=PRODUCT,
        )
        rebuilt_roots: list[Path] = []
        self.git.authority_root = canonical
        def build_authority(root, policy, ledger):
            rebuilt_roots.append(root)
            self.assertEqual(
                (root / ".github/release-signing-keys/lmdj-product.asc").read_bytes(),
                (ROOT / ".github/release-signing-keys/lmdj-product.asc").read_bytes(),
            )
            return replace(
                context, repo_root=root, policy=policy, ledger=ledger,
                tag_signer_fingerprint=policy.product_fingerprint,
                checksum_signer_fingerprint=policy.checksum_fingerprint,
                authority_reader=None, authority_context_builder=None,
            )
        context = replace(
            context, policy=stale_policy,
            authority_reader=lambda root: (self.policy, context.ledger),
            authority_context_builder=build_authority,
        )
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        report = audit(context, remote=True, tag=tag)
        self.assertEqual({item.code for item in report.findings}, {"ok"})
        self.assertEqual(rebuilt_roots, [canonical])

    def test_static_product_assembly_and_lock_fail_closed_in_both_modes(self) -> None:
        cases = (
            ("products/lmdj/version.json", None),
            ("products/lmdj/assembly.json", "{}\n"),
            ("products/lmdj/assembly.lock.json", "{}\n"),
        )
        for remote in (False, True):
            for relative, replacement in cases:
                with self.subTest(remote=remote, relative=relative):
                    authority = self.root / f"case-{int(remote)}-{Path(relative).name}"
                    authority.mkdir()
                    (authority / "evidence.md").write_text("fixture\n", encoding="utf-8")
                    self.install_static_authority(authority)
                    target = authority / relative
                    if replacement is None:
                        target.unlink()
                    else:
                        target.write_text(replacement, encoding="utf-8")
                    context = self.context()
                    if remote:
                        self.git.authority_root = authority
                        def build_authority(root, policy, ledger):
                            return replace(
                                context, repo_root=root, policy=policy, ledger=ledger,
                                tag_signer_fingerprint=policy.product_fingerprint,
                                checksum_signer_fingerprint=policy.checksum_fingerprint,
                                authority_reader=None, authority_context_builder=None,
                            )
                        context = replace(
                            context,
                            authority_reader=lambda root: (self.policy, context.ledger),
                            authority_context_builder=build_authority,
                        )
                        tag = str(self.entry()["tag"])
                        self.git.tags[tag] = self.tag_state()
                        self.github.releases[tag] = self.release(tag)
                        report = audit(context, remote=True, tag=tag)
                    else:
                        report = audit(replace(context, repo_root=authority), remote=False)
                    self.assertIn("unverifiable", {item.code for item in report.findings})

    def test_provider_source_package_drift_fails_static_audit_in_both_modes(self) -> None:
        for remote in (False, True):
            for relative in (
                "providers/local-proof-success/include/lmdj/providers/local_proof_success/factory.hpp",
                "providers/local-proof-success/src/provider.cpp",
            ):
                with self.subTest(remote=remote, relative=relative):
                    authority = self.root / f"provider-{int(remote)}-{Path(relative).name}"
                    authority.mkdir()
                    (authority / "evidence.md").write_text("fixture\n", encoding="utf-8")
                    self.install_static_authority(authority)
                    with (authority / relative).open("a", encoding="utf-8") as source:
                        source.write("\n// drift\n")
                    context = self.context()
                    if remote:
                        self.git.authority_root = authority
                        def build_authority(root, policy, ledger):
                            return replace(
                                context, repo_root=root, policy=policy, ledger=ledger,
                                tag_signer_fingerprint=policy.product_fingerprint,
                                checksum_signer_fingerprint=policy.checksum_fingerprint,
                                authority_reader=None, authority_context_builder=None,
                            )
                        context = replace(
                            context,
                            authority_reader=lambda root: (self.policy, context.ledger),
                            authority_context_builder=build_authority,
                        )
                        tag = str(self.entry()["tag"])
                        self.git.tags[tag] = self.tag_state()
                        self.github.releases[tag] = self.release(tag)
                        report = audit(context, remote=True, tag=tag)
                    else:
                        report = audit(replace(context, repo_root=authority), remote=False)
                    self.assertIn("unverifiable", {item.code for item in report.findings})

    def test_trust_anchor_failure_is_a_static_finding_and_cli_writes_json(self) -> None:
        def broken_trust_anchor(*args):
            raise OpenPgpError("fixture key mismatch")

        context = replace(self.context(), trust_anchor_verifier=broken_trust_anchor)
        destination = self.root / "audit.json"
        with patch.object(cli, "build_audit_context", return_value=context):
            exit_code = cli.main([
                "--repo-root", str(self.root), "audit", "--local",
                "--json", str(destination),
            ])
        self.assertEqual(exit_code, 1)
        document = json.loads(destination.read_text(encoding="utf-8"))
        self.assertIn("unverifiable", {item["code"] for item in document["findings"]})

        context = replace(
            context,
            authority_reader=lambda root: (self.policy, context.ledger),
            authority_context_builder=lambda root, policy, ledger: replace(
                context, repo_root=root, policy=policy, ledger=ledger,
                authority_reader=None, authority_context_builder=None,
            ),
        )
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        report = audit(context, remote=True, tag=tag)
        self.assertIn("unverifiable", {item.code for item in report.findings})
        self.assertNotIn("external-error", {item.code for item in report.findings})

        with patch.object(
            audit_module, "_remote_inventories",
            side_effect=OpenPgpError("fixture canonical key failure"),
        ):
            report = audit(context, remote=True, tag=tag)
        self.assertEqual({item.code for item in report.findings}, {"unverifiable"})
        self.assertFalse(report.incomplete_sources)

    def test_static_finding_names_its_projection_and_sanitizes_the_reason(self) -> None:
        def broken_trust_anchor(*args):
            raise OpenPgpError(
                "import failed GITHUB_TOKEN=ghs_fixturesecret home /home/runner/work/lmdj/lmdj",
            )

        report = audit(
            replace(self.context(), trust_anchor_verifier=broken_trust_anchor), remote=False,
        )
        finding = report.findings[0]
        self.assertEqual(finding.code, "unverifiable")
        self.assertEqual(report.exit_code, 1)
        self.assertIn("projection is inconsistent", finding.message)
        self.assertIn("signing trust anchors", finding.message)
        self.assertIn("OpenPgpError", finding.message)
        self.assertEqual(finding.sources, ("canonical-trust",))
        self.assertIn("GITHUB_TOKEN=[redacted]", finding.message)
        self.assertNotIn("ghs_fixturesecret", finding.message)
        self.assertNotIn("/home/runner", finding.message)

    def test_each_static_projection_reports_itself_independently(self) -> None:
        manifest = self.root / "packages/application-facade/module.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["version"] = "9.9.9"
        manifest.write_text(json.dumps(document), encoding="utf-8")
        report = audit(self.context(), remote=False)
        digest_finding = report.findings[0]
        self.assertEqual(digest_finding.code, "unverifiable")
        self.assertIn("Assembly lock component digests", digest_finding.message)
        self.assertIn("application-facade", digest_finding.message)

        shutil.copyfile(ROOT / "packages/application-facade/module.json", manifest)
        self.git.target_validation_error = RuntimeError(
            "Product Portal snapshot provenance is invalid",
        )
        target_finding = audit(self.context(), remote=False).findings[0]
        self.assertEqual(target_finding.code, "unverifiable")
        self.assertIn("exact release target validation", target_finding.message)
        self.assertIn("Product Portal snapshot provenance is invalid", target_finding.message)
        self.assertNotEqual(digest_finding.message, target_finding.message)

    def test_local_active_manifest_drift_is_unverifiable(self) -> None:
        manifest = self.root / "packages/application-facade/module.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["version"] = "9.9.9"
        manifest.write_text(json.dumps(document), encoding="utf-8")
        item = self.entry(
            tag="lmdj-v1.0.20.0", disposition="allocated", kind="product",
            identity="1.0.20.0", profile="web-runtime-host",
        )
        item["snapshot"] = "1.0.20.0"
        report = audit(self.context([item]), remote=False)
        self.assertEqual(report.findings[0].code, "unverifiable")

    def test_product_asset_digest_or_signature_mismatch_is_conflict(self) -> None:
        item = self.entry(
            tag="lmdj-v1.0.21.0", disposition="published", kind="product",
            identity="1.0.21.0", profile="web-runtime-host",
        )
        tag = str(item["tag"])
        self.git.tags[tag] = self.tag_state()
        archive = b"archive"
        checksum = b"0" * 64 + b"  host.zip\n"
        signature = b"signature"
        payloads = (archive, checksum, signature)
        names = ("host.zip", "host.zip.sha256", "host.zip.sha256.asc")
        assets = tuple(
            GitHubAsset(
                40 + index, name, len(payload),
                f"https://api.github.com/repos/endaye/lmdj/releases/assets/{40 + index}",
                f"https://github.com/endaye/lmdj/releases/download/test/{name}",
                17, None, "application/octet-stream", "uploaded",
            )
            for index, (name, payload) in enumerate(zip(names, payloads))
        )
        self.github.payloads = {asset.id: payload for asset, payload in zip(assets, payloads)}
        self.github.releases[tag] = self.release(
            tag, name="LMDJ 1.0.21.0", prerelease=True, assets=assets,
            kind="product", identity="1.0.21.0", profile="web-runtime-host",
            channel="canary",
        )
        context = self.context([item])
        context = replace(
            context,
            profile_verifier=lambda *args: (_ for _ in ()).throw(RuntimeError("bad signature")),
        )
        report = audit(context, remote=True, tag=tag)
        self.assertEqual(report.findings[0].code, "conflict")

    def test_dual_web_host_release_audit_accepts_both_signed_triplets(self) -> None:
        item = self.entry(
            tag="lmdj-v1.0.41.0",
            disposition="published",
            kind="product",
            identity="1.0.41.0",
            profile="web-hosts",
        )
        intent = load_ledger_document(
            {
                "schema": "lmdj.release-intents.v1",
                "entries": [item],
                "historical_exceptions": [],
            },
            self.policy,
        ).entries[0]
        payload_by_name: dict[str, bytes] = {}
        for host in ("creator-web", "web-runtime-host"):
            archive_name = f"lmdj-{host}-2.1.1-product-1.0.41.0.zip"
            archive = host.encode("ascii")
            payload_by_name[archive_name] = archive
            payload_by_name[f"{archive_name}.sha256"] = (
                f"{hashlib.sha256(archive).hexdigest()}  {archive_name}\n".encode("ascii")
            )
            payload_by_name[f"{archive_name}.sha256.asc"] = b"signature"
        assets = tuple(
            GitHubAsset(
                70 + index,
                name,
                len(payload),
                f"https://api.github.com/repos/endaye/lmdj/releases/assets/{70 + index}",
                f"https://github.com/endaye/lmdj/releases/download/test/{name}",
                17,
                None,
                "application/octet-stream",
                "uploaded",
            )
            for index, (name, payload) in enumerate(payload_by_name.items())
        )
        release = self.release(
            intent.tag,
            assets=assets,
            prerelease=True,
            kind="product",
            identity=intent.identity,
            profile=intent.profile,
            channel="canary",
        )
        self.github.releases[intent.tag] = release
        self.github.payloads = {
            asset.id: payload_by_name[asset.name] for asset in assets
        }
        context = self.context([item], ensure_current_product_intent=False)

        problem = audit_module._asset_problem(context, intent, release)

        self.assertIsNone(problem)

    def test_network_or_pagination_failure_is_external_error(self) -> None:
        self.github.error = TimeoutError("fixture secret")
        report = audit(self.context(), remote=True)
        self.assertEqual({item.code for item in report.findings}, {"external-error"})
        self.assertNotIn("fixture secret", json.dumps(report.to_document()))
        self.assertTrue(report.incomplete_sources)

    def test_json_is_atomic_and_refuses_symlink_destination(self) -> None:
        report = audit(self.context(), remote=False)
        destination = self.root / "report.json"
        write_report(report, destination)
        self.assertEqual(json.loads(destination.read_text())["schema"], "lmdj.release-audit.v1")
        destination.unlink()
        target = self.root / "target.json"
        target.write_text("unchanged", encoding="utf-8")
        destination.symlink_to(target)
        with self.assertRaises(OSError):
            write_report(report, destination)
        self.assertEqual(target.read_text(encoding="utf-8"), "unchanged")
        destination.unlink()
        destination.symlink_to(self.root / "missing-target.json")
        with self.assertRaises(OSError):
            write_report(report, destination)
        self.assertTrue(destination.is_symlink())

    def test_cli_requires_one_audit_mode_and_accepts_tag_and_json(self) -> None:
        options = cli.parse_arguments([
            "--repo-root", str(self.root), "audit", "--remote",
            "--tag", "lmdj-v1.0.20.0", "--json", "report.json",
        ])
        self.assertTrue(options.remote)
        self.assertFalse(options.local)
        self.assertEqual(options.tag, "lmdj-v1.0.20.0")
        self.assertEqual(options.json, Path("report.json"))
        with self.assertRaises(SystemExit):
            cli.parse_arguments(["--repo-root", str(self.root), "audit"])
        with self.assertRaises(SystemExit):
            cli.parse_arguments([
                "--repo-root", str(self.root), "audit", "--local", "--remote",
            ])

    def _pre_mutation_intent(self, disposition: str, *, target: str):
        """An intent in the exact state that authorizes the next mutation."""
        item = self.entry(
            tag=CURRENT_PRODUCT_TAG, disposition=disposition, kind="product",
            identity=CURRENT_PRODUCT_BUILD, profile="web-runtime-host",
        )
        item["target_revision"] = target
        context = self.context([item])
        return context, context.ledger.intent_for_tag(str(item["tag"]))

    def _remote_finding(self, context, intent):
        return audit_module._audit_remote_intent(context, intent, None, None, None, None)

    def test_pre_mutation_intent_outside_main_ancestry_is_unauthorized(self) -> None:
        """prepare refuses these targets, so the audit must refuse them too.

        Both states below are pre-mutation: they report no remote publication
        state and are exactly what authorizes the next mutation. Reporting them
        ok on object existence alone is how 1.0.22.0 and 1.0.23.0 stayed green
        while unpreparable.
        """
        for disposition in ("allocated", "releasable"):
            with self.subTest(disposition=disposition):
                context, intent = self._pre_mutation_intent(disposition, target="e" * 40)
                finding = self._remote_finding(context, intent)
                self.assertEqual(finding.code, "unauthorized")
                self.assertEqual(
                    finding.message, "release target is outside protected main ancestry",
                )

    def test_unpreparable_releasable_intent_is_named_before_its_ci_evidence(self) -> None:
        """CI evidence for a target prepare would refuse describes work that
        cannot be released, so ancestry is the finding that must surface."""
        context, intent = self._pre_mutation_intent("releasable", target="e" * 40)

        def unreachable(*args, **kwargs):
            raise AssertionError("CI evidence was consulted for an unpreparable target")

        with patch.object(audit_module, "_ci_problem", side_effect=unreachable):
            finding = self._remote_finding(context, intent)
        self.assertEqual(finding.code, "unauthorized")

    def test_pre_mutation_ancestry_probe_outage_is_external_error(self) -> None:
        """An unavailable probe never reads as a pass."""
        for disposition in ("allocated", "releasable"):
            with self.subTest(disposition=disposition):
                context, intent = self._pre_mutation_intent(disposition, target=TARGET)
                with patch.object(
                    type(self.git), "is_main_ancestor", side_effect=TimeoutError("fixture outage"),
                ):
                    finding = self._remote_finding(context, intent)
                self.assertEqual(finding.code, "external-error")
                self.assertEqual(finding.sources, ("git-remote",))

    def test_pre_mutation_intent_on_main_keeps_its_existing_finding(self) -> None:
        """The change is fail-closed only: on-main states are untouched."""
        context, intent = self._pre_mutation_intent("allocated", target=TARGET)
        finding = self._remote_finding(context, intent)
        self.assertEqual(finding.code, "ok")
        self.assertEqual(finding.message, "allocated intent has no remote publication state")

        context, intent = self._pre_mutation_intent("releasable", target=TARGET)
        self.github.scope = CiScopeProjection(
            schema="lmdj.ci-scope.v2", base_sha="a" * 40, head_sha=TARGET,
            mode="full", trusted_head=True,
            selected_lanes=tuple(sorted(LANES)),
            required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
        )
        self.github.jobs = [
            RunJobProjection(1, 123, "Change Scope", "completed", "success", "Core CI", TARGET),
            RunJobProjection(2, 123, "PR Gate", "completed", "success", "Core CI", TARGET),
        ]
        finding = self._remote_finding(context, intent)
        self.assertEqual(finding.code, "ok")
        self.assertEqual(
            finding.message,
            "releasable intent has full exact-main CI evidence and no remote publication state",
        )

    def test_historical_dispositions_are_not_ancestry_gated(self) -> None:
        """Abandoned and superseded-unreleased intents authorize no mutation,
        and their targets may legitimately sit outside main."""
        for disposition in ("abandoned", "superseded-unreleased"):
            with self.subTest(disposition=disposition):
                context, intent = self._pre_mutation_intent(disposition, target="e" * 40)
                finding = self._remote_finding(context, intent)
                self.assertEqual(finding.code, "ok")

    def test_stable_release_entry_is_directly_executable(self) -> None:
        entry = ROOT / "scripts/release.sh"
        self.assertTrue(os.access(entry, os.X_OK), "scripts/release.sh is not executable")
        completed = subprocess.run(
            [str(entry), "--help"], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("{prepare,push-tag,create-draft", completed.stdout)
        self.assertIn("audit", completed.stdout)


class ReleaseAuditIntegrationTest(ReleaseAuditFixture, unittest.TestCase):
    def test_local_audit_context_has_no_remote_credential_dependency(self) -> None:
        with patch.object(cli, "_authenticated_github_client", return_value=None):
            context = cli.build_audit_context(ROOT)

        self.assertIsNotNone(context.github)

    def test_remote_canonical_product_build_without_intent_audits_registered_entries(self) -> None:
        revision = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        context = self.canonical_remote_context(
            self.zero_intent_repository_context(ROOT, revision),
        )

        report = audit(context, remote=True)
        self.assertEqual({item.code for item in report.findings}, {"ok"})

    def test_repository_local_audit_does_not_assume_current_intent_count(self) -> None:
        run = subprocess.run

        def present_intent_target(command, **kwargs):
            if command[:5] != ["git", "-C", str(ROOT), "cat-file", "-e"]:
                return run(command, **kwargs)
            self.assertEqual(
                command[:5], ["git", "-C", str(ROOT), "cat-file", "-e"],
            )
            self.assertRegex(command[5], r"^[0-9a-f]{40}\^\{commit\}$")
            self.assertEqual(
                kwargs,
                {
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                    "check": False,
                },
            )
            return subprocess.CompletedProcess(command, 0)

        context = replace(
            cli.build_audit_context(ROOT),
            # Canonical key import is covered independently; this integration
            # test owns the current manifest, snapshot, ledger, and intent-count
            # projections that dominate the zero-intent behavior under test.
            trust_anchor_verifier=lambda root, policy: None,
        )
        with (
            patch.object(
                context.git,
                "validate_current_product_snapshot",
                # The corruption matrix below owns the real provenance command;
                # this test keeps the repository's manifest, lock, inventory,
                # and ledger projections real while isolating the intent-count
                # rule.
                return_value=None,
            ),
            patch(
                "tools.release.audit.subprocess.run",
                # Fresh CI clones intentionally lack pre-squash intent targets.
                # Object availability has its own fail-closed unit test; it must
                # not make this intent-count integration test checkout-dependent.
                side_effect=present_intent_target,
            ),
        ):
            report = audit(context, remote=False)
            self.assert_audit_passes(report)

    def test_zero_intent_local_and_remote_audits_reject_corrupt_snapshot_provenance(self) -> None:
        cases = (
            ("metadata revision", "metadata-revision"),
            ("metadata source tree", "metadata-source-tree"),
            ("squash witness", "squash-witness"),
        )
        revision = "760e2167914323dd70ea2e188da2f6136e8edc63"
        with self.repository_worktree(revision) as worktree:
            def restore_exact_worktree() -> None:
                subprocess.run(
                    ["git", "-C", str(worktree), "reset", "--hard", revision],
                    check=True, capture_output=True, text=True,
                )

            def assert_exact_worktree() -> None:
                head = subprocess.run(
                    ["git", "-C", str(worktree), "rev-parse", "HEAD"],
                    check=True, capture_output=True, text=True,
                ).stdout.strip()
                status = subprocess.run(
                    ["git", "-C", str(worktree), "status", "--porcelain"],
                    check=True, capture_output=True, text=True,
                ).stdout
                self.assertEqual(head, revision)
                self.assertEqual(status, "")

            for label, corruption in cases:
                with self.subTest(label=label):
                    restore_exact_worktree()
                    assert_exact_worktree()
                    try:
                        context = self.zero_intent_repository_context(worktree, revision)

                        product_build = current_product_build(worktree)
                        metadata_path = (
                            worktree / "apps/architecture-portal/versioned_metadata"
                            / f"version-{product_build}.json"
                        )
                        if corruption == "squash-witness":
                            path = (
                                worktree / "apps/architecture-portal/versioned_provenance"
                                / f"version-{product_build}-squash-witness.json"
                            )
                            document = json.loads(path.read_text(encoding="utf-8"))
                            document["source_tree"] = "d" * 40
                        else:
                            path = metadata_path
                            document = json.loads(path.read_text(encoding="utf-8"))
                            if corruption == "metadata-revision":
                                document["revision"] = "d" * 40
                            else:
                                document["source_commit"]["tree"] = "d" * 40
                        path.write_text(
                            json.dumps(document, indent=2) + "\n", encoding="utf-8",
                        )
                        if corruption == "squash-witness":
                            subprocess.run(
                                ["git", "-C", str(worktree), "add", str(path)],
                                check=True, capture_output=True, text=True,
                            )
                            subprocess.run(
                                [
                                    "git", "-C", str(worktree),
                                    "-c", "user.name=LMDJ Release Audit Test",
                                    "-c", "user.email=release-audit-test@invalid",
                                    "commit", "-m", "test: corrupt squash witness",
                                ],
                                check=True, capture_output=True, text=True,
                            )

                        validation_error: list[Exception] = []
                        validation_calls: list[tuple[Path, str]] = []

                        def validate_snapshot_once(selected_root: Path, identity: str) -> None:
                            validation_calls.append((selected_root.resolve(), identity))
                            if not validation_error:
                                try:
                                    target_validation_module.validate_current_product_snapshot(
                                        selected_root, identity,
                                    )
                                except Exception as error:
                                    validation_error.append(error)
                            if validation_error:
                                raise validation_error[0]

                        self.git.current_snapshot_validator = validate_snapshot_once
                        local = audit(context, remote=False)
                        remote = audit(self.canonical_remote_context(context), remote=True)
                        self.assertEqual(
                            validation_calls,
                            [(worktree.resolve(), product_build)] * 2,
                        )
                        for report in (local, remote):
                            finding = next(
                                item for item in report.findings
                                if item.code == "unverifiable"
                            )
                            self.assertIn(
                                "immutable Portal snapshot projection", finding.message,
                            )
                            self.assertEqual(finding.sources, ("architecture-portal",))
                    finally:
                        restore_exact_worktree()
                        assert_exact_worktree()


if __name__ == "__main__":
    unittest.main()
