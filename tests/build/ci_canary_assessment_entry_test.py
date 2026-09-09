"""Manual Actions entry composition; fixtures are not live isolation acceptance."""
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# This legacy fixture installs self_test_report in sys.modules. Load it before
# consumers so full discovery shares the same exception classes as production.
import ci_self_test_report_test as report_fixture
from tools.canary import assessment_entry as entry
from tools.canary import assessment as a, assessment_handoff as h, records as r
import ci_batch_runtime_test as fixture
import ci_canary_assessment_runtime_test as process_fixture
from ci_self_test_report_workflow_test import block, field, scalars
from workflow_inventory import jobs_in


class Http(fixture.Http):
    """Strict workflow-specific REST/GraphQL storage fixture, not API bypass."""
    def add_run(self, number):
        super().add_run(number)
        self.runs[number]['path'] = entry.AssessmentRuntime.workflow
        self.jobs[number][0]['name'] = entry.AssessmentRuntime.controller_job

    def _request(self, method, path, *, body=None, raw=False):
        prefix = '/repos/endaye/lmdj'
        if method == 'GET' and path == prefix + '/actions/workflows/7':
            self.calls.append((method, path, deepcopy(body)))
            return {'id': 7, 'path': entry.AssessmentRuntime.workflow}
        if method == 'GET' and path.startswith(prefix + '/contents/' + entry.AssessmentRuntime.workflow + '?ref='):
            assert path.split('?ref=')[1] in {run['head_sha'] for run in self.runs.values()}
            self.calls.append((method, path, deepcopy(body)))
            return {'type': 'file', 'path': entry.AssessmentRuntime.workflow, 'encoding': 'base64',
                    'content': base64.b64encode(b'trusted manual assessment workflow').decode()}
        return super()._request(method, path, body=body, raw=raw)


class PairHttp:
    def __init__(self, sha):
        self.assessment, self.outbox = Http(sha), Http(sha)
        self.outbox.issue.update(id='outbox-node', number=783)
        for name in ('runs', 'jobs', 'artifacts', 'downloads'):
            setattr(self.outbox, name, getattr(self.assessment, name))
        self.business = report_fixture.FakeGitHubApi()

    def _request(self, method, path, *, body=None, raw=False):
        is_outbox = '/issues/783' in path or path == '/graphql' and body['variables']['number'] == 783
        # Reuse the exact Issue endpoint fixture with a second independent
        # store; original payload writer identity still contains Issue 783.
        return (self.outbox if is_outbox else self.assessment)._request(
            method, path.replace('/issues/783', '/issues/782'), body=body, raw=raw)

    def __getattr__(self, name):
        return getattr(self.business, name)


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.git('config', 'commit.gpgsign', 'false')
        for name in (*a.MANIFESTS, entry.POLICY_PATH, entry.AssessmentRuntime.workflow):
            path = self.f.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'Complete assessment fixture')
        self.base = self.f.git('rev-parse', 'HEAD')
        changed = self.f.root / 'apps/creator-web/src/example.ts'
        changed.parent.mkdir(parents=True, exist_ok=True)
        changed.write_text('export const value = 1;\n')
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'Fixture Host correction')
        self.target = self.f.git('rev-parse', 'HEAD')
        self.api = PairHttp(self.target)
        self.env = {**self.f.env, 'GITHUB_SHA': self.target, 'BATCH_WRITER_LOCK': 'canary-assessment',
                    'CANARY_ASSESSMENT_EXECUTION_READY': 'true'}
        self.config = {'assessment': {**self.f.config, 'epoch': 'canary-assessment-inputs-fixture'},
                       'outbox': {**self.f.config, 'issue_number': 783, 'issue_node_id': 'outbox-node',
                                  'epoch': 'canary-assessment-outbox-fixture'}}
        self.control('init-assessment', {})
        self.control('init-outbox', {})

    def control(self, operation, request=None, run=17):
        return entry.control(operation, self.config, request if request is not None else {
            'base_sha': self.base, 'target_sha': self.target}, root=self.f.root,
            environment={**self.env, 'GITHUB_RUN_ID': str(run)}, api=self.api)

    def execute(self, claim, **extra):
        return entry.execute(claim['claim'], root=self.f.root, environment={**self.env, **extra})

    def terminal(self, claim, document):
        api = self.api.assessment
        api.runs[17].update(status='completed', conclusion='failure' if document['result']['state'] == 'blocked' else 'success')
        api.jobs[17][0].update(status='completed', conclusion='success')
        api.jobs[17].append({'id': 1701, 'run_id': 17, 'run_attempt': 1, 'name': h.PRODUCER_JOB,
            'status': 'completed', 'conclusion': 'success', 'steps': [
                {'name': name, 'status': 'completed', 'conclusion': 'success'} for name in (h.EXECUTE_STEP, h.UPLOAD_STEP)]})
        api.artifacts[17] = [{'id': 901, 'name': h.artifact_name(claim['claim']['context'], claim['claim']['executor']), 'expired': False}]
        api.downloads[901] = fixture.zipped({'assessment.json': document})
        api.add_run(18)

    def test_serialized_claim_blocked_execution_terminal_report_and_fresh_replay(self):
        claim = self.control('claim')
        self.assertEqual(claim['action'], 'execute')
        serialized = json.loads(json.dumps(claim))
        document = self.execute(serialized)  # No credentials; actual adapter, no model launch.
        self.assertEqual(document['result']['state'], 'blocked')
        self.assertEqual([item['error_class'] for item in document['result']['attempts']], ['missing_credential'] * 3)
        self.assertEqual(self.control('claim')['action'], 'pending')
        self.terminal(claim, document)
        request = {'input_digest': claim['input_digest']}
        self.env['CANARY_ASSESSMENT_EXECUTION_READY'] = 'false'
        with patch.object(entry.assessment_runtime, 'execute', side_effect=AssertionError('recovery must never execute models')):
            self.assertEqual(self.control('settle', request, 18)['state'], 'blocked')
            self.api.assessment.artifacts[17][0]['expired'] = True
            first = self.control('report', request, 18)
            self.assertEqual(first['report']['status'], 'delivered')
            self.assertEqual(self.control('report', request, 18), first)
        self.assertEqual(len(self.api.business.issues), 1)
        self.assertIn(document['result']['digest'], self.api.business.issues[0]['body'])
        self.assertEqual(self.api.business.issues[0]['state'], 'open')
        self.assertNotEqual(self.api.assessment.comments, self.api.outbox.comments)
        self.assertEqual(self.control('settle', request, 18)['action'], 'terminal')

    def test_disabled_claim_never_reaches_api_or_model(self):
        self.env['CANARY_ASSESSMENT_EXECUTION_READY'] = 'false'
        self.api.assessment.calls.clear()
        with self.assertRaisesRegex(r.CanaryError, 'readiness.*remedy:'):
            self.control('claim')
        self.assertFalse(self.api.assessment.calls)

    def test_wrong_operation_or_storage_identity_never_writes(self):
        before = deepcopy(self.api.assessment.comments)
        for field, value in (('issue_number', 807), ('issue_number', 817), ('issue_number', 849),
                             ('issue_number', 783), ('issue_node_id', 'outbox-node'),
                             ('epoch', 'canary-assessment-outbox-fixture')):
            with self.subTest(field=field, value=value):
                config = deepcopy(self.config)
                config['assessment'][field] = value
                with self.assertRaises(r.CanaryError):
                    entry.control('claim', config, {'base_sha': self.base, 'target_sha': self.target},
                                  root=self.f.root, environment=self.env, api=self.api)
        with self.assertRaisesRegex(r.CanaryError, 'mixes operations'):
            self.control('claim', {'base_sha': self.base, 'target_sha': self.target, 'input_digest': 'a' * 64})
        self.assertEqual(before, self.api.assessment.comments)

    def test_exact_run_attempt_ref_and_control_rejected_before_execution(self):
        claim = self.control('claim')
        for key, value in (('GITHUB_RUN_ID', '18'), ('GITHUB_RUN_ATTEMPT', '2'),
                           ('GITHUB_SHA', self.base), ('GITHUB_REF', 'refs/pull/1/merge'),
                           ('GITHUB_REPOSITORY', 'other/repo')):
            with self.subTest(key=key):
                with patch.object(entry.assessment_runtime, 'execute') as process:
                    with self.assertRaisesRegex(r.CanaryError, 'exact main executor'):
                        self.execute(claim, **{key: value})
                    process.assert_not_called()

    def test_resealed_mutated_input_cannot_replace_complete_git_bytes(self):
        claim = self.control('claim')
        context = claim['claim']['context']
        context['inputs'][0]['content'] += '\nforged'
        context['inputs'][0]['digest'] = r.digest(context['inputs'][0]['content'])
        claim['claim']['context'] = r.seal(context)
        claim['claim'] = r.seal(claim['claim'])
        with self.assertRaisesRegex(r.CanaryError, 'complete pinned Git input'):
            self.execute(claim)

    def test_checkout_control_is_independently_checked(self):
        claim = self.control('claim')
        self.f.git('checkout', '-q', '--detach', self.base)
        with self.assertRaisesRegex(r.CanaryError, 'checkout differs'):
            self.execute(claim)

    def test_policy_comes_from_frozen_git_not_modified_workspace(self):
        claim = self.control('claim')
        _, _, inputs = entry.authenticated_input(claim['claim'], root=self.f.root, environment=self.env)
        expected = entry.executor_policy(inputs)
        (self.f.root / entry.POLICY_PATH).write_text('{"models":"unreviewed"}')
        self.assertEqual(entry.executor_policy(inputs), expected)

    def test_production_runtime_still_rejects_assessment_workflow(self):
        original = fixture.runtime.Runtime(self.config['assessment'], root=self.f.root,
            environment={**self.env, 'BATCH_WRITER_LOCK': 'self-test-report'}, api=self.api)
        with self.assertRaisesRegex(fixture.batch.BatchError, 'provenance differs'):
            original.get_run(17, 1)

    def test_failed_upload_reports_reconciliation_and_never_resets_claim(self):
        claim = self.control('claim')
        self.terminal(claim, self.execute(claim))
        self.api.assessment.jobs[17][-1]['steps'][-1]['conclusion'] = 'failure'
        request = {'input_digest': claim['input_digest']}
        self.assertEqual(self.control('settle', request, 18)['action'], 'needs-reconciliation')
        self.assertEqual(self.control('report', request, 18)['report']['status'], 'delivered')
        self.assertEqual(self.control('claim', run=18)['action'], 'pending')

    def test_real_process_advice_persists_without_issue_or_ambient_credentials(self):
        claim = self.control('claim')
        process = process_fixture.RuntimeTests()
        process.setUp()
        self.addCleanup(process.doCleanups)
        process.fixture.context, process.fixture.target = claim['claim']['context'], self.target
        advice = process.fixture.advice()
        envelope = {'type': 'result', 'result': json.dumps(advice)}
        process.executable('glm', "assert 'GITHUB_TOKEN' not in os.environ\n"
            "assert 'KIMI_CODING_KEY' not in os.environ\nassert 'GROK_AUTH_JSON' not in os.environ\n"
            "assert os.environ['ANTHROPIC_API_KEY']=='fixture-only'\nprint(" + repr(json.dumps(envelope)) + ")\n")
        source = Path(process.config['glm']['executable'])
        actual_copy = entry.copy_verified_binary
        def fixture_copy(pin, target):
            if target.name == 'grok':
                raise OSError('grok unavailable must not block GLM')
            # Root ownership is exercised separately. The byte digest/copy and
            # bounded subprocess below are real; this is NOT runner acceptance.
            with patch.object(entry, '_root_owned'):
                actual_copy({'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}, target)
        with patch.object(entry, 'copy_verified_binary', side_effect=fixture_copy):
            document = self.execute(claim, ZAI_CODING_KEY='fixture-only', KIMI_CODING_KEY='not-for-glm',
                                    GROK_AUTH_JSON='not-for-glm', GITHUB_TOKEN='not-for-model')
        self.assertEqual(document['result']['selected_backend'], 'glm')
        self.assertEqual(len(document['result']['attempts']), 1)
        self.terminal(claim, document)
        request = {'input_digest': claim['input_digest']}
        self.assertEqual(self.control('settle', request, 18)['state'], 'advised')
        self.assertEqual(self.control('report', request, 18)['report']['status'], 'not-applicable')
        self.assertFalse(self.api.business.issues)

    def test_lost_claim_ack_can_only_reconcile_not_repeat_execution(self):
        self.api.assessment.lose = 'claim'
        with self.assertRaisesRegex(r.CanaryError, 'append outcome is unresolved'):
            self.control('claim')
        self.assertEqual(self.control('claim')['action'], 'pending')

    def test_unknown_business_post_recovers_exact_receipt_without_second_post(self):
        claim = self.control('claim')
        self.terminal(claim, self.execute(claim))
        request = {'input_digest': claim['input_digest']}
        class Crash(BaseException):
            pass
        original = self.api.business.create_issue
        def lost(**kwargs):
            original(**kwargs)
            raise Crash()
        with patch.object(self.api.business, 'create_issue', side_effect=lost):
            with self.assertRaises(Crash):
                self.control('report', request, 18)
        self.assertEqual(self.control('report', request, 18)['report']['status'], 'delivered')
        self.assertEqual(len([call for call in self.api.business.calls if call[0] == 'create_issue']), 1)

    def test_lost_complete_ack_reuses_retained_result_after_artifact_expiry(self):
        claim = self.control('claim')
        self.terminal(claim, self.execute(claim))
        request = {'input_digest': claim['input_digest']}
        self.api.assessment.lose = 'complete'
        with self.assertRaisesRegex(r.CanaryError, 'append outcome is unresolved'):
            self.control('settle', request, 18)
        self.api.assessment.artifacts[17][0]['expired'] = True
        with patch.object(entry.assessment_runtime, 'execute', side_effect=AssertionError('model replay')):
            self.assertEqual(self.control('settle', request, 18)['state'], 'blocked')

    def test_only_explicit_reserved_empty_issue_can_be_initialized_once(self):
        original = deepcopy(self.api.assessment.issue)
        with self.assertRaises(fixture.batch.BatchError):
            self.control('init-assessment', {})
        self.assertEqual(self.api.assessment.issue, original)

    def test_workflow_module_cli_retains_closed_result_and_safe_outputs(self):
        claim = self.control('claim')
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'input').mkdir()
            (directory / 'input/claim.json').write_bytes(r.canonical(claim['claim']))
            env = {**os.environ, **self.env, 'GITHUB_OUTPUT': str(directory / 'outputs'),
                   'GITHUB_STEP_SUMMARY': str(directory / 'summary')}
            for key in entry.assessment_runtime._SECRETS.values():
                env.pop(key, None)
            result = subprocess.run([sys.executable, '-m', 'tools.canary.assessment_entry', 'execute',
                '--root', str(self.f.root), '--directory', temp], cwd=ROOT, env=env,
                text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0,
                'why: actual workflow CLI did not retain its result; remedy: fix module wiring: ' + result.stderr)
            artifact = r.decode((directory / 'result/assessment.json').read_bytes())
            self.assertEqual(artifact, r.decode((directory / 'execute.json').read_bytes()))
            self.assertEqual(artifact['input_digest'], claim['input_digest'])
            self.assertEqual(artifact['result']['state'], 'blocked')
            self.assertEqual((directory / 'outputs').read_text().splitlines(), [
                'state=blocked', 'result_artifact=' + h.artifact_name(claim['claim']['context'], claim['claim']['executor'])])
            self.assertNotIn(self.env['GITHUB_TOKEN'], result.stdout + result.stderr + (directory / 'summary').read_text())

    def test_fresh_os_process_replays_complete_durable_receipt_without_model_or_post(self):
        claim = self.control('claim')
        self.terminal(claim, self.execute(claim))
        request = {'input_digest': claim['input_digest']}
        first = self.control('report', request, 18)
        self.api.assessment.runs[18].update(status='completed', conclusion='success')
        self.api.assessment.jobs[18][0].update(status='completed', conclusion='success')
        self.api.assessment.add_run(19)
        # Export complete simulated remote journal state; the fresh interpreter
        # has no parent Runtime, transport cache, receipt cache or result ZIP.
        snapshot = {'config': self.config, 'root': str(self.f.root), 'request': request,
                    'env': {**self.env, 'GITHUB_RUN_ID': '19', 'CANARY_ASSESSMENT_EXECUTION_READY': 'false'},
                    'stores': {name: {key: getattr(getattr(self.api, name), key) for key in ('issue', 'comments')}
                               for name in ('assessment', 'outbox')},
                    'runs': self.api.assessment.runs, 'jobs': self.api.assessment.jobs,
                    'business': {'issues': self.api.business.issues, 'comments': self.api.business.comments}}
        code = '''
import json, sys
sys.path.insert(0, 'tests/build')
from ci_canary_assessment_entry_test import PairHttp, entry
value = json.load(sys.stdin)
api = PairHttp(value['env']['GITHUB_SHA'])
for name, store in value['stores'].items():
    for key, document in store.items():
        setattr(getattr(api, name), key, document)
for name in ('assessment', 'outbox'):
    for key in ('runs', 'jobs'):
        setattr(getattr(api, name), key, {int(k): v for k, v in value[key].items()})
api.business.issues = value['business']['issues']
api.business.comments = {int(k): v for k, v in value['business']['comments'].items()}
def forbidden(*args, **kwargs):
    raise AssertionError('why: recovery repeated a model or POST; remedy: replay the original receipt')
entry.assessment_runtime.execute = forbidden
api.business.create_issue = api.business.create_comment = forbidden
result = entry.control('report', value['config'], value['request'], root=value['root'], environment=value['env'], api=api)
calls = api.assessment.calls + api.outbox.calls
assert not any(method == 'PATCH' or method == 'POST' and path != '/graphql' for method, path, body in calls)
assert not any('/artifacts' in path for method, path, body in calls)
print(json.dumps(result))
'''
        result = subprocess.run([sys.executable, '-c', code], input=json.dumps(snapshot), cwd=ROOT,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0,
            'why: fresh-process receipt replay failed; remedy: preserve complete journal identities: ' + result.stderr)
        self.assertEqual(json.loads(result.stdout), first)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / entry.AssessmentRuntime.workflow
        self.source = self.path.read_text()
        self.jobs = {job.job_id: block(self.source, job.job_id, 2) for job in jobs_in(self.path)}

    def test_manual_only_main_first_attempt_and_closed_job_inventory(self):
        import re
        triggers = block(self.source, 'on', 0)
        self.assertEqual(re.findall(r'^  ([\w-]+):', triggers, re.M), ['workflow_dispatch'],
            'why: assessment activated automatically; remedy: keep manual source entry until separate acceptance')
        self.assertEqual(set(self.jobs), {'controller', 'executor', 'outcome'})
        self.assertEqual(field(self.jobs['controller'], 'if', 4), "github.ref == 'refs/heads/main' && github.run_attempt == '1'")

    def test_writer_lock_is_short_and_not_held_across_model_job(self):
        import re
        self.assertIsNone(re.search(r'^concurrency:', self.source, re.M))
        lock = block(self.jobs['controller'], 'concurrency', 4)
        self.assertEqual(scalars(lock, 6), {'group': 'canary-assessment', 'cancel-in-progress': 'false', 'queue': 'max'})
        for name in ('executor', 'outcome'):
            directives = '\n'.join(line for line in self.jobs[name].splitlines() if not line.lstrip().startswith('#'))
            self.assertNotIn('concurrency:', directives)
            self.assertNotIn('BATCH_WRITER_LOCK:', directives)

    def test_model_job_has_no_privileged_token_and_uses_dedicated_isolated_routing(self):
        self.assertEqual(field(self.source, 'permissions', 0), '{}')
        self.assertEqual(scalars(block(self.jobs['controller'], 'permissions', 4), 6),
                         {'contents': 'read', 'actions': 'read', 'issues': 'write'})
        self.assertEqual(scalars(block(self.jobs['executor'], 'permissions', 4), 6), {'contents': 'read'})
        self.assertEqual(field(self.jobs['executor'], 'environment', 4), 'canary-assessment')
        self.assertEqual(field(self.jobs['executor'], 'runs-on', 4),
                         '[self-hosted, Linux, X64, lmdj-linux, lmdj-ai-isolated]')
        self.assertIn('- lmdj-ai-isolated', (ROOT / '.github/actionlint.yaml').read_text())
        env = block(self.jobs['executor'], 'env', 8)
        self.assertEqual(set(scalars(env, 10)), {'CANARY_ASSESSMENT_EXECUTION_READY', *entry.assessment_runtime._SECRETS.values()})
        self.assertTrue(all(job.is_self_hosted for job in jobs_in(self.path)),
                        'why: assessment could add hosted billing; remedy: keep all new jobs explicitly self-hosted')

    def test_exact_producer_steps_upload_before_separate_red_visibility(self):
        import re
        executor = self.jobs['executor']
        names = re.findall(r'^      - name: (.+)$', executor, re.M)
        self.assertEqual(names[-2:], [h.EXECUTE_STEP, h.UPLOAD_STEP])
        self.assertEqual(field(executor, 'name', 4), h.PRODUCER_JOB)
        self.assertEqual(field(self.jobs['controller'], 'name', 4), entry.AssessmentRuntime.controller_job)
        self.assertEqual(field(executor, 'needs', 4), 'controller')
        self.assertIn("if: needs.controller.outputs.action == 'execute'", executor)
        self.assertIn('name: ${{ needs.controller.outputs.input_artifact }}', executor)
        self.assertIn('name: ${{ steps.execute.outputs.result_artifact }}', executor)
        self.assertIn('/result/assessment.json', executor)
        self.assertIn('if-no-files-found: error', executor)
        self.assertIn('retention-days: 30', executor)
        directives = '\n'.join(line for line in executor.splitlines() if not line.lstrip().startswith('#'))
        for forbidden in ('continue-on-error:', 'exit 1', 'github-token:', 'run-id:', 'repository:'):
            self.assertNotIn(forbidden, directives)
        self.assertEqual(field(self.jobs['outcome'], 'needs', 4), 'executor')
        self.assertIn("if: needs.executor.outputs.state == 'blocked'", self.jobs['outcome'])
        self.assertIn('exit 1', self.jobs['outcome'])


class EntryTests(unittest.TestCase):
    def test_manual_workflow_is_explicitly_owned_by_its_contract_tests(self):
        import change_scope
        policy = change_scope.load_policy(ROOT / 'scripts/ci/scope_policy.json')
        result = change_scope.classify(policy, (change_scope.ChangedFile('M', (entry.AssessmentRuntime.workflow,)),),
            base_sha='a' * 40, head_sha='b' * 40, event_name='pull_request',
            draft=False, labels=(), trusted_head=True)
        self.assertEqual({name for name, selected in result['lanes'].items() if selected}, {'ci_contract'},
            'why: manual assessment workflow escapes its contract tests; remedy: preserve exact CI-contract ownership')

    def test_manual_entry_has_its_own_fixed_workflow_identity(self):
        self.assertEqual(entry.AssessmentRuntime.workflow, '.github/workflows/canary-assessment.yml',
            'why: assessment journal trusts the scheduler workflow; remedy: bind an independent fixed producer')

    def test_binary_ownership_type_and_mode_refusals(self):
        for mode, owner, directory in ((stat.S_IFREG | 0o755, 1000, False),
            (stat.S_IFREG | 0o775, 0, False), (stat.S_IFLNK | 0o755, 0, False),
            (stat.S_IFDIR | 0o777, 0, True), (stat.S_IFREG | 0o755, 0, True)):
            with self.subTest(mode=mode, owner=owner):
                with self.assertRaisesRegex(r.CanaryError, 'immutable root-owned.*remedy:'):
                    entry._root_owned(SimpleNamespace(st_mode=mode, st_uid=owner), directory=directory)
        entry._root_owned(SimpleNamespace(st_mode=stat.S_IFREG | 0o755, st_uid=0), directory=False)

    def test_copied_bytes_require_exact_sha_and_never_execute_partial_file(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(entry, '_root_owned'):
            source, target = Path(temp) / 'source', Path(temp) / 'copy'
            source.write_bytes(b'fixture bytes')
            source.chmod(0o755)
            with self.assertRaisesRegex(r.CanaryError, 'exact reviewed SHA-256'):
                entry.copy_verified_binary({'path': str(source), 'sha256': 'a' * 64}, target)
            self.assertFalse(target.stat().st_mode & 0o111)
            good = Path(temp) / 'good'
            entry.copy_verified_binary({'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}, good)
            self.assertEqual(good.read_bytes(), source.read_bytes())
            self.assertEqual(stat.S_IMODE(good.stat().st_mode), 0o500)

    def test_source_symlink_is_never_opened(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(entry, '_root_owned'):
            source = Path(temp) / 'symlink'
            source.symlink_to('/usr/bin/true')
            with self.assertRaises(OSError):
                entry.copy_verified_binary({'path': str(source), 'sha256': 'a' * 64}, Path(temp) / 'copy')


if __name__ == '__main__':
    unittest.main()
