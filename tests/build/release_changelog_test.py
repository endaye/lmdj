#!/usr/bin/env python3
"""Exact Git history and frozen release changelog contract tests."""

from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.changelog import (ChangelogError, binding, freeze, render,
                                     select_baseline, source_inventory, validate, verify_source)
from tools.release.model import Disposition, ReleaseIntent, ReleaseKind, ReleaseLedger


class ChangelogTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.first = self.commit("base")
        self.second = self.commit("feature")
        self.third = self.commit("docs")
        self.previous = ReleaseIntent("lmdj-v1.0.1.0", ReleaseKind.PRODUCT, "1.0.1.0",
                                      self.first, Disposition.PUBLISHED, "web-hosts", ())
        self.intent = replace(self.previous, tag="lmdj-v1.0.2.0", identity="1.0.2.0",
                              target_revision=self.third, disposition=Disposition.RELEASABLE)
        self.ledger = ReleaseLedger((self.previous, self.intent), ())
        self.changes = [{"category": "feature", "area": "creator", "text": "Adds a fixture feature",
                         "commits": [self.second]}]
        self.excluded = [{"commit": self.third, "reason": "Documentation-only fixture update"}]

    def git(self, *args):
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.run(["git", "-C", str(self.root), *args], env=environment,
                              check=True, text=True, capture_output=True).stdout.strip()

    def commit(self, text):
        self.git("commit", "--allow-empty", "-qm", text)
        return self.git("rev-parse", "HEAD")

    def document(self):
        return freeze(self.root, self.intent, self.ledger, self.changes, self.excluded)

    def test_exact_range_frozen_notes_and_binding_are_reproducible(self):
        document = self.document()
        self.assertEqual(document["commits"], [self.second, self.third])
        self.assertEqual(document["baseline"], {"tag": self.previous.tag, "target_revision": self.first})
        verify_source(self.root, self.intent, self.ledger, document)
        self.assertEqual(binding(document), binding(self.document()))
        notes = render(document)
        self.assertIn("https://github.com/endaye/lmdj/commit/" + self.second, notes)
        self.assertIn("No entries recorded in this category.", notes)
        self.assertNotIn("deployed", notes)
        self.changes[0]["text"] = "Later editorial mutation"
        self.assertNotIn("Later editorial mutation", render(document))

    def test_first_release_explicitly_accounts_for_entire_history(self):
        ledger = ReleaseLedger((self.intent,), ())
        excluded = self.excluded + [{"commit": self.first, "reason": "Initial fixture bootstrap"}]
        document = freeze(self.root, self.intent, ledger, self.changes, excluded)
        self.assertIsNone(document["baseline"])
        self.assertEqual(document["commits"], [self.first, self.second, self.third])
        self.assertIn("First release", render(document))

    def test_unpublished_and_other_profile_do_not_replace_published_baseline(self):
        unpublished = replace(self.intent, target_revision=self.second)
        other = replace(self.previous, tag="lmdj-v1.0.9.0", target_revision=self.second, profile="core")
        ledger = ReleaseLedger((self.previous, unpublished, other), ())
        self.assertEqual(select_baseline(self.root, self.intent, ledger)["target_revision"], self.first)

    def test_nearest_published_ancestor_selected_not_numeric_tag_order(self):
        closer = replace(self.previous, tag="lmdj-v0.9.9.0", target_revision=self.second)
        ledger = ReleaseLedger((self.previous, closer, self.intent), ())
        self.assertEqual(select_baseline(self.root, self.intent, ledger)["tag"], closer.tag)

    def test_duplicate_published_target_is_ambiguous(self):
        alias = replace(self.previous, tag="lmdj-v1.0.8.0")
        with self.assertRaisesRegex(ChangelogError, "ambiguous"):
            select_baseline(self.root, self.intent, ReleaseLedger((self.previous, alias), ()))

    def test_nonancestor_published_history_is_not_silently_first_release(self):
        self.git("checkout", "--orphan", "unrelated")
        unrelated = self.commit("unrelated")
        previous = replace(self.previous, target_revision=unrelated)
        with self.assertRaisesRegex(ChangelogError, "no candidate baseline"):
            select_baseline(self.root, self.intent, ReleaseLedger((previous,), ()))

    def test_missing_or_duplicate_or_out_of_range_source_refused(self):
        cases = [([], self.excluded),
                 (self.changes, self.excluded + self.excluded),
                 (self.changes, self.excluded + [{"commit": self.first, "reason": "outside"}])]
        for changes, excluded in cases:
            with self.subTest(changes=changes, excluded=excluded):
                with self.assertRaisesRegex(ChangelogError, "source commits"):
                    freeze(self.root, self.intent, self.ledger, changes, excluded)

    def test_candidate_movement_cannot_reuse_frozen_document(self):
        document = self.document()
        new_head = self.commit("later")
        with self.assertRaises(ChangelogError):
            verify_source(self.root, replace(self.intent, target_revision=new_head), self.ledger, document)

    def test_new_published_baseline_cannot_rebind_frozen_scope(self):
        document = self.document()
        closer = replace(self.previous, tag="lmdj-v1.0.1.1", target_revision=self.second)
        with self.assertRaises(ChangelogError):
            verify_source(self.root, self.intent, ReleaseLedger((self.previous, closer), ()), document)

    def test_unsafe_editorial_text_and_unknown_fields_refused(self):
        for text in ("<script>alert(1)</script>", "line\nbreak", "token=secret", "sk-secret", "{MDX}"):
            with self.subTest(text=text):
                changes = deepcopy(self.changes)
                changes[0]["text"] = text
                with self.assertRaisesRegex(ChangelogError, "unsafe"):
                    freeze(self.root, self.intent, self.ledger, changes, self.excluded)
        document = self.document()
        document["unknown"] = True
        with self.assertRaisesRegex(ChangelogError, "unknown"):
            validate(document)

    def test_plaintext_markdown_is_escaped_in_common_payload(self):
        changes = deepcopy(self.changes)
        changes[0]["text"] = "Adds *plain* text with | separators"
        notes = render(freeze(self.root, self.intent, self.ledger, changes, self.excluded))
        self.assertIn(r"Adds \*plain\* text with \| separators", notes)

    def test_ambient_git_repository_and_config_cannot_replace_source(self):
        with patch.dict(os.environ, {"GIT_DIR": "/missing-fixture", "GIT_CONFIG_COUNT": "1",
                                    "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"}):
            self.assertEqual(self.document()["commits"], [self.second, self.third])

    def test_shallow_graph_is_rejected(self):
        (self.root / ".git" / "shallow").write_text(self.second + "\n")
        with self.assertRaisesRegex(ChangelogError, "shallow"):
            self.document()

    def test_replaced_commit_objects_do_not_change_frozen_inventory(self):
        self.git("replace", self.second, self.first)
        self.assertEqual(self.document()["commits"], [self.second, self.third])

    def test_revision_options_and_noncommit_target_refused(self):
        with self.assertRaisesRegex(ChangelogError, "revision"):
            source_inventory(self.root, "--all", None)
        tree = self.git("rev-parse", self.third + "^{tree}")
        with self.assertRaisesRegex(ChangelogError, "not a commit"):
            source_inventory(self.root, tree, None)

    def test_legacy_grafts_cannot_omit_real_commits(self):
        (self.root / ".git" / "info" / "grafts").write_text(self.third + " " + self.first + "\n")
        self.assertEqual(self.document()["commits"], [self.second, self.third])
        with self.assertRaisesRegex(ChangelogError, "source commits"):
            freeze(self.root, self.intent, self.ledger, [], self.excluded)

    def test_worktree_common_directory_grafts_cannot_rewrite_history(self):
        worktree = self.root / "linked"
        self.git("worktree", "add", "--detach", str(worktree), self.third)
        (self.root / ".git" / "info" / "grafts").write_text(self.third + " " + self.first + "\n")
        document = freeze(worktree, self.intent, self.ledger, self.changes, self.excluded)
        self.assertEqual(document["commits"], [self.second, self.third])

    def partial_clone(self):
        self.git("config", "uploadpack.allowFilter", "true")
        self.git("config", "uploadpack.allowAnySHA1InWant", "true")
        clone = self.root / "partial"
        self.git("clone", "--filter=blob:none", "--no-checkout", self.root.as_uri(), str(clone))
        self.assertEqual(source_inventory(clone, self.third, None),
                         [self.first, self.second, self.third])
        missing = self.commit("not in partial clone")
        self.assert_missing(clone, missing)
        return clone, missing

    def assert_missing(self, clone, target):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")
        result = subprocess.run(["git", "-C", str(clone), "cat-file", "-e", target],
                                env=env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    @staticmethod
    def object_bytes(clone):
        objects = clone / ".git" / "objects"
        return {str(path.relative_to(objects)): path.read_bytes()
                for path in objects.rglob("*") if path.is_file()}

    def test_partial_clone_missing_target_is_not_fetched(self):
        clone, target = self.partial_clone()
        before = self.object_bytes(clone)
        with self.assertRaisesRegex(ChangelogError, "cannot be verified"):
            source_inventory(clone, target, None)
        self.assert_missing(clone, target)
        self.assertEqual(self.object_bytes(clone), before)

    def test_protocol_guard_prevents_fetch_if_git_ignores_lazy_fetch_flag(self):
        clone, target = self.partial_clone()
        before = self.object_bytes(clone)
        run = subprocess.run
        def without_lazy_fetch_flag(*args, **kwargs):
            kwargs["env"] = dict(kwargs["env"])
            kwargs["env"].pop("GIT_NO_LAZY_FETCH", None)
            return run(*args, **kwargs)
        with patch("tools.release.changelog.subprocess.run", side_effect=without_lazy_fetch_flag):
            with self.assertRaisesRegex(ChangelogError, "cannot be verified"):
                source_inventory(clone, target, None)
        self.assert_missing(clone, target)
        self.assertEqual(self.object_bytes(clone), before)


if __name__ == "__main__":
    unittest.main()
