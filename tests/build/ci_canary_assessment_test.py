"""Assessment protocol tests; fake process receipts do not prove live AI isolation."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.canary import assessment as a, records as r


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        for path in a.MANIFESTS:
            self.write(path, (ROOT / path).read_text())
        self.base = self.commit()
        self.write("apps/creator-web/src/example.ts", "export const value = 1;\n")
        self.target = self.commit()
        self.context = self.collect()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def collect(self):
        return a.collect(self.root, base_sha=self.base, target_sha=self.target,
                         control_sha=self.base, policy_digest="a" * 64)

    def advice(self):
        return {"schema": a.OUTPUT_SCHEMA, "input_digest": self.context["digest"],
                "coverage": [item["id"] for item in self.context["inputs"]],
                "components": [{"id": host["id"], "impact": "patch",
                                "rationale": "Compatible correction", "unknowns": [],
                                "references": [self.target], "dependency_effects": [],
                                "changelog": [{"kind": "fixed", "text": "Correct an existing behavior",
                                               "references": [self.target]}]}
                               for host in self.context["components"]]}

    def receipt(self, backend="glm", output=None, error=None):
        return {"backend": backend, "model": "fixture-model", "elapsed_seconds": 1,
                "input_digest": self.context["digest"],
                "returncode": 1 if error else 0, "error_class": error,
                "output": json.dumps(self.advice() if output is None else output)}

    def observe(self, history=None, **kwargs):
        return a.observe(self.context, history or [], self.receipt(**kwargs))

    def test_complete_input_has_each_delta_and_both_manifest_endpoints(self):
        ids = [item["id"] for item in self.context["inputs"]]
        self.assertIn("commit:" + self.target, ids)
        self.assertEqual(len(ids), 1 + 2 * len(a.MANIFESTS))
        self.assertEqual(self.context["target_sha"], self.target)
        self.assertFalse(self.context["admission_evidence"])

    def test_revert_retains_both_deltas_and_pinned_context(self):
        self.git("revert", "--no-edit", self.target)
        self.target = self.git("rev-parse", "HEAD")
        context = self.collect()
        self.assertEqual(len(context["commits"]), 2)
        self.write("apps/creator-web/module.json", "dirty")
        self.assertEqual(self.collect(), context)

    def test_rename_keeps_old_and_new_paths_in_patch(self):
        self.git("mv", "apps/creator-web/src/example.ts", "apps/creator-web/src/renamed.ts")
        self.target = self.commit()
        context = self.collect()
        patch = context["inputs"][1]["content"]
        self.assertIn("example.ts", patch)
        self.assertIn("renamed.ts", patch)

    def test_missing_baseline_is_not_empty_success(self):
        self.base = "0" * 40
        with self.assertRaises(r.CanaryError):
            self.collect()

    def test_large_input_is_rejected_not_truncated(self):
        self.write("large.txt", "a" * a.MAX_INPUT_BYTES)
        self.target = self.commit()
        with self.assertRaisesRegex(r.CanaryError, "budget"):
            self.collect()

    def test_first_valid_result_stops_chain(self):
        history = self.observe()
        self.assertIsNone(a.next_backend(self.context, history))
        result = a.finish(self.context, history)
        self.assertEqual(result["state"], "advised")
        self.assertIsNone(result["report_intent"])
        self.assertFalse(result["admission_evidence"])
        with self.assertRaises(r.CanaryError):
            self.observe(history, backend="kimi")

    def test_fallback_follows_glm_kimi_grok(self):
        history = self.observe(error="rate_limited")
        self.assertEqual(a.next_backend(self.context, history), "kimi")
        history = self.observe(history, backend="kimi", error="service_error")
        history = self.observe(history, backend="grok")
        self.assertEqual(a.finish(self.context, history)["selected_backend"], "grok")

    def test_all_failed_has_stable_report_intent_not_success(self):
        history = []
        for backend in a.BACKENDS:
            history = self.observe(history, backend=backend, error="timeout")
        result = a.finish(self.context, history)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["report_intent"]["reason"], "backends_unavailable")
        self.assertEqual(a.finish(self.context, history), result)
        self.assertNotIn("output", json.dumps(result))

    def test_major_is_valid_but_paused_without_asking_another_model(self):
        advice = self.advice()
        advice["components"][0]["impact"] = "major"
        history = self.observe(output=advice)
        self.assertIsNone(a.next_backend(self.context, history))
        self.assertEqual(a.finish(self.context, history)["report_intent"]["reason"], "compatibility_review")

    def test_unknown_and_migration_pause(self):
        for field, value in (("unknowns", ["Compatibility unclear"]),
                             ("changelog", [{"kind": "migration", "text": "Needs migration",
                                             "references": [self.target]}])):
            with self.subTest(field=field):
                advice = self.advice()
                advice["components"][0][field] = value
                self.assertEqual(a.finish(self.context, self.observe(output=advice))["state"], "blocked")

    def test_invented_reference_rejected(self):
        advice = self.advice()
        advice["components"][0]["references"] = ["b" * 40]
        self.assertEqual(self.observe(output=advice)[0]["error_class"], "invalid_output")

    def test_missing_input_coverage_rejected(self):
        advice = self.advice()
        advice["coverage"].pop()
        self.assertEqual(self.observe(output=advice)[0]["error_class"], "invalid_output")

    def test_missing_component_rejected(self):
        advice = self.advice()
        advice["components"].pop()
        self.assertEqual(self.observe(output=advice)[0]["error_class"], "invalid_output")

    def test_stale_input_digest_rejected(self):
        advice = self.advice()
        advice["input_digest"] = "b" * 64
        self.assertEqual(self.observe(output=advice)[0]["error_class"], "invalid_output")

    def test_command_field_is_rejected_not_executed(self):
        advice = self.advice()
        advice["command"] = "touch /tmp/should-not-execute"
        self.assertEqual(self.observe(output=advice)[0]["error_class"], "invalid_output")

    def test_duplicate_json_and_truncated_json_are_invalid(self):
        for raw in ('{"schema":1,"schema":2}', '{"schema":'):
            receipt = self.receipt()
            receipt["output"] = raw
            self.assertEqual(a.observe(self.context, [], receipt)[0]["error_class"], "invalid_output")

    def test_timeout_receipt_over_budget_cannot_produce_advice(self):
        receipt = self.receipt()
        receipt["elapsed_seconds"] = a.MAX_BACKEND_SECONDS + 1
        self.assertEqual(a.observe(self.context, [], receipt)[0]["error_class"], "timeout")

    def test_raw_provider_error_is_not_retained(self):
        receipt = self.receipt(error="service_error")
        receipt["output"] = "secret provider exception"
        history = a.observe(self.context, [], receipt)
        self.assertNotIn("secret", json.dumps(history))

    def test_wrong_order_or_forged_history_rejected(self):
        with self.assertRaises(r.CanaryError):
            self.observe(backend="grok")
        history = self.observe()
        history[0]["advice"]["input_digest"] = "c" * 64
        with self.assertRaises(r.CanaryError):
            a.finish(self.context, history)

    def test_partial_chain_cannot_be_finished(self):
        with self.assertRaises(r.CanaryError):
            a.finish(self.context, self.observe(error="missing_credential"))

    def test_empty_interval_cannot_invent_a_bump(self):
        self.base = self.target
        self.context = self.collect()
        self.assertEqual(self.observe()[0]["error_class"], "invalid_output")
        advice = self.advice()
        for component in advice["components"]:
            component.update(impact="none", references=[], changelog=[])
        self.assertEqual(a.finish(self.context, self.observe(output=advice))["state"], "advised")

    def test_unchanged_component_cannot_announce_changes(self):
        advice = self.advice()
        advice["components"][0]["impact"] = "none"
        self.assertEqual(self.observe(output=advice)[0]["error_class"], "invalid_output")

    def test_unknown_changelog_component_and_dependency_field_rejected(self):
        for mutate in (
            lambda doc: doc["components"][0].update(id="invented-host"),
            lambda doc: doc["components"][0]["changelog"][0].update(command="run this"),
            lambda doc: doc["components"][0].update(dependency_effects={"command": "run this"}),
        ):
            with self.subTest(mutate=mutate):
                advice = self.advice()
                mutate(advice)
                self.assertEqual(self.observe(output=advice)[0]["error_class"], "invalid_output")

    def test_pinned_target_does_not_follow_moving_main(self):
        self.write("later.txt", "not this candidate")
        self.commit()
        self.assertEqual(self.collect(), self.context)

    def test_changed_content_without_digest_update_blocks(self):
        context = deepcopy(self.context)
        context["inputs"][0]["content"] += "tampered"
        with self.assertRaises(r.CanaryError):
            a.next_backend(context, [])

    def test_resealed_omitted_input_still_blocks(self):
        context = deepcopy(self.context)
        context["inputs"].pop()
        with self.assertRaises(r.CanaryError):
            a.next_backend(r.seal(context), [])

    def test_pinned_assembly_malformed_json_blocks(self):
        self.write("products/lmdj/assembly.json", "not json")
        self.target = self.commit()
        with self.assertRaises(r.CanaryError):
            self.collect()

    def test_boolean_nan_negative_duration_are_not_process_receipts(self):
        for elapsed in (True, float("nan"), -1):
            with self.subTest(elapsed=elapsed), self.assertRaises(r.CanaryError):
                receipt = self.receipt()
                receipt["elapsed_seconds"] = elapsed
                a.observe(self.context, [], receipt)

    def test_nonzero_process_result_does_not_accept_valid_json(self):
        receipt = self.receipt()
        receipt["returncode"] = 2
        self.assertEqual(a.observe(self.context, [], receipt)[0]["error_class"], "runtime_failure")

    def test_context_and_history_remain_unchanged(self):
        context = deepcopy(self.context)
        history = self.observe(error="rate_limited")
        original = deepcopy(history)
        result = self.observe(history, backend="kimi")
        a.finish(self.context, result)
        self.assertEqual(self.context, context)
        self.assertEqual(history, original)

    def test_failed_history_cannot_be_reused_for_another_candidate(self):
        history = self.observe(error="rate_limited")
        self.write("later.txt", "new assessment inputs")
        self.target = self.commit()
        self.context = self.collect()
        with self.assertRaisesRegex(r.CanaryError, "another input"):
            self.observe(history, backend="kimi")

    def test_wrong_input_failure_receipt_does_not_consume_attempt(self):
        receipt = self.receipt(error="rate_limited")
        receipt["input_digest"] = "b" * 64
        with self.assertRaisesRegex(r.CanaryError, "another input"):
            a.observe(self.context, [], receipt)

    def test_resealed_unsupported_host_version_is_still_rejected(self):
        context = deepcopy(self.context)
        context["components"][0]["target_version"] = "1.0.0-preview"
        item = next(item for item in context["inputs"] if item["id"] == "target:apps/creator-web/module.json")
        manifest = json.loads(item["content"])
        manifest["version"] = "1.0.0-preview"
        item["content"] = json.dumps(manifest)
        item["digest"] = r.digest(item["content"])
        with self.assertRaisesRegex(r.CanaryError, "SemVer"):
            a.next_backend(r.seal(context), [])

    def test_infrastructure_and_compatibility_reports_do_not_reuse_payload_identity(self):
        history = []
        for backend in a.BACKENDS:
            history = self.observe(history, backend=backend, error="timeout")
        failed = a.finish(self.context, history)["report_intent"]
        advice = self.advice()
        advice["components"][0]["impact"] = "major"
        uncertain = a.finish(self.context, self.observe(output=advice))["report_intent"]
        self.assertNotEqual(failed["id"], uncertain["id"])


if __name__ == "__main__":
    unittest.main()
