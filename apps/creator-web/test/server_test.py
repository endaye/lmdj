#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_TOOL = REPO_ROOT / "apps/creator-web/tools/package.py"
SERVER_TOOL = REPO_ROOT / "tools/web-runtime/serve_distribution.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module cannot be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CreatorServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-creator-server-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.ui = self.root / "ui"
        self.runtime = self.root / "runtime"
        self.identity = self.root / "toolchain-identity.json"
        self.dist = self.root / "dist"
        self.repo.joinpath("products/lmdj").mkdir(parents=True)
        self.repo.joinpath("tools/web-runtime").mkdir(parents=True)
        self.ui.joinpath("assets").mkdir(parents=True)
        self.runtime.mkdir()
        version = {
            "contract": "lmdj.product-version.v1",
            "product": "lmdj",
            "milestone": 1,
            "minor": 0,
            "build": 16,
            "patch": 0,
        }
        lock = json.loads(
            (REPO_ROOT / "tools/web-runtime/emscripten.lock.json").read_text(
                encoding="utf-8"
            )
        )
        self.repo.joinpath("products/lmdj/version.json").write_text(
            json.dumps(version), encoding="utf-8"
        )
        self.repo.joinpath("tools/web-runtime/emscripten.lock.json").write_text(
            json.dumps(lock), encoding="utf-8"
        )
        package = load_module("lmdj_creator_package_fixture", PACKAGE_TOOL)
        self.identity.write_text(
            json.dumps({**lock, "emcc_version": package.EMCC_VERSION}),
            encoding="utf-8",
        )
        self.ui.joinpath("index.html").write_text(
            '<!doctype html><html><head><meta charset="UTF-8" />'
            '<link rel="stylesheet" href="/assets/source.css"></head>'
            '<body><div id="root"></div>'
            '<script type="module" src="/assets/source.js"></script>'
            '</body></html>\n',
            encoding="utf-8",
            newline="\n",
        )
        self.ui.joinpath("assets/source.js").write_text(
            "console.log('creator');\n", encoding="utf-8", newline="\n"
        )
        self.ui.joinpath("assets/source.css").write_text(
            "body{margin:0}\n", encoding="utf-8", newline="\n"
        )
        self.runtime.joinpath("lmdj-web-runtime.js").write_text(
            'const wasm="lmdj-web-runtime.wasm";\n', encoding="utf-8", newline="\n"
        )
        self.runtime.joinpath("lmdj-web-runtime.wasm").write_bytes(b"\x00asmcreator")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.name", "Creator Test"],
            check=True,
        )
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-qm", "test fixture"],
            check=True,
        )
        package.build_distribution(
            self.repo, self.ui, self.runtime, self.identity, self.dist
        )
        self.verifier = load_module("lmdj_creator_package_verifier", PACKAGE_TOOL)
        self.module = load_module("lmdj_shared_web_server_test", SERVER_TOOL)
        manifest = json.loads(self.dist.joinpath("host-manifest.json").read_bytes())
        self.js_path = self.dist / next(
            entry["path"] for entry in manifest["assets"]
            if entry["role"] == "runtime_script"
        )
        self.wasm_path = self.dist / next(
            entry["path"] for entry in manifest["assets"]
            if entry["role"] == "runtime_wasm"
        )
        self.server = self.module.make_server(
            self.dist, self.verifier, self.repo, "127.0.0.1", 0
        )
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
        result = (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            response.read(),
        )
        connection.close()
        return result

    def test_creator_distribution_has_exact_security_mime_and_cache_headers(self) -> None:
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["cross-origin-opener-policy"], "same-origin")
        self.assertEqual(headers["cross-origin-embedder-policy"], "require-corp")
        self.assertEqual(headers["cross-origin-resource-policy"], "same-origin")
        self.assertEqual(headers["content-security-policy"], self.module.CSP)
        self.assertEqual(headers["cache-control"], "no-store")

        status, headers, payload = self.request(
            "GET", "/" + self.wasm_path.relative_to(self.dist).as_posix()
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/wasm")
        self.assertEqual(
            headers["cache-control"], "public, max-age=31536000, immutable"
        )
        self.assertEqual(payload, self.wasm_path.read_bytes())

    def test_unowned_traversal_symlink_range_and_methods_fail_closed(self) -> None:
        outside = self.root / "secret.js"
        outside.write_text("secret", encoding="utf-8")
        alias = self.dist / f"assets/alias.{'a' * 64}.js"
        alias.symlink_to(outside)
        for path in [
            "/favicon.ico",
            "/assets/",
            "/%2e%2e/secret.js",
            "/assets/%2e%2e/host-manifest.json",
            "/" + alias.relative_to(self.dist).as_posix(),
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(
            self.request(
                "GET",
                "/" + self.wasm_path.relative_to(self.dist).as_posix(),
                {"Range": "bytes=0-1"},
            )[0],
            404,
        )
        for method in ["POST", "PUT", "DELETE", "OPTIONS", "PATCH", "TRACE"]:
            with self.subTest(method=method):
                self.assertEqual(self.request(method, "/index.html")[0], 405)

    def test_tampered_asset_and_non_loopback_bind_are_rejected(self) -> None:
        self.js_path.write_text("replacement\n", encoding="utf-8", newline="\n")
        status, _, body = self.request(
            "GET", "/" + self.js_path.relative_to(self.dist).as_posix()
        )
        self.assertEqual(status, 404)
        self.assertNotIn(b"replacement", body)
        with self.assertRaisesRegex(self.module.ServerError, "loopback-only"):
            self.module.make_server(
                self.dist, self.verifier, self.repo, "0.0.0.0", 0
            )


if __name__ == "__main__":
    unittest.main()
