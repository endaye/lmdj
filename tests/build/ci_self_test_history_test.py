#!/usr/bin/env python3
"""Dedup consumes real producer documents, with a read-only strict API double."""

from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import self_test as protocol
import self_test_history as history
import self_test_report as report

CONTROL, TARGET, OLD = "a" * 40, "b" * 40, "c" * 40


class Api:
    def __init__(self, policy):
        self.policy = policy
        self.runs = []
        self.artifacts = {}
        self.documents = {}
        self.calls = []
        self.ancestor = "ahead"

    def get_workflow(self):
        return {"id": 123, "path": ".github/workflows/ci.yml"}

    def list_runs(self, workflow, *, event, created, per_page, status):
        assert (workflow, created, per_page, status) == ("ci.yml", None, 20, "completed")
        self.calls.append(("runs", event))
        return [run for run in self.runs if run["event"] == event]

    def list_artifacts(self, run_id):
        self.calls.append(("artifacts", run_id))
        return self.artifacts.get(run_id, [])

    def compare(self, base, head):
        assert base == report.PRODUCER_REVISION and head == CONTROL
        return {"status": self.ancestor}

    def get_policy(self, revision):
        assert revision == CONTROL
        return self.policy

    def download_artifact(self, artifact_id):
        self.calls.append(("download", artifact_id))
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("verdict.json", json.dumps(self.documents[artifact_id]))
        return output.getvalue()


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "scripts/ci/self_test_policy.json").read_text())
        self.parsed = protocol.parse_policy(self.policy)
        self.api = Api(self.policy)

    def add(self, run_id=12, target=TARGET, event="schedule", failure=False):
        identity = protocol.Identity(protocol.EVIDENCE_SCHEMA,
                                     "schedule" if event == "schedule" else "candidate",
                                     CONTROL, target, run_id, 1, self.parsed.revision)
        rows = [protocol.Observation(suite.id, job, run_id, 1, target,
                                    "failure" if failure else "success")
                for suite in self.parsed.suites for job in suite.jobs]
        verdict = protocol.aggregate(identity, self.parsed, rows)
        self.api.runs.append({"id": run_id, "run_attempt": 1, "event": event,
                              "path": ".github/workflows/ci.yml", "head_sha": CONTROL,
                              "head_branch": "main", "status": "completed",
                              "conclusion": "failure" if failure else "success",
                              "html_url": f"https://github.com/owner/repo/actions/runs/{run_id}",
                              "repository": {"full_name": "owner/repo"}, "workflow_id": 123})
        self.api.artifacts[run_id] = [{"id": run_id, "expired": False,
                                      "name": f"self-test-verdict-{target}-{run_id}-1"}]
        self.api.documents[run_id] = {**verdict.as_document(), "evidence_digest": verdict.digest}

    def find(self):
        return history.find_conclusion(self.api, repository="owner/repo", target=TARGET,
                                       policy_document=self.policy, main_history={CONTROL, TARGET, OLD},
                                       current_run=99)

    def test_first_run_without_history_is_not_a_skip(self):
        self.assertIsNone(self.find())

    def test_late_old_target_does_not_hide_the_matching_target(self):
        self.add(13, OLD)
        self.add(12, TARGET)
        result = self.find()
        self.assertEqual(result["target_revision"], TARGET)
        self.assertEqual(result["source_run_id"], 12)
        self.assertNotIn(("download", 13), self.api.calls)

    def test_manual_candidate_evidence_is_reusable_by_schedule(self):
        self.add(event="workflow_dispatch")
        self.assertEqual(self.find()["status"], "passed")

    def test_existing_failure_remains_failed_without_fabricated_green(self):
        self.add(failure=True)
        result = self.find()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["evidence_digest"], self.api.documents[12]["evidence_digest"])

    def test_expired_absent_wrong_attempt_or_other_target_cannot_skip(self):
        for change in (lambda a: a.update(expired=True), lambda a: a.update(name="unrelated"),
                       lambda a: a.update(name=f"self-test-verdict-{TARGET}-12-2")):
            self.setUp()
            self.add()
            change(self.api.artifacts[12][0])
            self.assertIsNone(self.find())
        self.setUp()
        self.add(target=OLD)
        self.assertIsNone(self.find())

    def test_only_same_repository_main_workflow_attempt_one_is_trusted(self):
        for field, value in (("repository", {"full_name": "fork/repo"}),
                             ("workflow_id", 999), ("path", ".github/workflows/other.yml"),
                             ("head_branch", "feat/fake"), ("head_sha", "f" * 40),
                             ("run_attempt", 2), ("status", "in_progress")):
            self.setUp()
            self.add()
            self.api.runs[0][field] = value
            self.assertIsNone(self.find(), field)

    def test_policy_mismatch_and_preproducer_history_cannot_skip(self):
        self.add()
        changed = deepcopy(self.policy)
        changed["suites"][0]["note"] = "different protocol projection"
        self.api.policy = changed
        self.assertIsNone(self.find())
        self.api.policy = self.policy
        self.api.ancestor = "diverged"
        self.assertIsNone(self.find())

    def test_corrupt_digest_and_mixed_identity_are_rejected(self):
        self.add()
        self.api.documents[12]["evidence_digest"] = "0" * 64
        with self.assertRaises(report.ReportingError):
            self.find()
        self.setUp()
        self.add()
        self.api.documents[12]["identity"]["run_attempt"] = 2
        with self.assertRaises(report.ReportingError):
            self.find()

    def test_cli_api_failure_clears_stale_skip_authority_and_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, ancestry = root / "last.json", root / "history"
            output.write_text('{"status":"passed"}')
            ancestry.write_text(TARGET + "\n")
            with patch.object(report, "UrllibGitHubApi", side_effect=report.GitHubApiError(404, "Not found")):
                result = history.main(["--repository", "owner/repo", "--target", TARGET,
                                       "--run-id", "99", "--main-history", str(ancestry),
                                       "--policy", str(ROOT / "scripts/ci/self_test_policy.json"),
                                       "--out", str(output)])
            self.assertEqual(result, 0)
            self.assertIsNone(json.loads(output.read_text()))


if __name__ == "__main__":
    unittest.main()
