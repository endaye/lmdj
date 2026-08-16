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
    # The four native Core lanes route by the literal `ci-core` role, so none
    # of them resolves a runner through a selector and none may require a
    # selector result: the Linux selector no longer exists as a job at all,
    # and a support job that cannot run would gate the Gate on a permanent
    # skip.
    "core_ubuntu": ["core-ubuntu"],
    "core_asan": ["core-asan"],
    "core_coverage": ["core-coverage"],
    "core_macos": ["select-macos-runner", "macos-primary", "core-macos", "core-asan-macos"],
    "web_toolchain": ["web-toolchain-conformance"],
    # Cut over to the static `ci-web-heavy` netcup role, so the lane resolves
    # no runner through a selector and must not require a selector result.
    "web_runtime_host": ["web-runtime-host"],
    "creator": ["creator-web"],
    "web_runtime_lab": ["web-runtime-lab"],
    "deploy_contract": ["deploy-contract"],
    "chameleon_lab": ["chameleon-lab"],
    "package": ["package"],
}

# The closed set of formal jobs that a self-hosted role may ever execute.
# Change Scope, PR Gate and the surviving macOS selector are the Hosted control
# plane, and the macOS lane keeps its own runner policy, so none of them appear
# here.
SELF_HOSTED_JOBS = [
    "docs-static",
    "portal",
    "ci-contract",
    "core-ubuntu",
    "core-asan",
    "core-coverage",
    "web-toolchain-conformance",
    "web-runtime-host",
    "creator-web",
    "web-runtime-lab",
    "deploy-contract",
    "chameleon-lab",
    "package",
]

CASES = {
    "docs/guide.md": {"docs_static"},
    "docs/governance/git-workflow.md": {"docs_static", "portal"},
    "apps/README.md": {"docs_static", "portal"},
    "apps/creator-web/README.md": {"docs_static", "portal", "creator"},
    "apps/web-runtime-host/src/main.mjs": {"portal", "web_runtime_host"},
    "apps/web-runtime-host/test/deploy_command_test.py": {
        "portal", "web_runtime_host", "deploy_contract"
    },
    "apps/web-runtime-host/tools/deploy_orchestrator.py": {
        "portal", "web_runtime_host", "deploy_contract"
    },
    "apps/web-runtime-host/tools/netlify_api.py": {
        "portal", "web_runtime_host", "deploy_contract"
    },
    "apps/web-runtime-host/tools/release_bundle.py": {
        "portal", "web_runtime_host", "deploy_contract"
    },
    "apps/chameleon-lab/src/main.js": {"portal", "chameleon_lab"},
    "tests/core/audio/render_test.cpp": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/core/facade/c_api_stress_test.cpp": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/core/support/test.hpp": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/core/provider/CMakeLists.txt": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/platform/web/creator/editor.spec.mjs": {"creator"},
    "tests/platform/web/audio/realtime_audio_worklet.spec.mjs": {
        "web_toolchain", "web_runtime_host"
    },
    "tests/platform/web/project_io/project_io_web_test.cpp": {"web_toolchain"},
    "tests/build/ci_runner_fallback_test.py": {"ci_contract"},
    "tests/build/web_runtime_public_deployment_docs_test.py": {"deploy_contract"},
    "tests/conformance/version_lock_test.py": {"core_ubuntu", "package"},
    "scripts/chameleon-lab.sh": {"chameleon_lab"},
    "scripts/core.sh": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos", "package"
    },
    "packages/web-runtime-platform/web/runtime_loader.mjs": {
        "portal", "web_toolchain", "web_runtime_host"
    },
    "packages/web-runtime-platform/test/runtime_loader.test.mjs": {
        "portal", "web_toolchain", "web_runtime_host"
    },
    "packages/web-runtime-platform/test/source_boundary_test.py": {
        "portal", "web_toolchain", "web_runtime_host"
    },
    "packages/web-runtime-platform/test/control_runtime_test.cpp": {
        "portal", "core_ubuntu", "core_asan", "core_coverage", "core_macos",
        "web_toolchain", "web_runtime_host"
    },
    "tools/web-runtime/verify_emscripten.py": {
        "web_toolchain", "web_runtime_host", "creator"
    },
    "tools/release/model.py": {"deploy_contract", "ci_contract"},
    "packaging/core/CMakeLists.txt": {"core_ubuntu", "package"},
    "netlify.toml": {"portal", "ci_contract"},
    "scripts/release.sh": {"deploy_contract", "ci_contract"},
    "docs/release-evidence/release-intents.json": {
        "docs_static", "deploy_contract", "ci_contract"
    },
    "tests/build/release_model_test.py": {"deploy_contract", "ci_contract"},
    ".github/workflows/publish-release.yml": {"deploy_contract", "ci_contract"},
    ".github/workflows/release-audit.yml": {"deploy_contract", "ci_contract"},
    ".github/actionlint.yaml": {"ci_contract"},
    ".github/actions/web-ci-proof/action.yml": set(LANES),
    ".github/workflows/ci-self-hosted-benchmark.yml": {"ci_contract"},
    ".gitattributes": set(LANES),
}

TOP_LEVELS = {
    ".claude", ".gitattributes", ".github", ".gitignore", "AGENTS.md",
    "CLAUDE.md", "CMakeLists.txt", "CMakePresets.json", "README.md", "apps",
    "cmake", "contracts", "docs", "netlify.toml", "output", "packages",
    "packaging", "products", "providers", "references", "scripts", "testdata",
    "tests", "third_party", "tools", "workers",
}

CONCURRENCY_STRESS_SOURCES = (
    "tests/core/project_io/storage_platform_contract_test.cpp",
    "tests/core/project_io/project_bundle_transfer_test.cpp",
    "tests/core/audio/fixed_spsc_queue_test.cpp",
    "tests/core/audio/realtime_engine_test.cpp",
    "tests/core/audio/realtime_engine_stress_test.cpp",
    "tests/core/facade/c_api_stress_test.cpp",
)


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


def policy_match(match, path):
    kind, value = match["kind"], match["value"]
    if kind == "exact":
        return path == value
    if kind == "prefix":
        return path.startswith(value)
    if kind == "suffix":
        return path.endswith(value)
    raise AssertionError(f"unknown policy match kind: {kind}")


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
            "trusted_head": True,
        }
        defaults.update(kwargs)
        return self.module.classify(self.policy, changed(self.module, *paths), **defaults)

    def true_lanes(self, manifest):
        return {name for name, selected in manifest["lanes"].items() if selected}

    def test_policy_has_exact_closed_lanes_and_all_current_top_levels(self):
        self.assertEqual(set(self.policy["lanes"]), LANES)
        self.assertEqual(self.policy["lane_jobs"], LANE_JOBS)
        self.assertEqual(set(self.policy["known_top_levels"]), TOP_LEVELS)
        self.assertNotIn("expensive_family_exemptions", self.policy)

    def test_manifest_v2_records_closed_trust(self):
        manifest = self.classify(["docs/guide.md"], trusted_head=True)
        self.assertEqual(manifest["schema"], "lmdj.ci-scope.v2")
        self.assertIs(manifest["trusted_head"], True)
        broken = dict(manifest)
        broken["trusted_head"] = "true"
        with self.assertRaisesRegex(ValueError, "trusted head"):
            self.module.validate_manifest(broken, self.policy)

    def test_untrusted_head_is_encoded_and_non_boolean_trust_is_rejected(self):
        manifest = self.classify(["docs/guide.md"], trusted_head=False)
        self.assertIs(manifest["trusted_head"], False)
        self.assertIn(
            '"trusted_head":false', self.module.encode_manifest(manifest)
        )
        for value in ("true", 1, 0, None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.classify(["docs/guide.md"], trusted_head=value)

    def test_trust_derives_only_from_the_event_and_head_repository(self):
        derive = self.module.derive_trusted_head
        for event in ("push", "workflow_dispatch"):
            with self.subTest(event=event):
                self.assertIs(derive(event, "", "owner/repo"), True)
        self.assertIs(derive("pull_request", "owner/repo", "owner/repo"), True)
        self.assertIs(derive("pull_request", "fork/repo", "owner/repo"), False)
        self.assertIs(derive("pull_request", "", "owner/repo"), False)

    def test_policy_declares_the_closed_self_hosted_job_set(self):
        self.assertEqual(self.policy["manifest_schema"], "lmdj.ci-scope.v2")
        self.assertEqual(self.policy["self_hosted_jobs"], SELF_HOSTED_JOBS)
        formal_jobs = {
            job for jobs in self.policy["lane_jobs"].values() for job in jobs
        }
        self.assertTrue(set(SELF_HOSTED_JOBS).issubset(formal_jobs))
        for job in ("select-macos-runner", "macos-primary", "core-macos",
                    "core-asan-macos"):
            with self.subTest(job=job):
                self.assertNotIn(job, SELF_HOSTED_JOBS)
        # The Linux runner selector is not merely outside the self-hosted set:
        # it is no longer a formal job, because no lane can resolve a runner
        # from an API snapshot that was able to buy paid Ubuntu.
        self.assertNotIn("select-ubuntu-runner", formal_jobs)
        self.assertNotIn("select-ubuntu-runner", SELF_HOSTED_JOBS)

    def test_policy_rejects_a_weakened_self_hosted_job_set(self):
        mutations = {
            "missing": lambda policy: policy["self_hosted_jobs"].remove("package"),
            "extra": lambda policy: policy["self_hosted_jobs"].append(
                "select-ubuntu-runner"
            ),
            "duplicate": lambda policy: policy["self_hosted_jobs"].append(
                "package"
            ),
            "non-formal": lambda policy: policy["self_hosted_jobs"].append(
                "invented-job"
            ),
            "removed": lambda policy: policy.pop("self_hosted_jobs"),
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
                        trusted_head=True,
                    )

    def test_every_tracked_path_has_explicit_ownership_or_full_rule(self):
        inventory = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        ).stdout
        paths = [item.decode("utf-8") for item in inventory.split(b"\0") if item]
        unmatched = [
            path for path in paths
            if not any(policy_match(rule["match"], path) for rule in self.policy["rules"])
            and not any(
                policy_match(rule["match"], path)
                for rule in self.policy["full_rules"]
            )
        ]
        self.assertEqual(unmatched, [], "unclassified tracked paths:\n" + "\n".join(unmatched))

    def test_policy_rejects_mutations_that_weaken_the_closed_v1_contract(self):
        mutations = {
            "lane removal": lambda policy: (
                policy["lanes"].remove("core_asan"),
                policy["lane_jobs"].pop("core_asan"),
            ),
            "support job replacement": lambda policy: policy["lane_jobs"].__setitem__(
                "core_asan", ["different-asan-job"]
            ),
            "retired selector reintroduction": lambda policy: policy[
                "lane_jobs"
            ].__setitem__("core_asan", ["select-ubuntu-runner", "core-asan"]),
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

    def test_all_six_current_concurrency_stress_sources_include_macos(self):
        self.assertEqual(len(CONCURRENCY_STRESS_SOURCES), 6)
        self.assertEqual(len(set(CONCURRENCY_STRESS_SOURCES)), 6)
        for path in CONCURRENCY_STRESS_SOURCES:
            with self.subTest(path=path):
                self.assertIn("core_macos", self.true_lanes(self.classify([path])))

    def test_focused_manifest_validation_recomputes_ready_path_union(self):
        manifest = self.classify([
            "tests/core/facade/application_test.cpp",
        ])
        manifest["lanes"] = {
            lane: lane == "docs_static" for lane in self.policy["lanes"]
        }
        manifest["required_jobs"] = ["docs-static"]

        with self.assertRaisesRegex(ValueError, "focused manifest"):
            self.module.validate_manifest(manifest, self.policy)

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
            ".github/actions/web-ci-proof/action.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.classify([path])["mode"], "full")

    def test_portal_workflow_rules_are_exact_and_similar_unknown_name_is_full(self):
        for path in (
            ".github/workflows/architecture-portal.yml",
            ".github/workflows/architecture-portal-smoke.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.true_lanes(self.classify([path])),
                    {"portal", "ci_contract"},
                )
        unknown = self.classify([
            ".github/workflows/architecture-portal-new-control.yml"
        ])
        self.assertEqual(unknown["mode"], "full")
        self.assertEqual(self.true_lanes(unknown), LANES)

    def test_release_workflow_rules_are_exact_and_signing_control_remains_full(self):
        for path in (
            ".github/workflows/publish-release.yml",
            ".github/workflows/release-audit.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.true_lanes(self.classify([path])),
                    {"deploy_contract", "ci_contract"},
                )
        self.assertEqual(
            self.classify([".github/release-signing-keys/release.asc"])["mode"],
            "full",
        )

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

    def test_dispatch_without_lanes_still_selects_every_lane(self):
        manifest = self.classify(
            ["docs/guide.md"], event_name="workflow_dispatch"
        )
        self.assertEqual(manifest["mode"], "full")
        self.assertEqual(self.true_lanes(manifest), set(self.policy["lanes"]))

    def test_dispatch_with_lanes_runs_exactly_those_lanes(self):
        manifest = self.classify(
            ["docs/guide.md"],
            event_name="workflow_dispatch",
            requested_lanes=["web_toolchain", "creator"],
        )
        self.assertEqual(manifest["mode"], "requested")
        self.assertEqual(self.true_lanes(manifest), {"web_toolchain", "creator"})
        self.assertEqual(
            manifest["required_jobs"], ["creator-web", "web-toolchain-conformance"]
        )
        self.assertTrue(
            any("requested lanes" in reason for reason in manifest["reasons"]),
            "a requested manifest must say the lanes were requested",
        )

    def test_requested_lanes_are_independent_of_the_changed_paths(self):
        # The point of the input is to verify a lane the diff does not select.
        manifest = self.classify(
            ["docs/guide.md"],
            event_name="workflow_dispatch",
            requested_lanes=["core_asan"],
        )
        self.assertEqual(self.true_lanes(manifest), {"core_asan"})

    def test_lane_selection_fails_closed(self):
        with self.subTest("unknown lane"):
            with self.assertRaises(ValueError):
                self.classify(
                    ["docs/guide.md"],
                    event_name="workflow_dispatch",
                    requested_lanes=["not_a_lane"],
                )
        with self.subTest("empty lane name"):
            with self.assertRaises(ValueError):
                self.classify(
                    ["docs/guide.md"],
                    event_name="workflow_dispatch",
                    requested_lanes=[" "],
                )
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                with self.assertRaises(ValueError):
                    self.classify(
                        ["docs/guide.md"],
                        event_name=event,
                        requested_lanes=["docs_static"],
                    )

    def test_requested_manifest_must_select_a_nonempty_lane_subset(self):
        manifest = self.classify(
            ["docs/guide.md"],
            event_name="workflow_dispatch",
            requested_lanes=["docs_static"],
        )
        broken = json.loads(json.dumps(manifest))
        broken["lanes"] = {lane: False for lane in broken["lanes"]}
        broken["required_jobs"] = []
        with self.assertRaises(ValueError):
            self.module.validate_manifest(broken, self.policy)

    def test_dispatch_lane_input_is_declared_and_threaded(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("      lanes:", workflow)
        self.assertIn("REQUESTED_LANES: ${{ inputs.lanes }}", workflow)
        self.assertIn('--lanes "${REQUESTED_LANES:-}"', workflow)

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

    def test_cli_publishes_the_trusted_head_output_and_summary_line(self):
        with TemporaryGitRepository() as repository:
            base = repository.write_and_commit("docs/guide.md", "one\n", "base")
            head = repository.write_and_commit("docs/guide.md", "two\n", "head")
            manifest = repository.path / "manifest.json"
            output = repository.path / "output"
            summary = repository.path / "summary.md"
            result = subprocess.run([
                sys.executable, str(CLASSIFIER_PATH), "--policy", str(POLICY_PATH),
                "--event", "push", "--base-sha", base, "--head-sha", head,
                "--repository", "owner/repo", "--head-repository", "",
                "--pr-number", "0", "--manifest-out", str(manifest),
                "--github-output", str(output), "--summary", str(summary),
            ], cwd=repository.path, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "trusted-head=true", output.read_text(encoding="utf-8")
            )
            self.assertIn(
                '"trusted_head":true', manifest.read_text(encoding="utf-8")
            )
            self.assertIn("| Trust |", summary.read_text(encoding="utf-8"))

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

    def test_summary_explains_focused_lane_paths_without_generic_reason(self):
        manifest = self.classify(["apps/web-runtime-host/src/main.mjs"])
        summary = self.module._summary(manifest, self.policy)
        self.assertIn("apps/web-runtime-host/src/main.mjs", summary)
        self.assertIn("added", summary)
        self.assertIn("web_runtime_host", summary)
        self.assertIn("prefix: apps/web-runtime-host/", summary)
        self.assertNotIn("path ownership", summary)

    def test_summary_explains_full_upgrade_for_every_lane(self):
        manifest = self.classify(["future-system/config.json"])
        summary = self.module._summary(manifest, self.policy)
        self.assertIn("unknown top-level: future-system", summary)
        for lane in LANES:
            with self.subTest(lane=lane):
                self.assertRegex(summary, rf"(?m)^- <code>{lane}</code>: .*unknown top-level")

    def test_summary_records_dispatch_lane_selection_reason(self):
        # Reproduces run 31902121850: a lane enabled only via the dispatch
        # --lanes input (no path in the diff matches its rules) must still
        # receive an auditable reason so the summary does not fail closed.
        manifest = self.classify(
            ["docs/guide.md"],
            event_name="workflow_dispatch",
            requested_lanes=["web_toolchain"],
        )
        summary = self.module._summary(manifest, self.policy)
        self.assertRegex(
            summary,
            r"(?m)^- <code>web_toolchain</code>: .*workflow_dispatch",
        )

    def test_summary_lists_both_rename_paths_and_all_lane_reasons(self):
        records = self.module.parse_name_status_z(
            b"R100\0apps/creator-web/src/old.ts\0apps/web-runtime-host/src/new.mjs\0"
        )
        manifest = self.module.classify(
            self.policy, records, base_sha="a" * 40, head_sha="b" * 40,
            event_name="pull_request", draft=False, labels=(),
        )
        summary = self.module._summary(manifest, self.policy)
        self.assertIn("renamed", summary)
        self.assertIn("apps/creator-web/src/old.ts", summary)
        self.assertIn("apps/web-runtime-host/src/new.mjs", summary)
        for lane in ("portal", "creator", "web_runtime_host"):
            self.assertRegex(summary, rf"(?m)^- <code>{lane}</code>:")

    def test_summary_escapes_untrusted_markdown_and_control_characters(self):
        path = "docs/<script>|`line\nfeed`[click](https:example.invalid).md"
        manifest = self.classify([path])
        summary = self.module._summary(manifest, self.policy)
        self.assertNotIn("<script>", summary)
        self.assertNotIn("|`line\nfeed`", summary)
        self.assertIn("&lt;script&gt;", summary)
        self.assertIn("&#124;", summary)
        self.assertIn("&#96;", summary)
        self.assertIn(r"\n", summary)
        self.assertRegex(summary, r"<code>path .*&#124;.* matched prefix:")


if __name__ == "__main__":
    unittest.main(verbosity=2)
