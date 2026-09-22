#!/usr/bin/env python3
"""Verify Cloudflare responses against an independently verified Release dist.

This emits migration observations, not the Netlify deployment evidence Contract.
Encoded dot segments may be rejected at the edge or normalized by the local
emulator. A normalized response must match the signed index exactly.
Unknown paths must still return 404.
"""

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import build_opener


def validate_target(host_id: str, base_url: str, preview: bool, recovery_target: bool, initialization_target: bool = False) -> str:
    worker = {"creator-web": "creator", "web-runtime-host": "lab"}[host_id]
    if recovery_target and initialization_target:
        raise ValueError("select only one isolated target kind")
    if initialization_target:
        worker += "-initialization"
    if recovery_target:
        worker += "-recovery"
    host = urlsplit(base_url).hostname
    if host in {f"{worker}.lmdj.workers.dev", "127.0.0.1"}:
        return worker
    if preview and host and re.fullmatch(r"[0-9a-f]{8}-" + re.escape(worker) + r"\.lmdj\.workers\.dev", host):
        return worker
    raise ValueError("unexpected Host target; use the configured workers.dev hostname and explicit isolated target flag")


def _shared(preview=False):
    # Each call gets its own header policy; Preview allowances never leak to production.
    tool = Path(__file__).resolve().parent / "deployment_smoke.py"
    spec = importlib.util.spec_from_file_location("cloudflare_host_http", tool)
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    if preview:
        shared.REQUIRED_ROBOTS_DIRECTIVES = frozenset({"noindex"})
        shared.REQUIRED_SECURITY_HEADERS["x-robots-tag"] = "noindex"
    return shared


def _traversal(shared, opener, *, url, path, timeout_seconds, index_sha256):
    try:
        shared._require_traversal_rejection(opener, url=url, path=path,
                                           timeout_seconds=timeout_seconds)
    except shared.SmokeError:
        # Preserve the existing Cloudflare fixed edge page allowance.
        try:
            response = opener.open(shared._request(url, "no-store"), timeout=timeout_seconds)
            response.close()
        except HTTPError as error:
            try:
                body = error.read(4097)
            finally:
                error.close()
            template = ("<html><head><title>400 Bad Request</title></head>"
                        "<body><center><h1>400 Bad Request</h1></center>"
                        "<hr><center>cloudflare</center></body></html>")
            compact = "".join(body.decode("utf-8", errors="replace").split())
            if error.code == 400 and compact == "".join(template.split()):
                return "rejected with Cloudflare's fixed 400 error page"
        body, _ = shared._fetch(opener, url=url, label=path, content_type="text/html",
            cache_control="no-store", limit=shared.MAX_INDEX_BYTES,
            timeout_seconds=timeout_seconds)
        if hashlib.sha256(body).hexdigest() != index_sha256:
            raise shared.SmokeError("why: encoded dot path differs from verified Release bytes; remedy: reconcile the origin with the frozen index")
        return "normalized to exact verified index"
    return "rejected with validated 400 or 404"


def smoke_frozen(*, base_url, host_id, product_build, host_version,
                 index_sha256, manifest_sha256, preview=False):
    """Fresh complete HTTP proof rooted in authenticated entry-file digests."""
    validate_target(host_id, base_url, preview, False)
    shared = _shared(preview)
    if any(not isinstance(value, str) or shared.HASH_PATTERN.fullmatch(value) is None
           for value in (index_sha256, manifest_sha256)):
        raise shared.SmokeError("why: frozen entry digests are missing or invalid; remedy: supply both authenticated release SHA-256 values")
    def traversal(opener, **arguments):
        return _traversal(shared, opener, **arguments, index_sha256=index_sha256)
    return shared.smoke_http(base_url=base_url, expected_host_id=host_id,
        expected_product_build=product_build, expected_host_version=host_version,
        expected_index_sha256=index_sha256, expected_manifest_sha256=manifest_sha256,
        require_https=True, timeout_seconds=10, traversal_check=traversal)


def smoke(dist: Path, base_url: str, preview: bool = False, recovery_target: bool = False, initialization_target: bool = False) -> dict:
    shared = _shared(preview)
    manifest = json.loads((dist / "host-manifest.json").read_text())
    host_id = manifest["host_id"]
    validate_target(host_id, base_url, preview, recovery_target, initialization_target)
    host = urlsplit(base_url).hostname
    root = shared._validated_base_url(
        base_url, require_https=host != "127.0.0.1", timeout_seconds=30
    )
    manifest = json.loads((dist / "host-manifest.json").read_text())
    assets = shared._validate_manifest(
        manifest, expected_product_build=manifest["product_build"],
        expected_host_version=manifest["host_version"], expected_host_id=host_id,
    )
    opener = build_opener(shared.RedirectGuard())
    opener.addheaders = []
    checks = [("", "index.html", "text/html", "no-store"),
              ("index.html", "index.html", "text/html", "no-store"),
              ("host-manifest.json", "host-manifest.json", "application/json", "no-store")]
    checks += [(a["path"], a["path"], shared.CONTENT_TYPES[Path(a["path"]).suffix],
                shared.IMMUTABLE_CACHE) for a in assets]
    checks.append(("%2e%2e/index.html", "index.html", "text/html", "no-store"))
    digests = {}
    traversal = "normalized to exact verified index"
    for request_path, file_path, mime, cache in checks:
        if request_path == "%2e%2e/index.html":
            traversal = _traversal(shared, opener, url=root + request_path,
                path="/" + request_path, timeout_seconds=30,
                index_sha256=hashlib.sha256((dist / "index.html").read_bytes()).hexdigest())
            if traversal == "normalized to exact verified index":
                digests["/" + request_path] = hashlib.sha256((dist / "index.html").read_bytes()).hexdigest()
            continue
        body, final_url = shared._fetch(
            opener, url=root + request_path, label="/" + request_path,
            content_type=mime, cache_control=cache,
            limit=shared.MAX_ASSET_BYTES, timeout_seconds=30,
        )
        if body != (dist / file_path).read_bytes():
            raise shared.SmokeError(f"/{request_path} differs from verified Release bytes")
        digests["/" + request_path] = hashlib.sha256(body).hexdigest()
    for path in shared.NEGATIVE_PATHS:
        shared._require_negative(opener, url=root.rstrip("/") + path,
                                 path=path, timeout_seconds=30)
    return {"url": base_url, "product_build": manifest["product_build"],
            "host_version": manifest["host_version"], "preview": preview,
            "recovery_target": recovery_target, "initialization_target": initialization_target,
            "file_digests": digests, "unknown_paths": "404",
            "encoded_dot_segments": traversal,
            "status": "passed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verified_dist", type=Path)
    parser.add_argument("base_url")
    parser.add_argument("--preview", action="store_true")
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument("--initialization-target", action="store_true", help="require the fixed Host initialization test Worker")
    targets.add_argument("--recovery-target", action="store_true", help="require creator-recovery or lab-recovery instead of the official Worker")
    args = parser.parse_args()
    print(json.dumps(smoke(args.verified_dist, args.base_url, args.preview, args.recovery_target, args.initialization_target), indent=2))
