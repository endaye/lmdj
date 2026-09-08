#!/usr/bin/env python3
"""Execute actual workflow scripts with real Git and real T4 adapters.

No runner/jobs API simulation claims remote acceptance. GitHub dispatch/claim,
permissions, nested display names, upload visibility and cancellation need O1.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
sys.path.insert(0, str(ROOT / "tests/build"))
import batch_execution
import batch_verdict
import incremental_batch
import test_scope
from ci_self_test_workflow_test import job_body, job_needs

SOURCE = (ROOT / ".github/workflows/ci.yml").read_text()
POLICY = test_scope.load_policy(ROOT)
ALIASES = {"core-tsan": "nightly-tsan", "core-stress": "nightly-stress"}


def step(job, name):
    body = job_body(SOURCE, job)
    part = body.split("      - name: " + name + "\n", 1)[1]
    return part.split("\n      - ", 1)[0]


def script(job, name):
    found = step(job, name).split("        run: |\n", 1)
    if len(found) != 2:
        raise AssertionError("why: workflow step has no executable script; remedy: retain the named adapter step")
    lines = []
    for line in found[1].splitlines():
        if line.strip() and not line.startswith("          "):
            break
        lines.append(line[10:])
    if not any(line.strip() for line in lines):
        raise AssertionError("why: empty extracted script would fake a pass; remedy: include its final command line")
    return "\n".join(lines) + "\n"


class WorkflowContracts(unittest.TestCase):
    def test_portal_main_interval_mode_is_selected_only_by_authenticated_preparation(self):
        portal = job_body(SOURCE, "portal")
        self.assertIn("snapshot_mode: ${{ needs.change-scope.outputs.self-test == 'true' && 'main-interval' || 'own-tree' }}", portal,
                      "why: Portal interval mode is not bound to prepared self-test identity; remedy: select it only from authenticated change-scope output")
        self.assertIn("checkout_ref: ${{ needs.change-scope.outputs.self-test == 'true' && needs.change-scope.outputs.self-test-target || '' }}", portal)
        workflow = (ROOT / ".github/workflows/architecture-portal.yml").read_text()
        self.assertRegex(workflow, r"snapshot_mode:[\s\S]*?default: own-tree")
        self.assertIn("PORTAL_SNAPSHOT_MODE: ${{ inputs.snapshot_mode }}", workflow)
        self.assertIn('run: test "$(git rev-parse HEAD)" = "$EXPECTED_TARGET"', workflow)

    def test_empty_candidate_interval_still_runs_complete_current_build_provenance(self):
        workflow = (ROOT / ".github/workflows/architecture-portal.yml").read_text()
        verification = workflow.split("      - name: Verify architecture portal\n", 1)[1]
        self.assertIn("run: scripts/architecture-portal.sh check", verification)
        self.assertNotRegex(verification, r"(?m)^\s*if:",
                            "why: empty interval cannot skip candidate provenance; remedy: keep complete Portal verification unconditional")
        package = json.loads((ROOT / "apps/architecture-portal/package.json").read_text())
        self.assertIn("npm run check:release-docs", package["scripts"]["check"])
        provenance = (ROOT / "apps/architecture-portal/scripts/check-release-docs.mjs").read_text()
        for expression in ("facts.product.version", "verifySnapshotProvenance({", "headRevision: stdout.trim()"):
            self.assertIn(expression, provenance)

    def test_call_requires_both_inputs_and_only_existing_read_secret(self):
        call = SOURCE.split("  workflow_call:\n", 1)[1].split("  schedule:\n", 1)[0]
        for key in ("batch_request", "batch_executor"):
            self.assertRegex(call, rf"{key}:[\s\S]*?required: true\n        type: string")
        self.assertIn("SELF_HOSTED_RUNNER_READ_TOKEN:", call)
        self.assertNotIn("secrets: inherit", SOURCE)
        self.assertNotRegex(SOURCE, r"(?m)^\s+(?:issues|pull-requests|actions|contents): write\s*$")

    def test_original_schedule_and_manual_entry_remain(self):
        events = SOURCE.split("\npermissions:", 1)[0]
        self.assertNotRegex(events, r"(?m)^  (?:schedule|workflow_dispatch|push|pull_request|workflow_run):")
        self.assertIn("  workflow_call:", events)

    def test_legacy_artifacts_require_explicit_nonbatch_entry(self):
        for job in ("self-test-verdict", "pr-gate"):
            self.assertNotIn("\n  " + job + ":\n", SOURCE)
        self.assertNotIn("self_test.py resolve", SOURCE)
        self.assertNotIn("inputs.queue_ticket", SOURCE)

    def test_stress_is_selected_per_suite_not_per_batch(self):
        for job, suite in (("nightly-tsan", "core_tsan_stress"), ("nightly-stress", "core_release_stress")):
            self.assertIn(f"fromJSON(needs.change-scope.outputs.batch-execution).suites.{suite}", job_body(SOURCE, job))
            self.assertIn("needs.change-scope.outputs.batch-mode == 'false' ||", job_body(SOURCE, job))

    def test_verdict_reads_all_actual_product_jobs_and_retains_raw_needs(self):
        needed = set(job_needs(job_body(SOURCE, "batch-verdict")))
        jobs = set(POLICY.inventory.job_owner) | {"macos-fallback"}
        self.assertTrue({ALIASES.get(job, job) for job in jobs} <= needed)
        body = job_body(SOURCE, "batch-verdict")
        self.assertIn("NEEDS_JSON: ${{ toJSON(needs) }}", body)
        self.assertIn("batch_execution.from_needs", body)
        for name in ("execution.json", "needs.json", "verdict.json"):
            self.assertIn(name, body)
        self.assertIn("artifact=batch-verdict-", body)
        self.assertNotIn("artifact=self-test-verdict-", body)
        self.assertNotIn("overwrite: true", body)
        self.assertLess(body.index("Retain scoped verdict"), body.index("Keep failed selected work visible"))

    def test_current_python_reads_historical_policy_without_executing_it(self):
        prepare = script("change-scope", "Prepare the admitted fixed-target execution")
        judge = script("batch-verdict", "Judge selected suites from actual needs")
        self.assertIn("python3 scripts/ci/batch_execution.py prepare --root", prepare)
        self.assertIn("test_scope.load_policy('.batch-policy')", judge)
        self.assertNotRegex(prepare + judge, r"(?:python3 |cd )[\"']?\.batch-policy/")
        self.assertIn('"$GITHUB_WORKSPACE/.batch-policy"', prepare)

    def test_every_lane_uses_the_prepared_selection(self):
        for suite in POLICY.inventory.suites:
            if suite.scope_lane is None:
                continue
            for job in suite.jobs:
                self.assertIn(f"fromJSON(needs.change-scope.outputs.manifest).lanes.{suite.scope_lane}", job_body(SOURCE, job),
                              f"why: {job} is not selection-bound; remedy: retain the exact suite lane guard")


class WorkflowScripts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / "repo"
        self.root.mkdir()
        self.runner = self.directory / "runner"
        self.runner.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Workflow fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("remote", "add", "origin", str(self.root))
        for name in ("self-test-report.yml", "ci.yml", "core-nightly.yml", "architecture-portal.yml"):
            dest = self.root / ".github/workflows" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / ".github/workflows" / name, dest)
        for name in ("batch_execution.py", "batch_verdict.py", "incremental_batch.py", "test_scope.py",
                     "self_test.py", "change_scope.py", "scope_policy.json", "self_test_policy.json", "test_scope_policy.json"):
            dest = self.root / "scripts/ci" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "scripts/ci" / name, dest)
        self.git("add", ".")
        self.git("commit", "-qm", "control policy")
        self.control = self.git("rev-parse", "HEAD")
        note = self.root / "docs/notes/n.md"
        note.parent.mkdir(parents=True)
        note.write_text("fixture")
        self.git("add", ".")
        self.git("commit", "-qm", "target")
        self.target = self.git("rev-parse", "HEAD")
        self.output = self.directory / "output"
        self.summary = self.directory / "summary"
        self.env = {**os.environ, "GITHUB_REPOSITORY": "endaye/lmdj", "GITHUB_REF": "refs/heads/main",
                    "GITHUB_SHA": self.target, "GITHUB_RUN_ID": "51", "GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_WORKSPACE": str(self.root), "RUNNER_TEMP": str(self.runner),
                    "GITHUB_OUTPUT": str(self.output), "GITHUB_STEP_SUMMARY": str(self.summary),
                    "CALLER_WORKFLOW_REF": "endaye/lmdj/.github/workflows/self-test-report.yml@refs/heads/main"}

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True, stderr=subprocess.DEVNULL).strip()

    def request(self, suites):
        selection = test_scope.union_selections(POLICY, [test_scope._selection(POLICY, suites, ["fixture selection"])])
        return incremental_batch.make_request(POLICY, request_id="request-51", kind="auto", base_sha=self.control,
            target_sha=self.target, control_sha=self.control, selection=selection, origin_run={"run_id": 51, "attempt": 1})

    def invoke(self, job, name, **env):
        self.output.write_text("")
        result = subprocess.run(["bash", "-euo", "pipefail", "-c", script(job, name)], cwd=self.root,
                                env={**self.env, **env}, capture_output=True, text=True, timeout=20)
        values = dict(line.split("=", 1) for line in self.output.read_text().splitlines() if "=" in line)
        return result, values

    def prepare(self, suites, *, poison_historical_code=False):
        request = self.request(suites)
        env = {"BATCH_REQUEST": json.dumps(request), "BATCH_EXECUTOR": json.dumps({"run_id": 51, "attempt": 1})}
        read_result, _ = self.invoke("change-scope", "Read the frozen policy checkout", FROZEN_CONTROL=self.control)
        self.assertEqual(read_result.returncode, 0, read_result.stderr)
        if poison_historical_code:
            for name in ("batch_execution.py", "batch_verdict.py"):
                (self.root / ".batch-policy/scripts/ci" / name).write_text("raise RuntimeError('historical code executed')\n")
        result, values = self.invoke("change-scope", "Prepare the admitted fixed-target execution", **env)
        self.assertEqual(result.returncode, 0, "why: actual prepare script failed; remedy: inspect its Git/identity binding\n" + result.stderr + result.stdout)
        return json.loads(values["execution"])

    def judge(self, execution, results=None):
        selected = set(execution["selection"]["suites"])
        needs = {ALIASES.get(job, job): {"result": "success" if suite in selected else "skipped", "outputs": {}}
                 for job, suite in POLICY.inventory.job_owner.items()}
        needs["macos-fallback"] = {"result": "skipped", "outputs": {}}
        needs["change-scope"] = {"result": "success", "outputs": {}}
        if results:
            needs.update(results)
        result, values = self.invoke("batch-verdict", "Judge selected suites from actual needs",
                                    EXECUTION_JSON=json.dumps(execution), NEEDS_JSON=json.dumps(needs))
        directory = self.runner / "batch-verdict-51-1"
        document = json.loads((directory / "verdict.json").read_text()) if (directory / "verdict.json").exists() else None
        return result, values, document, needs

    def test_changed_executor_workflow_blocks_before_heavy_outputs(self):
        read_result, _ = self.invoke("change-scope", "Read the frozen policy checkout", FROZEN_CONTROL=self.control)
        self.assertEqual(read_result.returncode, 0, read_result.stderr)
        for name in ("self-test-report.yml", "ci.yml", "core-nightly.yml", "architecture-portal.yml"):
            with self.subTest(workflow=name):
                path = self.root / ".github/workflows" / name
                original = path.read_text()
                path.write_text(original + "\n# incompatible executor fixture\n")
                self.git("add", str(path))
                self.git("commit", "-qm", "changed executor")
                executor_control = self.git("rev-parse", "HEAD")
                result, outputs = self.invoke("change-scope", "Prepare the admitted fixed-target execution",
                    GITHUB_SHA=executor_control, BATCH_REQUEST=json.dumps(self.request(["docs_static"])),
                    BATCH_EXECUTOR=json.dumps({"run_id": 51, "attempt": 1}))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("workflow sources are incompatible", result.stderr)
                self.assertEqual(outputs, {}, "why: incompatible sources admitted heavy outputs; remedy: fail preflight")
                path.write_text(original)
                self.git("add", str(path))
                self.git("commit", "-qm", "restore executor source")

    def test_older_control_with_identical_workflows_is_executable(self):
        self.assertNotEqual(self.control, self.target)
        execution = self.prepare(["docs_static"])
        self.assertEqual(execution["identity"]["control_sha"], self.control)
        self.assertEqual(execution["identity"]["target_sha"], self.target)

    def test_policy_only_candidate_drift_blocks_before_heavy_outputs(self):
        self.check_policy_drift("candidate", rejected=True)

    def test_candidate_with_matching_policy_on_new_commit_is_executable(self):
        self.check_policy_drift("candidate", rejected=False, changed=False)

    def test_policy_only_node_drift_preserves_frozen_execution(self):
        self.check_policy_drift("node", rejected=False)

    def test_policy_only_auto_drift_preserves_frozen_execution(self):
        self.check_policy_drift("auto", rejected=False)

    def check_policy_drift(self, kind, *, rejected, changed=True):
        request = self.request(POLICY.suite_ids)
        request["kind"] = kind
        if kind != "auto":
            request["base"] = None
        read_result, _ = self.invoke("change-scope", "Read the frozen policy checkout", FROZEN_CONTROL=self.control)
        self.assertEqual(read_result.returncode, 0, read_result.stderr)
        if changed:
            path = self.root / "scripts/ci/scope_policy.json"
            policy = json.loads(path.read_text())
            policy["rules"].append({"match": {"kind": "exact", "value": "docs/policy-fixture.md"}, "lanes": ["portal"]})
            path.write_text(json.dumps(policy))
            self.git("add", str(path))
            self.git("commit", "-qm", "policy only executor drift")
        executor = self.git("rev-parse", "HEAD")
        result, outputs = self.invoke("change-scope", "Prepare the admitted fixed-target execution",
            GITHUB_SHA=executor, BATCH_REQUEST=json.dumps(request),
            BATCH_EXECUTOR=json.dumps({"run_id": 51, "attempt": 1}))
        if rejected:
            self.assertNotEqual(result.returncode, 0, "why: obsolete candidate policy admitted heavy work; remedy: reject before outputs")
            self.assertIn("candidate policy", result.stderr)
            self.assertIn("remedy:", result.stderr)
            self.assertEqual(outputs, {})
        else:
            self.assertEqual(result.returncode, 0, result.stderr)
            execution = json.loads(outputs["execution"])
            self.assertEqual(execution["identity"]["policy_digest"], POLICY.digest)
            self.assertEqual(execution["identity"]["request_kind"], kind)
            self.assertEqual(execution["selection"], request["selection"])

    def test_native_entry_remains_explicitly_legacy(self):
        result, values = self.invoke("change-scope", "Resolve the execution entry", BATCH_REQUEST="", BATCH_EXECUTOR="",
            CALLER_WORKFLOW_REF="endaye/lmdj/.github/workflows/ci.yml@refs/heads/main")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(values, {})

    def test_both_empty_call_inputs_do_not_become_legacy_full(self):
        result, values = self.invoke("change-scope", "Resolve the execution entry", BATCH_REQUEST="", BATCH_EXECUTOR="")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(values.get("batch-mode"), "false")

    def test_foreign_workflow_cannot_call_product_dag_with_forged_valid_json(self):
        result, values = self.invoke("change-scope", "Resolve the execution entry",
            BATCH_REQUEST=json.dumps({'control': self.control}),
            BATCH_EXECUTOR=json.dumps({'run_id': 51, 'attempt': 1}),
            CALLER_WORKFLOW_REF="endaye/lmdj/.github/workflows/foreign.yml@refs/heads/main")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(values, {})
        self.assertIn("why:", result.stderr)

    def test_one_missing_input_never_falls_back(self):
        for request, executor in ((json.dumps(self.request([])), ""), ("", '{"run_id":51,"attempt":1}')):
            with self.subTest(request=bool(request)):
                result, values = self.invoke("change-scope", "Resolve the execution entry", BATCH_REQUEST=request, BATCH_EXECUTOR=executor)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotEqual(values.get("batch-mode"), "false")

    def test_wrong_executor_and_boolean_identity_rejected(self):
        for executor in ({"run_id": 52, "attempt": 1}, {"run_id": 51, "attempt": True}):
            with self.subTest(executor=executor):
                result, _ = self.invoke("change-scope", "Resolve the execution entry",
                                       BATCH_REQUEST=json.dumps(self.request([])), BATCH_EXECUTOR=json.dumps(executor))
                self.assertNotEqual(result.returncode, 0)

    def test_duplicate_json_field_rejected_before_checkout(self):
        result, _ = self.invoke("change-scope", "Resolve the execution entry", BATCH_REQUEST=json.dumps(self.request([])),
                               BATCH_EXECUTOR='{"run_id":51,"run_id":51,"attempt":1}')
        self.assertNotEqual(result.returncode, 0)

    def test_real_prepare_and_judge_focused_does_not_execute_unselected_stress(self):
        execution = self.prepare(["creator"])
        self.assertEqual(execution["selection"]["kind"], "focused")
        self.assertFalse(execution["suites"]["core_tsan_stress"])
        result, values, verdict, needs = self.judge(execution)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(verdict["status"], "passed")
        self.assertEqual(len(verdict["suites"]), 16)
        self.assertEqual(values["artifact"], f"batch-verdict-{self.target}-51-1")
        self.assertEqual(json.loads((self.runner / "batch-verdict-51-1/needs.json").read_text()), needs)
        self.assertEqual(batch_verdict.scheduler_outcomes(verdict, POLICY, execution["identity"], execution["selection"]), {"creator": "passed"})

    def test_none_is_not_required_not_passed(self):
        result, _, verdict, _ = self.judge(self.prepare([]))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(verdict["status"], "not-required")
        self.assertTrue(all(s["status"] == "not-selected" for s in verdict["suites"]))

    def test_full_covers_sixteen_and_preserves_legacy_schema_boundary(self):
        result, _, verdict, _ = self.judge(self.prepare(POLICY.suite_ids))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(verdict["status"], "passed")
        self.assertEqual(sum(s["selected"] for s in verdict["suites"]), 16)
        self.assertEqual(verdict["evidence_schema"], batch_verdict.SCHEMA)
        self.assertNotEqual(verdict["evidence_schema"], "lmdj.ci-self-test.v1")

    def test_unselected_job_success_invalidates_verdict(self):
        result, _, verdict, _ = self.judge(self.prepare(["creator"]), {"nightly-tsan": {"result": "success", "outputs": {}}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(verdict)

    def test_tsan_infrastructure_output_is_debt(self):
        result, _, verdict, _ = self.judge(self.prepare(["core_tsan_stress"]),
            {"nightly-tsan": {"result": "failure", "outputs": {"infrastructure_failure": "true"}}})
        self.assertEqual(result.returncode, 0, result.stderr)
        suite = next(s for s in verdict["suites"] if s["id"] == "core_tsan_stress")
        self.assertEqual(suite["scheduler_outcome"], "infrastructure")
        self.assertEqual(suite["failures"], [])

    def test_macos_fallback_success_reuses_complete_alternative_rule(self):
        result, _, verdict, _ = self.judge(self.prepare(["core_macos"]),
            {"macos-primary": {"result": "skipped", "outputs": {}}, "macos-fallback": {"result": "success", "outputs": {}}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(verdict["status"], "passed")

    def test_wrong_attempt_verdict_refused(self):
        execution = self.prepare([])
        execution["identity"]["run_attempt"] = 2
        result, _, verdict, _ = self.judge(execution)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(verdict)

    def test_historical_control_python_is_never_executed(self):
        execution = self.prepare(["creator"], poison_historical_code=True)
        result, _, verdict, _ = self.judge(execution)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(verdict["status"], "passed")

    def test_mixed_macos_failure_and_unexecuted_work_preserves_both(self):
        result, _, verdict, _ = self.judge(self.prepare(["core_macos"]),
            {"core-macos": {"result": "failure", "outputs": {}}, "core-asan-macos": {"result": "skipped", "outputs": {}}})
        self.assertEqual(result.returncode, 0, result.stderr)
        suite = next(s for s in verdict["suites"] if s["id"] == "core_macos")
        # Existing complete-suite semantics classify an unexplained skip as
        # infrastructure; an absent observation is the separate missing case.
        self.assertEqual(suite["scheduler_outcome"], "infrastructure")
        self.assertIn("core-macos", suite["failures"])


if __name__ == "__main__":
    unittest.main()
