"""Real Git, scheduler Runtime, authenticated Journal and manual planning entry.

HTTP fixtures reproduce complete protocol shapes and uncertain write outcomes,
not actual Actions token scopes, queue scheduling or remote eventual visibility.
Those remain explicit live acceptance gaps; no remote storage is initialized.
"""
import base64
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts/ci')]
import ci_self_test_report_test  # Preserve the shared production exception identity.
import ci_batch_runtime_test as fixture
from tools.canary import planning_entry as entry, records as r
from ci_self_test_report_workflow_test import block, field, scalars
from workflow_inventory import jobs_in


class PlanningHttp(fixture.Http):
    def add_run(self, number):
        super().add_run(number)
        self.runs[number].update(path=entry.PlanningRuntime.workflow, workflow_id=9)
        self.jobs[number][0]['name'] = entry.PlanningRuntime.controller_job

    def _request(self, method, path, *, body=None, raw=False):
        prefix = '/repos/endaye/lmdj'
        if method == 'GET' and path == prefix + '/actions/workflows/9':
            self.calls.append((method, path, deepcopy(body)))
            return {'id': 9, 'path': entry.PlanningRuntime.workflow}
        if method == 'GET' and path.startswith(prefix + '/contents/' + entry.PlanningRuntime.workflow + '?ref='):
            assert path.split('?ref=')[1] in {run['head_sha'] for run in self.runs.values()}
            self.calls.append((method, path, deepcopy(body)))
            return {'type': 'file', 'path': entry.PlanningRuntime.workflow, 'encoding': 'base64',
                    'content': base64.b64encode(b'trusted manual planning workflow').decode()}
        return super()._request(method, path, body=body, raw=raw)


class PairHttp:
    def __init__(self, sha):
        self.scheduler, self.planner = fixture.Http(sha), PlanningHttp(sha)
        self.scheduler.issue.update(id='scheduler-node', number=807)
        self.planner.issue.update(id='planning-node', number=783)
        self.planner.runs.clear()
        self.planner.jobs.clear()
        self.planner.add_run(100)

    def __getattr__(self, name):
        return getattr(self.scheduler, name)

    def _request(self, method, path, *, body=None, raw=False):
        planning = ('/issues/783' in path or '/actions/workflows/9' in path
                    or '/contents/' + entry.PlanningRuntime.workflow in path
                    or path == '/graphql' and body['variables']['number'] == 783)
        match = re.search(r'/actions/runs/(\d+)/', path)
        if match:
            planning = int(match[1]) >= 100
        target = self.planner if planning else self.scheduler
        return target._request(method, path.replace('/issues/783', '/issues/782').replace('/issues/807', '/issues/782'),
                               body=body, raw=raw)


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.git('config', 'commit.gpgsign', 'false')
        for name in ('tools/canary/policy.json', 'apps/creator-web/module.json',
                     'apps/web-runtime-host/module.json', entry.PlanningRuntime.workflow):
            path = self.f.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        self.f.config.update(issue_number=807, issue_node_id='scheduler-node')
        pair = {'scheduler': self.f.config, 'outbox': {**self.f.config, 'issue_number': 817,
                                                     'issue_node_id': 'outbox-node'}}
        (self.f.root / entry.incremental_entry.STORAGE_PATH).write_text(json.dumps(pair))
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'Frozen planning fixture inputs')
        self.target = self.f.git('rev-parse', 'HEAD')
        self.f.api = self.api = PairHttp(self.target)
        self.f.env['GITHUB_SHA'] = self.target
        self.config = {**self.f.config, 'issue_number': 783, 'issue_node_id': 'planning-node',
                       'workflow_id': 9, 'epoch': 'canary-planning-fixture'}
        self.env = {**self.f.env, 'BATCH_WRITER_LOCK': 'canary-planning', 'GITHUB_RUN_ID': '100'}
        started = self.f.start()
        self.request = started['request']
        self.f.evidence(self.request)
        self.api.scheduler.add_run(18)
        self.f.make(18).reconcile(execute=False)
        self.control('init', {})
        self.control('bootstrap', {})

    def control(self, operation='observe-result', request=None, **env):
        return entry.control(operation, self.config,
            {'source_request_id': self.request['id']} if request is None else request,
            root=self.f.root, environment={**self.env, **env}, api=self.api)

    def writes(self, which):
        return [(method, path, body) for method, path, body in which.calls
                if method in ('PATCH', 'POST') and path != '/graphql']

    def move_main(self):
        path = self.f.root / 'docs/notes/after-plan.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('A later merge must not rewrite a frozen plan.\n')
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'Later main revision')
        target = self.f.git('rev-parse', 'HEAD')
        self.api.scheduler.sha = self.api.planner.sha = target
        self.api.planner.add_run(101)
        self.env.update(GITHUB_SHA=target, GITHUB_RUN_ID='101')
        return target

    def next_batch(self, path, *, failed_job=None):
        source = self.f.root / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(path + '\n')
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'Next source interval')
        target = self.f.git('rev-parse', 'HEAD')
        self.api.scheduler.sha = self.api.planner.sha = target
        self.f.env['GITHUB_SHA'] = target
        run = max(self.api.scheduler.runs) + 1
        self.api.scheduler.add_run(run)
        started = self.f.make(run).reconcile(execute=True)
        request = started['request']
        self.assertIsNotNone(request, 'why: fixture admitted no next interval; remedy: create a real main change')
        if request['selection']['suites']:
            original = fixture.batch_execution.from_needs
            def selected_needs(policy, identity, selection, needs, **kwargs):
                selected = {job for suite in policy.inventory.suites
                            if suite.id in selection['suites'] for job in suite.jobs}
                # The older shared fixture models a full DAG. Model actual
                # focused DAG skips before using the unchanged real judge.
                for job in fixture.runtime.JOB_NAMES:
                    if job not in selected:
                        needs[fixture.runtime.ALIASES.get(job, job)]['result'] = 'skipped'
                return original(policy, identity, selection, needs, **kwargs)
            with patch.object(fixture.batch_execution, 'from_needs', side_effect=selected_needs):
                self.f.evidence(request, run=run, failed_job=failed_job)
        else:
            self.api.scheduler.runs[run].update(status='completed', conclusion='success')
            self.api.scheduler.jobs[run][0].update(status='completed', conclusion='success')
        self.api.scheduler.add_run(run + 1)
        self.f.make(run + 1).reconcile(execute=False)
        observer = max(self.api.planner.runs) + 1
        self.api.planner.add_run(observer)
        self.env.update(GITHUB_SHA=target, GITHUB_RUN_ID=str(observer))
        return request

    def test_real_scheduler_to_plan_and_reopen_preserves_complete_bytes_without_source_reread(self):
        before = deepcopy((self.api.scheduler.issue, self.api.scheduler.comments))
        first = self.control()
        self.assertEqual(first['action'], 'planned')
        self.assertEqual(first['slot'], 'active')
        self.assertFalse(first['admission_evidence'])
        self.assertEqual(first['decision']['plan']['target_sha'], self.target)
        self.assertEqual(first['decision']['plan']['test_floor']['kind'], 'full')
        self.assertIsNone(first['intent']['progress']['version_accounted'])
        self.move_main()
        with patch.object(entry, 'scheduler_state', side_effect=AssertionError('finished recovery reread scheduler')):
            recovered = self.control('recover')
            duplicate = self.control()
        self.assertEqual(r.canonical(first), r.canonical(recovered))
        self.assertEqual(duplicate, first)
        self.assertEqual(before, (self.api.scheduler.issue, self.api.scheduler.comments))

    def test_partial_write_recovers_original_control_after_main_moves(self):
        self.api.planner.lose = 'blob'
        with self.assertRaises(Exception):
            self.control()
        original = entry.PlanningRuntime(self.config, root=self.f.root, environment=self.env, api=self.api)
        row = entry.storage.Plans(original.journal(), original.lock_held, self.config['epoch']).lookup(self.request['id'])
        self.assertIsNone(row['decision'])
        expected = row['intent']['decision_digest']
        self.move_main()
        recovered = self.control('recover')
        self.assertEqual(r.digest(recovered['decision']), expected)
        self.assertEqual(recovered['intent']['control_sha'], self.target)
        self.assertEqual(recovered['intent']['main_sha'], self.target)
        self.assertEqual(recovered, self.control('recover'))

    def unfinished(self):
        self.api.planner.lose = 'blob'
        with self.assertRaises(Exception):
            self.control()
        runtime = entry.PlanningRuntime(self.config, root=self.f.root, environment=self.env, api=self.api)
        # Reconcile the already visible original blob append, not the source.
        return entry.storage.Plans(runtime.journal(), runtime.lock_held, self.config['epoch']).lookup(self.request['id'])

    def test_unfinished_recovery_missing_source_history_writes_nothing(self):
        original = self.unfinished()
        self.api.scheduler.comments.pop()
        before = deepcopy((self.api.planner.issue, self.api.planner.comments))
        with self.assertRaises(Exception):
            self.control('recover')
        self.assertEqual(before, (self.api.planner.issue, self.api.planner.comments))
        runtime = entry.PlanningRuntime(self.config, root=self.f.root, environment=self.env, api=self.api)
        self.assertEqual(entry.storage.Plans(runtime.journal(), runtime.lock_held,
            self.config['epoch']).lookup(self.request['id']), original)

    def test_unfinished_recovery_changed_decision_cannot_replace_frozen_digest(self):
        self.unfinished()
        before = deepcopy((self.api.planner.issue, self.api.planner.comments))
        actual = entry.planning.plan_after_result
        def changed(*args, **kwargs):
            result = actual(*args, **kwargs)
            result['plan']['test_floor']['reasons'].append('Different decision must not overwrite original.')
            result['plan'] = r.seal(result['plan'])
            return result
        with patch.object(entry.planning, 'plan_after_result', side_effect=changed):
            with self.assertRaisesRegex(r.CanaryError, 'complete decision changed'):
                self.control('recover')
        self.assertEqual(before, (self.api.planner.issue, self.api.planner.comments))

    def test_recovery_without_original_intent_cannot_create_one(self):
        before = deepcopy(self.api.planner.comments)
        with self.assertRaisesRegex(r.CanaryError, 'no original persisted intent'):
            self.control('recover')
        self.assertEqual(before, self.api.planner.comments)

    def test_oversized_plan_is_rejected_before_reserving_unfinished_slot(self):
        before = deepcopy(self.api.planner.comments)
        actual = entry.planning.plan_after_result
        def oversized(*args, **kwargs):
            result = actual(*args, **kwargs)
            result['plan']['test_floor']['reasons'].append('x' * 600001)
            result['plan'] = r.seal(result['plan'])
            return result
        with patch.object(entry.planning, 'plan_after_result', side_effect=oversized):
            with self.assertRaisesRegex(r.CanaryError, 'uncompressed budget'):
                self.control()
        self.assertEqual(before, self.api.planner.comments)

    def test_failed_product_result_is_retained_as_ignored_not_a_plan(self):
        request = self.next_batch('scripts/ci/changed.py', failed_job='core-ubuntu')
        result = self.control(request={'source_request_id': request['id']})
        self.assertEqual(result['action'], 'ignored')
        self.assertEqual(result['decision']['source']['status'], 'failed')
        self.assertIsNone(result['decision']['plan'])
        self.assertFalse(result['admission_evidence'])

    def test_docs_none_result_does_not_invent_canary_work(self):
        request = self.next_batch('docs/notes/safe.md')
        self.assertEqual(request['selection']['suites'], [])
        result = self.control(request={'source_request_id': request['id']})
        self.assertEqual(result['action'], 'ignored')
        self.assertEqual(result['decision']['source']['status'], 'not-required')

    def test_newest_pending_and_late_older_result_preserve_active_target(self):
        active = self.control()
        older = self.next_batch('apps/creator-web/src/older.ts')
        newer = self.next_batch('apps/creator-web/src/newer.ts')
        pending = self.control(request={'source_request_id': newer['id']})
        late = self.control(request={'source_request_id': older['id']})
        self.assertEqual(pending['slot'], 'pending')
        self.assertEqual(late['slot'], 'historical')
        runtime = entry.PlanningRuntime(self.config, root=self.f.root, environment=self.env, api=self.api)
        state = entry.storage.Plans(runtime.journal(), runtime.lock_held, self.config['epoch']).load()
        self.assertEqual(state['active'], self.request['id'])
        self.assertEqual(state['pending'], newer['id'])
        self.assertEqual(self.control('recover'), active)

    def test_caller_cannot_supply_progress_or_scheduler_or_plan(self):
        before = deepcopy(self.api.planner.comments)
        for name in ('progress', 'scheduler', 'plan', 'target_sha'):
            with self.subTest(name=name), self.assertRaisesRegex(r.CanaryError, 'caller evidence'):
                self.control(request={'source_request_id': self.request['id'], name: {}})
        self.assertEqual(before, self.api.planner.comments)

    def test_wrong_run_attempt_ref_lock_or_live_job_cannot_write(self):
        before = deepcopy(self.api.planner.comments)
        for key, value in (('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_REF', 'refs/pull/1/merge'),
                           ('BATCH_WRITER_LOCK', 'self-test-report'), ('GITHUB_SHA', 'a' * 40)):
            with self.subTest(key=key), self.assertRaises(Exception):
                self.control(**{key: value})
        self.api.planner.jobs[100][0]['status'] = 'queued'
        with self.assertRaises(Exception):
            self.control()
        self.assertEqual(before, self.api.planner.comments)

    def test_nonmanual_run_cannot_write(self):
        before = deepcopy(self.api.planner.comments)
        self.api.planner.runs[100]['event'] = 'push'
        with self.assertRaisesRegex(r.CanaryError, 'manual invocation'):
            self.control()
        self.assertEqual(before, self.api.planner.comments)

    def test_alias_reserved_storage_is_rejected_before_api(self):
        before = len(self.api.planner.calls) + len(self.api.scheduler.calls)
        for number in (807, 817, 849):
            with self.subTest(number=number), self.assertRaises(r.CanaryError):
                entry.control('init', {**self.config, 'issue_number': number}, {},
                              root=self.f.root, environment=self.env, api=self.api)
        self.assertEqual(before, len(self.api.planner.calls) + len(self.api.scheduler.calls))

    def test_scheduler_checkpoint_pending_is_not_repaired_by_planner(self):
        runtime = self.f.make(18)
        self.api.scheduler.lose = 'observe'
        journal = runtime.journal()
        events = journal.load()
        with self.assertRaises(Exception):
            journal.append({'id': 'pending-observation', 'epoch': self.f.config['epoch'],
                            'generation': len(events), 'type': 'observe',
                            'data': {'target': self.target, 'descends_pending': True}})
        before = deepcopy((self.api.scheduler.issue, self.api.scheduler.comments, self.api.planner.comments))
        with self.assertRaisesRegex(Exception, 'only its controller'):
            self.control()
        self.assertEqual(before, (self.api.scheduler.issue, self.api.scheduler.comments, self.api.planner.comments))

    def test_init_cannot_reset_progress_or_completed_plan(self):
        first = self.control()
        with self.assertRaisesRegex(Exception, 'exact empty reserved'):
            self.control('init', {})
        self.assertEqual(self.control('recover'), first)

    def test_scheduler_writer_does_not_gain_planning_authority(self):
        before = deepcopy(self.api.planner.comments)
        self.api.planner.runs[100].update(path=fixture.runtime.WORKFLOW, workflow_id=7)
        with self.assertRaises(Exception):
            self.control()
        self.assertEqual(before, self.api.planner.comments)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / entry.PlanningRuntime.workflow
        self.source = self.path.read_text()
        self.job = block(self.source, 'controller', 2)

    def test_manual_only_single_short_controller(self):
        self.assertEqual(re.findall(r'^  ([\w-]+):', block(self.source, 'on', 0), re.M), ['workflow_dispatch'])
        self.assertEqual([job.job_id for job in jobs_in(self.path)], ['controller'])
        self.assertEqual(field(self.job, 'if', 4), "github.ref == 'refs/heads/main' && github.run_attempt == '1'")
        self.assertEqual(field(self.job, 'name', 4), entry.PlanningRuntime.controller_job)
        self.assertEqual(field(self.job, 'timeout-minutes', 4), '10')
        self.assertEqual(scalars(block(self.job, 'concurrency', 4), 6),
                         {'group': 'canary-planning', 'cancel-in-progress': 'false', 'queue': 'max'})

    def test_no_hosted_or_model_or_deployment_credentials(self):
        self.assertTrue(all(job.is_self_hosted for job in jobs_in(self.path)))
        self.assertEqual(field(self.source, 'permissions', 0), '{}')
        self.assertEqual(scalars(block(self.job, 'permissions', 4), 6),
                         {'contents': 'read', 'actions': 'read', 'issues': 'write'})
        self.assertEqual(set(scalars(block(self.job, 'env', 8), 10)),
                         {'GITHUB_TOKEN', 'BATCH_WRITER_LOCK', 'PLANNING_OPERATION', 'PLANNING_STORAGE', 'PLANNING_REQUEST'})
        self.assertIn('ref: ${{ github.sha }}', self.job)
        self.assertIn('persist-credentials: false', self.job)

    def test_complete_artifact_and_module_entry_are_wired(self):
        self.assertIn('python3 -m tools.canary.planning_entry --directory ', self.job)
        self.assertIn('/planning.json', self.job)
        self.assertIn('if-no-files-found: error', self.job)
        self.assertIn('name: canary-planning-${{ github.run_id }}-${{ github.run_attempt }}', self.job)


if __name__ == '__main__':
    unittest.main()
