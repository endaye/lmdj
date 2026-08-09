#!/usr/bin/env python3

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from socketserver import TCPServer
import sys
from urllib.parse import urlsplit


CSP = (
    "default-src 'none'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'none'; "
    "script-src 'self' 'wasm-unsafe-eval'; "
    "worker-src 'self' blob:; "
    "child-src 'self' blob:; "
    "connect-src 'self'; "
    "style-src 'self'; "
    "img-src 'self'; "
    "media-src 'self' blob:"
)
ISOLATION_HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": CSP,
}


class ServerError(RuntimeError):
    pass


class ConformanceServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class ConformanceHandler(SimpleHTTPRequestHandler):
    server_version = "LMDJWebToolchainConformance/1"
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".wasm": "application/wasm",
    }

    def __init__(self, *args, root: Path, verbose: bool, **kwargs) -> None:
        self.root = root
        self.verbose = verbose
        super().__init__(*args, directory=str(root), **kwargs)

    def end_headers(self) -> None:
        for name, value in ISOLATION_HEADERS.items():
            self.send_header(name, value)
        suffix = Path(urlsplit(self.path).path).suffix
        if suffix in {".html", ".json"}:
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        if self.verbose:
            super().log_message(format, *args)

    def translate_path(self, path: str) -> str:
        translated = Path(super().translate_path(path)).resolve(strict=False)
        try:
            translated.relative_to(self.root)
        except ValueError:
            return str(self.root / ".lmdj-web-toolchain-not-found")
        return str(translated)

    def list_directory(self, path: str):
        self.send_error(404)
        return None

    def _health(self, include_body: bool) -> None:
        body = json.dumps(
            {"ok": True, "service": "web-toolchain-conformance"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _preflight(self, include_body: bool) -> None:
        body = b"<!doctype html><html lang=\"en\"><title>preflight</title></html>\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/health.json":
            self._health(include_body=True)
            return
        if urlsplit(self.path).path == "/preflight.html":
            self._preflight(include_body=True)
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if urlsplit(self.path).path == "/health.json":
            self._health(include_body=False)
            return
        if urlsplit(self.path).path == "/preflight.html":
            self._preflight(include_body=False)
            return
        super().do_HEAD()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", default=4174, type=int)
    parser.add_argument("--write-port", type=Path)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def serve(options: argparse.Namespace) -> None:
    root = options.root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ServerError(f"root must be a directory: {root}")
    if options.bind not in {"127.0.0.1", "localhost", "::1"}:
        raise ServerError("the conformance server is loopback-only")
    if options.port < 0 or options.port > 65535:
        raise ServerError("port must be between 0 and 65535")
    if options.write_port is not None:
        write_port = options.write_port.expanduser()
        if write_port.exists() and write_port.is_symlink():
            raise ServerError("--write-port must not be a symlink")
        if not write_port.parent.is_dir():
            raise ServerError("--write-port parent must exist")

    handler = partial(
        ConformanceHandler,
        root=root,
        verbose=options.verbose,
    )
    server = ConformanceServer((options.bind, options.port), handler)
    actual_port = int(server.server_address[1])
    if options.write_port is not None:
        options.write_port.write_text(
            f"{actual_port}\n",
            encoding="utf-8",
            newline="\n",
        )
    print(f"http://{options.bind}:{actual_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> int:
    options = parse_arguments()
    try:
        serve(options)
    except (OSError, ServerError) as error:
        print(f"server error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
