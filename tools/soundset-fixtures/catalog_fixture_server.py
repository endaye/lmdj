#!/usr/bin/env python3
"""Static Sound Set Catalog fixture server (stdlib only).

The server exposes exactly three request shapes and nothing else:

    GET|HEAD /catalog/index.json          the Host-configured Catalog endpoint
    GET|HEAD /object/manifest/<sha256>    one canonical manifest object
    GET|HEAD /object/blob/<sha256>        one content-addressed Artifact blob

`<sha256>` must be exactly 64 lowercase hex characters, so a request can name
one basename under one object-kind directory and nothing else. There is no
archive endpoint, no directory listing, no index fallback, no path
normalisation, no query string, no redirect, and no cross-kind fallback: a
manifest hash requested under `blob` is a miss, not a redirect. Everything
else answers 404 (or 405 for a method other than GET/HEAD).

That is deliberately the whole of S11-D6's Catalog transport surface. A
Host-side network `CatalogTransport` can be pointed at this server and must
not need any other shape.

    python3 tools/soundset-fixtures/catalog_fixture_server.py \
        --root tests/fixtures/soundset --port 8099
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import stat
import sys
import threading


OBJECT_KIND_DIRECTORY = {"manifest": "manifest", "blob": "blob"}

CATALOG_INDEX_PATH = "/catalog/index.json"

OBJECT_REQUEST = re.compile(r"\A/object/(manifest|blob)/([0-9a-f]{64})\Z")

CONTENT_TYPES = {
    "catalog": "application/json",
    "manifest": "application/json",
    "blob": "application/octet-stream",
}

# A fixture blob is tiny; anything larger than this is not our corpus.
MAXIMUM_OBJECT_BYTES = 4 * 1024 * 1024


class CatalogFixtureRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "lmdj-soundset-catalog-fixture/1"
    sys_version = ""

    # Set by the server factory below.
    corpus_root: Path
    verbose: bool = False
    cross_origin: bool = False

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        if self.verbose:
            super().log_message(format, *args)

    def do_GET(self) -> None:
        self._respond(with_body=True)

    def do_HEAD(self) -> None:
        self._respond(with_body=False)

    def _reject_method(self) -> None:
        self._send(405, b"", "text/plain", with_body=True)

    do_POST = _reject_method
    do_PUT = _reject_method
    do_DELETE = _reject_method
    do_PATCH = _reject_method
    do_OPTIONS = _reject_method

    def _resolve(self, target: str) -> tuple[Path, str] | None:
        """Map a raw request target to a file, or None for every other shape."""
        # No query string, no fragment, no percent-encoding, no normalisation.
        # The literal target must be one of the three admitted shapes.
        if target == CATALOG_INDEX_PATH:
            return self.corpus_root / "catalog" / "index.json", "catalog"
        match = OBJECT_REQUEST.match(target)
        if match is None:
            return None
        kind, digest = match.group(1), match.group(2)
        return self.corpus_root / OBJECT_KIND_DIRECTORY[kind] / digest, kind

    def _raw_target(self) -> str:
        """Return the request target exactly as it arrived on the wire.

        `BaseHTTPRequestHandler.parse_request` collapses a leading `//` into
        `/` before it sets `self.path`, so reading `self.path` would let a
        shape through that this server never admitted. The raw request line is
        the only faithful source.
        """
        parts = self.requestline.split(" ")
        if len(parts) != 3:
            return ""
        return parts[1]

    def _respond(self, *, with_body: bool) -> None:
        resolved = self._resolve(self._raw_target())
        if resolved is None:
            self._send(404, b"", "text/plain", with_body=with_body)
            return
        path, kind = resolved
        payload = read_regular_file(path)
        if payload is None:
            self._send(404, b"", "text/plain", with_body=with_body)
            return
        self._send(200, payload, CONTENT_TYPES[kind], with_body=with_body)

    def _send(
        self,
        status: int,
        payload: bytes,
        content_type: str,
        *,
        with_body: bool,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if self.cross_origin:
            # For a Catalog meant to be read *directly* by a page. CORS is what
            # actually decides it: measured in Chromium and WebKit on a
            # cross-origin-isolated page, `Access-Control-Allow-Origin` alone
            # is sufficient and `Cross-Origin-Resource-Policy` alone is still
            # blocked, because the CORP check is skipped for a request whose
            # mode is not `no-cors` and `fetch` is `cors` by default. CORP is
            # sent anyway: it costs nothing and a `no-cors` consumer would need
            # it. Without CORS the browser refuses before the transport sees a
            # status, and the failure arrives as `catalog_unavailable`,
            # indistinguishable from a Catalog that is genuinely down.
            #
            # Off by default, and the LMDJ Creator does not need it at all: it
            # reaches its Catalog through a same-origin prefix the Host
            # forwards (#901), so the request the Catalog sees is server-side
            # and no browser policy applies to it.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.end_headers()
        if with_body and payload:
            self.wfile.write(payload)


def read_regular_file(path: Path) -> bytes | None:
    """Read `path` without following a symlink and without listing a directory.

    Mirrors the S11-D6 local adapter rule: open the single basename, refuse to
    follow a symlink, `fstat` for a regular file, then read bounded bytes.
    """
    # O_NOFOLLOW refuses a symlinked basename; O_NONBLOCK keeps a FIFO from
    # parking the request thread before `fstat` can reject it.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            return None
        if info.st_size > MAXIMUM_OBJECT_BYTES:
            return None
        payload = b""
        while len(payload) < info.st_size:
            chunk = os.read(descriptor, info.st_size - len(payload))
            if not chunk:
                break
            payload += chunk
        return payload if len(payload) == info.st_size else None
    finally:
        os.close(descriptor)


class CatalogFixtureServer:
    """Threaded fixture server bound to an ephemeral port by default."""

    def __init__(
        self,
        root: Path,
        host: str = "127.0.0.1",
        port: int = 0,
        verbose: bool = False,
        cross_origin: bool = False,
    ) -> None:
        self.root = Path(root).resolve()
        handler = type(
            "BoundCatalogFixtureRequestHandler",
            (CatalogFixtureRequestHandler,),
            {
                "corpus_root": self.root,
                "verbose": verbose,
                "cross_origin": cross_origin,
            },
        )
        self._server = ThreadingHTTPServer((host, port), handler)
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        return self._server.server_address[0], self._server.server_address[1]

    @property
    def base_url(self) -> str:
        host, port = self.address
        return f"http://{host}:{port}"

    def start(self) -> "CatalogFixtureServer":
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="soundset-catalog-fixture",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def wait(self) -> None:
        """Block until the serving thread ends (or the caller interrupts)."""
        while self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def __enter__(self) -> "CatalogFixtureServer":
        return self.start()

    def __exit__(self, *_exception) -> None:
        self.stop()


def main(argv: list[str]) -> int:
    default_root = (
        Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "soundset"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--cross-origin",
        action="store_true",
        help=(
            "answer with Access-Control-Allow-Origin and "
            "Cross-Origin-Resource-Policy so a cross-origin-isolated browser "
            "page can read the corpus"
        ),
    )
    arguments = parser.parse_args(argv)

    if not arguments.root.is_dir():
        print(f"corpus root is not a directory: {arguments.root}", file=sys.stderr)
        return 2

    server = CatalogFixtureServer(
        arguments.root,
        host=arguments.host,
        port=arguments.port,
        verbose=arguments.verbose,
        cross_origin=arguments.cross_origin,
    )
    print(f"serving {server.root} at {server.base_url}", flush=True)
    server.start()
    try:
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
