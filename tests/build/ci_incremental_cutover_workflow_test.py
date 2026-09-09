#!/usr/bin/env python3
"""Execute the actual cutover bridge; platform acceptance is separately gated."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
sys.path.insert(0, str(ROOT / 'tests/build'))
from ci_self_test_report_test import rep as self_test_report
import incremental_entry
from ci_self_test_report_workflow_test import block, field

SOURCE = (ROOT / '.github/workflows/self-test-report.yml').read_text()
CONTROLLER = block(SOURCE, 'controller', 2)


def step(name):
    return CONTROLLER.split('      - name: ' + name + '\n', 1)[1].split('\n      - ', 1)[0]


def inline(name):
    part = step(name).split("          python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
    return '\n'.join(line[10:] for line in part.splitlines())


class CutoverTests(unittest.TestCase):
    def invoke(self, event='push', operation='', extra=None, fail=False):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'outputs'
            env = dict(RUNNER_TEMP=temporary, GITHUB_OUTPUT=str(output),
                       GITHUB_STEP_SUMMARY=str(Path(temporary) / 'summary'),
                       GITHUB_EVENT_NAME=event, BATCH_OPERATION=operation,
                       JOURNAL_CONFIG='', BATCH_REQUEST='')
            env.update(extra or {})
            commands = []
            def run(command, **kwargs):
                commands.append(command)
                self.assertEqual(kwargs, {'check': True})
                self.assertFalse(output.exists(), 'why: action was emitted before persistence; remedy: publish only after runtime success')
                if fail:
                    raise subprocess.CalledProcessError(1, command)
                Path(command[command.index('--output') + 1]).write_text(json.dumps({
                    'action': 'idle', 'request': None, 'executor': {'run_id': 17, 'attempt': 1}}))
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(subprocess, 'run', side_effect=run), \
                    mock.patch.object(incremental_entry, 'load_storage', return_value={'scheduler': {'fixed': True}}) as storage:
                try:
                    exec(compile(inline('Reconcile the isolated journal under the short writer lock'), '<actual-cutover-bridge>', 'exec'), {})
                except BaseException:
                    self.assertFalse(output.exists())
                    raise
                content = output.read_text()
                return commands, content, storage.call_count

    def test_all_automatic_events_use_real_entry_and_publish_only_after_persistence(self):
        for event in ('push', 'schedule', 'workflow_run'):
            with self.subTest(event=event):
                commands, content, storage = self.invoke(event)
                self.assertEqual(commands[0][:3], ['python3', 'scripts/ci/incremental_entry.py', 'control'])
                self.assertNotIn('--config', commands[0])
                self.assertEqual(storage, 0)
                self.assertEqual(content, 'action=idle\nrequest=null\nexecutor={"run_id":17,"attempt":1}\n')

    def test_control_failure_never_emits_execution_output(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(fail=True)

    def test_manual_full_uses_fixed_default_and_existing_runtime(self):
        commands, _, storage = self.invoke('workflow_dispatch', 'reconcile',
            {'BATCH_REQUEST': '{"id":"candidate-one","kind":"candidate","target":"' + 'a' * 40 + '"}'})
        self.assertEqual(commands[0][:3], ['python3', 'scripts/ci/batch_runtime.py', 'reconcile'])
        self.assertIn('--request', commands[0])
        self.assertEqual(storage, 1)

    def test_default_production_storage_cannot_be_initialized(self):
        with self.assertRaisesRegex(SystemExit, 'why:.*remedy:'):
            self.invoke('workflow_dispatch', 'init')

    def test_mixed_legacy_probe_and_review_arguments_reject_before_runtime(self):
        for key in ('REPORT_CONFIG', 'PROBE_REQUEST', 'LEGACY_RUN_ID', 'REVIEW_RUN_ID', 'REVIEW_ATTEMPT'):
            with self.subTest(key=key), self.assertRaisesRegex(SystemExit, 'why:.*remedy:'):
                self.invoke('workflow_dispatch', 'reconcile', {key: 'unexpected'})

    def test_execute_releases_writer_without_report_or_discovery(self):
        for name in ('Report durable observations independently', 'Recover missed review observations independently'):
            body = step(name)
            self.assertIn("steps.control.outputs.action != 'execute'", field(body, 'if', 8))
            self.assertIn("steps.control.outcome == 'success'", field(body, 'if', 8))
            self.assertIn('always()', field(body, 'if', 8))
            self.assertEqual(field(body, 'continue-on-error', 8), 'true')
        self.assertIn('exit 1', step('Keep unresolved reporting visible'))
        self.assertNotIn('concurrency:', block(SOURCE, 'execute-batch', 2))
        discovery = field(step('Recover missed review observations independently'), 'if', 8)
        self.assertIn("github.event_name != 'workflow_run' || github.event.workflow_run.path == '.github/workflows/pr-review.yml'", discovery)

    def test_review_wakeups_are_coalesced_into_main_and_health_observations(self):
        events = block(SOURCE, 'on', 0)
        self.assertEqual(field(block(events, 'push', 2), 'branches', 4), '[main]')
        callbacks = block(events, 'workflow_run', 2)
        self.assertNotIn('branches:', callbacks)
        self.assertEqual(field(callbacks, 'workflows', 4), '["Incremental Completion", "Core CI"]',
                         'why: PR-only review activity must not start a scheduler/relay chain; remedy: discover retained review evidence on main/health observations and keep product completion callbacks')
        self.assertIn('"7,22,37,52 * * * *"', block(events, 'schedule', 2))
        self.assertNotIn('self_test_report.py', SOURCE)

    def test_coalesced_review_discovery_preserves_reporting_and_exact_manual_recovery(self):
        discovery = step('Recover missed review observations independently')
        self.assertIn('scripts/ci/review_discovery_runtime.py', discovery)
        self.assertIn('--limit 1 --background', discovery)
        self.assertIn("steps.control.outputs.action != 'execute'", field(discovery, 'if', 8))
        manual = step('Report through the isolated outbox under the short writer lock')
        self.assertIn("'report-discovery'", manual)
        manual_directives = '\n'.join(line for line in manual.splitlines() if not line.lstrip().startswith('#'))
        self.assertNotIn('--background', manual_directives,
                         'why: manual discovery must remain strict; remedy: allow pending only in automatic scans')
        self.assertIn("['--run-id', run_id, '--attempt', attempt]", manual)
        # Immediate review callbacks are retired, not their authenticated
        # compatibility handler or recovery of already durable review records.
        self.assertIn('Report durable observations independently', SOURCE)
        self.assertIn("'report-review': 'review'", manual)

    def test_actual_discovery_condition_excludes_idle_completion_scans(self):
        condition = field(step('Recover missed review observations independently'), 'if', 8)[3:-2].strip()
        for event, path, action, outcome, expected in (
            ('push', '', 'idle', 'success', True),
            ('schedule', '', 'idle', 'success', True),
            ('push', '', 'execute', 'success', False),
            ('workflow_run', '.github/workflows/self-test-report.yml', 'idle', 'success', False),
            ('workflow_run', '.github/workflows/incremental-completion.yml', 'idle', 'success', False),
            ('workflow_run', '.github/workflows/ci.yml', 'idle', 'success', False),
            ('workflow_run', '.github/workflows/pr-review.yml', 'idle', 'success', True),
            ('workflow_run', '.github/workflows/forged.yml', 'idle', 'success', False),
            ('workflow_run', '.github/workflows/pr-review.yml', 'idle', 'failure', False),
            ('workflow_dispatch', '', 'idle', 'success', False),
        ):
            with self.subTest(event=event, path=path, action=action, outcome=outcome):
                expression = condition
                for key, value in {'github.event_name': event, 'github.event.workflow_run.path': path, 'github.event.schedule': '',
                                   'steps.control.outputs.action': action, 'steps.control.outcome': outcome}.items():
                    expression = expression.replace(key, repr(value))
                expression = expression.replace('always()', 'True').replace('&&', ' and ').replace('||', ' or ')
                self.assertIs(eval(expression, {'__builtins__': {}}), expected)

    def test_retired_writer_cli_is_failclosed_before_any_api(self):
        with mock.patch.object(self_test_report, 'UrllibGitHubApi') as api:
            for command in (['report', '--run-id', '17'], ['missing', '--date', '2026-09-08']):
                self.assertEqual(self_test_report.main(command), 2)
            api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
