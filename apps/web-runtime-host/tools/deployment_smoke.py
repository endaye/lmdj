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
REQUIRED_ROBOTS_DIRECTIVES = frozenset(("noindex", "nofollow", "noarchive"))
MANIFEST_KEYS = {
    "assets",
    "distribution_contract",
    "emscripten",
    "heap_bytes",
    "host_id",
    "host_version",
    "manifest_version",
    "platform_version",
    "product_build",
    "protocol_version",
    "resource_limits",
}
LEGACY_MANIFEST_KEYS = MANIFEST_KEYS - {"host_id", "platform_version"}
CONTENT_TYPES = {
    ".css": "text/css",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".wasm": "application/wasm",
}
EQUIVALENT_MEDIA_TYPES = {
    "text/javascript": frozenset(("text/javascript", "application/javascript")),
}
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
HASHED_ASSET_PATTERN = re.compile(
    r"^assets/[a-z0-9-]+\.([0-9a-f]{64})\.(?:css|js|mjs|wasm)$"
)
ALLOWED_ASSET_ROLES = frozenset(
    (
        "host_main",
        "host_module",
        "host_style",
        "platform_module",
        "product_identity",
        "runtime_script",
        "runtime_wasm",
    )
)
SINGLETON_ASSET_ROLES = frozenset(
    ("host_main", "host_style", "runtime_script", "runtime_wasm")
)
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
)
TRAVERSAL_PATH = "/%2e%2e/index.html"


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
    def __init__(self, *, root_url: str | None = None) -> None:
        super().__init__()
        self.root_url = root_url
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
        _require_cache_control(
            headers,
            expected=expected_cache,
            label="redirect response",
        )
        if self.root_url is None:
            raise SmokeError("redirect is forbidden")
        request_url = urlsplit(req.full_url)
        target_url = urlsplit(newurl)
        if (
            self.redirect_count != 0
            or req.full_url != self.root_url
            or request_url.path != "/"
            or request_url.query
            or request_url.fragment
            or target_url.path != "/index.html"
            or target_url.query
            or target_url.fragment
            or target_url.username is not None
            or target_url.password is not None
        ):
            raise SmokeError("redirect is forbidden")
        self.redirect_count += 1
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


def _require_cache_control(headers, *, expected: str, label: str) -> None:
    observed = _header_values(headers, "cache-control")
    normalized = []
    if len(observed) == 1:
        normalized = [
            ", ".join(directive.strip() for directive in observed[0].split(","))
        ]
    if normalized != [expected]:
        raise SmokeError(
            f"{label} cache-control mismatch: expected {[expected]!r}, "
            f"got {observed!r}"
        )


def _require_robots_directives(headers, label: str) -> None:
    observed = _header_values(headers, "x-robots-tag")
    directives = [
        directive.strip()
        for value in observed
        for directive in value.split(",")
    ]
    if (
        not directives
        or any(not directive for directive in directives)
        or set(directives) != REQUIRED_ROBOTS_DIRECTIVES
    ):
        expected = REQUIRED_SECURITY_HEADERS["x-robots-tag"]
        raise SmokeError(
            f"{label} x-robots-tag mismatch: expected {[expected]!r}, "
            f"got {observed!r}"
        )


def _validate_headers(headers, label: str) -> None:
    for name, expected in REQUIRED_SECURITY_HEADERS.items():
        if name == "x-robots-tag":
            _require_robots_directives(headers, label)
            continue
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
    accepted = EQUIVALENT_MEDIA_TYPES.get(expected, frozenset((expected,)))
    if media_type not in accepted:
        raise SmokeError(
            f"{label} content-type mismatch: expected one of {sorted(accepted)!r}, "
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
) -> tuple[bytes, str]:
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
            _require_cache_control(
                response.headers,
                expected=cache_control,
                label=label,
            )
            return (
                _read_bounded(response, limit=limit, label=label),
                response.geturl(),
            )
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
                _require_cache_control(
                    response.headers,
                    expected="no-store",
                    label=path,
                )
    except HTTPError as error:
        try:
            _validate_headers(error.headers, path)
            status = error.code
            error.read(1)
            if status == 404:
                _require_cache_control(
                    error.headers,
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


def _require_traversal_rejection(
    opener, *, url: str, path: str, timeout_seconds: float
) -> None:
    request = _request(url, "no-store")
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = response.status
            headers = response.headers
            body = response.read(1)
    except HTTPError as error:
        try:
            status = error.code
            headers = error.headers
            body = error.read(1)
        finally:
            error.close()
    except SmokeError:
        raise
    except (OSError, URLError):
        raise SmokeError(f"{path} request failed") from None
    if status == 404:
        _validate_headers(headers, path)
        _require_cache_control(headers, expected="no-store", label=path)
        return
    if status != 400:
        raise SmokeError(f"{path} returned HTTP {status}, expected 400 or 404")
    if body:
        raise SmokeError(f"{path} returned a non-empty response body")


def _manifest_identity(manifest: object) -> tuple[str, str]:
    if (
        not isinstance(manifest, dict)
        or set(manifest) not in (MANIFEST_KEYS, LEGACY_MANIFEST_KEYS)
    ):
        raise SmokeError("manifest root schema is invalid")
    if manifest["distribution_contract"] != "lmdj.web-runtime-host.distribution.v1":
        raise SmokeError("manifest distribution identity is invalid")
    if manifest["manifest_version"] != 1:
        raise SmokeError("manifest version is invalid")
    product_build = manifest["product_build"]
    host_version = manifest["host_version"]
    if not isinstance(product_build, str) or not product_build:
        raise SmokeError("Product Build identity is invalid")
    if not isinstance(host_version, str) or not host_version:
        raise SmokeError("Host version identity is invalid")
    if set(manifest) == MANIFEST_KEYS and (
        not isinstance(manifest["host_id"], str)
        or not manifest["host_id"]
        or not isinstance(manifest["platform_version"], str)
        or not manifest["platform_version"]
    ):
        raise SmokeError("manifest extended identity is invalid")
    return product_build, host_version


def _validate_manifest(
    manifest: object,
    *,
    expected_product_build: str,
    expected_host_version: str,
) -> list[dict[str, object]]:
    product_build, host_version = _manifest_identity(manifest)
    if product_build != expected_product_build:
        raise SmokeError(
            f"Product Build mismatch: expected {expected_product_build!r}, "
            f"got {product_build!r}"
        )
    if host_version != expected_host_version:
        raise SmokeError(
            f"Host version mismatch: expected {expected_host_version!r}, "
            f"got {host_version!r}"
        )
    assert isinstance(manifest, dict)
    legacy_manifest = set(manifest) == LEGACY_MANIFEST_KEYS
    assets = manifest["assets"]
    if not isinstance(assets, list) or not assets:
        raise SmokeError("manifest asset inventory is invalid")
    validated: list[dict[str, object]] = []
    seen: set[str] = set()
    role_counts = {role: 0 for role in ALLOWED_ASSET_ROLES}
    for entry in assets:
        if not isinstance(entry, dict) or set(entry) != {
            "bytes", "path", "role", "sha256"
        }:
            raise SmokeError("manifest asset inventory entry is invalid")
        path = entry["path"]
        digest = entry["sha256"]
        size = entry["bytes"]
        role = entry["role"]
        path_match = (
            HASHED_ASSET_PATTERN.fullmatch(path)
            if isinstance(path, str)
            else None
        )
        if (
            path_match is None
            or not isinstance(digest, str)
            or HASH_PATTERN.fullmatch(digest) is None
            or path_match.group(1) != digest
            or not isinstance(role, str)
            or role not in ALLOWED_ASSET_ROLES
            or path in seen
        ):
            raise SmokeError("manifest asset inventory is invalid")
        if type(size) is not int or size < 1 or size > MAX_ASSET_BYTES:
            raise SmokeError(f"manifest asset bytes are invalid: {path}")
        seen.add(path)
        role_counts[role] += 1
        validated.append(entry)
    if any(role_counts[role] != 1 for role in SINGLETON_ASSET_ROLES):
        raise SmokeError("manifest required asset role inventory is invalid")
    if role_counts["host_module"] < 1:
        raise SmokeError("manifest required asset role inventory is invalid")
    if legacy_manifest and role_counts["platform_module"] != 0:
        raise SmokeError("manifest required asset role inventory is invalid")
    if not legacy_manifest and role_counts["platform_module"] < 1:
        raise SmokeError("manifest required asset role inventory is invalid")
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


def _validated_base_url(
    base_url: str,
    *,
    require_https: bool,
    timeout_seconds: float,
) -> str:
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
    return base_url.rstrip("/") + "/"


def _decode_manifest(manifest_bytes: bytes) -> object:
    try:
        return json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SmokeError("manifest is not valid UTF-8 JSON") from None


def discover_http_identity(
    *,
    base_url: str,
    require_https: bool = True,
    timeout_seconds: float = 10.0,
) -> dict[str, str]:
    """Strictly read the published manifest identity before a deployment smoke."""
    root = _validated_base_url(
        base_url,
        require_https=require_https,
        timeout_seconds=timeout_seconds,
    )
    opener = build_opener(RedirectGuard())
    opener.addheaders = []
    manifest_bytes, _ = _fetch(
        opener,
        url=urljoin(root, "host-manifest.json"),
        label="/host-manifest.json",
        content_type="application/json",
        cache_control="no-store",
        limit=MAX_MANIFEST_BYTES,
        timeout_seconds=timeout_seconds,
    )
    manifest = _decode_manifest(manifest_bytes)
    product_build, host_version = _manifest_identity(manifest)
    _validate_manifest(
        manifest,
        expected_product_build=product_build,
        expected_host_version=host_version,
    )
    return {
        "host_version": host_version,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "product_build": product_build,
    }


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
    root = _validated_base_url(
        base_url,
        require_https=require_https,
        timeout_seconds=timeout_seconds,
    )
    _, hostname, _ = _origin(base_url)
    if not expected_product_build or not expected_host_version:
        raise SmokeError("expected Product Build and Host version are required")
    if expected_deploy_id is not None:
        if DEPLOY_ID_PATTERN.fullmatch(expected_deploy_id) is None:
            raise SmokeError("expected Deploy ID is invalid")
        if not hostname.startswith(expected_deploy_id.lower() + "--"):
            raise SmokeError("immutable URL does not identify the expected Deploy ID")

    root_redirect_guard = RedirectGuard(root_url=root)
    root_opener = build_opener(root_redirect_guard)
    root_opener.addheaders = []
    root_index_bytes, root_final_url = _fetch(
        root_opener,
        url=root,
        label="/",
        content_type="text/html",
        cache_control="no-store",
        limit=MAX_INDEX_BYTES,
        timeout_seconds=timeout_seconds,
    )
    root_final_path = urlsplit(root_final_url).path
    if root_final_path not in {"/", "/index.html"}:
        raise SmokeError("root final path is invalid")

    redirect_guard = RedirectGuard()
    opener = build_opener(redirect_guard)
    opener.addheaders = []
    index_bytes, _ = _fetch(
        opener,
        url=urljoin(root, "index.html"),
        label="/index.html",
        content_type="text/html",
        cache_control="no-store",
        limit=MAX_INDEX_BYTES,
        timeout_seconds=timeout_seconds,
    )
    if root_index_bytes != index_bytes:
        raise SmokeError("root index identity does not match /index.html")
    manifest_bytes, _ = _fetch(
        opener,
        url=urljoin(root, "host-manifest.json"),
        label="/host-manifest.json",
        content_type="application/json",
        cache_control="no-store",
        limit=MAX_MANIFEST_BYTES,
        timeout_seconds=timeout_seconds,
    )
    try:
        index = root_index_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise SmokeError("index is not UTF-8") from None
    manifest = _decode_manifest(manifest_bytes)
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
        payload, _ = _fetch(
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
    _require_traversal_rejection(
        opener,
        url=root.rstrip("/") + TRAVERSAL_PATH,
        path=TRAVERSAL_PATH,
        timeout_seconds=timeout_seconds,
    )

    result: dict[str, object] = {
        "asset_count": len(assets),
        "host_version": expected_host_version,
        "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
        "manifest_sha256": manifest_digest,
        "product_build": expected_product_build,
        "root_final_path": root_final_path,
        "root_redirect_count": root_redirect_guard.redirect_count,
        "root_request_path": "/",
    }
    if expected_deploy_id is not None:
        result["deploy_id"] = expected_deploy_id
    return result


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    if argv and argv[0] == "discover-identity":
        parser = argparse.ArgumentParser(
            description="Strictly discover published Web Runtime Host identity"
        )
        parser.add_argument("base_url")
        parser.add_argument("--allow-http", action="store_true")
        parser.add_argument("--timeout", type=float, default=10.0)
        options = parser.parse_args(argv[1:])
        options.command = "discover-identity"
        return options
    parser = argparse.ArgumentParser(
        description="Validate an immutable published Web Runtime Host"
    )
    parser.add_argument("base_url")
    parser.add_argument("expected_product_build")
    parser.add_argument("expected_host_version")
    parser.add_argument("--expected-deploy-id")
    parser.add_argument("--allow-http", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    options = parser.parse_args(argv)
    options.command = "smoke"
    return options


def main(argv: list[str] | None = None) -> int:
    options = parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        if options.command == "discover-identity":
            result = discover_http_identity(
                base_url=options.base_url,
                require_https=not options.allow_http,
                timeout_seconds=options.timeout,
            )
        else:
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
