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

    def test_scheduled_tsan_runs_on_the_core_role(self) -> None:
        """Routing was accepted on same-revision evidence, and stays pinned.

        #693: the host caps `vm.mmap_rnd_bits` at 28, and the probe on
        netcup passed at that state. Without the cap no TSan runtime starts
        there, so the routing and the prerequisite check travel together.
        """
        tsan = self.job("core-tsan")
        message = (
            "why: scheduled TSan is trusted native Core workload since #693 "
            "and Hosted Ubuntu would bill 25-35 minutes a day for it; remedy: "
            f"route core-tsan with {CORE_ROLE} and keep the stress command"
        )
        self.assertIn(CORE_ROLE, tsan, message)
        self.assertNotIn("runs-on: ubuntu-24.04", tsan, message)
        for command in TSAN_COMMANDS:
            self.assertIn(command, tsan, message)

    def test_scheduled_tsan_verifies_the_host_prerequisite_first(self) -> None:
        """A host that loses the ASLR cap must fail naming the remedy.

        Under 32-bit entropy GCC's libtsan and LLVM 22's runtime die with a
        FATAL and clang-18's shared runtime dies with no output at all
        (`sanitizer-runtime-silent-start-failure`). The preflight turns all
        three into one readable failure before a TSan binary runs.
        """
        tsan = self.job("core-tsan")
        self.assertIn("name: Verify the TSan host prerequisite", tsan)
        self.assertIn('bits="$(sysctl -n vm.mmap_rnd_bits)"', tsan)
        self.assertIn('if [ "$bits" -gt 28 ]; then', tsan)
        self.assertIn("configure-sanitizer-aslr.sh", tsan)
        self.assertIn("why:", tsan)
        self.assertIn("remedy:", tsan)
        prerequisite = tsan.index("Verify the TSan host prerequisite")
        configure = tsan.index("scripts/core.sh configure tsan")
        self.assertLess(
            prerequisite,
            configure,
            msg=(
                "why: a prerequisite checked after the TSan build would let a "
                "runtime FATAL or a silent death report first; remedy: keep the "
                "sysctl check before the configure step"
            ),
        )

    def test_no_hosted_tsan_lane_or_probe_remains(self) -> None:
        """The probe answered its question; a second TSan lane would only drift."""
        self.assertNotIn("core-tsan-self-hosted-probe", self.source)
        self.assertNotIn("probe_self_hosted_tsan", self.source)
        self.assertNotIn(
            "runs-on: ubuntu-24.04",
            self.job("core-tsan"),
            msg=(
                "why: a Hosted TSan lane beside the ci-core one would measure "
                "a different kernel and bill Hosted minutes for a question the "
                "role already answers; remedy: keep core-tsan on ci-core only"
            ),
        )

    def test_tsan_compiles_with_the_pinned_clang(self) -> None:
        """TSan is the reason the Core pin exists, so the lane must use it.

        GCC 13.3's libtsan gives a less useful failure than LLVM 22's when
        the host regresses, and the pin is what the coverage lane and the
        host inventory verify. The pin is set at configure time; build and
        test inherit the cached compiler.
        """
        body = self.job("core-tsan")
        self.assertIn(
            "env CC=clang-22 CXX=clang++-22 scripts/core.sh configure tsan",
            body,
            msg=(
                "why: core-tsan would otherwise configure TSan with the "
                "platform default GCC rather than the pinned toolchain; "
                "remedy: keep the CC/CXX pin on the configure step"
            ),
        )
        self.assertIn("command -v clang-22", body)
        self.assertIn("command -v clang++-22", body)
        self.assertNotIn(
            "apt-get",
            body,
            msg=(
                "why: the ci-core host is provisioned once by the operator and "
                "shared by several runner services, so a per-job install would "
                "mutate shared machine state; remedy: verify with command -v "
                "and install nothing"
            ),
        )

    def test_both_native_jobs_share_the_repository_capacity_queue(self) -> None:
        """Naming the `ci-core` role is not enough to make them run one at a time.

        The role spans two runner services on one physical host, so without the
        capacity queue a dispatched probe and the release stress suite start in
        the same second and run beside each other. Both are timing-sensitive,
        and twenty consecutive stress repetitions are the least tolerant
        workload in the repository.

        Observed: run 33838737018 started the TSan probe (then
        `core-tsan-self-hosted-probe`) and
        `core-stress` at 04:58:05Z on `contabo-lmdj-linux` and
        `contabo-lmdj-linux-02`, and both failed. The probe's failure said
        nothing about whether the host can execute the TSan runtime, which is
        the only question it exists to answer.
        """
        for job_name in ("core-tsan", "core-stress"):
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
