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
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import build_opener


def smoke(dist: Path, base_url: str, preview: bool = False) -> dict:
    tool = Path(__file__).resolve().parents[2] / "web-runtime-host/tools/deployment_smoke.py"
    spec = importlib.util.spec_from_file_location("cloudflare_host_http", tool)
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    host = urlsplit(base_url).hostname
    if host not in {"creator.lmdj.workers.dev", "127.0.0.1"} and not (
        preview and host and host.endswith("-creator.lmdj.workers.dev")
    ):
        raise ValueError("unexpected Creator target")
    if preview:
        shared.REQUIRED_ROBOTS_DIRECTIVES = frozenset({"noindex"})
        shared.REQUIRED_SECURITY_HEADERS["x-robots-tag"] = "noindex"
    root = shared._validated_base_url(
        base_url, require_https=host != "127.0.0.1", timeout_seconds=30
    )
    manifest = json.loads((dist / "host-manifest.json").read_text())
    assets = shared._validate_manifest(
        manifest, expected_product_build=manifest["product_build"],
        expected_host_version=manifest["host_version"], expected_host_id="creator-web",
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
            try:
                shared._require_traversal_rejection(
                    opener, url=root + request_path, path="/" + request_path,
                    timeout_seconds=30,
                )
            except shared.SmokeError:
                # Cloudflare's edge 400 includes its fixed error page, while
                # the original Netlify probe requires an empty 400 body.
                try:
                    response = opener.open(shared._request(root + request_path, "no-store"), timeout=30)
                    response.close()
                except HTTPError as error:
                    body = error.read(4097)
                    error.close()
                    template = ("<html><head><title>400 Bad Request</title></head>"
                                "<body><center><h1>400 Bad Request</h1></center>"
                                "<hr><center>cloudflare</center></body></html>")
                    compact = "".join(body.decode("utf-8", errors="replace").split())
                    if error.code == 400 and compact == "".join(template.split()):
                        traversal = "rejected with Cloudflare's fixed 400 error page"
                        continue
                # Otherwise a normalized 200 must pass the byte check below.
            else:
                traversal = "rejected with validated 400 or 404"
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
            "file_digests": digests, "unknown_paths": "404",
            "encoded_dot_segments": traversal,
            "status": "passed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verified_dist", type=Path)
    parser.add_argument("base_url")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    print(json.dumps(smoke(args.verified_dist, args.base_url, args.preview), indent=2))
