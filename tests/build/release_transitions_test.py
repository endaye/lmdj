#!/usr/bin/env python3
"""Contract tests for exact tag and GitHub Draft transitions."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.commands import CommandError, CommandResult  # noqa: E402
from tools.release.git_repository import (  # noqa: E402
    GitRepository,
    GitRepositoryError,
    _signer_from_status,
)
from tools.release.github_api import (  # noqa: E402
    BranchProjection,
    CiScopeProjection,
    DeploymentBranchPolicy,
    GitHubApiError,
    GitHubAsset,
    GitHubClient,
    GitHubEnvironment,
    GitHubRelease,
    HttpResponse,
    RunJobProjection,
    RunProjection,
)
from tools.release.model import canonical_json, load_ledger_document, load_policy  # noqa: E402
from tools.release.prepare import (  # noqa: E402
    LocalTag,
    PrepareContext,
    ProductProof,
    _plan_document,
    _release_plan,
    load_authority_documents,
)
from tools.release.transitions import (  # noqa: E402
    TransitionError,
    create_draft,
    marker_for_plan,
    publish_draft,
    push_tag,
    verify_draft,
)
from tools.release import cli  # noqa: E402


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, arguments, *, cwd=None, environment=None) -> CommandResult:
        vector = [str(item) for item in arguments]
        self.commands.append(vector)
        return CommandResult(tuple(vector), 0, "", "")


class FakeGit:
    def __init__(self, target: str, signer: str) -> None:
        self.target = target
        self.signer = signer
        self.local = LocalTag("b" * 40, target, signer)
        self.remote: LocalTag | None = None
        self.fetches = 0
        self.pushes = 0
        self.push_raises_after_write = False
        self.push_raises_without_write = False
        self.push_failure_detail: str | None = None
        self.main_contains_target = True
        self.target_validation_error: Exception | None = None

    def fetch_authority(self, repository: str, branch: str) -> None:
        self.fetches += 1

    def main_revision(self) -> str:
        return self.target

    def is_main_ancestor(self, target: str) -> bool:
        return self.main_contains_target and target == self.target

    def is_revision_ancestor(self, ancestor: str, descendant: str) -> bool:
        return descendant == self.target

    def validate_release_target(self, worktree: Path, intent) -> None:
        if self.target_validation_error is not None:
            raise self.target_validation_error

    def remote_tag_state(self, tag: str) -> LocalTag | None:
        return self.remote

    def local_tag_state(self, tag: str) -> LocalTag | None:
        return self.local

    def push_tag(self, tag: str) -> None:
        self.pushes += 1
        if self.push_raises_without_write:
            raise GitRepositoryError(
                "Git release authority command failed",
                detail=self.push_failure_detail or "",
            )
        self.remote = self.local
        if self.push_raises_after_write:
            raise RuntimeError("network failure after write")

    @contextmanager
    def detached_worktree(self, target: str):
        with tempfile.TemporaryDirectory(prefix="release-transition-tree-") as directory:
            yield Path(directory)


_DRAFT_HTML_URL = "https://github.com/endaye/lmdj/releases/tag/untagged-0123456789ab"


def _published_html_url(tag: str) -> str:
    return f"https://github.com/endaye/lmdj/releases/tag/{tag}"


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
    def __init__(self, target: str) -> None:
        self.target = target
        self.branch = BranchProjection("main", True, target)
        self.runs = [RunProjection(123, "push", target, "main", "Core CI", "completed", "success")]
        self.jobs = [
            RunJobProjection(1, 123, "Change Scope", "completed", "success", "Core CI", target),
            RunJobProjection(2, 123, "PR Gate", "completed", "success", "Core CI", target),
        ]
        self.scope = CiScopeProjection(
            schema="lmdj.ci-scope.v2", base_sha="b" * 40, head_sha=target,
            mode="full", trusted_head=True,
            selected_lanes=tuple(sorted(LANES)),
            required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
        )
        self.release: GitHubRelease | None = None
        self.payloads: dict[int, bytes] = {}
        self.create_calls = 0
        self.upload_calls: list[str] = []
        self.fail_create_after_write = False
        self.fail_upload_after_write: set[str] = set()
        self.fail_publish_after_write = False
        self.publish_mutation: str | None = None
        self.release_reads = 0
        self.mutate_on_release_read: int | None = None
        self.patch_calls: list[tuple[int, dict[str, bool]]] = []
        self.release_version = 1
        self.validator_mode = "strong"
        self.mutate_before_conditional_patch = False
        self.next_asset_id = 40
        self.latest_release: GitHubRelease | None = None
        self.latest_error: Exception | None = None
        self.by_tag_unavailable = False

    def _release_projection(self) -> GitHubRelease | None:
        if self.release is None:
            return None
        return GitHubRelease(**self.release.__dict__)

    def _touch_release(self) -> None:
        self.release_version += 1

    def get_branch(self, repository: str, branch: str) -> BranchProjection:
        return self.branch

    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]:
        return self.runs

    def list_run_jobs(self, repository: str, run_id: int) -> list[RunJobProjection]:
        return list(self.jobs)

    def get_ci_scope_manifest(self, repository: str, run: RunProjection) -> CiScopeProjection:
        return self.scope

    def get_release_by_tag(self, repository: str, tag: str) -> GitHubRelease | None:
        if self.by_tag_unavailable:
            raise GitHubApiError("published-only by-tag endpoint is unavailable for Drafts")
        projected = self._release_projection()
        return projected if projected is not None and projected.tag_name == tag else None

    def list_releases(self, repository: str) -> list[GitHubRelease]:
        projected = self._release_projection()
        return [] if projected is None else [projected]

    def get_release(self, repository: str, release_id: int) -> GitHubRelease | None:
        self.release_reads += 1
        if self.release_reads == self.mutate_on_release_read and self.release is not None:
            field, value = getattr(
                self, "intervening_release_mutation", ("name", "intervening change"),
            )
            self.release = GitHubRelease(**{**self.release.__dict__, field: value})
            self._touch_release()
        projected = self._release_projection()
        return projected if projected is not None and projected.id == release_id else None

    def get_latest_release(self, repository: str) -> GitHubRelease | None:
        if self.latest_error is not None:
            raise self.latest_error
        return self.latest_release

    def create_draft_release(self, repository: str, *, tag: str, name: str, body: str,
                             prerelease: bool, make_latest: bool) -> GitHubRelease:
        self.create_calls += 1
        self.release = GitHubRelease(
            17, tag, name, body, True, prerelease, make_latest,
            _DRAFT_HTML_URL,
            "https://uploads.github.com/repos/endaye/lmdj/releases/17/assets{?name,label}", (),
            self.target,
        )
        if self.fail_create_after_write:
            raise GitHubApiError("GitHub release request is unavailable")
        return self.release

    def list_release_assets(self, repository: str, release_id: int) -> list[GitHubAsset]:
        return list(self.release.assets if self.release is not None else ())

    def upload_release_asset(self, repository: str, release_id: int, upload_url: str,
                             name: str, payload: bytes) -> GitHubAsset:
        if self.release is None or self.release.id != release_id:
            raise RuntimeError("wrong release ownership")
        self.upload_calls.append(name)
        self.next_asset_id += 1
        asset = GitHubAsset(
            self.next_asset_id, name, len(payload),
            f"https://api.github.com/repos/endaye/lmdj/releases/assets/{self.next_asset_id}",
            f"https://github.com/endaye/lmdj/releases/download/test/{name}",
            release_id, None, "application/octet-stream", "uploaded",
        )
        self.payloads[asset.id] = payload
        assert self.release is not None
        self.release = GitHubRelease(**{
            **self.release.__dict__, "assets": self.release.assets + (asset,),
        })
        self._touch_release()
        if name in self.fail_upload_after_write:
            raise GitHubApiError("GitHub release request is unavailable")
        return asset

    def download_asset(self, repository: str, release_id: int, asset: GitHubAsset) -> bytes:
        if repository != "endaye/lmdj" or asset.release_id != release_id:
            raise RuntimeError("wrong repository ownership")
        return self.payloads[asset.id]

    def publish_release(
        self, repository: str, release_id: int, *, prerelease: bool, make_latest: bool,
    ) -> GitHubRelease:
        if repository != "endaye/lmdj" or self.release is None or self.release.id != release_id:
            raise RuntimeError("wrong release ownership")
        if self.mutate_before_conditional_patch:
            self.release = GitHubRelease(**{
                **self.release.__dict__, "name": "concurrent change",
            })
            self._touch_release()
        payload = {
            "draft": False, "prerelease": prerelease, "make_latest": make_latest,
        }
        self.patch_calls.append((release_id, payload))
        self.release = GitHubRelease(**{
            **self.release.__dict__, "draft": False, "prerelease": prerelease,
            "make_latest": make_latest,
            "html_url": _published_html_url(self.release.tag_name),
        })
        self._touch_release()
        if self.publish_mutation == "name":
            self.release = GitHubRelease(**{**self.release.__dict__, "name": "changed"})
        elif self.publish_mutation == "target-commitish":
            self.release = GitHubRelease(**{
                **self.release.__dict__, "target_commitish": "changed-target",
            })
        elif self.publish_mutation == "asset-id":
            original = self.release.assets[0]
            changed = GitHubAsset(**{**original.__dict__, "id": original.id + 1000})
            self.payloads[changed.id] = self.payloads[original.id]
            self.release = GitHubRelease(**{
                **self.release.__dict__,
                "assets": (changed,) + self.release.assets[1:],
            })
        elif self.publish_mutation in (
            "asset-label", "asset-content-type", "asset-state",
        ):
            original = self.release.assets[0]
            field, value = {
                "asset-label": ("label", "changed label"),
                "asset-content-type": ("content_type", "application/zip"),
                "asset-state": ("state", "open"),
            }[self.publish_mutation]
            changed = GitHubAsset(**{**original.__dict__, field: value})
            self.release = GitHubRelease(**{
                **self.release.__dict__,
                "assets": (changed,) + self.release.assets[1:],
            })
        elif self.publish_mutation == "asset-download-url":
            # GitHub rewrites every asset download path from the untagged draft
            # form to the exact tag form on a genuine publish.
            rewritten = tuple(
                GitHubAsset(**{
                    **original.__dict__,
                    "browser_download_url": (
                        "https://github.com/endaye/lmdj/releases/download/"
                        f"{self.release.tag_name}/{original.name}"
                    ),
                })
                for original in self.release.assets
            )
            self.release = GitHubRelease(**{
                **self.release.__dict__, "assets": rewritten,
            })
        elif self.publish_mutation == "html-url":
            self.release = GitHubRelease(**{
                **self.release.__dict__, "html_url": _DRAFT_HTML_URL,
            })
        if self.fail_publish_after_write:
            raise GitHubApiError("GitHub release request is unavailable")
        projected = self._release_projection()
        assert projected is not None
        return projected


class ReleaseTransitionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-release-transition-")
        self.root = Path(self.temporary.name)
        self.target = "a" * 40
        self.tag = "lmdj-v1.0.21.0"
        self.profile = "web-runtime-host"
        # Retain the historical pre-cutover transition matrix explicitly.
        self.policy = replace(load_policy(ROOT / "tools/release/policy.json"), prospective_ci_protocol="ci-scope-v2")
        self.ledger = load_ledger_document({
            "schema": "lmdj.release-intents.v1",
            "entries": [{
                "tag": self.tag, "kind": "product", "identity": "1.0.21.0",
                "target_revision": self.target, "channel": "canary",
                "disposition": "releasable", "profile": self.profile,
                "snapshot": "1.0.21.0", "merged_main_run_id": 123,
                "evidence_paths": ["docs/quality/example-proof.md"],
            }],
            "historical_exceptions": [],
        }, self.policy)
        self.git = FakeGit(self.target, self.policy.product_fingerprint)
        self.github = FakeGitHub(self.target)
        self.verified_assets: list[tuple[str, ...]] = []
        self._write_prepared_output()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _asset_payloads(self) -> tuple[tuple[str, bytes], ...]:
        if self.profile == "web-hosts":
            result: list[tuple[str, bytes]] = []
            for host in ("creator-web", "web-runtime-host"):
                archive = f"lmdj-{host}-2.1.1-product-1.0.21.0.zip"
                result.extend(
                    (
                        (archive, f"{host}-zip".encode("ascii")),
                        (archive + ".sha256", f"{host}-checksum".encode("ascii")),
                        (archive + ".sha256.asc", f"{host}-signature".encode("ascii")),
                    )
                )
            return tuple(result)
        archive = "lmdj-web-runtime-host-1.1.2-product-1.0.21.0.zip"
        return ((archive, b"zip"), (archive + ".sha256", b"checksum"),
                (archive + ".sha256.asc", b"signature"))

    def _plan(self) -> dict[str, object]:
        assets = [
            {"name": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
            for name, payload in self._asset_payloads()
        ]
        return {
            "schema": "lmdj.release-plan.v1", "repository": "endaye/lmdj", "tag": self.tag,
            "tag_object": "b" * 40, "target_revision": self.target, "kind": "product",
            "identity": "1.0.21.0", "channel": "canary", "profile": self.profile,
            "ci": {"run_id": 123, "event": "push", "head_sha": self.target, "conclusion": "success"},
            "release": {"draft": True, "prerelease": True, "make_latest": False, "name": "LMDJ 1.0.21.0"},
            "assets": assets,
            "snapshot": "1.0.21.0",
        }

    def _write_prepared_output(self) -> None:
        output = self.root / "build/release/lmdj-v1.0.21.0"
        assets = output / "assets"
        assets.mkdir(parents=True)
        for name, payload in self._asset_payloads():
            (assets / name).write_bytes(payload)
        document = self._plan()
        digest = hashlib.sha256(canonical_json(document)).hexdigest()
        (output / "release-plan.json").write_bytes(canonical_json(document))
        (output / "release-plan.sha256").write_text(digest + "\n", encoding="ascii")
        (output / "release-notes.md").write_text("# LMDJ 1.0.21.0\n", encoding="utf-8")

    def context(self) -> PrepareContext:
        return PrepareContext(
            repo_root=self.root, policy=self.policy, ledger=self.ledger, git=self.git,
            github=self.github, profile_builder=lambda *args: None,
            profile_verifier=lambda profile, tree, root, intent, assets: self.verified_assets.append(
                tuple(item.name for item in assets)
            ),
            proof_reader=lambda tree, intent: ProductProof(
                "main", self.target, "1.0.21.0", "1.0.21.0", self.target,
            ),
            tag_signer_fingerprint=self.policy.product_fingerprint,
            checksum_signer_fingerprint=self.policy.checksum_fingerprint,
            authority_reader=lambda tree: (self.policy, self.ledger),
        )

    def _push_and_create(self):
        push_tag(self.tag, self.context())
        return create_draft(self.tag, self.context())

    def test_noncanonical_origin_is_rejected_before_exact_tag_mutation(self) -> None:
        repository = self.root / "origin-guard"
        remote = self.root / "noncanonical.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)
        for key, value in (("user.email", "release-test@example.invalid"), ("user.name", "Release Test")):
            subprocess.run(["git", "-C", str(repository), "config", key, value], check=True)
        (repository / "tracked.txt").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-m", "fixture"], check=True, capture_output=True)
        tag = "module/core-cli/v1.0.2"
        subprocess.run(["git", "-C", str(repository), "tag", "-a", tag, "-m", "fixture"], check=True)
        subprocess.run(["git", "-C", str(repository), "remote", "add", "origin", str(remote)], check=True)

        with self.assertRaisesRegex(GitRepositoryError, "canonical origin"):
            GitRepository(repository).push_tag(tag)
        observed = subprocess.run(
            ["git", "--git-dir", str(remote), "show-ref", "--verify", f"refs/tags/{tag}"],
            check=False, capture_output=True, text=True,
        )
        self.assertNotEqual(observed.returncode, 0)

    def test_git_repository_push_uses_one_exact_refspec_without_force_or_tags(self) -> None:
        class CanonicalRunner(RecordingRunner):
            def run(self, arguments, *, cwd=None, environment=None) -> CommandResult:
                result = super().run(arguments, cwd=cwd, environment=environment)
                if list(arguments) == ["git", "remote", "get-url", "--all", "origin"]:
                    return CommandResult(tuple(arguments), 0, "https://github.com/endaye/lmdj.git\n", "")
                if list(arguments) == ["git", "remote", "get-url", "--push", "--all", "origin"]:
                    return CommandResult(tuple(arguments), 0, "git@github.com:endaye/lmdj.git\n", "")
                return result

        runner = CanonicalRunner()
        repository = GitRepository(self.root, runner=runner)
        repository.push_tag("module/core-cli/v1.0.2")
        self.assertEqual(runner.commands[-1], [
            "git", "push", "origin",
            "refs/tags/module/core-cli/v1.0.2:refs/tags/module/core-cli/v1.0.2",
        ])
        self.assertNotIn("--tags", runner.commands[-1])
        self.assertNotIn("--force", runner.commands[-1])

    def test_local_tag_operations_force_openpgp_despite_global_git_signing_format(self) -> None:
        class CreatingRepository(GitRepository):
            def local_tag_state(self, tag: str) -> LocalTag:
                return LocalTag("b" * 40, self.root.name, "C" * 40)

        create_runner = RecordingRunner()
        target = "a" * 40
        repository = CreatingRepository(Path(target), runner=create_runner)
        repository.create_local_tag("lmdj-v1.0.21.0", target, "C" * 40, "fixture")
        self.assertEqual(create_runner.commands[0][:4], [
            "git", "-c", "gpg.format=openpgp", "tag",
        ])

        class VerifyingRunner(RecordingRunner):
            def run(self, arguments, *, cwd=None, environment=None) -> CommandResult:
                vector = [str(item) for item in arguments]
                self.commands.append(vector)
                if vector[-3:] == ["rev-parse", "--verify", "refs/tags/fixture"]:
                    return CommandResult(tuple(vector), 0, "b" * 40 + "\n", "")
                if vector[-3:] == ["cat-file", "-t", "refs/tags/fixture"]:
                    return CommandResult(tuple(vector), 0, "tag\n", "")
                if vector[-3:] == ["rev-parse", "--verify", "refs/tags/fixture^{commit}"]:
                    return CommandResult(tuple(vector), 0, target + "\n", "")
                if vector[-3:] == ["verify-tag", "--raw", "refs/tags/fixture"]:
                    status = "[GNUPG:] VALIDSIG " + "C" * 40 + "\n"
                    return CommandResult(tuple(vector), 0, "", status)
                raise AssertionError(vector)

        verify_runner = VerifyingRunner()
        verified = GitRepository(self.root, runner=verify_runner).local_tag_state("fixture")
        self.assertEqual(verified.signer_fingerprint, "C" * 40)
        verify_command = next(
            command for command in verify_runner.commands if "verify-tag" in command
        )
        self.assertEqual(verify_command[:4], [
            "git", "-c", "gpg.format=openpgp", "verify-tag",
        ])

    def test_origin_guard_rejects_any_extra_fetch_or_push_url(self) -> None:
        class MultipleUrlRunner(RecordingRunner):
            def __init__(self, *, extra_fetch: bool) -> None:
                super().__init__()
                self.extra_fetch = extra_fetch

            def run(self, arguments, *, cwd=None, environment=None) -> CommandResult:
                result = super().run(arguments, cwd=cwd, environment=environment)
                if list(arguments) == ["git", "remote", "get-url", "--all", "origin"]:
                    lines = ["https://github.com/endaye/lmdj.git"]
                    if self.extra_fetch:
                        lines.append("https://github.com/attacker/fork.git")
                    return CommandResult(tuple(arguments), 0, "\n".join(lines) + "\n", "")
                if list(arguments) == ["git", "remote", "get-url", "--push", "--all", "origin"]:
                    lines = ["https://github.com/endaye/lmdj.git"]
                    if not self.extra_fetch:
                        lines.append("https://github.com/attacker/fork.git")
                    return CommandResult(tuple(arguments), 0, "\n".join(lines) + "\n", "")
                return result

        for extra_fetch in (True, False):
            with self.subTest(extra_fetch=extra_fetch):
                runner = MultipleUrlRunner(extra_fetch=extra_fetch)
                with self.assertRaisesRegex(GitRepositoryError, "canonical origin"):
                    GitRepository(self.root, runner=runner).push_tag("module/core-cli/v1.0.2")
                self.assertFalse(any(command[:2] == ["git", "push"] for command in runner.commands))

    def test_origin_guard_accepts_implicit_push_url_equal_to_fetch_url(self) -> None:
        class ImplicitPushRunner(RecordingRunner):
            def run(self, arguments, *, cwd=None, environment=None) -> CommandResult:
                result = super().run(arguments, cwd=cwd, environment=environment)
                if list(arguments) in (
                    ["git", "remote", "get-url", "--all", "origin"],
                    ["git", "remote", "get-url", "--push", "--all", "origin"],
                ):
                    return CommandResult(
                        tuple(arguments), 0, "https://github.com/endaye/lmdj.git\n", "",
                    )
                return result

        runner = ImplicitPushRunner()
        GitRepository(self.root, runner=runner).push_tag("module/core-cli/v1.0.2")
        self.assertEqual(runner.commands[-1][:3], ["git", "push", "origin"])

    def test_git_repository_preserves_sanitized_command_detail(self) -> None:
        class FailingPushRunner(RecordingRunner):
            def run(self, arguments, *, cwd=None, environment=None) -> CommandResult:
                result = super().run(arguments, cwd=cwd, environment=environment)
                if list(arguments) in (
                    ["git", "remote", "get-url", "--all", "origin"],
                    ["git", "remote", "get-url", "--push", "--all", "origin"],
                ):
                    return CommandResult(
                        tuple(arguments), 0, "https://github.com/endaye/lmdj.git\n", "",
                    )
                if list(arguments)[:2] == ["git", "push"]:
                    raise CommandError(
                        "release command failed: git (exit 128)",
                        detail="remote: permission denied for refs/tags/lmdj-v1.0.36.0",
                    )
                return result

        with self.assertRaises(GitRepositoryError) as caught:
            GitRepository(self.root, runner=FailingPushRunner()).push_tag(
                "lmdj-v1.0.36.0",
            )

        self.assertEqual(
            caught.exception.detail,
            "remote: permission denied for refs/tags/lmdj-v1.0.36.0",
        )

    def test_fetch_authority_prunes_deleted_tags_from_the_scratch_namespace(self) -> None:
        runner = RecordingRunner()
        GitRepository(self.root, runner=runner).fetch_authority("endaye/lmdj", "main")
        self.assertEqual(runner.commands, [[
            "git", "fetch", "--no-tags", "--prune", "https://github.com/endaye/lmdj.git",
            "+refs/heads/main:refs/lmdj-release/origin-main",
            "+refs/tags/*:refs/lmdj-release/tags/*",
        ]])

    def test_git_tag_status_rejects_adverse_signature_even_with_validsig(self) -> None:
        valid = f"[GNUPG:] VALIDSIG {self.policy.product_fingerprint}\n"
        for status in ("EXPKEYSIG", "EXPSIG", "REVKEYSIG", "KEYREVOKED", "BADSIG", "ERRSIG"):
            with self.subTest(status=status):
                self.assertIsNone(_signer_from_status(
                    f"[GNUPG:] {status} {self.policy.product_fingerprint}\n" + valid,
                ))

    def test_push_refetches_and_reconciles_remote_object(self) -> None:
        result = push_tag(self.tag, self.context())
        self.assertEqual(result.status, "pushed")
        self.assertEqual(self.git.pushes, 1)
        self.assertGreaterEqual(self.git.fetches, 2)
        self.git.pushes = 0
        result = push_tag(self.tag, self.context())
        self.assertEqual(result.status, "already-pushed")
        self.assertEqual(self.git.pushes, 0)

    def test_uncertain_push_requires_the_fresh_remote_object(self) -> None:
        self.git.push_raises_after_write = True
        result = push_tag(self.tag, self.context())
        self.assertEqual(result.status, "pushed")
        self.git.remote = None
        self.git.push_raises_after_write = False
        self.git.push_raises_without_write = True
        with self.assertRaisesRegex(TransitionError, "freshly fetched remote tag"):
            push_tag(self.tag, self.context())

    def test_failed_push_reports_sanitized_transport_detail_after_remote_absence(self) -> None:
        self.git.push_raises_without_write = True
        self.git.push_failure_detail = (
            "remote: permission denied for refs/tags/lmdj-v1.0.21.0"
        )

        with self.assertRaises(TransitionError) as caught:
            push_tag(self.tag, self.context())

        self.assertIn("freshly fetched remote tag", str(caught.exception))
        self.assertIn(self.git.push_failure_detail, str(caught.exception))

    def test_push_rejects_remote_conflict_without_mutation(self) -> None:
        self.git.remote = LocalTag("c" * 40, self.target, self.policy.product_fingerprint)
        with self.assertRaisesRegex(TransitionError, "remote tag conflict"):
            push_tag(self.tag, self.context())
        self.assertEqual(self.git.pushes, 0)

    def test_create_draft_uploads_three_assets_and_reconciles_identically(self) -> None:
        first = self._push_and_create()
        self.assertEqual(first.status, "draft-created")
        self.assertEqual(len(self.github.release.assets), 3)
        self.assertEqual(self.github.create_calls, 1)
        second = create_draft(self.tag, self.context())
        self.assertEqual(second.status, "draft-verified")
        self.assertEqual(self.github.create_calls, 1)
        self.assertEqual(len(self.github.upload_calls), 3)

    def test_create_draft_uploads_and_reconciles_six_dual_host_assets(self) -> None:
        self.profile = "web-hosts"
        self.ledger = load_ledger_document({
            "schema": "lmdj.release-intents.v1",
            "entries": [{
                "tag": self.tag, "kind": "product", "identity": "1.0.21.0",
                "target_revision": self.target, "channel": "canary",
                "disposition": "releasable", "profile": self.profile,
                "snapshot": "1.0.21.0", "merged_main_run_id": 123,
                "evidence_paths": ["docs/quality/example-proof.md"],
            }],
            "historical_exceptions": [],
        }, self.policy)
        shutil.rmtree(self.root / "build/release/lmdj-v1.0.21.0")
        self._write_prepared_output()

        first = self._push_and_create()
        second = create_draft(self.tag, self.context())

        self.assertEqual(first.status, "draft-created")
        self.assertEqual(second.status, "draft-verified")
        self.assertEqual(len(self.github.release.assets), 6)
        self.assertEqual(len(self.github.upload_calls), 6)

    def test_draft_discovery_uses_complete_release_inventory_not_published_by_tag(self) -> None:
        self.github.by_tag_unavailable = True
        created = self._push_and_create()
        self.assertEqual(created.status, "draft-created")
        verified = verify_draft(
            self.tag, created.release_id, created.plan_sha256, self.context(),
        )
        self.assertEqual(verified.status, "draft-verified")

    def test_source_only_draft_has_zero_custom_assets(self) -> None:
        self.tag = "module/core-cli/v1.0.3"
        self.ledger = load_ledger_document({
            "schema": "lmdj.release-intents.v1",
            "entries": [{
                "tag": self.tag, "kind": "module", "identity": "core-cli@1.0.3",
                "target_revision": self.target, "disposition": "releasable",
                "profile": "source-only", "merged_main_run_id": 123,
                "evidence_paths": ["docs/quality/example-proof.md"],
            }],
            "historical_exceptions": [],
        }, self.policy)
        self.git.local = LocalTag("b" * 40, self.target, self.policy.product_fingerprint)
        output = self.root / "build/release/module%2Fcore-cli%2Fv1.0.3"
        (output / "assets").mkdir(parents=True)
        document = {
            "schema": "lmdj.release-plan.v1", "repository": "endaye/lmdj", "tag": self.tag,
            "tag_object": "b" * 40, "target_revision": self.target, "kind": "module",
            "identity": "core-cli@1.0.3", "profile": "source-only",
            "ci": {"run_id": 123, "event": "push", "head_sha": self.target, "conclusion": "success"},
            "release": {"draft": True, "prerelease": False, "make_latest": False,
                        "name": "module core-cli@1.0.3"},
            "assets": [],
        }
        digest = hashlib.sha256(canonical_json(document)).hexdigest()
        (output / "release-plan.json").write_bytes(canonical_json(document))
        (output / "release-plan.sha256").write_text(digest + "\n", encoding="ascii")
        (output / "release-notes.md").write_text("# module core-cli@1.0.3\n", encoding="utf-8")
        result = self._push_and_create()
        self.assertEqual(result.status, "draft-created")
        self.assertEqual(self.github.release.assets, ())
        self.assertEqual(self.github.upload_calls, [])

    def test_partial_upload_resume_and_uncertain_create_reconcile(self) -> None:
        push_tag(self.tag, self.context())
        self.github.fail_create_after_write = True
        self.github.fail_upload_after_write.add(self._asset_payloads()[0][0])
        result = create_draft(self.tag, self.context())
        self.assertEqual(result.status, "draft-created")
        self.assertEqual(len(self.github.release.assets), 3)
        self.assertEqual(len(set(self.github.upload_calls)), 3)

    def test_extra_or_same_name_different_digest_is_rejected_without_clobber(self) -> None:
        self._push_and_create()
        assert self.github.release is not None
        extra = GitHubAsset(
            99, "extra.txt", 1, "https://api.github.com/assets/99",
            "https://github.com/extra", 17, None,
            "application/octet-stream", "uploaded",
        )
        self.github.payloads[99] = b"x"
        self.github.release = GitHubRelease(**{**self.github.release.__dict__, "assets": self.github.release.assets + (extra,)})
        with self.assertRaisesRegex(TransitionError, "asset inventory"):
            create_draft(self.tag, self.context())
        self.github.release = GitHubRelease(**{**self.github.release.__dict__, "assets": self.github.release.assets[:-1]})
        first = self.github.release.assets[0]
        self.github.payloads[first.id] = b"different"
        with self.assertRaisesRegex(TransitionError, "digest"):
            create_draft(self.tag, self.context())

    def test_published_release_is_read_only_and_must_match(self) -> None:
        created = self._push_and_create()
        assert self.github.release is not None
        self.github.release = GitHubRelease(**{**self.github.release.__dict__, "draft": False})
        before = (self.github.create_calls, tuple(self.github.upload_calls))
        result = create_draft(self.tag, self.context())
        self.assertEqual(result.status, "already-published")
        self.assertEqual((self.github.create_calls, tuple(self.github.upload_calls)), before)
        self.github.release = GitHubRelease(**{**self.github.release.__dict__, "body": "wrong"})
        with self.assertRaises(TransitionError):
            create_draft(self.tag, self.context())
        self.assertEqual(created.release_id, result.release_id)

    def test_published_intent_never_resumes_a_historical_draft_or_patches_it(self) -> None:
        created = self._push_and_create()
        assert created.release_id is not None
        self.ledger = load_ledger_document({
            "schema": "lmdj.release-intents.v1",
            "entries": [{
                "tag": self.tag, "kind": "product", "identity": "1.0.21.0",
                "target_revision": self.target, "channel": "canary",
                "disposition": "published", "profile": "web-runtime-host",
                "snapshot": "1.0.21.0", "merged_main_run_id": 123,
                "evidence_paths": ["docs/quality/example-proof.md"],
            }],
            "historical_exceptions": [],
        }, self.policy)
        uploads = tuple(self.github.upload_calls)
        with self.assertRaisesRegex(TransitionError, "published.*read-only"):
            create_draft(self.tag, self.context())
        self.assertEqual(tuple(self.github.upload_calls), uploads)
        with self.assertRaisesRegex(TransitionError, "published.*read-only"):
            publish_draft(
                self.tag, created.release_id, created.plan_sha256, self.context(),
                actions_environment={"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch"},
            )
        self.assertEqual(self.github.patch_calls, [])

    def test_verify_draft_requires_authoritative_latest_projection(self) -> None:
        created = self._push_and_create()
        assert self.github.release is not None and created.release_id is not None
        self.github.latest_release = self.github.release
        with self.assertRaisesRegex(TransitionError, "latest Release projection"):
            verify_draft(self.tag, created.release_id, created.plan_sha256, self.context())

    def test_transition_rejects_kind_specific_exact_target_validation_failure(self) -> None:
        self.git.target_validation_error = RuntimeError("provider manifest mismatch")
        with self.assertRaisesRegex(TransitionError, "exact release target"):
            push_tag(self.tag, self.context())

    def test_real_verify_draft_is_agentless_with_empty_caller_keyring(self) -> None:
        tag = "module/application-facade/v1.0.1"
        policy, ledger = load_authority_documents(ROOT)
        intent = ledger.intent_for_tag(tag)
        assert intent is not None and intent.merged_main_run_id is not None
        target = intent.target_revision
        tag_object = subprocess.run(
            ["git", "rev-parse", f"refs/tags/{tag}"], cwd=ROOT,
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        run = RunProjection(
            intent.merged_main_run_id, "push", target, "main", "Core CI", "completed", "success",
        )
        plan = _release_plan(
            policy, tag, LocalTag(tag_object, target, policy.product_fingerprint), intent, (),
        )
        document = _plan_document(plan, intent, run, policy)
        digest = hashlib.sha256(canonical_json(document)).hexdigest()
        release_fields = document["release"]
        github = FakeGitHub(target)
        github.runs = [run]
        github.release = GitHubRelease(
            17, tag, release_fields["name"], marker_for_plan(document, digest),
            False, release_fields["prerelease"], release_fields["make_latest"],
            f"https://github.com/endaye/lmdj/releases/tag/{tag}",
            "https://uploads.github.com/repos/endaye/lmdj/releases/17/assets{?name,label}",
            (), target,
        )

        class OfflineGit(GitRepository):
            def __init__(self, root: Path) -> None:
                super().__init__(root)
                self._main_ref = "refs/remotes/origin/main"
                self._tag_prefix = "refs/tags/"

            def fetch_authority(self, repository: str, branch: str) -> None:
                return None

        git = OfflineGit(ROOT)
        github.branch = BranchProjection("main", True, git.main_revision())

        context = PrepareContext(
            repo_root=ROOT, policy=policy, ledger=ledger, git=git, github=github,
            profile_builder=lambda *args: None, profile_verifier=lambda *args: None,
            proof_reader=lambda *args: None,
            tag_signer_fingerprint=policy.product_fingerprint,
            checksum_signer_fingerprint=policy.checksum_fingerprint,
            authority_reader=lambda tree: (policy, ledger),
        )
        with tempfile.TemporaryDirectory(prefix="empty-release-keyring-") as directory:
            os.chmod(directory, 0o700)
            with patch.dict(os.environ, {"GNUPGHOME": directory}):
                verified = verify_draft(tag, 17, digest, context)
        self.assertEqual(verified.status, "already-published")

    def test_verify_draft_reconstructs_plan_without_local_release_output(self) -> None:
        result = self._push_and_create()
        expected = result.plan_sha256
        release_id = result.release_id
        output = self.root / "build/release/lmdj-v1.0.21.0"
        for path in sorted(output.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        output.rmdir()
        verified = verify_draft(self.tag, release_id, expected, self.context())
        self.assertEqual(verified.plan_sha256, expected)
        self.assertTrue(self.verified_assets)

    def test_publish_changes_only_draft_and_preserves_exact_assets(self) -> None:
        created = self._push_and_create()
        assert created.release_id is not None
        assert self.github.release is not None
        original = self.github.release
        result = publish_draft(
            self.tag, created.release_id, created.plan_sha256, self.context(),
            actions_environment={
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
            },
        )
        self.assertEqual(self.github.patch_calls, [(created.release_id, {
            "draft": False, "prerelease": True, "make_latest": False,
        })])
        self.assertEqual(result.status, "published")
        self.assertEqual(original.html_url, _DRAFT_HTML_URL)
        self.assertEqual(result.release_url, _published_html_url(self.tag))
        self.assertEqual(result.assets, original.assets)
        assert self.github.release is not None
        self.assertFalse(self.github.release.draft)
        self.assertEqual(self.github.release.html_url, _published_html_url(self.tag))
        self.assertEqual(
            {
                **self.github.release.__dict__,
                "draft": True,
                "html_url": original.html_url,
            },
            original.__dict__,
        )

    def test_publish_rejects_stale_untagged_html_url_after_publication(self) -> None:
        created = self._push_and_create()
        assert created.release_id is not None
        self.github.publish_mutation = "html-url"
        with self.assertRaisesRegex(
            TransitionError, "html_url is not the exact published tag URL",
        ):
            publish_draft(
                self.tag, created.release_id, created.plan_sha256, self.context(),
                actions_environment={
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_EVENT_NAME": "workflow_dispatch",
                },
            )
        self.assertEqual(len(self.github.patch_calls), 1)
        assert self.github.release is not None
        self.assertFalse(self.github.release.draft)
        self.assertEqual(self.github.release.html_url, _DRAFT_HTML_URL)

    def test_publish_tolerates_the_asset_download_url_rewrite(self) -> None:
        # Publication rewrites each asset download path exactly as it rewrites
        # the Release html_url, so that path is not a draft-invariant field. A
        # comparison that treats it as one fails 100% of genuine publications
        # after GitHub has already accepted the mutation.
        created = self._push_and_create()
        assert created.release_id is not None
        self.github.publish_mutation = "asset-download-url"
        result = publish_draft(
            self.tag, created.release_id, created.plan_sha256, self.context(),
            actions_environment={
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
            },
        )
        self.assertEqual(result.status, "published")
        assert self.github.release is not None
        self.assertFalse(self.github.release.draft)
        for asset in self.github.release.assets:
            self.assertEqual(
                asset.browser_download_url,
                "https://github.com/endaye/lmdj/releases/download/"
                f"{self.tag}/{asset.name}",
            )

    def test_publish_reconciles_an_accepted_patch_by_numeric_id(self) -> None:
        created = self._push_and_create()
        assert created.release_id is not None
        self.github.fail_publish_after_write = True
        result = publish_draft(
            self.tag, created.release_id, created.plan_sha256, self.context(),
            actions_environment={
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
            },
        )
        self.assertEqual(result.status, "published")
        self.assertEqual(self.github.create_calls, 1)
        self.assertEqual(len(self.github.patch_calls), 1)

    def test_publish_rejects_intervening_draft_mutation_before_patch(self) -> None:
        for field, value in (
            ("name", "intervening change"),
            ("target_commitish", "intervening-target"),
        ):
            with self.subTest(field=field):
                self.github = FakeGitHub(self.target)
                created = self._push_and_create()
                assert created.release_id is not None
                self.github.release_reads = 0
                self.github.mutate_on_release_read = 2
                self.github.intervening_release_mutation = (field, value)
                with self.assertRaisesRegex(TransitionError, "metadata"):
                    publish_draft(
                        self.tag, created.release_id, created.plan_sha256,
                        self.context(), actions_environment={
                            "GITHUB_ACTIONS": "true",
                            "GITHUB_EVENT_NAME": "workflow_dispatch",
                        },
                    )
                self.assertEqual(self.github.patch_calls, [])

    def test_publish_refetches_authority_immediately_before_mutation(self) -> None:
        created = self._push_and_create()
        assert created.release_id is not None
        published_ledger = load_ledger_document({
            "schema": "lmdj.release-intents.v1",
            "entries": [{
                "tag": self.tag, "kind": "product", "identity": "1.0.21.0",
                "target_revision": self.target, "channel": "canary",
                "disposition": "published", "profile": "web-runtime-host",
                "snapshot": "1.0.21.0", "merged_main_run_id": 123,
                "evidence_paths": ["docs/quality/example-proof.md"],
            }],
            "historical_exceptions": [],
        }, self.policy)
        reads = 0

        def authority_reader(tree):
            nonlocal reads
            reads += 1
            return self.policy, published_ledger if reads >= 3 else self.ledger

        context = replace(self.context(), authority_reader=authority_reader)
        with self.assertRaisesRegex(TransitionError, "published.*read-only"):
            publish_draft(
                self.tag, created.release_id, created.plan_sha256, context,
                actions_environment={
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_EVENT_NAME": "workflow_dispatch",
                },
            )
        self.assertEqual(self.github.patch_calls, [])

    def test_publish_detects_mutation_after_final_verification(self) -> None:
        created = self._push_and_create()
        assert created.release_id is not None
        self.github.mutate_before_conditional_patch = True
        with self.assertRaisesRegex(TransitionError, "metadata conflicts"):
            publish_draft(
                self.tag, created.release_id, created.plan_sha256,
                self.context(), actions_environment={
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_EVENT_NAME": "workflow_dispatch",
                },
            )
        self.assertEqual(len(self.github.patch_calls), 1)
        assert self.github.release is not None
        self.assertFalse(self.github.release.draft)

    def test_publish_does_not_depend_on_missing_or_weak_release_etag(self) -> None:
        for mode in ("missing", "weak"):
            with self.subTest(mode=mode):
                self.github = FakeGitHub(self.target)
                created = self._push_and_create()
                assert created.release_id is not None
                self.github.validator_mode = mode
                published = publish_draft(
                    self.tag, created.release_id, created.plan_sha256,
                    self.context(), actions_environment={
                        "GITHUB_ACTIONS": "true",
                        "GITHUB_EVENT_NAME": "workflow_dispatch",
                    },
                )
                self.assertEqual(published.status, "published")
                self.assertEqual(len(self.github.patch_calls), 1)

    def test_publish_rejects_metadata_or_asset_identity_drift(self) -> None:
        cases = (
            ("name", "metadata"),
            ("target-commitish", "metadata"),
            ("asset-id", "assets"),
            ("asset-label", "assets"),
            ("asset-content-type", "assets"),
            ("asset-state", "assets"),
        )
        for mutation, message in cases:
            with self.subTest(mutation=mutation):
                self.github = FakeGitHub(self.target)
                created = self._push_and_create()
                assert created.release_id is not None
                self.github.publish_mutation = mutation
                with self.assertRaisesRegex(TransitionError, message):
                    publish_draft(
                        self.tag, created.release_id, created.plan_sha256,
                        self.context(), actions_environment={
                            "GITHUB_ACTIONS": "true",
                            "GITHUB_EVENT_NAME": "workflow_dispatch",
                        },
                    )
                self.assertEqual(self.github.create_calls, 1)

    def test_publish_is_actions_dispatch_only(self) -> None:
        created = self._push_and_create()
        assert created.release_id is not None
        for environment in (
            {},
            {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push"},
            {"GITHUB_ACTIONS": "false", "GITHUB_EVENT_NAME": "workflow_dispatch"},
        ):
            with self.subTest(environment=environment):
                with self.assertRaisesRegex(TransitionError, "Actions workflow_dispatch"):
                    publish_draft(
                        self.tag, created.release_id, created.plan_sha256,
                        self.context(), actions_environment=environment,
                    )
        self.assertEqual(self.github.patch_calls, [])

    def test_marker_and_numeric_inputs_are_strict(self) -> None:
        result = self._push_and_create()
        assert self.github.release is not None
        self.github.release = GitHubRelease(**{**self.github.release.__dict__, "body": "<!-- lmdj.release-plan-marker.v1 {} -->"})
        with self.assertRaisesRegex(TransitionError, "marker"):
            verify_draft(self.tag, result.release_id, result.plan_sha256, self.context())
        with self.assertRaisesRegex(TransitionError, "numeric"):
            verify_draft(self.tag, True, result.plan_sha256, self.context())

    def test_github_client_paginates_assets_and_rejects_cycles(self) -> None:
        pages = {
            "/repos/endaye/lmdj/releases/17/assets?per_page=100": HttpResponse(
                200, {"Link": '<https://api.github.com/repos/endaye/lmdj/releases/17/assets?per_page=100&page=2>; rel="next"'},
                json.dumps([self._asset_json(1, "one")]).encode(),
            ),
            "/repos/endaye/lmdj/releases/17/assets?per_page=100&page=2": HttpResponse(
                200, {}, json.dumps([self._asset_json(2, "two")]).encode(),
            ),
        }
        client = GitHubClient(http_transport=lambda method, url, headers, body: pages[url])
        assets = client.list_release_assets("endaye/lmdj", 17)
        self.assertEqual([asset.id for asset in assets], [1, 2])
        self.assertEqual([asset.release_id for asset in assets], [17, 17])
        pages["/repos/endaye/lmdj/releases/17/assets?per_page=100&page=2"] = HttpResponse(
            200, {"Link": '<https://api.github.com/repos/endaye/lmdj/releases/17/assets?per_page=100>; rel="next"'}, b"[]",
        )
        with self.assertRaisesRegex(GitHubApiError, "pagination"):
            client.list_release_assets("endaye/lmdj", 17)

    def test_github_client_paginates_runs_and_rejects_cycles(self) -> None:
        first = "/repos/endaye/lmdj/actions/runs?head_sha=" + self.target + "&per_page=100"
        second = first + "&page=2"
        pages = {
            first: HttpResponse(
                200, {"Link": f'<https://api.github.com{second}>; rel="next"'},
                json.dumps({"total_count": 2, "workflow_runs": [self._run_json(1)]}).encode(),
            ),
            second: HttpResponse(
                200, {}, json.dumps({"total_count": 2, "workflow_runs": [self._run_json(2)]}).encode(),
            ),
            self._workflow_url(): HttpResponse(
                200, {}, json.dumps(self._workflow_json()).encode(),
            ),
        }
        client = GitHubClient(http_transport=lambda method, url, headers, body: pages[url])
        self.assertEqual([run.id for run in client.list_runs_for_sha("endaye/lmdj", self.target)], [1, 2])
        pages[second] = HttpResponse(
            200, {"Link": f'<https://api.github.com{first}>; rel="next"'},
            json.dumps({"total_count": 2, "workflow_runs": []}).encode(),
        )
        with self.assertRaisesRegex(GitHubApiError, "pagination"):
            client.list_runs_for_sha("endaye/lmdj", self.target)

    def test_github_run_pagination_rejects_a_truncated_total(self) -> None:
        client = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
            200, {}, json.dumps({
                "total_count": 2, "workflow_runs": [self._run_json(1)],
            }).encode(),
        ))
        with self.assertRaisesRegex(GitHubApiError, "pagination"):
            client.list_runs_for_sha("endaye/lmdj", self.target)

    def test_github_release_pagination_is_typed_complete_and_strict(self) -> None:
        first = "/repos/endaye/lmdj/releases?per_page=100"
        second = first + "&page=2"
        release_one = self._release_json(17)
        release_two = self._release_json(18)
        release_two["tag_name"] = "module/core-cli/v1.0.2"
        release_two["html_url"] = "https://github.com/endaye/lmdj/releases/tag/module/core-cli/v1.0.2"
        pages = {
            first: HttpResponse(
                200,
                {"Link": f'<https://api.github.com{second}>; rel="next", '
                         f'<https://api.github.com{second}>; rel="last"'},
                json.dumps([release_one]).encode(),
            ),
            second: HttpResponse(
                200,
                {"Link": f'<https://api.github.com{first}>; rel="prev", '
                         f'<https://api.github.com{second}>; rel="last"'},
                json.dumps([release_two]).encode(),
            ),
        }
        client = GitHubClient(http_transport=lambda method, url, headers, body: pages[url])
        self.assertEqual([item.id for item in client.list_releases("endaye/lmdj")], [17, 18])

        invalid_links = (
            '<https://api.github.com/repos/other/repo/releases?per_page=100&page=2>; rel="next"',
            f'<https://api.github.com{first}>; rel="next"',
            "not-a-valid-link",
        )
        for link in invalid_links:
            with self.subTest(link=link):
                response = HttpResponse(200, {"Link": link}, json.dumps([release_one]).encode())
                strict = GitHubClient(http_transport=lambda *args: response, page_cap=1)
                with self.assertRaisesRegex(GitHubApiError, "pagination"):
                    strict.list_releases("endaye/lmdj")

        duplicate = HttpResponse(
            200, {}, json.dumps([release_one, release_one]).encode(),
        )
        with self.assertRaisesRegex(GitHubApiError, "duplicate"):
            GitHubClient(http_transport=lambda *args: duplicate).list_releases("endaye/lmdj")

    def test_all_paginators_reject_legal_next_page_beyond_page_cap(self) -> None:
        cases = (
            (
                "/repos/endaye/lmdj/releases?per_page=100",
                "/repos/endaye/lmdj/releases?per_page=100&page=2",
                json.dumps([self._release_json(17)]).encode(),
                lambda client: client.list_releases("endaye/lmdj"),
            ),
            (
                "/repos/endaye/lmdj/releases/17/assets?per_page=100",
                "/repos/endaye/lmdj/releases/17/assets?per_page=100&page=2",
                json.dumps([self._asset_json(7, "asset.zip")]).encode(),
                lambda client: client.list_release_assets("endaye/lmdj", 17),
            ),
            (
                "/repos/endaye/lmdj/actions/runs?head_sha=" + self.target + "&per_page=100",
                "/repos/endaye/lmdj/actions/runs?head_sha=" + self.target + "&per_page=100&page=2",
                json.dumps({"total_count": 2, "workflow_runs": [self._run_json(1)]}).encode(),
                lambda client: client.list_runs_for_sha("endaye/lmdj", self.target),
            ),
        )
        for first, second, body, operation in cases:
            with self.subTest(first=first):
                response = HttpResponse(
                    200, {"Link": f'<https://api.github.com{second}>; rel="next"'}, body,
                )
                client = GitHubClient(http_transport=lambda *args: response, page_cap=1)
                with self.assertRaisesRegex(GitHubApiError, "pagination"):
                    operation(client)

    def test_all_paginators_reject_legal_cycles_before_duplicates(self) -> None:
        cases = (
            (
                "/repos/endaye/lmdj/releases?per_page=100",
                "/repos/endaye/lmdj/releases?per_page=100&page=2",
                lambda page: json.dumps([self._release_json(16 + page)]).encode(),
                lambda client: client.list_releases("endaye/lmdj"),
            ),
            (
                "/repos/endaye/lmdj/releases/17/assets?per_page=100",
                "/repos/endaye/lmdj/releases/17/assets?per_page=100&page=2",
                lambda page: json.dumps([self._asset_json(6 + page, f"asset-{page}.zip")]).encode(),
                lambda client: client.list_release_assets("endaye/lmdj", 17),
            ),
            (
                "/repos/endaye/lmdj/actions/runs?head_sha=" + self.target + "&per_page=100",
                "/repos/endaye/lmdj/actions/runs?head_sha=" + self.target + "&per_page=100&page=2",
                lambda page: json.dumps({"total_count": 2, "workflow_runs": [self._run_json(page)]}).encode(),
                lambda client: client.list_runs_for_sha("endaye/lmdj", self.target),
            ),
        )
        for first, second, body, operation in cases:
            with self.subTest(first=first):
                pages = {
                    first: HttpResponse(200, {"Link": f'<https://api.github.com{second}>; rel="next"'}, body(1)),
                    second: HttpResponse(200, {"Link": f'<https://api.github.com{first}>; rel="next"'}, body(2)),
                }
                with self.assertRaisesRegex(GitHubApiError, "pagination"):
                    operation(GitHubClient(http_transport=lambda method, url, headers, data: pages[url]))

    def test_github_latest_release_projection_is_typed_and_404_is_absent(self) -> None:
        release = self._release_json(17)
        client = GitHubClient(http_transport=lambda *args: HttpResponse(
            200, {}, json.dumps(release).encode(),
        ))
        latest = client.get_latest_release("endaye/lmdj")
        assert latest is not None
        self.assertEqual(latest.id, 17)
        absent = GitHubClient(http_transport=lambda *args: HttpResponse(404, {}, b"{}"))
        self.assertIsNone(absent.get_latest_release("endaye/lmdj"))

    def test_github_release_and_asset_urls_are_bound_to_numeric_identities(self) -> None:
        release = self._release_json(17)
        release["upload_url"] = "https://uploads.github.com/repos/endaye/lmdj/releases/18/assets{?name,label}"
        client = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
            200, {}, json.dumps(release).encode(),
        ))
        with self.assertRaisesRegex(GitHubApiError, "projection"):
            client.get_release("endaye/lmdj", 17)

        release = self._release_json(17)
        release["url"] = "https://api.github.com/repos/endaye/lmdj/releases/18"
        client = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
            200, {}, json.dumps(release).encode(),
        ))
        with self.assertRaisesRegex(GitHubApiError, "projection"):
            client.get_release("endaye/lmdj", 17)

        bad_asset = self._asset_json(7, "asset.zip")
        bad_asset["url"] = "https://api.github.com/repos/endaye/lmdj/releases/assets/8"
        client = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
            200, {}, json.dumps([bad_asset]).encode(),
        ))
        with self.assertRaisesRegex(GitHubApiError, "projection"):
            client.list_release_assets("endaye/lmdj", 17)

    def test_github_projections_preserve_mutable_release_and_asset_metadata(self) -> None:
        release = self._release_json(17)
        release["assets"] = [self._asset_json(7, "asset.zip")]
        client = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
            200, {}, json.dumps(release).encode(),
        ))
        projected = client.get_release("endaye/lmdj", 17)
        assert projected is not None
        self.assertEqual(
            getattr(projected, "target_commitish", None), self.target,
        )
        self.assertEqual(len(projected.assets), 1)
        asset = projected.assets[0]
        self.assertEqual(getattr(asset, "label", "missing"), None)
        self.assertEqual(
            getattr(asset, "content_type", None), "application/octet-stream",
        )
        self.assertEqual(getattr(asset, "state", None), "uploaded")

    def test_asset_media_type_parameters_are_accepted_and_reduced(self) -> None:
        cases = (
            ("text/markdown; charset=utf-8", "text/markdown"),
            ("text/markdown;charset=utf-8", "text/markdown"),
            ("  application/zip  ", "application/zip"),
            ("application/octet-stream", "application/octet-stream"),
        )
        for declared, expected in cases:
            with self.subTest(content_type=declared):
                document = self._asset_json(7, "asset.zip")
                document["content_type"] = declared
                client = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
                    200, {}, json.dumps([document]).encode(),
                ))
                assets = client.list_release_assets("endaye/lmdj", 17)
                self.assertEqual(len(assets), 1)
                self.assertEqual(getattr(assets[0], "content_type", None), expected)

    def test_asset_media_types_without_one_type_and_subtype_fail_closed(self) -> None:
        for declared in (
            "text/", "/markdown", "no-slash", "text/markdown/extra",
            "text /markdown", "; charset=utf-8", "",
        ):
            with self.subTest(content_type=declared):
                document = self._asset_json(7, "asset.zip")
                document["content_type"] = declared
                client = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
                    200, {}, json.dumps([document]).encode(),
                ))
                with self.assertRaisesRegex(GitHubApiError, "projection"):
                    client.list_release_assets("endaye/lmdj", 17)

    def test_github_mutable_metadata_shapes_fail_closed(self) -> None:
        cases = (
            ("target_commitish", "", "release"),
            ("make_latest", 1, "release"),
            ("label", 7, "asset"),
            ("content_type", "", "asset"),
            ("state", 7, "asset"),
        )
        for field, value, subject in cases:
            with self.subTest(field=field):
                if subject == "release":
                    document = self._release_json(17)
                    document[field] = value
                    response = document
                    operation = lambda client: client.get_release("endaye/lmdj", 17)
                else:
                    document = self._asset_json(7, "asset.zip")
                    document[field] = value
                    response = [document]
                    operation = lambda client: client.list_release_assets("endaye/lmdj", 17)
                client = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
                    200, {}, json.dumps(response).encode(),
                ))
                with self.assertRaisesRegex(GitHubApiError, "projection"):
                    operation(client)

    def test_asset_pagination_cannot_switch_release_identity(self) -> None:
        first = "/repos/endaye/lmdj/releases/17/assets?per_page=100"
        response = HttpResponse(
            200,
            {"Link": '<https://api.github.com/repos/endaye/lmdj/releases/18/assets?per_page=100&page=2>; rel="next"'},
            b"[]",
        )
        client = GitHubClient(http_transport=lambda method, url, headers, body: response)
        with self.assertRaisesRegex(GitHubApiError, "pagination"):
            client.list_release_assets("endaye/lmdj", 17)

    def test_github_client_uses_numeric_ids_one_encoded_upload_name_and_secret_safe_errors(self) -> None:
        requests: list[tuple[str, str, dict[str, str], bytes | None]] = []

        def transport(method, url, headers, body):
            requests.append((method, url, dict(headers), body))
            if method == "POST":
                return HttpResponse(201, {}, json.dumps(self._asset_json(7, "a b.zip")).encode())
            raise RuntimeError("token ghp_DO_NOT_LEAK")

        client = GitHubClient(token="ghp_DO_NOT_LEAK", http_transport=transport)
        asset = client.upload_release_asset(
            "endaye/lmdj", 17,
            "https://uploads.github.com/repos/endaye/lmdj/releases/17/assets{?name,label}",
            "a b.zip", b"payload",
        )
        self.assertEqual(asset.id, 7)
        self.assertTrue(requests[0][1].endswith("?name=a%20b.zip"))
        self.assertEqual(requests[0][1].count("name="), 1)
        with self.assertRaises(GitHubApiError) as caught:
            client.get_release("endaye/lmdj", 17)
        self.assertNotIn("ghp_DO_NOT_LEAK", str(caught.exception))
        with self.assertRaisesRegex(GitHubApiError, "numeric"):
            client.get_release("endaye/lmdj", True)

    def test_branch_projection_uses_authenticated_rest_boundary(self) -> None:
        requests: list[tuple[str, str, dict[str, str]]] = []
        token = "ghp_BRANCH_TOKEN"

        def transport(method, url, headers, body):
            requests.append((method, url, dict(headers)))
            return HttpResponse(200, {}, json.dumps({
                "name": "main", "protected": True, "commit": {"sha": self.target},
            }).encode())

        branch = GitHubClient(token=token, http_transport=transport).get_branch(
            "endaye/lmdj", "main",
        )
        self.assertEqual(branch.commit_sha, self.target)
        self.assertEqual(requests, [(
            "GET", "/repos/endaye/lmdj/branches/main",
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "lmdj-release-pipeline",
                "Authorization": f"Bearer {token}",
            },
        )])

    def test_release_environment_projection_includes_exact_branch_policy(self) -> None:
        requests: list[str] = []

        def transport(method, url, headers, body):
            requests.append(url)
            if url == "/repos/endaye/lmdj/environments/release":
                return HttpResponse(200, {}, json.dumps({
                    "name": "release",
                    "protection_rules": [],
                    "prevent_self_review": None,
                    "deployment_branch_policy": {
                        "protected_branches": False,
                        "custom_branch_policies": True,
                    },
                }).encode())
            if url.endswith("/deployment-branch-policies/9"):
                return HttpResponse(200, {}, json.dumps({
                    "id": 9, "name": "main", "type": "branch",
                }).encode())
            return HttpResponse(200, {}, json.dumps({
                "total_count": 1,
                "branch_policies": [{"id": 9, "name": "main"}],
            }).encode())

        environment = GitHubClient(http_transport=transport).get_release_environment(
            "endaye/lmdj",
        )
        self.assertEqual(environment, GitHubEnvironment(
            "release", 0, None, False, True,
            (DeploymentBranchPolicy(9, "main", "branch"),),
        ))
        self.assertEqual(requests[-2:], [(
            "/repos/endaye/lmdj/environments/release/"
            "deployment-branch-policies?per_page=100"
        ), (
            "/repos/endaye/lmdj/environments/release/"
            "deployment-branch-policies/9"
        )])

    def test_github_publish_sets_all_policy_fields_without_if_match(self) -> None:
        requests: list[tuple[str, str, dict[str, str], bytes | None]] = []

        def transport(method, url, headers, body):
            requests.append((method, url, dict(headers), body))
            document = self._release_json(17)
            document["draft"] = False
            return HttpResponse(200, {"ETag": '"release-17-v2"'}, json.dumps(document).encode())

        result = GitHubClient(http_transport=transport).publish_release(
            "endaye/lmdj", 17, prerelease=True, make_latest=False,
        )
        self.assertFalse(result.draft)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0:2], (
            "PATCH", "/repos/endaye/lmdj/releases/17",
        ))
        self.assertNotIn("If-Match", requests[0][2])
        self.assertEqual(
            json.loads(requests[0][3]),
            {"draft": False, "prerelease": True, "make_latest": "false"},
        )
        with self.assertRaisesRegex(GitHubApiError, "numeric"):
            GitHubClient(http_transport=transport).publish_release(
                "endaye/lmdj", True, prerelease=True, make_latest=False,
            )
        self.assertEqual(len(requests), 1)

        def wrong_projection(method, url, headers, body):
            document = self._release_json(18)
            document["draft"] = False
            return HttpResponse(200, {}, json.dumps(document).encode())

        with self.assertRaisesRegex(GitHubApiError, "projection"):
            GitHubClient(http_transport=wrong_projection).publish_release(
                "endaye/lmdj", 17, prerelease=True, make_latest=False,
            )

    def test_release_get_accepts_weak_or_missing_etag_without_projecting_authority(self) -> None:
        document = self._release_json(17)
        for header in ({"ETag": '"release-17-v1"'}, {"etag": 'W/"weak"'}, {}):
            with self.subTest(header=header):
                client = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
                    200, header, json.dumps(document).encode(),
                ))
                release = client.get_release("endaye/lmdj", 17)
                assert release is not None
                self.assertFalse(hasattr(release, "validator"))

    def test_publish_transport_uncertainty_is_secret_safe(self) -> None:
        secret = "ghp_PUBLISH_DO_NOT_LEAK"
        uncertain = GitHubClient(
            token=secret,
            http_transport=lambda method, url, headers, body: (_ for _ in ()).throw(
                RuntimeError(secret)
            ),
        )
        with self.assertRaises(GitHubApiError) as caught:
            uncertain.publish_release(
                "endaye/lmdj", 17, prerelease=True, make_latest=False,
            )
        self.assertNotIn(secret, str(caught.exception))

    def test_asset_io_requires_exact_repository_release_and_asset_ownership(self) -> None:
        requests: list[str] = []
        client = GitHubClient(http_transport=lambda method, url, headers, body: (
            requests.append(url) or HttpResponse(200, {}, b"payload")
        ))
        with self.assertRaisesRegex(GitHubApiError, "upload URL"):
            client.upload_release_asset(
                "endaye/lmdj", 17,
                "https://uploads.github.com/repos/endaye/lmdj/releases/18/assets{?name,label}",
                "asset.zip", b"payload",
            )
        with self.assertRaisesRegex(GitHubApiError, "API URL"):
            client.download_asset(
                "endaye/lmdj", 17,
                GitHubAsset(
                    7, "asset.zip", 7,
                    "https://api.github.com/repos/other/repository/releases/assets/7",
                    "https://github.com/other/repository/releases/download/test/asset.zip",
                    release_id=17, label=None,
                    content_type="application/octet-stream", state="uploaded",
                ),
            )
        self.assertEqual(requests, [])
        with self.assertRaisesRegex(GitHubApiError, "Release ownership"):
            client.download_asset(
                "endaye/lmdj", 17,
                GitHubAsset(
                    7, "asset.zip", 7,
                    "https://api.github.com/repos/endaye/lmdj/releases/assets/7",
                    "https://github.com/endaye/lmdj/releases/download/test/asset.zip",
                    release_id=18, label=None,
                    content_type="application/octet-stream", state="uploaded",
                ),
            )
        self.assertEqual(requests, [])
        payload = client.download_asset(
            "endaye/lmdj", 17,
            GitHubAsset(
                7, "asset.zip", 7,
                "https://api.github.com/repos/endaye/lmdj/releases/assets/7",
                "https://github.com/endaye/lmdj/releases/download/test/asset.zip",
                release_id=17, label=None,
                content_type="application/octet-stream", state="uploaded",
            ),
        )
        self.assertEqual(payload, b"payload")
        self.assertEqual(requests, [
            "https://api.github.com/repos/endaye/lmdj/releases/assets/7",
        ])

    def test_asset_download_strips_authorization_on_trusted_redirect(self) -> None:
        requests: list[tuple[str, dict[str, str]]] = []

        def transport(method, url, headers, body):
            requests.append((url, dict(headers)))
            if len(requests) == 1:
                return HttpResponse(302, {
                    "Location": "https://release-assets.githubusercontent.com/github-production-release-asset/fixture",
                }, b"")
            return HttpResponse(200, {"Content-Type": "application/octet-stream"}, b"payload")

        asset = GitHubAsset(
            7, "asset.zip", 7,
            "https://api.github.com/repos/endaye/lmdj/releases/assets/7",
            "https://github.com/endaye/lmdj/releases/download/test/asset.zip",
            17, None, "application/octet-stream", "uploaded",
        )
        payload = GitHubClient(token="ghp_ASSET_TOKEN", http_transport=transport).download_asset(
            "endaye/lmdj", 17, asset,
        )
        self.assertEqual(payload, b"payload")
        self.assertIn("Authorization", requests[0][1])
        self.assertNotIn("Authorization", requests[1][1])

    def test_asset_download_rejects_untrusted_redirect_without_following(self) -> None:
        requests: list[str] = []

        def transport(method, url, headers, body):
            requests.append(url)
            return HttpResponse(302, {"Location": "https://attacker.invalid/stolen"}, b"")

        asset = GitHubAsset(
            7, "asset.zip", 7,
            "https://api.github.com/repos/endaye/lmdj/releases/assets/7",
            "https://github.com/endaye/lmdj/releases/download/test/asset.zip",
            17, None, "application/octet-stream", "uploaded",
        )
        with self.assertRaisesRegex(GitHubApiError, "redirect"):
            GitHubClient(token="ghp_ASSET_TOKEN", http_transport=transport).download_asset(
                "endaye/lmdj", 17, asset,
            )
        self.assertEqual(len(requests), 1)

    def test_cli_exposes_separate_transition_and_rehearsal_boundaries(self) -> None:
        root = ["--repo-root", str(self.root)]
        self.assertEqual(cli.parse_arguments(root + ["push-tag", self.tag]).command, "push-tag")
        self.assertEqual(cli.parse_arguments(root + ["create-draft", self.tag]).command, "create-draft")
        verified = cli.parse_arguments(root + ["verify-draft", self.tag, "17", "a" * 64])
        self.assertEqual((verified.release_id, verified.plan_sha256), (17, "a" * 64))
        published = cli.parse_arguments(root + ["publish-draft", self.tag, "17", "a" * 64])
        self.assertEqual((published.release_id, published.plan_sha256), (17, "a" * 64))
        rehearsed = cli.parse_arguments(root + ["rehearsal", "cleanup", "release-rehearsal/20260813T091011Z-012345abcdef"])
        self.assertEqual((rehearsed.command, rehearsed.rehearsal_command), ("rehearsal", "cleanup"))

    @staticmethod
    def _asset_json(identifier: int, name: str) -> dict[str, object]:
        return {
            "id": identifier, "name": name, "label": None,
            "content_type": "application/octet-stream", "state": "uploaded",
            "size": 7,
            "url": f"https://api.github.com/repos/endaye/lmdj/releases/assets/{identifier}",
            "browser_download_url": f"https://github.com/endaye/lmdj/releases/download/test/{name}",
        }

    def _run_json(self, identifier: int) -> dict[str, object]:
        return {
            "id": identifier, "event": "push", "head_sha": self.target,
            "head_branch": "main", "name": "Core CI / main",
            "workflow_id": 313388832, "path": ".github/workflows/ci.yml",
            "status": "completed",
            "conclusion": "success",
        }

    @staticmethod
    def _workflow_url() -> str:
        return "/repos/endaye/lmdj/actions/workflows/313388832"

    @staticmethod
    def _workflow_json() -> dict[str, object]:
        return {
            "id": 313388832, "name": "Core CI",
            "path": ".github/workflows/ci.yml", "state": "active",
        }

    def _release_json(self, identifier: int) -> dict[str, object]:
        return {
            "id": identifier, "tag_name": self.tag, "name": "LMDJ 1.0.21.0",
            "target_commitish": self.target, "body": "body",
            "draft": True, "prerelease": True,
            "url": f"https://api.github.com/repos/endaye/lmdj/releases/{identifier}",
            "html_url": "https://github.com/endaye/lmdj/releases/tag/lmdj-v1.0.21.0",
            "upload_url": f"https://uploads.github.com/repos/endaye/lmdj/releases/{identifier}/assets{{?name,label}}",
            "assets": [],
        }


if __name__ == "__main__":
    unittest.main()
