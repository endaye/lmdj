#!/usr/bin/env python3
"""Contract tests for the stable Core shell entry point."""

from __future__ import annotations

import os
from pathlib import Path
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
            ["--preset", "dev", "-L", "^(unit|component)$"],
        )

    def test_full_mode_excludes_the_stress_tier(self) -> None:
        self.assert_test_arguments(
            ("test", "dev", "full"),
            ["--preset", "dev", "-LE", "^stress$"],
        )

    def test_stress_mode_selects_only_the_stress_tier(self) -> None:
        self.assert_test_arguments(
            ("test", "dev", "stress"),
            ["--preset", "dev", "-L", "^stress$"],
        )

    def test_default_test_mode_is_full(self) -> None:
        self.assert_test_arguments(
            ("test", "dev"),
            ["--preset", "dev", "-LE", "^stress$"],
        )

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
