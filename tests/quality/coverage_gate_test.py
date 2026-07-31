#!/usr/bin/env python3
"""Unit fixtures for the Core source-coverage threshold gate."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


repo_root = Path(__file__).resolve().parents[2]
gate_path = repo_root / "tests" / "quality" / "coverage_gate.py"


def file_summary(
    filename: str,
    *,
    line_count: int,
    line_covered: int,
    branch_count: int,
    branch_covered: int,
) -> dict[str, object]:
    return {
        "filename": filename,
        "summary": {
            "lines": {"count": line_count, "covered": line_covered},
            "branches": {"count": branch_count, "covered": branch_covered},
        },
    }


class CoverageGateTest(unittest.TestCase):
    def run_gate(
        self,
        files: list[dict[str, object]],
        thresholds: dict[str, object],
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            summary_path = temp_root / "summary.json"
            thresholds_path = temp_root / "thresholds.json"
            summary_path.write_text(
                json.dumps({"data": [{"files": files}]}),
                encoding="utf-8",
            )
            thresholds_path.write_text(
                json.dumps(thresholds),
                encoding="utf-8",
            )
            return subprocess.run(
                [
                    sys.executable,
                    str(gate_path),
                    "--summary",
                    str(summary_path),
                    "--thresholds",
                    str(thresholds_path),
                ],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_exact_threshold_passes(self) -> None:
        result = self.run_gate(
            [
                file_summary(
                    "packages/foundation/src/json.cpp",
                    line_count=100,
                    line_covered=80,
                    branch_count=100,
                    branch_covered=70,
                )
            ],
            {
                "overall": {"lines": 80, "branches": 70},
                "paths": {
                    "packages/foundation/": {"lines": 80, "branches": 70}
                },
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("Core coverage gate: PASS\n"))

    def test_line_threshold_below_by_point_zero_one_fails(self) -> None:
        result = self.run_gate(
            [
                file_summary(
                    "packages/foundation/src/json.cpp",
                    line_count=10_000,
                    line_covered=7_999,
                    branch_count=100,
                    branch_covered=70,
                )
            ],
            {"overall": {"lines": 80, "branches": 70}, "paths": {}},
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("lines 79.99% required 80.00%", result.stdout)

    def test_branch_threshold_below_by_point_zero_one_fails(self) -> None:
        result = self.run_gate(
            [
                file_summary(
                    "packages/foundation/src/json.cpp",
                    line_count=100,
                    line_covered=80,
                    branch_count=10_000,
                    branch_covered=6_999,
                )
            ],
            {"overall": {"lines": 80, "branches": 70}, "paths": {}},
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("branches 69.99% required 70.00%", result.stdout)

    def test_missing_configured_path_fails(self) -> None:
        result = self.run_gate(
            [
                file_summary(
                    "packages/foundation/src/json.cpp",
                    line_count=100,
                    line_covered=100,
                    branch_count=100,
                    branch_covered=100,
                )
            ],
            {
                "overall": {"lines": 80, "branches": 70},
                "paths": {
                    "packages/project-cooker/": {"lines": 90, "branches": 80}
                },
            },
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/project-cooker/: missing configured path",
            result.stdout,
        )

    def test_zero_executable_regions_fails(self) -> None:
        result = self.run_gate(
            [
                file_summary(
                    "packages/foundation/include/lmdj/foundation/error.hpp",
                    line_count=0,
                    line_covered=0,
                    branch_count=0,
                    branch_covered=0,
                )
            ],
            {"overall": {"lines": 0, "branches": 0}, "paths": {}},
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("overall: no executable regions", result.stdout)

    def test_excluded_test_path_is_ignored(self) -> None:
        result = self.run_gate(
            [
                file_summary(
                    "packages/foundation/src/json.cpp",
                    line_count=100,
                    line_covered=100,
                    branch_count=100,
                    branch_covered=100,
                ),
                file_summary(
                    "tests/core/foundation/json_test.cpp",
                    line_count=100,
                    line_covered=0,
                    branch_count=100,
                    branch_covered=0,
                ),
            ],
            {"overall": {"lines": 100, "branches": 100}, "paths": {}},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
