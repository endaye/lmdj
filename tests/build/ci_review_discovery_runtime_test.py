"""Real reducer/Journal/Outbox/collector journeys through strict HTTP fixtures.

The separately owned fixed shared-config loader has its own tests. Here its
constructor boundary is injected for isolated fixture Issue IDs; real Git
discovery config, actual runtime writer authentication and both journals run.
No fixture claims hosted permissions, pagination atomicity or remote recovery.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]
import review_discovery_runtime as module
import review_discovery as protocol
import batch_runtime
import review_scope
import ci_report_runtime_test as reporting_fixture

START, END = "2026-09-08T00:00:00Z", "2026-09-08T01:00:00Z"
NOW = datetime(2026, 9, 8, 1, 2, tzinfo=timezone.utc)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = reporting_fixture.RuntimeJourneyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.core, self.review = self.fixture.fixture, self.fixture.review
        self.api = self.fixture.api
        self.config = {"storage": self.core.config, "source_floor": {"control_sha": self.core.sha, "created_at": START},
                       "review_workflow_id": 42}
        self.shared = deepcopy(self.fixture.config)
        self.shared["scheduler"].update(issue_number=781, issue_node_id="unused-scheduler", epoch="unused-scheduler")
        self.loader_calls = []
        def load_storage(root, environment):
            self.loader_calls.append((root, deepcopy(environment)))
            self.assertEqual(root, self.core.root)
            self.assertEqual(environment["GITHUB_SHA"], self.core.sha)
            return deepcopy(self.shared)
        self.loader = mock.patch.dict(sys.modules, {"incremental_entry": SimpleNamespace(load_storage=load_storage)})
        self.loader.start()
        self.addCleanup(self.loader.stop)
        path = self.core.root / module.CONFIG_PATH
        path.write_text(json.dumps(self.config))
        self.core.git("add", module.CONFIG_PATH)
        self.core.git("commit", "-qm", "fixed fixture discovery config")
        self.core.sha = self.core.git("rev-parse", "HEAD")
        self.core.env["GITHUB_SHA"] = self.core.sha
        for http in (self.fixture.scheduler_http, self.fixture.outbox_http):
            http.sha = self.core.sha
            for run in http.runs.values():
                run["head_sha"] = self.core.sha
        self.review.run.update(created_at="2026-09-08T00:01:00Z")
        self.original = self.api._request
        self.inventory_override = None
        self.metadata_error = False
        self.list_reads = []
        def request(method, path, *, body=None, raw=False):
            if method == "GET" and path.endswith("/actions/workflows/42"):
                return {"id": 42, "path": module.collector.WORKFLOW}
            if method == "GET" and "/actions/workflows/42/runs?" in path:
                self.list_reads.append(path)
                if self.inventory_override:
                    return self.inventory_override(path)
                query = parse_qs(urlsplit(path).query)
                start, end = query["created"][0].split("..")
                values = [deepcopy(self.review.run)] if start <= self.review.run["created_at"] <= end else []
                return {"total_count": len(values), "workflow_runs": values}
            if method == "GET" and path.endswith("/actions/runs/51"):
                if self.metadata_error:
                    raise OSError("SECRET-TOKEN")
                return deepcopy(self.review.run)
            return self.original(method, path, body=body, raw=raw)
        self.api._request = request
        # Initialization is fixture setup through the existing real interface,
        # never performed by DiscoveryRuntime.run.
        self.core.make().initialize()
        self.fixture.initialize()

    def make(self):
        return module.DiscoveryRuntime(self.core.root, environment=self.core.env, api=self.api)

    def run_adapter(self, **kwargs):
        return self.make().run(now=NOW, **kwargs)

    def test_complete_http_to_real_collector_to_durable_outbox_queue_only(self):
        result = self.run_adapter()
        state = self.make().load()
        self.assertEqual("failure-queued", state["runs"]["51/1"]["status"])
        outbox = self.make().outbox.load()
        key = state["runs"]["51/1"]["proof"]["outbox_key"]
        self.assertEqual("queued", outbox["deliveries"][key]["status"])
        self.assertIn("was **not reviewed**", outbox["deliveries"][key]["payload"]["fields"]["summary"])
        self.assertFalse(self.api.issues)
        self.assertEqual({}, result["state"]["unresolved"])

    def test_fresh_process_replay_does_not_queue_or_download_again(self):
        self.run_adapter()
        before = len(self.fixture.outbox_http.comments)
        with mock.patch.object(self.api, "download_artifact", side_effect=AssertionError("terminal source need not redownload")):
            self.run_adapter()
        self.assertEqual(before, len(self.fixture.outbox_http.comments))
        self.assertFalse(self.api.issues)

    def test_temporary_artifact_missing_stays_unresolved_then_recovers(self):
        saved = deepcopy(self.review.artifacts)
        self.review.artifacts.clear()
        first = self.run_adapter()
        self.assertEqual("unresolved", first["state"]["unresolved"]["51/1"]["status"])
        self.assertFalse(self.make().outbox.load()["deliveries"])
        self.review.artifacts[:] = saved
        second = self.run_adapter()
        self.assertEqual({}, second["state"]["unresolved"])
        self.assertEqual(1, len(self.make().outbox.load()["deliveries"]))

    def test_unscanned_later_windows_remain_explicitly_incomplete(self):
        result = self.make().run(now=datetime(2026, 9, 10, tzinfo=timezone.utc))
        self.assertTrue(result["inventory_pending"])
        self.assertEqual("incomplete", result["status"])

    def test_explicit_expiry_is_durable_loss_not_backend_failure(self):
        self.review.artifacts[0]["expired"] = True
        first = self.run_adapter()
        self.assertEqual(["51/1"], first["state"]["retention_lost"])
        self.assertFalse(self.make().outbox.load()["deliveries"])
        self.review.artifacts[0]["expired"] = False
        self.run_adapter()
        self.assertEqual("failure-queued", self.make().load()["runs"]["51/1"]["status"])

    def test_metadata_error_is_persisted_without_terminal_downgrade(self):
        self.run_adapter()
        self.metadata_error = True
        result = self.run_adapter()
        self.assertIn("51", result["state"]["metadata_scan"]["errors"])
        self.assertEqual({}, result["state"]["unresolved"])
        self.assertEqual("failure-queued", self.make().load()["runs"]["51/1"]["status"])
        self.metadata_error = False
        self.assertEqual({}, self.run_adapter()["state"]["metadata_scan"]["errors"])

    def test_partial_inventory_cannot_advance(self):
        self.inventory_override = lambda _: {"total_count": 2, "workflow_runs": [self.review.run]}
        result = self.run_adapter()
        self.assertEqual(START, result["state"]["inventory_frontier"])
        self.assertTrue(result["errors"])
        self.assertFalse(self.make().load()["runs"])

    def test_multiple_real_page_shapes_retain_all_run_ids(self):
        values = [{**self.review.run, "id": n} for n in range(1, 102)]
        def listing(path):
            page = int(parse_qs(urlsplit(path).query)["page"][0])
            return {"total_count": 101, "workflow_runs": values[(page-1)*100:page*100]}
        self.inventory_override = listing
        instance = self.make()
        records = instance.inventory(START, END)
        self.assertEqual(list(range(1, 102)), [r["identity"]["run_id"] for r in records])
        self.assertEqual(2, len(self.list_reads))

    def test_older_than_artifact_default_retention_still_reads_retained_run(self):
        result = self.make().run(now=datetime(2026, 10, 10, tzinfo=timezone.utc))
        self.assertEqual("failure-queued", self.make().load()["runs"]["51/1"]["status"])
        self.assertEqual([], result["state"]["inventory_gaps"])
        self.assertEqual(1, len(self.make().outbox.load()["deliveries"]))

    def test_inventory_repository_numeric_id_mismatch_cannot_advance(self):
        value = deepcopy(self.review.run)
        value["repository"]["id"] = 999
        self.inventory_override = lambda _: {"total_count": 1, "workflow_runs": [value]}
        result = self.run_adapter()
        self.assertEqual(START, result["state"]["inventory_frontier"])
        self.assertTrue(result["errors"])
        self.assertFalse(self.make().load()["runs"])

    def test_inventory_403_or_404_does_not_mean_empty_interval(self):
        for status in (403, 404):
            def unavailable(_):
                raise module.reporting.GitHubApiError(status, "secret unavailable")
            self.inventory_override = unavailable
            result = self.run_adapter()
            self.assertEqual(START, result["state"]["inventory_frontier"])
            self.assertTrue(result["errors"])
            self.assertFalse(self.make().load()["windows"])

    def test_filtered_api_cap_splits_until_exact_dense_second_is_gap(self):
        self.inventory_override = lambda _: {"total_count": 1000, "workflow_runs": []}
        result = self.run_adapter()
        self.assertEqual(START, result["state"]["inventory_frontier"])
        self.assertEqual(1, len(result["state"]["inventory_gaps"]))
        self.assertLessEqual(len(self.list_reads), 18)

    def test_original_run_later_attempt_keeps_first_and_source_failure_gap(self):
        self.run_adapter()
        self.review.run["run_attempt"] = 2
        result = self.run_adapter()
        state = self.make().load()
        self.assertEqual("failure-queued", state["runs"]["51/1"]["status"])
        self.assertEqual("unresolved", state["runs"]["51/2"]["status"])
        self.assertEqual(state["runs"]["51/1"]["created_at"], state["runs"]["51/2"]["created_at"])
        self.assertIn("51/2", result["state"]["unresolved"])
        self.review.run["run_attempt"] = 1
        stale = self.run_adapter()
        self.assertIn("51", stale["state"]["metadata_scan"]["errors"])
        self.assertIn("51/2", stale["state"]["unresolved"])

    def test_valid_later_attempt_is_consumed_by_existing_collector_rules(self):
        self.run_adapter()
        old = deepcopy(self.review.run)
        self.review.run["run_attempt"] = 2
        self.review.identity["run_attempt"] = 2
        self.review.jobs[0]["run_attempt"] = 2
        self.review.artifacts.append({"id": 10, "name": f"pr-review-result-{self.review.identity['head_sha']}-51-2",
                                      "expired": False, "workflow_run": {"id": 51}})
        self.review.save()
        previous = self.api._request
        def request(method, path, *, body=None, raw=False):
            if path.endswith("/actions/runs/51/attempts/1"):
                return old
            if path.endswith("/actions/runs/51/attempts/2"):
                # Actual Actions attempt metadata uses its own creation time,
                # e.g. run 34124875948/2 is 59 seconds after run creation.
                return {**deepcopy(self.review.run), "created_at": "2026-09-08T00:01:59Z"}
            return previous(method, path, body=body, raw=raw)
        self.api._request = request
        def download(artifact):
            self.assertEqual(10, artifact)
            return self.review.download(9)
        self.api.download_artifact = download
        result = self.run_adapter()
        self.assertEqual({}, result["state"]["unresolved"])
        self.assertEqual("failure-queued", self.make().load()["runs"]["51/2"]["status"])
        self.assertEqual(2, len(self.make().outbox.load()["deliveries"]))
        state = self.make().load()
        self.assertEqual(old["created_at"], state["runs"]["51/2"]["created_at"])
        self.assertEqual(state["runs"]["51/1"]["created_at"], state["runs"]["51/2"]["created_at"])
        before = deepcopy(self.fixture.outbox_http.comments)
        self.run_adapter()
        self.assertEqual(before, self.fixture.outbox_http.comments)

    def test_first_attempt_timestamp_can_differ_without_moving_inventory(self):
        previous = self.api._request
        def request(method, path, *, body=None, raw=False):
            if path.endswith("/actions/runs/51/attempts/1"):
                # Actual run 34137319062 has a one-second offset on attempt 1.
                return {**deepcopy(self.review.run), "created_at": "2026-09-08T00:01:01Z"}
            return previous(method, path, body=body, raw=raw)
        self.api._request = request
        self.run_adapter()
        state = self.make().load()
        self.assertEqual("failure-queued", state["runs"]["51/1"]["status"])
        self.assertEqual(self.review.run["created_at"], state["runs"]["51/1"]["created_at"])
        self.assertEqual(END, state["inventory_frontier"])
        self.assertEqual(1, len(self.make().outbox.load()["deliveries"]))
        self.assertFalse(self.api.issues)

    def test_invalid_or_pre_run_attempt_timestamp_cannot_queue(self):
        previous = self.api._request
        for timestamp in ("2026-09-08T00:00:59Z", "not-a-time", None):
            def request(method, path, *, body=None, raw=False):
                if path.endswith("/actions/runs/51/attempts/1"):
                    return {**deepcopy(self.review.run), "created_at": timestamp}
                return previous(method, path, body=body, raw=raw)
            self.api._request = request
            with self.subTest(timestamp=timestamp):
                result = self.run_adapter()
                self.assertEqual("unresolved", result["state"]["unresolved"]["51/1"]["status"])
                self.assertFalse(self.make().outbox.load()["deliveries"])

    def test_later_timestamp_does_not_weaken_exact_source_identity(self):
        previous = self.api._request
        changes = ({"id": 52}, {"run_attempt": 2}, {"workflow_id": 43},
                   {"path": ".github/workflows/foreign.yml"},
                   {"repository": {"full_name": "endaye/lmdj", "id": 999}},
                   {"head_sha": "f" * 40})
        for change in changes:
            def request(method, path, *, body=None, raw=False):
                if path.endswith("/actions/runs/51/attempts/1"):
                    return {**deepcopy(self.review.run), "created_at": "2026-09-08T00:01:01Z", **change}
                return previous(method, path, body=body, raw=raw)
            self.api._request = request
            with self.subTest(change=change):
                result = self.run_adapter()
                self.assertEqual("unresolved", result["state"]["unresolved"]["51/1"]["status"])
                self.assertFalse(self.make().outbox.load()["deliveries"])

    def test_actual_journal_round_budget_continues_in_fresh_process(self):
        values = [{**self.review.run, "id": n} for n in (51, 52)]
        self.inventory_override = lambda _: {"total_count": 2, "workflow_runs": values}
        first = self.run_adapter(limit=1)
        self.assertEqual(1, first["state"]["metadata_scan"]["active"]["position"])
        self.assertEqual("incomplete", first["status"])
        self.inventory_override = None
        second = self.run_adapter(limit=1)
        self.assertIsNone(second["state"]["metadata_scan"]["active"])
        self.assertIn("52", second["state"]["metadata_scan"]["errors"])
        self.assertEqual(1, second["state"]["metadata_scan"]["round"])

    def test_valid_review_does_not_queue_report(self):
        output = {"schema": review_scope.REVIEW_SCHEMA, "summary": "Inspected", "findings": [],
                  "test_scope": {"labels": ["test:none"], "reason": "Explanatory docs"}}
        self.review.history = [review_scope.observe_attempt(reporting_fixture.review_fixture.POLICY,
            backend="glm", returncode=0, output=json.dumps(output))]
        self.review.save()
        result = self.run_adapter()
        self.assertEqual({}, result["state"]["unresolved"])
        self.assertEqual("valid-review", self.make().load()["runs"]["51/1"]["status"])
        self.assertEqual({}, self.make().outbox.load()["deliveries"])

    def test_queue_append_lost_response_recovers_without_business_post(self):
        self.fixture.outbox_http.lose = "POST"
        with self.assertRaises(Exception):
            self.run_adapter()
        self.fixture.outbox_http.lose = None
        result = self.run_adapter()
        self.assertEqual({}, result["state"]["unresolved"])
        self.assertEqual(1, len(self.make().outbox.load()["deliveries"]))
        self.assertEqual(1, len(self.fixture.outbox_http.comments))
        self.assertFalse(self.api.issues)

    def test_discovery_append_lost_response_recovers_exact_inventory(self):
        self.fixture.scheduler_http.lose = "POST"
        first = self.run_adapter()
        self.assertTrue(first["errors"])
        self.fixture.scheduler_http.lose = None
        self.run_adapter()
        events = self.make().journal.load()
        self.assertEqual(1, sum(event["type"] == "inventory" for event in events))
        self.assertEqual(1, len(self.make().load()["runs"]))

    def test_config_must_come_from_frozen_git_blob(self):
        path = self.core.root / module.CONFIG_PATH
        path.write_text("{}")
        self.assertEqual(42, self.make().config["review_workflow_id"])
        self.core.git("rm", "-f", module.CONFIG_PATH)
        self.core.git("commit", "-qm", "remove fixture configuration")
        self.core.sha = self.core.git("rev-parse", "HEAD")
        self.core.env["GITHUB_SHA"] = self.core.sha
        with self.assertRaises(Exception):
            self.make()

    def test_existing_controller_authentication_is_not_bypassed(self):
        self.core.env["BATCH_WRITER_LOCK"] = "wrong"
        with self.assertRaises(Exception):
            self.run_adapter()

    def test_cli_has_no_execute_output_and_errors_are_sanitized(self):
        summary = self.core.root / "summary.md"
        with mock.patch.object(module, "DiscoveryRuntime", side_effect=OSError("SECRET-TOKEN")):
            self.assertEqual(1, module.main(["--root", str(self.core.root), "--summary", str(summary)]))
        self.assertNotIn("SECRET-TOKEN", summary.read_text())
        self.assertIn("why:", summary.read_text())
        self.assertFalse((self.core.root / "result.json").exists())


if __name__ == "__main__":
    unittest.main()
