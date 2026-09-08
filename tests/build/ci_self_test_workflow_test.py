#!/usr/bin/env python3
"""Contract tests for the self-test batch wired into Core CI (plan T2).

A self-test batch is a schedule or an operator `workflow_dispatch` with no lane
selection. Queue dispatch admission is retired. Change Scope resolves its target
first, every formal workload checks out that target rather than the ref's
tip, the two Nightly stress suites run inside the batch, and one verdict job
judges the whole batch under scripts/ci/self_test_policy.json. These tests
pin the wiring so the policy, the workflow and the verdict step cannot drift
apart silently.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/build"))
from workflow_inventory import jobs_in  # noqa: E402

CI = ROOT / ".github/workflows/ci.yml"
NIGHTLY = ROOT / ".github/workflows/core-nightly.yml"
PORTAL = ROOT / ".github/workflows/architecture-portal.yml"
POLICY = ROOT / "scripts/ci/self_test_policy.json"

TARGET_REF = (
    "ref: ${{ needs.change-scope.outputs.self-test == 'true' "
    "&& needs.change-scope.outputs.self-test-target || '' }}"
)
#: Policy jobs run by a reusable-workflow caller job in ci.yml.
ALIASES = {"core-tsan": "nightly-tsan", "core-stress": "nightly-stress"}
#: ci.yml jobs whose checkout must follow the batch target. Every policy job
#: that is a real workload, plus the Mac fallback, which runs the same gates.
#: The two Mac adjudicators and the hosted control plane check out the
#: control revision on purpose: they run scripts, not the product.
ADJUDICATORS = {"core-macos", "core-asan-macos"}
CONTROL_PLANE = {"select-macos-runner"}


def job_body(source: str, job_id: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job_id)}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)", source)
    assert match is not None, f"why: ci.yml has no {job_id} job; remedy: define it"
    return match.group("body")


def job_needs(body: str) -> list[str]:
    inline = re.search(r"^    needs: \[(?P<list>[^\]]*)\]", body, re.M)
    if inline:
        return [item.strip() for item in inline.group("list").split(",") if item.strip()]
    single = re.search(r"^    needs: (?P<one>[a-z][a-z0-9-]*)\s*$", body, re.M)
    if single:
        return [single.group("one")]
    return []


class SelfTestBatchWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ci = CI.read_text(encoding="utf-8")
        cls.nightly = NIGHTLY.read_text(encoding="utf-8")
        cls.portal = PORTAL.read_text(encoding="utf-8")
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))
        cls.ci_job_ids = {job.job_id for job in jobs_in(CI)}

    # -- dispatch surface -------------------------------------------------

    def test_operator_dispatch_can_name_a_target_and_a_request_kind(self):
        events = self.ci.split("\npermissions:", 1)[0]
        self.assertIn("  workflow_call:", events)
        self.assertNotIn("  workflow_dispatch:", events)
        self.assertNotIn("  schedule:", events)

    def test_run_name_shows_a_targeted_self_test(self):
        self.assertIn("run-name: Core CI / admitted batch", self.ci)

    def test_change_scope_resolves_the_target_before_classifying(self):
        body = job_body(self.ci, "change-scope")
        self.assertIn("batch_execution.py prepare", body)
        self.assertIn("batch.make_request", (ROOT / "scripts/ci/batch_runtime.py").read_text())
        for key, output in (("self-test", "fixed-target"), ("self-test-target", "target"), ("self-test-action", "action")):
            self.assertIn(f"{key}: ${{{{ steps.batch.outputs.{output} }}}}", body)

    def test_self_test_batch_condition_is_schedule_or_empty_dispatch(self):
        body = job_body(self.ci, "change-scope")
        self.assertNotIn("self_test.py resolve", body)
        self.assertIn("batch = True", body)

    def test_scope_artifacts_are_named_after_the_target(self):
        self.assertIn("artifact=batch-verdict-", self.ci)
        self.assertIn("name: package-evidence-", self.ci)

    def workload_jobs(self) -> set[str]:
        jobs = set()
        for suite in self.policy["suites"]:
            for job in suite["jobs"]:
                if job in ALIASES or job in ADJUDICATORS or job in CONTROL_PLANE:
                    continue
                jobs.add(job)
            for alternatives in suite.get("alternatives", {}).values():
                jobs.update(alternatives)
        return jobs

    def test_every_workload_job_checks_out_the_batch_target(self) -> None:
        for job_id in sorted(self.workload_jobs()):
            with self.subTest(job=job_id):
                body = job_body(self.ci, job_id)
                if "uses: ./.github/workflows/" in body:
                    self.assertIn("checkout_ref: ${{ needs.change-scope.outputs.self-test == 'true'", body,
                                  f"why: {job_id} is a reusable-workflow call and cannot set ref itself; "
                                  "remedy: pass checkout_ref")
                    continue
                self.assertIn(TARGET_REF, body,
                              f"why: {job_id} would test the ref's tip while the batch claims the target; "
                              "remedy: add the target ref to its checkout")
                self.assertIn("change-scope", job_needs(body),
                              f"why: {job_id} reads change-scope outputs; remedy: list it in needs")

    def test_adjudicators_and_control_plane_check_out_the_control_revision(self) -> None:
        for job_id in sorted(ADJUDICATORS | CONTROL_PLANE | {"pre-heavy-gate", "batch-verdict"}):
            with self.subTest(job=job_id):
                self.assertNotIn(TARGET_REF, job_body(self.ci, job_id),
                                 f"why: {job_id} runs the control revision's scripts, not the product; "
                                 "remedy: leave its checkout on github.sha")

    def test_portal_reusable_workflow_takes_the_checkout_ref(self) -> None:
        self.assertIn("      checkout_ref:\n", self.portal)
        self.assertIn("ref: ${{ inputs.checkout_ref || '' }}", self.portal)
        self.assertIn("checkout_ref: ${{ needs.change-scope.outputs.self-test == 'true' && needs.change-scope.outputs.self-test-target || '' }}",
                      job_body(self.ci, "portal"))

    # -- nightly suites inside the batch ----------------------------------

    def test_core_nightly_is_callable_per_suite_without_duplicate_cron(self) -> None:
        self.assertIn("  workflow_call:\n", self.nightly)
        self.assertNotRegex(self.nightly, r'(?m)^  schedule:',
                            "why: stress runs in the daily complete batch; remedy: remove duplicate Nightly cron")
        for suite in ("tsan", "stress"):
            self.assertIn(f"inputs.suite == '{suite}'", self.nightly)
        self.assertEqual(self.nightly.count("ref: ${{ inputs.target_revision || '' }}"), 2,
                         "why: both stress jobs must check out the caller's target; remedy: set ref on both")
        self.assertNotIn("\nconcurrency:\n", self.nightly.split("\njobs:\n", 1)[0],
                         "why: workflow-level concurrency is not honoured for a called workflow; the jobs "
                         "carry the native-heavy queue themselves; remedy: keep it at job level only")

    def test_nightly_callers_pass_the_target_and_gate_on_admission(self) -> None:
        for job_id, suite in (("nightly-tsan", "tsan"), ("nightly-stress", "stress")):
            with self.subTest(job=job_id):
                body = job_body(self.ci, job_id)
                self.assertIn("uses: ./.github/workflows/core-nightly.yml", body)
                self.assertIn(f"suite: {suite}", body)
                self.assertIn("target_revision: ${{ needs.change-scope.outputs.self-test-target }}", body)
                self.assertIn("needs.change-scope.outputs.self-test-action == 'run'", body)
                self.assertIn("needs.change-scope.outputs.self-test == 'true' || needs.pre-heavy-gate.result == 'success'", body)
                self.assertIn("needs.change-scope.outputs.trusted-head == 'true'", body)

    # -- the verdict job ---------------------------------------------------

    def test_verdict_job_needs_every_policy_job(self) -> None:
        body = job_body(self.ci, "batch-verdict")
        needs = set(job_needs(body))
        for suite in self.policy["suites"]:
            for job in suite["jobs"]:
                with self.subTest(job=job):
                    self.assertIn(ALIASES.get(job, job), needs,
                                  f"why: a policy job absent from the verdict's needs is always 'missing'; "
                                  f"remedy: add {ALIASES.get(job, job)} to self-test-verdict needs")
            for alternatives in suite.get("alternatives", {}).values():
                for alt in alternatives:
                    self.assertIn(alt, needs)
        self.assertIn("change-scope", needs)
        self.assertNotIn("pre-heavy-gate", needs)
        self.assertIn("if: ${{ always() && needs.change-scope.outputs.batch-mode == 'true' && needs.change-scope.outputs.batch-execution != '' }}", body)
        self.assertIn("runs-on: ubuntu-24.04", body)

    def test_verdict_aliases_and_dependencies_mirror_the_needs_graph(self):
        body = job_body(self.ci, "batch-verdict")
        self.assertIn("batch_execution.from_needs", body)
        self.assertIn("\'core-tsan\': \'nightly-tsan\'", body)
        self.assertIn("\'core-stress\': \'nightly-stress\'", body)

    def test_verdict_retains_a_record_for_run_and_skip_alike(self):
        body = job_body(self.ci, "batch-verdict")
        for name in ("execution.json", "needs.json", "verdict.json"):
            self.assertIn(name, body)
        self.assertIn("retention-days: 30", body)
        self.assertIn("if-no-files-found: error", body)
        self.assertNotIn("overwrite: true", body)

    def test_explicit_requests_have_run_scoped_concurrency(self) -> None:
        self.assertIn("format('core-ci-self-test-{0}', github.run_id)", self.ci.split("\njobs:\n")[0])

    def test_history_lookup_is_bounded_and_only_runs_for_schedule(self):
        self.assertNotIn("self_test_history.py", self.ci)
        self.assertNotIn("self_test.py resolve", self.ci)

    def test_retired_reviews_are_absent_from_product_self_tests(self) -> None:
        for name in ("select-review-backend", "advisory-review", "grok-review"):
            self.assertNotIn(f"  {name}:\n", self.ci,
                             "why: retired review still requires product permissions; remedy: keep review in pr-review.yml")
        events = self.ci.split('\npermissions:', 1)[0]
        self.assertNotRegex(events, r'(?m)^  (?:pull_request|pull_request_target|push):')

    def test_both_entry_and_verdict_reject_inherited_attempt_results(self):
        self.assertIn("os.environ['GITHUB_RUN_ATTEMPT'] != '1'", job_body(self.ci, "change-scope"))
        self.assertIn("batch_execution.from_needs", job_body(self.ci, "batch-verdict"))

    def test_self_tests_continue_independent_heavy_suites_after_prior_failure(self) -> None:
        for job in ('portal', 'core-ubuntu', 'core-asan', 'core-coverage', 'package', 'nightly-tsan', 'nightly-stress'):
            body = job_body(self.ci, job)
            condition = body.split('    if: >-\n', 1)[1].split('      }}', 1)[0]
            for line in condition.splitlines():
                if '.result ==' in line:
                    self.assertIn("needs.change-scope.outputs.self-test == 'true' ||", line, (job, line))

    def test_every_target_checkout_checks_actual_head(self) -> None:
        for job in self.workload_jobs():
            body = job_body(self.ci, job)
            if 'uses: ./.github/workflows/' not in body:
                self.assertIn('git rev-parse HEAD', body)
        self.assertIn('git rev-parse HEAD', self.portal)
        self.assertEqual(self.nightly.count('git rev-parse HEAD'), 2)



if __name__ == "__main__":
    unittest.main()
