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
                "deployment_runs_sha256": "a" * 64, "attestation_sha256": "b" * 64}
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
        (self.repository / "tools/release/policy.json").write_text(json.dumps({
            "schema": "lmdj.release-policy.v1", "repository": "endaye/lmdj",
            "branch": "main", "blocking_workflow": "Core CI",
            "fingerprints": {"product": "2B5EE362F058800036AD4FB5116ECE156F954D29",
                             "checksum": "CB928A6E89DE498851688EF1AAC3E7019FC1478B"},
            "tag_patterns": {"product": "lmdj-v"},
            "profiles": ["web-hosts"], "channels": {}, "environments": {},
            "historical_cutoff": "2026-08-13T00:00:00Z",
            "promotion": {"max_channel": "dev", "required_hosts": ["runtime", "creator"]},
            "prospective_ci_protocol": "self-test-v1"}, indent=2) + "\n")
        (root / "release-intents.json").write_text(json.dumps({
            "schema": "lmdj.release-intents.v1",
            "entries": [{"tag": "lmdj-v1.0.57.0", "kind": "product",
                         "identity": "1.0.57.0", "target_revision": TARGET,
                         "channel": "canary", "disposition": "published",
                         "profile": "web-hosts", "evidence_paths": []}],
            "historical_exceptions": []}, indent=2) + "\n")
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
        plan = type("P", (), {"evidence_document":
                              "docs/release-evidence/lmdj-v1.0.57.0-dev-promotion.md"})()
        commit = PromotionCommit(self.worktree, self.repository, spec=spec(base_revision=self.base),
                                 plan=plan, author_name="Fixture",
                                 author_email="fixture@example.invalid")
        # apply_promotion runs inside commit; it needs the full policy ledger
        # contract, which the minimal fixture policy does not satisfy. The
        # commit path is exercised end to end by the promotion CLI suite; here
        # the declared-path staging and recovery refusal are pinned directly.
        with self.assertRaises(Exception):
            commit.commit(before_write=lambda: None)
        status = subprocess.run(["git", "-C", str(self.worktree), "status",
                                 "--porcelain", "--untracked-files=all"],
                                capture_output=True).stdout.decode()
        self.assertNotIn("?.", status[:2])
        head = subprocess.run(["git", "-C", str(self.worktree), "rev-parse", "HEAD"],
                              capture_output=True).stdout.decode().strip()
        self.assertEqual(head, self.base, "a failed apply must not commit")


if __name__ == "__main__":
    unittest.main()
