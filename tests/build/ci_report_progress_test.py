"""Report fairness across real entry transitions and actual workflow conditions.

The small admission model reproduces running/pending single-slot replacement,
not GitHub cron delays, runner availability, queue capacity or relay chain depth.
Those platform side effects require the remote acceptance recorded in the plan.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts/ci'), str(ROOT / 'tests/build')]
import ci_incremental_entry_test as journey
from ci_self_test_report_workflow_test import block, field
import incremental_entry as entry
import report_runtime
import report_outbox

SOURCE = (ROOT / '.github/workflows/self-test-report.yml').read_text()
CONTROLLER = block(SOURCE, 'controller', 2)


def expression(raw, **values):
    text = raw.split('${{', 1)[1].split('}}', 1)[0].strip()
    context = {'github.event_name': 'push', 'github.event.schedule': '',
        'github.event.workflow_run.path': '', 'github.run_id': '100',
        'inputs.batch_operation': '', 'steps.control.outcome': 'skipped',
        'steps.control.outputs.action': '', 'needs.controller.outputs.action': ''}
    context.update(values)
    for key in sorted(context, key=len, reverse=True):
        text = text.replace(key, repr(context[key]))
    text = re.sub(r'!(?!=)', ' not ', text).replace('&&', ' and ').replace('||', ' or ')
    return eval(text, {'__builtins__': {}, 'always': lambda: True,
                      'startsWith': lambda value, prefix: value.startswith(prefix)})


def condition(name):
    body = CONTROLLER.split('      - name: ' + name + '\n', 1)[1].split('\n      - ', 1)[0]
    return field(body, 'if', 8)


def group(event, schedule='', run='100'):
    return expression(field(block(SOURCE, 'concurrency', 0), 'group', 2),
        **{'github.event_name': event, 'github.event.schedule': schedule, 'github.run_id': run})


class Admission:
    """Single pending replacement, never cancel the running workflow."""
    def __init__(self):
        self.running, self.pending, self.cancelled = {}, {}, []

    def submit(self, key, run):
        if key not in self.running:
            self.running[key] = run
            return True
        if key in self.pending:
            self.cancelled.append(self.pending[key])
        self.pending[key] = run
        return False


class WorkflowTests(unittest.TestCase):
    def test_both_health_roles_match_the_actual_yaml_and_python(self):
        crons = re.findall(r'cron: "([^"]+)"', block(block(SOURCE, 'on', 0), 'schedule', 2))
        self.assertEqual(crons, [entry.SCHEDULER_HEALTH, entry.REPORT_HEALTH],
            'why: report role and scheduled triggers diverged; remedy: retain both exact health roles')

    def test_report_tick_runs_reports_without_control_output_or_execution_artifact(self):
        context = {'github.event_name': 'schedule', 'github.event.schedule': entry.REPORT_HEALTH}
        self.assertFalse(expression(condition('Reconcile the isolated journal under the short writer lock'), **context),
            'why: report tick can claim product work; remedy: skip its control bridge')
        for name in ('Report durable observations independently', 'Recover missed review observations independently'):
            self.assertTrue(expression(condition(name), **context),
                'why: report tick still waits for successful product control; remedy: admit its independent reporting step')
        upload = CONTROLLER.split('      - uses: actions/upload-artifact@v6\n', 1)[1]
        self.assertFalse(expression(field(upload, 'if', 8), **context))
        execute = field(block(SOURCE, 'execute-batch', 2), 'if', 4)
        self.assertFalse(expression(execute, **context))
        self.assertTrue(expression(execute, **{'needs.controller.outputs.action': 'execute'}),
            'why: reporting disabled an earlier admitted DAG; remedy: preserve the original execution output')

    def test_report_failure_does_not_suppress_independent_discovery(self):
        context = {'github.event_name': 'schedule', 'github.event.schedule': entry.REPORT_HEALTH,
                   'steps.automatic-report.outcome': 'failure', 'steps.automatic-discovery.outcome': 'success'}
        self.assertTrue(expression(condition('Recover missed review observations independently'), **context))
        self.assertTrue(expression(condition('Keep unresolved reporting visible'), **context))

    def test_continuous_pushes_cannot_replace_report_or_manual_admission(self):
        queue = Admission()
        self.assertTrue(queue.submit(group('push'), 'active-product'))
        report_key = group('schedule', entry.REPORT_HEALTH)
        self.assertTrue(queue.submit(report_key, 'report-one'),
            'why: long product workflow starves report admission; remedy: give reports their own coalescing group')
        self.assertFalse(queue.submit(report_key, 'report-two'))
        for i in range(20):
            self.assertFalse(queue.submit(group('push'), f'push-{i}'))
        self.assertEqual(queue.running[group('push')], 'active-product')
        self.assertEqual(queue.pending[report_key], 'report-two')
        self.assertNotIn('report-one', queue.cancelled)
        self.assertNotIn('report-two', queue.cancelled)
        for run in ('501', '502'):
            self.assertTrue(queue.submit(group('workflow_dispatch', run=run), run))
        self.assertEqual(group('schedule', entry.SCHEDULER_HEALTH), group('push'))
        admission = block(SOURCE, 'concurrency', 0)
        self.assertEqual(field(admission, 'queue', 2), 'single')
        self.assertEqual(field(admission, 'cancel-in-progress', 2), 'false')
        writer = block(CONTROLLER, 'concurrency', 4)
        self.assertEqual(field(writer, 'group', 6), 'self-test-report')
        self.assertEqual(field(writer, 'queue', 6), 'max')
        self.assertEqual(field(writer, 'cancel-in-progress', 6), 'false')


class HealthJourneyTests(unittest.TestCase):
    setUp = journey.EntryTests.setUp
    add_run = journey.EntryTests.add_run
    make = journey.EntryTests.make
    push = journey.EntryTests.push
    callback = journey.EntryTests.callback
    writes = journey.EntryTests.writes
    advance_main = journey.EntryTests.advance_main

    def payload(self, schedule=entry.REPORT_HEALTH):
        return {'repository': self.push()['repository'], 'schedule': schedule}

    def failed_then_active(self):
        first = self.make().control(self.push())
        self.f.api = self.scheduler
        self.f.evidence(first['request'], failed_job='creator-web')
        self.advance_main('packages/application-facade/new-main.txt')
        self.add_run(18, event='push')
        second = self.make(18, 'push').control(self.push())
        self.assertEqual(second['action'], 'execute')
        self.assertEqual(second['state']['results'][first['request']['id']]['outcomes']['creator'], 'failed')
        self.assertEqual(len(self.api.issues), 0)
        return first, second

    def test_report_tick_delivers_old_failure_while_new_main_remains_active_and_replay_deduplicates(self):
        first, second = self.failed_then_active()
        for run in (19, 20):
            self.advance_main(f'packages/application-facade/new-main-{run}.txt')
            self.add_run(run, event='push')
            answer = self.make(run, 'push').control(self.push())
            self.assertEqual(answer['action'], 'waiting')
            self.assertEqual(answer['state']['active']['claim'], second['state']['active']['claim'])
        self.add_run(21, event='schedule')
        reporter = self.make(21, 'schedule')
        reporter.authenticate()
        before = deepcopy(reporter.state())
        before_comments = deepcopy(self.scheduler.comments)
        self.calls.clear()
        with mock.patch.object(reporter.runtime, 'reconcile', side_effect=AssertionError('report must never reconcile')):
            result = reporter.reports(self.payload())
        self.assertEqual(result['status'], 'ready', result)
        self.assertEqual(result['source'], 'report-health')
        self.assertEqual(len(self.api.issues), 1)
        self.assertIn(first['request']['id'], self.api.issues[0]['body'])
        self.assertEqual(reporter.state(), before)
        self.assertEqual(self.scheduler.comments, before_comments)
        storage = report_runtime.ReportRuntime(self.config, root=self.f.root,
            environment=reporter.env, api=self.api)
        storage.storage.authenticate_current()
        delivered, = storage.outbox().load()['deliveries'].values()
        self.assertEqual(delivered['status'], 'delivered')
        self.assertEqual(delivered['payload']['issue_body'], self.api.issues[0]['body'])
        # A new Entry/Runtime/Journal reads serialized HTTP storage; no cached
        # Outbox instance or producer output is reused for this replay.
        self.add_run(22, event='schedule')
        self.calls.clear()
        with mock.patch.object(self.api, 'create_issue', side_effect=AssertionError('duplicate Issue POST')), \
             mock.patch.object(self.api, 'create_comment', side_effect=AssertionError('duplicate comment POST')):
            again = self.make(22, 'schedule').reports(self.payload())
        self.assertEqual(again['status'], 'ready')
        self.assertEqual(len(self.api.issues), 1)
        self.assertFalse(self.writes())

    def test_unknown_schedule_only_recovers_previously_frozen_outbox(self):
        source = journey.full_legacy_api()
        _, reports = report_runtime.reporting.plan_run(source, 100, attempt=1,
            repository='endaye/lmdj', sleep=lambda _: None)
        writer = report_runtime.ReportRuntime(self.config, root=self.f.root, environment=self.env, api=self.api)
        writer.storage.authenticate_current()
        box = writer.outbox()
        box.load()
        key = entry.batch.digest({'key': reports[0].key, 'observation': reports[0].observation})
        box._persist('queue', {'delivery': key, 'payload': report_outbox.freeze(reports[0], 'endaye')})
        self.add_run(18, event='schedule')
        before = deepcopy(self.scheduler.comments)
        result = self.make(18, 'schedule').reports(self.payload('unknown cron'))
        self.assertEqual(result['status'], 'error')
        self.assertEqual([r['operation'] for r in result['outcomes']], ['source', 'drain'])
        self.assertEqual(result['outcomes'][1]['result']['status'], 'delivered')
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual(self.scheduler.comments, before)

    def test_report_writer_authentication_failure_cannot_enter_recovery(self):
        self.add_run(18, event='push')
        with mock.patch.object(report_runtime.ReportRuntime, 'execute', side_effect=AssertionError('unauthenticated recovery')):
            with self.assertRaises(entry.batch.BatchError):
                self.make(18, 'schedule').reports(self.payload())
        self.assertFalse(self.writes())

    def test_correct_report_role_planning_failure_preserves_the_active_claim(self):
        _, second = self.failed_then_active()
        self.add_run(19, event='schedule')
        reporter = self.make(19, 'schedule')
        reporter.authenticate()
        before = deepcopy(reporter.state())
        original = report_runtime.ReportRuntime.execute
        calls = []
        def execute(runtime, operation, **kwargs):
            calls.append(operation)
            if operation == 'batches':
                raise OSError('source unavailable')
            return original(runtime, operation, **kwargs)
        with mock.patch.object(report_runtime.ReportRuntime, 'execute', execute):
            result = reporter.reports(self.payload())
        self.assertEqual(result['status'], 'error')
        self.assertEqual(calls, ['batches', 'drain'])
        self.assertEqual(reporter.state(), before)
        self.assertEqual(before['active']['claim'], second['state']['active']['claim'])
        self.f.evidence(second['request'], failed_job='creator-web', run=18)
        self.advance_main('packages/application-facade/after-report-failure.txt')
        self.add_run(20, event='schedule')
        resumed = self.make(20, 'schedule').control(self.payload(entry.SCHEDULER_HEALTH))
        self.assertEqual(resumed['action'], 'execute',
            'why: report failure stranded new main recovery; remedy: keep the independent scheduler health role')
        self.assertEqual(resumed['request']['base'], second['request']['target'])
        self.assertEqual(resumed['request']['target'], self.sha)
        self.assertEqual(resumed['state']['results'][second['request']['id']]['outcomes']['creator'], 'failed')


if __name__ == '__main__':
    unittest.main()
