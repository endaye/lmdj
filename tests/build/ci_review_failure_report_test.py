"""Real review protocol and issue adapter, with strict read-only API fixtures."""
import base64
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]
import review_failure_report as consumer
import review_scope
import test_scope
from ci_self_test_report_test import FakeGitHubApi

A, B, C = (c * 40 for c in "abc")
POLICY = test_scope.load_policy(ROOT)


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHubApi()
        self.api._request = self.get
        self.api.compare = lambda base, head: {"status": "ahead", "merge_base_commit": {"sha": base}}
        self.identity = dict(repository="endaye/lmdj", pr_number=7, head_sha=A, base_sha=B,
                             control_sha=B, backend="deterministic", run_id=51, run_attempt=1)
        self.history = [review_scope.observe_attempt(POLICY, backend=backend, returncode=1, output="", error_class="service_error")
                        for backend in review_scope.BACKENDS]
        self.run = dict(id=51, run_attempt=1, workflow_id=42, path=consumer.WORKFLOW,
                        repository={"id": 5, "full_name": "endaye/lmdj"}, status="completed", conclusion="failure",
                        event="pull_request", head_sha=A, pull_requests=[])
        self.jobs = [dict(id=1, name="Review fallback", run_id=51, run_attempt=1, status="completed", conclusion="success",
            steps=[dict(name=name, conclusion="success") for name in (
                "Collect complete fixed input without executing PR files", "Save honest final result", "Run actions/upload-artifact@v4")])]
        self.api.list_jobs = lambda run_id, attempt: deepcopy(self.jobs)
        self.artifacts = [dict(id=9, name=f"pr-review-result-{A}-51-1", expired=False, workflow_run={"id": 51})]
        self.source = b"trusted workflow"
        self.reads = []
        self.save()

    def save(self):
        identity = dict(self.identity)
        reviewed = self.history[-1]["status"] == "reviewed"
        if reviewed:
            identity["backend"] = self.history[-1]["backend"]
        result = review_scope.prepare_result(POLICY, identity, changed_paths=["docs/notes/a.md"], history=self.history)
        self.documents = {"context.json": {"identity": self.identity, "changed_paths": ["docs/notes/a.md"]},
                          "history.json": self.history, "result.json": result}
        self.documents["review.json" if reviewed else "failure.json"] = self.history[-1]["review"] if reviewed else result["failure"]
        self.api.download_artifact = self.download

    def download(self, artifact):
        self.assertEqual(artifact, 9)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, value in self.documents.items():
                archive.writestr(name, json.dumps(value))
        return output.getvalue()

    def get(self, method, path):
        self.assertEqual(method, "GET")
        self.assertNotIn("/pulls", path)
        self.reads.append(path)
        if path == "/repos/endaye/lmdj":
            return {"id": 5, "full_name": "endaye/lmdj"}
        if path.endswith("/actions/workflows/pr-review.yml"):
            return {"id": 42, "path": consumer.WORKFLOW}
        if path.endswith("/attempts/1"):
            return self.run
        if path.endswith("/branches/main"):
            return {"commit": {"sha": C}}
        if "/artifacts?" in path:
            return {"total_count": len(self.artifacts), "artifacts": self.artifacts}
        if "/contents/" in path:
            name = path.split("/contents/", 1)[1].split("?", 1)[0]
            raw = self.source if name == consumer.WORKFLOW else (ROOT / name).read_bytes()
            return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
        self.fail("unexpected endpoint " + path)

    def collect(self):
        return consumer.collect(self.api, "endaye/lmdj", 51, 1)

    def rejected(self):
        with self.assertRaises((consumer.reporting.ReportingError, review_scope.ReviewScopeError, test_scope.ScopeError, ValueError)):
            self.collect()
        self.assertFalse(self.api.issues)

    def test_all_three_failure_from_overall_failed_run_has_honest_report(self):
        report = self.collect()
        self.assertEqual(report.key, "pr-review/backends-unavailable")
        self.assertIn(A, report.observation)
        self.assertIn("not a product self-test verdict", report.issue_body("endaye"))
        self.assertNotIn("from a self-test verdict", report.issue_body("endaye"))

    def test_real_apply_report_creates_then_deduplicates(self):
        first = consumer.report(self.api, "endaye/lmdj", 51, 1, sleep=lambda _: None)
        second = consumer.report(self.api, "endaye/lmdj", 51, 1, sleep=lambda _: None)
        self.assertEqual((first.action, second.action), ("created", "duplicate"))
        self.assertEqual(len(self.api.issues), 1)
        self.assertEqual(self.api.issues[0]["labels"], ["self-test", "type:bug", "area:ci-release"])

    def test_valid_review_with_findings_is_not_backend_failure(self):
        output = {"schema": review_scope.REVIEW_SCHEMA, "summary": "Finding", "findings": [{"path": "a.py", "line": 1, "body": "Bug"}],
                  "test_scope": {"labels": ["test:full"], "reason": "shared change"}}
        self.history = [review_scope.observe_attempt(POLICY, backend="glm", returncode=0, output=json.dumps(output))]
        self.save()
        self.assertIsNone(consumer.report(self.api, "endaye/lmdj", 51, 1, sleep=lambda _: None))
        self.assertFalse(self.api.issues)

    def test_closed_mapping_is_explicitly_not_applicable(self):
        self.jobs[0]["conclusion"] = "skipped"
        for name, step, conclusion in (("Resolve review target", "Resolve the Pull Request head", "skipped"),
                                      ("Publish review and scope", "Map merged PR without another AI call", "success")):
            self.jobs.append(dict(id=len(name), name=name, run_id=51, run_attempt=1, status="completed", conclusion="success",
                                  steps=[dict(name=step, conclusion=conclusion)]))
        self.assertIsNone(self.collect())
        self.assertFalse(any("/artifacts?" in path for path in self.reads))

    def test_arbitrary_skipped_producer_is_not_clean(self):
        self.jobs[0]["conclusion"] = "skipped"
        self.rejected()

    def test_failed_closed_mapper_is_not_backend_failure(self):
        self.test_closed_mapping_is_explicitly_not_applicable()
        self.jobs[-1]["conclusion"] = "failure"
        self.jobs[-1]["steps"][0]["conclusion"] = "failure"
        self.assertIsNone(self.collect())

    def test_untrusted_actual_workflow_source_is_rejected(self):
        original = self.get
        def changed(method, path):
            response = original(method, path)
            if path.endswith("pr-review.yml?ref=" + A):
                return {"encoding": "base64", "content": base64.b64encode(b"untrusted").decode()}
            return response
        self.api._request = changed
        self.rejected()

    def test_wrong_nonempty_pr_association_is_rejected(self):
        self.run["pull_requests"] = [{"number": 8, "head": {"sha": A}}]
        self.rejected()

    def test_duplicate_json_key_in_receipt_is_rejected(self):
        def duplicate(artifact):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for name, value in self.documents.items():
                    archive.writestr(name, '{"identity":{},"identity":{}}' if name == "context.json" else json.dumps(value))
            return output.getvalue()
        self.api.download_artifact = duplicate
        self.rejected()

    def test_wrong_workflow_is_rejected(self):
        self.run["workflow_id"] = 43
        self.rejected()

    def test_wrong_attempt_is_rejected(self):
        self.run["run_attempt"] = 2
        self.rejected()

    def test_wrong_head_is_rejected(self):
        self.run["head_sha"] = C
        self.rejected()

    def test_missing_artifact_is_error_not_three_backend_failure(self):
        self.artifacts = []
        self.rejected()

    def test_wrong_artifact_run_is_rejected(self):
        self.artifacts[0]["workflow_run"]["id"] = 52
        self.rejected()

    def test_expired_artifact_is_rejected(self):
        self.artifacts[0]["expired"] = True
        self.rejected()

    def test_failed_save_step_is_rejected(self):
        self.jobs[0]["steps"][1]["conclusion"] = "failure"
        self.rejected()

    def test_failed_upload_step_is_rejected(self):
        self.jobs[0]["steps"][2]["conclusion"] = "failure"
        self.rejected()

    def test_failure_json_alone_is_not_evidence(self):
        self.documents = {"failure.json": self.documents["failure.json"]}
        self.rejected()

    def test_forged_failure_json_does_not_override_history(self):
        self.documents["failure.json"] = deepcopy(self.documents["failure.json"])
        self.documents["failure.json"]["attempts"][0]["error_class"] = "timeout"
        self.rejected()

    def test_forged_result_does_not_override_history(self):
        self.documents["result.json"]["status"] = "reviewed"
        self.rejected()

    def test_incomplete_chain_is_not_three_failures(self):
        self.documents["history.json"] = self.history[:2]
        self.rejected()

    def test_untrusted_control_is_rejected(self):
        self.api.compare = lambda *args: {"status": "diverged", "merge_base_commit": {"sha": A}}
        self.rejected()

    def test_unknown_archive_member_is_rejected(self):
        self.documents["extra.json"] = {}
        self.rejected()


if __name__ == "__main__":
    unittest.main()
