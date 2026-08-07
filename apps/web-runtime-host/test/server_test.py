#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_TOOL = REPO_ROOT / "apps/web-runtime-host/tools/server.py"
DEFAULT_DIST = Path(
    os.environ.get("LMDJ_WEB_HOST_DIST_ROOT", REPO_ROOT / "build/web/host/dist")
)
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
        shutil.copytree(DEFAULT_DIST, self.root)
        manifest = json.loads((self.root / "host-manifest.json").read_bytes())
        self.js_path = self.root / next(
            entry["path"] for entry in manifest["assets"]
            if entry["role"] == "runtime_script"
        )
        self.wasm_path = self.root / next(
            entry["path"] for entry in manifest["assets"]
            if entry["role"] == "runtime_wasm"
        )
        self.manifest_path = self.root / "host-manifest.json"
        self.index_path = self.root / "index.html"
        self.module = load_server_module()
        self.server = self.module.make_server(self.root, "127.0.0.1", 0)
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

    def test_host_wrapper_uses_the_shared_distribution_server(self) -> None:
        self.assertEqual(
            self.module.SHARED_SERVER.resolve(),
            (REPO_ROOT / "tools/web-runtime/serve_distribution.py").resolve(),
        )
        self.assertEqual(self.module.ProofHandler.__module__, "lmdj_shared_web_server")

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
        internal_alias = self.root / f"assets/alias.{'a' * 64}.js"
        internal_alias.symlink_to(self.js_path.name)
        for path in [
            "/assets/",
            "/%2e%2e/secret.js",
            "/assets/%2e%2e/host-manifest.json",
            "/assets/escape.js",
            "/" + internal_alias.relative_to(self.root).as_posix(),
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

    def test_invalid_or_symlink_distribution_root_is_rejected_before_bind(self) -> None:
        invalid = Path(self.temporary.name) / "invalid"
        shutil.copytree(DEFAULT_DIST, invalid)
        manifest_path = invalid / "host-manifest.json"
        old_bytes = manifest_path.read_bytes()
        manifest = json.loads(old_bytes)
        manifest["product_build"] = "999.0.0.0"
        new_bytes = json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        manifest_path.write_bytes(new_bytes)
        index_path = invalid / "index.html"
        index_path.write_text(
            index_path.read_text(encoding="utf-8").replace(
                hashlib.sha256(old_bytes).hexdigest(),
                hashlib.sha256(new_bytes).hexdigest(),
            ),
            encoding="utf-8",
            newline="\n",
        )
        with self.assertRaises(self.module.ServerError):
            self.module.make_server(invalid, "127.0.0.1", 0)

        alias = Path(self.temporary.name) / "dist-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(self.module.ServerError):
            self.module.make_server(alias, "127.0.0.1", 0)

    def test_file_swap_between_validation_and_open_never_serves_replacement(self) -> None:
        outside = Path(self.temporary.name) / "swap-secret.js"
        outside.write_text("secret replacement", encoding="utf-8")
        relative = self.js_path.relative_to(self.root).as_posix()
        original = self.js_path.with_name(self.js_path.name + ".original")
        real_open = os.open
        swapped = False

        def swap_before_leaf_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if (
                not swapped
                and kwargs.get("dir_fd") is not None
                and os.fspath(path) == self.js_path.name
            ):
                swapped = True
                self.js_path.rename(original)
                self.js_path.symlink_to(outside)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(
            self.module.os, "open", side_effect=swap_before_leaf_open
        ):
            self.assertIsNone(
                self.module.read_file_no_follow(self.root, relative)
            )
        self.assertTrue(swapped)

    def test_regular_file_replacement_after_bind_is_rejected_by_owned_inventory(self) -> None:
        self.js_path.write_text(
            "unverified replacement\n", encoding="utf-8", newline="\n"
        )
        status, _, payload = self.request(
            "GET", "/" + self.js_path.relative_to(self.root).as_posix()
        )
        self.assertEqual(status, 404)
        self.assertNotIn(b"unverified replacement", payload)

    def test_cli_ready_file_proves_the_new_server_pid_and_dynamic_port(self) -> None:
        ready_path = Path(self.temporary.name) / "ready.json"
        nonce = "test-owned-server"
        process = subprocess.Popen(
            [
                sys.executable,
                str(SERVER_TOOL),
                "--root",
                str(self.root),
                "--port",
                "0",
                "--ready-file",
                str(ready_path),
                "--ready-nonce",
                nonce,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            for _ in range(100):
                if ready_path.is_file() or process.poll() is not None:
                    break
                time.sleep(0.05)
            self.assertTrue(ready_path.is_file())
            ready = json.loads(ready_path.read_text(encoding="utf-8"))
            self.assertEqual(
                set(ready), {"host", "nonce", "pid", "port"}
            )
            self.assertEqual(ready["nonce"], nonce)
            self.assertEqual(ready["pid"], process.pid)
            self.assertEqual(ready["host"], "127.0.0.1")
            self.assertGreater(ready["port"], 0)
            connection = http.client.HTTPConnection(
                ready["host"], ready["port"], timeout=5
            )
            connection.request("GET", "/index.html")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            connection.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def test_head_has_headers_without_a_body(self) -> None:
        status, headers, body = self.request("HEAD", "/index.html")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(headers["content-security-policy"], EXPECTED_CSP)
        self.assertEqual(headers["cache-control"], "no-store")


if __name__ == "__main__":
    unittest.main()
