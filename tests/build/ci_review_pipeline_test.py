#!/usr/bin/env python3
"""Adapter contracts with real artifact files and strict bounded process doubles.

Backend network/authentication and GitHub writes are explicitly O1 gaps. The
tests do not turn a mocked write into evidence of platform permissions.
"""
import json
import os
import re
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import contextlib
import io

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import review_pipeline as pipeline
import review_scope
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

    def test_observed_bare_kimi_labels_still_trigger_fallback(self):
        self.capture("glm", BACKEND_OUTCOME="failure")
        malformed = dict(self.model, test_scope={"labels": ["creator", "docs_static", "portal"],
                                                "reason": "Observed malformed labels from PR #855."})
        self.capture("kimi", REVIEW_JSON=json.dumps(malformed))
        history = pipeline.read(self.directory / "history.json")
        self.assertEqual(history[-1]["error_class"], "invalid_output")
        self.assertEqual(review_scope.next_backend(test_scope.load_policy(ROOT), history), "grok")
        self.assertFalse((self.directory / "review.json").exists())

    def test_collected_schema_reaches_both_claude_argument_lists(self):
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
        source = (ROOT / ".github/workflows/pr-review.yml").read_text()
        arguments = re.findall(r"          claude_args: >-\n(.*?)(?=\n      -)", source, re.S)
        self.assertEqual(len(arguments), 2)
        for args in arguments:
            parsed = shlex.split(args.replace("${{ steps.input.outputs.review_schema }}", schema))
            actual = json.loads(parsed[parsed.index("--json-schema") + 1])
            self.assertEqual(actual, pipeline.response_schema(test_scope.load_policy(ROOT)),
                             "why: Claude did not receive trusted policy schema; remedy: wire the collect output")
            allowed = actual["properties"]["test_scope"]["properties"]["labels"]["items"]["enum"]
            for bare in ("creator", "docs_static", "portal", "test:unknown"):
                self.assertNotIn(bare, allowed)
        self.assertEqual((self.directory / "pr-body.md").read_text(), target["body"])

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

    def test_only_publish_gets_the_specific_message(self):
        """The generic line stays everywhere the model's text is still in scope.

        `grok` raises `ReviewScopeError` from positions that describe provider
        output, and two tests below keep those generic. This asserts the
        boundary directly rather than leaving it to them, because the arm added
        for `publish` is one `args.command` away from covering them too.
        """
        code, stderr = self.cli("finalize")  # empty history: chain unfinished
        self.assertEqual(code, 1)
        self.assertIn("review pipeline operation failed", stderr)
        self.assertNotIn("review chain did not finish", stderr)

    def test_attempt_after_success_is_refused(self):
        self.capture("glm")
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "fallback order"):
            self.capture("kimi")

    def test_partial_chain_is_not_finalized(self):
        self.capture("glm", BACKEND_OUTCOME="failure")
        with self.assertRaisesRegex(review_scope.ReviewScopeError, "did not finish"):
            pipeline.finalize(self.directory)

    def test_grok_has_bounded_read_only_process_and_no_github_token(self):
        (self.directory / "pr-body.md").write_text("untrusted body")
        (self.directory / "pr.diff").write_text("untrusted diff")

        def run(command, *, env, capture_output, text, timeout):
            self.assertEqual(command[0], "grok")
            self.assertIn("--no-subagents", command)
            self.assertEqual(command[command.index("--tools") + 1], "read_file,grep,list_dir")
            self.assertNotIn("GITHUB_TOKEN", env)
            self.assertNotIn("GH_TOKEN", env)
            self.assertNotIn("GROK_AUTH_JSON", env)
            self.assertEqual(timeout, 300)
            self.assertTrue(capture_output and text)
            return subprocess.CompletedProcess(command, 0, json.dumps({"text": json.dumps(self.model)}), "")

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "secret", "GH_TOKEN": "secret", "GROK_AUTH_JSON": "{}"}), \
                mock.patch.object(pipeline.subprocess, "run", side_effect=run):
            pipeline.grok(self.directory)
        self.assertEqual(pipeline.read(self.directory / "grok.json"), self.model)
        self.assertFalse((self.directory / "grok-auth/auth.json").exists())

    def test_grok_timeout_cleans_exact_temporary_auth(self):
        (self.directory / "pr-body.md").write_text("body")
        (self.directory / "pr.diff").write_text("diff")
        with mock.patch.dict(os.environ, {"GROK_AUTH_JSON": "{}"}), \
                mock.patch.object(pipeline.subprocess, "run", side_effect=subprocess.TimeoutExpired("grok", 300)), \
                self.assertRaises(subprocess.TimeoutExpired):
            pipeline.grok(self.directory)
        self.assertFalse((self.directory / "grok-auth/auth.json").exists())

    def assert_grok_diagnostic(self, category, *, returncode=None, stdout="RAW_PROVIDER_SECRET",
                               error=None, credential="PRIVATE_AUTH_SECRET"):
        (self.directory / "pr-body.md").write_text("PRIVATE_BODY_SECRET")
        (self.directory / "pr.diff").write_text("PRIVATE_DIFF_SECRET")
        output, errors = io.StringIO(), io.StringIO()
        process = subprocess.CompletedProcess(["grok"], returncode or 0, stdout, "RAW_STDERR_SECRET")
        with mock.patch.dict(os.environ, {"GROK_AUTH_JSON": credential, "XAI_API_KEY": ""}), \
                mock.patch.object(sys, "argv", ["review_pipeline.py", "grok", "--directory", str(self.directory)]), \
                mock.patch.object(pipeline.subprocess, "run", return_value=process, side_effect=error) as run, \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(pipeline.main(), 1)
        if category == "credential_unavailable":
            run.assert_not_called()
        else:
            run.assert_called_once()
        self.assertEqual(output.getvalue(), "")
        lines = errors.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), {"schema": "lmdj.ci-review-diagnostic.v1", "backend": "grok",
                                              "category": category, "returncode": returncode})
        self.assertIn("why: review pipeline operation failed; remedy:", lines[1])
        self.assertNotIn("SECRET", errors.getvalue(),
                         "why: failure diagnostics leaked raw data; remedy: emit finite local categories only")
        self.assertFalse((self.directory / "grok-auth/auth.json").exists())
        self.assertFalse((self.directory / "grok.json").exists())

    def test_grok_missing_credential_is_visible_before_process_launch(self):
        self.assert_grok_diagnostic("credential_unavailable", credential="")

    def test_grok_launch_failure_never_prints_exception(self):
        self.assert_grok_diagnostic("launch_failure", error=OSError("PRIVATE_LAUNCH_SECRET"))

    def test_grok_timeout_never_prints_partial_output(self):
        self.assert_grok_diagnostic("timeout", error=subprocess.TimeoutExpired(
            "PRIVATE_COMMAND_SECRET", 300, output="PARTIAL_OUTPUT_SECRET", stderr="PARTIAL_STDERR_SECRET"))

    def test_grok_process_failure_retains_actual_exit_code(self):
        self.assert_grok_diagnostic("process_failure", returncode=17)

    def test_grok_non_json_envelope_does_not_expose_parse_input(self):
        self.assert_grok_diagnostic("invalid_envelope", returncode=0)

    def test_grok_array_envelope_remains_invalid(self):
        self.assert_grok_diagnostic("invalid_envelope", returncode=0, stdout='["PRIVATE_ENVELOPE_SECRET"]')

    def test_grok_error_envelope_does_not_expose_provider_message(self):
        self.assert_grok_diagnostic("error_envelope", returncode=0,
                                   stdout=json.dumps({"type": "error", "message": "PRIVATE_ERROR_SECRET"}))

    def test_grok_invalid_review_remains_failure_without_echoing_model_text(self):
        self.assert_grok_diagnostic("invalid_review", returncode=0,
                                   stdout=json.dumps({"text": "PRIVATE_MODEL_SECRET"}))

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

    def test_workflow_uses_only_one_successful_chain_and_exact_artifact(self):
        source = (ROOT / ".github/workflows/pr-review.yml").read_text()
        self.assertEqual(source.count("name: Review fallback"), 1)
        self.assertEqual(source.count("timeout-minutes: 5"), 5)
        self.assertIn("steps.capture-glm.outputs.reviewed != 'true' && steps.capture-kimi.outputs.reviewed != 'true'", source)
        self.assertIn("${{ env.REVIEW_DIR }}/review.json", source)
        self.assertIn("${{ env.REVIEW_DIR }}/failure.json", source)
        self.assertIn("pr-test-scope-${{ needs.target.outputs.head_sha }}-${{ github.run_id }}-${{ github.run_attempt }}", source)
        self.assertNotIn("issues: write", source)
        self.assertNotIn("actions: write", source)

    def publish_with_doubles(self, *, stale=False, unavailable=False):
        calls = []
        def auth(identity):
            calls.append("authenticate")
            if stale:
                raise review_scope.ReviewScopeError("why: stale head; remedy: retry")
            return identity
        environment = {"GITHUB_REPOSITORY": "endaye/lmdj", "PR_NUMBER": "7", "HEAD_SHA": "a" * 40,
                       "GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_TOKEN": "secret"}
        with mock.patch.dict(os.environ, environment), \
                mock.patch.object(pipeline, "git", return_value=("c" * 40 + "\n").encode()), \
                mock.patch.object(pipeline, "fetch"), mock.patch.object(pipeline, "authenticate", side_effect=auth), \
                mock.patch.object(pipeline, "previous_records", return_value=([], unavailable)), \
                mock.patch.object(pipeline.change_scope, "read_git_inventory", return_value=[pipeline.change_scope.ChangedFile("M", ("docs/notes/a.md",))]), \
                mock.patch.object(pipeline, "publish_model", side_effect=lambda identity, record, model, **kwargs: calls.append(("review", {"summary": model["summary"] + model["test_scope"]["reason"] + pipeline.codec.encode(record)}))), \
                mock.patch.object(pipeline.grok_review, "github_request", side_effect=lambda *a: calls.append(("labels", a))):
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

    def test_same_head_unavailable_receipt_is_not_silently_ignored(self):
        identity = {**self.identity, "backend": "glm"}
        posted = {"commit_id": identity["head_sha"], "user": {"id": 5}, "body": pipeline.codec.unavailable(identity)}
        with mock.patch.object(pipeline, "api", return_value={"id": 5}), \
                mock.patch.object(pipeline, "pages", return_value=[posted]), mock.patch.object(pipeline, "authenticate"):
            records, unavailable = pipeline.previous_records(identity, test_scope.load_policy(ROOT))
        self.assertEqual(records, [])
        self.assertTrue(unavailable)

    def test_later_same_head_review_keeps_unavailable_scope_full(self):
        self.capture("glm")
        pipeline.finalize(self.directory)
        calls = self.publish_with_doubles(unavailable=True)
        self.assertEqual(pipeline.read(self.directory / "scope.json")["effective"]["kind"], "full")
        self.assertEqual(calls[3][1][-1], {"labels": ["test:full"]})

    def test_backend_conditions_require_successful_collection(self):
        source = (ROOT / ".github/workflows/pr-review.yml").read_text()
        for step in ("glm", "kimi", "grok", "capture-glm", "capture-kimi", "capture-grok"):
            block = source.split("        id: " + step + "\n", 1)[1].split("      - ", 1)[0]
            self.assertIn("steps.input.outcome == 'success'", block,
                          "why: backend could run without complete diff; remedy: gate it on input collection success")


if __name__ == "__main__":
    unittest.main()
