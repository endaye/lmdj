#!/usr/bin/env python3
"""Actual workflow producer CLI, isolated event files; no GitHub mutation."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.dispatch_receipt import receipt, ReceiptError, WORKFLOWS
from tools.release.model import canonical_json


class ReceiptTest(unittest.TestCase):
    def setUp(self):
        self.workflow = "publish-release.yml"
        self.event = {"ref": "refs/heads/main", "repository": {"id": 10, "full_name": "endaye/lmdj"},
            "sender": {"id": 20}, "inputs": {"request_id": "a" * 64, "tag": "lmdj-v1.0.57.0",
            "release_id": "30", "plan_sha256": "b" * 64}}
        self.env = {"GITHUB_REPOSITORY_ID": "10", "GITHUB_ACTOR_ID": "20", "GITHUB_RUN_ID": "40",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
            "GITHUB_REPOSITORY": "endaye/lmdj", "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_WORKFLOW_REF": "endaye/lmdj/.github/workflows/publish-release.yml@refs/heads/main",
            "GITHUB_SHA": "c" * 40, "GITHUB_WORKFLOW_SHA": "d" * 40}

    def produce(self):
        return receipt(self.event, self.env, self.workflow, "e" * 40)

    def test_all_three_workflows_bind_exact_inputs_and_distinct_tooling(self):
        for name, fields in WORKFLOWS.items():
            event = deepcopy(self.event)
            event["inputs"] = {k:v for k,v in event["inputs"].items() if k in fields}
            if name != "publish-release.yml":
                event["inputs"]["prior_site_sha256"] = "f" * 64
            env = {**self.env, "GITHUB_WORKFLOW_REF": f"endaye/lmdj/.github/workflows/{name}@refs/heads/main"}
            result = receipt(event, env, name, "e" * 40)
            self.assertEqual(result["inputs"], event["inputs"])
            self.assertEqual((result["run_id"], result["actor_id"]), (40, 20))
            self.assertEqual(result["tooling_revision"], "e" * 40)
            self.assertNotIn("verified", result)
            self.assertNotIn("success", result)

    def test_short_main_event_ref_uses_full_platform_ref(self):
        self.event["ref"] = "main"
        self.assertEqual(self.produce()["ref"], "refs/heads/main")

    def test_managed_deploy_requires_exact_digest_shape(self):
        self.workflow = "deploy-web-runtime-host.yml"
        self.env["GITHUB_WORKFLOW_REF"] = f"endaye/lmdj/.github/workflows/{self.workflow}@refs/heads/main"
        self.event["inputs"] = {k:v for k,v in self.event["inputs"].items() if k in ("tag", "request_id")}
        with self.assertRaises(ReceiptError): self.produce()
        for value in ("", "F" * 64, "bad", 3):
            self.event["inputs"]["prior_site_sha256"] = value
            with self.subTest(value=value), self.assertRaises(ReceiptError): self.produce()
        self.event["inputs"]["prior_site_sha256"] = "f" * 64
        self.assertEqual(self.produce()["inputs"]["prior_site_sha256"], "f" * 64)

    def test_deploy_workflow_passes_original_inputs_as_environment(self):
        for name in ("deploy-web-runtime-host.yml", "deploy-creator-web.yml"):
            source = (ROOT / ".github/workflows" / name).read_text()
            self.assertIn("      prior_site_sha256:", source)
            self.assertIn("LMDJ_RELEASE_REQUEST_ID: ${{ inputs.request_id }}", source)
            self.assertIn("LMDJ_PRIOR_SITE_SHA256: ${{ inputs.prior_site_sha256 }}", source)

    def test_invalid_receipt_does_not_advise_a_new_dispatch(self):
        self.event["inputs"].pop("request_id")
        with self.assertRaises(ReceiptError) as caught:
            self.produce()
        self.assertIn("never redispatch", str(caught.exception))
        self.assertNotIn("new attempt-1 dispatch", str(caught.exception))

    def test_each_platform_identity_refuses_one_changed_fact(self):
        for key, value in {"GITHUB_REPOSITORY_ID":"11", "GITHUB_ACTOR_ID":"21",
                "GITHUB_RUN_ATTEMPT":"2", "GITHUB_REF":"refs/tags/main",
                "GITHUB_WORKFLOW_REF":"endaye/lmdj/.github/workflows/other.yml@refs/heads/main",
                "GITHUB_EVENT_NAME":"push", "GITHUB_SHA":"not-a-sha",
                "GITHUB_REPOSITORY":"another/repo", "GITHUB_RUN_ID":"0"}.items():
            with self.subTest(key=key), self.assertRaises(ReceiptError):
                receipt(self.event, {**self.env,key:value}, self.workflow, "e" * 40)

    def test_unknown_input_cannot_leak_into_receipt(self):
        self.event["inputs"]["secret"] = "private-sentinel"
        with self.assertRaises(ReceiptError): self.produce()

    def test_request_id_is_not_arbitrary_text(self):
        self.event["inputs"]["request_id"] = "private-sentinel"
        with self.assertRaises(ReceiptError): self.produce()

    def test_wrong_event_ref_is_refused(self):
        self.event["ref"] = "refs/heads/other"
        with self.assertRaises(ReceiptError): self.produce()

    def test_missing_input_is_refused(self):
        del self.event["inputs"]["tag"]
        with self.assertRaises(ReceiptError): self.produce()

    def test_bool_actor_is_not_numeric_identity(self):
        self.event["sender"]["id"] = True
        with self.assertRaises(ReceiptError): self.produce()

    def cli(self, directory, raw=None):
        event = Path(directory) / "event.json"
        event.write_bytes(json.dumps(self.event).encode() if raw is None else raw)
        output = Path(directory) / "out" / "receipt.json"
        env = {**os.environ, **self.env, "GITHUB_EVENT_PATH": str(event), "GITHUB_TOKEN":"private-sentinel"}
        run = subprocess.run([sys.executable,"-m","tools.release.dispatch_receipt",
            "--workflow",self.workflow,"--output",str(output)],cwd=ROOT,env=env,
            capture_output=True,text=True,timeout=10)
        return run, output

    def test_real_cli_canonical_output_never_exports_token_or_event_extras(self):
        self.event["private_extra"] = "private-sentinel"
        with tempfile.TemporaryDirectory() as directory:
            run, output = self.cli(directory)
            self.assertEqual(run.returncode, 0, run.stderr)
            raw = output.read_bytes()
            self.assertEqual(raw, canonical_json(json.loads(raw)))
            self.assertNotIn(b"private-sentinel", raw)
            self.assertNotIn("private-sentinel", run.stdout+run.stderr)

    def test_real_cli_duplicate_input_rejected_without_receipt_or_secret_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = json.dumps(self.event).replace('"request_id":', '"request_id":"private-sentinel", "request_id":').encode()
            run, output = self.cli(directory, raw)
            self.assertEqual(run.returncode, 1)
            self.assertFalse(output.exists())
            self.assertNotIn("private-sentinel", run.stdout+run.stderr)

    def test_real_cli_cannot_overwrite_existing_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            run, output = self.cli(directory)
            self.assertEqual(run.returncode, 0)
            old = output.read_bytes()
            self.event["inputs"]["tag"] = "lmdj-v1.0.57.0"
            again, _ = self.cli(directory)
            self.assertEqual(again.returncode, 1)
            self.assertEqual(output.read_bytes(), old)

    def test_workflows_record_and_upload_before_existing_preflight(self):
        for workflow in WORKFLOWS:
            source = (ROOT/".github/workflows"/workflow).read_text()
            preflight = source.split("  preflight:\n",1)[1].split("\n  publish:",1)[0].split("\n  deploy:",1)[0]
            self.assertIn("description: Optional release operation digest for correlation only",source)
            self.assertEqual(preflight.count("if: ${{ inputs.request_id != '' }}"),2)
            self.assertIn(f"python3 -m tools.release.dispatch_receipt --workflow {workflow} --output build/release-dispatch/receipt.json",preflight)
            self.assertLess(preflight.index("Record dispatch correlation"),preflight.index("Upload dispatch correlation"))
            command = "scripts/release.sh audit" if workflow == "publish-release.yml" else "Select exact signed Product tag"
            self.assertLess(preflight.index("Upload dispatch correlation"),preflight.index(command))
            self.assertIn("if-no-files-found: error",preflight)
            self.assertNotIn("continue-on-error",preflight)
            self.assertNotIn("always()",preflight)


if __name__ == "__main__":
    unittest.main()
