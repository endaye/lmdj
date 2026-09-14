#!/usr/bin/env python3
"""Real Git + real runtime/journal composition through strict HTTP fixtures.

No GitHub writes occur. Fixtures reproduce protocol payloads and write-loss,
not actual token permissions, hosted locking, nested job names or event wakeups;
those remain explicit O1 platform acceptance gaps.
"""
import base64
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import batch_runtime as runtime
import batch_execution
import batch_verdict
import incremental_batch as batch
import test_scope
GitHubApiError = runtime.with_retry.__globals__["GitHubApiError"]

BOT = {"__typename": "Bot", "id": "MDM6Qm90NDE4OTgyODI="}


def zipped(documents):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in documents.items():
            archive.writestr(name, json.dumps(value))
    return result.getvalue()


class Http:
    def __init__(self, sha):
        self.sha, self.calls = sha, []
        self.issue = {"id": "fixed-node", "number": 782, "body": runtime.EMPTY_TEMPLATE,
                      "state": "OPEN", "author": {"__typename": "User", "id": "owner"},
                      "editor": None, "lastEditedAt": None}
        self.comments, self.runs, self.jobs, self.artifacts, self.downloads = [], {}, {}, {}, {}
        self.fail, self.lose, self.pages_override = None, None, {}
        self.old_runs, self.old_report_runs = [], []
        self.add_run(17)

    def add_run(self, number):
        self.runs[number] = {"id": number, "run_attempt": 1, "workflow_id": 7,
            "head_sha": self.sha, "head_branch": "main", "path": runtime.WORKFLOW,
            "status": "in_progress", "conclusion": None, "event": "workflow_dispatch",
            "repository": {"full_name": "endaye/lmdj"}, "head_repository": {"full_name": "endaye/lmdj"}}
        self.jobs[number] = [{"id": number * 100, "run_id": number, "run_attempt": 1,
                             "name": runtime.CONTROLLER_JOB, "status": "in_progress", "conclusion": None}]
        self.artifacts[number] = []

    def _request(self, method, path, *, body=None, raw=False):
        self.calls.append((method, path, deepcopy(body)))
        if self.fail == (method, path):
            raise OSError("SECRET-CREDENTIAL-IN-HTTP-EXCEPTION")
        if (method, path) in self.pages_override:
            return deepcopy(self.pages_override[method, path])
        if method == "POST" and path == "/graphql":
            issue = deepcopy(self.issue)
            if body["query"] == runtime.storage.COMMENTS_QUERY:
                issue["comments"] = {"nodes": deepcopy(self.comments), "totalCount": len(self.comments),
                                     "pageInfo": {"hasNextPage": False, "endCursor": None}}
            elif "comments{totalCount}" in body["query"]:
                issue["comments"] = {"totalCount": len(self.comments)}
            return {"data": {"repository": {"nameWithOwner": "endaye/lmdj", "issue": issue}}}
        prefix = "/repos/endaye/lmdj"
        if method == "GET" and path == prefix:
            return {"id": 1286600062, "full_name": "endaye/lmdj"}
        if method == "GET" and path == prefix + "/actions/workflows/pr-review.yml":
            return {"id": 8, "path": ".github/workflows/pr-review.yml"}
        if method == "GET" and path.startswith(prefix + "/actions/artifacts?"):
            return {"total_count": 0, "artifacts": []}
        if method == "GET" and path == prefix + "/git/ref/heads/main":
            return {"object": {"sha": self.sha, "type": "commit"}}
        if method == "GET" and path == prefix + "/actions/workflows/7":
            return {"id": 7, "path": runtime.WORKFLOW}
        if method == "GET" and path.startswith(prefix + "/compare/"):
            base = path.split("/compare/", 1)[1].split("...")[0]
            return {"status": "identical", "base_commit": {"sha": base}, "merge_base_commit": {"sha": base}}
        if method == "GET" and path.startswith(prefix + f"/contents/{runtime.WORKFLOW}?ref=") and path.split("?ref=")[1] in {r["head_sha"] for r in self.runs.values()}:
            return {"type": "file", "path": runtime.WORKFLOW, "encoding": "base64", "content": base64.b64encode(b"trusted workflow").decode()}
        if method == "GET" and "/actions/workflows/" in path and "/runs?" in path:
            runs = self.old_report_runs if "/self-test-report.yml/" in path else self.old_runs
            return {"total_count": len(runs), "workflow_runs": deepcopy(runs)}
        if method == "GET" and path.startswith(prefix + "/actions/runs/"):
            suffix = path.split("/actions/runs/", 1)[1]
            number = int(suffix.split("/")[0])
            if suffix.endswith("/attempts/1"):
                return deepcopy(self.runs[number])
            if "/jobs?" in suffix:
                return {"total_count": len(self.jobs[number]), "jobs": deepcopy(self.jobs[number])}
            if "/artifacts?" in suffix:
                return {"total_count": len(self.artifacts[number]), "artifacts": deepcopy(self.artifacts[number])}
        if method == "GET" and path.startswith(prefix + "/actions/artifacts/") and path.endswith("/zip"):
            assert raw
            return self.downloads[int(path.split("/artifacts/")[1].split("/")[0])]
        if method == "PATCH" and path == prefix + "/issues/782":
            self.issue.update(body=body["body"], editor=deepcopy(BOT), lastEditedAt="2026-09-08T00:00:00Z")
            if self.lose == "PATCH":
                self.lose = None
                raise OSError("LOST-WRITE-SECRET")
            return {"number": 782}
        if method == "POST" and path == prefix + "/issues/782/comments":
            self.comments.append({"id": "comment-" + str(len(self.comments)), "fullDatabaseId": str(10001 + len(self.comments)),
                                  "body": body["body"], "author": deepcopy(BOT), "editor": None, "lastEditedAt": None})
            kind = json.loads(body["body"])["payload"]["event"]["type"]
            if self.lose in ("POST", kind):
                self.lose = None
                raise OSError("LOST-WRITE-SECRET")
            return {"id": int(self.comments[-1]["fullDatabaseId"])}
        raise AssertionError(f"undeclared HTTP fixture endpoint: {method} {path}")


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        def git(*args):
            return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout.strip()
        self.git = git
        git("init", "-q", "-b", "main")
        git("config", "user.name", "Runtime fixture")
        git("config", "user.email", "ci@example.invalid")
        (self.root / "scripts/ci").mkdir(parents=True)
        for filename in ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json"):
            (self.root / "scripts/ci" / filename).write_bytes((ROOT / "scripts/ci" / filename).read_bytes())
        (self.root / ".github/workflows").mkdir(parents=True)
        for path in runtime.EXECUTION_SOURCES:
            (self.root / path).write_text("name: Frozen trusted workflow\n")
        git("add", "scripts/ci", ".github/workflows")
        git("commit", "-qm", "fixture policy")
        self.sha = git("rev-parse", "HEAD")
        git("remote", "add", "origin", str(self.root))
        self.api = Http(self.sha)
        self.config = {"repository": "endaye/lmdj", "issue_number": 782, "issue_node_id": "fixed-node",
                       "bot_node_id": BOT["id"], "workflow_id": 7, "epoch": "isolated-fixture"}
        self.env = {"GITHUB_REPOSITORY": "endaye/lmdj", "GITHUB_RUN_ID": "17", "GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_SHA": self.sha, "GITHUB_REF": "refs/heads/main", "GITHUB_TOKEN": "fixture-token",
                    "BATCH_WRITER_LOCK": "self-test-report"}
        self.policy = test_scope.load_policy(self.root)

    def make(self, run=17):
        return runtime.Runtime(self.config, root=self.root, api=self.api, environment={**self.env, "GITHUB_RUN_ID": str(run)})

    def test_runtime_gets_share_one_primary_reset_wait_budget_across_calls(self):
        instance = runtime.Runtime(self.config, root=self.root, api=self.api,
                                   environment={**self.env, "GITHUB_RUN_ID": "17", "BATCH_WRITER_LOCK": ""})
        clock = [100.0]
        self.api._request = mock.Mock(side_effect=[
            GitHubApiError(403, "quota", remaining=0, reset=120),
            {"ok": True},
            GitHubApiError(403, "quota", remaining=0, reset=140),
            {"ok": True},
        ])
        sleeps = []
        instance.clock = lambda: clock[0]
        instance.transport.clock = instance.clock
        with mock.patch.object(runtime.time, "sleep", side_effect=lambda delay: (sleeps.append(delay), clock.__setitem__(0, clock[0] + delay))):
            self.assertEqual(instance.call("GET", "/first"), {"ok": True})
            self.assertEqual(instance.transport._call("GET", "/second"), {"ok": True})
        self.assertEqual(sleeps, [20.0, 20.0])
        self.assertEqual(instance.retry_budget.remaining, 25.0)
        self.assertEqual(self.api._request.call_count, 4)

    def test_runtime_forbidden_and_malformed_reset_are_not_retried(self):
        instance = runtime.Runtime(self.config, root=self.root, api=self.api,
                                   environment={**self.env, "GITHUB_RUN_ID": "17", "BATCH_WRITER_LOCK": ""})
        self.api._request = mock.Mock(side_effect=[
            GitHubApiError(403, "auth", remaining=10, reset=110),
            GitHubApiError(403, "malformed", remaining=0),
        ])
        with self.assertRaises(batch.BatchError):
            instance.call("GET", "/auth")
        with self.assertRaises(batch.BatchError):
            instance.call("GET", "/malformed")
        self.assertEqual(self.api._request.call_count, 2)
        self.assertEqual(instance.retry_budget.remaining, 25.0)

    def test_unlocked_transport_get_recovers_after_primary_reset(self):
        instance = runtime.Runtime(self.config, root=self.root, api=self.api,
                                   environment={**self.env, "BATCH_WRITER_LOCK": ""})
        clock = [100.0]
        instance.clock = lambda: clock[0]
        instance.transport.clock = instance.clock
        self.api._request = mock.Mock(side_effect=[
            GitHubApiError(403, "quota", remaining=0, reset=120), {"healthy": True}])
        sleeps = []
        with mock.patch.object(runtime.time, "sleep", side_effect=lambda delay: (sleeps.append(delay), clock.__setitem__(0, clock[0] + delay))):
            self.assertEqual(instance.transport._call("GET", "/recovery"), {"healthy": True})
        self.assertEqual(sleeps, [20.0])
        self.assertEqual(self.api._request.call_count, 2)

    def test_lock_held_quota_does_not_sleep_or_mutate_and_later_context_recovers(self):
        instance = self.make()
        self.api._request = mock.Mock(side_effect=[
            GitHubApiError(403, "forbidden", remaining=10, reset=120),
            GitHubApiError(429, "secondary")])
        sleeps = []
        with mock.patch.object(runtime.time, "sleep", side_effect=sleeps.append):
            with self.assertRaises(batch.BatchError):
                instance.call("GET", "/locked")
            with self.assertRaises(runtime.storage.JournalBlocked):
                instance.transport._call("GET", "/locked-journal")
        self.assertEqual(sleeps, [])
        self.assertEqual(self.api._request.call_count, 2)
        later = self.make()
        self.api._request = mock.Mock(return_value={"healthy": True})
        self.assertEqual(later.call("GET", "/later-health"), {"healthy": True})

    def test_lock_held_primary_quota_waits_until_reset_and_is_not_not_live(self):
        instance = self.make()
        clock = [100.0]
        instance.clock = lambda: clock[0]
        instance.transport.clock = instance.clock
        self.api._request = mock.Mock(side_effect=[
            GitHubApiError(403, "quota", remaining=0, reset=120), {"healthy": True}])
        sleeps = []
        with mock.patch.object(runtime.time, "sleep", side_effect=lambda delay: (sleeps.append(delay), clock.__setitem__(0, clock[0] + delay))):
            self.assertEqual(instance.call("GET", "/locked-primary"), {"healthy": True})
        self.assertEqual(sleeps, [20.0])
        self.assertEqual(self.api._request.call_count, 2)

    def test_unlocked_transport_unknown_post_is_attempted_once_without_retry(self):
        instance = runtime.Runtime(self.config, root=self.root, api=self.api,
                                   environment={**self.env, "BATCH_WRITER_LOCK": ""})
        self.api._request = mock.Mock(side_effect=GitHubApiError(503, "unknown write"))
        sleeps = []
        with mock.patch.object(runtime.time, "sleep", side_effect=sleeps.append):
            with self.assertRaises(runtime.storage.JournalBlocked):
                instance.transport._call("POST", "/unknown-write", {"body": "payload"})
        self.assertEqual(self.api._request.call_count, 1)
        self.assertEqual(sleeps, [])

    def test_authentication_failure_retains_only_current_phase(self):
        for stage, owner, method in (
            ("auth-lock", "runtime", "lock_held"),
            ("auth-checkout", "runtime", "git"),
            ("auth-main-refresh", "inputs", "refresh"),
            ("auth-current-run", "runtime", "run_state"),
            ("auth-journal-writer", "transport", "_writer"),
            ("auth-current-job", "runtime", "pages"),
        ):
            with self.subTest(stage=stage):
                instance = self.make()
                target = instance if owner == "runtime" else getattr(instance, owner)
                with mock.patch.object(target, method, side_effect=OSError("SECRET")):
                    with self.assertRaises(OSError):
                        instance.authenticate_current()
                self.assertEqual(instance.diagnostic_stage, stage,
                    "why: authentication location lost; remedy: retain the failing closed phase")

    def test_successful_authentication_clears_previous_failure_phase(self):
        instance = self.make()
        instance.diagnostic_stage = "auth-main-refresh"
        instance.authenticate_current()
        self.assertIsNone(instance.diagnostic_stage,
            "why: successful auth must not blame later journal failures; remedy: clear phase on success")

    def start(self):
        instance = self.make()
        instance.initialize()
        return instance.reconcile(execute=True)

    def evidence(self, request, *, missing_job=None, failed_job=None, run=17,
                 shared_dependency_failure=False, emit_common_events=True):
        executor = {"run_id": run, "attempt": 1}
        self.git("checkout", "-q", "--detach", request["control"])
        prepared = batch_execution.prepare(self.policy, request, executor, repo=self.root,
            run_id=run, run_attempt=1, control_sha=request["control"], main_sha=self.api.sha)
        self.git("checkout", "-q", "main")
        if shared_dependency_failure:
            needs = {"change-scope": {"result": "failure", "outputs": {"reason": "shared control failure"}}}
            needs.update({runtime.ALIASES.get(job, job): {"result": "skipped", "outputs": {}}
                          for job in runtime.JOB_NAMES})
            needs["macos-fallback"] = {"result": "skipped", "outputs": {}}
        else:
            needs = {runtime.ALIASES.get(job, job): {"result": "success"} for job in runtime.JOB_NAMES}
            if missing_job:
                del needs[runtime.ALIASES.get(missing_job, missing_job)]
            if failed_job:
                needs[runtime.ALIASES.get(failed_job, failed_job)] = {"result": "failure"}
        verdict = batch_execution.from_needs(self.policy, prepared["identity"], request["selection"], needs,
                                            aliases=runtime.ALIASES, dependencies=runtime.dependencies(self.policy),
                                            emit_common_events=emit_common_events)
        self.api.runs[run].update(status="completed", conclusion="success" if verdict["status"] == "passed" else "failure")
        self.api.jobs[run][0].update(status="completed", conclusion="success")
        for index, (job, name) in enumerate(runtime.JOB_NAMES.items()):
            entry = needs.get(runtime.ALIASES.get(job, job))
            if entry:
                self.api.jobs[run].append({"id": 2000 + index, "run_id": run, "run_attempt": 1,
                    "name": runtime.PREFIX + name, "status": "completed", "conclusion": entry["result"]})
        failed = verdict["status"] == "failed"
        self.api.jobs[run].append({"id": 3000, "run_id": run, "run_attempt": 1, "name": runtime.PRODUCER_JOB,
            "status": "completed", "conclusion": "failure" if failed else "success", "steps": [
                {"name": "Judge selected suites from actual needs", "status": "completed", "conclusion": "success"},
                {"name": "Retain scoped verdict and raw needs", "status": "completed", "conclusion": "success"},
                {"name": "Keep failed selected work visible", "status": "completed", "conclusion": "failure" if failed else "skipped"}]})
        self.api.artifacts[run] = [{"id": 40, "name": f"batch-verdict-{request['target']}-{run}-1", "expired": False}]
        self.api.downloads[40] = zipped({"verdict.json": verdict, "execution.json": prepared, "needs.json": needs})
        return verdict

    def test_explicit_init_is_empty_not_a_tested_baseline(self):
        answer = self.make().initialize()
        self.assertEqual(answer["action"], "initialized")
        self.assertIsNone(answer["state"])
        self.assertEqual(self.make().journal().load(), [])
        writes = [(method, path) for method, path, _ in self.api.calls if method == "PATCH"]
        self.assertEqual(writes, [("PATCH", "/repos/endaye/lmdj/issues/782")])

    def test_init_cannot_reset_initialized_journal(self):
        self.start()
        before = deepcopy(self.api.issue)
        with self.assertRaisesRegex(batch.BatchError, "empty reserved"):
            self.make().initialize()
        self.assertEqual(self.api.issue, before)

    def test_init_rejects_existing_comment(self):
        self.api.comments.append({"human": "comment"})
        with self.assertRaisesRegex(batch.BatchError, "empty reserved"):
            self.make().initialize()
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.api.calls))

    def test_init_rejects_wrong_node_before_write(self):
        self.api.issue["id"] = "another-node"
        with self.assertRaisesRegex(batch.BatchError, "empty reserved"):
            self.make().initialize()
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.api.calls))

    def test_init_unknown_patch_response_is_not_retried(self):
        self.api.lose = "PATCH"
        with self.assertRaisesRegex(batch.BatchError, "outcome unknown"):
            self.make().initialize()
        self.assertEqual(sum(m == "PATCH" for m, _, _ in self.api.calls), 1)
        self.assertEqual(self.make().journal().load(), [])

    def test_normal_reconcile_never_auto_initializes(self):
        with self.assertRaises(batch.BatchError):
            self.make().reconcile(execute=True)
        self.assertFalse(any(m == "PATCH" for m, _, _ in self.api.calls))

    def test_live_controller_job_is_not_executor_terminal(self):
        self.make().initialize()
        answer = self.make().reconcile(execute=True)
        self.assertEqual(answer["action"], "execute")
        self.api.jobs[17][0].update(status="completed", conclusion="success")
        self.assertEqual(self.make().run_state({"run_id": 17, "attempt": 1}), "running")

    def test_init_claim_terminal_result_restart_and_settle(self):
        start = self.start()
        verdict = self.evidence(start["request"])
        self.api.add_run(18)
        result = self.make(18).reconcile(execute=False)
        self.assertEqual(result["action"], "idle")
        self.assertEqual(result["state"]["processed"], self.sha)
        self.assertIsNone(result["state"]["active"])
        reference = result["state"]["results"][start["request"]["id"]]["reference"]
        self.assertEqual(runtime.decode_reference(reference), verdict)
        self.api.downloads.clear()
        recovered = self.make(18).reconcile(execute=False)
        self.assertEqual(recovered["state"]["results"], result["state"]["results"])

    def test_product_failure_and_missing_coverage_both_survive_reference(self):
        start = self.start()
        verdict = self.evidence(start["request"], missing_job="core-asan-macos", failed_job="core-macos")
        self.api.add_run(18)
        result = self.make(18).reconcile(execute=False)
        row = next(s for s in verdict["suites"] if s["id"] == "core_macos")
        self.assertEqual(row["failures"], ["core-macos"])
        self.assertTrue(row["verification_debt"])
        stored = result["state"]["results"][start["request"]["id"]]
        self.assertEqual(runtime.decode_reference(stored["reference"]), verdict)
        self.assertIn("core_macos", result["state"]["debts"])

    def test_historical_v1_shared_dependency_bundle_replays_from_raw_needs(self):
        start = self.start()
        verdict = self.evidence(start["request"], shared_dependency_failure=True,
                                emit_common_events=False)
        self.assertEqual(verdict["evidence_schema"], batch_verdict.SCHEMA)
        self.assertNotIn("common_events", verdict)
        instance = self.make()
        instance.inputs.refresh()
        self.assertEqual(instance.result_for(start["request"], start["executor"])["status"], "ready")

    def test_forged_v2_common_event_is_rejected_after_authenticated_bundle(self):
        start = self.start()
        verdict = self.evidence(start["request"], shared_dependency_failure=True)
        with zipfile.ZipFile(io.BytesIO(self.api.downloads[40])) as archive:
            documents = {name: json.loads(archive.read(name)) for name in archive.namelist()}
        source = documents["verdict.json"]["common_events"][0]["source"]
        source["outputs"]["reason"] = "forged"
        source["digest"] = batch.digest({"result": source["result"], "outputs": source["outputs"]})
        verdict_document = documents["verdict.json"]
        verdict_document["evidence_digest"] = batch.digest({
            key: value for key, value in verdict_document.items() if key != "evidence_digest"})
        self.api.downloads[40] = zipped(documents)
        instance = self.make()
        instance.inputs.refresh()
        self.assertEqual(instance.result_for(start["request"], start["executor"]), {"status": "missing"})
        self.assertEqual(verdict["evidence_schema"], batch_verdict.COMMON_EVENT_SCHEMA)

    def test_artifact_visibility_lag_is_pending_not_missing(self):
        start = self.start()
        self.evidence(start["request"])
        self.api.artifacts[17] = []
        instance = self.make()
        instance.inputs.refresh()
        self.assertEqual(instance.result_for(start["request"], start["executor"]), {"status": "pending"})

    def test_expired_artifact_is_missing_not_wait_forever(self):
        start = self.start()
        self.evidence(start["request"])
        self.api.artifacts[17][0]["expired"] = True
        instance = self.make()
        instance.inputs.refresh()
        self.assertEqual(instance.result_for(start["request"], start["executor"]), {"status": "missing"})

    def test_job_api_failure_cannot_be_invented_success(self):
        start = self.start()
        self.evidence(start["request"])
        next(j for j in self.api.jobs[17] if j["name"] == runtime.PREFIX + "Docs / static")["conclusion"] = "failure"
        instance = self.make()
        instance.inputs.refresh()
        with self.assertRaisesRegex(batch.BatchError, "API conclusion"):
            instance.result_for(start["request"], start["executor"])

    def test_reviewed_macos_continue_on_error_difference_is_allowed(self):
        start = self.start()
        self.evidence(start["request"])
        next(j for j in self.api.jobs[17] if j["name"] == runtime.PREFIX + "macOS gates (primary)")["conclusion"] = "failure"
        instance = self.make()
        instance.inputs.refresh()
        self.assertEqual(instance.result_for(start["request"], start["executor"])["status"], "ready")

    def test_upload_failure_does_not_authenticate_a_present_artifact(self):
        start = self.start()
        self.evidence(start["request"])
        self.api.jobs[17][-1]["steps"][1]["conclusion"] = "failure"
        instance = self.make()
        instance.inputs.refresh()
        with self.assertRaisesRegex(batch.BatchError, "judge and upload"):
            instance.result_for(start["request"], start["executor"])

    def test_terminal_failed_upload_without_artifact_settles_with_debt(self):
        start = self.start()
        self.evidence(start["request"])
        self.api.jobs[17][-1]["conclusion"] = "failure"
        self.api.jobs[17][-1]["steps"][1]["conclusion"] = "failure"
        self.api.artifacts[17] = []
        self.api.add_run(18)
        answer = self.make(18).reconcile(execute=False)
        self.assertIsNone(answer["state"]["active"])
        self.assertTrue(answer["state"]["debts"])

    def test_api_failure_does_not_release_active_or_advance(self):
        start = self.start()
        self.api.add_run(18)
        self.api.fail = ("GET", "/repos/endaye/lmdj/actions/runs/17/attempts/1")
        with self.assertRaises(batch.BatchError):
            self.make(18).reconcile(execute=False)
        self.api.fail = None
        events = self.make(18).journal().load()
        self.assertFalse(any(e["type"] == "advance" for e in events))

    def test_old_active_core_run_blocks_bootstrap(self):
        self.make().initialize()
        self.api.old_runs = [{"id": 99, "status": "in_progress"}]
        answer = self.make().reconcile(execute=True)
        self.assertEqual(answer["action"], "waiting")
        self.assertIsNone(answer["state"]["active"])

    def test_queued_light_wakeups_do_not_starve_bootstrap(self):
        self.make().initialize()
        for run in (18, 19):
            self.api.add_run(run)
            self.api.runs[run]["status"] = "queued"
            self.api.jobs[run][0].update(status="queued", started_at=None, completed_at=None)
        self.api.old_report_runs = [self.api.runs[18], self.api.runs[19]]
        answer = self.make().reconcile(execute=True)
        self.assertEqual(answer["action"], "execute",
                         "why: lightweight lock waiters starve bootstrap; remedy: distinguish never-admitted controller wakes")

    def test_report_run_with_previous_execution_still_blocks_bootstrap(self):
        self.make().initialize()
        self.api.add_run(18)
        self.api.jobs[18][0].update(status="completed", conclusion="success")
        self.api.old_report_runs = [self.api.runs[18]]
        answer = self.make().reconcile(execute=True)
        self.assertEqual(answer["action"], "waiting")

    def test_active_workflow_with_only_queued_controller_is_still_light(self):
        self.make().initialize()
        self.api.add_run(18)
        self.api.jobs[18][0].update(status="queued", started_at=None, completed_at=None)
        self.api.old_report_runs = [self.api.runs[18]]
        self.assertEqual(self.make().reconcile(execute=True)["action"], "execute")

    def test_active_workflow_without_visible_jobs_is_ambiguous(self):
        self.make().initialize()
        self.api.add_run(18)
        self.api.jobs[18] = []
        self.api.old_report_runs = [self.api.runs[18]]
        self.assertEqual(self.make().reconcile(execute=True)["action"], "waiting")

    def test_skipped_legacy_report_beside_queued_controller_is_light(self):
        self.make().initialize()
        self.api.add_run(18)
        self.api.jobs[18][0].update(status="queued", started_at=None, completed_at=None)
        self.api.jobs[18].append({"id": 1801, "run_id": 18, "run_attempt": 1,
            "name": "Self-test report", "status": "completed", "conclusion": "skipped"})
        self.api.old_report_runs = [self.api.runs[18]]
        self.assertEqual(self.make().reconcile(execute=True)["action"], "execute")

    def test_bad_zip_is_missing_after_successful_producer_not_infinite_wait(self):
        start = self.start()
        self.evidence(start["request"])
        self.api.downloads[40] = b"not a zip"
        self.api.add_run(18)
        answer = self.make(18).reconcile(execute=False)
        self.assertIsNone(answer["state"]["active"])
        self.assertTrue(answer["state"]["debts"])

    def invalid_verdict(self, field):
        start = self.start()
        self.evidence(start["request"])
        with zipfile.ZipFile(io.BytesIO(self.api.downloads[40])) as archive:
            docs = {name: json.loads(archive.read(name)) for name in archive.namelist()}
        if field == "target":
            docs["verdict.json"]["identity"]["target_sha"] = "f" * 40
        else:
            docs["verdict.json"]["evidence_digest"] = "0" * 64
        self.api.downloads[40] = zipped(docs)
        instance = self.make()
        instance.inputs.refresh()
        return instance.result_for(start["request"], start["executor"])

    def test_wrong_artifact_target_is_missing_not_passing(self):
        self.assertEqual(self.invalid_verdict("target"), {"status": "missing"})

    def test_corrupt_artifact_digest_is_missing_not_passing(self):
        self.assertEqual(self.invalid_verdict("digest"), {"status": "missing"})

    def test_failed_download_is_unknown_not_missing(self):
        start = self.start()
        self.evidence(start["request"])
        self.api.fail = ("GET", "/repos/endaye/lmdj/actions/artifacts/40/zip")
        instance = self.make()
        instance.inputs.refresh()
        with self.assertRaisesRegex(batch.BatchError, "API unavailable"):
            instance.result_for(start["request"], start["executor"])

    def test_old_complete_upload_without_artifact_preserves_missing_debt(self):
        start = self.start()
        self.evidence(start["request"])
        self.api.artifacts[17] = []
        self.api.jobs[17][-1]["steps"][1]["completed_at"] = "2020-01-01T00:00:00Z"
        instance = self.make()
        instance.inputs.refresh()
        self.assertEqual(instance.result_for(start["request"], start["executor"]), {"status": "missing"})

    def test_incomplete_artifact_pagination_is_error(self):
        self.api.pages_override["GET", "/repos/endaye/lmdj/actions/runs/17/artifacts?per_page=100&page=1"] = {"total_count": 1, "artifacts": []}
        with self.assertRaisesRegex(batch.BatchError, "pagination"):
            self.make().pages("/actions/runs/17/artifacts", "artifacts")

    def test_duplicate_artifacts_are_not_first_match_wins(self):
        self.api.artifacts[17] = [{"id": i, "name": "same", "expired": False} for i in (1, 2)]
        with self.assertRaisesRegex(batch.BatchError, "ambiguous"):
            self.make().artifact_bundle(self.api.runs[17], "same", ("verdict.json",))

    def test_bundle_rejects_unexpected_zip_entry(self):
        self.api.artifacts[17] = [{"id": 1, "name": "same", "expired": False}]
        self.api.downloads[1] = zipped({"../verdict.json": {}})
        with self.assertRaisesRegex(runtime.InvalidEvidence, "not acceptable evidence"):
            self.make().artifact_bundle(self.api.runs[17], "same", ("verdict.json",))

    def test_reconcile_defaults_to_no_execution(self):
        self.make().initialize()
        answer = self.make().reconcile()
        self.assertEqual(answer["action"], "idle")
        self.assertIsNone(answer["state"]["active"])

    def test_lost_claim_response_cannot_start_duplicate_execution(self):
        self.make().initialize()
        self.api.lose = "claim"
        with self.assertRaises(batch.BatchError):
            self.make().reconcile(execute=True)
        answer = self.make().reconcile(execute=True)
        self.assertEqual(answer["action"], "waiting")
        events = self.make().journal().load()
        self.assertEqual(sum(e["type"] == "claim" for e in events), 1)

    def test_lost_admit_settlement_only_cannot_claim_live_executor(self):
        self.make().initialize()
        self.api.lose = "admit"
        with self.assertRaises(batch.BatchError):
            self.make().reconcile(execute=True)
        answer = self.make().reconcile(execute=False)
        self.assertEqual(answer["action"], "waiting")
        self.assertIsNone(answer["state"]["active"]["claim"])

    def test_explicit_command_redelivery_keeps_queued_original_identity(self):
        self.start()
        self.api.add_run(18)
        explicit = {"id": "candidate-one", "kind": "candidate", "target": self.sha}
        first = self.make(18).reconcile(execute=True, explicit=explicit)
        self.api.add_run(19)
        second = self.make(19).reconcile(execute=True, explicit=explicit)
        self.assertEqual(second["state"]["requests"][explicit["id"]], first["state"]["requests"][explicit["id"]])
        self.assertEqual(second["state"]["queue"], [explicit["id"]])

    def advance_main(self, *, workflow_change=False, content="changed main content\n"):
        path = runtime.EXECUTION_SOURCES[1] if workflow_change else "note.md"
        (self.root / path).write_text(content)
        self.git("add", path)
        self.git("commit", "-qm", "advance main fixture")
        self.api.sha = self.git("rev-parse", "HEAD")
        self.env["GITHUB_SHA"] = self.api.sha

    def test_queued_old_control_executes_and_settles_on_compatible_new_main(self):
        start = self.start()
        self.api.add_run(18)
        explicit = {"id": "queued-old-control", "kind": "candidate", "target": self.sha}
        self.make(18).reconcile(execute=True, explicit=explicit)
        self.evidence(start["request"])
        self.advance_main()
        self.api.add_run(19)
        claimed = self.make(19).reconcile(execute=True)
        self.assertEqual(claimed["action"], "execute")
        self.assertEqual(claimed["request"]["control"], self.sha)
        self.assertNotEqual(self.api.runs[19]["head_sha"], self.sha)
        self.evidence(claimed["request"], run=19)
        self.api.add_run(20)
        done = self.make(20).reconcile(execute=False)
        self.assertEqual(done["state"]["processed"], self.sha)
        self.assertIsNone(done["state"]["active"])
        self.assertEqual(set(done["state"]["results"][explicit["id"]]["outcomes"].values()), {"passed"})

    def test_changed_workflow_is_incompatible_and_terminal_request_releases_slot(self):
        start = self.start()
        self.api.add_run(18)
        explicit = {"id": "incompatible-candidate", "kind": "candidate", "target": self.sha}
        self.make(18).reconcile(execute=True, explicit=explicit)
        self.evidence(start["request"])
        self.advance_main(workflow_change=True)
        self.assertFalse(runtime.compatible_sources(self.make().git, self.sha, self.api.sha))
        self.api.add_run(19)
        claimed = self.make(19).reconcile(execute=True)
        self.assertEqual(claimed["request"]["id"], explicit["id"])
        # Models the T4f failed early preflight, not a fake terminal while its
        # caller is still running. Actual no-heavy gating is T4f/O1 evidence.
        self.api.runs[19].update(status="completed", conclusion="failure")
        self.api.jobs[19][0].update(status="completed", conclusion="success")
        self.api.add_run(20)
        done = self.make(20).reconcile(execute=False)
        stored = done["state"]["results"][explicit["id"]]
        self.assertEqual(set(stored["outcomes"].values()), {"missing"})
        self.assertIsNone(done["state"]["active"])
        self.assertIsNone(done["state"]["blocked"])

    def test_policy_only_candidate_drift_settles_missing_and_replays_without_clearing_auto_debt(self):
        self.check_candidate_policy_settlement(old_evidence=True)

    def test_policy_preflight_terminal_without_artifact_settles_and_replays(self):
        self.check_candidate_policy_settlement(old_evidence=False)

    def check_candidate_policy_settlement(self, *, old_evidence):
        start = self.start()
        self.api.add_run(18)
        explicit = {"id": "obsolete-policy-candidate", "kind": "candidate", "target": self.sha}
        queued = self.make(18).reconcile(execute=True, explicit=explicit)
        self.assertEqual(queued["state"]["queue"], [explicit["id"]])
        self.evidence(start["request"], missing_job="core-asan-macos", failed_job="docs-static")
        path = self.root / "scripts/ci/scope_policy.json"
        policy = json.loads(path.read_text())
        policy["rules"].append({"match": {"kind": "exact", "value": "docs/policy-fixture.md"}, "lanes": ["portal"]})
        path.write_text(json.dumps(policy))
        self.git("add", str(path))
        self.git("commit", "-qm", "policy only executor drift")
        self.api.sha = self.git("rev-parse", "HEAD")
        self.env["GITHUB_SHA"] = self.api.sha
        self.assertTrue(runtime.compatible_sources(self.make().git, self.sha, self.api.sha))
        self.api.add_run(19)
        admitted = self.make(19).reconcile(execute=True)
        self.assertEqual(admitted["request"], queued["state"]["requests"][explicit["id"]])
        self.assertEqual(admitted["state"]["active"]["executor_run"], {"run_id": 19, "attempt": 1})
        instance = self.make(19)
        instance.inputs.main = self.api.sha
        self.assertEqual(instance.result_for(admitted["request"], {"run_id": 19, "attempt": 1}),
                         {"status": "pending"}, "why: live executor cannot be settled; remedy: wait for actual terminal identity")
        if old_evidence:
            # Even a complete old-policy artifact is not acceptable evidence.
            self.evidence(admitted["request"], run=19)
        else:
            # Actual inline no-heavy preflight is exercised by WorkflowScripts;
            # this HTTP fixture supplies its terminal executor boundary.
            self.api.runs[19].update(status="completed", conclusion="failure")
            self.api.jobs[19][0].update(status="completed", conclusion="success")
        original = instance.inputs.policy_at
        def unavailable(revision):
            if revision == self.api.sha:
                raise OSError("policy read unavailable")
            return original(revision)
        with mock.patch.object(instance.inputs, "policy_at", side_effect=unavailable):
            with self.assertRaises(OSError):
                instance.result_for(admitted["request"], {"run_id": 19, "attempt": 1})
        self.api.add_run(20)
        settled = self.make(20).reconcile(execute=False)
        state = settled["state"]
        result = state["results"][explicit["id"]]
        self.assertEqual(set(result["outcomes"].values()), {"missing"},
            "why: obsolete policy has no acceptable candidate coverage; remedy: settle missing, never manufacture pass")
        self.assertEqual(set(result["outcomes"]), set(self.policy.suite_ids))
        self.assertEqual(result["reference"], "missing:" + explicit["id"])
        self.assertIsNone(state["active"])
        self.assertIsNone(state["blocked"])
        self.assertTrue(state["debts"])
        self.assertTrue(state["failures"])
        for key in ("processed", "debts", "failures"):
            self.assertEqual(state[key], admitted["state"][key])
        self.api.add_run(21)
        replayed = self.make(21).reconcile(execute=False)
        self.assertEqual(replayed["state"], state)

    def test_branch_context_is_rejected(self):
        self.env["GITHUB_REF"] = "refs/heads/task"
        with self.assertRaisesRegex(batch.BatchError, "main workflow"):
            self.make()

    def test_rerun_context_is_rejected(self):
        self.env["GITHUB_RUN_ATTEMPT"] = "2"
        with self.assertRaisesRegex(batch.BatchError, "first-attempt"):
            self.make()

    def test_missing_lock_is_rejected_before_write(self):
        self.env.pop("BATCH_WRITER_LOCK")
        with self.assertRaisesRegex(batch.BatchError, "short writer lock"):
            self.make().initialize()

    def test_stale_cli_output_is_not_overwritten_or_executed(self):
        destination = self.root / "answer.json"
        destination.write_text("previous execute")
        with mock.patch.object(runtime, "Runtime") as factory:
            self.assertEqual(runtime.main(["settle", "--config", "missing", "--output", str(destination)]), 1)
        factory.assert_not_called()
        self.assertEqual(destination.read_text(), "previous execute")

    def test_reference_roundtrip_does_not_depend_on_artifact(self):
        value = {"failures": ["core"], "debt": "missing", "raw": ["x" * 1000] * 100}
        self.assertEqual(runtime.decode_reference(runtime.encode_reference(value)), value)

    def test_interval_uses_real_actions_only_mapping_reader(self):
        self.advance_main()
        instance = self.make()
        instance.inputs.refresh()
        selected = instance.inputs.interval_selection(self.sha, self.api.sha, self.policy)
        self.assertEqual(selected["kind"], "full")
        self.assertTrue(instance.advice_diagnostics)
        paths = [path for method, path, _ in self.api.calls if method == "GET"]
        self.assertIn("/repos/endaye/lmdj/actions/workflows/pr-review.yml", paths)
        self.assertIn("/repos/endaye/lmdj/actions/artifacts?per_page=100&page=1", paths)
        self.assertFalse(any("/pulls" in path for path in paths))

    def test_authenticated_reader_advice_is_not_discarded_by_wiring(self):
        instance = self.make()
        with mock.patch.object(runtime, "MergeMapReader") as factory:
            factory.return_value.return_value = {"complete": True, "labels": ["test:creator"]}
            factory.return_value.diagnostics = []
            self.assertEqual(instance.inputs.advice({"interval": "fixture"}), {"complete": True, "labels": ["test:creator"]})
        arguments = factory.call_args.args
        self.assertEqual(arguments[:3], ("endaye/lmdj", 1286600062, 8))
        self.assertIs(arguments[3], instance.inputs)

    def paused_debts(self):
        first = self.start()
        self.evidence(first['request'], missing_job='core-asan-macos', failed_job='docs-static')
        self.api.add_run(18)
        self.make(18).reconcile(execute=False)
        self.advance_main()
        self.api.add_run(19)
        second = self.make(19).reconcile(execute=True)
        self.evidence(second['request'], missing_job='core-asan-macos', failed_job='docs-static', run=19)
        self.api.add_run(20)
        settled = self.make(20).reconcile(execute=False)
        self.assertTrue(settled['state']['debts']['core_macos']['paused'])
        self.assertEqual(settled['state']['debts']['core_macos']['attempts'], 2)
        return settled

    def test_resume_unpauses_only_without_execution_or_erasing_evidence(self):
        before = self.paused_debts()['state']
        command = {'id': 'repair-host-1', 'suites': ['core_macos'], 'reason': 'host repair verified'}
        after = self.make(20).reconcile(resume=command)
        self.assertEqual(after['action'], 'idle')
        self.assertIsNone(after['state']['active'])
        for key in ('processed', 'failures', 'results', 'requests'):
            self.assertEqual(after['state'][key], before[key], 'why: resume erased evidence; remedy: retain prior observations')
        expected = {**before['debts']['core_macos'], 'paused': False, 'attempts': 0}
        self.assertEqual(after['state']['debts'], {'core_macos': expected})
        self.assertTrue(after['state']['recovery_requested'])
        self.assertEqual(self.make(20).journal().load()[-1]['id'], 'resume:repair-host-1')

    def test_resume_redelivery_after_new_failure_cannot_reset_budget(self):
        self.paused_debts()
        command = {'id': 'repair-once', 'suites': ['core_macos'], 'reason': 'host repaired'}
        self.make(20).reconcile(resume=command)
        self.api.add_run(21)
        recovery = self.make(21).reconcile(execute=True)
        self.assertEqual(recovery['action'], 'execute')
        self.assertEqual(recovery['request']['base'], recovery['request']['target'])
        self.api.runs[21].update(status='completed', conclusion='cancelled')
        self.api.jobs[21][0].update(status='completed', conclusion='success')
        self.api.add_run(22)
        settled = self.make(22).reconcile(execute=False)
        before = self.make(22).journal().load()
        repeated = self.make(22).reconcile(resume=command)
        self.assertEqual(repeated['state'], settled['state'])
        self.assertEqual(self.make(22).journal().load(), before)
        self.assertEqual(repeated['state']['debts']['core_macos']['attempts'], 1)
        self.assertFalse(repeated['state']['recovery_requested'])
        self.assertEqual(self.make(22).reconcile(execute=True)['action'], 'idle')

    def test_resume_same_identity_different_payload_is_refused(self):
        self.paused_debts()
        command = {'id': 'repair-once', 'suites': ['core_macos'], 'reason': 'host repaired'}
        self.make(20).reconcile(resume=command)
        with self.assertRaisesRegex(batch.BatchError, 'different command'):
            self.make(20).reconcile(resume={**command, 'reason': 'different repair'})

    def test_resume_redelivery_after_coverage_is_noop(self):
        self.paused_debts()
        command = {'id': 'repair-once', 'suites': ['core_macos'], 'reason': 'host repaired'}
        self.make(20).reconcile(resume=command)
        self.advance_main(content="second main change\n")
        self.api.add_run(21)
        recovery = self.make(21).reconcile(execute=True)
        self.evidence(recovery['request'], run=21)
        self.api.add_run(22)
        settled = self.make(22).reconcile(execute=False)
        self.assertEqual(settled['state']['debts'], {})
        before = self.make(22).journal().load()
        repeated = self.make(22).reconcile(resume=command)
        self.assertEqual(repeated['state'], settled['state'],
                         'why: old resume recreated covered debt; remedy: replay stable command as a no-op')
        self.assertEqual(self.make(22).journal().load(), before)

    def test_resume_live_or_terminal_active_requires_separate_settle(self):
        start = self.start()
        command = {'id': 'not-yet', 'suites': ['core_macos'], 'reason': 'repair'}
        for terminal in (False, True):
            if terminal:
                self.evidence(start['request'], missing_job='core-asan-macos')
            self.api.add_run(18)
            before = self.make(18).journal().load()
            with self.assertRaisesRegex(batch.BatchError, 'settle'):
                self.make(18).reconcile(resume=command)
            self.assertEqual(self.make(18).journal().load(), before)

    def test_resume_closed_input_rejects_invalid_values_before_events(self):
        self.paused_debts()
        valid = {'id': 'repair', 'suites': ['core_macos'], 'reason': 'fixed host'}
        for command in ({**valid, 'extra': 1}, {**valid, 'id': ' '}, {**valid, 'reason': ' '},
                        {**valid, 'id': True}, {**valid, 'suites': []},
                        {**valid, 'suites': ['core_macos', 'core_macos']},
                        {**valid, 'suites': [True]}, {**valid, 'suites': ['not-a-debt']}):
            with self.subTest(command=command):
                before = self.make(20).journal().load()
                with self.assertRaises(batch.BatchError):
                    self.make(20).reconcile(resume=command)
                self.assertEqual(self.make(20).journal().load(), before)

    def test_resume_cannot_combine_execution_or_explicit_request(self):
        self.paused_debts()
        command = {'id': 'repair', 'suites': ['core_macos'], 'reason': 'fixed host'}
        for options in ({'execute': True}, {'explicit': {'id': 'node', 'kind': 'node', 'target': self.api.sha}}):
            before = self.make(20).journal().load()
            with self.assertRaisesRegex(batch.BatchError, 'resume'):
                self.make(20).reconcile(resume=command, **options)
            self.assertEqual(self.make(20).journal().load(), before)

    def test_resume_write_response_loss_replays_once(self):
        self.paused_debts()
        command = {'id': 'repair-once', 'suites': ['core_macos'], 'reason': 'fixed host'}
        self.api.lose = 'resume'
        with self.assertRaises(batch.BatchError):
            self.make(20).reconcile(resume=command)
        answer = self.make(20).reconcile(resume=command)
        self.assertEqual(answer['action'], 'idle')
        self.assertEqual(sum(e['type'] == 'resume' for e in self.make(20).journal().load()), 1)

    def test_resume_refuses_unavailable_storage(self):
        self.paused_debts()
        self.api.fail = ('POST', '/graphql')
        with self.assertRaises(batch.BatchError):
            self.make(20).reconcile(resume={'id': 'repair', 'suites': ['core_macos'], 'reason': 'fixed host'})

    def resume_cli(self, contents, operation='resume'):
        config, request, output = self.root / 'config.json', self.root / 'resume.json', self.root / 'answer.json'
        config.write_text(json.dumps(self.config))
        request.write_text(contents)
        instance = self.make(20)
        # Actual CLI parser, file input and real runtime/Journal/HTTP fixtures;
        # only constructor injection replaces environment/token discovery.
        with mock.patch.object(runtime, 'Runtime', return_value=instance):
            status = runtime.main([operation, '--config', str(config), '--request', str(request), '--output', str(output)])
        return status, json.loads(output.read_text()) if output.exists() else None

    def test_actual_resume_cli_persists_idle_action_not_execute(self):
        self.paused_debts()
        status, answer = self.resume_cli(json.dumps({'id': 'cli-repair', 'suites': ['core_macos'], 'reason': 'host restored'}))
        self.assertEqual(status, 0)
        self.assertEqual(answer['action'], 'idle')
        self.assertFalse(answer['state']['debts']['core_macos']['paused'])
        self.assertIsNone(answer['state']['active'])

    def test_resume_cli_null_is_not_implicit_settle(self):
        self.paused_debts()
        before = self.make(20).journal().load()
        status, answer = self.resume_cli('null')
        self.assertEqual(status, 1, 'why: null resume silently became settle; remedy: require an explicit closed command')
        self.assertIsNone(answer)
        self.assertEqual(self.make(20).journal().load(), before)

    def test_resume_cli_duplicate_key_refuses_without_output(self):
        self.paused_debts()
        status, answer = self.resume_cli('{"id":"first","id":"second","suites":["core_macos"],"reason":"fixed"}')
        self.assertEqual(status, 1)
        self.assertIsNone(answer)

    def test_init_and_settle_cli_do_not_accept_resume_command(self):
        self.paused_debts()
        for operation in ('init', 'settle'):
            before = self.make(20).journal().load()
            status, answer = self.resume_cli(json.dumps({'id': 'repair', 'suites': ['core_macos'], 'reason': 'fixed'}), operation)
            self.assertEqual(status, 1)
            self.assertIsNone(answer)
            self.assertEqual(self.make(20).journal().load(), before)

    def test_resume_cli_requires_command_file_before_constructing_runtime(self):
        with mock.patch.object(runtime, 'Runtime') as constructor:
            status = runtime.main(['resume', '--config', str(self.root / 'unused'), '--output', str(self.root / 'absent')])
        self.assertEqual(status, 1)
        constructor.assert_not_called()

    def test_resume_requires_same_writer_lock(self):
        self.paused_debts()
        self.env['BATCH_WRITER_LOCK'] = 'wrong'
        with self.assertRaisesRegex(batch.BatchError, 'short writer lock'):
            self.make(20).reconcile(resume={'id': 'repair', 'suites': ['core_macos'], 'reason': 'fixed'})

    def test_reference_bomb_and_trailing_stream_rejected(self):
        for compressed in (zlib.compress(b"x" * (runtime.MAX_DOCUMENT + 1)), zlib.compress(b"{}") + zlib.compress(b"{}")):
            with self.subTest(size=len(compressed)), self.assertRaisesRegex(batch.BatchError, "incomplete durable"):
                runtime.decode_reference(runtime.REFERENCE_PREFIX + base64.b64encode(compressed).decode())


if __name__ == "__main__":
    unittest.main()
