#!/usr/bin/env python3
"""Contract tests for local-only signed release preparation."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.github_api import BranchProjection, RunProjection  # noqa: E402
from tools.release.model import (  # noqa: E402
    Disposition,
    HistoricalException,
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
)
from tools.release.profiles import AssetBuild, ProfileBuild, build_profile  # noqa: E402
from tools.release.profiles import _create_dist_zip  # noqa: E402


class FakeGit:
    def __init__(self, target: str, signer: str) -> None:
        self.target = target
        self.signer = signer
        self.main_contains_target = True
        self.remote_tag: LocalTag | None = None
        self.local_tag: LocalTag | None = None
        self.calls: list[str] = []
        self.remote_mutations: list[str] = []

    def fetch_authority(self, branch: str) -> None:
        self.calls.append(f"fetch:{branch}")

    def is_main_ancestor(self, target: str) -> bool:
        self.calls.append(f"ancestor:{target}")
        return self.main_contains_target and target == self.target

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


class FakeGitHub:
    def __init__(self, target: str, run_id: int) -> None:
        self.branch = BranchProjection("main", True, target)
        self.runs = [RunProjection(run_id, "push", target, "completed", "success")]
        self.remote_mutations: list[str] = []

    def get_branch(self, repository: str, branch: str) -> BranchProjection:
        return self.branch

    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]:
        return self.runs


class ReleasePrepareTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-release-prepare-")
        self.root = Path(self.temporary.name)
        self.target_sha = "a" * 40
        self.tag = "lmdj-v1.0.21.0"
        self.policy = load_policy(ROOT / "tools/release/policy.json")
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
        output.mkdir(parents=True, exist_ok=True)
        assets = []
        for name, payload in (
            ("lmdj-web-runtime-host-1.1.2-product-1.0.21.0.zip", b"zip"),
            ("lmdj-web-runtime-host-1.1.2-product-1.0.21.0.zip.sha256", b"checksum"),
            ("lmdj-web-runtime-host-1.1.2-product-1.0.21.0.zip.sha256.asc", b"signature"),
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
        )

    def context(self) -> PrepareContext:
        return PrepareContext(
            repo_root=self.root,
            policy=self.policy,
            ledger=self.ledger,
            git=self.git,
            github=self.github,
            profile_builder=self.profile_builder,
            proof_reader=self.proof_reader,
            tag_signer_fingerprint=self.policy.product_fingerprint,
            checksum_signer_fingerprint=self.policy.checksum_fingerprint,
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

    def test_prepare_rejects_wrong_sha_and_non_main_target(self) -> None:
        self.github.runs[0] = RunProjection(123, "push", "b" * 40, "completed", "success")
        with self.assertRaisesRegex(PrepareError, "successful"):
            prepare(self.tag, self.context())
        self.github.runs[0] = RunProjection(123, "push", self.target_sha, "completed", "success")
        self.git.main_contains_target = False
        with self.assertRaisesRegex(PrepareError, "main ancestry"):
            prepare(self.tag, self.context())
        self.assertEqual(self.git.local_tag, None)

    def test_prepare_rejects_red_ci_and_branch_proof(self) -> None:
        self.github.runs[0] = RunProjection(123, "push", self.target_sha, "completed", "failure")
        with self.assertRaisesRegex(PrepareError, "successful"):
            prepare(self.tag, self.context())
        self.github.runs[0] = RunProjection(123, "push", self.target_sha, "completed", "success")
        self.proof_reader = lambda worktree, intent: ProductProof("feature/release", self.target_sha, "1.0.21.0", "1.0.21.0")
        with self.assertRaisesRegex(PrepareError, "merged-main Proof"):
            prepare(self.tag, self.context())

    def test_prepare_rejects_snapshot_drift(self) -> None:
        self.proof_reader = lambda worktree, intent: ProductProof("main", self.target_sha, "1.0.21.0", "1.0.20.0")
        with self.assertRaisesRegex(PrepareError, "snapshot"):
            prepare(self.tag, self.context())

    def test_prepare_rejects_forbidden_disposition_and_historical_exception(self) -> None:
        self.ledger = self.ledger_fixture("allocated")
        with self.assertRaisesRegex(PrepareError, "releasable"):
            prepare(self.tag, self.context())
        self.ledger = self.ledger_fixture()
        self.ledger = ReleaseLedger(
            self.ledger.entries,
            (HistoricalException(
                self.tag, self.target_sha, "2026-08-12T23:59:59Z",
                "pre-pipeline-ci-evidence", "audit only",
                ("docs/quality/example-proof.md",),
            ),),
        )
        with self.assertRaisesRegex(PrepareError, "historical exception"):
            prepare(self.tag, self.context())

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
        with self.assertRaisesRegex(ValueError, "unknown release profile"):
            build_profile("source-and-binary", self.root, self.root / "invalid", None)

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
        archive = self.root / "host.zip"
        _create_dist_zip(dist, archive)
        with zipfile.ZipFile(archive) as opened:
            self.assertEqual(
                opened.namelist(),
                ["dist/assets/runtime.mjs", "dist/index.html"],
            )


if __name__ == "__main__":
    unittest.main()
