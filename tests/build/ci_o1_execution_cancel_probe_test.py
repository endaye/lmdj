"""C2 local protocol journeys; cancelled fixture metadata is not real cancellation."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]
import o1_execution_cancel_probe as c2


class CancellationProbeTests(unittest.TestCase):
    def setUp(self):
        fixtures = importlib.import_module("ci_o1_execution_claim_probe_test")
        self.c1 = fixtures.ClaimProbeTests()
        self.f = importlib.import_module("ci_batch_runtime_test").RuntimeTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.c1.f, self.c1.module = self.f, c2.claim
        self.f.config["epoch"] = "o1-claim-cancel-fixture"
        self.c1.manifest = {"claim": deepcopy(self.f.config),
            "scheduler": {**self.f.config, "issue_number": 783, "issue_node_id": "scheduler-node", "epoch": "o1-recovery-scheduler-fixture"},
            "outbox": {**self.f.config, "issue_number": 784, "issue_node_id": "outbox-node", "epoch": "o1-recovery-outbox-fixture"}}
        self.c1.path = self.f.root / c2.claim.MANIFEST
        self.c1.commit_manifest()
        self.f.make().initialize()
        self.f.api.calls.clear()

    def make(self):
        return c2.CancellationProbe(self.f.config, root=self.f.root,
                                    environment=self.f.env, api=self.f.api)

    def intent(self):
        return {"operation": c2.OPERATION, "enabled": True}

    def test_default_disabled_is_false_and_zero_api(self):
        answer = self.make().execute({"operation": c2.OPERATION})
        self.assertEqual(answer, c2.record("disabled"), "why: default must not arm waiter; remedy: retain disabled false record")
        self.assertEqual(self.f.api.calls, [], "why: disabled accessed API; remedy: return before preparation")

    def test_closed_intent_and_boolean_are_strict(self):
        for value in (None, {}, {"operation": "cancel"}, {**self.intent(), "run_id": 17},
                      {**self.intent(), "enabled": 1}, {**self.intent(), "enabled": "true"}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "why:.*remedy:"):
                self.make().execute(value)
        self.assertEqual(self.c1.writes(), [])

    def test_old_claim_epoch_is_not_c2_storage(self):
        self.f.config["epoch"] = "o1-claim-fixture"
        with self.assertRaisesRegex(ValueError, "cancellation claim epoch"):
            self.make().execute(self.intent())
        self.assertEqual(self.c1.writes(), [])

    def test_manifest_mismatch_stops_before_writes(self):
        self.f.config["epoch"] = "o1-claim-cancel-other"
        with self.assertRaisesRegex(ValueError, "reviewed claim role"):
            self.make().execute(self.intent())
        self.assertEqual(self.c1.writes(), [])

    def test_old_active_executor_blocks_before_claim(self):
        self.f.api.old_runs = [{"id": 900, "status": "in_progress"}]
        with self.assertRaisesRegex(ValueError, "old controlled runs"):
            self.make().execute(self.intent())
        self.assertEqual(self.c1.writes(), [])

    def test_real_claim_ready_then_cancelled_run_missing_all16_and_replay(self):
        answer = self.make().execute(self.intent())
        self.assertEqual(set(answer), {"schema", "status", "diagnostic_ready", "identity"})
        self.assertIs(answer["diagnostic_ready"], True)
        self.assertEqual(answer["identity"]["run_id"], 17)
        self.assertEqual(answer["identity"]["attempt"], 1)
        self.assertEqual(answer["identity"]["control_sha"], self.c1.control)
        events = self.f.make().journal().load()
        self.assertEqual([e["type"] for e in events], ["observe", "admit", "claim"])
        frozen = deepcopy(events)
        request = events[1]["data"]["request"]
        self.assertEqual(len(request["selection"]["suites"]), 16)
        self.assertEqual(request["selection"]["kind"], "full")
        self.assertIsNone(request["base"])
        self.assertFalse((self.f.root / "result.json").exists())
        # Fixture simulates PLATFORM finalization. Actual GitHub cancellation,
        # waiter signals/locks and zero heavy jobs require the remote O1 leg.
        fresh = self.c1.fresh(conclusion="cancelled")
        settled = fresh.reconcile(execute=False)
        state = settled["state"]
        self.assertIsNone(state["active"])
        self.assertIsNone(settled["request"])
        self.assertEqual(state["processed"], self.c1.control)
        self.assertEqual(state["failures"], [])
        result = state["results"][request["id"]]
        self.assertEqual(result["reference"], "missing:" + request["id"])
        self.assertEqual(result["outcomes"], {s: "missing" for s in request["selection"]["suites"]})
        self.assertEqual(set(state["debts"]), set(request["selection"]["suites"]))
        self.assertTrue(all(d["attempts"] == 1 and d["outcome"] == "missing" for d in state["debts"].values()))
        after = fresh.journal().load()
        self.assertEqual(after[:3], frozen)
        self.assertEqual([e["type"] for e in after], ["observe", "admit", "claim", "result", "advance"])
        remote = deepcopy((self.f.api.issue, self.f.api.comments))
        replay = self.c1.fresh(18, 19, "success").reconcile(execute=False)
        self.assertEqual(replay["state"], state)
        self.assertEqual(remote, (self.f.api.issue, self.f.api.comments))

    def test_unknown_executor_never_becomes_missing(self):
        self.make().execute(self.intent())
        self.f.api.add_run(18)
        self.f.env["GITHUB_RUN_ID"] = "18"
        answer = self.f.make(18).reconcile(execute=False)
        self.assertIsNotNone(answer["state"]["active"])
        self.assertEqual(answer["state"]["results"], {})
        self.assertIsNone(answer["state"]["processed"])

    def test_claim_response_loss_is_not_ready_and_not_retried(self):
        self.f.api.lose = "claim"
        with self.assertRaises(Exception):
            self.make().execute(self.intent())
        snapshot = deepcopy((self.f.api.issue, self.f.api.comments))
        with self.assertRaises(Exception):
            self.make().execute(self.intent())
        self.assertEqual(snapshot, (self.f.api.issue, self.f.api.comments))

    def test_normal_return_is_not_durable_ready(self):
        probe = self.make()
        with mock.patch.object(probe.claim, "execute", return_value={"status": "disabled"}):
            with self.assertRaisesRegex(ValueError, "without the verified"):
                probe.execute(self.intent())

    def test_wrong_completion_identity_rejected(self):
        probe = self.make()
        wrong = c2.claim.ControlledExit({"run_id": 999})
        with mock.patch.object(probe.claim, "execute", side_effect=wrong):
            with self.assertRaisesRegex(ValueError, "malformed"):
                probe.execute(self.intent())

    def test_full_completion_wrong_run_or_boolean_attempt_is_not_ready(self):
        identity = {"run_id": 17, "attempt": 1, "control_sha": self.c1.control,
                    "request_id": "fixture-request", "journal_head": "a" * 64,
                    "issue_number": self.f.config["issue_number"], "epoch": self.f.config["epoch"]}
        for patch in ({"run_id": 99}, {"attempt": True}, {"control_sha": "b" * 40}):
            probe = self.make()
            with self.subTest(patch=patch), mock.patch.object(probe.claim, "execute",
                    side_effect=c2.claim.ControlledExit({**identity, **patch})):
                with self.assertRaisesRegex(ValueError, "does not bind"):
                    probe.execute(self.intent())
        self.assertEqual(self.c1.writes(), [])

    def cli(self, intent, *, existing=False):
        self.config = self.f.root / "c2-config.json"
        self.request = self.f.root / "c2-intent.json"
        self.diagnostic = self.f.root / "c2-diagnostic.json"
        self.summary = self.f.root / "c2-summary.txt"
        self.config.write_text(json.dumps(self.f.config))
        self.request.write_text(json.dumps(intent))
        if existing:
            self.diagnostic.write_text("retained old diagnostic")
        argv = ["--config", str(self.config), "--request", str(self.request),
                "--root", str(self.f.root), "--diagnostic", str(self.diagnostic), "--summary", str(self.summary)]
        actual = c2.CancellationProbe
        def construct(config, *, root):
            return actual(config, root=root, environment=self.f.env, api=self.f.api)
        with mock.patch.object(c2, "CancellationProbe", side_effect=construct):
            return c2.main(argv)

    def test_real_cli_ready_is_only_diagnostic_not_execution_output(self):
        github_output = self.f.root / "github-output"
        github_output.write_text("existing-other-step-output\n")
        with mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(github_output)}):
            self.assertEqual(self.cli(self.intent()), 0)
        self.assertEqual(github_output.read_text(), "existing-other-step-output\n")
        value = json.loads(self.diagnostic.read_text())
        self.assertIs(value["diagnostic_ready"], True)
        self.assertNotIn("action", value)
        self.assertNotIn("request", value)
        self.assertNotIn("executor", value)
        self.assertIn("not cancellation or test evidence", self.summary.read_text())

    def test_cli_disabled_has_false_record_zero_api(self):
        self.assertEqual(self.cli({"operation": c2.OPERATION}), 0)
        self.assertEqual(json.loads(self.diagnostic.read_text()), c2.record("disabled"))
        self.assertEqual(self.f.api.calls, [])

    def test_cli_failure_retains_false_record_and_durable_history(self):
        self.f.api.lose = "claim"
        self.assertEqual(self.cli(self.intent()), 1)
        self.assertEqual(json.loads(self.diagnostic.read_text()), c2.record("error"))
        self.assertEqual(len(self.f.api.comments), 3)

    def test_existing_diagnostic_refuses_before_api_without_overwrite(self):
        self.assertEqual(self.cli(self.intent(), existing=True), 1)
        self.assertEqual(self.diagnostic.read_text(), "retained old diagnostic")
        self.assertEqual(self.f.api.calls, [])


if __name__ == "__main__":
    unittest.main()
