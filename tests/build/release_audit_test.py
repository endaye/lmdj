#!/usr/bin/env python3
"""Contract tests for read-only local and remote release audits."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
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

from tools.release.audit import AuditContext, audit, write_report  # noqa: E402
import tools.release.audit as audit_module  # noqa: E402
from tools.release.github_api import (  # noqa: E402
    BranchProjection,
    GitHubAsset,
    GitHubRelease,
    RunProjection,
)
from tools.release.model import load_ledger_document, load_policy  # noqa: E402
from tools.release.openpgp import OpenPgpError  # noqa: E402
from tools.release.prepare import LocalTag, ProductProof  # noqa: E402
from tools.release import cli  # noqa: E402


TARGET = "a" * 40
TAG_OBJECT = "b" * 40
PRODUCT = "2B5EE362F058800036AD4FB5116ECE156F954D29"
CHECKSUM = "CB928A6E89DE498851688EF1AAC3E7019FC1478B"


class ReadOnlyGit:
    def __init__(self) -> None:
        self.tags: dict[str, LocalTag] = {}
        self.local_tags: dict[str, LocalTag] = {}
        self.fetches = 0
        self.remote_reads = 0
        self.local_reads = 0
        self.mutations: list[str] = []
        self.authority_root: Path | None = None

    def fetch_authority(self, repository: str, branch: str) -> None:
        self.fetches += 1

    def main_revision(self) -> str:
        return TARGET

    def is_main_ancestor(self, target: str) -> bool:
        return target == TARGET

    def is_revision_ancestor(self, ancestor: str, descendant: str) -> bool:
        return descendant == TARGET

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
        if self.authority_root is None:
            raise RuntimeError("fixture canonical authority is unavailable")
        yield self.authority_root

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
        self.releases: dict[str, GitHubRelease] = {}
        self.payloads: dict[int, bytes] = {}
        self.error: Exception | None = None
        self.reads = 0
        self.mutations: list[str] = []

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

    def list_releases(self, repository: str) -> list[GitHubRelease]:
        self._read()
        return list(self.releases.values())

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


class ReleaseAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-release-audit-")
        self.root = Path(self.temporary.name)
        (self.root / "evidence.md").write_text("fixture\n", encoding="utf-8")
        self.install_static_authority(self.root)
        self.policy = load_policy(ROOT / "tools/release/policy.json")
        self.git = ReadOnlyGit()
        self.github = ReadOnlyGitHub()
        self.git.authority_root = self.root

    def tearDown(self) -> None:
        self.temporary.cleanup()

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
            "tag": "lmdj-v1.0.20.0", "kind": "product", "identity": "1.0.20.0",
            "target_revision": TARGET, "channel": "canary", "disposition": "allocated",
            "profile": "web-runtime-host", "snapshot": "1.0.20.0",
            "evidence_paths": ["evidence.md"],
        }

    def install_static_authority(self, root: Path) -> None:
        paths = [
            ROOT / "products/lmdj/version.json",
            ROOT / "products/lmdj/assembly.json",
            ROOT / "products/lmdj/assembly.lock.json",
            ROOT / "apps/architecture-portal/versions.json",
            ROOT / "apps/architecture-portal/versioned_metadata/version-1.0.20.0.json",
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

    def context(
        self,
        entries: list[dict[str, object]] | None = None,
        exceptions: list[dict[str, object]] | None = None,
    ) -> AuditContext:
        selected = list(entries if entries is not None else [self.entry()])
        if not any(item.get("identity") == "1.0.20.0" for item in selected):
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

    def test_local_audit_has_no_remote_dependency_or_mutation(self) -> None:
        report = audit(self.context(), remote=False)
        self.assertEqual({item.code for item in report.findings}, {"ok"})
        self.assertEqual(self.git.fetches, 0)
        self.assertEqual(self.git.remote_reads, 0)
        self.assertEqual(self.git.local_reads, 2)
        self.assertEqual(self.github.reads, 0)
        self.assertEqual(self.git.mutations + self.github.mutations, [])

    def test_local_same_name_tag_conflict_is_visible_but_diagnostic_only(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.local_tags[tag] = self.tag_state(target="c" * 40, signer=CHECKSUM)
        report = audit(self.context(), remote=False, tag=tag)
        diagnostic = next(item for item in report.findings if item.subject == f"local:{tag}")
        self.assertEqual(diagnostic.code, "ok")
        self.assertIn("not authoritative", diagnostic.message)
        self.assertEqual(report.exit_code, 0)

    def test_published_remote_state_is_ok_and_read_only(self) -> None:
        tag = self.entry()["tag"]
        assert isinstance(tag, str)
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        report = audit(self.context(), remote=True)
        self.assertEqual({item.code for item in report.findings}, {"ok"})
        self.assertEqual(self.git.mutations + self.github.mutations, [])

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
        self.assertEqual(report.exit_code, 0)

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


if __name__ == "__main__":
    unittest.main()
