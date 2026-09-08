"""Actual manual probe boundary; no remote mutation or hosted fault claim."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts/ci'), str(ROOT / 'tests/build')]
from ci_self_test_report_workflow_test import block, field, scalars
import o1_recovery_probe as probe


class ProbeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / '.github/workflows/self-test-report.yml').read_text()
        self.controller = block(self.source, 'controller', 2)
        self.step = self.controller.split('      - name: Run the isolated recovery response probe\n', 1)[1].split('      - uses:', 1)[0]
        self.code = '\n'.join(line[10:] for line in self.step.split("          python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0].splitlines())

    def invoke(self, *, extra=None, real=False, returncode=0):
        with tempfile.TemporaryDirectory() as directory:
            base = {'repository': 'endaye/lmdj', 'issue_number': 900, 'issue_node_id': 'isolated-a',
                    'bot_node_id': 'bot', 'workflow_id': 7, 'epoch': 'o1-recovery-a'}
            config = {'scheduler': base, 'outbox': {**base, 'issue_number': 901, 'issue_node_id': 'isolated-b', 'epoch': 'o1-recovery-b'}}
            env = {'RUNNER_TEMP': directory, 'GITHUB_STEP_SUMMARY': str(Path(directory) / 'summary'),
                   'GITHUB_OUTPUT': str(Path(directory) / 'outputs'), 'BATCH_OPERATION': 'recovery-probe',
                   'REPORT_CONFIG': json.dumps(config), 'PROBE_REQUEST': json.dumps({'operation': probe.A}),
                   'GITHUB_REPOSITORY': 'endaye/lmdj', 'GITHUB_RUN_ID': '17', 'GITHUB_RUN_ATTEMPT': '1',
                   'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': 'a' * 40, 'BATCH_WRITER_LOCK': 'self-test-report',
                   'GITHUB_TOKEN': 'test-only-not-a-token', **(extra or {})}
            calls = []
            def execute(command, **kwargs):
                calls.append(command)
                self.assertEqual(command[:2], ['python3', 'scripts/ci/o1_recovery_probe.py'])
                self.assertEqual(set(command[2::2]), {'--config', '--request', '--root', '--summary'})
                self.assertEqual(kwargs, {'check': False})
                for flag, key in (('--config', 'REPORT_CONFIG'), ('--request', 'PROBE_REQUEST')):
                    self.assertEqual(Path(command[command.index(flag) + 1]).read_text(), env[key])
                code = probe.main(command[2:]) if real else returncode
                return subprocess.CompletedProcess(command, code)
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(subprocess, 'run', side_effect=execute), mock.patch(
                    'self_test_report.UrllibGitHubApi._request', side_effect=AssertionError('why: disabled probe called API; remedy: remain inert')):
                with self.assertRaises(SystemExit) as raised:
                    exec(compile(self.code, '<actual-probe-workflow>', 'exec'), {})
            self.assertFalse(Path(env['GITHUB_OUTPUT']).exists(), 'why: probe emitted executor outputs; remedy: no GITHUB_OUTPUT bridge')
            summary = Path(env['GITHUB_STEP_SUMMARY'])
            return raised.exception.code, calls, summary.read_text() if summary.exists() else ''

    def test_real_cli_default_disabled_uses_actual_flags_without_api(self):
        code, calls, summary = self.invoke(real=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn('"status": "disabled"', summary)

    def test_json_is_exact_file_data_not_interpolated_source(self):
        code, calls, _ = self.invoke(extra={'PROBE_REQUEST': '{"text":"$(touch /nope)\\n\'\\\"${{ github.token }}"}'})
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('${{', self.code)

    def test_real_cli_rejects_null_instead_of_enabling_probe(self):
        code, _, summary = self.invoke(real=True, extra={'PROBE_REQUEST': 'null'})
        self.assertEqual(code, 1)
        self.assertIn('"status": "error"', summary)

    def test_actual_process_exit86_and_other_failures_stay_nonzero(self):
        for expected in (1, 86):
            code, calls, _ = self.invoke(returncode=expected)
            self.assertEqual(code, expected, 'why: probe failure hidden; remedy: propagate the actual subprocess status')
            self.assertEqual(len(calls), 1)

    def test_mixed_inputs_rejected_before_cli(self):
        for key, value in [('BATCH_OPERATION', 'resume'), ('JOURNAL_CONFIG', '{}'), ('BATCH_REQUEST', '{}'),
                           ('LEGACY_RUN_ID', '7'), ('LEGACY_RECONCILE', 'true'), ('REVIEW_RUN_ID', '7'),
                           ('REVIEW_ATTEMPT', '1'), ('REPORT_LIMIT', '9'), ('REPORT_CONFIG', ''), ('PROBE_REQUEST', '')]:
            with self.subTest(key=key):
                code, calls, _ = self.invoke(extra={key: value})
                self.assertIn('why:', code)
                self.assertIn('remedy:', code)
                self.assertFalse(calls)

    def test_manual_main_first_attempt_guard_and_existing_authority(self):
        condition = field(self.controller, 'if', 4)
        for guard in ("github.event_name == 'workflow_dispatch'", "github.ref == 'refs/heads/main'",
                      "github.run_attempt == '1'"):
            self.assertIn(guard, condition)
        self.assertEqual(scalars(block(self.controller, 'permissions', 4), 6),
                         {'contents': 'read', 'actions': 'read', 'issues': 'write'})
        self.assertIn('group: self-test-report', self.controller)
        self.assertIn('BATCH_WRITER_LOCK: self-test-report', self.step)
        self.assertNotIn('continue-on-error:', self.step)

    def test_no_outputs_no_artifact_and_no_automatic_trigger_change(self):
        self.assertNotIn('GITHUB_OUTPUT', self.step)
        self.assertNotIn('--output', self.step)
        self.assertNotIn('continue-on-error', self.step)
        self.assertIn("if: ${{ inputs.batch_operation == 'recovery-probe' }}", self.step)
        self.assertIn("!startsWith(inputs.batch_operation, 'report-') && inputs.batch_operation != 'recovery-probe'", self.controller)
        events = block(self.source, 'on', 0)
        self.assertIn('workflows: ["Incremental Completion", "Core CI"]', events)
        self.assertIn('cron: "7,22,37,52 * * * *"', events)
        self.assertIn('  push:', events)
        inputs = block(block(events, 'workflow_dispatch', 2), 'inputs', 4)
        self.assertIn('default: reconcile', inputs)
        self.assertIn('probe_request:', inputs)


if __name__ == '__main__':
    unittest.main()
