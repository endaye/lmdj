#!/usr/bin/env python3
import json
import io
from contextlib import redirect_stdout, redirect_stderr
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from cloudflare_host import candidate, upload_receipt, child_environment, command_store, main, stage, write_diagnostic, CommandError
from cloudflare_run_store import RunStore, StoreError
from cloudflare_api import CloudflareError

A = '11111111-1111-1111-1111-111111111111'
B = '22222222-2222-2222-2222-222222222222'
D = '33333333-3333-3333-3333-333333333333'


class Client:
    worker = 'creator-recovery'
    def __init__(self):
        self.current = {'id': D, 'version_id': A}
        self.routing = {'enabled': False, 'previews_enabled': True}
        self.lookups = []
        self.publishes = []
        self.unknown = False
    def deployment(self): return dict(self.current)
    def route(self): return dict(self.routing)
    def require_version(self, value): self.lookups.append(value); return value
    def publish(self, *, version, expected_deployment):
        assert self.current['id'] == expected_deployment
        self.publishes.append(version)
        self.current = {'id': ('44444444-4444-4444-4444-444444444444' if version == B else D), 'version_id': version}
        if self.unknown: raise CloudflareError('unknown receipt', outcome_unknown=True)
        return dict(self.current)
    def set_route(self, *, enabled, expected_deployment):
        assert self.current['id'] == expected_deployment
        self.routing = {'enabled': enabled, 'previews_enabled': True}
        return dict(self.routing)


class HostCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.client = Client()

    def receipt(self, **overrides):
        row = {'type': 'version-upload', 'version': 1, 'worker_name': self.client.worker,
               'version_id': B, 'preview_url': f'https://{B[:8]}-{self.client.worker}.lmdj.workers.dev'}
        row.update(overrides)
        p = self.root/'output.jsonl'; p.write_text(json.dumps(row)+'\n')
        return p

    def test_machine_receipt_binds_worker_version_and_url(self):
        self.assertEqual(upload_receipt(self.receipt(), self.client.worker), B)

    def test_wrong_worker_receipt_is_rejected(self):
        with self.assertRaises(CommandError):
            upload_receipt(self.receipt(worker_name='creator'), self.client.worker)

    def test_wrong_preview_receipt_is_rejected(self):
        with self.assertRaises(CommandError):
            upload_receipt(self.receipt(preview_url='https://creator.lmdj.workers.dev'), self.client.worker)

    def test_duplicate_positive_receipts_are_unknown(self):
        p = self.receipt(); p.write_text(p.read_text()*2)
        with self.assertRaises(CommandError): upload_receipt(p, self.client.worker)

    def test_failed_command_record_invalidates_a_positive_upload_receipt(self):
        p = self.receipt()
        with p.open('a') as stream:
            stream.write(json.dumps({'type':'command-failed','version':1,'message':'fetch failed'})+'\n')
        with self.assertRaises(CommandError): upload_receipt(p, self.client.worker)

    def test_candidate_success_verifies_exact_version_and_keeps_production(self):
        prior = self.client.deployment(); checks = []
        with RunStore(self.root/'state', self.client.worker) as store:
            store.start('candidate')
            def uploaded():
                self.assertEqual(store.records()[-1]['data']['event'], 'candidate-upload-starting')
                return B
            def verified(value, url): checks.append((value,url)); return True
            result = candidate(self.client, store, uploader=uploaded, verifier=verified)
            self.assertEqual(result['version_id'], B)
            self.assertEqual(checks, [(B, f'https://{B[:8]}-{self.client.worker}.lmdj.workers.dev')])
            self.assertEqual(self.client.deployment(), prior)
            self.assertEqual(store.records()[-1]['data']['event'], 'run-finished')

    def test_empty_target_initialization_verifies_preview_with_stable_disabled(self):
        self.client.exists = lambda: False
        with RunStore(self.root/'state', self.client.worker) as store:
            store.start('candidate')
            def initialized(): self.client.current['version_id'] = B; return B
            result = candidate(self.client, store, uploader=initialized, verifier=lambda *_: True, initialize=True)
            self.assertEqual(result['version_id'], B)
            self.assertFalse(self.client.routing['enabled'])
            self.assertIn('initialized', [r['data']['event'] for r in store.records()])

    def test_initialization_refuses_an_existing_worker_before_upload(self):
        self.client.exists = lambda: True
        with RunStore(self.root/'state', self.client.worker) as store:
            store.start('candidate')
            with self.assertRaises(CommandError):
                candidate(self.client, store, uploader=lambda: self.fail('must not overwrite existing Worker'),
                          verifier=lambda *_: True, initialize=True)

    def test_initialization_requires_disabled_stable_route(self):
        self.client.exists = lambda: False
        with RunStore(self.root/'state', self.client.worker) as store:
            store.start('candidate')
            def exposed(): self.client.current['version_id'] = B; self.client.routing['enabled'] = True; return B
            with self.assertRaises(CommandError):
                candidate(self.client, store, uploader=exposed, verifier=lambda *_: True, initialize=True)
            self.assertNotEqual(store.records()[-1]['data']['event'], 'run-finished')

    def test_unknown_upload_leaves_pending_run_and_never_retries(self):
        calls = []
        with RunStore(self.root/'state', self.client.worker) as store:
            store.start('candidate')
            def failed(): calls.append(1); raise CommandError('timeout')
            with self.assertRaises(CommandError):
                candidate(self.client, store, uploader=failed, verifier=lambda *_: True)
        with RunStore(self.root/'state', self.client.worker) as store:
            with self.assertRaises(StoreError): store.start('candidate')
        self.assertEqual(calls, [1])

    def test_upload_concurrent_route_change_stops_before_http(self):
        with RunStore(self.root/'state', self.client.worker) as store:
            store.start('candidate')
            def changed(): self.client.routing['enabled'] = True; return B
            def forbidden(*_): self.fail('verification must not conceal changed production')
            with self.assertRaises(CommandError):
                candidate(self.client, store, uploader=changed, verifier=forbidden)
            self.assertNotEqual(store.records()[-1]['data']['event'], 'run-finished')

    def test_verification_must_return_exact_true(self):
        with RunStore(self.root/'state', self.client.worker) as store:
            store.start('candidate')
            with self.assertRaises(CommandError):
                candidate(self.client, store, uploader=lambda: B, verifier=lambda *_: 1)

    def test_staging_failure_before_mutation_does_not_lock_out_retry(self):
        with self.assertRaises(CommandError):
            with command_store(self.root/'state', self.client.worker, 'candidate'):
                raise CommandError('signature rejected')
        with RunStore(self.root/'state', self.client.worker) as store:
            self.assertEqual(store.records()[-1]['data']['outcome'], 'failed-before-publication')
            store.start('candidate')

    def main_journey(self, *, prior_tag='tag-A', fail_cutover=False):
        self.client.routing['enabled'] = True
        checks = []
        failed = False
        def staged(tag, host, workspace):
            out = workspace/host; (out/'dist').mkdir(parents=True)
            (out/'dist/tag').write_text(tag)
            return out, {'tag':tag, 'host_id':host, 'source':'a'*40, 'archive':{'sha256':'b'*64,'bytes':4}}
        def http(dist, url, **kwargs):
            nonlocal failed
            tag = (dist/'tag').read_text()
            actual = self.client.current['version_id'] if url == 'https://creator-recovery.lmdj.workers.dev' else (A if url.startswith('https://'+A[:8]) else B)
            checks.append((actual, tag, url))
            if tag != {A:'tag-A', B:'tag-B'}[actual]: raise RuntimeError('signed bytes mismatch')
            if fail_cutover and actual == B and url == 'https://creator-recovery.lmdj.workers.dev' and not failed:
                failed = True; raise RuntimeError('post-cutover smoke failed')
            return {}
        with patch('cloudflare_host.CloudflareClient', return_value=self.client), patch('cloudflare_host.stage', side_effect=staged), patch('cloudflare_host.smoke', side_effect=http), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = main(['promote','tag-B','--target','creator-recovery','--state-root',str(self.root/'state'),
                         '--version',B,'--prior-tag',prior_tag])
        return code, checks

    def test_full_command_promotes_the_verified_candidate_version(self):
        code, checks = self.main_journey()
        self.assertEqual(code, 0)
        self.assertEqual(self.client.current['version_id'], B)
        self.assertEqual(self.client.publishes, [B])
        self.assertEqual([x[0] for x in checks], [A,A,B,B])

    def test_full_command_failed_cutover_rechecks_exact_prior_after_recovery(self):
        code, checks = self.main_journey(fail_cutover=True)
        self.assertEqual(code, 2)
        self.assertEqual(self.client.current['version_id'], A)
        self.assertEqual(self.client.publishes, [B,A])
        self.assertEqual([x[0] for x in checks], [A,A,B,B,A,A])
        with RunStore(self.root/'state', self.client.worker) as store:
            self.assertEqual(store.records()[-1]['data']['outcome'], 'recovered')

    def test_wrong_signed_prior_stops_before_any_publication(self):
        code, _ = self.main_journey(prior_tag='wrong-prior')
        self.assertEqual(code, 2)
        self.assertEqual(self.client.publishes, [])
        self.assertEqual(self.client.current['version_id'], A)

    def test_unknown_publication_receipt_never_automatically_recovers(self):
        self.client.unknown = True
        code, _ = self.main_journey()
        self.assertEqual(code, 2)
        self.assertEqual(self.client.publishes, [B])
        with RunStore(self.root/'state', self.client.worker) as store:
            with self.assertRaises(StoreError): store.start('recover')

    def reconciliation_journey(self, *, change_during_http=False, wrong_sequence=False, wrong_run=False):
        state = self.root/'state'
        with RunStore(state, self.client.worker) as store:
            run = store.start('promote')
            store.observe({'event':'publication-starting'})
            sequence = store.records()[-1]['sequence']
        self.client.routing['enabled'] = True
        checks = []
        def staged(tag, host, workspace):
            out = workspace/host; (out/'dist').mkdir(parents=True)
            return out, {'tag':tag, 'host_id':host}
        def http(dist, url, **kwargs):
            checks.append(url)
            if change_during_http: self.client.current['id'] = B
            return {}
        with patch('cloudflare_host.CloudflareClient', return_value=self.client), patch('cloudflare_host.stage', side_effect=staged), patch('cloudflare_host.smoke', side_effect=http), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = main(['reconcile','lmdj-v1.0.42.0','--target','creator-recovery','--state-root',str(state),
                         '--version',A,'--expected-deployment',D,'--expected-run',A if wrong_run else run,
                         '--expected-sequence',str(sequence + int(wrong_sequence)), '--route','enabled'])
        return code, checks, sequence

    def test_reconcile_verifies_both_urls_and_completes_only_local_journal(self):
        code, checks, sequence = self.reconciliation_journey()
        self.assertEqual(code, 0)
        self.assertEqual(checks, [f'https://{A[:8]}-creator-recovery.lmdj.workers.dev',
                                  'https://creator-recovery.lmdj.workers.dev'])
        self.assertEqual(self.client.publishes, [])
        with RunStore(self.root/'state', self.client.worker) as store:
            self.assertEqual(store.records()[-2]['data']['reconciled_sequence'], sequence)
            self.assertEqual(store.records()[-1]['data']['outcome'], 'reconciled')
            store.start('candidate')

    def test_reconciliation_detects_remote_change_after_http(self):
        code, _, sequence = self.reconciliation_journey(change_during_http=True)
        self.assertEqual(code, 2)
        with RunStore(self.root/'state', self.client.worker) as store:
            self.assertEqual(store.records()[-1]['sequence'], sequence)
            with self.assertRaises(StoreError): store.start('candidate')

    def test_reconciliation_refuses_wrong_pending_position(self):
        code, _, sequence = self.reconciliation_journey(wrong_sequence=True)
        self.assertEqual(code, 2)
        with RunStore(self.root/'state', self.client.worker) as store:
            self.assertEqual(store.records()[-1]['sequence'], sequence)

    def test_absent_reconciliation_never_creates_a_worker(self):
        state = self.root/'state'
        with RunStore(state, self.client.worker) as store:
            run = store.start('candidate'); store.observe({'event':'candidate-upload-starting'})
            sequence = store.records()[-1]['sequence']
        self.client.exists = lambda: False
        with patch('cloudflare_host.CloudflareClient', return_value=self.client), patch('cloudflare_host.stage') as stage, redirect_stdout(io.StringIO()):
            code = main(['reconcile','--absent','--target','creator-recovery','--state-root',str(state),
                         '--expected-run',run,'--expected-sequence',str(sequence)])
        self.assertEqual(code, 0); stage.assert_not_called()
        self.assertEqual(self.client.publishes, [])
        with RunStore(state, self.client.worker) as store:
            self.assertTrue(store.records()[-2]['data']['absent'])
            store.start('candidate')

    def test_reconciliation_refuses_another_pending_run(self):
        code, _, sequence = self.reconciliation_journey(wrong_run=True)
        self.assertEqual(code, 2)
        with RunStore(self.root/'state', self.client.worker) as store:
            self.assertEqual(store.records()[-1]['sequence'], sequence)

    def test_failed_stage_retains_diagnostics_with_both_credentials_redacted(self):
        result = subprocess.CompletedProcess([], 1, 'github-fixture', 'cf-fixture validation failed')
        with patch.dict(os.environ, {'GITHUB_TOKEN':'github-fixture','CLOUDFLARE_API_TOKEN':'cf-fixture'}), patch('cloudflare_host.subprocess.run', return_value=result) as run:
            with self.assertRaises(CommandError): stage('lmdj-v1.0.42.0','creator-web',self.root)
        self.assertNotIn('CLOUDFLARE_API_TOKEN',run.call_args.kwargs['env'])
        log = (self.root/'stage-verification.log').read_text()
        self.assertIn('validation failed',log)
        self.assertNotIn('github-fixture',log)
        self.assertNotIn('cf-fixture',log)

    def test_timeout_byte_diagnostics_are_retained_without_credentials(self):
        with patch.dict(os.environ, {'CLOUDFLARE_API_TOKEN':'cf-fixture'}):
            write_diagnostic(self.root/'wrangler.log', b'cf-fixture network failed', None)
        self.assertEqual((self.root/'wrangler.log').read_text(), '[REDACTED] network failed')

    def test_provider_credentials_do_not_cross_child_boundaries(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN':'github-fixture', 'CLOUDFLARE_API_TOKEN':'cf-fixture',
                                    'GH_TOKEN':'other-gh', 'NETLIFY_AUTH_TOKEN':'netlify-fixture'}, clear=True):
            github = child_environment(github=True); cloud = child_environment(cloudflare=True)
        self.assertEqual(github['GITHUB_TOKEN'], 'github-fixture')
        self.assertNotIn('CLOUDFLARE_API_TOKEN', github)
        self.assertEqual(cloud['CLOUDFLARE_API_TOKEN'], 'cf-fixture')
        self.assertNotIn('GITHUB_TOKEN', cloud)
        self.assertNotIn('GH_TOKEN', cloud)
        self.assertNotIn('NETLIFY_AUTH_TOKEN', cloud)


if __name__ == '__main__': unittest.main()
