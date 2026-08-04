#!/usr/bin/env python3

from __future__ import annotations

import argparse
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sys
from urllib.parse import unquote_to_bytes, urlsplit


CSP = (
    "default-src 'none'; base-uri 'none'; object-src 'none'; "
    "frame-ancestors 'none'; form-action 'none'; "
    "script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
    "child-src 'self' blob:; connect-src 'self'; style-src 'self'; "
    "img-src 'self'; media-src 'self' blob:; manifest-src 'self'"
)
SECURITY_HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
}
HASHED_ASSET = re.compile(
    r"^assets/[a-z0-9-]+\.[0-9a-f]{64}\.(?:css|js|mjs|wasm)$"
)
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".wasm": "application/wasm",
}


class ServerError(RuntimeError):
    pass


class ProofServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class ProofHandler(BaseHTTPRequestHandler):
    server_version = "LMDJWebRuntimeHostProof/1"

    def __init__(self, *args, root: Path, verbose: bool = False, **kwargs) -> None:
        self.root = root
        self.verbose = verbose
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args) -> None:
        if self.verbose:
            super().log_message(format, *args)

    def end_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        if code == HTTPStatus.NOT_IMPLEMENTED:
            self._status(HTTPStatus.METHOD_NOT_ALLOWED, self.command != "HEAD")
            return
        super().send_error(code, message, explain)

    def _status(self, status: int, include_body: bool) -> None:
        body = f"{status}\n".encode("ascii") if include_body else b""
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _resolve(self) -> tuple[Path, str] | None:
        try:
            raw_path = unquote_to_bytes(urlsplit(self.path).path)
            decoded = raw_path.decode("utf-8", errors="strict")
        except (UnicodeDecodeError, ValueError):
            return None
        if "\x00" in decoded or "\\" in decoded or not decoded.startswith("/"):
            return None
        relative = decoded.removeprefix("/")
        if relative == "":
            relative = "index.html"
        parts = Path(relative).parts
        if any(part in {"", ".", ".."} for part in parts):
            return None
        if relative not in {"index.html", "host-manifest.json"} and HASHED_ASSET.fullmatch(relative) is None:
            return None
        candidate = self.root.joinpath(*parts)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.root)
        except (OSError, ValueError):
            return None
        if not resolved.is_file():
            return None
        return resolved, relative

    def _serve(self, include_body: bool) -> None:
        if self.headers.get("Range") is not None:
            self._status(404, include_body)
            return
        selected = self._resolve()
        if selected is None:
            self._status(404, include_body)
            return
        path, relative = selected
        try:
            payload = path.read_bytes()
        except OSError:
            self._status(404, include_body)
            return
        content_type = CONTENT_TYPES.get(path.suffix.lower())
        if content_type is None:
            self._status(404, include_body)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if relative in {"index.html", "host-manifest.json"}:
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header(
                "Cache-Control", "public, max-age=31536000, immutable"
            )
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def do_GET(self) -> None:
        self._serve(include_body=True)

    def do_HEAD(self) -> None:
        self._serve(include_body=False)

    def do_POST(self) -> None:
        self._status(405, include_body=True)

    do_PUT = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST
    do_PATCH = do_POST


def make_server(
    root: Path, host: str = "127.0.0.1", port: int = 4175, verbose: bool = False
) -> ProofServer:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ServerError(f"root must be a directory: {root}")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ServerError("the proof server is loopback-only")
    if port < 0 or port > 65_535:
        raise ServerError("port must be between 0 and 65535")
    return ProofServer(
        (host, port), partial(ProofHandler, root=root, verbose=verbose)
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=4175, type=int)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    options = parse_arguments()
    try:
        server = make_server(
            options.root, options.host, options.port, options.verbose
        )
    except (OSError, ServerError) as error:
        print(f"web proof server error: {error}", file=sys.stderr)
        return 2
    print(f"http://{options.host}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
