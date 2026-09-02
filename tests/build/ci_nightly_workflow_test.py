#!/usr/bin/env python3
"""Contract tests for trusted Core Nightly runner routing."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/core-nightly.yml"
CORE_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-core]"
)
TSAN_COMMANDS = (
    "python3 tests/fixtures/audio/make_fixtures.py",
    "python3 tests/fixtures/golden/reference_render.py",
    "bash scripts/verify-core-dependencies.sh",
    "scripts/core.sh configure tsan",
    "scripts/core.sh build tsan",
    "scripts/core.sh test tsan stress",
)


class CoreNightlyWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def job(self, job_name: str) -> str:
        match = re.search(
            rf"^  {re.escape(job_name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:|\Z)",
            self.source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(
            match,
            "why: the Nightly routing contract cannot inspect the missing "
            f"{job_name} job; remedy: define {job_name} in core-nightly.yml",
        )
        assert match is not None
        return match.group("body")

    def test_release_stress_uses_the_native_core_role(self) -> None:
        stress = self.job("core-stress")
        message = (
            "why: trusted Release stress must queue on the native Core role "
            "instead of consuming Hosted Ubuntu; remedy: route core-stress "
            f"with {CORE_ROLE} and retain the bounded repeat command"
        )
        self.assertIn(CORE_ROLE, stress, message)
        self.assertNotIn("runs-on: ubuntu-24.04", stress, message)
        self.assertIn("--repeat until-fail:20", stress, message)

    def test_scheduled_tsan_stays_hosted_until_probe_acceptance(self) -> None:
        tsan = self.job("core-tsan")
        message = (
            "why: scheduled TSan has no accepted Contabo runtime evidence; "
            "remedy: keep core-tsan on ubuntu-24.04 until the explicit "
            "same-revision ci-core probe succeeds"
        )
        self.assertIn("runs-on: ubuntu-24.04", tsan, message)
        self.assertNotIn("ci-core", tsan, message)
        for command in TSAN_COMMANDS:
            self.assertIn(command, tsan, message)

    def test_manual_tsan_probe_is_explicit_and_uses_the_core_role(self) -> None:
        probe_input = re.search(
            r"^  workflow_dispatch:\n(?P<body>.*?)(?=^  schedule:)",
            self.source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(
            probe_input,
            "why: TSan compatibility must require an explicit manual dispatch; "
            "remedy: declare workflow_dispatch inputs before the schedule",
        )
        assert probe_input is not None
        message = (
            "why: an implicit TSan probe would spend ci-core capacity on every "
            "schedule; remedy: add a false-by-default boolean "
            "probe_self_hosted_tsan dispatch input"
        )
        self.assertIn("probe_self_hosted_tsan:", probe_input.group("body"), message)
        self.assertIn("type: boolean", probe_input.group("body"), message)
        self.assertIn("default: false", probe_input.group("body"), message)

        probe = self.job("core-tsan-self-hosted-probe")
        self.assertIn(
            "github.event_name == 'workflow_dispatch' && inputs.probe_self_hosted_tsan",
            probe,
            message,
        )
        self.assertIn(CORE_ROLE, probe, message)
        self.assertIn("timeout-minutes: 30", probe, message)

    def test_hosted_and_self_hosted_tsan_run_the_same_commands(self) -> None:
        hosted = self.job("core-tsan")
        probe = self.job("core-tsan-self-hosted-probe")
        message = (
            "why: a probe with different commands cannot establish runner "
            "compatibility for scheduled TSan; remedy: keep the fixture, "
            "dependency, configure, build and stress commands identical"
        )
        for command in TSAN_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, hosted, message)
                self.assertIn(command, probe, message)

    def test_nightly_keeps_read_only_repository_permission(self) -> None:
        prefix = self.source.split("jobs:", 1)[0]
        message = (
            "why: Nightly build and compatibility jobs require no repository "
            "mutation; remedy: retain top-level contents: read and remove any "
            "contents: write permission"
        )
        self.assertIn("permissions:\n  contents: read", prefix, message)
        self.assertNotIn("contents: write", self.source, message)


if __name__ == "__main__":
    unittest.main()
