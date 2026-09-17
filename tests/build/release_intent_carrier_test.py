#!/usr/bin/env python3
"""Intent documents, the owned docs commit, and the ledger append are exact."""
from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.intent import (  # noqa: E402
    IntentCommit,
    IntentError,
    intent_markdown,
    intent_operation_id,
    ledger_append,
    ledger_row,
    pr_document,
    validate_spec,
)

REQUEST_SHA = "a" * 64
TARGET = "b" * 40
RUN_ID = 4242


def batch_reference(target=TARGET, run_id=RUN_ID):
    """A closed verified batch reference document, as the verification step binds."""
    return {"schema": "lmdj.ci-batch-release-reference.v1",
            "executor_control_revision": "d" * 40, "executor_event": "push",
            "run_attempt": 1, "origin_record_digest": "e" * 64,
            "admission_record_digest": "f" * 64, "evidence_digest": "0" * 64,
            "request": {"id": "batch-4242", "kind": "auto", "base": "1" * 40,
                        "target": target, "control": "d" * 40,
                        "policy": "2" * 64,
                        "selection": {"kind": "full", "suites": ["unit"],
                                      "reasons": ["candidate"]},
                        "origin_run": {"run_id": run_id, "attempt": 1}}}


def spec(**changes):
    base = {"operation_id": intent_operation_id(REQUEST_SHA), "request_sha256": REQUEST_SHA,
            "repository_id": 12, "actor_id": 34, "target_revision": TARGET,
            "product_build": "1.0.57.0", "tag": "lmdj-v1.0.57.0",
            "snapshot_sha256": "c" * 64, "batch_reference": batch_reference(),
            "batch_run_id": RUN_ID}
    base.update(changes)
    if ("target_revision" in changes or "batch_run_id" in changes) \
            and "batch_reference" not in changes:
        # The reference document binds the target and the run; an override of
        # either must rebind the document or the spec is inconsistent.
        base["batch_reference"] = batch_reference(target=base["target_revision"],
                                                  run_id=base["batch_run_id"])
    return base


def seed_repository(root, *, build="1.0.56.0"):
    def git(*args):
        return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
                              check=True, capture_output=True)
    (root / "products/lmdj").mkdir(parents=True)
    (root / "apps/architecture-portal").mkdir(parents=True)
    (root / "docs/release-evidence").mkdir(parents=True)
    (root / "apps/architecture-portal/versions.json").write_text(
        json.dumps(["1.0.52.0", build]) + "\n")
    (root / "docs/release-evidence/release-intents.json").write_text(json.dumps(
        {"schema": "lmdj.release-intents.v1",
         "entries": [{"tag": "lmdj-v1.0.40.0", "kind": "product", "identity": "1.0.40.0",
                      "target_revision": "c" * 40, "channel": "canary",
                      "disposition": "superseded-unreleased", "profile": "web-hosts"}],
         "historical_exceptions": []}) + "\n")
    (root / "README.md").write_text("seed\n")
    git("init", "-q", "-b", "main")
    git("config", "user.name", "Seeder")
    git("config", "user.email", "seed@example.invalid")
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    return git("rev-parse", "HEAD").stdout.decode().strip()


class IntentDocumentsTest(unittest.TestCase):
    def pr_spec(self, **changes):
        base = {"head_sha": "3" * 40, "tree_sha": "4" * 40}
        base.update(changes)
        return spec(**base)

    def test_spec_document_row_and_markdown_are_bound_and_exact(self):
        document = pr_document(self.pr_spec())
        self.assertEqual(document["head"], "docs/release-witness-" + intent_operation_id(REQUEST_SHA))
        self.assertEqual(document["base"], "main")
        self.assertIn("docs(release): record 1.0.57.0 canary release intent", document["title"])
        row = ledger_row(spec())
        self.assertEqual(row["target_revision"], TARGET)
        self.assertEqual(row["disposition"], "releasable")
        self.assertEqual(row["merged_main_run_id"], 4242)
        self.assertEqual(row["batch_test_evidence"], batch_reference())
        markdown = intent_markdown(spec())
        self.assertIn("lmdj-v1.0.57.0", markdown)
        self.assertIn("`b" * 1, markdown)

    def test_mismatched_tag_or_operation_is_refused(self):
        with self.assertRaises(IntentError):
            validate_spec(spec(tag="lmdj-v1.0.58.0"))
        with self.assertRaises(IntentError):
            validate_spec(spec(operation_id="d" * 64))
        with self.assertRaises(IntentError):
            validate_spec(spec(product_build="1.0.57"))

    def test_a_string_or_unclosed_batch_reference_is_refused(self):
        # The ledger row freezes `batch_test_evidence`, which the ledger model
        # parses as a closed reference document; the encoded text form would
        # corrupt the ledger on its next load.
        for bad in ("batch-verdict-v1:zlib-base64:AAA", {"schema": "other"},
                    dict(batch_reference(), schema="other")):
            with self.assertRaises(IntentError):
                validate_spec(spec(batch_reference=bad))

    def test_a_batch_reference_binding_another_target_or_run_is_refused(self):
        with self.assertRaises(IntentError):
            validate_spec(spec(batch_reference=batch_reference(target="9" * 40)))
        with self.assertRaises(IntentError):
            validate_spec(spec(batch_reference=batch_reference(run_id=RUN_ID + 1)))

    def test_the_ledger_row_survives_the_ledger_model(self):
        # The row this carrier appends must load under the active policy; a
        # row the model rejects would corrupt the ledger for every later read.
        from tools.release.model import load_ledger_document, load_policy

        policy = load_policy(ROOT / "tools/release/policy.json")
        ledger = load_ledger_document(
            {"schema": "lmdj.release-intents.v1", "entries": [ledger_row(spec())],
             "historical_exceptions": []}, policy)
        self.assertEqual(ledger.entries[0].tag, "lmdj-v1.0.57.0")
        self.assertEqual(ledger.entries[0].batch_test_evidence["request"]["target"],
                         TARGET)

    def test_the_pr_spec_carries_the_commit_identity(self):
        # The carrier drives the PR sequence with the spec its durable commit
        # produced, which adds head_sha/tree_sha; the sequence, branch and PR
        # validators must accept exactly that shape.
        from tools.release.intent import validate_pr_spec
        from tools.release.intent_carrier import (
            IntentBranch,
            IntentPrSequence,
            IntentPullRequest,
        )

        pr = self.pr_spec()
        validate_pr_spec(pr)
        for validator in (IntentBranch._validate_spec, IntentPullRequest._validate_spec,
                          IntentPrSequence._validate_spec):
            validator(dict(pr))
        self.assertEqual(pr_document(pr)["base"], "main")
        with self.assertRaises(IntentError):
            validate_pr_spec(spec())  # the base spec is not a PR spec
        with self.assertRaises(IntentError):
            validate_pr_spec(self.pr_spec(head_sha="not-a-sha"))

    def test_ledger_append_refuses_duplicates_and_keeps_history(self):
        rows = [{"tag": "lmdj-v1.0.57.0"}]
        with self.assertRaises(IntentError):
            ledger_append(rows, ledger_row(spec()))
        fresh = ledger_append([{"tag": "lmdj-v1.0.40.0"}], ledger_row(spec()))
        self.assertEqual([row["tag"] for row in fresh], ["lmdj-v1.0.40.0", "lmdj-v1.0.57.0"])
        self.assertEqual(fresh[0], {"tag": "lmdj-v1.0.40.0"})


class IntentCommitTest(unittest.TestCase):
    def setUp(self):
        self.container = tempfile.TemporaryDirectory()
        self.addCleanup(self.container.cleanup)
        base = Path(self.container.name).resolve()
        self.repository = base / "repo"
        self.repository.mkdir()
        self.head = seed_repository(self.repository)
        self.worktree = base / "intent-worktree"
        self.freeze_calls = []

    def freeze(self, root):
        self.freeze_calls.append(Path(root))
        marker = Path(root) / "apps/architecture-portal/versioned_metadata"
        marker.mkdir(exist_ok=True)
        (marker / "version-1.0.57.0.json").write_text("{}\n")

    def new_commit(self, **changes):
        arguments = dict(root=self.worktree, repository_root=self.repository,
                         spec=spec(target_revision=self.head),
                         freeze=self.freeze, author_name="Fixture",
                         author_email="fixture@example.invalid")
        arguments.update(changes)
        return IntentCommit(**arguments)

    def writes(self):
        return [(name, (self.worktree / name).exists())
                for name in ("apps/architecture-portal/versions.json",
                             "apps/architecture-portal/versioned_metadata/version-1.0.57.0.json",
                             "docs/release-evidence/release-intents.json",
                             "docs/release-evidence/lmdj-v1.0.57.0-canary-release-intent.md")]

    def test_commit_appends_versions_snapshot_ledger_and_document(self):
        commit = self.new_commit()
        calls = []
        head, tree = commit.commit(before_write=lambda: calls.append(True))
        self.assertTrue(all(calls), "write guard must be invoked at every boundary")
        self.assertEqual(len(self.freeze_calls), 1)
        for name, exists in self.writes():
            self.assertTrue(exists, name)
        versions = json.loads((self.worktree / "apps/architecture-portal/versions.json").read_text())
        self.assertEqual(versions, ["1.0.52.0", "1.0.56.0", "1.0.57.0"])
        ledger = json.loads(
            (self.worktree / "docs/release-evidence/release-intents.json").read_text())
        self.assertEqual([row["tag"] for row in ledger["entries"]],
                         ["lmdj-v1.0.40.0", "lmdj-v1.0.57.0"])
        self.assertEqual(ledger["entries"][-1]["target_revision"], self.head)
        subject = subprocess.run(
            ["git", "-C", str(self.worktree), "log", "-1", "--format=%s"],
            capture_output=True).stdout.decode()
        self.assertIn("canary release intent", subject)
        self.assertNotEqual(head, self.head)
        resumed_head, resumed_tree = self.new_commit().commit(before_write=lambda: None)
        self.assertEqual((head, tree), (resumed_head, resumed_tree))

    def test_recovery_refuses_a_commit_that_lacks_the_ledger_row(self):
        commit = self.new_commit()
        commit.commit(before_write=lambda: None)
        # Replace the committed ledger with one that has no row for this tag;
        # the worktree stays clean, so only the committed tree can refuse it.
        ledger = self.worktree / "docs/release-evidence/release-intents.json"
        document = json.loads(ledger.read_text())
        document["entries"] = [row for row in document["entries"]
                               if row["tag"] != "lmdj-v1.0.57.0"]
        ledger.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        subprocess.run(["git", "-C", str(self.worktree), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-q",
                        "-am", "drop the intent row"], check=True, capture_output=True)
        with self.assertRaises(IntentError):
            self.new_commit().completed_head()

    def test_commit_refuses_files_outside_the_declared_intent_paths(self):
        # A freeze (or a concurrent process) leaves an unrelated worktree file:
        # staging must fail closed instead of committing it into the PR.
        subprocess.run(["git", "-C", str(self.repository), "worktree", "add",
                        "--detach", str(self.worktree), self.head], check=True,
                       capture_output=True)
        stray = self.worktree / "products/lmdj/unrelated.txt"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("stray\n")
        commit = self.new_commit()
        with self.assertRaises(IntentError):
            commit.commit(before_write=lambda: None)
        staged = subprocess.run(
            ["git", "-C", str(self.worktree), "ls-files", "--error-unmatch",
             "products/lmdj/unrelated.txt"], capture_output=True)
        self.assertNotEqual(staged.returncode, 0, "the stray file must never be staged")
        status = subprocess.run(
            ["git", "-C", str(self.worktree), "status", "--porcelain",
             "--untracked-files=all"], capture_output=True).stdout.decode()
        self.assertIn("?? products/lmdj/unrelated.txt", status,
                      "the refusal must leave the stray file untracked")

    def test_recovery_refuses_a_commit_that_amends_unrelated_paths(self):
        commit = self.new_commit()
        head, _ = commit.commit(before_write=lambda: None)
        # Amend the verified commit with an unrelated file while keeping the
        # ledger row and document intact; only the committed tree can refuse it.
        (self.worktree / "stray-after.txt").write_text("smuggled\n")
        subprocess.run(["git", "-C", str(self.worktree), "add", "stray-after.txt"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.worktree), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-q",
                        "--amend", "-m", "docs(release): record 1.0.57.0 canary release intent"],
                       check=True, capture_output=True)
        amended = subprocess.run(["git", "-C", str(self.worktree), "rev-parse", "HEAD"],
                                 capture_output=True).stdout.decode().strip()
        self.assertNotEqual(amended, head)
        with self.assertRaises(IntentError):
            self.new_commit().completed_head()

    def test_declared_paths_cover_the_real_freeze_layout(self):
        commit = self.new_commit()
        declared = commit._declared_path
        self.assertTrue(declared("apps/architecture-portal/versions.json"))
        self.assertTrue(declared("apps/architecture-portal/versioned_metadata/version-1.0.57.0.json"))
        self.assertTrue(declared("apps/architecture-portal/versioned_docs/version-1.0.57.0/contracts/project.mdx"))
        self.assertTrue(declared("apps/architecture-portal/versioned_sidebars/version-1.0.57.0-sidebars.json"))
        self.assertTrue(declared("apps/architecture-portal/static/versions/1.0.57.0/diagrams/assembly.svg"))
        self.assertTrue(declared("apps/architecture-portal/versioned_provenance/version-1.0.57.0-squash-witness.json"))
        self.assertTrue(declared("docs/release-evidence/release-intents.json"))
        self.assertTrue(declared("docs/release-evidence/lmdj-v1.0.57.0-canary-release-intent.md"))
        self.assertFalse(declared("apps/docs-site/docs/operations/version-and-release.mdx"))
        self.assertFalse(declared("products/lmdj/version.json"))
        self.assertFalse(declared("apps/architecture-portal/versioned_metadata/version-1.0.56.0.json"))
        self.assertFalse(declared("README.md"))
        self.assertFalse(declared("../escape.txt"))

    def test_completed_head_is_none_before_the_commit_exists(self):
        self.assertIsNone(self.new_commit().completed_head())

    def test_worktree_at_another_revision_is_refused(self):
        subprocess.run(["git", "-C", str(self.repository), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit",
                        "-q", "--allow-empty", "-m", "advance main"], check=True,
                       capture_output=True)
        advanced = subprocess.run(["git", "-C", str(self.repository), "rev-parse", "HEAD"],
                                  capture_output=True).stdout.decode().strip()
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        other_root = Path(other.name).resolve() / "elsewhere"
        other_root.mkdir(parents=True)
        subprocess.run(["git", "-C", str(self.repository), "worktree", "add",
                        "--detach", str(other_root), advanced], check=True,
                       capture_output=True)
        commit = self.new_commit(root=other_root)
        with self.assertRaises(IntentError):
            commit.commit(before_write=lambda: None)


if __name__ == "__main__":
    unittest.main()
