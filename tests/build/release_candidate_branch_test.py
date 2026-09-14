#!/usr/bin/env python3
"""Same real-Git lifecycle and faults under the closed candidate branch policy."""
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

import release_evidence_branch_test as fixture
from tools.release.candidate_branch import CandidateBranch
from tools.release.candidate_pr import pr_document
from tools.release.evidence_pr import EvidencePrError
from tools.release.evidence_branch import EvidenceBranchError, PublicationBranch
from tools.release.model import canonical_sha256
from tools.release.orchestration import RequestJournal


class CandidateBranchTest(fixture.BranchTest):
    def setUp(self):
        super().setUp()
        self.publication_spec = deepcopy(self.spec)
        self.spec.pop("tag")
        self.spec.pop("target_revision")
        self.spec.update(product_build="1.0.42.0", source_sha="d" * 40,
                         cut_binding_sha256="6" * 64, snapshot_sha256="7" * 64)
        self.bind_operation()

    def bind_operation(self):
        self.spec["operation_id"] = canonical_sha256({"request":self.spec["request_sha256"], "step":"candidate"})
        self.ref = "refs/heads/" + pr_document(self.spec)["head"]

    def advance(self, spec=None):
        controller = CandidateBranch(self.journal, self.repo, token="SECRET-TOKEN", authorize=self.authorize)
        controller.api = self.api
        with patch.object(fixture.module.subprocess, "run", side_effect=self.transport):
            return controller.advance(self.spec if spec is None else spec)

    def test_scope_rebound_and_corruption_refused(self):
        self.assertEqual(self.advance()["status"], "verified")
        with self.assertRaises(EvidenceBranchError):
            self.advance(dict(self.spec, task_evidence_sha256="f" * 64))
        (self.journal / "branch-state.json").write_bytes(b"{broken SECRET}")
        with self.assertRaisesRegex(EvidenceBranchError, "state is invalid"):
            self.advance()

    def test_oversized_document_refused_before_enrollment(self):
        with self.assertRaisesRegex(EvidencePrError, "document.*transport bounds"):
            self.advance(dict(self.spec, product_build="1" * 20000 + ".0.0.0"))
        self.assertFalse(self.journal.exists())
        self.assertEqual(self.auths, 0)
        self.assertEqual(self.pushes, 0)
        self.assertEqual(self.git("--git-dir=" + str(self.remote), "for-each-ref"), "")

    def test_oversized_state_does_not_replace_recoverable_journal(self):
        self.mode = "before"
        self.advance()
        filename = self.journal / "branch-state.json"
        original = filename.read_bytes()
        inventory = sorted(p.name for p in self.journal.iterdir())
        with RequestJournal(self.journal) as journal:
            value = json.loads(original)
            value["spec"]["product_build"] = "1" * 65536 + ".0.0.0"
            with self.assertRaisesRegex(EvidenceBranchError, "state exceeds"):
                PublicationBranch._save(journal, value)
        self.assertEqual(filename.read_bytes(), original)
        self.assertEqual(sorted(p.name for p in self.journal.iterdir()), inventory)

    def test_real_controller_death_before_and_after_remote_effect(self):
        for mode, code in (("death-before", 31), ("death-after", 32)):
            with self.subTest(mode=mode):
                self.journal = self.root / mode
                self.spec["request_sha256"] = ("4" if code == 31 else "5") * 64
                self.bind_operation()
                pid = os.fork()
                if pid == 0:
                    self.mode = mode
                    self.advance()
                    os._exit(99)
                _, child_status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(child_status), code)
                self.assertEqual(self.advance()["status"], "unknown" if code == 31 else "verified")
                self.assertEqual(self.pushes, 0)

    def test_cross_scope_and_source_as_cut_rejected_before_transport(self):
        with self.assertRaises(EvidencePrError):
            self.advance(self.publication_spec)
        with self.assertRaises(EvidencePrError):
            self.advance(dict(self.spec, head_sha=self.spec["source_sha"]))
        publisher = PublicationBranch(self.journal, self.repo, token="SECRET-TOKEN", authorize=self.authorize)
        with self.assertRaises(EvidencePrError):
            publisher.advance(self.spec)
        self.assertEqual(self.pushes, 0)
        self.assertEqual(self.auths, 0)


if __name__ == "__main__":
    unittest.main()
