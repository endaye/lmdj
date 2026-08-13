#!/usr/bin/env python3
"""Contract tests for the advisory local CI pre-flight.

The production change that makes these tests fail is a pre-flight that
selects a different lane set than CI, reports a pass for a lane it did not
actually run, or serves a cached pass after an input changed.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "scripts/ci/scope_policy.json"
CLASSIFIER_PATH = ROOT / "scripts/ci/change_scope.py"
PREFLIGHT_PATH = ROOT / "scripts/ci/local_preflight.py"
LANE_COMMANDS_PATH = ROOT / "scripts/ci/local_lanes.json"
ENTRY_POINT_PATH = ROOT / "scripts/local-ci.sh"
WORKFLOW_PATH = ROOT / ".github/workflows/ci.yml"

PYTHON_TEST_FILE = re.compile(r"[\w./-]*[\w-]+_test\.py")

LANES = {
    "docs_static", "portal", "ci_contract", "core_ubuntu", "core_asan",
    "core_coverage", "core_macos", "web_toolchain", "web_runtime_host",
    "creator", "web_runtime_lab", "deploy_contract", "chameleon_lab",
    "package",
}

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Pre-flight Test",
    "GIT_AUTHOR_EMAIL": "preflight@example.invalid",
    "GIT_COMMITTER_NAME": "Pre-flight Test",
    "GIT_COMMITTER_EMAIL": "preflight@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def workflow_job(name: str) -> str:
    """Return the body of one job in the real CI workflow."""
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    match = re.search(
        rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:|\Z)",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"workflow job is missing: {name}")
    return match.group("body")


def python_test_files(text: str) -> set[str]:
    """Return every Python test file path an invocation text names."""
    return set(PYTHON_TEST_FILE.findall(text))


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, check=True,
        env={**os.environ, **GIT_ENV},
    )
    return result.stdout.decode()


class TemporaryRepository:
    """A throwaway Git repository whose diffs feed the real scope policy."""

    def __init__(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.path = Path(self._directory.name)
        git(self.path, "init", "-q", "-b", "main")
        self.write("README.md", "baseline\n")
        git(self.path, "add", "-A")
        git(self.path, "commit", "-qm", "baseline")
        self.base_sha = git(self.path, "rev-parse", "HEAD").strip()

    def write(self, relative: str, contents: str) -> None:
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")

    def commit(self, message: str) -> None:
        git(self.path, "add", "-A")
        git(self.path, "commit", "-qm", message)

    def close(self) -> None:
        self._directory.cleanup()


class LaneTableContractTest(unittest.TestCase):
    """The local command table must stay aligned with the CI policy."""

    def setUp(self) -> None:
        self.classifier = load_module("change_scope_under_test", CLASSIFIER_PATH)
        self.preflight = load_module("local_preflight_under_test", PREFLIGHT_PATH)
        self.policy = self.classifier.load_policy(POLICY_PATH)

    def test_table_covers_exactly_the_canonical_lanes(self) -> None:
        lanes = self.preflight.load_lane_commands(policy=self.policy)
        self.assertEqual(set(lanes), LANES)
        self.assertEqual(set(lanes), set(self.policy["lanes"]))

    def test_table_rejects_a_lane_the_policy_does_not_declare(self) -> None:
        table = json.loads(LANE_COMMANDS_PATH.read_text(encoding="utf-8"))
        table["lanes"]["invented_lane"] = {
            "requires": {}, "commands": ["true"], "ci_only": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_lanes.json"
            path.write_text(json.dumps(table), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.preflight.load_lane_commands(path, policy=self.policy)

    def test_table_rejects_a_missing_lane(self) -> None:
        table = json.loads(LANE_COMMANDS_PATH.read_text(encoding="utf-8"))
        table["lanes"].pop("package")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_lanes.json"
            path.write_text(json.dumps(table), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.preflight.load_lane_commands(path, policy=self.policy)

    def test_lane_entry_schema_is_closed(self) -> None:
        table = json.loads(LANE_COMMANDS_PATH.read_text(encoding="utf-8"))
        table["lanes"]["docs_static"]["surprise"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_lanes.json"
            path.write_text(json.dumps(table), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.preflight.load_lane_commands(path, policy=self.policy)

    def test_every_lane_declares_commands_and_records_ci_only_steps(self) -> None:
        lanes = self.preflight.load_lane_commands(policy=self.policy)
        for lane, entry in lanes.items():
            with self.subTest(lane=lane):
                self.assertTrue(entry["commands"])
                self.assertIsInstance(entry["ci_only"], list)

    def test_platform_bound_lanes_declare_their_operating_system(self) -> None:
        lanes = self.preflight.load_lane_commands(policy=self.policy)
        self.assertEqual(lanes["core_macos"]["requires"]["os"], ["darwin"])
        for lane in ("core_ubuntu", "core_asan", "core_coverage"):
            with self.subTest(lane=lane):
                self.assertEqual(lanes[lane]["requires"]["os"], ["linux"])

    def test_classifier_exposes_the_matcher_the_preflight_reuses(self) -> None:
        self.assertTrue(hasattr(self.classifier, "_matches"))
        self.assertTrue(
            self.classifier._matches({"kind": "prefix", "value": "docs/"}, "docs/a.md")
        )


class LaneCommandDriftTest(unittest.TestCase):
    """Lane-key equality is not enough: the commands must not drift either.

    A suite that moves between lanes changes what a job runs. Without this
    contract the local table keeps the old composition and reports a pass for
    a lane it no longer reproduces.
    """

    def setUp(self) -> None:
        self.classifier = load_module("change_scope_drift", CLASSIFIER_PATH)
        self.preflight = load_module("local_preflight_drift", PREFLIGHT_PATH)
        self.policy = self.classifier.load_policy(POLICY_PATH)

    def local_test_files(self, lane: str, table=None) -> set[str]:
        if table is None:
            table = self.preflight.load_lane_commands(policy=self.policy)
        return python_test_files(" ".join(table[lane]["commands"]))

    def test_deploy_contract_job_runs_the_deploy_command_suite(self) -> None:
        workflow_tests = python_test_files(workflow_job("deploy-contract"))
        self.assertIn(
            "apps/web-runtime-host/test/deploy_command_test.py", workflow_tests
        )

    def test_deploy_contract_local_commands_cover_the_workflow_job(self) -> None:
        workflow_tests = python_test_files(workflow_job("deploy-contract"))
        self.assertTrue(workflow_tests, "deploy-contract runs no Python test file")
        self.assertEqual(self.local_test_files("deploy_contract"), workflow_tests)

    def test_a_dropped_local_command_stops_covering_the_workflow_job(self) -> None:
        table = json.loads(LANE_COMMANDS_PATH.read_text(encoding="utf-8"))["lanes"]
        entry = table["deploy_contract"]
        entry["commands"] = [
            command for command in entry["commands"]
            if "deploy_command_test.py" not in command
        ]
        self.assertNotEqual(
            self.local_test_files("deploy_contract", table),
            python_test_files(workflow_job("deploy-contract")),
        )

    def test_the_deploy_suite_belongs_to_the_lane_that_owns_its_subject(self) -> None:
        for path in (
            "apps/web-runtime-host/test/deploy_command_test.py",
            "apps/web-runtime-host/tools/deploy_orchestrator.py",
            "apps/web-runtime-host/tools/netlify_api.py",
            "apps/web-runtime-host/tools/release_bundle.py",
            "scripts/web-runtime-deploy.sh",
        ):
            with self.subTest(path=path):
                lanes, _ = self.classifier._evaluate_ready_paths(self.policy, [path])
                self.assertIn("deploy_contract", lanes)


class ScopePolicyEntryPointTest(unittest.TestCase):
    """The pre-flight's own files must not silently force full mode."""

    def setUp(self) -> None:
        self.classifier = load_module("change_scope_entry_point", CLASSIFIER_PATH)
        self.policy = self.classifier.load_policy(POLICY_PATH)

    def _lanes_for(self, path: str) -> tuple[set[str], set[str]]:
        return self.classifier._evaluate_ready_paths(self.policy, [path])

    def test_entry_point_is_classified_rather_than_unclassified(self) -> None:
        lanes, reasons = self._lanes_for("scripts/local-ci.sh")
        self.assertEqual(lanes, {"ci_contract"})
        self.assertEqual(reasons, set())

    def test_preflight_control_plane_files_still_force_full(self) -> None:
        for path in (
            "scripts/ci/local_preflight.py", "scripts/ci/local_lanes.json",
        ):
            with self.subTest(path=path):
                _, reasons = self._lanes_for(path)
                self.assertTrue(
                    any("central CI control plane" in reason for reason in reasons),
                    reasons,
                )

    def test_the_contract_test_belongs_to_the_ci_lane(self) -> None:
        lanes, reasons = self._lanes_for("tests/build/ci_local_preflight_test.py")
        self.assertEqual(lanes, {"ci_contract"})
        self.assertEqual(reasons, set())


class ManifestReuseTest(unittest.TestCase):
    """Lane selection must come from the classifier, not a second opinion."""

    def setUp(self) -> None:
        self.preflight = load_module("local_preflight_manifest", PREFLIGHT_PATH)
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.close)

    def plan(self, **kwargs):
        return self.preflight.build_plan(
            self.repository.path, self.repository.base_sha, **kwargs
        )

    def test_documentation_only_change_selects_only_the_docs_lane(self) -> None:
        self.repository.write("docs/guide.md", "text\n")
        self.repository.commit("docs")
        plan = self.plan()
        self.assertEqual(plan["mode"], "focused")
        self.assertEqual(plan["selected"], ["docs_static"])

    def test_core_module_change_selects_every_core_lane(self) -> None:
        self.repository.write("packages/foundation/src/thing.cpp", "int a = 1;\n")
        self.repository.commit("core")
        plan = self.plan()
        self.assertEqual(
            set(plan["selected"]),
            {"portal", "core_ubuntu", "core_asan", "core_coverage", "core_macos"},
        )

    def test_uncommitted_edits_are_classified_like_committed_ones(self) -> None:
        self.repository.write("docs/guide.md", "text\n")
        self.assertEqual(self.plan()["selected"], ["docs_static"])

    def test_untracked_new_file_is_not_silently_ignored(self) -> None:
        self.repository.write("apps/chameleon-lab/src/main.js", "// new\n")
        plan = self.plan()
        self.assertEqual(set(plan["selected"]), {"portal", "chameleon_lab"})

    def test_control_plane_change_upgrades_to_full_mode(self) -> None:
        self.repository.write(".github/workflows/ci.yml", "name: CI\n")
        self.repository.commit("workflow")
        plan = self.plan()
        self.assertEqual(plan["mode"], "full")
        self.assertEqual(set(plan["selected"]), LANES)

    def test_lane_restriction_narrows_without_inventing_lanes(self) -> None:
        self.repository.write("packages/foundation/src/thing.cpp", "int a = 1;\n")
        self.repository.commit("core")
        self.assertEqual(self.plan(only=["core_asan"])["selected"], ["core_asan"])
        with self.assertRaises(ValueError):
            self.plan(only=["not_a_lane"])


class CacheKeyTest(unittest.TestCase):
    """A cached pass must not survive a change to anything the lane reads."""

    def setUp(self) -> None:
        self.classifier = load_module("change_scope_cache", CLASSIFIER_PATH)
        self.preflight = load_module("local_preflight_cache", PREFLIGHT_PATH)
        self.policy = self.classifier.load_policy(POLICY_PATH)

    def key(self, blobs, inputs=("packages/foundation/src/a.cpp",)):
        return self.preflight.lane_cache_key(
            "core_ubuntu", ["scripts/core.sh proof"], list(inputs), blobs
        )

    def test_identical_inputs_produce_an_identical_key(self) -> None:
        blobs = {"packages/foundation/src/a.cpp": "a" * 40}
        self.assertEqual(self.key(blobs), self.key(dict(blobs)))

    def test_changed_input_content_invalidates_the_key(self) -> None:
        before = self.key({"packages/foundation/src/a.cpp": "a" * 40})
        after = self.key({"packages/foundation/src/a.cpp": "b" * 40})
        self.assertNotEqual(before, after)

    def test_deleted_input_invalidates_the_key(self) -> None:
        before = self.key({"packages/foundation/src/a.cpp": "a" * 40})
        self.assertNotEqual(before, self.key({}))

    def test_unrelated_path_does_not_invalidate_the_key(self) -> None:
        blobs = {"packages/foundation/src/a.cpp": "a" * 40}
        noisy = {**blobs, "docs/unrelated.md": "c" * 40}
        self.assertEqual(self.key(blobs), self.key(noisy))

    def test_changing_a_lane_command_invalidates_the_key(self) -> None:
        blobs = {"packages/foundation/src/a.cpp": "a" * 40}
        other = self.preflight.lane_cache_key(
            "core_ubuntu", ["scripts/core.sh proof --extra"],
            ["packages/foundation/src/a.cpp"], blobs,
        )
        self.assertNotEqual(self.key(blobs), other)

    def test_shared_and_unclassified_paths_are_inputs_to_every_lane(self) -> None:
        grouped = self.preflight.lane_input_paths(
            self.policy,
            [
                "cmake/LmdjDependencies.cmake", "docs/guide.md",
                "packages/foundation/src/a.cpp",
            ],
            self.classifier,
        )
        for lane in self.policy["lanes"]:
            with self.subTest(lane=lane):
                self.assertIn("cmake/LmdjDependencies.cmake", grouped[lane])
        self.assertNotIn("docs/guide.md", grouped["core_asan"])
        self.assertIn("docs/guide.md", grouped["docs_static"])

    def test_cache_round_trip_only_accepts_a_recorded_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            self.assertFalse(
                self.preflight.has_cached_pass(cache, "docs_static", "abc")
            )
            self.preflight.write_cached_pass(cache, "docs_static", "abc")
            self.assertTrue(
                self.preflight.has_cached_pass(cache, "docs_static", "abc")
            )
            self.assertFalse(
                self.preflight.has_cached_pass(cache, "docs_static", "other")
            )
            (cache / "docs_static.json").write_text("{}", encoding="utf-8")
            self.assertFalse(
                self.preflight.has_cached_pass(cache, "docs_static", "abc")
            )

    def test_cache_remembers_an_earlier_state_after_a_revert(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            self.preflight.write_cached_pass(cache, "core_ubuntu", "before")
            self.preflight.write_cached_pass(cache, "core_ubuntu", "edited")
            self.assertTrue(
                self.preflight.has_cached_pass(cache, "core_ubuntu", "before")
            )
            self.assertTrue(
                self.preflight.has_cached_pass(cache, "core_ubuntu", "edited")
            )

    def test_cache_retention_is_bounded_and_evicts_the_oldest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            for index in range(5):
                self.preflight.write_cached_pass(
                    cache, "core_ubuntu", f"key-{index}", retain=3
                )
            recorded = [
                item["key"]
                for item in self.preflight.read_cached_keys(cache, "core_ubuntu")
            ]
            self.assertEqual(recorded, ["key-4", "key-3", "key-2"])

    def test_rewriting_the_same_key_does_not_duplicate_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            self.preflight.write_cached_pass(cache, "core_ubuntu", "same")
            self.preflight.write_cached_pass(cache, "core_ubuntu", "same")
            self.assertEqual(
                len(self.preflight.read_cached_keys(cache, "core_ubuntu")), 1
            )


class RequirementHonestyTest(unittest.TestCase):
    """A lane this machine cannot run must never be reported as passing."""

    def setUp(self) -> None:
        self.preflight = load_module("local_preflight_requirements", PREFLIGHT_PATH)
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.close)

    def test_operating_system_mismatch_is_not_runnable(self) -> None:
        impossible = "darwin" if sys.platform.startswith("linux") else "linux"
        runnable, reason = self.preflight.check_requirements(
            self.repository.path, {"os": [impossible]}
        )
        self.assertFalse(runnable)
        self.assertIn(impossible, reason)

    def test_missing_command_is_not_runnable(self) -> None:
        runnable, reason = self.preflight.check_requirements(
            self.repository.path, {"commands": ["lmdj-no-such-command"]}
        )
        self.assertFalse(runnable)
        self.assertIn("lmdj-no-such-command", reason)

    def test_any_of_accepts_either_a_path_or_an_environment_variable(self) -> None:
        requires = {"any_of": [{"path": "build/present"}, {"env": "LMDJ_TEST_ENV"}]}
        runnable, _ = self.preflight.check_requirements(
            self.repository.path, copy.deepcopy(requires)
        )
        self.assertFalse(runnable)

        self.repository.write("build/present", "here\n")
        runnable, _ = self.preflight.check_requirements(
            self.repository.path, copy.deepcopy(requires)
        )
        self.assertTrue(runnable)

        (self.repository.path / "build/present").unlink()
        os.environ["LMDJ_TEST_ENV"] = "1"
        self.addCleanup(os.environ.pop, "LMDJ_TEST_ENV", None)
        runnable, _ = self.preflight.check_requirements(
            self.repository.path, copy.deepcopy(requires)
        )
        self.assertTrue(runnable)

    def test_clean_worktree_requirement_sees_uncommitted_edits(self) -> None:
        runnable, _ = self.preflight.check_requirements(
            self.repository.path, {"clean_worktree": True}
        )
        self.assertTrue(runnable)
        self.repository.write("dirty.txt", "x\n")
        runnable, reason = self.preflight.check_requirements(
            self.repository.path, {"clean_worktree": True}
        )
        self.assertFalse(runnable)
        self.assertIn("clean working tree", reason)

    def test_unrunnable_lane_reports_not_runnable_and_writes_no_cache(self) -> None:
        impossible = "darwin" if sys.platform.startswith("linux") else "linux"
        plan = {
            "base_sha": self.repository.base_sha,
            "head_sha": self.repository.base_sha,
            "selected": ["core_macos"],
            "cache_keys": {"core_macos": "key"},
            "lane_commands": {
                "core_macos": {
                    "requires": {"os": [impossible]},
                    "commands": ["exit 1"],
                    "ci_only": [],
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            results = self.preflight.execute(
                self.repository.path, plan, cache_dir=cache, use_cache=True,
                echo=False,
            )
            self.assertEqual([result.verdict for result in results],
                             [self.preflight.NOT_RUNNABLE])
            self.assertEqual(
                self.preflight.read_cached_keys(cache, "core_macos"), []
            )


class ExecutionTest(unittest.TestCase):
    """Verdicts, caching and exit semantics of an actual lane run."""

    def setUp(self) -> None:
        self.preflight = load_module("local_preflight_execution", PREFLIGHT_PATH)
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.close)

    def plan(self, commands):
        return {
            "base_sha": self.repository.base_sha,
            "head_sha": self.repository.base_sha,
            "selected": ["docs_static"],
            "cache_keys": {"docs_static": "stable-key"},
            "lane_commands": {
                "docs_static": {
                    "requires": {}, "commands": commands, "ci_only": [],
                }
            },
        }

    def test_second_run_with_unchanged_inputs_is_served_from_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            first = self.preflight.execute(
                self.repository.path, self.plan(["true"]), cache_dir=cache,
                use_cache=True, echo=False,
            )
            self.assertEqual(first[0].verdict, self.preflight.PASS)
            second = self.preflight.execute(
                self.repository.path, self.plan(["true"]), cache_dir=cache,
                use_cache=True, echo=False,
            )
            self.assertEqual(second[0].verdict, self.preflight.CACHED_PASS)

    def test_no_cache_reruns_a_previously_passing_lane(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            self.preflight.execute(
                self.repository.path, self.plan(["true"]), cache_dir=cache,
                use_cache=True, echo=False,
            )
            rerun = self.preflight.execute(
                self.repository.path, self.plan(["true"]), cache_dir=cache,
                use_cache=False, echo=False,
            )
            self.assertEqual(rerun[0].verdict, self.preflight.PASS)

    def test_failure_is_reported_and_never_cached(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            results = self.preflight.execute(
                self.repository.path, self.plan(["exit 3"]), cache_dir=cache,
                use_cache=True, echo=False,
            )
            self.assertEqual(results[0].verdict, self.preflight.FAIL)
            self.assertIn("exited 3", results[0].detail)
            self.assertEqual(
                self.preflight.read_cached_keys(cache, "docs_static"), []
            )

    def test_a_lane_stops_at_its_first_failing_command(self) -> None:
        marker = self.repository.path / "second-ran"
        with tempfile.TemporaryDirectory() as directory:
            self.preflight.execute(
                self.repository.path,
                self.plan(["exit 1", f"touch {marker}"]),
                cache_dir=Path(directory), use_cache=True, echo=False,
            )
        self.assertFalse(marker.exists())

    def test_base_and_head_placeholders_are_substituted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            results = self.preflight.execute(
                self.repository.path,
                self.plan([f"test {{base}} = {self.repository.base_sha}"]),
                cache_dir=Path(directory), use_cache=True, echo=False,
            )
            self.assertEqual(results[0].verdict, self.preflight.PASS)


class AdvisoryBoundaryTest(unittest.TestCase):
    """The pre-flight must present itself as advisory, never as evidence."""

    def setUp(self) -> None:
        self.preflight = load_module("local_preflight_boundary", PREFLIGHT_PATH)

    def test_hook_template_runs_the_entry_point_and_documents_the_bypass(self) -> None:
        template = self.preflight.HOOK_TEMPLATE
        self.assertIn("scripts/local-ci.sh", template)
        self.assertIn("--no-verify", template)
        self.assertIn("advisory", template)

    def test_entry_point_exists_and_is_executable(self) -> None:
        self.assertTrue(ENTRY_POINT_PATH.is_file())
        self.assertTrue(os.access(ENTRY_POINT_PATH, os.X_OK))

    def test_entry_point_states_it_authorizes_no_state_transition(self) -> None:
        text = ENTRY_POINT_PATH.read_text(encoding="utf-8")
        self.assertIn("PR Gate", text)
        self.assertIn("authorizes no push", text)

    def test_hook_installation_refuses_to_clobber_a_foreign_hook(self) -> None:
        repository = TemporaryRepository()
        self.addCleanup(repository.close)
        hook = self.preflight.install_hook(repository.path)
        self.assertTrue(os.access(hook, os.X_OK))
        hook.write_text("#!/bin/sh\necho someone else's hook\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.preflight.install_hook(repository.path)
        self.assertEqual(
            self.preflight.install_hook(repository.path, force=True).read_text(
                encoding="utf-8"
            ),
            self.preflight.HOOK_TEMPLATE,
        )

    def test_module_documents_that_it_is_not_evidence(self) -> None:
        documentation = " ".join((self.preflight.__doc__ or "").split())
        self.assertIn("It is not evidence.", documentation)
        self.assertIn("authorizes no push", documentation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
