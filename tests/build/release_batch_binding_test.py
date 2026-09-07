#!/usr/bin/env python3
"""Actual Git/HTTP/consumer to release routing and permanent-marker boundaries.

All identities are temporary fixtures. No release command, tag or remote write.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_batch_evidence_test as evidence_fixture
from tools.release.batch_reference import freeze
from tools.release.ci_evidence import verify_release_ci
from tools.release.model import load_policy, load_ledger_document, canonical_json, Disposition
from tools.release.prepare import _verify_ci, _plan_document, PrepareError
from tools.release.audit import _ci_problem, _release_problem
from tools.release.transitions import marker_for_plan, TransitionError


class BatchBindingTest(unittest.TestCase):
    def setUp(self):
        self.e = evidence_fixture.BatchReleaseEvidenceTest()
        self.e.setUp()
        self.addCleanup(self.e.doCleanups)
        # The production entry owns its clock. Keep fixture retention relative
        # to it rather than making all prospective journeys expire in October.
        for rows in self.e.artifacts.values():
            for row in rows:
                row["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.policy = replace(load_policy(ROOT / "tools/release/policy.json"),
            batch_evidence_source=freeze({"repository_id": 11, "workflow_id": 7,
                "workflow_path": ".github/workflows/self-test-report.yml", "producer_revision": self.e.control}))
        # Production GET adapter, including archive redirect authentication.
        from tools.release.github_api import GitHubClient, HttpResponse
        from release_github_api_test import SIGNED_REDIRECT
        evidence = self.e
        class Transport:
            def __init__(self):
                self.requests = []
            def __call__(self, method, url, headers, body):
                self.requests.append((method, url, dict(headers)))
                if url.startswith("https://api.github.com") or url.startswith("/repos/"):
                    path = url.removeprefix("https://api.github.com")
                    if path.endswith("/zip"):
                        return HttpResponse(302, {"Location": SIGNED_REDIRECT + "&artifact=" + path.split("/artifacts/")[1].split("/")[0]}, b"")
                    return HttpResponse(200, {}, json.dumps(evidence.get(path)).encode())
                identifier = int(url.split("&artifact=")[1])
                return HttpResponse(200, {"Content-Type": "application/zip"}, evidence.downloads[identifier])
        self.transport = Transport()
        self.github = GitHubClient(http_transport=self.transport, token="fixture-token")
        item = {"tag": "module/application-facade/v1.0.1", "kind": "module", "identity": "application-facade@1.0.1",
            "target_revision": self.e.control, "disposition": "releasable", "profile": "source-only",
            "merged_main_run_id": 102, "evidence_paths": ["evidence.md"], "batch_test_evidence": self.e.ref}
        self.intent = load_ledger_document({"schema": "lmdj.release-intents.v1", "entries": [item], "historical_exceptions": []}, self.policy).entries[0]
        self.context = SimpleNamespace(github=self.github, policy=self.policy, repo_root=self.e.root)

    def verify(self, intent=None, policy=None):
        return verify_release_ci(self.github, policy=policy or self.policy, intent=intent or self.intent, git_root=self.e.root)

    def test_full_real_git_http_chain_reaches_prepare_and_audit_without_writes(self):
        run = _verify_ci(self.context, self.intent)
        self.assertEqual((run.id, run.head_sha, run.workflow_name), (102, self.e.executor_control, "Self-test Report"))
        self.assertIsNone(_ci_problem(self.context, self.intent))
        self.assertTrue(self.transport.requests)
        self.assertTrue(all(method == "GET" for method, _, _ in self.transport.requests))
        downloads = [headers for _, url, headers in self.transport.requests if "blob.core.windows.net" in url]
        self.assertTrue(downloads)
        self.assertTrue(all(not any(k.lower() == "authorization" for k in headers) for headers in downloads))

    def test_no_reference_never_falls_back_to_legacy_fourteen(self):
        result = self.verify(replace(self.intent, batch_test_evidence=None))
        self.assertEqual(result.code, "unverifiable")
        self.assertEqual(self.transport.requests, [])

    def test_mixed_sources_and_old_protocol_batch_are_rejected_before_http(self):
        self.assertEqual(self.verify(replace(self.intent, self_test_evidence={})).code, "conflict")
        for protocol in ("self-test-v1", "ci-scope-v2"):
            self.assertEqual(self.verify(policy=replace(self.policy, prospective_ci_protocol=protocol)).code, "conflict")
        self.assertEqual(self.transport.requests, [])

    def test_frozen_source_policy_is_revalidated_without_weakening_closed_shape(self):
        self.assertEqual(self.verify().code, "ok")
        for field, value in (("workflow_path", ".github/workflows/ci.yml"), ("repository_id", True), ("extra", 1)):
            with self.subTest(field=field):
                source = dict(self.policy.batch_evidence_source)
                source[field] = value
                before = len(self.transport.requests)
                self.assertEqual(self.verify(policy=replace(self.policy, batch_evidence_source=freeze(source))).code, "conflict")
                self.assertEqual(len(self.transport.requests), before)

    def test_focused_none_wrong_sha_or_event_cannot_prepare(self):
        for mutation in ("focused", "none", "target", "event"):
            with self.subTest(mutation=mutation):
                ref = deepcopy(self.e.ref)
                if mutation in ("focused", "none"):
                    ref["request"]["selection"]["kind"] = mutation
                elif mutation == "target":
                    ref["request"]["target"] = self.e.executor_control
                else:
                    ref["executor_event"] = "push"
                with self.assertRaises(PrepareError):
                    _verify_ci(self.context, replace(self.intent, batch_test_evidence=freeze(ref)))

    def test_current_candidates_require_retained_evidence_and_latest_attempt_one(self):
        self.e.artifacts[102][0]["expired"] = True
        self.assertEqual(self.verify().code, "unverifiable")
        self.e.artifacts[102][0]["expired"] = False
        self.e.route("/actions/runs/102", dict(self.e.executor_run, run_attempt=2, conclusion="failure"))
        self.assertEqual(self.verify().code, "conflict")

    def test_only_published_uses_recorded_attempt_without_artifacts(self):
        self.e.route("/actions/runs/102", dict(self.e.executor_run, run_attempt=2, conclusion="failure"))
        for disposition in (Disposition.ALLOCATED, Disposition.ABANDONED, Disposition.SUPERSEDED_UNRELEASED):
            self.assertEqual(self.verify(replace(self.intent, disposition=disposition)).code, "conflict")
        result = self.verify(replace(self.intent, disposition=Disposition.PUBLISHED))
        self.assertEqual(result.code, "ok", result.message)
        paths = [url for _, url, _ in self.transport.requests]
        self.assertTrue(any("/attempts/1" in path for path in paths))
        self.assertFalse(any("/artifacts" in path or path.endswith("/runs/102") for path in paths))

    def test_published_recorded_identity_and_event_still_fail_closed(self):
        self.e.executor_run["event"] = "push"
        self.assertEqual(self.verify(replace(self.intent, disposition=Disposition.PUBLISHED)).code, "conflict")

    def document(self):
        run = _verify_ci(self.context, self.intent)
        plan = SimpleNamespace(schema="lmdj.release-plan.v1", repository=self.policy.repository, tag=self.intent.tag,
            tag_object="b" * 40, target_revision=self.intent.target_revision, kind=self.intent.kind,
            identity=self.intent.identity, profile=self.intent.profile, channel=None, assets=())
        return _plan_document(plan, self.intent, run, self.policy)

    def release(self, body):
        return SimpleNamespace(id=1, tag_name=self.intent.tag, name="module " + self.intent.identity,
            draft=False, prerelease=False, target_commitish=self.intent.target_revision, body=body)

    def marker_problem(self, body):
        return _release_problem(self.policy, replace(self.intent, disposition=Disposition.PUBLISHED),
            SimpleNamespace(object_id="b" * 40), self.release(body), latest_release_id=None, allow_missing_marker=True)

    def test_prepare_plan_freezes_entire_reference_and_v3_marker_binds_it(self):
        document = self.document()
        self.assertEqual(document["ci"]["batch_test_evidence"], self.e.ref)
        self.assertNotEqual(document["ci"]["head_sha"], document["ci"]["target_revision"])
        marker = marker_for_plan(document, hashlib.sha256(canonical_json(document)).hexdigest())
        self.assertIn("lmdj.release-plan-marker.v3", marker)
        self.assertIsNone(self.marker_problem(marker))
        document["ci"]["batch_test_evidence"]["request"]["selection"]["suites"].clear()
        self.assertEqual(len(self.intent.batch_test_evidence["request"]["selection"]["suites"]), 16)

    def test_marker_missing_old_schema_and_each_reference_identity_drift_rejected(self):
        document = self.document()
        marker = marker_for_plan(document, "d" * 64)
        self.assertIsNotNone(self.marker_problem("no permanent marker"))
        for version in ("v1", "v2"):
            self.assertIsNotNone(self.marker_problem(marker.replace("marker.v3", "marker." + version)))
        for field in ("executor_event", "origin_record_digest", "admission_record_digest", "evidence_digest", "executor_control_revision"):
            with self.subTest(field=field):
                changed = deepcopy(document)
                changed["ci"]["batch_test_evidence"][field] = "drift"
                self.assertIsNotNone(self.marker_problem(marker_for_plan(changed, "d" * 64)))
        self.assertIsNotNone(self.marker_problem(marker + marker))

    def test_mixed_plan_reference_never_gets_a_marker(self):
        document = self.document()
        document["ci"]["self_test_evidence"] = {}
        with self.assertRaises(TransitionError):
            marker_for_plan(document, "d" * 64)

    def test_full_prepare_orchestration_writes_only_local_exact_reference_plan(self):
        import release_prepare_test as fixture
        from tools.release.prepare import prepare
        f = fixture.ReleasePrepareTest()
        f.setUp()
        self.addCleanup(f.tearDown)
        f.root, f.target_sha, f.policy = self.e.root, self.e.control, self.policy
        f.git = fixture.FakeGit(self.e.control, self.policy.product_fingerprint)
        f.ledger = f.ledger_fixture()
        f.ledger = replace(f.ledger, entries=tuple(replace(i, merged_main_run_id=102,
            batch_test_evidence=self.intent.batch_test_evidence) for i in f.ledger.entries))
        f.github.get_batch_evidence = self.github.get_batch_evidence
        f.github.branch = replace(f.github.branch, commit_sha=self.e.control)
        prepared = prepare(f.tag, f.context())
        document = json.loads((prepared.output_root / "release-plan.json").read_text())
        self.assertEqual(document["ci"]["batch_test_evidence"], self.e.ref)
        self.assertEqual(document["ci"]["target_revision"], self.e.control)
        self.assertEqual(document["ci"]["head_sha"], self.e.executor_control)
        self.assertEqual(hashlib.sha256(canonical_json(document)).hexdigest(), prepared.digest)
        self.assertEqual(f.github.remote_mutations, [])
        self.assertEqual(f.git.remote_mutations, [])

    def test_actual_audit_published_requires_tag_release_marker_and_closed_assets(self):
        import release_audit_test as fixture
        from tools.release.audit import audit
        from tools.release.github_api import GitHubAsset
        f = fixture.ReleaseAuditFixture()
        f.setUp()
        self.addCleanup(f.tearDown)
        f.root, f.policy = self.e.root, self.policy
        f.install_static_authority(f.root)
        (f.root / "evidence.md").write_text("temporary audit fixture\n")
        self.e.git("add", "evidence.md")
        f.git.authority_root = f.root
        f.git.main_ancestor_targets.add(self.e.control)
        f.github.get_batch_evidence = self.github.get_batch_evidence
        item = f.entry()
        item.update(target_revision=self.e.control, merged_main_run_id=102, batch_test_evidence=self.e.ref)
        tag = item["tag"]
        document = self.document()
        marker = marker_for_plan(document, "d" * 64)
        valid_tag = f.tag_state(target=self.e.control)
        valid_release = f.release(tag, target=self.e.control, body=marker)
        def finding():
            report = audit(f.context([item]), remote=True, tag=tag)
            return next(row for row in report.findings if row.subject == tag)
        self.assertEqual(finding().code, "missing", finding().message)
        f.git.tags[tag] = valid_tag
        self.assertEqual(finding().code, "missing", finding().message)
        f.github.releases[tag] = valid_release
        self.assertEqual(finding().code, "ok", finding().message)
        # Published identity survives ephemeral deletion and a later failed
        # rerun, but not permanent proof drift.
        self.e.route("/actions/runs/102", dict(self.e.executor_run, run_attempt=2, conclusion="failure"))
        self.e.artifacts[102].clear()
        self.assertEqual(finding().code, "ok", finding().message)
        for changed in (replace(valid_release, draft=True), replace(valid_release, body="missing"),
                        replace(valid_release, body=marker.replace("marker.v3", "marker.v2"))):
            f.github.releases[tag] = changed
            self.assertNotEqual(finding().code, "ok")
        f.github.releases[tag] = replace(valid_release, assets=(GitHubAsset(123, "unexpected.zip", 1,
            "https://example.invalid/x", "https://example.invalid/x", valid_release.id, None, "application/zip", "uploaded"),))
        self.assertNotEqual(finding().code, "ok")
        f.github.releases[tag] = valid_release
        f.git.tags[tag] = replace(valid_tag, target_revision=self.e.executor_control)
        self.assertNotEqual(finding().code, "ok")
        self.assertEqual(f.github.mutations, [])
        self.assertEqual(f.git.mutations, [])

    def test_transition_recomputes_v3_and_published_history_cannot_hide_bad_signer_or_asset(self):
        import release_transitions_test as fixture
        from tools.release.transitions import create_draft
        f = fixture.ReleaseTransitionsTest()
        f.setUp()
        self.addCleanup(f.tearDown)
        f.root, f.target, f.policy = self.e.root, self.e.control, self.policy
        f.git = fixture.FakeGit(self.e.control, self.policy.product_fingerprint)
        f.github = fixture.FakeGitHub(self.e.control)
        f.github.get_batch_evidence = self.github.get_batch_evidence
        f.ledger = replace(f.ledger, entries=tuple(replace(i, target_revision=self.e.control,
            merged_main_run_id=102, batch_test_evidence=self.intent.batch_test_evidence) for i in f.ledger.entries))
        f._write_prepared_output()
        document = f._plan()
        document["ci"] = self.document()["ci"]
        output = f.root / "build/release" / f.tag
        (output / "release-plan.json").write_bytes(canonical_json(document))
        (output / "release-plan.sha256").write_text(hashlib.sha256(canonical_json(document)).hexdigest() + "\n")
        f.git.remote = f.git.local
        result = create_draft(f.tag, f.context())
        self.assertEqual(result.status, "draft-created")
        self.assertIn("lmdj.release-plan-marker.v3", f.github.release.body)
        self.assertIn(self.e.ref["evidence_digest"], f.github.release.body)
        f.github.release = replace(f.github.release, draft=False)
        f.ledger = replace(f.ledger, entries=tuple(replace(i, disposition=Disposition.PUBLISHED) for i in f.ledger.entries))
        self.e.route("/actions/runs/102", dict(self.e.executor_run, run_attempt=2, conclusion="failure"))
        self.e.artifacts[102].clear()
        self.assertEqual(create_draft(f.tag, f.context()).status, "already-published")
        created, uploaded = f.github.create_calls, list(f.github.upload_calls)
        original_tag = f.git.remote
        f.git.remote = replace(original_tag, signer_fingerprint="f" * 40)
        with self.assertRaises(TransitionError):
            create_draft(f.tag, f.context())
        f.git.remote = original_tag
        asset = f.github.release.assets[0]
        f.github.payloads[asset.id] = b"changed bytes"
        with self.assertRaises(TransitionError):
            create_draft(f.tag, f.context())
        self.assertEqual(f.github.create_calls, created)
        self.assertEqual(f.github.upload_calls, uploaded)


if __name__ == "__main__":
    unittest.main()
