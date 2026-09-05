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
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_ROOT = REPO_ROOT / "apps/creator-web/tools"
sys.path.insert(0, str(TOOLS_ROOT))

from deployment_smoke import (  # noqa: E402
    CSP,
    REQUIRED_SECURITY_HEADERS,
    SmokeError,
    smoke,
)


ASSETS = (
    ("main", ".js", "host_main"),
    ("runtime", ".js", "runtime_script"),
    ("runtime", ".wasm", "runtime_wasm"),
    ("styles", ".css", "host_style"),
    ("capture-worklet", ".js", "capture_worklet"),
    ("perform-master-tap", ".js", "perform_master_tap_worklet"),
)
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".wasm": "application/wasm",
}


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class Fixture:
    def __init__(self) -> None:
        self.omit_header: str | None = None
        self.cache_overrides: dict[str, str] = {}
        self.forced_ok: set[str] = set()
        self.payloads: dict[str, bytes] = {}
        entries = []
        for stem, suffix, role in ASSETS:
            payload = f"creator:{stem}{suffix}\n".encode()
            digest = hashlib.sha256(payload).hexdigest()
            path = f"assets/{stem}.{digest}{suffix}"
            self.payloads[f"/{path}"] = payload
            entries.append(
                {"bytes": len(payload), "path": path, "role": role, "sha256": digest}
            )
        self.manifest = {
            "assets": entries,
            "compatible_hosts": [
                {"host_id": "web-runtime-host", "host_version": "3.0.0"}
            ],
            "distribution_contract": "lmdj.creator-web.distribution.v1",
            "emscripten": {},
            "heap_bytes": 536_870_912,
            "host_id": "creator-web",
            "host_version": "3.0.0",
            "manifest_version": 1,
            "platform_version": "0.3.6",
            "product_build": "1.0.41.0",
            "protocol_version": 1,
            "resource_limits": {},
        }
        self.update()

    def update(self, *, update_index: bool = True) -> None:
        manifest = canonical_json(self.manifest)
        self.payloads["/host-manifest.json"] = manifest
        if not update_index and "/index.html" in self.payloads:
            return
        digest = hashlib.sha256(manifest).hexdigest()
        main = next(entry for entry in self.manifest["assets"] if entry["role"] == "host_main")
        style = next(entry for entry in self.manifest["assets"] if entry["role"] == "host_style")
        index = (
            "<!doctype html><html><head>"
            f'<meta name="lmdj-host-manifest-sha256" content="{digest}">'
            '<meta name="lmdj-host-manifest-path" content="./host-manifest.json">'
            '<meta name="lmdj-product-build" content="1.0.41.0">'
            '<meta name="lmdj-host-id" content="creator-web">'
            '<meta name="lmdj-host-version" content="3.0.0">'
            f'<link rel="stylesheet" href="./{style["path"]}">'
            f'<script type="module" src="./{main["path"]}"></script>'
            "</head><body>Creator</body></html>"
        ).encode()
        self.payloads["/index.html"] = index
        self.payloads["/"] = index

    def headers(self) -> dict[str, str]:
        headers = {**REQUIRED_SECURITY_HEADERS, "content-security-policy": CSP}
        if self.omit_header is not None:
            headers.pop(self.omit_header, None)
        return headers


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, fixture: Fixture) -> None:
        self.fixture = fixture
        super().__init__(("127.0.0.1", 0), Handler)

    @property
    def base_url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        fixture = self.server.fixture
        payload = fixture.payloads.get(self.path)
        if payload is None and self.path in fixture.forced_ok:
            payload = fixture.payloads["/index.html"]
        status = HTTPStatus.OK if payload is not None else HTTPStatus.NOT_FOUND
        self.send_response(status)
        suffix = Path(self.path).suffix
        content_type = (
            "text/html; charset=utf-8"
            if payload is not None and self.path in {"/", "/index.html"}
            else CONTENT_TYPES.get(suffix, "text/plain; charset=utf-8")
        )
        self.send_header("Content-Type", content_type)
        cache = fixture.cache_overrides.get(
            self.path,
            "no-store"
            if status != HTTPStatus.OK or self.path in {"/", "/index.html", "/host-manifest.json"}
            else "public, max-age=31536000, immutable",
        )
        self.send_header("Cache-Control", cache)
        if payload is not None:
            self.send_header("Content-Length", str(len(payload)))
        for name, value in fixture.headers().items():
            self.send_header(name, value)
        self.end_headers()
        if payload is not None:
            self.wfile.write(payload)


class CreatorDeploymentSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()
        self.server = Server(self.fixture)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def run_smoke(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "base_url": self.server.base_url,
            "expected_product": "1.0.41.0",
            "expected_host": "3.0.0",
            "expected_host_id": "creator-web",
            "require_https": False,
        }
        arguments.update(overrides)
        return smoke(**arguments)

    def test_accepts_exact_creator_identity_inventory_and_privacy_allowlist(self) -> None:
        result = self.run_smoke()
        self.assertEqual(result["host_id"], "creator-web")
        self.assertEqual(result["product_build"], "1.0.41.0")
        self.assertEqual(result["host_version"], "3.0.0")
        self.assertEqual(result["asset_count"], 6)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["url"], self.server.base_url + "/")
        self.assertEqual(
            set(result),
            {
                "asset_count", "completed_at", "host_id", "host_version",
                "index_sha256", "manifest_sha256", "product_build",
                "started_at", "status", "url",
            },
        )

    def test_rejects_missing_security_headers_and_csp(self) -> None:
        for header in (*REQUIRED_SECURITY_HEADERS, "content-security-policy"):
            with self.subTest(header=header):
                self.fixture.omit_header = header
                with self.assertRaisesRegex(SmokeError, re.escape(header)):
                    self.run_smoke()
                self.fixture.omit_header = None

    def test_rejects_bad_asset_cache_source_maps_and_retired_markers(self) -> None:
        main = next(
            "/" + entry["path"]
            for entry in self.fixture.manifest["assets"]
            if entry["role"] == "host_main"
        )
        self.fixture.cache_overrides[main] = "no-store"
        with self.assertRaisesRegex(SmokeError, "cache-control"):
            self.run_smoke()
        self.fixture.cache_overrides.clear()
        self.fixture.forced_ok.add("/assets/missing.map")
        with self.assertRaisesRegex(SmokeError, "missing.map"):
            self.run_smoke()
        self.fixture.forced_ok.clear()
        self.fixture.payloads[main] += b"lmdj.patch.v1"
        asset = next(entry for entry in self.fixture.manifest["assets"] if "/" + entry["path"] == main)
        asset["bytes"] = len(self.fixture.payloads[main])
        asset["sha256"] = hashlib.sha256(self.fixture.payloads[main]).hexdigest()
        old_path = asset["path"]
        asset["path"] = f"assets/main.{asset['sha256']}.js"
        self.fixture.payloads["/" + asset["path"]] = self.fixture.payloads.pop("/" + old_path)
        self.fixture.update()
        with self.assertRaisesRegex(SmokeError, "retired"):
            self.run_smoke()

    def test_rejects_wrong_identity_contract_hostname_and_deploy_id(self) -> None:
        for key, value, message in (
            ("host_id", "web-runtime-host", "Host ID"),
            ("product_build", "1.0.40.0", "Product Build"),
            ("distribution_contract", "wrong", "distribution"),
        ):
            with self.subTest(key=key):
                original = self.fixture.manifest[key]
                self.fixture.manifest[key] = value
                self.fixture.update()
                with self.assertRaisesRegex(SmokeError, message):
                    self.run_smoke()
                self.fixture.manifest[key] = original
                self.fixture.update()
        with self.assertRaisesRegex(SmokeError, "Deploy ID"):
            self.run_smoke(expected_deploy_id="creator-deploy-1")
        with self.assertRaisesRegex(SmokeError, "loopback"):
            smoke(
                base_url="http://creator.example/",
                expected_product="1.0.41.0",
                expected_host="3.0.0",
                expected_host_id="creator-web",
                require_https=False,
            )

    def test_cli_scrubs_credentials_and_prints_only_canonical_json(self) -> None:
        environment = os.environ.copy()
        environment.update(
            {
                "GITHUB_TOKEN": "github-secret",
                "NETLIFY_AUTH_TOKEN": "netlify-secret",
                "NETLIFY_CREATOR_SITE_ID": "site-secret",
            }
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS_ROOT / "deployment_smoke.py"),
                self.server.base_url,
                "1.0.41.0",
                "3.0.0",
                "--allow-http",
            ],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, completed.stdout.strip() + "\n")
        result = json.loads(completed.stdout)
        self.assertEqual(result["host_id"], "creator-web")
        self.assertNotIn("secret", completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
