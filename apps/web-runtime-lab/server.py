#!/usr/bin/env python3

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import ssl
import sys
from urllib.parse import urlsplit


LAB_ROOT = Path(__file__).resolve().parent
NOT_FOUND_PATH = LAB_ROOT / ".lmdj-web-runtime-not-found"
ISOLATION_HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}


class ServerError(RuntimeError):
    pass


class RuntimeLabServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class RuntimeLabHandler(SimpleHTTPRequestHandler):
    server_version = "LMDJWebRuntimeLab/1"

    def __init__(self, *args, verbose: bool = False, **kwargs) -> None:
        self.verbose = verbose
        super().__init__(*args, **kwargs)

    def end_headers(self) -> None:
        for name, value in ISOLATION_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        if self.verbose:
            super().log_message(format, *args)

    def translate_path(self, path: str) -> str:
        translated = Path(super().translate_path(path)).resolve(strict=False)
        try:
            translated.relative_to(LAB_ROOT)
        except ValueError:
            return str(NOT_FOUND_PATH)
        return str(translated)

    def _health(self, include_body: bool) -> None:
        body = json.dumps(
            {"ok": True, "service": "web-runtime-lab"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/health.json":
            self._health(include_body=True)
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if urlsplit(self.path).path == "/health.json":
            self._health(include_body=False)
            return
        super().do_HEAD()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--cert-file", type=Path)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--write-port", type=Path)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def is_loopback(bind: str) -> bool:
    if bind == "localhost":
        return True
    try:
        return ipaddress.ip_address(bind).is_loopback
    except ValueError:
        return False


def require_regular_file(path: Path, label: str) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink() or not expanded.is_file():
        raise ServerError(f"{label} must be a regular non-symlink file: {path}")
    return expanded.resolve()


def validate_options(options: argparse.Namespace) -> tuple[Path | None, Path | None]:
    if options.port < 0 or options.port > 65535:
        raise ServerError("port must be between 0 and 65535")
    if bool(options.cert_file) != bool(options.key_file):
        raise ServerError("--cert-file and --key-file must be supplied together")
    cert_file = None
    key_file = None
    if options.cert_file and options.key_file:
        cert_file = require_regular_file(options.cert_file, "certificate")
        key_file = require_regular_file(options.key_file, "private key")
    if not is_loopback(options.bind) and cert_file is None:
        raise ServerError("non-loopback binding requires TLS")
    if options.write_port is not None:
        write_port = options.write_port.expanduser()
        if write_port.exists() and write_port.is_symlink():
            raise ServerError("--write-port must not be a symlink")
        if not write_port.parent.is_dir():
            raise ServerError("--write-port parent must be an existing directory")
    return cert_file, key_file


def serve(options: argparse.Namespace) -> None:
    cert_file, key_file = validate_options(options)
    handler = partial(
        RuntimeLabHandler,
        directory=str(LAB_ROOT),
        verbose=options.verbose,
    )
    server = RuntimeLabServer((options.bind, options.port), handler)
    scheme = "http"
    if cert_file is not None and key_file is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    actual_port = int(server.server_address[1])
    if options.write_port is not None:
        options.write_port.write_text(
            f"{actual_port}\n",
            encoding="utf-8",
            newline="\n",
        )
    display_host = "127.0.0.1" if options.bind == "0.0.0.0" else options.bind
    print(f"{scheme}://{display_host}:{actual_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> int:
    options = parse_arguments()
    try:
        serve(options)
    except (OSError, ServerError, ssl.SSLError) as error:
        print(f"server error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
