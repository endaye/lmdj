#!/usr/bin/env python3
"""Real linked worktree source installation and crash recovery, no release."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_candidate_material_test as material_fixture
from scripts import version
from tools.release.candidate_workspace import CandidateSourceWorkspace, FILES
from tools.release.model import canonical_sha256
from tools.release.publication_workspace import PublicationWorkspaceError


class WorkspaceFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        material_fixture.MaterialTest.setUpClass()
        cls.addClassCleanup(material_fixture.MaterialTest.doClassCleanups)

    def setUp(self):
        self.fixture = material_fixture.MaterialTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.request = self.fixture.request
        operation = canonical_sha256({"request":canonical_sha256(self.request), "step":"candidate"})
        self.branch = "feat/release-candidate-" + operation
        self.root = self.fixture.container / "worktree"
        self.fixture.git("-c", "core.symlinks=true", "worktree", "add", "-b", self.branch, str(self.root), self.fixture.base)
        self.tool = CandidateSourceWorkspace(self.root, self.fixture.tool)
        self.calls = []

    def verify(self, root):
        current = version.load_version(root / "products/lmdj/version.json")
        assembly_path = root / "products/lmdj/assembly.json"
        assembly = version._verify_assembly(current, assembly_path)
        version._verify_lock(current, assembly_path, assembly,
                             root / "products/lmdj/assembly.lock.json", repo_root=root)
        self.calls.append(str(current))

    def prepare(self, **changes):
        arguments = dict(request=self.request, frozen=self.fixture.frozen,
                         main_revision=self.fixture.base, author_name="Fixture",
                         author_email="fixture@example.invalid", timestamp=1730000000,
                         verify=self.verify)
        arguments.update(changes)
        return self.tool.prepare_source(**arguments)


class WorkspaceRecoveryTest(WorkspaceFixture):
    def test_source_commit_is_clean_exact_and_not_a_finished_cut(self):
        original = self.fixture.git("rev-parse", "main")
        receipt = self.prepare()
        self.assertEqual(receipt["status"], "source-committed")
        self.assertEqual(set(receipt["files"]), FILES)
        self.assertEqual(self.tool.revision("HEAD"), receipt["commit"])
        self.assertEqual(self.tool.revision_from_index(), receipt["tree"])
        self.assertEqual(self.tool.git("status", "--porcelain"), b"")
        self.assertEqual(self.fixture.git("rev-parse", "main"), original)
        changed = self.tool.git("diff-tree", "--no-commit-id", "--name-only", "-r", original, receipt["commit"]).decode().splitlines()
        self.assertEqual(set(changed), FILES)
        self.assertEqual(len(self.calls), 1)
        # Source-only commit contains no invented snapshot or release ledger.
        self.assertFalse(any("versioned" in name or "release-evidence" in name for name in changed))

    def test_resume_revalidates_without_second_ref_update(self):
        first = self.prepare()
        with patch.object(self.tool, "git", wraps=self.tool.git) as git:
            self.assertEqual(self.prepare(), first)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(any(call.args[0] == "update-ref" for call in git.call_args_list))

    def test_failed_verification_preserves_base_and_reconciles_same_material(self):
        def fail(root):
            raise RuntimeError("sensitive fixture detail must not leak")
        with self.assertRaisesRegex(PublicationWorkspaceError, "candidate source Task verification failed") as caught:
            self.prepare(verify=fail)
        self.assertNotIn("sensitive", str(caught.exception))
        self.assertEqual(self.tool.revision("HEAD"), self.fixture.base)
        staged = self.tool.revision_from_index()
        receipt = self.prepare()
        self.assertEqual(receipt["tree"], staged)
        self.assertEqual(self.tool.git("status", "--porcelain"), b"")

    def test_binding_cannot_change_on_resume(self):
        self.prepare()
        with self.assertRaisesRegex(PublicationWorkspaceError, "binding changed"):
            self.prepare(timestamp=1730000001)


class WorkspaceCrashTest(WorkspaceFixture):
    def test_partial_installation_recovers_only_known_old_new_bytes(self):
        original = self.tool._install
        before = {name:(self.root / name).read_bytes() for name in FILES}
        installed = {}
        def interrupt(name, payload, old):
            result = original(name, payload, old)
            self.assertEqual((self.root / name).read_bytes(), payload)
            installed[name] = payload
            if len(installed) == 2:
                raise InterruptedError("fixture")
            return result
        with patch.object(self.tool, "_install", side_effect=interrupt):
            with self.assertRaises(InterruptedError): self.prepare()
        self.assertEqual(len(installed), 2)
        for name in FILES:
            self.assertEqual((self.root / name).read_bytes(), installed.get(name, before[name]))
        self.assertTrue(all(installed[name] != before[name] for name in installed))
        self.assertEqual(self.tool.revision("HEAD"), self.fixture.base)
        self.assertEqual(self.tool.revision_from_index(), self.tool.revision(self.fixture.base + "^{tree}"))
        self.prepare()
        for name, payload in installed.items():
            self.assertEqual((self.root / name).read_bytes(), payload)
        self.assertEqual(self.tool.git("status", "--porcelain"), b"")

    def test_process_death_after_ref_update_resumes_existing_commit(self):
        child = os.fork()
        if child == 0:
            original = self.tool.git
            def crash(*args, **kwargs):
                result = original(*args, **kwargs)
                if args[0] == "update-ref": os._exit(23)
                return result
            with patch.object(self.tool, "git", side_effect=crash):
                self.prepare()
            os._exit(99)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 23)
        committed = self.tool.revision("HEAD")
        self.assertNotEqual(committed, self.fixture.base)
        self.assertEqual(self.prepare()["commit"], committed)
        self.assertEqual(len(self.calls), 1)

class WorkspaceSafetyTest(WorkspaceFixture):
    def test_unrelated_edit_is_preserved_without_ref_change(self):
        filename = self.root / "packages/foundation/module.json"
        raw = filename.read_bytes() + b" \n"
        filename.write_bytes(raw)
        with self.assertRaisesRegex(PublicationWorkspaceError, "unrelated"):
            self.prepare()
        self.assertEqual(filename.read_bytes(), raw)
        self.assertEqual(self.tool.revision("HEAD"), self.fixture.base)

    def test_unrelated_staged_edit_is_preserved(self):
        filename = self.root / "packages/foundation/module.json"
        filename.write_bytes(filename.read_bytes() + b" \n")
        self.tool.git("add", "packages/foundation/module.json")
        staged = self.tool.revision_from_index()
        with self.assertRaisesRegex(PublicationWorkspaceError, "index contains"):
            self.prepare()
        self.assertEqual(self.tool.revision_from_index(), staged)
        self.assertEqual(self.tool.revision("HEAD"), self.fixture.base)

    def test_hidden_tracked_changes_refuse_before_reservation(self):
        name = "packages/foundation/module.json"
        self.tool.git("update-index", "--assume-unchanged", name)
        filename = self.root / name
        filename.write_bytes(filename.read_bytes() + b" \n")
        with self.assertRaisesRegex(PublicationWorkspaceError, "index hides"):
            self.prepare()
        catalogue = json.loads((self.fixture.state / "build-reservations").read_bytes())
        self.assertEqual(catalogue["catalogue"]["reservations"], [])

    def test_checkout_attributes_refuse_before_source_installation(self):
        original = {name:(self.root / name).read_bytes() for name in FILES}
        attributes = self.fixture.root / ".git/info/attributes"
        attributes.write_text("products/lmdj/version.json filter=fixture\n")
        with self.assertRaisesRegex(PublicationWorkspaceError, "checkout-transforming attributes"):
            self.prepare()
        self.assertEqual({name:(self.root / name).read_bytes() for name in FILES}, original)
        self.assertEqual(self.tool.revision("HEAD"), self.fixture.base)

    def test_worktree_config_cannot_redirect_checkout_outside_owned_root(self):
        elsewhere = self.fixture.container / "elsewhere"
        elsewhere.mkdir()
        self.tool.git("config", "extensions.worktreeConfig", "true")
        self.tool.git("config", "--worktree", "core.worktree", str(elsewhere))
        with self.assertRaisesRegex(PublicationWorkspaceError, "effective Git worktree root differs"):
            self.prepare()
        self.assertEqual(list(elsewhere.iterdir()), [])
        catalogue = json.loads((self.fixture.state / "build-reservations").read_bytes())
        self.assertEqual(catalogue["catalogue"]["reservations"], [])

    def test_primary_worktree_refuses_even_on_operation_branch(self):
        primary = CandidateSourceWorkspace(self.fixture.root, self.fixture.tool)
        self.fixture.git("symbolic-ref", "HEAD", "refs/heads/" + self.branch)
        try:
            with self.assertRaisesRegex(PublicationWorkspaceError, "dedicated linked worktree"):
                primary.prepare_source(request=self.request, frozen=self.fixture.frozen,
                    main_revision=self.fixture.base, author_name="Fixture", author_email="fixture@example.invalid",
                    timestamp=1730000000, verify=self.verify)
        finally:
            self.fixture.git("symbolic-ref", "HEAD", "refs/heads/main")

    def test_wrong_branch_refuses(self):
        self.tool.git("symbolic-ref", "HEAD", "refs/heads/main")
        with self.assertRaisesRegex(PublicationWorkspaceError, "branch"):
            self.prepare()

    def test_verifier_drift_cannot_advance_ref(self):
        def drift(root):
            self.verify(root)
            (root / "products/lmdj/version.json").write_bytes(b"unexpected")
        with self.assertRaisesRegex(PublicationWorkspaceError, "file bytes drifted"):
            self.prepare(verify=drift)
        self.assertEqual(self.tool.revision("HEAD"), self.fixture.base)

    def test_verifier_cannot_hide_unrelated_drift_with_index_flags(self):
        filename = self.root / "packages/foundation/module.json"
        def drift(root):
            self.verify(root)
            self.tool.git("update-index", "--assume-unchanged", "packages/foundation/module.json")
            filename.write_bytes(filename.read_bytes() + b" \n")
        with self.assertRaisesRegex(PublicationWorkspaceError, "index hides"):
            self.prepare(verify=drift)
        self.assertEqual(self.tool.revision("HEAD"), self.fixture.base)
        self.assertTrue(filename.read_bytes().endswith(b" \n"))


if __name__ == "__main__":
    unittest.main()
