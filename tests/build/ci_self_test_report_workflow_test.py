#!/usr/bin/env python3
"""Contract for `.github/workflows/self-test-report.yml`.

The reporter is the only thing in the self-test path that writes to the Issue
tracker, so what it runs, where, with which token and on which events is
pinned here. A change to any of them is a reviewed act.
"""

from __future__ import annotations

import json
import ast
from pathlib import Path
import re
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/build"))
from workflow_inventory import jobs_in  # noqa: E402

WORKFLOW = ROOT / ".github/workflows/self-test-report.yml"
SCRIPT = ROOT / "scripts/ci/self_test_report.py"
SCOPE_POLICY = ROOT / "scripts/ci/scope_policy.json"
HOSTED_POLICY = ROOT / "scripts/ci/hosted_runner_policy.json"


class SelfTestReportWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.document = yaml.safe_load(cls.source)
        cls.job = cls.document["jobs"]["report"]

    def test_it_reacts_to_core_ci_completion_a_daily_check_and_an_explicit_retry(self) -> None:
        on = self.document[True] if True in self.document else self.document["on"]
        self.assertEqual(on["workflow_run"], {"workflows": ["Core CI"], "types": ["completed"]},
                         "why: the reporter must see every finished batch and nothing before it "
                         "finishes; remedy: keep workflow_run on Core CI completed")
        self.assertEqual(on["schedule"], [{"cron": "0 18 * * *"}])
        self.assertIn("run_id", on["workflow_dispatch"]["inputs"])
        self.assertTrue(on["workflow_dispatch"]["inputs"]["run_id"]["required"])

    def test_the_job_skips_pull_request_and_push_completions(self) -> None:
        condition = self.job["if"]
        for event in ("schedule", "workflow_dispatch"):
            self.assertIn(f"github.event.workflow_run.event == '{event}'", condition)
        self.assertIn("github.event_name != 'workflow_run'", condition)
        self.assertNotIn("pull_request", condition,
                         "why: a pull_request run is never a self-test and each hosted minute is "
                         "billed; remedy: keep the job to the two batch events")

    def test_permissions_are_minimal_and_only_the_job_writes_issues(self) -> None:
        self.assertEqual(self.document["permissions"], {},
                         "why: the workflow default must be none so the job's grant is the only one; "
                         "remedy: keep `permissions: {}` at the top level")
        self.assertEqual(self.job["permissions"], {"contents": "read", "actions": "read", "issues": "write"})
        self.assertNotIn("pull-requests", self.source)
        self.assertNotIn("id-token", self.source)

    def test_only_default_branch_code_is_checked_out_and_nothing_from_the_batch_is_executed(self) -> None:
        steps = self.job["steps"]
        checkouts = [step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")]
        self.assertEqual(len(checkouts), 1)
        self.assertEqual(checkouts[0]["with"]["ref"], "${{ github.event.repository.default_branch }}",
                         "why: workflow_run and schedule already run default-branch code, and a dispatch "
                         "from a branch must not substitute its own reporter; remedy: pin the ref")
        self.assertEqual(checkouts[0]["with"]["fetch-depth"], 1)
        runs = "\n".join(str(step.get("run", "")) for step in steps)
        self.assertNotIn("download-artifact", self.source,
                         "why: the artifact is read as data through the REST API with path checks, not "
                         "unpacked into the workspace by an action; remedy: keep downloads in the script")
        self.assertIn("scripts/ci/self_test_report.py", runs)
        self.assertNotIn("core.sh", runs)
        self.assertNotIn("npm", runs)

    def test_the_two_steps_are_split_by_event_and_pass_the_run_id_through(self) -> None:
        steps = {step["name"]: step for step in self.job["steps"] if "name" in step}
        report = steps["Report the completed batch"]
        missing = steps["Check that today's batch started"]
        self.assertEqual(report["if"], "github.event_name != 'schedule'")
        self.assertEqual(missing["if"], "github.event_name == 'schedule'")
        self.assertIn("github.event.workflow_run.id", report["env"]["RUN_ID"])
        self.assertIn("inputs.run_id", report["env"]["RUN_ID"])
        self.assertIn('report --run-id "$RUN_ID"', report["run"])
        self.assertIn('missing --date "$(date -u +%Y-%m-%d)"', missing["run"])
        for step in (report, missing):
            self.assertEqual(step["env"]["GITHUB_TOKEN"], "${{ secrets.GITHUB_TOKEN }}")

    def test_one_writer_at_a_time_without_killing_a_running_report(self) -> None:
        self.assertEqual(self.document["concurrency"], {"group": "self-test-report", "cancel-in-progress": False, "queue": "max"})
        self.assertIn("reconcile", self.source,
                      "why: GitHub keeps one pending run per group and drops the rest, so the workflow "
                      "must say how a dropped trigger is recovered; remedy: keep the comment that "
                      "names the reconcile pass and keep the pass in the script")

    def test_it_is_a_recorded_hosted_control_plane_job(self) -> None:
        jobs = jobs_in(WORKFLOW)
        self.assertEqual([job.job_id for job in jobs], ["report"])
        self.assertEqual(jobs[0].runs_on, "ubuntu-24.04")
        policy = json.loads(HOSTED_POLICY.read_text(encoding="utf-8"))
        entry = next((e for e in policy["allowed"]
                      if e["workflow"] == "self-test-report.yml" and e["job"] == "report"), None)
        self.assertIsNotNone(entry, "why: a hosted job is a spending decision; remedy: record it in "
                                    "scripts/ci/hosted_runner_policy.json")
        self.assertEqual(entry["category"], "control-plane")

    def test_the_workflow_is_a_registered_ci_contract_path(self) -> None:
        policy = json.loads(SCOPE_POLICY.read_text(encoding="utf-8"))
        rule = next((r for r in policy["rules"]
                     if r["match"] == {"kind": "exact", "value": ".github/workflows/self-test-report.yml"}), None)
        self.assertIsNotNone(rule)
        self.assertEqual(rule["lanes"], ["ci_contract"])

    def test_the_script_detects_batches_by_the_agreed_artifact_name(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        assignment = next(node for node in ast.parse(source).body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "VERDICT_ARTIFACT" for target in node.targets))
        pattern = re.compile(ast.literal_eval(assignment.value.args[0]))
        match = pattern.fullmatch("self-test-verdict-" + "a" * 40 + "-100-2")
        self.assertEqual(match.groupdict(), {"target": "a" * 40, "run": "100", "attempt": "2"})
        self.assertIsNone(pattern.fullmatch("self-test-verdict-" + "a" * 40))
        self.assertIn('VERDICT_FILE = "verdict.json"', source)
        self.assertIn('WORKFLOW_NAME = "Core CI"', source)
        self.assertRegex(source, r'ALLOWED_EVENTS = frozenset\(\{"schedule", "workflow_dispatch"\}\)')


if __name__ == "__main__":
    unittest.main()
