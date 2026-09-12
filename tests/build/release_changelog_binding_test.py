#!/usr/bin/env python3
"""Producer → Draft → publication → remote audit frozen-body journey."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_transitions_test as fixtures
from tools.release.audit import _release_problem
from tools.release.changelog import ChangelogError, render
from tools.release.model import ReleaseModelError, load_ledger_document
from tools.release.prepare import PrepareError, prepare
from tools.release.profiles import AssetBuild, ProfileBuild
from tools.release.transitions import (TransitionError, create_draft, publish_draft,
                                      verify_draft, verify_published)


class ChangelogBindingTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReleaseTransitionsTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        f = self.fixture
        f.root = f.root / "with-changelog"
        f.profile = "web-hosts"
        self.record = {
            "schema": "lmdj.release-changelog.v1", "repository": "endaye/lmdj",
            "tag": f.tag, "product_build": "1.0.21.0", "profile": "web-hosts",
            "target_revision": f.target, "baseline": None, "commits": [f.target],
            "changes": [{"category": "fix", "area": "core", "text": "Fixture repair",
                         "commits": [f.target]}], "exclusions": [],
        }
        self.entry = {
            "tag": f.tag, "kind": "product", "identity": "1.0.21.0",
            "target_revision": f.target, "channel": "canary", "disposition": "releasable",
            "profile": "web-hosts", "snapshot": "1.0.21.0", "merged_main_run_id": 123,
            "evidence_paths": ["docs/quality/example-proof.md"], "changelog": self.record,
        }
        f.ledger = self.load_entry(self.entry)

    def load_entry(self, entry):
        return load_ledger_document({"schema": "lmdj.release-intents.v1", "entries": [entry],
                                     "historical_exceptions": []}, self.fixture.policy)

    def prepare(self):
        f = self.fixture
        def builder(profile, tree, output, intent):
            assets = []
            for name, payload in f._asset_payloads():
                path = output / name
                path.write_bytes(payload)
                assets.append(AssetBuild(path, name, len(payload), hashlib.sha256(payload).hexdigest()))
            return ProfileBuild(tuple(assets))
        # Existing fixture has synthetic SHAs/signatures/API. The companion
        # release_changelog_test exercises real Git source verification.
        with patch("tools.release.prepare.verify_changelog_source") as source:
            result = prepare(f.tag, replace(f.context(), profile_builder=builder))
            source.assert_called_once_with(f.root, f.ledger.entries[0], f.ledger, self.record)
        return result

    def publish(self, created):
        f = self.fixture
        return publish_draft(f.tag, created.release_id, created.plan_sha256, f.context(),
                             actions_environment={"GITHUB_ACTIONS": "true",
                                                  "GITHUB_EVENT_NAME": "workflow_dispatch"})

    def audit_problem(self):
        f = self.fixture
        return _release_problem(f.policy, f.ledger.entries[0], f.git.remote, f.github.release,
                                latest_release_id=None, allow_missing_marker=False)

    def test_full_producer_publication_and_audit_journey_share_frozen_body(self):
        f = self.fixture
        prepared = self.prepare()
        plan = json.loads((prepared.output_root / "release-plan.json").read_text())
        self.assertEqual(plan["changelog"], self.record)
        self.assertEqual((prepared.output_root / "release-notes.md").read_text(), render(self.record))
        created = f._push_and_create()
        self.assertEqual(len(created.assets), 6)
        self.assertIn("lmdj.release-plan-marker.v4", f.github.release.body)
        original = f.github.release.body
        verify_draft(f.tag, created.release_id, created.plan_sha256, f.context())
        self.assertIsNone(self.audit_problem())
        self.publish(created)
        self.assertEqual(f.github.release.body, original)
        self.assertEqual(verify_published(f.tag, created.release_id, created.plan_sha256,
                                         f.context()).status, "published")
        self.assertIsNone(self.audit_problem())

    def test_prepare_resume_rejects_changed_saved_notes(self):
        prepared = self.prepare()
        (prepared.output_root / "release-notes.md").write_text("Modified notes\n")
        with self.assertRaisesRegex(PrepareError, "reconcile"):
            self.prepare()

    def test_changed_local_notes_prevent_draft_creation(self):
        f = self.fixture
        prepared = self.prepare()
        (prepared.output_root / "release-notes.md").write_text("Modified notes\n")
        with self.assertRaisesRegex(TransitionError, "frozen changelog"):
            f._push_and_create()
        self.assertIsNone(f.github.release)

    def test_changed_draft_text_blocks_verify_publish_and_audit(self):
        f = self.fixture
        self.prepare()
        created = f._push_and_create()
        f.github.release = replace(f.github.release, body=f.github.release.body.replace("Fixture repair", "Invented feature"))
        with self.assertRaisesRegex(TransitionError, "frozen changelog"):
            verify_draft(f.tag, created.release_id, created.plan_sha256, f.context())
        with self.assertRaisesRegex(TransitionError, "frozen changelog"):
            self.publish(created)
        self.assertTrue(f.github.release.draft)
        self.assertIn("frozen changelog", self.audit_problem())

    def test_changed_published_text_fails_remote_verification(self):
        f = self.fixture
        self.prepare()
        created = f._push_and_create()
        self.publish(created)
        f.github.release = replace(f.github.release, body=f.github.release.body + "\nUnbound text")
        with self.assertRaisesRegex(TransitionError, "frozen changelog"):
            verify_published(f.tag, created.release_id, created.plan_sha256, f.context())
        self.assertIn("frozen changelog", self.audit_problem())

    def test_reviewed_ledger_content_change_cannot_reuse_old_plan(self):
        self.prepare()
        changed = deepcopy(self.entry)
        changed["changelog"]["changes"][0]["text"] = "Different reviewed wording"
        self.fixture.ledger = self.load_entry(changed)
        with self.assertRaisesRegex(TransitionError, "reconcile"):
            self.fixture._push_and_create()

    def test_source_failure_prevents_prepare_output(self):
        f = self.fixture
        with patch("tools.release.prepare.verify_changelog_source", side_effect=ChangelogError("source differs")):
            with self.assertRaises(PrepareError):
                prepare(f.tag, f.context())
        self.assertFalse((f.root / "build/release").exists())
        self.assertEqual(f.git.pushes, 0)

    def test_ledger_binds_content_identity_and_deep_freezes_it(self):
        record = self.fixture.ledger.entries[0].changelog
        with self.assertRaises(TypeError):
            record["changes"][0]["text"] = "mutated"
        for field, value in (("target_revision", "c" * 40), ("tag", "lmdj-v1.0.99.0"),
                             ("profile", "web-runtime-host")):
            with self.subTest(field=field):
                changed = deepcopy(self.entry)
                changed["changelog"][field] = value
                with self.assertRaises(ReleaseModelError):
                    self.load_entry(changed)

    def test_marker_binding_cannot_be_changed_with_body_kept_intact(self):
        f = self.fixture
        self.prepare()
        f._push_and_create()
        f.github.release = replace(f.github.release, body=f.github.release.body.replace('"notes_sha256":"', '"notes_sha256":"0'))
        self.assertIn("bind the frozen changelog", self.audit_problem())

    def test_historical_missing_marker_exception_cannot_excuse_bound_changelog(self):
        f = self.fixture
        self.prepare()
        f._push_and_create()
        f.github.release = replace(f.github.release, body=render(self.record))
        problem = _release_problem(f.policy, f.ledger.entries[0], f.git.remote, f.github.release,
                                   latest_release_id=None, allow_missing_marker=True)
        self.assertEqual(problem, "GitHub Release plan marker is missing")

    def test_literal_protocol_name_in_notes_is_not_an_extra_marker(self):
        f = self.fixture
        self.record["changes"][0]["text"] = "Repairs lmdj.release-plan-marker.v4 compatibility"
        f.ledger = self.load_entry(self.entry)
        self.prepare()
        created = f._push_and_create()
        self.assertIsNone(self.audit_problem())
        self.publish(created)
        self.assertEqual(verify_published(f.tag, created.release_id, created.plan_sha256,
                                         f.context()).status, "published")
        self.assertIsNone(self.audit_problem())

    def test_intent_change_at_last_publication_authority_read_blocks_patch(self):
        from tools.release import transitions
        f = self.fixture
        self.prepare()
        created = f._push_and_create()
        original = transitions._formal_authority
        reads = []
        def changed_authority(*args, **kwargs):
            reads.append(1)
            if len(reads) == 3:
                entry = deepcopy(self.entry)
                entry["changelog"]["changes"][0]["text"] = "Concurrent changed notes"
                f.ledger = self.load_entry(entry)
            return original(*args, **kwargs)
        with patch.object(transitions, "_formal_authority", side_effect=changed_authority):
            with self.assertRaisesRegex(TransitionError, "intent changed before publication"):
                self.publish(created)
        self.assertTrue(f.github.release.draft)

    def test_v4_preserves_authenticated_complete_batch_evidence_through_publication(self):
        import release_batch_binding_test as batch_fixtures
        batch = batch_fixtures.BatchBindingTest()
        batch.setUp()
        self.addCleanup(batch.doCleanups)
        f = self.fixture
        f.root, f.target, f.policy = batch.e.root, batch.e.control, batch.policy
        f.git = fixtures.FakeGit(f.target, f.policy.product_fingerprint)
        f.github = fixtures.FakeGitHub(f.target)
        f.github.get_batch_evidence = batch.github.get_batch_evidence
        self.record["target_revision"] = f.target
        self.record["commits"] = [f.target]
        self.record["changes"][0]["commits"] = [f.target]
        self.entry.update(target_revision=f.target, merged_main_run_id=102,
                          batch_test_evidence=batch.e.ref)
        f.ledger = self.load_entry(self.entry)
        self.prepare()
        created = f._push_and_create()
        self.assertIn(batch.e.ref["evidence_digest"], f.github.release.body)
        self.assertIn("lmdj.release-plan-marker.v4", f.github.release.body)
        self.publish(created)
        self.assertEqual(verify_published(f.tag, created.release_id, created.plan_sha256,
                                         f.context()).status, "published")
        self.assertIsNone(self.audit_problem())
        f.github.release = replace(f.github.release, body=f.github.release.body.replace(
            batch.e.ref["evidence_digest"], "f" * 64))
        self.assertIn("exact batch reference", self.audit_problem())


if __name__ == "__main__":
    unittest.main()
