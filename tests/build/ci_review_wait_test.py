"""Current-head admission through real publisher/collector with read-only API fixtures."""
from copy import deepcopy
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import warnings
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]
sys.path.insert(0, str(ROOT))
from tools.release.model import canonical_sha256
from tools.release.review_inventory import bind_eligibility, ReviewInventoryError
import ci_review_failure_report_test as fixtures
import review_wait as wait
import review_scope

A, B = fixtures.A, fixtures.B
REPO = "endaye/lmdj"


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.source = fixtures.ConsumerTests()
        self.source.setUp()
        model = {"schema": review_scope.REVIEW_SCHEMA, "summary": "Reviewed the complete diff; no correctness findings.",
                 "findings": [], "test_scope": {"labels": ["test:none"], "reason": "Documentation-only change."}}
        self.source.history = [review_scope.observe_attempt(fixtures.POLICY, backend="glm", returncode=0, output=json.dumps(model))]
        self.source.run.update(conclusion="success", pull_requests=[{"number": 7, "head": {"sha": A}}])
        self.source.jobs.append(dict(id=2, name="Publish review and scope", run_id=51, run_attempt=1,
                                     status="completed", conclusion="success"))
        self.source.save()
        self.owner = {"id": 10, "login": "endaye", "type": "User"}
        self.repo = {"id": 5, "full_name": REPO, "owner": self.owner}
        self.pull = {"number": 7, "state": "open", "draft": False, "merged": False, "user": self.owner,
                     "head": {"sha": A, "repo": self.repo}, "base": {"ref": "main", "repo": self.repo}}
        self.bot = {"id": 20, "type": "Bot", "login": "github-actions[bot]"}
        self.check_runs = [{"id": 500, "name": wait.PORTAL_CHECK_RUN, "head_sha": A,
                            "status": "completed", "conclusion": "success"}]
        self.comments, self.reviews, self.inline, self.inline_details = [], [], [], {}
        self.detail_reads = []
        self.pull_reads = 0
        self.move = False
        self.fail_page = False
        self.render()

    def render(self):
        model = self.source.documents["review.json"]
        payloads = []
        wait.pipeline.pr_review_target.publish_review(REPO, 7, A, "51", "1", "glm",
            {"summary": model["summary"], "findings": model["findings"]}, api=lambda p: self.pull,
            write=lambda p, data: payloads.append(data))
        self.reviews = [{"id": 60, "user": self.bot, "state": "COMMENTED", "commit_id": A,
                         "submitted_at": "2026-09-10T01:00:00Z", "body": payloads[0]["body"] + "\n\nScope reason: Documentation-only change."}]
        self.render_comments(payloads[0]["comments"])

    def render_comments(self, comments):
        # GitHub's per-review list is a legacy projection: it does not return
        # original_line/side. Only the exact comment detail endpoint has those.
        # Observed on PR #1243, run 34633148497 attempt 2, comments 3992461160/69.
        self.inline = [{"id": 70 + i, "user": self.bot, "pull_request_review_id": 60,
                        "commit_id": A, "original_commit_id": A, "original_position": 200 + i,
                        "path": c["path"], "body": c["body"]}
                       for i, c in enumerate(comments)]
        self.inline_details = {item["id"]: {**deepcopy(item), "original_line": c["line"],
                                "line": c["line"], "side": c["side"], "original_start_line": None}
                               for item, c in zip(self.inline, comments)}

    def render_v2(self, findings=None):
        document = json.loads((ROOT / "tests/fixtures/ci/pr-agent/complete-input.json").read_text())
        document["identity"].update(pull_request=7, base_sha=B, head_sha=A, control_sha=B, run_id="51")
        unsigned = deepcopy(document)
        unsigned.pop("input_sha256")
        document["input_sha256"] = hashlib.sha256(
            json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        authenticated = wait.pipeline.t2.authenticate_input(document)
        collector = wait.pipeline.collector_witness(document)
        engine = {"name": "pr-agent", "source_commit": "1" * 40, "version": "0.45.0",
                  "bundle": {"archive_sha256": "2" * 64, "archive_byte_length": 7,
                             "manifest_sha256": "3" * 64, "adapter_sha256": "4" * 64,
                             "default_config_sha256": "5" * 64, "requirements_lock_sha256": "6" * 64,
                             "stock_tokenizer_asset_sha256": "7" * 64},
                  "runtime_config": {"sha256": "8" * 64, "byte_length": 7}}
        trusted = {"schema": review_scope.TRUSTED_CONFIG_SCHEMA, "provider_order": ["deepseek"],
                   "providers": {"deepseek": {"enabled": True, "model": "fixture-model"},
                                 "glm": {"enabled": False}, "xai": {"enabled": False}, "kimi": {"enabled": False}},
                   "engine": engine}
        coverage = wait.pipeline.t2._validate_coverage_receipt(wait.pipeline.t2._make_coverage(
            authenticated, provider="deepseek",
            model={"requested": "fixture-model", "actual": "fixture-served",
                   "response_version": "fixture-v1", "pricing_revision": "fixture-v1"},
            prompt=wait.pipeline.t2.render_prompt_input(authenticated), usage=None, engine=engine))
        review = {"schema": review_scope.REVIEW_SCHEMA, "summary": "Reviewed the complete v2 input.",
                  "findings": findings or [], "test_scope": {"labels": ["test:full"], "reason": "Complete engine review retains the deterministic floor."}}
        history = {"schema": review_scope.HISTORY_SCHEMA_V2, "attempts": [{
            "backend": "deepseek", "status": "reviewed", "error_class": None, "review": review,
            "engine": engine, "provider": "deepseek", "model": coverage["model"],
            "coverage_sha256": review_scope.coverage_digest(coverage),
        }]}
        changed_paths = sorted({hunk["path"] for hunk in collector["expected_hunks"]})
        wait.pipeline.review_scope.validate_history_v2(fixtures.POLICY, history, identity=self.source.identity,
            coverages={review_scope.coverage_digest(coverage): coverage}, changed_paths=changed_paths,
            collector=collector, trusted_config=trusted)
        publication = review_scope.prepare_result(fixtures.POLICY, {**self.source.identity, "backend": "deepseek"},
            changed_paths=changed_paths, history=history, coverages={review_scope.coverage_digest(coverage): coverage},
            collector=collector, trusted_config=trusted)
        self.source.history = history
        self.source.documents = {"context.json": {"identity": self.source.identity, "changed_paths": changed_paths},
                                 "history.json": history, "result.json": publication, "review.json": review,
                                 "collector.json": collector, "t2-config-witness.json": trusted,
                                 "coverage-" + review_scope.coverage_digest(coverage) + ".json": coverage}
        marker = wait.pipeline.codec.encode_history(history)
        payloads = []
        wait.pipeline.pr_review_target.publish_review(REPO, 7, A, "51", "1", "deepseek",
            publication["publication"]["review"], api=lambda p: self.pull, coverage=coverage,
            history_digest=review_scope.history_digest(history), history_marker=marker,
            write=lambda p, data: payloads.append(data))
        self.reviews = [{"id": 60, "user": self.bot, "state": "COMMENTED", "commit_id": A,
                         "submitted_at": "2026-09-10T01:00:00Z", "body": payloads[0]["body"] + "\n\nScope reason: Complete engine review retains the deterministic floor."}]
        self.render_comments(payloads[0]["comments"])

    def _request(self, method, path, *, raw=False):
        self.assertEqual(method, "GET", "helper must never mutate GitHub")
        route, query = urlsplit(path).path, parse_qs(urlsplit(path).query)
        prefix = "/repos/" + REPO
        if route == prefix:
            return deepcopy(self.repo)
        if route == prefix + "/pulls/7":
            self.pull_reads += 1
            value = deepcopy(self.pull)
            if self.move and self.pull_reads >= 2:
                value["head"]["sha"] = B
            return value
        if route == "/users/github-actions%5Bbot%5D":
            return self.bot
        if route == "/users/endaye":
            return self.owner
        if route == prefix + "/compare/" + B + "..." + fixtures.C:
            return {"status": "ahead", "merge_base_commit": {"sha": B}}
        if route.endswith("/actions/artifacts/9/zip"):
            self.assertTrue(raw)
            return self.source.download(9)
        if route.startswith(prefix + "/pulls/comments/"):
            self.assertFalse(query)
            comment_id = int(route.rsplit("/", 1)[1])
            self.detail_reads.append(comment_id)
            if comment_id not in self.inline_details:
                raise OSError("comment detail unavailable")
            return deepcopy(self.inline_details[comment_id])
        inventories = {prefix + "/pulls/7/reviews": (self.reviews, None),
            prefix + "/issues/7/comments": (self.comments, None),
            prefix + "/pulls/7/reviews/60/comments": (self.inline, None),
            prefix + "/commits/" + A + "/check-runs": (self.check_runs, "check_runs"),
            prefix + "/actions/runs/51/attempts/1/jobs": (self.source.jobs, "jobs"),
            prefix + "/actions/runs/51/artifacts": (self.source.artifacts, "artifacts"),
            prefix + "/actions/workflows/pr-review.yml/runs": ([self.source.run], "workflow_runs")}
        if route in inventories:
            page = int(query["page"][0])
            self.assertEqual(query["per_page"], ["100"])
            if self.fail_page and page == 2:
                raise OSError("API page unavailable")
            items, key = inventories[route]
            batch = deepcopy(items[(page-1)*100:page*100])
            return {key: batch, "total_count": len(items)} if key else batch
        return deepcopy(self.source.get(method, path))

    def check(self):
        return wait.check(wait.Reader(self, REPO), REPO, 7, A)

    def attest(self, kind="waiver"):
        record = {"schema": wait.ATTESTATION, "head_sha": A, "kind": kind, "reason": "Owner accepts missing automated review for this exact revision."}
        if kind == "takeover":
            record["review"] = {"reviewer_login": "endaye", "reviewer_id": 10, "author_session": "worker-T3",
                "reviewer_session": "coordinator-review", "independent": True, "scope": "All changed files and task tests.",
                "findings": [], "limitations": "No remote workflow execution."}
        self.comments = [{"id": 80, "user": self.owner, "body": json.dumps(record),
                          "created_at": "2026-09-10T02:00:00Z", "updated_at": "2026-09-10T02:00:00Z"}]
        self.reviews = []
        return record

    def update_record(self, record):
        self.comments[0]["body"] = json.dumps(record)

    def test_authentic_clean_review_is_eligible_not_merge_authority(self):
        result = self.check()
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["conversation_protection"], "not_evaluated")
        self.assertFalse(result["merge_authorized"])

    def body_inventory(self):
        # GraphQL-shaped decision input; collector pagination has its own real
        # client tests. Eligibility below still uses the actual artifact reader.
        inventory = {"schema": "lmdj.release-review-inventory.v1", "repository": REPO,
            "repository_id": self.repo["id"], "pr": {"number": 7, "headRefOid": A},
            "reviews": [], "comments": [], "reviewThreads": [], "closingIssuesReferences": []}
        for kind, rows in (("reviews", self.reviews), ("comments", self.comments)):
            inventory[kind] = [{"id": f"{kind}-{row['id']}", "databaseId": row["id"],
                "body": row["body"], "author": {"login": row["user"]["login"], "databaseId":row["user"]["id"]}} for row in rows]
        return {"inventory": inventory, "sha256": canonical_sha256(inventory)}

    def test_qualified_generated_body_binds_through_release_inventory(self):
        self.render_generated()
        eligibility, collected = self.check(), self.body_inventory()
        self.assertTrue(eligibility["eligible"], eligibility)
        binding = bind_eligibility(collected, eligibility)
        expected = self.reviews[0]["body"].encode("utf-8")
        observed = eligibility["evidence"][0]["body_observation"]
        self.assertEqual(observed["sha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(observed["byte_length"], len(expected))
        self.assertEqual(observed["author_id"], self.bot["id"])
        self.assertEqual(binding["linked"][0]["database_id"], 60)
        self.assertEqual(binding["linked"][0]["kind"], "reviews")

    def test_generated_bot_suffix_projection_binds_with_exact_numeric_identity(self):
        self.render_generated()
        eligibility = self.check()
        binding = bind_eligibility(self.bot_graphql_inventory(), eligibility)
        self.assertEqual(binding["linked"][0]["database_id"], 60)
        collected = self.bot_graphql_inventory()
        collected["inventory"]["reviews"][0]["author"]["databaseId"] += 1
        collected["sha256"] = canonical_sha256(collected["inventory"])
        with self.assertRaisesRegex(ReviewInventoryError, "body author differs"):
            bind_eligibility(collected, eligibility)

    def test_qualified_automated_body_binds_without_granting_merge_authority(self):
        self.render_v2()
        eligibility, collected = self.check(), self.body_inventory()
        binding = bind_eligibility(collected, eligibility)
        expected = self.reviews[0]["body"].encode("utf-8")
        observed = eligibility["evidence"][0]["body_observation"]
        self.assertEqual(observed["sha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(observed["byte_length"], len(expected))
        self.assertEqual(observed["author_id"], self.bot["id"])
        self.assertEqual(binding["linked"][0]["database_id"], 60)
        self.assertEqual(binding["eligibility_sha256"], canonical_sha256(eligibility))
        self.assertNotIn("eligible", binding)
        self.assertNotIn("merge_authorized", binding)

    def test_owner_record_body_binding_counts_utf8_bytes_not_characters(self):
        record = self.attest("takeover")
        record["reason"] = "独立审查完成；保留自动审查失败记录。"
        self.comments[0]["body"] = json.dumps(record, ensure_ascii=False)
        eligibility = self.check()
        binding = bind_eligibility(self.body_inventory(), eligibility)
        raw = self.comments[0]["body"].encode("utf-8")
        self.assertEqual(binding["linked"][0]["body_observation"]["byte_length"], len(raw))
        self.assertGreater(len(raw), len(self.comments[0]["body"]))

    def bot_graphql_inventory(self):
        collected = self.body_inventory()
        collected["inventory"]["reviews"][0]["author"]["login"] = self.bot["login"].removesuffix("[bot]")
        collected["sha256"] = canonical_sha256(collected["inventory"])
        return collected

    def test_authenticated_bot_rest_suffix_matches_graphql_login(self):
        eligibility = self.check()
        binding = bind_eligibility(self.bot_graphql_inventory(), eligibility)
        self.assertEqual(binding["linked"][0]["database_id"], 60)

    def test_bot_login_projection_still_requires_exact_numeric_identity(self):
        eligibility = self.check()
        collected = self.bot_graphql_inventory()
        collected["inventory"]["reviews"][0]["author"]["databaseId"] += 1
        collected["sha256"] = canonical_sha256(collected["inventory"])
        with self.assertRaisesRegex(ReviewInventoryError, "body author differs"):
            bind_eligibility(collected, eligibility)

    def test_owner_login_does_not_get_bot_suffix_normalization(self):
        self.attest()
        eligibility = self.check()
        collected = self.body_inventory()
        eligibility["evidence"][0]["body_observation"]["author_login"] += "[bot]"
        with self.assertRaisesRegex(ReviewInventoryError, "body author differs"):
            bind_eligibility(collected, eligibility)

    def test_same_review_id_edited_body_cannot_reuse_old_observation(self):
        eligibility = self.check()
        self.reviews[0]["body"] += "\nNew objection after the observation"
        with self.assertRaisesRegex(ReviewInventoryError, "body bytes differ"):
            bind_eligibility(self.body_inventory(), eligibility)

    def test_same_comment_id_edited_body_cannot_reuse_old_observation(self):
        self.attest()
        eligibility = self.check()
        self.comments[0]["body"] += " "
        with self.assertRaisesRegex(ReviewInventoryError, "body bytes differ"):
            bind_eligibility(self.body_inventory(), eligibility)

    def test_author_change_cannot_reuse_body_observation(self):
        eligibility = self.check()
        self.reviews[0]["user"] = {"id": 99, "login": "another-user"}
        with self.assertRaisesRegex(ReviewInventoryError, "body author differs"):
            bind_eligibility(self.body_inventory(), eligibility)

    def test_binding_preserves_unlinked_content_and_conversation_obligations(self):
        eligibility = self.check()
        self.reviews.append({"id": 91, "user": self.owner, "body": "Earlier unresolved review"})
        self.comments.append({"id": 92, "user": self.owner, "body": "Please verify migration"})
        collected = self.body_inventory()
        collected["inventory"]["reviewThreads"] = [{"id":"thread","isResolved":False}]
        collected["inventory"]["closingIssuesReferences"] = [{"number":9,"repository":{"nameWithOwner":REPO}}]
        collected["sha256"] = canonical_sha256(collected["inventory"])
        binding = bind_eligibility(collected, eligibility)
        self.assertEqual(binding["unlinked_reviews"], [91])
        self.assertEqual(binding["unlinked_comments"], [92])
        self.assertEqual((binding["thread_count"],binding["closing_count"]), (1,1))

    def test_reused_login_with_another_numeric_author_cannot_bind(self):
        eligibility = self.check()
        self.reviews[0]["user"] = {**self.bot, "id":99}
        with self.assertRaisesRegex(ReviewInventoryError, "body author differs"):
            bind_eligibility(self.body_inventory(), eligibility)

    def test_same_repository_name_with_another_numeric_identity_cannot_bind(self):
        eligibility = self.check()
        eligibility["repository_id"] += 1
        with self.assertRaisesRegex(ReviewInventoryError, "matching qualified observation"):
            bind_eligibility(self.body_inventory(), eligibility)

    def test_old_eligibility_without_body_observation_cannot_bind(self):
        eligibility = self.check()
        del eligibility["evidence"][0]["body_observation"]
        with self.assertRaisesRegex(ReviewInventoryError, "lacks a complete body observation"):
            bind_eligibility(self.body_inventory(), eligibility)

    def test_eligibility_for_another_head_cannot_bind(self):
        eligibility = self.check()
        eligibility["head_sha"] = B
        with self.assertRaisesRegex(ReviewInventoryError, "matching qualified observation"):
            bind_eligibility(self.body_inventory(), eligibility)

    def test_collector_body_changed_without_digest_cannot_bind(self):
        eligibility, collected = self.check(), self.body_inventory()
        collected["inventory"]["reviews"][0]["body"] += "new text"
        with self.assertRaisesRegex(ReviewInventoryError, "collector body digest differs"):
            bind_eligibility(collected, eligibility)

    def test_authentic_v2_review_is_eligible_after_full_artifact_validation(self):
        self.render_v2()
        result = self.check()
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["evidence"][0]["backend"], "deepseek")

    def current_workflow_archive(self):
        self.render_v2()
        # These are retained diagnostics, deliberately not canonical authority.
        self.source.documents.update({name: {"diagnostic": name, "status": "not-reviewed"}
            for name in ("t2-input.json", "collection-receipt.json", "t2-result.json")})
        source = (ROOT / ".github/workflows/pr-review.yml").read_text()
        upload = source.split("      - uses: actions/upload-artifact", 1)[1].split("      - name:", 1)[0]
        patterns = [line.strip().removeprefix("${{ env.REVIEW_DIR }}/")
                    for line in upload.splitlines() if line.strip().startswith("${{ env.REVIEW_DIR }}/")]
        selected = {}
        for pattern in patterns:
            matches = {name: data for name, data in self.source.documents.items() if fnmatch.fnmatchcase(name, pattern)}
            # failure.json and collection-failure.json exist only on failure
            # paths, and generated-only-receipt.json only on the generated-only
            # path; this archive models a reviewable producer output.
            self.assertTrue(matches or pattern in ("failure.json", "collection-failure.json",
                                                   "generated-only-receipt.json"),
                            "why: producer upload path has no source-shaped fixture: " + pattern
                            + "; remedy: model its actual file before claiming reader compatibility")
            selected.update(matches)
        self.source.documents = selected

    def test_current_producer_uploaded_v2_inventory_is_admitted_by_real_reader(self):
        self.current_workflow_archive()
        result = self.check()
        self.assertTrue(result["eligible"],
                        "why: actual producer member inventory is rejected by the reader; "
                        "remedy: reconcile only documented diagnostic members without weakening canonical receipts\n" + str(result))
        self.assertEqual(result["evidence"][0]["findings"], [])

    def test_diagnostic_members_remain_optional_for_historical_v2_receipts(self):
        names = ("t2-input.json", "collection-receipt.json", "t2-result.json")
        for mask in range(8):
            with self.subTest(mask=mask):
                self.render_v2()
                self.source.documents.update({name: {"status": "reviewed", "arbitrary": "not authority"}
                    for index, name in enumerate(names) if mask & (1 << index)})
                self.assertTrue(self.check()["eligible"])

    def test_v1_cannot_smuggle_v2_diagnostic_members(self):
        for name in ("t2-input.json", "collection-receipt.json", "t2-result.json"):
            with self.subTest(name=name):
                self.source.documents[name] = {}
                self.assertFalse(self.check()["eligible"])
                del self.source.documents[name]

    def test_current_v2_archive_still_rejects_unknown_or_nested_members(self):
        self.current_workflow_archive()
        for name in ("unknown.json", "nested/t2-input.json", "../t2-result.json"):
            with self.subTest(name=name):
                self.source.documents[name] = {}
                self.assertFalse(self.check()["eligible"])
                del self.source.documents[name]

    def test_diagnostics_never_replace_required_canonical_receipts(self):
        for name in ("context.json", "history.json", "result.json", "review.json", "collector.json", "t2-config-witness.json"):
            with self.subTest(name=name):
                self.current_workflow_archive()
                del self.source.documents[name]
                self.assertFalse(self.check()["eligible"])

    def test_diagnostics_never_override_tampered_canonical_results(self):
        self.current_workflow_archive()
        self.source.documents["t2-result.json"] = {"status": "reviewed", "findings": []}
        self.source.documents["review.json"]["summary"] = "forged summary"
        self.assertFalse(self.check()["eligible"])

    def test_v2_diagnostics_keep_duplicate_members_and_json_errors_rejected(self):
        self.current_workflow_archive()
        original = self.source.download
        for kind in ("duplicate-member", "duplicate-key", "invalid-json"):
            with self.subTest(kind=kind):
                def download(artifact):
                    raw = original(artifact)
                    output = wait.io.BytesIO()
                    with wait.zipfile.ZipFile(wait.io.BytesIO(raw)) as source, wait.zipfile.ZipFile(output, "w") as target:
                        for name in source.namelist():
                            data = source.read(name)
                            if name == "t2-result.json" and kind != "duplicate-member":
                                data = b'{"same":1,"same":2}' if kind == "duplicate-key" else b'{'
                            target.writestr(name, data)
                        if kind == "duplicate-member":
                            with warnings.catch_warnings():
                                warnings.filterwarnings("ignore", message="Duplicate name:")
                                target.writestr("t2-result.json", b'{}')
                    return output.getvalue()
                self.source.download = download
                self.assertFalse(self.check()["eligible"])
        self.source.download = original

    def render_generated(self):
        """A control-plane generated-only receipt: producer with the finalizer
        gated off, an archive holding exactly the receipt, and the marker
        COMMENT the trusted publisher posts for it."""
        identity = {"repository": REPO, "pull_request": 7, "base_sha": B, "head_sha": A,
                    "control_sha": B, "run_id": "51", "run_attempt": 1}
        receipt = {"schema": wait.pipeline.input_producer.GENERATED_ONLY_RECEIPT_SCHEMA,
                   "status": "generated-only", "identity": identity, "head_sha": A,
                   "excluded_generated": {
                       "count": 1,
                       "paths": ["apps/architecture-portal/versioned_provenance/version-1.0.57.0.json"],
                       "entries": [{"path": "apps/architecture-portal/versioned_provenance/version-1.0.57.0.json",
                                    "object_id": "1" * 40, "sha256": "2" * 64}]}}
        receipt["receipt_sha256"] = hashlib.sha256(
            wait.pipeline.input_producer.json_bytes(receipt)).hexdigest()
        self.source.documents = {"generated-only-receipt.json": receipt}
        next(step for step in self.source.jobs[0]["steps"]
             if step["name"] == "Save honest final result")["conclusion"] = "skipped"
        # The publisher hashes the exact retained bytes; the fixture archive
        # serializes with json.dumps, so the marker digest binds those bytes.
        digest = hashlib.sha256(json.dumps(receipt).encode()).hexdigest()
        body = wait.pipeline.pr_review_target.generated_body(REPO, 7, A, "51", "1", digest)
        self.reviews = [{"id": 60, "user": self.bot, "state": "COMMENTED", "commit_id": A,
                         "submitted_at": "2026-09-10T01:00:00Z", "body": body}]
        return body, digest

    def test_authentic_generated_receipt_with_green_portal_lane_is_eligible(self):
        _body, digest = self.render_generated()
        result = self.check()
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["evidence"][0]["kind"], "generated")
        self.assertEqual(result["evidence"][0]["receipt_sha256"], digest)
        self.assertFalse(result["merge_authorized"])

    def test_generated_marker_on_a_wrong_head_is_not_current_head_evidence(self):
        self.render_generated()
        self.reviews[0]["commit_id"] = B
        result = self.check()
        self.assertFalse(result["eligible"], result)
        self.assertEqual(result["status"], "pending")

    def test_generated_foreign_malformed_and_duplicate_markers_are_invalid(self):
        body, _digest = self.render_generated()
        marker = body.splitlines()[0]
        for name, mutate in (
            ("foreign", lambda b: b.replace("endaye/lmdj", "other/repo", 1)),
            ("malformed", lambda b: b.replace("sha256=", "sha256=not-a-digest", 1)),
            ("duplicate", lambda b: b + "\n" + marker),
        ):
            with self.subTest(name=name):
                self.reviews[0]["body"] = mutate(body)
                result = self.check()
                self.assertFalse(result["eligible"], result)
                self.assertEqual(result["status"], "invalid")
                self.reviews[0]["body"] = body

    def test_generated_marker_mixed_with_the_model_marker_family_is_invalid(self):
        body, _digest = self.render_generated()
        self.reviews[0]["body"] = body + ("\n<!-- lmdj-review-v2 endaye/lmdj 7 " + A +
                                          " 51 1 deepseek sha256=" + "0" * 64 + " -->")
        result = self.check()
        self.assertFalse(result["eligible"], result)
        self.assertEqual(result["status"], "invalid")

    def test_model_review_quoting_the_generated_marker_in_prose_is_admitted(self):
        # #1381: the authentic deepseek review described the new marker family
        # in prose; routing must key on anchored markers, never substrings.
        self.render_v2()
        self.reviews[0]["body"] += ("\n\nThis change introduces the "
                                    "lmdj-review-generated-v1 receipt marker for Portal witness PRs.")
        result = self.check()
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["evidence"][0]["kind"], "automated")
        self.assertEqual(result["evidence"][0]["backend"], "deepseek")

    def test_generated_receipt_quoting_a_model_marker_in_prose_is_admitted(self):
        body, digest = self.render_generated()
        self.reviews[0]["body"] = body + "\n\nSupersedes the lmdj-review-v2 model path for this shape."
        result = self.check()
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["evidence"][0]["kind"], "generated")
        self.assertEqual(result["evidence"][0]["receipt_sha256"], digest)

    def test_substring_mention_without_an_anchored_marker_is_invalid_evidence(self):
        self.render_v2()
        self.reviews[0] = {"id": 61, "user": self.bot, "state": "COMMENTED", "commit_id": A,
                           "submitted_at": "2026-09-10T03:00:00Z",
                           "body": "Notes on lmdj-review-generated-v1 and lmdj-review-v2 marker formats."}
        result = self.check()
        self.assertFalse(result["eligible"], result)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["diagnostics"][0]["review_id"], 61)
        self.assertIn("ambiguous publisher identity", result["diagnostics"][0]["why"])

    def test_generated_non_bot_author_is_invalid(self):
        self.render_generated()
        self.reviews[0]["user"] = {"id": 999, "login": "github-actions[bot]"}
        result = self.check()
        self.assertFalse(result["eligible"], result)
        self.assertEqual(result["status"], "invalid")

    def test_generated_edited_body_is_caught_by_byte_binding_not_admission(self):
        # Appended prose does not touch the anchored marker, so check() admits
        # the review (same prefix posture as automated()); the byte-exact
        # body_observation binding is what rejects a later edit at shipping time.
        body, _digest = self.render_generated()
        eligibility = self.check()
        self.assertTrue(eligibility["eligible"], eligibility)
        self.reviews[0]["body"] = body + "\nEdited after publication."
        with self.assertRaisesRegex(ReviewInventoryError, "body bytes differ"):
            bind_eligibility(self.body_inventory(), eligibility)

    def test_generated_receipt_digest_mismatch_is_invalid(self):
        body, digest = self.render_generated()
        self.reviews[0]["body"] = body.replace("sha256=" + digest, "sha256=" + "0" * 64)
        result = self.check()
        self.assertFalse(result["eligible"], result)
        self.assertEqual(result["status"], "invalid")

    def test_generated_receipt_with_unclosed_entries_is_invalid(self):
        for failure in ("duplicate", "tampered", "missing", "extra-field", "null-mismatch"):
            with self.subTest(failure=failure):
                self.render_generated()
                document = self.source.documents["generated-only-receipt.json"]
                entries = document["excluded_generated"]["entries"]
                if failure == "duplicate":
                    entries.append(deepcopy(entries[0]))
                elif failure == "tampered":
                    entries[0]["sha256"] = "not-a-digest"
                elif failure == "missing":
                    entries.clear()
                elif failure == "extra-field":
                    entries[0]["note"] = "x"
                else:
                    entries[0]["sha256"] = None
                # Keep every other authentication layer intact so only the
                # entries closure can refuse: reseal the self-describing
                # digest and republish the marker over the new retained bytes.
                document.pop("receipt_sha256")
                document["receipt_sha256"] = hashlib.sha256(
                    wait.pipeline.input_producer.json_bytes(document)).hexdigest()
                digest = hashlib.sha256(json.dumps(document).encode()).hexdigest()
                self.reviews[0]["body"] = wait.pipeline.pr_review_target.generated_body(
                    REPO, 7, A, "51", "1", digest)
                result = self.check()
                self.assertFalse(result["eligible"], result)
                self.assertEqual(result["status"], "invalid")

    def test_generated_receipt_without_portal_lane_stays_pending(self):
        self.render_generated()
        self.check_runs = []
        result = self.check()
        self.assertFalse(result["eligible"], result)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["diagnostics"][0]["status"], "portal_gate_pending")

    def test_generated_receipt_with_failed_portal_lane_stays_pending(self):
        self.render_generated()
        self.check_runs[0]["conclusion"] = "failure"
        result = self.check()
        self.assertFalse(result["eligible"], result)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["diagnostics"][0]["status"], "portal_gate_pending")

    def test_v2_foreign_malformed_and_duplicate_markers_are_invalid(self):
        self.render_v2()
        for name, mutate in (
            ("foreign", lambda body: body.replace("endaye/lmdj", "other/repo", 1)),
            ("malformed", lambda body: body.replace("sha256=", "sha256=not-a-digest", 1)),
            ("duplicate", lambda body: body + "\n" + body.splitlines()[1]),
        ):
            with self.subTest(name=name):
                original = self.reviews[0]["body"]
                self.reviews[0]["body"] = mutate(original)
                result = self.check()
                self.assertFalse(result["eligible"], result)
                self.assertEqual(result["status"], "invalid")
                self.reviews[0]["body"] = original

    def test_v2_wrong_head_is_not_current_head_evidence(self):
        self.render_v2()
        self.reviews[0]["commit_id"] = B
        result = self.check()
        self.assertFalse(result["eligible"], result)
        self.assertEqual(result["status"], "pending")

    def test_authentic_findings_are_retained_for_disposition(self):
        review = self.source.history[0]["review"]
        review["findings"] = [{"path": "docs/notes/a.md", "line": 1, "body": "Incorrect documented command."}]
        self.source.save()
        self.render()
        result = self.check()
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["evidence"][0]["findings"], review["findings"])

    def test_legacy_list_v2_findings_use_exact_comment_details(self):
        findings = [{"path": "src/example.py", "line": 2, "body": "Check the changed return value."},
                    {"path": "src/example.py", "line": 3, "body": "Check the changed comment."}]
        self.render_v2(findings)
        self.assertTrue(all("original_line" not in item and "side" not in item for item in self.inline))
        result = self.check()
        self.assertTrue(result["eligible"], result)
        self.assertEqual(self.detail_reads, [70, 71])
        self.assertEqual(result["evidence"][0]["findings"], findings)

    def one_v2_finding(self):
        self.render_v2([{"path": "src/example.py", "line": 2, "body": "Check the changed return value."}])

    def test_comment_detail_must_match_the_exact_review_inventory(self):
        for key, value in (("id", 999), ("pull_request_review_id", 999),
                           ("user", {"id": 999}), ("original_commit_id", B),
                           ("path", "other.py"), ("body", "edited body")):
            with self.subTest(key=key):
                self.one_v2_finding()
                self.inline_details[70][key] = value
                result = self.check()
                self.assertFalse(result["eligible"], result)
                self.assertIn("detail differs", result["diagnostics"][0]["why"])

    def test_matching_list_and_detail_cannot_forge_model_or_author_identity(self):
        for key, value in (("pull_request_review_id", 999), ("user", {"id": 999}),
                           ("original_commit_id", B), ("path", "other.py"), ("body", "edited body")):
            with self.subTest(key=key):
                self.one_v2_finding()
                self.inline[0][key] = value
                self.inline_details[70][key] = value
                self.assertFalse(self.check()["eligible"])

    def test_detail_must_supply_exact_original_single_right_side_line(self):
        for key, value in (("original_line", None), ("original_line", 3), ("original_line", True),
                           ("side", "LEFT"), ("side", None), ("original_start_line", 1)):
            with self.subTest(key=key, value=value):
                self.one_v2_finding()
                self.inline_details[70][key] = value
                self.assertFalse(self.check()["eligible"])

    def test_comment_detail_unavailable_never_uses_legacy_position_as_line(self):
        self.one_v2_finding()
        self.inline[0]["original_position"] = 2
        self.inline_details.clear()
        result = self.check()
        self.assertFalse(result["eligible"], result)
        self.assertEqual(self.detail_reads, [70])

    def test_comment_detail_non_object_is_invalid(self):
        self.one_v2_finding()
        self.inline_details[70] = []
        self.assertFalse(self.check()["eligible"])

    def test_duplicate_comment_inventory_is_rejected_before_hydration(self):
        self.render_v2([{"path": "src/example.py", "line": line, "body": "Check this change."}
                        for line in (2, 3)])
        self.inline[1] = deepcopy(self.inline[0])
        self.assertFalse(self.check()["eligible"])
        self.assertEqual(self.detail_reads, [])

    def test_missing_comment_inventory_id_is_rejected_before_hydration(self):
        self.one_v2_finding()
        self.inline[0]["id"] = "70"
        self.assertFalse(self.check()["eligible"])
        self.assertEqual(self.detail_reads, [])

    def test_missing_published_finding_is_invalid(self):
        self.test_authentic_findings_are_retained_for_disposition()
        self.inline = []
        self.assertFalse(self.check()["eligible"])

    def test_failed_run_is_not_review(self):
        self.source.run["conclusion"] = "failure"
        self.assertFalse(self.check()["eligible"])

    def test_failed_publisher_is_not_review(self):
        self.source.jobs[1]["conclusion"] = "failure"
        self.assertFalse(self.check()["eligible"])

    def test_unpublished_result_is_pending(self):
        self.reviews = []
        self.assertEqual(self.check()["status"], "pending")

    def test_invalid_artifact_is_not_review(self):
        self.source.documents["review.json"]["summary"] = "altered"
        self.assertFalse(self.check()["eligible"])

    def test_wrong_run_attempt_is_invalid(self):
        self.source.run["run_attempt"] = 2
        self.assertFalse(self.check()["eligible"])

    def test_wrong_workflow_source_is_invalid(self):
        original = self.source.get
        def get(method, path):
            value = original(method, path)
            if "/contents/.github/workflows/pr-review.yml?ref=" + A in path:
                value["content"] = "Zm9yZ2Vk"
            return value
        self.source.get = get
        self.assertFalse(self.check()["eligible"])

    def test_spoofed_bot_login_is_not_identity(self):
        self.reviews[0]["user"] = {"id": 999, "login": "github-actions[bot]"}
        self.assertFalse(self.check()["eligible"])

    def test_head_changes_during_collection(self):
        self.move = True
        self.assertEqual(self.check()["status"], "stale")

    def test_initial_head_is_stale(self):
        self.pull["head"]["sha"] = B
        self.assertEqual(self.check()["status"], "stale")

    def test_closed_pr_is_not_eligible(self):
        self.pull["state"] = "closed"
        self.assertFalse(self.check()["eligible"])

    def test_owner_waiver_retains_failed_run(self):
        self.attest()
        self.source.run["conclusion"] = "failure"
        result = self.check()
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["runs"][0]["conclusion"], "failure")

    def test_nonowner_cannot_waive(self):
        self.attest()
        self.comments[0]["user"] = {"id": 11, "login": "endaye"}
        self.assertFalse(self.check()["eligible"])

    def test_label_alone_is_pending(self):
        self.reviews = []
        self.pull["labels"] = [{"name": "review:skipped"}]
        self.assertEqual(self.check()["status"], "pending")

    def test_waiver_needs_reason(self):
        record = self.attest()
        record["reason"] = " "
        self.update_record(record)
        self.assertFalse(self.check()["eligible"])

    def test_stale_waiver_does_not_apply(self):
        record = self.attest()
        record["head_sha"] = B
        self.update_record(record)
        self.assertFalse(self.check()["eligible"])

    def test_shared_owner_login_independent_agent_takeover(self):
        self.attest("takeover")
        self.assertTrue(self.check()["eligible"])

    def test_author_cannot_attest_self_as_independent_agent(self):
        record = self.attest("takeover")
        record["review"]["reviewer_session"] = record["review"]["author_session"]
        self.update_record(record)
        self.assertFalse(self.check()["eligible"])

    def test_takeover_reviewer_numeric_identity_is_verified(self):
        record = self.attest("takeover")
        record["review"]["reviewer_id"] = 99
        self.update_record(record)
        self.assertFalse(self.check()["eligible"])

    def test_takeover_findings_need_disposition(self):
        record = self.attest("takeover")
        record["review"]["findings"] = [{"finding": "command incorrect", "disposition": ""}]
        self.update_record(record)
        self.assertFalse(self.check()["eligible"])

    def test_legacy_markdown_requires_explicit_adoption(self):
        self.attest("takeover")
        self.comments[0]["body"] = "Independent agent reviewed " + A + "; no findings."
        self.assertEqual(self.check()["status"], "pending")

    def test_edited_attestation_is_invalid(self):
        self.attest()
        self.comments[0]["updated_at"] = "2026-09-11T00:00:00Z"
        self.assertFalse(self.check()["eligible"])

    def test_complete_second_page_owner_comment(self):
        self.attest()
        self.comments = [{"id": 100+i, "body": "discussion"} for i in range(100)] + self.comments
        self.assertTrue(self.check()["eligible"])

    def test_second_page_failure_never_approves(self):
        self.test_complete_second_page_owner_comment()
        self.fail_page = True
        self.assertEqual(self.check()["status"], "unavailable")

    def test_complete_artifact_pagination(self):
        self.source.artifacts = [{"id": 100+i, "name": "unrelated"} for i in range(100)] + self.source.artifacts
        self.assertTrue(self.check()["eligible"])

    def test_duplicate_inventory_is_unavailable(self):
        self.reviews *= 2
        self.assertEqual(self.check()["status"], "invalid")

    def test_all_backends_failed_is_never_clean(self):
        self.source.history = [review_scope.observe_attempt(fixtures.POLICY, backend=b, returncode=1,
            output="", error_class="service_error") for b in review_scope.BACKENDS]
        self.source.save()
        self.source.run["conclusion"] = "failure"
        result = self.check()
        self.assertFalse(result["eligible"])
        self.assertEqual(result["runs"][0]["conclusion"], "failure")

    def test_pending_comment_is_not_submitted_review(self):
        self.reviews[0]["state"] = "PENDING"
        self.assertFalse(self.check()["eligible"])

    def test_artifact_expiry_needs_takeover(self):
        self.source.artifacts[0]["expired"] = True
        self.assertFalse(self.check()["eligible"])

    def test_api_failure_never_approves(self):
        original = self._request
        def request(method, path, **kwargs):
            if "/issues/7/comments" in path:
                raise OSError("API failed")
            return original(method, path, **kwargs)
        self._request = request
        self.assertEqual(self.check()["status"], "unavailable")

    def test_new_main_base_does_not_require_update(self):
        original = self._request
        def request(method, path, **kwargs):
            value = original(method, path, **kwargs)
            if path == "/repos/" + REPO + "/pulls/7":
                value["base"]["sha"] = A if self.pull_reads == 1 else B
            return value
        self._request = request
        self.assertTrue(self.check()["eligible"])

    def test_final_pr_closure_invalidates_review(self):
        self.attest()
        original = self._request
        def request(method, path, **kwargs):
            value = original(method, path, **kwargs)
            if path == "/repos/" + REPO + "/pulls/7" and self.pull_reads > 1:
                value["state"] = "closed"
            return value
        self._request = request
        self.assertFalse(self.check()["eligible"])

    def test_cli_without_credentials_is_structured_nonzero(self):
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        process = subprocess.run([sys.executable, str(ROOT / "scripts/ci/review_wait.py"), "--repository", REPO,
            "--pr-number", "7", "--expect-head", A], env=env, capture_output=True, text=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stdout)["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
