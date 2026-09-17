#!/usr/bin/env python3
"""The deployment sequence records evidence only when every leg passed."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/web-runtime-host/tools"))

from cloudflare_deploy import CloudflareDeployError, deploy  # noqa: E402
from cloudflare_deployment_evidence import (  # noqa: E402
    production_url,
    validate_document,
    version_url,
)

TAG = "lmdj-v1.0.60.0"
PRIOR_TAG = "lmdj-v1.0.59.0"
REVISION = "b" * 40
RUN_ID = 35184323606
CANDIDATE = "1f2e3d4c-5b6a-4788-9900-aabbccddeeff"
PRIOR_VERSION = "0e1d2c3b-4a59-4677-8899-ffeeddccbbaa"
DEPLOYMENT = "9a8b7c6d-5e4f-4302-8110-223344556677"
NODE = "/opt/node/bin/node"
WRANGLER = "/opt/wrangler/bin/wrangler.js"


def release(host, product="1.0.60.0", version="3.0.0"):
    stem = {"creator-web": "lmdj-creator-web"}.get(host, "lmdj-web-runtime-host")
    return {"product_build": product, "host_version": version,
            "archive": {"filename": f"{stem}-{version}-product-{product}.zip",
                        "sha256": "1" * 64},
            "release_files": {"index_sha256": "2" * 64, "manifest_sha256": "3" * 64}}


class Adapter:
    """The shared Cloudflare adapter, recording the order it was driven in."""

    def __init__(self, *, exists=True, fail=None, promoted_version=CANDIDATE,
                 workspace=None, stage=True):
        self.exists = exists
        self.fail = fail
        self.promoted_version = promoted_version
        self.workspace = workspace
        self.stage = stage
        self.calls = []

    def __call__(self, arguments):
        command = arguments[0]
        self.calls.append(command)
        if self.fail == command:
            raise CloudflareDeployError(f"{command} failed")
        if command == "inspect":
            deployment = ({"id": DEPLOYMENT, "version_id": PRIOR_VERSION}
                          if self.exists else None)
            return json.dumps({"worker": "w", "exists": self.exists,
                               "deployment": deployment, "route": None,
                               "records": []})
        if command == "candidate":
            host = arguments[arguments.index("--target") + 1]
            if self.stage:
                (Path(self.workspace) / host / "dist").mkdir(parents=True, exist_ok=True)
            return json.dumps({"result": {"version_id": CANDIDATE},
                               "workspace": str(self.workspace)})
        if command == "promote":
            return json.dumps({"result": {"id": DEPLOYMENT,
                                          "version_id": self.promoted_version}})
        raise AssertionError(command)


class Browser:
    def __init__(self, fail_on=None):
        self.fail_on, self.seen = fail_on, []

    def __call__(self, url):
        self.seen.append(url)
        if self.fail_on is not None and self.fail_on in url:
            raise CloudflareDeployError("browser check failed")


class Http:
    """The exact-signed HTTP verification this module runs for itself."""

    def __init__(self, fail_on=None):
        self.fail_on, self.seen = fail_on, []

    def __call__(self, distribution, url, preview):
        self.seen.append((url, preview, distribution.is_dir()))
        if self.fail_on is not None and self.fail_on in url:
            raise CloudflareDeployError("exact signed HTTP verification failed")


class DeployTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / "evidence.json"
        self.reads = []
        self.stamps = iter(["2026-09-17T04:00:00Z", "2026-09-17T04:20:00Z"])

    def read_site(self, url):
        self.reads.append((url, list(self.adapter.calls)))
        return {"status": 200, "etag": "prior"}

    def deploy_once(self, host="web-runtime-host", *, adapter=None,
                    browser=None, http=None, prior=True, **changes):
        self.adapter = adapter or Adapter()
        if self.adapter.workspace is None:
            self.adapter.workspace = self.root / "workspace"
        self.browser = browser or Browser()
        self.http = http or Http()
        arguments = dict(
            host=host, tag=TAG, release=release(host), run_id=RUN_ID,
            git_revision=REVISION, state_root=self.root / "state",
            output=self.output, node=NODE, wrangler=WRANGLER,
            adapter=self.adapter, verify_http=self.http, browser=self.browser,
            read_site=self.read_site, clock=lambda: next(self.stamps),
            prior_tag=PRIOR_TAG if prior else None,
            prior_release=release(host, "1.0.59.0", "2.9.0") if prior else None)
        arguments.update(changes)
        return deploy(**arguments)

    def written(self):
        return json.loads(self.output.read_text(encoding="utf-8"))

    def complete_deployment(self, host):
        self.deploy_once(host)
        document = self.written()
        self.assertEqual(validate_document(document, host=host), document)
        self.assertEqual(document["publication"],
                         {"version_id": CANDIDATE, "deployment_id": DEPLOYMENT,
                          "percentage": 100})
        self.assertEqual(self.browser.seen,
                         [version_url(host, CANDIDATE), production_url(host)])
        # The HTTP results in the document are the ones this module observed.
        self.assertEqual([(url, preview) for url, preview, _ in self.http.seen],
                         [(version_url(host, CANDIDATE), True),
                          (production_url(host), False)])
        self.assertTrue(all(staged for _, _, staged in self.http.seen))

    def test_a_complete_runtime_deployment_records_valid_evidence(self):
        self.complete_deployment("web-runtime-host")

    def test_a_complete_creator_deployment_records_valid_evidence(self):
        self.complete_deployment("creator-web")

    def test_the_prior_is_read_before_anything_mutates(self):
        # The digest the release driver froze before dispatch must describe the
        # deployment this run replaced, not one it created.
        self.deploy_once()
        self.assertEqual(len(self.reads), 1)
        url, calls_before = self.reads[0]
        self.assertEqual(url, production_url("web-runtime-host"))
        self.assertEqual(calls_before, ["inspect"])

    def test_a_first_deployment_has_no_prior(self):
        self.deploy_once(adapter=Adapter(exists=False), prior=False)
        self.assertIsNone(self.written()["prior_good"])

    def test_a_prior_tag_without_a_deployment_is_refused(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=Adapter(exists=False))
        self.assertFalse(self.output.exists())

    def test_an_existing_deployment_without_its_prior_tag_is_refused(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(prior=False)
        self.assertFalse(self.output.exists())

    def test_a_prior_tag_without_its_release_is_refused(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(prior_release=None)
        self.assertFalse(self.output.exists())

    def test_a_failed_candidate_never_promotes_or_records(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=Adapter(fail="candidate"))
        self.assertNotIn("promote", self.adapter.calls)
        self.assertFalse(self.output.exists())

    def test_a_failed_promotion_records_nothing(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=Adapter(fail="promote"))
        self.assertFalse(self.output.exists())

    def test_a_failed_candidate_browser_check_never_promotes(self):
        # An HTTP pass is not a Host: production must not be touched when the
        # candidate does not actually run in a browser.
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(browser=Browser(fail_on=CANDIDATE[:8]))
        self.assertNotIn("promote", self.adapter.calls)
        self.assertFalse(self.output.exists())

    def test_a_failed_production_browser_check_records_nothing(self):
        # The promotion already happened; recording it as verified would tell
        # the release driver a browser check passed that did not.
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(browser=Browser(fail_on="//lab."))
        self.assertIn("promote", self.adapter.calls)
        self.assertFalse(self.output.exists())

    def test_a_failed_candidate_http_check_never_promotes(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(http=Http(fail_on=CANDIDATE[:8]))
        self.assertNotIn("promote", self.adapter.calls)
        self.assertFalse(self.output.exists())

    def test_a_failed_production_http_check_records_nothing(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(http=Http(fail_on="//lab."))
        self.assertIn("promote", self.adapter.calls)
        self.assertFalse(self.output.exists())

    def test_a_candidate_that_staged_nothing_is_refused(self):
        # Without the staged signed bytes there is nothing to verify against,
        # so the run must stop rather than record an unverified pass.
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=Adapter(stage=False))
        self.assertNotIn("promote", self.adapter.calls)
        self.assertFalse(self.output.exists())

    def test_a_deployment_without_a_version_identity_is_refused(self):
        class NoVersion(Adapter):
            def __call__(self, arguments):
                if arguments[0] == "inspect":
                    self.calls.append("inspect")
                    return json.dumps({"worker": "w", "exists": True,
                                       "deployment": {"id": DEPLOYMENT},
                                       "route": None, "records": []})
                return super().__call__(arguments)

        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=NoVersion())
        self.assertFalse(self.output.exists())

    def test_promoting_another_version_is_refused(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=Adapter(promoted_version=PRIOR_VERSION))
        self.assertFalse(self.output.exists())

    def test_an_unconfigured_host_is_refused(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(host="portal")
        self.assertFalse(self.output.exists())

    def test_an_unreadable_adapter_result_is_refused(self):
        class Silent(Adapter):
            def __call__(self, arguments):
                super().__call__(arguments)
                return "not json" if arguments[0] == "candidate" else \
                    json.dumps({"worker": "w", "exists": False,
                                "deployment": None, "route": None, "records": []})

        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=Silent(exists=False), prior=False)
        self.assertFalse(self.output.exists())

    def test_a_release_description_must_be_complete(self):
        incomplete = release("web-runtime-host")
        del incomplete["release_files"]
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(release=incomplete)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
