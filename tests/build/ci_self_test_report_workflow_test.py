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
import tempfile
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


def wakeup_group(source, event, run_id):
    group = field(block(source, "concurrency", 0), "group", 2)
    prefix, expression = group.split("${{", 1)
    expression = expression.removesuffix("}}").strip()
    expression = expression.replace("github.event_name", repr(event)).replace("github.run_id", str(run_id))
    expression = expression.replace("&&", "and").replace("||", "or")
    # Repository-owned scalar expression, never model text. This models the
    # documented platform key, not actual remote scheduling/locking.
    return prefix + str(eval(expression, {"__builtins__": {}}, {}))


class SelfTestReportWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.source = WORKFLOW.read_text()
        self.job = block(self.source, "controller", 2)

    def wakeup_group(self, event, run_id):
        return wakeup_group(self.source, event, run_id)

    def test_automatic_admission_has_one_replaceable_pending_slot(self):
        admission = block(self.source, "concurrency", 0)
        self.assertEqual(field(admission, "queue", 2), "single",
                         "why: automatic wakeups accumulate as commands; remedy: coalesce only pending automatic observations")
        self.assertEqual(field(admission, "cancel-in-progress", 2), "false",
                         "why: a running batch could be cancelled by a new merge; remedy: retain in-progress work")
        groups = {self.wakeup_group(event, run_id) for event in ("push", "schedule", "workflow_run")
                  for run_id in (101, 102)}
        self.assertEqual(groups, {"self-test-report-wakeup-automatic"})

    def test_each_manual_command_has_an_independent_admission_group(self):
        groups = {self.wakeup_group("workflow_dispatch", run_id) for run_id in range(1, 51)}
        self.assertEqual(len(groups), 50,
                         "why: manual commands may replace each other; remedy: isolate manual admission by immutable run ID")
        self.assertNotIn(self.wakeup_group("push", 99), groups)
        self.assertNotIn("self-test-report", groups)

    def test_automatic_burst_replaces_pending_but_not_running_or_manual(self):
        # Pending cancellation may itself emit relay callbacks on GitHub.
        # This local queue model omits that platform effect; the Task plan
        # retains relay fanout/chain-limit behavior as remote acceptance gaps.
        running, pending = {}, {}
        for event, run_id in [("push", 1)] + [(("push", "workflow_run", "schedule")[n % 3], n)
                                              for n in range(2, 51)] + [
                ("workflow_dispatch", n) for n in range(51, 61)]:
            group = self.wakeup_group(event, run_id)
            if group in running:
                pending[group] = run_id
            else:
                running[group] = run_id
        auto = self.wakeup_group("push", 1)
        self.assertEqual(running[auto], 1)
        self.assertEqual(pending, {auto: 50})
        self.assertTrue(set(range(51, 61)) <= set(running.values()))

    def test_outer_admission_never_owns_the_shared_journal_lock(self):
        for event in ("push", "schedule", "workflow_run", "workflow_dispatch"):
            self.assertNotEqual(self.wakeup_group(event, 101), "self-test-report",
                                "why: product work would hold the journal lock; remedy: keep wakeup admission and short writer groups distinct")
        self.assertNotIn("concurrency:", block(self.source, "execute-batch", 2))

    def test_retained_latest_observation_still_collects_every_commit(self):
        sys.path.insert(0, str(ROOT / "scripts/ci"))
        from test_scope import collect_interval
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.run(["git", "-C", directory, *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "-b", "main")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "commit.gpgsign", "false")
            git("commit", "--allow-empty", "-m", "processed baseline")
            base = git("rev-parse", "HEAD")
            paths = ["first.md", "second.md", "third.md"]
            commits = []
            for path in paths:
                (Path(directory) / path).write_text(path)
                git("add", path)
                git("commit", "-m", path)
                commits.append(git("rev-parse", "HEAD"))
            # The first two wakeups are replaced, not the commits they refer
            # to. Use the real canonical collector with only the last target.
            interval = collect_interval(directory, base, commits[-1])
            self.assertEqual([commit["sha"] for commit in interval["commits"]], commits)
            self.assertEqual(interval["paths"], paths)

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
        # Workflow admission may coalesce redundant automatic observations,
        # but only this short job may hold the shared journal writer group.
        self.assertEqual(scalars(block(self.job, "concurrency", 4), 6),
                         {"group": "self-test-report", "cancel-in-progress": "false", "queue": "max"})
        self.assertEqual([job.job_id for job in jobs_in(WORKFLOW)],
                         ["controller", "cancel-probe-waiter", "execute-batch"])
        policy = json.loads(HOSTED_POLICY.read_text())
        self.assertFalse(any(e["workflow"] == "self-test-report.yml" for e in policy["allowed"]))
        self.assertIn("runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general, contabo]", self.job)

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
