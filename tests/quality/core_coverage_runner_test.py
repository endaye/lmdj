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
root_cmake_path = repo_root / "CMakeLists.txt"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class CoreCoverageRunnerTest(unittest.TestCase):
    def test_project_bundle_transfer_test_is_a_coverage_object(self) -> None:
        root_cmake = root_cmake_path.read_text(encoding="utf-8")
        coverage_targets_start = root_cmake.index(
            "    lmdj_coverage_targets\n"
        )
        coverage_targets_end = root_cmake.index(
            "  )\n",
            coverage_targets_start,
        )
        coverage_targets = root_cmake[
            coverage_targets_start:coverage_targets_end
        ]

        self.assertIn(
            "    lmdj_project_bundle_transfer_tests\n",
            coverage_targets,
        )

    def test_sample_analysis_test_is_a_coverage_object(self) -> None:
        root_cmake = root_cmake_path.read_text(encoding="utf-8")
        coverage_targets_start = root_cmake.index(
            "    lmdj_coverage_targets\n"
        )
        coverage_targets_end = root_cmake.index(
            "  )\n",
            coverage_targets_start,
        )
        coverage_targets = root_cmake[
            coverage_targets_start:coverage_targets_end
        ]

        self.assertIn(
            "    lmdj_project_cooker_sample_analysis_tests\n",
            coverage_targets,
        )

    def test_object_probe_keeps_native_audio_device_free(self) -> None:
        runner = runner_path.read_text(encoding="utf-8")
        probe_start = runner.index('probe_root="$run_root/probes"')
        probe_end = runner.index(
            'if [[ "$shared_object_count" -ne 1 ]]',
            probe_start,
        )
        probe_block = runner[probe_start:probe_end]

        argument_start = probe_block.index("  probe_arguments=()")
        argument_end = probe_block.index(
            '  probe_stdout="$probe_root/$object_number.stdout"',
            argument_start,
        )
        argument_block = probe_block[argument_start:argument_end]
        harness = f"""#!/usr/bin/env bash
set -euo pipefail
for object_path in \
  /tmp/lmdj-native-audio-probe \
  /tmp/lmdj-foundation-tests; do
{argument_block}
  printf '%s:%s\\n' \
    "$(basename "$object_path")" \
    "${{probe_arguments[*]-}}"
done
"""
        completed = subprocess.run(
            ["/bin/bash"],
            input=harness,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout.splitlines(),
            [
                "lmdj-native-audio-probe:--no-device",
                "lmdj-foundation-tests:",
            ],
        )

        invocation_start = probe_block.index(
            '  probe_stdout="$probe_root/$object_number.stdout"'
        )
        invocation_end = probe_block.index(
            "  if grep -Eq 'LLVM Profile (Error|Warning)'",
            invocation_start,
        )
        invocation_block = probe_block[invocation_start:invocation_end]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            capture_root = temp_root / "capture"
            probe_root = temp_root / "probes"
            capture_root.mkdir()
            probe_root.mkdir()
            native_probe = temp_root / "lmdj-native-audio-probe"
            ordinary_probe = temp_root / "lmdj-foundation-tests"
            executable = """#!/bin/sh
printf '%s\\n' "$*" >"$CAPTURE_ROOT/$(basename "$0").args"
if IFS= read -r input; then
  printf 'data:%s\\n' "$input" >"$CAPTURE_ROOT/$(basename "$0").stdin"
else
  printf 'eof\\n' >"$CAPTURE_ROOT/$(basename "$0").stdin"
fi
"""
            write_executable(native_probe, executable)
            write_executable(ordinary_probe, executable)
            invocation_harness = f"""#!/usr/bin/env bash
set -euo pipefail
probe_root={probe_root!s}
object_number=0
for object_path in {native_probe!s} {ordinary_probe!s}; do
  object_number=$((object_number + 1))
{argument_block}{invocation_block}done
"""
            environment = os.environ.copy()
            environment["CAPTURE_ROOT"] = str(capture_root)
            invoked = subprocess.run(
                ["/bin/bash"],
                input=invocation_harness,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(invoked.returncode, 0, invoked.stderr)
            self.assertEqual(
                (capture_root / "lmdj-native-audio-probe.args").read_text(
                    encoding="utf-8"
                ),
                "--no-device\n",
            )
            self.assertEqual(
                (capture_root / "lmdj-foundation-tests.args").read_text(
                    encoding="utf-8"
                ),
                "\n",
            )
            for stdin_capture in capture_root.glob("*.stdin"):
                self.assertEqual(
                    stdin_capture.read_text(encoding="utf-8"),
                    "eof\n",
                )

        self.assertIn(
            '"$object_path" ${probe_arguments[@]+"${probe_arguments[@]}"}',
            probe_block,
        )
        self.assertIn(
            '>"$probe_stdout" 2>"$probe_stderr" </dev/null',
            probe_block,
        )

    def test_each_topology_export_uses_its_matching_module_profile(
        self,
    ) -> None:
        runner = runner_path.read_text(encoding="utf-8")
        topology_start = runner.index('topologies_root="$run_root/topologies"')
        topology_end = runner.index(
            'for fragment_path in "$fragments_root"/*.lcov',
            topology_start,
        )
        topology_block = runner[topology_start:topology_end]

        self.assertNotIn("--empty-profile", topology_block)
        self.assertIn(
            '-instr-profile="$module_profiles_root/$object_number.profdata"',
            topology_block,
        )

    def test_missing_llvm_tools_cannot_leave_documented_stale_artifacts(
        self,
    ) -> None:
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
                fake_bin / "uname",
                "#!/bin/sh\nprintf 'Linux\\n'\n",
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
            self.assertIn("unable to locate llvm-profdata", result.stderr)
            for artifact_path in artifact_paths:
                self.assertFalse(
                    artifact_path.exists(),
                    f"stale artifact survived missing tool: {artifact_path.name}",
                )

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
