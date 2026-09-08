"""Real Git/Runtime/Journal/Outbox adapter journeys; no actual GitHub writes.

HTTP timing, workflow callback depth and step continue-on-error/needs semantics
remain platform integration obligations. These fixtures do not enable T5.
"""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]
# Load the reporter fixture's canonical module before the composition imports;
# its loader registers exception classes used by the fault journeys below.
from ci_self_test_report_test import FakeGitHubApi, full_legacy_api
import incremental_entry as entry
import batch_runtime
import report_runtime
import ci_batch_runtime_test as fixtures


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.RuntimeTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        path = self.f.root / entry.STORAGE_PATH
        path.write_bytes((ROOT / entry.STORAGE_PATH).read_bytes())
        self.f.git("add", entry.STORAGE_PATH)
        self.f.git("commit", "-qm", "reviewed fixed storage fixture")
        self.sha = self.f.git("rev-parse", "HEAD")
        self.config = json.loads(path.read_text())
        self.env = {**self.f.env, "GITHUB_SHA": self.sha, "GITHUB_EVENT_NAME": "push"}
        self.http = {role: fixtures.Http(self.sha) for role in self.config}
        for role, http in self.http.items():
            http.issue.update(id=self.config[role]["issue_node_id"], number=self.config[role]["issue_number"])
        self.scheduler = self.http["scheduler"]
        self.api = FakeGitHubApi()
        self.calls, self.source_runs = [], {}
        self.review = None
        self.add_run(17, event="push")
        self.workflow_ids = {batch_runtime.WORKFLOW: 352307416, ".github/workflows/ci.yml": 9,
                             ".github/workflows/pr-review.yml": 8}
        def request(method, path, *, body=None, raw=False):
            self.calls.append((method, path, deepcopy(body)))
            prefix = "/repos/endaye/lmdj"
            if method == "POST" and path == "/graphql":
                number = body["variables"]["number"]
                role = next(k for k, v in self.config.items() if v["issue_number"] == number)
                return self.http[role]._request(method, path, body=body, raw=raw)
            for role, config in self.config.items():
                if path.startswith(prefix + f"/issues/{config['issue_number']}"):
                    answer = self.http[role]._request(method, path.replace(f"/issues/{config['issue_number']}", "/issues/782"), body=body, raw=raw)
                    if answer.get("number") == 782:
                        answer["number"] = config["issue_number"]
                    return answer
            if method == "GET" and path.startswith(prefix + "/actions/workflows/") and "/runs?" not in path:
                value = path.rsplit("/", 1)[1]
                selected = next((p for p, identifier in self.workflow_ids.items() if value in (str(identifier), p.rsplit("/", 1)[1])), None)
                if selected:
                    return {"id": self.workflow_ids[selected], "path": selected}
            if method == "GET" and path in self.source_runs:
                return deepcopy(self.source_runs[path])
            if self.review is not None and any(piece in path for piece in ("/contents/scripts/ci/", "/contents/.github/workflows/pr-review.yml", "/actions/runs/51/artifacts", "/branches/main")):
                self.assertIsNone(body)
                self.assertFalse(raw)
                return self.review.get(method, path)
            return self.scheduler._request(method, path, body=body, raw=raw)
        self.api._request = request
        # Explicit fixture initialization is separate from Entry, which has no
        # initialization command and must refuse a genuinely empty journal.
        self.make().runtime.initialize()
        report_runtime.ReportRuntime(self.config, root=self.f.root, environment=self.env, api=self.api).execute("init-outbox")
        self.calls.clear()

    def add_run(self, number, *, event="workflow_run"):
        for http in self.http.values():
            http.add_run(number)
            http.runs[number]["workflow_id"] = 352307416
            http.runs[number]["event"] = event
            for key in ("repository", "head_repository"):
                http.runs[number][key]["id"] = 1286600062

    def make(self, run=17, kind=None):
        return entry.Entry(root=self.f.root, environment={**self.env, "GITHUB_RUN_ID": str(run),
            "GITHUB_EVENT_NAME": kind or self.env["GITHUB_EVENT_NAME"]}, api=self.api)

    def push(self):
        return {"repository": {"full_name": "endaye/lmdj"}, "ref": "refs/heads/main", "deleted": False, "after": self.sha}

    def callback(self, run):
        return {"repository": {"full_name": "endaye/lmdj"}, "action": "completed", "workflow_run": deepcopy(run)}

    def finish(self, number):
        self.scheduler.runs[number].update(status="completed", conclusion="failure")
        for job in self.scheduler.jobs[number]:
            job.update(status="completed", conclusion="success")
        return self.callback(self.scheduler.runs[number])

    def writes(self):
        return [(method, path, body) for method, path, body in self.calls if method in {"PATCH", "POST"} and path != "/graphql"]

    def source(self, path, identifier, *, head="a" * 40, branch="main", event="workflow_dispatch", attempt=1):
        document = {"id": identifier, "run_attempt": attempt, "workflow_id": self.workflow_ids[path],
            "path": path, "head_sha": head, "head_branch": branch, "event": event, "status": "completed", "conclusion": "failure",
            "repository": {"id": 1286600062, "full_name": "endaye/lmdj"}}
        self.source_runs[f"/repos/endaye/lmdj/actions/runs/{identifier}/attempts/{attempt}"] = document
        return document

    def test_main_push_authenticates_real_journal_then_returns_only_durable_claim(self):
        answer = self.make().control(self.push())
        self.assertEqual(answer["action"], "execute")
        events = self.make().runtime.journal().load()
        self.assertEqual([row["type"] for row in events], ["observe", "admit", "claim"])
        self.assertEqual(answer["state"]["active"]["claim"], {"run_id": 17, "attempt": 1})
        self.assertEqual(answer["schema"], batch_runtime.SCHEMA)
        self.assertEqual(set(answer), {"schema", "action", "reason", "request", "executor", "state"})

    def test_committed_manifest_ignores_dirty_operator_file(self):
        (self.f.root / entry.STORAGE_PATH).write_text('{"scheduler":"untrusted"}')
        self.assertEqual(entry.load_storage(self.f.root, self.env), self.config)

    def test_authenticated_roots_emit_one_closed_source_witness(self):
        for kind in ("push", "schedule"):
            with self.subTest(kind=kind):
                self.scheduler.runs[17]["event"] = kind
                payload = self.push() if kind == "push" else {"repository": self.push()["repository"]}
                payload["private_fixture"] = "must-not-appear"
                output = io.StringIO()
                with redirect_stdout(output):
                    answer = self.make(kind=kind).control(payload)
                lines = output.getvalue().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertEqual(json.loads(lines[0]), {
                    "schema": "lmdj.ci-source-witness.v1",
                    "current": {"run_id": 17, "attempt": 1, "control": self.sha, "event": kind},
                    "source_family": kind, "source_run": None})
                self.assertEqual(set(answer), {"schema", "action", "reason", "request", "executor", "state"})
                self.assertNotIn("must-not-appear", output.getvalue())

    def test_authenticated_callback_witness_binds_actual_parent_not_depth(self):
        self.make().control(self.push())
        payload = self.finish(17)
        self.add_run(18)
        output = io.StringIO()
        with redirect_stdout(output):
            result = self.make(18, "workflow_run").control(payload)
        self.assertEqual(json.loads(output.getvalue()), {
            "schema": "lmdj.ci-source-witness.v1",
            "current": {"run_id": 18, "attempt": 1, "control": self.sha, "event": "workflow_run"},
            "source_family": "batch", "source_run": {"id": 17, "attempt": 1}})
        self.assertIsNone(result["state"]["active"])
        self.assertIn("/repos/endaye/lmdj/actions/runs/17/attempts/1", [path for _, path, _ in self.calls])
        # An authenticated idle parent is still traceable without inventing
        # admission or a depth number for the next completed callback.
        idle_payload = self.finish(18)
        self.add_run(19)
        self.calls.clear()
        output = io.StringIO()
        with redirect_stdout(output):
            idle = self.make(19, "workflow_run").control(idle_payload)
        self.assertEqual(json.loads(output.getvalue())["source_run"], {"id": 18, "attempt": 1})
        self.assertEqual(idle["action"], "idle")
        self.assertFalse(self.writes())

    def test_failed_current_or_source_authentication_emits_no_witness(self):
        output = io.StringIO()
        with redirect_stdout(output):
            with self.assertRaises(Exception):
                self.make().control(dict(self.push(), deleted=True))
            self.scheduler.runs[17]["event"] = "workflow_dispatch"
            with self.assertRaises(Exception):
                self.make().control(self.push())
            self.scheduler.runs[17]["event"] = "workflow_run"
            source = self.source(".github/workflows/ci.yml", 100)
            payload = self.callback(source)
            payload["workflow_run"]["head_sha"] = "f" * 40
            with self.assertRaises(Exception):
                self.make(kind="workflow_run").control(payload)
        self.assertEqual(output.getvalue(), "")
        self.assertFalse(self.writes())

    def test_wrong_head_and_missing_committed_manifest_are_rejected(self):
        with self.assertRaises(Exception):
            entry.load_storage(self.f.root, {**self.env, "GITHUB_SHA": "f" * 40})
        self.f.git("rm", entry.STORAGE_PATH)
        self.f.git("commit", "-qm", "missing storage fixture")
        with self.assertRaises(Exception):
            entry.load_storage(self.f.root, {**self.env, "GITHUB_SHA": self.f.git("rev-parse", "HEAD")})

    def test_no_automatic_initialization_of_empty_scheduler(self):
        self.scheduler.issue["body"] = batch_runtime.EMPTY_TEMPLATE
        with self.assertRaises(Exception):
            self.make().control(self.push())
        self.assertFalse(self.writes())

    def test_committed_manifest_rejects_unknown_roles_fields_and_aliased_identities(self):
        for mutation in ("role", "field", "boolean", "alias"):
            with self.subTest(mutation=mutation):
                config = deepcopy(self.config)
                if mutation == "role": config["extra"] = {}
                if mutation == "field": config["scheduler"]["operator_path"] = "elsewhere"
                if mutation == "boolean": config["scheduler"]["issue_number"] = True
                if mutation == "alias": config["outbox"]["issue_node_id"] = config["scheduler"]["issue_node_id"]
                (self.f.root / entry.STORAGE_PATH).write_text(json.dumps(config))
                self.f.git("add", entry.STORAGE_PATH)
                self.f.git("commit", "-qm", "invalid reviewed storage fixture " + mutation)
                with self.assertRaises(Exception):
                    entry.load_storage(self.f.root, {**self.env, "GITHUB_SHA": self.f.git("rev-parse", "HEAD")})
        self.assertFalse(self.writes())

    def test_uninitialized_outbox_errors_without_modifying_durable_scheduler_claim(self):
        adapter = self.make()
        answer = adapter.control(self.push())
        self.http["outbox"].issue["body"] = batch_runtime.EMPTY_TEMPLATE
        self.calls.clear()
        self.assertEqual(adapter.reports(self.push())["status"], "error")
        self.assertEqual(adapter.state()["active"], answer["state"]["active"])
        self.assertFalse(self.writes())

    def test_wrong_event_main_ref_or_deleted_push_never_writes(self):
        for changed in (dict(self.push(), ref="refs/heads/task"), dict(self.push(), deleted=True), dict(self.push(), after="a" * 40)):
            with self.subTest(changed=changed), self.assertRaises(Exception):
                self.make().control(changed)
        with self.assertRaises(Exception):
            self.make(kind="repository_dispatch").control(self.push())
        self.assertFalse(self.writes())

    def test_current_api_event_must_match_environment_before_admission(self):
        self.scheduler.runs[17]["event"] = "workflow_dispatch"
        with self.assertRaises(Exception):
            self.make().control(self.push())
        self.assertFalse(self.writes())

    def test_schedule_observes_pending_but_never_creates_date_named_request(self):
        self.scheduler.runs[17]["event"] = "schedule"
        answer = self.make(kind="schedule").control({"repository": self.push()["repository"], "schedule": "*/15 * * * *"})
        self.assertEqual(answer["action"], "execute")
        self.assertEqual(answer["request"]["kind"], "bootstrap")
        self.assertNotIn("schedule", answer["request"]["id"])
        before = deepcopy(answer["state"]["active"])
        self.add_run(18, event="schedule")
        next_answer = self.make(18, "schedule").control({"repository": self.push()["repository"]})
        self.assertEqual(next_answer["action"], "waiting")
        self.assertEqual(next_answer["state"]["active"], before)

    def test_exact_active_completion_settles_and_idle_completion_cannot_loop(self):
        original = self.make().control(self.push())
        payload = self.finish(17)
        self.add_run(18)
        result = self.make(18, "workflow_run").control(payload)
        self.assertEqual(result["action"], "idle")
        self.assertIsNone(result["state"]["active"])
        self.assertEqual(result["state"]["processed"], original["request"]["target"])
        self.assertEqual(set(result["state"]["debts"]), set(original["request"]["selection"]["suites"]))
        idle = self.finish(18)
        self.add_run(19)
        self.calls.clear()
        ignored = self.make(19, "workflow_run").control(idle)
        self.assertEqual(ignored["action"], "idle")
        self.assertFalse(self.writes())
        self.assertEqual(self.make(19, "workflow_run").reports(idle)["status"], "ignored")
        self.assertFalse(self.writes())

    def test_none_active_idle_output_still_matches_completion(self):
        original = self.make().control(self.push())
        self.f.api = self.scheduler
        self.f.evidence(original["request"])
        docs = self.f.root / "docs/plans/fixture.md"
        docs.parent.mkdir(parents=True)
        docs.write_text("documentation-only interval\n")
        self.f.git("add", str(docs.relative_to(self.f.root)))
        self.f.git("commit", "-qm", "docs-only main advancement")
        self.sha = self.f.git("rev-parse", "HEAD")
        self.env["GITHUB_SHA"] = self.sha
        for http in self.http.values():
            http.sha = self.sha
        self.add_run(18, event="push")
        none = self.make(18, "push").control(self.push())
        self.assertEqual(none["action"], "idle")
        self.assertEqual(none["request"]["selection"]["kind"], "none")
        self.assertEqual(none["state"]["active"]["claim"], {"run_id": 18, "attempt": 1})
        payload = self.finish(18)
        self.add_run(19)
        result = self.make(19, "workflow_run").control(payload)
        self.assertIsNone(result["state"]["active"])
        request_id = none["request"]["id"]
        self.assertEqual(result["state"]["results"][request_id]["outcomes"], {})
        self.assertEqual(result["state"]["results"][request_id]["reference"], "not-required:" + request_id)

    def test_wrong_callback_identity_attempt_or_source_does_not_reconcile(self):
        self.make().control(self.push())
        payload = self.finish(17)
        self.add_run(18)
        self.calls.clear()
        for key, value in (("head_sha", "f" * 40), ("workflow_id", True), ("path", ".github/workflows/foreign.yml")):
            changed = deepcopy(payload)
            changed["workflow_run"][key] = value
            with self.subTest(key=key), self.assertRaises(Exception):
                self.make(18, "workflow_run").control(changed)
        self.assertFalse(self.writes())

    def test_reporting_failure_never_changes_control_answer_and_still_drains(self):
        controller = self.make()
        answer = controller.control(self.push())
        before = batch_runtime.self_test.canonical_json(answer)
        actual = report_runtime.ReportRuntime.execute
        operations = []
        def run(reporter, operation, **kwargs):
            operations.append(operation)
            self.assertEqual(kwargs.get("limit"), 1,
                "why: an automatic report monopolizes the controller; remedy: bound each attempt while preserving durable backlog")
            if operation == "batches":
                raise OSError("fixture planning failed")
            return actual(reporter, operation, **kwargs)
        with mock.patch.object(report_runtime.ReportRuntime, "execute", run):
            reported = controller.reports(self.push())
        self.assertEqual(reported["status"], "error")
        self.assertEqual(operations, ["batches", "drain"])
        self.assertEqual(batch_runtime.self_test.canonical_json(answer), before)
        self.assertEqual(controller.state()["active"], answer["state"]["active"])

    def test_cli_control_failure_never_writes_an_execute_output(self):
        with tempfile.TemporaryDirectory() as directory:
            event, output = Path(directory) / "event.json", Path(directory) / "result.json"
            event.write_text(json.dumps(dict(self.push(), deleted=True)))
            real_entry = entry.Entry
            def factory(**kwargs):
                return real_entry(**kwargs, environment={**self.env, "GITHUB_EVENT_PATH": str(event)}, api=self.api)
            with mock.patch.object(entry, "Entry", factory):
                self.assertEqual(entry.main(["control", "--root", str(self.f.root), "--output", str(output)]), 1)
            self.assertFalse(output.exists())
            self.assertFalse(self.writes())

    def test_legacy_full_event_only_reports_through_outbox_and_replay_is_idempotent(self):
        self.scheduler.runs[17]["event"] = "workflow_run"
        source = full_legacy_api()
        for name in ("get_run", "get_workflow", "compare", "list_artifacts", "download_artifact", "get_policy"):
            setattr(self.api, name, getattr(source, name))
        observed = source.get_run(100)
        self.workflow_ids[".github/workflows/ci.yml"] = observed["workflow_id"]
        payload = self.callback(self.source(".github/workflows/ci.yml", 100, head=observed["head_sha"]))
        adapter = self.make(kind="workflow_run")
        self.assertEqual(adapter.control(payload)["action"], "idle")
        self.assertFalse(self.writes())
        answer = adapter.reports(payload)
        self.assertEqual(answer["status"], "ready", answer)
        self.assertEqual(answer["outcomes"][0]["result"]["verdict_status"], "failed")
        self.assertEqual(len(self.api.issues), 1)
        box = report_runtime.ReportRuntime(self.config, root=self.f.root, environment=self.env, api=self.api).outbox().load()
        delivered = next(iter(box["deliveries"].values()))
        self.assertEqual(delivered["status"], "delivered")
        self.assertEqual(self.api.issues[0]["body"], delivered["payload"]["issue_body"])
        self.assertEqual(adapter.reports(payload)["status"], "ready")
        self.assertEqual(len(self.api.issues), 1)
        self.assertFalse(self.scheduler.comments)

    def test_pr_branch_review_completion_keeps_exact_receipts_without_main_filter(self):
        self.scheduler.runs[17]["event"] = "workflow_run"
        import ci_review_failure_report_test as review_fixture
        self.review = review_fixture.ConsumerTests()
        self.review.setUp()
        self.workflow_ids[".github/workflows/pr-review.yml"] = 42
        document = self.source(".github/workflows/pr-review.yml", 51, branch="feat/fixture", event="pull_request")
        document["pull_requests"] = []
        self.review.run = document
        for name in ("compare", "list_jobs", "download_artifact"):
            setattr(self.api, name, getattr(self.review.api, name))
        payload = self.callback(document)
        adapter = self.make(kind="workflow_run")
        self.assertEqual(adapter.control(payload)["action"], "idle")
        self.assertFalse(self.writes())
        result = adapter.reports(payload)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(len(self.api.issues), 1)
        self.assertIn("PR Review backends unavailable", self.api.issues[0]["body"])
        self.assertFalse(self.scheduler.comments)

    def test_reports_can_use_settled_source_after_control_cleared_active(self):
        original = self.make().control(self.push())
        self.f.api = self.scheduler
        self.f.evidence(original["request"], failed_job="creator-web")
        payload = self.callback(self.scheduler.runs[17])
        self.add_run(18)
        adapter = self.make(18, "workflow_run")
        result = adapter.control(payload)
        self.assertIsNone(result["state"]["active"])
        self.assertEqual(adapter.reports(payload)["status"], "ready")
        self.assertEqual(len(self.api.issues), 1)
        self.assertIn(original["request"]["id"], self.api.issues[0]["body"])
        self.assertEqual(adapter.reports(payload)["status"], "ready")
        self.assertEqual(len(self.api.issues), 1)

    def test_second_batch_attempt_unknown_workflow_and_foreign_repository_refuse(self):
        self.make().control(self.push())
        self.finish(17)
        self.add_run(18)
        self.calls.clear()
        second = self.source(batch_runtime.WORKFLOW, 17, head=self.sha, attempt=2)
        with self.assertRaises(Exception):
            self.make(18, "workflow_run").control(self.callback(second))
        foreign = self.source(".github/workflows/ci.yml", 100)
        foreign["repository"]["id"] = 7
        with self.assertRaises(Exception):
            self.make(18, "workflow_run").control(self.callback(foreign))
        foreign["path"] = ".github/workflows/unknown.yml"
        self.assertEqual(self.make(18, "workflow_run").reports(self.callback(foreign))["status"], "error")
        self.assertFalse(self.writes())

    def test_source_auth_failure_still_recovers_previously_frozen_outbox_payload(self):
        source = full_legacy_api()
        _, planned = report_runtime.reporting.plan_run(source, 100, attempt=1, repository="endaye/lmdj", sleep=lambda _: None)
        reporter = report_runtime.ReportRuntime(self.config, root=self.f.root, environment=self.env, api=self.api)
        reporter.storage.authenticate_current()
        box = reporter.outbox()
        box.load()
        import report_outbox
        import incremental_batch as batch
        key = batch.digest({"key": planned[0].key, "observation": planned[0].observation})
        box._persist("queue", {"delivery": key, "payload": report_outbox.freeze(planned[0], "endaye")})
        self.scheduler.runs[17]["event"] = "workflow_run"
        payload = self.callback(self.source(".github/workflows/ci.yml", 100))
        payload["workflow_run"]["head_sha"] = "f" * 40
        before = deepcopy(self.scheduler.comments)
        result = self.make(kind="workflow_run").reports(payload)
        self.assertEqual(result["status"], "error")
        self.assertEqual([row["operation"] for row in result["outcomes"]], ["source", "drain"])
        self.assertEqual(result["outcomes"][1]["result"]["status"], "delivered")
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual(reporter.outbox().load()["deliveries"][key]["status"], "delivered")
        self.assertEqual(self.scheduler.comments, before)

    def test_cli_report_cannot_overwrite_preexisting_control_result(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            raw = batch_runtime.self_test.canonical_json(self.make().control(self.push()))
            output.write_text(raw)
            with mock.patch.object(entry, "Entry", side_effect=AssertionError("must refuse before any runtime")):
                self.assertEqual(entry.main(["reports", "--root", str(self.f.root), "--output", str(output)]), 1)
            self.assertEqual(output.read_text(), raw)

    def test_cli_unverified_report_writes_only_separate_error_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            with mock.patch.object(entry, "Entry", side_effect=OSError("fixture-secret-must-not-escape")):
                self.assertEqual(entry.main(["reports", "--root", str(self.f.root), "--output", str(output)]), 1)
            result = json.loads(output.read_text())
            self.assertEqual((result["schema"], result["status"], result["source"]), (entry.REPORT_SCHEMA, "error", "unverified"))
            self.assertNotIn("action", result)
            self.assertNotIn("fixture-secret", output.read_text())
            self.assertFalse(self.writes())


if __name__ == "__main__":
    unittest.main()
