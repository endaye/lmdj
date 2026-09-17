#!/usr/bin/env python3
"""Real journals/dispatch reader/Host validators, isolated Git and HTTP fixtures."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).parent))
import release_managed_dispatch_test as managed_fixture
from tools.release.deployment_effect import DeploymentEffect, HOSTS, LIMIT
from tools.release.model import canonical_json, canonical_sha256
from tools.release.orchestration import STEPS, JournalError
from tools.release.orchestration_driver import Observation
from tools.release.orchestration_driver import ReleaseDriver
import release_orchestration_driver_test as driver_fixture


CLOUDFLARE_CONTRACTS = {
    "web-runtime-host": "lmdj.web-runtime-host.deployment-evidence.v3",
    "creator-web": "lmdj.creator-web.deployment-evidence.v2",
}
# Built in a child so the two Hosts' same-named tool imports stay isolated, the
# way this file loads every Host fixture. These documents are what the
# deployment workflows publish, and what `HOSTS` now expects.
CLOUDFLARE_DOCUMENT = """
import json, sys
sys.path.insert(0, "apps/web-runtime-host/tools")
from cloudflare_deployment_evidence import CONTRACTS, WORKERS, production_url, version_url
host = sys.argv[1]
p, hv = "1.0.60.0", "3.0.0"
v = "1f2e3d4c-5b6a-4788-9900-aabbccddeeff"
stem = {"creator-web": "lmdj-creator-web"}.get(host, "lmdj-web-runtime-host")
def check(url):
    return {"status": "passed", "url": url, "product_build": p, "host_version": hv}
iu, lu = version_url(host, v), production_url(host)
print(json.dumps({
    "contract": CONTRACTS[host], "tag": "lmdj-v" + p, "product_build": p,
    "host_version": hv, "git_revision": "b" * 40, "channel": "canary",
    "worker": WORKERS[host],
    "release_url": "https://github.com/endaye/lmdj/releases/tag/lmdj-v" + p,
    "archive": {"filename": stem + "-" + hv + "-product-" + p + ".zip", "sha256": "1" * 64},
    "release_files": {"index_sha256": "2" * 64, "manifest_sha256": "3" * 64},
    "publication": {"version_id": v, "deployment_id": "9a8b7c6d-5e4f-4302-8110-223344556677",
                    "percentage": 100},
    "prior_good": None,
    "immutable": {"version_id": v, "url": iu, "http": check(iu), "browser": check(iu)},
    "production": {"url": lu, "http": check(lu), "browser": check(lu)},
    "github_actions": {"run_id": "41",
                       "run_url": "https://github.com/endaye/lmdj/actions/runs/41"},
    "started_at": "2026-09-17T04:00:00Z", "ended_at": "2026-09-17T04:20:00Z"}))
"""


class CloudflareEffectShapeTest(unittest.TestCase):
    """The two pieces the live routing rests on, each pinned on its own.

    The effect suite drives these through a real `DeploymentEffect`; these pin
    them where a driven test cannot say which half failed: the trusted validator
    the effect runs, and the extraction that turns a Cloudflare document into
    the one projection shape the comparison uses. The Netlify branch stays
    covered here because no live workflow reaches it any more.
    """

    VALIDATOR = ROOT / "apps/web-runtime-host/tools/cloudflare_deployment_evidence.py"

    def document(self, host="web-runtime-host"):
        loaded = subprocess.run([sys.executable, "-c", CLOUDFLARE_DOCUMENT, host],
                                capture_output=True, text=True, check=True, timeout=10)
        return json.loads(loaded.stdout)

    def extractor(self, contract):
        # `_site` and `_prior` read nothing but the contract, so a stand-in
        # carrying one is enough; building a DeploymentEffect would drag in the
        # dispatch consumer without testing more.
        stub = SimpleNamespace(contract=contract)
        return (lambda d: DeploymentEffect._site(stub, d),
                lambda p: DeploymentEffect._prior(stub, p))

    def validate(self, document, contract):
        return subprocess.run(
            [sys.executable, str(self.VALIDATOR), "validate", contract],
            input=json.dumps(document), capture_output=True, text=True, timeout=10)

    def test_the_trusted_validator_accepts_and_echoes_canonically(self):
        # `_document` compares the validator's stdout with canonical_json, so a
        # mismatch here would refuse every Cloudflare deployment once flipped.
        for host, contract in CLOUDFLARE_CONTRACTS.items():
            with self.subTest(host=host):
                document = self.document(host)
                result = self.validate(document, contract)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.encode(), canonical_json(document))

    def test_the_validator_refuses_a_document_from_another_host(self):
        document = self.document()
        result = self.validate(document, CLOUDFLARE_CONTRACTS["creator-web"])
        self.assertNotEqual(result.returncode, 0)

    def test_the_validator_refuses_unreadable_input_with_a_reason(self):
        # The effect refuses any nonzero exit, so this is about what the
        # operator reads: a reason, not a traceback or a decoder message. Both
        # ways an input can be unreadable, since they reach different handlers.
        for label, payload in (("undecodable bytes", b"\xff\xfe not json"),
                               ("valid bytes, not JSON", b"not json at all")):
            with self.subTest(input=label):
                result = subprocess.run(
                    [sys.executable, str(self.VALIDATOR), "validate",
                     CLOUDFLARE_CONTRACTS["creator-web"]],
                    input=payload, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"is not a readable document", result.stderr)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertNotIn(b"Expecting value", result.stderr)

    def test_the_validator_refuses_an_unsupported_contract(self):
        document = self.document()
        result = self.validate(document, "lmdj.web-runtime-host.deployment-evidence.v2")
        self.assertNotEqual(result.returncode, 0)

    def test_the_worker_is_the_site_identity(self):
        document = self.document()
        site, _ = self.extractor(CLOUDFLARE_CONTRACTS["web-runtime-host"])
        self.assertEqual(site(document), document["worker"])
        # The Netlify branch is untouched and still reads its own key.
        netlify, _ = self.extractor("lmdj.web-runtime-host.deployment-evidence.v2")
        self.assertEqual(netlify({"site_id": "a-netlify-site"}), "a-netlify-site")

    def test_the_prior_projects_into_the_one_comparison_shape(self):
        prior = {
            "version_id": "0e1d2c3b-4a59-4677-8899-ffeeddccbbaa",
            "version_url": "https://0e1d2c3b-lab.lmdj.workers.dev",
            "product_build": "1.0.59.0", "host_version": "2.9.0",
            "release_files": {"index_sha256": "4" * 64, "manifest_sha256": "5" * 64},
            "site_response": {"status": 200},
        }
        _, project = self.extractor(CLOUDFLARE_CONTRACTS["web-runtime-host"])
        projected = project(prior)
        # Exactly the key set DeploymentEffect validates on the frozen prior.
        self.assertEqual(set(projected), {
            "deploy_id", "deploy_url", "product_build", "host_version",
            "index_sha256", "manifest_sha256"})
        self.assertEqual(projected["deploy_id"], prior["version_id"])
        self.assertEqual(projected["deploy_url"], prior["version_url"])
        self.assertEqual(projected["index_sha256"], "4" * 64)
        self.assertEqual(projected["manifest_sha256"], "5" * 64)


class RuntimeEffectTest(unittest.TestCase):
    workflow = "deploy-web-runtime-host.yml"

    def setUp(self):
        m = managed_fixture.ManagedDispatchTest(); m.setUp(); self.addCleanup(m.doCleanups)
        m.configure(self.workflow)
        self.managed = m
        self.step, host, artifact_name, _ = HOSTS[self.workflow]
        fixture_file = ROOT / "apps/web-runtime-host/test/cloudflare_deployment_evidence_test.py"
        # Isolate the two Hosts' same-named Python imports. Do not replace their
        # production schema validator with a test callback.
        loaded = subprocess.run([sys.executable, "-c",
            "import json,runpy,sys; m=runpy.run_path(sys.argv[1]); print(json.dumps(m['document'](sys.argv[2])))",
            str(fixture_file), host], capture_output=True, text=True, check=True, timeout=10)
        self.document = json.loads(loaded.stdout)
        self.document["github_actions"] = {"run_id":"41", "run_url":"https://github.com/endaye/lmdj/actions/runs/41"}
        c = m.child; f = c.fixture
        c.spec["inputs"]["tag"] = self.document["tag"]
        c.spec["inputs"]["prior_site_sha256"] = canonical_sha256(self.document["prior_good"]["site_response"])
        f.inputs = deepcopy(c.spec["inputs"]); f.document["inputs"] = deepcopy(f.inputs); f.pack()
        m.adapter.spec = deepcopy(c.spec)
        f.run.update(status="completed", conclusion="success")
        f.job.update(status="completed", conclusion="success")
        self.artifact = {"id":90, "name":artifact_name, "expired":False, "expires_at":"2026-10-13T00:00:00Z",
            "workflow_run":{"id":41, "repository_id":10, "head_repository_id":10,
                            "head_sha":f.source, "head_branch":"main"}}
        self.pack()
        transport = c.client._http_transport
        self.post_hook = None
        def complete(method, url, headers, body):
            result = transport(method, url, headers, body)
            if method == "POST":
                self.jobs = f.routes["/actions/runs/41/attempts/1/jobs?per_page=100&page=1"]
                self.jobs["jobs"].append({**deepcopy(self.jobs["jobs"][0]), "id":142, "name":"deploy",
                    "steps":[{"name":"Upload deployment evidence and failure logs", "status":"completed", "conclusion":"success"}]})
                self.jobs["total_count"] = 2
                self.inventory = f.routes["/actions/runs/41/artifacts?per_page=100&page=1"]
                self.inventory["artifacts"].append(self.artifact); self.inventory["total_count"] = 2
                if self.post_hook: self.post_hook()
            return result
        c.client._http_transport = complete
        d = self.document; prior = d["prior_good"]
        self.expected = {**{k:deepcopy(d[k]) for k in ("product_build", "host_version", "archive", "release_files")},
            "site_id":d["worker"],
            "target_revision":d["git_revision"], "prior_site_sha256":c.spec["inputs"]["prior_site_sha256"], "prior":{
                "deploy_id":prior["version_id"], "deploy_url":prior["version_url"],
                **{k:prior[k] for k in ("product_build", "host_version")},
                **{k:prior["release_files"][k] for k in ("index_sha256", "manifest_sha256")}}}
        self.effect = DeploymentEffect(consumer=f.consumer, spec=c.spec, expected=self.expected)
        m.adapter.verify_effect = self.effect
        self.next_step = STEPS[STEPS.index(self.step)+1]
        m.backend.override[self.next_step] = Observation("pending")

    def pack(self, payload=None, members=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, data in (members if members is not None else [
                    ("evidence.json", canonical_json(self.document) if payload is None else payload),
                    ("deployment.log", b"fixture deployment completed\n")]):
                archive.writestr(name, data)
        raw = stream.getvalue()
        self.artifact.update(size_in_bytes=len(raw), digest="sha256:"+hashlib.sha256(raw).hexdigest())
        self.managed.child.fixture.extra_zips["/actions/artifacts/90/zip"] = raw

    def drive(self): return self.managed.driver.run(self.managed.request)

    def observe(self):
        m = self.managed; state = m.disk_state()
        operation = next(t for t in state["transitions"] if t["step"] == self.step)
        binding = m.child.controller.observe(m.child.spec)["binding"]
        return self.effect(state, operation, binding)

    def test_actual_host_schema_and_dispatch_are_composed_without_redeployment(self):
        result = self.drive()
        self.assertEqual((result.status, result.step), ("pending", self.next_step))
        self.assertEqual(self.observe().status, "verified")
        self.assertEqual(self.managed.new_driver().resume(self.managed.request["id"]), result)
        self.assertEqual(len(self.managed.child.posts), 1)

    def test_expected_prior_digest_must_match_original_dispatch_at_construction(self):
        expected = {**self.expected, "prior_site_sha256":"f" * 64}
        with self.assertRaisesRegex(JournalError, "original Site snapshot"):
            DeploymentEffect(consumer=self.managed.child.fixture.consumer,
                             spec=self.managed.child.spec, expected=expected)
        self.assertEqual(self.managed.child.posts, [])

    def test_pending_run_does_not_advance(self):
        self.managed.child.fixture.run.update(status="in_progress", conclusion=None)
        result = self.drive()
        self.assertEqual((result.status, result.step), ("pending", self.step))
        self.assertNotIn(self.next_step, self.managed.backend.calls)

    def test_failed_run_never_accepts_a_success_document_or_redeploys(self):
        self.managed.child.fixture.run.update(conclusion="failure")
        self.assertEqual(self.drive().status, "conflict")
        self.assertEqual(self.managed.new_driver().resume(self.managed.request["id"]).status, "conflict")
        self.assertEqual(len(self.managed.child.posts), 1)
        self.assertNotIn(self.next_step, self.managed.backend.calls)

    def test_failed_deploy_job_is_not_accepted(self):
        self.post_hook = lambda: self.jobs["jobs"][1].update(conclusion="failure")
        self.assertEqual(self.drive().status, "conflict")

    def test_wrong_deploy_attempt_is_not_accepted(self):
        self.post_hook = lambda: self.jobs["jobs"][1].update(run_attempt=2)
        self.assertEqual(self.drive().status, "conflict")

    def test_missing_upload_is_not_accepted(self):
        self.post_hook = lambda: self.jobs["jobs"][1].update(steps=[])
        self.assertEqual(self.drive().status, "unknown")

    def test_frozen_site_candidate_archive_bytes_and_prior_are_each_bound(self):
        self.drive()
        for key in self.expected:
            with self.subTest(key=key):
                saved = deepcopy(self.effect.expected[key])
                self.effect.expected[key] = "different" if not isinstance(saved, dict) else {**saved, "different":True}
                self.assertEqual(self.observe().status, "conflict")
                self.effect.expected[key] = saved
        self.assertEqual(self.observe().status, "verified")

    def test_reported_run_id_is_bound(self):
        self.document["github_actions"] = {"run_id":"42", "run_url":"https://github.com/endaye/lmdj/actions/runs/42"}
        self.pack(); self.assertEqual(self.drive().status, "conflict")

    def test_production_browser_identity_drift_is_refused_by_actual_host_validator(self):
        self.document["production"]["browser"]["product_build"] = "1.0.999.0"
        self.pack(); self.assertEqual(self.drive().status, "unknown")

    def test_prior_none_only_accepts_frozen_first_deployment(self):
        self.document["prior_good"] = None; self.pack()
        self.assertEqual(self.drive().status, "conflict")
        self.effect.expected["prior"] = None
        self.assertEqual(self.observe().status, "verified")

    def test_recovery_or_unsafe_extra_member_cannot_prove_success(self):
        self.drive()
        for name in ("recovery-evidence.json", "../evidence.json", "unexpected.json"):
            with self.subTest(name=name):
                self.pack(members=[("evidence.json", canonical_json(self.document)), (name, b"{}")])
                self.assertEqual(self.observe().status, "unknown")

    def test_duplicate_json_key_is_rejected_before_host_parser(self):
        raw = canonical_json(self.document)
        self.pack(payload=b'{"worker":"foreign",'+raw[1:])
        self.assertEqual(self.drive().status, "unknown")

    def _compressed_evidence(self, compression, *, forged=False):
        prefix = canonical_json(self.document)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=compression) as archive:
            archive.writestr("evidence.json", prefix + (b" " * (8 * LIMIT) if forged else b""))
            archive.writestr("deployment.log", b"fixture completed\n")
        raw = bytearray(stream.getvalue())
        if forged:
            central = raw.index(b"PK\x01\x02")
            for offset in (14, central + 16):
                struct.pack_into("<I", raw, offset, zlib.crc32(prefix))
            for offset in (22, central + 24):
                struct.pack_into("<I", raw, offset, len(prefix))
        self.assertLess(len(raw), LIMIT)
        self.artifact.update(size_in_bytes=len(raw), digest="sha256:" + hashlib.sha256(raw).hexdigest())
        self.managed.child.fixture.extra_zips["/actions/artifacts/90/zip"] = bytes(raw)

    def test_forged_zip_metadata_cannot_request_unbounded_decode(self):
        self.assertEqual(self.drive().step, self.next_step)
        self.assertEqual(self.observe().status, "verified")
        self._compressed_evidence(zipfile.ZIP_DEFLATED, forged=True)
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
            self.assertEqual(self.observe().status, "verified")
        self.assertTrue(observed)
        self.assertTrue(all(0 < limit <= LIMIT + 1 and size <= LIMIT + 1 for limit, size in observed), observed)
        self.assertEqual(len(self.managed.child.posts), 1)

    def test_compression_without_bounded_decoder_is_refused(self):
        self.assertEqual(self.drive().step, self.next_step)
        self.assertEqual(self.observe().status, "verified")
        for compression in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            with self.subTest(compression=compression):
                self._compressed_evidence(compression)
                self.assertEqual(self.observe().status, "unknown")
        self.assertEqual(len(self.managed.child.posts), 1)

    def test_wrong_artifact_origin_is_rejected(self):
        self.artifact["workflow_run"]["id"] = 42
        self.assertEqual(self.drive().status, "unknown")

    def test_internally_consistent_foreign_site_cannot_be_accepted(self):
        # Every mention of the Worker replaced at once, so the document agrees
        # with itself about a Worker that is not this Host's. The Cloudflare
        # validator binds the Worker to the Host, so this never reaches the
        # frozen comparison: it is refused one layer earlier than Netlify's was.
        worker = self.document["worker"]
        self.document = json.loads(
            canonical_json(self.document).replace(worker.encode(), b"different"))
        self.assertEqual(self.document["worker"], "different")
        self.pack()
        self.assertEqual(self.drive().status, "unknown")

    def test_a_frozen_site_the_document_does_not_name_is_a_conflict(self):
        # The comparison the validator cannot make: the Host's own Worker is
        # valid, and the projection this release froze names another.
        self.drive()
        self.effect.expected["site_id"] = "another-worker"
        self.assertEqual(self.observe().status, "conflict")

    def test_reused_reader_uses_live_clock_for_deployment_retention(self):
        class Clock(datetime):
            day = 13
            @classmethod
            def now(cls, tz=None): return cls(2026, 9, cls.day, tzinfo=tz)
        self.artifact["expires_at"] = "2026-09-14T00:00:00Z"
        self.managed.child.fixture.consumer._fixed_now = None
        with patch("tools.release.dispatch_evidence.datetime", Clock):
            self.assertEqual(self.drive().step, self.next_step)
            self.assertEqual(self.observe().status, "verified")
            Clock.day = 14
            self.assertEqual(self.observe().status, "unknown")

    def test_wrong_archive_digest_is_rejected(self):
        self.artifact["digest"] = "sha256:"+"f"*64
        self.assertEqual(self.drive().status, "unknown")

    def test_duplicate_evidence_artifact_is_rejected(self):
        def duplicate():
            self.inventory["artifacts"].append({**deepcopy(self.artifact), "id":91})
            self.inventory["total_count"] += 1
        self.post_hook = duplicate
        self.assertEqual(self.drive().status, "unknown")

    def test_evidence_expiring_during_host_validation_is_rejected_at_return(self):
        self.artifact["expires_at"] = "2026-09-14T00:00:00Z"
        self.drive()
        c = self.managed.child.fixture.consumer
        original = subprocess.run
        def expire(*args, **kwargs):
            result = original(*args, **kwargs)
            if self.document["contract"] in args[0]:
                c._fixed_now = datetime(2026, 9, 14, tzinfo=timezone.utc)
            return result
        with patch("tools.release.deployment_effect.subprocess.run", side_effect=expire):
            self.assertEqual(self.observe().status, "unknown")

    def test_later_artifact_drift_invalidates_completed_parent_evidence(self):
        self.drive()
        self.document["archive"]["sha256"] = "f"*64; self.pack()
        result = self.managed.new_driver().resume(self.managed.request["id"])
        self.assertEqual((result.status, result.step), ("evidence-conflict", self.step))
        self.assertEqual(len(self.managed.child.posts), 1)

    def test_correlation_expiring_after_last_binding_cannot_accept_longer_lived_deployment(self):
        def short_receipt():
            for artifact in self.inventory["artifacts"]:
                if artifact["name"] == "release-dispatch-correlation":
                    artifact["expires_at"] = "2026-09-14T00:00:00Z"
        self.post_hook = short_receipt
        self.assertEqual(self.drive().step, self.next_step)
        original = self.effect._outcome
        calls = 0
        def advance_clock(binding):
            nonlocal calls
            result = original(binding)
            calls += 1
            if calls == 2:
                self.managed.child.fixture.consumer._fixed_now = datetime(2026, 9, 14, tzinfo=timezone.utc)
            return result
        self.effect._outcome = advance_clock
        self.assertEqual(self.observe().status, "unknown")


class CreatorEffectTest(RuntimeEffectTest):
    workflow = "deploy-creator-web.yml"


class DualHostEffectTest(unittest.TestCase):
    def setUp(self):
        self.runtime = RuntimeEffectTest(); self.runtime.setUp(); self.addCleanup(self.runtime.doCleanups)
        self.creator = CreatorEffectTest(); self.creator.setUp(); self.addCleanup(self.creator.doCleanups)
        first, second = self.runtime.managed, self.creator.managed
        second.parent = first.parent
        first.backend.override.pop("creator")
        first.backend.override["promotion"] = Observation("pending")
        self.driver = ReleaseDriver(first.parent, driver_fixture.POLICY, first.backend,
                                    dispatches=(first.adapter, second.adapter))

    def test_both_real_effects_are_verified_in_order_before_promotion(self):
        first, second = self.runtime.managed, self.creator.managed
        result = self.driver.run(first.request)
        self.assertEqual((result.status, result.step), ("pending", "promotion"))
        self.assertEqual(result.verified_steps[-2:], ("runtime", "creator"))
        self.assertEqual(self.driver.resume(first.request["id"]), result)
        self.assertEqual((len(first.child.posts), len(second.child.posts)), (1, 1))

    def test_creator_failure_preserves_verified_runtime_without_retry_or_promotion(self):
        first, second = self.runtime.managed, self.creator.managed
        second.child.fixture.run.update(conclusion="failure")
        result = self.driver.run(first.request)
        self.assertEqual((result.status, result.step), ("conflict", "creator"))
        self.assertEqual(result.verified_steps[-1], "runtime")
        self.assertNotIn("promotion", first.backend.calls)
        self.assertEqual(self.driver.resume(first.request["id"]), result)
        self.assertEqual((len(first.child.posts), len(second.child.posts)), (1, 1))


if __name__ == "__main__": unittest.main()
