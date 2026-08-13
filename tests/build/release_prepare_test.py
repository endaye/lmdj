#!/usr/bin/env python3
"""Contract tests for local-only signed release preparation."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
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
    read_product_snapshot_proof,
)
from tools.release.profiles import (  # noqa: E402
    AssetBuild,
    ProfileBuild,
    ProfileRuntime,
    _create_dist_zip,
    _stage_and_sign,
    _verify_checksum,
    build_profile,
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
        self.runs = [RunProjection(run_id, "push", target, "main", "Core CI", "completed", "success")]
        self.remote_mutations: list[str] = []
        self.run_queries = 0

    def get_branch(self, repository: str, branch: str) -> BranchProjection:
        return self.branch

    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]:
        self.run_queries += 1
        return self.runs


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
        with self.assertRaisesRegex(ValueError, "unknown release profile"):
            build_profile("source-and-binary", self.root, self.root / "invalid", None)

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

    def test_cli_normalizes_usage_and_verification_failures(self) -> None:
        self.assertEqual(cli.main(["prepare"]), 64)
        self.assertEqual(cli.main(["--repo-root", str(self.root), "prepare", "bad-tag"]), 2)

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


if __name__ == "__main__":
    unittest.main()
