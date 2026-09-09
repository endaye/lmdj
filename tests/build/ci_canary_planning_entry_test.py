"""Real Git, scheduler Runtime, authenticated Journal and bounded discovery.

HTTP fixtures reproduce complete protocol shapes and uncertain write outcomes,
not actual Actions token scopes, queue scheduling or remote eventual visibility.
Those remain explicit live acceptance gaps; no remote storage is initialized.
"""
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts/ci')]
import ci_self_test_report_test  # Preserve the shared production exception identity.
import ci_batch_runtime_test as fixture
from tools.canary import planning_entry as entry, records as r
from ci_self_test_report_workflow_test import block, field, scalars, wakeup_group
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
        self.env = {**self.f.env, 'BATCH_WRITER_LOCK': 'canary-planning', 'GITHUB_RUN_ID': '100',
                    'GITHUB_EVENT_NAME': 'workflow_dispatch'}
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
        path.write_text('A later merge must not rewrite a frozen plan: ' + self.f.git('rev-parse', 'HEAD') + '\n')
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'Later main revision')
        target = self.f.git('rev-parse', 'HEAD')
        self.api.scheduler.sha = self.api.planner.sha = target
        observer = max(self.api.planner.runs) + 1
        self.api.planner.add_run(observer)
        self.env.update(GITHUB_SHA=target, GITHUB_RUN_ID=str(observer))
        return target

    def next_batch(self, path, *, failed_job=None, missing_verdict=False):
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
            if missing_verdict:
                self.api.scheduler.artifacts[run][0]['expired'] = True
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

    def test_discovery_without_source_id_persists_one_complete_observation(self):
        before = deepcopy((self.api.scheduler.issue, self.api.scheduler.comments))
        result = self.control('reconcile-next', {})
        self.assertEqual(result['intent']['source_request_id'], self.request['id'])
        self.assertEqual(result, self.control('recover'))
        self.assertEqual(result['decision']['plan']['version_interval']['kind'], 'bootstrap')
        self.assertIsNone(result['decision']['plan']['version_interval']['base_sha'])
        self.assertEqual(result['decision']['plan']['test_floor']['kind'], 'full')
        self.assertEqual(self.control('reconcile-next', {})['action'], 'idle')
        self.assertEqual(before, (self.api.scheduler.issue, self.api.scheduler.comments))

    def test_discovery_recovers_original_unfinished_before_newer_source(self):
        original = self.unfinished()
        newer = self.next_batch('apps/creator-web/src/newer.ts')
        result = self.control('reconcile-next', {})
        self.assertEqual(result['intent'], original['intent'])
        self.assertEqual(r.digest(result['decision']), original['intent']['decision_digest'])
        next_result = self.control('reconcile-next', {})
        self.assertEqual(next_result['intent']['source_request_id'], newer['id'])
        self.assertEqual(next_result['slot'], 'pending')
        self.assertEqual(self.control('recover'), result)

    def planning_state(self):
        runtime = entry.PlanningRuntime(self.config, root=self.f.root, environment=self.env, api=self.api)
        return entry.storage.Plans(runtime.journal(), runtime.lock_held, self.config['epoch']).load()

    def automatic(self, *, callback=17):
        run = self.api.scheduler.runs[callback]
        repository = {'id': 1286600062, 'full_name': 'endaye/lmdj'}
        run.update(repository=deepcopy(repository), head_repository=deepcopy(repository))
        path = self.f.root / 'callback.json'
        payload = {'action': 'completed', 'repository': repository, 'workflow_run': deepcopy(run)}
        path.write_text(json.dumps(payload))
        self.api.planner.runs[int(self.env['GITHUB_RUN_ID'])]['event'] = 'workflow_run'
        self.env.update(GITHUB_EVENT_NAME='workflow_run', GITHUB_EVENT_PATH=str(path),
                        CANARY_PLANNING_AUTOMATIC_READY='true')
        return path, payload

    def test_automatic_failed_callback_is_only_hint_for_authenticated_passed_source(self):
        # A reporting-only failure can still wake a valid retained test result.
        self.api.scheduler.runs[18].update(status='completed', conclusion='failure')
        self.api.scheduler.jobs[18][0].update(status='completed', conclusion='failure')
        self.automatic(callback=18)
        before = deepcopy((self.api.scheduler.issue, self.api.scheduler.comments))
        first = self.control('reconcile-next', {})
        self.assertEqual(first['intent']['source_request_id'], self.request['id'])
        self.assertEqual(first['decision']['source']['status'], 'passed')
        self.assertEqual(self.planning_state()['active'], self.request['id'])
        self.assertEqual(before, (self.api.scheduler.issue, self.api.scheduler.comments))
        self.assertEqual(self.control('reconcile-next', {})['action'], 'idle')

    def test_discovery_in_stable_admission_order_retains_ignored_sources_and_newer_pending(self):
        none = self.next_batch('docs/notes/no-test.md')
        self.assertEqual(none['selection']['suites'], [])
        failed = self.next_batch('scripts/ci/failure.py', failed_job='core-ubuntu')
        missing = self.next_batch('scripts/ci/missing.py', missing_verdict=True)
        newer = self.next_batch('apps/creator-web/src/newer.ts')
        expected = [(self.request, 'planned', 'passed'), (none, 'ignored', 'not-required'),
                    (failed, 'ignored', 'failed'), (missing, 'ignored', 'missing'), (newer, 'planned', 'passed')]
        # Late callback does not select itself or change scheduler ordering.
        self.automatic(callback=17)
        for request, action, status in expected:
            with self.subTest(request=request['id']):
                result = self.control('reconcile-next', {})
                self.assertEqual(result['intent']['source_request_id'], request['id'])
                self.assertEqual(result['action'], action)
                self.assertEqual(result['decision']['source']['status'], status)
                state = self.planning_state()
                self.assertIsNotNone(state['observations'][request['id']]['decision'])
                self.assertEqual(state['active'], self.request['id'])
                self.assertEqual(state['progress'], r.initial_progress('endaye/lmdj'))
        self.assertEqual(state['pending'], newer['id'])
        self.assertEqual(self.control('reconcile-next', {})['action'], 'idle')

    def test_discovery_ignores_actual_explicit_candidate_even_with_full_green(self):
        first = self.control('reconcile-next', {})
        self.api.scheduler.add_run(19)
        started = self.f.make(19).reconcile(execute=True,
            explicit={'id': 'manual-candidate', 'kind': 'candidate', 'target': self.target})
        self.assertEqual(started['request']['kind'], 'candidate')
        self.f.evidence(started['request'], run=19)
        self.api.scheduler.add_run(20)
        self.f.make(20).reconcile(execute=False)
        result = self.control('reconcile-next', {})
        self.assertEqual(result['action'], 'ignored')
        self.assertEqual(result['decision']['source']['status'], 'passed')
        self.assertIsNone(result['decision']['plan'])
        self.assertEqual(self.planning_state()['active'], first['intent']['source_request_id'])

    def test_discovery_lost_intent_chunk_and_complete_ack_preserves_original_observation(self):
        for kind in ('intent', 'blob', 'complete'):
            with self.subTest(kind=kind):
                if kind != 'intent':
                    source = self.next_batch('apps/creator-web/src/' + kind + '.ts')
                else:
                    source = self.request
                self.api.planner.lose = kind
                with self.assertRaisesRegex(r.CanaryError, 'append outcome is unresolved'):
                    self.control('reconcile-next', {})
                state = self.planning_state()  # Authenticate/reconcile the visible original POST.
                intent = state['observations'][source['id']]['intent']
                prefix = deepcopy(self.api.planner.comments)
                self.move_main()
                recovered = self.control('reconcile-next', {})
                if kind == 'complete':
                    self.assertEqual(recovered['action'], 'idle')
                else:
                    self.assertEqual(recovered['intent'], intent)
                    self.assertEqual(r.digest(recovered['decision']), intent['decision_digest'])
                final = self.control('recover', {'source_request_id': source['id']})
                self.assertEqual(final['intent'], intent)
                self.assertEqual(self.api.planner.comments[:len(prefix)], prefix)
                state = self.planning_state()
                self.assertIsNone(state['unfinished'])
                self.assertIsNotNone(state['observations'][source['id']]['decision'])

    def test_automatic_readiness_and_operation_refusals_do_not_reach_api(self):
        self.automatic()
        for operation, request, ready in (('reconcile-next', {}, ''), ('reconcile-next', {}, 'false'),
                                         ('init', {}, 'true'), ('bootstrap', {}, 'true'),
                                         ('observe-result', {'source_request_id': self.request['id']}, 'true')):
            with self.subTest(operation=operation, ready=ready):
                self.api.planner.calls.clear()
                self.api.scheduler.calls.clear()
                with self.assertRaisesRegex(r.CanaryError, 'readiness or operation'):
                    self.control(operation, request, CANARY_PLANNING_AUTOMATIC_READY=ready)
                self.assertFalse(self.api.planner.calls + self.api.scheduler.calls)

    def test_callback_hint_and_actual_identity_refusals_cannot_write(self):
        path, payload = self.automatic()
        changes = [('id', 18), ('run_attempt', 2), ('run_attempt', True), ('workflow_id', 9),
                   ('head_sha', 'a' * 40), ('head_branch', 'topic'), ('path', entry.PlanningRuntime.workflow),
                   ('status', 'in_progress'), ('conclusion', 'failure'), ('event', 'push'),
                   ('head_repository', {'id': 7, 'full_name': 'attacker/lmdj'})]
        before = deepcopy((self.api.planner.issue, self.api.planner.comments))
        for field_name, value in changes:
            with self.subTest(field=field_name):
                changed = deepcopy(payload)
                changed['workflow_run'][field_name] = value
                path.write_text(json.dumps(changed))
                with self.assertRaises(Exception):
                    self.control('reconcile-next', {})
                self.assertEqual(before, (self.api.planner.issue, self.api.planner.comments))
        for changes in ({'action': 'requested'}, {'repository': {'id': 1, 'full_name': 'endaye/lmdj'}}):
            path.write_text(json.dumps({**payload, **changes}))
            with self.assertRaises(Exception):
                self.control('reconcile-next', {})
            self.assertEqual(before, (self.api.planner.issue, self.api.planner.comments))
        path.write_text(json.dumps(payload))
        original = deepcopy(self.api.scheduler.runs[17])
        for field_name, value in (('workflow_id', 8), ('path', '.github/workflows/pr-review.yml'),
                                  ('head_branch', 'topic'), ('status', 'in_progress'),
                                  ('head_repository', {'id': 1286600062, 'full_name': 'attacker/lmdj'})):
            with self.subTest(actual=field_name):
                self.api.scheduler.runs[17] = {**original, field_name: value}
                # Even a consistent forged hint cannot alter the actual source contract.
                path.write_text(json.dumps({**payload, 'workflow_run': self.api.scheduler.runs[17]}))
                with self.assertRaises(Exception):
                    self.control('reconcile-next', {})
                self.assertEqual(before, (self.api.planner.issue, self.api.planner.comments))
        self.api.scheduler.runs[17] = original

    def test_discovery_missing_storage_and_injected_request_never_write(self):
        before = deepcopy((self.api.planner.issue, self.api.planner.comments))
        for request in ({'source_request_id': self.request['id']}, {'scheduler': {}}, {'progress': {}}, {'plan': {}}):
            with self.assertRaisesRegex(r.CanaryError, 'caller evidence'):
                self.control('reconcile-next', request)
        with self.assertRaises(r.CanaryError):
            entry.control('reconcile-next', {}, {}, root=self.f.root, environment=self.env, api=self.api)
        self.assertEqual(before, (self.api.planner.issue, self.api.planner.comments))

    def test_automatic_actual_repository_and_workflow_metadata_must_match(self):
        self.automatic()
        before = deepcopy((self.api.planner.issue, self.api.planner.comments))
        for suffix, document in (('', {'id': 9, 'full_name': 'endaye/lmdj'}),
                                 ('/actions/workflows/7', {'id': 8, 'path': fixture.runtime.WORKFLOW}),
                                 ('/actions/workflows/7', {'id': 7, 'path': entry.PlanningRuntime.workflow})):
            with self.subTest(suffix=suffix, document=document):
                key = ('GET', '/repos/endaye/lmdj' + suffix)
                self.api.scheduler.pages_override[key] = document
                with self.assertRaises(Exception):
                    self.control('reconcile-next', {})
                self.assertEqual(before, (self.api.planner.issue, self.api.planner.comments))
                self.api.scheduler.pages_override.pop(key)

    def test_automatic_hint_requires_both_repository_identities(self):
        path, payload = self.automatic()
        before = deepcopy((self.api.planner.issue, self.api.planner.comments))
        for name in ('repository', 'head_repository'):
            with self.subTest(name=name):
                incomplete = deepcopy(payload)
                incomplete['workflow_run'].pop(name)
                path.write_text(json.dumps(incomplete))
                with self.assertRaisesRegex(r.CanaryError, 'repository identity differs'):
                    self.control('reconcile-next', {})
                self.assertEqual(before, (self.api.planner.issue, self.api.planner.comments))

    def test_discovery_requires_explicit_bootstrap(self):
        # Independent fixture journal after explicit init but before bootstrap.
        saved_body = json.loads(self.api.planner.issue['body'])
        saved_body['payload'] = {'head': None, 'pending': None}
        self.api.planner.issue['body'] = json.dumps(saved_body)
        self.api.planner.comments.clear()
        before = deepcopy((self.api.planner.issue, self.api.planner.comments))
        with self.assertRaisesRegex(r.CanaryError, 'explicitly bootstrapped'):
            self.control('reconcile-next', {})
        self.assertEqual(before, (self.api.planner.issue, self.api.planner.comments))

    def test_discovery_missing_or_pending_scheduler_source_never_repairs_it(self):
        for corruption in ('missing', 'pending'):
            with self.subTest(corruption=corruption):
                issue, comments = deepcopy(self.api.scheduler.issue), deepcopy(self.api.scheduler.comments)
                if corruption == 'missing':
                    self.api.scheduler.comments.pop()
                else:
                    self.api.scheduler.lose = 'observe'
                    journal = self.f.make(18).journal()
                    events = journal.load()
                    with self.assertRaises(Exception):
                        journal.append({'id': 'unresolved-source', 'epoch': self.f.config['epoch'],
                            'generation': len(events), 'type': 'observe',
                            'data': {'target': self.target, 'descends_pending': True}})
                before = deepcopy((self.api.scheduler.issue, self.api.scheduler.comments,
                                   self.api.planner.issue, self.api.planner.comments))
                with self.assertRaises(Exception):
                    self.control('reconcile-next', {})
                self.assertEqual(before, (self.api.scheduler.issue, self.api.scheduler.comments,
                                         self.api.planner.issue, self.api.planner.comments))
                self.api.scheduler.issue, self.api.scheduler.comments = issue, comments

    def test_fresh_process_replays_full_observation_then_discovers_next_source(self):
        first = self.control('reconcile-next', {})
        newer = self.next_batch('apps/creator-web/src/after-restart.ts')
        snapshot = {'root': str(self.f.root), 'config': self.config, 'environment': self.env,
                    'first_source': self.request['id'], 'stores': {}}
        for name in ('scheduler', 'planner'):
            api = getattr(self.api, name)
            snapshot['stores'][name] = {key: getattr(api, key) for key in ('sha', 'issue', 'comments', 'runs', 'jobs')}
        code = '''
import json, os, sys
sys.path.insert(0, 'tests/build')
from ci_canary_planning_entry_test import PairHttp, entry
from unittest.mock import patch
value = json.load(sys.stdin)
api = PairHttp(value['environment']['GITHUB_SHA'])
for name, document in value['stores'].items():
    for key, data in document.items():
        setattr(getattr(api, name), key, {int(k): v for k, v in data.items()} if key in ('runs', 'jobs') else data)
def forbidden(*args, **kwargs):
    raise AssertionError('completed observation must not read scheduler or invoke a model')
from tools.canary import assessment_runtime
assessment_runtime.execute = forbidden
kwargs = dict(root=value['root'], environment=value['environment'], api=api)
with patch.object(entry, 'scheduler_state', side_effect=forbidden):
    original = entry.control('recover', value['config'], {'source_request_id': value['first_source']}, **kwargs)
next_result = entry.control('reconcile-next', value['config'], {}, **kwargs)
runtime = entry.PlanningRuntime(value['config'], **kwargs)
state = entry.storage.Plans(runtime.journal(), runtime.lock_held, value['config']['epoch']).load()
assert not any(method in ('PATCH', 'POST') and path != '/graphql' for method, path, body in api.scheduler.calls)
assert not any('/artifacts' in path for method, path, body in api.scheduler.calls + api.planner.calls)
print(json.dumps({'pid': os.getpid(), 'original': original, 'next': next_result,
                  'state': state, 'comments': api.planner.comments}))
'''
        child = subprocess.run([sys.executable, '-c', code], cwd=ROOT, input=json.dumps(snapshot),
                               text=True, capture_output=True, timeout=30)
        self.assertEqual(child.returncode, 0,
            'why: real-process discovery recovery failed; remedy: preserve the complete authenticated state: ' + child.stderr)
        result = json.loads(child.stdout)
        self.assertNotEqual(result['pid'], os.getpid())
        self.assertEqual(r.canonical(result['original']), r.canonical(first))
        self.assertEqual(result['next']['intent']['source_request_id'], newer['id'])
        self.assertEqual(result['state']['active'], self.request['id'])
        self.assertEqual(result['state']['pending'], newer['id'])
        self.assertIsNone(result['state']['unfinished'])
        self.assertEqual(result['state']['progress'], r.initial_progress('endaye/lmdj'))
        self.assertEqual(result['comments'][:len(self.api.planner.comments)], self.api.planner.comments)

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
        with self.assertRaisesRegex(r.CanaryError, 'API event differs'):
            self.control()
        self.assertEqual(before, self.api.planner.comments)
        with self.assertRaisesRegex(r.CanaryError, 'manual invocation'):
            self.control(GITHUB_EVENT_NAME='push')
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


class BaselineEntryTests(unittest.TestCase):
    def setUp(self):
        self.journey = JourneyTests()
        self.journey.setUp()
        self.addCleanup(self.journey.doCleanups)
        j = self.journey
        j.f.git('config', 'core.filemode', 'true')
        # This complete temporary Git repository has its own reviewed fixture
        # control/config. It is not an adoption of the real approved main SHA.
        self.approval = json.loads((ROOT / entry.BASELINE_PATH).read_text())
        for host in self.approval['hosts']:
            path = j.f.root / host['path']
            manifest = json.loads(path.read_text())
            manifest['version'] = host['version']
            path.write_text(json.dumps(manifest))
        (j.f.root / 'apps/creator-web/CHANGELOG.md').write_text('Existing history must not be backfilled.\n')
        self.baseline = self.commit_control('Approved fixture version baseline')
        self.approval['revision'] = self.baseline
        self.write_approval(self.approval)

    def commit_control(self, message):
        j = self.journey
        j.f.git('add', '.')
        j.f.git('commit', '-qm', message)
        sha = j.f.git('rev-parse', 'HEAD')
        j.api.scheduler.sha = j.api.planner.sha = sha
        observer = max(j.api.planner.runs) + 1
        j.api.planner.add_run(observer)
        j.env.update(GITHUB_SHA=sha, GITHUB_RUN_ID=str(observer))
        return sha

    def write_approval(self, document):
        (self.journey.f.root / entry.BASELINE_PATH).write_text(json.dumps(document, indent=2) + '\n')
        return self.commit_control('Reviewed fixture approval configuration')

    def adopt(self, **env):
        return self.journey.control('adopt-version-baseline', {}, **env)

    def assert_no_delivery_progress(self, progress):
        self.assertEqual(progress['deployments'], dict.fromkeys(r.SITES))
        self.assertIsNone(progress['formal'])

    def scheduler_bytes(self):
        j = self.journey
        runtime = entry.PlanningRuntime(j.config, root=j.f.root, environment=j.env, api=j.api)
        runtime.authenticate_current()
        state = entry.scheduler_state(runtime, entry.source_storage(runtime))
        return r.canonical({'state': state, 'issue': j.api.scheduler.issue, 'comments': j.api.scheduler.comments})

    def cli_process(self, operation='adopt-version-baseline', request=None):
        """Actual main()/argparse/output path; only remote HTTP is fixture data."""
        j = self.journey
        snapshot = {'root': str(j.f.root), 'config': j.config, 'environment': j.env,
                    'operation': operation, 'request': request or {},
                    'stores': {name: {key: getattr(getattr(j.api, name), key)
                        for key in ('sha', 'issue', 'comments', 'runs', 'jobs')} for name in ('scheduler', 'planner')}}
        code = '''
import json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, 'tests/build')
from ci_canary_planning_entry_test import PairHttp, entry
value = json.load(sys.stdin)
api = PairHttp(value['environment']['GITHUB_SHA'])
for name, document in value['stores'].items():
    for key, data in document.items():
        setattr(getattr(api, name), key, {int(k): v for k, v in data.items()} if key in ('runs', 'jobs') else data)
from tools.canary import assessment_runtime
def forbidden(*args, **kwargs):
    raise AssertionError('planning must not invoke a model')
assessment_runtime.execute = forbidden
with tempfile.TemporaryDirectory() as directory:
    env = {**value['environment'], 'PLANNING_OPERATION': value['operation'],
           'PLANNING_STORAGE': json.dumps(value['config']), 'PLANNING_REQUEST': json.dumps(value['request']),
           'GITHUB_STEP_SUMMARY': directory + '/summary'}
    sys.argv = ['planning_entry', '--root', value['root'], '--directory', directory]
    with patch.dict(os.environ, env, clear=True), patch.object(entry.batch_runtime, 'UrllibGitHubApi', return_value=api):
        entry.main()
    answer = json.loads((Path(directory) / 'planning.json').read_text())
    assert not any(method in ('PATCH', 'POST') and path != '/graphql' for method, path, body in api.scheduler.calls)
    print(json.dumps({'pid': os.getpid(), 'answer': answer, 'issue': api.planner.issue,
                     'comments': api.planner.comments, 'calls': api.planner.calls}))
'''
        child = subprocess.run([sys.executable, '-c', code], cwd=ROOT, input=json.dumps(snapshot),
                               text=True, capture_output=True, timeout=30)
        self.assertEqual(child.returncode, 0,
            'why: actual CLI baseline journey failed; remedy: preserve complete Git/journal evidence: ' + child.stderr)
        result = json.loads(child.stdout)
        self.assertNotEqual(result['pid'], os.getpid())
        j.api.planner.issue, j.api.planner.comments = result['issue'], result['comments']
        return result

    def test_baseline_adoption_is_an_actual_manual_control_operation(self):
        self.assertEqual(entry.request_for('adopt-version-baseline', {}), {},
            'why: approved baseline has no integrated entry; remedy: wire the existing planning command')

    def test_actual_cli_adoption_restart_and_real_result_plan_keep_independent_baselines(self):
        j = self.journey
        j.next_batch('scripts/ci/pre-adoption-failure.py', failed_job='core-ubuntu')
        missing = j.next_batch('apps/creator-web/src/before-adoption.ts', missing_verdict=True)
        before = self.scheduler_bytes()
        self.assertTrue(json.loads(before)['state']['debts'])
        self.assertTrue(json.loads(before)['state']['failures'])
        history = (j.f.root / 'apps/creator-web/CHANGELOG.md').read_bytes()
        first = self.cli_process()['answer']
        self.assertEqual(first['action'], 'baseline-adopted')
        self.assertFalse(first['admission_evidence'])
        self.assertEqual(first['progress']['version_accounted'],
                         {'revision': self.baseline, 'receipt_digest': first['receipt']['digest']})
        self.assertEqual(first['receipt']['approval'], self.approval)
        self.assert_no_delivery_progress(first['progress'])
        self.assertEqual(self.scheduler_bytes(), before)
        j.move_main()
        replay = self.cli_process()
        self.assertEqual(r.canonical(replay['answer']), r.canonical(first))
        self.assertFalse(any(method in ('PATCH', 'POST') and path != '/graphql'
                             for method, path, body in replay['calls']))
        self.assertEqual((j.f.root / 'apps/creator-web/CHANGELOG.md').read_bytes(), history)
        later = j.next_batch('apps/creator-web/src/after-adoption.ts')
        self.assertEqual(later['base'], missing['target'])
        self.assertNotEqual(later['base'], self.baseline)
        before = self.scheduler_bytes()
        result = j.control('observe-result', {'source_request_id': later['id']})
        version_interval = result['decision']['plan']['version_interval']
        expected = entry.test_scope.collect_interval(j.f.root, self.baseline, later['target'])
        self.assertEqual(version_interval, {'kind': 'complete', **expected})
        self.assertIn(missing['target'], [commit['sha'] for commit in version_interval['commits']])
        self.assertEqual(result['intent']['progress'], first['progress'])
        self.assertEqual(result['decision']['plan']['test_floor']['kind'], 'full')
        for site in r.SITES:
            self.assertEqual(result['decision']['plan']['site_intervals'][site]['kind'], 'bootstrap')
            self.assertEqual(result['decision']['plan']['site_test_floors'][site]['kind'], 'full')
        self.assertEqual(self.scheduler_bytes(), before)
        self.assertEqual(self.adopt(), first)
        self.assertEqual(j.control('recover', {'source_request_id': later['id']}), result)

    def test_approval_is_only_frozen_git_and_historical_manifest_not_dirty_or_current_bytes(self):
        j = self.journey
        for host in self.approval['hosts']:
            path = j.f.root / host['path']
            document = json.loads(path.read_text())
            document['version'] = '9.9.9'
            path.write_text(json.dumps(document))
        self.commit_control('Current versions do not rewrite the approved baseline')
        (j.f.root / entry.BASELINE_PATH).write_text('{"revision":"unreviewed"}')
        first = self.adopt()
        self.assertEqual(first['receipt']['approval'], self.approval)
        self.assertEqual([item['version'] for item in first['receipt']['manifests']], ['4.1.0', '4.1.0'])
        self.assertEqual([json.loads(item['bytes'])['version'] for item in first['receipt']['manifests']],
                         ['4.1.0', '4.1.0'])

    def test_missing_bootstrap_and_existing_observations_are_not_migrated(self):
        j = self.journey
        j.control('observe-result', {'source_request_id': j.next_batch('apps/creator-web/src/observed.ts')['id']})
        before = deepcopy((j.api.planner.issue, j.api.planner.comments))
        with self.assertRaises(r.CanaryError):
            self.adopt()
        self.assertEqual(before, (j.api.planner.issue, j.api.planner.comments))
        # A separate fixture state immediately after explicit init, not a reset operation.
        document = json.loads(j.api.planner.issue['body'])
        document['payload'] = {'head': None, 'pending': None}
        j.api.planner.issue['body'] = json.dumps(document)
        j.api.planner.comments.clear()
        before = deepcopy((j.api.planner.issue, j.api.planner.comments))
        with self.assertRaises(r.CanaryError):
            self.adopt()
        self.assertEqual(before, (j.api.planner.issue, j.api.planner.comments))

    def test_caller_evidence_automatic_attempt_ref_and_lock_cannot_adopt(self):
        j = self.journey
        before = deepcopy((j.api.planner.issue, j.api.planner.comments))
        for request in ({'revision': self.baseline}, {'progress': {}}, {'receipt': {}}, {'manifests': []}):
            with self.subTest(request=request), self.assertRaises(r.CanaryError):
                j.control('adopt-version-baseline', request)
        for key, value in (('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_RUN_ID', '17'),
                           ('GITHUB_REF', 'refs/heads/topic'), ('BATCH_WRITER_LOCK', 'self-test-report')):
            with self.subTest(key=key), self.assertRaises(Exception):
                self.adopt(**{key: value})
        j.automatic()
        with self.assertRaisesRegex(r.CanaryError, 'readiness or operation'):
            self.adopt()
        self.assertEqual(before, (j.api.planner.issue, j.api.planner.comments))

    def test_changed_unapproved_policy_or_host_inventory_never_writes(self):
        j = self.journey
        for key, value in (('decision_ref', 'https://github.com/endaye/lmdj/pull/1'),
                           ('repository', 'attacker/lmdj'), ('historical_changelog', 'backfill'),
                           ('hosts', self.approval['hosts'][:1])):
            with self.subTest(key=key):
                self.write_approval({**self.approval, key: value})
                before = deepcopy((j.api.planner.issue, j.api.planner.comments))
                with self.assertRaises(r.CanaryError):
                    self.adopt()
                self.assertEqual(before, (j.api.planner.issue, j.api.planner.comments))

    def test_wrong_manifest_version_and_symlink_or_executable_sources_never_write(self):
        j = self.journey
        path = j.f.root / self.approval['hosts'][0]['path']
        manifest = json.loads(path.read_text())
        manifest['version'] = '4.0.0'
        path.write_text(json.dumps(manifest))
        wrong = self.commit_control('Wrong historical Host manifest')
        self.write_approval({**self.approval, 'revision': wrong})
        before = deepcopy((j.api.planner.issue, j.api.planner.comments))
        with self.assertRaisesRegex(r.CanaryError, 'manifest differs'):
            self.adopt()
        self.assertEqual(before, (j.api.planner.issue, j.api.planner.comments))
        self.write_approval(self.approval)
        config = j.f.root / entry.BASELINE_PATH
        config.chmod(0o755)
        self.commit_control('Executable config is not canonical evidence')
        with self.assertRaisesRegex(r.CanaryError, 'regular nonexecutable'):
            self.adopt()
        config.unlink()
        config.symlink_to('policy.json')
        self.commit_control('Symlink config is not canonical evidence')
        with self.assertRaisesRegex(r.CanaryError, 'regular nonexecutable'):
            self.adopt()
        self.assertEqual(before, (j.api.planner.issue, j.api.planner.comments))

    def test_baseline_must_be_on_main_first_parent_even_when_side_commit_was_merged(self):
        j = self.journey
        j.f.git('checkout', '-qb', 'fix/baseline-side-fixture', self.baseline)
        (j.f.root / 'side-only.txt').write_text('Side branch is not a first-parent baseline.\n')
        j.f.git('add', '.')
        j.f.git('commit', '-qm', 'Side branch candidate')
        side = j.f.git('rev-parse', 'HEAD')
        j.f.git('checkout', '-q', 'main')
        self.write_approval({**self.approval, 'revision': side})
        before = deepcopy((j.api.planner.issue, j.api.planner.comments))
        with self.assertRaisesRegex(entry.test_scope.ScopeError, "baseline is not on target's first-parent history"):
            self.adopt()
        j.f.git('merge', '--no-ff', '-qm', 'Merge side candidate without making it first-parent', 'fix/baseline-side-fixture')
        j.move_main()
        with self.assertRaisesRegex(entry.test_scope.ScopeError, "baseline is not on target's first-parent history"):
            self.adopt()
        self.assertEqual(before, (j.api.planner.issue, j.api.planner.comments))

    def test_older_green_discovery_retains_historical_source_without_progress(self):
        j = self.journey
        adopted = self.adopt()
        scheduler = self.scheduler_bytes()
        result = j.control('reconcile-next', {})
        self.assertEqual(result['action'], 'historical')
        self.assertEqual(result['slot'], 'historical')
        self.assertEqual(result['decision']['source']['request_id'], j.request['id'])
        self.assertEqual(result['decision']['source']['target_sha'], j.request['target'])
        self.assertEqual(result['decision']['source']['status'], 'passed')
        self.assertEqual(result['decision']['baseline_receipt'], adopted['receipt'])
        self.assertIsNone(result['decision']['plan'])
        self.assertFalse(result['admission_evidence'])
        self.assertEqual(self.scheduler_bytes(), scheduler)
        self.assertEqual(j.planning_state()['progress'], adopted['progress'])
        self.assertEqual(set(j.planning_state()['observations']), {j.request['id']})
        for key in ('active', 'pending', 'unfinished'):
            self.assertIsNone(j.planning_state()[key])

    def test_historical_restart_then_later_plan_preserves_full_bootstrap_and_all_version_commits(self):
        j = self.journey
        failed = j.next_batch('scripts/ci/historical-journey-failure.py', failed_job='core-ubuntu')
        missing = j.next_batch('apps/creator-web/src/historical-journey-missing.ts', missing_verdict=True)
        adopted = self.cli_process()['answer']
        before = self.scheduler_bytes()
        self.assertTrue(json.loads(before)['state']['failures'])
        self.assertTrue(json.loads(before)['state']['debts'])
        historic = self.cli_process('reconcile-next')['answer']
        self.assertEqual(historic['action'], 'historical')
        self.assertEqual(historic['decision']['baseline_receipt'], adopted['receipt'])
        prefix = deepcopy(j.api.planner.comments)
        j.move_main()
        replay = self.cli_process('recover', {'source_request_id': j.request['id']})
        self.assertEqual(r.canonical(replay['answer']), r.canonical(historic))
        self.assertEqual(j.api.planner.comments, prefix)
        self.assertFalse(any(method in ('PATCH', 'POST') and path != '/graphql'
                             for method, path, body in replay['calls']))
        for request, status in ((failed, 'failed'), (missing, 'missing')):
            ignored = self.cli_process('reconcile-next')['answer']
            self.assertEqual(ignored['action'], 'ignored')
            self.assertEqual(ignored['intent']['source_request_id'], request['id'])
            self.assertEqual(ignored['decision']['source']['status'], status)
        self.assertEqual(self.scheduler_bytes(), before)
        later = j.next_batch('apps/creator-web/src/historical-journey-later.ts')
        before = self.scheduler_bytes()
        planned = self.cli_process('reconcile-next')['answer']
        self.assertEqual(planned['action'], 'planned')
        self.assertEqual(planned['slot'], 'active')
        self.assertEqual(planned['intent']['source_request_id'], later['id'])
        plan = planned['decision']['plan']
        self.assertEqual(plan['version_interval'], {'kind': 'complete',
            **entry.test_scope.collect_interval(j.f.root, self.baseline, later['target'])})
        for site in r.SITES:
            self.assertEqual(plan['site_intervals'][site]['kind'], 'bootstrap')
            self.assertEqual(plan['site_test_floors'][site]['kind'], 'full')
        self.assertEqual(plan['test_floor']['kind'], 'full')
        self.assertEqual(self.cli_process('reconcile-next')['answer']['action'], 'idle')
        self.assertEqual(j.planning_state()['progress'], adopted['progress'])
        self.assertEqual(self.scheduler_bytes(), before)

    def historical_inputs(self):
        j = self.journey
        runtime = entry.PlanningRuntime(j.config, root=j.f.root, environment=j.env, api=j.api)
        runtime.authenticate_current()
        state = j.planning_state()
        return dict(scheduler=entry.scheduler_state(runtime, entry.source_storage(runtime)),
            source_request_id=j.request['id'], main_sha=runtime.inputs.main,
            control_sha=runtime.control, progress=state['progress'], baseline_receipt=state['baseline_receipt'])

    def test_direct_planner_without_adopted_receipt_still_refuses_reverse_interval(self):
        self.adopt()
        inputs = self.historical_inputs()
        inputs.pop('baseline_receipt')
        with self.assertRaisesRegex(r.CanaryError, "baseline is not on target's first-parent history"):
            entry.planning.plan_after_result(self.journey.f.root, **inputs)

    def test_historical_receipt_does_not_authorize_changed_progress(self):
        self.adopt()
        inputs = self.historical_inputs()
        pointer = {'revision': self.baseline, 'receipt_digest': 'a' * 64}
        for key in ('version_accounted', 'formal', *r.SITES):
            progress = deepcopy(inputs['progress'])
            if key in r.SITES:
                progress['deployments'][key] = pointer
            else:
                progress[key] = pointer
            with self.subTest(key=key), self.assertRaisesRegex(r.CanaryError, 'initial adopted progress'):
                entry.planning.plan_after_result(self.journey.f.root, **{**inputs, 'progress': r.seal(progress)})

    def test_corrupt_historical_verdict_is_not_a_skippable_observation(self):
        j = self.journey
        self.adopt()
        inputs = self.historical_inputs()
        inputs['scheduler']['results'][j.request['id']]['reference'] = 'invalid-retained-verdict'
        before = deepcopy((j.api.planner.issue, j.api.planner.comments))
        with patch.object(entry, 'scheduler_state', return_value=inputs['scheduler']), self.assertRaises(r.CanaryError):
            j.control('reconcile-next', {})
        self.assertEqual(before, (j.api.planner.issue, j.api.planner.comments))
        self.assertFalse(j.planning_state()['observations'])

    def test_target_equal_to_baseline_still_plans_first_site_bootstrap(self):
        j = self.journey
        request = j.next_batch('apps/creator-web/src/baseline-target.ts')
        self.approval['revision'] = request['target']
        self.write_approval(self.approval)
        self.adopt()
        result = j.control('observe-result', {'source_request_id': request['id']})
        self.assertEqual(result['action'], 'planned')
        self.assertEqual(result['slot'], 'active')
        self.assertEqual(result['decision']['plan']['version_interval']['commits'], [])
        self.assertEqual(result['decision']['plan']['test_floor']['kind'], 'full')

    def test_historical_intent_lost_ack_recovers_original_bytes_in_new_process(self):
        j = self.journey
        self.adopt()
        j.api.planner.lose = 'intent'
        with self.assertRaisesRegex(r.CanaryError, 'append outcome is unresolved'):
            j.control('reconcile-next', {})
        intent = j.planning_state()['observations'][j.request['id']]['intent']
        prefix = deepcopy(j.api.planner.comments)
        j.move_main()
        result = self.cli_process('reconcile-next')['answer']
        self.assertEqual(result['action'], 'historical')
        self.assertEqual(result['intent'], intent)
        self.assertEqual(r.digest(result['decision']), intent['decision_digest'])
        self.assertEqual(j.api.planner.comments[:len(prefix)], prefix)
        self.assertIsNone(j.planning_state()['unfinished'])
        self.assertIsNone(j.planning_state()['active'])

    def test_historical_chunk_and_complete_ack_recover_without_duplicate_posts(self):
        for kind in ('blob', 'complete'):
            with self.subTest(kind=kind):
                other = BaselineEntryTests()
                other.setUp()
                self.addCleanup(other.doCleanups)
                j = other.journey
                adopted = other.adopt()
                j.api.planner.lose = kind
                with self.assertRaisesRegex(r.CanaryError, 'append outcome is unresolved'):
                    j.control('reconcile-next', {})
                j.planning_state()
                prefix = deepcopy(j.api.planner.comments)
                recovered = other.cli_process('recover', {'source_request_id': j.request['id']})['answer']
                self.assertEqual(recovered['action'], 'historical')
                self.assertEqual(recovered['decision']['baseline_receipt'], adopted['receipt'])
                self.assertEqual(j.api.planner.comments[:len(prefix)], prefix)
                self.assertIsNone(j.planning_state()['unfinished'])
                self.assertEqual(j.planning_state()['progress'], adopted['progress'])

    def test_lost_adoption_ack_recovers_in_new_cli_process_without_second_post(self):
        j = self.journey
        j.api.planner.lose = 'adopt-version-baseline'
        with self.assertRaisesRegex(r.CanaryError, 'append outcome is unresolved'):
            self.adopt()
        comments = deepcopy(j.api.planner.comments)
        recovered = self.cli_process()
        self.assertEqual(recovered['comments'], comments)
        self.assertFalse(any(method == 'POST' and path != '/graphql' for method, path, body in recovered['calls']))
        self.assertEqual(recovered['answer']['receipt']['approval'], self.approval)
        self.assertEqual(recovered['answer'], self.adopt())

    def test_shipped_config_preserves_the_exact_owner_approved_revision_and_versions(self):
        approval = entry.storage.validate_baseline_approval(json.loads((ROOT / entry.BASELINE_PATH).read_text()))
        self.assertEqual(approval['revision'], 'a81faad3b85d362e3e44541cd28ee21dac6848a4')
        self.assertEqual([host['version'] for host in approval['hosts']], ['4.1.0', '4.1.0'])
        # Historical Git authentication belongs to the complete temporary Git
        # journeys above; ordinary CI-contract checkout may legitimately be shallow.


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / entry.PlanningRuntime.workflow
        self.source = self.path.read_text()
        self.job = block(self.source, 'controller', 2)

    def test_manual_operation_inventory_includes_the_integrated_baseline_entry(self):
        options = field(block(self.source, 'operation', 6), 'options', 8)
        values = [value.strip() for value in options.removeprefix('[').removesuffix(']').split(',')]
        self.assertEqual(set(values), set(entry.OPERATIONS))
        self.assertEqual(len(values), len(entry.OPERATIONS))
        self.assertIn('adopt-version-baseline', values)

    def test_automatic_admission_coalesces_without_cancelling_running_or_manual_work(self):
        admission = scalars(block(self.source, 'concurrency', 0), 2)
        self.assertEqual(admission, {
            'group': "canary-planning-wakeup-${{ github.event_name == 'workflow_dispatch' && github.run_id || 'automatic' }}",
            'cancel-in-progress': 'false', 'queue': 'single'})
        self.assertEqual(wakeup_group(self.source, 'workflow_run', 100),
                         wakeup_group(self.source, 'workflow_run', 101))
        self.assertNotEqual(wakeup_group(self.source, 'workflow_dispatch', 100),
                            wakeup_group(self.source, 'workflow_dispatch', 101))
        self.assertNotEqual(wakeup_group(self.source, 'workflow_dispatch', 100),
                            wakeup_group(self.source, 'workflow_run', 100))
        self.assertEqual(scalars(block(self.job, 'concurrency', 4), 6),
                         {'group': 'canary-planning', 'cancel-in-progress': 'false', 'queue': 'max'})

    def test_manual_and_gated_completion_share_single_short_controller(self):
        triggers = block(self.source, 'on', 0)
        self.assertEqual(re.findall(r'^  ([\w-]+):', triggers, re.M), ['workflow_run', 'workflow_dispatch'])
        self.assertEqual(scalars(block(triggers, 'workflow_run', 2), 4),
                         {'workflows': '["Self-test Report"]', 'types': '[completed]'})
        self.assertEqual([job.job_id for job in jobs_in(self.path)], ['controller'])
        self.assertEqual(' '.join(field(self.job, 'if', 4).split()),
            "github.ref == 'refs/heads/main' && github.run_attempt == '1' && "
            "(github.event_name == 'workflow_dispatch' || "
            "(github.event_name == 'workflow_run' && vars.CANARY_PLANNING_AUTOMATIC_READY == 'true'))")
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
                         {'GITHUB_TOKEN', 'BATCH_WRITER_LOCK', 'PLANNING_OPERATION', 'PLANNING_STORAGE',
                          'PLANNING_REQUEST', 'CANARY_PLANNING_AUTOMATIC_READY'})
        values = scalars(block(self.job, 'env', 8), 10)
        self.assertEqual(values['CANARY_PLANNING_AUTOMATIC_READY'], '${{ vars.CANARY_PLANNING_AUTOMATIC_READY }}')
        self.assertEqual(values['PLANNING_OPERATION'], "${{ github.event_name == 'workflow_run' && 'reconcile-next' || inputs.operation }}")
        self.assertEqual(values['PLANNING_STORAGE'], "${{ github.event_name == 'workflow_run' && vars.CANARY_PLANNING_STORAGE || inputs.storage }}")
        self.assertEqual(values['PLANNING_REQUEST'], "${{ github.event_name == 'workflow_run' && '{}' || inputs.request }}")
        self.assertIn('ref: ${{ github.sha }}', self.job)
        self.assertIn('persist-credentials: false', self.job)

    def test_complete_artifact_and_module_entry_are_wired(self):
        self.assertIn('python3 -m tools.canary.planning_entry --directory ', self.job)
        self.assertIn('/planning.json', self.job)
        self.assertIn('if-no-files-found: error', self.job)
        self.assertIn('name: canary-planning-${{ github.run_id }}-${{ github.run_attempt }}', self.job)


if __name__ == '__main__':
    unittest.main()
