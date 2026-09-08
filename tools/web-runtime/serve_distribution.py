#!/usr/bin/env python3

from __future__ import annotations

import argparse
from functools import partial
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
from socketserver import TCPServer
import stat
import sys
from types import ModuleType
from urllib.error import HTTPError, URLError
from urllib.parse import unquote_to_bytes, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


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
    "X-Robots-Tag": "noindex, nofollow, noarchive",
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

# #901, the S11-D6 Catalog proxy, kept in step with
# `apps/web-runtime-host/deploy/cloudflare_worker.mjs`. The deployed Creator
# reaches its Catalog through a same-origin prefix so that `connect-src 'self'`
# -- the exfiltration barrier around the Projects and audio the Creator holds in
# OPFS -- never has to name a foreign origin. This server exists so the browser
# acceptance journey drives that same topology instead of a shape production
# does not use.
#
# The two properties that keep this a forwarder rather than a relay are the
# Worker's, and they are not the same kind of property.
#
# The destination is structural: it is composed from the configured upstream
# plus a literal, a member of a frozen pair, and a re-matched 64-hex digest.
# That alphabet carries no `/ \ . : @ % ? #` and no control character, so the
# only request-derived bytes in the target cannot terminate a path segment,
# introduce an authority, or change the scheme or port.
#
# The admitted grammar is a check, not a composition, and calling it structural
# would be wrong. Borrowing `catalogObjectPath`'s throw does not close it: the
# threat this design is built against is a compromised dependency in the page,
# and such code calls the prefix directly without ever reaching the transport.
# The check below is what holds in that case.
#
# With no `--catalog-upstream` the prefix answers 404 and this server behaves
# exactly as it did before, which is what every existing proof still asserts.
CATALOG_PREFIX = "soundset-catalog/"
CATALOG_INDEX_SUFFIX = "catalog/index.json"
CATALOG_OBJECT_SUFFIX = re.compile(r"\Aobject/([a-z]+)/([0-9a-f]{64})\Z")
CATALOG_OBJECT_KINDS = ("manifest", "blob")
CATALOG_OBJECT_CONTENT_TYPES = {
    "manifest": "application/json",
    "blob": "application/octet-stream",
}
MAXIMUM_CATALOG_OBJECT_BYTES = 8 * 1024 * 1024
MAXIMUM_CATALOG_INDEX_BYTES = 1024 * 1024
CATALOG_TIMEOUT_SECONDS = 30
CONTENT_LENGTH_TOKEN = re.compile(r"\A[0-9]+\Z")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
DEFAULT_PORTS = {"http": 80, "https": 443}


class _RefuseRedirect(HTTPRedirectHandler):
    """Keeps a redirecting Catalog from turning one forward into another fetch."""

    def redirect_request(self, *_arguments, **_keywords):
        return None


# The host class is deliberately narrower than WHATWG's: `new URL()` leaves
# `!"$&'()*+,;=`{}~` and a leading `.` or `-` untouched in a host, and none of
# them belongs in a Catalog address. `_` is admitted because some internal
# names really are spelled `a_b.example`. Narrower means this side refuses a
# few values production would accept, which is the safe direction and is
# asserted rather than assumed -- see `UPSTREAM_PARITY_REFUSED`.
#
# The one grammar a configured upstream must match, derived by measurement
# rather than from spec recall: the path class is exactly the ASCII characters
# `new URL()` leaves untouched inside a path, so anything the Worker would
# rewrite is outside it. Enumerating WHATWG's normalisations instead was tried
# and lost -- two review passes kept finding spellings it had missed, because a
# list of behaviours is always one behaviour behind the parser.
# Deciding what a valid upstream looks like is finite; chasing a parser is not.
# `(?:/[class]*)*/` is the classic catastrophic-backtracking shape and is not
# one here: the class excludes `/`, so each iteration must consume the
# separator and the decomposition of any input is unique -- there is nothing to
# backtrack into. Measured at 40 000 groups and a 40 000-character segment,
# both in single-digit milliseconds. Recorded so nobody "fixes" it into
# something slower.
CANONICAL_UPSTREAM = re.compile(
    r"\Ahttps?://"
    r"(?P<host>\[[^\[\]/?#%]+\]|[a-z0-9][a-z0-9._\-]*)"
    r"(?::(?P<port>[1-9][0-9]{0,4}))?"
    r"(?P<path>(?:/[A-Za-z0-9!$%&'()*+,\-.:;=@\[\]_|~]*)*/)\Z"
)


def _ends_in_a_number(host: str) -> bool:
    """WHATWG's `endsInANumber`, which is not "the whole host looks numeric".

    The distinction is the defect this replaced. A `numeric_like` test over the
    whole host missed `foo.1`, `example.1`, `foo.0x7f`, `a.0777` and `a.123`:
    WHATWG asks only whether the LAST LABEL is a number, and when it is, runs
    the IPv4 parser over the whole host and throws when that fails. So the
    Worker refused those and this side accepted and forwarded them verbatim --
    the unsound direction. A fuzz over hosts drawn from this grammar's own
    alphabet hit the class at roughly 1.7 percent, so it was not a corner.
    """
    labels = host.split(".")
    if len(labels) > 1 and labels[-1] == "":
        labels = labels[:-1]
    last = labels[-1]
    if last.isascii() and last.isdigit():
        return True
    lowered = last.lower()
    if lowered.startswith("0x"):
        rest = lowered[2:]
        return rest == "" or all(c in "0123456789abcdef" for c in rest)
    return False


def _host_is_canonical(host: str) -> bool:
    """True when `new URL()` would leave this host spelling untouched."""
    if host.startswith("["):
        # WHATWG forbids a zone identifier in an IPv6 host and throws;
        # `ipaddress` has supported scope ids since 3.9 and round-trips them,
        # so the round trip alone would accept a base production cannot express.
        if not host.endswith("]") or "%" in host:
            return False
        try:
            return f"[{ipaddress.IPv6Address(host[1:-1]).compressed}]" == host
        except ValueError:
            return False
    if _ends_in_a_number(host):
        try:
            return str(ipaddress.IPv4Address(host)) == host
        except ValueError:
            return False
    return True


def normalize_catalog_upstream(upstream: str) -> str:
    """Return the upstream base, or raise for one this server will not forward to.

    The Worker refuses any value that is not already the base it composes,
    which is a property of having a WHATWG parser. This side has none, so it
    decides the same question with a closed grammar instead. The two agree
    exactly as far as that grammar is faithful, and
    `CatalogUpstreamParityTest` is what keeps them honest about it.

    Every rejection is a `ServerError`. Nothing here may raise anything else:
    an escaping exception is not a refusal, it is a crash the proof server's
    own configuration path turns into an empty response on every request.
    """
    if not isinstance(upstream, str):
        raise ServerError("catalog upstream must be a string")
    match = CANONICAL_UPSTREAM.fullmatch(upstream)
    if match is None:
        raise ServerError("catalog upstream is not a canonical https base")
    host = match.group("host")
    if not _host_is_canonical(host):
        raise ServerError("catalog upstream host is not in canonical form")
    scheme, _, _ = upstream.partition("://")
    # `http` is admitted only for a loopback Catalog, which is what the
    # acceptance fixture is; the Worker admits `https` alone, and that is the
    # single intended disagreement between the two.
    if scheme == "http" and host not in LOOPBACK_HOSTS:
        raise ServerError("a plaintext catalog upstream must be loopback")
    path = match.group("path")
    if "//" in path:
        raise ServerError("catalog upstream path is not normalised")
    # WHATWG treats a segment as a dot segment when the whole segment is `.`
    # or `..`, in either encoded or literal form -- so `/a%2eb/` is an ordinary
    # segment and `/%2e/` is not. A substring test for `%2e` refused five
    # legitimate bases the Worker accepts.
    for segment in path.split("/"):
        if segment.lower().replace("%2e", ".") in {".", ".."}:
            raise ServerError("catalog upstream path carries a dot segment")
    port = match.group("port")
    if port is not None:
        # The grammar admits five digits, so the range is checked here rather
        # than spelled into the pattern. `int()` cannot raise: the group is
        # `[1-9][0-9]{0,4}` and nothing else reaches it.
        if not 1 <= int(port) <= 65_535:
            raise ServerError("catalog upstream port is out of range")
        if int(port) == DEFAULT_PORTS[scheme]:
            raise ServerError("catalog upstream states its scheme's default port")
    return upstream


def catalog_target(base: str, suffix: str) -> tuple[str, str, bool, int] | None:
    """Compose `(url, content_type, immutable, maximum_bytes)`, or None.

    The bound is per shape, matching `soundset_catalog.mjs`: one bound for both
    would leave this eight times more permissive than its only client for the
    index.
    """
    if suffix == CATALOG_INDEX_SUFFIX:
        return (
            f"{base}{CATALOG_INDEX_SUFFIX}",
            "application/json",
            False,
            MAXIMUM_CATALOG_INDEX_BYTES,
        )
    match = CATALOG_OBJECT_SUFFIX.match(suffix)
    if match is None:
        return None
    if match.group(1) not in CATALOG_OBJECT_KINDS:
        return None
    # Read back out of the frozen pair rather than taken from the match, so the
    # host and every path segment but the digest are this module's own literals.
    kind = CATALOG_OBJECT_KINDS[CATALOG_OBJECT_KINDS.index(match.group(1))]
    digest = match.group(2)
    return (
        f"{base}object/{kind}/{digest}",
        CATALOG_OBJECT_CONTENT_TYPES[kind],
        True,
        MAXIMUM_CATALOG_OBJECT_BYTES,
    )


def read_catalog_upstream_file(path: Path) -> str | None:
    """Read the upstream a proof run configured, or None when there is none.

    The acceptance journey owns its Catalog fixture on a kernel-assigned port
    and stops it mid-run on purpose, so the proof server cannot be told the
    upstream before it starts the way a deployment's binding tells the Worker.
    It reads it here instead, per request, from a file the lane writes.

    This is the proof server's own affordance and has no production analogue --
    but it does not weaken either property the proxy rests on. The destination
    still comes from this server's configuration and never from the request,
    and the admitted grammar is untouched.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        raw = os.read(descriptor, 4096)
    except OSError:
        return None
    finally:
        os.close(descriptor)
    try:
        candidate = raw.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        return None
    if not candidate:
        return None
    try:
        return normalize_catalog_upstream(candidate)
    except ServerError:
        return None
    except Exception:  # noqa: BLE001
        # `normalize_catalog_upstream` promises `ServerError` and nothing else.
        # If that promise ever breaks, a configured value must still be a 404
        # here rather than an exception escaping into the handler, where it
        # becomes an empty response on every request instead of a refusal.
        return None


def read_catalog_object(
    url: str, content_type: str, maximum_bytes: int
) -> tuple[int, bytes]:
    """Fetch one admitted target and return `(status, payload)` for the page.

    A missing object stays a missing object; every other upstream outcome --
    unreachable, redirecting, erroring, oversized -- is the single failure the
    transport reports as `catalog_unavailable`.
    """
    # A fresh request: none of the page's headers, cookies or credentials travel
    # upstream. The opener refuses redirects rather than following them.
    opener = build_opener(_RefuseRedirect())
    opener.addheaders = []
    request = Request(url, method="GET", headers={"Accept": content_type})
    try:
        with opener.open(request, timeout=CATALOG_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return 502, b""
            # The declared length is refused before the body is read, matching
            # the Worker. This check existed on the Worker side alone when the
            # bounded read was added, which made the remedy for one divergence
            # a sibling of it: the same upstream answered 502 in production and
            # 200 here.
            # Reproduce Fetch's `Headers.get` rather than match its rule.
            # It normalises each value and joins repeats with ", ";
            # `email.message.get` does neither, keeping trailing whitespace and
            # returning only the first of a repeated header. A strict token on
            # both sides made the two agree on the RULE while they still
            # disagreed about the STRING the rule runs on, so `  2  ` answered
            # 200 there and 502 here -- a divergence created by the commit that
            # closed two others. Third time in this work that matching a rule
            # across two runtimes failed and reproducing the other side's view
            # worked.
            values = response.headers.get_all("Content-Length")
            if values:
                declared = ", ".join(value.strip() for value in values)
                if not CONTENT_LENGTH_TOKEN.fullmatch(declared):
                    return 502, b""
                if int(declared) > maximum_bytes:
                    return 502, b""
            payload = response.read(maximum_bytes + 1)
    except HTTPError as error:
        return (404, b"") if error.code == 404 else (502, b"")
    except (URLError, OSError, ValueError):
        return 502, b""
    if len(payload) > maximum_bytes:
        return 502, b""
    return 200, payload


class ServerError(RuntimeError):
    pass


def load_verifier(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"lmdj_distribution_verifier_{hashlib.sha256(str(path).encode()).hexdigest()}",
        path,
    )
    if spec is None or spec.loader is None:
        raise ServerError("distribution verifier cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "verify_distribution") or not hasattr(module, "DistributionError"):
        raise ServerError("distribution verifier contract is invalid")
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
        if (descriptor_status.st_dev, descriptor_status.st_ino) != (
            root_status.st_dev,
            root_status.st_ino,
        ):
            return None
        directory_fd = root_fd
        for component in parts[:-1]:
            directory_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            opened.append(directory_fd)
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
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

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class ProofHandler(BaseHTTPRequestHandler):
    server_version = "LMDJWebRuntimeProof/1"

    def __init__(
        self,
        *args,
        root: Path,
        expected_hashes: dict[str, str],
        catalog_upstream: str | None = None,
        catalog_upstream_file: Path | None = None,
        verbose: bool = False,
        **kwargs,
    ) -> None:
        self.root = root
        self.expected_hashes = expected_hashes
        self.catalog_upstream = catalog_upstream
        self.catalog_upstream_file = catalog_upstream_file
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
        self.send_header("Cache-Control", "no-store")
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
        relative = decoded.removeprefix("/") or "index.html"
        if any(part in {"", ".", ".."} for part in Path(relative).parts):
            return None
        if (
            relative not in {"index.html", "host-manifest.json"}
            and HASHED_ASSET.fullmatch(relative) is None
        ):
            return None
        return relative

    def _catalog_suffix(self) -> str | None:
        """The admitted-prefix suffix, or None when this is not a Catalog path.

        The raw target is matched, never a percent-decoded one. `URL.pathname`
        in the Worker keeps its encoding, so decoding here would admit shapes
        production refuses -- `catalog%2findex.json` being the obvious one --
        and a proof server more permissive than the deployment proves nothing.
        The transport percent-encodes nothing: its targets are literals and hex.
        """
        split = urlsplit(self.path)
        relative = split.path.removeprefix("/")
        if not relative.startswith(CATALOG_PREFIX):
            return None
        # The transport issues one shape: GET, no query, no fragment. Anything
        # else under the prefix is a Catalog path this server does not admit.
        if split.query or split.fragment:
            return ""
        return relative[len(CATALOG_PREFIX):]

    def _serve_catalog(self, suffix: str, include_body: bool) -> None:
        if self.command != "GET":
            self._status(405, include_body)
            return
        upstream = self.catalog_upstream
        if upstream is None and self.catalog_upstream_file is not None:
            upstream = read_catalog_upstream_file(self.catalog_upstream_file)
        if upstream is None:
            self._status(404, include_body)
            return
        target = catalog_target(upstream, suffix)
        if target is None:
            self._status(404, include_body)
            return
        url, content_type, immutable, maximum_bytes = target
        status, payload = read_catalog_object(url, content_type, maximum_bytes)
        if status != 200:
            self._status(status, include_body)
            return
        self.send_response(200)
        # This server's content type for the shape it resolved, never the
        # upstream's: a Catalog does not get to decide how the page reads bytes.
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header(
            "Cache-Control",
            "public, max-age=31536000, immutable" if immutable else "no-store",
        )
        self.end_headers()
        if include_body and payload:
            self.wfile.write(payload)

    def _serve(self, include_body: bool) -> None:
        if self.headers.get("Range") is not None:
            self._status(404, include_body)
            return
        suffix = self._catalog_suffix()
        if suffix is not None:
            self._serve_catalog(suffix, include_body)
            return
        relative = self._select_relative()
        if relative is None:
            self._status(404, include_body)
            return
        payload = read_file_no_follow(self.root, relative)
        if payload is None or self.expected_hashes.get(relative) != hashlib.sha256(payload).hexdigest():
            self._status(404, include_body)
            return
        content_type = CONTENT_TYPES.get(Path(relative).suffix.lower())
        if content_type is None:
            self._status(404, include_body)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header(
            "Cache-Control",
            "no-store" if relative in {"index.html", "host-manifest.json"}
            else "public, max-age=31536000, immutable",
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
    root: Path,
    verifier: ModuleType,
    repo_root: Path,
    host: str = "127.0.0.1",
    port: int = 4175,
    verbose: bool = False,
    catalog_upstream: str | None = None,
    catalog_upstream_file: Path | None = None,
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
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ServerError("the proof server is loopback-only")
    if port < 0 or port > 65_535:
        raise ServerError("port must be between 0 and 65535")
    if catalog_upstream is not None and catalog_upstream_file is not None:
        raise ServerError("configure one catalog upstream, not two")
    catalog_base = (
        None if catalog_upstream is None
        else normalize_catalog_upstream(catalog_upstream)
    )
    try:
        verifier.verify_distribution(root, repo_root)
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
            catalog_upstream=catalog_base,
            catalog_upstream_file=catalog_upstream_file,
            verbose=verbose,
        ),
    )


def parse_arguments(argv: list[str], require_verifier: bool) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--verifier", required=require_verifier, type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=4175, type=int)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--catalog-upstream",
        help=(
            "absolute http(s) base of the Sound Set Catalog this server "
            "forwards to under /soundset-catalog/; omitted means the "
            "deployment offers no Catalog and the prefix answers 404"
        ),
    )
    parser.add_argument(
        "--catalog-upstream-file",
        type=Path,
        help=(
            "path a proof run writes the Catalog upstream into, read per "
            "request; for a lane whose fixture port is not known until after "
            "this server is listening"
        ),
    )
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--ready-nonce")
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    default_verifier: Path | None = None,
    default_repo_root: Path | None = None,
) -> int:
    options = parse_arguments(
        sys.argv[1:] if argv is None else argv,
        require_verifier=default_verifier is None,
    )
    verifier_path = options.verifier or default_verifier
    repo_root = options.repo_root or default_repo_root
    if verifier_path is None or repo_root is None:
        print("web proof server error: verifier and repo root are required", file=sys.stderr)
        return 2
    if (options.ready_file is None) != (options.ready_nonce is None):
        print(
            "web proof server error: --ready-file and --ready-nonce are required together",
            file=sys.stderr,
        )
        return 2
    try:
        verifier = load_verifier(verifier_path.resolve(strict=True))
        server = make_server(
            options.root,
            verifier,
            repo_root.resolve(strict=True),
            options.host,
            options.port,
            options.verbose,
            options.catalog_upstream,
            options.catalog_upstream_file,
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
            ready_path = requested_ready.parent.resolve(strict=True) / requested_ready.name
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
    raise SystemExit(main(default_repo_root=Path(__file__).resolve().parents[2]))
