"""C1 complete local journeys; HTTP fixtures do not prove hosted cancellation/locking."""
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


class ClaimProbeTests(unittest.TestCase):
    def setUp(self):
        fixtures = importlib.import_module("ci_batch_runtime_test")
        self.module = importlib.import_module("o1_execution_claim_probe")
        self.f = fixtures.RuntimeTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.config["epoch"] = "o1-claim-fixture"
        # Real Git blob with the same closed role schema, using isolated fixture
        # identities, NOT a changed copy of the reviewed production manifest.
        self.manifest = {"claim": deepcopy(self.f.config),
            "scheduler": {**self.f.config, "issue_number": 783, "issue_node_id": "scheduler-node", "epoch": "o1-recovery-scheduler-fixture"},
            "outbox": {**self.f.config, "issue_number": 784, "issue_node_id": "outbox-node", "epoch": "o1-recovery-outbox-fixture"}}
        self.path = self.f.root / self.module.MANIFEST
        self.commit_manifest()
        self.f.make().initialize()
        self.f.api.calls.clear()

    def commit_manifest(self):
        self.path.write_text(json.dumps(self.manifest))
        self.f.git("add", self.module.MANIFEST)
        self.f.git("commit", "-qm", "fixture manifest")
        self.control = self.f.git("rev-parse", "HEAD")
        self.f.sha = self.f.api.sha = self.control
        self.f.env["GITHUB_SHA"] = self.control
        self.f.api.add_run(17)

    def make(self, config=None):
        return self.module.ClaimProbe(config or self.f.config, root=self.f.root, environment=self.f.env, api=self.f.api)

    def intent(self):
        return {"operation": self.module.OPERATION, "fault": self.module.FAULT}

    def writes(self):
        return [c for c in self.f.api.calls if c[0] != "GET" and c[1] != "/graphql"]

    def trigger(self):
        probe = self.make()
        with self.assertRaises(self.module.ControlledExit) as stopped:
            probe.execute(probe.prepare(self.intent()))
        return stopped.exception.identity

    def fresh(self, previous=17, current=18, conclusion="failure"):
        self.f.api.runs[previous].update(status="completed", conclusion=conclusion)
        self.f.api.jobs[previous][0].update(status="completed", conclusion=conclusion)
        self.f.api.add_run(current)
        self.f.env["GITHUB_RUN_ID"] = str(current)
        return self.f.make(current)

    def test_default_disabled_has_no_api_calls_or_files(self):
        probe = self.make()
        prepared = probe.prepare({"operation": self.module.OPERATION})
        self.assertEqual(probe.execute(prepared), {"status": "disabled", "remote_writes": 0})
        self.assertEqual(self.f.api.calls, [])
        self.assertFalse((self.f.root / "result.json").exists())

    def test_prepare_authenticates_fixed_blob_and_empty_state_without_writes(self):
        prepared = self.make().prepare(self.intent())
        self.assertEqual(prepared["manifest"], self.manifest)
        self.assertEqual(prepared["controller"]["control_sha"], self.control)
        self.assertEqual(self.writes(), [])

    def test_real_claim_exit_then_distinct_settle_all16_missing_debt_then_fresh_replay(self):
        identity = self.trigger()
        self.assertEqual(identity["run_id"], 17)
        journal = self.f.make().journal()
        events = journal.load()
        self.assertEqual([e["type"] for e in events], ["observe", "admit", "claim"])
        request = events[1]["data"]["request"]
        self.assertEqual(len(request["selection"]["suites"]), 16)
        self.assertEqual(request["selection"]["kind"], "full")
        self.assertEqual(events[2]["data"]["run"], {"run_id": 17, "attempt": 1})
        self.assertEqual(journal.anchor.read(), {"head": identity["journal_head"], "pending": None})
        self.assertFalse((self.f.root / "result.json").exists())
        fresh = self.fresh()
        answer = fresh.reconcile(execute=False)
        state = answer["state"]
        self.assertEqual(answer["action"], "idle")
        self.assertIsNone(state["active"])
        self.assertEqual(state["processed"], self.control)
        self.assertEqual(state["failures"], [])
        result = state["results"][request["id"]]
        self.assertEqual(result["reference"], "missing:" + request["id"])
        self.assertEqual(result["outcomes"], {suite: "missing" for suite in request["selection"]["suites"]})
        self.assertEqual(set(state["debts"]), set(request["selection"]["suites"]))
        self.assertTrue(all(d["attempts"] == 1 and d["outcome"] == "missing" for d in state["debts"].values()))
        self.assertEqual([e["type"] for e in fresh.journal().load()], ["observe", "admit", "claim", "result", "advance"])
        before = deepcopy((self.f.api.issue, self.f.api.comments))
        replay = self.fresh(18, 19, "success").reconcile(execute=False)
        self.assertEqual(replay["state"], state)
        self.assertEqual(before, (self.f.api.issue, self.f.api.comments))

    def test_same_issue_changed_epoch_is_rejected_by_manifest_before_writes(self):
        changed = {**self.f.config, "epoch": "o1-claim-other"}
        # Existing Runtime itself accepts the empty anchor under this epoch.
        ordinary = self.module.batch_runtime.Runtime(changed, root=self.f.root, environment=self.f.env, api=self.f.api)
        ordinary.authenticate_current()
        self.assertEqual(ordinary.journal().load(), [])
        with self.assertRaisesRegex(ValueError, "differs from the reviewed claim role"):
            self.make(changed).prepare(self.intent())
        self.assertEqual(self.writes(), [])

    def test_a_b_storage_config_cannot_be_used_as_claim(self):
        for role in ("scheduler", "outbox"):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, "claim role"):
                self.make(self.manifest[role]).prepare(self.intent())
        self.assertEqual(self.writes(), [])

    def test_missing_manifest_cannot_use_uncommitted_replacement(self):
        self.f.git("rm", self.module.MANIFEST)
        self.f.git("commit", "-qm", "fixture missing manifest")
        self.f.env["GITHUB_SHA"] = self.f.git("rev-parse", "HEAD")
        self.path.write_text(json.dumps(self.manifest))
        with self.assertRaises(Exception):
            self.make().prepare(self.intent())
        self.assertEqual(self.writes(), [])

    def test_dirty_working_copy_cannot_replace_committed_manifest(self):
        self.path.write_text('{"malicious":"replacement"}')
        self.assertEqual(self.make().prepare(self.intent())["manifest"], self.manifest)
        self.assertEqual(self.writes(), [])

    def test_manifest_numbers_and_nodes_must_be_independently_unique(self):
        for key in ("issue_number", "issue_node_id"):
            bad = deepcopy(self.manifest)
            bad["scheduler"][key] = bad["claim"][key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "alias"):
                self.module.validate_manifest(bad)

    def test_closed_intent_excludes_cancel_wait_and_arbitrary_selection(self):
        for value in ({"operation": "cancel"}, {**self.intent(), "selection": []},
                      {"operation": self.module.OPERATION, "fault": "wait"}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "why:.*remedy:"):
                self.make().prepare(value)
        self.assertEqual(self.writes(), [])

    def test_old_running_execution_blocks_before_any_journal_write(self):
        self.f.api.old_runs = [{"id": 900, "status": "in_progress"}]
        with self.assertRaisesRegex(ValueError, "old controlled runs"):
            self.make().prepare(self.intent())
        self.assertEqual(self.writes(), [])

    def test_real_racing_old_run_audit_remains_enabled(self):
        probe = self.make()
        prepared = probe.prepare(self.intent())
        old_check = probe.runtime.old_runs_terminal
        checks = []
        def check():
            checks.append(True)
            if len(checks) == 2:
                self.f.api.old_runs = [{"id": 900, "status": "in_progress"}]
            return old_check()
        probe.runtime.old_runs_terminal = check
        with self.assertRaisesRegex(ValueError, "did not reach"):
            probe.execute(prepared)
        self.assertEqual(len(checks), 2)
        self.assertEqual([e["type"] for e in self.f.make().journal().load()], ["observe"])

    def test_original_claim_write_loss_is_not_controlled_exit_or_second_claim(self):
        self.f.api.lose = "claim"
        with self.assertRaises(Exception):
            probe = self.make()
            probe.execute(probe.prepare(self.intent()))
        self.assertEqual(len(self.f.api.comments), 3)
        before = deepcopy(self.writes())
        with self.assertRaisesRegex(ValueError, "pending"):
            self.make().prepare(self.intent())
        self.assertEqual(before, self.writes())
        answer = self.fresh().reconcile(execute=False)
        self.assertEqual(len(answer["state"]["debts"]), 16)
        self.assertEqual(sum(e["type"] == "claim" for e in self.f.make(18).journal().load()), 1)

    def test_running_executor_waits_and_keeps_original_claim(self):
        self.trigger()
        self.f.api.add_run(18)
        answer = self.f.make(18).reconcile(execute=False)
        self.assertEqual(answer["action"], "waiting")
        self.assertEqual(answer["state"]["active"]["claim"], {"run_id": 17, "attempt": 1})
        self.assertIsNone(answer["state"]["processed"])
        self.assertFalse(answer["state"]["results"])

    def test_real_docs_delta_after_failure_retains_debt_without_execution(self):
        self.trigger()
        settled = self.fresh().reconcile(execute=False)["state"]
        file = self.f.root / "docs/notes/c1-fixture.md"
        file.parent.mkdir(parents=True)
        file.write_text("Local fixture explanatory note, not remote acceptance.\n")
        self.f.git("add", "docs/notes/c1-fixture.md")
        self.f.git("commit", "-qm", "fixture genuine Git docs delta")
        latest = self.f.git("rev-parse", "HEAD")
        self.f.api.sha = latest
        self.f.env["GITHUB_SHA"] = latest
        runtime = self.fresh(18, 19, "success")
        answer = runtime.reconcile(execute=False)
        self.assertEqual(answer["action"], "idle")
        self.assertEqual(answer["state"]["pending"], latest)
        self.assertEqual(answer["state"]["processed"], self.control)
        self.assertEqual(answer["state"]["debts"], settled["debts"])
        self.assertEqual(answer["state"]["failures"], settled["failures"])
        policy = runtime.inputs.policy_at(runtime.control)
        floor = runtime.inputs.interval_selection(self.control, latest, policy)
        self.assertEqual(floor["kind"], "none")
        required = self.module.batch.required_selection(answer["state"], policy, floor)
        self.assertEqual(set(required["suites"]), set(policy.suite_ids))

    def test_cli_exits_nonzero_without_executable_output_or_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, request, summary, output = [root / name for name in ("config", "request", "summary", "github-output")]
            config.write_text(json.dumps(self.f.config))
            request.write_text(json.dumps(self.intent()))
            argv = ["--config", str(config), "--request", str(request), "--root", str(self.f.root), "--summary", str(summary)]
            with mock.patch.object(self.module, "ClaimProbe", return_value=self.make()), mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(output)}):
                self.assertEqual(self.module.main(argv), 87)
            self.assertIn("not GitHub cancellation", summary.read_text())
            self.assertNotIn('"action": "execute"', summary.read_text())
            self.assertFalse(output.exists())
            self.assertFalse((self.f.root / "result.json").exists())

    def test_unknown_executor_metadata_never_advances_or_reclaims(self):
        self.trigger()
        self.f.api.runs[17]["status"] = "unknown-platform-state"
        self.f.api.add_run(18)
        before = deepcopy((self.f.api.issue, self.f.api.comments))
        with self.assertRaises(Exception):
            self.f.make(18).reconcile(execute=False)
        self.assertEqual(before, (self.f.api.issue, self.f.api.comments))

    def test_wrong_workflow_source_and_nonfirst_attempt_never_write(self):
        self.f.api.runs[17]["workflow_id"] = 999
        with self.assertRaises(Exception):
            self.make().prepare(self.intent())
        self.f.env["GITHUB_RUN_ATTEMPT"] = "2"
        with self.assertRaises(Exception):
            self.make()
        self.assertEqual(self.writes(), [])

    def test_new_main_between_prepare_and_execute_cannot_arm(self):
        probe = self.make()
        prepared = probe.prepare(self.intent())
        self.f.api.sha = "d" * 40
        with self.assertRaises(Exception):
            probe.execute(prepared)
        self.assertEqual(self.writes(), [])

    def test_prepared_snapshot_mutation_is_rejected(self):
        probe = self.make()
        prepared = probe.prepare(self.intent())
        prepared["controller"]["run_id"] = 123
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            probe.execute(prepared)
        self.assertEqual(self.writes(), [])

    def test_nonempty_reuse_cannot_emit_a_second_claim(self):
        self.trigger()
        before = deepcopy(self.writes())
        with self.assertRaisesRegex(ValueError, "fresh empty"):
            self.make().prepare(self.intent())
        self.assertEqual(before, self.writes())

    def test_invalid_manifest_and_protected_ids_fail_closed(self):
        for changed in (None, {}, {**self.manifest, "extra": {}},
                        {**self.manifest, "claim": {**self.manifest["claim"], "issue_number": 807}},
                        {**self.manifest, "claim": {**self.manifest["claim"], "workflow_id": 999}},
                        {**self.manifest, "claim": {**self.manifest["claim"], "epoch": "o1-recovery-claim-wrong"}}):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "why:.*remedy:"):
                self.module.validate_manifest(changed)

    def test_duplicate_keys_in_committed_manifest_are_rejected(self):
        body = json.dumps(self.manifest)
        self.path.write_text(body[:-1] + ',"claim":' + json.dumps(self.manifest["claim"]) + '}')
        self.f.git("add", self.module.MANIFEST)
        self.f.git("commit", "-qm", "fixture duplicate manifest key")
        self.f.env["GITHUB_SHA"] = self.f.git("rev-parse", "HEAD")
        with self.assertRaises(Exception):
            self.make().prepare(self.intent())
        self.assertEqual(self.writes(), [])

    def test_cli_original_failure_is_not_c1_success_and_no_secret_is_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, request, summary = [root / name for name in ("config", "request", "summary")]
            config.write_text(json.dumps(self.f.config))
            request.write_text(json.dumps(self.intent()))
            argv = ["--config", str(config), "--request", str(request), "--root", str(self.f.root), "--summary", str(summary)]
            self.f.api.lose = "claim"
            with mock.patch.object(self.module, "ClaimProbe", return_value=self.make()):
                self.assertEqual(self.module.main(argv), 1)
            self.assertIn('"status": "error"', summary.read_text())
            self.assertNotIn("SECRET", summary.read_text())
            self.assertNotIn("controlled-claim-before-output-exit", summary.read_text())

    def test_cli_disabled_uses_actual_constructor_without_api_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, request, summary = [root / name for name in ("config", "request", "summary")]
            config.write_text(json.dumps(self.f.config))
            request.write_text(json.dumps({"operation": self.module.OPERATION}))
            argv = ["--config", str(config), "--request", str(request), "--root", str(self.f.root), "--summary", str(summary)]
            with mock.patch.dict("os.environ", self.f.env), mock.patch.object(self.module.batch_runtime.UrllibGitHubApi, "_request", side_effect=AssertionError("unexpected API")) as api:
                self.assertEqual(self.module.main(argv), 0)
                api.assert_not_called()
            self.assertIn('"remote_writes": 0', summary.read_text())


if __name__ == "__main__":
    unittest.main()
