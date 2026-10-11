#!/usr/bin/env python3
"""Focused CI work must retain every audited consumer and full fallback."""
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import contract_selection as selection


class ContractSelectionTest(unittest.TestCase):
    def git_fixture(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        def git(*args):
            return subprocess.check_output(["git", "-C", str(root), *args], env=environment,
                                           stderr=subprocess.PIPE, text=True).strip()
        git("init", "-b", "feat/selector-fixture")
        path = root / "scripts/ci/local_preflight.py"
        path.parent.mkdir(parents=True)
        path.write_text("# baseline\n")
        git("add", ".")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-m", "baseline")
        return root, git, git("rev-parse", "HEAD")

    def test_local_inventory_includes_dirty_and_untracked_files(self):
        root, _, base = self.git_fixture()
        (root / "scripts/ci/local_preflight.py").write_text("# changed\n")
        (root / "new-control.py").write_text("# unknown\n")
        self.assertEqual(selection.changed_paths(root, base),
                         ["new-control.py", "scripts/ci/local_preflight.py"])

    def test_rename_to_documentation_keeps_the_old_control_path(self):
        root, git, base = self.git_fixture()
        (root / "docs/plans").mkdir(parents=True)
        git("mv", "scripts/ci/local_preflight.py", "docs/plans/retired.md")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-m", "rename")
        self.assertEqual(selection.changed_paths(root, base, "HEAD"),
                         ["docs/plans/retired.md", "scripts/ci/local_preflight.py"])

    def test_preflight_change_selects_absolute_consumer_inventory_without_seam(self):
        result = selection.select(ROOT, ["scripts/ci/local_preflight.py",
                                         "docs/plans/2026-10-11-lmdj-daily-ci-simplification.md"])
        self.assertEqual(result["mode"], "focused", result["reason"])
        self.assertFalse(result["seam"])
        self.assertEqual(result["tests"], sorted([
            "tests/build/ci_contract_selection_test.py",
            "tests/build/ci_local_preflight_test.py",
            "tests/build/ci_change_scope_test.py",
            "tests/build/ci_workflow_topology_test.py",
            "tests/build/ci_build_acceleration_test.py",
            "tests/build/ci_issue_done_skill_test.py",
            "tests/build/ci_scope_policy_consumer_parity_test.py",
            "tests/build/ci_scope_policy_differential_test.py",
            "tests/build/ci_toolchain_pin_test.py",
            "tests/build/ci_classification_inputs_test.py",
        ]))

    def test_full_inventory_matches_tracked_test_producer(self):
        # Independent Git inventory: a selector-owned list could agree with
        # its own focused catalog while silently omitting a complete suite.
        tracked = subprocess.check_output(["git", "ls-files", "tests/build/ci_*_test.py"],
                                          cwd=ROOT, text=True).splitlines()
        expected = set(tracked) | {"tests/build/ci_contract_selection_test.py"}
        result = selection.select(ROOT, ["scripts/ci/local_preflight.py"], profile="full")
        self.assertEqual(set(result["tests"]), expected)
        self.assertTrue(result["seam"])

    def test_unknown_or_changed_selector_requires_full(self):
        for path in ("scripts/ci/new_control.py", "scripts/ci/contract_selection.py",
                     "tests/build/ci_contract_selection_test.py", "unknown/extension.xyz"):
            with self.subTest(path=path):
                result = selection.select(ROOT, [path])
                self.assertEqual(result["mode"], "full")
                self.assertTrue(result["seam"])

    def test_every_real_handler_boundary_keeps_its_seam(self):
        for path in ("scripts/ci/pr_agent_review.py", "scripts/ci/pr-agent/config.toml",
                     "scripts/ci/pr-agent/requirements.lock", "scripts/ci/pr-agent/integration-test.sh",
                     "tests/fixtures/ci/pr-agent/summary.md", "tests/build/ci_pr_agent_review_test.py"):
            with self.subTest(path=path):
                self.assertTrue(selection.select(ROOT, [path])["seam"])

    def test_new_reader_is_detected_and_forces_full(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts/ci").mkdir(parents=True)
            (root / "tests/build").mkdir(parents=True)
            shutil.copy(ROOT / "scripts/ci/scope_policy.json", root / "scripts/ci/scope_policy.json")
            for path in selection.PREFLIGHT_TESTS | {selection.OWN_TEST}:
                (root / path).write_text("# test fixture\n")
            (root / "scripts/ci/new_reader.py").write_text("import local_preflight\n")
            self.assertEqual(selection.new_consumers(root), ["scripts/ci/new_reader.py"])
            result = selection.select(root, ["scripts/ci/local_preflight.py"])
            self.assertEqual(result["mode"], "full")
            self.assertTrue(result["seam"])

    def test_audit_comments_do_not_invent_executable_consumers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comment.py"
            path.write_text('"""local_preflight.py is documented here."""\n# local_preflight\n')
            self.assertEqual(selection.references(path), "")
            path.write_text('from local_preflight import build_plan\n')
            self.assertIn("local_preflight", selection.references(path))

    def test_invalid_git_range_is_not_an_empty_plan(self):
        with self.assertRaisesRegex(ValueError, "why:.*remedy:"):
            selection.changed_paths(ROOT, "missing-contract-selection-base")

    def test_failed_contract_tests_prevent_the_seam(self):
        with mock.patch.object(selection, "changed_paths", return_value=["scripts/ci/pr_agent_review.py"]), \
                mock.patch.object(selection, "run_tests", return_value=1), \
                mock.patch.object(selection.subprocess, "run", side_effect=AssertionError("must not run seam")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(selection.main(["--base", "base", "--execute", "all"]), 1)

    def test_pr_tests_mode_emits_exact_seam_output_without_running_it(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output"
            with mock.patch.object(selection, "changed_paths", return_value=["scripts/ci/local_preflight.py"]), \
                    mock.patch.object(selection, "run_tests", return_value=0), \
                    mock.patch.object(selection.subprocess, "run", side_effect=AssertionError("must not run seam")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(selection.main(["--base", "base", "--execute", "tests",
                                                 "--github-output", str(output)]), 0)
            self.assertEqual(output.read_text(), "seam=false\n")


if __name__ == "__main__":
    unittest.main()
