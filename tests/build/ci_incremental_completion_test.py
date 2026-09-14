#!/usr/bin/env python3
"""Actual Runtime/Git/ZIP composition; HTTP fixtures are not platform acceptance."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import incremental_completion as relay
import batch_runtime
import incremental_batch


def zipped(document):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('receipt.json', json.dumps(document))
    return stream.getvalue()


class CompletionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        for path in (relay.WORKFLOW, relay.SCRIPT):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT/path).read_bytes())
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')
        self.sha = self.git('rev-parse', 'HEAD').strip()
        self.main = self.sha
        self.git('remote', 'add', 'origin', str(self.root))
        self.repository = {'id': 1286600062, 'full_name': 'endaye/lmdj'}
        self.runs = {17: self.run_document(17, batch_runtime.WORKFLOW, 352307416),
                     18: self.run_document(18, relay.WORKFLOW, 99)}
        self.runs[18].update(status='in_progress', conclusion=None)
        self.jobs = [{'id': 55, 'run_id': 18, 'run_attempt': 1, 'head_sha': self.sha,
                      'name': relay.JOB, 'status': 'in_progress', 'conclusion': None,
                      'steps': [{'name': relay.SAVE, 'status': 'in_progress', 'conclusion': None}]}]
        self.artifacts = []
        self.raw = b''
        self.calls = []
        self.config = {'repository':'endaye/lmdj', 'issue_number':807, 'issue_node_id':'node',
                       'bot_node_id':'bot', 'workflow_id':352307416, 'epoch':'fixture'}
        self.env = {'GITHUB_REPOSITORY':'endaye/lmdj', 'GITHUB_REF':'refs/heads/main',
                    'GITHUB_RUN_ID':'18', 'GITHUB_RUN_ATTEMPT':'1', 'GITHUB_SHA':self.sha,
                    'GITHUB_TOKEN':'fixture-token', 'GITHUB_EVENT_NAME':'workflow_run',
                    'GITHUB_WORKFLOW_REF':f'endaye/lmdj/{relay.WORKFLOW}@refs/heads/main'}

    def git(self, *args):
        return subprocess.check_output(['git','-C',str(self.root),*args], stderr=subprocess.DEVNULL).decode()

    def run_document(self, number, path, workflow):
        return {'id':number, 'run_attempt':1, 'workflow_id':workflow, 'path':path,
                'head_sha':self.sha, 'head_branch':'main', 'event':'workflow_run',
                'status':'completed', 'conclusion':'failure',
                'repository':deepcopy(self.repository), 'head_repository':deepcopy(self.repository)}

    def _request(self, method, path, *, body=None, raw=False):
        self.calls.append((method,path,body))
        assert method == 'GET' and body is None, 'relay attempted a mutation'
        suffix = path.removeprefix('/repos/endaye/lmdj')
        if suffix == '': return deepcopy(self.repository)
        if suffix == '/git/ref/heads/main': return {'object':{'type':'commit','sha':self.main}}
        if suffix == '/actions/workflows/incremental-completion.yml': return {'id':99,'path':relay.WORKFLOW}
        for number, run in self.runs.items():
            if suffix == f'/actions/runs/{number}/attempts/1': return deepcopy(run)
        if suffix == '/actions/runs/18/attempts/1/jobs?per_page=100&page=1':
            return {'total_count':len(self.jobs),'jobs':deepcopy(self.jobs)}
        if suffix == '/actions/runs/18/artifacts?per_page=100&page=1':
            return {'total_count':len(self.artifacts),'artifacts':deepcopy(self.artifacts)}
        if suffix == '/actions/artifacts/44/zip' and raw: return self.raw
        raise AssertionError('unexpected API '+path)

    def runtime(self):
        instance = batch_runtime.Runtime(self.config, root=self.root, environment=self.env, api=self)
        instance.inputs.main = self.sha
        return instance

    def payload(self):
        return {'repository':deepcopy(self.repository), 'action':'completed', 'workflow_run':deepcopy(self.runs[17])}

    def completed(self):
        document = relay.produce(self.runtime(), self.payload())
        self.runs[18].update(status='completed', conclusion='success')
        self.jobs[0].update(status='completed', conclusion='success')
        self.jobs[0]['steps'] = [{'name':name,'status':'completed','conclusion':'success'} for name in (relay.SAVE,relay.UPLOAD)]
        self.artifacts = [{'id':44,'name':'incremental-completion-18-1','expired':False,
                           'workflow_run':{'id':18,'repository_id':1286600062,'head_repository_id':1286600062,
                                           'head_sha':self.sha,'head_branch':'main'}}]
        self.raw = zipped(document)
        return document

    def rejected(self, action):
        with self.assertRaisesRegex((incremental_batch.BatchError, batch_runtime.InvalidEvidence), 'why:.*remedy:'):
            action()

    def test_actual_producer_to_zip_reader_preserves_exact_parent_and_immediate_witness(self):
        document = self.completed()
        parent, witness = relay.resolve(self.runtime(), deepcopy(self.runs[18]))
        self.assertEqual(parent, self.runs[17])
        self.assertEqual(witness, {'run_id':18,'attempt':1,'control':self.sha})
        self.assertEqual(document['parent'], relay.identity(parent))
        self.assertTrue(all(method=='GET' for method,_,_ in self.calls))

    def test_parent_failure_is_valid_completion_not_a_green_verdict(self):
        self.completed()
        parent,_ = relay.resolve(self.runtime(), self.runs[18])
        self.assertEqual(parent['conclusion'],'failure')
        self.assertNotIn('execute', parent)

    def test_producer_rejects_event_parent_attempt_alias(self):
        payload=self.payload(); payload['workflow_run']['run_attempt']=True
        self.rejected(lambda:relay.produce(self.runtime(),payload))

    def test_producer_rejects_wrong_context(self):
        self.env['GITHUB_WORKFLOW_REF']='endaye/lmdj/.github/workflows/foreign.yml@refs/heads/main'
        self.rejected(lambda:relay.produce(self.runtime(),self.payload()))

    def test_parent_must_be_terminal(self):
        self.runs[17]['status']='in_progress'
        self.rejected(lambda:relay.produce(self.runtime(),self.payload()))

    def test_wrong_parent_workflow_is_rejected(self):
        self.runs[17]['workflow_id']=99
        self.rejected(lambda:relay.produce(self.runtime(),self.payload()))

    def test_queued_relay_remains_valid_when_main_advances(self):
        self.git('commit', '--allow-empty', '-m', 'later main')
        self.main = self.git('rev-parse', 'HEAD').strip()
        self.git('checkout', '--detach', self.sha)
        document = relay.produce(self.runtime(), self.payload())
        self.assertEqual(document['relay']['control'], self.sha)
        self.assertNotEqual(self.main, self.sha)
        self.assertEqual(document['parent']['id'],17)
        self.assertTrue(all(method=='GET' for method,_,_ in self.calls))

    def test_unknown_parent_conclusion_is_not_terminal_evidence(self):
        self.runs[17]['conclusion']='invented'
        self.rejected(lambda:relay.produce(self.runtime(),self.payload()))

    def test_extra_relay_job_is_rejected(self):
        self.completed();self.jobs.append({**self.jobs[0],'id':56})
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_receipt_parent_wrong_head_is_rejected(self):
        document=self.completed();document['parent']['head_sha']='a'*40;self.raw=zipped(document)
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_parent_numeric_repository_mismatch_is_rejected(self):
        self.runs[17]['repository']['id']=2
        self.rejected(lambda:relay.produce(self.runtime(),self.payload()))

    def test_event_hint_changed_head_is_rejected(self):
        payload=self.payload();payload['workflow_run']['head_sha']='a'*40
        self.rejected(lambda:relay.produce(self.runtime(),payload))

    def test_missing_receipt_is_not_no_work(self):
        self.completed();self.artifacts=[]
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_expired_receipt_is_rejected(self):
        self.completed();self.artifacts[0]['expired']=True
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_duplicate_artifacts_are_rejected(self):
        self.completed();self.artifacts.append({**self.artifacts[0],'id':45})
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_wrong_artifact_binding_is_rejected(self):
        self.completed();self.artifacts[0]['workflow_run']['id']=17
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_upload_skipped_is_rejected(self):
        self.completed();self.jobs[0]['steps'][1]['conclusion']='skipped'
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_unknown_receipt_field_is_rejected(self):
        document=self.completed();document['execute']=True;self.raw=zipped(document)
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_receipt_relay_binding_is_not_model_claim(self):
        document=self.completed();document['relay']['run_id']=19;self.raw=zipped(document)
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_nested_receipt_type_alias_is_rejected(self):
        document=self.completed();document['relay']['attempt']=True;self.raw=zipped(document)
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_relay_rerun_hint_is_rejected(self):
        self.completed();hint=deepcopy(self.runs[18]);hint['run_attempt']=2
        self.rejected(lambda:relay.resolve(self.runtime(),hint))

    def test_unexpected_zip_member_is_rejected(self):
        self.completed();self.raw=b'invalid zip'
        self.rejected(lambda:relay.resolve(self.runtime(),self.runs[18]))

    def test_source_module_drift_is_rejected(self):
        self.completed();old=self.sha
        (self.root/relay.SCRIPT).write_text('# changed source\n')
        self.git('add','.');self.git('commit','-m','source drift')
        self.sha=self.git('rev-parse','HEAD').strip();self.env['GITHUB_SHA']=self.sha
        instance=self.runtime()
        self.assertNotEqual(old,self.sha)
        self.rejected(lambda:relay.resolve(instance,self.runs[18]))

    def test_workflow_has_no_output_bridge_or_write_permissions(self):
        text=(ROOT/relay.WORKFLOW).read_text()
        self.assertNotIn('GITHUB_OUTPUT',text)
        self.assertNotIn('issues: write',text)
        self.assertNotIn('workflow_dispatch:',text)
        self.assertIn('workflows: ["Self-test Report"]',text)
        self.assertIn('timeout-minutes: 25', text)

    def test_cli_primary_quota_prints_closed_http_diagnostic(self):
        from self_test_report import GitHubApiError
        log = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'receipt.json'
            event = Path(directory) / 'event.json'
            event.write_text('{}')
            error = GitHubApiError(403, 'quota', remaining=0, reset=1788877325)
            with mock.patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event)}, clear=False), \
                    mock.patch('incremental_entry.load_storage', return_value={'scheduler': {}}), \
                    mock.patch.object(relay.batch_runtime, 'Runtime', side_effect=error), \
                    redirect_stdout(log):
                self.assertEqual(relay.main(['--output', str(output)]), 1)
        rows = [json.loads(line) for line in log.getvalue().splitlines() if line.startswith('{')]
        self.assertEqual(rows, [{'schema': 'lmdj.ci-entry-diagnostic.v1', 'operation': 'relay',
                                 'stage': 'authenticate', 'error_kind': 'github-api-error',
                                 'http': {'status': 403, 'remaining': 0, 'reset': 1788877325}}])
        self.assertIn('why: completion relay could not authenticate its source; remedy:', log.getvalue())
        self.assertNotIn('quota', log.getvalue().split('why:', 1)[0])

    def test_cli_post_auth_failure_does_not_label_authenticate(self):
        log = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'receipt.json'
            event = Path(directory) / 'event.json'
            event.write_text('{}')
            runtime = mock.Mock()
            runtime.diagnostic_stage = None
            with mock.patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event)}, clear=False), \
                    mock.patch('incremental_entry.load_storage', return_value={'scheduler': {}}), \
                    mock.patch.object(relay.batch_runtime, 'Runtime', return_value=runtime), \
                    mock.patch.object(relay, 'produce', side_effect=OSError('SECRET')), \
                    redirect_stdout(log):
                self.assertEqual(relay.main(['--output', str(output)]), 1)
        rows = [json.loads(line) for line in log.getvalue().splitlines() if line.startswith('{')]
        self.assertEqual(rows[0]['stage'], 'unknown')
        self.assertEqual(rows[0]['error_kind'], 'os-error')
        self.assertNotIn('SECRET', log.getvalue())


if __name__=='__main__': unittest.main()
