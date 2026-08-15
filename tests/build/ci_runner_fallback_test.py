#!/usr/bin/env python3
"""Contract tests for the trusted self-hosted CI routing topology."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
ACTIONLINT_CONFIG = REPO_ROOT / ".github/actionlint.yaml"
ACTION = REPO_ROOT / ".github/actions/macos-core-gates/action.yml"
ASSERT_GATE = REPO_ROOT / ".github/scripts/assert-macos-gate-result.sh"
WEB_HEAVY_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-web-heavy]"
)
# Lanes cut over to the dedicated netcup role, mapped to the `web-ci-proof`
# lane each one must still request. Cutting over must not silently reroute a
# lane's workload.
WEB_HEAVY_LANES = {
    "web-toolchain-conformance": "web_toolchain",
    "creator-web": "creator",
    "web-runtime-host": "web_runtime_host",
}
# Jobs whose runner is still resolved by `select-ubuntu-runner`. Cutting a
# lane over removes it from here and from the selector's guard together, so
# the selector is never started for a route nobody reads.
SELECTOR_CONSUMERS = (
    "web-runtime-lab",
    "core-ubuntu",
    "core-asan",
    "core-coverage",
)


class CiRunnerFallbackTest(unittest.TestCase):
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

    def action_step(self, step_name: str) -> str:
        source = ACTION.read_text(encoding="utf-8")
        match = re.search(
            rf"^    - name: {re.escape(step_name)}\n"
            r"(?P<body>.*?)(?=^    - name:|\Z)",
            source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, f"composite action step is missing: {step_name}")
        assert match is not None
        return match.group("body")

    def run_gate(
        self,
        gate: str,
        **environment: str,
    ) -> subprocess.CompletedProcess[str]:
        process_environment = os.environ.copy()
        process_environment.update(environment)
        return subprocess.run(
            ["bash", str(ASSERT_GATE), gate],
            cwd=REPO_ROOT,
            env=process_environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_workflow_preserves_required_check_names_and_routes_mac_gates(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: core (ubuntu-latest)", source)
        self.assertIn("name: core (macos-latest)", source)
        self.assertIn("name: core-asan-macos", source)
        self.assertIn("secrets.SELF_HOSTED_RUNNER_READ_TOKEN", source)
        self.assertIn("endaye-mbp-m1", source)
        self.assertIn("needs.select-macos-runner.outputs.runner", source)
        self.assertIn("needs.macos-primary.outputs.completed != 'true'", source)
        self.assertIn("timeout-minutes: 30", source)
        self.assertIn("github.event.pull_request.head.repo.full_name", source)
        self.assertEqual(source.count("Runner selection candidates:"), 2)
        self.assertEqual(source.count("Runner selection inventory:"), 2)
        self.assertEqual(source.count("TARGET_RUNNER_NAME:"), 1)
        self.assertNotRegex(source, r"(?m)^\s+RUNNER_NAME:")
        self.assertNotIn('"$RUNNER_NAME"', source)

    def test_workflow_routes_linux_gates_to_contabo_when_selected(self) -> None:
        selector = self.workflow_job("select-ubuntu-runner")
        self.assertIn("needs: change-scope", selector)
        self.assertIn("needs.change-scope.outputs.manifest", selector)
        self.assertNotIn("TARGET_RUNNER_NAME", selector)
        self.assertNotIn("contabo-lmdj-linux", selector)
        self.assertNotIn(".name ==", selector)
        self.assertIn('if [[ "$eligible_count" == "0" ]]', selector)
        self.assertGreaterEqual(
            selector.count(
                'contains(["self-hosted", "Linux", "X64", "lmdj-linux", "contabo"])'
            ),
            2,
        )
        self.assertIn(
            "runner=[\"self-hosted\",\"Linux\",\"X64\",\"lmdj-linux\",\"contabo\"]",
            selector,
        )
        self.assertIn("runner=[\"ubuntu-24.04\"]", selector)
        self.assertIn("github.event.pull_request.head.repo.full_name", selector)

        for job_name in SELECTOR_CONSUMERS:
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(
                    "needs: [change-scope, select-ubuntu-runner]", job
                )
                self.assertIn(
                    "runs-on: ${{ fromJSON(needs.select-ubuntu-runner.outputs.runner) }}",
                    job,
                )

    def test_selector_consumers_also_require_a_trusted_head(self) -> None:
        """The selector's fork branch is depth, not the only trust boundary.

        `select-ubuntu-runner` decides where a job runs; it cannot decide
        whether the job runs at all. Every workload that can land on the pool
        therefore carries the closed manifest trust condition, so an untrusted
        head is blocked before routing rather than diverted to paid runners.
        """
        for job_name in (*SELECTOR_CONSUMERS, "package"):
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(
                    "runs-on: ${{ fromJSON(needs.select-ubuntu-runner.outputs.runner) }}",
                    job,
                )
                self.assertIn(
                    "needs.change-scope.outputs.trusted-head == 'true'", job
                )
        selector = self.workflow_job("select-ubuntu-runner")
        self.assertIn("runs-on: ubuntu-24.04", selector)
        self.assertNotIn("trusted-head", selector)

    def test_cut_over_web_lanes_are_pinned_to_the_netcup_web_heavy_role(self) -> None:
        """Web Toolchain, Creator and Web Runtime Host use the netcup node.

        The role label set is static, not selector-resolved. `ci-web-heavy`
        exists only on the dedicated node, so a busy or absent role queues a
        cut-over lane instead of diverting it to paid runners, which is why
        these jobs keep their own `needs: change-scope` rather than joining the
        `select-ubuntu-runner` consumers. Trust therefore cannot come from the
        selector's fork branch and must stay on each job itself.
        """
        for job_name, lane in WEB_HEAVY_LANES.items():
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(WEB_HEAVY_ROLE, job)
                self.assertIn("needs: change-scope", job)
                self.assertNotIn("needs: select-ubuntu-runner", job)
                self.assertNotIn("needs.select-ubuntu-runner.outputs.runner", job)
                self.assertNotIn("runs-on: ubuntu-24.04", job)
                self.assertIn(
                    "needs.change-scope.outputs.trusted-head == 'true'", job
                )
                self.assertIn(f"lane: {lane}", job)
                self.assertIn('install-system-deps: "false"', job)

    def test_actionlint_config_is_plain_git_text_not_an_lfs_pointer(self) -> None:
        attribute = subprocess.run(
            ["git", "check-attr", "filter", "--", str(ACTIONLINT_CONFIG)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertNotIn("filter: lfs", attribute)
        self.assertNotIn(
            "version https://git-lfs.github.com/spec/v1",
            ACTIONLINT_CONFIG.read_text(encoding="utf-8"),
        )

    def test_self_hosted_coverage_uses_preinstalled_toolchain(self) -> None:
        coverage = self.workflow_job("core-coverage")
        self.assertIn(
            "name: Install coverage toolchain on GitHub-hosted runner",
            coverage,
        )
        self.assertIn(
            "if: ${{ needs.select-ubuntu-runner.outputs.self-hosted != 'true' }}",
            coverage,
        )
        self.assertIn("name: Verify coverage toolchain", coverage)
        self.assertIn("command -v clang-18", coverage)
        self.assertIn("command -v llvm-cov-18", coverage)

    def test_cut_over_web_gates_record_why_the_hosted_pin_was_lifted(self) -> None:
        """The routing reason must survive, or a later pass will churn it back.

        Creator was hosted because the Wasm/OPFS fault matrix is
        timing-sensitive and exceeded bounded budgets on the heterogeneous
        shared pool. Extra runner slots and toolchain caches never addressed
        that; the dedicated CI-only role removes the heterogeneity itself,
        which is a different argument and was proven lane by lane. Keeping
        both halves in the file stops a later cost pass from reading the move
        as "more slots were enough", and stops a later determinism pass from
        restoring a pin whose premise is gone.
        """
        for job_name in WEB_HEAVY_LANES:
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn("dedicated CI-only netcup node", job)
                self.assertIn("instead of diverting it to paid runners", job)
                self.assertNotIn("for determinism, not for capacity", job)
        creator = self.workflow_job("creator-web")
        self.assertIn("timing-sensitive", creator)
        self.assertIn("bounded test budgets", creator)

    def test_selectors_queue_on_a_busy_pool_instead_of_paying_for_hosted(self) -> None:
        """A loaded trusted pool must queue, never divert to paid runners.

        `select-*` resolves once, before any workload job starts. Treating a
        momentarily busy pool as unavailable sent an entire six-lane manifest
        to GitHub-hosted infrastructure, which is what made concurrent retries
        expensive rather than merely slow.
        """
        for selector_name in ("select-ubuntu-runner", "select-macos-runner"):
            with self.subTest(selector=selector_name):
                selector = self.workflow_job(selector_name)
                eligibility = re.search(
                    r'eligible_count="\$\(\n(?P<body>.*?)\n          \)"',
                    selector,
                    flags=re.DOTALL,
                )
                self.assertIsNotNone(
                    eligibility, f"{selector_name} has no eligibility expression"
                )
                assert eligibility is not None
                body = eligibility.group("body")
                self.assertNotIn(".busy == false", body)
                self.assertIn('.status == "online"', body)

    def test_selectors_still_fall_back_when_no_trusted_runner_is_online(self) -> None:
        ubuntu = self.workflow_job("select-ubuntu-runner")
        macos = self.workflow_job("select-macos-runner")
        self.assertIn(
            "select_hosted 'no online trusted self-hosted runner is available'",
            ubuntu,
        )
        self.assertIn(
            "select_hosted 'self-hosted runner is offline, missing, or mislabeled'",
            macos,
        )
        for selector in (ubuntu, macos):
            self.assertIn("untrusted fork pull request", selector)
            self.assertIn("runner status token is unavailable", selector)

    def test_slow_pool_lane_keeps_headroom_over_its_observed_duration(self) -> None:
        """The job limit must clear the slowest trusted runner, not the fastest.

        web-runtime-host was observed at 40 minutes on the trusted pool and
        cancelled at exactly 45 once, against 16-19 minutes GitHub-hosted. The
        lane now always runs self-hosted, on the dedicated role, so a limit
        calibrated to hosted speed would convert a cost saving into an
        intermittent red Pull Request. The netcup node has not yet produced
        its own timing evidence, so the headroom stays until it does.
        """
        job = self.workflow_job("web-runtime-host")
        match = re.search(r"timeout-minutes: (\d+)", job)
        self.assertIsNotNone(match, "web-runtime-host declares no timeout")
        assert match is not None
        self.assertGreaterEqual(int(match.group(1)), 60)
        self.assertIn("hang detector, not", job)

    def test_ubuntu_selector_still_reports_idle_capacity_as_diagnostics(self) -> None:
        selector = self.workflow_job("select-ubuntu-runner")
        self.assertIn("idle_count=", selector)
        self.assertIn(".busy == false", selector)
        self.assertIn("selected jobs queue instead of using paid runners", selector)

    def test_macos_jobs_keep_selector_fallback_and_adjudicator_topology(self) -> None:
        selector = self.workflow_job("select-macos-runner")
        primary = self.workflow_job("macos-primary")
        fallback = self.workflow_job("macos-fallback")
        core = self.workflow_job("core-macos")
        asan = self.workflow_job("core-asan-macos")

        self.assertIn("needs: change-scope", selector)
        self.assertIn("needs.change-scope.outputs.manifest", selector)
        self.assertIn(
            "needs: [change-scope, select-macos-runner]", primary
        )
        self.assertIn("needs: [select-macos-runner, macos-primary]", fallback)
        expected_adjudicator_needs = (
            "needs: [change-scope, select-macos-runner, macos-primary, macos-fallback]"
        )
        self.assertIn(expected_adjudicator_needs, core)
        self.assertIn(expected_adjudicator_needs, asan)

    def test_linux_fixture_consumers_rehydrate_lfs_before_generation(self) -> None:
        consumers = {
            "web-runtime-host": "uses: ./.github/actions/web-ci-proof",
            "core-ubuntu": "python3 tests/fixtures/audio/make_fixtures.py",
            "core-asan": "python3 tests/fixtures/audio/make_fixtures.py",
            "core-coverage": "python3 tests/fixtures/audio/make_fixtures.py",
        }

        for job_name, consumer in consumers.items():
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                hydration = "git lfs checkout -- tests/fixtures/audio"
                self.assertIn(hydration, job)
                self.assertLess(job.index(hydration), job.index(consumer))

    def test_self_hosted_mac_uses_preinstalled_python_while_hosted_uses_setup(self) -> None:
        primary = self.workflow_job("macos-primary")
        self.assertIn("name: Verify self-hosted Python 3.11", primary)
        self.assertIn("command -v python3.11", primary)
        self.assertIn("$RUNNER_TEMP/lmdj-python-3.11", primary)
        self.assertIn(
            "needs.select-macos-runner.outputs.self-hosted == 'true'", primary
        )
        self.assertIn(
            "needs.select-macos-runner.outputs.self-hosted != 'true'", primary
        )
        self.assertEqual(primary.count("uses: actions/setup-python@v6"), 1)

    def test_composite_action_publishes_results_instead_of_retrying_tests(self) -> None:
        source = ACTION.read_text(encoding="utf-8")
        self.assertEqual(source.count("continue-on-error: true"), 4)
        self.assertEqual(source.count("scripts/core.sh proof"), 1)
        self.assertEqual(source.count("scripts/core.sh configure asan"), 1)
        self.assertEqual(source.count("ctest --preset asan -L '^native$'"), 1)
        self.assertIn("echo 'completed=true'", source)

    def test_acceleration_failure_leaves_completion_unset_for_hosted_fallback(self) -> None:
        acceleration = self.action_step("Configure bounded build acceleration")
        prepare = self.action_step("Prepare deterministic Core inputs")
        publisher = self.action_step("Publish semantic gate results")

        self.assertIn("id: acceleration", acceleration)
        self.assertIn("continue-on-error: true", acceleration)
        self.assertIn(
            "if: ${{ steps.acceleration.outcome == 'success' }}", prepare
        )
        self.assertIn(
            "if: ${{ always() && steps.acceleration.outcome == 'success' }}",
            publisher,
        )
        self.assertIn("echo 'completed=true'", publisher)
        self.assertIn("PREPARE_RESULT: ${{ steps.prepare.outcome }}", publisher)

    def test_primary_semantic_success_passes(self) -> None:
        completed = self.run_gate(
            "core",
            PRIMARY_COMPLETED="true",
            PRIMARY_PREPARE_RESULT="success",
            PRIMARY_CORE_RESULT="success",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("lane=primary", completed.stdout)

    def test_fallback_result_replaces_missing_primary_infrastructure_result(self) -> None:
        completed = self.run_gate(
            "asan",
            FALLBACK_COMPLETED="true",
            FALLBACK_PREPARE_RESULT="success",
            FALLBACK_ASAN_RESULT="success",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("lane=fallback", completed.stdout)

    def test_semantic_failure_is_not_hidden_by_fallback_logic(self) -> None:
        completed = self.run_gate(
            "core",
            PRIMARY_COMPLETED="true",
            PRIMARY_PREPARE_RESULT="success",
            PRIMARY_CORE_RESULT="failure",
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("not retried", completed.stderr)

    def test_missing_terminal_result_fails_closed(self) -> None:
        completed = self.run_gate("asan")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("no fallback result", completed.stderr)

    def test_unknown_gate_is_a_usage_error(self) -> None:
        completed = self.run_gate("unknown")
        self.assertEqual(completed.returncode, 64)


if __name__ == "__main__":
    unittest.main()
