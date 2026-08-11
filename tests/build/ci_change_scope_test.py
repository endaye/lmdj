#!/usr/bin/env python3
"""Contract tests for the fail-closed Change Scope classifier.

The production change that makes these tests fail is an absent or permissive
scope-policy/classifier implementation.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "scripts/ci/scope_policy.json"
CLASSIFIER_PATH = ROOT / "scripts/ci/change_scope.py"

LANES = {
    "docs_static", "portal", "ci_contract", "core_ubuntu", "core_asan",
    "core_coverage", "core_macos", "web_toolchain", "web_runtime_host",
    "creator", "web_runtime_lab", "deploy_contract", "chameleon_lab",
    "package",
}

LANE_JOBS = {
    "docs_static": ["docs-static"],
    "portal": ["portal"],
    "ci_contract": ["ci-contract"],
    "core_ubuntu": ["select-ubuntu-runner", "core-ubuntu"],
    "core_asan": ["select-ubuntu-runner", "core-asan"],
    "core_coverage": ["select-ubuntu-runner", "core-coverage"],
    "core_macos": ["select-macos-runner", "macos-primary", "core-macos", "core-asan-macos"],
    "web_toolchain": ["web-toolchain-conformance"],
    "web_runtime_host": ["select-ubuntu-runner", "web-runtime-host"],
    "creator": ["creator-web"],
    "web_runtime_lab": ["select-ubuntu-runner", "web-runtime-lab"],
    "deploy_contract": ["deploy-contract"],
    "chameleon_lab": ["chameleon-lab"],
    "package": ["package"],
}

CASES = {
    "docs/guide.md": {"docs_static"},
    "docs/governance/git-workflow.md": {"docs_static", "portal"},
    "apps/creator-web/README.md": {"docs_static", "portal", "creator"},
    "apps/web-runtime-host/src/main.mjs": {"portal", "web_runtime_host"},
    "apps/chameleon-lab/src/main.js": {"portal", "chameleon_lab"},
    "tests/core/audio/render_test.cpp": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/platform/web/creator/editor.spec.mjs": {"creator"},
    "tests/build/ci_runner_fallback_test.py": {"ci_contract"},
    "tools/web-runtime/verify_emscripten.py": {
        "web_toolchain", "web_runtime_host", "creator"
    },
    "packaging/core/CMakeLists.txt": {"core_ubuntu", "package"},
    "netlify.toml": {"portal", "ci_contract"},
    ".gitattributes": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos",
        "web_runtime_host", "creator", "package", "ci_contract"
    },
}

TOP_LEVELS = {
    ".gitattributes", ".github", ".gitignore", "AGENTS.md", "CLAUDE.md",
    "CMakeLists.txt", "CMakePresets.json", "README.md", "apps", "cmake",
    "contracts", "docs", "netlify.toml", "output", "packages", "packaging",
    "products", "providers", "references", "scripts", "testdata", "tests",
    "tools", "workers",
}


def load_classifier():
    spec = importlib.util.spec_from_file_location("change_scope", CLASSIFIER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load change scope classifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def changed(module, *paths):
    return tuple(module.ChangedFile("A", (path,)) for path in paths)


class TemporaryGitRepository:
    def __enter__(self):
        self._directory = tempfile.TemporaryDirectory()
        self.path = Path(self._directory.name)
        self.run("git", "init", "--quiet")
        self.run("git", "config", "user.email", "ci@example.invalid")
        self.run("git", "config", "user.name", "CI Test")
        return self

    def __exit__(self, *_):
        self._directory.cleanup()

    def run(self, *args, check=True):
        return subprocess.run(
            args, cwd=self.path, check=check, text=True, capture_output=True
        )

    def write_and_commit(self, relative_path, contents, message):
        path = self.path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        self.run("git", "add", "--", relative_path)
        self.run("git", "commit", "--quiet", "-m", message)
        return self.run("git", "rev-parse", "HEAD").stdout.strip()


class ChangeScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with POLICY_PATH.open(encoding="utf-8") as policy_file:
            cls.policy = json.load(policy_file)
        cls.module = load_classifier()

    def classify(self, paths, **kwargs):
        defaults = {
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "event_name": "pull_request",
            "draft": False,
            "labels": (),
        }
        defaults.update(kwargs)
        return self.module.classify(self.policy, changed(self.module, *paths), **defaults)

    def true_lanes(self, manifest):
        return {name for name, selected in manifest["lanes"].items() if selected}

    def test_policy_has_exact_closed_lanes_and_all_current_top_levels(self):
        self.assertEqual(set(self.policy["lanes"]), LANES)
        self.assertEqual(self.policy["lane_jobs"], LANE_JOBS)
        self.assertEqual(set(self.policy["known_top_levels"]), TOP_LEVELS)

    def test_policy_rejects_mutations_that_weaken_the_closed_v1_contract(self):
        mutations = {
            "lane removal": lambda policy: (
                policy["lanes"].remove("core_asan"),
                policy["lane_jobs"].pop("core_asan"),
            ),
            "support job replacement": lambda policy: policy["lane_jobs"].__setitem__(
                "core_asan", ["select-ubuntu-runner", "different-asan-job"]
            ),
            "central control rule removal": lambda policy: policy.__setitem__(
                "full_rules", [
                    rule for rule in policy["full_rules"]
                    if rule["match"] != {"kind": "prefix", "value": "scripts/ci/"}
                ]
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                policy = copy.deepcopy(self.policy)
                mutate(policy)
                with self.assertRaises(ValueError):
                    self.module.classify(
                        policy, changed(self.module, "docs/guide.md"),
                        base_sha="a" * 40, head_sha="b" * 40,
                        event_name="pull_request", draft=False, labels=(),
                    )

    def test_every_case_uses_union_semantics(self):
        for path, expected in CASES.items():
            with self.subTest(path=path):
                self.assertEqual(self.true_lanes(self.classify([path])), expected)

    def test_rename_classifies_old_and_new_paths(self):
        records = self.module.parse_name_status_z(
            b"R100\0apps/creator-web/src/editor.ts\0apps/web-runtime-host/src/main.mjs\0"
        )
        manifest = self.module.classify(
            self.policy, records, base_sha="a" * 40, head_sha="b" * 40,
            event_name="pull_request", draft=False, labels=(),
        )
        self.assertEqual(
            self.true_lanes(manifest), {"portal", "creator", "web_runtime_host"}
        )

    def test_deleted_known_path_keeps_its_consumers(self):
        records = self.module.parse_name_status_z(
            b"D\0apps/web-runtime-host/src/main.mjs\0"
        )
        self.assertIn("web_runtime_host", self.true_lanes(self.module.classify(
            self.policy, records, base_sha="a" * 40, head_sha="b" * 40,
            event_name="pull_request", draft=False, labels=(),
        )))

    def test_unknown_top_level_upgrades_to_full(self):
        manifest = self.classify(["future-system/config.json"])
        self.assertEqual(manifest["mode"], "full")
        self.assertEqual(self.true_lanes(manifest), LANES)
        self.assertTrue(any("unknown top-level" in reason for reason in manifest["reasons"]))

    def test_central_ci_files_upgrade_to_full(self):
        for path in (
            ".github/workflows/ci.yml", "scripts/ci/change_scope.py",
            "scripts/ci/pr_gate.py", "scripts/ci/scope_policy.json",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.classify([path])["mode"], "full")

    def test_three_expensive_families_upgrade_to_full_but_docs_portal_do_not_count(self):
        full = self.classify([
            "tests/core/render_test.cpp", "apps/web-runtime-host/src/main.mjs",
            "apps/creator-web/src/editor.ts",
        ])
        focused = self.classify([
            "docs/guide.md", "apps/architecture-portal/src/main.js",
            "apps/web-runtime-host/src/main.mjs",
        ])
        self.assertEqual(full["mode"], "full")
        self.assertEqual(focused["mode"], "focused")

    def test_ci_full_upgrades_ready_pr_to_full(self):
        plain = self.classify(["docs/guide.md"])
        labeled = self.classify(["docs/guide.md"], labels={"ci:full"})
        self.assertEqual(plain["mode"], "focused")
        self.assertEqual(labeled["mode"], "full")

    def test_main_and_dispatch_are_full(self):
        for event_name in ("push", "workflow_dispatch"):
            with self.subTest(event_name=event_name):
                manifest = self.classify(["docs/guide.md"], event_name=event_name)
                self.assertEqual(manifest["mode"], "full")
                self.assertEqual(self.true_lanes(manifest), LANES)

    def test_draft_emits_only_docs_static_and_ci_contract_evidence(self):
        manifest = self.classify(["tests/core/render_test.cpp"], draft=True)
        self.assertEqual(manifest["mode"], "draft")
        self.assertEqual(self.true_lanes(manifest), {"docs_static", "ci_contract"})
        self.assertTrue(any("deferred" in reason for reason in manifest["reasons"]))

    def test_invalid_sha_noncanonical_path_duplicate_path_and_unknown_status_fail(self):
        with self.subTest("invalid sha"):
            with self.assertRaises(ValueError):
                self.classify(["docs/guide.md"], base_sha="short")
        with self.subTest("noncanonical path"):
            with self.assertRaises(ValueError):
                self.module.parse_name_status_z(b"A\0docs//guide.md\0")
        with self.subTest("duplicate path"):
            with self.assertRaises(ValueError):
                self.module.parse_name_status_z(b"A\0docs/guide.md\0M\0docs/guide.md\0")
        with self.subTest("unknown status"):
            with self.assertRaises(ValueError):
                self.module.parse_name_status_z(b"X\0docs/guide.md\0")
        with self.subTest("malformed rename record"):
            with self.assertRaises(ValueError):
                self.module.classify(
                    self.policy, (self.module.ChangedFile(
                        "Rxyz", ("apps/creator-web/old.js", "apps/web-runtime-host/new.mjs")
                    ),), base_sha="a" * 40, head_sha="b" * 40,
                    event_name="pull_request", draft=False, labels=(),
                )
        with self.subTest("malformed modified record"):
            with self.assertRaises(ValueError):
                self.module.classify(
                    self.policy, (self.module.ChangedFile("M100", ("docs/guide.md",)),),
                    base_sha="a" * 40, head_sha="b" * 40,
                    event_name="pull_request", draft=False, labels=(),
                )

    def test_git_inventory_uses_complete_base_to_head_range_not_last_commit(self):
        with TemporaryGitRepository() as repository:
            base = repository.write_and_commit("docs/guide.md", "one\n", "base")
            repository.write_and_commit("apps/creator-web/src/editor.ts", "one\n", "creator")
            head = repository.write_and_commit("tests/core/render_test.cpp", "one\n", "core")
            records = self.module.read_git_inventory(str(repository.path), base, head)
            all_paths = {path for record in records for path in record.paths}
            self.assertEqual(
                all_paths,
                {"apps/creator-web/src/editor.ts", "tests/core/render_test.cpp"},
            )

    def test_name_status_parser_handles_add_modify_delete_and_rename_nul_records(self):
        records = self.module.parse_name_status_z(
            b"A\0docs/new.md\0M\0docs/old.md\0D\0docs/gone.md\0"
            b"R100\0apps/creator-web/old.js\0apps/web-runtime-host/new.mjs\0"
        )
        self.assertEqual(records, (
            self.module.ChangedFile("A", ("docs/new.md",)),
            self.module.ChangedFile("M", ("docs/old.md",)),
            self.module.ChangedFile("D", ("docs/gone.md",)),
            self.module.ChangedFile("R100", (
                "apps/creator-web/old.js", "apps/web-runtime-host/new.mjs"
            )),
        ))

    def test_missing_git_object_or_failed_diff_is_a_hard_error(self):
        with TemporaryGitRepository() as repository:
            base = repository.write_and_commit("docs/guide.md", "one\n", "base")
            head = repository.write_and_commit("docs/guide.md", "two\n", "head")
            def invoke(manifest, base_sha, environment=None):
                return subprocess.run([
                    sys.executable, str(CLASSIFIER_PATH), "--policy", str(POLICY_PATH),
                    "--event", "push", "--base-sha", base_sha, "--head-sha", head,
                    "--repository", "owner/repo", "--pr-number", "1", "--manifest-out",
                    str(manifest), "--github-output", str(repository.path / "output"),
                    "--summary", str(repository.path / "summary.md"),
                ], cwd=repository.path, capture_output=True, text=True, env=environment)

            with self.subTest("missing object"):
                manifest = repository.path / "missing-object.json"
                result = invoke(manifest, "0" * 40)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(manifest.exists())
            with self.subTest("failed diff"):
                manifest = repository.path / "failed-diff.json"
                fake_bin = repository.path / "fake-bin"
                fake_bin.mkdir()
                fake_git = fake_bin / "git"
                fake_git.write_text(
                    "#!/bin/sh\n"
                    "if [ \"$1\" = \"cat-file\" ]; then exit 0; fi\n"
                    "if [ \"$1\" = \"diff\" ]; then exit 9; fi\n"
                    "exit 7\n",
                    encoding="utf-8",
                )
                fake_git.chmod(0o755)
                environment = dict(os.environ, PATH=str(fake_bin))
                result = invoke(manifest, base, environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(manifest.exists())

    def test_manifest_is_compact_deterministic_and_schema_closed(self):
        first = self.classify(["docs/guide.md"])
        second = self.classify(["docs/guide.md"])
        first_json = self.module.encode_manifest(first)
        self.assertEqual(first_json, self.module.encode_manifest(second))
        self.assertNotIn("\n", first_json)
        invalid = dict(first)
        invalid["injected"] = True
        with self.assertRaises(ValueError):
            self.module.encode_manifest(invalid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
