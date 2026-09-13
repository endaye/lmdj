#!/usr/bin/env python3
"""Real Git and shipped GET transport with isolated GitHub artifact fixtures."""
from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_changelog_binding_test as fixtures
from tools.release.changelog import binding
from tools.release.changelog_site import project, LEDGER, PUBLICATIONS
from tools.release.changelog_site_evidence import ChangelogSiteEvidenceConsumer, SiteEvidenceError, WORKFLOW
from tools.release.github_api import GitHubClient, GitHubApiError, HttpResponse
from tools.release.model import load_ledger_document, canonical_json


class SiteEvidenceTest(unittest.TestCase):
    def live_clock(self):
        class Clock(datetime):
            current = (2026, 9, 13)

            @classmethod
            def now(cls, tz=None):
                return cls(*cls.current, tzinfo=tz)
        mocked = patch("tools.release.changelog_site_evidence.datetime", Clock)
        mocked.start()
        self.addCleanup(mocked.stop)
        self.consumer = ChangelogSiteEvidenceConsumer(
            api_get=self.client.get_changelog_site_evidence, git_root=self.root,
            policy=self.policy, repository_id=1, workflow_id=7,
            producer_revision=self.producer)
        return Clock

    def test_reused_reader_rejects_evidence_at_actual_expiry(self):
        clock = self.live_clock()
        self.assertEqual(self.verify()["run_id"], 101)
        clock.current = (2026, 10, 13)
        with self.assertRaisesRegex(SiteEvidenceError, "retention elapsed"):
            self.verify()

    def test_evidence_expiring_during_download_is_not_returned(self):
        clock = self.live_clock()
        self.assertEqual(self.verify()["run_id"], 101)
        self.after_download = lambda: setattr(clock, "current", (2026, 10, 13))
        with self.assertRaisesRegex(SiteEvidenceError, "retention elapsed"):
            self.verify()

    def setUp(self):
        helper = fixtures.ChangelogBindingTest()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.policy = helper.fixture.policy
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.git("init", "-q", "-b", "main")
        self.write("README.md", b"trusted producer fixture\n")
        self.git("add", ".")
        self.commit()
        self.producer = self.git("rev-parse", "HEAD").strip()
        entry = deepcopy(helper.entry)
        entry.update(disposition="published", target_revision=self.producer)
        entry["changelog"]["target_revision"] = self.producer
        entry["changelog"]["commits"] = [self.producer]
        entry["changelog"]["changes"][0]["commits"] = [self.producer]
        self.tag = entry["tag"]
        ledger_doc = {"schema": "lmdj.release-intents.v1", "entries": [entry], "historical_exceptions": []}
        digests = binding(entry["changelog"])
        self.record = {"tag": self.tag, "target_revision": self.producer, "release_id": 456,
                       "published_at": "2026-09-13T00:00:00Z", "plan_sha256": "b" * 64,
                       "changelog_sha256": digests["sha256"], "notes_sha256": digests["notes_sha256"]}
        publications = {"schema": "lmdj.release-changelog-publications.v1", "entries": [self.record]}
        self.write(LEDGER, canonical_json(ledger_doc))
        self.write(PUBLICATIONS, canonical_json(publications))
        self.git("add", ".")
        self.commit()
        self.source = self.git("rev-parse", "HEAD").strip()
        self.prefix = "/repos/endaye/lmdj"
        self.run = {"id": 101, "run_attempt": 1, "workflow_id": 7, "path": WORKFLOW, "head_sha": self.source,
                    "head_branch": "main", "event": "push", "status": "completed", "conclusion": "success",
                    "repository": {"id": 1, "full_name": "endaye/lmdj"}, "head_repository": {"id": 1, "full_name": "endaye/lmdj"}}
        job = {"id": 202, "run_id": 101, "run_attempt": 1, "head_sha": self.source, "name": "deploy",
               "status": "completed", "conclusion": "success", "steps": [{"name": name, "status": "completed", "conclusion": "success"}
                   for name in ("Build and verify the Git source", "Verify version Preview and publish the same version", "Retain deployment and recovery observations")]}
        self.artifact = {"id": 303, "name": "cloudflare-portal-" + self.source, "expired": False,
                         "expires_at": "2026-10-13T00:00:00Z", "workflow_run": {"id": 101, "repository_id": 1,
                         "head_repository_id": 1, "head_sha": self.source, "head_branch": "main"}}
        self.routes = {"/branches/main": {"name": "main", "protected": True, "commit": {"sha": self.source}},
                       "/actions/workflows/deploy-cloudflare-portal.yml": {"id": 7, "path": WORKFLOW, "state": "active"},
                       "/actions/runs/101": self.run, "/actions/runs/101/attempts/1": self.run,
                       "/actions/runs/101/attempts/1/jobs?per_page=100&page=1": {"total_count": 1, "jobs": [job]},
                       "/actions/runs/101/artifacts?per_page=100&page=1": {"total_count": 1, "artifacts": [self.artifact]}}
        self.document = {"git_revision": self.source, "worker": "docs", "status": "passed", "prior": [], "prior_route": {},
                         "version_id": "12345678-1234-1234-1234-123456789012"}
        generated = project(load_ledger_document(ledger_doc, self.policy), publications)
        for phase, url in (("preview", "https://12345678-docs.lmdj.workers.dev"), ("production", "https://docs.lmdj.workers.dev")):
            pages = []
            for page in generated:
                route = "/releases/" if page["file"].endswith("/index.mdx") else "/releases/" + Path(page["file"]).stem + "/"
                pages.append({"route": route, "url": url + route, "source_sha256": hashlib.sha256(page["content"].encode()).hexdigest(),
                              "content_sha256": "c" * 64, "response_sha256": "d" * 64, "response_bytes": 1024})
            self.document[phase] = {"url": url, "status": "passed", "changelogs": {"schema": "lmdj.release-changelog-smoke.v1", "revision": self.source, "pages": pages}}
        self.calls, self.after_download = [], None
        self.pack()
        self.client = GitHubClient(http_transport=self.transport)
        self.consumer = ChangelogSiteEvidenceConsumer(api_get=self.client.get_changelog_site_evidence, git_root=self.root,
            policy=self.policy, repository_id=1, workflow_id=7, producer_revision=self.producer,
            now=datetime(2026, 9, 13, tzinfo=timezone.utc))

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def commit(self):
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")

    def write(self, relative, payload):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    def pack(self, *, member="cloudflare-portal-101.json", payload=None):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            archive.writestr(member, canonical_json(self.document) if payload is None else payload)
        self.zip = raw.getvalue()
        self.artifact.update(size_in_bytes=len(self.zip), digest="sha256:" + hashlib.sha256(self.zip).hexdigest())

    def transport(self, method, url, headers, body):
        self.calls.append((method, url))
        self.assertEqual(method, "GET")
        self.assertIsNone(body)
        self.assertTrue(url.startswith(self.prefix))
        suffix = url[len(self.prefix):]
        if suffix == "/actions/artifacts/303/zip":
            if self.after_download:
                self.after_download()
            return HttpResponse(200, {"Content-Type": "application/zip"}, self.zip)
        return HttpResponse(200, {}, json.dumps(self.routes[suffix]).encode())

    def verify(self):
        return self.consumer.verify(tag=self.tag, run_id=101, source_revision=self.source, publication_record=self.record)

    def test_authenticated_run_zip_and_source_pages_produce_repeatable_receipt_without_writes(self):
        original = self.git("status", "--porcelain")
        result = self.verify()
        self.assertEqual(result, self.verify())
        self.assertEqual(result["source_revision"], self.source)
        self.assertEqual(result["target_revision"], self.producer)
        self.assertEqual(result["url"], "https://docs.lmdj.workers.dev/releases/1.0.21.0/")
        self.assertEqual(result["evidence_sha256"], hashlib.sha256(canonical_json(self.document)).hexdigest())
        self.assertEqual(self.git("status", "--porcelain"), original)
        self.assertTrue(all(method == "GET" for method, _ in self.calls))

    def test_wrong_run_workflow_attempt_event_or_repository_is_refused(self):
        original = deepcopy(self.run)
        for key, value in (("id", 102), ("workflow_id", True), ("path", ".github/workflows/other.yml"),
                           ("event", "workflow_dispatch"), ("run_attempt", 2), ("head_sha", self.producer),
                           ("conclusion", "failure"), ("head_repository", {"id": 9, "full_name": "endaye/lmdj"})):
            with self.subTest(key=key):
                self.run.clear(); self.run.update(original); self.run[key] = value
                with self.assertRaises(SiteEvidenceError): self.verify()

    def test_missing_required_job_step_is_refused(self):
        self.routes["/actions/runs/101/attempts/1/jobs?per_page=100&page=1"]["jobs"][0]["steps"].pop()
        with self.assertRaisesRegex(SiteEvidenceError, "required deployment step"):
            self.verify()

    def test_expired_artifact_is_unverifiable_not_success(self):
        self.artifact["expired"] = True
        with self.assertRaises(SiteEvidenceError) as caught: self.verify()
        self.assertEqual(caught.exception.code, "unverifiable")

    def test_artifact_origin_and_transfer_digest_are_checked(self):
        self.artifact["workflow_run"]["head_sha"] = self.producer
        with self.assertRaisesRegex(SiteEvidenceError, "artifact origin"):
            self.verify()
        self.artifact["workflow_run"]["head_sha"] = self.source
        self.artifact["digest"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(SiteEvidenceError, "transfer digest"):
            self.verify()

    def test_missing_version_page_is_not_hidden_by_index_success(self):
        self.document["production"]["changelogs"]["pages"].pop()
        self.pack()
        with self.assertRaisesRegex(SiteEvidenceError, "omits a required"):
            self.verify()

    def test_wrong_site_source_digest_and_cross_site_content_are_refused(self):
        original = deepcopy(self.document)
        for key, value in (("url", "https://other.invalid/releases/"), ("source_sha256", "e" * 64), ("content_sha256", "e" * 64), ("response_bytes", True)):
            with self.subTest(key=key):
                self.document = deepcopy(original)
                self.document["production"]["changelogs"]["pages"][0][key] = value
                self.pack()
                with self.assertRaises(SiteEvidenceError): self.verify()

    def test_run_restarted_while_downloading_cannot_reuse_attempt_one(self):
        self.after_download = lambda: self.run.update(run_attempt=2)
        with self.assertRaisesRegex(SiteEvidenceError, "first-attempt"):
            self.verify()

    def test_nonterminal_run_is_pending_not_verified_or_a_terminal_failure(self):
        self.run.update(status="in_progress", conclusion=None)
        with self.assertRaises(SiteEvidenceError) as caught: self.verify()
        self.assertEqual(caught.exception.code, "pending")
        self.assertFalse(any(url.endswith("/zip") for _, url in self.calls))

    def test_protection_removed_while_downloading_prevents_receipt(self):
        self.after_download = lambda: self.routes["/branches/main"].update(protected=False)
        with self.assertRaisesRegex(SiteEvidenceError, "main is not protected"):
            self.verify()

    def test_transport_failure_never_exposes_private_detail(self):
        def unavailable(*args, **kwargs):
            raise RuntimeError("secret-provider-detail")
        self.consumer.api_get = unavailable
        with self.assertRaises(SiteEvidenceError) as caught: self.verify()
        self.assertEqual(caught.exception.code, "unverifiable")
        self.assertNotIn("secret-provider-detail", str(caught.exception))

    def test_wrong_member_and_duplicate_json_fields_are_rejected(self):
        self.pack(member="other.json")
        with self.assertRaisesRegex(SiteEvidenceError, "member identity"):
            self.verify()
        payload = canonical_json(self.document).replace(b'"status":"passed"', b'"status":"failed","status":"passed"', 1)
        self.pack(payload=payload)
        with self.assertRaisesRegex(SiteEvidenceError, "JSON"):
            self.verify()

    def test_publication_record_drift_cannot_reuse_site_receipt(self):
        self.record["release_id"] += 1
        with self.assertRaisesRegex(SiteEvidenceError, "source publication differs"):
            self.verify()

    def test_unprotected_main_and_incomplete_job_inventory_are_refused(self):
        self.routes["/branches/main"]["protected"] = False
        with self.assertRaisesRegex(SiteEvidenceError, "main is not protected"):
            self.verify()
        self.routes["/branches/main"]["protected"] = True
        self.routes["/actions/runs/101/attempts/1/jobs?per_page=100&page=1"]["total_count"] = 2
        with self.assertRaisesRegex(SiteEvidenceError, "ended prematurely"):
            self.verify()

    def test_git_environment_cannot_substitute_another_repository(self):
        with patch.dict(os.environ, {"GIT_DIR": "/nonexistent", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"}):
            self.assertEqual(self.verify()["source_revision"], self.source)

    def test_transport_routes_are_closed_and_fail_without_http(self):
        before = len(self.calls)
        for route, raw in (("/repos/other/lmdj/branches/main", False), (self.prefix + "/actions/runs/101/attempts/2", False),
                           (self.prefix + "/actions/runs/101/rerun", False), (self.prefix + "/releases/1", False),
                           (self.prefix + "/actions/artifacts/303", True)):
            with self.assertRaises(GitHubApiError): self.client.get_changelog_site_evidence(route, raw=raw)
        self.assertEqual(len(self.calls), before)

    def test_missing_partial_clone_blob_is_not_hydrated_by_verification(self):
        self.assert_partial_clone_stays_passive()

    def test_protocol_guard_keeps_old_git_passive_without_lazy_fetch_flag(self):
        self.assert_partial_clone_stays_passive(omit_lazy_fetch=True)

    def assert_partial_clone_stays_passive(self, *, omit_lazy_fetch=False):
        self.assertEqual(self.verify()["source_revision"], self.source)
        self.git("config", "uploadpack.allowFilter", "true")
        self.git("config", "uploadpack.allowAnySHA1InWant", "true")
        clone = self.root / "partial"
        self.git("clone", "--filter=blob:none", "--no-checkout", self.root.as_uri(), str(clone))
        blob = self.git("rev-parse", self.source + ":" + LEDGER).strip()
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")
        absent = subprocess.run(["git", "-C", str(clone), "cat-file", "-e", blob],
                                capture_output=True, env=env)
        self.assertNotEqual(absent.returncode, 0, "fixture must omit the ledger blob")
        objects = clone / ".git" / "objects"
        inventory = lambda: {str(p.relative_to(objects)): p.read_bytes()
                             for p in objects.rglob("*") if p.is_file()}
        before = inventory()
        self.consumer.root = clone
        run = subprocess.run
        def without_lazy_fetch_flag(*args, **kwargs):
            kwargs["env"] = dict(kwargs["env"])
            kwargs["env"].pop("GIT_NO_LAZY_FETCH", None)
            return run(*args, **kwargs)
        seam = patch("tools.release.changelog_site_evidence.subprocess.run",
                     side_effect=without_lazy_fetch_flag) if omit_lazy_fetch else nullcontext()
        with seam, self.assertRaisesRegex(SiteEvidenceError, "Git provenance cannot be verified"):
            self.verify()
        self.assertEqual(inventory(), before, "read-only evidence must not hydrate objects")


if __name__ == "__main__":
    unittest.main()
