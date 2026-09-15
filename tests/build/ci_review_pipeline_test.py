#!/usr/bin/env python3
"""Adapter contracts with real artifact files and strict bounded process doubles.

Backend network/authentication and GitHub writes are explicitly O1 gaps. The
tests do not turn a mocked write into evidence of platform permissions.
"""
import copy
import hashlib
import json
import os
import re
import shlex
from pathlib import Path
import subprocess
import stat
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
import contextlib
import io
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import review_pipeline as pipeline
import review_scope
import pr_agent_review as t2
import test_scope


class PipelineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.identity = dict(repository="endaye/lmdj", pr_number=7, head_sha="a" * 40,
                             base_sha="b" * 40, control_sha="c" * 40, backend="deterministic", run_id=99, run_attempt=1)
        self.model = {"schema": review_scope.REVIEW_SCHEMA, "summary": "Reviewed.", "findings": [],
                      "test_scope": {"labels": ["test:none"], "reason": "Original explanatory document rationale."}}
        pipeline.save(self.directory / "context.json", {"identity": self.identity, "changed_paths": ["docs/notes/a.md"]})
        pipeline.save(self.directory / "history.json", [])
        self.env = {"GITHUB_OUTPUT": str(self.directory / "output"), "REVIEW_JSON": json.dumps(self.model),
                    "BACKEND_OUTCOME": "success", "BACKEND_AVAILABLE": "true"}

    def capture(self, backend, **env):
        with mock.patch.dict(os.environ, {**self.env, **env}):
            pipeline.capture(self.directory, backend)

    def test_glm_success_persists_full_original_model(self):
        self.capture("glm")
        pipeline.finalize(self.directory)
        self.assertEqual(pipeline.read(self.directory / "review.json"), self.model)
        self.assertEqual(pipeline.read(self.directory / "result.json")["status"], "reviewed")
        self.assertIn("reviewed=true", (self.directory / "output").read_text())

    def test_glm_failure_then_kimi_success_preserves_each_receipt(self):
        self.capture("glm", BACKEND_OUTCOME="failure")
        self.capture("kimi")
        pipeline.finalize(self.directory)
        history = pipeline.read(self.directory / "history.json")
        self.assertEqual([item["status"] for item in history], ["failed", "reviewed"])
        self.assertEqual(pipeline.read(self.directory / "result.json")["publication"]["record"]["backend"], "kimi")

    def test_invalid_json_triggers_next_backend(self):
        self.capture("glm", REVIEW_JSON="not-json")
        history = pipeline.read(self.directory / "history.json")
        self.assertEqual(history[0]["error_class"], "invalid_output")
        self.assertEqual(review_scope.next_backend(test_scope.load_policy(ROOT), history), "kimi")

    def test_missing_key_is_not_empty_success(self):
        self.capture("glm", BACKEND_AVAILABLE="false", BACKEND_OUTCOME="skipped")
        self.assertEqual(pipeline.read(self.directory / "history.json")[0]["error_class"], "missing_credential")

    def test_all_failure_persists_failure_not_clean_review(self):
        for backend in review_scope.BACKENDS:
            self.capture(backend, BACKEND_OUTCOME="failure")
        pipeline.finalize(self.directory)
        failure = pipeline.read(self.directory / "failure.json")
        self.assertEqual(failure["status"], "not-reviewed")
        self.assertEqual(len(failure["attempts"]), 3)
        self.assertFalse((self.directory / "review.json").exists())

    def cli(self, *arguments, env=None):
        """Run the real CLI the workflow runs, and return `(returncode, stderr)`.

        The workflow reads an exit code, not a return value, so that is what
        this asserts. Calling `finalize()` directly would pass whatever the
        function does and say nothing about the job's conclusion, which is the
        thing #939 was about.
        """
        environment = {**os.environ, **self.env, **(env or {})}
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/ci/review_pipeline.py"),
             *arguments, "--directory", str(self.directory)],
            capture_output=True, text=True, timeout=60, env=environment,
        )
        return completed.returncode, completed.stderr

    def test_finalize_exits_nonzero_when_no_model_reviewed(self):
        # The producer job is named `Review fallback`; its conclusion is what a
        # reader scanning job names sees. Reporting success over a
        # `not-reviewed` artifact makes that name a lie.
        for backend in review_scope.BACKENDS:
            self.capture(backend, BACKEND_OUTCOME="failure")
        code, stderr = self.cli("finalize")
        self.assertEqual(code, 1)
        self.assertIn("no model reviewed this head", stderr)

    def test_finalize_still_writes_every_receipt_when_it_fails(self):
        # The exit code changes; the evidence must not. A dropped review is
        # recoverable from this artifact, which is how #916's was found hours
        # later, so failing must not cost the receipts.
        for backend in review_scope.BACKENDS:
            self.capture(backend, BACKEND_OUTCOME="failure")
        code, _ = self.cli("finalize")
        self.assertEqual(code, 1)
        result = pipeline.read(self.directory / "result.json")
        self.assertEqual(result["status"], "not-reviewed")
        failure = pipeline.read(self.directory / "failure.json")
        self.assertEqual(len(failure["attempts"]), 3)
        self.assertTrue((self.directory / "history.json").exists())
        self.assertTrue((self.directory / "context.json").exists())

    def test_finalize_exits_zero_when_a_model_did_review(self):
        # The positive control. Without it the case above would pass against a
        # `finalize` that always failed, which would be a different defect and
        # would read identically here.
        self.capture("glm")
        code, stderr = self.cli("finalize")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(
            pipeline.read(self.directory / "result.json")["status"], "reviewed")

    def test_a_crash_and_a_clean_not_reviewed_are_told_apart(self):
        # Both exit nonzero, so the job fails either way -- but a reader
        # diagnosing the run must be able to tell "the backends were down" from
        # "the pipeline broke". Same exit code, different stderr.
        code, stderr = self.cli("finalize")  # empty history: chain unfinished
        self.assertEqual(code, 1)
        self.assertIn("review pipeline operation failed", stderr)
        self.assertNotIn("no model reviewed this head", stderr)

    def test_publish_prints_which_precondition_refused(self):
        """#939: the publisher's refusals must name themselves.

        It drops roughly one review in four and every log said only "review
        pipeline operation failed", so no remedy could be designed: a retry
        aimed at the wrong precondition would look like a fix and change
        nothing. These messages already existed at every `require` in
        `publish()`; the handler was destroying them.
        """
        self.capture("glm")
        pipeline.finalize(self.directory)
        # The publisher's whole environment, with exactly one value wrong, so
        # the first `require` in `publish()` is the only thing that can fire.
        code, stderr = self.cli("publish", env={
            "GITHUB_REPOSITORY": self.identity["repository"],
            "PR_NUMBER": "999999",
            "HEAD_SHA": self.identity["head_sha"],
            "GITHUB_RUN_ID": str(self.identity["run_id"]),
            "GITHUB_RUN_ATTEMPT": str(self.identity["run_attempt"]),
        })
        self.assertEqual(code, 1)
        self.assertIn("artifact identity differs from publisher context", stderr)
        self.assertNotIn("review pipeline operation failed", stderr)

    def test_commands_with_provider_text_in_scope_keep_the_generic_message(self):
        """finalize/capture retain generic diagnostics while provider text is in scope;
        publish and pre-model collect-t2 print their authored refusals instead."""
        code, stderr = self.cli("finalize")
        self.assertEqual(code, 1)
        self.assertIn("review pipeline operation failed", stderr)
        self.assertNotIn("review chain did not finish", stderr)

    def publisher_error(self, operation):
        errors = io.StringIO()
        with mock.patch.object(sys, "argv", ["review_pipeline.py", "publish",
                "--directory", str(self.directory)]), \
                mock.patch.object(pipeline, "publish", side_effect=operation), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(pipeline.main(), 1)
        return errors.getvalue()

    def test_publish_reports_http_status_through_real_api_error_wrapper(self):
        secret = "PRIVATE-token-url-body-header"
        response = io.BytesIO(secret.encode())
        error = urllib.error.HTTPError("https://example.invalid/" + secret,
                                      403, secret, {"secret": secret}, response)
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": secret}), \
                mock.patch.object(pipeline.pr_review_target.urllib.request,
                                  "urlopen", side_effect=error):
            stderr = self.publisher_error(lambda _: pipeline.api("/" + secret))
        self.assertIn("category=http-error status=403", stderr)
        self.assertNotIn(secret, stderr)
        self.assertLessEqual(response.tell(), 4097)

    def http_refusal(self, body, headers=None, url=None, code=403):
        response = body if hasattr(body, "read") else io.BytesIO(body)
        error = urllib.error.HTTPError(url or
            "https://api.github.com/repos/endaye/lmdj/actions/runs/99/attempts/1",
            code, "PRIVATE", headers or {}, response)
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "PRIVATE"}), \
                mock.patch.object(pipeline.pr_review_target.urllib.request,
                                  "urlopen", side_effect=error):
            stderr = self.publisher_error(lambda _: pipeline.api("/PRIVATE"))
        self.assertNotIn("PRIVATE", stderr)
        return stderr

    def test_http_primary_limit_retains_numeric_headers_through_api_wrapper(self):
        stderr = self.http_refusal(b'{"message":"PRIVATE"}', {
            "x-ratelimit-remaining": "0", "x-ratelimit-reset": "1789310000",
            "retry-after": "60", "authorization": "PRIVATE"})
        self.assertIn("reason=primary-rate-limit", stderr)
        self.assertIn("endpoint=run-attempt", stderr)
        self.assertIn("remaining=0 reset=1789310000 retry-after=60", stderr)

    def test_http_secondary_limit_uses_closed_message_category(self):
        stderr = self.http_refusal(json.dumps({"message":
            "You have exceeded a secondary rate limit. PRIVATE"}).encode(), code=429)
        self.assertIn("status=429", stderr)
        self.assertIn("reason=secondary-rate-limit", stderr)

    def test_http_permission_refusal_uses_closed_message_category(self):
        stderr = self.http_refusal(b'{"message":"Resource not accessible by integration"}')
        self.assertIn("reason=integration-permission", stderr)

    def test_non_refusal_http_status_does_not_read_response_body(self):
        body = io.BytesIO(b"PRIVATE")
        stderr = self.http_refusal(body, code=500)
        self.assertIn("category=http-error status=500", stderr)
        self.assertNotIn("reason=", stderr)
        self.assertEqual(body.tell(), 0)

    def test_non_publish_http_failure_never_reads_or_projects_response(self):
        body = io.BytesIO(b"PRIVATE")
        error = urllib.error.HTTPError("PRIVATE", 403, "PRIVATE", {}, body)
        errors = io.StringIO()
        with mock.patch.object(sys, "argv", ["review_pipeline.py", "finalize",
                "--directory", str(self.directory)]), \
                mock.patch.object(pipeline, "finalize", side_effect=error), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(pipeline.main(), 1)
        self.assertNotIn("PRIVATE", errors.getvalue())
        self.assertNotIn("category=", errors.getvalue())
        self.assertEqual(body.tell(), 0)

    def test_http_refusal_drops_non_decimal_or_overlong_headers_and_unknown_url(self):
        for value in ("PRIVATE", "1\nPRIVATE", "9" * 100, "-1", "１２"):
            with self.subTest(value=value):
                stderr = self.http_refusal(b'{"message":"PRIVATE"}', {
                    "x-ratelimit-remaining": value, "x-ratelimit-reset": value,
                    "retry-after": value}, "https://PRIVATE.invalid/PRIVATE")
                self.assertIn("endpoint=unknown reason=unknown", stderr)
                self.assertNotIn("remaining=", stderr)
                self.assertNotIn("reset=", stderr)
                self.assertNotIn("retry-after=", stderr)

    def test_http_refusal_body_is_bounded_and_never_uses_partial_json(self):
        body = io.BytesIO(b'{"message":"Resource not accessible by integration",'
                          b'"padding":"' + b'x' * 10000 + b'"}')
        self.assertIn("reason=unknown", self.http_refusal(body))
        self.assertEqual(body.tell(), 4097)

    def test_http_refusal_unreadable_or_invalid_body_keeps_original_failure(self):
        broken = mock.Mock()
        broken.read.side_effect = TimeoutError("PRIVATE")
        for body in (b"PRIVATE", b"[]", b'{"message":null}', b"\xff", broken):
            with self.subTest(body_type=type(body).__name__):
                self.assertIn("status=403 endpoint=run-attempt reason=unknown",
                              self.http_refusal(body))

    def test_publish_distinguishes_network_failure_from_http_refusal(self):
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "PRIVATE"}), \
                mock.patch.object(pipeline.pr_review_target.urllib.request, "urlopen",
                                  side_effect=urllib.error.URLError("PRIVATE")):
            stderr = self.publisher_error(lambda _: pipeline.api("/PRIVATE"))
        self.assertIn("category=network-error", stderr)
        self.assertNotIn("PRIVATE", stderr)

    def test_publish_unknown_error_does_not_print_message_or_dynamic_class(self):
        error = type("PRIVATE", (Exception,), {})("PRIVATE")
        stderr = self.publisher_error(error)
        self.assertIn("category=unexpected-error", stderr)
        self.assertNotIn("PRIVATE", stderr)

    def test_publish_does_not_emit_non_numeric_http_status(self):
        error = urllib.error.HTTPError("PRIVATE", "PRIVATE", "PRIVATE", {}, None)
        stderr = self.publisher_error(error)
        self.assertIn("category=http-error", stderr)
        self.assertNotIn("status=", stderr)
        self.assertNotIn("PRIVATE", stderr)

    def test_publish_cyclic_causes_terminate_without_printing_exception(self):
        error = RuntimeError("PRIVATE")
        error.__cause__ = error
        stderr = self.publisher_error(error)
        self.assertIn("category=unexpected-error", stderr)
        self.assertNotIn("PRIVATE", stderr)

    def test_publish_known_failure_categories_are_literal_and_secret_safe(self):
        for error, category in (
            (TimeoutError("PRIVATE"), "timeout"),
            (subprocess.TimeoutExpired(["PRIVATE"], 60, output="PRIVATE"), "timeout"),
            (FileNotFoundError("PRIVATE"), "file-missing"),
            (PermissionError("PRIVATE"), "permission-denied"),
            (json.JSONDecodeError("PRIVATE", "PRIVATE", 0), "invalid-json"),
            (UnicodeError("PRIVATE"), "invalid-encoding"),
            (KeyError("PRIVATE"), "missing-field"),
            (OSError("PRIVATE"), "os-error"),
        ):
            with self.subTest(category=category, error_type=type(error).__name__):
                stderr = self.publisher_error(error)
                self.assertIn("category=" + category, stderr)
                self.assertNotIn("PRIVATE", stderr)

    def test_attempt_after_success_is_refused(self):
        self.capture("glm")
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "fallback order"):
            self.capture("kimi")

    def test_partial_chain_is_not_finalized(self):
        self.capture("glm", BACKEND_OUTCOME="failure")
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "did not finish"):
            pipeline.finalize(self.directory)

    def test_engine_process_failure_records_one_failed_deepseek_attempt(self):
        # The engine crashed or was refused before printing a result: the
        # attempt still happened under the trusted provider order, so history
        # records one failed deepseek attempt and finalize reports not-reviewed
        # instead of leaving the chain unfinished.
        source = json.loads((ROOT / "tests/fixtures/ci/pr-agent/complete-input.json").read_text())
        # Production identities carry the numeric GitHub run id; re-sign the fixture with one.
        source["identity"]["run_id"] = "99"
        unsigned = copy.deepcopy(source)
        unsigned.pop("input_sha256", None)
        source["input_sha256"] = hashlib.sha256(
            json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        authenticated = t2.authenticate_input(source)
        identity = {"repository": authenticated["identity"]["repository"], "pr_number": authenticated["identity"]["pull_request"],
                    "head_sha": authenticated["identity"]["head_sha"], "base_sha": authenticated["identity"]["base_sha"],
                    "control_sha": authenticated["identity"]["control_sha"], "backend": "deterministic",
                    "run_id": 99, "run_attempt": authenticated["identity"]["run_attempt"]}
        collector = pipeline.collector_witness(source)
        engine = {"name": "pr-agent", "source_commit": "1" * 40, "version": "0.45.0",
                  "bundle": {"archive_sha256": "2" * 64, "archive_byte_length": 7, "manifest_sha256": "3" * 64,
                             "adapter_sha256": "4" * 64, "default_config_sha256": "5" * 64,
                             "requirements_lock_sha256": "6" * 64, "stock_tokenizer_asset_sha256": "7" * 64},
                  "runtime_config": {"sha256": "8" * 64, "byte_length": 7}}
        trusted = {"schema": review_scope.TRUSTED_CONFIG_SCHEMA, "provider_order": ["deepseek", "glm", "xai", "kimi"],
                   "providers": {"deepseek": {"enabled": True, "model": "deepseek/deepseek-flash"},
                                 "glm": {"enabled": False}, "xai": {"enabled": False}, "kimi": {"enabled": False}},
                   "engine": engine}
        pipeline.save(self.directory / "context.json",
                      {"identity": identity, "changed_paths": sorted({h["path"] for h in collector["expected_hunks"]})})
        pipeline.save(self.directory / "t2-input.json", source)
        pipeline.save(self.directory / "t2-config-witness.json", trusted)
        cases = {
            "no result file": (None, "failure", "service_error"),
            "engine-level refusal": ({"schema": t2.RESULT_SCHEMA, "status": "not-reviewed",
                                      "error_class": "authentication_error", "error": "bounded"}, "failure", "missing_credential"),
            "budget refusal": ({"schema": t2.RESULT_SCHEMA, "status": "not-reviewed",
                                "error_class": "budget_exhausted", "error": "bounded"}, "failure", "budget_exhausted"),
            "killed by step timeout": (None, "cancelled", "timeout"),
            "garbage on stdout": ("Traceback (most recent call last)", "failure", "service_error"),
        }
        for label, (result, outcome, expected) in cases.items():
            with self.subTest(case=label):
                result_path = self.directory / "t2-result.json"
                if result is None:
                    result_path.unlink(missing_ok=True)
                elif isinstance(result, str):
                    result_path.write_text(result, encoding="utf-8")
                else:
                    pipeline.save(result_path, result)
                pipeline.save(self.directory / "history.json", [])
                for stale in ("result.json", "failure.json", "review.json"):
                    (self.directory / stale).unlink(missing_ok=True)
                self.capture("deepseek", BACKEND_OUTCOME=outcome, T2_RESULT_JSON=str(result_path), REVIEW_JSON="")
                history = pipeline.read(self.directory / "history.json")
                self.assertEqual(history["schema"], review_scope.HISTORY_SCHEMA_V2)
                self.assertEqual([(a["backend"], a["status"], a["error_class"]) for a in history["attempts"]],
                                 [("deepseek", "failed", expected)])
                self.assertIsNone(history["attempts"][0]["coverage_sha256"])
                self.assertEqual(pipeline.read(self.directory / "collector.json"), collector)
                self.assertEqual(pipeline.read(self.directory / "t2-config-witness.json"), trusted)
                self.assertIn("reviewed=false", (self.directory / "output").read_text())
                self.assertEqual(pipeline.finalize(self.directory), "not-reviewed")
                self.assertTrue((self.directory / "failure.json").exists())
                self.assertFalse((self.directory / "review.json").exists())
        # A completed attempt history is never overwritten by a synthesized failure.
        pipeline.save(self.directory / "history.json", history)
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "existing attempt history"):
            self.capture("deepseek", BACKEND_OUTCOME="failure", T2_RESULT_JSON=str(self.directory / "absent.json"), REVIEW_JSON="")

    def test_schema_vocabulary_matches_every_label_the_validator_accepts(self):
        policy = test_scope.load_policy(ROOT)
        labels = pipeline.response_schema(policy)["properties"]["test_scope"]["properties"]["labels"]
        self.assertEqual(labels["minItems"], 1,
                         "why: empty advice is rejected downstream; remedy: require a label during generation")
        allowed = labels["items"]["enum"]
        self.assertCountEqual(allowed, ["test:none", "test:full"] + [f"test:{s}" for s in policy.suite_ids],
                              "why: model and validator vocabularies differ; remedy: derive all labels from policy")
        for label in allowed:
            with self.subTest(label=label):
                model = dict(self.model, test_scope={"labels": [label], "reason": "Scope rationale."})
                self.assertEqual(review_scope.validate_review(policy, model), model)

    def test_t2_result_adapter_consumes_actual_coverage_without_outer_fallback(self):
        source = json.loads((ROOT / "tests/fixtures/ci/pr-agent/complete-input.json").read_text())
        authenticated = t2.authenticate_input(source)
        coverage = t2._validate_coverage_receipt(t2._make_coverage(
            authenticated, provider="deepseek",
            model={"requested": "fixture-model", "actual": "fixture-served",
                   "response_version": "fixture-v1", "pricing_revision": "fixture-v1"},
            prompt=t2.render_prompt_input(authenticated), usage=None))
        identity = {"repository": "endaye/lmdj", "pr_number": authenticated["identity"]["pull_request"],
                    "head_sha": authenticated["identity"]["head_sha"], "base_sha": authenticated["identity"]["base_sha"],
                    "control_sha": authenticated["identity"]["control_sha"], "backend": "deterministic",
                    "run_id": authenticated["identity"]["run_id"], "run_attempt": authenticated["identity"]["run_attempt"]}
        attempt = {"status": "not-reviewed", "error_class": "rate_limited", "error": "bounded",
                   "provider": "deepseek", "model": coverage["model"], "engine": coverage["engine"],
                   "review": None, "native_review": None, "coverage": coverage,
                   "usage": coverage["usage"], "duration_ms": 1}
        result = {"schema": "lmdj.pr-agent-result.v1", "status": "not-reviewed", "error_class": "rate_limited",
                  "identity": authenticated["identity"], "input_sha256": authenticated["input_sha256"],
                  "engine": coverage["engine"], "selected_attempt": None, "attempts": [attempt],
                  "skipped_providers": [{"provider": "glm", "status": "disabled"}], "elapsed_ms": 1}
        paths = sorted({hunk["path"] for hunk in coverage["expected_hunks"]})
        collector = pipeline.collector_witness(source)
        trusted = {"schema": review_scope.TRUSTED_CONFIG_SCHEMA, "provider_order": ["deepseek"],
                   "providers": {"deepseek": {"enabled": True, "model": "fixture-model"},
                                 "glm": {"enabled": False}, "xai": {"enabled": False}, "kimi": {"enabled": False}},
                   "engine": coverage["engine"]}
        history, inventory = pipeline.adapt_t2_result(result, identity=identity, changed_paths=paths,
                                                       collector=collector, trusted_config=trusted)
        self.assertEqual(history["attempts"][0]["backend"], "deepseek")
        self.assertIsNone(review_scope.next_backend(test_scope.load_policy(ROOT), history, identity=identity,
                                                    coverages=inventory, changed_paths=paths))

    def test_same_path_two_hunk_drop_is_rejected_by_independent_collector(self):
        source = json.loads((ROOT / "tests/fixtures/ci/pr-agent/complete-input.json").read_text())
        second_hunk = "@@ -4,0 +5 @@\n+tail\n"
        source["diff"]["text"] = source["diff"]["text"].replace(
            "\ndiff --git a/obsolete.txt", second_hunk + "\ndiff --git a/obsolete.txt", 1)
        source["files"][0]["patch"] += second_hunk
        source["files"][0]["patch_sha256"] = hashlib.sha256(source["files"][0]["patch"].encode()).hexdigest()
        source["files"][0]["hunks"].append({
            "id": "src-example-h2", "patch": second_hunk,
            "patch_sha256": hashlib.sha256(second_hunk.encode()).hexdigest(),
            "right_lines": [{"line": 5, "text": "tail", "sha256": hashlib.sha256(b"tail").hexdigest()}],
        })
        diff_bytes = source["diff"]["text"].encode()
        source["diff"]["byte_length"] = len(diff_bytes)
        source["diff"]["sha256"] = hashlib.sha256(diff_bytes).hexdigest()
        unsigned = copy.deepcopy(source)
        unsigned.pop("input_sha256", None)
        source["input_sha256"] = hashlib.sha256(
            json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        authenticated = t2.authenticate_input(source)
        collector = pipeline.collector_witness(source)
        engine = {"name": "pr-agent", "source_commit": "1" * 40, "version": "0.45.0",
                  "bundle": {key: value for key, value in {
                      "archive_sha256": "2" * 64, "archive_byte_length": 7,
                      "manifest_sha256": "3" * 64, "adapter_sha256": "4" * 64,
                      "default_config_sha256": "5" * 64, "requirements_lock_sha256": "6" * 64,
                      "stock_tokenizer_asset_sha256": "7" * 64}.items()},
                  "runtime_config": {"sha256": "8" * 64, "byte_length": 7}}
        trusted = {"schema": review_scope.TRUSTED_CONFIG_SCHEMA, "provider_order": ["deepseek"],
                   "providers": {"deepseek": {"enabled": True, "model": "fixture-model"},
                                 "glm": {"enabled": False}, "xai": {"enabled": False}, "kimi": {"enabled": False}},
                   "engine": engine}
        coverage = t2._validate_coverage_receipt(t2._make_coverage(
            authenticated, provider="deepseek",
            model={"requested": "fixture-model", "actual": "fixture-served",
                   "response_version": "fixture-v1", "pricing_revision": "fixture-v1"},
            prompt=t2.render_prompt_input(authenticated), usage=None, engine=engine))
        identity = {**authenticated["identity"], "pr_number": authenticated["identity"]["pull_request"],
                    "backend": "deterministic"}
        attempt = {"status": "reviewed", "error_class": None, "error": None,
                   "provider": "deepseek", "model": coverage["model"], "engine": engine,
                   "review": {"summary": "Reviewed.", "findings": []}, "native_review": {},
                   "coverage": coverage, "usage": coverage["usage"], "duration_ms": 1}
        result = {"schema": "lmdj.pr-agent-result.v1", "status": "reviewed", "error_class": None,
                  "identity": authenticated["identity"], "input_sha256": authenticated["input_sha256"],
                  "engine": engine, "selected_attempt": 0, "attempts": [attempt],
                  "skipped_providers": [{"provider": "glm", "status": "disabled"}], "elapsed_ms": 1}
        forged = copy.deepcopy(result)
        forged_coverage = forged["attempts"][0]["coverage"]
        forged_coverage["expected_hunks"].pop(1)
        forged_coverage["observed_hunks"].pop(1)
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "independently authenticated collector"):
            pipeline.adapt_t2_result(forged, identity=identity,
                                     changed_paths=sorted({h["path"] for h in collector["expected_hunks"]}),
                                     collector=collector, trusted_config=trusted)

    def test_actual_t2_run_engine_reviewed_output_reaches_v2_publisher(self):
        runtime = Path(os.environ.get("PR_AGENT_TEST_PYTHON", ""))
        source_root = Path(os.environ.get("PR_AGENT_TEST_SOURCE_ROOT", ""))
        if (os.environ.get("PR_AGENT_RUN_INTEGRATION") != "1"
                or not runtime.is_file() or not (source_root / "pr_agent").is_dir()):
            self.skipTest("offline T2 actual-handler proof requires PR_AGENT_RUN_INTEGRATION=1 and pinned runtime/source")
        script = textwrap.dedent(f"""
            import asyncio, copy, importlib.util, json, os, sys, tempfile
            from pathlib import Path
            root = Path({str(ROOT)!r})
            sys.path.insert(0, str(root / "scripts/ci"))
            spec = importlib.util.spec_from_file_location("t2tests", root / "tests/build/ci_pr_agent_review_test.py")
            t2tests = importlib.util.module_from_spec(spec); spec.loader.exec_module(t2tests)
            import pr_agent_review as t2
            import review_pipeline as pipeline
            import review_scope
            import review_scope_codec as codec
            import pr_review_target
            test = t2tests.RealHandlerIntegrationTests("test_stock_reviewer_receives_every_authenticated_segment_and_captures_native_output")
            test.setUp()
            try:
                test.input_path.write_text(json.dumps(t2tests.signed_input(lambda d: d["identity"].update(run_id="99"))), encoding="utf-8")
                response = (t2tests.FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")
                async def fake_acompletion(**kwargs):
                    return t2tests.FakeCompletion(dict(model="fixture-deepseek-served",
                        choices=[dict(message=dict(content=response), finish_reason="stop")],
                        usage=dict(prompt_tokens=10, completion_tokens=5, total_tokens=15)))
                result, _upstream, _ledger = test.run_with_fake(fake_acompletion)
                document = json.loads(test.input_path.read_text(encoding="utf-8"))
                authenticated = t2.authenticate_input(document)
                import tomllib
                config = t2._safe_config(tomllib.loads(test.config_path.read_text(encoding="utf-8")))
                trusted = {{"schema": review_scope.TRUSTED_CONFIG_SCHEMA, "provider_order": config["provider_order"], "providers": config["providers"], "engine": result["engine"]}}
                identity = dict(repository=authenticated["identity"]["repository"],
                    pr_number=authenticated["identity"]["pull_request"], base_sha=authenticated["identity"]["base_sha"],
                    head_sha=authenticated["identity"]["head_sha"], control_sha=authenticated["identity"]["control_sha"],
                    run_id=99, run_attempt=authenticated["identity"]["run_attempt"], backend="deterministic")
                with tempfile.TemporaryDirectory(prefix="lmdj-t2-capture-") as temporary:
                    directory = Path(temporary)
                    (directory / "context.json").write_text(json.dumps({{"identity": identity,
                        "changed_paths": sorted({{h["path"] for h in t2.expected_coverage(authenticated)}})}}), encoding="utf-8")
                    (directory / "history.json").write_text("[]", encoding="utf-8")
                    (directory / "t2-input.json").write_text(json.dumps(document), encoding="utf-8")
                    (directory / "t2-config-witness.json").write_text(json.dumps(trusted), encoding="utf-8")
                    (directory / "t2-result.json").write_text(json.dumps(result), encoding="utf-8")
                    os.environ["GITHUB_OUTPUT"] = str(directory / "output")
                    pipeline.capture(directory, "deepseek")
                    history = json.loads((directory / "history.json").read_text(encoding="utf-8"))
                    collector = json.loads((directory / "collector.json").read_text(encoding="utf-8"))
                    persisted_config = json.loads((directory / "t2-config-witness.json").read_text(encoding="utf-8"))
                    coverage_digest = history["attempts"][-1]["coverage_sha256"]
                    coverage = json.loads((directory / ("coverage-" + coverage_digest + ".json")).read_text(encoding="utf-8"))
                    pipeline.finalize(directory)
                    publication = json.loads((directory / "result.json").read_text(encoding="utf-8"))
                    review = json.loads((directory / "review.json").read_text(encoding="utf-8"))
                    assert history["schema"] == review_scope.HISTORY_SCHEMA_V2
                    assert collector == pipeline.collector_witness(document)
                    assert persisted_config == trusted and coverage["complete"] is True
                    assert review["test_scope"]["labels"] == ["test:full"]
                    assert publication["status"] == "reviewed" and publication["publication"]["review"] == {{"summary": review["summary"], "findings": review["findings"]}}
                marker = codec.encode_history(history)
                assert codec.decode_history(marker) == history
                target = {{"number": identity["pr_number"], "state": "open", "draft": False, "merged": False,
                    "head": {{"sha": identity["head_sha"], "repo": {{"full_name": identity["repository"]}}}},
                    "base": {{"ref": "main"}}}}
                writes = []
                pr_review_target.publish_review(identity["repository"], identity["pr_number"], identity["head_sha"], "99", "1", "deepseek",
                    publication["publication"]["review"], api=lambda path: target,
                    coverage=coverage, history_digest=review_scope.history_digest(history),
                    history_marker=marker, write=lambda path, payload: writes.append(payload))
                assert result["status"] == "reviewed" and publication["status"] == "reviewed" and len(writes) == 1
                print("actual-t2-v2-publisher-proof")
            finally:
                test.doCleanups()
        """)
        completed = subprocess.run([str(runtime), "-c", script], cwd=ROOT, text=True,
                                   capture_output=True, timeout=180)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("actual-t2-v2-publisher-proof", completed.stdout)

    def test_observed_bare_kimi_labels_still_trigger_fallback(self):
        self.capture("glm", BACKEND_OUTCOME="failure")
        malformed = dict(self.model, test_scope={"labels": ["creator", "docs_static", "portal"],
                                                "reason": "Observed malformed labels from PR #855."})
        self.capture("kimi", REVIEW_JSON=json.dumps(malformed))
        history = pipeline.read(self.directory / "history.json")
        self.assertEqual(history[-1]["error_class"], "invalid_output")
        self.assertEqual(review_scope.next_backend(test_scope.load_policy(ROOT), history), "grok")
        self.assertFalse((self.directory / "review.json").exists())

    def test_legacy_collect_still_emits_only_the_trusted_schema_output(self):
        target = {"review": "true", "head_sha": "a" * 40, "base_sha": "b" * 40,
                  "body": "untrusted $(echo forged) body\nreview_schema=forged"}
        expected = {
            ("rev-parse", "HEAD"): b"c" * 40,
            ("merge-base", "b" * 40, "a" * 40): b"b" * 40,
            ("diff", "--no-ext-diff", "--no-textconv", "b" * 40, "a" * 40, "--"): b"untrusted diff",
            ("diff", "--no-ext-diff", "--no-textconv", "--name-status", "-z", "--find-renames",
             "b" * 40, "a" * 40, "--"): b"M\0docs/notes/a.md\0",
        }
        env = {**self.env, "GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "7", "HEAD_SHA": "a" * 40,
               "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(pipeline.pr_review_target, "resolve_target", return_value=target), \
                mock.patch.object(pipeline, "fetch") as fetch, \
                mock.patch.object(pipeline, "git", side_effect=lambda *args: expected[args]):
            pipeline.collect(self.directory)
        fetch.assert_called_once_with("b" * 40, "a" * 40)
        output = (self.directory / "output").read_text().splitlines()
        self.assertEqual(len(output), 1, "why: schema output has extra records; remedy: serialize only trusted policy")
        name, schema = output[0].split("=", 1)
        self.assertEqual(name, "review_schema")
        self.assertEqual(json.loads(schema), pipeline.response_schema(test_scope.load_policy(ROOT)))
        # The production workflow feeds the engine from collect-t2, never from
        # a model-side JSON-schema argument.
        source = (ROOT / ".github/workflows/pr-review.yml").read_text()
        self.assertNotIn("claude_args", source)
        self.assertIn('review_pipeline.py collect-t2 --directory "$REVIEW_DIR"', source)

    def test_git_failure_does_not_echo_credentials(self):
        with mock.patch.object(pipeline.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"secret")), \
                self.assertRaisesRegex(review_scope.ReviewScopeError, "Git input") as raised:
            pipeline.git("fetch", "main")
        self.assertNotIn("secret", str(raised.exception))

    def test_pagination_reads_second_page(self):
        def api(path):
            return {"jobs": [{"id": i} for i in range(100)]} if path.endswith("&page=1") else {"jobs": [{"id": 100}]}
        with mock.patch.object(pipeline, "api", side_effect=api):
            self.assertEqual(len(pipeline.pages("/jobs", "jobs")), 101)

    def test_pagination_failure_is_not_empty(self):
        with mock.patch.object(pipeline, "api", return_value={"message": "forbidden"}), \
                self.assertRaisesRegex(review_scope.ReviewScopeError, "incomplete inventory"):
            pipeline.pages("/jobs", "jobs")

    def test_workflow_uses_only_one_engine_attempt_and_exact_artifact(self):
        source = (ROOT / ".github/workflows/pr-review.yml").read_text()
        self.assertEqual(source.count("name: Review fallback"), 1)
        self.assertEqual(source.count("review_pipeline.py capture --backend"), 1,
                         "why: the engine owns provider fallback; remedy: keep one capture step")
        self.assertIn("${{ env.REVIEW_DIR }}/review.json", source)
        self.assertIn("${{ env.REVIEW_DIR }}/failure.json", source)
        self.assertIn("${{ env.REVIEW_DIR }}/t2-config-witness.json", source)
        self.assertIn("pr-test-scope-${{ needs.target.outputs.head_sha }}-${{ github.run_id }}-${{ github.run_attempt }}", source)
        self.assertNotIn("issues: write", source)
        self.assertNotIn("actions: write", source)

    def publish_with_doubles(self, *, stale=False, unavailable=False, prior_reviews=None):
        calls = []
        def auth(identity, store=None, reuse=False):
            calls.append("authenticate")
            if stale:
                raise review_scope.ReviewScopeError("why: stale head; remedy: retry")
            return identity
        environment = {"GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "7", "HEAD_SHA": "a" * 40,
                       "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_TOKEN": "secret"}
        with mock.patch.dict(os.environ, environment), \
                mock.patch.object(pipeline, "git", return_value=("c" * 40 + "\n").encode()), \
                mock.patch.object(pipeline, "fetch"), mock.patch.object(pipeline, "authenticate", side_effect=auth), \
                (mock.patch.object(pipeline, "previous_records", return_value=([], unavailable))
                 if prior_reviews is None else contextlib.nullcontext()), \
                mock.patch.object(pipeline, "api", return_value={"id": 5}), \
                mock.patch.object(pipeline, "pages", return_value=prior_reviews or []), \
                mock.patch.object(pipeline.change_scope, "read_git_inventory", return_value=[pipeline.change_scope.ChangedFile("M", ("docs/notes/a.md",))]), \
                mock.patch.object(pipeline, "publish_model", side_effect=lambda identity, record, model, **kwargs: calls.append(("review", {"summary": model["summary"] + model["test_scope"]["reason"] + pipeline.codec.encode(record)}))), \
                mock.patch.object(pipeline.pr_review_target, "github_request", side_effect=lambda *a: calls.append(("labels", a))):
            pipeline.publish(self.directory)
        return calls

    def test_publisher_rechecks_and_persists_scope_before_labels(self):
        self.capture("glm")
        pipeline.finalize(self.directory)
        calls = self.publish_with_doubles()
        self.assertEqual([c if isinstance(c, str) else c[0] for c in calls],
                         ["authenticate", "review", "authenticate", "labels", "authenticate"])
        self.assertEqual(pipeline.read(self.directory / "scope.json")["effective"]["kind"], "none")
        body = calls[1][1]["summary"]
        self.assertIn("lmdj-test-scope-record-v2", body)
        self.assertIn(self.model["test_scope"]["reason"], body)

    def test_stale_head_stops_before_scope_or_writes(self):
        self.capture("glm")
        pipeline.finalize(self.directory)
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "stale head"):
            self.publish_with_doubles(stale=True)
        self.assertFalse((self.directory / "scope.json").exists())

    def test_all_failure_is_visible_and_retains_scope_artifact(self):
        for backend in review_scope.BACKENDS:
            self.capture(backend, BACKEND_OUTCOME="failure")
        pipeline.finalize(self.directory)
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "all review backends failed"):
            self.publish_with_doubles()
        self.assertTrue((self.directory / "scope.json").exists())

    def test_forged_result_fails_before_publication(self):
        self.capture("glm")
        pipeline.finalize(self.directory)
        result = pipeline.read(self.directory / "result.json")
        result["publication"]["labels"] = ["test:full"]
        pipeline.save(self.directory / "result.json", result)
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "inconsistent"):
            self.publish_with_doubles()

    def test_many_paths_do_not_spend_model_summary_budget(self):
        policy = test_scope.load_policy(ROOT)
        paths = ["apps/creator-web/" + str(i) + "x" * 80 + ".tsx" for i in range(100)]
        identity = {**self.identity, "backend": "glm"}
        record = test_scope.build_record(policy, changed_paths=paths, ai_labels=["test:none"], **identity)
        writes = []
        target = {"review": "true", "base_ref": "main", "head_sha": identity["head_sha"]}
        with mock.patch.object(pipeline.pr_review_target, "resolve_target", return_value=target):
            pipeline.publish_model(identity, record, self.model, write=lambda path, data: writes.append(data))
        self.assertEqual(len(writes), 1)
        self.assertEqual(pipeline.codec.decode(writes[0]["body"]), record)
        self.assertLess(len(writes[0]["body"].encode()), pipeline.codec.MAX_COMMENT_BYTES)

    def test_metadata_overflow_still_publishes_valid_review_with_full_marker(self):
        identity = {**self.identity, "backend": "glm"}
        record = test_scope.build_record(test_scope.load_policy(ROOT), changed_paths=[], **identity)
        writes = []
        with mock.patch.object(pipeline.pr_review_target, "resolve_target", return_value={"review": "true", "base_ref": "main", "head_sha": identity["head_sha"]}), \
                mock.patch.object(pipeline.codec, "MAX_MARKER_BYTES", 1):
            pipeline.publish_model(identity, record, self.model, write=lambda path, data: writes.append(data))
        self.assertEqual(len(writes), 1)
        self.assertIn(self.model["summary"], writes[0]["body"])
        self.assertEqual(pipeline.codec.unavailable_identities(writes[0]["body"]), [identity])

    def test_api_store_reuses_identical_paths_and_uncached_calls_refetch(self):
        calls = []

        def fake_api(path):
            calls.append(path)
            return {"id": 7, "path": path}

        store = {}
        with mock.patch.object(pipeline.pr_review_target, "_api", side_effect=fake_api):
            first = pipeline.api("/repos/endaye/lmdj", store)
            second = pipeline.api("/repos/endaye/lmdj", store)
            third = pipeline.api("/repos/endaye/lmdj")
        self.assertEqual(first, second)
        self.assertEqual(calls, ["/repos/endaye/lmdj", "/repos/endaye/lmdj"])
        self.assertEqual(third["path"], "/repos/endaye/lmdj")

    def test_previous_records_authenticate_duplicate_priors_once(self):
        identity = {**self.identity, "backend": "glm"}
        prior = test_scope.build_record(test_scope.load_policy(ROOT),
            changed_paths=["docs/notes/a.md"], ai_labels=["test:full"], **identity)
        posted = {"commit_id": identity["head_sha"], "user": {"id": 5},
                  "body": pipeline.codec.encode(prior)}
        auths = []

        def fake_auth(ident, store=None, reuse=False):
            token = ("identity", ident["repository"], ident["run_id"], ident["run_attempt"])
            if reuse and store is not None and token in store:
                return store[token]
            auths.append(ident["run_id"])
            if reuse and store is not None:
                store[token] = ident
            return ident

        with mock.patch.object(pipeline, "api", return_value={"id": 5}), \
                mock.patch.object(pipeline, "pages", return_value=[posted, posted]), \
                mock.patch.object(pipeline, "authenticate", side_effect=fake_auth):
            records, unavailable = pipeline.previous_records(identity, test_scope.load_policy(ROOT), {})
        self.assertEqual(auths, [identity["run_id"]])
        self.assertEqual(len(records), 2)
        self.assertFalse(unavailable)

    def test_same_head_unavailable_receipt_is_not_silently_ignored(self):
        identity = {**self.identity, "backend": "glm"}
        posted = {"commit_id": identity["head_sha"], "user": {"id": 5}, "body": pipeline.codec.unavailable(identity)}
        with mock.patch.object(pipeline, "api", return_value={"id": 5}), \
                mock.patch.object(pipeline, "pages", return_value=[posted]), mock.patch.object(pipeline, "authenticate"):
            records, unavailable = pipeline.previous_records(identity, test_scope.load_policy(ROOT))
        self.assertEqual(records, [])
        self.assertTrue(unavailable)

    def test_same_head_review_after_control_update_publishes_with_full_scope(self):
        self.capture("glm")
        pipeline.finalize(self.directory)
        prior_identity = {**self.identity, "backend": "glm", "control_sha": "d" * 40, "run_id": 98}
        prior = test_scope.build_record(test_scope.load_policy(ROOT),
            changed_paths=["docs/notes/a.md"], ai_labels=["test:full"], **prior_identity)
        posted = {"commit_id": self.identity["head_sha"], "user": {"id": 5}, "body": pipeline.codec.encode(prior)}
        calls = self.publish_with_doubles(prior_reviews=[posted])
        record = pipeline.read(self.directory / "scope.json")
        self.assertEqual(record["control_sha"], self.identity["control_sha"])
        self.assertFalse(record["complete"])
        self.assertEqual(record["effective"]["kind"], "full")
        self.assertEqual([c[0] for c in calls if isinstance(c, tuple)], ["review", "labels"])
        self.assertEqual(next(c[1][-1] for c in calls if isinstance(c, tuple) and c[0] == "labels"),
                         {"labels": ["test:full"]})

    def test_later_same_head_review_keeps_unavailable_scope_full(self):
        self.capture("glm")
        pipeline.finalize(self.directory)
        calls = self.publish_with_doubles(unavailable=True)
        self.assertEqual(pipeline.read(self.directory / "scope.json")["effective"]["kind"], "full")
        self.assertEqual(calls[3][1][-1], {"labels": ["test:full"]})

    def test_backend_conditions_require_successful_collection(self):
        source = (ROOT / ".github/workflows/pr-review.yml").read_text()
        for step in ("deepseek", "capture-deepseek"):
            block = source.split("        id: " + step + "\n", 1)[1].split("      - ", 1)[0]
            self.assertIn("steps.input.outcome == 'success'", block,
                          "why: the engine could run without the complete authenticated input; remedy: gate it on collection success")
        engine = source.split("        id: deepseek\n", 1)[1].split("      - ", 1)[0]
        self.assertIn("slot.lock bash -euo pipefail <<'REVIEW'", engine)
        self.assertLess(engine.index("slot.lock"), engine.index("run-engine.sh --witness"))
        self.assertLess(engine.index("run-engine.sh --witness"), engine.index("run-engine.sh --input"),
                        "why: witness and model must bind one protected release; remedy: execute both under the same slot lock")

    def make_real_t2_repo(self):
        temporary = tempfile.TemporaryDirectory(prefix="lmdj-pipeline-t2-")
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name) / "repo"
        repository.mkdir()

        def git(*args):
            result = subprocess.run(["git", *args], cwd=repository, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            return result.stdout.decode().strip()

        git("init", "-q")
        (repository / "source.txt").write_text("old\n", encoding="utf-8")
        git("add", ".")
        git("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        (repository / "source.txt").write_text("new\n", encoding="utf-8")
        git("add", ".")
        git("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "head")
        head = git("rev-parse", "HEAD")
        return repository, base, head

    def make_real_bounded_failure_repo(self):
        """Build the over-budget refusal with real Git byte-path objects."""
        temporary = tempfile.TemporaryDirectory(prefix="lmdj-pipeline-bounded-failure-")
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name) / "repo"
        repository.mkdir()

        def git(*args, data=None):
            result = subprocess.run(["git", *args], cwd=repository, input=data, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            return result.stdout

        git("init", "-q")
        blob = git("hash-object", "-w", "--stdin", data=b"new\n").strip()

        def commit(names, parent=None):
            tree_input = b"".join(
                b"100644 blob " + blob + b"\t" + name + b"\0" for name in sorted(names)
            )
            tree = git("mktree", "-z", data=tree_input).decode().strip()
            command = ["-c", "user.name=test", "-c", "user.email=test@example.invalid",
                       "commit-tree", tree]
            if parent is not None:
                command.extend(["-p", parent])
            head = git(*command, data=b"bounded failure\n").decode().strip()
            git("update-ref", "HEAD", head.encode())
            return head

        base = commit([b"source.txt"])
        invalid = [f"a{index:04d}-".encode() + b"x" * 160 + b"\xff.txt" for index in range(256)]
        head = commit([b"source.txt", b"z-later.txt", *invalid], parent=base)
        return repository, base, head

    def make_real_rename_repo(self, *, pure):
        temporary = tempfile.TemporaryDirectory(prefix="lmdj-pipeline-rename-")
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name) / "repo"
        (repository / "contracts").mkdir(parents=True)
        (repository / "apps/creator-web").mkdir(parents=True)

        def git(*args):
            result = subprocess.run(["git", *args], cwd=repository, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            return result.stdout.decode().strip()

        git("init", "-q")
        (repository / "contracts/old.txt").write_text(
            "one\ntwo\nthree\nkeep\nend\n", encoding="utf-8")
        git("add", ".")
        git("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        git("mv", "contracts/old.txt", "apps/creator-web/new.txt")
        if not pure:
            (repository / "apps/creator-web/new.txt").write_text(
                "one\ntwo\nthree\nchanged\nend\n", encoding="utf-8")
            git("add", ".")
        git("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "head")
        head = git("rev-parse", "HEAD")
        return repository, base, head

    def collect_real_t2(self, repository, base, head, output, *, pull_number=1151):
        witness_output = output.parent / (output.name + "-github-output")
        target = {"review": "true", "head_sha": head, "base_sha": base, "body": "body"}
        environment = {
            "GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": str(pull_number), "HEAD_SHA": head,
            "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_OUTPUT": str(witness_output),
        }
        with mock.patch.dict(os.environ, environment, clear=False), \
                mock.patch.object(pipeline, "ROOT", repository), \
                mock.patch.object(pipeline, "fetch"), \
                mock.patch.object(pipeline, "response_schema", return_value={}), \
                mock.patch.object(pipeline.test_scope, "load_policy", return_value={}), \
                mock.patch.object(pipeline.pr_review_target, "resolve_target", side_effect=[target, target]), \
                mock.patch.object(sys, "argv", ["review_pipeline.py", "collect-t2", "--directory", str(output)]):
            self.assertEqual(pipeline.main(), 0)
        witness_line = next(line for line in witness_output.read_text().splitlines()
                            if line.startswith("t2_publication_witness="))
        witness = json.loads(witness_line.split("=", 1)[1])
        document = pipeline.read(output / "t2-input.json")
        return document, witness

    def complete_real_t3(self, repository, output, document, witness):
        authenticated = t2.authenticate_input(document)
        collector = pipeline.trusted_collector_t2(output, witness)
        engine = {
            "name": "pr-agent", "source_commit": "1" * 40, "version": "0.45.0",
            "bundle": {
                "archive_sha256": "2" * 64, "archive_byte_length": 7,
                "manifest_sha256": "3" * 64, "adapter_sha256": "4" * 64,
                "default_config_sha256": "5" * 64, "requirements_lock_sha256": "6" * 64,
                "stock_tokenizer_asset_sha256": "7" * 64,
            },
            "runtime_config": {"sha256": "8" * 64, "byte_length": 7},
        }
        model = {"requested": "fixture-model", "actual": "fixture-served",
                 "response_version": "fixture-v1", "pricing_revision": "fixture-v1"}
        coverage = t2._validate_coverage_receipt(t2._make_coverage(
            authenticated, provider="deepseek", model=model,
            prompt=t2.render_prompt_input(authenticated), usage=None, engine=engine))
        review = {"summary": "Reviewed the complete rename.", "findings": []}
        attempt = {
            "status": "reviewed", "error_class": None, "error": None,
            "provider": "deepseek", "model": coverage["model"], "engine": engine,
            "review": review, "native_review": {}, "coverage": coverage,
            "usage": coverage["usage"], "duration_ms": 1,
        }
        result = {
            "schema": "lmdj.pr-agent-result.v1", "status": "reviewed", "error_class": None,
            "identity": authenticated["identity"], "input_sha256": authenticated["input_sha256"],
            "engine": engine, "selected_attempt": 0, "attempts": [attempt],
            "skipped_providers": [], "elapsed_ms": 1,
        }
        trusted = {
            "schema": review_scope.TRUSTED_CONFIG_SCHEMA, "provider_order": ["deepseek"],
            "providers": {
                "deepseek": {"enabled": True, "model": model["requested"]},
                "glm": {"enabled": False}, "xai": {"enabled": False}, "kimi": {"enabled": False},
            },
            "engine": engine,
        }
        pipeline.save(output / "t2-result.json", result)
        pipeline.save(output / "t2-config-witness.json", trusted)
        environment = {
            "GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": str(authenticated["identity"]["pull_request"]),
            "HEAD_SHA": authenticated["identity"]["head_sha"], "GITHUB_RUN_ID": "99",
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_OUTPUT": str(output / "t3-output"),
        }
        with mock.patch.dict(os.environ, environment, clear=False), \
                mock.patch.object(pipeline, "ROOT", repository), \
                mock.patch.object(pipeline.test_scope, "load_policy", return_value=test_scope.load_policy(ROOT)), \
                mock.patch.object(sys, "argv", ["review_pipeline.py", "capture", "--backend", "deepseek",
                                                  "--directory", str(output)]):
            self.assertEqual(pipeline.main(), 0)
        with mock.patch.dict(os.environ, environment, clear=False), \
                mock.patch.object(pipeline, "ROOT", repository), \
                mock.patch.object(pipeline.test_scope, "load_policy", return_value=test_scope.load_policy(ROOT)), \
                mock.patch.object(sys, "argv", ["review_pipeline.py", "finalize", "--directory", str(output)]):
            self.assertEqual(pipeline.main(), 0)
        self.assertEqual(pipeline.read(output / "result.json")["status"], "reviewed")
        return collector, coverage, result

    def test_real_pure_and_edited_rename_journeys_bind_old_new_through_t3_and_publisher(self):
        for pure in (True, False):
            with self.subTest(rename="pure" if pure else "edited"):
                repository, base, head = self.make_real_rename_repo(pure=pure)
                output = self.directory / ("pure-rename" if pure else "edited-rename")
                document, witness = self.collect_real_t2(repository, base, head, output,
                                                         pull_number=1151 if pure else 1152)
                context = pipeline.read(output / "context.json")
                self.assertEqual(context["changed_paths"],
                                 ["apps/creator-web/new.txt", "contracts/old.txt"])
                collector, coverage, _result = self.complete_real_t3(repository, output, document, witness)
                self.assertEqual(review_scope.changed_path_inventory(collector["expected_hunks"]),
                                 context["changed_paths"])
                if pure:
                    self.assertEqual(collector["right_inventory"], [])
                else:
                    self.assertEqual(collector["right_inventory"],
                                     [{"path": "apps/creator-web/new.txt", "line": 4}])
                self.assertEqual(review_scope.changed_path_inventory(coverage["expected_hunks"]),
                                 context["changed_paths"])
                environment = {
                    "GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": str(1151 if pure else 1152),
                    "HEAD_SHA": head, "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_TOKEN": "secret",
                }
                original_inventory = pipeline.change_scope.read_git_inventory
                observed_inventories = []
                def read_inventory(*args, **kwargs):
                    value = original_inventory(*args, **kwargs)
                    observed_inventories.append(value)
                    return value
                with mock.patch.dict(os.environ, environment, clear=False), \
                        mock.patch.object(pipeline, "ROOT", repository), \
                        mock.patch.object(pipeline.test_scope, "load_policy", return_value=test_scope.load_policy(ROOT)), \
                        mock.patch.object(pipeline, "authenticate", return_value=context["identity"]), \
                        mock.patch.object(pipeline, "fetch"), \
                        mock.patch.object(pipeline, "previous_records", return_value=([], False)), \
                        mock.patch.object(pipeline, "publish_model"), \
                        mock.patch.object(pipeline.pr_review_target, "github_request"), \
                        mock.patch.object(pipeline.change_scope, "read_git_inventory",
                                          side_effect=read_inventory):
                    pipeline.publish(output)
                self.assertEqual(len(observed_inventories), 1)
                actual = observed_inventories[0]
                self.assertEqual([(item.status[0], item.paths) for item in actual],
                                 [("R", ("contracts/old.txt", "apps/creator-web/new.txt"))])
                print(json.dumps({
                    "rename": "pure" if pure else "edited",
                    "context_paths": context["changed_paths"],
                    "collector_right_inventory": collector["right_inventory"],
                    "coverage_paths": review_scope.changed_path_inventory(coverage["expected_hunks"]),
                    "publisher_git_inventory": [
                        {"status": item.status, "paths": list(item.paths)} for item in actual
                    ],
                }, sort_keys=True))

    def test_synchronize_collection_publishes_authenticated_batch_in_same_input(self):
        from ci_review_recheck_test import BatchPlatform
        import review_recheck
        api = BatchPlatform()
        self.addCleanup(api.history.source.tearDown)
        api.document["identity"]["run_id"] = "99"
        review_recheck.reseal(api.document)
        output = self.directory / "push-input"
        head = api.document["identity"]["head_sha"]
        base = api.document["identity"]["base_sha"]
        target = {"review": "true", "head_sha": head, "base_sha": base, "body": "fix"}
        environment = {"GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "7", "HEAD_SHA": head,
            "GITHUB_RUN_ID": api.document["identity"]["run_id"], "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "pull_request", "PR_EVENT_ACTION": "synchronize", "AUTO_RECHECK": "true",
            "RECHECK_COMMENT_ID": "", "GITHUB_OUTPUT": "", "GITHUB_STEP_SUMMARY": str(self.directory / "summary")}
        def git(*args):
            if args[0] == "rev-parse": return (api.document["identity"]["control_sha"] + "\n").encode()
            if args[0] == "merge-base" and args[1] == base: return (base + "\n").encode()
            return api.git(*args)
        with mock.patch.dict(os.environ, environment), mock.patch.object(pipeline, "git", side_effect=git), \
                mock.patch.object(pipeline, "fetch"), \
                mock.patch.object(pipeline.input_producer, "build_input", return_value=copy.deepcopy(api.document)), \
                mock.patch.object(review_recheck, "client", return_value=api), \
                mock.patch.object(pipeline.pr_review_target, "resolve_target", return_value=target):
            # Source transport is supplied; actual auth and atomic publication run.
            witness = pipeline.collect_t2(output)
        document = pipeline.read(output / "t2-input.json")
        self.assertEqual([r["comment_id"] for r in t2.authenticate_input(document)["repair_requests"]], [70, 71])
        collector = pipeline.trusted_collector_t2(output, witness)
        self.assertEqual(collector["input_sha256"], document["input_sha256"])
        self.assertIn("collected", (self.directory / "summary").read_text())

    def refused_recheck_publication(self, *, failure=None, name="refused-recheck"):
        """Publish a repair-mode review whose recheck publication is refused.

        Returns (refusal receipt, captured stdout, recheck platform). By default
        the strict verdict contract refuses the corrupted quotes; `failure`
        raises a specific authored refusal instead.
        """
        from ci_review_recheck_test import BatchPlatform
        import review_recheck
        api = BatchPlatform()
        self.addCleanup(api.history.source.tearDown)
        # Production identities carry the numeric GitHub run id.
        api.document["identity"]["run_id"] = "99"
        review_recheck.reseal(api.document)
        api.collect_batch()
        document = api.document
        authenticated = t2.authenticate_input(document)
        collector = pipeline.collector_witness(document)
        identity = {"repository": authenticated["identity"]["repository"],
                    "pr_number": authenticated["identity"]["pull_request"],
                    "base_sha": authenticated["identity"]["base_sha"],
                    "head_sha": authenticated["identity"]["head_sha"],
                    "control_sha": authenticated["identity"]["control_sha"],
                    "backend": "deterministic", "run_id": 99,
                    "run_attempt": authenticated["identity"]["run_attempt"]}
        engine = {"name": "pr-agent", "source_commit": "1" * 40, "version": "0.45.0",
                  "bundle": {"archive_sha256": "2" * 64, "archive_byte_length": 7,
                             "manifest_sha256": "3" * 64, "adapter_sha256": "4" * 64,
                             "default_config_sha256": "5" * 64, "requirements_lock_sha256": "6" * 64,
                             "stock_tokenizer_asset_sha256": "7" * 64},
                  "runtime_config": {"sha256": "8" * 64, "byte_length": 7}}
        trusted = {"schema": review_scope.TRUSTED_CONFIG_SCHEMA, "provider_order": ["deepseek"],
                   "providers": {"deepseek": {"enabled": True, "model": "fixture-model"},
                                 "glm": {"enabled": False}, "xai": {"enabled": False}, "kimi": {"enabled": False}},
                   "engine": engine}
        coverage = t2._validate_coverage_receipt(t2._make_coverage(
            authenticated, provider="deepseek",
            model={"requested": "fixture-model", "actual": "fixture-served",
                   "response_version": "fixture-v1", "pricing_revision": "fixture-v1"},
            prompt=t2.render_prompt_input(authenticated), usage=None, engine=engine))
        self.assertTrue(coverage["complete"])
        native = api.native()
        for verdict in native["review"]["repair_rechecks"]:
            # The exact observed defect: the quote does not cover the anchor.
            verdict["original_quote"] = "def value():"
        review = {"summary": native["review"]["general_comments"], "findings": []}
        attempt = {"status": "reviewed", "error_class": None, "error": None, "provider": "deepseek",
                   "model": coverage["model"], "engine": engine, "review": review,
                   "native_review": native, "coverage": coverage, "usage": coverage["usage"],
                   "duration_ms": 1}
        result = {"schema": "lmdj.pr-agent-result.v1", "status": "reviewed", "error_class": None,
                  "identity": authenticated["identity"], "input_sha256": authenticated["input_sha256"],
                  "engine": engine, "selected_attempt": 0, "attempts": [attempt],
                  "skipped_providers": [], "elapsed_ms": 1}
        output = self.directory / name
        pipeline.save(output / "context.json", {"identity": identity, "changed_paths":
                      sorted({hunk["path"] for hunk in collector["expected_hunks"]})})
        pipeline.save(output / "history.json", [])
        pipeline.save(output / "t2-input.json", document)
        pipeline.save(output / "t2-result.json", result)
        pipeline.save(output / "t2-config-witness.json", trusted)
        environment = {"GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "7", "HEAD_SHA": identity["head_sha"],
                       "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_TOKEN": "fixture-secret",
                       "GITHUB_OUTPUT": str(output / "capture-output"), "GITHUB_EVENT_NAME": "pull_request",
                       "PR_EVENT_ACTION": "synchronize", "AUTO_RECHECK": "true", "RECHECK_COMMENT_ID": ""}
        refusal_patch = (mock.patch.object(review_recheck, "publish_batch", side_effect=failure)
                         if failure is not None
                         else mock.patch.object(review_recheck, "client", return_value=api))
        with mock.patch.dict(os.environ, environment, clear=False), \
                mock.patch.object(pipeline, "git", return_value=(identity["control_sha"] + "\n").encode()), \
                mock.patch.object(pipeline, "fetch"), \
                mock.patch.object(pipeline, "authenticate", side_effect=lambda *args, **kwargs: identity), \
                mock.patch.object(pipeline, "previous_records", return_value=([], False)), \
                mock.patch.object(pipeline, "publish_model"), \
                mock.patch.object(pipeline.pr_review_target, "github_request"), \
                mock.patch.object(pipeline.change_scope, "read_git_inventory", return_value=[
                    pipeline.change_scope.ChangedFile("M", ("src/example.py",)),
                    pipeline.change_scope.ChangedFile("D", ("obsolete.txt",))]), \
                mock.patch.object(review_recheck, "client", return_value=api), \
                refusal_patch:
            pipeline.capture(output, "deepseek")
            pipeline.finalize(output)
            with contextlib.redirect_stdout(io.StringIO()) as printed, \
                    mock.patch.object(sys, "argv", ["review_pipeline.py", "publish",
                                                    "--directory", str(output)]):
                self.assertEqual(pipeline.main(), 0)
        # The validated review is published; only the rechecks were refused.
        self.assertEqual(pipeline.read(output / "review.json")["summary"], review["summary"])
        return pipeline.read(output / "repair-recheck.json"), printed.getvalue(), api

    def common_refusal_is_bounded_and_recorded(self, refusal, printed, api):
        self.assertEqual(refusal["schema"], pipeline.REPAIR_REFUSAL_SCHEMA)
        self.assertEqual(refusal["status"], "refused")
        # The receipt keeps the remedy the refusal named, bounded like the why.
        self.assertTrue(refusal["remedy"].strip())
        self.assertNotIn("\n", refusal["remedy"])
        self.assertLessEqual(len(refusal["remedy"].encode("utf-8")), pipeline.MAX_REPAIR_REFUSAL_REASON_BYTES)
        self.assertNotIn("fixture-secret", json.dumps(refusal))
        lines = [line for line in printed.splitlines() if line.startswith("Repair recheck refused")]
        self.assertEqual(len(lines), 1)
        self.assertIn("why: ", lines[0])
        self.assertIn("remedy: ", lines[0])
        # No verdict may reach a thread: nothing was written and all stay open.
        self.assertEqual(api.writes, [])
        self.assertEqual(api.states, {"T70": False, "T71": False})

    def test_refused_repair_verdict_publishes_the_review_and_records_a_refusal(self):
        """An unusable recheck section must not fail the publish step.

        #1344: one refused repair verdict made `publish` non-zero, so a head
        whose review was completely validated was published without its review.
        """
        refusal, printed, api = self.refused_recheck_publication()
        self.common_refusal_is_bounded_and_recorded(refusal, printed, api)
        self.assertIn("why: original source quote does not cover the finding anchor", refusal["why"])
        self.assertEqual(refusal["remedy"], "return explicit repair evidence or insufficient_evidence")

    def test_refused_original_review_authenticity_publishes_the_review_and_records_a_refusal(self):
        """A refused re-authentication of the recheck source is the same refusal.

        `review_wait.Refused` is the protocol's own authored refusal and is not
        a ReviewScopeError; it must not cost a review that is already published
        and validated either.
        """
        import review_wait
        refusal, printed, api = self.refused_recheck_publication(
            failure=review_wait.Refused("why: the original review could not be re-authenticated; "
                                        "remedy: take over the recheck manually"),
            name="refused-authenticity")
        self.common_refusal_is_bounded_and_recorded(refusal, printed, api)
        self.assertIn("why: the original review could not be re-authenticated", refusal["why"])
        self.assertEqual(refusal["remedy"], "take over the recheck manually")

    def test_repair_refusal_receipt_is_bounded_and_carries_no_external_text(self):
        oversized = pipeline.repair_refusal_receipt(
            review_scope.ReviewScopeError("why: " + "x" * 5000 + "; remedy: reuse the receipt"))
        self.assertEqual(set(oversized), {"schema", "status", "why", "remedy"})
        self.assertEqual(oversized["status"], "refused")
        self.assertEqual(oversized["schema"], pipeline.REPAIR_REFUSAL_SCHEMA)
        self.assertLessEqual(len(oversized["why"].encode("utf-8")), pipeline.MAX_REPAIR_REFUSAL_REASON_BYTES)
        self.assertTrue(oversized["why"].startswith("why: xxx"))
        self.assertNotIn("\n", oversized["why"])
        # The bounded clause may not swallow the remedy the refusal named.
        self.assertEqual(oversized["remedy"], "reuse the receipt")
        # A refusal that names no remedy keeps the bounded literal.
        unnamed = pipeline.repair_refusal_receipt(review_scope.ReviewScopeError("all review backends failed"))
        self.assertEqual(unnamed["remedy"], pipeline.REPAIR_REFUSAL_REMEDY)
        self.assertEqual(unnamed["why"], "all review backends failed")
        # A reporter message can embed an external error or response body.
        projected = pipeline.repair_refusal_receipt(
            pipeline.reporting.ReportingError("why: response body: private provider text; remedy: inspect"))
        self.assertNotIn("private provider text", projected["why"])
        self.assertEqual(projected["remedy"], pipeline.REPAIR_REFUSAL_REMEDY)

    def test_repair_trigger_binding_refuses_unsolicited_or_wrong_mode_artifacts(self):
        for event, action, automatic, requested, document in (
            ("workflow_dispatch", "", "true", "", {"repair_requests": []}),
            ("pull_request", "opened", "true", "", {"repair_requests": []}),
            ("pull_request", "synchronize", "true", "70", {"repair_requests": []}),
            ("pull_request", "synchronize", "false", "", {"repair_requests": []}),
            ("pull_request", "synchronize", "true", "", {}),
        ):
            with self.subTest(event=event, action=action, automatic=automatic, requested=requested), \
                    mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": event, "PR_EVENT_ACTION": action,
                        "AUTO_RECHECK": automatic, "RECHECK_COMMENT_ID": requested}):
                with self.assertRaises(review_scope.ReviewScopeError):
                    pipeline.repair_mode(document)

    def test_collect_t2_cli_dispatch_publishes_input_and_real_t3_witness(self):
        repository, base, head = self.make_real_t2_repo()
        output = self.directory / "t2-output"
        witness_output = self.directory / "github-output"
        target = {"review": "true", "head_sha": head, "base_sha": base, "body": "body"}
        environment = {"GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "1151", "HEAD_SHA": head,
                       "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_OUTPUT": str(witness_output)}
        with mock.patch.dict(os.environ, environment, clear=False), \
                mock.patch.object(pipeline, "ROOT", repository), \
                mock.patch.object(pipeline, "fetch"), \
                mock.patch.object(pipeline, "response_schema", return_value={}), \
                mock.patch.object(pipeline.test_scope, "load_policy", return_value={}), \
                mock.patch.object(pipeline.pr_review_target, "resolve_target", side_effect=[target, target]), \
                mock.patch.object(sys, "argv", ["review_pipeline.py", "collect-t2", "--directory", str(output)]):
            self.assertEqual(pipeline.main(), 0)
        self.assertEqual(sorted(item.name for item in output.iterdir()),
                         ["collection-receipt.json", "context.json", "history.json", "pr-body.md", "pr.diff", "t2-input.json"])
        document = pipeline.read(output / "t2-input.json")
        authenticated = t2.authenticate_input(document)
        context = pipeline.read(output / "context.json")
        witness_line = next(line for line in witness_output.read_text().splitlines()
                            if line.startswith("t2_publication_witness="))
        witness = json.loads(witness_line.split("=", 1)[1])
        self.assertEqual(witness["receipt_sha256"], hashlib.sha256(
            (output / "collection-receipt.json").read_bytes()).hexdigest())
        collector = pipeline.trusted_collector_t2(output, witness)
        self.assertEqual(collector, pipeline.collector_witness(document))
        self.assertEqual(collector["input_sha256"], document["input_sha256"])
        self.assertEqual(collector["identity"]["head_sha"], context["identity"]["head_sha"])
        self.assertEqual(authenticated["identity"]["pull_request"], 1151)
        receipt = pipeline.read(output / "collection-receipt.json")
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(receipt["input_sha256"], document["input_sha256"])
        self.assertEqual(receipt["context_sha256"], hashlib.sha256(
            pipeline.input_producer.json_bytes(context)).hexdigest())
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "successful-producer witness"):
            pipeline.trusted_collector_t2(output)
        (output / "t2-input.json").write_bytes(b"leftover bytes")
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "successful-producer witness"):
            pipeline.trusted_collector_t2(output, witness)

        bounded_repository, bounded_base, bounded_head = self.make_real_bounded_failure_repo()
        bounded_output = self.directory / "bounded-failure-output"
        bounded_witness_output = self.directory / "bounded-failure-github-output"
        bounded_identity = {
            "repository": "endaye/lmdj", "pull_request": 1151, "base_sha": bounded_base,
            "head_sha": bounded_head, "control_sha": bounded_head, "run_id": "99", "run_attempt": 1,
        }
        with self.assertRaises(pipeline.input_producer.InputCollectionError) as raised:
            pipeline.input_producer.build_input(bounded_repository, bounded_identity)
        original_failure = raised.exception.result
        original_payload = pipeline.input_producer.json_bytes(original_failure)
        self.assertGreater(len(original_payload), pipeline.input_producer.MAX_FAILURE_BYTES)
        bounded_target = {"review": "true", "head_sha": bounded_head, "base_sha": bounded_base, "body": "body"}
        bounded_environment = {
            "GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "1151", "HEAD_SHA": bounded_head,
            "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_OUTPUT": str(bounded_witness_output),
        }
        errors = io.StringIO()
        with mock.patch.dict(os.environ, bounded_environment, clear=False), \
                mock.patch.object(pipeline, "ROOT", bounded_repository), \
                mock.patch.object(pipeline, "fetch"), \
                mock.patch.object(pipeline.pr_review_target, "resolve_target", return_value=bounded_target), \
                mock.patch.object(sys, "argv", ["review_pipeline.py", "collect-t2", "--directory", str(bounded_output)]), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(pipeline.main(), 1)
        receipt_path = bounded_output / "collection-failure.json"
        receipt = receipt_path.read_bytes()
        failure = json.loads(receipt)
        self.assertLessEqual(len(receipt), pipeline.input_producer.MAX_FAILURE_BYTES)
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["failure_summary"]["schema"],
                         pipeline.input_producer.FAILURE_SUMMARY_SCHEMA)
        self.assertEqual(failure["failure_summary"]["original"], {
            "sha256": hashlib.sha256(original_payload).hexdigest(),
            "byte_length": len(original_payload),
        })
        self.assertEqual(failure["failure_summary"]["inventory"]["total_records"], 257)
        self.assertLess(failure["failure_summary"]["inventory"]["retained_records"], 257)
        self.assertTrue(failure["failure_summary"]["truncated"])
        self.assertFalse(failure["failure_summary"]["complete"])
        self.assertEqual(failure["raw_inventory"], original_failure["raw_inventory"])
        self.assertTrue(any("z-later.txt" in item.get("paths", []) for item in failure["inventory"]))
        self.assertEqual(sorted(item.name for item in bounded_output.iterdir()), ["collection-failure.json"])
        self.assertFalse((bounded_output / "t2-input.json").exists())
        self.assertFalse((bounded_output / "collection-receipt.json").exists())
        self.assertFalse(bounded_witness_output.exists(), "failed CLI collection must emit no success witness")
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "successful-producer witness"):
            pipeline.trusted_collector_t2(bounded_output)
        self.assertIn(str(raised.exception), errors.getvalue())
        self.assertNotIn("review pipeline operation failed", errors.getvalue())
        print(json.dumps({
            "cli_returncode": 1,
            "failure_receipt": failure,
            "failure_receipt_bytes": len(receipt),
            "github_output_exists": bounded_witness_output.exists(),
            "residual_artifacts": sorted(item.name for item in bounded_output.iterdir()),
            "fresh_consumer_rejected": True,
        }, sort_keys=True))

    def test_t2_consumer_rejects_uncertain_leftovers_even_when_failure_fence_write_fails(self):
        output = self.directory / "uncertain-output"
        artifacts = {
            "t2-input.json": b'{"fixture":"inert"}',
            "collection-receipt.json": b'{"status":"complete"}',
        }
        original_fsync = pipeline.input_producer._fsync_directory
        original_write = pipeline.input_producer._write_no_clobber
        original_unlink = Path.unlink
        calls = 0

        def fail_final_fsync(directory):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected receipt fsync failure")
            return original_fsync(directory)

        def fail_fence_write(directory, name, data):
            if name == "collection-failure.json":
                raise pipeline.input_producer.PublicationError("injected failure-fence write failure")
            return original_write(directory, name, data)

        def fail_marker_unlink(path, *args, **kwargs):
            if path == output / "collection-receipt.json":
                raise OSError("injected final-marker cleanup failure")
            return original_unlink(path, *args, **kwargs)

        with mock.patch.object(pipeline.input_producer, "_fsync_directory", side_effect=fail_final_fsync), \
                mock.patch.object(pipeline.input_producer, "_write_no_clobber", side_effect=fail_fence_write), \
                mock.patch.object(Path, "unlink", new=fail_marker_unlink), \
                self.assertRaises(pipeline.input_producer.PublicationError):
            pipeline.input_producer.publish_collection(output, artifacts)
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "successful-producer witness"):
            pipeline.trusted_collector_t2(output)

    def test_collect_t2_cli_publication_failure_fences_the_full_six_artifact_boundary(self):
        repository, base, head = self.make_real_t2_repo()
        output = self.directory / "failed-t2-output"
        target = {"review": "true", "head_sha": head, "base_sha": base, "body": "body"}
        environment = {
            "GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "1151", "HEAD_SHA": head,
            "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_OUTPUT": "",
        }
        original_fsync = pipeline.input_producer._fsync_directory
        calls = 0

        def fail_receipt_directory_fsync(directory):
            nonlocal calls
            calls += 1
            # Five complete non-receipt links precede the receipt's final
            # directory durability boundary in the actual collect-t2 path.
            if calls == 6:
                raise OSError("injected final receipt directory fsync failure")
            return original_fsync(directory)

        errors = io.StringIO()
        with mock.patch.dict(os.environ, environment, clear=False), \
                mock.patch.object(pipeline, "ROOT", repository), \
                mock.patch.object(pipeline, "fetch"), \
                mock.patch.object(pipeline.pr_review_target, "resolve_target", side_effect=[target, target]), \
                mock.patch.object(pipeline.input_producer, "_fsync_directory",
                                  side_effect=fail_receipt_directory_fsync), \
                mock.patch.object(sys, "argv", ["review_pipeline.py", "collect-t2", "--directory", str(output)]), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(pipeline.main(), 1)
        self.assertEqual(calls, 7)  # the best-effort failure fence also durably commits
        self.assertEqual(
            sorted(item.name for item in output.iterdir()),
            ["collection-failure.json", "context.json", "history.json", "pr-body.md", "pr.diff", "t2-input.json"],
        )
        self.assertFalse((output / "collection-receipt.json").exists())
        self.assertNotIn("injected final receipt", errors.getvalue())
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "successful-producer witness"):
            pipeline.trusted_collector_t2(output)

    def test_collect_t2_cli_triple_publication_fault_leaves_exact_six_residuals_without_witness(self):
        repository, base, head = self.make_real_t2_repo()
        positive = self.directory / "triple-fault-positive"
        document, _witness = self.collect_real_t2(repository, base, head, positive)
        artifact_names = {
            "context.json", "pr.diff", "pr-body.md", "history.json", "t2-input.json",
            "collection-receipt.json",
        }
        expected = {name: (positive / name).read_bytes() for name in artifact_names}

        output = self.directory / "triple-fault-output"
        witness_output = self.directory / "triple-fault-github-output"
        target = {"review": "true", "head_sha": head, "base_sha": base, "body": "body"}
        environment = {
            "GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "1151", "HEAD_SHA": head,
            "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_OUTPUT": str(witness_output),
        }
        original_fsync = pipeline.input_producer.os.fsync
        original_open = pipeline.input_producer.os.open
        original_unlink = Path.unlink
        directory_fsync_calls = 0
        receipt_fsync_failures = 0
        receipt_unlink_calls = 0
        fence_open_calls = 0

        def fail_final_receipt_fsync(descriptor):
            nonlocal directory_fsync_calls, receipt_fsync_failures
            descriptor_stat = os.fstat(descriptor)
            if stat.S_ISDIR(descriptor_stat.st_mode) and output.is_dir():
                output_stat = output.stat()
                if ((descriptor_stat.st_dev, descriptor_stat.st_ino) ==
                        (output_stat.st_dev, output_stat.st_ino)):
                    directory_fsync_calls += 1
                    if (output / "collection-receipt.json").is_file():
                        receipt_fsync_failures += 1
                        raise OSError("injected final receipt directory fsync EIO")
            return original_fsync(descriptor)

        def fail_failure_fence_open(path, *args, **kwargs):
            nonlocal fence_open_calls
            candidate = Path(path)
            if (candidate.parent == output and candidate.name.startswith(".collection-failure.json.")
                    and candidate.name.endswith(".partial")):
                fence_open_calls += 1
                raise OSError("injected failure-fence open EIO")
            return original_open(path, *args, **kwargs)

        def fail_receipt_unlink(path, *args, **kwargs):
            nonlocal receipt_unlink_calls
            if path == output / "collection-receipt.json":
                receipt_unlink_calls += 1
                raise OSError("injected receipt unlink EIO")
            return original_unlink(path, *args, **kwargs)

        errors = io.StringIO()
        with mock.patch.dict(os.environ, environment, clear=False), \
                mock.patch.object(pipeline, "ROOT", repository), \
                mock.patch.object(pipeline, "fetch"), \
                mock.patch.object(pipeline, "response_schema", return_value={}), \
                mock.patch.object(pipeline.test_scope, "load_policy", return_value={}), \
                mock.patch.object(pipeline.pr_review_target, "resolve_target", side_effect=[target, target]), \
                mock.patch.object(pipeline.input_producer.os, "fsync",
                                  side_effect=fail_final_receipt_fsync), \
                mock.patch.object(pipeline.input_producer.os, "open",
                                  side_effect=fail_failure_fence_open), \
                mock.patch.object(Path, "unlink", new=fail_receipt_unlink), \
                mock.patch.object(sys, "argv", ["review_pipeline.py", "collect-t2", "--directory", str(output)]), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(pipeline.main(), 1)
        self.assertEqual((directory_fsync_calls, receipt_fsync_failures,
                          receipt_unlink_calls, fence_open_calls), (6, 1, 1, 1))
        self.assertFalse(witness_output.exists(), "failed CLI collection must emit no success witness")
        residual_names = sorted(item.name for item in output.iterdir())
        self.assertEqual(residual_names, sorted(artifact_names))
        self.assertEqual({item.name: item.read_bytes() for item in output.iterdir()}, expected)
        self.assertNotIn("collection-failure.json", residual_names)
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "successful-producer witness") as refused:
            pipeline.trusted_collector_t2(output)
        print(json.dumps({
            "cli_returncode": 1,
            "directory_fsync_calls": directory_fsync_calls,
            "receipt_fsync_failures": receipt_fsync_failures,
            "receipt_unlink_calls": receipt_unlink_calls,
            "failure_fence_open_calls": fence_open_calls,
            "residual_artifacts": sorted(artifact_names),
            "residual_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(expected.items())},
            "success_witness_emitted": witness_output.exists(),
            "strict_consumer_refusal": str(refused.exception),
        }, sort_keys=True))

    def make_real_generated_only_repo(self):
        """A real Git base/head whose complete inventory is Portal-class generated."""
        temporary = tempfile.TemporaryDirectory(prefix="lmdj-pipeline-generated-only-")
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name) / "repo"
        repository.mkdir()

        def git(*args):
            result = subprocess.run(["git", *args], cwd=repository, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            return result.stdout.decode().strip()

        git("init", "-q")
        (repository / "source.txt").write_text("old\n", encoding="utf-8")
        git("add", ".")
        git("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        provenance = repository / "apps/architecture-portal/versioned_provenance"
        provenance.mkdir(parents=True)
        (provenance / "version-1.0.57.0.json").write_text("{}\n", encoding="utf-8")
        git("add", ".")
        git("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "head")
        head = git("rev-parse", "HEAD")
        return repository, base, head

    def test_collect_t2_generated_only_publishes_receipt_and_exits_zero(self):
        repository, base, head = self.make_real_generated_only_repo()
        output = self.directory / "generated-only-output"
        witness_output = self.directory / "generated-only-github-output"
        target = {"review": "true", "head_sha": head, "base_sha": base, "body": "body"}
        environment = {
            "GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "1151", "HEAD_SHA": head,
            "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_OUTPUT": str(witness_output),
        }
        with mock.patch.dict(os.environ, environment, clear=False), \
                mock.patch.object(pipeline, "ROOT", repository), \
                mock.patch.object(pipeline, "fetch"), \
                mock.patch.object(pipeline.pr_review_target, "resolve_target", return_value=target), \
                mock.patch.object(sys, "argv", ["review_pipeline.py", "collect-t2", "--directory", str(output)]):
            self.assertEqual(pipeline.main(), 0)
        self.assertEqual(sorted(item.name for item in output.iterdir()), ["generated-only-receipt.json"])
        self.assertFalse((output / "collection-receipt.json").exists())
        self.assertFalse((output / "collection-failure.json").exists())
        receipt_bytes = (output / "generated-only-receipt.json").read_bytes()
        receipt = pipeline.read(output / "generated-only-receipt.json")
        self.assertEqual(receipt["schema"], pipeline.input_producer.GENERATED_ONLY_RECEIPT_SCHEMA)
        self.assertEqual(receipt["status"], "generated-only")
        self.assertEqual(receipt["identity"]["head_sha"], head)
        self.assertEqual(receipt["excluded_generated"]["paths"],
                         ["apps/architecture-portal/versioned_provenance/version-1.0.57.0.json"])
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        self.assertEqual(receipt["receipt_sha256"], hashlib.sha256(
            pipeline.input_producer.json_bytes(unsigned)).hexdigest())
        lines = witness_output.read_text().splitlines()
        self.assertIn("generated_only=true", lines)
        digest = hashlib.sha256(receipt_bytes).hexdigest()
        self.assertIn("generated_receipt_sha256=" + digest, lines)

    def publish_generated_with_doubles(self, *, prior=None):
        """Run publish_generated with API doubles; `prior` is 'same' or 'conflict'."""
        repository, base, head = self.make_real_generated_only_repo()
        output = Path(tempfile.mkdtemp(prefix="publish-generated-output-", dir=self.directory))
        identity = {
            "repository": "endaye/lmdj", "pull_request": 1151, "base_sha": base,
            "head_sha": head, "control_sha": head, "run_id": "99", "run_attempt": 1,
        }
        receipt = {
            "schema": pipeline.input_producer.GENERATED_ONLY_RECEIPT_SCHEMA,
            "status": "generated-only",
            "identity": identity,
            "head_sha": head,
            "excluded_generated": {
                "count": 1,
                "paths": ["apps/architecture-portal/versioned_provenance/version-1.0.57.0.json"],
                "entries": [{"path": "apps/architecture-portal/versioned_provenance/version-1.0.57.0.json",
                             "object_id": "1" * 40, "sha256": "2" * 64}],
            },
        }
        receipt["receipt_sha256"] = hashlib.sha256(pipeline.input_producer.json_bytes(receipt)).hexdigest()
        pipeline.save(output / "generated-only-receipt.json", receipt)
        digest = hashlib.sha256((output / "generated-only-receipt.json").read_bytes()).hexdigest()
        prior_digests = {"same": digest, "conflict": "0" * 64}
        bodies = [] if prior is None else [pipeline.pr_review_target.generated_body(
            "endaye/lmdj", 1151, head, "99", "1", prior_digests[prior])]
        calls = []
        environment = {"GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "1151", "HEAD_SHA": head,
                       "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_TOKEN": "secret"}
        bot = {"id": 20, "type": "Bot", "login": "github-actions[bot]"}
        priors = [{"commit_id": head, "user": bot, "body": body} for body in bodies]
        with mock.patch.dict(os.environ, environment), \
                mock.patch.object(pipeline, "git", return_value=(head + "\n").encode()), \
                mock.patch.object(pipeline, "authenticate", side_effect=lambda *a, **k: calls.append("authenticate")), \
                mock.patch.object(pipeline, "api", return_value=bot), \
                mock.patch.object(pipeline, "pages", return_value=priors), \
                mock.patch.object(pipeline.pr_review_target, "publish_generated",
                                  side_effect=lambda *args: calls.append(("publish", args))):
            marker = pipeline.publish_generated(output)
        return marker, calls, head, digest

    def test_publish_generated_posts_the_marker_once(self):
        marker, calls, head, digest = self.publish_generated_with_doubles()
        self.assertEqual(marker, pipeline.pr_review_target.generated_identity(
            "endaye/lmdj", 1151, head, "99", "1", digest))
        self.assertEqual([c if isinstance(c, str) else c[0] for c in calls], ["authenticate", "publish"])

    def test_publish_generated_skips_an_identical_duplicate(self):
        marker, calls, head, digest = self.publish_generated_with_doubles(prior="same")
        self.assertEqual(marker, pipeline.pr_review_target.generated_identity(
            "endaye/lmdj", 1151, head, "99", "1", digest))
        self.assertNotIn("publish", [c if isinstance(c, str) else c[0] for c in calls])

    def test_publish_generated_refuses_a_conflicting_duplicate(self):
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "different content"):
            self.publish_generated_with_doubles(prior="conflict")

    def test_collect_t2_target_change_before_publication_fails_closed(self):
        repository, base, head = self.make_real_t2_repo()
        output = self.directory / "changed-target-output"
        target = {"review": "true", "head_sha": head, "base_sha": base, "body": "body"}
        moved = {"review": "true", "head_sha": "f" * 40, "base_sha": base, "body": "body"}
        environment = {"GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "1151", "HEAD_SHA": head,
                       "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_OUTPUT": ""}
        with mock.patch.dict(os.environ, environment, clear=False), \
                mock.patch.object(pipeline, "ROOT", repository), \
                mock.patch.object(pipeline, "fetch"), \
                mock.patch.object(pipeline.pr_review_target, "resolve_target", side_effect=[target, moved]), \
                self.assertRaisesRegex(review_scope.ReviewScopeError, "before complete-input publication"):
            pipeline.collect_t2(output)
        self.assertFalse((output / "t2-input.json").exists())
        self.assertFalse((output / "collection-receipt.json").exists())

    def test_collect_t2_refuses_preexisting_output_before_resolving_target(self):
        output = self.directory / "already-used"
        output.mkdir()
        sentinel = output / "sentinel"
        sentinel.write_bytes(b"old")
        with mock.patch.object(pipeline.pr_review_target, "resolve_target") as resolve:
            with self.assertRaisesRegex(pipeline.input_producer.PublicationError, "already used"):
                pipeline.collect_t2(output)
        resolve.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b"old")


if __name__ == "__main__":
    unittest.main()
