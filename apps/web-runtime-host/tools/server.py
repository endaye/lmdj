#!/usr/bin/env python3

from __future__ import annotations

import argparse
from functools import partial
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
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


def load_distribution_verifier():
    package_path = Path(__file__).with_name("package.py")
    spec = importlib.util.spec_from_file_location(
        "lmdj_web_runtime_host_package", package_path
    )
    if spec is None or spec.loader is None:
        raise ServerError("distribution verifier cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_file_no_follow(root: Path, relative: str) -> bytes | None:
    parts = Path(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None
    opened: list[int] = []
    try:
        root_status = os.lstat(root)
        if stat.S_ISLNK(root_status.st_mode) or not stat.S_ISDIR(root_status.st_mode):
            return None
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        root_fd = os.open(root, directory_flags)
        opened.append(root_fd)
        descriptor_status = os.fstat(root_fd)
        if (
            descriptor_status.st_dev,
            descriptor_status.st_ino,
        ) != (root_status.st_dev, root_status.st_ino):
            return None
        directory_fd = root_fd
        for component in parts[:-1]:
            directory_fd = os.open(
                component, directory_flags, dir_fd=directory_fd
            )
            opened.append(directory_fd)
        file_fd = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd
        )
        opened.append(file_fd)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            return None
        chunks = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError:
        return None
    finally:
        for descriptor in reversed(opened):
            try:
                os.close(descriptor)
            except OSError:
                pass


class ProofServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class ProofHandler(BaseHTTPRequestHandler):
    server_version = "LMDJWebRuntimeHostProof/1"

    def __init__(
        self,
        *args,
        root: Path,
        expected_hashes: dict[str, str],
        verbose: bool = False,
        **kwargs,
    ) -> None:
        self.root = root
        self.expected_hashes = expected_hashes
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

    def _select_relative(self) -> str | None:
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
        return relative

    def _serve(self, include_body: bool) -> None:
        if self.headers.get("Range") is not None:
            self._status(404, include_body)
            return
        relative = self._select_relative()
        if relative is None:
            self._status(404, include_body)
            return
        payload = read_file_no_follow(self.root, relative)
        if (
            payload is None
            or self.expected_hashes.get(relative)
            != hashlib.sha256(payload).hexdigest()
        ):
            self._status(404, include_body)
            return
        content_type = CONTENT_TYPES.get(Path(relative).suffix.lower())
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
    requested_root = root.expanduser()
    if not requested_root.is_absolute():
        requested_root = Path.cwd() / requested_root
    try:
        root_status = os.lstat(requested_root)
    except OSError as error:
        raise ServerError(f"root must be a directory: {requested_root}") from error
    if stat.S_ISLNK(root_status.st_mode) or not stat.S_ISDIR(root_status.st_mode):
        raise ServerError(f"root must be a non-symlink directory: {requested_root}")
    root = requested_root.resolve(strict=True)
    if not root.is_dir():
        raise ServerError(f"root must be a directory: {root}")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ServerError("the proof server is loopback-only")
    if port < 0 or port > 65_535:
        raise ServerError("port must be between 0 and 65535")
    verifier = load_distribution_verifier()
    try:
        verifier.verify_distribution(root, Path(__file__).resolve().parents[3])
    except verifier.DistributionError as error:
        raise ServerError(f"distribution verification failed: {error}") from error
    manifest_bytes = read_file_no_follow(root, "host-manifest.json")
    index_bytes = read_file_no_follow(root, "index.html")
    if manifest_bytes is None or index_bytes is None:
        raise ServerError("verified distribution cannot be opened safely")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ServerError("verified manifest cannot be decoded") from error
    expected_hashes = {
        "host-manifest.json": hashlib.sha256(manifest_bytes).hexdigest(),
        "index.html": hashlib.sha256(index_bytes).hexdigest(),
        **{entry["path"]: entry["sha256"] for entry in manifest["assets"]},
    }
    return ProofServer(
        (host, port),
        partial(
            ProofHandler,
            root=root,
            expected_hashes=expected_hashes,
            verbose=verbose,
        ),
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=4175, type=int)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--ready-nonce")
    return parser.parse_args()


def main() -> int:
    options = parse_arguments()
    if (options.ready_file is None) != (options.ready_nonce is None):
        print(
            "web proof server error: --ready-file and --ready-nonce are required together",
            file=sys.stderr,
        )
        return 2
    try:
        server = make_server(
            options.root, options.host, options.port, options.verbose
        )
    except (OSError, ServerError) as error:
        print(f"web proof server error: {error}", file=sys.stderr)
        return 2
    port = server.server_address[1]
    print(f"http://{options.host}:{port}", flush=True)
    ready_path = None
    if options.ready_file is not None:
        requested_ready = options.ready_file.expanduser()
        if not requested_ready.is_absolute():
            requested_ready = Path.cwd() / requested_ready
        try:
            ready_parent = requested_ready.parent.resolve(strict=True)
            ready_path = ready_parent / requested_ready.name
            descriptor = os.open(
                ready_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            payload = json.dumps(
                {
                    "host": options.host,
                    "nonce": options.ready_nonce,
                    "pid": os.getpid(),
                    "port": port,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as error:
            server.server_close()
            print(f"web proof server error: ready file: {error}", file=sys.stderr)
            return 2
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if ready_path is not None:
            try:
                ready_path.unlink()
            except FileNotFoundError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
