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
    def setUp(self):
        self.source = WORKFLOW.read_text()
        self.job = block(self.source, "controller", 2)

    def test_permissions_are_minimal_and_only_controller_writes_issues(self):
        self.assertEqual(field(self.source, "permissions", 0), "{}")
        self.assertEqual(scalars(block(self.job, "permissions", 4), 6),
                         {"contents": "read", "actions": "read", "issues": "write"})
        self.assertNotIn("actions: write", self.source)
        self.assertNotIn("id-token:", self.source)

    def test_current_control_checkout_and_no_product_execution_in_writer(self):
        self.assertIn("ref: ${{ github.sha }}", self.job)
        self.assertIn("fetch-depth: 0", self.job)
        self.assertIn("persist-credentials: false", self.job)
        self.assertNotIn("core.sh", self.job)
        self.assertNotIn("download-artifact", self.job)

    def test_short_single_writer_and_complete_job_inventory(self):
        self.assertNotRegex(self.source, r"(?m)^concurrency:")
        self.assertEqual(scalars(block(self.job, "concurrency", 4), 6),
                         {"group": "self-test-report", "cancel-in-progress": "false", "queue": "max"})
        self.assertEqual([job.job_id for job in jobs_in(WORKFLOW)],
                         ["controller", "cancel-probe-waiter", "execute-batch"])
        policy = json.loads(HOSTED_POLICY.read_text())
        entry = next(e for e in policy["allowed"] if e["workflow"] == "self-test-report.yml" and e["job"] == "controller")
        self.assertEqual(entry["category"], "control-plane")

    def test_old_daily_missing_and_direct_writer_are_not_reachable(self):
        self.assertNotIn("scripts/ci/self_test_report.py", self.source)
        self.assertNotIn("missing --date", self.source)
        self.assertNotIn("\\n  report:\\n", self.source)
        self.assertIn("'report-legacy': 'legacy'", self.job)
        self.assertIn("scripts/ci/report_runtime.py", self.job)

    def test_workflow_is_a_registered_ci_contract_path(self):
        policy = json.loads(SCOPE_POLICY.read_text())
        rule = next(r for r in policy["rules"]
                    if r["match"] == {"kind": "exact", "value": ".github/workflows/self-test-report.yml"})
        self.assertEqual(rule["lanes"], ["ci_contract"])

    def test_historical_reader_retains_exact_artifact_identity(self):
        source = SCRIPT.read_text()
        assignment = next(node for node in ast.parse(source).body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "VERDICT_ARTIFACT" for target in node.targets))
        self.assertIn("self-test-verdict-", ast.literal_eval(assignment.value.args[0]))


if __name__ == "__main__":
    unittest.main()
