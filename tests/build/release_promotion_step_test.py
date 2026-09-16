#!/usr/bin/env python3
"""The promotion step's spec, PR document and commit binding are exact."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.model import canonical_sha256  # noqa: E402
from tools.release.promotion_step import (  # noqa: E402
    PromotionCommit,
    PromotionStepError,
    pr_document,
    promotion_operation_id,
    validate_spec,
)

REQUEST = "4" * 64
BASE = "5" * 40
TARGET = "6" * 40


def spec(**changes):
    document = {"operation_id": promotion_operation_id(REQUEST), "request_sha256": REQUEST,
                "repository_id": 12, "actor_id": 34, "base_revision": BASE,
                "head_sha": "7" * 40, "tree_sha": "8" * 40, "tag": "lmdj-v1.0.57.0",
                "target_revision": TARGET, "to_channel": "dev", "from_channel": "canary",
                "deployment_runs_sha256": canonical_sha256({"runs": [
                    {"host": "runtime", "run_id": 111, "evidence_sha256": "a" * 64},
                    {"host": "creator", "run_id": 222, "evidence_sha256": "b" * 64}]}),
                "attestation_sha256": canonical_sha256({"attestation": "verified"})}
    document.update(changes)
    return document


class SpecTest(unittest.TestCase):
    def test_spec_is_closed_and_pr_document_is_bound(self):
        validate_spec(spec())
        document = pr_document(spec())
        self.assertEqual(document["head"],
                         "docs/release-witness-" + promotion_operation_id(REQUEST))
        self.assertIn("dev promotion", document["title"])
        with self.assertRaises(PromotionStepError):
            validate_spec(spec(operation_id="0" * 64))
        with self.assertRaises(PromotionStepError):
            validate_spec(dict(spec(), extra=1))
        with self.assertRaises(PromotionStepError):
            validate_spec(spec(from_channel="dev", to_channel="dev"))


class CommitTest(unittest.TestCase):
    def setUp(self):
        self.container = tempfile.TemporaryDirectory()
        self.addCleanup(self.container.cleanup)
        base = Path(self.container.name).resolve()
        self.repository = base / "repo"
        self.repository.mkdir()
        (root := self.repository / "docs/release-evidence").mkdir(parents=True)
        (self.repository / "tools/release").mkdir(parents=True)
        import shutil
        shutil.copy2(ROOT / "tools/release/policy.json",
                     self.repository / "tools/release/policy.json")
        entries_line = ('    {"tag":"lmdj-v1.0.57.0","kind":"product",'
                        '"identity":"1.0.57.0","target_revision":"' + TARGET +
                        '","channel":"canary","disposition":"published",'
                        '"profile":"web-hosts","evidence_paths":'
                        '["docs/release-evidence/intent.md"]}')
        (root / "release-intents.json").write_text(
            '{\n  "schema": "lmdj.release-intents.v1",\n  "entries": [\n'
            + entries_line +
            '\n  ],\n  "historical_exceptions": []\n}\n')
        git = lambda *a: subprocess.run(["git", "-c", "core.hooksPath=/dev/null",
                                         "-C", str(self.repository), *a],
                                        check=True, capture_output=True)
        git("init", "-q", "-b", "main")
        git("config", "user.name", "Seeder")
        git("config", "user.email", "seed@example.invalid")
        git("add", "-A")
        git("commit", "-q", "-m", "seed")
        self.base = git("rev-parse", "HEAD").stdout.decode().strip()
        self.worktree = base / "promotion-worktree"

    def test_commit_records_the_promotion_and_is_idempotent(self):
        plan = type("P", (), {"tag": "lmdj-v1.0.57.0", "identity": "1.0.57.0",
                              "target_revision": TARGET, "profile": "web-hosts",
                              "from_channel": "canary", "to_channel": "dev",
                              "promoted_at": "2026-09-15T00:00:00Z",
                              "attestation": "verified", "deployment_runs": (
            type("R", (), {"host": "runtime", "run_id": 111,
                           "evidence_sha256": "a" * 64})(),
            type("R", (), {"host": "creator", "run_id": 222,
                           "evidence_sha256": "b" * 64})()),
                              "evidence_paths": ("docs/release-evidence/"
                                                 "lmdj-v1.0.57.0-dev-promotion.md",),
                              "evidence_document":
                              "docs/release-evidence/lmdj-v1.0.57.0-dev-promotion.md"})()
        commit = PromotionCommit(self.worktree, self.repository,
                                 spec=spec(base_revision=self.base),
                                 plan=plan, main_tip=lambda: self.base,
                                 author_name="Fixture",
                                 author_email="fixture@example.invalid")
        head, tree = commit.commit(before_write=lambda: None)
        self.assertNotEqual(head, self.base)
        ledger = json.loads(subprocess.run(
            ["git", "-C", str(self.worktree), "show", f"{head}:docs/release-evidence/release-intents.json"],
            capture_output=True).stdout.decode())
        row = next(row for row in ledger["entries"] if row["tag"] == "lmdj-v1.0.57.0")
        self.assertEqual(row["promotions"][0]["channel"], "dev")
        self.assertTrue((self.worktree / "docs/release-evidence/"
                         "lmdj-v1.0.57.0-dev-promotion.md").exists())
        # Idempotent resume returns the same commit without re-applying.
        resumed = PromotionCommit(self.worktree, self.repository,
                                  spec=spec(base_revision=self.base),
                                  plan=plan, main_tip=lambda: self.base,
                                  author_name="Fixture",
                                  author_email="fixture@example.invalid")
        self.assertEqual(resumed.completed_head(), head)
        resumed_head, resumed_tree = resumed.commit(before_write=lambda: None)
        self.assertEqual((head, tree), (resumed_head, resumed_tree))


    def test_stale_base_revision_is_refused_before_any_write(self):
        plan = type("P", (), {"tag": "lmdj-v1.0.57.0", "identity": "1.0.57.0",
                              "target_revision": TARGET, "profile": "web-hosts",
                              "from_channel": "canary", "to_channel": "dev",
                              "promoted_at": "2026-09-15T00:00:00Z",
                              "attestation": "verified", "deployment_runs": (
            type("R", (), {"host": "runtime", "run_id": 111,
                           "evidence_sha256": "a" * 64})(),
            type("R", (), {"host": "creator", "run_id": 222,
                           "evidence_sha256": "b" * 64})()),
                              "evidence_paths": ("docs/release-evidence/"
                                                 "lmdj-v1.0.57.0-dev-promotion.md",),
                              "evidence_document":
                              "docs/release-evidence/lmdj-v1.0.57.0-dev-promotion.md"})()
        stale = PromotionCommit(self.worktree, self.repository,
                                spec=spec(base_revision=self.base),
                                plan=plan, main_tip=lambda: "f" * 40,
                                author_name="Fixture",
                                author_email="fixture@example.invalid")
        with self.assertRaises(PromotionStepError):
            stale.commit(before_write=lambda: None)
        self.assertFalse(self.worktree.exists(), "no worktree may be created")


if __name__ == "__main__":
    unittest.main()
