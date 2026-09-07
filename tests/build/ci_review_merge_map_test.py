#!/usr/bin/env python3
"""Merged mapping contracts; mocked API is not a live publication rehearsal."""
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import review_merge_map as mapping
import review_scope
import test_scope


class MapTests(unittest.TestCase):
    def setUp(self):
        self.policy = test_scope.load_policy(ROOT)
        self.identity = dict(repository="endaye/lmdj", pr_number=7, head_sha="a" * 40,
                             base_sha="b" * 40, control_sha="c" * 40, backend="kimi", run_id=99, run_attempt=1)
        self.record = test_scope.build_record(self.policy, changed_paths=["docs/notes/a.md"], **self.identity)
        self.arguments = dict(repository="endaye/lmdj", repository_id=5, pr_number=7, head_sha="a" * 40,
                              merge_sha="d" * 40, control_sha="e" * 40, run_id=100, run_attempt=1, workflow_id=42,
                              changed_paths=["docs/notes/a.md"], scope_records=[{"record": self.record, "review_id": 11, "artifact_id": 12}],
                              complete=True, gaps=[])

    def test_complete_map_retains_exact_merge_head_and_scope_receipt(self):
        document = mapping.build_map(**self.arguments)
        self.assertEqual(mapping.validate_map(document), document)
        self.assertEqual(document["merge_sha"], "d" * 40)
        self.assertEqual(document["head_sha"], "a" * 40)
        self.assertEqual(document["scope_records"][0]["artifact_id"], 12)
        self.assertFalse(mapping.requires_full(document))

    def test_missing_scope_requires_full(self):
        document = mapping.build_map(**{**self.arguments, "scope_records": [], "complete": False, "gaps": ["no evidence"]})
        self.assertTrue(mapping.requires_full(document))

    def test_missing_scope_cannot_claim_complete(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "authenticated scope records"):
            mapping.build_map(**{**self.arguments, "scope_records": []})

    def test_partial_scope_cannot_claim_complete(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "without gaps"):
            mapping.build_map(**{**self.arguments, "gaps": ["publisher still running"]})

    def test_incomplete_map_must_explain_full(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "explain"):
            mapping.build_map(**{**self.arguments, "complete": False})

    def test_wrong_pr_scope_is_rejected(self):
        self.arguments["scope_records"][0]["record"]["head_sha"] = "f" * 40
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "another PR head"):
            mapping.build_map(**self.arguments)

    def test_forged_nested_scope_digest_is_rejected(self):
        self.record["record_digest"] = "f" * 64
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "nested scope"):
            mapping.build_map(**self.arguments)

    def test_unknown_map_field_is_rejected(self):
        document = mapping.build_map(**self.arguments)
        document["trusted"] = True
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "schema is not closed"):
            mapping.validate_map(document)

    def test_digest_cannot_silently_change_merge_target(self):
        document = mapping.build_map(**self.arguments)
        document["merge_sha"] = "f" * 40
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "disagree"):
            mapping.validate_map(document)


class HistoricalTests(unittest.TestCase):
    def setUp(self):
        MapTests.setUp(self)

    def authenticate(self, *, conclusion="success", artifact_record=None, expired=False, source_match=True, producer="success", run_patch=None):
        run = {"id": 99, "run_attempt": 1, "workflow_id": 42, "repository": {"id": 5, "full_name": "endaye/lmdj"},
               "status": "completed", "conclusion": conclusion, "event": "workflow_dispatch", "head_branch": "main", "head_sha": "c" * 40}
        run.update(run_patch or {})
        def api(path):
            self.assertEqual(path, "/repos/endaye/lmdj/actions/runs/99/attempts/1")
            return run
        def pages(path, key):
            if path.endswith("/jobs"):
                return [{"name": name, "run_id": 99, "run_attempt": 1, "status": "completed", "conclusion": producer}
                        for name in ("Review fallback", "Publish review and scope")]
            self.assertTrue(path.endswith("/artifacts"))
            return [{"id": 12, "name": "pr-test-scope-" + "a" * 40 + "-99-1", "expired": expired}]
        reads = []
        def git(*args):
            if args[0] == "merge-base":
                return ("c" * 40 + "\n").encode()
            reads.append(args)
            return b"source" if source_match or len(reads) == 1 else b"different"
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("scope.json", json.dumps(artifact_record if artifact_record is not None else self.record))
        with mock.patch.object(mapping.pipeline, "api", side_effect=api), \
                mock.patch.object(mapping.pipeline, "pages", side_effect=pages), \
                mock.patch.object(mapping.pipeline, "git", side_effect=git), mock.patch.object(mapping.pipeline, "fetch"), \
                mock.patch.object(mapping, "policy_at", return_value=self.policy):
            return mapping.authenticated_record(self.record, repository_id=5, workflow_id=42, download=lambda artifact_id: archive.getvalue())

    def test_historical_evidence_needs_no_open_pr(self):
        self.assertEqual(self.authenticate(), 12)

    def test_merged_pr_empty_association_retains_exact_head_evidence(self):
        self.assertEqual(self.authenticate(run_patch={"event": "pull_request", "head_sha": "a" * 40,
                                                      "pull_requests": []}), 12)

    def test_empty_association_does_not_authorize_wrong_run_head(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "reviewed head"):
            self.authenticate(run_patch={"event": "pull_request", "head_sha": "d" * 40, "pull_requests": []})

    def test_nonempty_association_must_still_match_pr(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "reviewed head"):
            self.authenticate(run_patch={"event": "pull_request", "head_sha": "a" * 40,
                "pull_requests": [{"number": 8, "head": {"sha": "a" * 40}}]})

    def test_matching_association_does_not_override_wrong_actual_head(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "reviewed head"):
            self.authenticate(run_patch={"event": "pull_request", "head_sha": "d" * 40,
                "pull_requests": [{"number": 7, "head": {"sha": "a" * 40}}]})

    def test_missing_association_is_not_an_empty_platform_array(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "reviewed head"):
            self.authenticate(run_patch={"event": "pull_request", "head_sha": "a" * 40})

    def test_empty_association_cannot_substitute_another_pr_artifact(self):
        other = test_scope.build_record(self.policy, changed_paths=["docs/notes/a.md"],
                                       **{**self.identity, "pr_number": 8})
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "actual publisher artifact"):
            self.authenticate(artifact_record=other, run_patch={"event": "pull_request", "head_sha": "a" * 40,
                                                              "pull_requests": []})

    def test_failed_run_cannot_authorize_scope(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "terminal successful"):
            self.authenticate(conclusion="failure")

    def test_failed_publisher_cannot_authorize_scope(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "producer or publisher"):
            self.authenticate(producer="failure")

    def test_expired_artifact_forces_conservative_fallback(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "missing or expired"):
            self.authenticate(expired=True)

    def test_matching_comment_digest_is_not_actual_artifact_proof(self):
        changed = copy.deepcopy(self.record)
        changed["ai_labels"] = ["test:full"]
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "actual publisher artifact"):
            self.authenticate(artifact_record=changed)

    def test_untrusted_historical_workflow_is_rejected(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "workflow source"):
            self.authenticate(source_match=False)


class WorkflowTests(unittest.TestCase):
    def test_closed_uses_independent_concurrency_without_ai(self):
        source = (ROOT / ".github/workflows/pr-review.yml").read_text()
        self.assertIn("github.event.action == 'closed' && '-merge-map'", source)
        target = source.split("  target:\n", 1)[1].split("  review:\n", 1)[0]
        self.assertIn("if: ${{ github.event.action != 'closed' }}", target)
        self.assertIn("if: ${{ needs.target.outputs.review == 'true' }}", source)
        publish = source.split("  publish:\n", 1)[1]
        self.assertIn("review_merge_map.py --output", publish)
        self.assertNotIn("anthropics/", publish)
        self.assertNotIn("issues: write", source)
        self.assertNotIn("actions: write", source)


class MetadataTests(unittest.TestCase):
    def setUp(self):
        MapTests.setUp(self)

    def test_compressed_publisher_record_is_used_without_another_codec(self):
        self.assertEqual(mapping.review_record(mapping.codec.encode(self.record)), self.record)

    def test_unavailable_marker_cannot_disappear_as_no_record(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "unavailable"):
            mapping.review_record(mapping.codec.unavailable(self.identity))

    def test_unavailable_marker_dominates_a_valid_none_record(self):
        body = mapping.codec.encode(self.record) + "\n" + mapping.codec.unavailable(self.identity)
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "unavailable"):
            mapping.review_record(body)

    def test_plain_model_text_is_not_scope_evidence(self):
        self.assertIsNone(mapping.review_record("All good, test:none"))


class ProducerTests(unittest.TestCase):
    def setUp(self):
        MapTests.setUp(self)

    def produce(self, *, body=None, runs=(), authenticate=True):
        def api(path):
            if path.endswith("/pulls/7"):
                return dict(number=7, state="closed", merged=True, base={"ref": "main", "repo": {"id": 5}},
                            head={"sha": "a" * 40}, merge_commit_sha="d" * 40)
            if path.endswith("/pr-review.yml"):
                return {"id": 42, "path": ".github/workflows/pr-review.yml"}
            if path.startswith("/users/"):
                return {"id": 10}
            self.assertEqual(path, "/repos/endaye/lmdj")
            return {"id": 5}
        def pages(path, key=None):
            if path.endswith("/reviews"):
                return [{"id": 11, "commit_id": "a" * 40, "user": {"id": 10}, "state": "COMMENTED",
                         "body": mapping.codec.encode(self.record) if body is None else body}]
            return list(runs) if "head_sha=" in path else []
        def git(*args):
            if args[0] == "rev-parse":
                return ("e" * 40).encode()
            if args[0] == "rev-list":
                return ("e" * 40 + "\n" + "d" * 40).encode()
            return ("b" * 40).encode()
        with mock.patch.object(mapping.pipeline, "api", side_effect=api), \
                mock.patch.object(mapping.pipeline, "pages", side_effect=pages), \
                mock.patch.object(mapping.pipeline, "git", side_effect=git), mock.patch.object(mapping.pipeline, "fetch"), \
                mock.patch.object(mapping.test_scope, "collect_interval", return_value={"paths": ["docs/notes/a.md"]}), \
                mock.patch.object(mapping, "authenticated_record", return_value=12,
                                  side_effect=None if authenticate else ValueError("missing artifact")), \
                mock.patch.dict(mapping.os.environ, GITHUB_TOKEN="test", GITHUB_RUN_ID="100", GITHUB_RUN_ATTEMPT="1"):
            return mapping.produce("endaye/lmdj", 7, "a" * 40, "d" * 40)

    def test_complete_receipts_allow_focused_map_after_merge(self):
        document = self.produce()
        self.assertTrue(document["complete"])
        self.assertEqual(document["scope_records"][0]["record"], self.record)

    def test_overflow_marker_forces_full_in_actual_producer(self):
        document = self.produce(body=mapping.codec.unavailable(self.identity))
        self.assertTrue(mapping.requires_full(document))
        self.assertEqual(document["scope_records"], [])

    def test_unverified_record_cannot_authorize_none(self):
        self.assertTrue(mapping.requires_full(self.produce(authenticate=False)))

    def test_inflight_run_prevents_incomplete_union_from_claiming_complete(self):
        document = self.produce(runs=[{"id": 102, "run_attempt": 1, "status": "in_progress"}])
        self.assertTrue(mapping.requires_full(document))

    def test_successful_unaccounted_run_prevents_none(self):
        document = self.produce(runs=[{"id": 102, "run_attempt": 1, "status": "completed", "conclusion": "success"}])
        self.assertTrue(mapping.requires_full(document))

    def test_unsupported_scope_marker_prevents_none(self):
        self.assertTrue(mapping.requires_full(self.produce(body="<!-- lmdj-test-scope-record-v99 opaque -->")))


if __name__ == "__main__":
    unittest.main()
