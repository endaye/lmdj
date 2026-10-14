#!/usr/bin/env python3
"""Regression fixtures for authoritative multi-object coverage union."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


repo_root = Path(__file__).resolve().parents[2]
union_path = repo_root / "tests" / "quality" / "coverage_union.py"
source_path = repo_root / "packages" / "foundation" / "src" / "json.cpp"


def lcov_record(
    *,
    lines: dict[int, int],
    branches: dict[tuple[int, int, int], int | None],
    source: Path = source_path,
) -> str:
    records = ["TN:", f"SF:{source}"]
    records.extend(
        f"DA:{line},{count}" for line, count in sorted(lines.items())
    )
    records.extend(
        f"BRDA:{line},{block},{branch},{'-' if taken is None else taken}"
        for (line, block, branch), taken in sorted(branches.items())
    )
    records.append("end_of_record")
    return "\n".join(records) + "\n"


class CoverageUnionTest(unittest.TestCase):
    def run_union(
        self,
        temp_root: Path,
        fragments: list[str],
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        summary_path = temp_root / "summary.json"
        report_path = temp_root / "report.txt"

        fragment_paths: list[Path] = []
        for index, fragment in enumerate(fragments, start=1):
            fragment_path = temp_root / f"fragment-{index}.lcov"
            fragment_path.write_text(fragment, encoding="utf-8")
            fragment_paths.append(fragment_path)

        command = [
            sys.executable,
            str(union_path),
            "--repo-root",
            str(repo_root),
        ]
        for fragment_path in fragment_paths:
            command.extend(["--fragment", str(fragment_path)])
        command.extend(
            [
                "--summary",
                str(summary_path),
                "--report",
                str(report_path),
            ]
        )
        result = subprocess.run(
            command,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        return result, summary_path, report_path

    def test_unions_counts_across_objects_by_physical_identity(
        self,
    ) -> None:
        # Two objects compile the same source; each export names every
        # identity, and each covers a different half of it.
        fragments = [
            lcov_record(
                lines={10: 3, 20: 0},
                branches={(10, 0, 0): 1, (20, 0, 1): None},
            ),
            lcov_record(
                lines={10: 0, 20: 4},
                branches={(10, 0, 0): None, (20, 0, 1): 2},
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            result, summary_path, report_path = self.run_union(
                Path(temp_dir),
                fragments,
            )

            self.assertEqual(
                result.returncode,
                0,
                result.stdout + result.stderr,
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            file_summary = summary["data"][0]["files"][0]["summary"]
            self.assertEqual(
                file_summary["lines"],
                {"count": 2, "covered": 2, "notcovered": 0, "percent": 100.0},
            )
            self.assertEqual(
                file_summary["branches"],
                {"count": 2, "covered": 2, "notcovered": 0, "percent": 100.0},
            )
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("packages/foundation/src/json.cpp", report)
            self.assertIn("TOTAL", report)

    def test_unions_duplicate_source_compile_variants_by_physical_identity(
        self,
    ) -> None:
        # Production and fault-interception variants of one source have
        # different mappings; the union keeps each identity exactly once.
        fragments = [
            lcov_record(
                lines={10: 3, 20: 4},
                branches={(10, 0, 0): 1, (20, 0, 1): 2},
            ),
            lcov_record(
                lines={10: 5, 30: 6},
                branches={(10, 0, 0): 3, (30, 0, 2): 4},
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            result, summary_path, _ = self.run_union(
                Path(temp_dir),
                fragments,
            )

            self.assertEqual(
                result.returncode,
                0,
                result.stdout + result.stderr,
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            file_summary = summary["data"][0]["files"][0]["summary"]
            self.assertEqual(
                file_summary["lines"],
                {"count": 3, "covered": 3, "notcovered": 0, "percent": 100.0},
            )
            self.assertEqual(
                file_summary["branches"],
                {"count": 3, "covered": 3, "notcovered": 0, "percent": 100.0},
            )

    def test_union_without_first_party_source_fails_without_stale_outputs(
        self,
    ) -> None:
        fragments = [
            lcov_record(
                lines={10: 1},
                branches={(10, 0, 0): 1},
                source=Path("/usr/include/c++/v1/vector"),
            )
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            summary_path = temp_root / "summary.json"
            report_path = temp_root / "report.txt"
            summary_path.write_text("stale summary", encoding="utf-8")
            report_path.write_text("stale report", encoding="utf-8")

            result, summary_path, report_path = self.run_union(
                temp_root,
                fragments,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "coverage fragments contain no first-party source",
                result.stderr,
            )
            self.assertFalse(summary_path.exists())
            self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
