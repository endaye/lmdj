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
import os
import subprocess
import sys
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/build"))
from workflow_inventory import jobs_in  # noqa: E402

WORKFLOW = ROOT / ".github/workflows/self-test-report.yml"
SCRIPT = ROOT / "scripts/ci/self_test_report.py"
SCOPE_POLICY = ROOT / "scripts/ci/scope_policy.json"
HOSTED_POLICY = ROOT / "scripts/ci/hosted_runner_policy.json"


def block(source: str, key: str, indent: int) -> str:
    """Extract one exact-indentation mapping entry, not a general YAML parser."""
    pattern = rf"(?m)^{' ' * indent}{re.escape(key)}:([^\n]*)\n"
    matches = list(re.finditer(pattern, source))
    if len(matches) != 1:
        raise AssertionError(f"why: expected one {key!r} at indentation {indent}; remedy: keep the workflow declaration explicit")
    match = matches[0]
    tail = source[match.end():]
    end = re.search(rf"(?m)^ {{0,{indent}}}[^ #\n]", tail)
    return match.group(1).strip() + "\n" + tail[:end.start() if end else len(tail)]


def field(source: str, key: str, indent: int) -> str:
    value = block(source, key, indent)
    first, _, remainder = value.partition("\n")
    if first in ("|", ">-"):
        return textwrap.dedent(remainder).strip()
    return first


def scalars(source: str, indent: int) -> dict[str, str]:
    return dict(re.findall(rf"(?m)^{' ' * indent}([\w-]+): (.+)$", source))


class SelfTestReportWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.job = block(cls.source, "report", 2)
        cls.steps = {match.group(1): match.group(2) for match in re.finditer(
            r"(?ms)^      - name: ([^\n]+)\n(.*?)(?=^      - |\Z)", cls.job)}

    def test_it_reacts_to_core_ci_completion_a_daily_check_and_an_explicit_retry(self) -> None:
        on = block(self.source, "on", 0)
        self.assertEqual(scalars(block(on, "workflow_run", 2), 4),
                         {"workflows": '["Core CI"]', "types": "[completed]", "branches": "[main]"},
                         "why: the reporter must see every finished batch and nothing before it "
                         "finishes; remedy: keep workflow_run on Core CI completed")
        schedule = block(on, "schedule", 2)
        self.assertEqual(re.findall(r'(?m)^    - cron: (.+)$', schedule), ['"0 18 * * *"'])
        inputs = block(block(on, "workflow_dispatch", 2), "inputs", 4)
        self.assertEqual(field(block(inputs, "run_id", 6), "required", 8), "false")
        self.assertEqual(field(block(inputs, "batch_operation", 6), "default", 8), "legacy")
        retry = block(inputs, "reconcile", 6)
        self.assertEqual(field(retry, "type", 8), "boolean")
        self.assertEqual(field(retry, "default", 8), "false")

    def test_the_job_skips_pull_request_and_push_completions(self) -> None:
        condition = field(self.job, "if", 4)
        for event in ("schedule", "workflow_dispatch"):
            self.assertIn(f"github.event.workflow_run.event == '{event}'", condition)
        self.assertIn("github.event_name != 'workflow_run'", condition)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", condition)
        self.assertNotIn("pull_request", condition,
                         "why: a pull_request run is never a self-test and each hosted minute is "
                         "billed; remedy: keep the job to the two batch events")

    def test_permissions_are_minimal_and_only_the_job_writes_issues(self) -> None:
        self.assertEqual(field(self.source, "permissions", 0), "{}",
                         "why: the workflow default must be none so the job's grant is the only one; "
                         "remedy: keep `permissions: {}` at the top level")
        self.assertEqual(scalars(block(self.job, "permissions", 4), 6),
                         {"contents": "read", "actions": "read", "issues": "write"})
        self.assertNotIn("pull-requests", self.source)
        self.assertNotIn("id-token", self.source)

    def test_only_default_branch_code_is_checked_out_and_nothing_from_the_batch_is_executed(self) -> None:
        checkouts = list(re.finditer(r"(?ms)^      - uses: actions/checkout@[^\n]+\n(.*?)(?=^      - |\Z)", self.job))
        self.assertEqual(len(checkouts), 1)
        checkout = checkouts[0].group(1)
        self.assertEqual(field(checkout, "ref", 10), "${{ github.event.repository.default_branch }}",
                         "why: workflow_run and schedule already run default-branch code, and a dispatch "
                         "from a branch must not substitute its own reporter; remedy: pin the ref")
        self.assertEqual(field(checkout, "fetch-depth", 10), "1")
        runs = "\n".join(field(step, "run", 8) for step in self.steps.values())
        self.assertNotIn("download-artifact", self.source,
                         "why: the artifact is read as data through the REST API with path checks, not "
                         "unpacked into the workspace by an action; remedy: keep downloads in the script")
        self.assertIn("scripts/ci/self_test_report.py", runs)
        self.assertNotIn("core.sh", runs)
        self.assertNotIn("npm", runs)

    def test_the_two_steps_are_split_by_event_and_pass_the_run_id_through(self) -> None:
        report = self.steps["Report the completed batch"]
        missing = self.steps["Check that today's batch started"]
        self.assertEqual(field(report, "if", 8), "github.event_name != 'schedule'")
        self.assertEqual(field(missing, "if", 8), "github.event_name == 'schedule'")
        self.assertIn("github.event.workflow_run.id", field(report, "RUN_ID", 10))
        self.assertIn("inputs.run_id", field(report, "RUN_ID", 10))
        self.assertIn('report --run-id "$RUN_ID"', field(report, "run", 8))
        self.assertIn('missing --date "$(date -u +%Y-%m-%d)"', field(missing, "run", 8))
        for step in (report, missing):
            self.assertEqual(field(step, "GITHUB_TOKEN", 10), "${{ secrets.GITHUB_TOKEN }}")

    def test_one_writer_at_a_time_without_killing_a_running_report(self) -> None:
        self.assertNotRegex(self.source, r'(?m)^concurrency:',
                            'why: a parent lock would span product execution; remedy: lock only short writers')
        self.assertEqual(scalars(block(self.job, "concurrency", 4), 6),
                         {"group": "self-test-report", "cancel-in-progress": "false", "queue": "max"})
        self.assertIn("reconcile", self.source,
                      "why: GitHub keeps one pending run per group and drops the rest, so the workflow "
                      "must say how a dropped trigger is recovered; remedy: keep the comment that "
                      "names the reconcile pass and keep the pass in the script")

    def test_it_is_a_recorded_hosted_control_plane_job(self) -> None:
        jobs = jobs_in(WORKFLOW)
        self.assertEqual([job.job_id for job in jobs], ["report", "controller", "cancel-probe-waiter", "execute-batch"])
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

    def test_manual_retry_can_execute_without_reconciling_unrelated_runs(self) -> None:
        step = self.steps["Report the completed batch"]
        self.assertEqual(field(step, "RECONCILE", 10), "${{ github.event_name != 'workflow_dispatch' || inputs.reconcile }}")
        source = field(step, "run", 8).replace("${{ github.repository }}", "endaye/lmdj")
        for reconcile in ("true", "false"):
            with self.subTest(reconcile=reconcile):
                result = subprocess.run(
                    ["bash", "-c", "python3() { printf '%s\\n' \"$@\"; }\n" + source],
                    env={**os.environ, "RECONCILE": reconcile, "RUN_ID": "100", "GITHUB_STEP_SUMMARY": "/unused"},
                    capture_output=True, text=True, check=True)
                args = result.stdout.splitlines()
                self.assertEqual("--no-reconcile" in args, reconcile == "false")
                self.assertIn("100", args)


if __name__ == "__main__":
    unittest.main()
