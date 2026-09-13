#!/usr/bin/env python3
"""Real HTTP/Netlify validators over routed loopback HTTP; no public TLS claim."""
import ast
import base64
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
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
        host_id, name = live_host.HOSTS[self.host]
        filename = ROOT / "apps" / host_id / "test/deployment_smoke_test.py"
        program = """import base64,json,runpy,sys
m=runpy.run_path(sys.argv[1]); f=m['SmokeFixture' if sys.argv[2]=='runtime' else 'Fixture']()
if sys.argv[2]=='runtime':
    f.payloads['/index.html']=f.payloads['/index.html'].replace(b'</head>',b'<meta name="lmdj-host-id" content="web-runtime-host"></head>')
    f.payloads['/']=f.payloads['/index.html']
print(json.dumps({'manifest':f.manifest,'payloads':{k:base64.b64encode(v).decode() for k,v in f.payloads.items()}}))
"""
        data = json.loads(subprocess.run([sys.executable, "-c", program, str(filename), self.host],
            check=True, capture_output=True, text=True, timeout=10).stdout)
        payloads = {k:base64.b64decode(v) for k,v in data["payloads"].items()}
        self.payloads = {kind:deepcopy(payloads) for kind in ("immutable", "production")}
        self.expected = {"site_id":"site-123", "deploy_id":"deploy-456",
            "product_build":data["manifest"]["product_build"], "host_version":data["manifest"]["host_version"],
            "index_sha256":hashlib.sha256(payloads["/index.html"]).hexdigest(),
            "manifest_sha256":hashlib.sha256(payloads["/host-manifest.json"]).hexdigest()}
        self.production = f"https://{name}.netlify.app"
        self.immutable = f"https://deploy-456--{name}.netlify.app"
        self.site = {"id":"site-123", "state":"current", "disabled":False, "ssl_url":self.production,
            "published_deploy":{"id":"deploy-456", "site_id":"site-123", "state":"ready", "deploy_ssl_url":self.immutable}}
        self.calls = []; self.api_calls = 0; self.api_hook = None; self.api_raw = None
        self.api_redirect = False; self.omit_header = None
        case = self

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
                    payload = case.api_raw if case.api_raw is not None else json.dumps(case.site).encode()
                    self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
                if kind not in case.payloads:
                    self.send_response(500); self.end_headers(); return
                payload = case.payloads[kind].get(route)
                self.send_response(404 if payload is None else 200)
                suffix = Path(route).suffix
                media = {".json":"application/json", ".mjs":"text/javascript", ".js":"text/javascript",
                         ".wasm":"application/wasm", ".css":"text/css"}.get(suffix, "text/html")
                self.send_header("Content-Type", "text/plain; charset=utf-8" if payload is None else media + ("" if media == "application/wasm" else "; charset=utf-8"))
                self.send_header("Cache-Control", "public, max-age=31536000, immutable" if payload is not None and route.startswith("/assets/") else "no-store")
                for key,value in {**live_host._smoke.REQUIRED_SECURITY_HEADERS, "content-security-policy":live_host._smoke.CSP}.items():
                    if key != case.omit_header: self.send_header(key, value)
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
                    if url.startswith(live_host.API_BASE + "/"):
                        kind, route = "api", url.removeprefix(live_host.API_BASE)
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
        for name in ("tools.release.live_host.build_opener", "tools.release.live_host._smoke.build_opener"):
            mocked = patch(name, side_effect=routed_opener); mocked.start(); self.addCleanup(mocked.stop)
        self.reader = live_host.SiteReader(token="fixture-secret")
        self.verifier = live_host.LiveHostVerifier(self.reader)

    def verify(self): return self.verifier.verify(self.host, self.expected)

    def test_fresh_reads_verify_both_urls_every_asset_and_current_pointer(self):
        first = self.verify(); calls = len(self.calls)
        self.assertEqual(self.verify(), first)
        self.assertEqual(len(self.calls), calls * 2); self.assertEqual(self.api_calls, 4)
        for kind in ("immutable", "production"):
            observed = {route for found,route,_ in self.calls if found == kind}
            self.assertTrue(set(self.payloads[kind]).issubset(observed))
            self.assertTrue(set(live_host._smoke.NEGATIVE_PATHS).issubset(observed))
        self.assertTrue(all(auth == ("Bearer fixture-secret" if kind == "api" else None) for kind,_,auth in self.calls))

    def test_wrong_pointer_refuses_before_http(self):
        self.site["published_deploy"]["id"] = "other-deploy"
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(len(self.calls), 1)

    def test_pointer_change_during_http_refuses(self):
        self.api_hook = lambda: self.site.update(disabled=True) if self.api_calls == 2 else None
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(self.api_calls, 2)
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
        self.api_raw = b'{"id":"fixture-secret",' + json.dumps(self.site).encode()[1:]
        with self.assertRaises(JournalError) as caught: self.verify()
        self.assertNotIn("fixture-secret", str(caught.exception))

    def test_inherited_mutation_routes_are_closed_without_http(self):
        for call in (lambda:self.reader.create_draft(site_id="site-123", files={"/index.html":b"fixture"}, title="fixture"),
                     lambda:self.reader.publish_deploy(site_id="site-123", deploy_id="deploy-456"),
                     lambda:self.reader.disable_site(site_id="site-123", reason="fixture"),
                     lambda:self.reader._json_request("POST", "/sites/site-123", {}, None)):
            with self.assertRaises(JournalError): call()
        self.assertEqual(self.calls, [])

    def test_invalid_frozen_site_is_rejected_without_network(self):
        self.expected["site_id"] = "../secrets"
        with self.assertRaises(JournalError): self.verify()
        self.assertEqual(self.calls, [])

    def test_oversized_api_response_is_refused(self):
        self.api_raw = b"x" * (1024 * 1024 + 1)
        with self.assertRaises(JournalError): self.verify()

    def test_host_url_policy_matches_canonical_producer(self):
        host_id, site_name = live_host.HOSTS[self.host]
        tree = ast.parse((ROOT / "apps" / host_id / "tools/deploy_orchestrator.py").read_text())
        values = {n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                  and n.targets[0].id in ("CANONICAL_PRODUCTION_URL", "CANONICAL_NETLIFY_SITE")}
        self.assertEqual(values, {"CANONICAL_PRODUCTION_URL":self.production, "CANONICAL_NETLIFY_SITE":site_name})


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
            for stage in ("immutable", "production"):
                fixture.document[stage]["http"]["result"][key] = self.expected[key]
            fixture.effect.expected["release_files"][key] = self.expected[key]
        fixture.effect.expected.update(product_build=self.expected["product_build"], host_version=self.expected["host_version"],
                                       archive=deepcopy(fixture.document["archive"]))
        fixture.effect.expected["prior"]["host_version"] = self.expected["host_version"]
        child = fixture.managed.child; f = child.fixture
        child.spec["inputs"]["tag"] = fixture.document["tag"]
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
        self.site["disabled"] = True
        result = m.new_driver().resume(m.request["id"])
        self.assertEqual((result.status, result.step), ("evidence-unknown", fixture.step))
        self.assertEqual(len(m.child.posts), 1)

    def test_live_failure_blocks_successor_without_redeployment(self):
        fixture = self.integrate(); m = fixture.managed
        self.site["disabled"] = True
        self.assertEqual(fixture.drive().status, "unknown")
        self.assertEqual(m.new_driver().resume(m.request["id"]).status, "unknown")
        self.assertNotIn(fixture.next_step, m.backend.calls)
        self.assertEqual(len(m.child.posts), 1)

    def test_retained_evidence_changed_during_live_checks_is_refused(self):
        fixture = self.integrate(); m = fixture.managed
        def drift():
            if self.api_calls == 2:
                fixture.document["archive"]["sha256"] = "f" * 64
                fixture.pack()
        self.api_hook = drift
        self.assertEqual(fixture.drive().status, "unknown")
        self.assertEqual(self.api_calls, 2)
        self.assertNotIn(fixture.next_step, m.backend.calls)
        self.assertEqual(len(m.child.posts), 1)


class CreatorManagedLiveTest(ManagedLiveTest):
    host = "creator"


if __name__ == "__main__": unittest.main()
