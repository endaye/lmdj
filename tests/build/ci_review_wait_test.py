"""Current-head admission through real publisher/collector with read-only API fixtures."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]
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
        self.comments, self.reviews, self.inline = [], [], []
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
        self.inline = [{"id": 70 + i, "user": self.bot, "pull_request_review_id": 60, "original_commit_id": A,
                        "path": c["path"], "original_line": c["line"], "body": c["body"]}
                       for i, c in enumerate(payloads[0]["comments"])]

    def render_v2(self):
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
                  "findings": [], "test_scope": {"labels": ["test:full"], "reason": "Complete engine review retains the deterministic floor."}}
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
        self.inline = []

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
        inventories = {prefix + "/pulls/7/reviews": (self.reviews, None),
            prefix + "/issues/7/comments": (self.comments, None),
            prefix + "/pulls/7/reviews/60/comments": (self.inline, None),
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

    def test_authentic_v2_review_is_eligible_after_full_artifact_validation(self):
        self.render_v2()
        result = self.check()
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["evidence"][0]["backend"], "deepseek")

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
