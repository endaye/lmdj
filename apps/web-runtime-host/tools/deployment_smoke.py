#!/usr/bin/env python3

from __future__ import annotations

import argparse
import codecs
import hashlib
import ipaddress
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


CSP = (
    "default-src 'none'; base-uri 'none'; object-src 'none'; "
    "frame-ancestors 'none'; form-action 'none'; "
    "script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
    "child-src 'self' blob:; connect-src 'self'; style-src 'self'; "
    "img-src 'self'; media-src 'self' blob:; manifest-src 'self'"
)
REQUIRED_SECURITY_HEADERS = {
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-embedder-policy": "require-corp",
    "cross-origin-resource-policy": "same-origin",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, nofollow, noarchive",
}
EXPECTED_ASSETS = (
    ("assets/diagnostic-project.", ".mjs", "host_module"),
    ("assets/input-adapters.", ".mjs", "host_module"),
    ("assets/main.", ".mjs", "host_main"),
    ("assets/preflight.", ".mjs", "host_module"),
    ("assets/protocol.", ".mjs", "host_module"),
    ("assets/runtime.", ".js", "runtime_script"),
    ("assets/runtime.", ".wasm", "runtime_wasm"),
    ("assets/state-machine.", ".mjs", "host_module"),
    ("assets/styles.", ".css", "host_style"),
)
MANIFEST_KEYS = {
    "assets",
    "distribution_contract",
    "emscripten",
    "heap_bytes",
    "host_version",
    "manifest_version",
    "product_build",
    "protocol_version",
    "resource_limits",
}
CONTENT_TYPES = {
    ".css": "text/css",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".wasm": "application/wasm",
}
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DEPLOY_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_REDIRECTS = 5
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
NEGATIVE_PATHS = (
    "/src/main.mjs",
    "/missing",
    "/assets/missing.map",
    "/%2e%2e/index.html",
)


class SmokeError(RuntimeError):
    pass


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise SmokeError("URL must use HTTP or HTTPS with a hostname")
    try:
        port = parsed.port
    except ValueError as error:
        raise SmokeError("URL port is invalid") from error
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme, parsed.hostname.lower(), port


class RedirectGuard(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old_origin = _origin(req.full_url)
        new_origin = _origin(newurl)
        if old_origin[0] == "https" and new_origin[0] == "http":
            raise SmokeError("HTTPS downgrade redirect is forbidden")
        if old_origin != new_origin:
            raise SmokeError("cross-origin redirect is forbidden")
        _validate_headers(headers, "redirect response")
        expected_cache = getattr(req, "lmdj_expected_cache", None)
        if expected_cache is None:
            raise SmokeError("redirect request cache contract is missing")
        _require_header(
            headers,
            name="cache-control",
            expected=expected_cache,
            label="redirect response",
        )
        self.redirect_count += 1
        if self.redirect_count > MAX_REDIRECTS:
            raise SmokeError("redirect limit exceeded")
        redirected = super().redirect_request(
            req, fp, code, msg, headers, newurl
        )
        if redirected is not None:
            redirected.lmdj_expected_cache = expected_cache
        return redirected


def _header_values(headers, name: str) -> list[str]:
    if hasattr(headers, "get_all"):
        return headers.get_all(name) or []
    value = headers.get(name)
    return [] if value is None else [value]


def _require_header(headers, *, name: str, expected: str, label: str) -> None:
    observed = _header_values(headers, name)
    if observed != [expected]:
        raise SmokeError(
            f"{label} {name} mismatch: expected {[expected]!r}, got {observed!r}"
        )


def _validate_headers(headers, label: str) -> None:
    for name, expected in REQUIRED_SECURITY_HEADERS.items():
        _require_header(headers, name=name, expected=expected, label=label)
    _require_header(
        headers,
        name="content-security-policy",
        expected=CSP,
        label=label,
    )


def _optional_single_header(headers, name: str, label: str) -> str | None:
    values = _header_values(headers, name)
    if len(values) > 1:
        raise SmokeError(f"{label} {name} must occur at most once")
    return values[0] if values else None


def _parse_content_type(value: str, label: str) -> tuple[str, dict[str, str]]:
    parts = value.split(";")
    media_type = parts[0].strip().lower()
    if not media_type or "/" not in media_type:
        raise SmokeError(f"{label} content-type is invalid")
    parameters: dict[str, str] = {}
    for raw_parameter in parts[1:]:
        parameter = raw_parameter.strip()
        if not parameter or "=" not in parameter:
            raise SmokeError(f"{label} content-type parameters are invalid")
        name, raw_value = parameter.split("=", 1)
        name = name.strip().lower()
        raw_value = raw_value.strip()
        if (
            not name
            or name in parameters
            or not raw_value
            or (raw_value.startswith('"') != raw_value.endswith('"'))
        ):
            raise SmokeError(f"{label} content-type parameters are invalid")
        if raw_value.startswith('"'):
            raw_value = raw_value[1:-1]
            if not raw_value or '"' in raw_value:
                raise SmokeError(f"{label} content-type parameters are invalid")
        parameters[name] = raw_value
    return media_type, parameters


def _validate_content_type(headers, *, expected: str, label: str) -> None:
    values = _header_values(headers, "content-type")
    if len(values) != 1:
        raise SmokeError(
            f"{label} content-type mismatch: expected one value, got {values!r}"
        )
    media_type, parameters = _parse_content_type(values[0], label)
    if media_type != expected:
        raise SmokeError(
            f"{label} content-type mismatch: expected {expected!r}, "
            f"got {media_type!r}"
        )
    if media_type == "application/wasm":
        if parameters:
            raise SmokeError(f"{label} content-type parameters are invalid")
        return
    if set(parameters) - {"charset"}:
        raise SmokeError(f"{label} content-type parameters are invalid")
    charset = parameters.get("charset")
    if charset is None:
        if media_type != "application/json":
            raise SmokeError(f"{label} content-type charset is missing")
        return
    try:
        normalized_charset = codecs.lookup(charset).name
    except LookupError:
        raise SmokeError(f"{label} content-type charset is invalid") from None
    if normalized_charset != "utf-8":
        raise SmokeError(f"{label} content-type charset is invalid")


def _request(url: str, cache_control: str) -> Request:
    request = Request(url, headers={"Accept-Encoding": "identity"})
    request.lmdj_expected_cache = cache_control
    return request


def _read_bounded(response, *, limit: int, label: str) -> bytes:
    content_length = _optional_single_header(
        response.headers, "content-length", label
    )
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as error:
            raise SmokeError(f"{label} content-length is invalid") from error
        if declared < 0 or declared > limit:
            raise SmokeError(f"{label} response exceeds size limit")
    payload = response.read(limit + 1)
    if len(payload) > limit:
        raise SmokeError(f"{label} response exceeds size limit")
    if content_length is not None and len(payload) != declared:
        raise SmokeError(f"{label} content-length mismatch")
    return payload


def _fetch(
    opener,
    *,
    url: str,
    label: str,
    content_type: str,
    cache_control: str,
    limit: int,
    timeout_seconds: float,
) -> bytes:
    try:
        with opener.open(
            _request(url, cache_control),
            timeout=timeout_seconds,
        ) as response:
            if response.status != 200:
                raise SmokeError(f"{label} returned HTTP {response.status}")
            _validate_headers(response.headers, label)
            _validate_content_type(
                response.headers, expected=content_type, label=label
            )
            _require_header(
                response.headers,
                name="cache-control",
                expected=cache_control,
                label=label,
            )
            return _read_bounded(response, limit=limit, label=label)
    except SmokeError:
        raise
    except HTTPError as error:
        error.close()
        raise SmokeError(f"{label} returned HTTP {error.code}") from None
    except (OSError, URLError) as error:
        raise SmokeError(f"{label} request failed") from None


def _require_negative(
    opener, *, url: str, path: str, timeout_seconds: float
) -> None:
    request = _request(url, "no-store")
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = response.status
            _validate_headers(response.headers, path)
            response.read(1)
            if status == 404:
                _require_header(
                    response.headers,
                    name="cache-control",
                    expected="no-store",
                    label=path,
                )
    except HTTPError as error:
        try:
            _validate_headers(error.headers, path)
            status = error.code
            error.read(1)
            if status == 404:
                _require_header(
                    error.headers,
                    name="cache-control",
                    expected="no-store",
                    label=path,
                )
        finally:
            error.close()
    except SmokeError:
        raise
    except (OSError, URLError):
        raise SmokeError(f"{path} request failed") from None
    if status != 404:
        raise SmokeError(f"{path} returned HTTP {status}, expected 404")


def _validate_manifest(
    manifest: object,
    *,
    expected_product_build: str,
    expected_host_version: str,
) -> list[dict[str, object]]:
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise SmokeError("manifest root schema is invalid")
    if manifest["distribution_contract"] != "lmdj.web-runtime-host.distribution.v1":
        raise SmokeError("manifest distribution identity is invalid")
    if manifest["manifest_version"] != 1:
        raise SmokeError("manifest version is invalid")
    if manifest["product_build"] != expected_product_build:
        raise SmokeError(
            f"Product Build mismatch: expected {expected_product_build!r}, "
            f"got {manifest['product_build']!r}"
        )
    if manifest["host_version"] != expected_host_version:
        raise SmokeError(
            f"Host version mismatch: expected {expected_host_version!r}, "
            f"got {manifest['host_version']!r}"
        )
    assets = manifest["assets"]
    if not isinstance(assets, list) or len(assets) != len(EXPECTED_ASSETS):
        raise SmokeError("manifest asset inventory is invalid")
    validated: list[dict[str, object]] = []
    seen: set[str] = set()
    for entry, (prefix, suffix, role) in zip(assets, EXPECTED_ASSETS, strict=True):
        if not isinstance(entry, dict) or set(entry) != {
            "bytes", "path", "role", "sha256"
        }:
            raise SmokeError("manifest asset inventory entry is invalid")
        path = entry["path"]
        digest = entry["sha256"]
        size = entry["bytes"]
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or HASH_PATTERN.fullmatch(digest) is None
            or path != f"{prefix}{digest}{suffix}"
            or entry["role"] != role
            or path in seen
        ):
            raise SmokeError("manifest asset inventory is invalid")
        if type(size) is not int or size < 1 or size > MAX_ASSET_BYTES:
            raise SmokeError(f"manifest asset bytes are invalid: {path}")
        seen.add(path)
        validated.append(entry)
    return validated


def _require_exact_once(text: str, fragment: str, label: str) -> None:
    if text.count(fragment) != 1:
        raise SmokeError(f"index {label} mismatch")


def _is_loopback_host(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def smoke_http(
    *,
    base_url: str,
    expected_product_build: str,
    expected_host_version: str,
    expected_deploy_id: str | None = None,
    require_https: bool = True,
    timeout_seconds: float = 10.0,
) -> dict[str, object]:
    """Validate index, manifest, every declared asset, and negative routes."""
    parsed = urlsplit(base_url)
    scheme, hostname, _ = _origin(base_url)
    if require_https and scheme != "https":
        raise SmokeError("HTTPS base URL is required")
    if scheme == "http" and not _is_loopback_host(hostname):
        raise SmokeError("cleartext HTTP is allowed only for a loopback target")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise SmokeError("base URL must be an origin without credentials, path, query, or fragment")
    if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 60:
        raise SmokeError("timeout must be greater than zero and at most 60 seconds")
    if not expected_product_build or not expected_host_version:
        raise SmokeError("expected Product Build and Host version are required")
    if expected_deploy_id is not None:
        if DEPLOY_ID_PATTERN.fullmatch(expected_deploy_id) is None:
            raise SmokeError("expected Deploy ID is invalid")
        if not hostname.startswith(expected_deploy_id.lower() + "--"):
            raise SmokeError("immutable URL does not identify the expected Deploy ID")

    root = base_url.rstrip("/") + "/"
    redirect_guard = RedirectGuard()
    opener = build_opener(redirect_guard)
    opener.addheaders = []
    index_bytes = _fetch(
        opener,
        url=urljoin(root, "index.html"),
        label="/index.html",
        content_type="text/html",
        cache_control="no-store",
        limit=MAX_INDEX_BYTES,
        timeout_seconds=timeout_seconds,
    )
    manifest_bytes = _fetch(
        opener,
        url=urljoin(root, "host-manifest.json"),
        label="/host-manifest.json",
        content_type="application/json",
        cache_control="no-store",
        limit=MAX_MANIFEST_BYTES,
        timeout_seconds=timeout_seconds,
    )
    try:
        index = index_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise SmokeError("index is not UTF-8") from None
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SmokeError("manifest is not valid UTF-8 JSON") from None
    assets = _validate_manifest(
        manifest,
        expected_product_build=expected_product_build,
        expected_host_version=expected_host_version,
    )
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    _require_exact_once(
        index,
        f'<meta name="lmdj-host-manifest-sha256" content="{manifest_digest}">',
        "manifest digest",
    )
    for fragment, label in (
        ('<meta name="lmdj-host-manifest-path" content="./host-manifest.json">', "manifest path"),
        (f'<meta name="lmdj-product-build" content="{expected_product_build}">', "Product Build"),
        (f'<meta name="lmdj-host-version" content="{expected_host_version}">', "Host version"),
    ):
        _require_exact_once(index, fragment, label)

    for entry in assets:
        path = str(entry["path"])
        suffix = next(suffix for suffix in CONTENT_TYPES if path.endswith(suffix))
        payload = _fetch(
            opener,
            url=urljoin(root, path),
            label="/" + path,
            content_type=CONTENT_TYPES[suffix],
            cache_control=IMMUTABLE_CACHE,
            limit=int(entry["bytes"]),
            timeout_seconds=timeout_seconds,
        )
        if len(payload) != entry["bytes"]:
            raise SmokeError(f"asset size mismatch: {path}")
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise SmokeError(f"asset digest mismatch: {path}")

    main = next(entry for entry in assets if entry["role"] == "host_main")
    style = next(entry for entry in assets if entry["role"] == "host_style")
    _require_exact_once(index, f'src="./{main["path"]}"', "main asset binding")
    _require_exact_once(index, f'href="./{style["path"]}"', "style asset binding")

    for path in NEGATIVE_PATHS:
        _require_negative(
            opener,
            url=root.rstrip("/") + path,
            path=path,
            timeout_seconds=timeout_seconds,
        )

    result: dict[str, object] = {
        "asset_count": len(assets),
        "host_version": expected_host_version,
        "product_build": expected_product_build,
    }
    if expected_deploy_id is not None:
        result["deploy_id"] = expected_deploy_id
    return result


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an immutable published Web Runtime Host"
    )
    parser.add_argument("base_url")
    parser.add_argument("expected_product_build")
    parser.add_argument("expected_host_version")
    parser.add_argument("--expected-deploy-id")
    parser.add_argument("--allow-http", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        result = smoke_http(
            base_url=options.base_url,
            expected_product_build=options.expected_product_build,
            expected_host_version=options.expected_host_version,
            expected_deploy_id=options.expected_deploy_id,
            require_https=not options.allow_http,
            timeout_seconds=options.timeout,
        )
    except SmokeError as error:
        print(f"web deployment smoke error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
