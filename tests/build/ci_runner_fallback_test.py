#!/usr/bin/env python3
"""Contract tests for the self-hosted macOS CI fallback topology."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
ACTION = REPO_ROOT / ".github/actions/macos-core-gates/action.yml"
ASSERT_GATE = REPO_ROOT / ".github/scripts/assert-macos-gate-result.sh"


class CiRunnerFallbackTest(unittest.TestCase):
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

    def test_composite_action_publishes_results_instead_of_retrying_tests(self) -> None:
        source = ACTION.read_text(encoding="utf-8")
        self.assertEqual(source.count("continue-on-error: true"), 3)
        self.assertEqual(source.count("scripts/core.sh proof"), 1)
        self.assertEqual(source.count("scripts/core.sh configure asan"), 1)
        self.assertEqual(source.count("ctest --preset asan -L '^native$'"), 1)
        self.assertIn("echo 'completed=true'", source)

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
