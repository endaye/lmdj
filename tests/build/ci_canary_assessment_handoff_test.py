"""Actual Runtime/Journal composition; HTTP/job/ZIP fixtures are not live proof."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.canary import assessment as a, assessment_handoff as h, records as r
import ci_batch_runtime_test as fixture
import ci_canary_assessment_test as advice_fixtures
import ci_batch_controller_test as memory_fixture
import ci_self_test_report_test as report_fixture
import report_outbox
from incremental_batch_journal import Journal
import test_scope


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.git('config', 'commit.gpgsign', 'false')
        tracked = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files'], text=True).splitlines()
        for name in tracked:
            if h.metadata_proposal.source_path(name) or name in h.metadata_proposal.GENERATORS:
                path = self.f.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / name).read_bytes())
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'Complete canonical fixture inputs')
        self.base = self.f.git('rev-parse', 'HEAD')
        changed = self.f.root / 'apps/creator-web/src/example.ts'
        changed.parent.mkdir(parents=True, exist_ok=True)
        changed.write_text('export const value = 1;\n')
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'Fixture Host correction')
        self.target = self.f.git('rev-parse', 'HEAD')
        self.f.sha = self.f.api.sha = self.f.env['GITHUB_SHA'] = self.target
        self.f.api.runs[17]['head_sha'] = self.target
        self.f.config['epoch'] = 'canary-assessment-fixture'
        self.f.policy = test_scope.load_policy(self.f.root)
        self.f.make().initialize()
        self.claim = self.fresh().claim(base_sha=self.base, target_sha=self.target)
        self.context, self.owner = self.claim['context'], self.claim['executor']
        self.key = self.context['digest']

    def fresh(self, run=17):
        return h.Handoff(self.f.make(run))

    def result(self, blocked=False):
        if blocked:
            history = []
            for backend in a.BACKENDS:
                history = a.observe(self.context, history, {'backend': backend, 'model': 'fixture',
                    'elapsed_seconds': 0, 'input_digest': self.key, 'returncode': -1,
                    'error_class': 'missing_credential', 'output': ''})
        else:
            advice_fixture = advice_fixtures.AssessmentTests()
            advice_fixture.context, advice_fixture.target = self.context, self.target
            history = advice_fixture.observe()
        return a.finish(self.context, history)

    def completed(self, *, result=None):
        self.f.api.runs[17].update(status='completed', conclusion='success')
        self.f.api.jobs[17][0].update(status='completed', conclusion='success')
        self.producer = {'id': 1701, 'run_id': 17, 'run_attempt': 1,
            'name': h.PRODUCER_JOB, 'status': 'completed', 'conclusion': 'success',
            'steps': [{'name': name, 'status': 'completed', 'conclusion': 'success',
                       'completed_at': (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()}
                      for name in (h.EXECUTE_STEP, h.UPLOAD_STEP)]}
        self.f.api.jobs[17].append(self.producer)
        self.result_value = result if result is not None else self.result()
        self.document = h.artifact_document(self.context, self.owner, self.result_value)
        self.f.api.artifacts[17] = [{'id': 901, 'name': h.artifact_name(self.context, self.owner), 'expired': False}]
        self.upload()
        self.f.api.add_run(18)
        return self.fresh(18)

    def upload(self):
        self.f.api.downloads[901] = fixture.zipped({'assessment.json': self.document})

    def write_calls(self):
        return [call for call in self.f.api.calls if call[0] == 'PATCH' or call[0] == 'POST' and call[1] != '/graphql']

    def test_exact_producer_to_durable_terminal_then_prepare_actual_canonical_outputs(self):
        instance = self.completed()
        terminal = instance.settle(self.key)
        self.assertEqual(terminal['result'], self.result_value)
        self.assertEqual(terminal['executor'], self.owner)
        self.assertEqual(terminal['action'], 'terminal')
        self.f.api.artifacts[17][0]['expired'] = True
        self.f.api.calls.clear()
        replay = self.fresh(18).settle(self.key)
        self.assertEqual(replay['result'], self.result_value)
        self.assertFalse(any('/artifacts' in call[1] for call in self.f.api.calls))
        self.assertFalse(self.write_calls())
        current = json.loads((self.f.root / h.metadata_proposal.PRODUCT[0]).read_text())
        proposed = f"{current['milestone']}.{current['minor']}.{current['build'] + 1}.0"
        before = self.f.git('status', '--porcelain')
        candidate = self.fresh(18).prepare_metadata(self.key, proposed_build=proposed, allocation_date='2026-09-09')
        self.assertEqual(candidate['input_digest'], self.key)
        self.assertEqual(candidate['state'], 'metadata-proposed')
        self.assertFalse(candidate['admission_evidence'])
        self.assertTrue(set(h.metadata_proposal.PRODUCT) <= {edit['path'] for edit in candidate['edits']})
        self.assertEqual(before, self.f.git('status', '--porcelain'))
        self.assertFalse(self.write_calls())

    def test_active_producer_never_downloads_or_reexecutes(self):
        self.f.api.add_run(18)
        self.f.api.calls.clear()
        self.assertEqual(self.fresh(18).settle(self.key)['action'], 'pending')
        self.assertFalse(any('/artifacts' in call[1] for call in self.f.api.calls))
        self.assertFalse(self.write_calls())

    def test_claim_replay_never_returns_execute_again(self):
        self.assertEqual(self.claim['action'], 'execute')
        self.assertEqual(self.fresh().claim(base_sha=self.base, target_sha=self.target)['action'], 'pending')

    def test_blocked_advice_persists_but_cannot_prepare_metadata(self):
        instance = self.completed(result=self.result(blocked=True))
        self.assertEqual(instance.settle(self.key)['result']['state'], 'blocked')
        with self.assertRaisesRegex(r.CanaryError, 'advised terminal.*remedy:'):
            instance.prepare_metadata(self.key, proposed_build='1.0.999.0', allocation_date='2026-09-09')

    def test_pending_claim_cannot_prepare_metadata(self):
        with self.assertRaisesRegex(r.CanaryError, 'advised terminal'):
            self.fresh().prepare_metadata(self.key, proposed_build='1.0.999.0', allocation_date='2026-09-09')

    def test_cancelled_or_failed_upload_preserves_claim_for_reconciliation(self):
        instance = self.completed()
        self.producer.update(conclusion='cancelled')
        self.f.api.runs[17].update(conclusion='cancelled')
        self.f.api.calls.clear()
        result = instance.settle(self.key)
        self.assertEqual(result['action'], 'needs-reconciliation')
        self.assertIsNone(result['result'])
        self.assertFalse(self.write_calls())
        self.assertFalse(any('/artifacts' in call[1] for call in self.f.api.calls))

    def test_missing_artifact_after_successful_upload_is_pending_not_missing(self):
        instance = self.completed()
        self.f.api.artifacts[17] = []
        self.assertEqual(instance.settle(self.key)['action'], 'pending')
        self.assertIsNone(instance.settle(self.key)['result'])

    def test_expired_artifact_is_reconciliation_not_a_new_claim(self):
        instance = self.completed()
        self.f.api.artifacts[17][0]['expired'] = True
        self.assertEqual(instance.settle(self.key)['action'], 'needs-reconciliation')
        self.assertEqual(self.fresh(18)._storage().claim(self.context, self.owner)['action'], 'pending')

    def test_malformed_zip_does_not_persist_terminal_result(self):
        instance = self.completed()
        self.f.api.downloads[901] = b'not a zip'
        self.assertEqual(instance.settle(self.key)['action'], 'needs-reconciliation')
        self.assertIsNone(instance.settle(self.key)['result'])

    def test_artifact_identity_and_protocol_cannot_be_forged_with_a_new_seal(self):
        instance = self.completed()
        original = deepcopy(self.document)
        for change in ('executor', 'input', 'result', 'extra'):
            with self.subTest(change=change):
                self.document = deepcopy(original)
                if change == 'executor':
                    self.document['executor']['run_id'] = 18
                elif change == 'input':
                    self.document['input_digest'] = 'a' * 64
                elif change == 'result':
                    self.document['result']['state'] = 'blocked'
                    self.document['result'] = r.seal(self.document['result'])
                else:
                    self.document['extra'] = 'unreviewed'
                self.document = r.seal(self.document)
                self.upload()
                self.assertEqual(instance.settle(self.key)['action'], 'needs-reconciliation')

    def test_wrong_run_control_and_job_attempt_fail_without_writes(self):
        instance = self.completed()
        self.f.api.runs[17]['head_sha'] = self.base
        # The real Journal rejects this forged original writer before the
        # consumer can inspect its artifact. A looser fake would miss this.
        with self.assertRaisesRegex(r.CanaryError, 'journal cannot be authenticated'):
            instance.settle(self.key)
        self.f.api.runs[17]['head_sha'] = self.target
        self.producer['run_attempt'] = True
        with self.assertRaisesRegex(r.CanaryError, 'job inventory differs'):
            instance.settle(self.key)

    def test_consumer_rechecks_producer_control_after_journal_read(self):
        instance = self.completed()
        original = instance.runtime.get_run
        def changed(run_id, attempt):
            run = original(run_id, attempt)
            if run_id == 17:
                run['head_sha'] = self.base
            return run
        with patch.object(instance.runtime, 'get_run', side_effect=changed):
            with self.assertRaisesRegex(r.CanaryError, 'producer control differs'):
                instance.settle(self.key)

    def test_fresh_observer_recovers_claim_response_loss_without_execution(self):
        # A new context is still explicit; resetting the existing key is never
        # used to manufacture another execute action.
        self.f.api.lose = 'claim'
        with self.assertRaisesRegex(r.CanaryError, 'append outcome is unresolved'):
            self.fresh().claim(base_sha=self.base, target_sha=self.base)
        self.assertEqual(self.fresh().claim(base_sha=self.base, target_sha=self.base)['action'], 'pending')

    def test_successful_job_with_failed_upload_step_is_not_a_producer(self):
        instance = self.completed()
        self.producer['steps'][1]['conclusion'] = 'failure'
        self.assertEqual(instance.settle(self.key)['action'], 'needs-reconciliation')

    def test_missing_producer_cannot_consume_an_artifact_with_the_right_name(self):
        instance = self.completed()
        self.f.api.jobs[17].remove(self.producer)
        self.assertEqual(instance.settle(self.key)['action'], 'needs-reconciliation')

    def test_artifact_visibility_recovers_without_a_second_claim(self):
        instance = self.completed()
        artifact = self.f.api.artifacts[17].pop()
        self.assertEqual(instance.settle(self.key)['action'], 'pending')
        self.f.api.artifacts[17].append(artifact)
        self.assertEqual(self.fresh(18).settle(self.key)['result'], self.result_value)

    def test_ambiguous_producer_or_artifact_is_not_absence(self):
        instance = self.completed()
        self.f.api.jobs[17].append({**deepcopy(self.producer), 'id': 1702})
        with self.assertRaisesRegex(r.CanaryError, 'producer job is ambiguous'):
            instance.settle(self.key)
        self.f.api.jobs[17].pop()
        self.f.api.artifacts[17].append({**self.f.api.artifacts[17][0], 'id': 902})
        with self.assertRaisesRegex(fixture.batch.BatchError, 'ambiguous exact-attempt artifact'):
            instance.settle(self.key)

    def test_api_failure_is_not_missing_evidence(self):
        instance = self.completed()
        self.f.api.fail = ('GET', '/repos/endaye/lmdj/actions/runs/17/artifacts?per_page=100&page=1')
        with self.assertRaisesRegex(fixture.batch.BatchError, 'runtime API unavailable'):
            instance.settle(self.key)

    def test_lost_complete_ack_reuses_durable_result_without_download_or_model(self):
        instance = self.completed()
        self.f.api.lose = 'complete'
        with self.assertRaisesRegex(r.CanaryError, 'append outcome is unresolved'):
            instance.settle(self.key)
        self.f.api.artifacts[17] = []
        self.assertEqual(self.fresh(18).settle(self.key)['result'], self.result_value)

    def test_actual_runtime_authentication_precedes_assessment_read(self):
        self.f.env['BATCH_WRITER_LOCK'] = 'not-held'
        self.f.api.calls.clear()
        with self.assertRaisesRegex(fixture.batch.BatchError, 'short writer lock'):
            self.fresh().settle(self.key)
        self.assertFalse(self.f.api.calls)

    def test_production_storage_and_nonassessment_epoch_are_rejected(self):
        for number, epoch in ((807, 'canary-assessment-fixture'), (817, 'canary-assessment-fixture'), (782, 'report-epoch')):
            with self.subTest(number=number, epoch=epoch):
                config = {**self.f.config, 'issue_number': number, 'epoch': epoch}
                runtime = fixture.runtime.Runtime(config, root=self.f.root, environment=self.f.env, api=self.f.api)
                with self.assertRaisesRegex(r.CanaryError, 'storage aliases' if number in (807, 817) else 'storage epoch'):
                    h.Handoff(runtime)

    def outbox(self, memory):
        journal = Journal(783, memory, memory, lambda *args: True, lambda: memory.lock)
        return report_outbox.Outbox(journal, lambda: memory.lock, 'report-fixture')

    def test_missing_execution_enters_durable_issue_without_resetting_claim(self):
        instance = self.completed()
        self.producer['conclusion'] = 'cancelled'
        memory, api = memory_fixture.Memory(), report_fixture.FakeGitHubApi()
        first = instance.report(self.key, self.outbox(memory), api)
        again = self.fresh(18).report(self.key, self.outbox(memory), api)
        self.assertEqual(first, again)
        self.assertEqual(first['status'], 'delivered')
        self.assertEqual(len(api.issues), 1)
        self.assertIn(self.key, api.issues[0]['body'])
        self.assertIsNone(self.fresh(18).settle(self.key)['result'])
        self.assertEqual([event['type'] for event in self.outbox(memory).journal.load()], ['queue', 'claim', 'ack', 'delivered'])

    def test_blocked_terminal_report_reuses_existing_assessment_outbox_path(self):
        instance = self.completed(result=self.result(blocked=True))
        memory, api = memory_fixture.Memory(), report_fixture.FakeGitHubApi()
        receipt = instance.report(self.key, self.outbox(memory), api)
        self.assertEqual(receipt['status'], 'delivered')
        self.assertIn(self.result_value['digest'], api.issues[0]['body'])
        self.assertEqual(instance.report(self.key, self.outbox(memory), api), receipt)

    def test_uncertain_issue_write_reopens_receipt_without_another_business_post(self):
        instance = self.completed()
        self.producer['conclusion'] = 'cancelled'
        memory, api = memory_fixture.Memory(), report_fixture.FakeGitHubApi()
        class Crash(BaseException):
            pass
        original = api.create_issue
        def lost(**kwargs):
            original(**kwargs)
            raise Crash()
        api.create_issue = lost
        with self.assertRaises(Crash):
            instance.report(self.key, self.outbox(memory), api)
        api.create_issue = original
        self.assertEqual(self.fresh(18).report(self.key, self.outbox(memory), api)['status'], 'delivered')
        self.assertEqual(len([call for call in api.calls if call[0] == 'create_issue']), 1)

    def test_missing_upload_beyond_retention_requires_reconciliation(self):
        instance = self.completed()
        self.f.api.artifacts[17] = []
        self.producer['steps'][1]['completed_at'] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        result = instance.settle(self.key)
        self.assertEqual(result['action'], 'needs-reconciliation')
        self.assertIn('never repeat', result['remedy'])

    def test_pending_and_advised_results_do_not_file_failure_issues(self):
        memory, api = memory_fixture.Memory(), report_fixture.FakeGitHubApi()
        self.f.api.add_run(18)
        self.assertEqual(self.fresh(18).report(self.key, self.outbox(memory), api), {'status': 'pending'})
        instance = self.completed()
        self.assertEqual(instance.report(self.key, self.outbox(memory), api), {'status': 'not-applicable'})
        self.assertFalse(memory.comments)
        self.assertFalse(api.calls)

    def test_report_alias_refused_before_any_source_mutation(self):
        memory = memory_fixture.Memory()
        outbox = report_outbox.Outbox(memory.journal(), lambda: memory.lock, 'report-fixture')
        self.f.api.calls.clear()
        with self.assertRaisesRegex(r.CanaryError, 'outbox aliases assessment'):
            self.fresh().report(self.key, outbox, report_fixture.FakeGitHubApi())
        self.assertFalse(self.f.api.calls)
        self.assertFalse(memory.comments)


if __name__ == '__main__':
    unittest.main()
