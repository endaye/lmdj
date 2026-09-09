#!/usr/bin/env python3
"""Contract tests for the focused main CI and reusable Portal topology."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCOPE_POLICY = REPO_ROOT / "scripts/ci/scope_policy.json"
MAIN_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
PORTAL_WORKFLOW = REPO_ROOT / ".github/workflows/architecture-portal.yml"
WEB_PROOF_ACTION = REPO_ROOT / ".github/actions/web-ci-proof/action.yml"

FORMAL_LANE_JOBS = (
    "docs-static",
    "portal",
    "ci-contract",
    "core-ubuntu",
    "core-asan",
    "core-coverage",
    "core-macos",
    "core-asan-macos",
    "web-toolchain-conformance",
    "web-runtime-host",
    "creator-web",
    "web-runtime-lab",
    "deploy-contract",
    "chameleon-lab",
    "package",
)
SUPPORT_JOBS = (
    "select-macos-runner",
    "macos-primary",
)
# Every job a self-hosted role may ever execute. Each one must already carry
# the closed trust condition, including while it is still Hosted, so that a
# later repository or routing change cannot open a self-hosted lane to an
# untrusted head before the Gate sees it.
SELF_HOSTED_JOBS = (
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
)
HOSTED_CONTROL_PLANE_JOBS = (
    "change-scope",
    "select-macos-runner",
    # Judges a self-test batch from `needs` and retains the verdict; runs the
    # control revision's scripts, never the target's, and must outlive the
    # pool it judges for the same reason batch verdict must.
    "batch-verdict",
)
# Hosted Ubuntu jobs that are not control plane: each republishes an already
# produced macOS result under its required check name and runs no workload.
MACOS_ADJUDICATOR_JOBS = (
    "core-macos",
    "core-asan-macos",
)
TRUST_CONDITION = "needs.change-scope.outputs.trusted-head == 'true'"
WEB_HEAVY_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-web-heavy]"
)
# Lanes cut over to the dedicated netcup `ci-web-heavy` role so far, mapped to
# the lane each one runs. The migration is proven one lane at a time, so this
# stays an exact set: an unreviewed extra `ci-web-heavy` route is a topology
# change, not a detail.
WEB_HEAVY_JOBS = {
    "web-toolchain-conformance": "web_toolchain",
    "creator-web": "creator",
    "web-runtime-host": "web_runtime_host",
    "web-runtime-lab": "web_runtime_lab",
}
# Cut-over jobs that do not go through the shared `web-ci-proof` action,
# mapped to the proof step each keeps instead. Web Runtime Lab never shared
# the emsdk/Playwright setup contract, so it has no `lane` or
# `install-system-deps` input to carry: its cutover changes where it runs and
# nothing about what it runs.
WEB_HEAVY_DIRECT_PROOFS = {
    "web-runtime-lab": "run: scripts/web-runtime-lab.sh test",
}
GENERAL_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general]"
)
# General Linux workload cut over to the dual-node general role, mapped to the
# manifest lane each guards. The role exists on both trusted hosts, so these
# jobs are the ones that can absorb either node's spare capacity. This stays
# an exact set for the same reason the Web set does: an unreviewed extra route
# is a topology change, not a detail.
GENERAL_JOBS = {
    "docs-static": "docs_static",
    "ci-contract": "ci_contract",
    "deploy-contract": "deploy_contract",
    "chameleon-lab": "chameleon_lab",
}
# The one general lane that runs as a reusable workflow. A `uses:` job cannot
# carry `runs-on`, so the caller holds only the lane guard and the trust
# condition and the role is declared on the called workflow's job.
GENERAL_REUSABLE_JOBS = ("portal",)
CORE_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-core]"
)
# The native Core workload, mapped to the manifest lane each guards. This role
# lives only on the shared Contabo host: the persistent native `ccache` and
# the preinstalled coverage toolchain are host state, not pool state. These
# four were the Linux runner selector's last consumers, so pinning the exact
# set is also what keeps the retired selector from being reintroduced for a
# fifth.
CORE_JOBS = {
    "core-ubuntu": "core_ubuntu",
    "core-asan": "core_asan",
    "core-coverage": "core_coverage",
    "package": "package",
}
RELEASE_HISTORY_CONSUMERS = (
    "deploy-contract",
    "core-ubuntu",
    "core-asan",
    "core-coverage",
    "macos-primary",
    "macos-fallback",
    "package",
)
RELEASE_NODE_CONSUMERS = (
    "deploy-contract",
    "package",
    "core-ubuntu",
    "core-asan",
    "core-coverage",
    "macos-primary",
    "macos-fallback",
)
FORMAL_RESULTS = FORMAL_LANE_JOBS + SUPPORT_JOBS
# Review is exclusively in pr-review.yml; Core CI has no non-lane reviewers.
GENERAL_ROLE_NON_LANE_JOBS = ("change-scope", "select-macos-runner",
                              "core-macos", "core-asan-macos", "batch-verdict")
HEAVY_JOBS = (
    "portal", "core-ubuntu", "package", "core-coverage", "core-asan",
)
HEAVY_LANES = {
    "portal": "portal",
    "core-ubuntu": "core_ubuntu",
    "package": "package",
    "core-coverage": "core_coverage",
    "core-asan": "core_asan",
}
FORMAL_RESULT_LANE_GUARDS = {
    "docs-static": {"docs_static"},
    "portal": {"portal"},
    "ci-contract": {"ci_contract"},
    "core-ubuntu": {"portal", "core_ubuntu"},
    "core-asan": {"portal", "core_ubuntu", "package", "core_coverage", "core_asan"},
    "core-coverage": {"portal", "core_ubuntu", "package", "core_coverage"},
    "core-macos": {"core_macos"},
    "core-asan-macos": {"core_macos"},
    "web-toolchain-conformance": {"web_toolchain"},
    "web-runtime-host": {"web_runtime_host"},
    "creator-web": {"creator"},
    "web-runtime-lab": {"web_runtime_lab"},
    "deploy-contract": {"deploy_contract"},
    "chameleon-lab": {"chameleon_lab"},
    "package": {"portal", "core_ubuntu", "package"},
    "select-macos-runner": {"core_macos"},
    "macos-primary": {"core_macos"},
}


class CiWorkflowTopologyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main_source = MAIN_WORKFLOW.read_text(encoding="utf-8")
        cls.portal_source = PORTAL_WORKFLOW.read_text(encoding="utf-8")
        cls.web_proof_source = WEB_PROOF_ACTION.read_text(encoding="utf-8")

    def workflow_job(self, job_name: str, *, portal: bool = False) -> str:
        source = self.portal_source if portal else self.main_source
        match = re.search(
            rf"^  {re.escape(job_name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:|\Z)",
            source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, f"workflow job is missing: {job_name}")
        assert match is not None
        return match.group("body")

    def event_block(self, source: str) -> str:
        match = re.search(
            r"^on:\n(?P<body>.*?)(?=^[a-z][a-z-]*:\n)",
            source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, "workflow event block is missing")
        assert match is not None
        return match.group("body")

    def job_needs(self, job_name: str) -> set[str]:
        job = self.workflow_job(job_name)
        match = re.search(
            r"^    needs: (?P<needs>\[[^\n]+\]|[a-z0-9-]+)$",
            job,
            flags=re.MULTILINE,
        )
        self.assertIsNotNone(match, f"workflow job has no static needs: {job_name}")
        assert match is not None
        raw = match.group("needs").strip("[]")
        return {value.strip() for value in raw.split(",") if value.strip()}

    def called_impact_step(self) -> str:
        match = re.search(
            r"^      - name: Check Pull Request documentation impact\n"
            r"(?P<body>        if: \$\{\{ inputs\.check_documentation_impact \}\}\n"
            r".*?)(?=^      - name:|\Z)",
            self.portal_source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, "called documentation-impact step is missing")
        assert match is not None
        return match.group("body")

    def test_portal_exposes_workflow_call_with_typed_inputs(self) -> None:
        expected = '''  workflow_call:
    inputs:
      check_documentation_impact:
        required: false
        type: boolean
        default: false
      base_sha:
        required: false
        type: string
        default: ""
      head_sha:
        required: false
        type: string
        default: ""
      pull_request_body:
        required: false
        type: string
        default: ""
'''
        self.assertIn(expected, self.portal_source)

    def test_portal_impact_check_uses_explicit_base_and_head_inputs(self) -> None:
        step = self.called_impact_step()
        self.assertIn("if: ${{ inputs.check_documentation_impact }}", step)
        self.assertIn("PORTAL_PR_BODY: ${{ inputs.pull_request_body }}", step)
        self.assertIn("PORTAL_BASE_SHA: ${{ inputs.base_sha }}", step)
        self.assertIn("PORTAL_HEAD_SHA: ${{ inputs.head_sha }}", step)
        self.assertIn(
            "run: npm --prefix apps/docs-site run check:impact", step
        )
        self.assertNotIn("github.event.pull_request.base.sha", step)
        self.assertNotIn("github.event.pull_request.head.sha", step)

    def test_docs_static_checks_whitespace_over_the_merge_base_range(self) -> None:
        """The whitespace check measures the change's own contribution.

        `resolved-base-sha` is the base branch tip at event time, so a two-dot
        range reports, in reverse, everything that landed on the base branch
        after the branch was cut. A line carrying trailing whitespace that the
        base branch *deleted* after the cut would then read as added here, and
        `--check` would fail a branch that never wrote it. Issue #539 tracks
        this range and `read_git_inventory` together;
        `tests/build/ci_change_scope_test.py` owns the git behaviour.
        """
        job = self.workflow_job("docs-static")
        self.assertIn('run: git diff --check "$BASE_SHA...$HEAD_SHA"', job)
        self.assertNotIn('git diff --check "$BASE_SHA" "$HEAD_SHA"', job)

    def test_portal_never_measures_a_two_dot_range_between_the_inputs(self) -> None:
        """The range belongs to the checkers, which measure it from the merge base.

        `base_sha` is the base branch tip at event time, so a two-dot range
        additionally reports, in reverse, everything that landed on the base
        branch after the branch was cut. Issue #531 is a branch that was merely
        behind inheriting portal pages it never touched. The workflow therefore
        computes no range at all: `apps/docs-site/test/changed-files.test.mjs`
        owns the behaviour, where a behind-base branch is expressible as a test.
        """
        self.assertNotRegex(
            self.portal_source,
            r'git diff[^\n]*"\$PORTAL_BASE_SHA"\s+"\$PORTAL_HEAD_SHA"',
        )
        self.assertNotIn("git diff", self.portal_source)

    def test_portal_reusable_job_keeps_fetch_depth_zero_node_22_and_full_check(self) -> None:
        self.assertIn("fetch-depth: 0", self.portal_source)
        self.assertIn('node-version: "22"', self.portal_source)
        self.assertIn("scripts/docs-site.sh install", self.portal_source)
        self.assertIn("scripts/docs-site.sh check", self.portal_source)

    def test_release_contract_consumers_checkout_complete_history_and_tags(self) -> None:
        for job_name in RELEASE_HISTORY_CONSUMERS:
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn("uses: actions/checkout@v6", job)
                self.assertIn("fetch-depth: 0", job)

    def test_release_contract_consumers_install_the_pinned_node_runtime(self) -> None:
        for job_name in RELEASE_NODE_CONSUMERS:
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn("uses: actions/setup-node@v6", job)
                self.assertIn('node-version: "22"', job)

    def test_portal_does_not_use_checks_api_or_cross_run_polling(self) -> None:
        for forbidden in ("api.github.com", "/check-runs", "gh api"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.portal_source)
        self.assertNotRegex(self.portal_source, r"(?im)^\s*(while|until)\b")

    def test_main_workflow_has_no_workflow_level_paths_filter(self) -> None:
        events = self.event_block(self.main_source)
        self.assertNotRegex(events, r"(?m)^\s+paths(?:-ignore)?:")

    def test_product_ci_has_only_read_only_execution_permissions(self) -> None:
        directives = "\n".join(line for line in self.main_source.splitlines()
                               if not line.lstrip().startswith("#"))
        self.assertNotRegex(directives, r"(?m)^\s+(?:pull-requests|issues):",
                            "why: retired review grants prevent least-privilege reuse; remedy: keep review authority in pr-review.yml")
        self.assertNotRegex(directives, r"(?m)^\s+[a-z-]+: write$",
                            "why: product execution must not write repository state; remedy: isolate publishers from Core CI")

    def test_product_ci_has_no_retired_review_jobs(self) -> None:
        for job in ("select-review-backend", "advisory-review", "grok-review"):
            self.assertNotIn(f"  {job}:\n", self.main_source,
                             "why: retired review jobs still expand the product DAG; remedy: use the independent PR Review entry")

    def test_product_ci_has_no_pr_or_ordinary_push_trigger(self) -> None:
        events = self.event_block(self.main_source)
        self.assertNotRegex(events, r"(?m)^  (?:pull_request|pull_request_target|push):",
                            "why: product verification is independent of optimistic merges; remedy: keep only daily/manual entries")

    def test_self_test_events_have_independent_non_cancelling_admission(self) -> None:
        concurrency = re.search(
            r"^concurrency:\n(?P<body>.*?)(?=^[a-z][a-z-]*:\n)",
            self.main_source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(concurrency, "workflow concurrency block is missing")
        assert concurrency is not None
        body = concurrency.group("body")
        self.assertIn("format('core-ci-self-test-{0}', github.run_id)", body)
        self.assertIn("cancel-in-progress: false", body)

    def test_change_scope_has_three_minute_limit_zero_dependency_install_and_live_pr_read(self):
        job = self.workflow_job("change-scope")
        for text in (GENERAL_ROLE, "timeout-minutes: 3", "fetch-depth: 0", "batch_execution.py prepare"):
            self.assertIn(text, job)
        for forbidden in (r"\bnpm\b", r"\bpip(?:3)?\b", r"\bcmake\b", "actions/runners", "SELF_HOSTED_RUNNER_READ_TOKEN"):
            self.assertNotRegex(job, forbidden)
        self.assertNotIn("pull-requests:", self.main_source)

    def test_control_plane_uses_the_dual_node_general_role(self) -> None:
        """Control work can use either trusted general host, never paid Linux."""
        for job_name in HOSTED_CONTROL_PLANE_JOBS:
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(GENERAL_ROLE, job)
                self.assertNotIn("ci-web-heavy", job)
                self.assertNotIn("ci-core", job)
        # macOS adjudication also uses the general role; only actual Mac recovery is paid.
        hosted = re.findall(r"(?m)^    runs-on: ubuntu-24\.04$", self.main_source)
        self.assertEqual(
            len(hosted),
            0,
        )

    def test_change_scope_publishes_trusted_head_from_event_or_queue_ticket(self):
        job = self.workflow_job("change-scope")
        self.assertIn("trusted-head: ${{ steps.batch.outputs.trusted-head }}", job)
        self.assertIn("batch_execution.py prepare", job)
        self.assertNotIn("inputs.queue_ticket", job)

    def test_every_self_hosted_job_requires_a_trusted_head(self) -> None:
        policy = json.loads(SCOPE_POLICY.read_text(encoding="utf-8"))
        self.assertEqual(tuple(policy["self_hosted_jobs"]), SELF_HOSTED_JOBS)
        for job_name in SELF_HOSTED_JOBS:
            with self.subTest(job=job_name):
                self.assertIn(TRUST_CONDITION, self.workflow_job(job_name))

    def test_control_plane_and_macos_jobs_are_outside_the_trust_condition(self) -> None:
        for job_name in (
            *HOSTED_CONTROL_PLANE_JOBS, "macos-primary", "macos-fallback",
            "core-macos", "core-asan-macos",
        ):
            with self.subTest(job=job_name):
                self.assertNotIn(TRUST_CONDITION, self.workflow_job(job_name))

    def test_every_formal_lane_depends_directly_on_change_scope(self) -> None:
        for job_name in FORMAL_LANE_JOBS:
            with self.subTest(job=job_name):
                self.assertIn("change-scope", self.job_needs(job_name))
        for job_name in SUPPORT_JOBS:
            with self.subTest(support=job_name):
                self.assertIn("change-scope", self.job_needs(job_name))

    def test_formal_result_jobs_have_exact_manifest_lane_guards(self) -> None:
        self.assertEqual(set(FORMAL_RESULT_LANE_GUARDS), set(FORMAL_RESULTS))
        for job_name, expected_lanes in FORMAL_RESULT_LANE_GUARDS.items():
            with self.subTest(job=job_name):
                self.assertEqual(
                    set(re.findall(
                        r"lanes\.([a-z_]+)", self.workflow_job(job_name)
                    )),
                    expected_lanes,
                )

    def test_cut_over_lanes_use_the_static_netcup_role_not_the_selector(self) -> None:
        """All four Web lanes are cut over, by role and not by selector.

        `select-ubuntu-runner` resolves once per run and can fall back to paid
        Ubuntu. The dedicated role must queue instead, so each cut-over lane
        carries a literal label set and keeps `needs: change-scope` alone.
        Pinning the exact `ci-web-heavy` job set keeps a later lane from
        inheriting the route without its own proof run.
        """
        for job_name, lane in WEB_HEAVY_JOBS.items():
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertEqual(self.job_needs(job_name), {"change-scope"})
                self.assertIn(WEB_HEAVY_ROLE, job)
                self.assertNotIn("runs-on: ubuntu-24.04", job)
                self.assertNotIn("select-ubuntu-runner", job)
                self.assertIn(TRUST_CONDITION, job)
                if job_name in WEB_HEAVY_DIRECT_PROOFS:
                    self.assertIn(WEB_HEAVY_DIRECT_PROOFS[job_name], job)
                    self.assertNotIn("web-ci-proof", job)
                    self.assertNotIn("install-system-deps", job)
                else:
                    self.assertIn(f"lane: {lane}", job)
                    self.assertIn('install-system-deps: "false"', job)
        self.assertEqual(
            self.main_source.count("ci-web-heavy"), len(WEB_HEAVY_JOBS)
        )

    def test_general_workload_lanes_use_the_dual_node_role_not_the_selector(self) -> None:
        """The short Linux jobs cut over as one group, by role not by selector.

        `select-ubuntu-runner` resolves once per run and can fall back to paid
        Ubuntu; the static role queues instead. These four are short, share no
        toolchain contract and carry no per-lane risk, so the reviewable unit
        is the group rather than the lane. Pinning the exact job set still
        keeps a later lane from inheriting the route without review.
        """
        for job_name, lane in GENERAL_JOBS.items():
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertEqual(self.job_needs(job_name), {"change-scope"})
                self.assertIn(GENERAL_ROLE, job)
                self.assertNotIn("runs-on: ubuntu-24.04", job)
                self.assertNotIn("select-ubuntu-runner", job)
                self.assertIn(TRUST_CONDITION, job)
                self.assertEqual(
                    set(re.findall(r"lanes\.([a-z_]+)", job)), {lane}
                )
        self.assertEqual(
            self.main_source.count("ci-general"),
            len(GENERAL_JOBS) + len(GENERAL_ROLE_NON_LANE_JOBS),
            "why: every literal ci-general must be a reviewed lane or a named "
            "non-lane job; remedy: extend GENERAL_JOBS or "
            "GENERAL_ROLE_NON_LANE_JOBS deliberately",
        )

    def test_main_is_swept_daily_and_the_sweep_names_itself(self):
        events = self.event_block(self.main_source)
        self.assertNotIn("schedule:", events)
        self.assertNotIn("workflow_dispatch:", events)
        self.assertIn("workflow_call:", events)

    def test_release_compatibility_scope_and_gate_remain_real_producer_jobs(self):
        self.assertNotIn("\n  pr-gate:\n", self.main_source)
        self.assertIn("batch_execution.py prepare", self.workflow_job("change-scope"))
        self.assertIn("batch_execution.from_needs", self.workflow_job("batch-verdict"))

    def test_the_policy_does_not_claim_main_always_runs_full(self) -> None:
        """The sweep's premise and the policy must not contradict each other.

        A docs-only push classifies focused (1 of 14 lanes); the sentence that
        said `main` always runs the full manifest predates the focused-`main`
        decision and, left alone, would have this file asserting both.
        """
        policy = (REPO_ROOT / "docs/quality/core-test-policy.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "`main` and manual dispatch always run the full manifest", policy,
            "why: a docs-only push classifies focused, which is what #543 exists "
            "for; remedy: describe push classification as exact-range",
        )

    def test_portal_role_is_declared_on_the_called_workflow(self) -> None:
        """Portal routes where a reusable workflow can actually be routed.

        The caller is a `uses:` job, which GitHub does not allow to declare
        `runs-on`, so the role has to live on the called workflow's own job.
        That workflow is `workflow_call`-only and has exactly one caller, so
        placing the role there reroutes Portal and nothing else.
        """
        for job_name in GENERAL_REUSABLE_JOBS:
            with self.subTest(job=job_name):
                caller = self.workflow_job(job_name)
                self.assertEqual(self.job_needs(job_name), {"change-scope"})
                self.assertIn(TRUST_CONDITION, caller)
                self.assertNotIn("runs-on:", caller)
        called = self.workflow_job("portal", portal=True)
        self.assertIn(GENERAL_ROLE, called)
        self.assertNotIn("ubuntu-24.04", self.portal_source)
        self.assertEqual(self.portal_source.count("ci-general"), 1)
        events = self.event_block(self.portal_source)
        self.assertNotRegex(
            events, r"(?m)^  (?:pull_request|push|schedule|workflow_dispatch):"
        )

    def test_ci_contract_keeps_no_container_action_on_the_trusted_role(self) -> None:
        """Nothing in CI may require the Docker socket that runs production.

        The CI-only host has no daemon and the shared host's runner users are
        outside the `docker` group, both on purpose. actionlint stays at the
        same version but arrives as a digest-pinned release archive, which is
        a stricter pin than the mutable tag it replaces.
        """
        self.assertNotIn("docker://", self.main_source)
        self.assertNotIn("docker://", self.portal_source)
        self.assertNotIn("docker://", self.web_proof_source)

    def test_web_runtime_host_keeps_its_exact_emscripten_identity_check(self) -> None:
        """Changing where the lane runs must not change what it proves.

        The dedicated role provisions a persistent toolchain, which is exactly
        the condition under which a silently different Emscripten would go
        unnoticed. The lane therefore keeps verifying the pinned compiler
        identity before its proof, and keeps rehydrating the LFS audio
        fixtures first, so a role-provisioned host cannot pass on stand-in
        inputs.
        """
        self.assertIn(
            "web_runtime_host) python3 tools/web-runtime/verify_emscripten.py"
            " && scripts/web-runtime-host.sh proof ;;",
            self.web_proof_source,
        )
        job = self.workflow_job("web-runtime-host")
        hydration = "git lfs checkout -- tests/fixtures/audio"
        self.assertIn("lfs: true", job)
        self.assertIn(hydration, job)
        self.assertLess(
            job.index(hydration),
            job.index("uses: ./.github/actions/web-ci-proof"),
        )

    def test_web_runtime_lab_keeps_its_own_stable_proof_steps(self) -> None:
        """The Lab cutover moves the lane, it does not fold it into the others.

        Web Runtime Lab was deliberately left out of the shared `web-ci-proof`
        action because it does not share the emsdk/Playwright setup contract:
        it is a short, stable Node/Python suite that installs nothing on the
        host. Rerouting it to the role is not an invitation to normalize it
        onto the heavy path, nor to inherit web-runtime-host's 75-minute hang
        detector, which exists for a lane that is two orders of magnitude
        longer.
        """
        job = self.workflow_job("web-runtime-lab")
        self.assertNotIn("uses: ./.github/actions/web-ci-proof", job)
        self.assertNotIn("timeout-minutes", job)
        self.assertNotIn("lfs: true", job)
        for step in (
            "uses: actions/checkout@v6",
            'python-version: "3.11"',
            'node-version: "22"',
            "- run: scripts/web-runtime-lab.sh test",
        ):
            with self.subTest(step=step):
                self.assertIn(step, job)

    def test_creator_no_longer_needs_web_toolchain_or_core(self) -> None:
        job = self.workflow_job("creator-web")
        self.assertEqual(self.job_needs("creator-web"), {"change-scope"})
        self.assertNotIn("web-toolchain-conformance", job)
        self.assertNotIn("core-ubuntu", job)
        self.assertIn(WEB_HEAVY_ROLE, job)

    def test_the_linux_runner_selector_no_longer_exists(self) -> None:
        """The guard shrank to nothing, so the job goes rather than idles.

        A selector with no consumers would still be a live route: it resolves
        once per run and its hosted branch could be reconnected by a single
        `needs`. Removing the job, its outputs, its Runner API probe and its
        use of the runner-read token is what makes automatic Hosted Linux
        capacity unreachable instead of merely unused.
        """
        for absent in (
            "select-ubuntu-runner",
            "Select Ubuntu runner",
            "no online trusted self-hosted runner is available",
        ):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, self.main_source)
        policy = json.loads(SCOPE_POLICY.read_text(encoding="utf-8"))
        for lane, jobs in policy["lane_jobs"].items():
            with self.subTest(lane=lane):
                self.assertNotIn("select-ubuntu-runner", jobs)

    def test_macos_selector_runs_only_when_core_macos_is_selected(self) -> None:
        job = self.workflow_job("select-macos-runner")
        self.assertEqual(self.job_needs("select-macos-runner"), {"change-scope"})
        self.assertEqual(set(re.findall(r"lanes\.([a-z_]+)", job)), {"core_macos"})
        self.assertIn("if: ${{ !cancelled()", job)

    def test_portal_is_same_run_reusable_job_and_batch_verdict_needs_it(self):
        portal = self.workflow_job("portal")
        for text in ("uses: ./.github/workflows/architecture-portal.yml", "check_documentation_impact:", "base_sha:", "head_sha:", "pull_request_body:"):
            self.assertIn(text, portal)
        self.assertIn("portal", self.job_needs("batch-verdict"))

    def test_batch_verdict_has_every_formal_lane_in_static_needs_and_runs_with_always(self):
        job = self.workflow_job("batch-verdict")
        self.assertEqual(self.job_needs("batch-verdict"), {"change-scope", "macos-fallback", "nightly-tsan", "nightly-stress", *FORMAL_RESULTS})
        self.assertIn("always()", job)
        self.assertIn("NEEDS_JSON: ${{ toJSON(needs) }}", job)
        self.assertIn("batch_execution.from_needs", job)

    def test_no_job_depends_on_an_always_false_admission_gate(self) -> None:
        """Heavy lanes must not depend on a dead batch-mode admission job.

        `change-scope` hard-codes batch mode true, so a `batch-mode == 'false'`
        condition can never admit a job. This catches reintroducing either the
        retired gate itself or a new always-false prerequisite of a lane.
        """
        directives = "\n".join(
            line for line in self.main_source.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertNotIn("pre-heavy-gate", directives)
        self.assertNotIn(
            "batch-mode == 'false'", directives,
            "why: a batch-mode false admission condition is unreachable; "
            "remedy: remove the dead gate and keep only live lane selection",
        )
        for job_name in re.findall(r"^  ([a-z0-9-]+):\n", self.main_source, re.MULTILINE):
            body = self.workflow_job(job_name)
            needs_match = re.search(r"^    needs: (?P<needs>\[[^\n]+\]|[a-z0-9-]+)$", body, re.MULTILINE)
            if not needs_match:
                continue
            needs = needs_match.group("needs")
            self.assertNotRegex(
                body,
                r"batch-mode == 'false'",
                msg=f"why: {job_name} has an unreachable admission condition; "
                    "remedy: remove the dead prerequisite and condition",
            )
            self.assertNotIn(
                "pre-heavy-gate", needs,
                msg=f"why: {job_name} depends on a retired dead admission job; "
                    "remedy: keep only live product dependencies",
            )

    def test_heavy_jobs_form_the_sparse_predecessor_chain(self) -> None:
        for index, job_name in enumerate(HEAVY_JOBS):
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                earlier = HEAVY_JOBS[:index]
                self.assertEqual(
                    self.job_needs(job_name),
                    {"change-scope", *earlier},
                )
                self.assertIn("needs.change-scope.outputs.self-test == 'true'", job)
                self.assertIn(TRUST_CONDITION, job)
                for predecessor in earlier:
                    self.assertIn(
                        "(needs.change-scope.outputs.self-test == 'true' || !fromJSON(needs.change-scope.outputs.manifest).lanes."
                        f"{HEAVY_LANES[predecessor]} || needs.{predecessor}.result == 'success')",
                        job,
                    )
                for later in HEAVY_JOBS[index + 1:]:
                    self.assertNotIn(later, self.job_needs(job_name))
        portal = self.workflow_job("portal")
        self.assertIn("uses: ./.github/workflows/architecture-portal.yml", portal)
        self.assertNotIn("runs-on:", portal)

    def test_native_core_lanes_use_the_static_core_role_not_the_selector(self) -> None:
        """The last four Linux lanes move by role, retiring the selector.

        Ubuntu Core, Linux ASan, Coverage and Core package were the only jobs
        still resolving `runs-on` from a once-per-run API snapshot that could
        buy paid Ubuntu. Naming the literal label set makes them queue on a
        saturated or absent role rather than diverting a whole manifest to paid
        runners. Each retains direct Change Scope and trust dependencies, then
        waits only for every earlier native-heavy predecessor. The exact job
        set keeps a later lane from inheriting the route without its own proof
        run.
        """
        for job_name, lane in CORE_JOBS.items():
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertEqual(
                    self.job_needs(job_name),
                    {"change-scope", *HEAVY_JOBS[:HEAVY_JOBS.index(job_name)]},
                )
                self.assertIn(CORE_ROLE, job)
                self.assertNotIn("runs-on: ubuntu-24.04", job)
                self.assertNotIn("select-ubuntu-runner", job)
                self.assertIn(TRUST_CONDITION, job)
                self.assertEqual(
                    set(re.findall(r"lanes\.([a-z_]+)", job)),
                    {HEAVY_LANES[heavy] for heavy in HEAVY_JOBS[:HEAVY_JOBS.index(job_name) + 1]},
                )
        self.assertEqual(self.main_source.count("ci-core"), len(CORE_JOBS))

    def test_scope_and_gate_timeouts_are_three_minutes_and_lane_limits_match_policy(self) -> None:
        expected = {
            "change-scope": 3,
            "batch-verdict": 5,
            "docs-static": 10,
            "ci-contract": 10,
            "deploy-contract": 15,
            "chameleon-lab": 10,
            "package": 35,
            "core-ubuntu": 30,
            "core-asan": 35,
            "core-coverage": 35,
            "web-toolchain-conformance": 35,
            # Calibrated to the trusted pool, which runs this lane about 2.2x
            # slower than GitHub-hosted (40 min observed, one cancellation at
            # exactly 45, against 16-19 min hosted).
            "web-runtime-host": 75,
            "creator-web": 35,
            "macos-primary": 30,
        }
        for job_name, minutes in expected.items():
            with self.subTest(job=job_name):
                self.assertIn(
                    f"timeout-minutes: {minutes}", self.workflow_job(job_name)
                )
        self.assertIn("timeout-minutes: 15", self.workflow_job("portal", portal=True))

    def test_scope_manifest_is_uploaded_and_summarized(self):
        job = self.workflow_job("batch-verdict")
        for text in ("uses: actions/upload-artifact@v4", "artifact=batch-verdict-", "execution.json", "needs.json", "verdict.json", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"):
            self.assertIn(text, job)
        self.assertNotIn("overwrite: true", job)

    def test_scope_artifact_retention_is_the_release_evidence_lifetime(self):
        job = self.workflow_job("batch-verdict")
        self.assertIn("retention-days: 30", job)
        self.assertIn("if-no-files-found: error", job)
        self.assertIn("path: ${{ runner.temp }}/batch-verdict-", job)

    def test_package_lane_retains_its_digest_evidence(self) -> None:
        """The archive dies with the runner; its digests must outlive it.

        Release assets are rebuilt and signed by `release.sh prepare` on the
        operator machine. Without these few kilobytes there is no digest-level
        cross-check between what CI proved packageable and what an operator
        later ships, and no baseline for multi-platform distribution. This is
        comparison evidence, not a release input, so it is deliberately not
        the manifest `tools/release/ci_evidence.py` reads.
        """
        job = self.workflow_job("package")
        self.assertIn("uses: actions/upload-artifact@v4", job)
        self.assertIn("name: package-evidence-${{", job)
        self.assertIn("build/core/dist/*.build-manifest.json", job)
        self.assertIn("build/core/dist/*.zip.sha256", job)
        self.assertNotIn("build/core/dist/*.zip\n", job)
        self.assertIn("if-no-files-found: error", job)
        self.assertIn("retention-days: 14", job)

    def test_package_lane_states_its_fixture_and_dependency_assumption(self) -> None:
        """This lane skips dependency verification and fixture generation.

        Both are safe only because `scripts/core.sh package` runs the unit and
        component tiers against LFS-checked fixtures. A generated fixture
        entering either tier invalidates that silently, so the assumption is
        stated where the next editor of the job will read it.
        """
        job = self.workflow_job("package")
        self.assertIn("verify-core-dependencies.sh", job)
        self.assertIn("generated fixture", job)
        self.assertIn("unit and component", job)

    def test_push_classification_uses_the_exact_before_range(self):
        job = self.workflow_job("change-scope")
        self.assertIn("resolved-base-sha: ${{ steps.batch.outputs.base }}", job)
        self.assertIn("resolved-head-sha: ${{ steps.batch.outputs.target }}", job)
        self.assertNotIn("github.event.before", job)

    def test_dispatch_input_documents_the_explicit_full_evidence_path(self):
        events = self.event_block(self.main_source)
        self.assertNotIn("workflow_dispatch:", events)
        self.assertIn("batch_request:", events)

    def test_no_job_uses_retry_for_semantic_workloads(self) -> None:
        semantic_source = self.main_source + self.web_proof_source
        self.assertNotRegex(semantic_source, r"(?im)^\s+uses: .*retry")
        self.assertNotRegex(
            semantic_source,
            r"(?im)^\s*(?:for|while|until)\s+.*(?:attempt|retry)",
        )
        semantic_commands = (
            "scripts/core.sh proof",
            "scripts/core.sh configure asan",
            "scripts/core.sh build asan",
            "scripts/core.sh test asan full",
            "scripts/core.sh test asan stress",
            "scripts/core-coverage.sh check",
            "scripts/web-toolchain-conformance.sh proof",
            "scripts/web-runtime-host.sh proof",
            "scripts/creator-web.sh proof",
            "scripts/web-runtime-lab.sh test",
            "scripts/chameleon-lab.sh test",
            "scripts/core.sh package",
        )
        for command in semantic_commands:
            with self.subTest(command=command):
                self.assertEqual(semantic_source.count(command), 1)

    def test_architecture_portal_no_longer_has_duplicate_pr_or_main_triggers(self) -> None:
        events = self.event_block(self.portal_source)
        self.assertIn("workflow_call:", events)
        self.assertNotRegex(events, r"(?m)^  (?:pull_request|push):")
        self.assertNotRegex(self.portal_source, r"(?m)^concurrency:")
        self.assertNotIn("cancel-in-progress:", self.portal_source)


if __name__ == "__main__":
    unittest.main()
