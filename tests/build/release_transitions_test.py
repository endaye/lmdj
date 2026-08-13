#!/usr/bin/env python3
"""Contract tests for exact tag and GitHub Draft transitions."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.commands import CommandResult  # noqa: E402
from tools.release.git_repository import GitRepository  # noqa: E402
from tools.release.github_api import (  # noqa: E402
    BranchProjection,
    GitHubApiError,
    GitHubAsset,
    GitHubClient,
    GitHubRelease,
    GitHubReleaseValidator,
    HttpResponse,
    RunProjection,
)
from tools.release.model import canonical_json, load_ledger_document, load_policy  # noqa: E402
from tools.release.prepare import LocalTag, PrepareContext, ProductProof  # noqa: E402
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
        self.main_contains_target = True

    def fetch_authority(self, repository: str, branch: str) -> None:
        self.fetches += 1

    def main_revision(self) -> str:
        return self.target

    def is_main_ancestor(self, target: str) -> bool:
        return self.main_contains_target and target == self.target

    def is_revision_ancestor(self, ancestor: str, descendant: str) -> bool:
        return descendant == self.target

    def remote_tag_state(self, tag: str) -> LocalTag | None:
        return self.remote

    def local_tag_state(self, tag: str) -> LocalTag | None:
        return self.local

    def push_tag(self, tag: str) -> None:
        self.pushes += 1
        if self.push_raises_without_write:
            raise RuntimeError("network failure before write")
        self.remote = self.local
        if self.push_raises_after_write:
            raise RuntimeError("network failure after write")

    @contextmanager
    def detached_worktree(self, target: str):
        with tempfile.TemporaryDirectory(prefix="release-transition-tree-") as directory:
            yield Path(directory)


class FakeGitHub:
    def __init__(self, target: str) -> None:
        self.target = target
        self.branch = BranchProjection("main", True, target)
        self.runs = [RunProjection(123, "push", target, "main", "Core CI", "completed", "success")]
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
        self.conditional_patch_calls: list[GitHubReleaseValidator] = []
        self.release_version = 1
        self.validator_mode = "strong"
        self.mutate_before_conditional_patch = False
        self.next_asset_id = 40

    def _release_projection(self) -> GitHubRelease | None:
        if self.release is None:
            return None
        validator = None
        if self.validator_mode == "strong":
            validator = GitHubReleaseValidator(
                self.release.id, f'"release-{self.release.id}-v{self.release_version}"',
            )
        elif self.validator_mode == "weak":
            validator = GitHubReleaseValidator(
                self.release.id, f'W/"release-{self.release.id}-v{self.release_version}"',
            )
        return GitHubRelease(**{**self.release.__dict__, "validator": validator})

    def _touch_release(self) -> None:
        self.release_version += 1

    def get_branch(self, repository: str, branch: str) -> BranchProjection:
        return self.branch

    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]:
        return self.runs

    def get_release_by_tag(self, repository: str, tag: str) -> GitHubRelease | None:
        projected = self._release_projection()
        return projected if projected is not None and projected.tag_name == tag else None

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

    def create_draft_release(self, repository: str, *, tag: str, name: str, body: str,
                             prerelease: bool, make_latest: bool) -> GitHubRelease:
        self.create_calls += 1
        self.release = GitHubRelease(
            17, tag, name, body, True, prerelease, make_latest,
            "https://github.com/endaye/lmdj/releases/tag/test",
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
        self, repository: str, release_id: int, validator: GitHubReleaseValidator,
    ) -> GitHubRelease:
        if repository != "endaye/lmdj" or self.release is None or self.release.id != release_id:
            raise RuntimeError("wrong release ownership")
        if (
            not isinstance(validator, GitHubReleaseValidator)
            or validator.release_id != release_id
            or not validator.etag.startswith('"') or not validator.etag.endswith('"')
        ):
            raise GitHubApiError("GitHub Release strong validator is unavailable")
        if self.mutate_before_conditional_patch:
            self.release = GitHubRelease(**{
                **self.release.__dict__, "name": "concurrent change",
            })
            self._touch_release()
        self.conditional_patch_calls.append(validator)
        expected = f'"release-{release_id}-v{self.release_version}"'
        if validator.etag != expected:
            raise GitHubApiError("GitHub Release publication precondition failed")
        self.patch_calls.append((release_id, {"draft": False}))
        self.release = GitHubRelease(**{**self.release.__dict__, "draft": False})
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
        self.policy = load_policy(ROOT / "tools/release/policy.json")
        self.ledger = load_ledger_document({
            "schema": "lmdj.release-intents.v1",
            "entries": [{
                "tag": self.tag, "kind": "product", "identity": "1.0.21.0",
                "target_revision": self.target, "channel": "canary",
                "disposition": "releasable", "profile": "web-runtime-host",
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
            "identity": "1.0.21.0", "channel": "canary", "profile": "web-runtime-host",
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

    def test_git_repository_push_uses_one_exact_refspec_without_force_or_tags(self) -> None:
        runner = RecordingRunner()
        repository = GitRepository(self.root, runner=runner)
        repository.push_tag("module/core-cli/v1.0.2")
        self.assertEqual(runner.commands, [[
            "git", "push", "origin",
            "refs/tags/module/core-cli/v1.0.2:refs/tags/module/core-cli/v1.0.2",
        ]])
        self.assertNotIn("--tags", runner.commands[0])
        self.assertNotIn("--force", runner.commands[0])

    def test_fetch_authority_prunes_deleted_tags_from_the_scratch_namespace(self) -> None:
        runner = RecordingRunner()
        GitRepository(self.root, runner=runner).fetch_authority("endaye/lmdj", "main")
        self.assertEqual(runner.commands, [[
            "git", "fetch", "--no-tags", "--prune", "https://github.com/endaye/lmdj.git",
            "+refs/heads/main:refs/lmdj-release/origin-main",
            "+refs/tags/*:refs/lmdj-release/tags/*",
        ]])

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
        self.assertEqual(self.github.patch_calls, [(created.release_id, {"draft": False})])
        self.assertEqual(result.status, "published")
        self.assertEqual(result.assets, original.assets)
        assert self.github.release is not None
        self.assertEqual(
            {**self.github.release.__dict__, "draft": True},
            original.__dict__,
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

    def test_publish_condition_rejects_mutation_after_final_verification(self) -> None:
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
        self.assertEqual(len(self.github.conditional_patch_calls), 1)
        self.assertEqual(self.github.patch_calls, [])
        assert self.github.release is not None
        self.assertTrue(self.github.release.draft)

    def test_publish_refuses_missing_or_weak_release_validator(self) -> None:
        for mode in ("missing", "weak"):
            with self.subTest(mode=mode):
                self.github = FakeGitHub(self.target)
                created = self._push_and_create()
                assert created.release_id is not None
                self.github.validator_mode = mode
                with self.assertRaisesRegex(
                    TransitionError, "strong validator|could not be reconciled",
                ):
                    publish_draft(
                        self.tag, created.release_id, created.plan_sha256,
                        self.context(), actions_environment={
                            "GITHUB_ACTIONS": "true",
                            "GITHUB_EVENT_NAME": "workflow_dispatch",
                        },
                    )
                self.assertEqual(self.github.conditional_patch_calls, [])
                self.assertEqual(self.github.patch_calls, [])

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

    def test_github_publish_patches_only_draft_by_numeric_id(self) -> None:
        requests: list[tuple[str, str, dict[str, str], bytes | None]] = []

        def transport(method, url, headers, body):
            requests.append((method, url, dict(headers), body))
            document = self._release_json(17)
            document["draft"] = False
            return HttpResponse(200, {"ETag": '"release-17-v2"'}, json.dumps(document).encode())

        validator = GitHubReleaseValidator(17, '"release-17-v1"')
        result = GitHubClient(http_transport=transport).publish_release(
            "endaye/lmdj", 17, validator,
        )
        self.assertFalse(result.draft)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0:2], (
            "PATCH", "/repos/endaye/lmdj/releases/17",
        ))
        self.assertEqual(requests[0][2].get("If-Match"), '"release-17-v1"')
        self.assertEqual(requests[0][3], b'{"draft":false}')
        with self.assertRaisesRegex(GitHubApiError, "numeric"):
            GitHubClient(http_transport=transport).publish_release(
                "endaye/lmdj", True, validator,
            )
        self.assertEqual(len(requests), 1)

        with self.assertRaisesRegex(GitHubApiError, "ownership"):
            GitHubClient(http_transport=transport).publish_release(
                "endaye/lmdj", 17, GitHubReleaseValidator(18, '"release-18-v1"'),
            )
        with self.assertRaisesRegex(GitHubApiError, "strong"):
            GitHubClient(http_transport=transport).publish_release(
                "endaye/lmdj", 17, GitHubReleaseValidator(17, 'W/"weak"'),
            )
        self.assertEqual(len(requests), 1)

        def wrong_projection(method, url, headers, body):
            document = self._release_json(18)
            document["draft"] = False
            return HttpResponse(200, {}, json.dumps(document).encode())

        with self.assertRaisesRegex(GitHubApiError, "projection"):
            GitHubClient(http_transport=wrong_projection).publish_release(
                "endaye/lmdj", 17, validator,
            )

    def test_release_get_retains_only_a_strong_exact_id_validator(self) -> None:
        document = self._release_json(17)
        for header, expected in (
            ({"ETag": '"release-17-v1"'}, GitHubReleaseValidator(17, '"release-17-v1"')),
            ({"etag": 'W/"weak"'}, None),
            ({}, None),
        ):
            with self.subTest(header=header):
                client = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
                    200, header, json.dumps(document).encode(),
                ))
                release = client.get_release("endaye/lmdj", 17)
                assert release is not None
                self.assertEqual(release.validator, expected)

    def test_conditional_publish_reports_precondition_and_redacts_uncertainty(self) -> None:
        validator = GitHubReleaseValidator(17, '"release-17-v1"')
        rejected = GitHubClient(http_transport=lambda method, url, headers, body: HttpResponse(
            412, {}, b'{"message":"changed"}',
        ))
        with self.assertRaisesRegex(GitHubApiError, "precondition"):
            rejected.publish_release("endaye/lmdj", 17, validator)

        secret = "ghp_PUBLISH_DO_NOT_LEAK"
        uncertain = GitHubClient(
            token=secret,
            http_transport=lambda method, url, headers, body: (_ for _ in ()).throw(
                RuntimeError(secret)
            ),
        )
        with self.assertRaises(GitHubApiError) as caught:
            uncertain.publish_release("endaye/lmdj", 17, validator)
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
            "head_branch": "main", "name": "Core CI", "status": "completed",
            "conclusion": "success",
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
