#!/usr/bin/env python3
"""The retired queue control plane must not return to the live topology."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
RETIRED_PATHS = (
    ".github/workflows/merge-queue.yml",
    "scripts/ci/merge_queue.py",
    "scripts/ci/merge_queue_watchdog.py",
    "scripts/ci/pr_gate.py",
    "scripts/ci/github_queue_api.py",
)
INVENTORY_TEST = Path(__file__).relative_to(ROOT).as_posix()


class RetiredQueueMechanismsTest(unittest.TestCase):
    def test_retired_control_plane_paths_are_absent(self) -> None:
        tracked = set(
            subprocess.run(
                ("git", "ls-files", "-z"),
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout.decode().split("\0")
        )
        tracked.discard(INVENTORY_TEST)
        for relative in RETIRED_PATHS:
            with self.subTest(path=relative):
                self.assertFalse(
                    relative in tracked or (ROOT / relative).exists(),
                    "why: a retired queue control-plane path is live again; "
                    "remedy: remove the mechanism and its workflow consumer",
                )

    def test_scope_policy_has_no_rule_for_retired_workflow(self) -> None:
        policy = json.loads(
            (ROOT / "scripts/ci/scope_policy.json").read_text(encoding="utf-8")
        )
        retired_workflow = ".github/workflows/merge-queue.yml"
        for rule in policy["full_rules"]:
            self.assertNotEqual(
                rule.get("match", {}).get("value"),
                retired_workflow,
                "why: scope policy still routes the retired queue workflow; "
                "remedy: remove its exact rule",
            )


if __name__ == "__main__":
    unittest.main()
