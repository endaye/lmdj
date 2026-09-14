#!/usr/bin/env python3
"""Actual publication Task and squash tree proofs with moving main fixtures."""

from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/build"))
import release_publication_workspace_test as fixtures
import release_promotion_test as promotion_fixtures
from tools.release.changelog import binding
from tools.release.batch_reference import thaw
from tools.release.evidence_source import EvidenceSourceError, PublicationSourceVerifier, PublishedPrSourceGate
from tools.release.github_api import BranchProjection
from tools.release.model import canonical_json, load_ledger_document
from tools.release.publication_evidence import LEDGER, INDEX
from tools.release.publication_workspace import PublicationWorkspace, PublicationWorkspaceError


class SourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate the seed through the real workspace/planner once. Every test
        # clones its emitted Git objects into a separate repository; source
        # validation need not repeat the unrelated publication/signing fixture
        # journey for each one-fact source mutation.
        cls.seed = cls()
        cls.addClassCleanup(cls.seed.doCleanups)
        cls.seed._prepare_seed()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="lmdj-source-case-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "repo"
        subprocess.run(["git", "clone", "--no-hardlinks", "--no-checkout",
                        str(self.seed.root), str(self.root)],
                       capture_output=True, check=True)
        def git(*args):
            return subprocess.run(["git", "-C", str(self.root), *args],
                capture_output=True, text=True, check=True).stdout.strip()
        git("-c", "core.symlinks=true", "checkout", "--detach", self.seed.spec["head_sha"])
        self.fixture = SimpleNamespace(git=git, workspace=PublicationWorkspace(self.root))
        self.policy, self.intent = self.seed.policy, self.seed.intent
        self.record, self.spec = deepcopy(self.seed.record), deepcopy(self.seed.spec)
        self.target, self.base, self.main = self.seed.target, self.seed.base, self.seed.base
        self.source = PublicationSourceVerifier(self.root)

    def _prepare_seed(self):
        self.fixture = fixtures.WorkspaceTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.policy = self.fixture.fixture.f.policy
        # The original publication unit fixture uses synthetic target IDs. Bind
        # a separate source-only fixture to an actual ancestor commit instead;
        # do not present this rewritten fixture as signed-publication proof.
        self.target = self.fixture.base
        ledger = self.root / LEDGER
        ledger.write_text(ledger.read_text().replace(self.fixture.intent.target_revision, self.target))
        document = json.loads(ledger.read_bytes())
        self.intent = load_ledger_document(document, self.policy).intent_for_tag(self.fixture.intent.tag)
        hashes = binding(thaw(self.intent.changelog))
        self.record = dict(self.fixture.record, target_revision=self.target,
                           changelog_sha256=hashes["sha256"], notes_sha256=hashes["notes_sha256"])
        self.fixture.git("add", LEDGER)
        self.fixture.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture candidate binding")
        self.base = self.fixture.git("rev-parse", "HEAD")
        self.fixture.base, self.fixture.intent, self.fixture.record = self.base, self.intent, self.record
        self.fixture.arguments.update(base_revision=self.base, intent=self.intent, record=self.record)
        result = self.fixture.run_task()
        self.spec = dict(operation_id=result["operation_id"], request_sha256="2" * 64,
            repository_id=12, actor_id=34, base_revision=self.base, head_sha=result["commit"],
            tree_sha=result["tree"], tag=self.intent.tag, target_revision=self.target,
            task_evidence_sha256="3" * 64)
        self.source = PublicationSourceVerifier(self.root)
        self.main = self.base

    def verify(self, spec=None, **changes):
        return self.source.verify(spec or self.spec, **dict(policy=self.policy, intent=self.intent,
            record=self.record, main_revision=self.main, **changes))

    def commit(self, tree, *parents):
        args = ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit-tree", tree]
        for parent in parents:
            args += ["-p", parent]
        return self.fixture.git(*args, "-m", "fixture squash")

    def changed_tree(self, base, path, data):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "index"
            git = self.fixture.workspace.git
            git("read-tree", base, index=index)
            blob = git("hash-object", "-w", "--stdin", data=data).decode().strip()
            git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + path, index=index)
            return git("write-tree", index=index).decode().strip()

    def test_head_proof_repeats_without_worktree_index_or_ref_mutation(self):
        before = (self.fixture.git("rev-parse", "HEAD"), self.fixture.git("write-tree"), self.fixture.git("status", "--porcelain"))
        first = self.verify()
        self.assertEqual(self.verify(), first)
        self.assertIsNone(first["merge_sha"])
        self.assertEqual((self.fixture.git("rev-parse", "HEAD"), self.fixture.git("write-tree"), self.fixture.git("status", "--porcelain")), before)

    def test_actual_single_parent_squash_is_verified(self):
        merged = self.commit(self.spec["tree_sha"], self.base)
        self.main = merged
        result = self.verify(merge_revision=merged)
        self.assertEqual(result["merge_sha"], merged)
        self.assertEqual(result["merge_parent"], self.base)
        self.assertEqual(result["merge_tree"], self.spec["tree_sha"])

    def test_unrelated_main_progress_is_preserved_without_changing_candidate(self):
        prior_tree = self.changed_tree(self.base, "unrelated.txt", b"another merged Task\n")
        prior = self.commit(prior_tree, self.base)
        merged_tree = self.source._expected_tree(prior, self.policy, self.intent, self.record)
        merged = self.commit(merged_tree, prior)
        later_tree = self.changed_tree(merged, "later.txt", b"later Task\n")
        self.main = self.commit(later_tree, merged)
        proof = self.verify(merge_revision=merged)
        self.assertEqual(proof["target_revision"], self.target)
        self.assertEqual(proof["merge_parent"], prior)
        self.assertNotEqual(proof["merge_tree"], proof["tree_sha"])

    def test_smuggled_unrelated_head_change_fails_even_with_matching_declared_tree(self):
        tree = self.changed_tree(self.spec["head_sha"], "smuggled.txt", b"not publication evidence\n")
        head = self.commit(tree, self.base)
        with self.assertRaisesRegex(EvidenceSourceError, "complete exact publication patch"):
            self.verify(dict(self.spec, head_sha=head, tree_sha=tree))

    def test_changed_frozen_page_fails_even_with_matching_declared_tree(self):
        tree = self.changed_tree(self.spec["head_sha"], INDEX, b"rewritten notes\n")
        head = self.commit(tree, self.base)
        with self.assertRaisesRegex(EvidenceSourceError, "complete exact publication patch"):
            self.verify(dict(self.spec, head_sha=head, tree_sha=tree))

    def test_merge_tree_cannot_drop_intervening_main_changes(self):
        prior = self.commit(self.changed_tree(self.base, "unrelated.txt", b"retain\n"), self.base)
        merged = self.commit(self.spec["tree_sha"], prior)
        self.main = merged
        with self.assertRaisesRegex(EvidenceSourceError, "squash tree differs"):
            self.verify(merge_revision=merged)

    def test_merge_cannot_smuggle_extra_changes(self):
        tree = self.changed_tree(self.spec["head_sha"], "smuggled.txt", b"extra\n")
        merged = self.commit(tree, self.base)
        self.main = merged
        with self.assertRaisesRegex(EvidenceSourceError, "squash tree differs"):
            self.verify(merge_revision=merged)

    def test_two_parent_merge_is_not_a_squash(self):
        merged = self.commit(self.spec["tree_sha"], self.base, self.spec["head_sha"])
        self.main = merged
        with self.assertRaisesRegex(EvidenceSourceError, "distinct squash"):
            self.verify(merge_revision=merged)

    def test_unmerged_squash_object_is_not_main_evidence(self):
        merged = self.commit(self.spec["tree_sha"], self.base)
        with self.assertRaises(PublicationWorkspaceError):
            self.verify(merge_revision=merged)

    def test_fast_forward_head_is_not_a_squash(self):
        self.main = self.spec["head_sha"]
        with self.assertRaisesRegex(EvidenceSourceError, "distinct squash"):
            self.verify(merge_revision=self.main)

    def test_head_cannot_contain_multiple_task_commits(self):
        intermediate = self.commit(self.spec["tree_sha"], self.base)
        extra = self.commit(self.spec["tree_sha"], intermediate)
        with self.assertRaisesRegex(EvidenceSourceError, "exactly one commit"):
            self.verify(dict(self.spec, head_sha=extra))

    def test_request_target_drift_is_refused(self):
        with self.assertRaisesRegex(EvidenceSourceError, "fresh publication differs"):
            self.verify(dict(self.spec, target_revision="f" * 40))

    def test_reverted_publication_is_not_current_main_evidence(self):
        merged = self.commit(self.spec["tree_sha"], self.base)
        base_tree = self.fixture.git("rev-parse", self.base + "^{tree}")
        self.main = self.commit(base_tree, merged)
        with self.assertRaisesRegex(EvidenceSourceError, "current main no longer contains"):
            self.verify(merge_revision=merged)

    def test_later_promotion_preserves_the_same_publication_source_proof(self):
        merged = self.commit(self.spec["tree_sha"], self.base)
        self.main = merged
        before = self.verify(merge_revision=merged)
        text = self.fixture.workspace.git("cat-file", "blob", merged + ":" + LEDGER).decode()
        old = next(line for line in text.split("\n") if '"tag":"' + self.intent.tag + '"' in line)
        entry = json.loads(old.strip().removesuffix(","))
        entry["promotions"] = [promotion_fixtures._promotion()]
        updated = text.replace(old, "    " + json.dumps(entry, separators=(",", ":")) + ("," if old.rstrip().endswith(",") else ""))
        self.intent = load_ledger_document(json.loads(updated), self.policy).intent_for_tag(self.intent.tag)
        self.main = self.commit(self.changed_tree(merged, LEDGER, updated.encode()), merged)
        self.assertEqual(self.verify(merge_revision=merged), before)

    def test_injected_git_environment_cannot_replace_source(self):
        with patch.dict(os.environ, {"GIT_INDEX_FILE": "/nonexistent/index", "GIT_DIR": "/nonexistent/repo",
            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"}):
            self.assertEqual(self.verify()["head_sha"], self.spec["head_sha"])

    def test_live_wrapper_rechecks_protection_and_allows_descendant_main(self):
        later = self.commit(self.changed_tree(self.base, "unrelated.txt", b"later\n"), self.base)
        github = SimpleNamespace(get_branch=lambda *_: branches.pop(0))
        context = SimpleNamespace(policy=self.policy, github=github)
        branches = [BranchProjection("main", True, self.base), BranchProjection("main", True, later)]
        gate = PublishedPrSourceGate(self.root, context_factory=lambda: context, release_id=77, plan_sha256="4" * 64)
        with patch("tools.release.evidence_source.collect_publication_state", return_value=(self.record, self.intent)) as collect:
            self.assertEqual(gate.verify(self.spec)["head_sha"], self.spec["head_sha"])
            collect.assert_called_once_with(self.intent.tag, 77, "4" * 64, context)
        branches[:] = [BranchProjection("main", True, self.base), BranchProjection("main", False, later)]
        with patch("tools.release.evidence_source.collect_publication_state", return_value=(self.record, self.intent)):
            with self.assertRaisesRegex(EvidenceSourceError, "protection changed"):
                gate.verify(self.spec)

    def test_live_publication_failure_never_reaches_source_proof(self):
        gate = PublishedPrSourceGate(self.root, context_factory=lambda: object(), release_id=77, plan_sha256="4" * 64)
        with patch("tools.release.evidence_source.collect_publication_state", side_effect=ValueError("failed signed-publication gate")), patch.object(gate.source, "verify") as verify:
            with self.assertRaises(ValueError):
                gate.verify(self.spec)
            verify.assert_not_called()

    def test_final_main_observation_catches_a_late_publication_revert(self):
        merged = self.commit(self.spec["tree_sha"], self.base)
        reverted = self.commit(self.fixture.git("rev-parse", self.base + "^{tree}"), merged)
        branches = [BranchProjection("main", True, merged), BranchProjection("main", True, reverted)]
        context = SimpleNamespace(policy=self.policy, github=SimpleNamespace(get_branch=lambda *_: branches.pop(0)))
        gate = PublishedPrSourceGate(self.root, context_factory=lambda: context, release_id=77, plan_sha256="4" * 64)
        with patch("tools.release.evidence_source.collect_publication_state", return_value=(self.record, self.intent)):
            with self.assertRaisesRegex(EvidenceSourceError, "current main no longer contains"):
                gate.verify(self.spec, merge_revision=merged)

    def test_partial_clone_missing_blob_never_starts_remote_fetch(self):
        with tempfile.TemporaryDirectory(prefix="lmdj-partial-source-") as directory:
            bare, partial = Path(directory) / "remote.git", Path(directory) / "partial"
            def git(*args):
                return subprocess.run(["git", *map(str, args)], check=True, capture_output=True, text=True).stdout
            git("clone", "--bare", self.root, bare)
            git("-C", bare, "config", "uploadpack.allowFilter", "true")
            git("clone", "--filter=blob:none", "--no-checkout", bare.as_uri(), partial)
            oid = self.fixture.git("rev-parse", self.spec["head_sha"] + ":" + LEDGER)
            missing = git("-C", partial, "rev-list", "--objects", "--all", "--missing=print")
            self.assertIn("?" + oid, missing)
            self.assertEqual(git("-C", partial, "rev-parse", "--is-shallow-repository").strip(), "false")
            requests = []
            class Reject(BaseHTTPRequestHandler):
                def do_GET(self):
                    requests.append(self.path)
                    self.send_error(500)
                def log_message(self, *_):
                    pass
            server = HTTPServer(("127.0.0.1", 0), Reject)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                git("-C", partial, "remote", "set-url", "origin", f"http://127.0.0.1:{server.server_port}/remote.git")
                # Causal baseline: ordinary partial-clone object access reaches
                # the observer (which deliberately refuses to supply objects).
                environment = {key: value for key, value in os.environ.items() if key in ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
                environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                                   GIT_ALLOW_PROTOCOL="http", GIT_TERMINAL_PROMPT="0")
                baseline = subprocess.run(["git", "-C", str(partial), "cat-file", "blob", oid],
                    capture_output=True, env=environment, timeout=10)
                self.assertNotEqual(baseline.returncode, 0)
                self.assertTrue(requests)
                requests.clear()
                reader = PublicationSourceVerifier(partial.resolve())
                with self.assertRaises(PublicationWorkspaceError):
                    reader.git("cat-file", "blob", oid)
                self.assertEqual(requests, [])
                self.assertIn("?" + oid, git("-C", partial, "rev-list", "--objects", "--all", "--missing=print"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
