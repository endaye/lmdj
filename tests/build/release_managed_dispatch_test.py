#!/usr/bin/env python3
"""Real nested journals and dispatch reader; fake HTTP and effect verifier."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
import release_durable_dispatch_test as dispatch_fixture
import release_orchestration_driver_test as driver_fixture
from tools.release.dispatch_transition import DispatchTransition, WORKFLOW_STEPS
from tools.release.model import canonical_sha256
from tools.release.orchestration import JournalError, RequestJournal, STEPS
from tools.release.orchestration_driver import Observation, ReleaseDriver


class ManagedDispatchTest(unittest.TestCase):
    def setUp(self):
        self.child=dispatch_fixture.DurableTest();self.child.setUp();self.addCleanup(self.child.doCleanups)
        self.parent=self.child.root.parent/"parent"
        remote=self.child.root.parent/"effects";remote.mkdir()
        self.backend=driver_fixture.Backend(remote)
        self.request=dict(driver_fixture.request(),repository="endaye/lmdj",actor_id=20)
        self.backend.authenticate=lambda request,policy:self.assertTrue(self.backend.auth and request==self.request and policy==driver_fixture.POLICY)
        self.effect_status="pending";self.scope_valid=True;self.effect_calls=[]
        self.configure("publish-release.yml")

    def configure(self,workflow):
        c=self.child;f=c.fixture
        f.workflow=workflow
        step=WORKFLOW_STEPS[workflow]
        op=canonical_sha256({"request":canonical_sha256(self.request),"step":step})
        c.spec.update(request_sha256=canonical_sha256(self.request),operation_id=op,workflow=workflow)
        c.spec["inputs"]["request_id"]=op
        if workflow!="publish-release.yml":
            c.spec["inputs"].pop("release_id",None);c.spec["inputs"].pop("plan_sha256",None)
        f.inputs=deepcopy(c.spec["inputs"])
        f.document.update(inputs=deepcopy(f.inputs),workflow=workflow)
        f.run["path"]=".github/workflows/"+workflow
        f.routes["/actions/workflows/"+workflow]={"id":50,"path":f.run["path"],"state":"active"}
        f.routes["/actions/workflows/"+workflow+"/runs?per_page=100&page=1"]={"total_count":0,"workflow_runs":[]}
        f.consumer.workflow=workflow
        f.pack()
        c.controller=c.new_controller()
        self.adapter=DispatchTransition(c.controller,c.spec,bind=self.bind,verify_effect=self.verify_effect)
        original=c.transport
        def transport(method,url,headers,body):
            if method=="POST":
                state=self.disk_state()
                self.assertEqual(state["transitions"][-1]["step"],step)
                self.assertEqual(state["transitions"][-1]["status"],"intent")
                # The base fixture asserts the publish URL. Adapt that assertion
                # only, preserving real client routing and exact input checks.
                self.assertEqual(url,"/repos/endaye/lmdj/actions/workflows/"+workflow+"/dispatches")
                url="/repos/endaye/lmdj/actions/workflows/publish-release.yml/dispatches"
            return original(method,url,headers,body)
        c.client._http_transport=transport
        self.driver=self.new_driver()

    def disk_state(self):
        # Parent lock is intentionally still held by the actual driver at POST.
        return json.loads((self.parent/(self.request["id"]+".json")).read_bytes())["state"]

    def new_driver(self):
        return ReleaseDriver(self.parent,driver_fixture.POLICY,self.backend,dispatches=(self.adapter,))

    def bind(self,state,operation,spec):
        self.assertTrue(self.scope_valid)
        self.assertEqual(spec,self.child.spec)

    def verify_effect(self,state,operation,binding):
        self.assertEqual(binding["run_id"],41)
        self.assertEqual(binding["inputs"],self.child.spec["inputs"])
        self.effect_calls.append(binding)
        if self.effect_status=="error":raise RuntimeError("private-sentinel")
        if self.effect_status=="verified":
            return Observation("verified",{"sha256":"e"*64,"reference":"fixture:effect-41"})
        return Observation(self.effect_status)

    def test_correlation_is_not_completion_and_pending_effect_blocks_successors(self):
        result=self.driver.run(self.request)
        self.assertEqual((result.status,result.step),("pending","publication"))
        self.assertEqual(len(self.child.posts),1)
        self.assertNotIn("published_record",self.backend.calls)
        self.effect_status="verified"
        result=self.new_driver().resume(self.request["id"])
        self.assertEqual((result.status,result.verified_steps),("complete",STEPS))
        self.assertEqual(self.new_driver().resume(self.request["id"]),result)
        self.assertEqual(len(self.child.posts),1)
        evidence=self.disk_state()["transitions"][STEPS.index("publication")]["evidence"]
        self.assertNotEqual(evidence["sha256"],"e"*64)
        self.assertNotIn("publication",self.backend.calls)

    def test_observation_never_posts_even_when_enrolled_and_ready(self):
        c=self.child
        self.assertEqual(c.controller.observe(c.spec)["status"],"unknown")
        self.assertFalse(c.root.exists())
        self.assertEqual(c.controller.observe(c.spec,initialize=True)["status"],"absent")
        raw=(c.root/"dispatch.json").read_bytes()
        self.assertEqual(c.controller.observe(c.spec)["status"],"absent")
        self.assertEqual((c.root/"dispatch.json").read_bytes(),raw)
        self.assertEqual(c.posts,[])

    def test_parent_crash_before_child_post_recovers_the_first_send(self):
        advance=self.adapter.advance
        self.adapter.advance=lambda *a,**kw:(_ for _ in ()).throw(driver_fixture.Crash())
        with self.assertRaises(driver_fixture.Crash):self.driver.run(self.request)
        self.assertFalse(json.loads((self.child.root/"dispatch.json").read_bytes())["post_intent"])
        self.assertEqual(self.child.posts,[])
        self.adapter.advance=advance;self.effect_status="verified"
        self.assertEqual(self.new_driver().resume(self.request["id"]).status,"complete")
        self.assertEqual(len(self.child.posts),1)

    def test_process_death_before_child_post_reopens_enrolled_operation(self):
        pid=os.fork()
        if pid==0:
            self.adapter.advance=lambda *a,**kw:os._exit(75)
            try:self.driver.run(self.request)
            finally:os._exit(74)
        _,status=os.waitpid(pid,0)
        self.assertEqual(os.waitstatus_to_exitcode(status),75)
        self.assertEqual(self.disk_state()["transitions"][-1]["status"],"intent")
        self.assertFalse(json.loads((self.child.root/"dispatch.json").read_bytes())["post_intent"])
        self.effect_status="verified"
        self.assertEqual(self.new_driver().resume(self.request["id"]).status,"complete")
        self.assertEqual(len(self.child.posts),1)

    def test_missing_child_state_after_parent_intent_is_not_enrolled_again(self):
        self.driver.run(self.request)
        filename=self.child.root/"dispatch.json";filename.rename(self.child.root/"retained.json")
        self.effect_status="verified"
        self.assertEqual(self.new_driver().resume(self.request["id"]).status,"unknown")
        self.assertFalse(filename.exists());self.assertEqual(len(self.child.posts),1)

    def test_unknown_delivery_is_never_resent_and_late_receipt_is_reconciled(self):
        self.child.mode="drop"
        self.assertEqual(self.driver.run(self.request).status,"unknown")
        self.assertEqual(self.new_driver().resume(self.request["id"]).status,"unknown")
        self.child.fixture.another_run(41);self.effect_status="verified"
        self.assertEqual(self.new_driver().resume(self.request["id"]).status,"complete")
        self.assertEqual(len(self.child.posts),1)

    def test_read_only_effect_failure_never_allows_a_successor_or_repost(self):
        self.driver.run(self.request)
        for effect,expected in (("absent","unknown"),("conflict","conflict"),("unknown","unknown"),("error","unknown")):
            self.effect_status=effect
            self.assertEqual(self.new_driver().resume(self.request["id"]).status,expected)
        self.assertNotIn("runtime",self.backend.calls);self.assertEqual(len(self.child.posts),1)

    def test_changed_scope_cannot_enroll_or_send(self):
        self.scope_valid=False
        self.assertEqual(self.driver.run(self.request).status,"unknown")
        self.assertFalse(self.child.root.exists());self.assertEqual(self.child.posts,[])

    def test_scope_changed_at_transport_boundary_blocks_first_post(self):
        self.child.guard_hook=lambda:setattr(self,"scope_valid",False)
        self.assertEqual(self.driver.run(self.request).status,"unknown")
        self.assertEqual(self.child.posts,[])

    def test_verified_effect_is_revalidated_before_later_steps(self):
        self.effect_status="verified"
        self.backend.override["changelog_site"]=Observation("pending")
        self.assertEqual(self.driver.run(self.request).step,"changelog_site")
        self.effect_status="conflict"
        result=self.new_driver().resume(self.request["id"])
        self.assertEqual((result.status,result.step),("evidence-conflict","publication"))
        self.assertNotIn("runtime",self.backend.calls);self.assertEqual(len(self.child.posts),1)

    def test_completed_effect_with_changed_evidence_is_not_silently_adopted(self):
        self.effect_status="verified"
        self.assertEqual(self.driver.run(self.request).status,"complete")
        self.adapter.verify_effect=lambda *a:Observation("verified",{"sha256":"f"*64,"reference":"fixture:effect-41"})
        self.assertEqual(self.new_driver().resume(self.request["id"]).status,"evidence-conflict")
        self.assertEqual(len(self.child.posts),1)

    def test_changed_explicit_tag_is_rejected(self):
        self.request.update(mode="tag",requested_tag="lmdj-v1.0.999.0")
        self.configure("publish-release.yml")
        self.assertEqual(self.driver.run(self.request).status,"unknown")
        self.assertEqual(self.child.posts,[])

    def test_previous_evidence_conflict_stops_before_child_send(self):
        self.backend.override["draft"]=Observation("conflict")
        self.assertEqual(self.driver.run(self.request).step,"draft")
        self.assertEqual(self.child.posts,[])

    def test_parent_authority_lost_at_transport_boundary_blocks_post(self):
        self.child.guard_hook=lambda:setattr(self.backend,"auth",False)
        self.assertEqual(self.driver.run(self.request).status,"unknown")
        self.assertEqual(self.child.posts,[])

    def test_parent_writer_replaced_at_transport_boundary_blocks_post(self):
        def replace():
            (self.parent/"writer.lock").rename(self.parent/"retained.lock")
            fd=os.open(self.parent/"writer.lock",os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        self.child.guard_hook=replace
        with self.assertRaises(JournalError):self.driver.run(self.request)
        self.assertEqual(self.child.posts,[])

    def test_process_death_after_acceptance_reopens_original_nested_journals(self):
        self.child.mode="crash"
        pid=os.fork()
        if pid==0:
            try:self.driver.run(self.request)
            finally:os._exit(74)
        _,status=os.waitpid(pid,0)
        self.assertEqual(os.waitstatus_to_exitcode(status),73)
        self.assertEqual((self.child.root.parent/"remote-accepted").read_text(),"41")
        self.child.fixture.another_run(41);self.effect_status="verified"
        self.assertEqual(self.new_driver().resume(self.request["id"]).status,"complete")
        self.assertEqual(self.child.posts,[])

    def test_runtime_dispatch_uses_its_own_step_and_blocks_creator(self):
        self.configure("deploy-web-runtime-host.yml")
        result=self.driver.run(self.request)
        self.assertEqual((result.status,result.step),("pending","runtime"))
        self.assertNotIn("creator",self.backend.calls)
        self.effect_status="verified"
        self.assertEqual(self.new_driver().resume(self.request["id"]).status,"complete")
        self.assertEqual(len(self.child.posts),1)

    def test_creator_failure_preserves_runtime_and_blocks_promotion(self):
        self.configure("deploy-creator-web.yml");self.effect_status="conflict"
        result=self.driver.run(self.request)
        self.assertEqual((result.status,result.step),("conflict","creator"))
        self.assertIn("runtime",self.backend.calls);self.assertNotIn("promotion",self.backend.calls)
        self.assertEqual(self.new_driver().resume(self.request["id"]).status,"conflict")
        self.assertEqual(self.backend.calls.count("runtime"),1);self.assertEqual(len(self.child.posts),1)

    def test_duplicate_or_arbitrary_dispatch_adapter_is_rejected(self):
        for adapters in ((self.adapter,self.adapter),(lambda:None,)):
            with self.assertRaises(JournalError):
                ReleaseDriver(self.parent,driver_fixture.POLICY,self.backend,dispatches=adapters)


if __name__=="__main__":unittest.main()
