#!/usr/bin/env python3
"""Every GitHub-hosted job is a recorded spending decision.

Self-hosted minutes cost nothing; hosted minutes are metered, and GitHub bills
each job rounded up to a whole minute, so on hosted runners job *count* costs
more than job duration. A fan-out of short hosted jobs is the most expensive
possible shape, and it is also the easiest one to arrive at by accident: adding
`runs-on: ubuntu-24.04` is the path of least resistance.

`docs/quality/core-test-policy.md` already states which jobs may run hosted and
why. Prose drifts — the Merge Queue watchdog ran hosted on a fifteen-minute cron,
consuming the account's whole included allowance, while the policy described a
four-job exception that did not include it. This turns that prose into a list
that cannot drift.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from workflow_inventory import REPO_ROOT, all_jobs


POLICY = REPO_ROOT / "scripts/ci/hosted_runner_policy.json"
POLICY_PATH = "scripts/ci/hosted_runner_policy.json"

# A reason has to survive being read by someone who was not in the room.
MINIMUM_REASON_CHARS = 60


class CiHostedRunnerPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(POLICY.read_text(encoding="utf-8"))
        self.allowed = self.policy["allowed"]
        self.entries = {(e["workflow"], e["job"]): e for e in self.allowed}
        self.hosted = {
            (job.workflow, job.job_id): job
            for job in all_jobs()
            if job.needs_host_justification
        }

    def test_policy_declares_its_schema_and_categories(self) -> None:
        self.assertEqual(self.policy["schema"], "lmdj.hosted-runner-policy.v1")
        self.assertTrue(self.policy["rationale"])
        self.assertTrue(self.policy["categories"])

    def test_every_hosted_job_is_recorded(self) -> None:
        """A job that can consume hosted minutes must say why it may."""
        for key, job in sorted(self.hosted.items()):
            with self.subTest(workflow=job.workflow, job=job.job_id):
                # assertTrue, not assertIn: assertIn would dump the whole
                # allowlist ahead of the message and bury it, which is the
                # failure mode .agents/pitfalls/gate-failure-readability.md
                # records.
                self.assertTrue(
                    key in self.entries,
                    msg=(
                        f"why: {job.workflow} job {job.job_id!r} declares "
                        f"runs-on {job.runs_on!r}, which can resolve to a "
                        "GitHub-hosted runner, and hosted minutes are metered "
                        "while self-hosted minutes are free; every hosted job "
                        "is therefore a spending decision that must be "
                        f"recorded; remedy: either route it to a self-hosted "
                        f"role, or add an entry to {POLICY_PATH} naming a "
                        "category and a reason that would convince a reader "
                        "who was not in the room"
                    ),
                )

    def test_the_allowlist_has_no_stale_entries(self) -> None:
        """A list that outlives its jobs stops describing anything."""
        for key in sorted(self.entries):
            workflow, job_id = key
            with self.subTest(workflow=workflow, job=job_id):
                self.assertTrue(
                    key in self.hosted,
                    msg=(
                        f"why: {POLICY_PATH} still permits {job_id!r} in "
                        f"{workflow} to run hosted, but that job either no "
                        "longer exists or no longer names a hosted runner, so "
                        "the entry records a decision nobody is making; "
                        "remedy: delete the entry in the same change that "
                        "moved or removed the job"
                    ),
                )

    def test_every_entry_carries_a_category_and_a_real_reason(self) -> None:
        categories = set(self.policy["categories"])
        for entry in self.allowed:
            label = f"{entry['workflow']}:{entry['job']}"
            with self.subTest(entry=label):
                self.assertTrue(
                    entry.get("category") in categories,
                    msg=(
                        f"why: {label} names a category outside the declared "
                        f"set {sorted(categories)}, so the reason cannot be "
                        "weighed against a stated bar; remedy: use one of the "
                        f"declared categories in {POLICY_PATH}, or declare a "
                        "new one alongside what it admits"
                    ),
                )
                reason = entry.get("reason", "")
                self.assertGreaterEqual(
                    len(reason),
                    MINIMUM_REASON_CHARS,
                    msg=(
                        f"why: {label} gives a reason of {len(reason)} "
                        f"characters, below the {MINIMUM_REASON_CHARS} needed "
                        "for it to say anything a later reader can act on; "
                        "remedy: state what the job publishes or what authority "
                        "it holds that a self-hosted runner cannot supply"
                    ),
                )

    def test_temporary_entries_name_the_issue_that_removes_them(self) -> None:
        """`temporary` admits a job on borrowed time, so the debt must be addressed.

        Without this, `temporary` becomes the category everything lands in and
        the allowlist reverts to a list of whatever happens to exist.
        """
        for entry in self.allowed:
            if entry.get("category") != "temporary":
                continue
            label = f"{entry['workflow']}:{entry['job']}"
            with self.subTest(entry=label):
                self.assertRegex(
                    entry.get("reason", ""),
                    r"#\d+",
                    msg=(
                        f"why: {label} is admitted as temporary, which is an "
                        "explicit statement that it is not justified on the "
                        "merits; an unowned exemption never expires; remedy: "
                        "name the Issue that removes it, or move it to the "
                        "category that actually justifies it"
                    ),
                )

    def test_the_native_core_role_stays_off_hosted_runners(self) -> None:
        """The heavy lanes are the ones a routing slip would cost the most."""
        for job in all_jobs():
            if not job.has_role("ci-core"):
                continue
            with self.subTest(workflow=job.workflow, job=job.job_id):
                self.assertFalse(
                    job.needs_host_justification,
                    msg=(
                        f"why: {job.workflow} job {job.job_id!r} names the "
                        "ci-core role but its runs-on can reach a hosted "
                        "runner, and these are the longest jobs in the "
                        "repository; remedy: name the self-hosted role "
                        "literally so a busy or absent role queues the job "
                        "instead of buying paid capacity for it"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
