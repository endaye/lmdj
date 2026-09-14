#!/usr/bin/env python3
"""Actual bare-Git observation/adoption; no remote write from observe."""
import json
import os
import unittest
from unittest.mock import patch

import release_candidate_branch_test as fixture
from tools.release.candidate_branch import CandidateBranch
from tools.release.evidence_branch import EvidenceBranchError
from tools.release.evidence_pr import EvidencePrError
from tools.release.orchestration import JournalError, RequestJournal


class ObservationTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CandidateBranchTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.controller = CandidateBranch(self.f.journal, self.f.repo, token="SECRET-TOKEN", authorize=self.f.authorize)
        self.controller.api = self.f.api

    def call(self, method, **kwargs):
        with patch.object(fixture.fixture.module.subprocess, "run", side_effect=self.f.transport):
            return getattr(self.controller, method)(self.f.spec, **kwargs)

    def test_initialization_observation_and_guarded_push_have_separate_effects(self):
        self.assertEqual(self.call("observe")["status"], "unknown")
        self.assertFalse((self.f.journal / "branch-state.json").exists())
        self.assertEqual(self.call("observe", initialize=True)["status"], "absent")
        self.assertEqual(self.f.pushes, 0)
        pushed = self.call("advance", require_initialized=True)
        self.assertEqual(pushed["status"], "verified")
        self.assertEqual(self.call("observe"), pushed)
        self.assertEqual(self.f.remote_sha(), self.f.spec["head_sha"])
        self.assertEqual(self.f.pushes, 1)

    def test_missing_started_child_is_unknown_even_with_an_exact_remote_ref(self):
        self.call("observe", initialize=True)
        self.call("advance", require_initialized=True)
        (self.f.journal / "branch-state.json").unlink()
        self.assertEqual(self.call("observe")["status"], "unknown")
        self.assertEqual(self.call("advance", require_initialized=True)["status"], "unknown")
        self.assertFalse((self.f.journal / "branch-state.json").exists())
        self.assertEqual(self.f.pushes, 1)

    def test_observed_adoption_survives_final_authority_failure_and_remote_deletion(self):
        self.f.git("-C", str(self.f.repo), "push", str(self.f.remote), self.f.spec["head_sha"] + ":" + self.f.ref)
        self.f.fail_auth = 2
        self.assertEqual(self.call("observe", initialize=True)["status"], "unknown")
        self.assertTrue(json.loads((self.f.journal / "branch-state.json").read_bytes())["claimed"])
        self.f.fail_auth = None
        self.f.git("--git-dir=" + str(self.f.remote), "update-ref", "-d", self.f.ref)
        self.assertEqual(self.call("observe")["status"], "unknown")
        self.assertEqual(self.call("advance", require_initialized=True)["status"], "unknown")
        self.assertEqual(self.f.pushes, 0)

    def test_late_push_result_is_observed_without_another_push(self):
        self.call("observe", initialize=True)
        self.f.mode = "before"
        self.assertEqual(self.call("advance", require_initialized=True)["status"], "unknown")
        self.f.mode = None
        self.assertEqual(self.call("observe")["status"], "unknown")
        self.f.git("-C", str(self.f.repo), "push", str(self.f.remote), self.f.spec["head_sha"] + ":" + self.f.ref)
        self.assertEqual(self.call("observe")["status"], "verified")
        self.assertEqual(self.f.pushes, 1)

    def test_rebound_child_is_not_reinitialized_by_observation(self):
        self.call("observe", initialize=True)
        before = (self.f.journal / "branch-state.json").read_bytes()
        self.f.spec["task_evidence_sha256"] = "f" * 64
        with self.assertRaises(EvidenceBranchError):
            self.call("observe", initialize=True)
        self.assertEqual((self.f.journal / "branch-state.json").read_bytes(), before)
        self.assertEqual(self.f.pushes, 0)

    def test_oversized_document_observation_cannot_enroll(self):
        self.f.spec["product_build"] = "1" * 20000 + ".0.0.0"
        with self.assertRaises(EvidencePrError):
            self.call("observe", initialize=True)
        self.assertFalse(self.f.journal.exists())
        self.assertEqual(self.f.auths, 0)
        self.assertEqual(self.f.pushes, 0)

    def test_explicit_initialization_cannot_recreate_missing_enrolled_state(self):
        self.call("observe", initialize=True)
        (self.f.journal / "branch-state.json").unlink()
        with self.assertRaisesRegex(EvidenceBranchError, "enrolled.*state is missing"):
            self.call("observe", initialize=True)
        self.assertFalse((self.f.journal / "branch-state.json").exists())
        self.assertEqual(self.f.pushes, 0)

    def test_child_writer_is_rechecked_after_parent_guard(self):
        self.call("observe", initialize=True)
        def guard():
            (self.f.journal / "writer.lock").rename(self.f.journal / "retained.lock")
            fd = os.open(self.f.journal / "writer.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        self.assertEqual(self.call("advance", require_initialized=True, before_write=guard)["status"], "unavailable")
        self.assertEqual(self.call("observe")["status"], "unknown")
        self.assertEqual(self.f.pushes, 0)

    def test_parent_guard_own_error_type_is_sanitized_and_not_replayed(self):
        self.call("observe", initialize=True)
        def guard():
            raise EvidenceBranchError("SECRET-GUARD")
        self.assertEqual(self.call("advance", require_initialized=True, before_write=guard),
                         {"status":"unavailable", "evidence":None})
        self.assertEqual(self.call("advance", require_initialized=True)["status"], "unknown")
        self.assertEqual(self.f.pushes, 0)

    def test_observation_respects_the_existing_writer_lock(self):
        self.call("observe", initialize=True)
        with RequestJournal(self.f.journal):
            with self.assertRaises(JournalError):
                self.call("observe")
        self.assertEqual(self.f.pushes, 0)


if __name__ == "__main__":
    unittest.main()
