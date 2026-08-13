#!/usr/bin/env python3
"""Contract tests for read-only local and remote release audits."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.audit import AuditContext, audit, write_report  # noqa: E402
from tools.release.github_api import (  # noqa: E402
    BranchProjection,
    GitHubAsset,
    GitHubRelease,
    RunProjection,
)
from tools.release.model import load_ledger_document, load_policy  # noqa: E402
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
        self.policy = load_policy(ROOT / "tools/release/policy.json")
        self.git = ReadOnlyGit()
        self.github = ReadOnlyGitHub()

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

    def context(
        self,
        entries: list[dict[str, object]] | None = None,
        exceptions: list[dict[str, object]] | None = None,
    ) -> AuditContext:
        ledger = load_ledger_document({
            "schema": "lmdj.release-intents.v1",
            "entries": entries if entries is not None else [self.entry()],
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
    ) -> GitHubRelease:
        return GitHubRelease(
            identifier, tag, name, "fixture", draft, prerelease, False,
            f"https://github.com/endaye/lmdj/releases/tag/{tag}",
            f"https://uploads.github.com/repos/endaye/lmdj/releases/{identifier}/assets{{?name,label}}",
            assets, target,
        )

    def test_local_audit_has_no_remote_dependency_or_mutation(self) -> None:
        report = audit(self.context(), remote=False)
        self.assertEqual({item.code for item in report.findings}, {"ok"})
        self.assertEqual(self.git.fetches, 0)
        self.assertEqual(self.git.remote_reads, 0)
        self.assertEqual(self.git.local_reads, 1)
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
        report = audit(self.context([], [exception]), remote=True)
        self.assertEqual([item.code for item in report.findings], ["ok-with-historical-exception"])
        self.assertIn("fixture predates", report.findings[0].message)
        self.assertEqual(report.exit_code, 0)

    def test_missing_published_tag_and_release_is_missing(self) -> None:
        report = audit(self.context(), remote=True)
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

    def test_local_active_manifest_drift_is_unverifiable(self) -> None:
        for relative in (
            "products/lmdj",
            "packages",
            "apps/core-cli",
            "apps/core-mcp",
            "apps/creator-web",
            "apps/native-test-host",
            "apps/web-runtime-host",
            "apps/architecture-portal/versioned_metadata",
            "apps/architecture-portal/versions.json",
            "providers",
            "contracts",
        ):
            source = ROOT / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copyfile(source, destination)
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
