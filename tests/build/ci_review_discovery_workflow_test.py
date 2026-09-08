"""Manual discovery routes exact data to one CLI; no scheduler execution."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts/ci'), str(ROOT / 'tests/build')]
from ci_self_test_report_workflow_test import block, field


class DiscoveryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / '.github/workflows/self-test-report.yml').read_text()
        self.controller = block(self.source, 'controller', 2)
        step = self.controller.split('      - name: Report through the isolated outbox under the short writer lock\n', 1)[1].split('      - name:', 1)[0]
        self.code = '\n'.join(line[10:] for line in step.split("          python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0].splitlines())

    def invoke(self, extra=None, code=0, actual=False):
        with tempfile.TemporaryDirectory() as directory:
            summary, output = Path(directory) / 'summary', Path(directory) / 'output'
            env = {'REPORT_OPERATION': 'report-discovery', 'REPORT_LIMIT': '8',
                   'RUNNER_TEMP': directory, 'GITHUB_STEP_SUMMARY': str(summary), 'GITHUB_OUTPUT': str(output),
                   **(extra or {})}
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                self.assertEqual(command[:2], ['python3', 'scripts/ci/review_discovery_runtime.py'])
                self.assertEqual(kwargs, {'check': False})
                self.assertEqual(set(command[2::2]), {'--root', '--summary', '--limit'} |
                                 ({'--run-id', '--attempt'} if env.get('REVIEW_RUN_ID') else set()))
                if actual:
                    module = importlib.import_module('review_discovery_runtime')
                    instance = mock.Mock()
                    instance.run.return_value = {'status': 'incomplete' if code else 'inventoried-only'}
                    with mock.patch.object(module, 'DiscoveryRuntime', return_value=instance):
                        outcome = module.main(command[2:])
                    instance.run.assert_called_once_with(int(env['REPORT_LIMIT']),
                        int(env['REVIEW_RUN_ID']) if env.get('REVIEW_RUN_ID') else None,
                        int(env['REVIEW_ATTEMPT']) if env.get('REVIEW_ATTEMPT') else None)
                else:
                    outcome = code
                return subprocess.CompletedProcess(command, outcome)
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(subprocess, 'run', side_effect=run):
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(self.code, '<actual-discovery-workflow>', 'exec'), {})
            self.assertFalse(output.exists(), 'why: discovery emitted scheduler output; remedy: keep report-only boundary')
            self.assertFalse((Path(directory) / 'incremental-controller/result.json').exists())
            return stopped.exception.code, calls, summary.read_text() if summary.exists() else ''

    def test_scan_and_exact_attempt_invoke_once_without_fallthrough(self):
        for extra in ({}, {'REVIEW_RUN_ID': '51', 'REVIEW_ATTEMPT': '2'}):
            with self.subTest(extra=extra):
                code, calls, _ = self.invoke(extra)
                self.assertEqual(code, 0)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][calls[0].index('--limit') + 1], '8')

    def test_cli_nonzero_is_not_hidden(self):
        for status in (0, 1, 86):
            with self.subTest(status=status):
                code, calls, _ = self.invoke(code=status)
                self.assertEqual(code, status)
                self.assertEqual(len(calls), 1)

    def test_mixed_or_invalid_inputs_reject_before_subprocess(self):
        pairs = [('REPORT_CONFIG', '{}'), ('JOURNAL_CONFIG', '{}'), ('BATCH_REQUEST', '{}'),
                 ('PROBE_REQUEST', '{}'), ('LEGACY_RUN_ID', '17'), ('LEGACY_RECONCILE', 'true'),
                 ('REVIEW_RUN_ID', '51'), ('REVIEW_ATTEMPT', '1'), ('REPORT_LIMIT', '0'),
                 ('REPORT_LIMIT', '33'), ('REPORT_LIMIT', '8; touch /bad')]
        for key, value in pairs:
            with self.subTest(key=key, value=value):
                code, calls, _ = self.invoke({key: value})
                self.assertIn('why:', code)
                self.assertIn('remedy:', code)
                self.assertEqual(calls, [])
        for value in ('0', '-1', '1.0', 'true', '1\n2'):
            with self.subTest(value=value):
                code, calls, _ = self.invoke({'REVIEW_RUN_ID': value, 'REVIEW_ATTEMPT': '1'})
                self.assertIn('why:', code)
                self.assertEqual(calls, [])

    def test_actual_cli_parser_summary_and_incomplete_exit(self):
        for code in (0, 1):
            with self.subTest(code=code):
                actual, calls, summary = self.invoke({'REVIEW_RUN_ID': '51', 'REVIEW_ATTEMPT': '2'}, code=code, actual=True)
                self.assertEqual(actual, code)
                self.assertEqual(len(calls), 1)
                self.assertIn('not scheduler execution', summary)

    def test_manual_operation_existing_lock_and_no_output(self):
        condition = field(self.controller, 'if', 4)
        for value in ("github.event_name == 'workflow_dispatch'", "github.ref == 'refs/heads/main'",
                      "github.run_attempt == '1'"):
            self.assertIn(value, condition)
        self.assertIn('group: self-test-report', self.controller)
        self.assertEqual(self.controller.count('BATCH_WRITER_LOCK: self-test-report'), 7)
        self.assertNotIn('${{', self.code)


if __name__ == '__main__':
    unittest.main()
