"""Execute the C2 inline entry; fixture cancellation is not remote acceptance."""
from copy import deepcopy
import importlib
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
import o1_execution_cancel_probe as c2


class CancelWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / '.github/workflows/self-test-report.yml').read_text()
        self.controller = block(self.source, 'controller', 2)
        self.step = self.controller.split('      - name: Prepare the isolated cancellation diagnostic\n', 1)[1].split('      - name:', 1)[0]
        self.code = '\n'.join(line[10:] for line in self.step.split("          python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0].splitlines())

    def fixture(self):
        fixture = importlib.import_module('ci_o1_execution_cancel_probe_test').CancellationProbeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def invoke(self, fixture, *, extra=None, mutate=None, code_override=None):
        with tempfile.TemporaryDirectory() as directory:
            summary, output = [Path(directory) / name for name in ('summary', 'output')]
            env = {**fixture.f.env, 'RUNNER_TEMP': directory, 'GITHUB_STEP_SUMMARY': str(summary),
                   'GITHUB_OUTPUT': str(output), 'BATCH_OPERATION': 'cancel-probe',
                   'JOURNAL_CONFIG': json.dumps(fixture.f.config), 'PROBE_REQUEST': json.dumps(fixture.intent()),
                   **(extra or {})}
            calls, actual_run = [], subprocess.run
            def run(command, **kwargs):
                if command[:2] != ['python3', 'scripts/ci/o1_execution_cancel_probe.py']:
                    self.assertEqual(command[0], 'git', 'why: unexpected subprocess; remedy: use real CLI and Git only')
                    return actual_run(command, **kwargs)
                calls.append(command)
                self.assertEqual(kwargs, {'check': False})
                self.assertEqual(set(command[2::2]), {'--config', '--request', '--root', '--diagnostic', '--summary'})
                for flag, key in (('--config', 'JOURNAL_CONFIG'), ('--request', 'PROBE_REQUEST')):
                    self.assertEqual(Path(command[command.index(flag) + 1]).read_text(), env[key])
                code = c2.main(command[2:])
                diagnostic = Path(command[command.index('--diagnostic') + 1])
                if mutate:
                    value = json.loads(diagnostic.read_text())
                    changed = mutate(value)
                    diagnostic.write_text(changed if isinstance(changed, str) else json.dumps(value))
                return subprocess.CompletedProcess(command, code if code_override is None else code_override)
            with mock.patch.dict(os.environ, env), mock.patch.object(Path, 'cwd', return_value=fixture.f.root), \
                    mock.patch.object(subprocess, 'run', side_effect=run), \
                    mock.patch.object(c2.batch_runtime, 'UrllibGitHubApi', return_value=fixture.f.api):
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(self.code, '<actual-C2-workflow>', 'exec'), {})
            self.assertFalse((Path(directory) / 'incremental-controller/result.json').exists())
            return stopped.exception.code, output.read_text() if output.exists() else '', calls

    def test_actual_claim_ready_and_cancelled_fixture_settlement_replay(self):
        f = self.fixture()
        code, output, calls = self.invoke(f)
        self.assertEqual(code, 0)
        self.assertEqual(output, 'diagnostic_ready=true\n')
        self.assertEqual(len(calls), 1)
        events = f.f.make().journal().load()
        self.assertEqual([e['type'] for e in events], ['observe', 'admit', 'claim'])
        self.assertEqual(len(events[1]['data']['request']['selection']['suites']), 16)
        # Only fixture metadata supplies cancellation here; actual platform
        # cancellation, waiter signals and whole-run terminal status remain O1.
        fresh = f.c1.fresh(conclusion='cancelled')
        settled = fresh.reconcile(execute=False)
        self.assertIsNone(settled['state']['active'])
        self.assertEqual(len(settled['state']['debts']), 16)
        self.assertTrue(all(d['attempts'] == 1 and d['outcome'] == 'missing' for d in settled['state']['debts'].values()))
        self.assertEqual(settled['state']['failures'], [])
        self.assertEqual(fresh.journal().load()[:3], events)
        before = deepcopy((f.f.api.issue, f.f.api.comments))
        self.assertEqual(f.c1.fresh(18, 19, 'success').reconcile(execute=False)['state'], settled['state'])
        self.assertEqual(before, (f.f.api.issue, f.f.api.comments))

    def test_actual_disabled_does_not_arm_or_call_api(self):
        f = self.fixture()
        code, output, _ = self.invoke(f, extra={'PROBE_REQUEST': json.dumps({'operation': c2.OPERATION})})
        self.assertEqual((code, output), (0, ''))
        self.assertEqual(f.f.api.calls, [])

    def test_actual_error_does_not_arm_or_conceal_journal(self):
        f = self.fixture()
        f.f.api.lose = 'claim'
        code, output, _ = self.invoke(f)
        self.assertEqual((code, output), (1, ''))
        self.assertTrue(f.c1.writes())

    def test_nonzero_with_ready_file_does_not_arm(self):
        f = self.fixture()
        code, output, _ = self.invoke(f, code_override=1)
        self.assertEqual((code, output), (1, ''))

    def test_wrong_actual_main_or_attempt_stops_before_cli(self):
        for key, value in [('GITHUB_REF', 'refs/heads/feature'), ('GITHUB_RUN_ATTEMPT', '2')]:
            with self.subTest(key=key):
                code, output, calls = self.invoke(self.fixture(), extra={key: value})
                self.assertIn('why:', code)
                self.assertEqual((output, calls), ('', []))

    def test_disabled_cannot_carry_identity_or_readiness(self):
        for mutate in (lambda v: v.update(status='disabled'),
                       lambda v: v.update(status='disabled', diagnostic_ready=False)):
            with self.subTest(mutate=mutate):
                code, output, _ = self.invoke(self.fixture(), mutate=mutate)
                self.assertIn('why:', code)
                self.assertEqual(output, '')

    def test_mixed_inputs_stop_before_cli(self):
        for key, value in [('BATCH_OPERATION', 'claim-probe'), ('REPORT_CONFIG', '{}'), ('BATCH_REQUEST', '{}'),
                           ('LEGACY_RUN_ID', '17'), ('LEGACY_RECONCILE', 'true'), ('REVIEW_RUN_ID', '17'),
                           ('REVIEW_ATTEMPT', '1'), ('REPORT_LIMIT', '9'), ('JOURNAL_CONFIG', ''), ('PROBE_REQUEST', '')]:
            with self.subTest(key=key):
                code, output, calls = self.invoke(self.fixture(), extra={key: value})
                self.assertIn('why:', code)
                self.assertIn('remedy:', code)
                self.assertEqual((output, calls), ('', []))

    def test_invalid_ready_records_fail_closed(self):
        mutations = [lambda v: v.update(schema='other'), lambda v: v.update(status='error'),
                     lambda v: v.update(status='unknown'), lambda v: v.update(diagnostic_ready='true'),
                     lambda v: v.update(diagnostic_ready=1), lambda v: v.update(extra=True),
                     lambda v: v.update(identity=None), lambda v: v['identity'].update(extra=True),
                     lambda v: v['identity'].update(run_id=True), lambda v: v['identity'].update(run_id=999),
                     lambda v: v['identity'].update(attempt=2), lambda v: v['identity'].update(attempt=True),
                     lambda v: v['identity'].update(control_sha='b' * 40),
                     lambda v: v['identity'].update(issue_number=True), lambda v: v['identity'].update(issue_number=999),
                     lambda v: v['identity'].update(epoch='o1-claim-cancel-other'),
                     lambda v: v['identity'].update(request_id='other'), lambda v: v['identity'].update(journal_head='bad'),
                     lambda v: '{"schema":"one","schema":"two"}']
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                code, output, _ = self.invoke(self.fixture(), mutate=mutate)
                self.assertIn('why:', code)
                self.assertIn('remedy:', code)
                self.assertEqual(output, '')

    def test_waiter_is_manual_readiness_only_without_authority_or_lock(self):
        waiter = block(self.source, 'cancel-probe-waiter', 2)
        condition = field(waiter, 'if', 4)
        for value in ("needs.controller.result == 'success'", "needs.controller.outputs.diagnostic_ready == 'true'",
                      "inputs.batch_operation == 'cancel-probe'", "github.event_name == 'workflow_dispatch'",
                      "github.ref == 'refs/heads/main'", "github.run_attempt == '1'"):
            self.assertIn(value, condition)
        self.assertEqual(field(waiter, 'permissions', 4), '{}')
        self.assertEqual(field(waiter, 'timeout-minutes', 4), '5')
        self.assertEqual(field(waiter, 'runs-on', 4), '[self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general, contabo]')
        for forbidden in ('concurrency:', 'always()', 'uses:', 'GITHUB_TOKEN', 'secrets.', 'continue-on-error', 'GITHUB_OUTPUT'):
            self.assertNotIn(forbidden, waiter)
        self.assertIn('sleep 285', waiter)
        self.assertIn('exit 1', waiter)
        self.assertIn('why:', waiter)
        self.assertIn('remedy:', waiter)

    def test_existing_authority_sources_and_inventory_remain_complete(self):
        self.assertEqual(scalars(block(self.controller, 'permissions', 4), 6),
                         {'contents': 'read', 'actions': 'read', 'issues': 'write'})
        self.assertIn('group: self-test-report', block(self.controller, 'concurrency', 4))
        self.assertNotRegex(self.source, r'(?m)^concurrency:')
        self.assertIn("inputs.batch_operation != 'cancel-probe'", self.controller)
        self.assertNotIn('${{', self.code)
        from batch_evidence_validation import EXECUTION_SOURCES, JOB_NAMES
        self.assertIn('.github/workflows/self-test-report.yml', EXECUTION_SOURCES)
        self.assertNotIn('cancel-probe-waiter', JOB_NAMES)
        policy = json.loads((ROOT / 'scripts/ci/hosted_runner_policy.json').read_text())
        entries = [e for e in policy['allowed'] if e['workflow'] == 'self-test-report.yml' and e['job'] == 'cancel-probe-waiter']
        self.assertEqual(entries, [], 'why: a diagnostic wait must not consume hosted minutes; remedy: retain its literal Contabo self-hosted route without a paid exemption')


if __name__ == '__main__':
    unittest.main()
