#!/usr/bin/env python3
"""Actual publication verifier and dispatch consumer, isolated external fixtures."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
import release_publication_test as publication_fixture
import release_managed_dispatch_test as managed_fixture
from tools.release.model import Disposition, ReleaseLedger, canonical_sha256
from tools.release.orchestration_driver import Observation
from tools.release.publication_effect import PublicationEffect


class PublicationEffectTest(unittest.TestCase):
    def setUp(self):
        p=publication_fixture.PublicationTest();p.setUp();self.addCleanup(p.doCleanups)
        m=managed_fixture.ManagedDispatchTest();m.setUp();self.addCleanup(m.doCleanups)
        self.publication,self.managed=p,m
        self.record=p.collect()
        c=m.child;f=c.fixture
        c.spec["inputs"].update(tag=p.fixture.tag,release_id=str(p.created.release_id),plan_sha256=p.created.plan_sha256)
        f.inputs=deepcopy(c.spec["inputs"]);f.document["inputs"]=deepcopy(f.inputs);f.pack()
        m.adapter.spec=deepcopy(c.spec)
        f.run.update(status="completed",conclusion="success")
        f.job.update(status="completed",conclusion="success")
        self.job_mutation=None
        transport=c.client._http_transport
        def completed_jobs(method,url,headers,body):
            result=transport(method,url,headers,body)
            if method=="POST":
                inventory=f.routes["/actions/runs/41/attempts/1/jobs?per_page=100&page=1"]
                publish={**deepcopy(inventory["jobs"][0]),"id":142,"name":"publish","steps":[]}
                inventory["jobs"].append(publish);inventory["total_count"]=2
                if self.job_mutation:self.job_mutation(inventory)
            return result
        c.client._http_transport=completed_jobs
        self.expected={key:self.record[key] for key in ("target_revision","changelog_sha256","notes_sha256")}
        self.effect=PublicationEffect(context=p.fixture.context(),consumer=f.consumer,spec=c.spec,expected=self.expected)
        m.adapter.verify_effect=self.effect
        m.backend.override["published_record"]=Observation("pending")
        self.original=self.writes()

    def writes(self):
        f=self.publication.fixture
        return (f.github.create_calls,list(f.github.upload_calls),list(f.github.patch_calls),f.git.pushes)

    def drive(self):return self.managed.driver.run(self.managed.request)

    def test_real_collector_is_connected_and_observation_does_not_republish(self):
        m=self.managed
        result=self.drive()
        self.assertEqual((result.status,result.step),("pending","published_record"))
        state=m.disk_state();operation=state["transitions"][7]
        binding=m.child.controller.observe(m.child.spec)["binding"]
        observed=self.effect(state,operation,binding)
        self.assertEqual(observed.status,"verified")
        self.assertEqual(observed.evidence["sha256"],canonical_sha256(self.record))
        self.assertEqual(m.new_driver().resume(m.request["id"]),result)
        self.assertEqual(self.writes(),self.original);self.assertEqual(len(m.child.posts),1)

    def test_pending_run_is_not_release_acceptance(self):
        self.managed.child.fixture.run.update(status="in_progress",conclusion=None)
        result=self.drive()
        self.assertEqual((result.status,result.step),("pending","publication"))

    def test_failed_run_blocks_success_even_when_release_exists(self):
        self.managed.child.fixture.run.update(conclusion="failure")
        result=self.drive()
        self.assertEqual((result.status,result.step),("conflict","publication"))
        self.assertNotIn("runtime",self.managed.backend.calls)
        self.assertEqual(self.writes(),self.original)

    def test_wrong_candidate_is_conflict(self):
        self.effect.expected["target_revision"]="f"*40
        self.assertEqual(self.drive().status,"conflict")

    def test_successful_run_with_failed_preflight_is_not_accepted(self):
        self.job_mutation=lambda inventory:inventory["jobs"][0].update(conclusion="failure")
        self.assertEqual(self.drive().status,"conflict")

    def test_missing_publish_job_is_not_accepted(self):
        self.job_mutation=lambda inventory:inventory.update(jobs=inventory["jobs"][:1],total_count=1)
        self.assertEqual(self.drive().status,"conflict")

    def test_publish_job_from_another_attempt_is_not_accepted(self):
        self.job_mutation=lambda inventory:inventory["jobs"][1].update(run_attempt=2)
        self.assertEqual(self.drive().status,"conflict")

    def test_wrong_frozen_changelog_is_conflict(self):
        self.effect.expected["changelog_sha256"]="f"*64
        self.assertEqual(self.drive().status,"conflict")

    def test_wrong_frozen_notes_is_conflict(self):
        self.effect.expected["notes_sha256"]="f"*64
        self.assertEqual(self.drive().status,"conflict")

    def test_changed_public_body_cannot_complete_publication(self):
        f=self.publication.fixture
        f.github.release=replace(f.github.release,body=f.github.release.body+"\nDrift")
        result=self.drive()
        self.assertEqual((result.status,result.step),("unknown","publication"))

    def test_corrupt_asset_cannot_complete_publication(self):
        f=self.publication.fixture
        identifier=next(iter(f.github.payloads));f.github.payloads[identifier]=b"corrupt"
        self.assertEqual(self.drive().status,"unknown")

    def test_missing_publication_date_is_not_invented(self):
        f=self.publication.fixture
        f.github.release=replace(f.github.release,published_at=None)
        self.assertEqual(self.drive().status,"unknown")

    def test_draft_is_not_accepted_from_successful_run(self):
        f=self.publication.fixture
        f.github.release=replace(f.github.release,draft=True)
        self.assertEqual(self.drive().status,"unknown")

    def test_binding_is_independently_reverified(self):
        self.drive();m=self.managed;state=m.disk_state();operation=state["transitions"][7]
        binding=m.child.controller.observe(m.child.spec)["binding"]
        binding["artifact_sha256"]="f"*64
        self.assertEqual(self.effect(state,operation,binding).status,"unknown")

    def test_attempt_changes_during_release_read_prevent_acceptance(self):
        f=self.publication.fixture;m=self.managed
        original=f.github.get_release
        def changing(*args):
            value=original(*args)
            m.child.fixture.routes["/actions/runs/41"]["run_attempt"]=2
            return value
        f.github.get_release=changing
        self.assertEqual(self.drive().status,"unknown")

    def test_receipt_expiring_during_final_outcome_read_is_not_verified(self):
        result = self.drive()
        self.assertEqual((result.status, result.step), ("pending", "published_record"))
        m = self.managed
        state = m.disk_state()
        operation = state["transitions"][7]
        binding = m.child.controller.observe(m.child.spec)["binding"]
        original = self.effect._outcome
        calls = []

        def advancing_outcome(observed):
            # Execute real run/attempt/job reads; only advance the fixture
            # clock after the final read, without replacing its outcome.
            outcome = original(observed)
            calls.append(outcome)
            if len(calls) == 2:
                self.effect.consumer._fixed_now = datetime(2026, 10, 13, tzinfo=timezone.utc)
            return outcome

        self.effect._outcome = advancing_outcome
        self.assertEqual(self.effect(state, operation, binding).status, "unknown")
        self.assertEqual(calls, ["verified", "verified"])
        self.assertEqual(self.writes(), self.original)
        self.assertEqual(len(m.child.posts), 1)

    def test_published_ledger_handoff_preserves_proof_without_republication(self):
        result=self.drive();f=self.publication.fixture;m=self.managed
        published=replace(f.ledger.entries[0],disposition=Disposition.PUBLISHED)
        f.ledger=ReleaseLedger((published,),())
        self.effect.context=f.context()
        self.assertEqual(m.new_driver().resume(m.request["id"]),result)
        self.assertEqual(self.writes(),self.original);self.assertEqual(len(m.child.posts),1)


if __name__=="__main__":unittest.main()
