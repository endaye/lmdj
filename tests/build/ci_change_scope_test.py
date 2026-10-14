#!/usr/bin/env python3
"""Contract tests for the fail-closed Change Scope classifier.

The production change that makes these tests fail is an absent or permissive
scope-policy/classifier implementation.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import re
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import fnmatch


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "scripts/ci/scope_policy.json"
CLASSIFIER_PATH = ROOT / "scripts/ci/change_scope.py"

LANES = {
    "docs_static", "portal", "ci_contract", "core_ubuntu", "core_asan",
    "core_coverage", "core_macos", "web_toolchain", "web_runtime_host",
    "creator", "web_runtime_lab", "deploy_contract",
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
    "package": ["package"],
}

# The closed set of formal workload jobs that a self-hosted role may execute.
# Change Scope, the aggregate verdict and the surviving macOS selector are
# control-plane jobs on shared ci-general capacity, while the macOS lane keeps
# its own runner policy, so none of them appear here.
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
    "package",
]

CASES = {
    "demos/README.md": {"docs_static", "web_runtime_lab"},
    "demos/protocol-proof/main.cpp": {"docs_static"},
    "demos/lmdj-song-pipeline/song_pipeline/cli.py": {"docs_static"},
    "demos/ascii-matrix-camera/index.html": {"docs_static"},
    ".github/ISSUE_TEMPLATE/feature.yml": {"docs_static", "ci_contract"},
    "docs/guide.md": {"docs_static"},
    # release_skill_test.py asserts on this page, so the release-facing
    # lanes that hold it must run when it changes.
    "docs/governance/git-workflow.md": {
        "docs_static", "portal", "ci_contract", "deploy_contract"
    },
    "docs/governance/github-work-management.md": {
        "docs_static", "portal", "ci_contract"
    },
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
    "demos/web-runtime-lab/src/worklet.js": {"docs_static", "portal", "web_runtime_lab"},
    "apps/web-runtime-lab/src/worklet.js": {"portal", "web_runtime_lab"},
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
    "tests/fixtures/long-material/make_fixtures.py": {"creator"},
    "tests/build/ci_runner_fallback_test.py": {"ci_contract"},
    "tests/build/facade_surface_sharding_test.py": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/build/facade_surface_sharding_unit_test.py": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/build/web_runtime_public_deployment_docs_test.py": {"deploy_contract"},
    "tests/conformance/version_lock_test.py": {"core_ubuntu", "core_asan", "core_coverage", "package"},
    "scripts/core.sh": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos", "package"
    },
    "packages/web-runtime-platform/web/runtime_loader.mjs": {
        "portal", "web_toolchain", "web_runtime_host", "creator"
    },
    "packages/web-runtime-platform/test/runtime_loader.test.mjs": {
        "portal", "web_toolchain", "web_runtime_host", "creator"
    },
    "packages/web-runtime-platform/test/performance_master_capture.test.mjs": {
        "portal", "web_toolchain", "web_runtime_host", "creator"
    },
    "packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs": {
        "portal", "web_toolchain", "web_runtime_host", "creator"
    },
    "packages/web-runtime-platform/test/performance_protocol.test.mjs": {
        "portal", "web_toolchain", "web_runtime_host", "creator"
    },
    # Core, Web Runtime and Creator are three expensive families: the existing
    # fail-closed threshold promotes these shared inputs to full mode.
    "packages/web-runtime-platform/test/source_boundary_test.py": LANES,
    "packages/web-runtime-platform/test/control_runtime_test.cpp": LANES,
    "packages/web-runtime-platform/test/performance_bridge_test.cpp": LANES,
    "tools/web-runtime/verify_emscripten.py": {
        "web_toolchain", "web_runtime_host", "creator"
    },
    "tools/provider-benchmark/generate_sample_slice_smoke.py": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/fixtures/provider-benchmark/sample-slice/manifest.json": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/fixtures/cardputer/music_fixture.py": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/fixtures/cardputer/music_fixture.json": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/build/cardputer_music_fixture_test.py": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "apps/cardputer-host/main/runtime_host.cpp": {
        "portal", "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "apps/cardputer-host/main/audio_driver.cpp": {
        "portal", "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "apps/cardputer-host/CMakeLists.txt": {
        "portal", "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "apps/cardputer-host/sdkconfig.defaults": {
        "portal", "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "scripts/cardputer-host.sh": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/platform/cardputer/audio_lifecycle_test.cpp": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/platform/cardputer/CMakeLists.txt": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/build/cardputer_host_build_test.py": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tools/release/model.py": {"deploy_contract", "ci_contract"},
    "tools/canary/planning.py": {"ci_contract"},
    "tools/canary/records.py": {"ci_contract"},
    "tools/canary/policy.json": {"ci_contract"},
    "packaging/core/CMakeLists.txt": {"core_ubuntu", "package"},
    "netlify.toml": {"portal", "ci_contract"},
    "wrangler.json": {"portal", "ci_contract"},
    # verify_emscripten.py binds the lock Node major to .node-version, so
    # every lane that runs it reads this file.
    ".node-version": {"portal", "ci_contract", "web_toolchain", "web_runtime_host", "creator"},
    "scripts/release.sh": {"deploy_contract", "ci_contract"},
    "docs/release-evidence/release-intents.json": {
        "docs_static", "deploy_contract", "ci_contract"
    },
    "tests/build/release_model_test.py": {"deploy_contract", "ci_contract"},
    ".github/workflows/publish-release.yml": {"deploy_contract", "ci_contract"},
    ".github/workflows/release-audit.yml": {"deploy_contract", "ci_contract"},
    ".github/actionlint.yaml": {"ci_contract"},
    ".github/pull_request_template.md": {
        "docs_static", "portal", "ci_contract"
    },
    ".github/actions/web-ci-proof/action.yml": set(LANES),
    ".github/workflows/ci-self-hosted-benchmark.yml": {"ci_contract"},
    ".github/workflows/pr-contract.yml": {"ci_contract"},
    ".gitattributes": set(LANES),
}

TOP_LEVELS = {
    ".agents", ".claude", ".codex", ".gitattributes", ".github", ".gitignore",
    "AGENTS.md", "CLAUDE.md", "CMakeLists.txt", "CMakePresets.json", "LICENSE",
    "README.md", "apps", "cmake", "contracts", "docs", "netlify.toml", "wrangler.json", ".node-version",
    "output", "packages", "packaging", "products", "providers", "references",
    "scripts", "testdata", "tests", "third_party", "tools", "workers", "demos",
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

    def checkout(self, ref, *, create=False):
        args = ["git", "checkout", "--quiet"]
        if create:
            args.append("-b")
        self.run(*args, ref)
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

    def classify_unverifiable_push(self, *, base_sha):
        """Classify a push whose exact `before` range cannot be verified."""
        with TemporaryGitRepository() as repository:
            repository.write_and_commit("docs/guide.md", "one\n", "base")
            head = repository.write_and_commit("docs/guide.md", "two\n", "head")
            inventory, reason = self.module.resolve_push_inventory(
                str(repository.path), base_sha, head,
            )
        self.assertIsNone(inventory)
        return self.module.classify(
            self.policy, (), base_sha=base_sha, head_sha=head,
            event_name="push", draft=False, labels=(), unverifiable_base=reason,
        )

    def true_lanes(self, manifest):
        return {name for name, selected in manifest["lanes"].items() if selected}

    def test_web_compiled_core_modules_select_every_web_consumer(self):
        # Project I/O conformance links Application Facade and its seven Core
        # dependencies; both distribution proofs compile the Web Runtime Host.
        modules = (
            "application-facade", "audio-runtime", "authoring-domain",
            "foundation", "project-cooker", "project-io", "provider-sdk",
            "web-runtime-platform",
        )
        for module in modules:
            for suffix in ("CMakeLists.txt", "include/public.hpp", "src/source.cpp"):
                path = f"packages/{module}/{suffix}"
                with self.subTest(path=path):
                    lanes = self.lanes_for_path(path)
                    for lane in ("web_toolchain", "web_runtime_host", "creator"):
                        self.assertIn(lane, lanes, msg=(
                            f"why: Web-compiled input {path} omits consumer {lane}; "
                            "remedy: add the Web consumer to its scope-policy rule"
                        ))

    def test_project_io_web_storage_selects_every_web_consumer(self):
        path = "packages/project-io/src/web/library_opfs_storage.js"
        for lane in ("web_toolchain", "web_runtime_host", "creator"):
            with self.subTest(lane=lane):
                self.assertIn(lane, self.lanes_for_path(path), msg=(
                    f"why: OPFS link library omits {lane}; remedy: route "
                    "Project I/O Web storage to every compiling Web lane"
                ))

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

    def lanes_for_path(self, path):
        """Return the exact lane union the policy gives one path."""
        return {
            lane for rule in self.policy["rules"]
            if policy_match(rule["match"], path) for lane in rule["lanes"]
        }

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

    def test_generated_dev_outputs_are_not_tracked(self):
        inventory = subprocess.run(
            ["git", "ls-files", "--", "build/dev/"], cwd=ROOT,
            check=True, capture_output=True, text=True,
        ).stdout
        self.assertEqual(inventory, "",
                         "why: generated build/dev outputs are tracked; "
                         "remedy: remove only generated outputs from the index, retaining local files")

    def test_generated_dev_outputs_are_ignored(self):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--", "build/dev/CMakeCache.txt"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         "why: build/dev outputs can be staged accidentally; "
                         "remedy: restore the build/dev/ ignore rule")

    def test_every_document_a_test_reads_reaches_that_test_lane(self):
        # A test that asserts on a document's content is a gate over that
        # document, so editing the document must run the lane that holds the
        # test. Three tests once read eleven documents routed away from their
        # own lane -- `web_runtime_public_deployment_docs_test.py` asserted on
        # a design document routed only to `docs_static` -- and only the
        # queue's unconditional full run caught it. Deriving the expectation
        # from the tests' real read sites keeps a new document from repeating
        # it. The scan reads literal paths only: a dynamically built path is
        # invisible to it, so this gate closes the common case rather than
        # proving the general one.
        # `.agents/` joins `docs/`: the Pitfall Ledger lint reads
        # `.agents/pitfalls`, and a ledger-only Pull Request routed to
        # `docs_static` never ran it -- the third occurrence of the pitfall
        # this test exits (#685). A captured path that is a directory is given
        # its trailing slash so prefix rules classify it.
        read_sites = re.compile(
            r"""(?:readRepo|readFile)\s*\(\s*["'`]((?:docs|\.agents|\.claude)/[A-Za-z0-9_./-]+)"""
            r"""|(?:REPO_ROOT|ROOT)\s*/\s*["']((?:docs|\.agents|\.claude)/[A-Za-z0-9_./-]+)["']"""
        )
        inventory = subprocess.run(
            ["git", "ls-files", "tests", "apps", "-z"],
            cwd=ROOT, check=True, capture_output=True,
        ).stdout
        sources = [
            item.decode("utf-8") for item in inventory.split(b"\0")
            if item and re.search(r"(_test\.py|\.test\.mjs)$", item.decode("utf-8"))
        ]
        gaps = []
        for source in sources:
            source_lanes = self.lanes_for_path(source)
            if not source_lanes:
                continue
            text = (ROOT / source).read_text(encoding="utf-8", errors="ignore")
            documents = {
                match[0] or match[1] for match in read_sites.findall(text)
            }
            for document in sorted(documents):
                if not (ROOT / document).exists():
                    continue
                if (ROOT / document).is_dir():
                    document = document.rstrip("/") + "/"
                missing = source_lanes - self.lanes_for_path(document)
                if missing:
                    gaps.append(
                        f"{document} is missing {sorted(missing)}, read by {source}"
                    )
        self.assertEqual(
            gaps, [],
            "a document a test asserts on does not reach that test's lane.\n"
            "why: editing the document classifies without the lane that holds "
            "the test, so the assertion over its content never runs on the "
            "Pull Request:\n  " + "\n  ".join(gaps) + "\n"
            "remedy: add an exact rule for each document in "
            "scripts/ci/scope_policy.json carrying the missing lanes. Rules are "
            "additive, so the rule needs only the lanes the document does not "
            "already get.",
        )

    def test_registered_e2e_tests_reach_an_executor_that_runs_them(self):
        """Bind CTest e2e registrations to the lanes whose commands execute them.

        The lane-to-command entries below are intentionally limited to
        runtime-generated invocations: the lane's shell script builds the
        CTest command at runtime, so its source cannot be represented as a
        literal test path.  Literal paths are discovered from CMake and the
        scripts instead of being copied into an expected-lanes table.  This
        closes the common registration/routing gap; generated paths and
        invocations in other scripts remain outside this check.
        """
        runtime_ctest_invocations = {
            "scripts/core.sh": {
                # `proof` excludes CTest e2e tests, but its literal Python
                # invocations are checked separately below.
                "core_ubuntu": (r"-E '[^']*e2e\\.[^']*'", False),
                "core_macos": (r"-E '[^']*e2e\\.[^']*'", False),
                # `test ... full` runs every non-stress CTest tier.
                "core_asan": (r"ctest --preset \"\$test_preset\" -LE '\^stress\$'", True),
            },
            "scripts/core-coverage.sh": {
                "core_coverage": (r"ctest --preset coverage", True),
            },
        }
        direct_invocations = {}
        ctest_lanes = set()
        for runner, lanes in runtime_ctest_invocations.items():
            text = (ROOT / runner).read_text(encoding="utf-8")
            for lane, (command_pattern, runs_ctest_e2e) in lanes.items():
                self.assertRegex(
                    text, command_pattern,
                    f"{runner} no longer contains the mapped {lane} executor",
                )
                if runs_ctest_e2e:
                    ctest_lanes.add(lane)
            for path in re.findall(r"tests/e2e/[A-Za-z0-9_./-]+\.py", text):
                direct_invocations.setdefault(path, set()).update(
                    lane for lane, (_, runs_ctest_e2e) in lanes.items()
                    if not runs_ctest_e2e
                )

        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        registrations = re.findall(
            r"lmdj_add_test\(\s*NAME\s+(\S+)(.*?\n\s*\))",
            cmake, re.DOTALL,
        )
        e2e_paths = []
        for name, block in registrations:
            if re.search(r"\bTIER\s+e2e\b", block):
                paths = re.findall(r"tests/e2e/[A-Za-z0-9_./-]+\.py", block)
                e2e_paths.extend((name, path) for path in paths)
        self.assertTrue(e2e_paths, "CMake no longer exposes any e2e registration to inspect")

        gaps = []
        for test_name, path in e2e_paths:
            routed = self.lanes_for_path(path)
            executor_lanes = direct_invocations.get(path, set()) | ctest_lanes
            executed = routed & executor_lanes
            if not executed:
                source = next(
                    (runner for runner in runtime_ctest_invocations
                     if path in direct_invocations or runner == "scripts/core-coverage.sh"),
                    "CMakeLists.txt",
                )
                gaps.append(
                    f"{path}: missing executor lane; source runner {source} "
                    f"(CTest registration {test_name})"
                )
        self.assertEqual(
            gaps, [],
            "registered e2e test is routed away from every command that runs it.\n"
            "why: a CTest registration or literal runner path is not coverage "
            "unless its owning lane invokes that test.\n"
            "remedy: add the executing lane to the additive rule for the test "
            "path, or register a literal invocation in the owning runner.\n"
            + "\n".join(gaps),
        )

    def test_literal_runner_globs_reach_their_lane(self):
        # The Creator runner owns a literal shell glob rather than CTest.
        # Discover executable node/python arguments and expand them against
        # the tracked inventory; do not copy the current glob into the gate.
        literal_glob_invocations = {
            "scripts/creator-web.sh": {
                "creator": (
                    ".github/actions/web-ci-proof/action.yml",
                ),
            },
        }
        inventory = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True,
        ).stdout.decode("utf-8").split("\0")

        def discover(source):
            executable = "\n".join(
                line for line in source.splitlines()
                if not line.lstrip().startswith("#")
            )
            paths = []
            for line in executable.splitlines():
                if "node --test" not in line and "python3" not in line:
                    continue
                try:
                    tokens = shlex.split(line, comments=True, posix=True)
                except ValueError:
                    continue
                for token in tokens:
                    token = token.removeprefix("$repo_root/")
                    if token.startswith(("packages/", "tests/")) and (
                        "*" in token or token.endswith((".py", ".mjs"))
                    ):
                        paths.append(token)
            return paths

        self.assertEqual(discover("# node --test packages/example/test/*.test.mjs"), [])
        self.assertEqual(
            discover('node --test "$repo_root"/packages/example/test/*.test.mjs'),
            ["packages/example/test/*.test.mjs"],
        )
        glob_gaps = []
        for runner, lanes in literal_glob_invocations.items():
            text = (ROOT / runner).read_text(encoding="utf-8")
            executable_lines = "\n".join(
                line for line in text.splitlines()
                if not line.lstrip().startswith("#")
            )
            self.assertRegex(executable_lines, r"node --test",
                             f"{runner} has no executable test command")
            for lane, metadata in lanes.items():
                for token in discover(text):
                    for path in sorted(p for p in inventory if p and fnmatch.fnmatch(p, token)):
                        if lane not in self.lanes_for_path(path):
                            glob_gaps.append(
                                f"{path}: missing executor lane {lane}; source runner {runner}"
                            )
                lane_source = metadata[0]
            action = (ROOT / lane_source).read_text(encoding="utf-8")
            self.assertRegex(action, r"creator:full\) scripts/creator-web\.sh proof",
                             f"{lane_source} no longer connects creator to {runner}")
        self.assertEqual(
            glob_gaps, [],
            "literal runner glob reaches a file without its executor lane.\n"
            "why: a matched test file is not coverage unless its policy route "
            "reaches the runner that expands the glob.\n"
            "remedy: add the runner lane to the file's additive policy rule.\n"
            + "\n".join(glob_gaps),
        )

    def test_e2e_executor_gate_has_a_red_case_for_removed_bundle_routes(self):
        original = self.lanes_for_path

        def without_bundle_executors(path):
            lanes = original(path)
            if path.startswith("tests/e2e/project_bundle_"):
                lanes -= {"core_asan", "core_coverage"}
            return lanes

        self.lanes_for_path = without_bundle_executors
        try:
            with self.assertRaisesRegex(AssertionError, "project_bundle_.*missing executor lane"):
                self.test_registered_e2e_tests_reach_an_executor_that_runs_them()
        finally:
            self.lanes_for_path = original

    def test_glob_gate_has_a_red_case_for_removed_creator_route(self):
        original = self.lanes_for_path

        def without_creator(path):
            return original(path) - {"creator"}

        self.lanes_for_path = without_creator
        try:
            with self.assertRaisesRegex(AssertionError, "missing executor lane creator"):
                self.test_literal_runner_globs_reach_their_lane()
        finally:
            self.lanes_for_path = original

    # A Python test file runs only where something names it, and a directory of
    # suites looks like coverage whether or not anything does: CTest left a
    # conformance suite unregistered for six Stages (#784), runner lists missed
    # three Creator suites (#1800), and no lane ran tests/quality (#2219). This
    # gate reads every tracked `*_test.py`, plus every `test_*.py` that is a
    # unittest or pytest module, and requires each to be run by a lane that its
    # policy route selects. A lane runs a file when one of its CI commands in
    # scripts/ci/local_lanes.json, a script that command reaches, or a CTest
    # registration the command's CTest filter selects names the file, globs it,
    # or discovers it with `unittest discover -s DIR -p PATTERN`.
    #
    # Blind spot: a runner is credited with every test its source names, so a
    # file named only on a subcommand the lane never calls (for example only
    # under `scripts/core.sh package`) still reads as run by every lane calling
    # that runner. The CTest filters below are the exception: they are modelled
    # per lane command and bound to the literal filter text in the runner.
    UNOWNED_TESTS = {
        "scripts/ci/self_test.py": (
            "helper, not a test: the self-test evidence protocol module that "
            "scripts/ci imports as `self_test`"),
        "demos/lmdj-song-pipeline/tests/test_smoke.py": (
            "demo, not product (CLAUDE.md `demos/`): pytest in the demo's own "
            "virtualenv, run by hand per its docstring"),
        "tools/needle-spike/tests/router_smoke_test.py": (
            "spike, not product: needs a downloaded native engine and is run by "
            "hand per tools/needle-spike/README.md"),
        "tools/needle-spike/tests/tool_surface_test.py": (
            "spike, not product: run by hand per tools/needle-spike/README.md"),
    }
    TEST_OWNERSHIP_WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/pr-contract.yml")
    TEST_MODULE_CONTENT = re.compile(r"\bunittest\b|^\s*def test_|^\s*import pytest\b", re.MULTILINE)
    SCRIPT_ROOT_VARIABLES = ("repo_root", "ROOT_DIR")
    # Python runners that discover suites in-process rather than on a command
    # line: (start directory, pattern) and the literal source binding each.
    PYTHON_DISCOVERY_RUNNERS = {
        "tests/build/release_suite_runner.py": (
            "tests/build", "release_*_test.py",
            ('START = ROOT / "tests" / "build"', 'PATTERN = "release_*_test.py"')),
        # The Pull Request ci-contract job runs the change-selected subset.
        "scripts/ci/contract_selection.py": (
            "tests/build", "ci_*_test.py", ('root.joinpath("tests/build").glob("ci_*_test.py")',)),
    }
    # How each CTest-running lane command filters registrations, bound to the
    # literal filter text in the runner that executes it.
    CTEST_LANE_FILTERS = (
        (r"scripts/core\.sh test \S+ full", "scripts/core.sh",
         "-LE '^stress$' -E '^build\\.release_'",
         lambda name, labels: "stress" not in labels and not name.startswith("build.release_")),
        (r"scripts/core\.sh test \S+ fast", "scripts/core.sh",
         "-L '^(unit|component)$' -E '^build\\.release_'",
         lambda name, labels: bool({"unit", "component"} & labels)
         and not name.startswith("build.release_")),
        (r"scripts/core\.sh test \S+ stress", "scripts/core.sh", "-L '^stress$'",
         lambda name, labels: "stress" in labels),
        (r"scripts/core\.sh proof", "scripts/core.sh",
         "-E '^(build\\.active_tree|build\\.version|build\\.release_|contract\\.schemas|"
         "conformance\\.|host\\.|e2e\\.)' \\\n      -LE '^stress$'",
         lambda name, labels: "stress" not in labels and not re.match(
             r"(build\.active_tree|build\.version|build\.release_|contract\.schemas|"
             r"conformance\.|host\.|e2e\.)", name)),
        (r"scripts/core\.sh package", "scripts/core.sh",
         "ctest --preset release -L '^(unit|component)$'",
         lambda name, labels: bool({"unit", "component"} & labels)),
        (r"scripts/core-coverage\.sh check", "CMakePresets.json",
         '"name": "^build\\\\.release_.*$",\n          "label": "^stress$"',
         lambda name, labels: "stress" not in labels and not name.startswith("build.release_")),
    )

    def tracked_files(self):
        return [path for path in subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True,
        ).stdout.decode("utf-8").split("\0") if path]

    def python_test_inventory(self, tracked, read=None):
        """Every tracked `*_test.py`, and every `test_*.py` whose content is a
        unittest or pytest module rather than a tool or helper it names."""
        read = read or (lambda path: (ROOT / path).read_text(encoding="utf-8"))
        suites = []
        for path in tracked:
            name = path.rsplit("/", 1)[-1]
            if name.endswith("_test.py") or (
                    name.startswith("test_") and name.endswith(".py")
                    and self.TEST_MODULE_CONTENT.search(read(path))):
                suites.append(path)
        return suites

    @staticmethod
    def executable_text(text):
        return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))

    def resolve_script_paths(self, text, base=""):
        """Rewrite a script's repository-rooted path variables to plain
        repository-relative paths, so `"$creator_root/test/x_test.py"` reads as
        `apps/creator-web/test/x_test.py`."""
        roots = dict.fromkeys(self.SCRIPT_ROOT_VARIABLES, "")
        assignment = re.compile(r'^\s*(?:readonly\s+|local\s+|export\s+)?(\w+)="?\$\{?(\w+)\}?/([\w./-]*)"?\s*$',
                                re.MULTILINE)
        for _ in range(3):
            for name, root, rest in assignment.findall(text):
                if root in roots and name not in roots:
                    roots[name] = (roots[root] + "/" + rest).lstrip("/").rstrip("/")
        for name, value in sorted(roots.items(), key=lambda item: -len(item[0])):
            prefix = value + "/" if value else ""
            text = re.sub(r'"?\$(?:\{' + name + r'\}|' + name + r'\b)"?/', prefix, text)
        for variable, value in (("CMAKE_SOURCE_DIR", ""), ("PROJECT_SOURCE_DIR", ""),
                                ("CMAKE_CURRENT_SOURCE_DIR", base)):
            text = text.replace("${" + variable + "}/", value + "/" if value else "")
        return text

    def scan_runner_text(self, text, tracked, suites):
        """Return (tests the text runs, tracked scripts it invokes)."""
        tracked_set = set(tracked)
        tests, scripts = set(), set()
        for line in text.splitlines():
            match = re.search(r"\bunittest discover\b(.*)", line)
            if match:
                try:
                    words = shlex.split(match.group(1), comments=True)
                except ValueError:
                    words = match.group(1).split()
                options = dict(zip(words[0::2], words[1::2]))
                start = options.get("-s", ".").strip("/").removeprefix("./")
                pattern = options.get("-p", "test*.py")
                tests.update(self.discovered(suites, start, pattern))
        for token in re.findall(r"(?<![\w./*-])((?:[\w.*-]+/)+[\w.*-]+\.(?:py|sh))\b", text):
            if "*" in token:
                directory, pattern = token.rsplit("/", 1)
                tests.update(path for path in suites if path.rsplit("/", 1)[0] == directory
                             and fnmatch.fnmatchcase(path.rsplit("/", 1)[1], pattern))
            elif token in tracked_set:
                (tests if token in suites else scripts).add(token)
        return tests, scripts

    @staticmethod
    def discovered(suites, start, pattern):
        prefix = start + "/" if start not in ("", ".") else ""
        return {path for path in suites if path.startswith(prefix)
                and "/" not in path[len(prefix):]
                and fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)}

    def runner_closure(self, text, tracked, suites, base=""):
        """Tests reached from `text` and every tracked script it invokes."""
        tests, pending, seen = set(), [(text, base)], set()
        while pending:
            source, directory = pending.pop()
            found, scripts = self.scan_runner_text(
                self.resolve_script_paths(self.executable_text(source), directory), tracked, suites)
            tests |= found
            for script in sorted(scripts - seen):
                seen.add(script)
                if script in self.PYTHON_DISCOVERY_RUNNERS:
                    start, pattern, bindings = self.PYTHON_DISCOVERY_RUNNERS[script]
                    runner = (ROOT / script).read_text(encoding="utf-8")
                    for binding in bindings:
                        self.assertIn(binding, runner, f"{script} no longer discovers {start}/{pattern}")
                    tests |= self.discovered(suites, start, pattern)
                elif script.endswith(".sh"):
                    pending.append(((ROOT / script).read_text(encoding="utf-8"),
                                    script.rsplit("/", 1)[0]))
        return tests

    def ctest_registrations(self, tracked, suites):
        """Yield (name, labels, tests) for every lmdj_add_test registration."""
        for cmake in tracked:
            if not (cmake.endswith("CMakeLists.txt") or cmake.endswith(".cmake")):
                continue
            text = self.executable_text((ROOT / cmake).read_text(encoding="utf-8"))
            directory = cmake.rsplit("/", 1)[0] if "/" in cmake else ""
            for start in (m.end() for m in re.finditer(r"\blmdj_add_test\(", text)):
                depth, end = 1, start
                while depth and end < len(text):
                    depth += {"(": 1, ")": -1}.get(text[end], 0)
                    end += 1
                block = text[start:end - 1]
                name = re.search(r"\bNAME\s+\"?([^\s\"]+)", block)
                tier = re.search(r"\bTIER\s+(\w+)", block)
                labels = re.search(r"\bLABELS\s+([^\n]*)", block)
                if not name or "function(" in text[max(0, start - 40):start]:
                    continue
                label_set = {tier.group(1)} if tier else set()
                if labels:
                    label_set |= set(re.findall(r"[\w-]+", labels.group(1)))
                yield name.group(1), label_set, self.runner_closure(block, tracked, suites, directory)

    def python_test_invocations(self, tracked, suites):
        """Map each suite to {lane: {lane commands that reach it}}, over the
        commands CI runs: a lane's main commands and its Pull Request
        (`quick`) subset."""
        lanes = json.loads((ROOT / "scripts/ci/local_lanes.json").read_text(encoding="utf-8"))["lanes"]
        registrations = list(self.ctest_registrations(tracked, suites))
        self.assertTrue(registrations, "no lmdj_add_test registration was found to inspect")
        filters = []
        for command_pattern, runner, literal, selects in self.CTEST_LANE_FILTERS:
            self.assertIn(literal, (ROOT / runner).read_text(encoding="utf-8"),
                          f"{runner} no longer applies the CTest filter this gate models "
                          f"for `{command_pattern}`")
            filters.append((command_pattern, selects))
        invoked = {}
        for lane, entry in lanes.items():
            for command in (*entry["commands"], *entry.get("quick", {}).get("commands", ())):
                reached = self.runner_closure(command, tracked, suites)
                for command_pattern, selects in filters:
                    if re.search(command_pattern, command):
                        for name, labels, tests in registrations:
                            if selects(name, labels):
                                reached |= tests
                for path in reached:
                    invoked.setdefault(path, {}).setdefault(lane, set()).add(command)
        return invoked

    def route_lanes(self, path):
        if any(policy_match(rule["match"], path) for rule in self.policy["full_rules"]):
            return set(self.policy["lanes"])
        return self.lanes_for_path(path)

    def python_test_gaps(self, suites, invocations, unowned=None):
        unowned = self.UNOWNED_TESTS if unowned is None else unowned
        gaps = []
        for path in sorted(suites):
            runners = set(invocations.get(path, {}))
            if path in unowned:
                if runners:
                    gaps.append(f"{path}: allowlisted as unrun, but lane(s) {sorted(runners)} run it")
            elif not runners:
                gaps.append(f"{path}: no lane command runs it")
            elif not runners & self.route_lanes(path):
                gaps.append(f"{path}: run only by lane(s) {sorted(runners)}, "
                            f"which its route {sorted(self.route_lanes(path))} never selects")
        for path in sorted(set(unowned) - set(suites)):
            gaps.append(f"{path}: allowlisted as unrun, but it is not a tracked test file")
        return gaps

    @staticmethod
    def workflow_command_key(command):
        """The part of a lane command a workflow step must repeat verbatim:
        without a leading `env NAME=value` and before the first long option,
        whose values (`{base}`, `--shards 4`) differ between local and CI."""
        command = re.sub(r"^env(?:\s+[A-Z_]+=(?:\"[^\"]*\"|\S+))+\s+", "", command)
        return command.split(" --", 1)[0]

    def python_test_workflow_gaps(self, invocations, workflows, actions):
        """A routed lane must run a suite in CI, not only in local_lanes.json:
        some lane that runs the file and that its route selects must have a
        reaching command in that lane's job in every workflow defining it. A
        lane reaching the file only through a local-only variant (core_macos's
        `quick` fast tier) does not count."""
        gaps = []
        for path, runners in sorted(invocations.items()):
            failures = []
            for lane in sorted(set(runners) & self.route_lanes(path)):
                jobs = self.policy["lane_jobs"][lane]
                keys = {self.workflow_command_key(command) for command in runners[lane]}
                command = " or ".join(f"`{key}`" for key in sorted(keys))
                missing = []
                for name, workflow in sorted(workflows.items()):
                    blocks = [re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [\w-]+:\n|\Z)", workflow)
                              for job in jobs]
                    # Directives only: a comment naming the command is not a step running it.
                    directives = [self.executable_text(block.group(1)) for block in blocks if block]
                    directives += [actions.get(used, "") for text in list(directives)
                                   for used in re.findall(r"uses: \./(\.github/actions/[\w-]+)", text)]
                    # A folded `run: >-` step spans lines; compare on single spaces.
                    directives = [" ".join(text.split()) for text in directives]
                    if directives and not any(key in text for key in keys for text in directives):
                        missing.append(name)
                if not missing:
                    break
                failures.append(f"lane {lane} runs {command}, which none of its jobs {jobs} "
                                f"in {', '.join(missing)} runs")
            else:
                if failures:
                    gaps.append(f"{path}: " + "; ".join(failures))
        return gaps

    def test_every_python_test_is_run_by_a_lane_that_owns_it(self):
        tracked = self.tracked_files()
        suites = self.python_test_inventory(tracked)
        invocations = self.python_test_invocations(tracked, suites)
        # Independent oracle: one known runner per mechanism the model reads,
        # so a parser change that loses a mechanism fails here by name even
        # where the inventory and the invocation map would agree on nothing.
        for path, lane in (
                ("tests/quality/core_coverage_runner_test.py", "ci_contract"),  # discover
                ("tests/build/ci_change_scope_test.py", "ci_contract"),  # discover
                ("apps/creator-web/test/favicon_test.py", "creator"),  # script variable
                ("apps/web-runtime-host/test/server_test.py", "web_runtime_host"),  # $repo_root
                ("tools/asset-server/kit_test.py", "creator"),  # nested script
                ("tests/build/release_cli_orchestration_test.py", "deploy_contract"),  # Python runner
                ("tests/conformance/project_bundle_contract_test.py", "core_asan"),  # CTest
                ("tests/core/support/no_bare_fork_test.py", "core_asan"),  # CTest -> script
                ("tests/conformance/schema_contract_test.py", "core_ubuntu"),  # core.sh proof
        ):
            self.assertIn(path, suites)
            self.assertIn(lane, invocations.get(path, {}), f"the gate no longer sees {lane} run {path}")
        # CTest filters: release suites belong to deploy_contract, not to the
        # Core lanes that exclude `build.release_` by name.
        self.assertNotIn("core_asan", invocations["tests/build/release_cli_orchestration_test.py"])
        self.assertTrue(all(reason.strip() for reason in self.UNOWNED_TESTS.values()))
        gaps = self.python_test_gaps(suites, invocations)
        self.assertEqual(
            gaps, [],
            "a tracked Python test file is not run by any lane that owns it.\n"
            "why: a test file runs only where a lane command, a runner script or a "
            "CTest registration names it, so an unlisted file reads as coverage "
            "but never executes (#784, #1800, #2219).\n"
            "remedy: run it from the lane that owns its code: name it in that "
            "lane's runner (for example run_nonbrowser_tests in "
            "scripts/web-runtime-host.sh or test_creator in scripts/creator-web.sh), "
            "register it with lmdj_add_test, or add it to a lane command in "
            "scripts/ci/local_lanes.json and that lane's job; keep its route in "
            "scripts/ci/scope_policy.json selecting that lane. Only a file that is "
            "not a test, or is outside the product, goes in UNOWNED_TESTS with a "
            "reason; remove an entry once a lane runs the file.\n"
            + "\n".join(gaps),
        )
        workflows = {name: (ROOT / name).read_text(encoding="utf-8")
                     for name in self.TEST_OWNERSHIP_WORKFLOWS}
        self.assertTrue(all(re.search(r"(?m)^  ci-contract:\n", text) for text in workflows.values()),
                        "both workflows must still define the ci-contract job this gate reads")
        actions = {path.rsplit("/", 1)[0]: self.executable_text((ROOT / path).read_text(encoding="utf-8"))
                   for path in tracked
                   if path.startswith(".github/actions/") and path.endswith("/action.yml")}
        gaps = self.python_test_workflow_gaps(invocations, workflows, actions)
        self.assertEqual(
            gaps, [],
            "a lane command that runs a Python test is not run by that lane's CI job.\n"
            "why: scripts/ci/local_lanes.json describes the lane; only the workflow "
            "job executes it in CI.\n"
            "remedy: run the same command in that lane's job (or a local action it "
            "uses) in the named workflow.\n"
            + "\n".join(gaps),
        )

    def test_python_test_gate_has_red_cases(self):
        self.assertEqual(
            self.python_test_gaps(["tests/quality/test_orphan.py"], {}, unowned={}),
            ["tests/quality/test_orphan.py: no lane command runs it"],
        )
        self.assertEqual(
            self.python_test_gaps(["apps/creator-web/test/orphan_test.py"], {}, unowned={}),
            ["apps/creator-web/test/orphan_test.py: no lane command runs it"],
        )
        allowlisted = {"tools/spike/tests/probe_test.py": "spike, run by hand"}
        self.assertEqual(self.python_test_gaps(["tools/spike/tests/probe_test.py"], {},
                                               unowned=allowlisted), [])
        self.assertEqual(
            self.python_test_gaps([], {}, unowned=allowlisted),
            ["tools/spike/tests/probe_test.py: allowlisted as unrun, "
             "but it is not a tracked test file"],
        )
        self.assertEqual(
            self.python_test_gaps(["tools/spike/tests/probe_test.py"],
                                  {"tools/spike/tests/probe_test.py": {"creator": "x"}},
                                  unowned=allowlisted),
            ["tools/spike/tests/probe_test.py: allowlisted as unrun, but lane(s) "
             "['creator'] run it"],
        )
        contents = {"tests/quality/test_budget_report.py": "import json\n",
                    "tests/quality/test_orphan.py": "import unittest\n",
                    "tests/quality/test_pytest.py": "def test_case():\n    pass\n"}
        self.assertEqual(
            self.python_test_inventory(["tests/quality/coverage_gate.py",
                                        "tests/quality/test_budget_report.py",
                                        "tests/quality/test_orphan.py",
                                        "tests/quality/test_pytest.py",
                                        "apps/creator-web/test/helpers/nested_test.py"],
                                       read=contents.__getitem__),
            ["tests/quality/test_orphan.py", "tests/quality/test_pytest.py",
             "apps/creator-web/test/helpers/nested_test.py"],
        )
        suites = ["apps/creator-web/test/x_test.py", "tests/quality/a_test.py",
                  "tests/quality/nested/b_test.py", "packages/p/test/c_test.py"]
        runner = ('creator_root="$repo_root/apps/creator-web"\n'
                  'python3 "$creator_root/test/x_test.py"\n'
                  '# python3 "$repo_root/packages/p/test/c_test.py"\n'
                  "python3 -m unittest discover -s tests/quality -p '*_test.py'\n")
        tests, _ = self.scan_runner_text(
            self.resolve_script_paths(self.executable_text(runner)), suites, suites)
        self.assertEqual(sorted(tests), ["apps/creator-web/test/x_test.py", "tests/quality/a_test.py"])
        tests, _ = self.scan_runner_text('python3 "$repo_root"/packages/p/test/*_test.py'
                                         .replace('"$repo_root"/', ""), suites, suites)
        self.assertEqual(tests, {"packages/p/test/c_test.py"})
        command = "python3 -m unittest discover -s tests/quality -p '*_test.py'"
        invocations = {"tests/quality/coverage_gate_test.py": {"ci_contract": {command}}}
        runs = f"jobs:\n  ci-contract:\n    steps:\n      - run: {command}\n"
        lacks = f"jobs:\n  ci-contract:\n    steps: []\n  core-coverage:\n      - run: {command}\n"
        commented = f"jobs:\n  ci-contract:\n    steps:\n      # {command}\n"
        via_action = "jobs:\n  ci-contract:\n    steps:\n      - uses: ./.github/actions/x\n"
        gap = ("tests/quality/coverage_gate_test.py: lane ci_contract runs "
               f"`{command}`, which none of its jobs ['ci-contract'] in pr.yml runs")
        self.assertEqual(self.workflow_command_key(
            'env PATH="/x:$PATH" CC=clang scripts/core-coverage.sh check'), "scripts/core-coverage.sh check")
        self.assertEqual(self.workflow_command_key(
            "python3 scripts/ci/contract_selection.py --base {base} --execute all"),
            "python3 scripts/ci/contract_selection.py")
        folded = ("jobs:\n  ci-contract:\n    steps:\n      - run: >-\n"
                  "          python3 -m unittest discover\n          -s tests/quality -p '*_test.py'\n")
        gaps = lambda pr, actions={}: self.python_test_workflow_gaps(
            invocations, {"ci.yml": runs, "pr.yml": pr}, actions)
        self.assertEqual(gaps(runs), [])
        self.assertEqual(gaps(folded), [])
        # A workflow that does not define the lane's job owes nothing.
        self.assertEqual(gaps("jobs: {}\n"), [])
        self.assertEqual(gaps(lacks), [gap])
        self.assertEqual(gaps(commented), [gap])
        self.assertEqual(gaps(via_action, {".github/actions/x": f"run: {command}\n"}), [])
        self.assertEqual(gaps(via_action, {".github/actions/x": "run: true\n"}), [gap])
        original = self.lanes_for_path
        self.lanes_for_path = lambda path: original(path) - {"ci_contract", "creator"}
        try:
            self.assertEqual(
                self.python_test_gaps(["tests/quality/coverage_gate_test.py"],
                                      invocations, unowned={}),
                ["tests/quality/coverage_gate_test.py: run only by lane(s) ['ci_contract'], "
                 "which its route ['core_coverage'] never selects"],
            )
            self.assertEqual(
                self.python_test_gaps(["apps/creator-web/test/package_test.py"],
                                      {"apps/creator-web/test/package_test.py": {"creator": "x"}},
                                      unowned={}),
                ["apps/creator-web/test/package_test.py: run only by lane(s) ['creator'], "
                 "which its route ['portal'] never selects"],
            )
        finally:
            self.lanes_for_path = original

    def test_every_tracked_top_level_is_admitted_by_the_policy(self):
        # `_evaluate_ready_paths` checks the top-level segment against
        # `known_top_levels` independently of, and before, any routing rule
        # match, so a rule alone does not stop the unknown-top-level upgrade.
        # Two rule additions have already shipped without the matching
        # admission -- `.agents/` and `LICENSE` -- and each silently ran full
        # CI for a Markdown-only change until this gate existed. Derive the
        # expectation from the worktree so a new top level cannot land with
        # only half the policy updated.
        inventory = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        ).stdout
        tracked = {
            item.decode("utf-8").split("/", 1)[0]
            for item in inventory.split(b"\0") if item
        }
        unknown = sorted(tracked - set(self.policy["known_top_levels"]))
        self.assertEqual(
            unknown, [],
            "scope policy does not admit every tracked top level.\n"
            f"why: {unknown} are tracked in the worktree but absent from "
            "known_top_levels, and the classifier rejects an unlisted "
            "top-level segment before any routing rule is consulted, so every "
            "change touching them upgrades the run to full CI even when a "
            "rule already routes the path.\n"
            "remedy: add each name to `known_top_levels` in "
            "scripts/ci/scope_policy.json and to `TOP_LEVELS` in this file, "
            "and confirm the path also matches a `rules` or `full_rules` "
            "entry.",
        )

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

    def test_rule_note_is_an_optional_annotation_and_never_a_lane_input(self):
        # A rule whose lane set depends on coverage owned elsewhere says so
        # where it is edited: `packaging/core/` does not route `packages/**`
        # here because tests/distribution/package_acceptance_test.py runs
        # inside scripts/core.sh proof on the core lanes. The note is an
        # annotation only -- selection must be identical without it, and an
        # empty one fails closed rather than reading as an absent note.
        noted = [rule for rule in self.policy["rules"] if "note" in rule]
        self.assertTrue(noted, "no rule states the assumption its lanes rest on")
        for rule in noted:
            self.assertIsInstance(rule["note"], str)
            self.assertTrue(rule["note"].strip())

        stripped = copy.deepcopy(self.policy)
        for rule in stripped["rules"]:
            rule.pop("note", None)
        for path in ("packaging/core/README.md", "docs/guide.md"):
            with self.subTest(path=path):
                self.assertEqual(
                    self.true_lanes(self.classify([path])),
                    self.true_lanes(self.module.classify(
                        stripped, changed(self.module, path),
                        base_sha="a" * 40, head_sha="b" * 40,
                        event_name="pull_request", draft=False, labels=(),
                    )),
                )

        for invalid in ("", 0):
            with self.subTest(note=invalid):
                policy = copy.deepcopy(self.policy)
                policy["rules"][0]["note"] = invalid
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
            "scripts/ci/scope_policy.json",
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

    def test_retired_review_paths_keep_ownership_for_deletion_and_historical_diffs(self):
        for filename in (
            ".github/scripts/advisory_review_liveness.py", ".github/scripts/grok_review.py",
            ".github/workflows/advisory-review-liveness.yml", ".github/workflows/pr-agent-credential-preflight.yml",
        ):
            with self.subTest(filename=filename):
                manifest = self.classify([filename])
                self.assertEqual(manifest["mode"], "focused")
                self.assertEqual(self.true_lanes(manifest), {"ci_contract"})

    def test_review_target_script_is_ci_contract_and_similar_unknown_name_is_full(self):
        # `.github/scripts/pr_review_target.py` binds a review run to a PR head
        # and publishes the trusted review; an unknown workflow with a similar
        # name is still a full-CI control-plane path.
        manifest = self.classify([".github/scripts/pr_review_target.py"])
        self.assertEqual(manifest["mode"], "focused")
        self.assertEqual(self.true_lanes(manifest), {"ci_contract"})
        unknown = self.classify([".github/workflows/grok-review-control.yml"])
        self.assertEqual(unknown["mode"], "full")
        self.assertEqual(self.true_lanes(unknown), LANES)

    def test_pr_contract_workflow_is_ci_contract_only(self):
        manifest = self.classify([".github/workflows/pr-contract.yml"])
        self.assertEqual(manifest["mode"], "focused")
        self.assertEqual(self.true_lanes(manifest), {"ci_contract"})

    def test_a_portal_witness_inventory_selects_the_portal_lane(self):
        # The generated-only receipt evidence path binds to the PR-gate
        # portal-provenance check run; if a witness-shaped head did not select
        # the portal lane, every such receipt would stay pending forever.
        manifest = self.classify([
            "apps/architecture-portal/versioned_provenance/version-1.0.57.0.json",
            "apps/architecture-portal/versioned_metadata/version-1.0.57.0.json",
            "apps/architecture-portal/versioned_sidebars/version-1.0.57.0-sidebars.json",
            "apps/architecture-portal/static/versions/1.0.57.0/manifest.json",
        ])
        self.assertEqual(manifest["mode"], "focused")
        self.assertEqual(self.true_lanes(manifest), {"portal"})

    def test_a_scheduled_sweep_of_main_is_full_and_trusted(self):
        """#543: the daily sweep runs the complete manifest-selected set.

        Focused `main` is a recorded cost decision; its blind spot is a lane
        left red across docs-only pushes that never select it. A `schedule`
        event on `main`'s tip classifies full so that cannot hide.
        """
        manifest = self.classify(["docs/guide.md"], event_name="schedule")
        self.assertEqual(manifest["mode"], "full")
        self.assertEqual(self.true_lanes(manifest), LANES)
        self.assertIn("full event: schedule", manifest["reasons"])
        self.assertTrue(manifest["trusted_head"])

    def test_a_scheduled_sweep_carries_no_lane_selection(self):
        with self.assertRaises(ValueError):
            self.classify(["docs/guide.md"], event_name="schedule", requested_lanes={"docs_static"})

    def test_a_self_test_skip_selects_no_lane_and_says_why(self):
        """A schedule or empty-dispatch batch whose target already has a
        complete self-test conclusion runs nothing: focused, no lane, the
        reason in the manifest. Focused rather than a new mode so release
        authority, which needs a retained full manifest, rejects the run."""
        for event in ("schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                # A self-test batch has no change inventory: its base is its
                # head, the target itself.
                manifest = self.classify(
                    [], event_name=event,
                    self_test_skip="target a1b2c3d4e5f6 already concluded passed",
                )
                self.assertEqual(manifest["mode"], "focused")
                self.assertEqual(self.true_lanes(manifest), set())
                self.assertEqual(manifest["required_jobs"], [])
                self.assertEqual(manifest["reasons"],
                                 ["self-test skip: target a1b2c3d4e5f6 already concluded passed"])
                self.assertTrue(manifest["trusted_head"])

    def test_a_self_test_skip_is_refused_outside_a_self_test_batch(self):
        cases = {
            "pull_request": dict(event_name="pull_request"),
            "push": dict(event_name="push"),
            "lane selection": dict(event_name="workflow_dispatch", requested_lanes={"docs_static"}),
            "empty reason": dict(event_name="schedule", self_test_skip=""),
            "with an inventory that owns lanes": dict(event_name="schedule", paths=["docs/guide.md"]),
        }
        for label, kwargs in cases.items():
            with self.subTest(case=label):
                kwargs.setdefault("self_test_skip", "already concluded")
                paths = kwargs.pop("paths", [])
                with self.assertRaises(ValueError):
                    self.classify(paths, **kwargs)

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
            "docs/guide.md", "apps/docs-site/src/main.js",
            "apps/web-runtime-host/src/main.mjs",
        ])
        self.assertEqual(full["mode"], "full")
        self.assertEqual(focused["mode"], "focused")

    def test_ci_full_upgrades_ready_pr_to_full(self):
        plain = self.classify(["docs/guide.md"])
        labeled = self.classify(["docs/guide.md"], labels={"ci:full"})
        self.assertEqual(plain["mode"], "focused")
        self.assertEqual(labeled["mode"], "full")

    def test_queue_label_authorizes_without_changing_scope(self):
        # The label authorizes a merge; it does not widen one. Merge evidence
        # is the classification, so a docs-only change carries the same
        # manifest whether or not it is queued.
        plain = self.classify(["docs/guide.md"])
        labelled = self.classify(["docs/guide.md"], labels={"merge:queue"})
        self.assertEqual(labelled["mode"], "focused")
        self.assertEqual(self.true_lanes(labelled), {"docs_static"})
        self.assertEqual(labelled["lanes"], plain["lanes"])
        self.assertEqual(labelled["reasons"], plain["reasons"])

    def test_docs_main_push_is_focused(self):
        manifest = self.classify(["docs/guide.md"], event_name="push")
        self.assertEqual(manifest["mode"], "focused")
        self.assertEqual(self.true_lanes(manifest), {"docs_static"})

    def test_dispatch_without_lanes_is_still_full(self):
        manifest = self.classify(["docs/guide.md"], event_name="workflow_dispatch")
        self.assertEqual(manifest["mode"], "full")
        self.assertEqual(self.true_lanes(manifest), LANES)

    def test_unverifiable_push_base_is_full(self):
        manifest = self.classify_unverifiable_push(base_sha="0" * 40)
        self.assertEqual(manifest["mode"], "full")
        self.assertIn("unverifiable push base", manifest["reasons"])

    def test_every_unverifiable_push_base_condition_is_full_without_guessed_paths(self):
        with TemporaryGitRepository() as repository:
            base = repository.write_and_commit("docs/guide.md", "one\n", "base")
            head = repository.write_and_commit("docs/guide.md", "two\n", "head")
            repository.run("git", "checkout", "--quiet", "-b", "other", base)
            unrelated = repository.write_and_commit(
                "docs/other.md", "one\n", "unrelated",
            )
            blob = repository.run(
                "git", "rev-parse", f"{head}:docs/guide.md",
            ).stdout.strip()
            cases = {
                "zero before": "0" * 40,
                "absent before": "1" * 40,
                "non-commit before": blob,
                "non-ancestor before": unrelated,
            }
            for name, base_sha in cases.items():
                with self.subTest(name=name):
                    inventory, reason = self.module.resolve_push_inventory(
                        str(repository.path), base_sha, head,
                    )
                    self.assertIsNone(inventory)
                    self.assertTrue(reason)
                    manifest = self.module.classify(
                        self.policy, (), base_sha=base_sha, head_sha=head,
                        event_name="push", draft=False, labels=(),
                        unverifiable_base=reason,
                    )
                    self.assertEqual(manifest["mode"], "full")
                    self.assertEqual(self.true_lanes(manifest), LANES)
                    self.assertEqual(manifest["changed_files"], [])
                    self.assertIn("unverifiable push base", manifest["reasons"])
                    self.assertTrue(any(
                        item.startswith("unverifiable push base: ")
                        for item in manifest["reasons"]
                    ))

    def test_verifiable_push_base_reports_the_exact_inventory(self):
        with TemporaryGitRepository() as repository:
            base = repository.write_and_commit("docs/guide.md", "one\n", "base")
            head = repository.write_and_commit(
                "apps/creator-web/src/editor.ts", "one\n", "creator",
            )
            inventory, reason = self.module.resolve_push_inventory(
                str(repository.path), base, head,
            )
            self.assertIsNone(reason)
            self.assertEqual(
                {path for record in inventory for path in record.paths},
                {"apps/creator-web/src/editor.ts"},
            )

    def behind_base_branch(self, repository):
        """Cut a branch, then land an unrelated change on the base branch.

        Returns the base branch tip a `pull_request` event would carry, which is
        strictly ahead of the branch's merge base, and the branch head.
        """
        repository.write_and_commit("docs/guide.md", "one\n", "base")
        repository.checkout("task", create=True)
        head = repository.write_and_commit(
            "docs/research/note.md", "branch work\n", "branch",
        )
        repository.checkout("-")
        base = repository.write_and_commit(
            "apps/creator-web/src/editor.ts", "landed elsewhere\n", "main moves on",
        )
        return base, head

    def test_behind_base_branch_reports_only_its_own_inventory(self):
        with TemporaryGitRepository() as repository:
            base, head = self.behind_base_branch(repository)
            inventory = self.module.read_git_inventory(
                str(repository.path), base, head,
            )
            self.assertEqual(
                {path for record in inventory for path in record.paths},
                {"docs/research/note.md"},
            )
            # The two-dot range the classifier used before issue #539, for
            # contrast: it blames the branch for the base branch's own commit.
            two_dot = repository.run(
                "git", "diff", "--name-only", base, head,
            ).stdout.split()
            self.assertIn("apps/creator-web/src/editor.ts", two_dot)

    def test_behind_base_branch_does_not_over_select_lanes(self):
        with TemporaryGitRepository() as repository:
            base, head = self.behind_base_branch(repository)
            manifest = self.module.classify(
                self.policy,
                self.module.read_git_inventory(str(repository.path), base, head),
                base_sha=base, head_sha=head, event_name="pull_request",
                draft=False, labels=(), trusted_head=True,
            )
            self.assertEqual(manifest["mode"], "focused")
            self.assertEqual(
                [entry["paths"] for entry in manifest["changed_files"]],
                [["docs/research/note.md"]],
            )
            selected = {lane for lane, on in manifest["lanes"].items() if on}
            self.assertEqual(selected, {"docs_static"})
            self.assertNotIn("creator_web", selected)

    def test_a_base_side_deletion_does_not_read_as_an_addition(self):
        """The shape that would fail `docs-static`'s whitespace check.

        `git diff --check` reads added lines. Two-dot reverses a base-side
        deletion into an addition, so a trailing-whitespace line the base branch
        removed after the branch was cut would be attributed to a branch that
        never wrote it.
        """
        with TemporaryGitRepository() as repository:
            repository.write_and_commit("docs/guide.md", "trailing \n", "base")
            repository.checkout("task", create=True)
            head = repository.write_and_commit(
                "docs/research/note.md", "clean\n", "branch",
            )
            repository.checkout("-")
            base = repository.write_and_commit(
                "docs/guide.md", "clean\n", "main drops the whitespace",
            )
            two_dot = repository.run(
                "git", "diff", "--check", base, head, check=False,
            )
            self.assertNotEqual(two_dot.returncode, 0, two_dot.stdout)
            three_dot = repository.run(
                "git", "diff", "--check", f"{base}...{head}", check=False,
            )
            self.assertEqual(three_dot.returncode, 0, three_dot.stdout)

    def test_unverifiable_push_base_never_carries_a_path_inventory(self):
        with self.assertRaises(ValueError):
            self.classify(
                ["docs/guide.md"], event_name="push",
                unverifiable_base="fixture reason",
            )
        for event in ("pull_request", "workflow_dispatch"):
            with self.subTest(event=event):
                with self.assertRaises(ValueError):
                    self.module.classify(
                        self.policy, (), base_sha="a" * 40, head_sha="b" * 40,
                        event_name=event, draft=False, labels=(),
                        unverifiable_base="fixture reason",
                    )

    def test_unsafe_main_pushes_stay_full(self):
        cases = {
            "product assembly": ["products/lmdj/assembly.json"],
            "contract": ["contracts/project/lmdj.project.v5.schema.json"],
            "ci control": [".github/workflows/ci.yml"],
            "ci script": ["scripts/ci/change_scope.py"],
            "unknown path": ["invented-top-level/file.txt"],
            "three expensive families": [
                "tests/core/render_test.cpp",
                "apps/web-runtime-host/src/main.mjs",
                "apps/creator-web/src/editor.ts",
            ],
        }
        for name, paths in cases.items():
            with self.subTest(name=name):
                manifest = self.classify(paths, event_name="push")
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
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertNotIn("inputs.lanes", workflow)
        self.assertIn("batch_request:", workflow)
        self.assertIn("batch_execution.py prepare", workflow)

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

    def invoke_classifier(self, repository, *, event, base_sha, head_sha,
                          manifest, environment=None):
        return subprocess.run([
            sys.executable, str(CLASSIFIER_PATH), "--policy", str(POLICY_PATH),
            "--event", event, "--base-sha", base_sha, "--head-sha", head_sha,
            "--repository", "owner/repo", "--head-repository", "owner/repo",
            "--pr-number", "1", "--manifest-out", str(manifest),
            "--github-output", str(repository.path / "output"),
            "--summary", str(repository.path / "summary.md"),
        ], cwd=repository.path, capture_output=True, text=True, env=environment)

    def fake_git_bin(self, repository, *, diff_status):
        fake_bin = repository.path / "fake-bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"cat-file\" ]; then exit 0; fi\n"
            "if [ \"$1\" = \"merge-base\" ]; then exit 0; fi\n"
            f"if [ \"$1\" = \"diff\" ]; then exit {diff_status}; fi\n"
            "exit 7\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        return dict(os.environ, PATH=str(fake_bin))

    def test_missing_git_object_or_failed_diff_is_a_hard_error_off_the_push_path(self):
        with TemporaryGitRepository() as repository:
            base = repository.write_and_commit("docs/guide.md", "one\n", "base")
            head = repository.write_and_commit("docs/guide.md", "two\n", "head")
            with self.subTest("missing object"):
                manifest = repository.path / "missing-object.json"
                result = self.invoke_classifier(
                    repository, event="pull_request", base_sha="1" * 40,
                    head_sha=head, manifest=manifest,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(manifest.exists())
            with self.subTest("failed diff"):
                manifest = repository.path / "failed-diff.json"
                result = self.invoke_classifier(
                    repository, event="pull_request", base_sha=base,
                    head_sha=head, manifest=manifest,
                    environment=self.fake_git_bin(repository, diff_status=9),
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(manifest.exists())

    def test_push_with_an_unverifiable_base_publishes_a_full_manifest(self):
        with TemporaryGitRepository() as repository:
            head = repository.write_and_commit("docs/guide.md", "one\n", "base")
            manifest = repository.path / "zero-base.json"
            result = self.invoke_classifier(
                repository, event="push", base_sha="0" * 40, head_sha=head,
                manifest=manifest,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(document["mode"], "full")
            self.assertEqual(document["base_sha"], "0" * 40)
            self.assertEqual(document["changed_files"], [])
            self.assertIn("unverifiable push base", document["reasons"])

    def test_push_with_an_incomplete_inventory_publishes_a_full_manifest(self):
        with TemporaryGitRepository() as repository:
            base = repository.write_and_commit("docs/guide.md", "one\n", "base")
            head = repository.write_and_commit("docs/guide.md", "two\n", "head")
            manifest = repository.path / "incomplete.json"
            result = self.invoke_classifier(
                repository, event="push", base_sha=base, head_sha=head,
                manifest=manifest,
                environment=self.fake_git_bin(repository, diff_status=9),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(document["mode"], "full")
            self.assertEqual(document["changed_files"], [])
            self.assertIn("unverifiable push base", document["reasons"])

    def test_docs_only_push_publishes_a_focused_manifest(self):
        with TemporaryGitRepository() as repository:
            base = repository.write_and_commit("docs/guide.md", "one\n", "base")
            head = repository.write_and_commit("docs/guide.md", "two\n", "head")
            manifest = repository.path / "focused.json"
            result = self.invoke_classifier(
                repository, event="push", base_sha=base, head_sha=head,
                manifest=manifest,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(document["mode"], "focused")
            self.assertEqual(
                {lane for lane, on in document["lanes"].items() if on},
                {"docs_static"},
            )
            self.assertEqual(document["required_jobs"], ["docs-static"])

    def test_preserving_policy_push_publishes_focused_manifest_and_summary(self):
        """The producer proof must survive the CLI's summary validation."""
        target = (
            "packages/web-runtime-platform/test/"
            "performance_master_capture.test.mjs"
        )
        with TemporaryGitRepository() as repository:
            base_policy = copy.deepcopy(self.policy)
            base_policy["rules"] = [
                rule for rule in base_policy["rules"]
                if rule["match"] != {"kind": "exact", "value": target}
            ]
            base = repository.write_and_commit(
                "scripts/ci/scope_policy.json",
                json.dumps(base_policy, indent=2) + "\n",
                "base policy",
            )
            policy_path = repository.path / "scripts/ci/scope_policy.json"
            policy_path.write_text(
                json.dumps(self.policy, indent=2) + "\n", encoding="utf-8"
            )
            introduced = repository.path / target
            introduced.parent.mkdir(parents=True, exist_ok=True)
            introduced.write_text("// routed by the head policy\n", encoding="utf-8")
            repository.run("git", "add", "--", "scripts/ci/scope_policy.json", target)
            repository.run(
                "git", "commit", "--quiet", "-m", "add routed path"
            )
            head = repository.run("git", "rev-parse", "HEAD").stdout.strip()
            manifest = repository.path / "focused-policy.json"
            result = subprocess.run([
                sys.executable, str(CLASSIFIER_PATH),
                "--policy", str(policy_path),
                "--event", "push", "--base-sha", base, "--head-sha", head,
                "--repository", "owner/repo", "--head-repository", "",
                "--pr-number", "0", "--manifest-out", str(manifest),
                "--github-output", str(repository.path / "output"),
                "--summary", str(repository.path / "summary.md"),
            ], cwd=repository.path, capture_output=True, text=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(document["mode"], "focused")
            self.assertEqual(document["schema"], "lmdj.ci-scope.v2")
            self.assertTrue((repository.path / "summary.md").is_file())

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

    def test_retired_queue_manifest_key_is_rejected(self):
        # The merge queue was retired (#1103) and release evidence never
        # admitted a `queue` key, so a manifest carrying one is not closed.
        manifest = self.classify(["docs/guide.md"])
        manifest["queue"] = {
            "ticket": "mq:123:1", "pr_number": 220,
            "base_sha": "a" * 40, "head_sha": "b" * 40,
        }
        with self.assertRaisesRegex(ValueError, "not closed"):
            self.module.validate_manifest(manifest, self.policy)

    def test_retired_queue_cli_arguments_are_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.module.main([
                    "--policy", "p", "--event", "workflow_dispatch",
                    "--base-sha", "a" * 40, "--head-sha", "b" * 40,
                    "--repository", "endaye/lmdj", "--head-repository", "endaye/lmdj",
                    "--pr-number", "0", "--manifest-out", "m", "--github-output", "o",
                    "--summary", "s", "--queue-ticket", "mq:123:1",
                ])

    def test_operator_dispatch_keeps_unconditional_full_for_release_evidence(self):
        # scripts/release.sh rejects focused and requested evidence, so the
        # operator's empty dispatch must stay the one way to produce full
        # evidence for an exact main SHA.
        manifest = self.classify(
            ["docs/guide.md"], event_name="workflow_dispatch"
        )
        self.assertEqual(manifest["mode"], "full")
        self.assertEqual(self.true_lanes(manifest), LANES)
        self.assertIn("full event: workflow_dispatch", manifest["reasons"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
