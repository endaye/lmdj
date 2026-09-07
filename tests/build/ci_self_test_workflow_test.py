#!/usr/bin/env python3
"""Contract tests for the self-test batch wired into Core CI (plan T2).

A self-test batch is a schedule or an operator `workflow_dispatch` with no lane
selection. Queue dispatch admission is retired. Change Scope resolves its target
first, every formal workload checks out that target rather than the ref's
tip, the two Nightly stress suites run inside the batch, and one verdict job
judges the whole batch under scripts/ci/self_test_policy.json. These tests
pin the wiring so the policy, the workflow and the verdict step cannot drift
apart silently.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/build"))
from workflow_inventory import jobs_in  # noqa: E402

CI = ROOT / ".github/workflows/ci.yml"
NIGHTLY = ROOT / ".github/workflows/core-nightly.yml"
PORTAL = ROOT / ".github/workflows/architecture-portal.yml"
POLICY = ROOT / "scripts/ci/self_test_policy.json"

TARGET_REF = (
    "ref: ${{ needs.change-scope.outputs.self-test == 'true' "
    "&& needs.change-scope.outputs.self-test-target || '' }}"
)
#: Policy jobs run by a reusable-workflow caller job in ci.yml.
ALIASES = {"core-tsan": "nightly-tsan", "core-stress": "nightly-stress"}
#: ci.yml jobs whose checkout must follow the batch target. Every policy job
#: that is a real workload, plus the Mac fallback, which runs the same gates.
#: The two Mac adjudicators and the hosted control plane check out the
#: control revision on purpose: they run scripts, not the product.
ADJUDICATORS = {"core-macos", "core-asan-macos"}
CONTROL_PLANE = {"select-macos-runner"}


def job_body(source: str, job_id: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job_id)}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)", source)
    assert match is not None, f"why: ci.yml has no {job_id} job; remedy: define it"
    return match.group("body")


def job_needs(body: str) -> list[str]:
    inline = re.search(r"^    needs: \[(?P<list>[^\]]*)\]", body, re.M)
    if inline:
        return [item.strip() for item in inline.group("list").split(",") if item.strip()]
    single = re.search(r"^    needs: (?P<one>[a-z][a-z0-9-]*)\s*$", body, re.M)
    if single:
        return [single.group("one")]
    return []


class SelfTestBatchWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ci = CI.read_text(encoding="utf-8")
        cls.nightly = NIGHTLY.read_text(encoding="utf-8")
        cls.portal = PORTAL.read_text(encoding="utf-8")
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))
        cls.ci_job_ids = {job.job_id for job in jobs_in(CI)}

    # -- dispatch surface -------------------------------------------------

    def test_operator_dispatch_can_name_a_target_and_a_request_kind(self) -> None:
        inputs = self.ci.split("  workflow_dispatch:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertIn("      target:\n", inputs,
                      "why: without a target input the only self-test target is the dispatched ref's tip; "
                      "remedy: keep the `target` input")
        self.assertIn("      request_kind:\n", inputs)
        self.assertIn("options: [node, candidate]", inputs)
        self.assertIn("default: node", inputs)
        self.assertIn("workflow_dispatch cannot", inputs,
                      "why: the input's description must say why a SHA cannot be the dispatch ref; "
                      "remedy: keep that sentence")

    def test_run_name_shows_a_targeted_self_test(self) -> None:
        self.assertIn("format('self-test {0}', inputs.target || github.sha)", self.ci)
        self.assertIn("(github.event_name == 'schedule' && 'sweep main')", self.ci)

    # -- change-scope resolves first --------------------------------------

    def test_change_scope_resolves_the_target_before_classifying(self) -> None:
        body = job_body(self.ci, "change-scope")
        resolve = body.index("id: resolve")
        classify = body.index("id: scope")
        self.assertLess(resolve, classify,
                        "why: classification must see the resolved target as its head; remedy: keep "
                        "the resolve step ahead of the classify step")
        self.assertIn("python3 scripts/ci/self_test.py resolve", body)
        for flag in ("--request", "--tip \"$GITHUB_SHA\"", "--main-history",
                     "--control-revision \"$GITHUB_SHA\"", "--run-id \"$GITHUB_RUN_ID\"",
                     "--run-attempt \"$GITHUB_RUN_ATTEMPT\""):
            self.assertIn(flag, body, f"why: resolve needs {flag}; remedy: pass it")
        self.assertIn('git rev-list refs/remotes/origin/main', body)
        self.assertIn('git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main', body)
        self.assertIn('"$GITHUB_REF" != "refs/heads/main"', body)
        self.assertIn('git merge-base --is-ancestor "$GITHUB_SHA" refs/remotes/origin/main', body)
        self.assertIn('if [[ "$EVENT_NAME" == "schedule" ]]; then', body)
        self.assertIn('history_args=(--last-conclusion "$WORK/last-conclusion.json")', body)
        for output in ("self-test", "self-test-action", "self-test-target", "self-test-identity"):
            self.assertIn(f"      {output}: ${{{{ steps.resolve.outputs.{output} }}}}", body)
        self.assertIn('--self-test-skip "${SELF_TEST_SKIP:-}"', body)
        self.assertIn("steps.resolve.outputs.self-test-action == 'skip'", body)

    def test_self_test_batch_condition_is_schedule_or_empty_dispatch(self) -> None:
        body = job_body(self.ci, "change-scope")
        self.assertIn(
            'if [[ "$EVENT_NAME" == "schedule" || ( "$EVENT_NAME" == "workflow_dispatch" '
            '&& -z "${REQUESTED_LANES:-}" && -z "${QUEUE_TICKET:-}" ) ]]; then',
            body,
            "why: a lane-selected or queue dispatch is not a complete self-test; remedy: keep both exclusions")

    def test_scope_artifacts_are_named_after_the_target(self) -> None:
        self.assertIn(
            "name: ci-scope-${{ (steps.resolve.outputs.self-test == 'true' && steps.resolve.outputs.self-test-target)",
            self.ci)
        self.assertIn(
            "name: package-evidence-${{ (needs.change-scope.outputs.self-test == 'true' && needs.change-scope.outputs.self-test-target)",
            self.ci)

    # -- every workload checks out the target -----------------------------

    def workload_jobs(self) -> set[str]:
        jobs = set()
        for suite in self.policy["suites"]:
            for job in suite["jobs"]:
                if job in ALIASES or job in ADJUDICATORS or job in CONTROL_PLANE:
                    continue
                jobs.add(job)
            for alternatives in suite.get("alternatives", {}).values():
                jobs.update(alternatives)
        return jobs

    def test_every_workload_job_checks_out_the_batch_target(self) -> None:
        for job_id in sorted(self.workload_jobs()):
            with self.subTest(job=job_id):
                body = job_body(self.ci, job_id)
                if "uses: ./.github/workflows/" in body:
                    self.assertIn("checkout_ref: ${{ needs.change-scope.outputs.self-test == 'true'", body,
                                  f"why: {job_id} is a reusable-workflow call and cannot set ref itself; "
                                  "remedy: pass checkout_ref")
                    continue
                self.assertIn(TARGET_REF, body,
                              f"why: {job_id} would test the ref's tip while the batch claims the target; "
                              "remedy: add the target ref to its checkout")
                self.assertIn("change-scope", job_needs(body),
                              f"why: {job_id} reads change-scope outputs; remedy: list it in needs")

    def test_adjudicators_and_control_plane_check_out_the_control_revision(self) -> None:
        for job_id in sorted(ADJUDICATORS | CONTROL_PLANE | {"pre-heavy-gate", "pr-gate", "self-test-verdict"}):
            with self.subTest(job=job_id):
                self.assertNotIn(TARGET_REF, job_body(self.ci, job_id),
                                 f"why: {job_id} runs the control revision's scripts, not the product; "
                                 "remedy: leave its checkout on github.sha")

    def test_portal_reusable_workflow_takes_the_checkout_ref(self) -> None:
        self.assertIn("      checkout_ref:\n", self.portal)
        self.assertIn("ref: ${{ inputs.checkout_ref || '' }}", self.portal)
        self.assertIn("checkout_ref: ${{ needs.change-scope.outputs.self-test == 'true' && needs.change-scope.outputs.self-test-target || '' }}",
                      job_body(self.ci, "portal"))

    # -- nightly suites inside the batch ----------------------------------

    def test_core_nightly_is_callable_per_suite_without_duplicate_cron(self) -> None:
        self.assertIn("  workflow_call:\n", self.nightly)
        self.assertNotRegex(self.nightly, r'(?m)^  schedule:',
                            "why: stress runs in the daily complete batch; remedy: remove duplicate Nightly cron")
        for suite in ("tsan", "stress"):
            self.assertIn(f"inputs.suite == '{suite}'", self.nightly)
        self.assertEqual(self.nightly.count("ref: ${{ inputs.target_revision || '' }}"), 2,
                         "why: both stress jobs must check out the caller's target; remedy: set ref on both")
        self.assertNotIn("\nconcurrency:\n", self.nightly.split("\njobs:\n", 1)[0],
                         "why: workflow-level concurrency is not honoured for a called workflow; the jobs "
                         "carry the native-heavy queue themselves; remedy: keep it at job level only")

    def test_nightly_callers_pass_the_target_and_gate_on_admission(self) -> None:
        for job_id, suite in (("nightly-tsan", "tsan"), ("nightly-stress", "stress")):
            with self.subTest(job=job_id):
                body = job_body(self.ci, job_id)
                self.assertIn("uses: ./.github/workflows/core-nightly.yml", body)
                self.assertIn(f"suite: {suite}", body)
                self.assertIn("target_revision: ${{ needs.change-scope.outputs.self-test-target }}", body)
                self.assertIn("needs.change-scope.outputs.self-test-action == 'run'", body)
                self.assertIn("needs.change-scope.outputs.self-test == 'true' || needs.pre-heavy-gate.result == 'success'", body)
                self.assertIn("needs.change-scope.outputs.trusted-head == 'true'", body)

    # -- the verdict job ---------------------------------------------------

    def test_verdict_job_needs_every_policy_job(self) -> None:
        body = job_body(self.ci, "self-test-verdict")
        needs = set(job_needs(body))
        for suite in self.policy["suites"]:
            for job in suite["jobs"]:
                with self.subTest(job=job):
                    self.assertIn(ALIASES.get(job, job), needs,
                                  f"why: a policy job absent from the verdict's needs is always 'missing'; "
                                  f"remedy: add {ALIASES.get(job, job)} to self-test-verdict needs")
            for alternatives in suite.get("alternatives", {}).values():
                for alt in alternatives:
                    self.assertIn(alt, needs)
        self.assertIn("change-scope", needs)
        self.assertIn("pre-heavy-gate", needs)
        self.assertIn("if: ${{ always() && !cancelled() && needs.change-scope.outputs.self-test == 'true' }}", body)
        self.assertIn("runs-on: ubuntu-24.04", body)

    def test_verdict_aliases_and_dependencies_mirror_the_needs_graph(self) -> None:
        body = job_body(self.ci, "self-test-verdict")
        for policy_job, caller in ALIASES.items():
            self.assertIn(f"--alias {policy_job}={caller}", body)
        declared = dict(re.findall(r"--dependency ([a-z0-9-]+)=([a-z0-9,-]+)", body))
        self.assertTrue(declared, "why: without dependencies every skip is 'missing'; remedy: declare them")
        for job, upstreams in declared.items():
            with self.subTest(job=job):
                caller = ALIASES.get(job, job)
                actual = set(job_needs(job_body(self.ci, caller)))
                for upstream in upstreams.split(","):
                    self.assertIn(upstream, actual,
                                  f"why: {job} declares {upstream} as a dependency but its needs do not "
                                  f"list it, so blocked_by would name a job that never gated it; "
                                  f"remedy: keep --dependency {job}= equal to a subset of {caller}'s needs")
        for heavy in ("portal", "core-ubuntu", "package", "core-coverage", "core-asan", "core-tsan", "core-stress"):
            self.assertIn("pre-heavy-gate", declared.get(heavy, ""),
                          f"why: {heavy} is admitted by the Pre-heavy Gate; a skip behind a red gate is blocked; "
                          f"remedy: declare pre-heavy-gate first for {heavy}")

    def test_verdict_retains_a_record_for_run_and_skip_alike(self) -> None:
        body = job_body(self.ci, "self-test-verdict")
        self.assertIn('echo "artifact=self-test-verdict-$TARGET-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"', body)
        self.assertIn('echo "artifact=self-test-skip-$TARGET-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"', body)
        self.assertNotIn('overwrite: true', body)
        self.assertIn("python3 scripts/ci/self_test.py observations", body)
        self.assertIn("python3 scripts/ci/self_test.py aggregate", body)
        self.assertIn("if: ${{ always() && steps.judge.outputs.artifact != '' }}", body)
        self.assertIn("if-no-files-found: error", body)
        self.assertIn("retention-days: 30", body)

    def test_explicit_requests_have_run_scoped_concurrency(self) -> None:
        self.assertIn("format('core-ci-self-test-{0}', github.run_id)", self.ci.split("\njobs:\n")[0])

    def test_history_lookup_is_bounded_and_only_runs_for_schedule(self) -> None:
        body = job_body(self.ci, "change-scope")
        lookup = body.split('if [[ "$EVENT_NAME" == "schedule" ]]; then', 1)[1].split('          fi', 1)[0]
        self.assertIn('timeout 90s python3 scripts/ci/self_test_history.py', lookup)
        self.assertIn('--target "$GITHUB_SHA"', lookup)
        self.assertIn("printf 'null\\n'", lookup)

    def test_old_review_selector_has_no_reachable_product_event(self) -> None:
        self.assertIn("if: ${{ github.event_name == 'pull_request' }}", job_body(self.ci, 'select-review-backend'))
        events = self.ci.split('\npermissions:', 1)[0]
        self.assertNotRegex(events, r'(?m)^  (?:pull_request|pull_request_target|push):')

    def test_both_entry_and_verdict_reject_inherited_attempt_results(self) -> None:
        for job in ('change-scope', 'self-test-verdict'):
            self.assertIn('"$GITHUB_RUN_ATTEMPT" != "1"', job_body(self.ci, job))
            self.assertIn('new workflow_dispatch', job_body(self.ci, job))

    def test_self_tests_continue_independent_heavy_suites_after_prior_failure(self) -> None:
        for job in ('portal', 'core-ubuntu', 'core-asan', 'core-coverage', 'package', 'nightly-tsan', 'nightly-stress'):
            body = job_body(self.ci, job)
            condition = body.split('    if: >-\n', 1)[1].split('      }}', 1)[0]
            for line in condition.splitlines():
                if '.result ==' in line:
                    self.assertIn("needs.change-scope.outputs.self-test == 'true' ||", line, (job, line))

    def test_every_target_checkout_checks_actual_head(self) -> None:
        for job in self.workload_jobs():
            body = job_body(self.ci, job)
            if 'uses: ./.github/workflows/' not in body:
                self.assertIn('git rev-parse HEAD', body)
        self.assertIn('git rev-parse HEAD', self.portal)
        self.assertEqual(self.nightly.count('git rev-parse HEAD'), 2)


class ResolverShellTest(unittest.TestCase):
    """Execute the workflow's actual shell and real Python CLI, not a copied model.

    The only double is git's three exact read/fetch shapes. It refuses unknown
    arguments; no network, checkout mutation or heavy product build runs here.
    """

    def resolve(self, **overrides):
        body = job_body(CI.read_text(), 'change-scope')
        script = body.split('      - name: Resolve the self-test target\n', 1)[1]
        script = script.split('        run: |\n', 1)[1].split('      - name:', 1)[0]
        script = textwrap.dedent(script)
        fake_git = '''git() {
          case "$*" in
            'fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main') return 0 ;;
            "merge-base --is-ancestor $GITHUB_SHA refs/remotes/origin/main")
              case "$MAIN_HISTORY" in *"$GITHUB_SHA"*) return 0 ;; *) return 1 ;; esac ;;
            'rev-list refs/remotes/origin/main') printf '%s\\n' "$MAIN_HISTORY" ;;
            *) echo "unexpected git invocation: $*" >&2; return 96 ;;
          esac
        }
        timeout() {
          if [[ "$1" != "90s" || "$2" != "python3" || "$3" != "scripts/ci/self_test_history.py" ]]; then
            echo "unexpected bounded command: $*" >&2; return 96
          fi
          if [[ -n "${HISTORY_JSON:-}" ]]; then
            printf '%s\\n' "$HISTORY_JSON" >"$WORK/last-conclusion.json"
          else
            command timeout "$@"
          fi
        }
        '''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = dict(os.environ, EVENT_NAME='workflow_dispatch', REQUESTED_LANES='',
                       QUEUE_TICKET='', TARGET_INPUT='b' * 40, REQUEST_KIND='candidate',
                       GITHUB_REF='refs/heads/main', GITHUB_SHA='a' * 40,
                       GITHUB_RUN_ID='17', GITHUB_RUN_ATTEMPT='1', GITHUB_ACTOR='owner',
                       GITHUB_REPOSITORY='owner/repo', GITHUB_TOKEN='',
                       WORK=str(root), GITHUB_OUTPUT=str(root / 'output'),
                       MAIN_HISTORY='a' * 40 + '\n' + 'b' * 40)
            env.update(overrides)
            result = subprocess.run(['/bin/bash', '-c', fake_git + script], cwd=ROOT,
                                    env=env, text=True, capture_output=True)
            output = (root / 'output').read_text() if (root / 'output').exists() else ''
            resolution = json.loads((root / 'resolution.json').read_text()) if (root / 'resolution.json').exists() else None
            return result, output, resolution

    def test_first_manual_batch_needs_no_retained_history_artifact(self):
        result, _, resolution = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(resolution['identity']['target_revision'], 'b' * 40)
        self.assertEqual(resolution['identity']['control_revision'], 'a' * 40)

    def test_non_main_dispatch_ref_and_non_main_target_are_rejected(self):
        for changes in ({'GITHUB_REF': 'refs/heads/feat/test'}, {'TARGET_INPUT': 'f' * 40},
                        {'GITHUB_SHA': 'f' * 40}, {'TARGET_INPUT': 'main'}, {'TARGET_INPUT': '"bad-json'}):
            with self.subTest(changes=changes):
                result, _, _ = self.resolve(**changes)
                self.assertNotEqual(result.returncode, 0)

    def test_reruns_are_refused_with_a_fresh_dispatch_remedy(self):
        result, _, _ = self.resolve(GITHUB_RUN_ATTEMPT='2')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('new workflow_dispatch', result.stderr)

    def test_target_cannot_silently_modify_lane_or_queue_dispatch(self):
        for changes in ({'REQUESTED_LANES': 'portal'},):
            result, _, _ = self.resolve(**changes)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('target is only valid', result.stderr)

    def test_retired_queue_dispatch_is_rejected(self):
        result, _, _ = self.resolve(QUEUE_TICKET='mq:1:1', TARGET_INPUT='')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('queue admission is retired', result.stderr)

    def test_schedule_fixes_event_sha_even_when_newer_main_exists(self):
        result, output, resolution = self.resolve(EVENT_NAME='schedule', TARGET_INPUT='', REQUEST_KIND='schedule')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('self-test=true', output)
        self.assertEqual(resolution['identity']['target_revision'], 'a' * 40)
        self.assertEqual(resolution['identity']['request_kind'], 'schedule')

    def test_actual_schedule_shell_passes_verified_conclusion_to_real_resolver(self):
        sys.path.insert(0, str(ROOT / 'scripts/ci'))
        import self_test
        policy = self_test.load_policy(POLICY)
        retained = json.dumps({'target_revision': 'a' * 40, 'status': 'failed',
                               'evidence_digest': 'd' * 64, 'policy_revision': policy.revision})
        result, output, resolution = self.resolve(EVENT_NAME='schedule', TARGET_INPUT='',
                                                  REQUEST_KIND='schedule', HISTORY_JSON=retained)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(resolution['action'], 'skip')
        self.assertIn('self-test-action=skip', output)
        self.assertIn('complete failed conclusion', resolution['diagnostics'][0])

    def test_manual_candidate_never_reads_even_matching_history(self):
        result, _, resolution = self.resolve(HISTORY_JSON='invalid-if-read')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(resolution['action'], 'run')

    def test_verdict_rejects_rerun_before_reading_inherited_identity(self):
        body = job_body(CI.read_text(), 'self-test-verdict')
        script = body.split('        run: |\n', 1)[1].split('      # Evidence lifetime', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, WORK=directory, GITHUB_RUN_ATTEMPT='2', IDENTITY='inherited-invalid')
            result = subprocess.run(['/bin/bash', '-c', textwrap.dedent(script)],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('new workflow_dispatch', result.stderr)
            self.assertFalse((Path(directory) / 'identity.json').exists())


if __name__ == "__main__":
    unittest.main()
