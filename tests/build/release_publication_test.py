#!/usr/bin/env python3
"""Verified Release → canonical publication record, never a new release write."""

from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_changelog_binding_test as fixtures
from tools.release import cli
from tools.release.changelog_site import project
from tools.release.github_api import GitHubApiError, GitHubClient, HttpResponse
from tools.release.model import Disposition, ReleaseLedger, canonical_json
from tools.release.publication import PublicationError, collect_publication
from tools.release.transitions import TransitionError, verify_published


class PublicationTest(unittest.TestCase):
    def setUp(self):
        self.journey = fixtures.ChangelogBindingTest()
        self.journey.setUp()
        self.addCleanup(self.journey.doCleanups)
        self.fixture = self.journey.fixture
        self.journey.prepare()
        self.created = self.fixture._push_and_create()
        self.journey.publish(self.created)
        self.fixture.github.release = replace(self.fixture.github.release, published_at="2026-09-13T00:00:00Z")

    def collect(self):
        f = self.fixture
        return collect_publication(f.tag, self.created.release_id, self.created.plan_sha256, f.context())

    def test_collect_reconcile_and_project_preserve_every_external_object(self):
        f = self.fixture
        original = (f.github.release, deepcopy(f.github.payloads), f.git.local, f.git.remote, f.ledger)
        writes = (f.github.create_calls, list(f.github.upload_calls), list(f.github.patch_calls), f.git.pushes)
        record = self.collect()
        self.assertEqual(self.collect(), record)
        self.assertEqual(record["release_id"], self.created.release_id)
        self.assertEqual(record["published_at"], f.github.release.published_at)
        self.assertEqual(record["plan_sha256"], self.created.plan_sha256)
        self.assertEqual((f.github.release, f.github.payloads, f.git.local, f.git.remote, f.ledger), original)
        self.assertEqual((f.github.create_calls, f.github.upload_calls, f.github.patch_calls, f.git.pushes), writes)
        # Publication can precede the reviewed ledger PR. Collector does not
        # change that authority; the consumer requires the later published state.
        self.assertEqual(f.ledger.entries[0].disposition, Disposition.RELEASABLE)
        published = replace(f.ledger.entries[0], disposition=Disposition.PUBLISHED)
        pages = project(ReleaseLedger((published,), ()), {
            "schema": "lmdj.release-changelog-publications.v1", "entries": [record]})
        self.assertIn(record["notes_sha256"], pages[1]["content"])

    def test_missing_date_is_not_replaced_with_local_clock(self):
        f = self.fixture
        f.github.release = replace(f.github.release, published_at=None)
        with self.assertRaisesRegex(PublicationError, "never invent"):
            self.collect()

    def test_body_drift_prevents_record(self):
        f = self.fixture
        f.github.release = replace(f.github.release, body=f.github.release.body + "\nDrift")
        with self.assertRaises(TransitionError):
            self.collect()

    def test_draft_prevents_record(self):
        f = self.fixture
        f.github.release = replace(f.github.release, draft=True)
        with self.assertRaisesRegex(TransitionError, "still a Draft"):
            self.collect()

    def test_publication_date_changes_during_verification_prevent_record(self):
        f = self.fixture
        f.github.mutate_on_release_read = f.github.release_reads + 2
        f.github.intervening_release_mutation = ("published_at", "2026-09-14T00:00:00Z")
        with self.assertRaises(TransitionError):
            self.collect()

    def test_redraft_during_verification_cannot_report_published(self):
        f = self.fixture
        f.github.mutate_on_release_read = f.github.release_reads + 2
        f.github.intervening_release_mutation = ("draft", True)
        with self.assertRaisesRegex(TransitionError, "changed during verification"):
            verify_published(f.tag, self.created.release_id, self.created.plan_sha256, f.context())

    def test_cli_emits_one_canonical_record_not_a_completion_claim(self):
        f = self.fixture
        output = io.StringIO()
        with patch.object(cli, "build_context", return_value=f.context()), redirect_stdout(output):
            code = cli.main(["--repo-root", str(f.root), "publication-record", f.tag,
                             str(self.created.release_id), self.created.plan_sha256])
        self.assertEqual(code, 0)
        record = json.loads(output.getvalue())
        self.assertEqual(output.getvalue().encode(), canonical_json(record))
        self.assertEqual(record, self.collect())
        self.assertNotIn("status", record)

    def test_production_get_parser_retains_actual_publication_date(self):
        f = self.fixture
        document = f._release_json(17)
        document.update(draft=False, published_at="2026-09-13T00:00:00Z")
        requests = []
        def transport(method, url, headers, body):
            requests.append((method, url))
            return HttpResponse(200, {}, json.dumps(document).encode())
        client = GitHubClient(http_transport=transport)
        self.assertEqual(client.get_release("endaye/lmdj", 17).published_at, document["published_at"])
        self.assertEqual(requests, [("GET", "/repos/endaye/lmdj/releases/17")])

    def test_production_get_parser_rejects_malformed_dates(self):
        f = self.fixture
        for value in (True, "", "2026-02-30T00:00:00Z", "2026-09-13T00:00:00+00:00"):
            with self.subTest(value=value):
                document = dict(f._release_json(17), published_at=value)
                client = GitHubClient(http_transport=lambda *args: HttpResponse(200, {}, json.dumps(document).encode()))
                with self.assertRaisesRegex(GitHubApiError, "timestamp"):
                    client.get_release("endaye/lmdj", 17)

    def test_legacy_release_without_frozen_notes_is_not_backfilled(self):
        import release_transitions_test as legacy_fixtures
        legacy = legacy_fixtures.ReleaseTransitionsTest()
        legacy.setUp()
        self.addCleanup(legacy.tearDown)
        created = legacy._published_fixture()
        legacy.github.release = replace(legacy.github.release, published_at="2026-09-13T00:00:00Z")
        with self.assertRaisesRegex(PublicationError, "no frozen changelog"):
            collect_publication(legacy.tag, created.release_id, created.plan_sha256, legacy.context())


if __name__ == "__main__":
    unittest.main()
