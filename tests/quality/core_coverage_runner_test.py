#!/usr/bin/env python3
"""Focused lifecycle regression fixtures for the Core coverage runner."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


repo_root = Path(__file__).resolve().parents[2]
runner_path = repo_root / "scripts" / "core-coverage.sh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class CoreCoverageRunnerTest(unittest.TestCase):
    def test_failed_run_cannot_leave_documented_stale_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            scripts_root = temp_root / "scripts"
            coverage_root = temp_root / "build" / "core" / "coverage" / "coverage"
            fake_bin = temp_root / "fake-bin"
            scripts_root.mkdir()
            coverage_root.mkdir(parents=True)
            fake_bin.mkdir()
            shutil.copy2(runner_path, scripts_root / runner_path.name)

            artifact_paths = [
                coverage_root / "merged.profdata",
                coverage_root / "summary.json",
                coverage_root / "report.txt",
            ]
            for artifact_path in artifact_paths:
                artifact_path.write_text("stale evidence", encoding="utf-8")

            write_executable(
                fake_bin / "cmake",
                """#!/bin/sh
if [ "$1" = "-E" ] && [ "$2" = "make_directory" ]; then
  /bin/mkdir -p "$3"
fi
exit 0
""",
            )
            write_executable(
                fake_bin / "ctest",
                """#!/bin/sh
echo "ctest sentinel failure" >&2
exit 9
""",
            )
            for tool_name in ("llvm-profdata", "llvm-cov"):
                write_executable(
                    fake_bin / tool_name,
                    "#!/bin/sh\nexit 0\n",
                )

            environment = os.environ.copy()
            environment["PATH"] = (
                f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin"
            )
            result = subprocess.run(
                [str(scripts_root / runner_path.name), "report"],
                cwd=temp_root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ctest sentinel failure", result.stderr)
            for artifact_path in artifact_paths:
                self.assertFalse(
                    artifact_path.exists(),
                    f"stale artifact survived failure: {artifact_path.name}",
                )


if __name__ == "__main__":
    unittest.main()
