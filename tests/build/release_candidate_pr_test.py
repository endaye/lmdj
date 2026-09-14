#!/usr/bin/env python3
"""Candidate policy on the same real durable PR/HTTP transport lifecycle."""
from copy import deepcopy
import unittest

import release_evidence_pr_test as fixture
from tools.release.candidate_pr import CandidatePullRequest, pr_document, validate_spec
from tools.release.evidence_pr import EvidencePrError, validate_spec as validate_publication
from tools.release.github_api import GitHubApiError
from tools.release.model import canonical_sha256


class CandidatePrTest(fixture.PrTest):
    def setUp(self):
        super().setUp()
        self.publication_spec = deepcopy(self.spec)
        self.publication_document = deepcopy(self.document)
        self.spec.pop("tag")
        self.spec.pop("target_revision")
        self.spec.update(product_build="1.0.42.0", source_sha="d" * 40,
                         cut_binding_sha256="6" * 64, snapshot_sha256="7" * 64)
        self.spec["operation_id"] = canonical_sha256({"request":self.spec["request_sha256"], "step":"candidate"})
        self.document = pr_document(self.spec)
        self.controller = self.new_controller()

    def new_controller(self):
        return CandidatePullRequest(self.root, api=self.client.candidate_pr_request,
            authorize=self.authorize, review=self.review, verify_merged=self.verify_merged)

    def test_oversized_generated_document_is_rejected_before_enrollment(self):
        self.spec["product_build"] = "1" * 10000 + ".0.0.0"
        for invoke in (lambda: self.controller.observe(self.spec, initialize=True),
                       lambda: self.controller.advance(self.spec)):
            with self.assertRaisesRegex(EvidencePrError, "document.*transport"):
                invoke()
            self.assertFalse(self.root.exists(), "local validation must precede enrollment")
            self.assertEqual(self.calls, [], "invalid document must not reach HTTP")

    def test_largest_generated_document_within_transport_bound_is_sent(self):
        self.spec["product_build"] = "1.0.0.0"
        baseline = len(pr_document(self.spec)["body"])
        digits = 1 + (20000 - baseline) // 2  # Build appears twice in the body.
        self.spec["product_build"] = "1" * digits + ".0.0.0"
        self.document = pr_document(self.spec)
        self.assertLessEqual(len(self.document["body"]), 20000)
        self.assertGreater(len(self.document["body"]) + 2, 20000)
        self.assertEqual(self.controller.advance(self.spec)["status"], "verified")
        posted = [body for method, _, body in self.calls if method == "POST"]
        self.assertEqual(posted, [self.document])

    def test_body_declares_required_task_checks_without_closing_issues(self):
        self.assertEqual(fixture.check_pr_body(self.document["body"]), [])
        for command in ("scripts/docs-site.sh check", "python3 tests/build/ci_change_scope_test.py", "git diff --cached --check"):
            self.assertIn(command, self.document["body"])
        self.assertIn("/versions/1.0.42.0/", self.document["body"])
        self.assertNotIn("releases/tag/", self.document["body"])
        self.assertNotIn("target_revision", self.spec)
        self.assertEqual(self.document["head"], "feat/release-candidate-" + self.spec["operation_id"])

    def test_candidate_and_publication_scopes_cannot_cross(self):
        with self.assertRaises(EvidencePrError):
            validate_spec(self.publication_spec)
        with self.assertRaises(EvidencePrError):
            validate_publication(self.spec)
        for api, document in ((self.client.candidate_pr_request, self.publication_document),
                              (self.client.release_pr_request, self.document)):
            with self.assertRaises(GitHubApiError):
                api("POST", "/pulls", document)
            with self.assertRaises(GitHubApiError):
                api("GET", "/git/ref/heads/" + document["head"])
        self.assertFalse(self.calls)

    def test_transport_does_not_offer_other_mutations(self):
        super().test_transport_does_not_offer_other_mutations()
        for method, route, body in (("DELETE", "/pulls/99", None), ("PATCH", "/pulls/99", {}),
            ("PUT", "/pulls/99/merge", {"sha":"b" * 40, "merge_method":"merge"}),
            ("POST", "/pulls", dict(self.document, base="other")),
            ("GET", "/pulls?state=open", None), ("GET", "https://foreign.invalid", None)):
            with self.assertRaises(GitHubApiError):
                self.client.candidate_pr_request(method, route, body)
        self.assertFalse(self.calls)

    def test_wrong_request_operation_or_nonzero_patch_cannot_write(self):
        for field, value in (("operation_id", "8" * 64), ("product_build", "1.0.42.1"),
                             ("source_sha", self.spec["head_sha"]), ("product_build", "01.0.42.0")):
            with self.subTest(field=field, value=value), self.assertRaises(EvidencePrError):
                self.advance(**{field:value})
        self.assertFalse(self.calls)

    def test_observation_is_read_only_and_missing_initialized_state_is_unknown(self):
        self.assertEqual(self.controller.observe(self.spec)["status"], "unknown")
        self.assertEqual(self.controller.observe(self.spec, initialize=True)["status"], "absent")
        self.assertFalse(self.writes())
        self.review_state = "pending"
        self.controller.advance(self.spec, require_initialized=True)
        self.assertEqual(self.controller.observe(self.spec)["status"], "pending")
        self.assertEqual(len(self.writes()), 1)
        (self.root / "pr-state.json").unlink()
        self.assertEqual(self.controller.observe(self.spec)["status"], "unknown")
        self.assertEqual(self.controller.advance(self.spec, require_initialized=True)["status"], "unknown")
        self.assertEqual(len(self.writes()), 1)


if __name__ == "__main__":
    unittest.main()
