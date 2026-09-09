"""Actual reporter/outbox/journal composition; no GitHub writes.

The companion real HTTP fixture exercises provenance and exact request shapes,
not hosted token scopes, actual writer locking or eventual visibility timing.
Those remain O1 gaps; memory crash journeys do not claim remote acceptance.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]
import report_runtime as module
import batch_runtime
import batch_verdict
import batch_execution
import incremental_batch as batch
import report_outbox
import review_scope
import test_scope
from ci_batch_controller_test import Memory, Inputs, A, B, C, POLICY
import ci_batch_runtime_test as runtime_fixture
import ci_review_failure_report_test as review_fixture
from ci_self_test_report_test import FakeGitHubApi, full_legacy_api


class Crash(BaseException):
    pass


def append(memory, kind, data, epoch="scheduler"):
    generation = len(memory.comments)
    memory.journal().append(dict(id=f"{epoch}:{generation}", epoch=epoch, generation=generation, type=kind, data=data))


def result(memory, *, kind="bootstrap", selection=None, target=B, control=A, policy=POLICY,
           base=None, failed=(), missing=(), special=None, advance=False):
    run = {"run_id": 100 + len(memory.comments), "attempt": 1}
    selection = selection or test_scope.select(policy, ["scripts/ci/a.py"])
    request = batch.make_request(policy, request_id="request-" + str(run["run_id"]), kind=kind,
        base_sha=base, target_sha=target, control_sha=control, selection=selection, origin_run=run)
    append(memory, "observe", {"target": target, "descends_pending": True})
    if kind in {"node", "candidate"}:
        append(memory, "enqueue", request)
    append(memory, "admit", dict(request=request, executor_run=run, history_complete=True, ancestor=True, old_runs_terminal=True))
    append(memory, "claim", dict(request_id=request["id"], run=run))
    identity = dict(request_id=request["id"], request_kind=kind, base_sha=base, target_sha=target,
        control_sha=control, policy_digest=policy.digest, run_id=run["run_id"], run_attempt=1)
    observations = [dict(suite=suite.id, job=job, run_id=run["run_id"], run_attempt=1,
                         target_revision=target, conclusion="failure" if job in failed else "success")
                    for suite in policy.inventory.suites if suite.id in selection["suites"]
                    for job in suite.jobs if job not in missing]
    verdict = batch_verdict.build(policy, identity, selection, observations)
    outcomes = batch_verdict.scheduler_outcomes(verdict, policy, identity, selection)
    reference = batch_runtime.encode_reference(verdict)
    if special == "missing":
        outcomes = {suite: "missing" for suite in selection["suites"]}
        reference = "missing:" + request["id"]
    elif special == "none":
        reference = "not-required:" + request["id"]
    append(memory, "result", dict(request_id=request["id"], run=run, target=target,
        policy=policy.digest, outcomes=outcomes, reference=reference, terminal=True))
    if advance:
        append(memory, "advance", {"request_id": request["id"]})
    return request, verdict


def common_result(memory, *, independent=None):
    run = {"run_id": 100 + len(memory.comments), "attempt": 1}
    selection = test_scope._selection(POLICY, POLICY.suite_ids, ["shared control failure"])
    request = batch.make_request(POLICY, request_id="request-" + str(run["run_id"]), kind="bootstrap",
        base_sha=None, target_sha=B, control_sha=A, selection=selection, origin_run=run)
    append(memory, "observe", {"target": B, "descends_pending": True})
    append(memory, "admit", dict(request=request, executor_run=run, history_complete=True, ancestor=True, old_runs_terminal=True))
    append(memory, "claim", dict(request_id=request["id"], run=run))
    identity = dict(request_id=request["id"], request_kind="bootstrap", base_sha=None, target_sha=B,
        control_sha=A, policy_digest=POLICY.digest, run_id=run["run_id"], run_attempt=1)
    needs = {"change-scope": {"result": "failure", "outputs": {"reason": "shared control failure"}}}
    needs.update({{"core-tsan": "nightly-tsan", "core-stress": "nightly-stress"}.get(job, job):
                  {"result": "skipped", "outputs": {}}
                  for job in POLICY.inventory.job_owner})
    needs["macos-fallback"] = {"result": "skipped", "outputs": {}}
    if independent == "missing":
        del needs["core-macos"]
    elif independent == "cancelled":
        needs["core-macos"] = {"result": "cancelled", "outputs": {}}
    elif independent == "infrastructure":
        needs["core-macos"] = {"result": "failure", "outputs": {"infrastructure_failure": "true"}}
    verdict = batch_execution.from_needs(POLICY, identity, selection, needs,
        aliases={"core-tsan": "nightly-tsan", "core-stress": "nightly-stress"},
        dependencies={job: ["change-scope"] for job in POLICY.inventory.job_owner})
    outcomes = batch_verdict.scheduler_outcomes(verdict, POLICY, identity, selection)
    append(memory, "result", dict(request_id=request["id"], run=run, target=B,
        policy=POLICY.digest, outcomes=outcomes, reference=batch_runtime.encode_reference(verdict), terminal=True))
    return request, verdict


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.scheduler, self.outbox = Memory(), Memory()
        self.inputs = Inputs()
        self.runtime = SimpleNamespace(journal=self.scheduler.journal, inputs=self.inputs,
            current={"run_id": 1, "attempt": 1}, lock_held=lambda: True,
            config={"epoch": "scheduler"}, control=A)
        self.api = FakeGitHubApi()
        self.adapter = object.__new__(module.ReportRuntime)
        self.adapter.api = self.api
        self.adapter.scheduler = self.runtime
        self.adapter.outbox = lambda: report_outbox.Outbox(self.outbox.journal(), lambda: True, "outbox")

    def planned(self):
        state = module.scheduler_state(self.runtime)
        return module.plan_batch_reports("endaye/lmdj", state, self.inputs)

    def validated_common_result(self):
        """Feed the planner the exact reference accepted by the real runtime."""
        fixture = runtime_fixture.RuntimeTests("test_explicit_init_is_empty_not_a_tested_baseline")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        start = fixture.start()
        fixture.evidence(start["request"], shared_dependency_failure=True)
        executor = fixture.make()
        executor.inputs.refresh()
        receipt = executor.result_for(start["request"], start["executor"])
        self.assertEqual(receipt["status"], "ready")
        verdict = batch_runtime.decode_reference(receipt["reference"])
        request = start["request"]
        self.inputs.policies[request["control"]] = POLICY
        run = start["executor"]
        append(self.scheduler, "observe", {"target": request["target"], "descends_pending": True})
        append(self.scheduler, "admit", dict(request=request, executor_run=run, history_complete=True,
                                              ancestor=True, old_runs_terminal=True))
        append(self.scheduler, "claim", dict(request_id=request["id"], run=run))
        append(self.scheduler, "result", dict(request_id=request["id"], run=run, target=request["target"],
            policy=request["policy"], outcomes=batch_verdict.scheduler_outcomes(
                verdict, POLICY, verdict["identity"], request["selection"]),
            reference=receipt["reference"], terminal=True))
        return request, verdict

    def posts(self):
        return [call for call in self.api.calls if call[0] in {"create_issue", "create_comment"}]

    def pending_stale_recovery(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = next(item for item in self.planned() if item.management is not None)
        self.adapter.deliver((failure,), 32)
        result(self.scheduler, kind="auto", base=B, target=C, advance=True)
        recovery = next(item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                        if item.key == failure.key)
        original = self.api.create_comment

        def die(number, body):
            response = original(number, body)
            raise Crash("recovery comment response lost")

        self.api.create_comment = die
        with self.assertRaises(Crash):
            self.adapter.deliver((), 32, recoveries=(recovery,))
        self.api.create_comment = original
        result(self.scheduler, kind="auto", base=C, target="d" * 40,
               failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        return recovery

    def legacy(self):
        self.api = full_legacy_api()
        self.adapter.api = self.api
        self.adapter.repository = "endaye/lmdj"
        self.adapter.storage = SimpleNamespace(authenticate_current=lambda: None)

    def test_legacy_full_plan_crosses_outbox_before_issue_and_replay_has_no_post(self):
        self.legacy()
        with mock.patch.object(module.reporting, "report_run", side_effect=AssertionError("old direct writer forbidden")):
            answer = self.adapter.execute("legacy", run_id=100, attempt=1)
            self.assertEqual(answer["outcomes"][0]["status"], "delivered")
            self.assertEqual([e["type"] for e in self.outbox.journal().load()], ["queue", "claim", "ack", "delivered"])
            self.assertEqual(len(self.posts()), 1)
            self.assertIn("100/1", self.api.issues[0]["body"])
            self.adapter.execute("legacy", run_id=100, attempt=1)
            self.assertEqual(len(self.posts()), 1)
        self.assertFalse(self.scheduler.comments)

    def test_legacy_wrong_attempt_cannot_queue_or_post(self):
        self.legacy()
        with self.assertRaises(Exception):
            self.adapter.execute("legacy", run_id=100, attempt=2)
        self.assertFalse(self.outbox.comments)
        self.assertFalse(self.posts())

    def test_legacy_lost_post_response_is_recovered_by_receipt_not_a_second_post(self):
        self.legacy()
        original = self.api.create_issue
        def lost(**kwargs):
            original(**kwargs)
            raise Crash("response lost after actual issue creation")
        self.api.create_issue = lost
        with self.assertRaises(Crash):
            self.adapter.execute("legacy", run_id=100, attempt=1)
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual([e["type"] for e in self.outbox.journal().load()], ["queue", "claim"])
        answer = self.adapter.execute("legacy", run_id=100, attempt=1)
        self.assertEqual(answer["status"], "ready")
        self.assertEqual(len(self.posts()), 1)
        state = self.adapter.outbox().load()
        delivery = next(iter(state["deliveries"].values()))
        self.assertEqual(delivery["status"], "delivered")
        self.assertEqual(delivery["receipt"]["issue_number"], self.api.issues[0]["number"])

    def test_pre_advance_failure_reaches_actual_issue_and_durable_receipt(self):
        request, _ = result(self.scheduler, failed=(POLICY.inventory.suites[0].jobs[0],))
        before = deepcopy((self.scheduler.comments, self.scheduler.checkpoint))
        planned = self.planned()
        self.assertEqual(len(planned), 1)
        answer = self.adapter.deliver(planned, 1)
        self.assertEqual(answer["outcomes"][0]["status"], "delivered")
        body = self.api.issues[0]["body"]
        self.assertIn(request["id"], body)
        self.assertIn(request["target"], body)
        self.assertIn("not full-release evidence", body)
        self.assertEqual([e["type"] for e in self.outbox.journal().load()], ["queue", "claim", "ack", "delivered"])
        self.assertEqual(before, (self.scheduler.comments, self.scheduler.checkpoint))
        self.assertIsNotNone(module.scheduler_state(self.runtime)["active"])

    def test_failed_and_missing_jobs_in_same_suite_produce_two_observations(self):
        suite = next(s for s in POLICY.inventory.suites if len(s.jobs) > 1)
        result(self.scheduler, failed=(suite.jobs[0],), missing=(suite.jobs[1],))
        reports = self.planned()
        self.assertEqual({r.key for r in reports}, {
            module.reporting.managed_bucket_key("scheduler", POLICY.digest, suite.id, "test_failure"),
            module.reporting.managed_bucket_key("scheduler", POLICY.digest, suite.id, "missing")})
        self.assertTrue(all(suite.jobs[0] in r.summary and "Verification debt: missing" in r.summary for r in reports))

    def test_focused_keeps_unselected_not_passed(self):
        result(self.scheduler, advance=True)
        selection = test_scope._selection(POLICY, ["creator"], ["host"])
        suite = next(s for s in POLICY.inventory.suites if s.id == "creator")
        result(self.scheduler, kind="auto", base=B, target=C, selection=selection, failed=(suite.jobs[0],))
        report = self.planned()[0]
        self.assertIn("Scope: **focused**", report.summary)
        self.assertIn("Not selected (not passes):", report.summary)
        self.assertNotIn("from a self-test verdict", report.issue_body("endaye"))

    def test_none_terminal_receipt_owes_no_report(self):
        result(self.scheduler, advance=True)
        result(self.scheduler, kind="auto", base=B, target=C,
               selection=test_scope.select(POLICY, ["docs/notes/a.md"]), special="none")
        self.assertEqual(self.planned(), ())

    def test_missing_terminal_receipt_is_not_fabricated_verdict(self):
        result(self.scheduler, special="missing")
        planned = self.planned()
        self.assertEqual(len(planned), 16)
        self.assertTrue(all(r.key.endswith("-missing") for r in planned))
        self.assertTrue(all("no product verdict" in r.detail for r in planned))

    def test_authenticated_shared_event_reaches_one_durable_report_with_all_suite_debt(self):
        request, verdict = common_result(self.scheduler)
        self.assertEqual(verdict["evidence_schema"], batch_verdict.COMMON_EVENT_SCHEMA)
        reports = self.planned()
        self.assertEqual(len(reports), 1)
        report = reports[0]
        event = verdict["common_events"][0]
        self.assertEqual(report.key, module.reporting.common_event_report_key(event["event_id"]))
        self.assertIn(event["event_id"], report.summary)
        for suite in POLICY.suite_ids:
            self.assertIn(suite, report.detail)
        first = self.adapter.deliver(reports, 32)
        self.assertEqual(first["outcomes"][0]["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)
        second = self.adapter.deliver(reports, 32)
        self.assertEqual(second["outcomes"], [])
        self.assertEqual(len(self.posts()), 1)
        stored = self.adapter.outbox().load()
        delivery = next(iter(stored["deliveries"].values()))
        self.assertEqual(delivery["status"], "delivered")
        self.assertIn(request["id"], delivery["payload"]["issue_body"])

    def test_common_event_keeps_independent_mixed_suite_debt_separate(self):
        request, verdict = common_result(self.scheduler, independent="missing")
        self.assertEqual(verdict["evidence_schema"], batch_verdict.COMMON_EVENT_SCHEMA)
        reports = self.planned()
        keys = {report.key for report in reports}
        event = verdict["common_events"][0]
        self.assertIn(module.reporting.common_event_report_key(event["event_id"]), keys)
        self.assertTrue(any(key.endswith("-core-macos-missing") for key in keys))
        common = next(report for report in reports
                      if report.key == module.reporting.common_event_report_key(event["event_id"]))
        self.assertIn("core_macos", common.detail)
        independent = next(report for report in reports if report.key.endswith("-core-macos-missing"))
        self.assertIn("Verification debt: missing", independent.summary)
        self.assertIn(request["id"], independent.summary)

    def test_common_event_keeps_independent_cancellation_separate(self):
        _, verdict = common_result(self.scheduler, independent="cancelled")
        reports = self.planned()
        event_key = module.reporting.common_event_report_key(verdict["common_events"][0]["event_id"])
        self.assertIn(event_key, {report.key for report in reports})
        cancellation = next(report for report in reports if report.key.endswith("-core-macos-blocked"))
        self.assertIn("Verification debt: cancelled", cancellation.summary)

    def test_common_event_keeps_independent_infrastructure_separate(self):
        _, verdict = common_result(self.scheduler, independent="infrastructure")
        reports = self.planned()
        event_key = module.reporting.common_event_report_key(verdict["common_events"][0]["event_id"])
        self.assertIn(event_key, {report.key for report in reports})
        infrastructure = next(report for report in reports
                              if report.key.endswith("-core-macos-infrastructure-failure"))
        self.assertIn("Verification debt: infrastructure", infrastructure.summary)

    def test_validated_v2_artifact_reaches_planner_and_outbox(self):
        request, verdict = self.validated_common_result()
        self.assertEqual(verdict["evidence_schema"], batch_verdict.COMMON_EVENT_SCHEMA)
        reports = self.planned()
        self.assertEqual(len(reports), 1)
        answer = self.adapter.deliver(reports, 1)
        self.assertEqual(answer["outcomes"][0]["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)
        self.assertIn(request["id"], self.api.issues[0]["body"])

    def test_wrong_special_reference_is_rejected(self):
        result(self.scheduler)
        state = module.scheduler_state(self.runtime)
        item = next(iter(state["results"].values()))
        for reference in (None, "missing:other", "not-required:other", "legacy-verdict", ""):
            with self.subTest(reference=reference):
                item["reference"] = reference
                with self.assertRaises(Exception):
                    module.plan_batch_reports("endaye/lmdj", state, self.inputs)

    def test_missing_requires_all_selected_outcomes_missing(self):
        request, _ = result(self.scheduler)
        state = module.scheduler_state(self.runtime)
        state["results"][request["id"]]["reference"] = "missing:" + request["id"]
        with self.assertRaisesRegex(ValueError, "non-missing outcomes"):
            module.plan_batch_reports("endaye/lmdj", state, self.inputs)

    def test_none_cannot_hide_selected_work(self):
        request, _ = result(self.scheduler)
        state = module.scheduler_state(self.runtime)
        state["results"][request["id"]]["reference"] = "not-required:" + request["id"]
        with self.assertRaisesRegex(ValueError, "claims selected work"):
            module.plan_batch_reports("endaye/lmdj", state, self.inputs)

    def test_result_outcomes_must_equal_scoped_verdict(self):
        request, _ = result(self.scheduler, failed=(POLICY.inventory.suites[0].jobs[0],))
        state = module.scheduler_state(self.runtime)
        state["results"][request["id"]]["outcomes"][POLICY.inventory.suites[0].id] = "passed"
        with self.assertRaisesRegex(ValueError, "outcomes differ"):
            module.plan_batch_reports("endaye/lmdj", state, self.inputs)

    def test_rehashed_wrong_verdict_identity_is_rejected(self):
        request, verdict = result(self.scheduler)
        verdict["identity"]["target_sha"] = C
        state = module.scheduler_state(self.runtime)
        state["results"][request["id"]]["reference"] = batch_runtime.encode_reference(verdict)
        with self.assertRaisesRegex(batch_verdict.VerdictError, "identity"):
            module.plan_batch_reports("endaye/lmdj", state, self.inputs)

    def test_old_result_uses_old_policy_after_current_policy_changes(self):
        result(self.scheduler, failed=(POLICY.inventory.suites[0].jobs[0],))
        expected = self.planned()
        # Digest change is sufficient to catch accidentally using current policy.
        from dataclasses import replace
        self.inputs.policies[C] = replace(POLICY, digest="f" * 64)
        self.runtime.control = C
        self.assertEqual(self.planned(), expected)

    def test_missing_historical_policy_is_error_not_empty_report(self):
        result(self.scheduler)
        del self.inputs.policies[A]
        with self.assertRaisesRegex(batch.BatchError, "historical policy"):
            self.planned()

    def test_pending_scheduler_append_never_replaces_anchor(self):
        self.scheduler.fail = ("observe", "after")
        with self.assertRaises(Exception):
            append(self.scheduler, "observe", {"target": B, "descends_pending": True})
        before = deepcopy((self.scheduler.comments, self.scheduler.checkpoint))
        with self.assertRaisesRegex(Exception, "only its controller"):
            self.planned()
        self.assertEqual(before, (self.scheduler.comments, self.scheduler.checkpoint))
        self.assertFalse(self.posts())

    def test_deleted_scheduler_tail_is_not_partial_clean_history(self):
        result(self.scheduler)
        self.scheduler.comments.pop()
        with self.assertRaisesRegex(Exception, "suffix"):
            self.planned()

    def test_limit_skips_delivered_and_reaches_later_observations(self):
        result(self.scheduler, failed=tuple(s.jobs[0] for s in POLICY.inventory.suites[:2]))
        reports = self.planned()
        self.assertGreater(len(reports), 1)
        self.assertEqual(self.adapter.deliver(reports, 1)["remaining"], len(reports) - 1)
        self.adapter.deliver(reports, 1)
        self.assertEqual(len(self.posts()), 2)

    def test_unresolved_claim_does_not_starve_later_queue_records(self):
        result(self.scheduler, special="missing")
        reports = self.planned()
        self.outbox.fail = ("claim", "after")
        with self.assertRaises(Exception):
            self.adapter.deliver(reports, 1)
        self.assertEqual(self.adapter.deliver(reports, 1)["status"], "needs-reconciliation")
        self.assertEqual(self.adapter.deliver(reports, 1)["status"], "needs-reconciliation")
        self.assertEqual(len(self.adapter.outbox().load()["deliveries"]), 3)
        self.assertFalse(self.posts())

    def test_post_then_death_recovers_without_second_post(self):
        result(self.scheduler, failed=(POLICY.inventory.suites[0].jobs[0],))
        reports = self.planned()
        original = self.api.create_issue
        def die(**kwargs):
            original(**kwargs)
            raise Crash()
        self.api.create_issue = die
        with self.assertRaises(Crash):
            self.adapter.deliver(reports, 1)
        self.api.create_issue = original
        self.assertEqual(self.adapter.deliver(reports, 1)["status"], "ready")
        self.assertEqual(len(self.posts()), 1)

    def test_invisible_receipt_remains_unresolved_until_exact_body_reappears(self):
        result(self.scheduler, failed=(POLICY.inventory.suites[0].jobs[0],))
        reports = self.planned()
        original_post, original_list = self.api.create_issue, self.api.list_issues
        def invisible(**kwargs):
            response = original_post(**kwargs)
            self.api.list_issues = lambda **kwargs: []
            return response
        self.api.create_issue = invisible
        with self.assertRaises(Exception):
            self.adapter.deliver(reports, 1)
        self.assertEqual(self.adapter.deliver(reports, 1)["status"], "needs-reconciliation")
        self.assertEqual(len(self.posts()), 1)
        self.api.list_issues = original_list
        self.assertEqual(self.adapter.deliver(reports, 1)["status"], "ready")
        self.assertEqual(len(self.posts()), 1)

    def test_later_historical_candidate_failure_does_not_touch_auto_cursor(self):
        result(self.scheduler, advance=True)
        result(self.scheduler, kind="candidate", target=A, failed=(POLICY.inventory.suites[0].jobs[0],))
        before = module.scheduler_state(self.runtime)
        self.assertEqual(before["processed"], B)
        report = self.planned()[0]
        self.assertIn("(candidate)", report.summary)
        self.adapter.deliver((report,), 1)
        self.assertEqual(module.scheduler_state(self.runtime), before)

    def test_changed_frozen_body_rejected_without_new_post(self):
        result(self.scheduler, failed=(POLICY.inventory.suites[0].jobs[0],))
        report = self.planned()[0]
        self.adapter.deliver((report,), 1)
        from dataclasses import replace
        with self.assertRaisesRegex(ValueError, "body changed"):
            self.adapter.deliver((replace(report, summary="Different"),), 1)
        self.assertEqual(len(self.posts()), 1)

    def test_new_managed_bucket_recovers_only_after_actual_same_suite_success(self):
        request, _ = result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = self.planned()[0]
        self.assertIsNotNone(failure.management)
        self.assertEqual(failure.management["epoch"], "scheduler")
        self.adapter.deliver((failure,), 32)
        self.assertEqual(self.adapter.outbox().epoch, "outbox")
        issue = self.api.issues[0]
        self.assertIn("managed=v1", issue["body"])
        result(self.scheduler, kind="auto", base=B, target=C)
        state = module.scheduler_state(self.runtime)
        recoveries = module.plan_bucket_recoveries(state, self.inputs)
        matching = [item for item in recoveries if item.key == failure.key]
        self.assertTrue(matching)
        answer = self.adapter.deliver((), 32, recoveries=matching)
        self.assertEqual(answer["recoveries"][0]["status"], "closed")
        self.assertEqual(issue["state"], "closed")
        self.assertEqual(len(self.posts()), 2)  # first Issue and one recovery comment
        self.assertEqual([c[0] for c in self.api.calls if c[0] == "set_issue_state"], ["set_issue_state"])

    def test_pre_t8b_frozen_delivery_replays_as_unmanaged_on_current_full_replay(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],))
        current = self.planned()[0]
        legacy_key = f"self-test-{current.management['suite']}-{current.management['failure_class']}".replace("_", "-")
        legacy = module.reporting.Report(key=legacy_key, title=current.title, observation=current.observation,
            severity=current.severity, labels=current.labels, summary=current.summary, detail=current.detail)
        old_payload = report_outbox.freeze(legacy, "endaye")
        old_payload["fields"].pop("management")
        old_payload["fields"].pop("causal_order")
        box = self.adapter.outbox()
        box.load()
        old_id = batch.digest({"key": legacy.key, "observation": legacy.observation})
        box._persist("queue", {"delivery": old_id, "payload": old_payload})
        self.assertEqual(box.drain_once(self.api)["status"], "delivered")
        before = list(self.posts())
        answer = self.adapter.deliver((current,), 32)
        self.assertEqual(answer["outcomes"], [])
        self.assertEqual(self.posts(), before)
        stored = self.adapter.outbox().load()
        self.assertEqual(len(stored["deliveries"]), 1)
        self.assertIsNone(next(iter(stored["deliveries"].values()))["payload"]["fields"].get("management"))
        self.assertEqual(len(self.api.issues), 1)

    def test_old_unmanaged_payload_defaults_replay_without_duplicate_or_rewrite(self):
        result(self.scheduler, kind="bootstrap", advance=True)
        result(self.scheduler, kind="candidate", base=B, target=C,
               failed=(POLICY.inventory.suites[0].jobs[0],))
        current = next(report for report in self.planned()
                       if report.management is None and "(candidate)" in report.summary)
        self.assertIsNone(current.causal_order)
        old_payload = report_outbox.freeze(current, "endaye")
        old_payload["fields"].pop("management")
        old_payload["fields"].pop("causal_order")
        box = self.adapter.outbox()
        box.load()
        delivery = batch.digest({"key": current.key, "observation": current.observation})
        box._persist("queue", {"delivery": delivery, "payload": old_payload})
        self.assertEqual(box.drain_once(self.api)["status"], "delivered")
        before = list(self.posts())
        answer = self.adapter.deliver((current,), 32)
        self.assertEqual(answer["outcomes"], [])
        self.assertEqual(self.posts(), before)
        stored = self.adapter.outbox().load()
        self.assertEqual(next(iter(stored["deliveries"].values()))["payload"], old_payload)

    def test_review_entry_reconciles_pending_stale_recovery_without_close(self):
        recovery = self.pending_stale_recovery()
        report = module.reporting.Report(key="review-stale-entry", title="review", observation="review/1",
            severity="medium", labels=(module.reporting.REPORT_LABEL,), summary="review", detail="review")
        self.adapter.storage = SimpleNamespace(authenticate_current=lambda: None)
        self.adapter.repository = "endaye/lmdj"
        with mock.patch.object(module.review_failure_report, "collect", return_value=report):
            answer = self.adapter.execute("review", run_id=51, attempt=1, limit=1)
        self.assertEqual(self.adapter.outbox().load()["recoveries"][recovery.recovery_id]["status"], "stale")
        self.assertFalse(any(call[0] == "set_issue_state" for call in self.api.calls))

    def test_legacy_entry_reconciles_pending_stale_recovery_without_close(self):
        recovery = self.pending_stale_recovery()
        report = module.reporting.Report(key="legacy-stale-entry", title="legacy", observation="legacy/1",
            severity="medium", labels=(module.reporting.REPORT_LABEL,), summary="legacy", detail="legacy")
        metadata = SimpleNamespace(error=None, skipped=None, target=C, verdict_status="failed")
        self.adapter.storage = SimpleNamespace(authenticate_current=lambda: None)
        self.adapter.repository = "endaye/lmdj"
        with mock.patch.object(module.reporting, "plan_run", return_value=(metadata, (report,))):
            answer = self.adapter.execute("legacy", run_id=100, attempt=1, limit=1)
        self.assertEqual(self.adapter.outbox().load()["recoveries"][recovery.recovery_id]["status"], "stale")
        self.assertFalse(any(call[0] == "set_issue_state" for call in self.api.calls))

    def test_execute_drain_refreshes_floor_for_pending_recovery(self):
        recovery = self.pending_stale_recovery()
        self.adapter.storage = SimpleNamespace(authenticate_current=lambda: None)
        self.adapter.repository = "endaye/lmdj"
        answer = self.adapter.execute("drain")
        self.assertEqual(answer["status"], "idle")
        self.assertEqual(self.adapter.outbox().load()["recoveries"][recovery.recovery_id]["status"], "stale")
        self.assertFalse(any(call[0] == "set_issue_state" for call in self.api.calls))

    def test_lost_recovery_comment_with_newer_failure_and_handoff_stays_stale(self):
        recovery = self.pending_stale_recovery()
        issue = self.api.issues[0]
        issue["body"] += "\nmaintainer note"
        issue["editor"] = {"login": "maintainer", "type": "User"}
        self.adapter.storage = SimpleNamespace(authenticate_current=lambda: None)
        self.adapter.repository = "endaye/lmdj"
        before_comments = len([call for call in self.api.calls if call[0] == "create_comment"])
        self.adapter.execute("drain")
        self.assertEqual(self.adapter.outbox().load()["recoveries"][recovery.recovery_id]["status"], "stale")
        self.assertEqual(len([call for call in self.api.calls if call[0] == "create_comment"]), before_comments)
        self.assertFalse(any(call[0] == "set_issue_state" for call in self.api.calls))

    def test_explicit_candidate_success_never_recovers_managed_bucket(self):
        _, _ = result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = self.planned()[0]
        self.adapter.deliver((failure,), 32)
        result(self.scheduler, kind="candidate", base=B, target=C)
        state = module.scheduler_state(self.runtime)
        recoveries = module.plan_bucket_recoveries(state, self.inputs)
        self.assertFalse([item for item in recoveries if item.key == failure.key])
        self.assertEqual(self.api.issues[0]["state"], "open")
        self.assertFalse(any(c[0] == "set_issue_state" for c in self.api.calls))

    def test_explicit_candidate_failure_keeps_legacy_unmanaged_key(self):
        result(self.scheduler, kind="bootstrap", advance=True)
        result(self.scheduler, kind="candidate", base=B, target=C,
               failed=(POLICY.inventory.suites[0].jobs[0],))
        report = self.planned()[0]
        self.assertIsNone(report.management)
        self.assertEqual(report.key, "self-test-docs-static-test-failure")
        self.assertEqual(self.adapter.deliver((report,), 32)["outcomes"][0]["status"], "delivered")
        before = list(self.posts())
        self.assertEqual(self.adapter.deliver((report,), 32)["outcomes"], [])
        self.assertEqual(self.posts(), before)

    def test_changed_failure_classes_in_one_suite_recover_as_separate_buckets(self):
        suite = next(s for s in POLICY.inventory.suites if len(s.jobs) > 1)
        selection = test_scope._selection(POLICY, POLICY.suite_ids, ["grouped suite debt"])
        result(self.scheduler, kind="bootstrap", selection=selection,
               failed=(suite.jobs[0],), missing=(suite.jobs[1],), advance=True)
        failures = self.planned()
        self.assertEqual({report.management["failure_class"] for report in failures}, {"test_failure", "missing"})
        self.adapter.deliver(failures, 32)
        result(self.scheduler, kind="auto", base=B, target=C, selection=selection, advance=True)
        recoveries = [recovery for recovery in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                      if recovery.key in {report.key for report in failures}]
        self.assertEqual({recovery.failure_class for recovery in recoveries}, {"test_failure", "missing"})
        for _ in recoveries:
            self.adapter.deliver((), 1, recoveries=recoveries)
        self.assertTrue(all(self.api.issues[index]["state"] == "closed" for index in range(2)))

    def test_stale_success_is_not_allowed_to_override_newer_failure(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        first = self.planned()[0]
        result(self.scheduler, kind="auto", base=B, target=C, failed=(POLICY.inventory.suites[0].jobs[0],))
        all_reports = self.planned()
        newer = all_reports[-1]
        self.adapter.deliver((newer,), 32)
        before = len(self.posts())
        stale = self.adapter.deliver((first,), 32)
        self.assertEqual(stale["outcomes"][0]["status"], "stale")
        self.assertEqual(len(self.posts()), before)

    def test_old_or_human_intervened_bucket_is_not_auto_closed(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = self.planned()[0]
        self.adapter.deliver((failure,), 32)
        issue = self.api.issues[0]
        issue["editor"] = {"login": "maintainer", "type": "User"}
        result(self.scheduler, kind="auto", base=B, target=C)
        recoveries = module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
        answer = self.adapter.deliver((), 32, recoveries=[r for r in recoveries if r.key == failure.key])
        self.assertEqual(answer["recoveries"][0]["status"], "not-applicable")
        self.assertEqual(issue["state"], "open")

    def test_recovery_allows_changed_selection_reasons_and_expanded_scope(self):
        selection = test_scope._selection(POLICY, POLICY.suite_ids, ["initial scope"])
        result(self.scheduler, kind="bootstrap", selection=selection,
               failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = next(item for item in self.planned() if item.management is not None)
        self.adapter.deliver((failure,), 32)
        expanded = test_scope._selection(POLICY, POLICY.suite_ids, ["expanded scope and new reason"])
        result(self.scheduler, kind="auto", base=B, target=C, selection=expanded)
        recovery = next(item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                        if item.key == failure.key)
        self.assertNotEqual(failure.management["selection"], recovery.selection)
        answer = self.adapter.deliver((), 32, recoveries=(recovery,))
        self.assertEqual(answer["recoveries"][0]["status"], "closed")

    def test_crash_after_recovery_comment_does_not_repeat_comment(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = next(item for item in self.planned() if item.management is not None)
        self.adapter.deliver((failure,), 32)
        result(self.scheduler, kind="auto", base=B, target=C)
        recovery = next(item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                        if item.key == failure.key)
        original = self.api.create_comment
        def die(number, body):
            response = original(number, body)
            raise Crash("recovery comment response lost")
        self.api.create_comment = die
        with self.assertRaises(Crash):
            self.adapter.deliver((), 32, recoveries=(recovery,))
        self.api.create_comment = original
        self.assertEqual(self.adapter.deliver((), 32, recoveries=(recovery,))["recoveries"][0]["status"], "closed")
        self.assertEqual(len([c for c in self.api.calls if c[0] == "create_comment"]), 1)

    def test_lost_recovery_close_response_reads_state_without_repatch(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = next(item for item in self.planned() if item.management is not None)
        self.adapter.deliver((failure,), 32)
        result(self.scheduler, kind="auto", base=B, target=C)
        recovery = next(item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                        if item.key == failure.key)
        original = self.api.set_issue_state
        def die(number, state):
            response = original(number, state)
            raise Crash("recovery close response lost")
        self.api.set_issue_state = die
        with self.assertRaises(Crash):
            self.adapter.deliver((), 32, recoveries=(recovery,))
        self.api.set_issue_state = original
        self.assertEqual(self.adapter.deliver((), 32, recoveries=(recovery,))["recoveries"][0]["status"], "closed")
        self.assertEqual(len([c for c in self.api.calls if c[0] == "set_issue_state"]), 1)

    def test_stale_close_claim_reconciles_exact_patch_without_forbidden_reducer_event(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = next(item for item in self.planned() if item.management is not None)
        self.adapter.deliver((failure,), 32)
        result(self.scheduler, kind="auto", base=B, target=C, advance=True)
        recovery = next(item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                        if item.key == failure.key)
        original = self.api.set_issue_state

        def die(number, state):
            response = original(number, state)
            raise Crash("recovery close response lost")

        self.api.set_issue_state = die
        with self.assertRaises(Crash):
            self.adapter.deliver((), 32, recoveries=(recovery,))
        self.api.set_issue_state = original
        result(self.scheduler, kind="auto", base=C, target="d" * 40,
               failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        answer = self.adapter.deliver((), 32, recoveries=(recovery,))
        self.assertEqual(answer["recoveries"][0]["status"], "closed")
        self.assertEqual(self.adapter.outbox().load()["recoveries"][recovery.recovery_id]["status"], "closed")
        self.assertEqual(len([call for call in self.api.calls if call[0] == "set_issue_state"]), 1)

    def test_new_recovery_mismatched_issue_number_never_patches(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = next(item for item in self.planned() if item.management is not None)
        self.adapter.deliver((failure,), 32)
        issue = self.api.issues[0]
        recorded = issue["number"]
        issue["number"] = recorded + 100
        result(self.scheduler, kind="auto", base=B, target=C, advance=True)
        recovery = next(item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                        if item.key == failure.key)
        answer = self.adapter.deliver((), 32, recoveries=(recovery,))
        self.assertEqual(answer["recoveries"][0]["status"], "not-applicable")
        self.assertFalse(any(call[0] == "set_issue_state" for call in self.api.calls))

    def test_resumed_close_claim_mismatched_issue_number_never_repatches(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = next(item for item in self.planned() if item.management is not None)
        self.adapter.deliver((failure,), 32)
        result(self.scheduler, kind="auto", base=B, target=C, advance=True)
        recovery = next(item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                        if item.key == failure.key)
        original = self.api.set_issue_state

        def die(number, state):
            raise Crash("close PATCH response lost before remote mutation")

        self.api.set_issue_state = die
        with self.assertRaises(Crash):
            self.adapter.deliver((), 32, recoveries=(recovery,))
        self.api.set_issue_state = original
        issue = self.api.issues[0]
        issue["number"] += 100
        before = len([call for call in self.api.calls if call[0] == "set_issue_state"])
        answer = self.adapter.deliver((), 32, recoveries=(recovery,))
        self.assertEqual(answer["recoveries"][0]["status"], "needs-reconciliation")
        self.assertEqual(len([call for call in self.api.calls if call[0] == "set_issue_state"]), before)

    def test_recovery_budget_skips_terminal_keys_and_reaches_later_key(self):
        selection = test_scope._selection(POLICY, POLICY.suite_ids, ["recovery fairness"])
        result(self.scheduler, kind="bootstrap", selection=selection,
               failed=tuple(s.jobs[0] for s in POLICY.inventory.suites[:2]), advance=True)
        failures = [report for report in self.planned() if report.management is not None]
        self.assertEqual(len(failures), 2)
        self.adapter.deliver(failures, 32)
        result(self.scheduler, kind="auto", base=B, target=C, selection=selection, advance=True)
        recoveries = [recovery for recovery in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                      if recovery.key in {report.key for report in failures}]
        self.assertEqual(len(recoveries), 2)
        first = recoveries[0]
        first_answer = self.adapter.deliver((), 1, recoveries=recoveries)
        self.assertEqual(first_answer["recoveries"][0]["status"], "closed")
        before = len([call for call in self.api.calls if call[0] == "set_issue_state"])
        second_answer = self.adapter.deliver((), 1, recoveries=recoveries)
        self.assertEqual(second_answer["recoveries"][0]["status"], "closed")
        self.assertEqual(len([call for call in self.api.calls if call[0] == "set_issue_state"]), before + 1)
        third_before = len([call for call in self.api.calls if call[0] == "set_issue_state"])
        third_answer = self.adapter.deliver((), 1, recoveries=recoveries)
        self.assertEqual(third_answer["recoveries"], [])
        self.assertEqual(len([call for call in self.api.calls if call[0] == "set_issue_state"]), third_before)
        self.assertEqual(self.adapter.outbox().load()["recoveries"][first.recovery_id]["status"], "closed")

    def test_human_inapplicable_recovery_is_reserved_before_later_key(self):
        selection = test_scope._selection(POLICY, POLICY.suite_ids, ["human handoff fairness"])
        result(self.scheduler, kind="bootstrap", selection=selection,
               failed=tuple(s.jobs[0] for s in POLICY.inventory.suites[:2]), advance=True)
        failures = [report for report in self.planned() if report.management is not None]
        self.assertEqual(len(failures), 2)
        self.adapter.deliver(failures, 32)
        first_issue = self.api.issues[0]
        first_issue["body"] += "\nmaintainer investigation"
        result(self.scheduler, kind="auto", base=B, target=C, selection=selection, advance=True)
        recoveries = [recovery for recovery in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                      if recovery.key in {report.key for report in failures}]
        states = []
        results = []
        for _ in range(3):
            answer = self.adapter.deliver((), 1, recoveries=recoveries)
            results.append([item["status"] for item in answer["recoveries"]])
            states.append([issue["state"] for issue in self.api.issues])
        self.assertEqual(results, [["not-applicable"], ["closed"], []])
        self.assertEqual(states, [["open", "open"], ["open", "closed"], ["open", "closed"]])
        self.assertEqual(len([call for call in self.api.calls if call[0] == "set_issue_state"]), 1)
        stored = self.adapter.outbox().load()
        self.assertEqual(stored["recoveries"][recoveries[0].recovery_id]["status"], "not-applicable")

    def test_legacy_same_key_precedes_managed_bucket_without_adoption(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = self.planned()[0]
        self.api.issues.append({"number": 700, "title": "legacy", "body": failure.key_marker,
                                "labels": [module.reporting.REPORT_LABEL], "assignees": [], "state": "open",
                                "user": {"login": "github-actions[bot]", "type": "Bot"}})
        self.adapter.deliver((failure,), 32)
        self.assertEqual(len(self.api.issues), 2)
        self.assertNotEqual(self.api.issues[0]["number"], self.adapter.outbox().load()["buckets"][failure.key])

    def test_recurrence_reopens_the_same_managed_issue(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        first = self.planned()[0]
        self.adapter.deliver((first,), 32)
        issue = self.api.issues[0]
        issue_number = issue["number"]
        issue["state"] = "closed"
        result(self.scheduler, kind="auto", base=B, target=C,
               failed=(POLICY.inventory.suites[0].jobs[0],))
        recurrence = max((report for report in self.planned() if report.key == first.key),
                          key=lambda report: report.causal_order)
        answer = self.adapter.deliver((recurrence,), 32)
        self.assertEqual(answer["outcomes"][0]["status"], "delivered")
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual(issue["number"], issue_number)
        self.assertEqual(issue["state"], "open")
        self.assertEqual(len([call for call in self.api.calls if call[0] == "set_issue_state"]), 1)

    def test_human_body_edit_without_editor_metadata_prevents_recovery(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = self.planned()[0]
        self.adapter.deliver((failure,), 32)
        issue = self.api.issues[0]
        issue["body"] += "\nmaintainer note"
        result(self.scheduler, kind="auto", base=B, target=C)
        recovery = next(item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                        if item.key == failure.key)
        before = len([call for call in self.api.calls if call[0] in {"create_comment", "set_issue_state"}])
        answer = self.adapter.deliver((), 32, recoveries=(recovery,))
        self.assertEqual(answer["recoveries"][0]["status"], "not-applicable")
        self.assertEqual(len([call for call in self.api.calls if call[0] in {"create_comment", "set_issue_state"}]), before)
        self.assertEqual(issue["state"], "open")

    def test_later_success_does_not_recover_already_closed_bucket_but_recurrence_can(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = self.planned()[0]
        self.adapter.deliver((failure,), 32)
        result(self.scheduler, kind="auto", base=B, target=C, advance=True)
        first_success = next(item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                             if item.key == failure.key)
        self.assertEqual(self.adapter.deliver((), 32, recoveries=(first_success,))["recoveries"][0]["status"], "closed")
        issue = self.api.issues[0]
        comments = len([call for call in self.api.calls if call[0] == "create_comment"])
        d, e = "d" * 40, "e" * 40
        result(self.scheduler, kind="auto", base=C, target=d, advance=True)
        later_success = max((item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                             if item.key == failure.key), key=lambda item: item.order)
        self.assertEqual(self.adapter.deliver((), 32, recoveries=(later_success,))["recoveries"][0]["status"], "not-applicable")
        self.assertEqual(len([call for call in self.api.calls if call[0] == "create_comment"]), comments)
        result(self.scheduler, kind="auto", base=d, target=e,
               failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        recurrence = max((report for report in self.planned() if report.key == failure.key),
                         key=lambda report: report.causal_order)
        self.adapter.deliver((recurrence,), 32)
        f = "f" * 40
        result(self.scheduler, kind="auto", base=e, target=f, advance=True)
        recovered = max((item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                         if item.key == failure.key), key=lambda item: item.order)
        self.assertEqual(self.adapter.deliver((), 32, recoveries=(recovered,))["recoveries"][0]["status"], "closed")
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual(issue["number"], self.api.issues[0]["number"])
        self.assertEqual(len([call for call in self.api.calls if call[0] == "create_comment"]), comments + 2)

    def test_unknown_recovery_close_state_stays_unresolved_without_repatch(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        failure = self.planned()[0]
        self.adapter.deliver((failure,), 32)
        result(self.scheduler, kind="auto", base=B, target=C)
        recovery = next(item for item in module.plan_bucket_recoveries(module.scheduler_state(self.runtime), self.inputs)
                        if item.key == failure.key)
        original = self.api.set_issue_state
        def unknown(number, state):
            self.api.calls.append(("set_issue_state", number, state))
            raise Crash("close outcome unknown before remote state change")
        self.api.set_issue_state = unknown
        with self.assertRaises(Crash):
            self.adapter.deliver((), 32, recoveries=(recovery,))
        self.api.set_issue_state = original
        before = len([call for call in self.api.calls if call[0] == "set_issue_state"])
        answer = self.adapter.deliver((), 32, recoveries=(recovery,))
        self.assertEqual(answer["recoveries"][0]["status"], "needs-reconciliation")
        self.assertEqual(len([call for call in self.api.calls if call[0] == "set_issue_state"]), before)

    def test_newer_failure_beyond_delivery_limit_blocks_drain_only_recovery(self):
        result(self.scheduler, kind="bootstrap", failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        first = self.planned()[0]
        self.adapter.deliver((first,), 32)
        result(self.scheduler, kind="auto", base=B, target=C,
               failed=(POLICY.inventory.suites[1].jobs[0],), advance=True)
        d, e = "d" * 40, "e" * 40
        result(self.scheduler, kind="auto", base=C, target=d,
               failed=(POLICY.inventory.suites[0].jobs[0],), advance=True)
        result(self.scheduler, kind="auto", base=d, target=e)
        state = module.scheduler_state(self.runtime)
        planned = module.plan_batch_reports("endaye/lmdj", state, self.inputs)
        recovery = next(item for item in module.plan_bucket_recoveries(state, self.inputs)
                        if item.key == first.key)
        answer = self.adapter.deliver(planned, 1, recoveries=(recovery,))
        self.assertEqual(answer["recoveries"][0]["status"], "stale")
        close_count = len([call for call in self.api.calls if call[0] == "set_issue_state"])
        drain = self.adapter.outbox().drain_once(self.api, causal_floor={first.key: 3})
        self.assertNotEqual(drain.get("status"), "closed")
        self.assertEqual(len([call for call in self.api.calls if call[0] == "set_issue_state"]), close_count)


class RuntimeJourneyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = runtime_fixture.RuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.review = review_fixture.ConsumerTests()
        self.review.setUp()
        self.api = self.review.api
        self.scheduler_http = self.fixture.api
        self.outbox_http = runtime_fixture.Http(self.fixture.sha)
        self.outbox_http.issue["id"] = "outbox-node"
        self.outbox_http.issue["number"] = 783
        self.config = {"scheduler": self.fixture.config,
            "outbox": {**self.fixture.config, "issue_number": 783, "issue_node_id": "outbox-node", "epoch": "outbox"}}
        self.actual_calls = []
        review_get = self.api._request
        def request(method, path, *, body=None, raw=False):
            self.actual_calls.append((method, path, deepcopy(body)))
            if method == "POST" and path == "/graphql":
                number = body["variables"]["number"]
                self.assertIn(number, (782, 783))
                return (self.scheduler_http if number == 782 else self.outbox_http)._request(method, path, body=body, raw=raw)
            if "/issues/783" in path:
                response = self.outbox_http._request(method, path.replace("/issues/783", "/issues/782"), body=body, raw=raw)
                if isinstance(response, dict) and response.get("number") == 782:
                    response["number"] = 783
                return response
            if "/issues/782" in path or "/attempts/1/jobs?" in path or any(f"/actions/runs/{run}/" in path for run in (17, 18, 19)) or "/git/ref/" in path or "/actions/workflows/7" in path or "/contents/.github/workflows/self-test-report.yml" in path or "/compare/" in path:
                return self.scheduler_http._request(method, path, body=body, raw=raw)
            self.assertIsNone(body)
            self.assertFalse(raw)
            return review_get(method, path)
        self.api._request = request

    def make(self, config=None, environment=None):
        return module.ReportRuntime(config or self.config, root=self.fixture.root,
            environment=environment or self.fixture.env, api=self.api)

    def initialize(self):
        return self.make().execute("init-outbox")

    def test_init_only_writes_reserved_outbox_and_does_not_set_baseline(self):
        answer = self.initialize()
        self.assertEqual(answer["action"], "initialized")
        self.assertIsNone(answer["state"])
        self.assertEqual(self.scheduler_http.issue["body"], batch_runtime.EMPTY_TEMPLATE)
        self.assertEqual([p for m, p, _ in self.actual_calls if m == "PATCH"], ["/repos/endaye/lmdj/issues/783"])

    def install_legacy(self):
        source = full_legacy_api()
        for name in ("get_run", "get_workflow", "compare", "list_artifacts", "download_artifact", "get_policy"):
            setattr(self.api, name, getattr(source, name))
        return source

    def test_legacy_full_reaches_authenticated_http_journal_and_exact_receipt(self):
        self.initialize()
        source = self.install_legacy()
        scheduler_before = deepcopy(self.scheduler_http.issue)
        answer = self.make().execute("legacy", run_id=100, attempt=1)
        self.assertEqual(answer["source"], "self-test-v1")
        self.assertEqual(answer["verdict_status"], "failed")
        state = self.make().outbox().load()
        self.assertEqual(len(state["deliveries"]), 1)
        delivery = next(iter(state["deliveries"].values()))
        self.assertEqual(delivery["status"], "delivered")
        self.assertEqual(delivery["receipt"], {"issue_number": self.api.issues[0]["number"], "comment_id": None})
        self.assertEqual(self.api.issues[0]["body"], delivery["payload"]["issue_body"])
        self.assertEqual(scheduler_before, self.scheduler_http.issue)
        self.assertFalse(source.issues)  # the source adapter only reads evidence
        self.make().execute("legacy", run_id=100, attempt=1)
        self.assertEqual(len(self.api.issues), 1)
        self.assertFalse(self.api.comments)

    def test_legacy_unknown_run_api_does_not_queue_or_post(self):
        self.initialize()
        source = self.install_legacy()
        source.runs.clear()
        with self.assertRaises(Exception):
            self.make().execute("legacy", run_id=100, attempt=1)
        self.assertFalse(self.api.issues)
        self.assertFalse(self.outbox_http.comments)

    def test_legacy_queued_report_can_drain_after_artifact_expiry(self):
        self.initialize()
        source = self.install_legacy()
        _, planned = module.reporting.plan_run(source, 100, attempt=1, repository="endaye/lmdj", sleep=lambda _: None)
        box = self.make().outbox()
        box.load()
        key = batch.digest({"key": planned[0].key, "observation": planned[0].observation})
        box._persist("queue", {"delivery": key, "payload": report_outbox.freeze(planned[0], "endaye")})
        source.blobs.clear()
        self.assertEqual(self.make().execute("drain")["status"], "delivered")
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual(self.make().execute("drain"), {"status": "idle"})

    def test_legacy_old_frozen_fields_replay_through_current_entry_without_duplicate(self):
        self.initialize()
        source = self.install_legacy()
        _, planned = module.reporting.plan_run(source, 100, attempt=1, repository="endaye/lmdj", sleep=lambda _: None)
        old_payload = report_outbox.freeze(planned[0], "endaye")
        old_payload["fields"].pop("management")
        old_payload["fields"].pop("causal_order")
        box = self.make().outbox()
        box.load()
        key = batch.digest({"key": planned[0].key, "observation": planned[0].observation})
        box._persist("queue", {"delivery": key, "payload": old_payload})
        answer = self.make().execute("legacy", run_id=100, attempt=1, limit=1)
        self.assertEqual(answer["outcomes"], [])
        self.assertEqual(answer["drain"]["status"], "delivered")
        stored = self.make().outbox().load()
        self.assertEqual(next(iter(stored["deliveries"].values()))["payload"], old_payload)
        self.assertEqual(len(self.api.issues), 1)

    def test_review_old_frozen_fields_replay_through_current_entry_without_duplicate(self):
        self.initialize()
        planned = module.review_failure_report.collect(self.api, "endaye/lmdj", 51, 1)
        old_payload = report_outbox.freeze(planned, "endaye")
        old_payload["fields"].pop("management")
        old_payload["fields"].pop("causal_order")
        box = self.make().outbox()
        box.load()
        key = batch.digest({"key": planned.key, "observation": planned.observation})
        box._persist("queue", {"delivery": key, "payload": old_payload})
        answer = self.make().execute("review", run_id=51, attempt=1, limit=1)
        self.assertEqual(answer["outcomes"], [])
        self.assertEqual(answer["drain"]["status"], "delivered")
        stored = self.make().outbox().load()
        self.assertEqual(next(iter(stored["deliveries"].values()))["payload"], old_payload)
        self.assertEqual(len(self.api.issues), 1)

    def test_legacy_cli_passes_explicit_run_attempt_to_outbox(self):
        self.initialize()
        self.install_legacy()
        with tempfile.TemporaryDirectory() as directory:
            config, summary = Path(directory) / "config.json", Path(directory) / "summary"
            config.write_text(json.dumps(self.config))
            with mock.patch.dict("os.environ", self.fixture.env, clear=True), mock.patch.object(
                    batch_runtime, "UrllibGitHubApi", return_value=self.api):
                code = module.main(["--config", str(config), "--root", str(self.fixture.root), "--summary", str(summary),
                                    "legacy", "--run-id", "100", "--attempt", "1"])
            self.assertEqual(code, 0)
            self.assertIn('"source": "self-test-v1"', summary.read_text())
            self.assertEqual(len(self.api.issues), 1)

    def test_all_backends_failure_zip_reaches_issue_and_real_authenticated_outbox(self):
        self.initialize()
        answer = self.make().execute("review", run_id=51, attempt=1)
        self.assertEqual(answer["outcomes"][0]["status"], "delivered")
        self.assertEqual(len(self.api.issues), 1)
        self.assertIn("not a product self-test verdict", self.api.issues[0]["body"])
        events = self.make().outbox().load()
        self.assertEqual([d["status"] for d in events["deliveries"].values()], ["delivered"])
        self.assertFalse(any("/pulls" in p for _, p, _ in self.actual_calls))
        self.make().execute("review", run_id=51, attempt=1)
        self.assertEqual(len(self.api.issues), 1)

    def test_valid_review_with_findings_writes_nothing(self):
        self.review.history = [review_scope.observe_attempt(POLICY, backend="glm", returncode=0,
            output=json.dumps({"schema": review_scope.REVIEW_SCHEMA, "summary": "Bug", "findings": [
                {"path": "a.py", "line": 1, "body": "Bug"}], "test_scope": {"labels": ["test:full"], "reason": "shared"}}))]
        self.review.save()
        self.assertEqual(self.make().execute("review", run_id=51, attempt=1), {"status": "not-applicable"})
        self.assertFalse(self.api.issues)
        self.assertFalse(self.outbox_http.comments)

    def test_failed_finalizer_lost_post_response_recovers_without_source_or_second_post(self):
        self.review.finalize_with_current_producer()
        self.initialize()
        original = self.api.create_issue
        def lost(**kwargs):
            original(**kwargs)
            raise Crash('response lost after Issue creation')
        self.api.create_issue = lost
        with self.assertRaises(Crash):
            self.make().execute('review', run_id=51, attempt=1)
        state = self.make().outbox().load()
        key, claimed = next(iter(state['deliveries'].items()))
        self.assertEqual(claimed['status'], 'claimed')
        self.assertIsNone(claimed['ack'])
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual(self.api.issues[0]['body'].encode(), claimed['payload']['issue_body'].encode())
        self.review.artifacts.clear()
        posts = [call for call in self.api.calls if call[0] in {'create_issue', 'create_comment'}]
        self.assertEqual(self.make().execute('drain'), {'status': 'idle'})
        recovered = self.make().outbox().load()['deliveries'][key]
        self.assertEqual(recovered['status'], 'delivered')
        self.assertEqual(recovered['payload'], claimed['payload'])
        self.assertEqual(recovered['receipt'], {'issue_number': self.api.issues[0]['number'], 'comment_id': None})
        self.assertEqual(self.make().execute('drain'), {'status': 'idle'})
        self.assertEqual([call for call in self.api.calls if call[0] in {'create_issue', 'create_comment'}], posts)

    def settled_batch(self):
        self.initialize()
        start = self.fixture.start()
        verdict = self.fixture.evidence(start["request"], failed_job="docs-static")
        self.scheduler_http.add_run(18)
        self.outbox_http.add_run(18)
        settled = self.fixture.make(18).reconcile(execute=False)
        saved = settled["state"]["results"][start["request"]["id"]]["reference"]
        self.assertEqual(batch_runtime.decode_reference(saved), verdict)
        self.fixture.env["GITHUB_RUN_ID"] = "18"
        return verdict

    def test_real_executor_artifact_persisted_reference_reaches_issue_after_artifact_loss(self):
        verdict = self.settled_batch()
        before = deepcopy((self.scheduler_http.issue, self.scheduler_http.comments))
        self.scheduler_http.downloads.clear()
        answer = self.make().execute("batches", limit=1)
        self.assertEqual(answer["outcomes"][0]["status"], "delivered")
        self.assertIn(verdict["evidence_digest"], self.api.issues[0]["body"])
        self.assertIn("docs-static", self.api.issues[0]["body"])
        self.assertEqual(before, (self.scheduler_http.issue, self.scheduler_http.comments))
        buckets = self.make().outbox().load()["buckets"]
        self.assertEqual(len(buckets), 1)
        self.assertTrue(next(iter(buckets)).endswith("-docs-static-test-failure"))
        self.assertEqual(next(iter(buckets.values())), self.api.issues[0]["number"])

    def test_real_git_historical_policy_survives_new_control(self):
        verdict = self.settled_batch()
        file = self.fixture.root / "scripts/ci/test_scope_policy.json"
        document = json.loads(file.read_text())
        document["none_prefixes"].append("docs/extra-notes/")
        file.write_text(json.dumps(document))
        self.fixture.git("add", "scripts/ci/test_scope_policy.json")
        self.fixture.git("commit", "-qm", "new policy")
        new_sha = self.fixture.git("rev-parse", "HEAD")
        self.scheduler_http.sha = self.outbox_http.sha = new_sha
        self.scheduler_http.add_run(19)
        self.outbox_http.add_run(19)
        self.fixture.env["GITHUB_RUN_ID"] = "19"
        self.fixture.env["GITHUB_SHA"] = new_sha
        self.assertNotEqual(test_scope.load_policy(self.fixture.root).digest, verdict["identity"]["policy_digest"])
        self.make().execute("batches", limit=1)
        self.assertIn(verdict["identity"]["policy_digest"], self.api.issues[0]["body"])

    def test_authenticated_scheduler_human_edit_prevents_any_issue_write(self):
        self.settled_batch()
        self.scheduler_http.comments[-1]["editor"] = {"__typename": "User", "id": "human"}
        self.scheduler_http.comments[-1]["lastEditedAt"] = "2026-09-08T00:00:01Z"
        with self.assertRaises(Exception):
            self.make().execute("batches")
        self.assertFalse(self.api.issues)
        self.assertFalse(self.outbox_http.comments)

    def test_pending_authenticated_scheduler_never_patches_checkpoint(self):
        self.initialize()
        self.fixture.make().initialize()
        self.scheduler_http.lose = "observe"
        with self.assertRaises(Exception):
            self.fixture.make().reconcile(execute=False)
        checkpoint = self.scheduler_http.issue["body"]
        self.actual_calls.clear()
        with self.assertRaisesRegex(Exception, "only its controller"):
            self.make().execute("batches")
        self.assertEqual(self.scheduler_http.issue["body"], checkpoint)
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.actual_calls))
        self.assertFalse(self.api.issues)

    def test_bad_failure_artifact_does_not_queue_or_create_issue(self):
        self.review.documents["failure.json"]["attempts"][0]["error_class"] = "timeout"
        with self.assertRaises(Exception):
            self.make().execute("review", run_id=51, attempt=1)
        self.assertFalse(self.api.issues)
        self.assertFalse(self.outbox_http.comments)

    def test_closed_mapper_is_not_applicable(self):
        self.review.jobs[0]["conclusion"] = "skipped"
        for name, step, conclusion in (("Resolve review target", "Resolve the Pull Request head", "skipped"),
                                      ("Publish review and scope", "Map merged PR without another AI call", "success")):
            self.review.jobs.append(dict(id=len(name), name=name, run_id=51, run_attempt=1, status="completed", conclusion="success",
                steps=[dict(name=step, conclusion=conclusion)]))
        self.assertEqual(self.make().execute("review", run_id=51, attempt=1), {"status": "not-applicable"})
        self.assertFalse(self.api.issues)

    def test_same_issue_config_is_rejected_before_any_http(self):
        config = deepcopy(self.config)
        config["outbox"] = deepcopy(config["scheduler"])
        with self.assertRaisesRegex(ValueError, "aliases"):
            self.make(config)
        self.assertFalse(self.actual_calls)

    def test_missing_short_lock_prevents_all_writes(self):
        with self.assertRaisesRegex(Exception, "lock"):
            self.make(environment={**self.fixture.env, "BATCH_WRITER_LOCK": ""}).execute("init-outbox")
        self.assertFalse(self.outbox_http.comments)
        self.assertFalse(self.api.issues)

    def test_existing_scheduler_config_cannot_be_overridden_with_new_permission_identity(self):
        config = deepcopy(self.config)
        config["outbox"]["workflow_id"] = 999
        with self.assertRaisesRegex(ValueError, "writer authority"):
            self.make(config)
        self.assertFalse(self.actual_calls)

    def test_drain_replays_queued_report_without_source_artifact(self):
        self.initialize()
        planned = module.review_failure_report.collect(self.api, "endaye/lmdj", 51, 1)
        box = self.make().outbox()
        key = batch.digest({"key": planned.key, "observation": planned.observation})
        box.load()
        box._persist("queue", {"delivery": key, "payload": report_outbox.freeze(planned, "endaye")})
        self.review.artifacts.clear()
        answer = self.make().execute("drain")
        self.assertEqual(answer["status"], "delivered")
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual(self.make().execute("drain"), {"status": "idle"})

    def test_cli_failure_redacts_exception_and_returns_nonzero(self):
        self.scheduler_http.fail = ("GET", "/repos/endaye/lmdj/git/ref/heads/main")
        with tempfile.TemporaryDirectory() as directory:
            config, summary = Path(directory) / "config.json", Path(directory) / "summary"
            config.write_text(json.dumps(self.config))
            with mock.patch.dict("os.environ", self.fixture.env, clear=True), mock.patch.object(
                    batch_runtime, "UrllibGitHubApi", return_value=self.api):
                code = module.main(["--config", str(config), "--root", str(self.fixture.root), "--summary", str(summary), "drain"])
            self.assertEqual(code, 1)
            self.assertIn('"why"', summary.read_text())
            self.assertIn('"remedy"', summary.read_text())
            self.assertNotIn("SECRET", summary.read_text())
            self.assertFalse(self.api.issues)

    def test_untrusted_current_writer_prevents_source_collection(self):
        self.scheduler_http.jobs[17][0]["name"] = "Other job"
        with self.assertRaises(Exception):
            self.make().execute("review", run_id=51, attempt=1)
        self.assertFalse(self.review.reads)
        self.assertFalse(self.api.issues)

    def test_cli_config_and_exact_attempt_reach_real_consumer_and_durable_issue(self):
        self.initialize()
        with tempfile.TemporaryDirectory() as directory:
            config, summary = Path(directory) / "config.json", Path(directory) / "summary"
            config.write_text(json.dumps(self.config))
            with mock.patch.dict("os.environ", self.fixture.env, clear=True), mock.patch.object(
                    batch_runtime, "UrllibGitHubApi", return_value=self.api):
                code = module.main(["--config", str(config), "--root", str(self.fixture.root), "--summary", str(summary),
                                    "review", "--run-id", "51", "--attempt", "1"])
            self.assertEqual(code, 0)
            self.assertIn('"status": "delivered"', summary.read_text())
            self.assertIn("/51/1/", next(iter(self.make().outbox().load()["deliveries"].values()))["payload"]["fields"]["observation"])
            self.assertEqual(len(self.api.issues), 1)


if __name__ == "__main__":
    unittest.main()
