#!/usr/bin/env python3
"""Contract tests for the manifest-driven PR gate.

The production change that makes these tests fail is an absent or permissive
manifest/result truth-table validator.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "scripts/ci/scope_policy.json"
GATE_PATH = ROOT / "scripts/ci/pr_gate.py"
HEAD_SHA = "a" * 40
OTHER_HEAD_SHA = "b" * 40

VALID_RESULTS = {
    "docs-static": "success",
    "portal": "success",
    "ci-contract": "skipped",
    "select-ubuntu-runner": "success",
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


def load_gate():
    spec = importlib.util.spec_from_file_location("pr_gate", GATE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load PR gate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PrGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        cls.module = load_gate()

    def manifest(self, enabled=("docs_static", "portal", "web_runtime_host")):
        lanes = {lane: lane in enabled for lane in self.policy["lanes"]}
        required_jobs = sorted({
            job for lane in enabled for job in self.policy["lane_jobs"][lane]
        })
        return {
            "schema": self.policy["manifest_schema"],
            "base_sha": OTHER_HEAD_SHA,
            "head_sha": HEAD_SHA,
            "mode": "focused",
            "reasons": ["test fixture"],
            "changed_files": [],
            "lanes": lanes,
            "required_jobs": required_jobs,
        }

    def validate(self, manifest=None, results=None, expected_head_sha=HEAD_SHA):
        return self.module.validate_gate(
            self.policy, manifest or self.manifest(), results or VALID_RESULTS,
            expected_head_sha,
        )

    def test_exact_required_success_and_unrequired_skipped_passes(self):
        report = self.validate()
        self.assertTrue(report.ok)
        self.assertEqual(report.errors, ())

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

    def test_full_manifest_requires_every_formal_job(self):
        manifest = self.manifest(tuple(self.policy["lanes"]))
        report = self.validate(manifest=manifest, results={job: "success" for job in VALID_RESULTS})
        self.assertTrue(report.ok)
        self.assertEqual(set(report.requested_jobs), set(VALID_RESULTS))

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

    def test_slo_overage_is_reported_but_success_stays_success(self):
        report = self.validate()
        summary = self.module.render_summary(report, self.policy, timing_reader=lambda: [{
            "name": "docs-static", "created_at": "2026-08-11T00:00:00Z",
            "started_at": "2026-08-11T00:00:01Z",
            "completed_at": "2026-08-11T00:03:02Z",
        }])
        self.assertTrue(report.ok)
        self.assertIn("SLO missed", summary)


if __name__ == "__main__":
    unittest.main()
