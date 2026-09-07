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
        self.adapter.outbox = lambda: report_outbox.Outbox(self.outbox.journal(), lambda: True, "outbox")

    def planned(self):
        state = module.scheduler_state(self.runtime)
        return module.plan_batch_reports("endaye/lmdj", state, self.inputs)

    def posts(self):
        return [call for call in self.api.calls if call[0] in {"create_issue", "create_comment"}]

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
        self.assertEqual({r.key for r in reports}, {f"self-test-{suite.id}-test-failure".replace("_", "-"), f"self-test-{suite.id}-missing".replace("_", "-")})
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
        self.assertEqual(self.make().outbox().load()["buckets"], {"self-test-docs-static-test-failure": self.api.issues[0]["number"]})

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
