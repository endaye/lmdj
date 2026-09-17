#!/usr/bin/env python3
"""The deployment sequence records evidence only when every leg passed."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/web-runtime-host/tools"))

import cloudflare_deploy  # noqa: E402
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


def receipt(host, tag=None, product="1.0.60.0", version="3.0.0",
            source=REVISION, index="2" * 64, manifest="3" * 64):
    stem = {"creator-web": "lmdj-creator-web"}.get(host, "lmdj-web-runtime-host")
    return {"kind": "verified-host-stage", "source": source,
            "tag": tag or ("lmdj-v" + product), "host_id": host,
            "product_build": product, "host_version": version,
            "archive": {"name": f"{stem}-{version}-product-{product}.zip",
                        "sha256": "1" * 64},
            "files": {"index.html": {"sha256": index},
                      "host-manifest.json": {"sha256": manifest}}}


def write_stage(directory, document):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "dist").mkdir(exist_ok=True)
    (directory / "stage.json").write_text(json.dumps(document), encoding="utf-8")


class Adapter:
    """The shared Cloudflare adapter, recording the order it was driven in."""

    def __init__(self, *, exists=True, fail=None, promoted_version=CANDIDATE,
                 workspace=None, stage=True, receipt=None):
        self.receipt = receipt
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
        host = arguments[arguments.index("--target") + 1]
        if command == "candidate":
            if self.stage:
                write_stage(Path(self.workspace) / host,
                            self.receipt or receipt(host))
            return json.dumps({"result": {"version_id": CANDIDATE},
                               "workspace": str(self.workspace)})
        if command == "promote":
            return json.dumps({"result": {"id": DEPLOYMENT,
                                          "version_id": self.promoted_version},
                               "workspace": str(self.workspace)})
        raise AssertionError(command)


class Browser:
    def __init__(self, fail_on=None, soft_fail_on=None):
        self.fail_on, self.soft_fail_on, self.seen = fail_on, soft_fail_on, []

    def __call__(self, url):
        self.seen.append(url)
        if self.fail_on is not None and self.fail_on in url:
            raise CloudflareDeployError("browser check failed")
        if self.soft_fail_on is not None and self.soft_fail_on in url:
            return None
        return True


class Http:
    """The exact-signed HTTP verification this module runs for itself."""

    def __init__(self, fail_on=None, soft_fail_on=None):
        self.fail_on, self.soft_fail_on, self.seen = fail_on, soft_fail_on, []

    def __call__(self, distribution, url, preview):
        self.seen.append((url, preview, distribution.is_dir()))
        if self.fail_on is not None and self.fail_on in url:
            raise CloudflareDeployError("exact signed HTTP verification failed")
        if self.soft_fail_on is not None and self.soft_fail_on in url:
            return None
        return True


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
        return self.observation

    observation = {"response": {"status": 200, "etag": "prior"},
                   "product_build": "1.0.59.0", "host_version": "2.9.0",
                   "release_files": {"index_sha256": "4" * 64,
                                     "manifest_sha256": "5" * 64}}

    def deploy_once(self, host="web-runtime-host", *, adapter=None,
                    browser=None, http=None, prior=True, observation=None,
                    **changes):
        if observation is not None:
            self.observation = observation
        self.adapter = adapter or Adapter()
        if self.adapter.workspace is None:
            self.adapter.workspace = self.root / "state" / "workspace"
        self.browser = browser or Browser()
        self.http = http or Http()
        arguments = dict(
            host=host, tag=TAG, run_id=RUN_ID, state_root=self.root / "state",
            output=self.output, node=NODE, wrangler=WRANGLER,
            adapter=self.adapter, verify_http=self.http, browser=self.browser,
            read_site=self.read_site, clock=lambda: next(self.stamps),
            prior_tag=PRIOR_TAG if prior else None)
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

    def test_the_prior_is_described_from_what_production_served(self):
        # Not from re-staging its signed release afterwards, which would
        # describe what that release should have been rather than what was live.
        self.deploy_once()
        prior = self.written()["prior_good"]
        self.assertEqual(prior["product_build"], "1.0.59.0")
        self.assertEqual(prior["host_version"], "2.9.0")
        self.assertEqual(prior["release_files"]["index_sha256"], "4" * 64)
        self.assertEqual(prior["site_response"], {"status": 200, "etag": "prior"})
        self.assertEqual(prior["version_id"], PRIOR_VERSION)

    def test_a_same_tag_redeploy_still_describes_the_replaced_deployment(self):
        # The prior comes from the live observation, so it cannot be confused
        # with the candidate's own release when the tags match.
        self.deploy_once(prior_tag=TAG)
        prior = self.written()["prior_good"]
        self.assertEqual(prior["product_build"], "1.0.59.0")
        self.assertNotEqual(prior["product_build"],
                            self.written()["product_build"])

    def test_an_incomplete_prior_observation_is_refused(self):
        for absent in ("response", "product_build", "host_version",
                       "release_files"):
            self.setUp()
            observation = dict(DeployTest.observation)
            del observation[absent]
            with self.subTest(absent=absent), self.assertRaises(CloudflareDeployError):
                self.deploy_once(observation=observation)
            self.assertFalse(self.output.exists())
        self.assertNotIn("candidate", self.adapter.calls)

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

    def test_the_document_describes_what_was_staged(self):
        # Not what a caller said: the Build, Host version, source revision and
        # digests all come from the receipt the adapter left behind.
        self.deploy_once(adapter=Adapter(receipt=receipt(
            "web-runtime-host", product="1.0.60.0", version="3.1.0",
            source="c" * 40, index="7" * 64)))
        document = self.written()
        self.assertEqual(document["host_version"], "3.1.0")
        self.assertEqual(document["git_revision"], "c" * 40)
        self.assertEqual(document["release_files"]["index_sha256"], "7" * 64)
        self.assertEqual(document["archive"]["filename"],
                         "lmdj-web-runtime-host-3.1.0-product-1.0.60.0.zip")

    def test_a_receipt_for_another_tag_is_refused(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=Adapter(
                receipt=receipt("web-runtime-host", tag="lmdj-v1.0.58.0")))
        self.assertFalse(self.output.exists())

    def test_an_incomplete_receipt_is_refused(self):
        for absent in ("archive", "files", "product_build", "host_version",
                       "source", "kind"):
            document = receipt("web-runtime-host")
            del document[absent]
            self.setUp()
            with self.subTest(absent=absent), self.assertRaises(CloudflareDeployError):
                self.deploy_once(adapter=Adapter(receipt=document))
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

    def test_a_post_promotion_failure_issues_no_second_mutation(self):
        # Production is left serving the promoted version and the operator
        # reconciles with the adapter's `recover`. Rolling back from out here
        # would be a blind production mutation on an uncharacterised failure.
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(browser=Browser(fail_on="//lab."))
        self.assertEqual(self.adapter.calls, ["inspect", "candidate", "promote"])
        self.assertNotIn("recover", self.adapter.calls)

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

    def test_a_verifier_that_does_not_report_true_is_not_a_pass(self):
        # A check that skipped, retried into a falsy result or reported a soft
        # failure must never be written down as passed.
        for kind, made in (("http", lambda u: {"http": Http(soft_fail_on=u)}),
                           ("browser", lambda u: {"browser": Browser(soft_fail_on=u)})):
            for url in (CANDIDATE[:8], "//lab."):
                self.setUp()
                with self.subTest(kind=kind, url=url), \
                        self.assertRaises(CloudflareDeployError):
                    self.deploy_once(**made(url))
                self.assertFalse(self.output.exists())

    def test_a_workspace_outside_the_state_root_is_refused(self):
        # The verified bytes must provably be the ones this run staged.
        foreign = self.root / "elsewhere"
        (foreign / "web-runtime-host" / "dist").mkdir(parents=True)
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=Adapter(workspace=foreign))
        self.assertNotIn("promote", self.adapter.calls)
        self.assertFalse(self.output.exists())

    def test_promoting_another_version_is_refused(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=Adapter(promoted_version=PRIOR_VERSION))
        self.assertFalse(self.output.exists())

    def test_an_unconfigured_host_is_refused(self):
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(host="portal", adapter=Adapter(
                receipt=receipt("web-runtime-host")))
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

    def test_a_served_file_digest_must_be_staged(self):
        document = receipt("web-runtime-host")
        del document["files"]["host-manifest.json"]
        with self.assertRaises(CloudflareDeployError):
            self.deploy_once(adapter=Adapter(receipt=document))
        self.assertFalse(self.output.exists())


class EntryPointTest(unittest.TestCase):
    """The shipped command refuses bad input and never invents an exit code."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.captured = {}

    def arguments(self, *, state_root=None):
        return [TAG, "--target", "web-runtime-host",
                "--state-root", str(state_root or self.root / "state"),
                "--output", str(self.root / "evidence.json"),
                "--run-id", str(RUN_ID), "--node", NODE, "--wrangler", WRANGLER,
                "--prior-tag", PRIOR_TAG]

    def test_a_relative_state_root_is_refused(self):
        # Every local operator shares one root; a relative one is not shared.
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = cloudflare_deploy.main(self.arguments(state_root=Path("state")))
        self.assertEqual(code, 2)
        self.assertIn("state root", errors.getvalue())

    def test_a_failed_run_leaves_the_output_path_untouched(self):
        # Diagnostics belong beside the run's own state; a caller checking for
        # the evidence path must not find its directory conjured by a failure.
        output = self.root / "evidence" / "evidence.json"
        errors = io.StringIO()
        with patch.object(cloudflare_deploy, "deploy",
                          side_effect=CloudflareDeployError("candidate failed")), \
                contextlib.redirect_stderr(errors):
            code = cloudflare_deploy.main(
                [TAG, "--target", "web-runtime-host",
                 "--state-root", str(self.root / "state"),
                 "--output", str(output), "--run-id", str(RUN_ID),
                 "--node", NODE, "--wrangler", WRANGLER])
        self.assertEqual(code, 2)
        self.assertFalse(output.exists())
        self.assertFalse(output.parent.exists())

    def test_a_failed_deployment_exits_two_without_a_traceback(self):
        errors = io.StringIO()
        with patch.object(cloudflare_deploy, "deploy",
                          side_effect=CloudflareDeployError("candidate failed")), \
                contextlib.redirect_stderr(errors):
            code = cloudflare_deploy.main(self.arguments())
        self.assertEqual(code, 2)
        self.assertIn("candidate failed", errors.getvalue())

    def test_a_complete_deployment_reports_where_the_evidence_landed(self):
        written = self.root / "evidence.json"
        output = io.StringIO()
        with patch.object(cloudflare_deploy, "deploy", return_value=written), \
                contextlib.redirect_stdout(output):
            code = cloudflare_deploy.main(self.arguments())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()),
                         {"host": "web-runtime-host", "tag": TAG,
                          "evidence": str(written)})

    def test_the_command_passes_the_operator_inputs_through(self):
        seen = {}

        def record(**arguments):
            seen.update(arguments)
            return self.root / "evidence.json"

        with patch.object(cloudflare_deploy, "deploy", side_effect=record), \
                contextlib.redirect_stdout(io.StringIO()):
            cloudflare_deploy.main(self.arguments())
        self.assertEqual(seen["host"], "web-runtime-host")
        self.assertEqual(seen["tag"], TAG)
        self.assertEqual(seen["prior_tag"], PRIOR_TAG)
        self.assertEqual(seen["run_id"], str(RUN_ID))
        self.assertEqual(seen["node"], NODE)
        self.assertEqual(seen["wrangler"], WRANGLER)

    def browser_run(self, *, stdout, returncode=0, environment=None):
        check = cloudflare_deploy.real_browser("web-runtime-host", self.root)
        result = type("R", (), {"returncode": returncode, "stdout": stdout,
                                "stderr": ""})()
        with patch.object(cloudflare_deploy.subprocess, "run",
                          return_value=result) as runner:
            with patch.dict(cloudflare_deploy.os.environ,
                            environment or {}, clear=True):
                try:
                    passed = check("https://lab.lmdj.workers.dev")
                except CloudflareDeployError:
                    passed = False
        return passed, runner.call_args.kwargs["env"]

    def report(self, **stats):
        counts = {"expected": 1, "unexpected": 0, "flaky": 0, "skipped": 0}
        counts.update(stats)
        return json.dumps({"stats": counts})

    def test_the_browser_environment_is_an_allowlist(self):
        # The browser runs third-party test code; a denylist silently admits
        # every credential nobody thought to name.
        passed, environment = self.browser_run(
            stdout=self.report(),
            environment={"CLOUDFLARE_API_TOKEN": "secret", "GITHUB_TOKEN": "s",
                         "CLOUDFLARE_ACCOUNT_ID": "acct", "NPM_TOKEN": "npm",
                         "PATH": "/usr/bin", "HOME": "/home/runner"})
        self.assertTrue(passed)
        self.assertEqual(set(environment),
                         {"PATH", "HOME", "LMDJ_WEB_HOST_CLEAN_ROOM",
                          "LMDJ_WEB_HOST_EXTERNAL_SERVER",
                          "LMDJ_WEB_HOST_BASE_URL"})
        self.assertEqual(environment["LMDJ_WEB_HOST_BASE_URL"],
                         "https://lab.lmdj.workers.dev")

    def test_a_clean_exit_that_ran_nothing_is_not_a_pass(self):
        # A project or spec filter matching nothing exits 0; writing that into
        # the evidence as a passed browser check is exactly what must not happen.
        for stats in ({"expected": 0}, {"skipped": 1}, {"unexpected": 1},
                      {"flaky": 1}):
            with self.subTest(stats=stats):
                passed, _ = self.browser_run(stdout=self.report(**stats),
                                             environment={"PATH": "/usr/bin"})
                self.assertFalse(passed)

    def test_unreadable_reporter_output_is_not_a_pass(self):
        for stdout in ("", "not json", "[]", '{"stats": "none"}'):
            with self.subTest(stdout=stdout):
                passed, _ = self.browser_run(stdout=stdout,
                                             environment={"PATH": "/usr/bin"})
                self.assertFalse(passed)

    def test_a_diagnostic_name_never_escapes_its_directory(self):
        # The name is derived from a URL hostname; nothing derived from data
        # may decide where a file lands.
        for label in ("../../etc/passwd", "a/b", "", None, "x\x00y",
                      "lab.lmdj.workers.dev"):
            with self.subTest(label=label):
                name = cloudflare_deploy._log_name("browser", label)
                # The invariant is containment, not the absence of dots: a name
                # with no separator cannot traverse wherever it is joined.
                self.assertEqual(Path(name).name, name)
                self.assertEqual((self.root / name).resolve().parent,
                                 self.root.resolve())

    def test_even_a_short_secret_is_redacted(self):
        result = type("R", (), {"returncode": 1, "stdout": "tok=abc123",
                                "stderr": ""})()
        with patch.dict(cloudflare_deploy.os.environ, {"GH_TOKEN": "abc123"}):
            path = cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        self.assertNotIn("abc123", path.read_text(encoding="utf-8"))

    def test_the_browser_keeps_the_proxy_a_runner_needs(self):
        # Without these the browser cannot reach the deployed origin behind an
        # egress proxy, and that failure would read as a regression.
        _, environment = self.browser_run(
            stdout=self.report(),
            environment={"PATH": "/usr/bin", "HTTPS_PROXY": "http://p:3128",
                         "NO_PROXY": "localhost", "SOME_TOKEN": "secret"})
        self.assertEqual(environment["HTTPS_PROXY"], "http://p:3128")
        self.assertEqual(environment["NO_PROXY"], "localhost")
        self.assertNotIn("SOME_TOKEN", environment)

    def test_a_non_string_diagnostic_label_does_not_escape(self):
        # The factory is exported; a caller passing anything must not produce a
        # TypeError where a CloudflareDeployError is documented.
        for label in (7, object(), ["a"]):
            with self.subTest(label=type(label).__name__):
                name = cloudflare_deploy._log_name("adapter", label)
                self.assertEqual(Path(name).name, name)

    def test_an_unattributed_failure_still_exits_two(self):
        errors = io.StringIO()
        with patch.object(cloudflare_deploy, "deploy",
                          side_effect=RuntimeError("upstream text")), \
                contextlib.redirect_stderr(errors):
            code = cloudflare_deploy.main(self.arguments())
        self.assertEqual(code, 2)
        # The upstream text may carry credentials; only the category is said.
        self.assertNotIn("upstream text", errors.getvalue())
        self.assertIn("unattributed", errors.getvalue())

    def test_a_relative_state_root_creates_nothing(self):
        # The refusal happens before `deploy`, so the adapter and browser
        # closures never run and no diagnostics tree appears anywhere.
        before = sorted(Path.cwd().iterdir())
        with contextlib.redirect_stderr(io.StringIO()):
            code = cloudflare_deploy.main(self.arguments(state_root=Path("state")))
        self.assertEqual(code, 2)
        self.assertEqual(sorted(Path.cwd().iterdir()), before)
        self.assertFalse((Path.cwd() / "state").exists())

    def test_a_named_marker_survives_the_shape_pass(self):
        # A credential this process held should be named even when its only
        # occurrence is inside a header the shape patterns also match.
        result = type("R", (), {
            "returncode": 1,
            "stdout": "Authorization: Bearer held-by-this-process\n",
            "stderr": ""})()
        with patch.dict(cloudflare_deploy.os.environ,
                        {"CLOUDFLARE_API_TOKEN": "held-by-this-process"},
                        clear=True):
            path = cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        body = path.read_text(encoding="utf-8")
        self.assertNotIn("held-by-this-process", body)
        self.assertIn("[REDACTED CLOUDFLARE_API_TOKEN]", body)

    def test_a_redacted_value_does_not_shield_a_second_secret(self):
        # Per match, not per line: one already-masked value on a line must not
        # let a real secret beside it survive.
        result = type("R", (), {
            "returncode": 1,
            "stdout": "token=held-value other_token=never-held-value\n",
            "stderr": ""})()
        with patch.dict(cloudflare_deploy.os.environ,
                        {"SOME_TOKEN": "held-value"}, clear=True):
            path = cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        body = path.read_text(encoding="utf-8")
        self.assertNotIn("held-value", body)
        self.assertNotIn("never-held-value", body)
        self.assertIn("[REDACTED SOME_TOKEN]", body)

    def test_a_linked_diagnostic_directory_is_refused(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (self.root / "diagnostics").symlink_to(elsewhere)
        result = type("R", (), {"returncode": 1, "stdout": "x", "stderr": ""})()
        with self.assertRaises(CloudflareDeployError):
            cloudflare_deploy._diagnostic(self.root / "diagnostics",
                                          "adapter.log", result)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_a_shorter_credential_cannot_leave_a_longer_one_s_tail(self):
        # Replacing in iteration order would turn "abcdef" into
        # "[REDACTED A_TOKEN]ef" and leave the tail of a real secret behind.
        result = type("R", (), {"returncode": 1, "stdout": "v=abcdef\n",
                                "stderr": ""})()
        with patch.dict(cloudflare_deploy.os.environ,
                        {"A_TOKEN": "abcd", "B_TOKEN": "abcdef"}, clear=True):
            path = cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        body = path.read_text(encoding="utf-8")
        self.assertNotIn("abcdef", body)
        self.assertNotIn("ef\n", body)
        self.assertIn("[REDACTED B_TOKEN]", body)

    def test_a_marker_is_not_rewritten_by_another_credential(self):
        # One pass cannot re-enter what it just wrote, so the name that says
        # which credential leaked survives.
        result = type("R", (), {"returncode": 1, "stdout": "v=real-secret\n",
                                "stderr": ""})()
        with patch.dict(cloudflare_deploy.os.environ,
                        {"FIRST_TOKEN": "real-secret",
                         "SECOND_TOKEN": "REDACTED"}, clear=True):
            path = cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        self.assertIn("[REDACTED FIRST_TOKEN]",
                      path.read_text(encoding="utf-8"))

    def test_the_browser_keeps_the_trust_its_proxy_needs(self):
        # Forwarding the proxy without its CA bundle fails the leg after
        # promotion, which is the failure the proxy entries exist to avoid.
        _, environment = self.browser_run(
            stdout=self.report(),
            environment={"PATH": "/usr/bin", "HTTPS_PROXY": "http://p:3128",
                         "NODE_EXTRA_CA_CERTS": "/etc/ca.pem"})
        self.assertEqual(environment["NODE_EXTRA_CA_CERTS"], "/etc/ca.pem")

    def test_a_timeout_says_so_rather_than_reporting_a_failure(self):
        # A hung run and a failed assertion call for different remedies.
        adapter = cloudflare_deploy.real_adapter(self.root, timeout=1)
        with patch.object(cloudflare_deploy.subprocess, "run",
                          side_effect=cloudflare_deploy.subprocess.TimeoutExpired(
                              "npm", 1)):
            with self.assertRaises(CloudflareDeployError) as raised:
                adapter(["candidate", TAG])
        self.assertIn("timed out", str(raised.exception))
        with patch.object(cloudflare_deploy.subprocess, "run",
                          side_effect=FileNotFoundError("npm")):
            with self.assertRaises(CloudflareDeployError) as raised:
                adapter(["candidate", TAG])
        self.assertIn("could not be launched", str(raised.exception))

    def test_output_is_withheld_when_redaction_cannot_run(self):
        # Redaction is what makes retaining the output safe at all.
        result = type("R", (), {"returncode": 1, "stdout": "raw-output",
                                "stderr": ""})()
        with patch.object(cloudflare_deploy, "_redacted",
                          side_effect=RuntimeError("pattern too large")):
            path = cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        body = path.read_text(encoding="utf-8")
        self.assertNotIn("raw-output", body)
        self.assertIn("withheld", body)

    def test_every_launch_failure_keeps_its_diagnostic(self):
        # Anything escaping to main's backstop loses the file an operator needs.
        adapter = cloudflare_deploy.real_adapter(self.root, timeout=1)
        for raised in (ValueError("bad env"),
                       cloudflare_deploy.subprocess.SubprocessError("other")):
            with self.subTest(raised=type(raised).__name__), \
                    patch.object(cloudflare_deploy.subprocess, "run",
                                 side_effect=raised), \
                    self.assertRaises(CloudflareDeployError) as caught:
                adapter(["candidate", TAG])
            self.assertIn("inspect", str(caught.exception))

    def test_a_large_environment_still_gets_a_diagnostic(self):
        # Falling back keeps the longest-first ordering that matters, so a big
        # environment costs the single-pass property, not the whole file.
        result = type("R", (), {"returncode": 1, "stdout": "v=abcdef\n",
                                "stderr": ""})()
        with patch.dict(cloudflare_deploy.os.environ,
                        {"A_TOKEN": "abcd", "B_TOKEN": "abcdef"}, clear=True), \
                patch.object(cloudflare_deploy.re, "compile",
                             side_effect=cloudflare_deploy.re.error("too big")):
            body = cloudflare_deploy._redacted("v=abcdef\n")
        self.assertNotIn("abcdef", body)
        self.assertIn("[REDACTED B_TOKEN]", body)

    def test_the_backstop_retains_a_redacted_diagnostic(self):
        errors = io.StringIO()
        with patch.object(cloudflare_deploy, "deploy",
                          side_effect=RuntimeError("upstream s3cr3t-value")), \
                patch.dict(cloudflare_deploy.os.environ,
                           {"CLOUDFLARE_API_TOKEN": "s3cr3t-value"}), \
                contextlib.redirect_stderr(errors):
            code = cloudflare_deploy.main(self.arguments())
        self.assertEqual(code, 2)
        self.assertIn("inspect", errors.getvalue())
        retained = (self.root / "state" / "diagnostics" / "unattributed.log")
        self.assertTrue(retained.is_file())
        body = retained.read_text(encoding="utf-8")
        self.assertIn("RuntimeError", body)
        self.assertNotIn("s3cr3t-value", body)

    def test_a_hung_or_unlaunchable_command_is_our_error_not_a_traceback(self):
        # main only catches CloudflareDeployError, so anything else escaping
        # here becomes a traceback and a non-2 exit.
        adapter = cloudflare_deploy.real_adapter(self.root, timeout=1)
        for raised in (cloudflare_deploy.subprocess.TimeoutExpired("npm", 1),
                       FileNotFoundError("npm")):
            with self.subTest(raised=type(raised).__name__), \
                    patch.object(cloudflare_deploy.subprocess, "run",
                                 side_effect=raised), \
                    self.assertRaises(CloudflareDeployError):
                adapter(["candidate", TAG])

    def test_a_credential_shaped_name_is_redacted_without_being_listed(self):
        result = type("R", (), {"returncode": 1, "stdout": "v=zz9q",
                                "stderr": ""})()
        with patch.dict(cloudflare_deploy.os.environ,
                        {"SOME_VENDOR_TOKEN": "zz9q"}, clear=True):
            path = cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        self.assertNotIn("zz9q", path.read_text(encoding="utf-8"))

    def test_a_value_too_short_to_be_a_credential_is_left_alone(self):
        # Replacing it everywhere would mangle unrelated output, and a
        # three-character secret is not a real one.
        result = type("R", (), {"returncode": 1, "stdout": "path a/b/c ok",
                                "stderr": ""})()
        with patch.dict(cloudflare_deploy.os.environ,
                        {"SOME_TOKEN": "a/b"}, clear=True):
            path = cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        self.assertIn("path a/b/c ok", path.read_text(encoding="utf-8"))

    def test_a_credential_this_process_never_held_is_still_redacted(self):
        # Value replacement cannot reach a token the adapter minted itself.
        result = type("R", (), {
            "returncode": 1,
            "stdout": "Authorization: Bearer minted-elsewhere-9\n",
            "stderr": "api_key = other-minted-value\n"})()
        with patch.dict(cloudflare_deploy.os.environ, {}, clear=True):
            path = cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        body = path.read_text(encoding="utf-8")
        self.assertNotIn("minted-elsewhere-9", body)
        self.assertNotIn("other-minted-value", body)
        self.assertIn("[REDACTED]", body)

    def test_a_linked_diagnostic_path_is_refused(self):
        victim = self.root / "victim.txt"
        victim.write_text("original", encoding="utf-8")
        (self.root / "adapter.log").symlink_to(victim)
        result = type("R", (), {"returncode": 1, "stdout": "x", "stderr": ""})()
        with self.assertRaises(CloudflareDeployError):
            cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        self.assertEqual(victim.read_text(encoding="utf-8"), "original")

    def test_a_retained_diagnostic_redacts_secrets_and_is_owner_only(self):
        result = type("R", (), {
            "returncode": 1,
            "stdout": "value is s3cr3t-value here\n",
            "stderr": "Authorization: Bearer s3cr3t-value\n"})()
        with patch.dict(cloudflare_deploy.os.environ,
                        {"CLOUDFLARE_API_TOKEN": "s3cr3t-value"}, clear=True):
            path = cloudflare_deploy._diagnostic(self.root, "adapter.log", result)
        body = path.read_text(encoding="utf-8")
        self.assertNotIn("s3cr3t-value", body)
        self.assertIn("[REDACTED CLOUDFLARE_API_TOKEN]", body)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
