#!/usr/bin/env python3
"""Contract tests for the trusted self-hosted CI routing topology."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
PORTAL_WORKFLOW = REPO_ROOT / ".github/workflows/architecture-portal.yml"
ACTIONLINT_CONFIG = REPO_ROOT / ".github/actionlint.yaml"
ACTION = REPO_ROOT / ".github/actions/macos-core-gates/action.yml"
ASSERT_GATE = REPO_ROOT / ".github/scripts/assert-macos-gate-result.sh"
WEB_HEAVY_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-web-heavy]"
)
# Lanes cut over to the dedicated netcup role, mapped to the lane each one
# runs. Cutting over must not silently reroute a lane's workload.
WEB_HEAVY_LANES = {
    "web-toolchain-conformance": "web_toolchain",
    "creator-web": "creator",
    "web-runtime-host": "web_runtime_host",
    "web-runtime-lab": "web_runtime_lab",
}
# Cut-over jobs that do not go through the shared `web-ci-proof` action,
# mapped to the proof step each keeps instead. Web Runtime Lab never shared
# the emsdk/Playwright setup contract, so it names no `lane` input and has no
# system dependencies to suppress.
WEB_HEAVY_DIRECT_PROOFS = {
    "web-runtime-lab": "run: scripts/web-runtime-lab.sh test",
}
GENERAL_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general]"
)
# General Linux workload cut over to the dual-node general role, mapped to the
# manifest lane each job guards. This role exists on both trusted hosts, so
# unlike the Web role it absorbs either node's spare capacity. `portal` is
# absent because it is a reusable-workflow call: a `uses:` job cannot carry
# `runs-on`, so its runner is declared on the called workflow's own job.
GENERAL_JOBS = {
    "docs-static": "docs_static",
    "ci-contract": "ci_contract",
    "deploy-contract": "deploy_contract",
    "chameleon-lab": "chameleon_lab",
}
# None of these jobs shares a composite action, so each keeps its own proof
# path verbatim. Pinning the command per job keeps the cutover a change of
# where they run and not of what they run.
# Reviews use a separate workflow and are not product jobs on this role.
GENERAL_ROLE_NON_LANE_JOBS = ("change-scope", "pre-heavy-gate", "select-macos-runner",
                              "core-macos", "core-asan-macos", "batch-verdict")
GENERAL_PROOFS = {
    "docs-static": 'run: git diff --check "$BASE_SHA...$HEAD_SHA"',
    "ci-contract": "run: python3 -m unittest discover -s tests/build -p 'ci_*_test.py'",
    "deploy-contract": (
        "run: python3 apps/web-runtime-host/test/deploy_command_test.py --shards 4"
    ),
    "chameleon-lab": "run: scripts/chameleon-lab.sh test",
}
CORE_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-core]"
)
# The native Core workload, mapped to the manifest lane each job guards. This
# role lives only on the shared Contabo host, which is where the persistent
# native `ccache` and the preinstalled coverage toolchain live, so unlike the
# general role it cannot absorb the CI-only node's spare capacity. Cutting
# these four over retires the Linux runner selector outright.
CORE_JOBS = {
    "core-ubuntu": "core_ubuntu",
    "core-asan": "core_asan",
    "core-coverage": "core_coverage",
    "package": "package",
}
# Every literal self-hosted label the workflows name. actionlint rejects a
# `runs-on` label it has never been told about, so an unregistered role turns
# the CI contract lane red rather than the route it describes.
REGISTERED_RUNNER_LABELS = (
    "lmdj-linux",
    "lmdj-linux-pool",
    "ci-web-heavy",
    "ci-general",
    "ci-core",
)
HOSTED_CONTROL_PLANE_JOBS = (
    "change-scope",
    "batch-verdict",
    "select-macos-runner",
)


class CiRunnerFallbackTest(unittest.TestCase):
    def workflow_job(self, job_name: str) -> str:
        source = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(
            rf"^  {re.escape(job_name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:|\Z)",
            source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, f"workflow job is missing: {job_name}")
        assert match is not None
        return match.group("body")

    def action_step(self, step_name: str) -> str:
        source = ACTION.read_text(encoding="utf-8")
        match = re.search(
            rf"^    - name: {re.escape(step_name)}\n"
            r"(?P<body>.*?)(?=^    - name:|\Z)",
            source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, f"composite action step is missing: {step_name}")
        assert match is not None
        return match.group("body")

    def run_gate(
        self,
        gate: str,
        **environment: str,
    ) -> subprocess.CompletedProcess[str]:
        process_environment = os.environ.copy()
        process_environment.update(environment)
        return subprocess.run(
            ["bash", str(ASSERT_GATE), gate],
            cwd=REPO_ROOT,
            env=process_environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_workflow_preserves_required_check_names_and_routes_mac_gates(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: core (ubuntu-latest)", source)
        self.assertIn("name: core (macos-latest)", source)
        self.assertIn("name: core-asan-macos", source)
        self.assertIn("secrets.SELF_HOSTED_RUNNER_READ_TOKEN", source)
        self.assertIn("endaye-mbp-m1", source)
        self.assertIn("needs.select-macos-runner.outputs.runner", source)
        self.assertIn("needs.macos-primary.outputs.completed != 'true'", source)
        self.assertIn("timeout-minutes: 30", source)
        self.assertIn("github.event.pull_request.head.repo.full_name", source)
        self.assertEqual(source.count("Runner selection candidates:"), 1)
        self.assertEqual(source.count("Runner selection inventory:"), 1)
        self.assertEqual(source.count("TARGET_RUNNER_NAME:"), 1)
        self.assertNotRegex(source, r"(?m)^\s+RUNNER_NAME:")
        self.assertNotIn('"$RUNNER_NAME"', source)

    def test_native_core_workload_is_pinned_to_the_shared_host_core_role(self) -> None:
        """The last four Linux lanes route by role, so nothing resolves them.

        Ubuntu Core, Linux ASan, Coverage and Core package were the Linux
        runner selector's only remaining consumers. They name the literal
        label set instead, so a saturated or absent role queues them rather
        than diverting the run to paid runners, which is why each keeps
        `needs: change-scope` alone and carries the closed trust condition
        itself: the selector's fork branch is no longer in their path.
        """
        for job_name, lane in CORE_JOBS.items():
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(CORE_ROLE, job)
                self.assertIn("needs: change-scope", job)
                self.assertNotIn("select-ubuntu-runner", job)
                self.assertNotIn("runs-on: ubuntu-24.04", job)
                self.assertIn(
                    "needs.change-scope.outputs.trusted-head == 'true'", job
                )
                self.assertIn(f"lanes.{lane}", job)
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(source.count("ci-core"), len(CORE_JOBS))

    def test_no_linux_workload_can_reach_the_hosted_fallback_any_more(self) -> None:
        """The Linux selector is gone, not merely unused.

        While the job existed, one API snapshot could still decide that an
        entire manifest be bought from GitHub-hosted Ubuntu. Deleting the job
        removes the fallback route itself: its result key, its Runner API
        probe and its use of the runner-read token all leave with it, and the
        only remaining `ubuntu-24.04` workloads are the Hosted control plane
        and the untouched macOS lane.
        """
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("select-ubuntu-runner", source)
        self.assertNotIn("Select Ubuntu runner", source)
        self.assertEqual(source.count("api.github.com/repos"), 1)
        self.assertEqual(
            source.count("secrets.SELF_HOSTED_RUNNER_READ_TOKEN"), 1
        )
        macos_selector = self.workflow_job("select-macos-runner")
        self.assertIn("actions/runners", macos_selector)
        self.assertIn(
            "RUNNER_READ_TOKEN: ${{ secrets.SELF_HOSTED_RUNNER_READ_TOKEN }}",
            macos_selector,
        )

    def test_cut_over_web_lanes_are_pinned_to_the_netcup_web_heavy_role(self) -> None:
        """All four Web lanes now use the CI-only netcup node.

        The role label set is static, not selector-resolved. `ci-web-heavy`
        exists only on the dedicated node, so a busy or absent role queues a
        cut-over lane instead of diverting it to paid runners, which is why
        these jobs keep their own `needs: change-scope` rather than joining the
        `select-ubuntu-runner` consumers. Trust therefore cannot come from the
        selector's fork branch and must stay on each job itself.
        """
        for job_name, lane in WEB_HEAVY_LANES.items():
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(WEB_HEAVY_ROLE, job)
                self.assertIn("needs: change-scope", job)
                self.assertNotIn("needs: select-ubuntu-runner", job)
                self.assertNotIn("needs.select-ubuntu-runner.outputs.runner", job)
                self.assertNotIn("runs-on: ubuntu-24.04", job)
                self.assertIn(
                    "needs.change-scope.outputs.trusted-head == 'true'", job
                )
                if job_name in WEB_HEAVY_DIRECT_PROOFS:
                    self.assertIn(WEB_HEAVY_DIRECT_PROOFS[job_name], job)
                    self.assertNotIn("web-ci-proof", job)
                else:
                    self.assertIn(f"lane: {lane}", job)
                    self.assertIn('install-system-deps: "false"', job)

    def test_general_linux_workload_is_pinned_to_the_dual_node_general_role(self) -> None:
        """The short Linux jobs move as one group, not lane by lane.

        The Web cutover was staged because each of those lanes is long, heavy
        and individually risky. These four are short, cheap and share no
        toolchain contract, so the reviewable unit is the group. The label set
        is literal rather than selector-resolved, so a busy or absent role
        queues them instead of diverting them to paid runners, which is why
        each keeps its own `needs: change-scope` and carries the closed trust
        condition itself.
        """
        for job_name, lane in GENERAL_JOBS.items():
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(GENERAL_ROLE, job)
                self.assertIn("needs: change-scope", job)
                self.assertNotIn("select-ubuntu-runner", job)
                self.assertNotIn("runs-on: ubuntu-24.04", job)
                self.assertIn(
                    "needs.change-scope.outputs.trusted-head == 'true'", job
                )
                self.assertIn(f"lanes.{lane}", job)
                self.assertIn(GENERAL_PROOFS[job_name], job)
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(
            source.count("ci-general"),
            len(GENERAL_JOBS) + len(GENERAL_ROLE_NON_LANE_JOBS),
            "why: every literal ci-general in ci.yml must be a reviewed lane or a "
            "named non-lane job, or a later lane inherits the route unreviewed; "
            "remedy: add the job to GENERAL_JOBS with its lane, or to "
            "GENERAL_ROLE_NON_LANE_JOBS with its reason",
        )

    def test_portal_role_is_declared_where_a_called_workflow_can_carry_it(self) -> None:
        """A `uses:` job has no `runs-on` to route, so the callee owns it.

        Portal is the one general lane that runs as a reusable workflow. The
        caller therefore keeps only the lane guard and the trust condition,
        and the role belongs on the called workflow's job. That workflow has a
        single `workflow_call` trigger and a single caller, so moving it does
        not silently reroute anything else.
        """
        caller = self.workflow_job("portal")
        self.assertIn("uses: ./.github/workflows/architecture-portal.yml", caller)
        self.assertNotIn("runs-on:", caller)
        self.assertIn(
            "needs.change-scope.outputs.trusted-head == 'true'", caller
        )
        called = PORTAL_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(GENERAL_ROLE, called)
        self.assertNotIn("ubuntu-24.04", called)
        self.assertEqual(called.count("ci-general"), 1)

    def test_control_plane_uses_contabo_separate_from_heavy_executors(self) -> None:
        """Control availability is independent of Netcup, not of all self-hosts."""
        for job_name in HOSTED_CONTROL_PLANE_JOBS:
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn("runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general, contabo]", job)
                self.assertNotIn("ci-web-heavy", job)
                self.assertNotIn("ci-core", job)

    def test_ci_contract_lints_with_a_checksum_pinned_binary_not_a_container(self) -> None:
        """The trusted Linux role cannot run a Docker container action.

        The CI-only host has no Docker daemon and the runner users on the
        shared host are outside the `docker` group, both deliberately: CI must
        not be able to reach the socket that runs production. A container
        action was also a weaker pin than it looked, because a Docker tag is
        mutable and names a version rather than an artifact. The release
        archive is pinned by digest instead and the check fails closed.
        """
        job = self.workflow_job("ci-contract")
        self.assertNotIn("docker://", job)
        self.assertIn("ACTIONLINT_VERSION: 1.7.12", job)
        self.assertIn(
            "ACTIONLINT_SHA256: "
            "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
            job,
        )
        self.assertIn(
            "actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz", job
        )
        self.assertIn("sha256sum --check --strict -", job)
        self.assertNotIn("docker://", WORKFLOW.read_text(encoding="utf-8"))

    def test_actionlint_registers_every_literal_self_hosted_role(self) -> None:
        config = ACTIONLINT_CONFIG.read_text(encoding="utf-8")
        for label in REGISTERED_RUNNER_LABELS:
            with self.subTest(label=label):
                self.assertIn(f"    - {label}\n", config)

    def test_actionlint_config_is_plain_git_text_not_an_lfs_pointer(self) -> None:
        attribute = subprocess.run(
            ["git", "check-attr", "filter", "--", str(ACTIONLINT_CONFIG)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertNotIn("filter: lfs", attribute)
        self.assertNotIn(
            "version https://git-lfs.github.com/spec/v1",
            ACTIONLINT_CONFIG.read_text(encoding="utf-8"),
        )

    def test_self_hosted_coverage_uses_preinstalled_toolchain(self) -> None:
        """Coverage provisions nothing now that it only ever runs on the role.

        The `apt-get install clang-18 llvm-18` step existed for the hosted
        fallback alone. With the fallback gone it would only mutate state that
        both runner services on the shared host share, so the lane keeps the
        verification and drops the installation.
        """
        coverage = self.workflow_job("core-coverage")
        self.assertNotIn("apt-get", coverage)
        self.assertNotIn("GitHub-hosted runner", coverage)
        self.assertIn("name: Verify coverage toolchain", coverage)
        self.assertIn("command -v clang-22", coverage)
        self.assertIn("command -v llvm-cov-22", coverage)

    def test_cut_over_web_gates_record_why_the_hosted_pin_was_lifted(self) -> None:
        """The routing reason must survive, or a later pass will churn it back.

        Creator was hosted because the Wasm/OPFS fault matrix is
        timing-sensitive and exceeded bounded budgets on the heterogeneous
        shared pool. Extra runner slots and toolchain caches never addressed
        that; the dedicated CI-only role removes the heterogeneity itself,
        which is a different argument and was proven lane by lane. Keeping
        both halves in the file stops a later cost pass from reading the move
        as "more slots were enough", and stops a later determinism pass from
        restoring a pin whose premise is gone.
        """
        for job_name in WEB_HEAVY_LANES:
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn("dedicated CI-only netcup node", job)
                self.assertIn("instead of diverting it to paid runners", job)
                self.assertNotIn("for determinism, not for capacity", job)
        creator = self.workflow_job("creator-web")
        self.assertIn("timing-sensitive", creator)
        self.assertIn("bounded test budgets", creator)

    def test_macos_selector_queues_on_a_busy_mac_instead_of_paying_for_hosted(self) -> None:
        """A loaded trusted Mac must queue, never divert to paid runners.

        `select-macos-runner` resolves once, before its workload starts.
        Treating a momentarily busy runner as unavailable is what made
        concurrent retries expensive rather than merely slow, and macOS is the
        one lane where that selector still exists at all.
        """
        selector = self.workflow_job("select-macos-runner")
        eligibility = re.search(
            r'eligible_count="\$\(\n(?P<body>.*?)\n          \)"',
            selector,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(
            eligibility, "select-macos-runner has no eligibility expression"
        )
        assert eligibility is not None
        body = eligibility.group("body")
        self.assertNotIn(".busy == false", body)
        self.assertIn('.status == "online"', body)

    def test_macos_selector_still_falls_back_when_no_trusted_runner_is_online(self) -> None:
        """The surviving fallback is macOS-only and deliberately so.

        A single laptop runner asleep would hang a Pull Request rather than
        delay it, and hosted macOS is the lane the Owner accepted paying for.
        Linux has no counterpart any more: an absent Linux role queues.
        """
        macos = self.workflow_job("select-macos-runner")
        self.assertIn(
            "select_hosted 'self-hosted runner is offline, missing, or mislabeled'",
            macos,
        )
        self.assertIn("untrusted fork pull request", macos)
        self.assertIn("runner status token is unavailable", macos)
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(source.count("select_hosted"), macos.count("select_hosted"))

    def test_slow_pool_lane_keeps_headroom_over_its_observed_duration(self) -> None:
        """The job limit must clear the slowest trusted runner, not the fastest.

        web-runtime-host was observed at 40 minutes on the trusted pool and
        cancelled at exactly 45 once, against 16-19 minutes GitHub-hosted. The
        lane now always runs self-hosted, on the dedicated role, so a limit
        calibrated to hosted speed would convert a cost saving into an
        intermittent red Pull Request. The netcup node has not yet produced
        its own timing evidence, so the headroom stays until it does.
        """
        job = self.workflow_job("web-runtime-host")
        match = re.search(r"timeout-minutes: (\d+)", job)
        self.assertIsNotNone(match, "web-runtime-host declares no timeout")
        assert match is not None
        self.assertGreaterEqual(int(match.group(1)), 60)
        self.assertIn("hang detector, not", job)

    def test_macos_jobs_keep_selector_fallback_and_adjudicator_topology(self) -> None:
        selector = self.workflow_job("select-macos-runner")
        primary = self.workflow_job("macos-primary")
        fallback = self.workflow_job("macos-fallback")
        core = self.workflow_job("core-macos")
        asan = self.workflow_job("core-asan-macos")

        self.assertIn("needs: change-scope", selector)
        self.assertIn("needs.change-scope.outputs.manifest", selector)
        self.assertIn(
            "needs: [change-scope, select-macos-runner]", primary
        )
        # change-scope is a direct need since the self-test batch: the
        # fallback checks out the batch's target like every other workload.
        self.assertIn("needs: [change-scope, select-macos-runner, macos-primary]", fallback)
        expected_adjudicator_needs = (
            "needs: [change-scope, select-macos-runner, macos-primary, macos-fallback]"
        )
        self.assertIn(expected_adjudicator_needs, core)
        self.assertIn(expected_adjudicator_needs, asan)

    def test_linux_fixture_consumers_rehydrate_lfs_before_generation(self) -> None:
        consumers = {
            "web-runtime-host": (
                "git lfs checkout -- tests/fixtures/audio",
                "uses: ./.github/actions/web-ci-proof",
            ),
            "core-ubuntu": (
                "git lfs checkout -- tests/fixtures",
                "python3 tests/fixtures/audio/make_fixtures.py",
            ),
            "core-asan": (
                "git lfs checkout -- tests/fixtures",
                "python3 tests/fixtures/audio/make_fixtures.py",
            ),
            "core-coverage": (
                "git lfs checkout -- tests/fixtures",
                "python3 tests/fixtures/audio/make_fixtures.py",
            ),
        }

        for job_name, (hydration, consumer) in consumers.items():
            with self.subTest(job=job_name):
                job = self.workflow_job(job_name)
                self.assertIn(hydration, job)
                self.assertLess(job.index(hydration), job.index(consumer))

    def test_self_hosted_mac_uses_preinstalled_python_while_hosted_uses_setup(self) -> None:
        primary = self.workflow_job("macos-primary")
        self.assertIn("name: Verify self-hosted Python 3.11", primary)
        self.assertIn("command -v python3.11", primary)
        self.assertIn("$RUNNER_TEMP/lmdj-python-3.11", primary)
        self.assertIn(
            "needs.select-macos-runner.outputs.self-hosted == 'true'", primary
        )
        self.assertIn(
            "needs.select-macos-runner.outputs.self-hosted != 'true'", primary
        )
        self.assertEqual(primary.count("uses: actions/setup-python@v6"), 1)

    def test_composite_action_publishes_results_instead_of_retrying_tests(self) -> None:
        source = ACTION.read_text(encoding="utf-8")
        self.assertEqual(source.count("continue-on-error: true"), 4)
        self.assertEqual(source.count("scripts/core.sh proof"), 1)
        self.assertEqual(source.count("scripts/core.sh configure asan"), 1)
        self.assertEqual(source.count("ctest --preset asan -L '^native$'"), 1)
        self.assertIn("echo 'completed=true'", source)

    def test_acceleration_failure_leaves_completion_unset_for_hosted_fallback(self) -> None:
        acceleration = self.action_step("Configure bounded build acceleration")
        prepare = self.action_step("Prepare deterministic Core inputs")
        publisher = self.action_step("Publish semantic gate results")

        self.assertIn("id: acceleration", acceleration)
        self.assertIn("continue-on-error: true", acceleration)
        self.assertIn(
            "if: ${{ steps.acceleration.outcome == 'success' }}", prepare
        )
        self.assertIn(
            "if: ${{ always() && steps.acceleration.outcome == 'success' }}",
            publisher,
        )
        self.assertIn("echo 'completed=true'", publisher)
        self.assertIn("PREPARE_RESULT: ${{ steps.prepare.outcome }}", publisher)

    def test_primary_semantic_success_passes(self) -> None:
        completed = self.run_gate(
            "core",
            PRIMARY_COMPLETED="true",
            PRIMARY_PREPARE_RESULT="success",
            PRIMARY_CORE_RESULT="success",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("lane=primary", completed.stdout)

    def test_fallback_result_replaces_missing_primary_infrastructure_result(self) -> None:
        completed = self.run_gate(
            "asan",
            FALLBACK_COMPLETED="true",
            FALLBACK_PREPARE_RESULT="success",
            FALLBACK_ASAN_RESULT="success",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("lane=fallback", completed.stdout)

    def test_semantic_failure_is_not_hidden_by_fallback_logic(self) -> None:
        completed = self.run_gate(
            "core",
            PRIMARY_COMPLETED="true",
            PRIMARY_PREPARE_RESULT="success",
            PRIMARY_CORE_RESULT="failure",
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("not retried", completed.stderr)

    def test_missing_terminal_result_fails_closed(self) -> None:
        completed = self.run_gate("asan")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("no fallback result", completed.stderr)

    def test_unknown_gate_is_a_usage_error(self) -> None:
        completed = self.run_gate("unknown")
        self.assertEqual(completed.returncode, 64)


if __name__ == "__main__":
    unittest.main()
