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

    def test_both_tsan_lanes_compile_with_the_pinned_clang(self) -> None:
        """TSan is the reason the Core pin exists, so both lanes must use it.

        GCC 13.3's libtsan refuses to initialise under the 6.8 kernel's 32-bit
        `vm.mmap_rnd_bits` (`FATAL: ThreadSanitizer: unexpected memory
        mapping`, #676). A TSan lane that inherits the platform default
        compiler therefore measures GCC's runtime, not the pinned one, and a
        probe compiled differently from the scheduled lane proves nothing
        about it. The pin is set at configure time; build and test inherit the
        cached compiler.
        """
        for job_name in ("core-tsan", "core-tsan-self-hosted-probe"):
            with self.subTest(job=job_name):
                body = self.job(job_name)
                self.assertIn(
                    "env CC=clang-22 CXX=clang++-22 scripts/core.sh configure tsan",
                    body,
                    msg=(
                        f"why: {job_name} would otherwise configure TSan with "
                        "GCC's libtsan, whose runtime cannot start under "
                        "32-bit mmap_rnd_bits; remedy: keep the CC/CXX pin on "
                        "the configure step of both TSan lanes"
                    ),
                )
                self.assertIn("command -v clang-22", body)
                self.assertIn("command -v clang++-22", body)

    def test_only_the_hosted_tsan_lane_installs_the_toolchain(self) -> None:
        """The Hosted image lacks the pin; the self-hosted host already has it.

        Installing on the role would mutate state that two runner services
        share, the same reason Coverage installs nothing there.
        """
        hosted = self.job("core-tsan")
        probe = self.job("core-tsan-self-hosted-probe")
        install = "sudo bash scripts/ci/host/install-llvm-toolchain.sh 22"
        self.assertIn(
            install,
            hosted,
            msg=(
                "why: ubuntu-24.04 ships clang-18 and GCC 13, so without the "
                "install step the hosted TSan lane cannot honour the clang-22 "
                "pin; remedy: keep the install-llvm-toolchain.sh step before "
                "the toolchain verification"
            ),
        )
        self.assertNotIn(
            install,
            probe,
            msg=(
                "why: the ci-core host is provisioned once by the operator and "
                "shared by two runner services, so a per-job install would "
                "mutate shared machine state; remedy: verify the toolchain "
                "with command -v and install nothing in the probe"
            ),
        )
        self.assertNotIn("apt-get", probe)

    def test_both_native_jobs_share_the_repository_capacity_queue(self) -> None:
        """Naming the `ci-core` role is not enough to make them run one at a time.

        The role spans two runner services on one physical host, so without the
        capacity queue a dispatched probe and the release stress suite start in
        the same second and run beside each other. Both are timing-sensitive,
        and twenty consecutive stress repetitions are the least tolerant
        workload in the repository.

        Observed: run 33838737018 started `core-tsan-self-hosted-probe` and
        `core-stress` at 04:58:05Z on `contabo-lmdj-linux` and
        `contabo-lmdj-linux-02`, and both failed. The probe's failure said
        nothing about whether the host can execute the TSan runtime, which is
        the only question it exists to answer.
        """
        for job_name in ("core-tsan-self-hosted-probe", "core-stress"):
            with self.subTest(job=job_name):
                self.assertRegex(
                    self.job(job_name),
                    r"(?m)^    concurrency:\n"
                    r"      group: lmdj-native-heavy\n"
                    r"      queue: max\n"
                    r"      cancel-in-progress: false$",
                    msg=(
                        f"why: {job_name} names the ci-core role, which spans two "
                        "runner services on one host, so a sibling native job "
                        "runs beside it rather than after it and consumes the "
                        "CPU its timing-sensitive tests were budgeted for; "
                        "remedy: keep the lmdj-native-heavy block with queue: "
                        "max before cancel-in-progress: false, the same one "
                        "ci.yml puts on every admitted shared-host lane"
                    ),
                )

    def test_the_hosted_tsan_lane_does_not_join_the_queue(self) -> None:
        """It runs on a different machine, so it contends for nothing."""
        self.assertNotIn(
            "lmdj-native-heavy",
            self.job("core-tsan"),
            msg=(
                "why: core-tsan runs on GitHub-hosted Ubuntu, a different "
                "machine from the shared Contabo host, so joining the "
                "lmdj-native-heavy queue would only make it wait behind "
                "native lanes it cannot contend with; remedy: keep the "
                "core-tsan job body free of the lmdj-native-heavy "
                "concurrency block"
            ),
        )

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
