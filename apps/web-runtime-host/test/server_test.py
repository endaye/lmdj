#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_TOOL = REPO_ROOT / "apps/web-runtime-host/tools/server.py"
EXPECTED_CSP = (
    "default-src 'none'; base-uri 'none'; object-src 'none'; "
    "frame-ancestors 'none'; form-action 'none'; "
    "script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
    "child-src 'self' blob:; connect-src 'self'; style-src 'self'; "
    "img-src 'self'; media-src 'self' blob:; manifest-src 'self'"
)


def load_server_module():
    spec = importlib.util.spec_from_file_location("lmdj_web_server", SERVER_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError("server module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-web-server-")
        self.root = Path(self.temporary.name) / "dist"
        assets = self.root / "assets"
        assets.mkdir(parents=True)
        digest = "a" * 64
        self.js_path = assets / f"runtime.{digest}.js"
        self.wasm_path = assets / f"runtime.{digest}.wasm"
        self.js_path.write_text("export {};\n", encoding="utf-8", newline="\n")
        self.wasm_path.write_bytes(b"\x00asm\x01\x00\x00\x00")
        self.manifest_path = self.root / "host-manifest.json"
        self.manifest_path.write_text("{}", encoding="utf-8", newline="\n")
        self.index_path = self.root / "index.html"
        self.index_path.write_text(
            "<!doctype html><title>LMDJ</title>\n", encoding="utf-8", newline="\n"
        )
        module = load_server_module()
        self.server = module.make_server(self.root, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def request(
        self, method: str, path: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        body = response.read()
        result = (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            body,
        )
        connection.close()
        return result

    def test_exact_isolation_csp_mime_and_cache_headers(self) -> None:
        status, headers, _ = self.request("GET", "/index.html")
        self.assertEqual(status, 200)
        self.assertEqual(headers["cross-origin-opener-policy"], "same-origin")
        self.assertEqual(headers["cross-origin-embedder-policy"], "require-corp")
        self.assertEqual(headers["cross-origin-resource-policy"], "same-origin")
        self.assertEqual(headers["content-security-policy"], EXPECTED_CSP)
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(headers["content-type"], "text/html; charset=utf-8")

        status, headers, _ = self.request("GET", "/host-manifest.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")

        status, headers, payload = self.request(
            "GET", "/" + self.wasm_path.relative_to(self.root).as_posix()
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/wasm")
        self.assertEqual(
            headers["cache-control"], "public, max-age=31536000, immutable"
        )
        self.assertEqual(payload, self.wasm_path.read_bytes())

        status, headers, _ = self.request(
            "GET", "/" + self.js_path.relative_to(self.root).as_posix()
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/javascript; charset=utf-8")
        self.assertEqual(
            headers["cache-control"], "public, max-age=31536000, immutable"
        )

    def test_traversal_directory_range_and_unknown_methods_fail_closed(self) -> None:
        outside = Path(self.temporary.name) / "secret.js"
        outside.write_text("secret", encoding="utf-8")
        (self.root / "assets/escape.js").symlink_to(outside)
        for path in [
            "/assets/",
            "/%2e%2e/secret.js",
            "/assets/%2e%2e/host-manifest.json",
            "/assets/escape.js",
        ]:
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 404)
        status, _, _ = self.request(
            "GET",
            "/" + self.wasm_path.relative_to(self.root).as_posix(),
            {"Range": "bytes=0-1"},
        )
        self.assertEqual(status, 404)
        for method in ["POST", "PUT", "DELETE", "OPTIONS", "PATCH", "TRACE", "CONNECT", "BREW"]:
            with self.subTest(method=method):
                status, _, _ = self.request(method, "/index.html")
                self.assertEqual(status, 405)

    def test_head_has_headers_without_a_body(self) -> None:
        status, headers, body = self.request("HEAD", "/index.html")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(headers["content-security-policy"], EXPECTED_CSP)
        self.assertEqual(headers["cache-control"], "no-store")


if __name__ == "__main__":
    unittest.main()
