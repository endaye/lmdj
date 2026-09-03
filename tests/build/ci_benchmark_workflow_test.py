#!/usr/bin/env python3
"""Contract tests for the non-authoritative self-hosted host benchmarks."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from workflow_inventory import WORKFLOW_DIR, jobs_in


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / ".github/workflows/ci-self-hosted-benchmark.yml"
CORE_BENCHMARK = REPO_ROOT / ".github/workflows/ci-self-hosted-core-benchmark.yml"
FORMAL = REPO_ROOT / ".github/workflows/ci.yml"
ACTION = REPO_ROOT / ".github/actions/web-ci-proof/action.yml"
CONTABO = REPO_ROOT / "scripts/ci/elastic-runner/contabo.json"

CORE_ROLE = "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-core]"


def core_role_job_names(workflow: Path) -> list[str]:
    """Display names of every job in `workflow` that names the `ci-core` role."""
    return [job.display_name for job in jobs_in(workflow) if job.has_role("ci-core")]


# Lane -> the script commands the formal ci.yml job runs for it. The benchmark
# measures the same workload or the number it reports describes nothing.
CORE_LANE_COMMANDS = {
    "core_ubuntu": ("scripts/core.sh proof",),
    "package": ("scripts/core.sh package",),
    "core_coverage": ("scripts/core-coverage.sh check",),
    "core_asan": (
        "scripts/core.sh configure asan",
        "scripts/core.sh build asan",
        "scripts/core.sh test asan full",
        "scripts/core.sh test asan stress",
    ),
}


class CiBenchmarkWorkflowTest(unittest.TestCase):
    def test_benchmark_is_dispatch_only_and_non_authoritative(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertNotRegex(source, r"(?m)^  (?:pull_request|push|schedule):")
        self.assertIn("permissions:\n  contents: read", source)
        self.assertNotIn("PR Gate", source)
        self.assertNotIn("pr_gate.py", source)

    def test_benchmark_targets_only_the_web_role(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        self.assertIn(
            "runs-on: [self-hosted, Linux, X64, lmdj-linux, "
            "lmdj-linux-pool, ci-web-heavy]",
            source,
        )
        for lane in ("web_toolchain", "web_runtime_host", "creator"):
            self.assertIn(f"- {lane}", source)

    def test_benchmark_revision_is_the_dispatched_trusted_sha(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        self.assertIn('[[ "$REVISION" =~ ^[0-9a-f]{40}$ ]]', source)
        self.assertIn('[[ "$REVISION" == "$TRUSTED_SHA" ]]', source)
        self.assertIn("TRUSTED_SHA: ${{ github.sha }}", source)

    def test_formal_and_benchmark_workflows_share_one_proof_action(self) -> None:
        formal = FORMAL.read_text(encoding="utf-8")
        benchmark = BENCHMARK.read_text(encoding="utf-8")
        for source in (formal, benchmark):
            self.assertIn("uses: ./.github/actions/web-ci-proof", source)

    def test_persistent_emsdk_install_is_serialized_atomic_and_group_readable(self) -> None:
        source = ACTION.read_text(encoding="utf-8")
        self.assertIn('flock 9', source)
        self.assertIn("for slot in {1..32}; do", source)
        self.assertIn("(umask 0007; mkdir \"$candidate\")", source)
        self.assertIn('[[ -n "$temporary" ]]', source)
        self.assertNotIn('mktemp -d "$cache_root/.install-', source)
        self.assertNotIn('chmod 0770 "$temporary"', source)
        self.assertNotIn('chmod 2770 "$temporary"', source)
        self.assertIn('mv "$temporary" "$target"', source)

    def test_persistent_emsdk_trusts_only_the_exact_shared_git_checkout(self) -> None:
        source = ACTION.read_text(encoding="utf-8")
        self.assertIn("echo 'GIT_CONFIG_COUNT=1' >>\"$GITHUB_ENV\"", source)
        self.assertIn(
            "echo 'GIT_CONFIG_KEY_0=safe.directory' >>\"$GITHUB_ENV\"",
            source,
        )
        self.assertIn(
            "printf 'GIT_CONFIG_VALUE_0=%s\\n' \"$target\" >>\"$GITHUB_ENV\"",
            source,
        )
        self.assertNotIn("safe.directory=*", source)


class CiCoreBenchmarkWorkflowTest(unittest.TestCase):
    """The `ci-core` counterpart of the Web benchmark.

    The native-heavy chain owns the longest phase wall clock in Core CI, so a
    host-migration decision needs same-revision timings from both hosts. These
    tests hold the measurement to the same non-authoritative, trusted-revision
    contract as the Web benchmark, and additionally to the two properties the
    Web benchmark does not need: shared-host capacity admission and workload
    parity with the formal lanes.
    """

    def setUp(self) -> None:
        self.source = CORE_BENCHMARK.read_text(encoding="utf-8")
        # The absence assertions below are about what the workflow *does*, so
        # they read the directives only. A rationale comment is free to name
        # `PR Gate` or the Web role it contrasts with.
        self.directives = "\n".join(
            line
            for line in self.source.splitlines()
            if not line.lstrip().startswith("#")
        )

    def test_core_benchmark_is_dispatch_only_and_non_authoritative(self) -> None:
        self.assertIn("workflow_dispatch:", self.source)
        self.assertNotRegex(self.source, r"(?m)^  (?:pull_request|push|schedule):")
        self.assertIn("permissions:\n  contents: read", self.source)
        self.assertNotIn("PR Gate", self.directives)
        self.assertNotIn("pr_gate.py", self.directives)
        self.assertNotIn("change_scope.py", self.directives)

    def test_core_benchmark_targets_only_the_native_core_role(self) -> None:
        self.assertIn(CORE_ROLE, self.source)
        self.assertNotIn("ci-web-heavy", self.directives)
        self.assertNotIn("ci-general", self.directives)
        for lane in CORE_LANE_COMMANDS:
            with self.subTest(lane=lane):
                self.assertIn(f"          - {lane}\n", self.source)

    def test_core_benchmark_revision_is_the_dispatched_trusted_sha(self) -> None:
        self.assertIn('[[ "$REVISION" =~ ^[0-9a-f]{40}$ ]]', self.source)
        self.assertIn('[[ "$REVISION" == "$TRUSTED_SHA" ]]', self.source)
        self.assertIn("TRUSTED_SHA: ${{ github.sha }}", self.source)

    def test_core_benchmark_joins_the_shared_host_capacity_queue(self) -> None:
        """Separate runner services on one host are not independent capacity.

        A benchmark outside `lmdj-native-heavy` would land on the sibling
        `ci-core` service while a formal lane runs, corrupting its own
        measurement and consuming that lane's test budgets.
        """
        self.assertRegex(
            self.source,
            r"(?m)^    concurrency:\n"
            r"      group: lmdj-native-heavy\n"
            r"      queue: max\n"
            r"      cancel-in-progress: false$",
            msg=(
                "why: a benchmark on the shared Contabo host contends with formal "
                "native Core work; remedy: keep queue: max before "
                "cancel-in-progress: false on the benchmark job"
            ),
        )

    def test_elastic_controller_classifies_the_benchmark_as_core_work(self) -> None:
        """The job name and `core_job_names` are one vocabulary in two files.

        `_current_job_is_core` prefix-matches the listener's job name against
        this list. An unregistered name classifies as non-core, so the
        controller would keep scaling elastic services out while a
        timing-sensitive Core measurement is running.
        """
        name_match = re.search(r"(?m)^    name: (.+)$", self.source)
        assert name_match is not None, "the benchmark job must declare a name"
        job_name = name_match.group(1)
        self.assertTrue(
            job_name.startswith("Core benchmark"),
            f"unexpected benchmark job name: {job_name}",
        )
        registered = json.loads(CONTABO.read_text(encoding="utf-8"))["core_job_names"]
        self.assertTrue(
            any(job_name.startswith(entry) for entry in registered),
            "why: the elastic controller prefix-matches the running job name "
            f"against core_job_names; remedy: register a prefix of {job_name!r} "
            f"in scripts/ci/elastic-runner/contabo.json, which currently has "
            f"{registered}",
        )

    def test_every_ci_core_job_is_registered_with_the_elastic_controller(self) -> None:
        """The registration trap generalizes past this benchmark.

        `core_job_names` is only validated for non-emptiness, so any new
        `ci-core` job whose name is unregistered silently classifies as
        non-core and the controller keeps admitting elastic load beneath it.
        This enumerates the role's real job set instead of trusting a
        hand-maintained list to stay complete.
        """
        registered = json.loads(CONTABO.read_text(encoding="utf-8"))["core_job_names"]
        found = {
            workflow.name: core_role_job_names(workflow)
            for workflow in sorted(WORKFLOW_DIR.glob("*.yml"))
        }
        self.assertTrue(
            any(found.values()), "the ci-core role scan found no jobs at all"
        )
        for workflow_name, job_names in found.items():
            for job_name in job_names:
                with self.subTest(workflow=workflow_name, job=job_name):
                    self.assertTrue(
                        any(job_name.startswith(entry) for entry in registered),
                        "why: the elastic controller prefix-matches the running "
                        f"job name, so unregistered {job_name!r} in "
                        f"{workflow_name} classifies as non-core and scale-out "
                        "continues under timing-sensitive Core work; remedy: add "
                        "a prefix of it to core_job_names in "
                        f"scripts/ci/elastic-runner/contabo.json, which has "
                        f"{registered}",
                    )

    def test_core_benchmark_runs_the_formal_lane_workload(self) -> None:
        """A benchmark that runs different commands measures a different thing."""
        formal = FORMAL.read_text(encoding="utf-8")
        for lane, commands in CORE_LANE_COMMANDS.items():
            for command in commands:
                with self.subTest(lane=lane, command=command):
                    self.assertIn(command, formal)
                    self.assertIn(command, self.source)

    def test_core_benchmark_records_the_evidence_a_comparison_needs(self) -> None:
        for field in (
            "runner_name=%s",
            "elapsed_seconds=%s",
            "cpu_count=%s",
            "use_ccache=%s",
            "parallel_level=%s",
        ):
            with self.subTest(field=field):
                self.assertIn(field, self.source)

    def test_core_benchmark_keeps_the_formal_cache_and_parallelism_defaults(self) -> None:
        """Deviating from the formal settings must be an explicit dispatch choice.

        `package` bypasses the persistent ccache in ci.yml, and every CI CMake
        build is capped at three parallel jobs, so `lane-default` and `3` are
        the only settings whose timings compare with a formal lane run.
        """
        self.assertIn("default: lane-default", self.source)
        self.assertIn('default: "3"', self.source)
        self.assertIn('[[ "$CACHE_MODE" == "cold" || "$LANE" == "package" ]]', self.source)


if __name__ == "__main__":
    unittest.main()
