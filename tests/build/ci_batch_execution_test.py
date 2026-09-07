#!/usr/bin/env python3
"""Real local Git and artifact boundaries, not remote scheduler acceptance."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import batch_execution as execution
import incremental_batch as batch
import test_scope


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.run_git("init", "-q", "-b", "main")
        self.run_git("config", "user.name", "CI fixture")
        self.run_git("config", "user.email", "ci@example.invalid")
        directory = self.repo / "scripts/ci"
        directory.mkdir(parents=True)
        for name in ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json"):
            (directory / name).write_bytes((ROOT / "scripts/ci" / name).read_bytes())
        self.run_git("add", "scripts/ci")
        self.run_git("commit", "-qm", "fixture policies")
        self.base = self.run_git("rev-parse", "HEAD")
        (self.repo / "note.md").write_text("note\n")
        self.run_git("add", "note.md")
        self.run_git("commit", "-qm", "fixture note")
        self.target = self.run_git("rev-parse", "HEAD")
        self.policy = test_scope.load_policy(self.repo)
        self.selection = test_scope._selection(self.policy, ["docs_static"], ["owned changed docs"])
        self.executor = {"run_id": 99, "attempt": 1}
        self.request = batch.make_request(
            self.policy, request_id="fixed-request", kind="auto", base_sha=self.base,
            target_sha=self.target, control_sha=self.target, selection=self.selection,
            origin_run={"run_id": 98, "attempt": 1})

    def run_git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def prepare(self, **overrides):
        arguments = dict(repo=self.repo, run_id=99, run_attempt=1,
                         control_sha=self.target, main_sha=self.target)
        arguments.update(overrides)
        return execution.prepare(self.policy, self.request, self.executor, **arguments)

    def verdict(self, needs, **options):
        prepared = self.prepare()
        return execution.from_needs(self.policy, prepared["identity"], self.selection, needs, **options)

    def test_actual_executor_is_independent_of_queued_request_origin(self):
        prepared = self.prepare()
        self.assertEqual(prepared["identity"]["run_id"], 99,
                         "why: queued request selected its old origin run; remedy: use admitted executor")

    def test_lane_and_stress_projection_comes_from_complete_policy(self):
        prepared = self.prepare()
        self.assertEqual(set(prepared["suites"]), set(self.policy.suite_ids))
        self.assertEqual(set(prepared["lanes"]), set(self.policy.routing["lanes"]))
        self.assertEqual([key for key, value in prepared["suites"].items() if value], ["docs_static"])

    def test_wrong_executor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "admitted executor"):
            self.prepare(run_id=100)

    def test_partial_rerun_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "admitted executor"):
            self.prepare(run_attempt=2)

    def test_boolean_executor_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "admitted executor"):
            self.prepare(run_id=True)

    def test_checkout_of_target_cannot_replace_frozen_control(self):
        self.request["control"] = self.base
        with self.assertRaisesRegex(ValueError, "checkout"):
            self.prepare(control_sha=self.base)

    def test_missing_target_history_is_rejected(self):
        self.request["target"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "Git provenance"):
            self.prepare()

    def test_explicit_candidate_cannot_use_annotated_tag_object_as_commit(self):
        self.run_git("tag", "-a", "fixture-candidate", "-m", "local fixture only")
        tag_object = self.run_git("rev-parse", "refs/tags/fixture-candidate")
        self.request.update(kind="candidate", target=tag_object,
                            selection=test_scope.select(self.policy, ["contracts/example.json"]))
        with self.assertRaisesRegex(ValueError, "target.*commit"):
            self.prepare()

    def test_main_identity_cannot_be_peeled_from_tag_object(self):
        self.run_git("tag", "-a", "fixture-main", "-m", "local fixture only")
        tag_object = self.run_git("rev-parse", "refs/tags/fixture-main")
        with self.assertRaisesRegex(ValueError, "main.*commit"):
            self.prepare(main_sha=tag_object)

    def test_shallow_repository_cannot_validate_a_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "clone", "--depth=1", self.repo.as_uri(), directory],
                           check=True, capture_output=True)
            with self.assertRaisesRegex(ValueError, "shallow history"):
                self.prepare(repo=Path(directory))

    def test_target_outside_main_history_is_rejected(self):
        self.run_git("checkout", "-q", "--orphan", "outside")
        self.run_git("commit", "-qm", "outside history")
        outside = self.run_git("rev-parse", "HEAD")
        self.run_git("checkout", "-q", "main")
        self.request["target"] = outside
        with self.assertRaisesRegex(ValueError, "Git provenance"):
            self.prepare()

    def test_non_first_parent_baseline_is_rejected(self):
        self.run_git("checkout", "-qb", "side", self.base)
        (self.repo / "side.md").write_text("side\n")
        self.run_git("add", "side.md")
        self.run_git("commit", "-qm", "side")
        side = self.run_git("rev-parse", "HEAD")
        self.run_git("checkout", "-q", "main")
        self.run_git("merge", "--no-ff", "-qm", "merge fixture", "side")
        self.target = self.run_git("rev-parse", "HEAD")
        self.request.update(base=side, target=self.target, control=self.target)
        with self.assertRaisesRegex(ValueError, "first-parent"):
            self.prepare()

    def test_missing_selected_results_retain_debt(self):
        verdict = self.verdict({})
        selected = next(row for row in verdict["suites"] if row["id"] == "docs_static")
        self.assertEqual(selected["scheduler_outcome"], "missing")
        self.assertEqual(verdict["status"], "failed")

    def test_unselected_skips_are_not_observations(self):
        verdict = self.verdict({"docs-static": {"result": "success"}, "core-ubuntu": {"result": "skipped"}})
        self.assertEqual(verdict["status"], "passed")
        self.assertEqual([row["job"] for row in verdict["observations"]], ["docs-static"])

    def test_unselected_executed_product_job_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unselected product job"):
            self.verdict({"core-ubuntu": {"result": "success"}})

    def test_explicit_alias_retains_canonical_job_identity(self):
        verdict = self.verdict({"documents": {"result": "success"}}, aliases={"docs-static": "documents"})
        self.assertEqual(verdict["observations"][0]["job"], "docs-static")

    def test_alias_cannot_make_two_product_jobs_share_evidence(self):
        with self.assertRaisesRegex(ValueError, "share one needs"):
            self.verdict({}, aliases={"docs-static": "core-ubuntu"})

    def test_invalid_product_output_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "job outputs"):
            self.verdict({"docs-static": {"result": "success", "outputs": {"infrastructure_failure": True}}})

    def test_unknown_infrastructure_flag_cannot_become_test_success(self):
        with self.assertRaisesRegex(ValueError, "unknown infrastructure"):
            self.verdict({"docs-static": {"result": "success", "outputs": {"infrastructure_failure": "unknown"}}})

    def test_dependency_failure_marks_selected_skip_blocked(self):
        verdict = self.verdict({"docs-static": {"result": "skipped"}, "prepare": {"result": "failure"}},
                               dependencies={"docs-static": ["prepare"]})
        selected = next(row for row in verdict["suites"] if row["id"] == "docs_static")
        self.assertEqual(selected["scheduler_outcome"], "blocked")

    def test_none_is_not_a_successful_product_test(self):
        self.selection = test_scope._selection(self.policy, [], ["explanatory docs"])
        self.request["selection"] = self.selection
        self.assertEqual(self.verdict({})["status"], "not-required")

    def test_cli_writes_exact_execution_identity(self):
        input_path, output_path = self.repo / "input.json", self.repo / "output.json"
        input_path.write_text(json.dumps({"request": self.request, "executor": self.executor,
                                         "run_id": 99, "run_attempt": 1, "control_sha": self.target,
                                         "main_sha": self.target}))
        self.assertEqual(execution.main(["prepare", "--root", str(self.repo), "--input", str(input_path),
                                         "--output", str(output_path)]), 0)
        self.assertEqual(json.loads(output_path.read_text()), self.prepare())

    def test_cli_rejects_duplicate_keys_without_output(self):
        input_path, output_path = self.repo / "input.json", self.repo / "output.json"
        input_path.write_text('{"identity": {}, "identity": {}}')
        self.assertEqual(execution.main(["verdict", "--root", str(self.repo), "--input", str(input_path),
                                         "--output", str(output_path)]), 1)
        self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
