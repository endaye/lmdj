#!/usr/bin/env python3
"""Contract tests for bounded CI build acceleration and persistent ccache use."""

from __future__ import annotations

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

    def test_linux_native_jobs_use_ccache_only_on_self_hosted_lane(self) -> None:
        expected_cache_selector = (
            "use-ccache: ${{ needs.select-ubuntu-runner.outputs.self-hosted }}"
        )
        for job_name in ("core-ubuntu", "core-asan", "core-coverage"):
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(
                    "needs: [change-scope, select-ubuntu-runner]", job
                )
                self.assertIn(
                    "uses: ./.github/actions/configure-build-acceleration", job
                )
                self.assertIn(expected_cache_selector, job)
                self.assertIn("ccache --show-log-stats", job)

    def test_package_uses_lfs_and_bounded_acceleration_without_ccache(self) -> None:
        job = self.workflow_job("package")
        self.assertIn("needs: [change-scope, select-ubuntu-runner]", job)
        self.assertIn(
            "runs-on: ${{ fromJSON(needs.select-ubuntu-runner.outputs.runner) }}",
            job,
        )
        self.assertIn("lfs: true", job)
        self.assertIn("git lfs checkout -- tests/fixtures/audio", job)
        self.assertIn(
            "uses: ./.github/actions/configure-build-acceleration", job
        )
        self.assertIn("use-ccache: false", job)
        self.assertIn("scripts/core.sh package", job)

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
