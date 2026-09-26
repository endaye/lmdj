#!/usr/bin/env python3
"""Static contract for scheduled read-only release drift reporting."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.target_validation import validate_current_product_snapshot
WORKFLOW = ROOT / ".github/workflows/release-audit.yml"
ACTION_PINS = {
    "actions/checkout": ("de0fac2e4500dabe0009e67214ff5f5447ce83dd", "v6.0.2"),
    "actions/setup-node": ("249970729cb0ef3589644e2896645e5dc5ba9c38", "v6.5.0"),
    "actions/upload-artifact": ("b7c566a772e6b6bfb58ed0dc250532a479d7789f", "v6.0.0"),
}


class ReleaseAuditWorkflowTest(unittest.TestCase):
    def source(self) -> str:
        self.assertTrue(WORKFLOW.is_file(), "release audit workflow is missing")
        return WORKFLOW.read_text(encoding="utf-8")

    def test_triggers_main_push_weekly_schedule_and_manual_dispatch(self) -> None:
        source = self.source()
        self.assertRegex(source, r"(?m)^  push:\n    branches: \[main\]$")
        self.assertRegex(source, r"(?m)^  schedule:\n    - cron: '0 3 \* \* 1'$")
        self.assertRegex(source, r"(?m)^  workflow_dispatch:\s*$")

    def test_workflow_is_read_only_bounded_and_non_cancelling(self) -> None:
        source = self.source()
        self.assertRegex(source, r"(?ms)^permissions:\n  contents: read\n  actions: read$")
        self.assertIn("timeout-minutes: 15", source)
        self.assertRegex(source, r"(?ms)^concurrency:\n  group: release-audit-.*\n  cancel-in-progress: false$")
        lowered = source.lower()
        for forbidden in (
            "contents: write", "deploy", "netlify", "repository_dispatch",
            "secrets.", "pull-requests: write", "issues: write",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_event_selects_local_or_remote_audit_and_always_uploads_json(self) -> None:
        source = self.source()
        self.assertIn('scripts/release.sh audit --local --json "$REPORT_PATH"', source)
        self.assertIn('scripts/release.sh audit --remote --json "$REPORT_PATH"', source)
        self.assertIn("github.event_name == 'push'", source)
        upload = source[source.index("actions/upload-artifact@"):]
        self.assertIn("if: always()", upload)
        self.assertIn("path: build/release/audit/report.json", upload)
        self.assertIn("if-no-files-found: error", upload)

    def test_job_provisions_every_toolchain_the_static_audit_shells_out_to(self) -> None:
        source = self.source()
        target_validation = (ROOT / "tools/release/target_validation.py").read_text(encoding="utf-8")
        self.assertIn('"python3", "scripts/version.py", "verify"', target_validation)
        self.assertIn("name: Select standalone system Python", source)
        self.assertIn("uses: actions/setup-node@", source)
        self.assertIn('node-version: "26"', source)

    def assert_snapshot_node_call(self, *, current: bool, historical_script: bool) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            lock = root / 'products/lmdj/assembly.lock.json'
            lock.parent.mkdir(parents=True)
            lock.write_bytes(b'{"fixture":"exact lock bytes"}\n')
            metadata = root / 'apps/architecture-portal/versioned_metadata/version-1.0.1.0.json'
            metadata.parent.mkdir(parents=True)
            metadata.write_text(json.dumps({'product_build': '1.0.1.0',
                'assembly_lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest()}))
            sites = (['apps/docs-site'] if current else []) + (['apps/architecture-portal'] if historical_script else [])
            for site in sites:
                script = root / site / 'scripts/check-release-docs.mjs'
                script.parent.mkdir(parents=True)
                script.write_text('// fixture only; never executed\n')
            calls = []
            class RecordingRunner:
                def run(self, argv, *, cwd):
                    calls.append((list(argv), cwd))
            with patch('tools.release.target_validation.CommandRunner.run',
                       side_effect=AssertionError('why: real command execution is outside this fixture; remedy: retain the recording runner')):
                validate_current_product_snapshot(root, '1.0.1.0', runner=RecordingRunner())
            site = 'apps/docs-site' if current else 'apps/architecture-portal'
            self.assertEqual(calls, [(['node', f'{site}/scripts/check-release-docs.mjs'], root)])

    def test_snapshot_validator_invokes_current_docs_site_with_node(self) -> None:
        self.assert_snapshot_node_call(current=True, historical_script=False)

    def test_snapshot_validator_invokes_historical_portal_with_node(self) -> None:
        self.assert_snapshot_node_call(current=False, historical_script=True)

    def test_snapshot_validator_prefers_docs_site_when_both_scripts_exist(self) -> None:
        self.assert_snapshot_node_call(current=True, historical_script=True)

    def test_fresh_runner_fetch_credential_is_env_scoped_and_intents_hydrate_first(self) -> None:
        source = self.source()
        self.assertLess(
            source.index("Hydrate release intent target objects"),
            source.index("Audit release identity and drift"),
        )
        credential = (
            "GIT_CONFIG_KEY_0: "
            "url.https://x-access-token:${{ github.token }}@github.com/.insteadOf"
        )
        self.assertEqual(source.count('GIT_CONFIG_COUNT: "1"'), 2)
        self.assertEqual(source.count(credential), 2)
        self.assertEqual(source.count("GIT_CONFIG_VALUE_0: https://github.com/"), 2)

    def test_actions_are_exactly_pinned_and_checkout_has_no_credentials(self) -> None:
        source = self.source()
        uses_lines = [line.strip() for line in source.splitlines() if "uses:" in line]
        self.assertEqual(len(uses_lines), 3)
        for line in uses_lines:
            match = re.fullmatch(
                r"-?\s*uses: (actions/[a-z-]+)@([0-9a-f]{40}) # (v[0-9]+(?:\.[0-9]+){1,2})",
                line,
            )
            self.assertIsNotNone(match, f"action is not pinned: {line}")
            assert match is not None
            self.assertEqual((match.group(2), match.group(3)), ACTION_PINS[match.group(1)])
        self.assertIn("fetch-depth: 0", source)
        self.assertIn("persist-credentials: false", source)


if __name__ == "__main__":
    unittest.main()
