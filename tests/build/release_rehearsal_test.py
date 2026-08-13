#!/usr/bin/env python3
"""Contract tests for the destructive but exact-ID guarded rehearsal helper."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.github_api import GitHubAsset, GitHubRelease  # noqa: E402
from tools.release.rehearsal import (  # noqa: E402
    REHEARSAL_ASSET,
    RehearsalContext,
    RehearsalError,
    RehearsalState,
    cleanup_rehearsal,
    create_rehearsal_draft,
    rehearsal_marker,
    validate_rehearsal_tag,
)


class FakeRehearsalGit:
    def __init__(self, state: RehearsalState) -> None:
        self.object = state.tag_object
        self.deleted: list[str] = []

    def remote_tag_object(self, tag: str) -> str | None:
        return self.object

    def delete_remote_tag(self, tag: str, expected_object: str) -> None:
        if self.object != expected_object:
            raise RuntimeError("object changed")
        self.deleted.append(tag)
        self.object = None


class FakeRehearsalGitHub:
    def __init__(self, state: RehearsalState) -> None:
        self.payload = REHEARSAL_ASSET
        self.asset = GitHubAsset(
            8, state.asset_name, len(self.payload), "https://api.github.com/assets/8",
            "https://github.com/asset", 9, None,
            "application/octet-stream", "uploaded",
        )
        self.release = GitHubRelease(
            state.release_id, state.tag, f"LMDJ release rehearsal {state.tag}",
            rehearsal_marker(state), True, True, False, "https://github.com/rehearsal",
            "https://uploads.github.com/repos/endaye/lmdj/releases/9/assets{?name,label}", (self.asset,),
            state.tag_object,
        )
        self.deleted: list[int] = []
        self.uploads = 0

    def get_release(self, repository: str, release_id: int):
        return self.release if self.release is not None and self.release.id == release_id else None

    def get_release_by_tag(self, repository: str, tag: str):
        return self.release if self.release is not None and self.release.tag_name == tag else None

    def list_release_assets(self, repository: str, release_id: int):
        return list(self.release.assets if self.release else ())

    def download_asset(self, repository: str, release_id: int, asset: GitHubAsset) -> bytes:
        if repository != "endaye/lmdj" or asset.release_id != release_id:
            raise RuntimeError("wrong repository ownership")
        return self.payload

    def create_draft_release(self, repository: str, *, tag: str, name: str, body: str,
                             prerelease: bool, make_latest: bool) -> GitHubRelease:
        self.release = GitHubRelease(
            9, tag, name, body, True, prerelease, make_latest,
            "https://github.com/rehearsal",
            "https://uploads.github.com/repos/endaye/lmdj/releases/9/assets{?name,label}", (),
            self.release.target_commitish if self.release is not None else "main",
        )
        return self.release

    def upload_release_asset(self, repository: str, release_id: int, upload_url: str,
                             name: str, payload: bytes) -> GitHubAsset:
        if self.release is None or self.release.id != release_id:
            raise RuntimeError("wrong release ownership")
        self.uploads += 1
        self.payload = payload
        self.asset = GitHubAsset(
            8, name, len(payload), "https://api.github.com/assets/8",
            "https://github.com/asset", release_id, None,
            "application/octet-stream", "uploaded",
        )
        self.release = GitHubRelease(**{**self.release.__dict__, "assets": (self.asset,)})
        return self.asset

    def delete_release(self, repository: str, release_id: int) -> None:
        self.deleted.append(release_id)
        self.release = None


class ReleaseRehearsalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-rehearsal-")
        self.root = Path(self.temporary.name)
        self.tag = "release-rehearsal/20260813T091011Z-012345abcdef"
        self.state = RehearsalState(
            schema="lmdj.release-rehearsal-state.v1", tag=self.tag, tag_object="a" * 40,
            signer_fingerprint="D" * 40, release_id=9,
            asset_name="lmdj-release-rehearsal.txt", asset_sha256=hashlib.sha256(REHEARSAL_ASSET).hexdigest(),
        )
        self.git = FakeRehearsalGit(self.state)
        self.github = FakeRehearsalGitHub(self.state)
        self.context = RehearsalContext(self.root, "endaye/lmdj", self.git, self.github)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_exact_rehearsal_syntax_and_formal_tags_are_refused(self) -> None:
        self.assertEqual(validate_rehearsal_tag(self.tag), self.tag)
        for tag in (
            "release-rehearsal/20260813T091011Z-012345abcdef0",
            "release-rehearsal/20260813-012345abcdef",
            "release-rehearsal/20260813T091011Z-012345ABCDEf",
            "lmdj-v1.0.21.0", "module/core-cli/v1.0.3",
        ):
            with self.subTest(tag=tag), self.assertRaises(RehearsalError):
                validate_rehearsal_tag(tag)

    def test_rehearsal_requires_a_non_product_test_signer(self) -> None:
        with self.assertRaisesRegex(RehearsalError, "test signer"):
            create_rehearsal_draft(self.state, self.context, product_fingerprints={"D" * 40})

    def test_rehearsal_creates_and_reconciles_one_marked_draft_asset(self) -> None:
        self.github.release = None
        state = RehearsalState(**{**self.state.__dict__, "release_id": None})
        created = create_rehearsal_draft(state, self.context)
        self.assertEqual(created.release_id, 9)
        self.assertEqual(self.github.uploads, 1)
        self.assertEqual(self.github.release.body, rehearsal_marker(created))
        reconciled = create_rehearsal_draft(created, self.context)
        self.assertEqual(reconciled, created)
        self.assertEqual(self.github.uploads, 1)

    def test_cleanup_deletes_exact_draft_then_exact_tag_and_proves_absence(self) -> None:
        cleanup_rehearsal(self.state, self.context)
        self.assertEqual(self.github.deleted, [9])
        self.assertEqual(self.git.deleted, [self.tag])
        self.assertIsNone(self.github.get_release("endaye/lmdj", 9))
        self.assertIsNone(self.git.remote_tag_object(self.tag))

    def test_cleanup_rejects_published_wrong_id_object_marker_or_asset(self) -> None:
        for change in ("published", "id", "object", "marker", "asset"):
            with self.subTest(change=change):
                git = FakeRehearsalGit(self.state)
                github = FakeRehearsalGitHub(self.state)
                context = RehearsalContext(self.root, "endaye/lmdj", git, github)
                if change == "published":
                    github.release = GitHubRelease(**{**github.release.__dict__, "draft": False})
                elif change == "id":
                    github.release = GitHubRelease(**{**github.release.__dict__, "id": 10})
                elif change == "object":
                    git.object = "b" * 40
                elif change == "marker":
                    github.release = GitHubRelease(**{**github.release.__dict__, "body": "unknown"})
                else:
                    github.payload = b"changed"
                with self.assertRaises(RehearsalError):
                    cleanup_rehearsal(self.state, context)
                self.assertEqual(github.deleted, [])
                self.assertEqual(git.deleted, [])


if __name__ == "__main__":
    unittest.main()
