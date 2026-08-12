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
ACTION = REPO_ROOT / ".github/actions/macos-core-gates/action.yml"
ASSERT_GATE = REPO_ROOT / ".github/scripts/assert-macos-gate-result.sh"


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

        for job_name in (
            "web-runtime-host",
            "web-runtime-lab",
            "core-ubuntu",
            "core-asan",
            "core-coverage",
        ):
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(
                    "needs: [change-scope, select-ubuntu-runner]", job
                )
                self.assertIn(
                    "runs-on: ${{ fromJSON(needs.select-ubuntu-runner.outputs.runner) }}",
                    job,
                )

    def test_resource_intensive_web_gates_use_hosted_runners(self) -> None:
        for job_name in ("web-toolchain-conformance", "creator-web"):
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertNotIn("needs: select-ubuntu-runner", job)
                self.assertIn("needs: change-scope", job)
                self.assertIn("runs-on: ubuntu-24.04", job)
                self.assertNotIn("needs.select-ubuntu-runner.outputs.runner", job)

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
            "web-runtime-host": "scripts/web-runtime-host.sh proof",
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
