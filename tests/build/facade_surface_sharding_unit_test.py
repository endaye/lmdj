#!/usr/bin/env python3
"""Focused regressions for the Facade surface sharding build gate."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("facade_surface_sharding_test.py")
SPEC = importlib.util.spec_from_file_location("facade_surface_sharding", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
SHARDING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDING)


class FacadeSurfaceShardingTest(unittest.TestCase):
    def test_extra_registration_for_binary_is_rejected(self) -> None:
        executable = Path("/tmp/lmdj_facade_sequence_surface_tests")
        expected = {
            "facade.sequence_surface": "lifecycle",
            "facade.sequence_surface.recovery": "recovery",
        }
        registrations = {
            "facade.sequence_surface": [
                str(executable.resolve()),
                "--shard=lifecycle",
            ],
            "facade.sequence_surface.recovery": [
                str(executable.resolve()),
                "--shard=recovery",
            ],
            "facade.sequence_switch_rebase": [
                str(executable.resolve()),
                "--switch-rebase-only",
            ],
        }

        errors = SHARDING.validate_registrations(
            executable, expected, registrations
        )

        self.assertEqual(len(errors), 1)
        self.assertIn("facade.sequence_switch_rebase", errors[0])
        self.assertIn("unexpected", errors[0])

    def test_unconfigured_build_directory_returns_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            errors = SHARDING.validate(Path(directory))

        self.assertTrue(errors)
        self.assertIn("--list-shards failed", errors[0])


if __name__ == "__main__":
    unittest.main()
