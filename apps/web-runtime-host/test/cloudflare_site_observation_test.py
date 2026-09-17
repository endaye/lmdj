#!/usr/bin/env python3
"""An observation reports what the origin served, or refuses to report at all."""

import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/web-runtime-host/tools"))

from cloudflare_site_observation import (  # noqa: E402
    ENTRY,
    MANIFEST,
    ObservationError,
    observe,
)

URL = "https://lab.lmdj.workers.dev"
INDEX = b"<!doctype html><title>host</title>"


def manifest_bytes(**changes):
    document = {"host_id": "web-runtime-host", "product_build": "1.0.59.0",
                "host_version": "2.9.0"}
    document.update(changes)
    return json.dumps(document).encode("utf-8")


class SmokeError(RuntimeError):
    pass


class Shared:
    """The Host smoke's bounded, header-validating fetch."""

    MAX_ASSET_BYTES = 64 * 1024 * 1024
    SmokeError = SmokeError

    def __init__(self, bodies, *, fail=None):
        self.bodies, self.fail, self.seen = bodies, fail, []

    def RedirectGuard(self):  # noqa: N802 - mirrors the shared module's name
        return object()

    def _fetch(self, opener, *, url, label, content_type, cache_control, limit,
               timeout_seconds):
        self.seen.append((url, content_type, cache_control, limit, timeout_seconds))
        if self.fail is not None and self.fail in url:
            raise SmokeError("returned HTTP 404")
        return self.bodies[label.lstrip("/")], url


def shared(**changes):
    bodies = {ENTRY: INDEX, MANIFEST: manifest_bytes()}
    bodies.update(changes.pop("bodies", {}))
    return Shared(bodies, **changes)


class ObserveTest(unittest.TestCase):
    def test_it_reports_the_identity_and_digests_the_origin_served(self):
        module = shared()
        result = observe(URL, opener=object(), shared=module)
        self.assertEqual(result["product_build"], "1.0.59.0")
        self.assertEqual(result["host_version"], "2.9.0")
        self.assertEqual(result["release_files"], {
            "index_sha256": hashlib.sha256(INDEX).hexdigest(),
            "manifest_sha256": hashlib.sha256(manifest_bytes()).hexdigest()})
        self.assertEqual(result["response"]["url"], URL)

    def test_it_reads_both_entry_files_with_the_host_smoke_contract(self):
        module = shared()
        observe(URL, opener=object(), shared=module)
        self.assertEqual([(url, content_type, cache) for
                          url, content_type, cache, _, _ in module.seen],
                         [(f"{URL}/{ENTRY}", "text/html", "no-store"),
                          (f"{URL}/{MANIFEST}", "application/json", "no-store")])

    def test_a_trailing_slash_does_not_double(self):
        module = shared()
        observe(URL + "/", opener=object(), shared=module)
        self.assertEqual(module.seen[0][0], f"{URL}/{ENTRY}")

    def test_an_unreachable_file_refuses_rather_than_guessing(self):
        for absent in (ENTRY, MANIFEST):
            with self.subTest(absent=absent), self.assertRaises(ObservationError):
                observe(URL, opener=object(), shared=shared(fail=absent))

    def test_an_unreadable_manifest_is_refused(self):
        module = shared(bodies={MANIFEST: b"not json"})
        with self.assertRaises(ObservationError):
            observe(URL, opener=object(), shared=module)

    def test_a_manifest_that_is_not_a_document_is_refused(self):
        module = shared(bodies={MANIFEST: b"[]"})
        with self.assertRaises(ObservationError):
            observe(URL, opener=object(), shared=module)

    def test_a_manifest_without_its_identity_is_refused(self):
        for absent in ("product_build", "host_version"):
            document = json.loads(manifest_bytes())
            del document[absent]
            module = shared(bodies={MANIFEST: json.dumps(document).encode("utf-8")})
            with self.subTest(absent=absent), self.assertRaises(ObservationError):
                observe(URL, opener=object(), shared=module)

    def test_an_empty_identity_is_refused(self):
        module = shared(bodies={MANIFEST: manifest_bytes(product_build="")})
        with self.assertRaises(ObservationError):
            observe(URL, opener=object(), shared=module)

    def test_the_deployment_sequence_accepts_this_observation(self):
        # The one fact that matters: the consumer is the judge, so its own
        # prior composition must accept this document unchanged, and the result
        # must satisfy the evidence contract's prior shape.
        from cloudflare_deploy import _prior
        from cloudflare_deployment_evidence import version_url

        version = "0e1d2c3b-4a59-4677-8899-ffeeddccbbaa"
        result = observe(URL, opener=object(), shared=shared())
        prior = _prior(result, "web-runtime-host", version)
        self.assertEqual(set(prior),
                         {"version_id", "version_url", "product_build",
                          "host_version", "release_files", "site_response"})
        self.assertEqual(prior["version_url"],
                         version_url("web-runtime-host", version))
        self.assertEqual(prior["site_response"], result["response"])
        self.assertEqual(prior["release_files"], result["release_files"])


if __name__ == "__main__":
    unittest.main()
