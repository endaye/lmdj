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
import pr_agent_review as producer
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

    def coverage(self):
        blob = {"object_id": "e" * 40, "sha256": "f" * 64, "byte_length": 7}
        hunk = {"id": "h1", "path": "apps/creator-web/a.ts", "old_path": None,
                "change_kind": "modified", "old_blob": blob, "new_blob": blob,
                "patch": {"sha256": "0" * 64, "byte_length": 7}, "right_lines": [1]}
        return {
            "schema": review.COVERAGE_SCHEMA,
            "identity": {"repository": self.identity["repository"], "pull_request": self.identity["pr_number"],
                          "base_sha": self.identity["base_sha"], "head_sha": self.identity["head_sha"],
                          "control_sha": self.identity["control_sha"], "run_id": str(self.identity["run_id"]),
                          "run_attempt": self.identity["run_attempt"]},
            "engine": {"name": "pr-agent", "source_commit": "1" * 40, "version": "0.45.0",
                        "bundle": {"archive_sha256": "2" * 64, "archive_byte_length": 7,
                                   "manifest_sha256": "3" * 64, "adapter_sha256": "4" * 64,
                                   "default_config_sha256": "5" * 64, "requirements_lock_sha256": "6" * 64,
                                   "stock_tokenizer_asset_sha256": "7" * 64},
                        "runtime_config": {"sha256": "8" * 64, "byte_length": 7}},
            "provider": "deepseek",
            "model": {"requested": "deepseek-v4-pro", "actual": "DeepSeek-V4-Pro-0813",
                       "response_version": "v1", "pricing_revision": "fixture-v1"},
            "input_sha256": "9" * 64, "expected_hunks": [hunk], "observed_hunks": [hunk],
            "remaining_files": [], "failed_chunks": [], "complete": True, "usage": {},
        }

    def v2_attempt(self, coverage=None, *, findings=None):
        payload = copy.deepcopy(self.payload)
        payload["findings"] = findings or []
        return review.observe_attempt_v2(self.policy, identity=self.identity, backend="deepseek",
                                         returncode=0, output=json.dumps(payload), coverage=coverage)

    def test_first_choice_is_glm(self):
        self.assertEqual(review.next_backend(self.policy, []), "glm")

    def test_v2_starts_deepseek_and_preserves_engine_provider_model_identity(self):
        coverage = self.coverage()
        attempt = self.v2_attempt(coverage)
        history = {"schema": review.HISTORY_SCHEMA_V2, "attempts": [attempt]}
        inventory = {review.coverage_digest(coverage): coverage}
        self.assertIsNone(review.next_backend(self.policy, history, identity=self.identity, coverages=inventory))
        self.assertEqual(history["attempts"][0]["provider"], "deepseek")
        self.assertEqual(history["attempts"][0]["model"]["actual"], "DeepSeek-V4-Pro-0813")
        result = review.prepare_result(self.policy, {**self.identity, "backend": "deepseek"},
                                       changed_paths=["apps/creator-web/a.ts"], history=history,
                                       coverages=inventory)
        self.assertEqual(result["status"], "reviewed")

    def test_v2_digest_mismatch_and_out_of_diff_finding_are_refused(self):
        coverage = self.coverage()
        attempt = self.v2_attempt(coverage, findings=[{"path": "apps/creator-web/a.ts", "line": 99, "body": "bad"}])
        history = {"schema": review.HISTORY_SCHEMA_V2, "attempts": [attempt]}
        inventory = {review.coverage_digest(coverage): coverage}
        with self.assertRaisesRegex(review.ReviewScopeError, "RIGHT-side"):
            review.prepare_result(self.policy, {**self.identity, "backend": "deepseek"},
                                  changed_paths=["apps/creator-web/a.ts"], history=history,
                                  coverages=inventory)
        tampered = copy.deepcopy(coverage)
        tampered["model"]["actual"] = "forged-model"
        with self.assertRaisesRegex(review.ReviewScopeError, "digest mismatch"):
            review.validate_history_v2(self.policy, {"schema": review.HISTORY_SCHEMA_V2, "attempts": [self.v2_attempt(coverage)]},
                                       identity=self.identity,
                                       coverages={review.coverage_digest(coverage): tampered})
        with self.assertRaisesRegex(review.ReviewScopeError, "identity is required"):
            review.validate_history_v2(self.policy, history, coverages=inventory)

    def test_v2_consumer_accepts_actual_t2_coverage_receipt_shape(self):
        document = json.loads((ROOT / "tests/fixtures/ci/pr-agent/complete-input.json").read_text())
        authenticated = producer.authenticate_input(document)
        receipt = producer._validate_coverage_receipt(producer._make_coverage(
            authenticated, provider="deepseek",
            model={"requested": "fixture-model", "actual": None,
                   "response_version": None, "pricing_revision": "fixture-v1"},
            prompt=producer.render_prompt_input(authenticated), usage=None))
        self.assertEqual(review.validate_coverage(None, receipt), receipt)
        self.assertTrue(all(type(line) is int for hunk in receipt["expected_hunks"] for line in hunk["right_lines"]))

    def test_rename_inventory_keeps_old_and_new_but_right_anchors_stay_new_only(self):
        coverage = self.coverage()
        hunk = coverage["expected_hunks"][0]
        hunk["path"] = "apps/creator-web/new.ts"
        hunk["old_path"] = "contracts/old.ts"
        hunk["change_kind"] = "renamed"
        paths = review.changed_path_inventory(coverage["expected_hunks"])
        self.assertEqual(paths, ["apps/creator-web/new.ts", "contracts/old.ts"])
        collector = {
            "schema": review.COLLECTOR_SCHEMA,
            "identity": coverage["identity"],
            "input_sha256": coverage["input_sha256"],
            "expected_hunks": copy.deepcopy(coverage["expected_hunks"]),
            "right_inventory": [{"path": "apps/creator-web/new.ts", "line": 1}],
        }
        review.validate_collector(collector, identity=self.identity)
        review.validate_coverage(None, coverage, changed_paths=paths, collector=collector)
        with self.assertRaisesRegex(review.ReviewScopeError, "changed-path inventory"):
            review.validate_coverage(None, coverage, changed_paths=["apps/creator-web/new.ts"], collector=collector)
        forged = copy.deepcopy(collector)
        forged["right_inventory"] = [{"path": "contracts/old.ts", "line": 1}]
        with self.assertRaisesRegex(review.ReviewScopeError, "RIGHT-side inventory"):
            review.validate_collector(forged, identity=self.identity)

    def test_rename_hunk_requires_old_path_and_non_rename_cannot_carry_one(self):
        coverage = self.coverage()
        coverage["expected_hunks"][0]["change_kind"] = "renamed"
        with self.assertRaisesRegex(review.ReviewScopeError, "rename hunk lacks"):
            review.validate_coverage(None, coverage)
        coverage = self.coverage()
        coverage["expected_hunks"][0]["old_path"] = "contracts/old.ts"
        with self.assertRaisesRegex(review.ReviewScopeError, "non-rename hunk carries"):
            review.validate_coverage(None, coverage)

    def test_rename_scope_rejects_extra_path_wrong_old_path_and_forged_rename(self):
        coverage = self.coverage()
        for collection in ("expected_hunks", "observed_hunks"):
            hunk = coverage[collection][0]
            hunk["path"] = "apps/creator-web/new.ts"
            hunk["old_path"] = "contracts/old.ts"
            hunk["change_kind"] = "renamed"
        paths = review.changed_path_inventory(coverage["expected_hunks"])
        collector = {
            "schema": review.COLLECTOR_SCHEMA,
            "identity": coverage["identity"],
            "input_sha256": coverage["input_sha256"],
            "expected_hunks": copy.deepcopy(coverage["expected_hunks"]),
            "right_inventory": [{"path": "apps/creator-web/new.ts", "line": 1}],
        }
        with self.assertRaisesRegex(review.ReviewScopeError, "changed-path inventory"):
            review.validate_coverage(None, coverage, changed_paths=paths + ["forged/extra.ts"], collector=collector)

        wrong_old = copy.deepcopy(coverage)
        wrong_old["expected_hunks"][0]["old_path"] = "contracts/wrong.ts"
        with self.assertRaisesRegex(review.ReviewScopeError, "expected partition"):
            review.validate_coverage(None, wrong_old, changed_paths=paths, collector=collector)

        forged_collector = copy.deepcopy(collector)
        forged_collector["expected_hunks"][0]["old_path"] = "contracts/forged.ts"
        with self.assertRaisesRegex(review.ReviewScopeError, "expected partition"):
            review.validate_coverage(None, coverage, changed_paths=paths, collector=forged_collector)

    def test_rename_scope_rejects_old_side_inline_finding_after_positive_edit(self):
        coverage = self.coverage()
        for collection in ("expected_hunks", "observed_hunks"):
            hunk = coverage[collection][0]
            hunk["path"] = "apps/creator-web/new.ts"
            hunk["old_path"] = "contracts/old.ts"
            hunk["change_kind"] = "renamed"
        collector = {
            "schema": review.COLLECTOR_SCHEMA,
            "identity": coverage["identity"],
            "input_sha256": coverage["input_sha256"],
            "expected_hunks": copy.deepcopy(coverage["expected_hunks"]),
            "right_inventory": [{"path": "apps/creator-web/new.ts", "line": 1}],
        }
        payload = copy.deepcopy(self.payload)
        payload["findings"] = [{"path": "contracts/old.ts", "line": 1, "body": "forged old-side finding"}]
        with self.assertRaisesRegex(review.ReviewScopeError, "not anchored"):
            review.validate_review(self.policy, payload, coverage=coverage,
                                   changed_paths=review.changed_path_inventory(coverage["expected_hunks"]),
                                   collector=collector)

    def test_v2_order_model_and_engine_bind_to_trusted_t2_config(self):
        coverage = self.coverage()
        trusted = {"schema": review.TRUSTED_CONFIG_SCHEMA, "provider_order": ["deepseek", "glm"],
                   "providers": {"deepseek": {"enabled": True, "model": coverage["model"]["requested"]},
                                 "glm": {"enabled": True, "model": "glm-fixture"},
                                 "xai": {"enabled": False}, "kimi": {"enabled": False}},
                   "engine": coverage["engine"]}
        history = {"schema": review.HISTORY_SCHEMA_V2, "attempts": [self.v2_attempt(coverage)]}
        inventory = {review.coverage_digest(coverage): coverage}
        review.validate_history_v2(self.policy, history, identity=self.identity, coverages=inventory,
                                   changed_paths=["apps/creator-web/a.ts"], trusted_config=trusted)
        reordered = copy.deepcopy(history)
        reordered["attempts"][0]["backend"] = "glm"
        with self.assertRaisesRegex(review.ReviewScopeError, "provider identity"):
            review.validate_history_v2(self.policy, reordered, identity=self.identity, coverages=inventory,
                                       changed_paths=["apps/creator-web/a.ts"], trusted_config=trusted)
        forged = copy.deepcopy(coverage)
        forged["model"]["requested"] = "forged-model"
        forged_inventory = {review.coverage_digest(forged): forged}
        forged_history = copy.deepcopy(history)
        forged_history["attempts"][0]["coverage_sha256"] = review.coverage_digest(forged)
        forged_history["attempts"][0]["model"] = forged["model"]
        with self.assertRaisesRegex(review.ReviewScopeError, "trusted T2 configuration"):
            review.validate_history_v2(self.policy, forged_history, identity=self.identity,
                                       coverages=forged_inventory,
                                       changed_paths=["apps/creator-web/a.ts"], trusted_config=trusted)

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

    def test_issue_1062_placeholder_is_invalid_output(self):
        self.payload = {"findings": [], "schema": "lmdj.ci-review-output.v1",
                        "summary": "placeholder",
                        "test_scope": {"labels": ["test:core_ubuntu"], "reason": "placeholder"}}
        self.assertEqual(self.attempt("kimi"), {
            "backend": "kimi", "status": "failed", "error_class": "invalid_output", "review": None})

    def test_placeholder_in_either_field_is_invalid_output(self):
        for field in ("summary", "reason"):
            for value in ("placeholder", "PLACEHOLDER", " \tPlAcEhOlDeR\n"):
                with self.subTest(field=field, value=value):
                    payload = copy.deepcopy(self.payload)
                    target = payload if field == "summary" else payload["test_scope"]
                    target[field] = value
                    result = review.observe_attempt(self.policy, backend="glm", returncode=0,
                                                    output=json.dumps(payload))
                    self.assertEqual(result, {"backend": "glm", "status": "failed",
                                              "error_class": "invalid_output", "review": None})

    def test_placeholder_diagnostic_names_field_and_remedy(self):
        for field in ("summary", "reason"):
            with self.subTest(field=field):
                payload = copy.deepcopy(self.payload)
                target = payload if field == "summary" else payload["test_scope"]
                target[field] = "placeholder"
                with self.assertRaisesRegex(review.ReviewScopeError,
                                            rf"why: .*{field}.*placeholder; remedy: .+"):
                    review.validate_review(self.policy, payload)

    def test_clean_review_with_no_findings_is_reviewed(self):
        self.assertEqual(self.attempt("glm"), {
            "backend": "glm", "status": "reviewed", "error_class": None, "review": self.payload})

    def test_substantive_placeholder_mentions_are_reviewed(self):
        self.payload["summary"] = "Reviewed the placeholder rejection in review_scope.py; no defects found."
        self.payload["test_scope"]["reason"] = "CI protocol tests cover placeholder rejection and clean reviews."
        self.assertEqual(self.attempt("glm"), {
            "backend": "glm", "status": "reviewed", "error_class": None, "review": self.payload})

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
