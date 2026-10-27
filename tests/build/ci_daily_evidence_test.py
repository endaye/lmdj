#!/usr/bin/env python3
"""Daily execution cannot impersonate complete evidence or erase its debt."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import batch_evidence_validation as evidence
import batch_execution as execution
import batch_runtime
import batch_verdict as verdict
import incremental_batch as batch
import report_runtime
import test_scope
import self_test_evidence

A, B, C, D = (c * 40 for c in "abcd")


class DailyEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.policy = test_scope.load_policy(ROOT)
        self.selection = test_scope._selection(self.policy, self.policy.suite_ids, ["complete selected inventory"])
        self.workloads = {suite: "deferred" for suite in self.policy.suite_ids}
        self.workloads.update(creator="quick", docs_static="full")
        self.request = batch.make_request(self.policy, request_id="daily", kind="auto", base_sha=A,
            target_sha=B, control_sha=A, selection=self.selection,
            origin_run={"run_id": 17, "attempt": 1}, verification=self.workloads)
        self.identity = dict(request_id="daily", request_kind="auto", base_sha=A,
            target_sha=B, control_sha=A, policy_digest=self.policy.digest, run_id=17, run_attempt=1)
        self.needs = {evidence.ALIASES.get(job, job): {"result": "skipped", "outputs": {}}
                      for job in self.policy.inventory.job_owner}
        self.needs.update({"change-scope": {"result": "success", "outputs": {}},
                           "creator-web": {"result": "success", "outputs": {}},
                           "docs-static": {"result": "success", "outputs": {}}})

    def document(self, needs=None):
        return execution.from_needs(self.policy, self.identity, self.selection, needs or self.needs,
            aliases=evidence.ALIASES, dependencies=evidence.dependencies(self.policy),
            verification=self.workloads)

    def bundle(self):
        return {"execution.json": execution.execution_plan(self.policy, self.identity, self.selection, self.workloads),
                "verdict.json": self.document(), "needs.json": deepcopy(self.needs)}

    def suite(self, document, name):
        return next(item for item in document["suites"] if item["id"] == name)

    def test_raw_needs_bundle_retains_all_suites_and_exact_daily_workloads(self):
        bundle = self.bundle()
        checked, identity = evidence.validate_bundle(bundle, self.request, {"id": 17}, self.policy)
        self.assertEqual(identity, self.identity)
        self.assertEqual(checked["evidence_schema"], verdict.DAILY_SCHEMA)
        self.assertEqual(checked["status"], "quick-passed")
        self.assertEqual(len(checked["suites"]), 15)
        self.assertEqual(self.suite(checked, "creator")["status"], "quick-passed")
        self.assertEqual(self.suite(checked, "core_coverage")["status"], "deferred")
        self.assertEqual(self.suite(checked, "docs_static")["status"], "passed")
        self.assertEqual({name for name, on in bundle["execution.json"]["lanes"].items() if on},
                         {"creator", "docs_static"})
        self.assertEqual({row["job"] for row in checked["observations"]}, {"creator-web", "docs-static"})

    def test_daily_bundle_requires_independently_frozen_map(self):
        bundle = self.bundle()
        request = deepcopy(self.request)
        del request["verification"]
        with self.assertRaises(ValueError):
            evidence.validate_bundle(bundle, request, {"id": 17}, self.policy)
        with self.assertRaisesRegex(ValueError, "frozen verification"):
            verdict.validate(bundle["verdict.json"], self.policy, self.identity, self.selection)

    def test_rehashed_full_pass_is_rejected(self):
        document = self.document()
        document["status"] = "passed"
        self.suite(document, "creator")["status"] = "passed"
        document["evidence_digest"] = batch.digest({k: v for k, v in document.items() if k != "evidence_digest"})
        with self.assertRaisesRegex(ValueError, "recomputed"):
            verdict.validate(document, self.policy, self.identity, self.selection, verification=self.workloads)

    def test_candidate_cannot_use_daily_even_with_complete_suite_names(self):
        for kind in ("candidate", "node", "bootstrap"):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "only automatic"):
                batch.make_request(self.policy, request_id="candidate", kind=kind, base_sha=None,
                    target_sha=B, control_sha=A, selection=self.selection,
                    origin_run={"run_id": 17, "attempt": 1}, verification=self.workloads)
        identity = {**self.identity, "request_kind": "candidate", "base_sha": None}
        with self.assertRaisesRegex(ValueError, "complete verification"):
            verdict.build(self.policy, identity, self.selection, [], verification=self.workloads)

    def test_complete_release_validator_rejects_daily_receipt(self):
        with self.assertRaises(self_test_evidence.SelfTestEvidenceError):
            self_test_evidence.validate_verdict_document(self.document(), policy=self.policy.inventory)

    def test_missing_bundle_reports_only_uncovered_active_work(self):
        state = dict(epoch="daily-test", _result_order=["daily"],
                     results={"daily": dict(run={"run_id": 17, "attempt": 1},
                         reference="missing:daily", outcomes=batch.missing_outcomes(self.request))},
                     requests={"daily": self.request})
        reports = report_runtime.plan_batch_reports("endaye/lmdj", state,
                                                    SimpleNamespace(policy_at=lambda _, **kwargs: self.policy))
        self.assertEqual(len(reports), 1)
        self.assertIn("- Missing selected execution evidence: creator, docs_static", reports[0].summary)
        self.assertEqual({key for key, _ in reports[0].supersedes},
                         {key for suite in ("creator", "docs_static")
                          for key in (report_runtime.reporting.managed_bucket_key(
                              "daily-test", self.request["policy"], suite, "missing"),
                                      f"self-test-{suite}-missing".replace("_", "-"))})

    def test_unpaused_full_debt_requires_full_recovery_workload(self):
        outcomes = {suite: "passed" for suite in self.policy.suite_ids}
        outcomes["creator"] = "missing"
        state = self.finish(batch.new_state("daily-test"), A, kind="bootstrap", outcomes=outcomes)
        with self.assertRaisesRegex(ValueError, "executable full verification debt"):
            self.finish(state, B, workloads=self.workloads, outcomes={})

    def test_deferred_product_execution_is_rejected(self):
        needs = deepcopy(self.needs)
        needs["core-coverage"]["result"] = "success"
        with self.assertRaisesRegex(ValueError, "unselected product job"):
            self.document(needs)

    def test_deferred_observation_cannot_be_injected_directly(self):
        rows = self.document()["observations"] + [dict(suite="core_coverage", job="core-coverage",
            run_id=17, run_attempt=1, target_revision=B, conclusion="success")]
        with self.assertRaisesRegex(ValueError, "deferred suite"):
            verdict.build(self.policy, self.identity, self.selection, rows, verification=self.workloads)

    def test_missing_quick_job_is_debt_but_intentional_deferral_is_not(self):
        needs = deepcopy(self.needs)
        del needs["creator-web"]
        document = self.document(needs)
        self.assertEqual(self.suite(document, "creator")["scheduler_outcome"], "missing")
        self.assertTrue(self.suite(document, "creator")["verification_debt"])
        self.assertFalse(self.suite(document, "core_coverage")["verification_debt"])
        missing = batch.missing_outcomes(self.request)
        self.assertEqual(missing["creator"], "missing")
        self.assertEqual(missing["core_coverage"], "deferred")

    def test_failed_quick_test_retains_its_real_job_failure(self):
        needs = deepcopy(self.needs)
        needs["creator-web"]["result"] = "failure"
        row = self.suite(self.document(needs), "creator")
        self.assertEqual(row["scheduler_outcome"], "quick-failed")
        self.assertEqual(row["failures"], ["creator-web"])

    def test_legacy_automatic_request_keeps_complete_semantics(self):
        request = {k: v for k, v in self.request.items() if k != "verification"}
        batch._request(self.policy, request)
        plan = execution.execution_plan(self.policy, self.identity, self.selection)
        self.assertNotIn("verification", plan)
        self.assertTrue(all(plan["suites"].values()))
        rows = [dict(suite=s.id, job=j, run_id=17, run_attempt=1, target_revision=B, conclusion="success")
                for s in self.policy.inventory.suites for j in s.jobs]
        document = verdict.build(self.policy, self.identity, self.selection, rows)
        self.assertEqual(document["evidence_schema"], verdict.SCHEMA)
        self.assertEqual(document["status"], "passed")
        self.assertTrue(all(s["status"] == "passed" for s in document["suites"]))

    def apply(self, state, kind, data):
        return batch.reduce(state, dict(id=str(state["generation"]), epoch=state["epoch"],
            generation=state["generation"], type=kind, data=data), self.policy)

    def finish(self, state, target, *, kind="auto", workloads=None, outcomes=None):
        state = self.apply(state, "observe", dict(target=target, descends_pending=True))
        request = batch.make_request(self.policy, request_id=f"r{state['generation']}", kind=kind,
            base_sha=state["processed"], target_sha=target, control_sha=A, selection=self.selection,
            origin_run={"run_id": 17, "attempt": 1}, verification=workloads)
        state = self.apply(state, "admit", dict(request=request, executor_run=request["origin_run"],
            history_complete=True, ancestor=True, old_runs_terminal=True))
        state = self.apply(state, "claim", dict(request_id=request["id"], run=request["origin_run"]))
        state = self.apply(state, "result", dict(request_id=request["id"], run=request["origin_run"],
            target=target, policy=self.policy.digest, outcomes=outcomes,
            reference="retained-result", terminal=True))
        return self.apply(state, "advance", dict(request_id=request["id"]))

    def debt_state(self):
        outcomes = {suite: "passed" for suite in self.policy.suite_ids}
        outcomes.update(creator="missing", core_coverage="missing")
        state = self.finish(batch.new_state("daily-test"), A, kind="bootstrap", outcomes=outcomes)
        return self.finish(state, B, outcomes=outcomes)

    def test_quick_success_and_deferral_preserve_paused_full_debt(self):
        state = self.debt_state()
        before = deepcopy(state["debts"])
        self.assertTrue(all(d["paused"] for d in before.values()))
        outcomes = verdict.scheduler_outcomes(self.document(), self.policy, self.identity,
                                             self.selection, verification=self.workloads)
        state = self.finish(state, C, workloads=self.workloads, outcomes=outcomes)
        self.assertEqual(state["debts"], before)
        self.assertEqual(state["processed"], C)
        self.assertIsNone(state["active"])

    def test_real_full_pass_can_still_clear_full_debt(self):
        state = self.finish(self.debt_state(), C, outcomes={s: "passed" for s in self.policy.suite_ids})
        self.assertEqual(state["debts"], {})

    def test_reducer_rejects_full_outcome_for_daily_workload(self):
        state = self.finish(batch.new_state("daily-test"), A, kind="bootstrap",
                            outcomes={s: "passed" for s in self.policy.suite_ids})
        outcomes = {s: "deferred" for s in self.policy.suite_ids}
        outcomes.update(creator="passed", docs_static="passed")
        with self.assertRaisesRegex(ValueError, "contradicts frozen"):
            self.finish(state, B, workloads=self.workloads, outcomes=outcomes)

    def test_quick_success_cannot_close_full_creator_failure_bucket(self):
        document = self.document()
        result = dict(run={"run_id": 17, "attempt": 1}, reference=batch_runtime.encode_reference(document),
                      outcomes=verdict.scheduler_outcomes(document, self.policy, self.identity,
                                                          self.selection, verification=self.workloads))
        state = dict(epoch="daily-test", _result_order=["daily"], results={"daily": result},
                     requests={"daily": self.request})
        inputs = SimpleNamespace(policy_at=lambda _, **kwargs: self.policy)
        recoveries = report_runtime.plan_bucket_recoveries(state, inputs)
        self.assertTrue(all(item.suite == "docs_static" for item in recoveries))
        self.assertTrue(recoveries)  # the complete static check still has actual full evidence
        self.assertEqual(report_runtime.plan_batch_reports("endaye/lmdj", state, inputs), ())


if __name__ == "__main__":
    unittest.main()
