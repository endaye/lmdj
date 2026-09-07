#!/usr/bin/env python3
"""Protocol tests, not claims of real backend or GitHub write execution."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import review_scope as review
import test_scope


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.policy = test_scope.load_policy(ROOT)
        self.payload = {"schema": review.REVIEW_SCHEMA, "summary": "Reviewed the exact diff.",
                        "findings": [], "test_scope": {"labels": ["test:none"], "reason": "Only explanatory notes."}}
        self.identity = dict(repository="endaye/lmdj", pr_number=7, head_sha="a" * 40,
                             base_sha="b" * 40, control_sha="c" * 40,
                             backend="kimi", run_id=99, run_attempt=1)

    def attempt(self, backend, **kwargs):
        return review.observe_attempt(self.policy, backend=backend, returncode=0,
                                      output=json.dumps(self.payload), **kwargs)

    def test_first_choice_is_glm(self):
        self.assertEqual(review.next_backend(self.policy, []), "glm")

    def test_glm_rate_limit_uses_kimi_and_stops(self):
        history = [self.attempt("glm", error_class="rate_limited")]
        self.assertEqual(review.next_backend(self.policy, history), "kimi")
        history.append(self.attempt("kimi"))
        self.assertIsNone(review.next_backend(self.policy, history))

    def test_two_failures_use_grok(self):
        history = [self.attempt("glm", error_class="service_error"), self.attempt("kimi", error_class="timeout")]
        self.assertEqual(review.next_backend(self.policy, history), "grok")
        history.append(self.attempt("grok"))
        self.assertIsNone(review.next_backend(self.policy, history))

    def test_findings_are_success_and_do_not_retry_for_clean(self):
        self.payload["findings"] = [{"path": "apps/creator-web/a.ts", "line": 1, "body": "Fix the unsafe access."}]
        result = self.attempt("glm")
        self.assertEqual(result["status"], "reviewed")
        self.assertIsNone(review.next_backend(self.policy, [result]))

    def test_valid_model_claim_cannot_override_failed_process(self):
        result = review.observe_attempt(self.policy, backend="glm", returncode=1, output=json.dumps(self.payload))
        self.assertEqual(result["error_class"], "runtime_failure")
        self.assertIsNone(result["review"])

    def test_unknown_labels_are_backend_failure(self):
        self.payload["test_scope"]["labels"] = ["test:invented"]
        self.assertEqual(self.attempt("glm")["error_class"], "invalid_output")

    def test_empty_advice_is_backend_failure(self):
        self.payload["test_scope"]["labels"] = []
        self.assertEqual(self.attempt("glm")["error_class"], "invalid_output")

    def test_partial_findings_are_not_a_valid_review(self):
        self.payload["findings"] = [{"path": "a"}]
        self.assertEqual(self.attempt("glm")["status"], "failed")

    def test_duplicate_json_is_not_accepted(self):
        text = json.dumps(self.payload)[:-1] + ', "summary": "clean"}'
        result = review.observe_attempt(self.policy, backend="glm", returncode=0, output=text)
        self.assertEqual(result["error_class"], "invalid_output")

    def test_failure_output_never_echoes_secret(self):
        result = review.observe_attempt(self.policy, backend="glm", returncode=1, output="secret-token-example")
        self.assertNotIn("secret-token-example", json.dumps(result))

    def test_illegal_error_diagnostic_does_not_echo_input(self):
        with self.assertRaisesRegex(review.ReviewScopeError, "unknown backend error category") as raised:
            self.attempt("glm", error_class="secret-token-example")
        self.assertNotIn("secret-token-example", str(raised.exception))

    def test_retry_after_success_is_rejected(self):
        with self.assertRaisesRegex(review.ReviewScopeError, "stop the fallback"):
            review.next_backend(self.policy, [self.attempt("glm"), self.attempt("kimi")])

    def test_wrong_backend_order_is_rejected(self):
        with self.assertRaisesRegex(review.ReviewScopeError, "fallback order"):
            review.next_backend(self.policy, [self.attempt("kimi")])

    def test_every_documented_failure_category_allows_next_backend(self):
        for error in review.ERRORS:
            with self.subTest(error=error):
                self.assertEqual(review.next_backend(self.policy, [self.attempt("glm", error_class=error)]), "kimi")

    def test_total_failure_is_structured_not_reviewed(self):
        history = [self.attempt(b, error_class="missing_credential") for b in review.BACKENDS]
        result = review.failure_document(self.policy, {**self.identity, "backend": "deterministic"}, history)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual([a["backend"] for a in result["attempts"]], list(review.BACKENDS))
        self.assertEqual(result["head_sha"], self.identity["head_sha"])
        self.assertEqual(result["control_sha"], self.identity["control_sha"])
        self.assertIn("request_id", result)
        self.assertIn("remedy", result)

    def test_failure_request_identity_is_stable_and_attempt_bound(self):
        history = [self.attempt(b, error_class="service_error") for b in review.BACKENDS]
        identity = {**self.identity, "backend": "deterministic"}
        first = review.failure_document(self.policy, identity, history)
        self.assertEqual(review.failure_document(self.policy, identity, history), first)
        later = review.failure_document(self.policy, {**identity, "run_attempt": 2}, history)
        self.assertNotEqual(first["request_id"], later["request_id"])

    def test_partial_chain_cannot_claim_all_failed(self):
        with self.assertRaisesRegex(review.ReviewScopeError, "every backend"):
            review.failure_document(self.policy, {**self.identity, "backend": "deterministic"},
                                    [self.attempt("glm", error_class="timeout")])

    def test_unknown_review_field_rejected(self):
        self.payload["trusted"] = True
        with self.assertRaisesRegex(review.ReviewScopeError, "schema is not closed"):
            review.validate_review(self.policy, self.payload)

    def test_boolean_finding_line_rejected(self):
        self.payload["findings"] = [{"path": "file", "line": True, "body": "Fix it"}]
        with self.assertRaisesRegex(review.ReviewScopeError, "positive integer"):
            review.validate_review(self.policy, self.payload)

    def test_publication_keeps_rule_floor_and_legacy_review(self):
        output = review.prepare_publication(self.policy, self.identity, changed_paths=["contracts/a.json"], review=self.payload)
        self.assertEqual(output["labels"], ["test:full"])
        self.assertEqual(output["record"]["effective"]["kind"], "full")
        self.assertEqual(set(output["review"]), {"summary", "findings"})

    def test_same_head_records_union_advice(self):
        previous = test_scope.build_record(self.policy, changed_paths=["docs/notes/a.md"],
                                           ai_labels=["test:creator"], **{**self.identity, "backend": "glm"})
        output = review.prepare_publication(self.policy, self.identity, changed_paths=["docs/notes/a.md"],
                                             review=self.payload, previous_records=[previous])
        self.assertIn("test:creator", output["labels"])

    def test_old_head_cannot_be_combined_with_new_head(self):
        previous = test_scope.build_record(self.policy, changed_paths=["docs/notes/a.md"], **{**self.identity, "head_sha": "d" * 40})
        with self.assertRaisesRegex(review.ReviewScopeError, "different targets"):
            review.prepare_publication(self.policy, self.identity, changed_paths=["docs/notes/a.md"],
                                       review=self.payload, previous_records=[previous])

    def test_result_binds_actual_successful_backend(self):
        history = [self.attempt("glm", error_class="rate_limited"), self.attempt("kimi")]
        result = review.prepare_result(self.policy, self.identity, changed_paths=["contracts/a"], history=history)
        self.assertEqual(result["publication"]["record"]["backend"], "kimi")
        with self.assertRaisesRegex(review.ReviewScopeError, "backend identity mismatch"):
            review.prepare_result(self.policy, {**self.identity, "backend": "glm"}, changed_paths=[], history=history)

    def test_failed_result_keeps_floor_without_publishing_fake_review(self):
        history = [self.attempt(b, error_class="timeout") for b in review.BACKENDS]
        result = review.prepare_result(self.policy, {**self.identity, "backend": "deterministic"},
                                       changed_paths=["contracts/a"], history=history)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["publication"]["record"]["effective"]["kind"], "full")
        self.assertIsNone(result["publication"]["review"])

    def test_nonterminal_result_is_rejected(self):
        with self.assertRaisesRegex(review.ReviewScopeError, "not terminal"):
            review.prepare_result(self.policy, self.identity, changed_paths=[],
                                   history=[self.attempt("glm", error_class="timeout")])

    def test_all_failed_preserves_prior_valid_full_scope(self):
        paths = ["docs/notes/a.md"]
        previous = test_scope.build_record(self.policy, changed_paths=paths,
                                          ai_labels=["test:full"], **self.identity)
        result = review.prepare_result(
            self.policy, {**self.identity, "backend": "deterministic"}, changed_paths=paths,
            history=[self.attempt(b, error_class="timeout") for b in review.BACKENDS],
            previous_records=[previous])
        self.assertEqual(result["publication"]["record"]["effective"]["kind"], "full",
                         "why: backend outage erased previous valid scope; remedy: union prior records on failure too")
        self.assertEqual(result["status"], "not-reviewed")
        self.assertIsNone(result["publication"]["review"])

    def test_all_failed_rejects_previous_record_from_other_head(self):
        previous = test_scope.build_record(
            self.policy, changed_paths=["docs/notes/a.md"],
            **{**self.identity, "head_sha": "d" * 40})
        with self.assertRaisesRegex(review.ReviewScopeError, "different targets"):
            review.prepare_result(
                self.policy, {**self.identity, "backend": "deterministic"},
                changed_paths=["docs/notes/a.md"],
                history=[self.attempt(b, error_class="timeout") for b in review.BACKENDS],
                previous_records=[previous])


class IdentityTests(unittest.TestCase):
    def setUp(self):
        ReviewTests.setUp(self)
        # Shape checked read-only against run 34137678442/jobs on 2026-09-08:
        # real jobs include run_id and run_attempt (not shown in docs sample).
        self.context = dict(
            run={"id": 99, "run_attempt": 1, "workflow_id": 42, "event": "workflow_dispatch",
                 "head_sha": "c" * 40, "head_branch": "main", "name": "arbitrary display title",
                 "repository": {"id": 5, "full_name": "endaye/lmdj"}},
            workflow={"id": 42, "path": ".github/workflows/pr-review.yml"},
            producer_job={"run_id": 99, "run_attempt": 1, "name": "Review fallback", "status": "completed", "conclusion": "success"},
            pull={"number": 7, "state": "open", "draft": False, "merged": False,
                  "head": {"sha": "a" * 40, "repo": {"id": 5, "full_name": "endaye/lmdj"}},
                  "base": {"ref": "main", "sha": "b" * 40}},
            repository_id=5, workflow_id=42, producer_job_name="Review fallback",
            control_is_main_history=True, run_workflow_bytes=b"trusted workflow", control_workflow_bytes=b"trusted workflow")

    def test_exact_context_accepts_dynamic_title(self):
        self.assertEqual(review.authenticate_context(self.identity, **self.context), self.identity)

    def test_changed_workflow_cannot_self_certify(self):
        self.context["run_workflow_bytes"] = b"malicious producer"
        with self.assertRaisesRegex(review.ReviewScopeError, "differs from trusted"):
            review.authenticate_context(self.identity, **self.context)

    def test_workflow_numeric_identity_not_title_is_authority(self):
        self.context["run"]["workflow_id"] = 999
        with self.assertRaisesRegex(review.ReviewScopeError, "resolved review workflow"):
            review.authenticate_context(self.identity, **self.context)

    def test_old_head_is_rejected_before_publication(self):
        self.context["pull"]["head"]["sha"] = "e" * 40
        with self.assertRaisesRegex(review.ReviewScopeError, "stale"):
            review.authenticate_context(self.identity, **self.context)

    def test_failed_producer_is_not_model_success(self):
        self.context["producer_job"]["conclusion"] = "failure"
        with self.assertRaisesRegex(review.ReviewScopeError, "producer job"):
            review.authenticate_context(self.identity, **self.context)

    def test_previous_run_attempt_is_rejected(self):
        self.context["producer_job"]["run_attempt"] = 2
        with self.assertRaisesRegex(review.ReviewScopeError, "producer job"):
            review.authenticate_context(self.identity, **self.context)

    def test_untrusted_control_is_rejected(self):
        self.context["control_is_main_history"] = False
        with self.assertRaisesRegex(review.ReviewScopeError, "main history"):
            review.authenticate_context(self.identity, **self.context)

    def test_fork_repository_id_is_rejected(self):
        self.context["pull"]["head"]["repo"]["id"] = 88
        with self.assertRaisesRegex(review.ReviewScopeError, "fork head"):
            review.authenticate_context(self.identity, **self.context)

    def test_pr_event_requires_exact_associated_head(self):
        self.context["run"]["event"] = "pull_request"
        self.context["run"]["pull_requests"] = [{"number": 7, "head": {"sha": "a" * 40}}]
        self.assertEqual(review.authenticate_context(self.identity, **self.context), self.identity)
        self.context["run"]["pull_requests"][0]["head"]["sha"] = "b" * 40
        with self.assertRaisesRegex(review.ReviewScopeError, "bound to the reviewed head"):
            review.authenticate_context(self.identity, **self.context)


if __name__ == "__main__":
    unittest.main()
