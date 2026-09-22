#!/usr/bin/env python3
"""Real HTTP/Cloudflare validators over routed loopback HTTP; no public TLS claim."""
import base64
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).parent))
from tools.release import live_host
from tools.release.orchestration import JournalError
import release_deployment_effect_test as effect_fixture


class HostTest(unittest.TestCase):
    host = "runtime"

    def setUp(self):
        host_id = live_host.HOSTS[self.host]
        name = live_host._evidence.worker_for(host_id)
        filename = ROOT / "apps" / host_id / "test/deployment_smoke_test.py"
        program = """import base64,json,runpy,sys
m=runpy.run_path(sys.argv[1]); f=m['SmokeFixture' if sys.argv[2]=='runtime' else 'Fixture']()
if sys.argv[2]=='runtime':
    f.manifest['host_id']='web-runtime-host'; f.update_manifest(update_index=True)
    f.payloads['/index.html']=f.payloads['/index.html'].replace(b'</head>',b'<meta name="lmdj-host-id" content="web-runtime-host"></head>')
    f.payloads['/']=f.payloads['/index.html']
print(json.dumps({'manifest':f.manifest,'payloads':{k:base64.b64encode(v).decode() for k,v in f.payloads.items()}}))
"""
        data = json.loads(subprocess.run([sys.executable, "-c", program, str(filename), self.host],
            check=True, capture_output=True, text=True, timeout=10).stdout)
        payloads = {k:base64.b64decode(v) for k,v in data["payloads"].items()}
        self.payloads = {kind:deepcopy(payloads) for kind in ("immutable", "production")}
        self.expected = {"worker":name, "version_id":"1f2e3d4c-5b6a-4788-9900-aabbccddeeff",
            "deployment_id":"9a8b7c6d-5e4f-4302-8110-223344556677",
            "product_build":data["manifest"]["product_build"], "host_version":data["manifest"]["host_version"],
            "index_sha256":hashlib.sha256(payloads["/index.html"]).hexdigest(),
            "manifest_sha256":hashlib.sha256(payloads["/host-manifest.json"]).hexdigest()}
        self.production = live_host._evidence.production_url(host_id)
        self.immutable = live_host._evidence.version_url(host_id, self.expected["version_id"])
        self.deployment = {"id":self.expected["deployment_id"], "versions":[{
            "version_id":self.expected["version_id"], "percentage":100}]}
        self.route = {"enabled":True, "previews_enabled":True}
        self.calls = []; self.api_calls = 0; self.api_hook = None; self.api_raw = None
        self.api_redirect = False; self.omit_header = None
        self.production_robots = None; self.traversal = None; self.public_hook = None
        case = self
        self_shared = live_host._smoke._shared()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                kind, _, route = self.path[1:].partition("/"); route = "/" + route
                case.calls.append((kind, route, self.headers.get("Authorization")))
                if kind == "api":
                    case.api_calls += 1
                    if case.api_hook: case.api_hook()
                    if case.api_redirect:
                        self.send_response(302); self.send_header("Location", case.base + "/leak"); self.end_headers(); return
                    payload = case.api_raw if case.api_raw is not None else json.dumps({"success":True, "result":({"deployments":[case.deployment]} if route.endswith("/deployments") else case.route)}).encode()
                    self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
                if kind not in case.payloads:
                    self.send_response(500); self.end_headers(); return
                if case.public_hook: case.public_hook(kind, route)
                if route == "/%2e%2e/index.html" and case.traversal == "edge":
                    payload = (b"<html><head><title>400 Bad Request</title></head>"
                        b"<body><center><h1>400 Bad Request</h1></center>"
                        b"<hr><center>cloudflare</center></body></html>")
                    self.send_response(400); self.end_headers(); self.wfile.write(payload); return
                payload = case.payloads[kind].get(route)
                self.send_response(404 if payload is None else 200)
                suffix = Path(route).suffix
                media = {".json":"application/json", ".mjs":"text/javascript", ".js":"text/javascript",
                         ".wasm":"application/wasm", ".css":"text/css"}.get(suffix, "text/html")
                self.send_header("Content-Type", "text/plain; charset=utf-8" if payload is None else media + ("" if media == "application/wasm" else "; charset=utf-8"))
                self.send_header("Cache-Control", "public, max-age=31536000, immutable" if payload is not None and route.startswith("/assets/") else "no-store")
                for key,value in {**self_shared.REQUIRED_SECURITY_HEADERS, "content-security-policy":self_shared.CSP}.items():
                    if key != case.omit_header:
                        self.send_header(key, ("noindex" if kind == "immutable" else case.production_robots or value) if key == "x-robots-tag" else value)
                if payload is not None: self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if payload is not None: self.wfile.write(payload)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(thread.join, 5); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_port}"

        class Response:
            def __init__(self, actual, url): self.actual, self.url = actual, url
            def __getattr__(self, key): return getattr(self.actual, key)
            def geturl(self): return self.url
            def __enter__(self): return self
            def __exit__(self, *args): self.actual.close()

        def routed_opener(*handlers):
            real = build_opener(*handlers)
            class Routed:
                addheaders = []
                def open(self, operation, timeout):
                    url = operation.full_url
                    case.assertEqual(operation.get_method(), "GET")
                    if url.startswith("https://api.cloudflare.com/client/v4/"):
                        kind, route = "api", urlsplit(url).path
                        base = f'/client/v4/accounts/{live_host._api.ACCOUNT}/workers/scripts/{case.expected["worker"]}/'
                        case.assertIn(route, (base + "deployments", base + "subdomain"))
                    else:
                        parsed = urlsplit(url)
                        origin = f"{parsed.scheme}://{parsed.netloc}"
                        case.assertIn(origin, (case.production, case.immutable))
                        kind = "production" if origin == case.production else "immutable"
                        route = parsed.path
                        case.assertIsNone(operation.get_header("Authorization"))
                    mapped = Request(case.base + "/" + kind + route, headers=dict(operation.header_items()), method="GET")
                    return Response(real.open(mapped, timeout=timeout), url)
            return Routed()
        for name in ("tools.release.live_host.build_opener", "tools.release.live_host._origin.build_opener", "tools.release.live_host._smoke.build_opener", "urllib.request.build_opener"):
            mocked = patch(name, side_effect=routed_opener); mocked.start(); self.addCleanup(mocked.stop)
        self.reader = live_host.WorkerReader(token="fixture-secret", target=host_id)
        self.verifier = live_host.LiveHostVerifier(self.reader)

    def verify(self): return self.verifier.verify(self.host, self.expected)

    def test_fresh_reads_verify_both_urls_every_asset_and_current_pointer(self):
        first = self.verify(); calls = len(self.calls)
        self.assertEqual(self.verify(), first)
        self.assertEqual(len(self.calls), calls * 2); self.assertEqual(self.api_calls, 8)
        for kind in ("immutable", "production"):
            observed = {route for found,route,_ in self.calls if found == kind}
            self.assertTrue(set(self.payloads[kind]).issubset(observed))
            self.assertTrue(set(live_host._smoke._shared().NEGATIVE_PATHS).issubset(observed))
        self.assertTrue(all(auth == ("Bearer fixture-secret" if kind == "api" else None) for kind,_,auth in self.calls))

    def test_wrong_pointer_refuses_before_http(self):
        self.deployment["versions"][0]["version_id"] = "0e1d2c3b-4a59-4677-8899-ffeeddccbbaa"
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(len(self.calls), 1)

    def test_pointer_change_during_http_refuses(self):
        self.api_hook = lambda: self.route.update(enabled=False) if self.api_calls == 4 else None
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(self.api_calls, 4)
        self.assertTrue(any(kind == "production" for kind,_,_ in self.calls))

    def test_each_url_asset_corruption_is_refused(self):
        self.verify()
        for kind in self.payloads:
            with self.subTest(kind=kind):
                key = next(k for k in self.payloads[kind] if k.startswith("/assets/"))
                original = self.payloads[kind][key]; self.payloads[kind][key] = b"wrong"
                with self.assertRaises(JournalError): self.verify()
                self.payloads[kind][key] = original

    def test_self_consistent_index_drift_is_not_the_signed_index(self):
        for kind in self.payloads:
            self.payloads[kind]["/index.html"] += b"\n<!-- changed -->"
            self.payloads[kind]["/"] = self.payloads[kind]["/index.html"]
        with self.assertRaises(JournalError): self.verify()
        self.assertFalse(any(route.startswith("/assets/") for _,route,_ in self.calls))

    def test_security_header_loss_is_refused(self):
        self.omit_header = "cross-origin-embedder-policy"
        with self.assertRaises(JournalError): self.verify()

    def test_api_redirect_never_forwards_credentials(self):
        self.api_redirect = True
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(len(self.calls), 1)

    def test_duplicate_api_json_is_refused_and_response_is_not_exposed(self):
        self.api_raw = b'{"success":true,"success":"fixture-secret","result":{}}'
        with self.assertRaises(JournalError) as caught: self.verify()
        self.assertNotIn("fixture-secret", str(caught.exception))

    def test_inherited_mutation_routes_are_closed_without_http(self):
        for call in (lambda:self.reader.publish(version=self.expected["version_id"], expected_deployment=self.expected["deployment_id"]),
                     lambda:self.reader.set_route(enabled=True, expected_deployment=self.expected["deployment_id"]),
                     lambda:self.reader._request("deployments", {}),
                     lambda:self.reader._request("../secrets")):
            with self.assertRaises(JournalError): call()
        self.assertEqual(self.calls, [])

    def test_invalid_frozen_site_is_rejected_without_network(self):
        self.expected["worker"] = "../secrets"
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(self.calls, [])

    def test_oversized_api_response_is_refused(self):
        self.api_raw = b"x" * (1024 * 1024 + 1)
        with self.assertRaises(JournalError): self.verify()

    def test_full_deployment_id_is_bound_even_when_version_is_unchanged(self):
        self.deployment["id"] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(len(self.calls), 1)

    def test_version_prefix_collision_is_not_the_full_version(self):
        self.deployment["versions"][0]["version_id"] = "1f2e3d4c-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(len(self.calls), 1)

    def test_split_traffic_is_not_the_expected_deployment(self):
        self.deployment["versions"][0]["percentage"] = 50
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(len(self.calls), 1)

    def test_changed_deployment_is_detected_on_the_far_side(self):
        self.api_hook = lambda: self.deployment.update(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa") if self.api_calls == 3 else None
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(self.api_calls, 3)
        self.assertTrue(any(kind == "production" for kind,_,_ in self.calls))

    def test_preview_robots_allowance_does_not_leak_to_production(self):
        self.production_robots = "noindex"
        with self.assertRaises(JournalError): self.verify()
        self.assertTrue(any(kind == "production" for kind,_,_ in self.calls))

    def test_changed_manifest_is_refused_before_asset_download(self):
        self.payloads["immutable"]["/host-manifest.json"] += b" "
        with self.assertRaises(JournalError): self.verify()
        self.assertFalse(any(route.startswith("/assets/") for _,route,_ in self.calls))

    def test_public_observation_detects_drift_after_the_full_smoke(self):
        def drift(kind, route):
            if kind == "production" and route == "/index.html" and sum(
                    k == kind and p == route for k,p,_ in self.calls) == 2:
                self.payloads[kind][route] += b" changed"
        self.public_hook = drift
        with self.assertRaises(JournalError): self.verify()
        self.assertTrue(any(k == "production" and p.startswith("/assets/") for k,p,_ in self.calls))

    def test_nested_duplicate_api_key_is_refused(self):
        raw = json.dumps({"success":True,"result":{"deployments":[self.deployment]}})
        raw = raw.replace('"percentage": 100', '"percentage": 0, "percentage": 100')
        self.api_raw = raw.encode()
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(len(self.calls), 1)

    def test_unknown_public_route_cannot_serve_the_index(self):
        path = live_host._smoke._shared().NEGATIVE_PATHS[0]
        self.payloads["immutable"][path] = self.payloads["immutable"]["/index.html"]
        with self.assertRaises(JournalError): self.verify()

    def test_encoded_path_accepts_only_the_exact_frozen_index(self):
        for payloads in self.payloads.values():
            payloads["/%2e%2e/index.html"] = payloads["/index.html"]
        self.verify()
        self.payloads["production"]["/%2e%2e/index.html"] += b" changed"
        with self.assertRaises(JournalError): self.verify()

    def test_cloudflare_fixed_edge_rejection_is_accepted(self):
        self.traversal = "edge"
        self.verify()

    def test_distribution_smoke_keeps_the_same_cloudflare_traversal_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            dist = Path(directory)
            for route, payload in self.payloads["production"].items():
                if route == "/": continue
                target = dist / route.lstrip("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            self.traversal = "edge"
            result = live_host._smoke.smoke(dist, self.production)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["encoded_dot_segments"], "rejected with Cloudflare's fixed 400 error page")
            self.traversal = None
            self.payloads["production"]["/%2e%2e/index.html"] = self.payloads["production"]["/index.html"]
            result = live_host._smoke.smoke(dist, self.production)
            self.assertEqual(result["file_digests"]["/%2e%2e/index.html"], self.expected["index_sha256"])




class CreatorHostTest(HostTest):
    host = "creator"


class ManagedLiveTest(unittest.TestCase):
    host = "runtime"
    setUp = HostTest.setUp
    def integrate(self):
        fixture = effect_fixture.RuntimeEffectTest() if self.host == "runtime" else effect_fixture.CreatorEffectTest()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        original = deepcopy(fixture.document)
        def update(value):
            if isinstance(value, dict): return {k:update(v) for k,v in value.items()}
            if isinstance(value, list): return [update(v) for v in value]
            if isinstance(value, str): return value.replace(original["product_build"], self.expected["product_build"]).replace(original["host_version"], self.expected["host_version"])
            return value
        fixture.document = update(original)
        for key in ("index_sha256", "manifest_sha256"):
            fixture.document["release_files"][key] = self.expected[key]
            fixture.effect.expected["release_files"][key] = self.expected[key]
        fixture.document["immutable"]["version_id"] = self.expected["version_id"]
        fixture.document["immutable"]["url"] = self.immutable
        fixture.document["publication"].update(version_id=self.expected["version_id"], deployment_id=self.expected["deployment_id"])
        for check in ("http", "browser"):
            fixture.document["immutable"][check]["url"] = self.immutable
        fixture.effect.expected.update(product_build=self.expected["product_build"], host_version=self.expected["host_version"],
                                       archive=deepcopy(fixture.document["archive"]))
        fixture.effect.expected["prior"] = fixture.effect._prior(fixture.document["prior_good"])
        child = fixture.managed.child; f = child.fixture
        child.spec["inputs"]["tag"] = fixture.document["tag"]
        prior_digest = live_host.canonical_sha256(fixture.document["prior_good"]["site_response"])
        child.spec["inputs"]["prior_site_sha256"] = prior_digest
        fixture.effect.expected["prior_site_sha256"] = prior_digest
        f.inputs = deepcopy(child.spec["inputs"]); f.document["inputs"] = deepcopy(f.inputs); f.pack()
        fixture.effect.spec = deepcopy(child.spec); fixture.managed.adapter.spec = deepcopy(child.spec)
        fixture.pack()
        fixture.managed.adapter.verify_effect = live_host.LiveDeploymentEffect(recorded=fixture.effect, live=self.verifier)
        return fixture

    def test_managed_dispatch_requires_fresh_live_proof_on_every_resume(self):
        fixture = self.integrate(); m = fixture.managed
        result = fixture.drive()
        self.assertEqual((result.status, result.step), ("pending", fixture.next_step))
        self.assertEqual(m.new_driver().resume(m.request["id"]), result)
        self.route["enabled"] = False
        result = m.new_driver().resume(m.request["id"])
        self.assertEqual((result.status, result.step), ("evidence-unknown", fixture.step))
        self.assertEqual(len(m.child.posts), 1)

    def test_live_failure_blocks_successor_without_redeployment(self):
        fixture = self.integrate(); m = fixture.managed
        self.route["enabled"] = False
        self.assertEqual(fixture.drive().status, "unknown")
        self.assertEqual(m.new_driver().resume(m.request["id"]).status, "unknown")
        self.assertNotIn(fixture.next_step, m.backend.calls)
        self.assertEqual(m.disk_state()["transitions"][-1]["status"], "intent")
        self.assertEqual(len(m.child.posts), 1)

    def test_retained_evidence_changed_during_live_checks_is_refused(self):
        fixture = self.integrate(); m = fixture.managed
        def drift():
            if self.api_calls == 4:
                fixture.document["archive"]["sha256"] = "f" * 64
                fixture.pack()
        self.api_hook = drift
        self.assertEqual(fixture.drive().status, "unknown")
        self.assertEqual(self.api_calls, 4)
        self.assertNotIn(fixture.next_step, m.backend.calls)
        self.assertEqual(m.disk_state()["transitions"][-1]["status"], "intent")
        self.assertEqual(len(m.child.posts), 1)

    def test_artifact_change_before_http_is_refused_without_live_io(self):
        fixture = self.integrate(); m = fixture.managed
        document = fixture.effect._document
        calls = 0
        def changed(binding):
            nonlocal calls
            calls += 1
            if calls == 2:
                fixture.document["archive"]["sha256"] = "f" * 64
                fixture.pack()
            return document(binding)
        with patch.object(fixture.effect, "_document", side_effect=changed):
            self.assertEqual(fixture.drive().status, "unknown")
        self.assertEqual(self.calls, [])
        self.assertEqual(m.disk_state()["transitions"][-1]["status"], "intent")
        self.assertNotIn(fixture.next_step, m.backend.calls)
        self.assertEqual(len(m.child.posts), 1)

    def test_pending_recorded_run_does_not_start_live_verification(self):
        fixture = self.integrate(); m = fixture.managed
        m.child.fixture.run.update(status="in_progress", conclusion=None)
        result = fixture.drive()
        self.assertEqual((result.status, result.step), ("pending", fixture.step))
        self.assertEqual(self.calls, [])
        self.assertEqual(m.disk_state()["transitions"][-1]["status"], "intent")
        self.assertNotIn(fixture.next_step, m.backend.calls)
        self.assertEqual(len(m.child.posts), 1)


class CreatorManagedLiveTest(ManagedLiveTest):
    host = "creator"


if __name__ == "__main__": unittest.main()
