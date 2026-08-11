#!/usr/bin/env python3
"""Contract tests for the reusable Architecture Portal workflow."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/architecture-portal.yml"


class ArchitecturePortalWorkflowTopologyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def called_impact_step(self) -> str:
        match = re.search(
            r"^      - name: Check Pull Request documentation impact\n"
            r"(?P<body>        if: \$\{\{ inputs\.check_documentation_impact \}\}\n"
            r".*?)(?=^      - name:|\Z)",
            self.source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, "called documentation-impact step is missing")
        assert match is not None
        return match.group("body")

    def test_portal_exposes_workflow_call_with_typed_inputs(self) -> None:
        expected = '''  workflow_call:
    inputs:
      check_documentation_impact:
        required: false
        type: boolean
        default: false
      base_sha:
        required: false
        type: string
        default: ""
      head_sha:
        required: false
        type: string
        default: ""
'''
        self.assertIn(expected, self.source)

    def test_portal_impact_check_uses_explicit_base_and_head_inputs(self) -> None:
        step = self.called_impact_step()
        self.assertIn("if: ${{ inputs.check_documentation_impact }}", step)
        self.assertIn("PORTAL_BASE_SHA: ${{ inputs.base_sha }}", step)
        self.assertIn("PORTAL_HEAD_SHA: ${{ inputs.head_sha }}", step)
        self.assertIn(
            'git diff --name-only "$PORTAL_BASE_SHA" "$PORTAL_HEAD_SHA"', step
        )
        self.assertNotIn("github.event.pull_request.base.sha", step)
        self.assertNotIn("github.event.pull_request.head.sha", step)

    def test_portal_reusable_job_keeps_fetch_depth_zero_node_22_and_full_check(self) -> None:
        self.assertIn("fetch-depth: 0", self.source)
        self.assertIn('node-version: "22"', self.source)
        self.assertIn("scripts/architecture-portal.sh check", self.source)

    def test_portal_does_not_use_checks_api_or_cross_run_polling(self) -> None:
        for forbidden in ("api.github.com", "/check-runs", "gh api"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)
        self.assertNotRegex(self.source, r"(?im)^\s*(while|until)\b")


if __name__ == "__main__":
    unittest.main()
