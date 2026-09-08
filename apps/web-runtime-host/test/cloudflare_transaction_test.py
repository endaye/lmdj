#!/usr/bin/env python3
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from cloudflare_api import CloudflareError
from cloudflare_transaction import promote, TransactionError
A='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
B='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
D='dddddddd-dddd-dddd-dddd-dddddddddddd'
E='eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
F='ffffffff-ffff-ffff-ffff-ffffffffffff'
STABLE='https://creator-recovery.lmdj.workers.dev'

class FakeClient:
    worker='creator-recovery'
    def __init__(self, enabled=True):
        self.active={'id':D,'version_id':A};self.routes={'enabled':enabled,'previews_enabled':True}
        self.writes=[];self.unknown=False;self.reject_recovery=False
    def deployment(self):return dict(self.active)
    def route(self):return dict(self.routes)
    def require_version(self,v):return v
    def publish(self, *, version, expected_deployment):
        assert self.active['id']==expected_deployment
        self.writes.append(('publish',version))
        if self.reject_recovery and version==A: raise CloudflareError('rejected',outcome_unknown=True)
        self.active={'id':E if version==B else F,'version_id':version}
        if self.unknown: raise CloudflareError('lost receipt',outcome_unknown=True)
        return dict(self.active)
    def set_route(self, *, enabled, expected_deployment):
        assert self.active['id']==expected_deployment
        self.writes.append(('route',enabled));self.routes={'enabled':enabled,'previews_enabled':True}
        return dict(self.routes)

class TransactionTest(unittest.TestCase):
    def setup_case(self, enabled=True):
        c=FakeClient(enabled);events=[];checks=[]
        def verify(v,u):checks.append((v,u));return True
        return c,events,checks,verify
    def run_case(self,c,events,verify):return promote(c,candidate=B,verify=verify,observe=events.append)
    def test_success_checks_prior_candidate_then_production(self):
        c,e,checks,v=self.setup_case();self.run_case(c,e,v)
        self.assertEqual([x[0] for x in checks],[A,A,B,B])
        self.assertEqual(checks[-1],(B,STABLE))
        self.assertEqual(c.writes,[('publish',B),('route',True)])
        self.assertEqual(e[-1]['event'],'passed')
    def test_prior_verification_failure_never_publishes(self):
        c,e,_,_=self.setup_case()
        with self.assertRaises(TransactionError):self.run_case(c,e,lambda v,u:False)
        self.assertEqual(c.writes,[])
    def test_candidate_verification_failure_preserves_prior(self):
        c,e,_,_=self.setup_case()
        with self.assertRaises(TransactionError):self.run_case(c,e,lambda v,u:v==A)
        self.assertEqual(c.active,{'id':D,'version_id':A});self.assertEqual(c.writes,[])
    def test_failed_production_restores_prior_and_rechecks_both_urls(self):
        c,e,checks,_=self.setup_case()
        def verify(v,u):checks.append((v,u));return not(v==B and u==STABLE)
        with self.assertRaises(TransactionError):self.run_case(c,e,verify)
        self.assertEqual(c.active['version_id'],A)
        self.assertEqual([v for v,u in checks[-2:]],[A,A]);self.assertEqual(checks[-1],(A,STABLE))
        self.assertEqual(e[-1]['event'],'recovered')
    def test_failed_first_publication_disables_route(self):
        c,e,_,_=self.setup_case(False)
        with self.assertRaises(TransactionError):self.run_case(c,e,lambda v,u:u!=STABLE)
        self.assertFalse(c.routes['enabled']);self.assertEqual(e[-1]['event'],'disabled-first-publication')
        self.assertEqual(c.writes,[('publish',B),('route',True),('route',False)])
    def test_unknown_publication_does_not_retry_or_restore(self):
        c,e,_,v=self.setup_case();c.unknown=True
        with self.assertRaises(TransactionError):self.run_case(c,e,v)
        self.assertEqual(c.writes,[('publish',B)]);self.assertEqual(e[-1]['event'],'reconciliation-required')
    def test_concurrent_candidate_change_stops_before_publication(self):
        c,e,_,_=self.setup_case()
        def verify(v,u):
            if v==B:c.active={'id':F,'version_id':A}
            return True
        with self.assertRaises(TransactionError):self.run_case(c,e,verify)
        self.assertEqual(c.writes,[]);self.assertEqual(c.active['id'],F)
    def test_concurrent_same_version_republication_is_not_rolled_back(self):
        c,e,_,_=self.setup_case()
        def verify(v,u):
            if v==B and u==STABLE:c.active={'id':F,'version_id':B};return False
            return True
        with self.assertRaises(TransactionError):self.run_case(c,e,verify)
        self.assertEqual(c.active['id'],F);self.assertEqual(c.writes,[('publish',B),('route',True)])
        self.assertNotIn('recovered',[x['event'] for x in e])
    def test_rejected_recovery_is_not_success(self):
        c,e,_,_=self.setup_case();c.reject_recovery=True
        with self.assertRaises(TransactionError):self.run_case(c,e,lambda v,u:not(v==B and u==STABLE))
        self.assertEqual(e[-1]['event'],'recovery-unconfirmed')
        self.assertEqual(c.active['version_id'],B)
    def test_failed_recovered_http_does_not_claim_recovery(self):
        c,e,_,_=self.setup_case()
        def verify(v,u):
            if v==B and u==STABLE:return False
            return not(c.active['id']==F and u==STABLE)
        with self.assertRaises(TransactionError):self.run_case(c,e,verify)
        self.assertEqual(c.active['version_id'],A)
        self.assertEqual(e[-1]['event'],'recovery-unconfirmed')
    def test_observer_failure_before_publication_prevents_write(self):
        c,_,_,v=self.setup_case()
        def observe(event):raise OSError('evidence storage unavailable')
        with self.assertRaises(OSError):promote(c,candidate=B,verify=v,observe=observe)
        self.assertEqual(c.writes,[])
    def test_truthy_verification_value_is_not_a_pass(self):
        c,e,_,_=self.setup_case()
        with self.assertRaises(TransactionError):self.run_case(c,e,lambda v,u:{'status':'failed'})
        self.assertEqual(c.writes,[])

    def test_disabled_preview_requires_explicit_setup(self):
        c,e,_,v=self.setup_case();c.routes['previews_enabled']=False
        with self.assertRaises(TransactionError):self.run_case(c,e,v)
        self.assertEqual(c.writes,[])
    def test_concurrent_route_change_during_candidate_prevents_publish(self):
        c,e,_,_=self.setup_case()
        def verify(v,u):
            if v==B:c.routes['enabled']=False
            return True
        with self.assertRaises(TransactionError):self.run_case(c,e,verify)
        self.assertEqual(c.writes,[]);self.assertFalse(c.routes['enabled'])

if __name__=='__main__' :unittest.main()
