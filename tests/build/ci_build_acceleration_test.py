#!/usr/bin/env python3
"""Contract tests for bounded CI build acceleration and persistent ccache use."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
WEB_PROOF_ACTION = REPO_ROOT / ".github/actions/web-ci-proof/action.yml"
ACCELERATION_ACTION = (
    REPO_ROOT / ".github/actions/configure-build-acceleration/action.yml"
)
MACOS_ACTION = REPO_ROOT / ".github/actions/macos-core-gates/action.yml"
WEB_TOOLCHAIN = REPO_ROOT / "scripts/web-toolchain-conformance.sh"
WEB_HOST = REPO_ROOT / "scripts/web-runtime-host.sh"
GITIGNORE = REPO_ROOT / ".gitignore"
LOCAL_LANES = REPO_ROOT / "scripts/ci/local_lanes.json"
WORKFLOW_ROOT = REPO_ROOT / ".github/workflows"
ACTION_ROOT = REPO_ROOT / ".github/actions"
REFERENCE_RENDER = "python3 tests/fixtures/golden/reference_render.py"
CORE_PACKAGE = "scripts/core.sh package"
CORE_FIXTURE_CONSUMERS = (
    REFERENCE_RENDER,
    CORE_PACKAGE,
    "scripts/core.sh proof",
    "scripts/core.sh test ",
    "scripts/core-coverage.sh check",
    "python3 tests/core/provider/stage12_fixture_corpus_test.py",
)
FIXTURE_REHYDRATION = "git lfs checkout -- tests/fixtures"
FIXTURE_REHYDRATION_NOTE = (
    f"{FIXTURE_REHYDRATION} rehydrates the complete Core test fixture corpus"
)
WEB_HEAVY_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-web-heavy]"
)
CORE_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-core]"
)
# Lanes cut over to the dedicated netcup role, mapped to the lane each one
# runs.
WEB_HEAVY_LANES = {
    "web-toolchain-conformance": "web_toolchain",
    "creator-web": "creator",
    "web-runtime-host": "web_runtime_host",
    "web-runtime-lab": "web_runtime_lab",
}
# Cut-over jobs that do not go through the shared `web-ci-proof` action,
# mapped to the proof step each keeps instead. Web Runtime Lab installs no
# browser stack of its own, so it has no `install-system-deps` input to set
# and must not acquire one by being rerouted.
WEB_HEAVY_DIRECT_PROOFS = {
    "web-runtime-lab": "run: scripts/web-runtime-lab.sh test",
}
HEAVY_JOBS = (
    "portal", "core-ubuntu", "package", "core-coverage", "core-asan",
)


class CiBuildAccelerationTest(unittest.TestCase):
    def workflow_job(self, job_name: str) -> str:
        source = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(
            rf"^  {re.escape(job_name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:|\Z)",
            source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, f"workflow job is missing: {job_name}")
        assert match is not None
        return match.group("body")

    def core_fixture_execution_blocks(self) -> list[tuple[Path, str, str]]:
        blocks: list[tuple[Path, str, str]] = []
        for path in sorted(WORKFLOW_ROOT.glob("*.yml")):
            source = path.read_text(encoding="utf-8")
            if not any(command in source for command in CORE_FIXTURE_CONSUMERS):
                continue
            jobs = source.split("\njobs:\n", 1)
            self.assertEqual(
                len(jobs),
                2,
                f"workflow containing {REFERENCE_RENDER} has no jobs block: {path}",
            )
            matches = list(re.finditer(
                r"^  (?P<name>[a-z0-9-]+):\n",
                jobs[1],
                flags=re.MULTILINE,
            ))
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(jobs[1])
                body = jobs[1][match.end():end]
                if any(command in body for command in CORE_FIXTURE_CONSUMERS):
                    blocks.append((path, match.group("name"), body))

        for path in sorted(ACTION_ROOT.glob("*/action.yml")):
            source = path.read_text(encoding="utf-8")
            if any(command in source for command in CORE_FIXTURE_CONSUMERS):
                blocks.append((path, "composite action", source))
        return blocks

    def test_core_fixture_consumers_rehydrate_the_complete_corpus_first(self) -> None:
        blocks = self.core_fixture_execution_blocks()
        self.assertTrue(blocks, "Core fixture workflow consumers are missing")
        for path, name, block in blocks:
            with self.subTest(path=path.relative_to(REPO_ROOT), consumer=name):
                consumer_index = min(
                    block.index(command)
                    for command in CORE_FIXTURE_CONSUMERS
                    if command in block
                )
                hydration = re.search(
                    rf"(?m)^\s*(?:-\s*)?(?:run:\s*)?"
                    rf"{re.escape(FIXTURE_REHYDRATION)}\s*$",
                    block,
                )
                message = (
                    "why: Core proof, package, and fixture commands require the "
                    "complete LFS-backed test fixture corpus, not pointers; remedy: run "
                    f"`{FIXTURE_REHYDRATION}` in "
                    f"{path.relative_to(REPO_ROOT)}:{name} before the consumer"
                )
                self.assertIsNotNone(hydration, message)
                assert hydration is not None
                self.assertLess(
                    hydration.start(),
                    consumer_index,
                    message,
                )

    def test_core_lanes_declare_and_run_complete_fixture_rehydration(self) -> None:
        lanes = json.loads(LOCAL_LANES.read_text(encoding="utf-8"))["lanes"]
        contracts = {
            "core_ubuntu": (
                self.workflow_job("core-ubuntu"),
                "scripts/core.sh proof",
            ),
            "core_asan": (
                self.workflow_job("core-asan"),
                "scripts/core.sh test asan full",
            ),
            "core_coverage": (
                self.workflow_job("core-coverage"),
                "scripts/core-coverage.sh check",
            ),
            "core_macos": (
                MACOS_ACTION.read_text(encoding="utf-8"),
                "scripts/core.sh proof",
            ),
        }
        message = (
            "why: local Core commands rely on the checkout's existing LFS "
            "fixture bytes while CI rehydrates them explicitly; remedy: record "
            f"the exact CI-only step `{FIXTURE_REHYDRATION_NOTE}`"
        )
        for lane, (consumer_block, consumer) in contracts.items():
            with self.subTest(lane=lane, contract="local declaration"):
                self.assertIn(
                    FIXTURE_REHYDRATION_NOTE,
                    lanes[lane]["ci_only"],
                    message,
                )
            with self.subTest(lane=lane, contract="workflow ordering"):
                hydration_index = consumer_block.index(FIXTURE_REHYDRATION)
                self.assertLess(
                    hydration_index,
                    consumer_block.index(consumer),
                    message,
                )

    def test_acceleration_action_bounds_parallelism_and_scopes_ccache(self) -> None:
        self.assertTrue(
            ACCELERATION_ACTION.is_file(),
            "reusable build acceleration action is missing",
        )
        if not ACCELERATION_ACTION.is_file():
            return

        source = ACCELERATION_ACTION.read_text(encoding="utf-8")
        self.assertIn("parallel-level:", source)
        self.assertIn('default: "3"', source)
        self.assertIn("CMAKE_BUILD_PARALLEL_LEVEL", source)
        self.assertIn("use-ccache:", source)
        self.assertIn("command -v ccache", source)
        self.assertIn("CCACHE_DIR", source)
        self.assertIn("CCACHE_BASEDIR", source)
        self.assertIn("CCACHE_STATSLOG", source)
        self.assertIn("CMAKE_C_COMPILER_LAUNCHER=ccache", source)
        self.assertIn("CMAKE_CXX_COMPILER_LAUNCHER=ccache", source)
        self.assertNotIn("actions/cache", source)
        self.assertNotIn("ccache --zero-stats", source)

    def test_linux_native_jobs_always_use_the_role_persistent_ccache(self) -> None:
        """The cache condition goes with the selector output it read.

        `use-ccache` was gated on whether the run had been diverted to paid
        Ubuntu, where no persistent cache exists. These three lanes now only
        ever execute on the shared host that owns the cache, so the input is
        unconditionally true and the statistics step is unconditional too:
        native Core ccache behavior is preserved, not merely retained.
        """
        for job_name in ("core-ubuntu", "core-asan", "core-coverage"):
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn("change-scope", job)

    def test_native_jobs_retain_every_host_capacity_lock_waiter(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        capacity_jobs = (
            "portal",
            "core-ubuntu",
            "package",
            "core-asan",
            "core-coverage",
            # #1558 moved Release stress to the bare-metal macOS runner because
            # its 2.67 ms thread-CPU deadline cannot survive a hypervisor. The
            # gates build Core twice on that same machine, so they join the
            # queue rather than supply the contention that move removed.
            "macos-primary",
        )
        self.assertEqual(
            source.count("group: lmdj-native-heavy"),
            len(capacity_jobs),
            "why: every job that can contend with timing-sensitive native work "
            "on a shared machine must join one capacity queue; remedy: keep the "
            "lmdj-native-heavy concurrency block on "
            + ", ".join(capacity_jobs),
        )
        for job_name in capacity_jobs:
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertRegex(
                    job,
                    r"(?m)^    concurrency:\n"
                    r"      group: lmdj-native-heavy\n"
                    r"      queue: max\n"
                    r"      cancel-in-progress: false$",
                    msg=(
                        "why: GitHub's default concurrency queue replaces an older pending "
                        f"{job_name} waiter and sibling native work can consume the shared "
                        "host's test budgets; remedy: keep queue: max before "
                        "cancel-in-progress: false on every admitted shared-host lane"
                    ),
                )

        for job_name in ("core-ubuntu", "package", "core-asan", "core-coverage"):
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(CORE_ROLE, job)
                self.assertNotIn("select-ubuntu-runner", job)
                self.assertIn(
                    "uses: ./.github/actions/configure-build-acceleration", job
                )
                if job_name == "package":
                    self.assertIn("use-ccache: false", job)
                    self.assertNotIn("ccache --show-log-stats", job)
                else:
                    self.assertIn("use-ccache: true", job)
                    self.assertIn("ccache --show-log-stats", job)
                    self.assertIn(
                        "if: ${{ always() }}\n"
                        "        run: >-\n"
                        "          ccache --show-log-stats",
                        job,
                    )

    def test_package_uses_lfs_and_bounded_acceleration_without_ccache(self) -> None:
        job = self.workflow_job("package")
        self.assertIn("change-scope", job)
        self.assertIn(CORE_ROLE, job)
        self.assertNotIn("select-ubuntu-runner", job)
        self.assertIn("lfs: true", job)
        message = (
            "why: scripts/core.sh package runs audio.offline_renderer in the "
            "component tier, which reads the LFS-tracked golden WAV; remedy: "
            f"run `{FIXTURE_REHYDRATION}` before scripts/core.sh package"
        )
        with self.subTest(source="workflow"):
            self.assertIn(FIXTURE_REHYDRATION, job, message)
            self.assertLess(
                job.index(FIXTURE_REHYDRATION),
                job.index("scripts/core.sh package"),
                message,
            )
        with self.subTest(source="local lane declaration"):
            lanes = json.loads(LOCAL_LANES.read_text(encoding="utf-8"))
            package_ci_only = lanes["lanes"]["package"]["ci_only"]
            self.assertIn(
                FIXTURE_REHYDRATION_NOTE,
                package_ci_only,
                message,
            )
        self.assertIn(
            "uses: ./.github/actions/configure-build-acceleration", job
        )
        self.assertIn("use-ccache: false", job)
        self.assertIn("scripts/core.sh package", job)

    def test_native_heavy_jobs_use_the_exact_sparse_sequence(self) -> None:
        for index, job_name in enumerate(HEAVY_JOBS):
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                for dependency in ("change-scope", *HEAVY_JOBS[:index]):
                    self.assertIn(dependency, job)
                for later in HEAVY_JOBS[index + 1:]:
                    self.assertNotIn(
                        f"needs.{later}.result", job,
                        "why: a native-heavy job must not wait for a later job; "
                        "remedy: keep dependencies limited to earlier heavy jobs",
                    )

    def test_web_builds_use_bounded_parallelism_without_ccache(self) -> None:
        action = WEB_PROOF_ACTION.read_text(encoding="utf-8")
        for job_name in ("web-toolchain-conformance", "web-runtime-host"):
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(
                    "uses: ./.github/actions/web-ci-proof", job
                )
        self.assertIn(
            "uses: ./.github/actions/configure-build-acceleration", action
        )
        self.assertIn("use-ccache: false", action)

        for script_path in (WEB_TOOLCHAIN, WEB_HOST):
            with self.subTest(script=script_path.name):
                source = script_path.read_text(encoding="utf-8")
                self.assertIn("run_cmake_build()", source)
                self.assertIn("CMAKE_BUILD_PARALLEL_LEVEL", source)
                self.assertRegex(source, r'parallel_args=\(--parallel\)')

    def test_cut_over_web_lanes_reuse_the_provisioned_netcup_browser_stack(self) -> None:
        """A persistent CI-only role provisions browser deps once, not per run.

        `install-system-deps: "true"` lets Playwright apt-install host
        libraries on every run. That is cheap on a discarded hosted image and
        wrong on the dedicated netcup node, where it repeats work the role
        already provides and mutates state shared by both runner services.
        """
        for job_name, lane in WEB_HEAVY_LANES.items():
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(WEB_HEAVY_ROLE, job)
                self.assertNotIn('install-system-deps: "true"', job)
                if job_name in WEB_HEAVY_DIRECT_PROOFS:
                    self.assertIn(WEB_HEAVY_DIRECT_PROOFS[job_name], job)
                    self.assertNotIn("install-system-deps", job)
                else:
                    self.assertIn(f"lane: {lane}", job)
                    self.assertIn('install-system-deps: "false"', job)

    def test_generated_web_toolchain_does_not_dirty_source_tree(self) -> None:
        ignored = {
            line.strip()
            for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn("build/toolchains/", ignored)

    def test_linux_browser_jobs_force_utf8_locale(self) -> None:
        for job_name in (
            "web-toolchain-conformance",
            "web-runtime-host",
            "creator-web",
        ):
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(
                    "    env:\n      LANG: C.UTF-8\n      LC_ALL: C.UTF-8\n",
                    job,
                )

    def test_ubuntu_apple_target_probe_reuses_proof_configuration(self) -> None:
        job = self.workflow_job("core-ubuntu")
        self.assertIn("scripts/core.sh proof", job)
        self.assertIn("scripts/core.sh configure dev", job)
        self.assertNotIn("scripts/core.sh build dev", job)
        self.assertIn("cmake --build build/core/dev --target help", job)

    def test_macos_primary_uses_persistent_cache_but_fallback_does_not(self) -> None:
        primary = self.workflow_job("macos-primary")
        fallback = self.workflow_job("macos-fallback")
        action = MACOS_ACTION.read_text(encoding="utf-8")

        self.assertIn(
            "use-ccache: ${{ needs.select-macos-runner.outputs.self-hosted }}",
            primary,
        )
        self.assertIn("use-ccache: false", fallback)
        self.assertIn("use-ccache:", action)
        self.assertIn(
            "uses: ./.github/actions/configure-build-acceleration", action
        )
        self.assertIn("ccache --show-log-stats", action)


if __name__ == "__main__":
    unittest.main()
