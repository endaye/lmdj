#!/usr/bin/env python3
"""Same-source publication metadata and doc-site projection checks."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.batch_reference import freeze
from tools.release.changelog import ChangelogError, binding, render
from tools.release.changelog_site import project
from tools.release.model import Disposition, ReleaseIntent, ReleaseKind, ReleaseLedger


class ChangelogSiteTest(unittest.TestCase):
    def setUp(self):
        self.document = {"schema": "lmdj.release-changelog.v1", "repository": "endaye/lmdj",
            "tag": "lmdj-v1.0.1.0", "product_build": "1.0.1.0", "profile": "web-hosts",
            "target_revision": "a" * 40, "baseline": None, "commits": ["a" * 40],
            "changes": [{"category": "fix", "area": "core", "text": "修复 fixture",
                         "commits": ["a" * 40]}], "exclusions": []}
        self.intent = ReleaseIntent("lmdj-v1.0.1.0", ReleaseKind.PRODUCT, "1.0.1.0", "a" * 40,
                                    Disposition.PUBLISHED, "web-hosts", (), changelog=freeze(self.document))
        digests = binding(self.document)
        self.publication = {"tag": self.intent.tag, "target_revision": self.intent.target_revision,
                            "release_id": 123, "published_at": "2026-09-13T00:00:00Z",
                            "plan_sha256": "b" * 64, "changelog_sha256": digests["sha256"],
                            "notes_sha256": digests["notes_sha256"]}

    def project(self, publications=None, intent=None):
        return project(ReleaseLedger((intent or self.intent,), ()), {
            "schema": "lmdj.release-changelog-publications.v1",
            "entries": publications if publications is not None else [self.publication]})

    def test_version_page_embeds_exact_common_notes_and_actual_identity(self):
        pages = self.project()
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[1]["file"], "apps/docs-site/docs/releases/1.0.1.0.mdx")
        body = pages[1]["content"]
        self.assertIn(render(self.document), body)
        self.assertIn("https://github.com/endaye/lmdj/releases/tag/" + self.intent.tag, body)
        self.assertIn(self.publication["published_at"], body)
        self.assertIn(self.publication["notes_sha256"], body)
        self.assertIn("Plan SHA-256 (reviewed publication record)", body)
        self.assertIn("不在此处重新认证远端 Release", body)
        self.assertIn("不表示两个 Host 已部署或已晋级", body)
        self.assertNotIn("versioned_docs", pages[1]["file"])

    def test_old_history_without_frozen_notes_is_not_fabricated(self):
        pages = self.project([], replace(self.intent, changelog=None))
        self.assertEqual(len(pages), 1)
        self.assertIn("暂无", pages[0]["content"])

    def test_published_bound_changelog_requires_publication_record(self):
        with self.assertRaisesRegex(ChangelogError, "lacks a publication record"):
            self.project([])

    def test_prepublication_intent_cannot_generate_published_page(self):
        for disposition in (Disposition.ALLOCATED, Disposition.RELEASABLE, Disposition.ABANDONED):
            with self.subTest(disposition=disposition):
                with self.assertRaisesRegex(ChangelogError, "unpublished"):
                    self.project(intent=replace(self.intent, disposition=disposition))

    def test_changed_digest_or_target_refused(self):
        for key, value in (("notes_sha256", "f" * 64), ("changelog_sha256", "f" * 64),
                           ("target_revision", "f" * 40)):
            with self.subTest(key=key):
                changed = dict(self.publication, **{key: value})
                with self.assertRaisesRegex(ChangelogError, "identities differ"):
                    self.project([changed])

    def test_duplicate_record_unknown_fields_and_invalid_date_refused(self):
        cases = [[self.publication, self.publication], [dict(self.publication, secret="no")],
                 [dict(self.publication, published_at="2026-02-30T00:00:00Z")],
                 [dict(self.publication, release_id=True)]]
        for entries in cases:
            with self.subTest(entries=entries):
                with self.assertRaises(ChangelogError):
                    self.project(entries)

    def test_index_sorts_publication_history_and_preserves_both_pages(self):
        newer = deepcopy(self.document)
        newer.update(tag="lmdj-v1.0.2.0", product_build="1.0.2.0")
        intent = replace(self.intent, tag=newer["tag"], identity=newer["product_build"], changelog=freeze(newer))
        digests = binding(newer)
        record = dict(self.publication, tag=intent.tag, release_id=124, published_at="2026-09-14T00:00:00Z",
                      changelog_sha256=digests["sha256"], notes_sha256=digests["notes_sha256"])
        pages = project(ReleaseLedger((self.intent, intent), ()), {
            "schema": "lmdj.release-changelog-publications.v1", "entries": [self.publication, record]})
        self.assertEqual(len(pages), 3)
        self.assertLess(pages[0]["content"].index("[1.0.2.0]"), pages[0]["content"].index("[1.0.1.0]"))


if __name__ == "__main__":
    unittest.main()
