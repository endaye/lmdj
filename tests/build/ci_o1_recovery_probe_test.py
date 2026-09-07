"""Real protocol/HTTP-boundary journeys; hosted locks and eventual latency remain O1 gaps."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]


class ProbeTests(unittest.TestCase):
    def setUp(self):
        # Import fixtures after discovery: an existing fixture reloads the
        # reporter module, so eager imports can split exception class identity.
        importlib.import_module("ci_self_test_report_test")
        fixtures = importlib.import_module("ci_report_runtime_test")
        # Full discovery can already hold the earlier reporter module through
        # Outbox while the legacy fixture has replaced sys.modules. Compose the
        # probe with the actual driver's module, not an invented exception twin.
        with mock.patch.dict(sys.modules, {"self_test_report": fixtures.report_outbox.reporting}):
            self.module = importlib.import_module("o1_recovery_probe")
        self.f = fixtures.RuntimeJourneyTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.config["scheduler"]["epoch"] = "o1-recovery-scheduler-fixture"
        self.f.config["outbox"]["epoch"] = "o1-recovery-outbox-fixture"
        self.f.make().scheduler.initialize()
        self.f.initialize()
        self.http_calls = []
        original = self.f.api._request
        self.reply_error = None
        self.bad_reply = None
        self.inventory = None
        self.bot = {"login": "github-actions[bot]", "type": "Bot", "id": 41898282,
                    "node_id": self.f.config["outbox"]["bot_node_id"]}
        def request(method, path, *, body=None, raw=False):
            self.http_calls.append((method, path, deepcopy(body)))
            prefix = "/repos/endaye/lmdj/issues"
            if method == "GET" and path.startswith(prefix + "?"):
                if self.inventory is not None:
                    return self.inventory(path)
                return deepcopy(self.f.api.issues)
            if method == "POST" and path == prefix:
                if self.reply_error:
                    raise self.reply_error
                answer = self.f.api.create_issue(**body)
                self.f.api.issues[-1].update(id=90000 + answer["number"], user=deepcopy(self.bot))
                answer = deepcopy(self.f.api.issues[-1])
                answer["labels"] = [{"name": label} for label in answer["labels"]]
                answer["assignees"] = [{"login": user} for user in answer["assignees"]]
            else:
                answer = original(method, path, body=body, raw=raw)
                if method == "POST" and path.endswith("/comments"):
                    answer = {**answer, "body": body["body"], "user": deepcopy(self.bot)}
            if method == "POST" and path != "/graphql" and self.bad_reply:
                return self.bad_reply(answer)
            return answer
        self.f.api._request = request
        self.probe = self.make()

    def make(self):
        return self.module.Probe(self.f.config, root=self.f.fixture.root,
            environment=self.f.fixture.env, api=self.f.api)

    def request(self, operation=None, enabled=True):
        operation = operation or self.module.A
        request = {"operation": operation}
        if enabled:
            request["fault"] = self.module.FAULT
        if operation == self.module.B:
            request.update(review_run_id=51, review_attempt=1)
        return request

    def writes(self):
        return [c for c in self.http_calls if c[0] != "GET" and c[1] != "/graphql"]

    def fresh(self, previous=17, current=18):
        for http in (self.f.scheduler_http, self.f.outbox_http):
            http.jobs[previous][0].update(status="completed", conclusion="failure")
            http.runs[previous].update(status="completed", conclusion="failure")
            http.add_run(current)
        self.f.fixture.env["GITHUB_RUN_ID"] = str(current)
        return self.f.make()

    def test_default_disabled_is_entirely_zero_write(self):
        for operation in (self.module.A, self.module.B):
            self.assertEqual(self.probe.execute(self.probe.prepare(self.request(operation, False))),
                             {"status": "disabled", "remote_writes": 0})
        self.assertEqual(self.http_calls, [])

    def test_prepare_derives_actual_run_and_wire_bytes_without_writes(self):
        prepared = self.probe.prepare(self.request())
        self.assertEqual(prepared["controller"], {"run_id": 17, "attempt": 1, "control_sha": self.f.fixture.sha})
        wire = json.loads(prepared["expected"]["writes"][-1][2]["body"])
        self.assertEqual(wire["writer"]["run_id"], 17)
        self.assertEqual(wire["payload"]["event"], prepared["expected"]["event"])
        self.assertEqual(self.writes(), [])

    def test_a_successful_post_then_fresh_runtime_recovers_once_without_execution(self):
        prepared = self.probe.prepare(self.request())
        with self.assertRaises(self.module.ControlledFailure) as caught:
            self.probe.execute(prepared)
        self.assertEqual(caught.exception.code, 86)
        self.assertEqual(len(self.f.scheduler_http.comments), 1)
        self.assertEqual([c[0] for c in self.writes()], ["PATCH", "POST"])
        anchor = json.loads(self.f.scheduler_http.issue["body"])["payload"]
        self.assertEqual(anchor["pending"]["event"], prepared["expected"]["event"])
        self.assertIsNone(anchor["head"])
        fresh = self.fresh()
        answer = fresh.scheduler.reconcile(execute=False)
        self.assertNotEqual(answer["action"], "execute")
        self.assertIsNone(answer["state"]["processed"])
        self.assertIsNone(answer["state"]["active"])
        self.assertEqual([e["type"] for e in fresh.scheduler.journal().load()], ["observe"])
        self.assertEqual(json.loads(self.f.scheduler_http.issue["body"])["payload"],
                         {"head": anchor["pending"]["digest"], "pending": None})
        snapshot = deepcopy(self.writes())
        self.f.make().scheduler.reconcile(execute=False)
        self.assertEqual(self.writes(), snapshot)

    def test_b_real_consumer_queue_claim_then_fresh_outbox_positive_receipt(self):
        prepared = self.probe.prepare(self.request(self.module.B))
        self.assertEqual(self.writes(), [])
        with self.assertRaises(self.module.ControlledFailure):
            self.probe.execute(prepared)
        self.assertEqual(len(self.f.api.issues), 1)
        issue = self.f.api.issues[0]
        self.assertEqual(issue["body"], prepared["expected"]["frozen"]["issue_body"])
        self.assertIn("not another product defect", issue["body"])
        self.assertIn(prepared["expected"]["source_observation"], issue["body"])
        self.assertTrue(issue["title"].startswith("O1 recovery diagnostic:"))
        self.assertEqual([e["type"] for e in self.f.make().storage.journal().load()], ["queue", "claim"])
        state = self.f.make().outbox().load()
        delivery = state["deliveries"][prepared["expected"]["delivery"]]
        self.assertEqual(delivery["status"], "claimed")
        self.assertIsNone(delivery["ack"])
        fresh = self.fresh()
        self.assertEqual(fresh.execute("drain")["status"], "idle")
        state = fresh.outbox().load()
        self.assertEqual(state["deliveries"][prepared["expected"]["delivery"]]["receipt"],
                         {"issue_number": issue["number"], "comment_id": None})
        self.assertEqual([e["type"] for e in fresh.storage.journal().load()], ["queue", "claim", "delivered"])
        snapshot = deepcopy(self.writes())
        self.assertEqual(self.f.make().execute("drain")["status"], "idle")
        self.assertEqual(snapshot, self.writes())
        self.assertEqual(len(self.f.api.issues), 1)
        self.assertEqual(self.f.scheduler_http.comments, [])

    def test_reused_injector_refuses_nonempty_history(self):
        prepared = self.probe.prepare(self.request())
        with self.assertRaises(self.module.ControlledFailure):
            self.probe.execute(prepared)
        before = deepcopy(self.writes())
        with self.assertRaisesRegex(ValueError, "pending or nonempty"):
            self.make().execute(prepared)
        self.assertEqual(before, self.writes())

    def test_tampered_prepared_digest_or_body_refuses_before_write(self):
        prepared = self.probe.prepare(self.request())
        prepared["expected"]["writes"][0][2]["body"] += " "
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.probe.execute(prepared)
        self.assertEqual(self.writes(), [])

    def test_protected_storage_and_unreserved_epochs_reject(self):
        for number in (807, 817, 819):
            with self.subTest(number=number):
                self.f.config["scheduler"]["issue_number"] = number
                with self.assertRaisesRegex(ValueError, "isolated"):
                    self.make()
        self.f.config["scheduler"]["issue_number"] = 782
        self.f.config["outbox"]["epoch"] = "production"
        with self.assertRaisesRegex(ValueError, "isolated"):
            self.make()
        self.assertEqual(self.writes(), [])

    def test_closed_intent_rejects_endpoint_and_invalid_fault(self):
        for value in ({"operation": self.module.A, "endpoint": "/evil"},
                      {"operation": self.module.A, "fault": "retry"}, {}, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "why:.*remedy:"):
                self.probe.prepare(value)
        self.assertEqual(self.writes(), [])

    def test_invalid_original_post_response_never_becomes_controlled_failure(self):
        self.bad_reply = lambda _: {"id": 1}
        with self.assertRaises(Exception):
            self.probe.execute(self.probe.prepare(self.request()))
        self.assertEqual(len(self.f.scheduler_http.comments), 1)
        self.assertIsNotNone(json.loads(self.f.scheduler_http.issue["body"])["payload"]["pending"])

    def test_original_transport_failure_is_not_overwritten(self):
        self.f.scheduler_http.lose = "POST"
        with self.assertRaises(Exception):
            self.probe.execute(self.probe.prepare(self.request()))
        self.assertEqual(len(self.f.scheduler_http.comments), 1)
        self.assertEqual(self.fresh().scheduler.reconcile(execute=False)["action"], "idle")

    def test_namespace_existing_bucket_rejects_before_queue(self):
        self.f.api.issues.append({"number": 900, "body": "o1-recovery/o1-recovery-outbox-fixture/pr-review/backends-unavailable"})
        with self.assertRaisesRegex(ValueError, "already has a bucket"):
            self.probe.prepare(self.request(self.module.B))
        self.assertEqual(self.writes(), [])

    def test_pagination_reads_second_page_and_never_accepts_incomplete_inventory(self):
        rows = [{"number": n + 1, "body": "unrelated"} for n in range(100)]
        self.inventory = lambda path: rows if path.endswith("page=1") else [{"number": 900, "body": "o1-recovery/o1-recovery-outbox-fixture/x"}]
        with self.assertRaisesRegex(ValueError, "already has a bucket"):
            self.probe.prepare(self.request(self.module.B))
        self.inventory = lambda _: {"error": "unavailable"}
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.probe.prepare(self.request(self.module.B))
        self.assertEqual(self.writes(), [])

    def test_main_drift_between_prepare_and_execution_writes_nothing(self):
        prepared = self.probe.prepare(self.request())
        self.f.scheduler_http.sha = "d" * 40
        with self.assertRaises(Exception):
            self.probe.execute(prepared)
        self.assertEqual(self.writes(), [])

    def test_wrong_source_and_nonfirst_attempt_never_write(self):
        self.f.scheduler_http.runs[17]["workflow_id"] = 999
        with self.assertRaises(Exception):
            self.probe.prepare(self.request())
        self.f.fixture.env["GITHUB_RUN_ATTEMPT"] = "2"
        with self.assertRaises(Exception):
            self.make()
        self.assertEqual(self.writes(), [])

    def test_wrong_bot_receipt_is_not_successful_injection(self):
        self.bad_reply = lambda response: {**response, "user": {**self.bot, "node_id": "wrong"}}
        with self.assertRaises(Exception):
            self.probe.execute(self.probe.prepare(self.request()))
        self.assertEqual(len(self.f.scheduler_http.comments), 1)

    def test_pending_anchor_prepare_never_repairs_it(self):
        self.f.scheduler_http.lose = "POST"
        with self.assertRaises(Exception):
            self.f.make().scheduler.reconcile(execute=False)
        before = deepcopy(self.writes())
        with self.assertRaisesRegex(ValueError, "pending or nonempty"):
            self.probe.prepare(self.request())
        self.assertEqual(before, self.writes())

    def test_absent_receipt_stays_unknown_then_positive_visibility_recovers(self):
        prepared = self.probe.prepare(self.request(self.module.B))
        with self.assertRaises(self.module.ControlledFailure):
            self.probe.execute(prepared)
        issue = self.f.api.issues.pop()
        fresh = self.fresh()
        before = deepcopy(self.writes())
        answer = fresh.execute("drain")
        self.assertEqual(answer["status"], "needs-reconciliation")
        self.assertIn("do not automatically repeat", answer["remedy"])
        self.assertEqual(before, self.writes())
        self.f.api.issues.append(issue)
        self.assertEqual(self.f.make().execute("drain")["status"], "idle")
        self.assertEqual(len(self.f.api.issues), 1)
        self.assertEqual(sum(m == "POST" and p == "/repos/endaye/lmdj/issues" for m, p, _ in self.writes()), 1)

    def test_original_403_keeps_refused_leg_not_controlled_success(self):
        self.reply_error = self.module.reporting.GitHubApiError(403, "forced refusal")
        with self.assertRaises(Exception):
            self.probe.execute(self.probe.prepare(self.request(self.module.B)))
        self.assertEqual(self.f.api.issues, [])
        self.assertEqual([e["type"] for e in self.f.make().storage.journal().load()], ["queue", "claim", "refused"])
        self.assertEqual(self.fresh().execute("drain")["status"], "needs-reconciliation")

    def test_original_503_and_timeout_leave_claim_without_fake_success(self):
        for error in (self.module.reporting.GitHubApiError(503, "unavailable"), TimeoutError("lost")):
            with self.subTest(error=type(error).__name__):
                # Independent complete fixture per case: no claim reset.
                other = ProbeTests()
                other.setUp()
                try:
                    other.reply_error = error
                    with self.assertRaises(Exception):
                        other.probe.execute(other.probe.prepare(other.request(other.module.B)))
                    self.assertEqual([e["type"] for e in other.f.make().storage.journal().load()], ["queue", "claim"])
                    self.assertEqual(other.fresh().execute("drain")["status"], "needs-reconciliation")
                    self.assertEqual(len([c for c in other.writes() if c[:2] == ("POST", "/repos/endaye/lmdj/issues")]), 1)
                finally:
                    other.doCleanups()

    def test_unknown_body_or_extra_write_is_rejected_before_http(self):
        prepared = self.probe.prepare(self.request())
        adapter = self.module.SuppressingApi(self.f.api, prepared, self.f.config)
        with self.assertRaisesRegex(ValueError, "unexpected"):
            adapter._request("POST", "/repos/endaye/lmdj/issues", body={"body": "unrelated"})
        self.assertEqual(self.writes(), [])

    def test_cli_default_is_disabled_and_duplicate_keys_are_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, request, summary = [root / name for name in ("config", "request", "summary")]
            config.write_text(json.dumps(self.f.config))
            request.write_text(json.dumps(self.request(enabled=False)))
            argv = ["--config", str(config), "--request", str(request), "--summary", str(summary), "--root", str(self.f.fixture.root)]
            with mock.patch.dict("os.environ", self.f.fixture.env):
                self.assertEqual(self.module.main(argv), 0)
                self.assertIn('"remote_writes": 0', summary.read_text())
                request.write_text('{"operation":"journal-append-response","operation":"outbox-business-response"}')
                self.assertEqual(self.module.main(argv), 1)
            self.assertEqual(self.writes(), [])

    def test_valid_null_body_inventory_is_empty_but_missing_body_is_invalid(self):
        self.inventory = lambda _: [{"number": 10, "body": None}]
        self.probe.prepare(self.request(self.module.B))
        self.inventory = lambda _: [{"number": 10}]
        with self.assertRaisesRegex(ValueError, "identity/body"):
            self.probe.prepare(self.request(self.module.B))
        self.assertEqual(self.writes(), [])

    def test_success_receipt_title_labels_and_assignees_must_match_frozen_post(self):
        for field, value in (("title", "Wrong"), ("labels", []), ("assignees", [])):
            with self.subTest(field=field):
                other = ProbeTests()
                other.setUp()
                try:
                    other.bad_reply = lambda reply: {**reply, field: value}
                    with self.assertRaises(Exception):
                        other.probe.execute(other.probe.prepare(other.request(other.module.B)))
                    self.assertEqual([e["type"] for e in other.f.make().storage.journal().load()], ["queue", "claim"])
                    self.assertEqual(len(other.f.api.issues), 1)
                finally:
                    other.doCleanups()

    def test_a_invisible_comment_blocks_until_original_receipt_returns(self):
        with self.assertRaises(self.module.ControlledFailure):
            self.probe.execute(self.probe.prepare(self.request()))
        comment = self.f.scheduler_http.comments.pop()
        fresh = self.fresh()
        before = deepcopy(self.writes())
        with self.assertRaises(Exception):
            fresh.scheduler.reconcile(execute=False)
        self.assertEqual(before, self.writes())
        self.f.scheduler_http.comments.append(comment)
        self.assertEqual(self.f.make().scheduler.reconcile(execute=False)["action"], "idle")
        self.assertEqual(len(self.f.scheduler_http.comments), 1)

    def test_b_404_is_unknown_not_authority_to_repost(self):
        with self.assertRaises(self.module.ControlledFailure):
            self.probe.execute(self.probe.prepare(self.request(self.module.B)))
        fresh = self.fresh()
        self.f.api.failures["list_issues"] = [404]
        before = deepcopy(self.writes())
        self.assertEqual(fresh.execute("drain")["status"], "needs-reconciliation")
        self.assertEqual(before, self.writes())
        self.assertEqual(self.f.make().execute("drain")["status"], "idle")
        self.assertEqual(len(self.f.api.issues), 1)

    def test_valid_review_with_findings_is_not_a_failure_probe(self):
        scope = importlib.import_module("review_scope")
        policy = importlib.import_module("ci_report_runtime_test").POLICY
        self.f.review.history = [scope.observe_attempt(policy, backend="glm", returncode=0,
            output=json.dumps({"schema": scope.REVIEW_SCHEMA, "summary": "Bug", "findings": [
                {"path": "a.py", "line": 1, "body": "Bug"}], "test_scope": {"labels": ["test:full"], "reason": "shared"}}))]
        self.f.review.save()
        with self.assertRaisesRegex(ValueError, "not an authenticated all-backend failure"):
            self.probe.prepare(self.request(self.module.B))
        self.assertEqual(self.writes(), [])

    def test_cli_controlled_failure_is_nonzero_honest_summary_without_execute_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, request, summary = [root / name for name in ("config", "request", "summary")]
            config.write_text(json.dumps(self.f.config))
            request.write_text(json.dumps(self.request()))
            argv = ["--config", str(config), "--request", str(request), "--summary", str(summary), "--root", str(self.f.fixture.root)]
            with mock.patch.object(self.module, "Probe", return_value=self.probe):
                self.assertEqual(self.module.main(argv), 86)
            output = summary.read_text()
            self.assertIn("not a spontaneous GitHub fault", output)
            self.assertNotIn('"execute"', output)
            self.assertEqual(len(self.f.scheduler_http.comments), 1)

    def test_cli_original_failure_is_error_not_injected_and_does_not_leak_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, request, summary = [root / name for name in ("config", "request", "summary")]
            config.write_text(json.dumps(self.f.config))
            request.write_text(json.dumps(self.request()))
            argv = ["--config", str(config), "--request", str(request), "--summary", str(summary), "--root", str(self.f.fixture.root)]
            self.f.scheduler_http.lose = "POST"
            with mock.patch.object(self.module, "Probe", return_value=self.probe):
                self.assertEqual(self.module.main(argv), 1)
            self.assertIn('"status": "error"', summary.read_text())
            self.assertNotIn("SECRET", summary.read_text())

    def test_shared_pair_a_recovery_then_b_recovery_preserves_scheduler_bytes(self):
        with self.assertRaises(self.module.ControlledFailure):
            self.probe.execute(self.probe.prepare(self.request()))
        self.fresh().scheduler.reconcile(execute=False)
        before = deepcopy((self.f.scheduler_http.issue, self.f.scheduler_http.comments))
        probe = self.make()
        with self.assertRaises(self.module.ControlledFailure):
            probe.execute(probe.prepare(self.request(self.module.B)))
        self.assertEqual(before, (self.f.scheduler_http.issue, self.f.scheduler_http.comments))
        self.assertEqual(self.fresh(18, 19).execute("drain")["status"], "idle")
        self.assertEqual(before, (self.f.scheduler_http.issue, self.f.scheduler_http.comments))
        self.assertEqual(len(self.f.api.issues), 1)

    def test_b_pending_scheduler_cannot_repair_during_prepare(self):
        with self.assertRaises(self.module.ControlledFailure):
            self.probe.execute(self.probe.prepare(self.request()))
        before = deepcopy(self.writes())
        with self.assertRaisesRegex(ValueError, "pending append"):
            self.probe.prepare(self.request(self.module.B))
        self.assertEqual(before, self.writes())

    def test_b_rejects_authenticated_nonobserve_scheduler_history(self):
        answer = self.f.fixture.make().reconcile(execute=True)
        self.assertEqual(answer["action"], "execute")
        before = deepcopy(self.writes())
        with self.assertRaisesRegex(ValueError, "not observe-only"):
            self.probe.prepare(self.request(self.module.B))
        self.assertEqual(before, self.writes())


if __name__ == "__main__":
    unittest.main()
