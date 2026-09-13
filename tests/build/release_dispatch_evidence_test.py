#!/usr/bin/env python3
"""Real Git, real producer schema and closed HTTP reader; isolated API fixture."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import struct
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(Path(__file__).parent))
import release_dispatch_receipt_test as producer_fixture
from tools.release.dispatch_receipt import receipt
from tools.release.dispatch_evidence import DispatchEvidenceConsumer, DispatchEvidenceError, LIMIT
from tools.release.github_api import GitHubClient, GitHubApiError, HttpResponse
from tools.release.model import canonical_json


class EvidenceTest(unittest.TestCase):
    def live_clock(self):
        class Clock(datetime):
            current = (2026, 9, 13)

            @classmethod
            def now(cls, tz=None):
                return cls(*cls.current, tzinfo=tz)

        mocked = patch("tools.release.dispatch_evidence.datetime", Clock)
        mocked.start()
        self.addCleanup(mocked.stop)
        self.consumer = DispatchEvidenceConsumer(api_get=self.client.get_dispatch_evidence,
            git_root=self.root, repository_id=10, workflow=self.workflow, workflow_id=50,
            producer_revision=self.source)
        return Clock

    def test_reused_reader_rejects_evidence_at_actual_expiry(self):
        clock = self.live_clock()
        self.assertEqual(self.verify()["run_id"], 40)
        clock.current = (2026, 10, 13)
        with self.assertRaisesRegex(DispatchEvidenceError, "retention elapsed"):
            self.verify()
        self.assertTrue(all(method == "GET" for method, _ in self.calls))

    def test_evidence_expiring_during_download_is_not_returned(self):
        clock = self.live_clock()
        self.assertEqual(self.verify()["run_id"], 40)
        self.after_download = lambda: setattr(clock, "current", (2026, 10, 13))
        with self.assertRaisesRegex(DispatchEvidenceError, "retention elapsed"):
            self.verify()

    def git(self,*args):
        return subprocess.run(["git","-C",str(self.root),*args],check=True,capture_output=True,text=True).stdout.strip()

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.git("init","-q","-b","main")
        self.git("-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","--allow-empty","-qm","producer")
        self.source=self.git("rev-parse","HEAD")
        fixture=producer_fixture.ReceiptTest();fixture.setUp()
        self.inputs=deepcopy(fixture.event["inputs"])
        self.workflow=fixture.workflow
        env={**fixture.env,"GITHUB_SHA":self.source,"GITHUB_WORKFLOW_SHA":self.source}
        self.document=receipt(fixture.event,env,self.workflow,self.source)
        repo={"id":10,"full_name":"endaye/lmdj"}
        self.run={"id":40,"run_attempt":1,"workflow_id":50,"path":".github/workflows/"+self.workflow,
            "head_sha":self.source,"head_branch":"main","event":"workflow_dispatch","actor":{"id":20},
            "repository":repo,"head_repository":repo,"status":"completed","conclusion":"failure"}
        self.job={"id":60,"run_id":40,"run_attempt":1,"head_sha":self.source,"name":"preflight",
            "status":"completed","conclusion":"failure","steps":[{"name":name,"status":"completed","conclusion":"success"}
            for name in ("Record dispatch correlation","Upload dispatch correlation")]}
        self.artifact={"id":70,"name":"release-dispatch-correlation","expired":False,"expires_at":"2026-10-13T00:00:00Z",
            "workflow_run":{"id":40,"repository_id":10,"head_repository_id":10,"head_sha":self.source,"head_branch":"main"}}
        self.routes={"/branches/main":{"name":"main","protected":True,"commit":{"sha":self.source}},
            "/actions/workflows/"+self.workflow:{"id":50,"path":".github/workflows/"+self.workflow,"state":"active"},
            "/actions/runs/40":self.run,"/actions/runs/40/attempts/1":self.run,
            "/actions/runs/40/attempts/1/jobs?per_page=100&page=1":{"total_count":1,"jobs":[self.job]},
            "/actions/runs/40/artifacts?per_page=100&page=1":{"total_count":1,"artifacts":[self.artifact]}}
        self.calls=[];self.after_download=None
        self.extra_zips={}
        self.routes["/actions/workflows/"+self.workflow+"/runs?per_page=100&page=1"]={"total_count":1,"workflow_runs":[self.run]}
        self.pack()
        self.client=GitHubClient(http_transport=self.transport)
        self.consumer=DispatchEvidenceConsumer(api_get=self.client.get_dispatch_evidence,git_root=self.root,
            repository_id=10,workflow=self.workflow,workflow_id=50,producer_revision=self.source,
            now=datetime(2026,9,13,tzinfo=timezone.utc))

    def pack(self,member="receipt.json",payload=None):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as archive:
            archive.writestr(member,canonical_json(self.document) if payload is None else payload)
        self.zip=stream.getvalue()
        self.artifact.update(size_in_bytes=len(self.zip),digest="sha256:"+hashlib.sha256(self.zip).hexdigest())

    def transport(self,method,url,headers,body):
        self.calls.append((method,url));self.assertEqual(method,"GET");self.assertIsNone(body)
        prefix="/repos/endaye/lmdj";self.assertTrue(url.startswith(prefix));suffix=url[len(prefix):]
        if suffix in self.extra_zips:
            return HttpResponse(200,{"Content-Type":"application/zip"},self.extra_zips[suffix])
        if suffix=="/actions/artifacts/70/zip":
            if self.after_download:self.after_download()
            return HttpResponse(200,{"Content-Type":"application/zip"},self.zip)
        return HttpResponse(200,{},json.dumps(self.routes[suffix]).encode())

    def verify(self):
        return self.consumer.verify(run_id=40,actor_id=20,control_revision=self.source,inputs=self.inputs)

    def discover(self,prior=None):
        return self.consumer.discover(actor_id=20,control_revision=self.source,inputs=self.inputs,
                                      prior_run_ids=[] if prior is None else prior)

    def another_run(self,number,request_id=None,control=None):
        control=control or self.source
        row={**deepcopy(self.run),"id":number,"head_sha":control}
        job={**deepcopy(self.job),"id":number+100,"run_id":number,"head_sha":control}
        artifact={**deepcopy(self.artifact),"id":number+200}
        artifact["workflow_run"].update(id=number,head_sha=control)
        document=deepcopy(self.document)
        document.update(run_id=number,head_sha=control,workflow_sha=control,tooling_revision=control)
        if request_id is not None:document["inputs"]["request_id"]=request_id
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as archive:archive.writestr("receipt.json",canonical_json(document))
        raw=stream.getvalue();artifact.update(size_in_bytes=len(raw),digest="sha256:"+hashlib.sha256(raw).hexdigest())
        self.extra_zips[f"/actions/artifacts/{artifact['id']}/zip"]=raw
        self.routes.update({f"/actions/runs/{number}":row,f"/actions/runs/{number}/attempts/1":row,
            f"/actions/runs/{number}/attempts/1/jobs?per_page=100&page=1":{"total_count":1,"jobs":[job]},
            f"/actions/runs/{number}/artifacts?per_page=100&page=1":{"total_count":1,"artifacts":[artifact]}})
        inventory=self.routes["/actions/workflows/"+self.workflow+"/runs?per_page=100&page=1"]
        inventory["workflow_runs"].append(row);inventory["total_count"]+=1
        return row

    def test_discovery_correlates_original_run_without_post(self):
        result=self.discover()
        self.assertEqual(result["status"],"correlated");self.assertEqual(result["binding"]["run_id"],40)
        self.assertTrue(all(method=="GET" for method,_ in self.calls))

    def test_empty_discovery_is_unknown_not_absence_or_retry(self):
        self.routes["/actions/workflows/"+self.workflow+"/runs?per_page=100&page=1"]={"total_count":0,"workflow_runs":[]}
        self.assertEqual(self.discover(),{"status":"unknown","binding":None})

    def test_duplicate_original_request_is_conflict(self):
        self.another_run(41)
        self.assertEqual(self.discover(),{"status":"conflict","binding":None})

    def test_duplicate_request_on_newer_control_is_also_conflict(self):
        self.git("-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","--allow-empty","-qm","new-main")
        newer=self.git("rev-parse","HEAD")
        self.routes["/branches/main"]["commit"]["sha"]=newer
        self.another_run(41,control=newer)
        self.assertEqual(self.discover()["status"],"conflict")

    def test_unrelated_authenticated_request_does_not_hide_match(self):
        self.another_run(41,request_id="f"*64)
        self.assertEqual(self.discover()["binding"]["run_id"],40)

    def test_unreadable_new_candidate_prevents_uniqueness(self):
        self.another_run(41,request_id="f"*64)
        self.routes[f"/actions/runs/41/artifacts?per_page=100&page=1"]={"total_count":0,"artifacts":[]}
        self.assertEqual(self.discover()["status"],"unknown")

    def test_pre_post_baseline_excludes_only_preexisting_ids(self):
        self.another_run(41,request_id="f"*64)
        del self.routes["/actions/runs/41"]
        self.assertEqual(self.discover(prior=[41])["binding"]["run_id"],40)
        self.assertFalse(any(url.endswith("/actions/runs/41") for _,url in self.calls))

    def test_new_candidate_during_scan_is_unknown(self):
        self.after_download=lambda:self.another_run(41)
        self.assertEqual(self.discover()["status"],"unknown")

    def test_scan_wrong_total_does_not_claim_unique_match(self):
        self.routes["/actions/workflows/"+self.workflow+"/runs?per_page=100&page=1"]["total_count"]=2
        self.assertEqual(self.discover()["status"],"unknown")

    def test_actual_input_read_does_not_weaken_exact_input_verifier(self):
        self.document["inputs"]["request_id"]="f"*64;self.pack()
        read=self.consumer.read(run_id=40,actor_id=20,control_revision=self.source)
        self.assertEqual(read["inputs"]["request_id"],"f"*64)
        with self.assertRaises(DispatchEvidenceError):self.verify()

    def test_producer_zip_correlates_failed_effect_without_claiming_success_or_writing(self):
        before=self.git("status","--porcelain")
        result=self.verify()
        self.assertEqual(result,self.verify());self.assertEqual(result["run_id"],40)
        self.assertEqual(result["inputs"],self.inputs)
        self.assertEqual((result["repository_id"],result["actor_id"],result["workflow_id"]),(10,20,50))
        self.assertEqual(result["producer_revision"],self.source)
        self.assertNotIn("verified",result);self.assertNotIn("success",result)
        self.assertEqual(self.git("status","--porcelain"),before)

    def test_still_running_effect_can_be_correlated(self):
        self.run.update(status="in_progress",conclusion=None)
        self.assertEqual(self.verify()["run_id"],40)

    def test_each_host_dispatch_binds_its_workflow_tag_and_original_site(self):
        for workflow in ("deploy-web-runtime-host.yml","deploy-creator-web.yml"):
            with self.subTest(workflow=workflow):
                self.consumer.workflow=workflow
                self.inputs={k:v for k,v in self.inputs.items() if k in ("tag","request_id")}
                self.inputs["prior_site_sha256"] = "e" * 64
                self.run["path"]=".github/workflows/"+workflow
                self.routes["/actions/workflows/"+workflow]={"id":50,"path":self.run["path"],"state":"active"}
                self.document.update(workflow=workflow,inputs=dict(self.inputs));self.pack()
                self.assertEqual(self.verify()["inputs"],self.inputs)
                self.document["inputs"]["prior_site_sha256"] = "f" * 64
                self.pack()
                with self.assertRaises(DispatchEvidenceError): self.verify()

    def test_one_changed_run_identity_is_refused(self):
        original=deepcopy(self.run)
        for key,value in {"id":41,"run_attempt":2,"workflow_id":51,"path":".github/workflows/other.yml",
                "head_branch":"other","event":"push","head_sha":"f"*40,"actor":{"id":21},
                "head_repository":{"id":11,"full_name":"endaye/lmdj"}}.items():
            with self.subTest(key=key):
                self.run.clear();self.run.update(deepcopy(original));self.run[key]=value
                with self.assertRaises(DispatchEvidenceError):self.verify()

    def test_receipt_wrong_request_tag_plan_or_numeric_release_is_refused(self):
        old=deepcopy(self.document)
        for key,value in {"request_id":"f"*64,"tag":"lmdj-v1.0.57.0","release_id":"31","plan_sha256":"f"*64}.items():
            with self.subTest(key=key):
                self.document=deepcopy(old);self.document["inputs"][key]=value;self.pack()
                with self.assertRaisesRegex(DispatchEvidenceError,"exact request"):self.verify()

    def test_failed_or_skipped_upload_is_not_evidence(self):
        self.job["steps"][1]["conclusion"]="skipped"
        with self.assertRaisesRegex(DispatchEvidenceError,"did not succeed"):self.verify()

    def test_artifact_wrong_run_origin_is_refused(self):
        self.artifact["workflow_run"]["id"]=41
        with self.assertRaisesRegex(DispatchEvidenceError,"origin differs"):self.verify()

    def test_expired_artifact_is_not_negative_dispatch_proof(self):
        self.artifact["expires_at"]="2026-09-12T00:00:00Z"
        with self.assertRaisesRegex(DispatchEvidenceError,"retention elapsed"):self.verify()

    def test_transfer_digest_is_verified(self):
        self.artifact["digest"]="sha256:"+"f"*64
        with self.assertRaisesRegex(DispatchEvidenceError,"transfer differs"):self.verify()

    def test_duplicate_artifact_is_ambiguous(self):
        inventory=self.routes["/actions/runs/40/artifacts?per_page=100&page=1"]
        inventory.update(total_count=2,artifacts=[self.artifact,{**self.artifact,"id":71}])
        with self.assertRaisesRegex(DispatchEvidenceError,"ambiguous"):self.verify()

    def test_truncated_inventory_is_refused(self):
        self.routes["/actions/runs/40/artifacts?per_page=100&page=1"]["total_count"]=2
        with self.assertRaisesRegex(DispatchEvidenceError,"truncated"):self.verify()

    def test_second_page_artifact_is_collected(self):
        filler=[{"id":100+n,"name":"unrelated"} for n in range(100)]
        self.routes["/actions/runs/40/artifacts?per_page=100&page=1"]={"total_count":101,"artifacts":filler}
        self.routes["/actions/runs/40/artifacts?per_page=100&page=2"]={"total_count":101,"artifacts":[self.artifact]}
        self.assertEqual(self.verify()["artifact_id"],70)

    def test_member_path_is_refused(self):
        self.pack(member="../receipt.json")
        with self.assertRaisesRegex(DispatchEvidenceError,"unsafe"):self.verify()

    def test_duplicate_json_is_refused(self):
        self.pack(payload=canonical_json(self.document).replace(b'"run_id":40',b'"run_id":40,"run_id":40'))
        with self.assertRaisesRegex(DispatchEvidenceError,"malformed"):self.verify()

    def test_forged_zip_size_cannot_request_unbounded_decompression(self):
        self.assertEqual(self.verify()["run_id"], 40)
        prefix = canonical_json(self.document)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("receipt.json", prefix + b" " * (8 * LIMIT))
        forged = bytearray(stream.getvalue())
        central = forged.index(b"PK\x01\x02")
        for offset in (14, central + 16):
            struct.pack_into("<I", forged, offset, zlib.crc32(prefix))
        for offset in (22, central + 24):
            struct.pack_into("<I", forged, offset, len(prefix))
        self.zip = bytes(forged)
        self.artifact.update(size_in_bytes=len(self.zip), digest="sha256:" + hashlib.sha256(self.zip).hexdigest())
        self.assertLess(len(self.zip), LIMIT)
        factory = zipfile._get_decompressor
        observed = []

        class RecordingDecompressor:
            def __init__(self, inner):
                self.inner = inner

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def decompress(self, data, max_length=0):
                result = self.inner.decompress(data, max_length)
                observed.append((max_length, len(result)))
                return result

        with patch.object(zipfile, "_get_decompressor", side_effect=lambda *a: RecordingDecompressor(factory(*a))):
            self.assertEqual(self.verify()["run_id"], 40)
        self.assertTrue(observed)
        self.assertTrue(all(0 < limit <= LIMIT + 1 and size <= LIMIT + 1
                            for limit, size in observed), observed)

    def test_compression_without_bounded_decoder_is_refused(self):
        self.assertEqual(self.verify()["run_id"], 40)
        for compression in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            with self.subTest(compression=compression):
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w", compression=compression) as archive:
                    archive.writestr("receipt.json", canonical_json(self.document))
                self.zip = stream.getvalue()
                self.artifact.update(size_in_bytes=len(self.zip), digest="sha256:" + hashlib.sha256(self.zip).hexdigest())
                with self.assertRaisesRegex(DispatchEvidenceError, "compression does not support bounded decoding"):
                    self.verify()

    def test_partial_clone_cannot_lazy_fetch_missing_objects(self):
        (self.root/"blob.txt").write_text("source object must stay local")
        self.git("add","blob.txt")
        self.git("-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","-qm","blob")
        oid=self.git("rev-parse","HEAD:blob.txt")
        with tempfile.TemporaryDirectory() as directory:
            bare,partial=Path(directory)/"remote.git",Path(directory)/"partial"
            def git(*args):
                return subprocess.run(["git",*map(str,args)],check=True,capture_output=True,text=True).stdout
            git("clone","--bare",self.root,bare)
            git("-C",bare,"config","uploadpack.allowFilter","true")
            git("clone","--filter=blob:none","--no-checkout",bare.as_uri(),partial)
            self.assertIn("?"+oid,git("-C",partial,"rev-list","--objects","--all","--missing=print"))
            requests=[]
            class Reject(BaseHTTPRequestHandler):
                def do_GET(self):
                    requests.append(self.path);self.send_error(500)
                def log_message(self,*args):pass
            server=HTTPServer(("127.0.0.1",0),Reject)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                git("-C",partial,"remote","set-url","origin",f"http://127.0.0.1:{server.server_port}/remote.git")
                env={k:v for k,v in os.environ.items() if k in ("PATH","SYSTEMROOT","TMPDIR","TEMP","TMP")}
                env.update(GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM="1",GIT_ALLOW_PROTOCOL="http",GIT_TERMINAL_PROMPT="0")
                baseline=subprocess.run(["git","-C",str(partial),"cat-file","blob",oid],env=env,capture_output=True,timeout=10)
                self.assertNotEqual(baseline.returncode,0);self.assertTrue(requests);requests.clear()
                self.consumer.root=partial
                # Simulate a Git version that ignores GIT_NO_LAZY_FETCH while
                # retaining real partial-clone transport behavior. The protocol
                # prohibition must independently prevent any observer request.
                execute=subprocess.run
                def legacy_git(*args,**kwargs):
                    kwargs["env"]=dict(kwargs["env"])
                    kwargs["env"].pop("GIT_NO_LAZY_FETCH",None)
                    return execute(*args,**kwargs)
                with patch("tools.release.dispatch_evidence.subprocess.run",side_effect=legacy_git):
                    with self.assertRaises(DispatchEvidenceError):self.consumer.git("cat-file","blob",oid)
                self.assertEqual(requests,[])
                self.assertIn("?"+oid,git("-C",partial,"rev-list","--objects","--all","--missing=print"))
            finally:
                server.shutdown();server.server_close();thread.join()

    def test_rerun_during_archive_read_is_refused(self):
        self.after_download=lambda:self.run.update(run_attempt=2)
        with self.assertRaisesRegex(DispatchEvidenceError,"run identity"):self.verify()

    def test_archive_inventory_change_during_read_is_refused(self):
        self.after_download=lambda:self.artifact.update(name="renamed")
        with self.assertRaisesRegex(DispatchEvidenceError,"inventory changed"):self.verify()

    def test_tooling_from_unmerged_branch_is_refused(self):
        self.git("-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","--allow-empty","-qm","not-on-observed-main")
        self.document["tooling_revision"]=self.git("rev-parse","HEAD");self.pack()
        with self.assertRaisesRegex(DispatchEvidenceError,"ancestry"):self.verify()

    def test_api_outage_does_not_echo_token_or_claim_absence(self):
        def unavailable(*args,**kwargs):raise RuntimeError("private-sentinel")
        self.consumer.api=unavailable
        with self.assertRaises(DispatchEvidenceError) as caught:self.verify()
        self.assertNotIn("private-sentinel",str(caught.exception))

    def test_transport_rejects_dispatch_external_and_other_attempt_routes_without_io(self):
        for suffix in ("/actions/workflows/publish-release.yml/dispatches","/actions/runs/40/attempts/2",
                       "/actions/runs/40/artifacts?per_page=100&page=101","https://evil.invalid"):
            with self.subTest(suffix=suffix),self.assertRaises(GitHubApiError):
                self.client.get_dispatch_evidence("/repos/endaye/lmdj"+suffix)
        self.assertEqual(self.calls,[])


if __name__=="__main__":unittest.main()
