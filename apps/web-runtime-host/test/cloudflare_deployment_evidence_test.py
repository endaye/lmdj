#!/usr/bin/env python3
"""The Cloudflare evidence document must be exactly what the driver accepts."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps/web-runtime-host/tools"))

from cloudflare_deployment_evidence import (  # noqa: E402
    CONTRACTS,
    CloudflareEvidenceError,
    production_url,
    validate_document,
    version_url,
    write_document,
)

PRODUCT = "1.0.60.0"
HOST_VERSION = "3.0.0"
REVISION = "a" * 40
RUN_ID = "35184323606"
PROMOTED = "1f2e3d4c-5b6a-4788-9900-aabbccddeeff"
PRIOR = "0e1d2c3b-4a59-4677-8899-ffeeddccbbaa"
DEPLOYMENT = "9a8b7c6d-5e4f-4302-8110-223344556677"
ARCHIVES = {"creator-web": "lmdj-creator-web", "web-runtime-host": "lmdj-web-runtime-host"}


def check(url):
    return {"status": "passed", "url": url, "product_build": PRODUCT,
            "host_version": HOST_VERSION}


def prior_good(host, **changes):
    value = {"version_id": PRIOR, "version_url": version_url(host, PRIOR),
             "product_build": "1.0.59.0", "host_version": "2.9.0",
             "release_files": {"index_sha256": "4" * 64, "manifest_sha256": "5" * 64},
             "site_response": {"status": 200, "etag": "prior"}}
    value.update(changes)
    return value


def document(host, **changes):
    immutable_url = version_url(host, PROMOTED)
    live = production_url(host)
    value = {
        "contract": CONTRACTS[host],
        "tag": "lmdj-v" + PRODUCT,
        "product_build": PRODUCT,
        "host_version": HOST_VERSION,
        "git_revision": REVISION,
        "channel": "canary",
        "worker": {"creator-web": "creator", "web-runtime-host": "lab"}[host],
        "release_url": "https://github.com/endaye/lmdj/releases/tag/lmdj-v" + PRODUCT,
        "archive": {"filename": f"{ARCHIVES[host]}-{HOST_VERSION}-product-{PRODUCT}.zip",
                    "sha256": "1" * 64},
        "release_files": {"index_sha256": "2" * 64, "manifest_sha256": "3" * 64},
        "publication": {"version_id": PROMOTED, "deployment_id": DEPLOYMENT,
                        "percentage": 100},
        "prior_good": prior_good(host),
        "immutable": {"version_id": PROMOTED, "url": immutable_url,
                      "http": check(immutable_url), "browser": check(immutable_url)},
        "production": {"url": live, "http": check(live), "browser": check(live)},
        "github_actions": {"run_id": RUN_ID,
                           "run_url": f"https://github.com/endaye/lmdj/actions/runs/{RUN_ID}"},
        "started_at": "2026-09-17T04:00:00Z",
        "ended_at": "2026-09-17T04:20:00Z",
    }
    value.update(changes)
    return value


class ShapeTest(unittest.TestCase):
    def test_both_hosts_have_a_valid_document(self):
        for host in CONTRACTS:
            with self.subTest(host=host):
                self.assertEqual(validate_document(document(host), host=host),
                                 document(host))

    def test_the_driver_accepts_what_this_module_writes(self):
        # The one fact that matters: the release driver is the far-side judge,
        # so its own checker must accept this document unchanged.
        from tools.release.deployment_evidence import _evidence_problem
        from tools.release.model import load_policy

        policy = load_policy(ROOT / "tools/release/policy.json")
        for host, key in (("web-runtime-host", "runtime"), ("creator-web", "creator")):
            with self.subTest(host=host):
                problem = _evidence_problem(
                    document(host), host_policy=policy.promotion.hosts[key],
                    tag="lmdj-v" + PRODUCT, target_revision=REVISION,
                    identity=PRODUCT, run_id=int(RUN_ID))
                self.assertIsNone(problem)

    def test_an_unconfigured_host_is_refused(self):
        with self.assertRaises(CloudflareEvidenceError):
            validate_document(document("creator-web"), host="portal")

    def test_the_field_set_is_closed(self):
        for change in ({"extra": 1},):
            with self.assertRaises(CloudflareEvidenceError):
                validate_document(document("creator-web", **change), host="creator-web")
        for absent in ("prior_good", "worker", "publication", "immutable"):
            value = document("creator-web")
            del value[absent]
            with self.subTest(absent=absent), self.assertRaises(CloudflareEvidenceError):
                validate_document(value, host="creator-web")

    def test_a_foreign_contract_is_refused(self):
        for contract in (CONTRACTS["web-runtime-host"],
                         "lmdj.creator-web.deployment-evidence.v1"):
            with self.subTest(contract=contract), self.assertRaises(CloudflareEvidenceError):
                validate_document(document("creator-web", contract=contract),
                                  host="creator-web")

    def test_the_tag_must_follow_its_own_product_build(self):
        with self.assertRaises(CloudflareEvidenceError):
            validate_document(document("creator-web", tag="lmdj-v1.0.59.0"),
                              host="creator-web")

    def test_an_invalid_identity_is_refused(self):
        for change in ({"product_build": "1.0.60"}, {"host_version": "3.0"},
                       {"git_revision": "not-a-revision"}, {"channel": "dev"},
                       {"worker": "docs"},
                       {"release_url": "https://example.invalid/r"}):
            with self.subTest(change=change), self.assertRaises(CloudflareEvidenceError):
                value = document("creator-web", **change)
                if "product_build" in change:
                    value["tag"] = "lmdj-v" + change["product_build"]
                validate_document(value, host="creator-web")

    def test_the_run_must_name_itself(self):
        for actions in ({"run_id": "1", "run_url": document("creator-web")["github_actions"]["run_url"]},
                        {"run_id": RUN_ID, "run_url": "https://github.com/endaye/lmdj/actions/runs/1"},
                        {"run_id": RUN_ID}):
            with self.subTest(actions=actions), self.assertRaises(CloudflareEvidenceError):
                validate_document(document("creator-web", github_actions=actions),
                                  host="creator-web")

    def test_the_archive_must_be_this_release_s(self):
        archive = {"filename": "lmdj-creator-web-2.0.0-product-1.0.60.0.zip",
                   "sha256": "1" * 64}
        with self.assertRaises(CloudflareEvidenceError):
            validate_document(document("creator-web", archive=archive),
                              host="creator-web")

    def test_a_partial_promotion_is_refused(self):
        publication = {"version_id": PROMOTED, "deployment_id": DEPLOYMENT,
                       "percentage": 50}
        with self.assertRaises(CloudflareEvidenceError):
            validate_document(document("creator-web", publication=publication),
                              host="creator-web")

    def test_the_immutable_side_must_be_the_promoted_version(self):
        # Checking some other version proves nothing about this deployment.
        other = version_url("creator-web", PRIOR)
        immutable = {"version_id": PRIOR, "url": other,
                     "http": check(other), "browser": check(other)}
        with self.assertRaises(CloudflareEvidenceError):
            validate_document(document("creator-web", immutable=immutable),
                              host="creator-web")

    def test_a_check_that_did_not_pass_is_refused(self):
        for side, name in (("immutable", "http"), ("immutable", "browser"),
                           ("production", "http"), ("production", "browser")):
            value = document("creator-web")
            value[side][name] = dict(value[side][name], status="failed")
            with self.subTest(side=side, check=name), \
                    self.assertRaises(CloudflareEvidenceError):
                validate_document(value, host="creator-web")

    def test_a_check_bound_to_another_identity_is_refused(self):
        # A passed status is not enough: the result must be this deployment's.
        for change in ({"url": "https://creator.lmdj.workers.dev/other"},
                       {"product_build": "1.0.59.0"}, {"host_version": "2.9.0"}):
            value = document("creator-web")
            value["production"]["http"] = dict(value["production"]["http"], **change)
            with self.subTest(change=change), self.assertRaises(CloudflareEvidenceError):
                validate_document(value, host="creator-web")

    def test_a_first_deployment_has_no_prior(self):
        # A Worker's first deployment has nothing to roll back to, and
        # `deployment_effect` branches on exactly that; None must stay valid.
        self.assertIsNone(
            validate_document(document("creator-web", prior_good=None),
                              host="creator-web")["prior_good"])

    def test_a_prior_must_carry_what_the_driver_projects(self):
        # `tools/release/deployment_effect.py` reads the prior's identity, its
        # served digests and its recorded response; a prior missing any of them
        # cannot be projected, so it fails closed here.
        for absent in ("version_id", "version_url", "product_build",
                       "host_version", "release_files", "site_response"):
            value = prior_good("creator-web")
            del value[absent]
            with self.subTest(absent=absent), self.assertRaises(CloudflareEvidenceError):
                validate_document(document("creator-web", prior_good=value),
                                  host="creator-web")
        for change in ({"version_id": "not-a-version"},
                       {"version_url": "https://creator.lmdj.workers.dev"},
                       {"product_build": "1.0.59"}, {"host_version": "2.9"},
                       {"release_files": {"index_sha256": "4" * 64}},
                       {"site_response": {}}):
            with self.subTest(change=change), self.assertRaises(CloudflareEvidenceError):
                validate_document(
                    document("creator-web", prior_good=prior_good("creator-web", **change)),
                    host="creator-web")

    def test_the_promoted_version_is_not_its_own_prior(self):
        # Recording it would make recovery a no-op.
        value = prior_good("creator-web", version_id=PROMOTED,
                           version_url=version_url("creator-web", PROMOTED))
        with self.assertRaises(CloudflareEvidenceError):
            validate_document(document("creator-web", prior_good=value),
                              host="creator-web")

    def test_an_impossible_window_is_refused(self):
        with self.assertRaises(CloudflareEvidenceError):
            validate_document(document("creator-web", started_at="2026-09-17T05:00:00Z"),
                              host="creator-web")


class WriteTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_the_written_bytes_parse_back_to_the_same_document(self):
        target = self.root / "evidence.json"
        written = write_document(target, document("creator-web"), host="creator-web")
        self.assertEqual(written, target)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")),
                         document("creator-web"))
        self.assertTrue(target.read_text(encoding="utf-8").endswith("\n"))

    def test_an_invalid_document_is_never_written(self):
        target = self.root / "evidence.json"
        with self.assertRaises(CloudflareEvidenceError):
            write_document(target, document("creator-web", channel="dev"),
                           host="creator-web")
        self.assertFalse(target.exists())

    def test_an_unsafe_target_is_refused(self):
        link = self.root / "linked.json"
        link.symlink_to(self.root / "absent.json")
        with self.assertRaises(CloudflareEvidenceError):
            write_document(link, document("creator-web"), host="creator-web")
        missing = self.root / "absent-directory" / "evidence.json"
        with self.assertRaises(CloudflareEvidenceError):
            write_document(missing, document("creator-web"), host="creator-web")


if __name__ == "__main__":
    unittest.main()
