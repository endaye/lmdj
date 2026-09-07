#!/usr/bin/env python3
"""Real Git/reducer/prepare/needs/validator with closed read-only HTTP fixtures.

No GitHub calls, models or releases. Fixtures do not prove actual API access,
artifact retention, hosted locks or execution; real O1 remains outstanding.
"""
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release import batch_evidence as consumer
import batch_execution
import batch_evidence_validation as shared
import incremental_batch as batch
import self_test
import test_scope


def zipped(documents):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in documents.items():
            archive.writestr(name, json.dumps(value))
    return output.getvalue()


class BatchReleaseEvidenceTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Evidence fixture")
        self.git("config", "user.email", "ci@example.invalid")
        for path in [*("scripts/ci/" + n for n in consumer.POLICY_FILES), *shared.EXECUTION_SOURCES]:
            destination = self.root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / path).read_bytes())
        self.git("add", ".")
        self.git("commit", "-qm", "trusted producer fixture")
        self.control = self.git("rev-parse", "HEAD")
        self.policy = test_scope.load_policy(self.root)
        self.request = batch.make_request(self.policy, request_id="candidate-fixture", kind="candidate", base_sha=None,
            target_sha=self.control, control_sha=self.control, selection=test_scope._selection(self.policy, self.policy.suite_ids, ["explicit full request"]),
            origin_run={"run_id": 101, "attempt": 1})
        state = batch.new_state("fixture")
        def transition(kind, data):
            nonlocal state
            state = batch.reduce(state, {"id": str(state["generation"]), "epoch": "fixture", "generation": state["generation"], "type": kind, "data": data}, self.policy)
        transition("observe", {"target": self.control, "descends_pending": True})
        transition("enqueue", self.request)
        self.origin_snapshot = self.snapshot("waiting", None, 101, state)
        # A real newer main commit with identical workflows exercises queued
        # request.control != actual executor control, not a synthetic SHA stub.
        (self.root / "README.md").write_text("fixture main advancement\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "advance main without control drift")
        self.executor_control = self.git("rev-parse", "HEAD")
        transition("admit", {"request": self.request, "executor_run": {"run_id": 102, "attempt": 1},
            "history_complete": True, "ancestor": True, "old_runs_terminal": True})
        transition("claim", {"request_id": self.request["id"], "run": {"run_id": 102, "attempt": 1}})
        self.admission = self.snapshot("execute", self.request, 102, state)
        self.git("checkout", "--detach", "-q", self.control)
        execution = batch_execution.prepare(self.policy, self.request, {"run_id": 102, "attempt": 1}, repo=self.root,
            run_id=102, run_attempt=1, control_sha=self.control, main_sha=self.executor_control)
        self.needs = {shared.ALIASES.get(job, job): {"result": "success", "outputs": {}} for job in self.policy.inventory.job_owner}
        self.needs["macos-fallback"] = {"result": "skipped", "outputs": {}}
        self.verdict = batch_execution.from_needs(self.policy, execution["identity"], execution["selection"], self.needs,
            aliases=shared.ALIASES, dependencies=shared.dependencies(self.policy))
        self.bundle = {"execution.json": execution, "needs.json": self.needs, "verdict.json": self.verdict}
        self.routes, self.calls, self.downloads = {}, [], {}
        self.prefix = "/repos/endaye/lmdj"
        self.route("/branches/main", {"name": "main", "protected": True, "commit": {"sha": self.executor_control}})
        self.route("/actions/workflows/self-test-report.yml", {"id": 7, "path": consumer.WORKFLOW})
        self.origin_run = self.add_run(101, self.control)
        self.executor_run = self.add_run(102, self.executor_control)
        self.jobs = [self.job(102, self.executor_control, consumer.CONTROLLER)]
        producer = self.job(102, self.executor_control, shared.PRODUCER_JOB)
        producer["steps"] = [{"name": name, "status": "completed", "conclusion": status} for name, status in (
            ("Judge selected suites from actual needs", "success"), ("Retain scoped verdict and raw needs", "success"),
            ("Keep failed selected work visible", "skipped"))]
        self.jobs.append(producer)
        for observation in self.verdict["observations"]:
            self.jobs.append(self.job(102, self.executor_control, shared.PREFIX + shared.JOB_NAMES[observation["job"]], observation["conclusion"]))
        self.route("/actions/runs/102/attempts/1/jobs?per_page=100&page=1", {"total_count": len(self.jobs), "jobs": self.jobs})
        self.artifacts = {101: [], 102: []}
        self.add_artifact(101, 1, "batch-controller-101-1", {"result.json": self.origin_snapshot})
        self.add_artifact(102, 2, "batch-controller-102-1", {"result.json": self.admission})
        self.add_artifact(102, 3, f"batch-verdict-{self.control}-102-1", self.bundle)
        self.ref = {"schema": consumer.SCHEMA, "request": self.request, "executor_control_revision": self.executor_control,
            "run_attempt": 1, "origin_record_digest": self_test.digest_of(self.origin_snapshot),
            "admission_record_digest": self_test.digest_of(self.admission), "evidence_digest": self.verdict["evidence_digest"]}
        self.reader = consumer.BatchEvidenceConsumer(api_get=self.get, git_root=self.root, repository="endaye/lmdj",
            repository_id=11, workflow_id=7, producer_revision=self.control, now=datetime(2026, 9, 8, tzinfo=timezone.utc))

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, check=True).stdout.strip()

    def snapshot(self, action, request, run, state):
        return {"schema": "lmdj.ci-batch-runtime.v1", "action": action, "reason": "fixture", "request": deepcopy(request),
                "executor": {"run_id": run, "attempt": 1}, "state": deepcopy(state)}

    def job(self, run, control, name, conclusion="success"):
        identifier = getattr(self, "job_id", 1000) + 1
        self.job_id = identifier
        return {"id": identifier, "run_id": run, "run_attempt": 1, "head_sha": control, "name": name,
                "status": "completed", "conclusion": conclusion, "started_at": "2026-09-08T00:00:00Z"}

    def route(self, suffix, value):
        self.routes[self.prefix + suffix] = value

    def add_run(self, identifier, control):
        repo = {"id": 11, "full_name": "endaye/lmdj"}
        run = {"id": identifier, "run_attempt": 1, "workflow_id": 7, "head_sha": control, "head_branch": "main",
            "path": consumer.WORKFLOW, "status": "completed", "conclusion": "success", "event": "workflow_dispatch",
            "repository": repo, "head_repository": deepcopy(repo)}
        self.route(f"/actions/runs/{identifier}", run)
        self.route(f"/actions/runs/{identifier}/attempts/1", run)
        self.route(f"/actions/runs/{identifier}/attempts/1/jobs?per_page=100&page=1", {"total_count": 1, "jobs": [self.job(identifier, control, consumer.CONTROLLER)]})
        return run

    def add_artifact(self, run, identifier, name, documents):
        raw = zipped(documents)
        self.downloads[identifier] = raw
        self.artifacts[run].append({"id": identifier, "name": name, "expired": False, "expires_at": "2026-10-08T00:00:00Z", "size_in_bytes": len(raw),
            "workflow_run": {"id": run, "repository_id": 11, "head_repository_id": 11, "head_sha": self.control if run == 101 else self.executor_control, "head_branch": "main"}})
        self.route(f"/actions/runs/{run}/artifacts?per_page=100&page=1", {"total_count": len(self.artifacts[run]), "artifacts": self.artifacts[run]})

    def get(self, path, *, raw=False):
        self.calls.append((path, raw))
        if path.startswith(self.prefix + "/actions/artifacts/") and path.endswith("/zip"):
            self.assertTrue(raw)
            return self.downloads[int(path.split("/artifacts/")[1].split("/")[0])]
        self.assertFalse(raw)
        if path not in self.routes:
            raise AssertionError("unexpected read-only endpoint: " + path)
        return deepcopy(self.routes[path])

    def verify(self):
        return self.reader.verify(self.ref, run_id=102, target_revision=self.control)

    def rejected(self, phrase=None, code="conflict"):
        with self.assertRaises(consumer.BatchEvidenceError) as caught:
            self.verify()
        self.assertEqual(caught.exception.code, code)
        self.assertIn("why:", str(caught.exception))
        self.assertIn("remedy:", str(caught.exception))
        if phrase:
            self.assertIn(phrase, str(caught.exception))

    def test_real_queued_request_claim_three_file_verdict_is_accepted(self):
        self.assertNotEqual(self.control, self.executor_control)
        self.assertEqual(self.verify(), self.verdict)
        self.assertEqual(len(self.verdict["suites"]), 16)
        self.assertTrue(all(s["selected"] and s["status"] == "passed" and not s["verification_debt"] for s in self.verdict["suites"]))
        self.assertTrue(all("/issues" not in path for path, _ in self.calls))

    def test_closed_reference_rejects_unknown_field(self):
        self.ref["extra"] = True
        self.rejected("schema")

    def test_boolean_attempt_is_not_integer_identity(self):
        self.ref["run_attempt"] = True
        self.rejected("attempt")

    def test_wrong_candidate_sha_is_rejected(self):
        self.ref["request"]["target"] = self.executor_control
        self.rejected("target")

    def test_foreign_workflow_is_rejected(self):
        self.executor_run["path"] = ".github/workflows/ci.yml"
        self.rejected("trusted main")

    def test_foreign_repository_is_rejected(self):
        self.executor_run["repository"]["id"] = 12
        self.rejected("repository")

    def test_latest_rerun_is_rejected(self):
        self.route("/actions/runs/102", dict(self.executor_run, run_attempt=2))
        self.rejected("first-attempt")

    def test_missing_origin_artifact_is_unverifiable(self):
        self.route("/actions/runs/101/artifacts?per_page=100&page=1", {"total_count": 0, "artifacts": []})
        self.rejected("absent", "unverifiable")

    def test_expired_admission_artifact_is_unverifiable(self):
        self.artifacts[102][0]["expired"] = True
        self.rejected("expired", "unverifiable")

    def test_expired_verdict_timestamp_is_unverifiable(self):
        self.artifacts[102][1]["expires_at"] = "2026-09-07T00:00:00Z"
        self.rejected("expired", "unverifiable")

    def test_settlement_snapshot_cannot_replace_admission(self):
        self.admission["action"] = "idle"
        self.downloads[2] = zipped({"result.json": self.admission})
        self.ref["admission_record_digest"] = self_test.digest_of(self.admission)
        self.rejected("admission attestation")

    def test_claim_from_another_run_is_rejected_even_with_new_digest(self):
        self.admission["state"]["active"]["claim"]["run_id"] = 103
        self.downloads[2] = zipped({"result.json": self.admission})
        self.ref["admission_record_digest"] = self_test.digest_of(self.admission)
        self.rejected("admission attestation")

    def test_changed_needs_is_rejected_without_trusting_green_verdict(self):
        self.needs["creator-web"]["result"] = "failure"
        self.downloads[3] = zipped(self.bundle)
        self.rejected("recomputed")

    def test_missing_product_job_api_is_rejected(self):
        self.jobs.pop()
        self.route("/actions/runs/102/attempts/1/jobs?per_page=100&page=1", {"total_count": len(self.jobs), "jobs": self.jobs})
        self.rejected("recomputed")

    def test_unrelated_api_failure_cannot_be_turned_into_absence(self):
        del self.routes[self.prefix + "/actions/runs/102"]
        self.rejected("unknown", "external-error")

    def test_incomplete_pagination_is_external_error(self):
        self.routes[self.prefix + "/actions/runs/102/attempts/1/jobs?per_page=100&page=1"]["total_count"] += 1
        self.rejected("declared total", "external-error")

    def test_bad_zip_is_conflict(self):
        self.downloads[3] = b"invalid ZIP"
        self.rejected("malformed")

    def test_artifact_from_another_control_is_rejected(self):
        self.artifacts[102][1]["workflow_run"]["head_sha"] = self.control
        self.rejected("control identity")

    def rewrite_snapshot(self, origin=False):
        document, identifier, field = ((self.origin_snapshot, 1, "origin_record_digest") if origin
                                       else (self.admission, 2, "admission_record_digest"))
        self.downloads[identifier] = zipped({"result.json": document})
        self.ref[field] = self_test.digest_of(document)

    def test_origin_waiting_must_actually_have_the_request_queued(self):
        self.origin_snapshot["state"]["queue"] = []
        self.rewrite_snapshot(origin=True)
        self.rejected("queued")

    def test_admission_cannot_borrow_an_origin_from_another_epoch(self):
        self.admission["state"]["epoch"] = "other-journal-epoch"
        self.rewrite_snapshot()
        self.rejected("epoch")

    def test_boolean_execution_run_does_not_match_integer_identity(self):
        self.bundle["execution.json"]["identity"]["run_attempt"] = True
        self.downloads[3] = zipped(self.bundle)
        self.rejected()

    def test_focused_request_is_not_full_candidate_evidence(self):
        self.request.update(kind="auto", base=self.control,
            selection=test_scope._selection(self.policy, ["creator"], ["focused"]))
        self.rejected("focused or none")

    def test_none_request_is_not_full_candidate_evidence(self):
        self.request.update(kind="auto", base=self.control,
            selection=test_scope._selection(self.policy, [], ["none"]))
        self.rejected("focused or none")

    def test_wrong_policy_digest_cannot_certify(self):
        self.request["policy"] = "f" * 64
        self.rejected("policy")

    def advance(self, path, transform):
        self.git("checkout", "-q", "main")
        target = self.root / path
        target.write_text(transform(target.read_text()))
        self.git("add", path)
        self.git("commit", "-qm", "fixture control drift")
        main = self.git("rev-parse", "HEAD")
        self.route("/branches/main", {"name": "main", "protected": True, "commit": {"sha": main}})
        return main

    def test_changed_current_policy_rejects_old_green_evidence(self):
        def change(raw):
            document = json.loads(raw)
            document["none_prefixes"].append("docs/extra-fixture/")
            return json.dumps(document)
        self.advance("scripts/ci/test_scope_policy.json", change)
        self.rejected("policy")

    def source_drift(self, path):
        control = self.advance(path, lambda raw: raw + "\n# incompatible fixture source\n")
        self.ref["executor_control_revision"] = control
        self.executor_run["head_sha"] = control
        for job in self.jobs:
            job["head_sha"] = control
        self.rejected("workflow sources")

    def test_caller_source_drift_is_rejected(self):
        self.source_drift(".github/workflows/self-test-report.yml")

    def test_core_source_drift_is_rejected(self):
        self.source_drift(".github/workflows/ci.yml")

    def test_stress_source_drift_is_rejected(self):
        self.source_drift(".github/workflows/core-nightly.yml")

    def test_portal_source_drift_is_rejected(self):
        self.source_drift(".github/workflows/architecture-portal.yml")

    def test_controller_skipped_is_not_durable_claim_attestation(self):
        self.jobs[0]["conclusion"] = "skipped"
        self.rejected("controller")

    def test_controller_never_started_is_not_attestation(self):
        self.jobs[0]["started_at"] = None
        self.rejected("controller")

    def test_producer_upload_failure_is_not_accepted(self):
        self.jobs[1]["steps"][1]["conclusion"] = "failure"
        self.rejected("upload")

    def test_api_product_failure_cannot_be_hidden_by_green_needs(self):
        next(j for j in self.jobs if j["name"] == shared.PREFIX + "creator-web")["conclusion"] = "failure"
        self.rejected("recomputed")

    def test_macos_primary_continuation_remains_the_only_api_exception(self):
        next(j for j in self.jobs if j["name"] == shared.PREFIX + "macOS gates (primary)")["conclusion"] = "failure"
        self.assertEqual(self.verify(), self.verdict)

    def rebuild_verdict(self):
        execution = self.bundle["execution.json"]
        self.verdict = batch_execution.from_needs(self.policy, execution["identity"], execution["selection"], self.needs,
            aliases=shared.ALIASES, dependencies=shared.dependencies(self.policy))
        self.bundle["verdict.json"] = self.verdict
        self.downloads[3] = zipped(self.bundle)
        self.ref["evidence_digest"] = self.verdict["evidence_digest"]

    def test_true_macos_alternative_pass_is_reusable(self):
        self.needs["macos-primary"]["result"] = "skipped"
        self.needs["macos-fallback"]["result"] = "success"
        self.rebuild_verdict()
        self.assertEqual(self.verdict["status"], "passed")
        next(j for j in self.jobs if j["name"] == shared.PREFIX + "macOS gates (GitHub-hosted fallback)")["conclusion"] = "success"
        next(j for j in self.jobs if j["name"] == shared.PREFIX + "macOS gates (primary)")["conclusion"] = "skipped"
        self.routes[self.prefix + "/actions/runs/102/attempts/1/jobs?per_page=100&page=1"]["total_count"] = len(self.jobs)
        self.assertEqual(self.verify(), self.verdict)

    def test_failed_full_is_rejected_even_with_matching_rehashed_evidence(self):
        self.needs["creator-web"]["result"] = "failure"
        self.rebuild_verdict()
        next(j for j in self.jobs if j["name"] == shared.PREFIX + "creator-web")["conclusion"] = "failure"
        self.jobs[1]["conclusion"] = "failure"
        self.jobs[1]["steps"][2]["conclusion"] = "failure"
        self.rejected("upload")

    def test_full_missing_stress_is_never_pass(self):
        self.needs["nightly-tsan"]["result"] = "skipped"
        self.rebuild_verdict()
        self.assertEqual(self.verdict["status"], "failed")
        self.rejected()

    def test_wrong_verdict_digest_is_rejected(self):
        self.ref["evidence_digest"] = "f" * 64
        self.rejected("referenced")

    def test_duplicate_artifact_name_is_rejected(self):
        duplicate = dict(self.artifacts[102][1], id=99)
        self.artifacts[102].append(duplicate)
        self.routes[self.prefix + "/actions/runs/102/artifacts?per_page=100&page=1"]["total_count"] = 3
        self.rejected("ambiguous")

    def test_duplicate_json_key_is_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("result.json", '{"schema":1,"schema":2}')
        self.downloads[1] = output.getvalue()
        self.rejected("malformed")

    def test_boolean_execution_lane_is_not_replaced_by_integer(self):
        self.bundle["execution.json"]["lanes"]["creator"] = 1
        self.downloads[3] = zipped(self.bundle)
        self.rejected("projection types")

    def test_full_inventory_pagination_reads_the_last_page(self):
        jobs = self.jobs + [self.job(102, self.executor_control, "Unrelated fixture job", "skipped") for _ in range(105 - len(self.jobs))]
        self.route("/actions/runs/102/attempts/1/jobs?per_page=100&page=1", {"total_count": 105, "jobs": jobs[:100]})
        self.route("/actions/runs/102/attempts/1/jobs?per_page=100&page=2", {"total_count": 105, "jobs": jobs[100:]})
        self.assertEqual(self.verify(), self.verdict)
        self.assertIn((self.prefix + "/actions/runs/102/attempts/1/jobs?per_page=100&page=2", False), self.calls)

    def test_duplicate_job_on_later_page_is_external_error(self):
        jobs = self.jobs + [self.job(102, self.executor_control, "Unrelated fixture job", "skipped") for _ in range(100 - len(self.jobs))]
        self.route("/actions/runs/102/attempts/1/jobs?per_page=100&page=1", {"total_count": 101, "jobs": jobs})
        self.route("/actions/runs/102/attempts/1/jobs?per_page=100&page=2", {"total_count": 101, "jobs": [jobs[0]]})
        self.rejected("duplicate", "external-error")

    def test_old_failures_and_history_unknown_do_not_reclassify_current_full(self):
        self.admission["state"]["failures"] = [{"request_id": "old-request", "suite": "ci_contract"}]
        self.assertTrue(self.admission["state"]["history_unknown"])
        self.rewrite_snapshot()
        self.assertEqual(self.verify(), self.verdict)

    def same_run(self, kind):
        self.request = batch.make_request(self.policy, request_id="same-run-fixture", kind=kind, base_sha=None,
            target_sha=self.control, control_sha=self.control, selection=test_scope._selection(self.policy, self.policy.suite_ids, ["full"]),
            origin_run={"run_id": 102, "attempt": 1})
        state = batch.new_state("same-run-epoch")
        def transition(kind, data):
            nonlocal state
            state = batch.reduce(state, {"id": str(state["generation"]), "epoch": state["epoch"], "generation": state["generation"],
                "type": kind, "data": data}, self.policy)
        transition("observe", {"target": self.control, "descends_pending": True})
        if kind in {"candidate", "node"}:
            transition("enqueue", self.request)
        transition("admit", {"request": self.request, "executor_run": {"run_id": 102, "attempt": 1},
            "history_complete": True, "ancestor": True, "old_runs_terminal": True})
        transition("claim", {"request_id": self.request["id"], "run": {"run_id": 102, "attempt": 1}})
        self.admission = self.snapshot("execute", self.request, 102, state)
        self.executor_run["head_sha"] = self.control
        for row in self.jobs:
            row["head_sha"] = self.control
        for row in self.artifacts[102]:
            row["workflow_run"]["head_sha"] = self.control
        self.bundle["execution.json"] = batch_execution.prepare(self.policy, self.request, {"run_id": 102, "attempt": 1},
            repo=self.root, run_id=102, run_attempt=1, control_sha=self.control, main_sha=self.executor_control)
        self.ref.update(request=self.request, executor_control_revision=self.control)
        self.rewrite_snapshot()
        self.ref["origin_record_digest"] = self.ref["admission_record_digest"]
        self.rebuild_verdict()

    def test_same_run_candidate_preserves_exact_admission(self):
        self.same_run("candidate")
        self.assertEqual(self.verify(), self.verdict)

    def test_same_run_bootstrap_full_can_be_explicitly_reused(self):
        self.same_run("bootstrap")
        self.assertEqual(self.verify(), self.verdict)

    def test_same_run_node_full_can_be_explicitly_reused(self):
        self.same_run("node")
        self.assertEqual(self.verify(), self.verdict)

    def test_origin_snapshot_digest_is_independently_bound(self):
        self.ref["origin_record_digest"] = "0" * 64
        self.rejected("digest")

    def test_wrong_verdict_target_cannot_be_mixed(self):
        self.bundle["verdict.json"]["identity"]["target_sha"] = self.executor_control
        self.downloads[3] = zipped(self.bundle)
        self.rejected("recomputed")

    def test_duplicate_producer_is_rejected(self):
        self.jobs.append(dict(self.jobs[1], id=99999))
        self.routes[self.prefix + "/actions/runs/102/attempts/1/jobs?per_page=100&page=1"]["total_count"] = len(self.jobs)
        self.rejected("judge and upload")

    def test_non_main_target_commit_is_not_a_candidate(self):
        (self.root / "unmerged.txt").write_text("not main\n")
        self.git("add", "unmerged.txt")
        self.git("commit", "-qm", "detached unmerged candidate")
        unmerged = self.git("rev-parse", "HEAD")
        self.request["target"] = unmerged
        with self.assertRaises(consumer.BatchEvidenceError) as caught:
            self.reader.verify(self.ref, run_id=102, target_revision=unmerged)
        self.assertEqual(caught.exception.code, "unverifiable")

    def test_source_predating_the_trusted_producer_is_rejected(self):
        self.reader.producer_revision = self.executor_control
        self.rejected("provenance", "unverifiable")

    def test_api_exception_diagnostic_does_not_leak_transport_body(self):
        def failed(path, *, raw=False):
            raise OSError("SECRET-TRANSPORT-PAYLOAD")
        self.reader.api_get = failed
        with self.assertRaises(consumer.BatchEvidenceError) as caught:
            self.verify()
        self.assertEqual(caught.exception.code, "external-error")
        self.assertNotIn("SECRET", str(caught.exception))

    def test_visibility_step_must_be_terminal_even_when_conclusion_says_skipped(self):
        self.jobs[1]["steps"][2]["status"] = "in_progress"
        self.rejected("visibility")

    def test_latest_and_attempt_conclusion_disagreement_is_not_green(self):
        self.route("/actions/runs/102", dict(self.executor_run, conclusion="failure"))
        self.rejected("views")

    def test_scheduled_bootstrap_origin_and_executor_preserve_full_attestation(self):
        self.same_run("bootstrap")
        self.executor_run["event"] = "schedule"
        self.assertEqual(self.verify(), self.verdict)

    def test_scheduled_executor_can_admit_a_queued_explicit_candidate(self):
        self.executor_run["event"] = "schedule"
        self.assertNotEqual(self.control, self.executor_control)
        self.assertEqual(self.verify(), self.verdict)

    def test_unknown_origin_event_is_rejected(self):
        self.origin_run["event"] = "repository_dispatch"
        self.rejected("trusted main")

    def test_unknown_executor_event_is_rejected(self):
        self.executor_run["event"] = "repository_dispatch"
        self.rejected("trusted main")


if __name__ == "__main__":
    unittest.main()
