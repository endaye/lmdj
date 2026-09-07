#!/usr/bin/env python3
"""Static contract for the hosted serialized Merge Queue workflow."""

from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/merge-queue.yml"
CORE_WORKFLOW = ROOT / ".github/workflows/ci.yml"


class MergeQueueWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.core_source = CORE_WORKFLOW.read_text(encoding="utf-8")

    def job(self, name):
        match = re.search(
            rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:|\Z)",
            self.source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, f"missing workflow job {name}")
        return match.group("body")

    def test_retired_queue_accepts_no_new_label_or_scheduled_authorization(self):
        event = self.source.split("permissions:", 1)[0]
        self.assertNotIn("synchronize", event)
        self.assertNotIn("closed", event)
        self.assertNotRegex(event, r"(?m)^  (?:pull_request_target|schedule):")
        self.assertIn("accepted=false", self.job("route"))
        self.assertIn("mode=retired", self.job("route"))
        self.assertNotIn("accepted=true", self.job("route"))

    def test_real_retired_router_never_authorizes_even_a_stale_label(self):
        script = textwrap.dedent(self.job("route").split("        run: |\n", 1)[1])
        for event in ("workflow_dispatch", "pull_request_target", "schedule"):
            with self.subTest(event=event), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "output"
                result = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                                        env={**os.environ, "EVENT_NAME": event,
                                             "LABEL_NAME": "merge:queue", "PR_NUMBER": "17",
                                             "EVENT_ACTOR": "owner", "EVENT_HEAD_SHA": "a" * 40,
                                             "GITHUB_OUTPUT": str(output),
                                             "GITHUB_STEP_SUMMARY": str(Path(directory) / "summary")})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("accepted=false", output.read_text())
                self.assertIn("mode=retired", output.read_text())

    def test_exact_route_precedes_job_level_queue_concurrency(self):
        prefix = self.source.split("jobs:", 1)[0]
        self.assertNotIn("concurrency:", prefix)
        self.assertNotIn("concurrency:", self.job("route"))
        queue = self.job("queue-item")
        self.assertIn("needs: route", queue)
        self.assertIn("needs.route.outputs.accepted == 'true'", queue)
        self.assertIn("group: lmdj-merge-main", queue)
        self.assertIn("queue: max", queue)
        self.assertNotIn("cancel-in-progress", queue)

    def test_worker_runs_on_the_trusted_role_bounded_and_from_canonical_code(self):
        """The worker waits; it does not adjudicate, so it does not run hosted.

        `wait_validation` polls for another run to finish, about 33 minutes per
        validation and roughly 43% of the remaining hosted minutes. The hosted
        control-plane exception protects scope, trust, admission and verdict
        evidence; `route` makes the admission decision and keeps that role,
        while this job only carries it out. When every self-hosted runner is
        down the validation it waits for cannot run either, so hosting it buys
        no availability.
        """
        queue = self.job("queue-item")
        self.assertIn(
            "runs-on: [self-hosted, Linux, X64, lmdj-linux, "
            "lmdj-linux-pool, ci-general]",
            queue,
            msg=(
                "why: this job bills roughly 33 minutes of hosted time per "
                "validation to wait for a GitHub run it does not adjudicate; "
                "remedy: keep runs-on naming the ci-general role, and leave "
                "route hosted because that is where the admission decision is"
            ),
        )
        self.assertNotIn("runs-on: ubuntu-24.04", queue)
        self.assertIn("timeout-minutes: 360", queue)
        self.assertIn("uses: actions/checkout@v6", queue)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", queue)
        self.assertIn("persist-credentials: false", queue)
        self.assertIn("python3 scripts/ci/merge_queue.py run", queue)

    def test_worker_has_only_the_declared_token_permissions(self):
        queue = self.job("queue-item")
        for permission in (
            "actions: write", "checks: read", "contents: write", "pull-requests: write"
        ):
            self.assertIn(permission, queue)
        self.assertNotIn("issues:", queue)
        for forbidden in ("deployments:", "id-token:", "packages:", "administration:"):
            self.assertNotIn(forbidden, queue)

    def test_finalizer_and_watchdog_do_not_consume_queue_slots(self):
        finalizer = self.job("finalize")
        watchdog = self.job("watchdog")
        self.assertIn("if: ${{ always()", finalizer)
        self.assertIn("python3 scripts/ci/merge_queue.py finalize", finalizer)
        self.assertIn("continue-on-error: true", finalizer)
        self.assertNotIn("concurrency:", finalizer)
        self.assertIn("if: ${{ github.event_name == 'schedule' }}", watchdog)
        self.assertIn("python3 scripts/ci/merge_queue_watchdog.py", watchdog)
        self.assertNotIn("concurrency:", watchdog)
        self.assertNotRegex(self.source, r"(?m)^\s+- cron:")

    def test_watchdog_reconciles_on_the_trusted_role_not_hosted_minutes(self):
        """A 10-second job on a 15-minute cron is billed as a whole minute each run.

        At roughly 2,880 runs a month that is the account's entire included
        Actions allowance, spent on a reconciler that publishes no scope,
        admission or verdict evidence and so does not qualify for the hosted
        control-plane exception.
        """
        watchdog = self.job("watchdog")
        self.assertIn(
            "runs-on: [self-hosted, Linux, X64, lmdj-linux, "
            "lmdj-linux-pool, ci-general]",
            watchdog,
            msg=(
                "why: the watchdog runs every 15 minutes and GitHub rounds each "
                "job up to a whole minute, so hosting it spends about 2,880 "
                "billed minutes a month on roughly 14 minutes of work, and it "
                "publishes none of the evidence the hosted control-plane "
                "exception exists to protect; remedy: keep runs-on naming the "
                "ci-general role"
            ),
        )
        self.assertNotIn("runs-on: ubuntu-24.04", watchdog)
        self.assertNotRegex(self.source, r"(?m)^\s+- cron:",
                            "why: retired queue must not reconcile new tickets; remedy: keep cron disabled")

    def test_manual_preflight_is_bounded_and_uses_the_same_queue(self):
        self.assertIn("hold_seconds:", self.source)
        queue = self.job("queue-item")
        self.assertIn("needs.route.outputs.mode == 'preflight'", queue)
        self.assertIn("30 <= seconds <= 600", queue)

    def test_reports_are_retained_even_when_the_worker_fails(self):
        queue = self.job("queue-item")
        self.assertIn("uses: actions/upload-artifact@v4", queue)
        self.assertIn("name: merge-queue-report-${{ github.run_id }}", queue)
        self.assertIn("if-no-files-found: warn", queue)
        self.assertIn("retention-days: 14", queue)

    def test_actionlint_schema_lag_has_one_exact_removable_exception(self):
        self.assertIn("ACTIONLINT_VERSION: 1.7.12", self.core_source)
        self.assertIn(
            "ACTIONLINT_SHA256: 8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
            self.core_source,
        )
        self.assertIn(
            "-ignore 'unexpected key \"queue\" for \"concurrency\" section'",
            self.core_source,
        )
        self.assertEqual(self.source.count("queue: max"), 1)
        self.assertIn("rhysd/actionlint/issues/657", self.core_source)

    def test_core_dispatch_declares_and_threads_all_queue_inputs(self):
        for name in (
            "queue_ticket", "queue_pr_number", "queue_base_sha", "queue_head_sha"
        ):
            self.assertIn(f"      {name}:\n", self.core_source)
            self.assertIn(f"--{name.replace('_', '-')} ", self.core_source)
        self.assertIn("queue-validation-${{ github.run_id }}", self.core_source)
        self.assertIn("if: ${{ always() && inputs.queue_ticket != '' }}", self.core_source)
        self.assertIn("queue-mode: ${{ steps.scope.outputs.queue-mode }}", self.core_source)
        self.assertIn("pull-request-body: ${{ steps.scope.outputs.pull-request-body }}", self.core_source)

    def test_queue_exact_range_and_pr_body_feed_docs_portal_and_gate(self):
        self.assertIn("BASE_SHA: ${{ needs.change-scope.outputs.resolved-base-sha }}", self.core_source)
        self.assertIn("HEAD_SHA: ${{ needs.change-scope.outputs.resolved-head-sha }}", self.core_source)
        self.assertIn("pull_request_body: ${{ needs.change-scope.outputs.pull-request-body }}", self.core_source)
        self.assertIn("--queue-ticket \"${{ inputs.queue_ticket }}\"", self.core_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
