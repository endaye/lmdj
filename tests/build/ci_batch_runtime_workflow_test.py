#!/usr/bin/env python3
"""Manual wiring contracts; not real Actions queue/permission acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/build'))
sys.path.insert(0, str(ROOT / 'scripts/ci'))
from ci_self_test_report_workflow_test import block, field, scalars
import batch_execution
import incremental_batch
import test_scope


class RehearsalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / '.github/workflows/self-test-report.yml').read_text()
        self.control = block(self.source, 'controller', 2)
        self.executor = block(self.source, 'execute-batch', 2)

    def test_automatic_triggers_stay_legacy_until_o1(self):
        events = block(self.source, 'on', 0)
        self.assertNotIn('  push:', events)
        self.assertIn('workflows: ["Core CI"]', events)
        self.assertIn('cron: "0 18 * * *"', events)
        condition = field(self.control, 'if', 4)
        self.assertIn("github.event_name == 'workflow_dispatch'", condition)
        self.assertIn("github.ref == 'refs/heads/main'", condition)
        self.assertIn("inputs.batch_operation == 'settle'", condition)

    def test_lock_belongs_to_short_writers_not_executor(self):
        self.assertNotRegex(self.source, r'(?m)^concurrency:')
        for job in ('report', 'controller'):
            self.assertEqual(scalars(block(block(self.source, job, 2), 'concurrency', 4), 6),
                             {'group': 'self-test-report', 'cancel-in-progress': 'false', 'queue': 'max'})
        self.assertNotIn('concurrency:', self.executor)

    def test_controller_uses_exact_main_run_code_with_full_history(self):
        self.assertIn('ref: ${{ github.sha }}', self.control)
        self.assertIn('fetch-depth: 0', self.control)
        self.assertIn('persist-credentials: false', self.control)
        self.assertIn('name: Incremental batch controller', self.control)
        self.assertIn('BATCH_WRITER_LOCK: self-test-report', self.control)

    def test_only_short_controller_has_existing_issue_write(self):
        self.assertEqual(scalars(block(self.control, 'permissions', 4), 6),
                         {'contents': 'read', 'actions': 'read', 'issues': 'write'})
        self.assertEqual(scalars(block(self.executor, 'permissions', 4), 6),
                         {'contents': 'read', 'actions': 'read'})
        self.assertNotIn('secrets: inherit', self.source)
        self.assertNotIn('pull-requests:', self.source)
        self.assertNotIn('actions: write', self.source)

    def test_only_execute_action_reaches_reusable_suites(self):
        self.assertEqual(field(self.executor, 'if', 4), "${{ needs.controller.outputs.action == 'execute' }}")
        self.assertEqual(field(self.executor, 'uses', 4), './.github/workflows/ci.yml')
        self.assertEqual(scalars(block(self.executor, 'with', 4), 6), {
            'batch_request': '${{ needs.controller.outputs.request }}',
            'batch_executor': '${{ needs.controller.outputs.executor }}'})

    def invoke(self, operation, request='', *, fail=False, result=None):
        code = self.control.split("          python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
        code = '\n'.join(line[10:] for line in code.splitlines())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'outputs'
            env = {'RUNNER_TEMP': directory, 'GITHUB_OUTPUT': str(output),
                   'GITHUB_STEP_SUMMARY': str(Path(directory) / 'summary'),
                   'JOURNAL_CONFIG': '{"opaque":"config"}',
                   'BATCH_OPERATION': operation, 'BATCH_REQUEST': request}
            commands = []
            def run(command, **kwargs):
                commands.append(command)
                self.assertTrue(kwargs['check'])
                self.assertEqual(Path(command[command.index('--config') + 1]).read_text(), env['JOURNAL_CONFIG'])
                if request:
                    self.assertEqual(Path(command[command.index('--request') + 1]).read_text(), request)
                if fail:
                    raise subprocess.CalledProcessError(1, command)
                answer = result if result is not None else {
                    'schema': 'lmdj.ci-batch-runtime.v1',
                    'action': 'initialized' if operation == 'init' else 'idle',
                    'reason': 'local fixture, not platform evidence', 'request': None,
                    'executor': {'run_id': 10, 'attempt': 1}, 'state': None}
                Path(command[command.index('--output') + 1]).write_text(json.dumps(answer))
            with mock.patch.dict(os.environ, env), mock.patch.object(subprocess, 'run', side_effect=run):
                try:
                    exec(compile(code, '<workflow-runtime-adapter>', 'exec'), {})
                except BaseException:
                    self.assertFalse(output.exists(), 'why: failed control emitted execution outputs; remedy: publish only after confirmed runtime success')
                    raise
            return commands, output.read_text()

    def test_init_and_settle_pass_exact_operation_without_request(self):
        for operation in ('init', 'settle'):
            with self.subTest(operation=operation):
                commands, output = self.invoke(operation)
                self.assertEqual(len(commands), 1)
                self.assertEqual(commands[0][:3], ['python3', 'scripts/ci/batch_runtime.py', operation])
                self.assertNotIn('--request', commands[0])
                expected = 'initialized' if operation == 'init' else 'idle'
                self.assertIn(f'action={expected}\n', output)

    def test_reconcile_preserves_explicit_request_argument(self):
        commands, _ = self.invoke('reconcile', '{"kind":"candidate"}')
        self.assertIn('--request', commands[0])

    def test_settle_refuses_an_ignored_explicit_request(self):
        with self.assertRaisesRegex(SystemExit, 'explicit request outside reconcile'):
            self.invoke('settle', '{}')

    def test_runtime_failure_never_emits_execute_outputs(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke('reconcile', fail=True)

    def test_execute_outputs_reach_real_callee_validation_unchanged(self):
        # Own the complete Git fixture: CI checks this test out shallow, while
        # the real execution adapter correctly requires complete provenance.
        # Runtime remains a fixture; no platform claim or lock is certified.
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(['git', 'init', '--quiet', str(repo)], check=True)
            subprocess.run(['git', '-C', str(repo), '-c', 'user.name=CI fixture',
                            '-c', 'user.email=ci-fixture@example.invalid',
                            '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '--quiet',
                            '--allow-empty', '-m', 'Execution identity fixture'], check=True)
            control = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
            self.assert_execution_bridge(repo, control)

    def assert_execution_bridge(self, repo, control):
        policy = test_scope.load_policy(ROOT)
        executor = {'run_id': 10, 'attempt': 1}
        request = incremental_batch.make_request(policy, request_id='rehearsal-fixture', kind='node',
            base_sha=None, target_sha=control, control_sha=control,
            selection=test_scope.select(policy, [], ['test:full']), origin_run=executor)
        answer = {'schema': 'lmdj.ci-batch-runtime.v1', 'action': 'execute', 'reason': 'fixture',
                  'request': request, 'executor': executor, 'state': None}
        _, output = self.invoke('reconcile', result=answer)
        values = dict(line.split('=', 1) for line in output.splitlines())
        self.assertEqual(values['action'], 'execute')
        decoded_request, decoded_executor = json.loads(values['request']), json.loads(values['executor'])
        self.assertEqual(decoded_request, request)
        self.assertEqual(decoded_executor, executor)
        manifest = batch_execution.prepare(policy, decoded_request, decoded_executor, repo=repo,
            run_id=10, run_attempt=1, control_sha=control, main_sha=control)
        self.assertEqual(manifest['identity']['request_id'], request['id'])
        self.assertEqual(manifest['selection'], request['selection'])
        self.assertTrue(all(manifest['suites'].values()))


if __name__ == '__main__':
    unittest.main()
