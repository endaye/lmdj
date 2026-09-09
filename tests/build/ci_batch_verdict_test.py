#!/usr/bin/env python3
"""Pure new-schema semantics; no assertion of remote execution/provenance."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import batch_verdict as verdict
import self_test
import self_test_evidence
import test_scope


class VerdictTest(unittest.TestCase):
    def setUp(self):
        self.policy = test_scope.load_policy(ROOT)
        self.identity = {"request_id": "request-1", "request_kind": "auto", "base_sha": "a" * 40,
                         "target_sha": "b" * 40, "control_sha": "c" * 40,
                         "policy_digest": self.policy.digest, "run_id": 17, "run_attempt": 1}
        self.selection = test_scope._selection(self.policy, ["core_coverage"], ["changed coverage tooling"])

    def row(self, suite="core_coverage", job="core-coverage", **changes):
        return {"suite": suite, "job": job, "run_id": 17, "run_attempt": 1,
                "target_revision": "b" * 40, "conclusion": "success", **changes}

    def build(self, rows=None):
        return verdict.build(self.policy, self.identity, self.selection,
                             [self.row()] if rows is None else rows)

    def suite(self, document, name="core_coverage"):
        return next(suite for suite in document["suites"] if suite["id"] == name)

    def validate(self, document):
        return verdict.validate(document, self.policy, self.identity, self.selection)

    def rehash(self, document):
        document["evidence_digest"] = self_test.digest_of({k: v for k, v in document.items() if k != "evidence_digest"})

    def test_focused_reports_all_suites_without_fake_passes(self):
        document = self.build()
        self.assertEqual(len(document["suites"]), 16, "why: report omitted policy suites; remedy: enumerate full inventory")
        self.assertEqual(sum(suite["status"] == "not-selected" for suite in document["suites"]), 15,
                         "why: omitted work became passes; remedy: explicit not-selected")

    def test_focused_outcomes_only_selected(self):
        document = self.build()
        self.assertEqual(verdict.scheduler_outcomes(document, self.policy, self.identity, self.selection),
                         {"core_coverage": "passed"}, "why: nonselected sent as scheduler success; remedy: filter by selection")

    def test_none_is_not_required_not_passed(self):
        self.selection = test_scope._selection(self.policy, [], ["explanatory documentation"])
        document = self.build([])
        self.assertEqual(document["status"], "not-required", "why: empty run counted green; remedy: record not-required")
        self.assertEqual(verdict.scheduler_outcomes(document, self.policy, self.identity, self.selection), {},
                         "why: none invented tested suites; remedy: keep outcomes empty")

    def test_none_refuses_job_observations(self):
        self.selection = test_scope._selection(self.policy, [], ["explanatory documentation"])
        with self.assertRaisesRegex(verdict.VerdictError, "unselected"):
            self.build()

    def test_missing_all_selected_jobs_is_debt(self):
        document = self.build([])
        self.assertEqual(self.suite(document)["scheduler_outcome"], "missing",
                         "why: empty selected batch lost obligation; remedy: retain missing debt")

    def test_dependency_blocked_is_debt(self):
        document = self.build([self.row(conclusion="skipped", blocked_by="configure")])
        self.assertEqual(self.suite(document)["scheduler_outcome"], "blocked",
                         "why: blocked build treated as pass; remedy: preserve dependent test debt")

    def test_runner_failure_is_infrastructure_debt(self):
        document = self.build([self.row(conclusion="failure", infrastructure_failure=True)])
        self.assertEqual(self.suite(document)["scheduler_outcome"], "infrastructure",
                         "why: host failure treated as covered test; remedy: repair infrastructure")

    def test_cancelled_is_debt(self):
        document = self.build([self.row(conclusion="cancelled")])
        self.assertEqual(self.suite(document)["scheduler_outcome"], "cancelled",
                         "why: cancellation dropped debt; remedy: preserve unexecuted work")

    def test_timeout_is_debt(self):
        document = self.build([self.row(conclusion="timed_out")])
        self.assertTrue(self.suite(document)["verification_debt"], "why: timeout claimed coverage; remedy: retain debt")

    def test_failed_evidence_upload_is_debt(self):
        document = self.build([self.row(artifact="failed")])
        self.assertEqual(self.suite(document)["status"], "infrastructure_failure",
                         "why: missing artifact became reusable pass; remedy: preserve evidence failure")

    def test_real_failure_is_reported_without_invented_debt(self):
        document = self.build([self.row(conclusion="failure")])
        suite = self.suite(document)
        self.assertEqual((suite["scheduler_outcome"], suite["failures"], suite["verification_debt"]),
                         ("failed", ["core-coverage"], False), "why: product failure misclassified; remedy: retain test result")

    def test_frozen_selection_cannot_omit_transitive_consumers(self):
        self.selection = test_scope._selection(self.policy, ["core_ubuntu"], ["incomplete Core scope"])
        with self.assertRaisesRegex(verdict.VerdictError, "transitive consumers"):
            self.build([])

    def macos_rows(self):
        self.selection = test_scope._selection(self.policy, ["core_macos"], ["macOS changes"])
        return [self.row("core_macos", job) for job in self.policy.inventory.suite("core_macos").jobs]

    def test_macos_alternative_success_satisfies_primary_skip(self):
        rows = self.macos_rows()
        next(row for row in rows if row["job"] == "macos-primary")["conclusion"] = "skipped"
        rows.append(self.row("core_macos", "macos-fallback"))
        self.assertEqual(self.suite(self.build(rows), "core_macos")["status"], "passed",
                         "why: canonical alternative lost; remedy: reuse full-policy suite judge")

    def test_macos_skip_without_alternative_is_not_pass(self):
        rows = self.macos_rows()
        next(row for row in rows if row["job"] == "macos-primary")["conclusion"] = "skipped"
        self.assertEqual(self.suite(self.build(rows), "core_macos")["scheduler_outcome"], "infrastructure",
                         "why: unwitnessed skip green; remedy: require actual same-run fallback")

    def test_failed_alternative_evidence_cannot_supply_success(self):
        rows = self.macos_rows()
        next(row for row in rows if row["job"] == "macos-primary")["conclusion"] = "skipped"
        rows.append(self.row("core_macos", "macos-fallback", artifact="failed"))
        self.assertEqual(self.suite(self.build(rows), "core_macos")["status"], "infrastructure_failure",
                         "why: lost fallback evidence counted pass; remedy: preserve artifact debt")

    def test_mixed_test_failure_and_missing_preserves_both(self):
        rows = self.macos_rows()
        rows = [row for row in rows if row["job"] != "core-asan-macos"]
        next(row for row in rows if row["job"] == "core-macos")["conclusion"] = "failure"
        suite = self.suite(self.build(rows), "core_macos")
        self.assertEqual((suite["status"], suite["scheduler_outcome"], suite["failures"]),
                         ("test_failure", "missing", ["core-macos"]),
                         "why: failure hid unexecuted sanitizer; remedy: separate defect and verification debt")

    def test_mixed_test_failure_and_blocked_preserves_both(self):
        rows = self.macos_rows()
        next(row for row in rows if row["job"] == "core-macos")["conclusion"] = "failure"
        next(row for row in rows if row["job"] == "core-asan-macos").update(
            conclusion="skipped", blocked_by="configure-asan")
        suite = self.suite(self.build(rows), "core_macos")
        self.assertEqual((suite["scheduler_outcome"], suite["failures"]), ("blocked", ["core-macos"]),
                         "why: failed Core erased blocked sanitizer; remedy: retain both channels")

    def test_full_reuses_all_suites_including_stress(self):
        self.selection = test_scope._selection(self.policy, self.policy.suite_ids, ["full"])
        rows = [self.row(suite.id, job) for suite in self.policy.inventory.suites for job in suite.jobs]
        document = self.build(rows)
        self.assertEqual(document["status"], "passed", "why: complete observations did not aggregate; remedy: follow full inventory")
        self.assertEqual({suite["id"] for suite in document["suites"]}, set(self.policy.suite_ids),
                         "why: full dropped stress suites; remedy: use canonical inventory")

    def test_wrong_observation_identity_is_invalid(self):
        for changes in ({"run_id": 18}, {"run_attempt": 2}, {"target_revision": "e" * 40}):
            with self.subTest(changes=changes), self.assertRaises(verdict.VerdictError):
                self.build([self.row(**changes)])

    def test_duplicate_job_is_invalid(self):
        with self.assertRaisesRegex(verdict.VerdictError, "observed twice"):
            self.build([self.row(), self.row()])

    def test_unknown_job_is_invalid(self):
        with self.assertRaisesRegex(verdict.VerdictError, "not in the self-test policy"):
            self.build([self.row(job="invented-job")])

    def test_unknown_suite_is_invalid(self):
        with self.assertRaisesRegex(verdict.VerdictError, "unknown suite"):
            self.build([self.row(suite="invented-suite")])

    def test_wrong_job_owner_is_invalid(self):
        with self.assertRaisesRegex(verdict.VerdictError, "belongs to"):
            self.build([self.row(job="core-asan")])

    def test_unknown_conclusion_is_invalid(self):
        with self.assertRaises(verdict.VerdictError):
            self.build([self.row(conclusion="neutral")])

    def test_observation_types_are_not_coerced(self):
        for changes in ({"run_id": True}, {"run_attempt": "1"}, {"infrastructure_failure": "false"},
                        {"blocked_by": []}, {"artifact": 1}, {"unknown": 1}):
            with self.subTest(changes=changes), self.assertRaises(verdict.VerdictError):
                self.build([self.row(**changes)])

    def test_scope_kind_cannot_disagree_with_suite_set(self):
        self.selection["kind"] = "full"
        with self.assertRaises(verdict.VerdictError):
            self.build()

    def test_identity_policy_must_match_current_scope_policy(self):
        self.identity["policy_digest"] = "0" * 64
        with self.assertRaisesRegex(verdict.VerdictError, "policy digest"):
            self.build()

    def test_auto_requires_base_but_bootstrap_allows_none(self):
        self.identity["base_sha"] = None
        with self.assertRaisesRegex(verdict.VerdictError, "requires a baseline"):
            self.build()
        self.identity["request_kind"] = "bootstrap"
        self.selection = test_scope._selection(self.policy, self.policy.suite_ids, ["bootstrap"])
        self.assertEqual(self.build([])["status"], "failed", "why: empty bootstrap appeared healthy; remedy: full observations")

    def test_explicit_candidate_cannot_be_focused(self):
        self.identity["request_kind"] = "candidate"
        with self.assertRaisesRegex(verdict.VerdictError, "require full"):
            self.build()

    def test_rehashing_modified_status_does_not_bypass_replay(self):
        document = self.build([self.row(conclusion="failure")])
        document["status"] = "passed"
        self.rehash(document)
        with self.assertRaisesRegex(verdict.VerdictError, "recomputed"):
            self.validate(document)

    def test_boolean_integer_equality_cannot_bypass_exact_replay(self):
        document = self.build()
        self.suite(document)["selected"] = 1
        with self.assertRaisesRegex(verdict.VerdictError, "recomputed"):
            self.validate(document)

    def test_frozen_request_selection_must_be_independently_supplied(self):
        document = self.build()
        with self.assertRaisesRegex(verdict.VerdictError, "frozen request"):
            verdict.validate(document, self.policy, self.identity,
                             test_scope._selection(self.policy, [], ["forged exemption"]))

    def test_claimed_executor_identity_must_match(self):
        document = self.build()
        expected = {**self.identity, "run_id": 99}
        with self.assertRaisesRegex(verdict.VerdictError, "executor identity"):
            verdict.validate(document, self.policy, expected, self.selection)

    def test_validate_retains_original_observations_and_returns_copy(self):
        rows = [self.row(artifact="uploaded", started_at="2026-09-08T01:00:00Z")]
        document = self.build(rows)
        checked = self.validate(document)
        self.assertEqual(checked["observations"], rows, "why: original evidence lost; remedy: preserve typed observations")
        checked["observations"][0]["conclusion"] = "failure"
        self.assertEqual(document["observations"][0]["conclusion"], "success",
                         "why: returned data aliased evidence; remedy: defensive copies")

    def common_event(self, cause="change-scope", suites=None):
        suites = sorted(suites or self.selection["suites"])
        source = {"result": "failure", "outputs": {"reason": "quota"}}
        event = {"kind": "shared_dependency_failure", "request_id": self.identity["request_id"],
                 "run_id": self.identity["run_id"], "run_attempt": self.identity["run_attempt"],
                 "cause": cause,
                 "source": {"job": cause, **source,
                            "digest": self_test.digest_of(source)},
                 "blocked_suites": suites}
        event["event_id"] = self_test.digest_of({"request_id": self.identity["request_id"],
                                                  "run_id": self.identity["run_id"],
                                                  "run_attempt": self.identity["run_attempt"], "cause": cause})
        return event

    def test_common_event_is_v2_and_exactly_identity_bound(self):
        event = self.common_event()
        document = verdict.build(self.policy, self.identity, self.selection, [], common_events=[event])
        self.assertEqual(document["evidence_schema"], verdict.COMMON_EVENT_SCHEMA)
        self.assertEqual(verdict.validate(document, self.policy, self.identity, self.selection)["common_events"], [event])

    def test_common_event_rejects_identity_or_source_mismatch(self):
        event = self.common_event()
        for changes in ({"request_id": "other"}, {"source": {**event["source"], "result": "success"}}):
            with self.subTest(changes=changes):
                forged = deepcopy(event)
                forged.update(changes) if "request_id" in changes else forged["source"].update(changes["source"])
                with self.assertRaisesRegex(verdict.VerdictError, "common event"):
                    verdict.build(self.policy, self.identity, self.selection, [], common_events=[forged])

    def test_legacy_complete_validator_rejects_new_full_schema(self):
        self.selection = test_scope._selection(self.policy, self.policy.suite_ids, ["full"])
        rows = [self.row(suite.id, job) for suite in self.policy.inventory.suites for job in suite.jobs]
        with self.assertRaises(self_test_evidence.SelfTestEvidenceError):
            self_test_evidence.validate_verdict_document(self.build(rows), policy=self.policy.inventory)


if __name__ == "__main__":
    unittest.main()
