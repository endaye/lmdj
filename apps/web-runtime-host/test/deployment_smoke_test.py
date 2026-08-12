#!/usr/bin/env python3

from __future__ import annotations

import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import unittest
from urllib.request import Request


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_ROOT = REPO_ROOT / "apps/web-runtime-host/tools"
sys.path.insert(0, str(TOOLS_ROOT))

from deployment_smoke import (  # noqa: E402
    CSP,
    REQUIRED_SECURITY_HEADERS,
    RedirectGuard,
    SmokeError,
    smoke_http,
)


ASSET_LAYOUT = (
    ("diagnostic-client", ".mjs", "platform_module"),
    ("diagnostic-project", ".mjs", "host_module"),
    ("input-adapters", ".mjs", "platform_module"),
    ("main", ".mjs", "host_main"),
    ("preflight", ".mjs", "platform_module"),
    ("project-bundle-reader", ".mjs", "platform_module"),
    ("protocol", ".mjs", "platform_module"),
    ("runtime", ".js", "runtime_script"),
    ("runtime", ".wasm", "runtime_wasm"),
    ("runtime-loader", ".mjs", "platform_module"),
    ("runtime-session", ".mjs", "platform_module"),
    ("state-machine", ".mjs", "platform_module"),
    ("styles", ".css", "host_style"),
)
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".wasm": "application/wasm",
}


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def scrubbed_python_environment() -> dict[str, str]:
    environment = {"LANG": "C.UTF-8", "PATH": os.defpath}
    for name in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


class SmokeFixture:
    def __init__(self) -> None:
        self.omit_header: str | None = None
        self.redirect_omit_header: str | None = None
        self.redirect_duplicate_header: tuple[str, str] | None = None
        self.negative_duplicate_header: tuple[str, str] | None = None
        self.duplicate_header: tuple[str, str] | None = None
        self.header_overrides: dict[str, str] = {}
        self.content_type_overrides: dict[str, str] = {}
        self.cache_overrides: dict[str, str | None] = {}
        self.redirects: dict[str, str] = {}
        self.redirect_cache_overrides: dict[str, str | None] = {}
        self.delays: dict[str, float] = {}
        self.edge_rejections: dict[str, tuple[HTTPStatus, bytes]] = {}
        self.forced_ok: set[str] = set()
        self.payloads: dict[str, bytes] = {}
        assets = []
        for stem, suffix, role in ASSET_LAYOUT:
            payload = f"fixture:{stem}{suffix}\n".encode()
            digest = hashlib.sha256(payload).hexdigest()
            path = f"assets/{stem}.{digest}{suffix}"
            self.payloads[f"/{path}"] = payload
            assets.append(
                {
                    "bytes": len(payload),
                    "path": path,
                    "role": role,
                    "sha256": digest,
                }
            )
        self.manifest = {
            "assets": assets,
            "distribution_contract": "lmdj.web-runtime-host.distribution.v1",
            "emscripten": {},
            "heap_bytes": 536_870_912,
            "host_id": "lmdj-web-runtime-host",
            "host_version": "1.1.2",
            "manifest_version": 1,
            "platform_version": "0.1.5",
            "product_build": "1.0.15.2",
            "protocol_version": 1,
            "resource_limits": {},
        }
        self.update_manifest(update_index=True)

    def update_manifest(self, *, update_index: bool) -> None:
        manifest_bytes = canonical_json(self.manifest)
        self.payloads["/host-manifest.json"] = manifest_bytes
        if not update_index and "/index.html" in self.payloads:
            return
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        main = next(
            entry for entry in self.manifest["assets"]
            if entry["role"] == "host_main"
        )
        style = next(
            entry for entry in self.manifest["assets"]
            if entry["role"] == "host_style"
        )
        self.payloads["/index.html"] = (
            "<!doctype html><html><head>"
            f'<meta name="lmdj-host-manifest-sha256" content="{digest}">'
            '<meta name="lmdj-host-manifest-path" content="./host-manifest.json">'
            '<meta name="lmdj-product-build" content="1.0.15.2">'
            '<meta name="lmdj-host-version" content="1.1.2">'
            f'<link rel="stylesheet" href="./{style["path"]}">'
            f'<script type="module" src="./{main["path"]}"></script>'
            "</head><body></body></html>"
        ).encode()
        self.payloads["/"] = self.payloads["/index.html"]

    def security_headers(self) -> dict[str, str]:
        headers = {
            **REQUIRED_SECURITY_HEADERS,
            "content-security-policy": CSP,
        }
        headers.update(self.header_overrides)
        if self.omit_header is not None:
            headers.pop(self.omit_header, None)
        return headers


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, fixture: SmokeFixture) -> None:
        self.fixture = fixture
        super().__init__(("127.0.0.1", 0), FixtureHandler)

    @property
    def base_url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"


class FixtureHandler(BaseHTTPRequestHandler):
    server: FixtureServer

    def log_message(self, format: str, *args) -> None:
        pass

    def _headers(self, *, redirect: bool = False) -> None:
        headers = self.server.fixture.security_headers()
        if redirect and self.server.fixture.redirect_omit_header is not None:
            headers.pop(self.server.fixture.redirect_omit_header, None)
        for name, value in headers.items():
            self.send_header(name, value)
        if self.server.fixture.duplicate_header is not None:
            self.send_header(*self.server.fixture.duplicate_header)

    def do_GET(self) -> None:
        fixture = self.server.fixture
        if self.path in fixture.delays:
            time.sleep(fixture.delays[self.path])
        if self.path in fixture.edge_rejections:
            status, payload = fixture.edge_rejections[self.path]
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path in fixture.redirects:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", fixture.redirects[self.path])
            redirect_cache = fixture.redirect_cache_overrides.get(
                self.path,
                "public, max-age=31536000, immutable"
                if self.path.startswith("/assets/") else "no-store",
            )
            if redirect_cache is not None:
                self.send_header("Cache-Control", redirect_cache)
            self._headers(redirect=True)
            if fixture.redirect_duplicate_header is not None:
                self.send_header(*fixture.redirect_duplicate_header)
            self.end_headers()
            return
        payload = fixture.payloads.get(self.path)
        forced = payload is None and self.path in fixture.forced_ok
        if forced:
            payload = fixture.payloads["/index.html"]
        if payload is None:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            negative_cache = fixture.cache_overrides.get(self.path, "no-store")
            if negative_cache is not None:
                self.send_header("Cache-Control", negative_cache)
            self._headers()
            if fixture.negative_duplicate_header is not None:
                self.send_header(*fixture.negative_duplicate_header)
            self.end_headers()
            return
        self.send_response(HTTPStatus.OK)
        suffix = Path(self.path).suffix
        content_type = fixture.content_type_overrides.get(
            self.path,
            "text/html; charset=utf-8"
            if forced or self.path in {"/", "/index.html"}
            else CONTENT_TYPES[suffix],
        )
        cache = fixture.cache_overrides.get(
            self.path,
            "no-store"
            if forced or self.path in {"/", "/index.html", "/host-manifest.json"}
            else "public, max-age=31536000, immutable",
        )
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(payload)))
        self._headers()
        self.end_headers()
        try:
            self.wfile.write(payload)
        except BrokenPipeError:
            pass


class DeploymentSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = SmokeFixture()
        self.server = FixtureServer(self.fixture)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def smoke(self) -> dict[str, object]:
        return smoke_http(
            base_url=self.server.base_url,
            expected_product_build="1.0.15.2",
            expected_host_version="1.1.2",
            require_https=False,
        )

    def test_accepts_exact_host_identity_headers_mime_cache_and_negative_routes(self) -> None:
        result = self.smoke()
        self.assertEqual(
            result,
            {
                "asset_count": 13,
                "host_version": "1.1.2",
                "index_sha256": hashlib.sha256(
                    self.fixture.payloads["/index.html"]
                ).hexdigest(),
                "manifest_sha256": hashlib.sha256(
                    self.fixture.payloads["/host-manifest.json"]
                ).hexdigest(),
                "product_build": "1.0.15.2",
                "root_final_path": "/",
                "root_redirect_count": 0,
                "root_request_path": "/",
            },
        )

    def test_starts_at_root_and_allows_only_a_secure_no_store_redirect_to_index(self) -> None:
        self.fixture.redirects["/"] = "/index.html"
        result = self.smoke()
        self.assertEqual(result["root_request_path"], "/")
        self.assertEqual(result["root_final_path"], "/index.html")
        self.assertEqual(result["root_redirect_count"], 1)

        for location in (
            "/redirected-index.html",
            "/index.html?unexpected=query",
            f"http://localhost:{self.server.server_address[1]}/index.html",
        ):
            with self.subTest(location=location):
                self.fixture.redirects["/"] = location
                with self.assertRaisesRegex(SmokeError, "redirect"):
                    self.smoke()

    def test_rejects_root_index_identity_that_differs_from_direct_index(self) -> None:
        self.fixture.payloads["/"] = b"different root index"
        with self.assertRaisesRegex(SmokeError, "root index identity"):
            self.smoke()

    def test_rejects_missing_cross_origin_or_noindex_header(self) -> None:
        for header in REQUIRED_SECURITY_HEADERS:
            with self.subTest(header=header):
                self.fixture.omit_header = header
                with self.assertRaisesRegex(SmokeError, re.escape(header)):
                    self.smoke()
                self.fixture.omit_header = None

    def test_rejects_wrong_or_missing_csp(self) -> None:
        for value in ("default-src 'self'", None):
            with self.subTest(value=value):
                if value is None:
                    self.fixture.omit_header = "content-security-policy"
                else:
                    self.fixture.header_overrides["content-security-policy"] = value
                with self.assertRaisesRegex(SmokeError, "content-security-policy"):
                    self.smoke()
                self.fixture.omit_header = None
                self.fixture.header_overrides.clear()

    def test_accepts_redundant_netlify_draft_noindex_header(self) -> None:
        self.fixture.duplicate_header = ("X-Robots-Tag", "noindex")
        self.assertEqual(self.smoke()["asset_count"], 13)

    def test_rejects_duplicate_security_header_values(self) -> None:
        self.fixture.duplicate_header = ("X-Robots-Tag", "index, follow")
        with self.assertRaisesRegex(SmokeError, "x-robots-tag"):
            self.smoke()

    def test_rejects_wrong_wasm_mime_or_asset_cache(self) -> None:
        wasm = next(
            "/" + entry["path"] for entry in self.fixture.manifest["assets"]
            if entry["role"] == "runtime_wasm"
        )
        main = next(
            "/" + entry["path"] for entry in self.fixture.manifest["assets"]
            if entry["role"] == "host_main"
        )
        self.fixture.content_type_overrides[wasm] = "application/octet-stream"
        with self.assertRaisesRegex(SmokeError, "content-type"):
            self.smoke()
        self.fixture.content_type_overrides.clear()
        self.fixture.cache_overrides[main] = "no-cache"
        with self.assertRaisesRegex(SmokeError, "cache-control"):
            self.smoke()

    def test_accepts_standard_equivalent_content_types(self) -> None:
        main = next(
            "/" + entry["path"] for entry in self.fixture.manifest["assets"]
            if entry["role"] == "host_main"
        )
        self.fixture.content_type_overrides["/index.html"] = (
            'Text/HTML; Charset="UTF-8"'
        )
        self.fixture.content_type_overrides["/host-manifest.json"] = (
            "Application/JSON"
        )
        self.fixture.content_type_overrides[main] = (
            "APPLICATION/JAVASCRIPT; CHARSET=UTF8"
        )
        self.assertEqual(self.smoke()["asset_count"], 13)

    def test_accepts_cache_control_with_optional_whitespace(self) -> None:
        main = next(
            "/" + entry["path"] for entry in self.fixture.manifest["assets"]
            if entry["role"] == "host_main"
        )
        self.fixture.cache_overrides[main] = (
            "public,max-age=31536000,immutable"
        )
        self.assertEqual(self.smoke()["asset_count"], 13)

    def test_rejects_wrong_or_malformed_content_types(self) -> None:
        wasm = next(
            "/" + entry["path"] for entry in self.fixture.manifest["assets"]
            if entry["role"] == "runtime_wasm"
        )
        cases = (
            ("/index.html", "application/octet-stream"),
            ("/index.html", "text/html; charset=latin-1"),
            ("/index.html", "text/html; charset"),
            ("/index.html", "text/html; charset=utf-8; boundary=x"),
            (wasm, "application/wasm; charset=utf-8"),
        )
        for path, value in cases:
            with self.subTest(path=path, value=value):
                self.fixture.content_type_overrides[path] = value
                with self.assertRaisesRegex(SmokeError, "content-type"):
                    self.smoke()
                self.fixture.content_type_overrides.clear()

        self.fixture.duplicate_header = (
            "Content-Type", "text/html; charset=utf-8"
        )
        with self.assertRaisesRegex(SmokeError, "content-type"):
            self.smoke()

    def test_rejects_manifest_digest_identity_or_asset_mismatch(self) -> None:
        self.fixture.manifest["resource_limits"] = {"changed": True}
        self.fixture.update_manifest(update_index=False)
        with self.assertRaisesRegex(SmokeError, "manifest digest"):
            self.smoke()

        self.fixture.update_manifest(update_index=True)
        asset = self.fixture.manifest["assets"][0]
        asset_path = "/" + asset["path"]
        payload = bytearray(self.fixture.payloads[asset_path])
        payload[0] ^= 1
        self.fixture.payloads[asset_path] = bytes(payload)
        with self.assertRaisesRegex(SmokeError, "^asset digest mismatch:"):
            self.smoke()

    def test_rejects_wrong_product_or_host_identity(self) -> None:
        for key, message in (
            ("product_build", "Product Build"),
            ("host_version", "Host version"),
        ):
            with self.subTest(key=key):
                original = self.fixture.manifest[key]
                self.fixture.manifest[key] = "wrong"
                self.fixture.update_manifest(update_index=True)
                with self.assertRaisesRegex(SmokeError, message):
                    self.smoke()
                self.fixture.manifest[key] = original
                self.fixture.update_manifest(update_index=True)

    def test_rejects_incomplete_or_unbounded_manifest_inventory(self) -> None:
        removed_index = next(
            index
            for index, entry in enumerate(self.fixture.manifest["assets"])
            if entry["role"] == "runtime_wasm"
        )
        removed = self.fixture.manifest["assets"].pop(removed_index)
        self.fixture.update_manifest(update_index=True)
        with self.assertRaisesRegex(SmokeError, "inventory"):
            self.smoke()
        self.fixture.manifest["assets"].insert(removed_index, removed)
        self.fixture.manifest["assets"][0]["bytes"] = 100_000_000
        self.fixture.update_manifest(update_index=True)
        with self.assertRaisesRegex(SmokeError, "asset bytes"):
            self.smoke()

    def test_rejects_raw_source_unknown_source_map_or_traversal_200(self) -> None:
        for path in (
            "/src/main.mjs",
            "/missing",
            "/assets/missing.map",
            "/%2e%2e/index.html",
        ):
            with self.subTest(path=path):
                self.fixture.forced_ok.add(path)
                with self.assertRaisesRegex(SmokeError, re.escape(path)):
                    self.smoke()
                self.fixture.forced_ok.clear()

    def test_accepts_empty_netlify_edge_traversal_rejection(self) -> None:
        self.fixture.edge_rejections["/%2e%2e/index.html"] = (
            HTTPStatus.BAD_REQUEST,
            b"",
        )
        self.assertEqual(self.smoke()["asset_count"], 13)

    def test_rejects_wrong_or_nonempty_edge_traversal_rejection(self) -> None:
        for status, payload in (
            (HTTPStatus.NOT_FOUND, b""),
            (HTTPStatus.BAD_REQUEST, b"product response"),
        ):
            with self.subTest(status=status, payload=payload):
                self.fixture.edge_rejections["/%2e%2e/index.html"] = (
                    status,
                    payload,
                )
                with self.assertRaisesRegex(SmokeError, "/%2e%2e/index.html"):
                    self.smoke()

    def test_rejects_missing_wrong_or_duplicate_negative_route_cache(self) -> None:
        for observed in (None, "public, max-age=31536000, immutable"):
            with self.subTest(observed=observed):
                self.fixture.cache_overrides["/missing"] = observed
                with self.assertRaisesRegex(SmokeError, "cache-control"):
                    self.smoke()
        self.fixture.cache_overrides.clear()
        self.fixture.negative_duplicate_header = (
            "Cache-Control", "public, max-age=0"
        )
        with self.assertRaisesRegex(SmokeError, "cache-control"):
            self.smoke()

    def test_rejects_http_base_url_when_https_is_required(self) -> None:
        with self.assertRaisesRegex(SmokeError, "HTTPS"):
            smoke_http(
                base_url=self.server.base_url,
                expected_product_build="1.0.15.2",
                expected_host_version="1.1.2",
            )

    def test_cleartext_override_accepts_only_validated_loopback_targets(self) -> None:
        localhost_url = self.server.base_url.replace("127.0.0.1", "localhost")
        self.assertEqual(
            smoke_http(
                base_url=localhost_url,
                expected_product_build="1.0.15.2",
                expected_host_version="1.1.2",
                require_https=False,
            )["asset_count"],
            13,
        )
        with self.assertRaisesRegex(SmokeError, "request failed"):
            smoke_http(
                base_url="http://[::1]:1",
                expected_product_build="1.0.15.2",
                expected_host_version="1.1.2",
                require_https=False,
                timeout_seconds=0.01,
            )
        with self.assertRaisesRegex(SmokeError, "cleartext.*loopback"):
            smoke_http(
                base_url="http://192.0.2.1:9",
                expected_product_build="1.0.15.2",
                expected_host_version="1.1.2",
                require_https=False,
                timeout_seconds=0.01,
            )

    def test_applies_the_bounded_timeout_to_each_request(self) -> None:
        self.fixture.delays["/index.html"] = 0.1
        with self.assertRaisesRegex(SmokeError, "request failed"):
            smoke_http(
                base_url=self.server.base_url,
                expected_product_build="1.0.15.2",
                expected_host_version="1.1.2",
                require_https=False,
                timeout_seconds=0.01,
            )

    def test_rejects_redirect_to_different_origin(self) -> None:
        _, port = self.server.server_address
        self.fixture.redirects["/index.html"] = (
            f"http://localhost:{port}/host-manifest.json"
        )
        with self.assertRaisesRegex(SmokeError, "cross-origin redirect"):
            self.smoke()

    def test_rejects_same_origin_redirect_without_security_headers(self) -> None:
        redirected = "/redirected-index.html"
        self.fixture.payloads[redirected] = self.fixture.payloads["/index.html"]
        self.fixture.cache_overrides[redirected] = "no-store"
        self.fixture.redirects["/index.html"] = redirected
        self.fixture.redirect_omit_header = "x-robots-tag"
        with self.assertRaisesRegex(SmokeError, "x-robots-tag"):
            self.smoke()

    def test_rejects_missing_wrong_or_duplicate_redirect_cache(self) -> None:
        redirected = "/redirected-index.html"
        self.fixture.payloads[redirected] = self.fixture.payloads["/index.html"]
        self.fixture.cache_overrides[redirected] = "no-store"
        self.fixture.redirects["/index.html"] = redirected
        for observed in (None, "public, max-age=31536000, immutable"):
            with self.subTest(observed=observed):
                self.fixture.redirect_cache_overrides["/index.html"] = observed
                with self.assertRaisesRegex(SmokeError, "cache-control"):
                    self.smoke()
        self.fixture.redirect_cache_overrides.clear()
        self.fixture.redirect_duplicate_header = ("Cache-Control", "no-cache")
        with self.assertRaisesRegex(SmokeError, "cache-control"):
            self.smoke()

    def test_asset_redirect_requires_immutable_cache_for_original_route(self) -> None:
        asset_path = next(
            "/" + entry["path"] for entry in self.fixture.manifest["assets"]
            if entry["role"] == "host_main"
        )
        redirected = "/mirror" + asset_path
        self.fixture.payloads[redirected] = self.fixture.payloads[asset_path]
        self.fixture.cache_overrides[redirected] = (
            "public, max-age=31536000, immutable"
        )
        self.fixture.redirects[asset_path] = redirected
        self.fixture.redirect_cache_overrides[asset_path] = "no-store"
        with self.assertRaisesRegex(SmokeError, "cache-control"):
            self.smoke()

    def test_rejects_https_to_http_redirect(self) -> None:
        guard = RedirectGuard()
        request = Request("https://runtime.example/index.html")
        with self.assertRaisesRegex(SmokeError, "HTTPS downgrade"):
            guard.redirect_request(
                request,
                None,
                HTTPStatus.FOUND,
                "Found",
                {},
                "http://runtime.example/index.html",
            )

    def test_discover_identity_cli_extracts_the_actual_manifest_identity_in_a_scrubbed_environment(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS_ROOT / "deployment_smoke.py"),
                "discover-identity",
                self.server.base_url,
                "--allow-http",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=scrubbed_python_environment(),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            json.dumps(
                {
                    "host_version": "1.1.2",
                    "manifest_sha256": hashlib.sha256(
                        self.fixture.payloads["/host-manifest.json"]
                    ).hexdigest(),
                    "product_build": "1.0.15.2",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
        )
        self.assertEqual(completed.stderr, "")

    def test_discover_identity_cli_rejects_a_manifest_without_actual_identity(self) -> None:
        self.fixture.manifest["product_build"] = ""
        self.fixture.update_manifest(update_index=True)
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS_ROOT / "deployment_smoke.py"),
                "discover-identity",
                self.server.base_url,
                "--allow-http",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=scrubbed_python_environment(),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("Product Build identity is invalid", completed.stderr)

    def test_cli_prints_only_sorted_compact_json_after_success(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS_ROOT / "deployment_smoke.py"),
                self.server.base_url,
                "1.0.15.2",
                "1.1.2",
                "--allow-http",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            json.dumps(
                {
                    "asset_count": 13,
                    "host_version": "1.1.2",
                    "index_sha256": hashlib.sha256(
                        self.fixture.payloads["/index.html"]
                    ).hexdigest(),
                    "manifest_sha256": hashlib.sha256(
                        self.fixture.payloads["/host-manifest.json"]
                    ).hexdigest(),
                    "product_build": "1.0.15.2",
                    "root_final_path": "/",
                    "root_redirect_count": 0,
                    "root_request_path": "/",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
        )
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
