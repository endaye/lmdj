#!/usr/bin/env python3
"""Actual private journal, real consumer/HTTP client and process-crash fixtures."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
import release_dispatch_evidence_test as fixtures
from tools.release.durable_dispatch import DurableDispatch,DurableDispatchError
from tools.release.github_api import GitHubClient,HttpResponse
from tools.release.orchestration import JournalError


class DurableTest(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.EvidenceTest();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()/"operation"
        f=self.fixture
        f.routes["/actions/workflows/"+f.workflow+"/runs?per_page=100&page=1"]={"total_count":0,"workflow_runs":[]}
        self.spec={"request_sha256":"b"*64,"operation_id":f.inputs["request_id"],"repository_id":10,"actor_id":20,
            "workflow":f.workflow,"workflow_id":50,"control_revision":f.source,"producer_revision":f.source,"inputs":deepcopy(f.inputs)}
        self.posts=[];self.mode="accept";self.authorized=True;self.prepared=True;self.guard_hook=None
        self.client=GitHubClient(http_transport=self.transport)
        f.consumer.api=self.client.get_dispatch_evidence
        self.controller=self.new_controller()

    def authorize(self,spec):
        if not self.authorized:raise ValueError("private-sentinel")
        self.assertEqual(spec,self.spec)

    def new_controller(self):
        return DurableDispatch(self.root,client=self.client,consumer=self.fixture.consumer,authorize=self.authorize,ready=self.ready)

    def ready(self,spec):
        if not self.prepared:raise ValueError("no longer a Draft")

    def transport(self,method,url,headers,body):
        if method=="POST":
            state=json.loads((self.root/"dispatch.json").read_bytes())
            self.assertTrue(state["post_intent"]);self.assertEqual(state["baseline"],[])
            self.assertEqual(url,"/repos/endaye/lmdj/actions/workflows/publish-release.yml/dispatches")
            self.assertEqual(json.loads(body),{"ref":"main","inputs":self.spec["inputs"]})
            self.posts.append(url)
            if self.mode=="drop":raise TimeoutError("private-sentinel")
            self.fixture.another_run(41)
            if self.mode=="accepted-timeout":raise TimeoutError("private-sentinel")
            if self.mode=="crash":
                (self.root.parent/"remote-accepted").write_text("41")
                os._exit(73)
            return HttpResponse(204,{},b"")
        if url=="/user":return HttpResponse(200,{},json.dumps({"id":20}).encode())
        if url=="/repos/endaye/lmdj":return HttpResponse(200,{},json.dumps({"id":10,"full_name":"endaye/lmdj"}).encode())
        if self.guard_hook and url.endswith("/branches/main"):
            hook=self.guard_hook;self.guard_hook=None;hook()
        return self.fixture.transport(method,url,headers,body)

    def test_successful_dispatch_is_correlated_and_resume_never_reposts(self):
        result=self.controller.start(self.spec)
        self.assertEqual(result["status"],"correlated");self.assertEqual(result["binding"]["run_id"],41)
        self.assertEqual(self.new_controller().resume(self.spec),result)
        self.assertEqual(self.new_controller().start(self.spec),result)
        self.assertEqual(len(self.posts),1)
        self.assertEqual((self.root/"dispatch.json").stat().st_mode&0o777,0o600)

    def test_accepted_then_timeout_recovers_original_run(self):
        self.mode="accepted-timeout"
        self.assertEqual(self.controller.start(self.spec)["status"],"correlated")
        self.assertEqual(self.new_controller().resume(self.spec)["binding"]["run_id"],41)
        self.assertEqual(len(self.posts),1)

    def test_unknown_delivery_remains_unknown_without_replay(self):
        self.mode="drop"
        self.assertEqual(self.controller.start(self.spec),{"status":"unknown","binding":None})
        self.assertEqual(self.new_controller().resume(self.spec)["status"],"unknown")
        self.assertEqual(self.new_controller().start(self.spec)["status"],"unknown")
        self.assertEqual(len(self.posts),1)

    def test_late_receipt_is_found_on_same_intent(self):
        self.mode="drop";self.controller.start(self.spec)
        self.fixture.another_run(41)
        self.assertEqual(self.new_controller().resume(self.spec)["binding"]["run_id"],41)
        self.assertEqual(len(self.posts),1)

    def test_missing_state_is_not_recreated(self):
        self.root.mkdir(mode=0o700)
        self.assertEqual(self.controller.start(self.spec)["status"],"unknown")
        self.assertFalse((self.root/"dispatch.json").exists());self.assertEqual(self.posts,[])

    def test_growing_baseline_cannot_replace_readable_state_with_oversized_intent(self):
        # This input is accepted by the local closed validator; no claim is
        # made that the GitHub platform accepts such a long tag. Enrollment
        # fits the existing 1MiB reader limit, but the complete baseline does not.
        self.spec["inputs"]["tag"] = "lmdj-v1.0." + "9" * 900000 + ".0"
        workflow_runs = "/actions/workflows/" + self.fixture.workflow + "/runs"
        for page in range(1, 101):
            rows = [{"id": 10**18 + (page - 1) * 100 + i} for i in range(100)]
            self.fixture.routes[workflow_runs + f"?per_page=100&page={page}"] = {
                "total_count": 10000, "workflow_runs": rows}
        enrolled = []

        def transport(method, url, headers, body):
            if method == "POST":
                self.posts.append(url)
                self.fixture.routes[workflow_runs + "?per_page=100&page=1"] = {
                    "total_count": 0, "workflow_runs": []}
                raise TimeoutError("fixture delivery is unknown")
            if not enrolled and url.endswith(workflow_runs + "?per_page=100&page=1"):
                enrolled.append((self.root/"dispatch.json").read_bytes())
            return self.transport(method, url, headers, body)

        self.client = GitHubClient(http_transport=transport)
        self.fixture.consumer.api = self.client.get_dispatch_evidence
        self.controller = self.new_controller()
        with self.assertRaisesRegex(DurableDispatchError, "size bound"):
            self.controller.start(self.spec)
        self.assertEqual(self.posts, [])
        self.assertEqual((self.root/"dispatch.json").read_bytes(), enrolled[0])
        self.assertLessEqual(len(enrolled[0]), 1024 * 1024)
        self.assertFalse(json.loads(enrolled[0])["post_intent"])
        self.assertIsNone(json.loads(enrolled[0])["baseline"])
        # The public resume entrypoint can still read the original state; it
        # refuses the same oversized growth before any transport attempt.
        with self.assertRaisesRegex(DurableDispatchError, "size bound"):
            self.new_controller().resume(self.spec)
        self.assertEqual(self.posts, [])

    def test_oversized_enrollment_is_not_persisted_or_sent(self):
        self.spec["inputs"]["tag"] = "lmdj-v1.0." + "9" * (1024 * 1024) + ".0"
        with self.assertRaisesRegex(DurableDispatchError, "size bound"):
            self.controller.start(self.spec)
        self.assertFalse((self.root/"dispatch.json").exists())
        self.assertEqual(self.posts, [])

    def test_missing_directory_on_resume_is_not_created(self):
        self.assertEqual(self.controller.resume(self.spec)["status"],"unknown")
        self.assertFalse(self.root.exists())

    def test_changed_scope_is_rejected_before_another_post(self):
        self.controller.start(self.spec)
        changed=deepcopy(self.spec);changed["request_sha256"]="c"*64
        # Allow the caller's authority callback to reach the actual state binding.
        other=DurableDispatch(self.root,client=self.client,consumer=self.fixture.consumer,authorize=lambda _:None,ready=self.ready)
        with self.assertRaises(DurableDispatchError):other.resume(changed)
        self.assertEqual(len(self.posts),1)

    def test_corrupt_state_never_resets_intent(self):
        self.mode="drop";self.controller.start(self.spec)
        (self.root/"dispatch.json").write_bytes(b'{"secret":"private-sentinel"}')
        with self.assertRaises(DurableDispatchError) as caught:self.new_controller().resume(self.spec)
        self.assertNotIn("private-sentinel",str(caught.exception));self.assertEqual(len(self.posts),1)

    def test_lost_authority_before_post_prevents_write(self):
        self.guard_hook=lambda:setattr(self,"authorized",False)
        with self.assertRaises(DurableDispatchError):self.controller.start(self.spec)
        self.assertEqual(self.posts,[])

    def test_replaced_writer_lock_before_post_prevents_write(self):
        def replace():
            (self.root/"writer.lock").rename(self.root/"retained-old.lock")
            fd=os.open(self.root/"writer.lock",os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        self.guard_hook=replace
        with self.assertRaises(JournalError):self.controller.start(self.spec)
        self.assertEqual(self.posts,[])

    def test_process_crash_after_remote_acceptance_recovers_without_post(self):
        self.mode="crash"
        child=os.fork()
        if child==0:
            try:self.controller.start(self.spec)
            finally:os._exit(74)
        _,result=os.waitpid(child,0)
        self.assertEqual(os.waitstatus_to_exitcode(result),73)
        self.assertEqual((self.root.parent/"remote-accepted").read_text(),"41")
        self.fixture.another_run(41)
        recovered=self.new_controller().resume(self.spec)
        self.assertEqual(recovered["binding"]["run_id"],41)
        self.assertEqual(self.posts,[]) # child sent once; recovery sent none

    def test_process_crash_after_intent_before_post_is_not_replayed(self):
        child=os.fork()
        if child==0:
            self.guard_hook=lambda:os._exit(75)
            try:self.controller.start(self.spec)
            finally:os._exit(74)
        _,result=os.waitpid(child,0)
        self.assertEqual(os.waitstatus_to_exitcode(result),75)
        self.assertTrue(json.loads((self.root/"dispatch.json").read_bytes())["post_intent"])
        self.assertEqual(self.new_controller().resume(self.spec)["status"],"unknown")
        self.assertEqual(self.posts,[])

    def test_process_crash_before_intent_allows_first_post_only(self):
        child=os.fork()
        if child==0:
            original=self.controller._save
            def crash_before_intent(journal,state):
                if state["post_intent"]:os._exit(76)
                original(journal,state)
            self.controller._save=crash_before_intent
            try:self.controller.start(self.spec)
            finally:os._exit(74)
        _,result=os.waitpid(child,0)
        self.assertEqual(os.waitstatus_to_exitcode(result),76)
        self.assertFalse(json.loads((self.root/"dispatch.json").read_bytes())["post_intent"])
        self.assertEqual(self.new_controller().resume(self.spec)["status"],"correlated")
        self.assertEqual(len(self.posts),1)

    def test_changed_main_before_post_prevents_write_and_retains_intent(self):
        self.guard_hook=lambda:self.fixture.routes["/branches/main"]["commit"].update(sha="f"*40)
        self.assertEqual(self.controller.start(self.spec)["status"],"unknown")
        self.assertEqual(self.posts,[])
        self.assertTrue(json.loads((self.root/"dispatch.json").read_bytes())["post_intent"])

    def test_concurrent_writer_is_rejected(self):
        self.root.mkdir(mode=0o700)
        from tools.release.orchestration import RequestJournal
        with RequestJournal(self.root):
            with self.assertRaises(JournalError):self.new_controller().resume(self.spec)
        self.assertEqual(self.posts,[])

    def test_resume_does_not_require_superseded_pre_effect_state(self):
        self.assertEqual(self.controller.start(self.spec)["status"],"correlated")
        self.prepared=False # e.g. the Draft is now published
        self.assertEqual(self.new_controller().resume(self.spec)["status"],"correlated")
        self.assertEqual(len(self.posts),1)

    def test_initial_readiness_failure_does_not_record_a_post_intent(self):
        self.prepared=False
        with self.assertRaises(DurableDispatchError):self.controller.start(self.spec)
        self.assertFalse(json.loads((self.root/"dispatch.json").read_bytes())["post_intent"])
        self.assertEqual(self.posts,[])


if __name__=="__main__":unittest.main()
