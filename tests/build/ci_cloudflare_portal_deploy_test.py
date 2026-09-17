#!/usr/bin/env python3
"""Exercise production recovery without Cloudflare credentials or network."""
import copy
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


def receipt(url):
    return {"schema": "lmdj.release-changelog-smoke.v1", "revision": "source", "pages": [
        {"route": "/releases/", "url": url + "/releases/", "source_sha256": "a" * 64,
         "content_sha256": "b" * 64, "response_sha256": "c" * 64, "response_bytes": 123}]}


class DeploymentTest(unittest.TestCase):
    def scenario(self, *, exists=False, preview_failure=False, production_failure=False, lost_receipt=False,
                 upload_failure=False, concurrent_at=None, recovery_failure=False, invalid_receipt=False):
        prior = [{"id": "prior", "versions": [{"version_id": "previous", "percentage": 100}]}] if exists else []
        state = {"deployments": prior, "route": {"enabled": exists, "previews_enabled": True}, "writes": []}
        lost = False

        def request(req, **kwargs):
            nonlocal lost
            path = req.full_url.split("/workers/")[1]
            body = json.loads(req.data) if req.data else None
            if body is not None:
                state["writes"].append((path, copy.deepcopy(body)))
            if path == "scripts":
                result = [{"id": "docs"}] if exists else []
            elif path.endswith("/deployments"):
                if body:
                    if recovery_failure and body["versions"][0]["version_id"] == "previous":
                        raise OSError("recovery rejected before commit")
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
                if upload_failure:
                    return subprocess.CompletedProcess(command, 1, "", "upload rejected")
                if not exists:
                    state["deployments"] = [{"id": "initial", "versions": [{"version_id": VERSION, "percentage": 100}]}]
                return subprocess.CompletedProcess(command, 0, "Worker Version ID: " + VERSION, "")
            url = command[-1]
            self.assertNotIn("CLOUDFLARE_API_TOKEN", kwargs["env"])
            phase = "preview" if VERSION[:8] in url else "production"
            if concurrent_at == phase:
                state["deployments"] = [{"id": "operator", "versions": [{"version_id": "operator-version", "percentage": 100}]}]
            if (preview_failure and VERSION[:8] in url) or (production_failure and url == "https://docs.lmdj.workers.dev"):
                raise subprocess.CalledProcessError(1, command)
            invalid = invalid_receipt is True or invalid_receipt == phase
            return subprocess.CompletedProcess(command, 0, "not a receipt" if invalid else json.dumps(receipt(url)))

        with tempfile.TemporaryDirectory() as directory:
            env = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "source",
                   "CLOUDFLARE_API_TOKEN": "test-token", "GITHUB_RUN_ID": "1234", "RUNNER_TEMP": directory, "WRANGLER_JS": "fake-wrangler"}
            with patch.dict(os.environ, env, clear=True), patch.object(MODULE, "urlopen", side_effect=request), \
                 patch.object(MODULE.subprocess, "check_output", return_value="source"), \
                 patch.object(MODULE.subprocess, "run", side_effect=run), patch.object(MODULE.time, "sleep"):
                if preview_failure or production_failure or lost_receipt or upload_failure or concurrent_at or invalid_receipt:
                    with self.assertRaises((subprocess.CalledProcessError, OSError, RuntimeError)):
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
        for phase in ("preview", "production"):
            self.assertEqual(evidence[phase]["changelogs"], receipt(evidence[phase]["url"]))

    def test_smoke_exit_zero_without_receipt_does_not_promote(self):
        state, evidence = self.scenario(exists=True, invalid_receipt=True)
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(state["deployments"][0]["id"], "prior")
        self.assertFalse(any(path.endswith("/deployments") for path, _ in state["writes"]))

    def test_receipt_identity_schema_and_complete_page_shape_are_required(self):
        base = "https://docs.lmdj.workers.dev"
        valid = receipt(base)
        cases = []
        for field, value in (("revision", "other"), ("schema", "unknown"), ("pages", []), ("extra", "not permitted")):
            item = copy.deepcopy(valid)
            item[field] = value
            cases.append(item)
        for field, value in (("url", "https://wrong.invalid/releases/"), ("route", "/other/"),
                             ("source_sha256", "bad"), ("response_bytes", True)):
            item = copy.deepcopy(valid)
            item["pages"][0][field] = value
            cases.append(item)
        duplicate = copy.deepcopy(valid)
        duplicate["pages"] *= 2
        cases.append(duplicate)
        for item in cases:
            with self.subTest(item=item):
                with self.assertRaisesRegex(RuntimeError, "why:.*remedy:"):
                    MODULE.smoke_receipt(json.dumps(item), "source", base)

    def test_invalid_production_receipt_retains_preview_and_recovers_prior(self):
        state, evidence = self.scenario(exists=True, invalid_receipt="production")
        self.assertEqual(evidence["status"], "failed")
        self.assertIn("changelogs", evidence["preview"])
        self.assertNotIn("production", evidence)
        self.assertEqual(state["deployments"][0]["versions"][0]["version_id"], "previous")

    def test_duplicate_receipt_fields_are_not_accepted_as_canonical(self):
        base = "https://docs.lmdj.workers.dev"
        raw = json.dumps(receipt(base)).replace('"revision": "source"', '"revision": "other", "revision": "source"')
        with self.assertRaisesRegex(RuntimeError, "receipt is absent or mismatched"):
            MODULE.smoke_receipt(raw, "source", base)

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

    def test_failed_first_upload_never_enables_route(self):
        state, evidence = self.scenario(upload_failure=True)
        self.assertEqual(state["writes"], [])
        self.assertFalse(state["route"]["enabled"])
        self.assertEqual(evidence["status"], "failed")

    def test_failed_existing_candidate_preserves_prior_deployment(self):
        state, evidence = self.scenario(exists=True, preview_failure=True)
        self.assertEqual(state["deployments"][0]["id"], "prior")
        self.assertFalse(any(path.endswith("/deployments") for path, _ in state["writes"]))
        self.assertTrue(state["route"]["enabled"])
        self.assertEqual(evidence["status"], "failed")

    def test_failed_first_production_check_disables_new_route(self):
        state, evidence = self.scenario(production_failure=True)
        self.assertFalse(state["route"]["enabled"])
        self.assertFalse(evidence["recovery"]["route"]["enabled"])
        self.assertEqual(evidence["status"], "failed")

    def test_concurrent_preview_deployment_is_not_overwritten(self):
        state, evidence = self.scenario(exists=True, concurrent_at="preview")
        self.assertEqual(state["deployments"][0]["id"], "operator")
        self.assertFalse(any(path.endswith("/deployments") for path, _ in state["writes"]))
        self.assertNotIn("recovery", evidence)
        self.assertEqual(evidence["status"], "failed")

    def test_concurrent_production_deployment_is_not_rolled_back(self):
        state, evidence = self.scenario(exists=True, concurrent_at="production")
        self.assertEqual(state["deployments"][0]["id"], "operator")
        writes = [body for path, body in state["writes"] if path.endswith("/deployments")]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["versions"][0]["version_id"], VERSION)
        self.assertNotIn("recovery", evidence)
        self.assertEqual(evidence["status"], "failed")

    def test_lost_receipt_does_not_repeat_candidate_publication(self):
        state, evidence = self.scenario(exists=True, lost_receipt=True)
        writes = [body["versions"][0]["version_id"] for path, body in state["writes"] if path.endswith("/deployments")]
        self.assertEqual(writes, [VERSION, "previous"])
        self.assertEqual(evidence["recovery"]["deployment"], [{"version_id": "previous", "percentage": 100}])

    def test_rejected_recovery_is_not_reported_as_restored(self):
        state, evidence = self.scenario(exists=True, production_failure=True, recovery_failure=True)
        self.assertEqual(state["deployments"][0]["versions"][0]["version_id"], VERSION)
        self.assertEqual(evidence["status"], "failed")
        self.assertNotIn("recovery", evidence)


class EvidenceDurabilityTest(unittest.TestCase):
    """The evidence describes a promotion that already happened remotely."""

    def fsynced(self, call):
        """The inodes fsynced while `call` runs, in order."""
        seen = []
        real = os.fsync
        def record(descriptor):
            try:
                seen.append(os.fstat(descriptor).st_ino)
            except OSError:
                pass
            return real(descriptor)
        with patch.object(os, "fsync", record):
            call()
        return seen

    def test_the_document_is_published_by_a_rename_and_both_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "cloudflare-portal-1.json"
            seen = self.fsynced(
                lambda: MODULE.publish_document(target, '{"status": "passed"}\n'))
            self.assertEqual(target.read_text(encoding="utf-8"),
                             '{"status": "passed"}\n')
            # `os.replace` is `rename(2)` within one directory, so the bytes
            # fsynced before it carry the inode the document ends up with.
            # Membership and order, not an exact list: an unrelated fsync
            # elsewhere is not this test's business, but persisting the file
            # before publishing it is.
            document, parent = target.stat().st_ino, target.parent.stat().st_ino
            self.assertIn(document, seen,
                          "why: the document's own bytes were not persisted "
                          "before the rename published them; "
                          "remedy: fsync the file before os.replace")
            self.assertIn(parent, seen,
                          "why: the directory entry the publishing rename "
                          "creates was not persisted, so evidence for a "
                          "completed promotion can be lost; "
                          "remedy: fsync the parent directory after os.replace")
            self.assertLess(seen.index(document), seen.index(parent),
                            "why: the directory entry was persisted before the "
                            "bytes it publishes; "
                            "remedy: fsync the file, rename it, then the directory")
            self.assertEqual(sorted(entry.name for entry in Path(directory).iterdir()),
                             [target.name],
                             "the write left a temporary file behind")

    def test_a_failed_handover_closes_the_descriptor_it_was_given(self):
        # `mkstemp` hands over an open descriptor; if wrapping it fails, nothing
        # else will close it, and a deploy that writes evidence on every path
        # would leak one per attempt.
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence.json"
            closed = []
            real = os.close
            with patch.object(os, "fdopen", side_effect=ValueError("fixture")), \
                    patch.object(os, "close", lambda fd: (closed.append(fd), real(fd))[1]):
                with self.assertRaises(ValueError):
                    MODULE.publish_document(target, "{}\n")
            self.assertEqual(len(closed), 1,
                             "why: the descriptor mkstemp handed over was not "
                             "closed when wrapping it failed; "
                             "remedy: close it before re-raising")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_a_failed_write_leaves_no_partial_document(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence.json"
            with patch.object(os, "replace", side_effect=OSError("fixture")):
                with self.assertRaises(OSError):
                    MODULE.publish_document(target, "{}\n")
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
