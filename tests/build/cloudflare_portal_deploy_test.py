#!/usr/bin/env python3
"""Exercise production recovery without Cloudflare credentials or network."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("portal_deploy", ROOT / "scripts/cloudflare-portal-deploy.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
VERSION = "12345678-1234-1234-1234-123456789012"


class DeploymentTest(unittest.TestCase):
    def scenario(self, *, exists=False, preview_failure=False, production_failure=False, lost_receipt=False):
        prior = [{"id": "prior", "versions": [{"version_id": "previous", "percentage": 100}]}] if exists else []
        state = {"deployments": prior, "route": {"enabled": exists, "previews_enabled": True}}
        lost = False

        def request(req, **kwargs):
            nonlocal lost
            path = req.full_url.split("/workers/")[1]
            body = json.loads(req.data) if req.data else None
            if path == "scripts":
                result = [{"id": "docs"}] if exists else []
            elif path.endswith("/deployments"):
                if body:
                    state["deployments"] = [{"id": "deployed", "versions": body["versions"]}]
                    if lost_receipt and not lost:
                        lost = True
                        raise OSError("response lost after committed publication")
                result = {"deployments": state["deployments"]}
            elif path.endswith("/subdomain"):
                if body:
                    state["route"] = body
                result = state["route"]
            else:
                raise AssertionError(path)
            return io.StringIO(json.dumps({"success": True, "result": result}))

        def run(command, **kwargs):
            if command[1] == "fake-wrangler":
                if not exists:
                    state["deployments"] = [{"id": "initial", "versions": [{"version_id": VERSION, "percentage": 100}]}]
                return subprocess.CompletedProcess(command, 0, "Worker Version ID: " + VERSION, "")
            url = command[-1]
            self.assertNotIn("CLOUDFLARE_API_TOKEN", kwargs["env"])
            if (preview_failure and VERSION[:8] in url) or (production_failure and url == "https://docs.lmdj.workers.dev"):
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with tempfile.TemporaryDirectory() as directory:
            env = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "source",
                   "CLOUDFLARE_API_TOKEN": "test-token", "GITHUB_RUN_ID": "1234", "RUNNER_TEMP": directory, "WRANGLER_JS": "fake-wrangler"}
            with patch.dict(os.environ, env, clear=True), patch.object(MODULE, "urlopen", side_effect=request), \
                 patch.object(MODULE.subprocess, "check_output", return_value="source"), \
                 patch.object(MODULE.subprocess, "run", side_effect=run), patch.object(MODULE.time, "sleep"):
                if preview_failure or production_failure or lost_receipt:
                    with self.assertRaises((subprocess.CalledProcessError, OSError)):
                        MODULE.publish()
                else:
                    MODULE.publish()
            evidence = json.loads((Path(directory) / "cloudflare-portal-1234.json").read_text())
        return state, evidence

    def test_initial_success_enables_only_verified_version(self):
        state, evidence = self.scenario()
        self.assertEqual(evidence["status"], "passed")
        self.assertTrue(state["route"]["enabled"])
        self.assertEqual(state["deployments"][0]["versions"][0]["version_id"], VERSION)

    def test_failed_initial_preview_keeps_route_disabled(self):
        state, _ = self.scenario(preview_failure=True)
        self.assertFalse(state["route"]["enabled"])

    def test_failed_production_restores_exact_prior(self):
        state, evidence = self.scenario(exists=True, production_failure=True)
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(state["deployments"][0]["versions"][0]["version_id"], "previous")
        self.assertTrue(state["route"]["enabled"])

    def test_lost_publication_receipt_reconciles_and_restores_prior(self):
        state, _ = self.scenario(exists=True, lost_receipt=True)
        self.assertEqual(state["deployments"][0]["versions"][0]["version_id"], "previous")


if __name__ == "__main__":
    unittest.main()
