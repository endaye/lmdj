#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import http.client
import http.server
import importlib.util
import json
import os
import random
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_TOOL = REPO_ROOT / "apps/creator-web/tools/package.py"
SERVER_TOOL = REPO_ROOT / "tools/web-runtime/serve_distribution.py"
SAMPLE_EDITOR_MARKERS = (
    "Sample editor",
    "Replace Sample",
    "Reset Pad to Defaults",
    "Retry Prepare",
    "Accepted format: PCM16 WAV, mono or stereo, 44.1 or 48 kHz",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module cannot be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CreatorServerTest(unittest.TestCase):
    # A Creator deployment that offers no Catalog, which is every one today.
    # `CreatorCatalogProxyTest` re-runs this whole suite with one configured, so
    # the static surface and the CSP are asserted unchanged either way.
    catalog_upstream: str | None = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-creator-server-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.ui = self.root / "ui"
        self.runtime = self.root / "runtime"
        self.identity = self.root / "toolchain-identity.json"
        self.dist = self.root / "dist"
        self.repo.joinpath("products/lmdj/generated").mkdir(parents=True)
        self.repo.joinpath("tools/web-runtime").mkdir(parents=True)
        self.ui.joinpath("assets").mkdir(parents=True)
        self.runtime.mkdir()
        # Derive the fixture from the real identity so it cannot drift out of
        # step with the Product Build the packaging tool reads.
        version = json.loads(
            (REPO_ROOT / "products/lmdj/version.json").read_text(
                encoding="utf-8"
            )
        )
        lock = json.loads(
            (REPO_ROOT / "tools/web-runtime/emscripten.lock.json").read_text(
                encoding="utf-8"
            )
        )
        self.repo.joinpath("products/lmdj/version.json").write_text(
            json.dumps(version), encoding="utf-8"
        )
        shutil.copyfile(
            REPO_ROOT / "products/lmdj/generated/web-runtime-identity.json",
            self.repo / "products/lmdj/generated/web-runtime-identity.json",
        )
        self.repo.joinpath("tools/web-runtime/emscripten.lock.json").write_text(
            json.dumps(lock), encoding="utf-8"
        )
        package = load_module("lmdj_creator_package_fixture", PACKAGE_TOOL)
        self.identity.write_text(
            json.dumps(lock),
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
            "const sampleEditorProof = "
            + json.dumps(SAMPLE_EDITOR_MARKERS)
            + "; console.log(sampleEditorProof);\n"
            + 'const captureWorklet = "/assets/capture_worklet-fixture.js";\n'
            + 'const performTap = "/assets/performance_master_tap_worklet-fixture.js";\n',
            encoding="utf-8",
            newline="\n",
        )
        # The capture worklet is a fifth same-origin asset (CSP: script-src
        # 'self'); the packaging tool rebinds this reference to its hashed name.
        self.ui.joinpath("assets/capture_worklet-fixture.js").write_text(
            "registerProcessor('lmdj-capture-recorder', class {});\n",
            encoding="utf-8",
            newline="\n",
        )
        # Stage 10: the Perform master-tap processor is the sixth asset.
        self.ui.joinpath("assets/performance_master_tap_worklet-fixture.js").write_text(
            "registerProcessor('lmdj-perform-master-tap', class {});\n",
            encoding="utf-8",
            newline="\n",
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
        self.main_path = self.dist / next(
            entry["path"] for entry in manifest["assets"]
            if entry["role"] == "host_main"
        )
        self.wasm_path = self.dist / next(
            entry["path"] for entry in manifest["assets"]
            if entry["role"] == "runtime_wasm"
        )
        self.server = self.module.make_server(
            self.dist, self.verifier, self.repo, "127.0.0.1", 0,
            catalog_upstream=self.catalog_upstream,
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
        self.assertEqual(
            headers["x-robots-tag"], "noindex, nofollow, noarchive"
        )
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

        status, headers, payload = self.request(
            "GET", "/" + self.main_path.relative_to(self.dist).as_posix()
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/javascript; charset=utf-8")
        self.assertEqual(
            headers["cache-control"], "public, max-age=31536000, immutable"
        )
        self.assertEqual(payload, self.main_path.read_bytes())
        for marker in SAMPLE_EDITOR_MARKERS:
            self.assertIn(marker.encode("utf-8"), payload)

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
                status, headers, _ = self.request("GET", path)
                self.assertEqual(status, 404)
                self.assertEqual(headers["cache-control"], "no-store")
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


# Every value parsing would silently reinterpret, or that neither forwarder
# will forward to. `cloudflare_worker.test.mjs` pins a subset, and
# `CatalogUpstreamParityTest` below drives both implementations over it: a
# value one accepts and the other rewrites is how a proof server quietly stops
# standing in for production, which is the defect class that
# `URL.origin`-drops-userinfo already was.
UPSTREAM_PARITY_REFUSED = (
    # Not an http(s) base at all.
    "ftp://catalog.example.test/",
    "not-a-url",
    "",
    "https:///b/",
    # Carries something the base may not.
    "https://catalog.example.test/?query=1",
    "https://catalog.example.test/#fragment",
    "https://catalog.example.test//double/",
    # Credentials, including an empty userinfo `URL.origin` would drop.
    "https://user:pass@catalog.example.test/",
    "https://user@catalog.example.test/",
    "https://@catalog.example.test/",
    "https://:@catalog.example.test/",
    # A backslash terminates the authority, so this resolves to `evil.test`.
    "https://evil.test\\@catalog.example.test/",
    # Dot segments, literal and encoded.
    "https://catalog.example.test/a/../b/",
    "https://catalog.example.test/a/%2e%2e/b/",
    "https://catalog.example.test/%2e/b/",
    "https://catalog.example.test/a/.%2E/b/",
    # Host and scheme spellings WHATWG rewrites.
    "https://exämple.test/b/",
    "https://CATALOG.Example.Test/b/",
    "HTTPS://catalog.example.test/",
    "HtTpS://catalog.example.test/b/",
    "  https://catalog.example.test/b/  ",
    "https://catalog.example.test",
    # Empty query and fragment markers, which `urlsplit` silently drops.
    "https://catalog.example.test/b/?",
    "https://catalog.example.test/b/#",
    # Port forms. The last three reached `parts.port` and raised `ValueError`
    # rather than `ServerError`, which the previous harness could not express
    # -- see `worker_outcome`.
    "https://catalog.example.test:443/b/",
    "https://catalog.example.test:/b/",
    "https://catalog.example.test:08443/b/",
    "https://catalog.example.test:8443./b/",
    "https://catalog.example.test:x/b/",
    "https://catalog.example.test:65536/b/",
    "https://catalog.example.test:-1/b/",
    "https://catalog.example.test:99999999999999/b/",
    # Numeric host spellings that resolve to 127.0.0.1. `getaddrinfo` accepts
    # every one of them, so the proof server would have connected where
    # production refuses outright.
    "https://127.000.000.1/b/",
    "https://0x7f.0.0.1/b/",
    "https://0177.0.0.1/b/",
    "https://2130706433/b/",
    "https://127.1/b/",
    # IPv6 spellings that are not the compressed form.
    "https://[0:0:0:0:0:0:0:1]/b/",
    "https://[::0:1]/b/",
    "https://[0000::1]/b/",
    # Zone identifiers. `ipaddress` round-trips them; WHATWG has no such
    # concept and throws, so the proof server would have accepted a base the
    # deployment cannot express -- the permissive direction, and the last of it.
    "https://[fe80::1%25eth0]/",
    "https://[fe80::1%eth0]/",
    "https://[::1%25]/",
    # Port 0. WHATWG keeps it and `origin` round-trips it, so the Worker needs
    # its own refusal to stay in step with this side's grammar.
    "https://catalog.example.test:0/b/",
    # Path bytes WHATWG percent-encodes, measured rather than recalled.
    'https://catalog.example.test/a"b/',
    "https://catalog.example.test/a<b>/",
    "https://catalog.example.test/a`b/",
    "https://catalog.example.test/a{b}/",
    "https://catalog.example.test/a\x00b/",
    "https://catalog.example.test/a\x01b/",
    "https://catalog.example.test/a\x7fb/",
    # Explicit admission excludes a literal caret, whether the URL parser
    # preserves it (Node 22) or percent-encodes it (Node 26).
    "https://catalog.example.test/a^b/",
    "https://catalog.example.test/b/\n",
    # Host bytes `new URL()` leaves untouched that a Catalog address has no
    # business carrying. `_` is deliberately NOT here: it is admitted by both.
    "https://catalog!example.test/b/",
    "https://catalog~example.test/b/",
    "https://catalog{example}.test/b/",
    "https://.catalog.example.test/b/",
    "https://-catalog.example.test/b/",
)
# Accepted by both, and composed identically by both. The `%2e` bases are here
# on purpose: a substring test for `%2e` refused five legitimate bases that the
# Worker accepts, because WHATWG treats a segment as a dot segment only when
# the whole segment is `.` or `..`.
UPSTREAM_PARITY_ACCEPTED = (
    "https://catalog.example.test/",
    "https://catalog.example.test/sets/",
    "https://catalog.example.test:8443/b/",
    "https://catalog.example.test/%41/",
    "https://catalog.example.test/a%5Eb/",
    "https://catalog.example.test:65535/b/",
    "https://[2001:db8::1]:8443/b/",
    "https://catalog.example.test/a%2eb/",
    "https://catalog.example.test/v1%2e0/",
    "https://catalog.example.test/sets%2ejson/",
    "https://catalog.example.test/a|b/",
    "https://127.0.0.1/b/",
    "https://[::1]/b/",
    # Underscore hosts are real internal names, and both sides accept them.
    "https://a_b.example.test/b/",
)


class CatalogUpstreamFixture(http.server.BaseHTTPRequestHandler):
    """A programmable stand-in for a Sound Set Catalog.

    Records the exact target every forward asked for, so a case can assert that
    an attempt to move the destination never reached a Catalog at all rather
    than merely that the page saw an error.
    """

    protocol_version = "HTTP/1.1"
    received: list[tuple[str, str, dict[str, str]]] = []
    response_status = 200
    response_body = b'{"catalog":"fixture"}'
    response_content_type = "application/json"
    response_location: str | None = None
    declared_length: int | None = None
    declared_header: dict | None = None

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def _record_and_reply(self, include_body: bool) -> None:
        type(self).received.append(
            (
                self.command,
                self.path,
                {key.lower(): value for key, value in self.headers.items()},
            )
        )
        status = type(self).response_status
        body = type(self).response_body if status == 200 else b""
        self.send_response(status)
        if type(self).response_location is not None:
            self.send_header("Location", type(self).response_location)
        self.send_header("Content-Type", type(self).response_content_type)
        spelling = type(self).declared_header
        if spelling is None:
            declared = type(self).declared_length
            self.send_header(
                "Content-Length", str(len(body) if declared is None else declared)
            )
        elif spelling.get("omit") is not True:
            if "duplicate" in spelling:
                self.send_header("Content-Length", "2")
                self.send_header("Content-Length", spelling["duplicate"])
            elif "value" in spelling:
                self.send_header("Content-Length", spelling["value"])
            else:
                self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body and body:
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                # A refused response makes the client close before the body is
                # written. Expected, and its traceback would drown a real one.
                pass

    def do_GET(self) -> None:
        self._record_and_reply(include_body=True)

    def do_HEAD(self) -> None:
        self._record_and_reply(include_body=False)

    do_POST = do_GET
    do_PUT = do_GET
    do_DELETE = do_GET


class CreatorCatalogProxyTest(CreatorServerTest):
    """#901: the Creator reaches its Catalog same-origin, so `connect-src 'self'`
    never has to name a foreign origin.

    This subclass re-runs every inherited case with a Catalog configured, which
    is how the suite asserts that turning the proxy on changes neither the
    static surface nor the Content Security Policy.
    """

    DIGEST = "a" * 64

    def setUp(self) -> None:
        CatalogUpstreamFixture.received = []
        CatalogUpstreamFixture.response_status = 200
        CatalogUpstreamFixture.response_body = b'{"catalog":"fixture"}'
        CatalogUpstreamFixture.response_content_type = "application/json"
        CatalogUpstreamFixture.response_location = None
        CatalogUpstreamFixture.declared_length = None
        CatalogUpstreamFixture.declared_header = None
        self.upstream = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), CatalogUpstreamFixture
        )
        self.upstream.daemon_threads = True
        self.upstream_thread = threading.Thread(
            target=self.upstream.serve_forever, daemon=True
        )
        self.upstream_thread.start()
        host, port = self.upstream.server_address[:2]
        self.catalog_upstream = f"http://{host}:{port}/sets/"
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        self.upstream.shutdown()
        self.upstream.server_close()
        self.upstream_thread.join(timeout=5)

    def test_index_and_objects_forward_to_the_configured_upstream(self) -> None:
        status, headers, body = self.request(
            "GET", "/soundset-catalog/catalog/index.json"
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, b'{"catalog":"fixture"}')
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(
            [entry[1] for entry in CatalogUpstreamFixture.received],
            ["/sets/catalog/index.json"],
        )

        for kind, expected_type in (
            ("manifest", "application/json"),
            ("blob", "application/octet-stream"),
        ):
            CatalogUpstreamFixture.received = []
            status, headers, _ = self.request(
                "GET", f"/soundset-catalog/object/{kind}/{self.DIGEST}"
            )
            self.assertEqual(status, 200)
            self.assertEqual(headers["content-type"], expected_type)
            self.assertEqual(
                headers["cache-control"], "public, max-age=31536000, immutable"
            )
            self.assertEqual(
                [entry[1] for entry in CatalogUpstreamFixture.received],
                [f"/sets/object/{kind}/{self.DIGEST}"],
            )

    def test_nothing_in_the_request_reaches_a_second_origin(self) -> None:
        # Each of these tries to move the destination. None may reach the
        # configured Catalog, and none may reach anything else: the target is
        # composed from the upstream plus tokens this server re-derives, so
        # there is no request text in it to subvert.
        for attempt in (
            "/soundset-catalog/http://127.0.0.1:1/steal",
            "/soundset-catalog//127.0.0.1:1/steal",
            "/soundset-catalog/../steal",
            "/soundset-catalog/%2e%2e/steal",
            f"/soundset-catalog/object/manifest/{self.DIGEST}?to=http://127.0.0.1:1/",
            "/soundset-catalog/catalog/index.json?to=http://127.0.0.1:1/",
            "/soundset-catalog/catalog%2findex.json",
        ):
            with self.subTest(attempt=attempt):
                status, _, _ = self.request("GET", attempt)
                self.assertEqual(status, 404)
                self.assertEqual(CatalogUpstreamFixture.received, [])

    def test_the_admitted_grammar_is_the_two_transport_shapes(self) -> None:
        for path in (
            "/soundset-catalog/",
            "/soundset-catalog/catalog/index.jsonx",
            "/soundset-catalog/catalog/other.json",
            f"/soundset-catalog/object/archive/{self.DIGEST}",
            f"/soundset-catalog/object/manifest/{self.DIGEST.upper()}",
            f"/soundset-catalog/object/manifest/{self.DIGEST[:63]}",
            f"/soundset-catalog/object/manifest/{self.DIGEST}extra",
            f"/soundset-catalog/object/manifest/{self.DIGEST}/again",
            "/soundset-catalog/object/manifest",
        ):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 404)
                self.assertEqual(CatalogUpstreamFixture.received, [])

    def test_only_get_is_admitted(self) -> None:
        for method in ("HEAD", "POST", "PUT", "DELETE"):
            with self.subTest(method=method):
                status, _, _ = self.request(
                    method, "/soundset-catalog/catalog/index.json"
                )
                self.assertEqual(status, 405)
                self.assertEqual(CatalogUpstreamFixture.received, [])

    def test_page_headers_and_credentials_do_not_travel_upstream(self) -> None:
        self.request(
            "GET",
            "/soundset-catalog/catalog/index.json",
            headers={
                "Cookie": "session=must-not-leak",
                "Authorization": "Bearer must-not-leak",
                "X-Forwarded-Host": "attacker.invalid",
            },
        )
        self.assertEqual(len(CatalogUpstreamFixture.received), 1)
        forwarded = CatalogUpstreamFixture.received[0][2]
        for name in ("cookie", "authorization", "x-forwarded-host"):
            self.assertNotIn(name, forwarded)

    def test_upstream_outcomes_collapse_to_missing_or_unavailable(self) -> None:
        for status_code, location, expected in (
            (404, None, 404),
            (500, None, 502),
            (403, None, 502),
            (204, None, 502),
            (302, "http://127.0.0.1:1/elsewhere", 502),
        ):
            with self.subTest(upstream=status_code):
                CatalogUpstreamFixture.received = []
                CatalogUpstreamFixture.response_status = status_code
                CatalogUpstreamFixture.response_location = location
                status, _, _ = self.request(
                    "GET", "/soundset-catalog/catalog/index.json"
                )
                self.assertEqual(status, expected)

    def test_an_oversized_object_is_not_passed_through(self) -> None:
        CatalogUpstreamFixture.response_body = b"x" * (
            self.module.MAXIMUM_CATALOG_OBJECT_BYTES + 1
        )
        CatalogUpstreamFixture.response_content_type = "application/octet-stream"
        status, _, _ = self.request(
            "GET", f"/soundset-catalog/object/blob/{self.DIGEST}"
        )
        self.assertEqual(status, 502)

    def test_a_declared_length_past_the_bound_is_refused_before_the_body(self) -> None:
        # The Worker gained this check with the bounded read and this side did
        # not, so for one commit the same upstream answered 502 in production
        # and 200 here -- a divergence the remedy for a divergence introduced.
        CatalogUpstreamFixture.declared_length = 9 * 1024 * 1024
        status, _, _ = self.request(
            "GET", f"/soundset-catalog/object/blob/{self.DIGEST}"
        )
        self.assertEqual(status, 502)
        # An upstream that *under*-declares cannot use that to smuggle a large
        # body past the bound: HTTP framing is authoritative, so the read stops
        # at the declared length and the rest never enters this process. The
        # page gets the truncated bytes and Core rejects them on hash, which is
        # the layer that owns that decision.
        CatalogUpstreamFixture.declared_length = 2
        CatalogUpstreamFixture.response_body = b"y" * (
            self.module.MAXIMUM_CATALOG_OBJECT_BYTES + 1
        )
        status, _, body = self.request(
            "GET", f"/soundset-catalog/object/blob/{self.DIGEST}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(body), 2)

    def test_the_upstream_content_type_never_reaches_the_page(self) -> None:
        CatalogUpstreamFixture.response_content_type = "text/html; charset=utf-8"
        _, headers, _ = self.request("GET", "/soundset-catalog/catalog/index.json")
        self.assertEqual(headers["content-type"], "application/json")

    def test_an_unreachable_catalog_is_unavailable_not_a_crash(self) -> None:
        self.upstream.shutdown()
        self.upstream.server_close()
        self.upstream_thread.join(timeout=5)
        status, _, _ = self.request("GET", "/soundset-catalog/catalog/index.json")
        self.assertEqual(status, 502)
        # tearDown shuts an already-stopped server down again, which is safe.

    def test_a_refused_upstream_configuration_never_starts_the_server(self) -> None:
        for upstream in UPSTREAM_PARITY_REFUSED:
            with self.subTest(upstream=upstream):
                with self.assertRaises(self.module.ServerError):
                    self.module.make_server(
                        self.dist, self.verifier, self.repo, "127.0.0.1", 0,
                        catalog_upstream=upstream,
                    )

    def test_the_index_shape_carries_the_transports_own_smaller_bound(self) -> None:
        # One bound for both shapes would leave this eight times more
        # permissive than its only client for the index, whose bound in
        # `soundset_catalog.mjs` is 1 MiB against the object's 8 MiB.
        oversize = b"x" * (self.module.MAXIMUM_CATALOG_INDEX_BYTES + 1)
        CatalogUpstreamFixture.response_body = oversize
        status, _, _ = self.request("GET", "/soundset-catalog/catalog/index.json")
        self.assertEqual(status, 502)
        CatalogUpstreamFixture.received = []
        CatalogUpstreamFixture.response_content_type = "application/octet-stream"
        status, _, _ = self.request(
            "GET", f"/soundset-catalog/object/blob/{self.DIGEST}"
        )
        self.assertEqual(status, 200)


class CatalogUpstreamParityTest(unittest.TestCase):
    """The Worker and the proof server must agree about every configured value.

    Not a style point. The proof server exists so the browser acceptance
    journey drives the deployment's topology; a value the two read differently
    means the journey proves something production does not do. `URL.origin`
    silently dropping userinfo was one such value, and an adversarial review of
    this change found seven more before this test existed.
    """

    WORKER = REPO_ROOT / "apps/web-runtime-host/deploy/cloudflare_worker.mjs"

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module("lmdj_shared_web_server_parity", SERVER_TOOL)

    def worker_outcome(self, upstream: str) -> tuple[str, str | None]:
        """`("accept", base)`, `("refuse", None)` or `("crash", detail)`.

        Three outcomes, not two, and that is the point. The first version of
        this harness collapsed anything that was not an accept into a refusal,
        so a value that made an implementation *crash* was recorded as parity
        with a value the other side declined. Class D was exactly that: reading
        `parts.port` raised `ValueError`, the harness could not represent it,
        and the shared list therefore did not contain it -- a parity test
        blind to the class it exists to catch. Ask of any such harness: if a
        divergence existed that it cannot express, would its report look
        different? Here, now, it would.
        """
        script = """
import worker from %s;
const configured = JSON.parse(process.argv[1]);
let target = null;
globalThis.fetch = async (t) => {
  target = t;
  return new Response("{}", {status: 200, headers: {"content-length": "2"}});
};
const response = await worker.fetch(
  new Request("https://creator.lmdj.workers.dev/soundset-catalog/catalog/index.json"),
  {ASSETS: {fetch: () => new Response("a")}, CATALOG_UPSTREAM: configured},
);
process.stdout.write(JSON.stringify(
  response.status === 200 ? target.slice(0, -"catalog/index.json".length) : null,
));
""" % json.dumps(str(self.WORKER))
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script, json.dumps(upstream)],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if completed.returncode != 0:
            return ("crash", completed.stderr.strip()[:300])
        base = json.loads(completed.stdout)
        return ("accept", base) if base is not None else ("refuse", None)

    def python_outcome(self, upstream: str) -> tuple[str, str | None]:
        """The same three outcomes for the proof server. See `worker_outcome`."""
        try:
            return ("accept", self.module.normalize_catalog_upstream(upstream))
        except self.module.ServerError:
            return ("refuse", None)
        except Exception as error:  # noqa: BLE001 - a crash is its own outcome
            return ("crash", f"{type(error).__name__}: {error}")

    def test_neither_implementation_crashes_on_any_reviewed_value(self) -> None:
        # A crash is not a refusal. Through `--catalog-upstream-file` an
        # escaping exception is an empty response on every request rather than
        # a 404, and it is the acceptance lane's own configuration path.
        for upstream in (
            UPSTREAM_PARITY_REFUSED
            + UPSTREAM_PARITY_ACCEPTED
        ):
            with self.subTest(upstream=upstream):
                python_kind, python_detail = self.python_outcome(upstream)
                self.assertNotEqual(python_kind, "crash", python_detail)
                worker_kind, worker_detail = self.worker_outcome(upstream)
                self.assertNotEqual(worker_kind, "crash", worker_detail)

    def test_both_refuse_every_value_parsing_would_reinterpret(self) -> None:
        for upstream in UPSTREAM_PARITY_REFUSED:
            with self.subTest(upstream=upstream):
                self.assertEqual(
                    self.python_outcome(upstream), ("refuse", None), "proof server"
                )
                self.assertEqual(
                    self.worker_outcome(upstream), ("refuse", None), "Worker"
                )

    def test_both_compose_the_same_base_for_every_accepted_value(self) -> None:
        for upstream in UPSTREAM_PARITY_ACCEPTED:
            with self.subTest(upstream=upstream):
                expected = self.python_outcome(upstream)
                self.assertEqual(expected[0], "accept", "proof server")
                self.assertEqual(self.worker_outcome(upstream), expected)

    def test_parity_over_a_generated_corpus(self) -> None:
        """Both endpoints must give the same outcome for every generated HTTPS base.

        Generate inside the grammar's alphabet to exercise canonical host,
        port and path checks after character admission. Keep the fixed reviewed
        corpus above as regression pins, including disallowed characters.
        """
        rng = random.Random(901)
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789.-_"
        path_alphabet = "abcXYZ019!$%&'()*+,-.:;=@[]_|~"
        corpus = []
        for _ in range(400):
            host = "".join(
                rng.choice(alphabet) for _ in range(rng.randint(1, 12))
            )
            port = "" if rng.random() < 0.7 else f":{rng.randint(1, 65535)}"
            segments = "".join(
                "/" + "".join(
                    rng.choice(path_alphabet) for _ in range(rng.randint(0, 6))
                )
                for _ in range(rng.randint(0, 3))
            )
            corpus.append(f"https://{host}{port}{segments}/")
        accepted = 0
        for upstream in corpus:
            kind, base = self.python_outcome(upstream)
            self.assertNotEqual(kind, "crash", f"{upstream}: {base}")
            self.assertEqual(
                self.worker_outcome(upstream), (kind, base),
                f"Catalog admission parity differs for {upstream!r}; "
                "keep the shared grammar and canonical URL checks aligned",
            )
            if kind == "accept":
                accepted += 1
        # A corpus that accepted nothing would assert nothing.
        self.assertGreater(accepted, 50, "the corpus exercises too few accepts")

    def test_ascii_character_admission_matches_in_host_and_path(self) -> None:
        for codepoint in range(128):
            character = chr(codepoint)
            for upstream in (
                f"https://a{character}b.example.test/",
                f"https://catalog.example.test/a{character}b/",
            ):
                with self.subTest(upstream=upstream):
                    expected = self.python_outcome(upstream)
                    self.assertNotEqual(expected[0], "crash", expected[1])
                    self.assertEqual(self.worker_outcome(upstream), expected)

    def test_the_one_intended_difference_is_plaintext_loopback(self) -> None:
        # The proof server admits a loopback `http` Catalog because the
        # acceptance fixture is one; the Worker admits `https` alone. This is
        # the only disagreement, and it is asserted so it stays the only one.
        for host in ("localhost", "127.0.0.1", "[::1]"):
            loopback = f"http://{host}:8099/"
            with self.subTest(upstream=loopback):
                self.assertEqual(self.python_outcome(loopback), ("accept", loopback))
                self.assertEqual(self.worker_outcome(loopback), ("refuse", None))
        for elsewhere in ("http://catalog.example.test/", "http://127.0.0.2/"):
            self.assertEqual(self.python_outcome(elsewhere), ("refuse", None))
            self.assertEqual(self.worker_outcome(elsewhere), ("refuse", None))


# The upstream RESPONSE surface, the second place the two implementations must
# agree and the one that had no parity coverage at all. Two consecutive commits
# that were closing divergences elsewhere each introduced one here -- the
# declared-length pre-check landing on one side only, then a strict token that
# made both sides agree on the rule while still disagreeing about the string it
# ran on. Enumerable, unlike the configured-value surface, so it is enumerated:
# status, every Content-Length spelling that behaves differently, the body
# bound at each shape, and the emitted content type.
#
# `expected` is the status the PAGE sees, which is what both must produce.
RESPONSE_SURFACE_CASES = (
    ("plain 200", {}, 200, b"{}", None, 200),
    ("upstream 404", {}, 404, b"", None, 404),
    ("upstream 204", {}, 204, b"", None, 502),
    ("upstream 500", {}, 500, b"", None, 502),
    ("upstream 302", {}, 302, b"", "https://elsewhere.test/", 502),
    ("length absent", {"omit": True}, 200, b"{}", None, 200),
    ("length valid", {"value": "2"}, 200, b"{}", None, 200),
    # Fetch trims each value; `email.message` keeps the padding.
    ("length padded", {"value": "  2  "}, 200, b"{}", None, 200),
    # Fetch joins repeats with ", "; `email.message` returns the first.
    ("length duplicated", {"duplicate": "2"}, 200, b"{}", None, 502),
    ("length duplicated unequal", {"duplicate": "99999999"}, 200, b"{}", None, 502),
    # `int()` honours PEP 515; `Number()` reads hex.
    ("length underscored", {"value": "5_0"}, 200, b"{}", None, 502),
    ("length hex", {"value": "0x10"}, 200, b"{}", None, 502),
    ("length signed", {"value": "+2"}, 200, b"{}", None, 502),
    ("length negative", {"value": "-1"}, 200, b"{}", None, 502),
    ("length words", {"value": "abc"}, 200, b"{}", None, 502),
    ("length empty", {"value": ""}, 200, b"{}", None, 502),
)


class CatalogResponseSurfaceParityTest(CreatorCatalogProxyTest):
    """Both implementations must answer the page identically for one upstream.

    Inherits the proxy fixture so the Python side is driven through the real
    handler over HTTP, and drives the Worker over the same case list in node.
    """

    WORKER = REPO_ROOT / "apps/web-runtime-host/deploy/cloudflare_worker.mjs"

    def worker_status(self, header: dict, status: int, body: bytes,
                      location: str | None) -> int:
        script = """
import worker from %s;
const [header, status, body, location] = JSON.parse(process.argv[1]);
const entries = [["content-type", "application/json"]];
if (location !== null) entries.push(["location", location]);
if (header.omit !== true) {
  if (header.duplicate !== undefined) {
    entries.push(["content-length", "2"], ["content-length", header.duplicate]);
  } else if (header.value !== undefined) {
    entries.push(["content-length", header.value]);
  } else {
    entries.push(["content-length", String(body.length)]);
  }
}
globalThis.fetch = async () => new Response(
  status === 204 || status === 302 ? null : body,
  {status, headers: new Headers(entries)},
);
const response = await worker.fetch(
  new Request("https://creator.lmdj.workers.dev/soundset-catalog/catalog/index.json"),
  {ASSETS: {fetch: () => new Response("a")}, CATALOG_UPSTREAM: "https://catalog.example/base/"},
);
process.stdout.write(String(response.status));
""" % json.dumps(str(self.WORKER))
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script,
             json.dumps([header, status, body.decode(), location])],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if completed.returncode != 0:
            self.fail(f"the Worker crashed: {completed.stderr.strip()[:300]}")
        return int(completed.stdout)

    def test_both_answer_the_page_identically_for_one_upstream(self) -> None:
        for label, header, status, body, location, expected in RESPONSE_SURFACE_CASES:
            with self.subTest(case=label):
                CatalogUpstreamFixture.received = []
                CatalogUpstreamFixture.response_status = status
                CatalogUpstreamFixture.response_body = body
                CatalogUpstreamFixture.response_location = location
                CatalogUpstreamFixture.declared_header = header
                observed, _, _ = self.request(
                    "GET", "/soundset-catalog/catalog/index.json"
                )
                self.assertEqual(observed, expected, "proof server")
                self.assertEqual(
                    self.worker_status(header, status, body, location),
                    expected, "Worker",
                )


class CreatorNoCatalogTest(CreatorServerTest):
    """A deployment that configures no Catalog forwards nothing at all."""

    def test_the_prefix_is_inert_without_a_configured_upstream(self) -> None:
        for path in (
            "/soundset-catalog/catalog/index.json",
            f"/soundset-catalog/object/manifest/{'a' * 64}",
            "/soundset-catalog/",
        ):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 404)


class CreatorCatalogUpstreamFileTest(CreatorCatalogProxyTest):
    """The lane writes its Catalog upstream after this server is listening.

    Same proxy, same grammar, same refusals -- the whole inherited suite runs
    again -- with the upstream arriving through a file instead of a flag,
    because the acceptance journey's fixture port is not known until after the
    proof server has started.
    """

    def setUp(self) -> None:
        self.upstream_file_root = tempfile.TemporaryDirectory(
            prefix="lmdj-catalog-upstream-"
        )
        self.upstream_file = Path(self.upstream_file_root.name) / "upstream"
        super().setUp()
        # `super().setUp()` set `self.catalog_upstream` and started a server
        # with it; restart on the file path so the whole suite runs that way.
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.upstream_file.write_text(self.catalog_upstream, encoding="utf-8")
        self.server = self.module.make_server(
            self.dist, self.verifier, self.repo, "127.0.0.1", 0,
            catalog_upstream_file=self.upstream_file,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        super().tearDown()
        self.upstream_file_root.cleanup()

    def test_a_rewritten_file_moves_the_upstream_without_a_restart(self) -> None:
        self.request("GET", "/soundset-catalog/catalog/index.json")
        self.assertEqual(len(CatalogUpstreamFixture.received), 1)
        # A Catalog that goes away mid-run is the journey's unreachable leg.
        self.upstream_file.write_text("", encoding="utf-8")
        status, _, _ = self.request("GET", "/soundset-catalog/catalog/index.json")
        self.assertEqual(status, 404)
        self.assertEqual(len(CatalogUpstreamFixture.received), 1)
        self.upstream_file.write_text(self.catalog_upstream, encoding="utf-8")
        status, _, _ = self.request("GET", "/soundset-catalog/catalog/index.json")
        self.assertEqual(status, 200)
        self.assertEqual(len(CatalogUpstreamFixture.received), 2)

    def test_an_unusable_upstream_file_forwards_nothing(self) -> None:
        symlink = Path(self.upstream_file_root.name) / "symlinked"
        symlink.symlink_to(self.upstream_file)
        cases = {
            "missing": Path(self.upstream_file_root.name) / "absent",
            "symlink": symlink,
            "directory": Path(self.upstream_file_root.name),
        }
        for label, path in cases.items():
            with self.subTest(source=label):
                self.assertIsNone(self.module.read_catalog_upstream_file(path))
        for label, content in {
            "empty": "",
            "not-a-url": "not-a-url",
            "wrong-scheme": "ftp://127.0.0.1/",
            "non-loopback-plaintext": "http://catalog.invalid/",
            "query": "https://catalog.invalid/?query=1",
            "credentials": "https://user:pass@catalog.invalid/",
        }.items():
            with self.subTest(content=label):
                self.upstream_file.write_text(content, encoding="utf-8")
                self.assertIsNone(
                    self.module.read_catalog_upstream_file(self.upstream_file)
                )
                status, _, _ = self.request(
                    "GET", "/soundset-catalog/catalog/index.json"
                )
                self.assertEqual(status, 404)
                self.assertEqual(CatalogUpstreamFixture.received, [])

    def test_two_configured_upstreams_are_refused(self) -> None:
        with self.assertRaises(self.module.ServerError):
            self.module.make_server(
                self.dist, self.verifier, self.repo, "127.0.0.1", 0,
                catalog_upstream=self.catalog_upstream,
                catalog_upstream_file=self.upstream_file,
            )


if __name__ == "__main__":
    unittest.main()
