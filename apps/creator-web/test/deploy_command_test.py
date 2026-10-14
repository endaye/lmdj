#!/usr/bin/env python3
"""The shared Web Host deploy command suite, bound to the Creator Web Host entry point."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "web-runtime-host/test"))
import deploy_command_harness as harness  # noqa: E402


class DeployCommandTest(harness.DeployCommandCases, unittest.TestCase):
    HOST = harness.CREATOR


class HarnessIsolationTest(harness.HarnessIsolationCases, unittest.TestCase):
    pass


if __name__ == "__main__":
    sys.exit(harness.main(sys.argv))
