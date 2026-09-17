#!/usr/bin/env python3
"""Observe what a Host origin is serving right now, without a verified dist.

`cloudflare_smoke` answers "does this origin serve exactly these verified signed
bytes?", which needs the distribution in hand. The deployment sequence also has
to answer a different question first: what is production serving *before* this
run changes it? Its signed release is not staged — it belongs to whatever was
deployed last — so the identity has to come from the origin itself.

This reads the two files that carry that identity, through the same bounded,
header-validating fetch the Host smoke uses, and reports the Product Build, the
Host version and the served digests. It asserts nothing about correctness: an
observation is what was there, and the deployment evidence records it as the
prior it replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from urllib.request import build_opener

ENTRY = "index.html"
MANIFEST = "host-manifest.json"


def _shared():
    tool = Path(__file__).resolve().parent / "deployment_smoke.py"
    spec = importlib.util.spec_from_file_location("cloudflare_origin_http", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ObservationError(RuntimeError):
    """The origin did not report a readable identity for what it serves."""

    def __init__(self, reason):
        super().__init__(
            f"why: Host origin observation {reason}; remedy: read the live "
            "origin and its manifest directly before binding a prior")


def observe(base_url, *, opener=None, shared=None, timeout_seconds=30):
    """What this origin serves: identity plus the digests of the two entry files."""
    shared = shared or _shared()
    opener = opener if opener is not None else build_opener(shared.RedirectGuard())
    root = base_url if base_url.endswith("/") else base_url + "/"
    digests = {}
    bodies = {}
    for name, content_type in ((ENTRY, "text/html"), (MANIFEST, "application/json")):
        try:
            body, _ = shared._fetch(
                opener, url=root + name, label="/" + name,
                content_type=content_type, cache_control="no-store",
                limit=shared.MAX_ASSET_BYTES, timeout_seconds=timeout_seconds)
        except shared.SmokeError as error:
            raise ObservationError(f"could not read /{name} ({error})") from None
        bodies[name] = body
        digests[name] = hashlib.sha256(body).hexdigest()
    try:
        manifest = json.loads(bodies[MANIFEST])
    except ValueError:
        raise ObservationError("served an unreadable manifest") from None
    if not isinstance(manifest, dict):
        raise ObservationError("served a manifest that is not a document")
    for field in ("product_build", "host_version"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise ObservationError(f"served a manifest without {field}")
    return {
        "response": {"url": base_url, "product_build": manifest["product_build"],
                     "host_version": manifest["host_version"],
                     "file_digests": {"/" + ENTRY: digests[ENTRY],
                                      "/" + MANIFEST: digests[MANIFEST]}},
        "product_build": manifest["product_build"],
        "host_version": manifest["host_version"],
        "release_files": {"index_sha256": digests[ENTRY],
                          "manifest_sha256": digests[MANIFEST]},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    arguments = parser.parse_args(argv)
    try:
        print(json.dumps(observe(arguments.base_url), sort_keys=True))
    except ObservationError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
