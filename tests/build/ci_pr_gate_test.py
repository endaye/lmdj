#!/usr/bin/env python3
"""Contract tests for the manifest-driven PR gate.

The production change that makes these tests fail is an absent or permissive
manifest/result truth-table validator.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "scripts/ci/scope_policy.json"
GATE_PATH = ROOT / "scripts/ci/pr_gate.py"
MAIN_WORKFLOW_PATH = ROOT / ".github/workflows/ci.yml"
PORTAL_WORKFLOW_PATH = ROOT / ".github/workflows/architecture-portal.yml"
HEAD_SHA = "a" * 40
OTHER_HEAD_SHA = "b" * 40
OTHER_BASE_SHA = "c" * 40

VALID_RESULTS = {
    "docs-static": "success",
    "portal": "success",
    "ci-contract": "skipped",
    # The default fixture selects `web_runtime_host`, which now routes by the
    # static netcup role, so the selector is not a support job of any selected
    # lane and must report skipped like every other unselected job.
    "select-ubuntu-runner": "skipped",
    "select-macos-runner": "skipped",
    "macos-primary": "skipped",
    "core-ubuntu": "skipped",
    "core-asan": "skipped",
    "core-coverage": "skipped",
    "core-macos": "skipped",
    "core-asan-macos": "skipped",
    "web-toolchain-conformance": "skipped",
    "web-runtime-host": "success",
    "creator-web": "skipped",
    "web-runtime-lab": "skipped",
    "deploy-contract": "skipped",
    "chameleon-lab": "skipped",
    "package": "skipped",
}

FOCUSED_PATH_FIXTURES = {
    frozenset(("docs_static", "portal", "web_runtime_host")): (
        "apps/web-runtime-host/README.md",
    ),
    frozenset(("docs_static",)): ("docs/guide.md",),
    frozenset(("ci_contract",)): ("tests/build/ci_example_test.py",),
    frozenset(("core_macos",)): ("tests/platform/audio/device_test.cpp",),
    frozenset(("web_runtime_host",)): ("scripts/web-runtime-host.sh",),
    frozenset(("web_runtime_lab",)): ("scripts/web-runtime-lab.sh",),
    frozenset(("deploy_contract",)): ("scripts/web-runtime-deploy.sh",),
    frozenset(("chameleon_lab",)): ("scripts/chameleon-lab.sh",),
    frozenset(("package",)): ("tests/distribution/archive_test.py",),
    frozenset(("core_ubuntu",)): ("tests/fixtures/projects/demo.json",),
    frozenset(("core_ubuntu", "core_macos")): ("tests/host/cli_test.py",),
}

def workflow_job(source: str, job_id: str) -> str:
    match = re.search(
        rf"^  {re.escape(job_id)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:|\Z)",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"workflow job is missing: {job_id}")
    return match.group("body")


def declared_job_name(job_id: str, body: str) -> str:
    match = re.search(r"^    name: (?P<name>[^\n]+)$", body, re.MULTILINE)
    return match.group("name") if match else job_id


def workflow_display_names() -> dict[str, str]:
    """Derive actual run job names, including the reusable Portal shape."""
    main_source = MAIN_WORKFLOW_PATH.read_text(encoding="utf-8")
    portal_source = PORTAL_WORKFLOW_PATH.read_text(encoding="utf-8")
    names: dict[str, str] = {}
    for job_id in VALID_RESULTS:
        body = workflow_job(main_source, job_id)
        caller_name = declared_job_name(job_id, body)
        if "uses: ./.github/workflows/architecture-portal.yml" in body:
            callee_id = "portal"
            callee_name = declared_job_name(
                callee_id, workflow_job(portal_source, callee_id)
            )
            names[job_id] = f"{caller_name} / {callee_name}"
        else:
            names[job_id] = caller_name
    return names


def load_gate():
    spec = importlib.util.spec_from_file_location("pr_gate", GATE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load PR gate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def evaluate(manifest, results, policy):
    """Adjudicate one manifest/result pair against the closed v2 policy."""
    return load_gate().validate_gate(
        policy, manifest, results, HEAD_SHA, expected_base_sha=OTHER_HEAD_SHA,
    )


class PrGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        cls.module = load_gate()

    def manifest(
        self, enabled=("docs_static", "portal", "web_runtime_host"), *,
        lanes=None, trusted_head=True,
    ):
        enabled = tuple(sorted(lanes)) if lanes is not None else tuple(enabled)
        lanes = {lane: lane in enabled for lane in self.policy["lanes"]}
        required_jobs = sorted({
            job for lane in enabled for job in self.policy["lane_jobs"][lane]
        })
        enabled_set = frozenset(enabled)
        mode = "full" if enabled_set == frozenset(self.policy["lanes"]) else "focused"
        paths = (
            (".github/workflows/ci.yml",)
            if mode == "full"
            else FOCUSED_PATH_FIXTURES[enabled_set]
        )
        return {
            "schema": self.policy["manifest_schema"],
            "base_sha": OTHER_HEAD_SHA,
            "head_sha": HEAD_SHA,
            "mode": mode,
            "reasons": ["test fixture"],
            "changed_files": [
                {"result": "modified", "paths": [path]} for path in paths
            ],
            "lanes": lanes,
            "required_jobs": required_jobs,
            "trusted_head": trusted_head,
        }

    @staticmethod
    def matching_results(manifest):
        results = {job: "skipped" for job in VALID_RESULTS}
        for job in manifest["required_jobs"]:
            results[job] = "success"
        return results

    @staticmethod
    def results(**overrides):
        """Build a result set keyed by lane-style identifiers, all skipped."""
        results = {job: "skipped" for job in VALID_RESULTS}
        for name, result in overrides.items():
            job = name.replace("_", "-")
            if job not in results:
                raise AssertionError(f"unknown formal job: {job}")
            results[job] = result
        return results

    def validate(
        self, manifest=None, results=None, expected_head_sha=HEAD_SHA,
        expected_base_sha=OTHER_HEAD_SHA,
    ):
        return self.module.validate_gate(
            self.policy, manifest or self.manifest(), results or VALID_RESULTS,
            expected_head_sha, expected_base_sha=expected_base_sha,
        )

    def test_exact_required_success_and_unrequired_skipped_passes(self):
        report = self.validate()
        self.assertTrue(report.ok)
        self.assertEqual(report.errors, ())

    def test_untrusted_selected_self_hosted_lane_fails_gate(self):
        manifest = self.manifest(lanes={"core_ubuntu"}, trusted_head=False)
        report = evaluate(manifest, self.results(core_ubuntu="skipped"), self.policy)
        self.assertFalse(report.ok)
        self.assertIn("untrusted fork blocked from self-hosted CI", report.errors)

    def test_untrusted_block_is_reported_before_the_selected_skip_errors(self):
        manifest = self.manifest(lanes={"core_ubuntu"}, trusted_head=False)
        report = evaluate(manifest, self.results(core_ubuntu="skipped"), self.policy)
        self.assertEqual(
            report.errors[0], "untrusted fork blocked from self-hosted CI"
        )
        self.assertIn(
            "selected job core-ubuntu is skipped, expected success", report.errors
        )

    def test_untrusted_head_without_a_self_hosted_job_keeps_ordinary_errors(self):
        manifest = self.manifest(lanes={"core_macos"}, trusted_head=False)
        self.assertFalse(
            set(manifest["required_jobs"])
            & set(self.policy["self_hosted_jobs"])
        )
        report = evaluate(
            manifest, self.matching_results(manifest), self.policy
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.errors, ())

    def test_trusted_head_keeps_the_existing_truth_table(self):
        manifest = self.manifest(lanes={"core_ubuntu"}, trusted_head=True)
        report = evaluate(
            manifest, self.matching_results(manifest), self.policy
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.errors, ())

    def test_missing_or_non_boolean_trust_fails_the_gate_closed(self):
        for value in ("true", 1, None):
            with self.subTest(value=value):
                manifest = self.manifest()
                manifest["trusted_head"] = value
                self.assertFalse(self.validate(manifest=manifest).ok)
        manifest = self.manifest()
        del manifest["trusted_head"]
        self.assertFalse(self.validate(manifest=manifest).ok)

    def test_change_scope_failure_after_manifest_output_fails_gate(self):
        try:
            report = self.module.validate_gate(
                self.policy,
                self.manifest(),
                VALID_RESULTS,
                HEAD_SHA,
                expected_base_sha=OTHER_HEAD_SHA,
                change_scope_result="failure",
            )
        except TypeError as error:
            self.fail(f"producer result is not independently validated: {error}")
        self.assertFalse(report.ok)
        self.assertEqual(
            report.errors,
            ("change-scope producer is failure, expected success",),
        )
        self.assertEqual(len(VALID_RESULTS), 18)
        self.assertNotIn("change-scope", VALID_RESULTS)

    def test_required_skipped_failure_and_cancelled_fail(self):
        for result in ("skipped", "failure", "cancelled"):
            with self.subTest(result=result):
                results = dict(VALID_RESULTS, **{"portal": result})
                report = self.validate(results=results)
                self.assertFalse(report.ok)
                self.assertEqual(report.errors, (f"selected job portal is {result}, expected success",))

    def test_unrequired_success_failure_and_cancelled_fail(self):
        for result in ("success", "failure", "cancelled"):
            with self.subTest(result=result):
                results = dict(VALID_RESULTS, **{"ci-contract": result})
                report = self.validate(results=results)
                self.assertFalse(report.ok)
                self.assertEqual(report.errors, (f"unselected job ci-contract is {result}, expected skipped",))

    def test_missing_or_extra_formal_job_fails(self):
        missing = dict(VALID_RESULTS)
        del missing["portal"]
        report = self.validate(results=missing)
        self.assertEqual(report.errors, ("result key set mismatch: missing portal",))
        extra = dict(VALID_RESULTS, **{"invented-job": "skipped"})
        report = self.validate(results=extra)
        self.assertEqual(report.errors, ("result key set mismatch: extra invented-job",))

    def test_unknown_result_fails(self):
        report = self.validate(results=dict(VALID_RESULTS, **{"portal": "neutral"}))
        self.assertEqual(report.errors, ("unknown result for portal: neutral",))

    def test_key_set_unknown_result_and_truth_table_mismatches_all_accumulate(self):
        results = dict(VALID_RESULTS, **{
            "invented-job": "skipped",
            "ci-contract": "neutral",
            "portal": "failure",
        })
        report = self.validate(results=results)
        self.assertEqual(report.errors, (
            "result key set mismatch: extra invented-job",
            "unknown result for ci-contract: neutral",
            "selected job portal is failure, expected success",
        ))

    def test_unknown_schema_mode_lane_manifest_key_or_job_fails(self):
        mutations = {
            "schema": lambda manifest: manifest.__setitem__("schema", "unknown"),
            "mode": lambda manifest: manifest.__setitem__("mode", "unknown"),
            "lane": lambda manifest: manifest["lanes"].__setitem__("unknown", False),
            "key": lambda manifest: manifest.__setitem__("unexpected", True),
            "job": lambda manifest: manifest["required_jobs"].append("invented-job"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                manifest = self.manifest()
                mutate(manifest)
                report = self.validate(manifest=manifest)
                self.assertFalse(report.ok)
                self.assertTrue(report.errors)

    def test_manifest_mode_and_lane_selection_must_be_consistent(self):
        mutations = {}
        full = self.manifest()
        full["mode"] = "full"
        mutations["full with focused lanes"] = full
        draft = self.manifest(("docs_static",))
        draft["mode"] = "draft"
        mutations["draft without exact lightweight lanes"] = draft
        focused = self.manifest(tuple(self.policy["lanes"]))
        focused["mode"] = "focused"
        mutations["focused with every lane"] = focused
        for name, manifest in mutations.items():
            with self.subTest(name=name):
                report = self.validate(manifest=manifest)
                self.assertFalse(report.ok)
                self.assertIn("invalid policy or manifest", report.errors[0])

    def test_manifest_changed_file_schema_and_paths_fail_closed(self):
        malformed_entries = {
            "unknown key": {
                "result": "modified", "paths": ["docs/guide.md"], "extra": True,
            },
            "unknown result": {"result": "invented", "paths": ["docs/guide.md"]},
            "string paths": {"result": "modified", "paths": "docs/guide.md"},
            "rename one path": {"result": "renamed", "paths": ["docs/guide.md"]},
            "modified two paths": {
                "result": "modified", "paths": ["docs/a.md", "docs/b.md"],
            },
            "noncanonical path": {"result": "modified", "paths": ["../escape.md"]},
        }
        for name, entry in malformed_entries.items():
            with self.subTest(name=name):
                manifest = self.manifest()
                manifest["changed_files"] = [entry]
                self.assertFalse(self.validate(manifest=manifest).ok)

        duplicate = self.manifest()
        duplicate["changed_files"] = [
            {"result": "modified", "paths": ["docs/guide.md"]},
            {"result": "deleted", "paths": ["docs/guide.md"]},
        ]
        self.assertFalse(self.validate(manifest=duplicate).ok)

    def test_focused_manifest_rejects_core_path_downgraded_to_docs(self):
        manifest = self.manifest(("docs_static",))
        manifest["changed_files"] = [{
            "result": "modified",
            "paths": ["tests/core/facade/application_test.cpp"],
        }]
        report = self.validate(
            manifest=manifest,
            results=self.matching_results(manifest),
        )
        self.assertFalse(report.ok)
        self.assertIn("focused manifest", "\n".join(report.errors))

    def test_focused_manifest_rejects_web_path_without_portal_consumer(self):
        manifest = self.manifest(("web_runtime_host",))
        manifest["changed_files"] = [{
            "result": "modified",
            "paths": ["apps/web-runtime-host/src/main.mjs"],
        }]
        report = self.validate(
            manifest=manifest,
            results=self.matching_results(manifest),
        )
        self.assertFalse(report.ok)
        self.assertIn("focused manifest", "\n".join(report.errors))

    def test_focused_manifest_rejects_central_full_rule_path(self):
        manifest = self.manifest(("docs_static",))
        manifest["changed_files"] = [{
            "result": "modified",
            "paths": [".github/workflows/ci.yml"],
        }]
        report = self.validate(
            manifest=manifest,
            results=self.matching_results(manifest),
        )
        self.assertFalse(report.ok)
        self.assertIn("requires full", "\n".join(report.errors))

    def test_duplicate_required_job_and_lane_job_conflict_fail(self):
        duplicate = self.manifest()
        duplicate["required_jobs"].append("portal")
        self.assertFalse(self.validate(manifest=duplicate).ok)
        conflict = self.manifest()
        conflict["required_jobs"].remove("portal")
        self.assertFalse(self.validate(manifest=conflict).ok)

    def test_manifest_head_sha_must_equal_current_head_sha(self):
        report = self.validate(expected_head_sha=OTHER_HEAD_SHA)
        self.assertEqual(report.errors, (f"manifest head SHA {HEAD_SHA} does not match expected {OTHER_HEAD_SHA}",))

    def test_manifest_base_sha_must_equal_event_base_sha(self):
        report = self.validate(expected_base_sha=OTHER_BASE_SHA)
        self.assertEqual(
            report.errors,
            (
                f"manifest base SHA {OTHER_HEAD_SHA} does not match expected "
                f"{OTHER_BASE_SHA}",
            ),
        )

    def test_full_manifest_requires_every_formal_job(self):
        manifest = self.manifest(tuple(self.policy["lanes"]))
        report = self.validate(manifest=manifest, results={job: "success" for job in VALID_RESULTS})
        self.assertTrue(report.ok)
        self.assertEqual(set(report.requested_jobs), set(VALID_RESULTS))

    def test_web_runtime_host_requires_no_runner_selector(self):
        """The Gate projection must follow the lane off the selector.

        `web_runtime_host` routes by the static `ci-web-heavy` role, so the
        selector's guard leaves it skipped when only this lane is selected.
        Still projecting `select-ubuntu-runner` as a required job would then
        fail the run on a support job the lane never reads, and demanding the
        selector succeed would quietly restore the paid-runner fallback the
        cutover removed.
        """
        manifest = self.manifest(("web_runtime_host",))
        self.assertEqual(manifest["required_jobs"], ["web-runtime-host"])
        report = self.validate(
            manifest=manifest, results=self.matching_results(manifest)
        )
        self.assertTrue(report.ok)
        self.assertNotIn("select-ubuntu-runner", report.requested_jobs)
        self.assertIn("select-ubuntu-runner", report.skipped_jobs)
        stale = self.manifest(("web_runtime_host",))
        stale["required_jobs"] = sorted(
            [*stale["required_jobs"], "select-ubuntu-runner"]
        )
        stale_report = self.validate(
            manifest=stale, results=self.matching_results(stale)
        )
        self.assertFalse(stale_report.ok)
        self.assertIn(
            "required jobs do not derive from lanes",
            "\n".join(stale_report.errors),
        )

    def test_web_runtime_lab_requires_no_runner_selector(self):
        """The last Web lane leaves the selector, and its projection with it.

        With `web_runtime_lab` on the static `ci-web-heavy` role, no Web lane
        reads `select-ubuntu-runner` any more. Projecting the selector as a
        required job for this lane would fail the run on a support job the
        workflow guard now leaves skipped, and demanding it succeed would
        quietly restore the paid-runner fallback the cutover removed.
        """
        manifest = self.manifest(("web_runtime_lab",))
        self.assertEqual(manifest["required_jobs"], ["web-runtime-lab"])
        report = self.validate(
            manifest=manifest, results=self.matching_results(manifest)
        )
        self.assertTrue(report.ok)
        self.assertNotIn("select-ubuntu-runner", report.requested_jobs)
        self.assertIn("select-ubuntu-runner", report.skipped_jobs)
        stale = self.manifest(("web_runtime_lab",))
        stale["required_jobs"] = sorted(
            [*stale["required_jobs"], "select-ubuntu-runner"]
        )
        stale_report = self.validate(
            manifest=stale, results=self.matching_results(stale)
        )
        self.assertFalse(stale_report.ok)
        self.assertIn(
            "required jobs do not derive from lanes",
            "\n".join(stale_report.errors),
        )

    def test_core_macos_requires_both_published_adjudicators(self):
        manifest = self.manifest(("core_macos",))
        results = {job: "skipped" for job in VALID_RESULTS}
        for job in manifest["required_jobs"]:
            results[job] = "success"
        report = self.validate(manifest=manifest, results=results)
        self.assertTrue(report.ok)
        self.assertIn("core-macos", report.requested_jobs)
        self.assertIn("core-asan-macos", report.requested_jobs)

    def test_needs_json_normalizer_ignores_outputs_but_requires_result(self):
        needs = {job: {"result": result, "outputs": {"arbitrary": "value"}} for job, result in VALID_RESULTS.items()}
        self.assertEqual(self.module.normalize_needs(needs), VALID_RESULTS)
        del needs["portal"]["result"]
        with self.assertRaisesRegex(ValueError, "missing result for portal"):
            self.module.normalize_needs(needs)

    def test_timing_api_failure_is_a_warning_and_never_changes_gate_result(self):
        report = self.validate()
        def fail():
            raise OSError("offline")
        summary = self.module.render_summary(report, self.policy, timing_reader=fail)
        self.assertTrue(report.ok)
        self.assertIn("timing unavailable", summary)
        self.assertIn("Pre-Gate critical path | timing unavailable", summary)

    def test_slo_overage_is_reported_but_success_stays_success(self):
        report = self.validate()
        summary = self.module.render_summary(report, self.policy, timing_reader=lambda: [{
            "name": "docs-static", "created_at": "2026-08-11T00:00:00Z",
            "started_at": "2026-08-11T00:00:01Z",
            "completed_at": "2026-08-11T00:03:02Z",
        }])
        self.assertTrue(report.ok)
        self.assertIn("SLO missed", summary)

    def test_queue_delay_does_not_count_against_execution_slo(self):
        report = self.validate()
        summary = self.module.render_summary(report, self.policy, timing_reader=lambda: [{
            "name": "docs-static", "created_at": "2026-08-11T00:00:00Z",
            "started_at": "2026-08-11T00:10:00Z",
            "completed_at": "2026-08-11T00:10:10Z",
        }])
        self.assertTrue(report.ok)
        self.assertIn(
            "Timing docs-static | queue 600s; execution 10s; within SLO",
            summary,
        )
        self.assertNotIn(
            "Timing docs-static | queue 600s; execution 10s; SLO missed",
            summary,
        )

    def test_long_jobs_without_policy_slos_report_not_defined(self):
        undefined = {
            "ci_contract": "ci-contract",
            "web_runtime_lab": "web-runtime-lab",
            "deploy_contract": "deploy-contract",
            "chameleon_lab": "chameleon-lab",
            "package": "package",
        }
        display_names = workflow_display_names()
        for lane, job_id in undefined.items():
            with self.subTest(job=job_id):
                manifest = self.manifest((lane,))
                results = {job: "skipped" for job in VALID_RESULTS}
                for required in manifest["required_jobs"]:
                    results[required] = "success"
                report = self.validate(manifest=manifest, results=results)
                summary = self.module.render_summary(
                    report,
                    self.policy,
                    timing_reader=lambda job_id=job_id: [{
                        "name": display_names[job_id],
                        "created_at": "2026-08-11T00:00:00Z",
                        "started_at": "2026-08-11T00:00:01Z",
                        "completed_at": "2026-08-11T03:00:01Z",
                    }],
                )
                timing = (
                    f"Timing {job_id} | queue 1s; execution 10800s; "
                    "SLO not defined"
                )
                self.assertTrue(report.ok)
                self.assertIn(timing, summary)
                self.assertNotRegex(
                    summary,
                    rf"Timing {re.escape(job_id)} .*; (?:within SLO|SLO missed)",
                )

    def test_pool_selector_timing_has_no_lane_execution_slo(self):
        """The selector is a support job, so it is timed but never judged.

        No Web lane consumes `select-ubuntu-runner` any more, so the fixture
        uses `package`, one of the remaining consumers. What is under test is
        unchanged: the selector's own duration must never be scored against a
        lane SLO it does not own.
        """
        manifest = self.manifest(("package",))
        results = {job: "skipped" for job in VALID_RESULTS}
        for required in manifest["required_jobs"]:
            results[required] = "success"
        report = self.validate(manifest=manifest, results=results)
        summary = self.module.render_summary(
            report,
            self.policy,
            timing_reader=lambda: [{
                "name": workflow_display_names()["select-ubuntu-runner"],
                "created_at": "2026-08-11T00:00:00Z",
                "started_at": "2026-08-11T00:00:01Z",
                "completed_at": "2026-08-11T01:00:01Z",
            }],
        )
        self.assertTrue(report.ok)
        self.assertIn(
            "Timing select-ubuntu-runner | queue 1s; execution 3600s; "
            "SLO not defined",
            summary,
        )
        self.assertNotRegex(
            summary,
            r"Timing select-ubuntu-runner .*; (?:within SLO|SLO missed)",
        )

    def test_macos_selector_has_no_slo_but_primary_keeps_core_macos_slo(self):
        manifest = self.manifest(("core_macos",))
        results = {job: "skipped" for job in VALID_RESULTS}
        for required in manifest["required_jobs"]:
            results[required] = "success"
        report = self.validate(manifest=manifest, results=results)
        display_names = workflow_display_names()
        summary = self.module.render_summary(
            report,
            self.policy,
            timing_reader=lambda: [
                {
                    "name": display_names["select-macos-runner"],
                    "created_at": "2026-08-11T00:00:00Z",
                    "started_at": "2026-08-11T00:00:01Z",
                    "completed_at": "2026-08-11T01:00:01Z",
                },
                {
                    "name": display_names["macos-primary"],
                    "created_at": "2026-08-11T00:00:00Z",
                    "started_at": "2026-08-11T00:00:01Z",
                    "completed_at": "2026-08-11T00:10:02Z",
                },
            ],
        )
        self.assertTrue(report.ok)
        self.assertIn(
            "Timing select-macos-runner | queue 1s; execution 3600s; "
            "SLO not defined",
            summary,
        )
        self.assertNotRegex(
            summary,
            r"Timing select-macos-runner .*; (?:within SLO|SLO missed)",
        )
        self.assertIn(
            "Timing macos-primary | queue 1s; execution 601s; SLO missed",
            summary,
        )

    def test_timing_uses_workflow_display_names_and_marks_missing_selected_jobs(self):
        manifest = self.manifest(("core_ubuntu", "core_macos"))
        results = {job: "skipped" for job in VALID_RESULTS}
        for job in manifest["required_jobs"]:
            results[job] = "success"
        report = self.validate(manifest=manifest, results=results)
        summary = self.module.render_summary(report, self.policy, timing_reader=lambda: [
            {"name": "Select Ubuntu runner", "created_at": "2026-08-11T00:00:00Z", "started_at": "2026-08-11T00:00:01Z", "completed_at": "2026-08-11T00:00:02Z"},
            {"name": "core (ubuntu-latest)", "created_at": "2026-08-11T00:00:00Z", "started_at": "2026-08-11T00:00:01Z", "completed_at": "2026-08-11T00:00:02Z"},
            {"name": "macOS gates (primary)", "created_at": "2026-08-11T00:00:00Z", "started_at": "2026-08-11T00:00:01Z", "completed_at": "2026-08-11T00:00:02Z"},
            {"name": "core (macos-latest)", "created_at": "2026-08-11T00:00:00Z", "started_at": "2026-08-11T00:00:01Z", "completed_at": "2026-08-11T00:00:02Z"},
            {"name": "core-asan-macos", "created_at": "2026-08-11T00:00:00Z", "started_at": "2026-08-11T00:00:01Z", "completed_at": "2026-08-11T00:00:02Z"},
        ])
        self.assertTrue(report.ok)
        for job in ("select-ubuntu-runner", "core-ubuntu", "macos-primary", "core-macos", "core-asan-macos"):
            self.assertIn(f"Timing {job}", summary)
        self.assertIn("Timing select-macos-runner | timing unavailable", summary)

    def test_all_real_display_names_and_change_scope_feed_pre_gate_critical_path(self):
        manifest = self.manifest(tuple(self.policy["lanes"]))
        results = {job: "success" for job in VALID_RESULTS}
        report = self.validate(manifest=manifest, results=results)
        display_names = workflow_display_names()
        jobs = [{
            "name": "Change Scope",
            "created_at": "2026-08-11T00:00:00Z",
            "started_at": "2026-08-11T00:00:01Z",
            "completed_at": "2026-08-11T00:00:05Z",
        }]
        for job_id, display_name in display_names.items():
            jobs.append({
                "name": display_name,
                "created_at": "2026-08-11T00:00:05Z",
                "started_at": "2026-08-11T00:00:06Z",
                "completed_at": (
                    "2026-08-11T00:10:00Z"
                    if job_id == "package"
                    else "2026-08-11T00:00:07Z"
                ),
            })

        summary = self.module.render_summary(
            report, self.policy, timing_reader=lambda: jobs
        )

        self.assertTrue(report.ok)
        self.assertEqual(set(display_names), set(VALID_RESULTS))
        self.assertEqual(len(VALID_RESULTS), 18)
        self.assertNotIn("change-scope", VALID_RESULTS)
        self.assertIn("Timing change-scope", summary)
        for job_id in display_names:
            with self.subTest(job=job_id):
                self.assertIn(f"Timing {job_id}", summary)
                self.assertNotIn(
                    f"Timing {job_id} | timing unavailable", summary
                )
        self.assertIn("Pre-Gate critical path | 600s", summary)


if __name__ == "__main__":
    unittest.main()
