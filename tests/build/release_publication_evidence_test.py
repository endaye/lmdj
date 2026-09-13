#!/usr/bin/env python3
"""Verified publication → real Git evidence patch → same-request reconciliation."""

from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_publication_test as fixtures
from tools.release import cli
from tools.release.changelog import ChangelogError, binding, render
from tools.release.changelog_site import project
from tools.release.model import canonical_json, load_ledger_document
from tools.release.publication_evidence import LEDGER, PUBLICATIONS, PIN, INDEX, PAGES, collect_publication_patch, _rewrite_entry, _diff
from tools.release.transitions import TransitionError


class PublicationEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.journey = fixtures.PublicationTest()
        self.journey.setUp()
        self.addCleanup(self.journey.doCleanups)
        self.f = self.journey.fixture
        self.root = self.f.root.resolve()
        self.entry = deepcopy(self.journey.journey.entry)
        self.document = {"schema": "lmdj.release-intents.v1", "entries": [self.entry], "historical_exceptions": []}
        self.publications = {"schema": "lmdj.release-changelog-publications.v1", "entries": []}
        self.write_sources()
        self.write(PIN, "// Independent reviewed inventory, not an observed count.\nexport const SOURCE_DOCUMENT_COUNT = 47;\n")
        self.write("apps/docs-site/versioned_docs/version-1.0.0.0/frozen.mdx", "frozen\n")
        self.git("init", "-q")
        self.git("add", "docs", "apps")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")

    def write(self, relative, text):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def write_sources(self):
        lines = [json.dumps(entry, ensure_ascii=False, separators=(",", ":")) for entry in self.document["entries"]]
        self.write(LEDGER, '{\n  "schema":"lmdj.release-intents.v1",\n  "entries":[\n    '
                   + ',\n    '.join(lines) + '\n  ],\n  "historical_exceptions":[]\n}\n')
        self.write(PUBLICATIONS, canonical_json(self.publications).decode())
        ledger = load_ledger_document(self.document, self.f.policy)
        for page in project(ledger, self.publications):
            self.write(page["file"], page["content"])

    def git(self, *args, input=None, check=True):
        return subprocess.run(["git", "-C", str(self.root), *args], input=input,
                              text=True, capture_output=True, check=check)

    def collect(self):
        return collect_publication_patch(self.f.tag, self.journey.created.release_id,
                                         self.journey.created.plan_sha256, self.f.context())

    def test_actual_patch_applies_and_reconcile_is_empty_without_external_writes(self):
        before = (self.f.github.release, deepcopy(self.f.github.payloads), self.f.ledger,
                  self.f.github.create_calls, list(self.f.github.patch_calls), self.f.git.pushes)
        original_ledger = deepcopy(self.document)
        delta = self.collect()
        self.assertEqual(delta, self.collect())
        self.assertEqual(self.git("diff").stdout, "")
        self.git("apply", "--check", "-", input=delta)
        self.git("apply", "-", input=delta)
        actual = json.loads((self.root / LEDGER).read_text())
        original_ledger["entries"][0]["disposition"] = "published"
        self.assertEqual(actual, original_ledger)
        self.assertEqual(json.loads((self.root / PUBLICATIONS).read_text())["entries"], [self.journey.collect()])
        filename = PAGES + "/" + self.entry["identity"] + ".mdx"
        self.assertIn(render(self.entry["changelog"]), (self.root / filename).read_text())
        self.assertIn("SOURCE_DOCUMENT_COUNT = 48;", (self.root / PIN).read_text())
        self.assertEqual(self.collect(), "")
        self.assertEqual((self.f.github.release, self.f.github.payloads, self.f.ledger,
                          self.f.github.create_calls, self.f.github.patch_calls, self.f.git.pushes), before)
        self.assertEqual((self.root / "apps/docs-site/versioned_docs/version-1.0.0.0/frozen.mdx").read_text(), "frozen\n")
        self.git("add", "docs", "apps")
        changed = set(self.git("diff", "--cached", "--name-only").stdout.splitlines())
        self.assertEqual(changed, {LEDGER, PUBLICATIONS, PIN, INDEX, filename})

    def test_previous_release_page_and_ledger_line_remain_byte_identical(self):
        older = deepcopy(self.entry)
        older.update(tag="lmdj-v1.0.20.0", identity="1.0.20.0", snapshot="1.0.20.0", disposition="published")
        older["changelog"].update(tag=older["tag"], product_build=older["identity"])
        self.document["entries"].insert(0, older)
        digests = binding(older["changelog"])
        self.publications["entries"].append(dict(self.journey.collect(), tag=older["tag"], release_id=999,
            published_at="2026-09-12T00:00:00Z", changelog_sha256=digests["sha256"], notes_sha256=digests["notes_sha256"]))
        self.write_sources()
        older_page = self.root / PAGES / "1.0.20.0.mdx"
        before = older_page.read_bytes()
        ledger_line = (self.root / LEDGER).read_text().splitlines()[3]
        self.git("apply", "-", input=self.collect())
        self.assertEqual(older_page.read_bytes(), before)
        self.assertEqual((self.root / LEDGER).read_text().splitlines()[3], ledger_line)

    def test_local_authority_drift_prevents_patch(self):
        self.document["entries"][0]["evidence_paths"].append("docs/quality/unreviewed.md")
        self.write_sources()
        with self.assertRaisesRegex(ChangelogError, "canonical intents differ"):
            self.collect()

    def test_unpublished_api_prevents_patch(self):
        self.f.github.release = replace(self.f.github.release, draft=True)
        with self.assertRaises(TransitionError):
            self.collect()

    def test_edited_existing_page_prevents_patch(self):
        self.write(INDEX, "Invented release index\n")
        with self.assertRaisesRegex(ChangelogError, "frozen projection"):
            self.collect()

    def test_unknown_page_is_not_silently_removed(self):
        self.write(PAGES + "/1.0.999.0.mdx", "retain me\n")
        with self.assertRaisesRegex(ChangelogError, "inventory differs"):
            self.collect()

    def test_missing_index_is_not_silently_restored(self):
        (self.root / INDEX).unlink()
        with self.assertRaisesRegex(ChangelogError, "inventory differs"):
            self.collect()

    def test_existing_record_with_changed_plan_cannot_be_rewritten(self):
        self.git("apply", "-", input=self.collect())
        document = json.loads((self.root / PUBLICATIONS).read_text())
        document["entries"][0]["plan_sha256"] = "f" * 64
        self.write(PUBLICATIONS, canonical_json(document).decode())
        ledger = load_ledger_document(json.loads((self.root / LEDGER).read_text()), self.f.policy)
        for page in project(ledger, document):
            self.write(page["file"], page["content"])
        with self.assertRaisesRegex(ChangelogError, "record conflicts"):
            self.collect()

    def test_symlink_source_is_refused_without_touching_target(self):
        target = self.root / LEDGER
        outside = self.root / "preserved.json"
        original = target.read_bytes()
        target.rename(outside)
        target.symlink_to(outside)
        with self.assertRaisesRegex(ChangelogError, "regular file"):
            self.collect()
        self.assertEqual(outside.read_bytes(), original)

    def test_pin_increment_does_not_recount_observed_pages(self):
        # An incorrect pre-existing pin stays independently incorrect; adding a
        # page cannot silently hide another missing ordinary portal document.
        self.write(PIN, "export const SOURCE_DOCUMENT_COUNT = 100;\n")
        self.git("apply", "-", input=self.collect())
        self.assertEqual((self.root / PIN).read_text(), "export const SOURCE_DOCUMENT_COUNT = 101;\n")

    def test_duplicate_pin_is_refused(self):
        self.write(PIN, "export const SOURCE_DOCUMENT_COUNT = 47;\n" * 2)
        with self.assertRaisesRegex(ChangelogError, "count pin is unavailable"):
            self.collect()

    def test_unicode_line_separators_are_content_not_git_patch_boundaries(self):
        for separator in ("\u2028", "\u0085"):
            with self.subTest(separator=repr(separator)):
                self.write(PIN, f"// first{separator}second\nexport const SOURCE_DOCUMENT_COUNT = 47;\n")
                delta = self.collect()
                self.git("apply", "--check", "-", input=delta)
                self.git("apply", "-", input=delta)
                self.assertEqual((self.root / PIN).read_text(),
                                 f"// first{separator}second\nexport const SOURCE_DOCUMENT_COUNT = 48;\n")
                self.git("apply", "--reverse", "-", input=delta)

    def test_invalid_source_encoding_has_actionable_failure(self):
        (self.root / PUBLICATIONS).write_bytes(b"\xff")
        with self.assertRaisesRegex(ChangelogError, "invalid UTF-8.*remedy"):
            self.collect()

    def test_unicode_separator_in_json_entry_is_preserved_when_disposition_changes(self):
        original = (self.root / LEDGER).read_text().replace("Fixture repair", "Fixture\u2028repair")
        self.write(LEDGER, original)
        rewritten = _rewrite_entry(original, self.f.tag)
        expected = json.loads(original)
        expected["entries"][0]["disposition"] = "published"
        self.assertEqual(json.loads(rewritten), expected)
        delta = _diff(LEDGER, original, rewritten)
        self.git("apply", "--check", "-", input=delta)
        self.git("apply", "-", input=delta)
        self.assertEqual((self.root / LEDGER).read_text(), rewritten)

    def test_changed_source_causes_real_git_apply_to_refuse_without_partial_changes(self):
        delta = self.collect()
        self.write(INDEX, "new user edit\n")
        ledger_before = (self.root / LEDGER).read_bytes()
        result = self.git("apply", "-", input=delta, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / LEDGER).read_bytes(), ledger_before)
        self.assertFalse((self.root / PAGES / (self.entry["identity"] + ".mdx")).exists())

    def test_cli_emits_only_verified_patch(self):
        output = io.StringIO()
        with patch.object(cli, "build_context", return_value=self.f.context()), redirect_stdout(output):
            result = cli.main(["--repo-root", str(self.root), "publication-patch", self.f.tag,
                               str(self.journey.created.release_id), self.journey.created.plan_sha256])
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), self.collect())


if __name__ == "__main__":
    unittest.main()
