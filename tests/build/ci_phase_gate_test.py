#!/usr/bin/env python3
"""Contract tests for the fail-closed pre-heavy CI phase gate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/build"))
from ci_scope_policy_test_support import policy_transition


POLICY_PATH = ROOT / "scripts/ci/scope_policy.json"
PHASE_GATE_PATH = ROOT / "scripts/ci/phase_gate.py"


def load_phase_gate():
    spec = importlib.util.spec_from_file_location("phase_gate", PHASE_GATE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load phase gate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def requested_manifest(module, policy, lanes, *, trusted_head=True):
    return module.change_scope.classify(
        policy,
        (),
        base_sha="b" * 40,
        head_sha="a" * 40,
        event_name="workflow_dispatch",
        draft=False,
        labels=(),
        requested_lanes=lanes,
        trusted_head=trusted_head,
    )


def expected_results(module, manifest):
    selected = set(manifest["required_jobs"])
    return {
        job: "success" if job in selected else "skipped"
        for job in module.GATING_JOBS
    }


class PhaseGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        cls.module = load_phase_gate()

    def test_exact_gating_sets_are_closed(self):
        self.assertEqual(self.module.GATING_JOBS, (
            "docs-static", "ci-contract", "deploy-contract", "chameleon-lab",
            "web-toolchain-conformance", "web-runtime-host", "creator-web",
            "web-runtime-lab",
        ))
        self.assertEqual(self.module.HEAVY_JOBS, (
            "portal", "core-ubuntu", "package", "core-coverage", "core-asan",
        ))

    def test_selected_success_and_unselected_skip_pass(self):
        manifest = requested_manifest(self.module, self.policy, ("docs_static",))
        report = self.module.validate_phase_gate(
            self.policy, manifest, expected_results(self.module, manifest)
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.scope_skips, tuple(sorted(
            set(self.module.GATING_JOBS) - {"docs-static"}
        )))

    def policy_manifest(self, transition):
        inventory = self.module.change_scope.read_git_inventory(
            transition.root, transition.base_sha, transition.head_sha
        )
        return self.module.change_scope.classify(
            transition.head_policy,
            inventory,
            base_sha=transition.base_sha,
            head_sha=transition.head_sha,
            event_name="push",
            draft=False,
            labels=(),
            policy_edit_preserving=True,
        )

    def test_preserving_policy_manifest_requires_repository_proof(self):
        with policy_transition(self.policy, preserving=True) as transition:
            manifest = self.policy_manifest(transition)
            results = expected_results(self.module, manifest)
            without_repository = self.module.validate_phase_gate(
                transition.head_policy, manifest, results
            )
            with_repository = self.module.validate_phase_gate(
                transition.head_policy,
                manifest,
                results,
                repository=transition.root,
            )
        self.assertFalse(without_repository.ok)
        self.assertTrue(with_repository.ok, with_repository.errors)

    def test_nonpreserving_policy_manifest_fails_repository_proof(self):
        with policy_transition(self.policy, preserving=False) as transition:
            manifest = self.policy_manifest(transition)
            report = self.module.validate_phase_gate(
                transition.head_policy,
                manifest,
                expected_results(self.module, manifest),
                repository=transition.root,
            )
        self.assertFalse(report.ok)
        self.assertTrue(any(
            "why:" in error and "remedy:" in error for error in report.errors
        ))

    def test_unreadable_policy_history_fails_repository_proof(self):
        with policy_transition(self.policy, preserving=True) as transition:
            manifest = self.policy_manifest(transition)
            report = self.module.validate_phase_gate(
                transition.head_policy,
                manifest,
                expected_results(self.module, manifest),
                repository=transition.root / "missing",
            )
        self.assertFalse(report.ok)

    def test_selected_failure_cancel_and_skip_fail_closed(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static",)
        )
        for result in ("failure", "cancelled", "skipped"):
            with self.subTest(result=result):
                results = expected_results(self.module, manifest)
                results["docs-static"] = result
                report = self.module.validate_phase_gate(
                    self.policy, manifest, results
                )
                self.assertFalse(report.ok)
                if result == "skipped":
                    self.assertEqual(report.unexpected_skips, ("docs-static",))
                    self.assertEqual(report.primary_failures, ())
                else:
                    self.assertEqual(report.primary_failures, ("docs-static",))
                    self.assertEqual(report.unexpected_skips, ())
                self.assertTrue(report.errors)
                self.assertTrue(all(
                    "why:" in error and "remedy:" in error
                    for error in report.errors
                ))

    def test_unselected_job_that_runs_fails_closed(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static",)
        )
        for result in ("success", "failure", "cancelled"):
            with self.subTest(result=result):
                results = expected_results(self.module, manifest)
                results["ci-contract"] = result
                report = self.module.validate_phase_gate(
                    self.policy, manifest, results
                )
                self.assertFalse(report.ok)
                self.assertNotIn("ci-contract", report.scope_skips)
                self.assertIn("why:", report.errors[0])
                self.assertIn("remedy:", report.errors[0])

    def test_untrusted_selected_gating_skip_is_unexpected(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static",), trusted_head=False
        )
        results = expected_results(self.module, manifest)
        results["docs-static"] = "skipped"
        report = self.module.validate_phase_gate(
            self.policy, manifest, results
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.unexpected_skips, ("docs-static",))
        self.assertNotIn("docs-static", report.scope_skips)

    def test_unresolved_review_threads_hold_admission(self):
        """An open review thread is an admission condition, not a verdict.

        The reviewer's own result is never read. What is read is whether a
        human has resolved every finding -- by fixing or by replying -- and
        the hold sits here, before ~185 minutes of native-heavy work, rather
        than at merge where required_conversation_resolution held the same
        threads after that work had already run.
        """
        manifest = requested_manifest(self.module, self.policy, ("docs_static",))
        results = expected_results(self.module, manifest)
        clean = self.module.validate_phase_gate(
            self.policy, manifest, results, unresolved_review_threads=0,
        )
        self.assertTrue(clean.ok, clean.errors)

        held = self.module.validate_phase_gate(
            self.policy, manifest, results, unresolved_review_threads=3,
        )
        self.assertFalse(held.ok)
        message = " ".join(held.errors)
        self.assertIn("3 advisory review threads unresolved", message)
        self.assertIn("why:", message)
        self.assertIn("remedy:", message)
        self.assertIn("resolve each thread", message)

        one = self.module.validate_phase_gate(
            self.policy, manifest, results, unresolved_review_threads=1,
        )
        self.assertIn("1 advisory review thread unresolved", " ".join(one.errors))

    def test_a_dead_reviewer_posts_no_threads_and_admits(self):
        """Zero threads admits, whatever the reviewer did.

        A reviewer that failed, timed out, or never ran leaves nothing to
        resolve, and this gate must not hold the repository for it;
        advisory-review-liveness.yml is the mechanism that notices a lane
        that has gone quiet. The default is 0 so a caller that predates the
        argument admits exactly as before.
        """
        manifest = requested_manifest(self.module, self.policy, ("docs_static",))
        results = expected_results(self.module, manifest)
        report = self.module.validate_phase_gate(self.policy, manifest, results)
        self.assertTrue(report.ok, report.errors)

    def test_a_negative_or_non_integer_thread_count_fails_closed(self):
        manifest = requested_manifest(self.module, self.policy, ("docs_static",))
        results = expected_results(self.module, manifest)
        for bad in (-1, "3", None):
            with self.subTest(bad=bad):
                report = self.module.validate_phase_gate(
                    self.policy, manifest, results, unresolved_review_threads=bad,
                )
                self.assertFalse(report.ok)
                self.assertIn("non-negative integer", " ".join(report.errors))

    def test_product_gate_does_not_query_or_wait_for_review_threads(self):
        """The historical thread validator remains tested above, but unwired."""
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        gate = source.split("\n  pre-heavy-gate:\n", 1)[1].split("\n  core-ubuntu:\n", 1)[0]
        directives = "\n".join(line for line in gate.splitlines()
                               if not line.lstrip().startswith("#"))
        for needle in ("--unresolved-review-threads", "reviewThreads(", "gh api",
                       "advisory-review", "grok-review"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, directives,
                                 "why: product admission consumes obsolete PR state; remedy: preserve conversations in PR protection only")
        self.assertIn("python3 scripts/ci/phase_gate.py", gate,
                      "why: removing review must not remove product preflight; remedy: retain the phase judge")
        self.assertIn('--results-json "$PREFLIGHT_RESULTS_JSON"', gate)

    def test_change_scope_result_and_closed_json_shape_fail_closed(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static",)
        )
        valid = expected_results(self.module, manifest)
        cases = []
        missing = dict(valid)
        del missing["docs-static"]
        cases.append(missing)
        cases.append(dict(valid, invented={"result": "skipped"}))
        cases.append(dict(valid, **{"docs-static": "unknown"}))
        for results in cases:
            with self.subTest(results=results):
                self.assertFalse(self.module.validate_phase_gate(
                    self.policy, manifest, results
                ).ok)
        self.assertFalse(self.module.validate_phase_gate(
            self.policy, manifest, valid, change_scope_result="failure"
        ).ok)
        invalid_manifest = dict(manifest, invented=True)
        self.assertFalse(self.module.validate_phase_gate(
            self.policy, invalid_manifest, valid
        ).ok)
        self.assertFalse(self.module.validate_phase_gate(
            self.policy, manifest, []
        ).ok)
        with self.assertRaises(ValueError):
            self.module._load_json('{"x":1,"x":2}')

    def test_malformed_selected_and_unselected_result_values_fail_closed(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static",)
        )
        for job in ("docs-static", "ci-contract"):
            for value in ([], {}):
                with self.subTest(job=job, value=value):
                    results = expected_results(self.module, manifest)
                    results[job] = value
                    report = self.module.validate_phase_gate(
                        self.policy, manifest, results
                    )
                    self.assertFalse(report.ok)
                    self.assertTrue(report.errors)
                    self.assertTrue(all(
                        "why:" in error and "remedy:" in error
                        for error in report.errors
                    ))

    def test_cli_malformed_result_writes_failure_summary(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static",)
        )
        needs = {
            job: {"result": result}
            for job, result in expected_results(self.module, manifest).items()
        }
        needs["docs-static"] = {"result": []}
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.md"
            exit_code = self.module.main((
                "--policy", str(POLICY_PATH),
                "--manifest-json", json.dumps(manifest),
                "--results-json", json.dumps(needs),
                "--change-scope-result", "success",
                "--summary", str(summary),
            ))
            self.assertEqual(exit_code, 1)
            rendered = summary.read_text(encoding="utf-8")
        self.assertIn("| Result | fail |", rendered)
        self.assertIn("why:", rendered)
        self.assertIn("remedy:", rendered)

    def test_summary_uses_display_names_and_closed_categories(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static", "ci_contract")
        )
        results = expected_results(self.module, manifest)
        results["docs-static"] = "failure"
        results["ci-contract"] = "skipped"
        report = self.module.validate_phase_gate(
            self.policy, manifest, results
        )
        summary = self.module.render_summary(report)
        self.assertIn("| Result | fail |", summary)
        self.assertIn("Docs / static (`docs-static`)", summary)
        self.assertIn("CI contract (`ci-contract`)", summary)
        self.assertIn("Primary failure", summary)
        self.assertIn("Unexpected skip", summary)
        self.assertIn("Scope skip", summary)
        self.assertIn("why:", summary)
        self.assertIn("remedy:", summary)


if __name__ == "__main__":
    unittest.main()
