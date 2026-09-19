#!/usr/bin/env python3
"""Contract tests for the stable Core shell entry point."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_SCRIPT = REPO_ROOT / "scripts" / "core.sh"


class CoreScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-core-script-")
        self.temporary_root = Path(self.temporary.name)
        self.arguments_path = self.temporary_root / "ctest.arguments"
        fake_ctest = self.temporary_root / "ctest"
        fake_ctest.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf '%s\\n' \"$@\" >\"$LMDJ_CTEST_ARGUMENTS\"\n",
            encoding="utf-8",
        )
        fake_ctest.chmod(0o755)
        self.environment = os.environ.copy()
        self.environment["PATH"] = (
            f"{self.temporary_root}{os.pathsep}{self.environment['PATH']}"
        )
        self.environment["LMDJ_CTEST_ARGUMENTS"] = str(self.arguments_path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_core(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(CORE_SCRIPT), *arguments],
            cwd=REPO_ROOT,
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def assert_test_arguments(
        self,
        invocation: tuple[str, ...],
        expected: list[str],
    ) -> None:
        completed = self.run_core(*invocation)
        self.assertEqual(
            completed.returncode,
            0,
            (completed.stdout, completed.stderr),
        )
        self.assertEqual(
            self.arguments_path.read_text(encoding="utf-8").splitlines(),
            expected,
        )

    def test_fast_mode_selects_only_unit_and_component_tiers(self) -> None:
        self.assert_test_arguments(
            ("test", "dev", "fast"),
            ["--preset", "dev", "-L", "^(unit|component)$", "-E", "^build\\.release_"],
        )

    def test_full_mode_excludes_the_stress_tier(self) -> None:
        self.assert_test_arguments(
            ("test", "dev", "full"),
            ["--preset", "dev", "-LE", "^stress$", "-E", "^build\\.release_"],
        )

    def test_stress_mode_selects_only_the_stress_tier(self) -> None:
        self.assert_test_arguments(
            ("test", "dev", "stress"),
            ["--preset", "dev", "-L", "^stress$"],
        )

    def test_default_test_mode_is_full(self) -> None:
        self.assert_test_arguments(
            ("test", "dev"),
            ["--preset", "dev", "-LE", "^stress$", "-E", "^build\\.release_"],
        )

    def test_tsan_preset_selects_all_native_tests(self) -> None:
        presets = json.loads(
            (REPO_ROOT / "CMakePresets.json").read_text(encoding="utf-8")
        )
        tsan = next(
            preset
            for preset in presets["testPresets"]
            if preset["name"] == "tsan"
        )
        self.assertEqual(
            tsan["filter"],
            {"include": {"label": "^native$"}},
        )

    def test_stress_mode_cannot_select_release_tooling_entries(self) -> None:
        # The stress selector needs no name exclusion: no build.release_*
        # entry carries the stress tier label.
        cmake_source = (REPO_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        registrations = re.findall(
            r'lmdj_add_test\(\s*NAME "?build\.release_[^\n]*\n\s*TIER (\w+)',
            cmake_source,
        )
        self.assertGreater(len(registrations), 0)
        self.assertNotIn("stress", registrations)

    def test_coverage_preset_excludes_release_tooling_entries(self) -> None:
        presets = json.loads(
            (REPO_ROOT / "CMakePresets.json").read_text(encoding="utf-8")
        )
        coverage = next(
            preset
            for preset in presets["testPresets"]
            if preset["name"] == "coverage"
        )
        excluded = re.compile(coverage["filter"]["exclude"]["name"])
        self.assertIsNotNone(excluded.match("build.release_candidate_transition_journey"))
        self.assertIsNone(excluded.match("build.release"))
        self.assertIsNone(excluded.match("facade.candidate_store"))

    def test_proof_release_ctest_excludes_stress_label_and_release_tooling(self) -> None:
        script_source = CORE_SCRIPT.read_text(encoding="utf-8")
        proof_source = script_source.split("  proof)\n", maxsplit=1)[1].split(
            "  clean)\n", maxsplit=1
        )[0]
        self.assertIn(
            """ctest \\
      --test-dir "$release_root" \\
      --output-on-failure \\
      -E '^(build\\.active_tree|build\\.version|build\\.release_|contract\\.schemas|conformance\\.|host\\.|e2e\\.)' \\
      -LE '^stress$'""",
            proof_source,
        )

    def test_proof_reports_product_build_from_version_authority(self) -> None:
        script_source = CORE_SCRIPT.read_text(encoding="utf-8")
        proof_source = script_source.split("  proof)\n", maxsplit=1)[1].split(
            "  clean)\n", maxsplit=1
        )[0]
        self.assertIn(
            'product_tag="$(python3 scripts/version.py tag-name '
            '--version-file products/lmdj/version.json)"',
            proof_source,
        )
        self.assertIn(
            'echo "Product Build: ${product_tag#lmdj-v}"',
            proof_source,
        )
        self.assertNotRegex(proof_source, r'Product Build: [0-9]+(?:\.[0-9]+){3}')

    def test_unknown_test_mode_is_a_usage_error(self) -> None:
        completed = self.run_core("test", "dev", "unknown")
        self.assertEqual(completed.returncode, 64)
        self.assertFalse(self.arguments_path.exists())

    def test_test_rejects_zero_or_three_arguments(self) -> None:
        for arguments in (("test",), ("test", "dev", "full", "extra")):
            with self.subTest(arguments=arguments):
                completed = self.run_core(*arguments)
                self.assertEqual(completed.returncode, 64)
                self.assertFalse(self.arguments_path.exists())

    def test_configure_and_build_still_require_exactly_one_preset(self) -> None:
        for command in ("configure", "build"):
            for arguments in ((), ("dev", "extra")):
                with self.subTest(command=command, arguments=arguments):
                    completed = self.run_core(command, *arguments)
                    self.assertEqual(completed.returncode, 64)


if __name__ == "__main__":
    unittest.main()
