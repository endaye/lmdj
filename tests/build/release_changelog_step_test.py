#!/usr/bin/env python3
"""The changelog step's frozen document, owned docs commit and PR spec are exact."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.changelog import binding, render  # noqa: E402
from tools.release.changelog_step import (  # noqa: E402
    ChangelogCarrier,
    ChangelogCommit,
    ChangelogStepError,
    changelog_operation_id,
    evidence_document_relative,
    pr_document,
    validate_spec,
)
from tools.release.orchestration_driver import Observation  # noqa: E402

REQUEST = "4" * 64
BASE = "5" * 40
TARGET = "6" * 40


def spec(**changes):
    document = {"operation_id": changelog_operation_id(REQUEST), "request_sha256": REQUEST,
                "repository_id": 12, "actor_id": 34, "base_revision": BASE,
                "head_sha": "7" * 40, "tree_sha": "8" * 40, "target_revision": TARGET,
                "product_build": "1.0.57.0", "tag": "lmdj-v1.0.57.0",
                "changelog_sha256": "9" * 64, "notes_sha256": "a" * 64}
    document.update(changes)
    return document


def seed_repository(root):
    def git(*args):
        return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
                              check=True, capture_output=True)
    (root / "docs/release-evidence").mkdir(parents=True)
    git("init", "-q", "-b", "main")
    git("config", "user.name", "Seeder")
    git("config", "user.email", "seed@example.invalid")
    git("commit", "-q", "--allow-empty", "-m", "published baseline point")
    baseline = git("rev-parse", "HEAD").stdout.decode().strip()
    git("commit", "-q", "--allow-empty", "-m", "the candidate fix")
    target = git("rev-parse", "HEAD").stdout.decode().strip()
    ledger = {"schema": "lmdj.release-intents.v1", "entries": [
        {"tag": "lmdj-v1.0.56.0", "kind": "product", "identity": "1.0.56.0",
         "target_revision": baseline, "channel": "canary", "disposition": "published",
         "profile": "web-hosts", "evidence_paths": []},
        {"tag": "lmdj-v1.0.57.0", "kind": "product", "identity": "1.0.57.0",
         "target_revision": target, "channel": "canary", "disposition": "releasable",
         "profile": "web-hosts", "evidence_paths": ["docs/release-evidence/x.md"],
         "merged_main_run_id": 4242},
    ], "historical_exceptions": []}
    (root / "docs/release-evidence/release-intents.json").write_text(
        json.dumps(ledger, indent=2) + "\n")
    git("add", "-A")
    git("commit", "-q", "-m", "seed ledger")
    main = git("rev-parse", "HEAD").stdout.decode().strip()
    return main, baseline, target


class SpecTest(unittest.TestCase):
    def test_spec_is_closed_and_operation_is_step_bound(self):
        validate_spec(spec())
        with self.assertRaises(ChangelogStepError):
            validate_spec(spec(operation_id="0" * 64))
        with self.assertRaises(ChangelogStepError):
            validate_spec(dict(spec(), extra=1))
        with self.assertRaises(ChangelogStepError):
            validate_spec(spec(tag="lmdj-v1.0.58.0"))
        with self.assertRaises(ChangelogStepError):
            validate_spec(spec(head_sha=TARGET))

    def test_pr_document_binds_the_step_and_its_digests(self):
        document = pr_document(spec())
        self.assertEqual(document["head"], "docs/release-witness-" + changelog_operation_id(REQUEST))
        self.assertEqual(document["base"], "main")
        self.assertIn("bind 1.0.57.0 canary changelog", document["title"])
        self.assertIn("9" * 64, document["body"])


class ChangelogCommitTest(unittest.TestCase):
    def setUp(self):
        self.container = tempfile.TemporaryDirectory()
        self.addCleanup(self.container.cleanup)
        base = Path(self.container.name).resolve()
        self.repository = base / "repo"
        self.repository.mkdir()
        self.base, self.baseline, self.target = seed_repository(self.repository)
        self.worktree = base / "changelog-worktree"
        self.changes = [{"category": "fix", "area": "runtime", "text": "Fixes a fixture bug",
                         "commits": [self.target]}]
        self.exclusions = []

    def editorial(self):
        return self.changes, self.exclusions

    def expected_binding(self):
        # The exact frozen document: baseline is the published 1.0.56.0 row.
        changes, exclusions = self.editorial()
        from tools.release.changelog import freeze as freeze_changelog
        from tools.release.model import Disposition, ReleaseIntent, ReleaseKind, ReleaseLedger
        ledger_path = self.repository / "docs/release-evidence/release-intents.json"
        rows = json.loads(ledger_path.read_text())["entries"]

        def entry(row):
            return ReleaseIntent(row["tag"], ReleaseKind(row["kind"]), row["identity"],
                                 row["target_revision"], Disposition(row["disposition"]),
                                 row["profile"], tuple(row.get("evidence_paths", ())))
        entries = [entry(row) for row in rows]
        intent = next(item for item in entries if item.tag == "lmdj-v1.0.57.0")
        document = freeze_changelog(self.repository, intent,
                                    ReleaseLedger(tuple(entries), ()), changes, exclusions)
        return binding(document)

    def spec_for_fixture(self, **changes):
        bound = self.expected_binding()
        return spec(base_revision=self.base, target_revision=self.target,
                    changelog_sha256=bound["sha256"],
                    notes_sha256=bound["notes_sha256"], **changes)

    def new_commit(self, **changes):
        arguments = dict(root=self.worktree, repository_root=self.repository,
                         spec=self.spec_for_fixture(), editorial=self.editorial,
                         author_name="Fixture", author_email="fixture@example.invalid")
        arguments.update(changes)
        return ChangelogCommit(**arguments)

    def test_commit_binds_changelog_into_the_ledger_and_adds_notes(self):
        commit = self.new_commit()
        calls = []
        head, tree = commit.commit(before_write=lambda: calls.append(True))
        self.assertTrue(all(calls))
        expected = self.expected_binding()
        self.assertEqual(head, self.new_commit().commit(before_write=lambda: None)[0],
                         "resume is idempotent")
        ledger = json.loads((self.worktree / "docs/release-evidence/release-intents.json")
                            .read_text())
        row = next(row for row in ledger["entries"] if row["tag"] == "lmdj-v1.0.57.0")
        self.assertEqual(binding(row["changelog"]), expected)
        notes = (self.worktree / evidence_document_relative(self.spec_for_fixture())).read_text()
        self.assertEqual(notes, render(row["changelog"]))
        self.assertIn("Fixes a fixture bug", notes)
        # Committed tree carries exactly the two declared paths.
        diff = subprocess.run(["git", "-C", str(self.worktree), "diff-tree",
                               "--no-commit-id", "--name-only", "-r", self.base, head],
                              capture_output=True).stdout.decode().split()
        self.assertEqual(sorted(diff), sorted(["docs/release-evidence/release-intents.json",
                                              evidence_document_relative(self.spec_for_fixture())]))
        resumed = self.new_commit()
        self.assertIsNotNone(resumed.completed_head())
        self.assertEqual(resumed.completed_head(), head)
        self.assertEqual(tree, subprocess.run(
            ["git", "-C", str(self.worktree), "rev-parse", "HEAD^{tree}"],
            capture_output=True).stdout.decode().strip())

    def test_commit_refuses_files_outside_the_declared_paths(self):
        subprocess.run(["git", "-C", str(self.repository), "worktree", "add", "--detach",
                        str(self.worktree), self.base], check=True, capture_output=True)
        stray = self.worktree / "products/stray.txt"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("stray\n")
        with self.assertRaises(ChangelogStepError):
            self.new_commit().commit(before_write=lambda: None)
        status = subprocess.run(["git", "-C", str(self.worktree), "status", "--porcelain",
                                 "--untracked-files=all"], capture_output=True).stdout.decode()
        self.assertIn("?? products/stray.txt", status)

    def test_recovery_refuses_an_amended_commit_with_a_foreign_changelog(self):
        commit = self.new_commit()
        head, _ = commit.commit(before_write=lambda: None)
        ledger_path = self.worktree / "docs/release-evidence/release-intents.json"
        document = json.loads(ledger_path.read_text())
        row = next(row for row in document["entries"] if row["tag"] == "lmdj-v1.0.57.0")
        row["changelog"]["changes"] = []
        ledger_path.write_text(json.dumps(document, indent=2) + "\n")
        subprocess.run(["git", "-C", str(self.worktree), "commit", "-qam", "tamper"],
                       check=True, capture_output=True,
                       env={"GIT_AUTHOR_NAME": "F", "GIT_AUTHOR_EMAIL": "f@e.invalid",
                            "GIT_COMMITTER_NAME": "F", "GIT_COMMITTER_EMAIL": "f@e.invalid",
                            "PATH": "/usr/bin:/bin", "HOME": str(self.worktree)})
        with self.assertRaises(ChangelogStepError):
            self.new_commit().completed_head()


class CarrierMappingTest(unittest.TestCase):
    def test_sequence_states_map_to_honest_observations(self):
        container = tempfile.TemporaryDirectory()
        self.addCleanup(container.cleanup)
        root = Path(container.name).resolve()
        commit = ChangelogCommit(root / "worktree", root / "repo",
                                 spec=spec(), editorial=lambda: ([], []),
                                 author_name="F", author_email="f@e.invalid")
        # Build the real sequence via a tiny subclass of the same base so the
        # mapping test needs no GitHub transport.
        from tools.release.candidate_pr_sequence import CandidatePrSequence
        from tools.release.changelog_step import (
            ChangelogBranch as _B, ChangelogPullRequest as _P)

        class LocalSequence(CandidatePrSequence):
            _validate_spec = staticmethod(validate_spec)
            _document = staticmethod(pr_document)
            _branch_type, _pr_type = _B, _P
            _state_file = "changelog-pr-sequence.json"
            _schema = "lmdj.changelog-pr-sequence.v1"

        sequence = LocalSequence(root, branch=_B(root / "branch", root / "repo",
                                                 token="FIXTURE", authorize=lambda s: None),
                                 pr=_P(root / "pr", api=lambda *a, **k: None,
                                       authorize=lambda s: None, review=lambda *a: None,
                                       verify_merged=lambda *a: None))
        carrier = ChangelogCarrier(commit=commit, sequence=sequence)
        carrier._spec = spec()
        cases = [("absent", "pending"), ("pending", "pending"),
                 ("unknown", "unknown"), ("conflict", "conflict")]
        for status, expected in cases:
            sequence.observe = lambda spec_, initialize=False, status=status: {
                "status": status, "phase": "pr", "evidence": None}
            observed = carrier.observe({}, {"step": "changelog"})
            self.assertIsInstance(observed, Observation)
            self.assertEqual(observed.status, expected, status)
        # merged without a verified merge is unknown, never verified.
        sequence.observe = lambda spec_, initialize=False: {
            "status": "merged", "phase": "pr", "evidence": None}
        sequence.pr.observe_merge = lambda spec_: {"status": "unverified"}
        self.assertEqual(carrier.observe({}, {"step": "changelog"}).status, "unknown")

    def test_carrier_refuses_foreign_children(self):
        with self.assertRaises(ChangelogStepError):
            ChangelogCarrier(commit=object(), sequence=object())


if __name__ == "__main__":
    unittest.main()
