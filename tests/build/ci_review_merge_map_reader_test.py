"""Read-only consumer contracts; API fixtures do not establish platform O1."""
import base64
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import review_merge_map_reader as reader
import review_merge_map as mapping
import test_scope
import batch_controller

A, B, C = (c * 40 for c in "abc")
POLICY = test_scope.load_policy(ROOT)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.identity = dict(repository="endaye/lmdj", pr_number=7, head_sha=A, base_sha=B,
                             control_sha=B, backend="kimi", run_id=1, run_attempt=1)
        self.record = test_scope.build_record(POLICY, changed_paths=["docs/notes/a.md"], **self.identity)
        self.document = mapping.build_map(repository="endaye/lmdj", repository_id=5, pr_number=7,
            head_sha=A, merge_sha=C, control_sha=B, run_id=2, run_attempt=1, workflow_id=42,
            changed_paths=["docs/notes/a.md"], scope_records=[{"record": self.record, "review_id": 3, "artifact_id": 4}],
            complete=True, gaps=[])
        self.artifacts = [{"id": 6, "name": f"pr-review-merge-map-{C}-2-1", "expired": False, "workflow_run": {"id": 2}}]
        self.run = dict(id=2, run_attempt=1, workflow_id=42, path=".github/workflows/pr-review.yml",
            repository={"id": 5, "full_name": "endaye/lmdj"}, head_sha=A, pull_requests=[],
            event="pull_request", status="completed", conclusion="success")
        def job(name, result, steps):
            return dict(id=len(name), name=name, run_id=2, run_attempt=1, status="completed", conclusion=result,
                        steps=[dict(name=n, conclusion=c) for n, c in steps])
        self.jobs = [job("Resolve review target", "success", [("Resolve the Pull Request head", "skipped")]),
                     job("Review fallback", "skipped", []),
                     job("Publish review and scope", "success", [("Map merged PR without another AI call", "success"),
                                                               ("Publish exact-head review and scope", "skipped")])]
        self.source = b"trusted workflow"
        self.interval = {"base_sha": B, "target_sha": C, "paths": ["docs/notes/a.md"],
                         "changed_path_digest": self.record["changed_path_digest"],
                         "commits": [{"sha": C, "parent_sha": B,
                                      "changes": [{"status": "A", "paths": ["docs/notes/a.md"]}]}]}
        self.inputs = mock.Mock(repository=ROOT, main=C, control_sha=B)
        self.inputs.policy_at.return_value = POLICY
        self.inputs._git.side_effect = lambda *args: (B + "\n" + C).encode() if args[0] == "rev-list" else b"trusted workflow"
        self.reads = []
        self.consumer = reader.MergeMapReader("endaye/lmdj", 5, 42, self.inputs, self.get, self.download)

    def get(self, path):
        self.reads.append(path)
        self.assertNotIn("/pulls", path)
        if "/actions/artifacts?" in path:
            return {"total_count": len(self.artifacts), "artifacts": self.artifacts}
        if path.endswith("/attempts/1"):
            return self.run
        if "/jobs?" in path:
            return {"total_count": len(self.jobs), "jobs": self.jobs}
        if "/contents/" in path:
            return {"encoding": "base64", "content": base64.b64encode(self.source).decode()}
        self.fail("unexpected API endpoint " + path)

    def download(self, artifact):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("map.json", json.dumps(self.document))
        return archive.getvalue()

    def call(self):
        with mock.patch.object(reader.test_scope, "collect_interval", return_value=deepcopy(self.interval)):
            return self.consumer(deepcopy(self.interval))

    def change_map(self, **changes):
        args = {key: self.document[key] for key in mapping.KEYS - {"schema", "changed_path_digest", "digest"}}
        self.document = mapping.build_map(**{**args, **changes})

    def test_closed_run_pr_head_and_empty_association_are_valid(self):
        self.assertEqual(self.call(), {"complete": True, "labels": []})

    def test_closed_run_merge_sha_shape_is_also_bound_to_workflow_source(self):
        self.run["head_sha"] = C
        self.assertTrue(self.call()["complete"])

    def test_ai_additions_are_retained(self):
        self.record = test_scope.build_record(POLICY, changed_paths=["docs/notes/a.md"], ai_labels=["test:creator"], **self.identity)
        self.change_map(scope_records=[{"record": self.record, "review_id": 3, "artifact_id": 4}])
        self.assertIn("test:creator", self.call()["labels"])

    def test_missing_commit_mapping_is_not_no_pr(self):
        self.artifacts = []
        self.assertFalse(self.call()["complete"])

    def test_unmapped_second_commit_cannot_be_lost_in_net_paths(self):
        self.interval["commits"].append({"sha": "d" * 40, "parent_sha": C,
                                         "changes": [{"status": "M", "paths": ["docs/notes/a.md"]}]})
        self.assertFalse(self.call()["complete"])

    def test_real_git_interval_retains_valid_ai_suggestion_through_final_scope(self):
        # Real interval data, not a fake commit['paths'] shape. HTTP receipts
        # remain fixtures; this does not claim real Actions producer authority.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root),
                    '-c', 'user.name=CI fixture', '-c', 'user.email=ci-fixture@example.invalid',
                    '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', *args], text=True).strip()
            git('init', '-q')
            for name in ('scope_policy.json', 'self_test_policy.json', 'test_scope_policy.json'):
                path = root / 'scripts/ci' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / 'scripts/ci' / name).read_bytes())
            source = root / '.github/workflows/pr-review.yml'
            source.parent.mkdir(parents=True)
            source.write_bytes(self.source)
            git('add', '.')
            git('commit', '-qm', 'trusted policy fixture')
            base = git('rev-parse', 'HEAD')
            note = root / 'docs/notes/a.md'
            note.parent.mkdir(parents=True)
            note.write_text('Explanatory document; AI adds a consumer test.\n')
            git('add', '.')
            git('commit', '-qm', 'actual interval fixture')
            tip = git('rev-parse', 'HEAD')
            identity = {**self.identity, 'base_sha': base, 'head_sha': tip, 'control_sha': base}
            record = test_scope.build_record(POLICY, changed_paths=['docs/notes/a.md'],
                                            ai_labels=['test:creator'], **identity)
            self.document = mapping.build_map(repository='endaye/lmdj', repository_id=5, pr_number=7,
                head_sha=tip, merge_sha=tip, control_sha=base, run_id=2, run_attempt=1, workflow_id=42,
                changed_paths=['docs/notes/a.md'], scope_records=[{'record': record, 'review_id': 3, 'artifact_id': 4}],
                complete=True, gaps=[])
            self.artifacts[0]['name'] = f'pr-review-merge-map-{tip}-2-1'
            self.run['head_sha'] = tip
            self.inputs = batch_controller.GitInputs(root, base, lambda: tip)
            self.inputs.refresh()
            self.consumer = reader.MergeMapReader('endaye/lmdj', 5, 42, self.inputs, self.get, self.download)
            self.inputs.advice = self.consumer
            actual = test_scope.collect_interval(root, base, tip)
            self.assertEqual(self.consumer(actual), {'complete': True, 'labels': ['test:creator']},
                'why: real commit shape lost valid AI advice; remedy: derive per-commit paths from actual changes')
            selected = self.inputs.interval_selection(base, tip, POLICY)
            self.assertEqual(selected['kind'], 'focused')
            self.assertEqual(selected['suites'], ['creator'])

    def test_failed_mapper_cannot_authorize_none(self):
        self.run["conclusion"] = "failure"
        self.assertFalse(self.call()["complete"])

    def test_ordinary_review_cannot_impersonate_mapping_run(self):
        self.jobs[0]["steps"][0]["conclusion"] = "success"
        self.assertFalse(self.call()["complete"])

    def test_running_publisher_cannot_authorize_none(self):
        self.jobs[2]["status"] = "in_progress"
        self.assertFalse(self.call()["complete"])

    def test_wrong_run_attempt_is_rejected(self):
        self.run["run_attempt"] = 2
        self.assertFalse(self.call()["complete"])

    def test_wrong_workflow_is_rejected(self):
        self.run["workflow_id"] = 43
        self.assertFalse(self.call()["complete"])

    def test_wrong_repository_is_rejected(self):
        self.run["repository"]["id"] = 6
        self.assertFalse(self.call()["complete"])

    def test_wrong_head_is_rejected(self):
        self.run["head_sha"] = "d" * 40
        self.assertFalse(self.call()["complete"])

    def test_nonempty_wrong_pr_is_rejected(self):
        self.run["pull_requests"] = [{"number": 8, "head": {"sha": A}}]
        self.assertFalse(self.call()["complete"])

    def test_expired_artifact_is_rejected(self):
        self.artifacts[0]["expired"] = True
        self.assertFalse(self.call()["complete"])

    def test_artifact_run_mismatch_is_rejected(self):
        self.artifacts[0]["workflow_run"]["id"] = 9
        self.assertFalse(self.call()["complete"])

    def test_actual_workflow_must_match_trusted_control(self):
        self.source = b"untrusted workflow"
        self.assertFalse(self.call()["complete"])

    def test_mapping_paths_must_equal_actual_first_parent_delta(self):
        self.change_map(changed_paths=["docs/notes/b.md"])
        self.assertFalse(self.call()["complete"])

    def test_mapping_must_include_both_actual_rename_paths(self):
        paths = ['docs/notes/a.md', 'docs/notes/old.md']
        self.interval['commits'][0]['changes'] = [{'status': 'R100', 'paths': list(reversed(paths))}]
        self.interval['paths'] = paths
        self.assertFalse(self.call()['complete'])
        self.change_map(changed_paths=paths)
        self.assertTrue(self.call()['complete'])

    def test_incomplete_mapping_keeps_authenticated_partial_ai_advice(self):
        record = test_scope.build_record(POLICY, changed_paths=['docs/notes/a.md'],
                                        ai_labels=['test:creator'], **self.identity)
        self.change_map(complete=False, gaps=['another review unavailable'],
                        scope_records=[{'record': record, 'review_id': 3, 'artifact_id': 4}])
        self.assertEqual(self.call(), {'complete': False, 'labels': ['test:creator']})

    def test_historical_policy_is_independently_recomputed(self):
        self.inputs.policy_at.side_effect = ValueError("historical policy unavailable")
        self.assertFalse(self.call()["complete"])

    def test_incomplete_map_preserves_unavailability_not_a_scope_verdict(self):
        self.change_map(complete=False, gaps=["scope unavailable"])
        self.assertFalse(self.call()["complete"])

    def test_both_maps_are_read_not_latest_wins(self):
        self.artifacts.append({**self.artifacts[0], "id": 7, "expired": True})
        self.assertFalse(self.call()["complete"])

    def test_api_failure_is_not_empty_history(self):
        self.consumer.get = mock.Mock(side_effect=RuntimeError("403"))
        self.assertFalse(self.call()["complete"])
        self.assertIn("remedy:", self.consumer.diagnostics[0])

    def test_truncated_inventory_is_rejected(self):
        self.consumer.get = lambda path: {"total_count": 10, "artifacts": self.artifacts}
        self.assertFalse(self.call()["complete"])

    def test_malformed_zip_is_rejected(self):
        self.consumer.download = lambda artifact: b"invalid"
        self.assertFalse(self.call()["complete"])


if __name__ == "__main__":
    unittest.main()
