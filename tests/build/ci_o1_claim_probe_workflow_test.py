"""Actual C1 manual entry to real CLI/journal; no hosted fault/cancellation claim."""
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]
from ci_self_test_report_workflow_test import block, field, scalars


class ClaimWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("o1_execution_claim_probe")
        self.source = (ROOT / ".github/workflows/self-test-report.yml").read_text()
        self.controller = block(self.source, "controller", 2)
        self.step = self.controller.split("      - name: Run the isolated claim-before-output probe\n", 1)[1].split("      - name:", 1)[0]
        self.code = "\n".join(line[10:] for line in self.step.split("          python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0].splitlines())

    def invoke(self, *, extra=None, real=None, code=0, actual_disabled=False):
        with tempfile.TemporaryDirectory() as directory:
            summary, output = [Path(directory) / name for name in ("summary", "outputs")]
            config = real.f.config if real else {"repository": "endaye/lmdj", "issue_number": 826,
                "issue_node_id": "fixture-claim", "bot_node_id": "fixture-bot", "workflow_id": 7, "epoch": "o1-claim-fixture"}
            env = {"RUNNER_TEMP": directory, "GITHUB_STEP_SUMMARY": str(summary), "GITHUB_OUTPUT": str(output),
                "BATCH_OPERATION": "claim-probe", "JOURNAL_CONFIG": json.dumps(config),
                "PROBE_REQUEST": json.dumps({"operation": self.module.OPERATION}),
                "GITHUB_REPOSITORY": "endaye/lmdj", "GITHUB_RUN_ID": "17", "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "a" * 40, "BATCH_WRITER_LOCK": "self-test-report",
                **(real.f.env if real else {}), **(extra or {})}
            calls = []
            actual_run = subprocess.run
            def execute(command, **kwargs):
                if command[:2] != ["python3", "scripts/ci/o1_execution_claim_probe.py"]:
                    self.assertEqual(command[0], "git", "why: unexpected workflow subprocess; remedy: keep C1 controller-only")
                    return actual_run(command, **kwargs)
                calls.append(command)
                self.assertEqual(kwargs, {"check": False})
                self.assertEqual(set(command[2::2]), {"--config", "--request", "--root", "--summary"})
                for flag, key in (("--config", "JOURNAL_CONFIG"), ("--request", "PROBE_REQUEST")):
                    self.assertEqual(Path(command[command.index(flag) + 1]).read_text(), env[key])
                result = self.module.main(command[2:]) if real or actual_disabled else code
                return subprocess.CompletedProcess(command, result)
            root = real.f.root if real else ROOT
            with mock.patch.dict(os.environ, env), mock.patch.object(Path, "cwd", return_value=root), \
                    mock.patch.object(subprocess, "run", side_effect=execute), \
                    mock.patch.object(self.module.batch_runtime, "UrllibGitHubApi", return_value=real.f.api if real else mock.Mock()) as factory:
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(self.code, "<actual-C1-workflow>", "exec"), {})
                if actual_disabled:
                    factory.return_value._request.assert_not_called()
            self.assertFalse(output.exists(), "why: C1 emitted execute output; remedy: remove executable bridge")
            self.assertFalse((Path(directory) / "incremental-controller/result.json").exists())
            return stopped.exception.code, calls, summary.read_text() if summary.exists() else ""

    def fixture(self):
        fixture = importlib.import_module("ci_o1_execution_claim_probe_test").ClaimProbeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_actual_cli_defaults_disabled_without_api_or_outputs(self):
        code, calls, summary = self.invoke(actual_disabled=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn('"status": "disabled"', summary)

    def test_actual_entry_claim_exit_and_fresh_settle_full_missing_debt(self):
        fixture = self.fixture()
        code, calls, summary = self.invoke(real=fixture, extra={"PROBE_REQUEST": json.dumps(fixture.intent())})
        self.assertEqual(code, 87)
        self.assertEqual(len(calls), 1)
        self.assertIn("not GitHub cancellation", summary)
        events = fixture.f.make().journal().load()
        self.assertEqual([e["type"] for e in events], ["observe", "admit", "claim"])
        self.assertEqual(len(events[1]["data"]["request"]["selection"]["suites"]), 16)
        settled = fixture.fresh().reconcile(execute=False)
        self.assertEqual(settled["action"], "idle")
        self.assertEqual(len(settled["state"]["debts"]), 16)
        self.assertTrue(all(debt["outcome"] == "missing" for debt in settled["state"]["debts"].values()))
        before = deepcopy((fixture.f.api.issue, fixture.f.api.comments))
        self.assertEqual(fixture.fresh(18, 19, "success").reconcile(execute=False)["state"], settled["state"])
        self.assertEqual(before, (fixture.f.api.issue, fixture.f.api.comments))

    def test_actual_original_error_keeps_nonzero_and_no_controlled_success(self):
        fixture = self.fixture()
        fixture.f.api.lose = "claim"
        code, _, summary = self.invoke(real=fixture, extra={"PROBE_REQUEST": json.dumps(fixture.intent())})
        self.assertEqual(code, 1)
        self.assertIn('"status": "error"', summary)
        self.assertNotIn("SECRET", summary)
        self.assertNotIn("controlled-claim-before-output-exit", summary)

    def test_mixed_or_missing_inputs_reject_before_cli(self):
        for key, value in (("BATCH_OPERATION", "recovery-probe"), ("REPORT_CONFIG", "{}"),
            ("BATCH_REQUEST", "{}"), ("LEGACY_RUN_ID", "17"), ("LEGACY_RECONCILE", "true"),
            ("REVIEW_RUN_ID", "17"), ("REVIEW_ATTEMPT", "1"), ("REPORT_LIMIT", "9"),
            ("JOURNAL_CONFIG", ""), ("PROBE_REQUEST", "")):
            with self.subTest(key=key):
                code, calls, _ = self.invoke(extra={key: value})
                self.assertIn("why:", code)
                self.assertIn("remedy:", code)
                self.assertFalse(calls)

    def test_json_passed_as_exact_data_not_workflow_source(self):
        code, calls, _ = self.invoke(extra={"PROBE_REQUEST": '{"value":"$(touch /nope)\\n${{ github.token }}"}'})
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("${{", self.code)

    def test_exit_status_including_accidental_success_has_no_output(self):
        for expected in (0, 1, 87):
            with self.subTest(expected=expected):
                code, calls, _ = self.invoke(code=expected)
                self.assertEqual(code, expected)
                self.assertEqual(len(calls), 1)

    def test_manual_only_same_identity_permissions_and_short_lock(self):
        condition = field(self.controller, "if", 4)
        for value in ("github.event_name == 'workflow_dispatch'", "github.ref == 'refs/heads/main'",
                      "github.run_attempt == '1'", "inputs.batch_operation == 'claim-probe'"):
            self.assertIn(value, condition)
        self.assertEqual(scalars(block(self.controller, "permissions", 4), 6), {"contents": "read", "actions": "read", "issues": "write"})
        self.assertIn("group: self-test-report", block(self.controller, "concurrency", 4))
        self.assertIn("cancel-in-progress: false", self.controller)
        self.assertIn("BATCH_WRITER_LOCK: self-test-report", self.step)
        self.assertIn("ref: ${{ github.sha }}", self.controller)
        self.assertNotRegex(self.source, r"(?m)^concurrency:")

    def test_c1_excludes_scheduler_report_artifact_and_other_probe(self):
        self.assertIn("inputs.batch_operation != 'recovery-probe' && inputs.batch_operation != 'claim-probe' }}", self.controller)
        self.assertIn("if: ${{ startsWith(inputs.batch_operation, 'report-') }}", self.controller)
        self.assertIn("if: ${{ inputs.batch_operation == 'recovery-probe' }}", self.controller)
        self.assertIn("if: ${{ inputs.batch_operation == 'claim-probe' }}", self.step)
        for forbidden in ("GITHUB_OUTPUT", "--output", "upload-artifact", "continue-on-error"):
            self.assertNotIn(forbidden, self.step)
        outputs = scalars(block(self.controller, "outputs", 4), 6)
        self.assertEqual(outputs, {key: "${{ steps.control.outputs." + key + " }}" for key in ("action", "request", "executor")})
        self.assertIn("needs.controller.outputs.action == 'execute'", block(self.source, "execute-batch", 2))

    def test_legacy_automatic_triggers_and_default_remain(self):
        events = block(self.source, "on", 0)
        self.assertIn('workflows: ["Core CI"]', events)
        self.assertIn('cron: "0 18 * * *"', events)
        self.assertNotIn("  push:", events)
        inputs = block(block(events, "workflow_dispatch", 2), "inputs", 4)
        self.assertIn("default: legacy", inputs)
        self.assertIn("claim-probe", field(block(inputs, "batch_operation", 6), "options", 8))
        self.assertIn("inputs.batch_operation == '' || inputs.batch_operation == 'legacy'", block(self.source, "report", 2))


if __name__ == "__main__":
    unittest.main()
