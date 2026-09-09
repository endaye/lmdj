#!/usr/bin/env python3
"""Contract tests for the standalone PR review entry (capacity plan T4).

`pr-review.yml` reviews a Pull Request's current head independently of
`ci.yml`, and `.github/scripts/pr_review_target.py` is what binds a run to
that head. These pin T5a's automatic entry and the
trust boundaries, the head binding, the honest-state reporting, and the
relationship to `required_conversation_resolution` the plan asks to be written
down.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".github/scripts"))

import pr_review_target as target  # noqa: E402

WORKFLOW = REPO_ROOT / ".github/workflows/pr-review.yml"
CI = REPO_ROOT / ".github/workflows/ci.yml"
SCRIPT = REPO_ROOT / ".github/scripts/pr_review_target.py"
SCOPE_POLICY = REPO_ROOT / "scripts/ci/scope_policy.json"
PORTAL_PAGE = REPO_ROOT / "apps/docs-site/docs/operations/testing-and-proof.mdx"

HEAD = "a" * 40
OTHER = "b" * 40


def job_block(source: str, job_id: str) -> str:
    match = re.search(rf"\n  {re.escape(job_id)}:\n(.*?)(?=\n  [a-z][a-z0-9-]*:\n|\Z)", source, re.S)
    if match is None:
        raise AssertionError(f"job {job_id} not found")
    return match.group(1)


def pull(*, state="open", draft=False, head_repo="endaye/lmdj", head_sha=HEAD, labels=()):
    return {
        "number": 7, "state": state, "draft": draft, "title": "feat: x", "body": "body text",
        "html_url": "https://github.com/endaye/lmdj/pull/7",
        "head": {"sha": head_sha, "ref": "feat/x", "repo": {"full_name": head_repo}},
        "base": {"sha": OTHER, "ref": "main"},
        "labels": [{"name": name} for name in labels],
    }


class StandaloneEntryWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.jobs = {name: job_block(cls.source, actual) for name, actual in
                    (("target", "target"), ("claude-review", "review"), ("grok-review", "review"),
                     ("publish-claude", "publish"), ("publish-grok", "publish"))}

    def test_yaml_parser_retains_both_run_name_expressions_after_hash(self):
        # Use the actual pinned workflow parser instead of a hand-written YAML
        # approximation or an assertion that quotes happen to appear in source.
        executable = os.environ.get("LMDJ_ACTIONLINT") or shutil.which("actionlint")
        if not executable and os.environ.get("RUNNER_TEMP"):
            candidate = Path(os.environ["RUNNER_TEMP"]) / "actionlint"
            if candidate.is_file():
                executable = str(candidate)
        if not executable:
            self.skipTest("set LMDJ_ACTIONLINT to the pinned actionlint for YAML semantic verification")

        def parsed_expressions(line):
            # secrets is forbidden in run-name. Each visible expression must
            # produce one semantic diagnostic; a YAML comment produces none.
            # Probe separately because actionlint stops at a scalar's first
            # invalid expression; the other expression stays valid each time.
            detected = 0
            expressions = r"\$\{\{.*?\}\}"
            for position in range(len(re.findall(expressions, line))):
                indices = iter(range(len(re.findall(expressions, line))))
                probe = re.sub(expressions, lambda _: "${{ secrets.RUN_TITLE_PARSE_PROBE }}"
                               if next(indices) == position else "${{ 1 }}", line)
                document = ("name: parser probe\n" + probe + "\non: workflow_dispatch\njobs:\n"
                            "  check:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n")
                result = subprocess.run([executable, "-no-color", "-shellcheck=", "-pyflakes=", "-"],
                                        input=document, text=True, capture_output=True, timeout=15)
                if result.returncode not in (0, 1):
                    self.fail("why: actionlint did not complete semantic parsing; remedy: check its pinned installation")
                detected += 'context "secrets" is not allowed here' in result.stdout + result.stderr
            return detected

        # Real old spelling reproduced the production truncation. It parses
        # successfully but hides both expressions behind the YAML comment.
        old = "run-name: PR Review / #${{ inputs.pr_number }} @ ${{ github.sha }}"
        self.assertEqual(parsed_expressions(old), 0)
        current = next(line for line in self.source.splitlines() if line.startswith("run-name:"))
        self.assertEqual(parsed_expressions(current), 2,
                         "why: YAML discarded the PR/head run-name expressions after #; "
                         "remedy: quote the complete run-name scalar")

    def test_dispatch_only_on_main_and_pr_automatically_active(self):
        self.assertIn("github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'", self.jobs["target"])
        condition = self.jobs["target"].split('    if: >-\n', 1)[1].split('    runs-on:', 1)[0]
        self.assertEqual(' '.join(condition.split()),
                         "(github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main') || github.event_name == 'pull_request'")
        self.assertIn("pull_request:", self.source)
        self.assertNotIn("pull_request_target:", self.source)
        directives = '\n'.join(line for line in self.source.splitlines() if not line.lstrip().startswith('#'))
        self.assertNotIn('PR_REVIEW_ENTRY', directives,
                         'why: automatic review must activate with the workflow cutover; remedy: remove the manual-rollout variable gate')

    def test_automatic_review_has_one_entry_and_no_product_trigger(self):
        ci_events = CI.read_text().split('\npermissions:', 1)[0]
        self.assertNotRegex(ci_events, r'(?m)^  (?:pull_request|pull_request_target|push):',
                            'why: PR Review owns new-head review and product self-tests are independent; remedy: retire Core CI PR/push triggers')
        events = self.source.split('\npermissions:', 1)[0]
        self.assertIn('types: [opened, synchronize, reopened, ready_for_review, closed]', events)
        self.assertNotRegex(events, r'(?m)^  (?:push|schedule):')

    def test_no_pr_head_executable_checkout_in_any_job(self):
        trusted = "ref: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || github.sha }}"
        for name, job in self.jobs.items():
            with self.subTest(job=name):
                self.assertIn(trusted, job)
                self.assertNotIn("ref: ${{ needs.target.outputs.head_sha }}", job)
                self.assertIn("persist-credentials: false", job)
        for name in ("claude-review", "grok-review"):
            self.assertIn('review_pipeline.py collect --directory "$REVIEW_DIR"', self.jobs[name])
        adapter = (REPO_ROOT / "scripts/ci/review_pipeline.py").read_text()
        self.assertIn('"--no-ext-diff", "--no-textconv"', adapter)
        self.assertNotIn('git("checkout"', adapter)

    def test_models_have_no_write_token_or_executable_tools(self):
        for name in ("claude-review", "grok-review"):
            job = self.jobs[name]
            self.assertIn("pull-requests: read", job)
            self.assertNotIn(": write", job)
            self.assertNotIn("--publish-file", job)
            # Individual backend failures are captured and validated before
            # fallback. The job itself is not continue-on-error.
            self.assertNotRegex(job, r"(?m)^    continue-on-error: true$")
            self.assertIn("Manual takeover", job)
        claude = self.jobs["claude-review"]
        self.assertIn('--tools "Read" --allowedTools "Read" --disable-slash-commands', claude)
        self.assertIn('classify_inline_comments: "false"', claude)
        self.assertIn("steps.glm.outputs.structured_output", claude)
        self.assertIn("steps.kimi.outputs.structured_output", claude)
        self.assertNotIn("/pr-review --comment", claude)
        self.assertNotIn("Bash(", claude)
        grok = self.jobs["grok-review"]
        self.assertIn("review_pipeline.py grok", grok)
        self.assertNotIn("GITHUB_TOKEN:", grok.split("      - name: Grok review", 1)[1].split("      - name: Validate Grok", 1)[0])

    def test_the_producer_cannot_report_success_over_a_not_reviewed_result(self):
        """The `finalize` verdict must be able to fail the job.

        #939: `Review fallback` reported success while its artifact said
        `not-reviewed`, so a reader scanning job names saw a green check over a
        review that never happened. The lane as a whole never lost the
        distinction -- the publisher refuses a not-reviewed result -- but the
        producer's own name and conclusion did not match what it produced.

        `review_pipeline.py finalize` now exits nonzero for that case. This
        asserts the workflow lets that exit reach the job conclusion, because
        the fix is defeated by a single `continue-on-error` or `|| true` on the
        step, and neither would look wrong in review.
        """
        job = self.jobs["claude-review"]
        finalize = job.split("      - name: Save honest final result", 1)[1]
        finalize = finalize.split("      - uses:", 1)[0]
        self.assertIn("review_pipeline.py finalize", finalize)
        self.assertNotIn("continue-on-error", finalize)
        self.assertNotIn("|| true", finalize)
        self.assertNotIn("|| :", finalize)
        # The receipts must still upload after that failure, or a dropped
        # review stops being recoverable -- #916's was recovered from exactly
        # this artifact hours after the fact.
        upload = job.split("      - uses: actions/upload-artifact", 1)[1]
        self.assertIn("if: ${{ always() }}", upload)
        # And the workflow already expected this exit: its takeover step is
        # guarded on failure() and says NOT REVIEWED.
        self.assertIn("Manual takeover", job)
        self.assertIn("if: ${{ failure() }}", job)

    def test_publishers_are_short_trusted_data_consumers(self):
        for name in ("publish-claude", "publish-grok"):
            job = self.jobs[name]
            self.assertIn("pull-requests: write", job)
            self.assertIn("timeout-minutes: 5", job)
            self.assertNotIn("contents: write", job)
            self.assertNotIn("issues: write", job)
            self.assertIn('HEAD_SHA: ${{ needs.target.outputs.head_sha }}', job)
            self.assertIn("review_pipeline.py publish", job)
            self.assertIn("actions/download-artifact@v4", job)
            self.assertIn("github.run_attempt", job)
            self.assertIn("needs.target.outputs.head_sha", job)
            self.assertIn("Report the review state", job)
            self.assertIn("review the current head manually", job)
            self.assertNotIn("anthropics/claude-code-action", job)
            self.assertNotIn("grok_review.py", job)

    def test_review_has_no_heavy_dependency_and_no_merge_authority(self):
        jobs = self.source.split("\njobs:\n", 1)[1]
        for forbidden in ("queue_ticket", "phase_gate", "pr" + "_gate",
                          "lmdj-native-heavy", "needs: [change-scope", "contents: write"):
            self.assertNotIn(forbidden, jobs)
        self.assertIn("required_conversation_resolution", self.source)
        self.assertIn("#707", self.source)
        self.assertIn("not a new gate", self.source)

    def test_backend_selector_and_runtime_pins_stay_compatible(self):
        self.assertNotIn("vars.CLAUDE_REVIEW_ORDER", self.source)
        self.assertIn("steps.capture-glm.outputs.reviewed != 'true'", self.jobs["claude-review"])
        self.assertIn("steps.capture-kimi.outputs.reviewed != 'true'", self.jobs["grok-review"])
        pin = re.search(r"uses: anthropics/claude-code-action@([0-9a-f]{40})", self.source).group(1)
        self.assertEqual(pin, "fa2b2666b747000bf42767d1f332065b375e3c8f")
        pins = {"GROK_VERSION": "1.0.13", "GROK_SHA256": "edf79521581bb5e6b95abef848491a6a742e860da3e237ebe86a280d30dce4c1"}
        for key in pins:
            value = re.search(rf'{key}: "([^"]+)"', self.source).group(1)
            self.assertEqual(value, pins[key])
        self.assertIn("sha256sum --check --strict", self.source)
        self.assertNotIn("secrets.ANTHROPIC_API_KEY", self.source)
        self.assertIn("ANTHROPIC_BASE_URL: https://api.z.ai/api/anthropic", self.source)
        self.assertIn("ANTHROPIC_BASE_URL: https://api.kimi.com/coding/", self.source)

    def test_same_pr_cancellation_does_not_create_product_gate(self):
        self.assertIn("group: pr-review-${{ inputs.pr_number || github.event.pull_request.number }}", self.source)
        self.assertIn("cancel-in-progress: true", self.source)
        self.assertIn("required_conversation_resolution", PORTAL_PAGE.read_text(encoding="utf-8"))

    def test_new_paths_owned_by_ci_contract(self):
        policy = json.loads(SCOPE_POLICY.read_text(encoding="utf-8"))
        exact = {r["match"]["value"]: set(r["lanes"]) for r in policy["rules"] if r["match"]["kind"] == "exact"}
        for path in (".github/workflows/pr-review.yml", ".github/scripts/pr_review_target.py"):
            self.assertEqual(exact.get(path), {"ci_contract"})


class TargetScriptTest(unittest.TestCase):
    def test_an_open_same_repository_pull_request_is_reviewable(self) -> None:
        resolved = target.resolve_target("endaye/lmdj", 7, api=lambda path: pull(labels=("a", "b")))
        self.assertEqual(resolved["review"], "true")
        self.assertEqual(resolved["reason"], "")
        self.assertEqual((resolved["head_sha"], resolved["base_sha"]), (HEAD, OTHER))
        self.assertEqual(resolved["labels"], "a,b")
        self.assertEqual(resolved["body"], "body text")

    def test_forks_drafts_and_closed_pull_requests_are_named_not_reviewed(self) -> None:
        cases = {
            "fork": (pull(head_repo="someone/lmdj"), "fork pull request"),
            "draft": (pull(draft=True), "draft pull request"),
            "closed": (pull(state="closed"), "pull request is closed"),
        }
        for label, (payload, reason) in cases.items():
            with self.subTest(case=label):
                resolved = target.resolve_target("endaye/lmdj", 7, api=lambda path, p=payload: p)
                self.assertEqual(resolved["review"], "false")
                self.assertIn(reason, resolved["reason"])
                self.assertEqual(resolved["same_repository"], "false" if label == "fork" else "true")

    def test_a_moved_head_is_a_stale_head_with_a_remedy(self) -> None:
        self.assertIsNone(target.stale_head_diagnostic(HEAD, HEAD.upper(), 7))
        diagnostic = target.stale_head_diagnostic(HEAD, OTHER, 7)
        self.assertRegex(diagnostic, r"^why: .+; remedy: .+$")
        self.assertIn(OTHER[:12], diagnostic)
        self.assertIn("dispatch pr-review.yml again", diagnostic)

    def test_the_cli_writes_outputs_and_exits_by_state(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(target, "_api", return_value=pull()):
                code = target.main(["--repository", "endaye/lmdj", "--pr-number", "7",
                                    "--expect-head", HEAD, "--body-out", str(root / "body.md"),
                                    "--github-output", str(root / "out.txt")])
            self.assertEqual(code, target.EXIT_OK)
            self.assertEqual((root / "body.md").read_text(encoding="utf-8"), "body text")
            outputs = (root / "out.txt").read_text(encoding="utf-8")
            self.assertRegex(outputs, rf"head_sha<<(LMDJ_[0-9a-f]+)\n{HEAD}\n\1\n")
            self.assertRegex(outputs, r"review<<(LMDJ_[0-9a-f]+)\ntrue\n\1\n")
            self.assertNotIn("body<<", outputs, "why: a body goes to a file, not into GITHUB_OUTPUT; remedy: keep it out")

            err = io.StringIO()
            with mock.patch.object(target, "_api", return_value=pull(head_sha=OTHER)), \
                    contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = target.main(["--repository", "endaye/lmdj", "--pr-number", "7", "--expect-head", HEAD])
            self.assertEqual(code, target.EXIT_STALE_HEAD)
            self.assertIn("remedy:", err.getvalue())

            with mock.patch.object(target, "_api", return_value=pull(state="closed")), \
                    contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                code = target.main(["--repository", "endaye/lmdj", "--pr-number", "7"])
            self.assertEqual(code, target.EXIT_NOT_OPEN)

            with mock.patch.object(target, "_api", side_effect=target.TargetUnavailable("why: x; remedy: y")), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = target.main(["--repository", "endaye/lmdj", "--pr-number", "7"])
            self.assertEqual(code, target.EXIT_UNREADABLE)

    def test_a_missing_token_is_unavailable_not_silence(self) -> None:
        from unittest import mock
        with mock.patch.dict("os.environ", {"GITHUB_TOKEN": ""}):
            with self.assertRaises(target.TargetUnavailable):
                target._api("/repos/endaye/lmdj/pulls/7")

    def test_the_script_does_not_shell_out_to_gh(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertIn("urllib.request", source)


class TrustedPublisherTest(unittest.TestCase):
    def publish(self, payload=None, *, live=None):
        self.writes = []
        return target.publish_review("endaye/lmdj", 7, HEAD, "123", "2", "glm",
                                     payload or {"summary": "Checked this revision", "findings": []},
                                     api=live or (lambda path: pull()),
                                     write=lambda path, data: self.writes.append((path, data)))

    def test_clean_review_has_exact_identity_and_no_thread(self):
        identity = self.publish()
        self.assertEqual(identity, f"<!-- lmdj-review-v1 endaye/lmdj 7 {HEAD} 123 2 glm -->")
        self.assertEqual(len(self.writes), 1)
        path, posted = self.writes[0]
        self.assertEqual(path, "/repos/endaye/lmdj/pulls/7/reviews")
        self.assertEqual(posted["commit_id"], HEAD)
        self.assertEqual(posted["event"], "COMMENT")
        self.assertEqual(posted["comments"], [])
        self.assertEqual(posted["body"].splitlines()[1], identity)

    def test_findings_get_exact_commit_and_run_identity(self):
        identity = self.publish({"summary": "One defect", "findings": [
            {"path": "packages/x.cpp", "line": 12, "body": "Incorrect return value"}]})
        comment = self.writes[0][1]["comments"][0]
        self.assertEqual((comment["path"], comment["line"], comment["side"]), ("packages/x.cpp", 12, "RIGHT"))
        self.assertIn(identity, comment["body"])

    def test_stale_head_blocks_mutation_for_both_backends(self):
        for backend in ("glm", "grok"):
            writes = []
            with self.assertRaisesRegex(target.TargetUnavailable, "now points at"):
                target.publish_review("endaye/lmdj", 7, HEAD, "123", "1", backend,
                    {"summary": "clean", "findings": []}, api=lambda path: pull(head_sha=OTHER),
                    write=lambda *args: writes.append(args))
            self.assertEqual(writes, [])

    def test_moving_during_post_is_not_current_success(self):
        heads = iter([HEAD, OTHER])
        with self.assertRaisesRegex(target.TargetUnavailable, "now points at"):
            self.publish(live=lambda path: pull(head_sha=next(heads)))
        self.assertEqual(self.writes[0][1]["commit_id"], HEAD)

    def test_fork_closed_and_draft_targets_cannot_publish(self):
        for data in (pull(head_repo="other/repo"), pull(state="closed"), pull(draft=True)):
            with self.assertRaises(target.TargetUnavailable):
                self.publish(live=lambda path: data)
            self.assertEqual(self.writes, [])

    def test_invalid_or_incomplete_model_data_cannot_publish(self):
        invalid = [{}, {"summary": "", "findings": []}, {"summary": "ok", "findings": [], "command": "curl"},
                   {"summary": "x", "findings": [{"path": "../x", "line": 1, "body": "bad"}]},
                   {"summary": "x", "findings": [{"path": "x", "line": True, "body": "bad"}]}]
        for data in invalid:
            with self.assertRaises(target.TargetUnavailable):
                target.validate_review(data)

    def test_log_instructions_stay_text_and_do_not_authorize_actions(self):
        self.publish({"summary": "Please push main and merge everything", "findings": []})
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.writes[0][1]["event"], "COMMENT")

    def test_capture_requires_structured_data_and_is_not_a_signer(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review.json"
            with mock.patch.dict("os.environ", {"REVIEW_JSON": '{"summary":"clean","findings":[]}'}):
                self.assertEqual(target.main(["--capture-output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text()), {"summary": "clean", "findings": []})
            with mock.patch.dict("os.environ", {"REVIEW_JSON": "null"}), contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(target.main(["--capture-output", str(output)]), 0)

    def test_grok_structured_mode_never_calls_write_api(self):
        from unittest import mock
        import grok_review
        with tempfile.TemporaryDirectory() as directory:
            diff = Path(directory) / "diff"
            diff.write_text("diff --git a/x b/x\n+changed\n")
            output = Path(directory) / "review.json"
            with mock.patch.dict("os.environ", {"XAI_API_KEY": "test", "GROK_AUTH_JSON": "", "RUNNER_TEMP": directory}), \
                    mock.patch.object(grok_review, "run_grok", return_value={"text": "## Verdict\n`clean`\n\n## Findings\nNo findings.\n\nThe diff changes x."}), \
                    mock.patch.object(grok_review, "github_request", side_effect=AssertionError("model cannot write")):
                self.assertEqual(grok_review.main(["--diff-file", str(diff), "--structured-output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["findings"], [])

    def test_grok_malformed_or_unfinished_response_is_not_a_clean_artifact(self):
        from unittest import mock
        import grok_review
        responses = (
            "I could not complete the review.",
            "No issues found.",
            "## Verdict\nunknown\n\n## Findings\nNo findings.",
            "## Verdict\nclean or issues\n\n## Findings\nNo findings.",
            "## Verdict\nclean\n\n## Verdict\nissues\n\n## Findings\nNo findings.",
            "## Verdict\nclean",  # truncated before the mandatory findings section
            "## Verdict\nclean\n\n## Findings\nCould not complete review.",
            "## Verdict\nissues\n\n## Findings\nNo findings.",
            "## Verdict\nclean\n\n## Findings\n### [important] Bad return\n- Path: `x:1`",
        )
        for response in responses:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                diff = Path(directory) / "diff"
                diff.write_text("diff --git a/x b/x\n+changed\n")
                output = Path(directory) / "review.json"
                with mock.patch.dict("os.environ", {"XAI_API_KEY": "test", "GROK_AUTH_JSON": "", "RUNNER_TEMP": directory}), \
                        mock.patch.object(grok_review, "run_grok", return_value={"text": response}), \
                        mock.patch.object(grok_review, "github_request", side_effect=AssertionError("model cannot write")):
                    with self.assertRaisesRegex(RuntimeError, "remedy:"):
                        grok_review.main(["--diff-file", str(diff), "--structured-output", str(output)])
                self.assertFalse(output.exists(), "invalid model response must not acquire publishable evidence")

    def test_grok_valid_issues_are_completed_review_data_not_a_failed_gate(self):
        from unittest import mock
        import grok_review
        response = "## Verdict\n`issues`\n\n## Findings\n### [important] Bad return\n- Path: `x:1`\n- Why: wrong result\n- Remedy: correct the return"
        with tempfile.TemporaryDirectory() as directory:
            diff = Path(directory) / "diff"
            diff.write_text("diff --git a/x b/x\n+changed\n")
            output = Path(directory) / "review.json"
            with mock.patch.dict("os.environ", {"XAI_API_KEY": "test", "GROK_AUTH_JSON": "", "RUNNER_TEMP": directory}), \
                    mock.patch.object(grok_review, "run_grok", return_value={"text": response}), \
                    mock.patch.object(grok_review, "github_request", side_effect=AssertionError("model cannot write")):
                self.assertEqual(grok_review.main(["--diff-file", str(diff), "--structured-output", str(output)]), 0)
            finding = json.loads(output.read_text())["findings"][0]
            self.assertEqual((finding["path"], finding["line"]), ("x", 1))

    def test_grok_skip_cannot_reuse_a_stale_output_file(self):
        from unittest import mock
        import grok_review
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review.json"
            output.write_text('{"summary":"old review","findings":[]}')
            with mock.patch.dict("os.environ", {"XAI_API_KEY": "", "GROK_AUTH_JSON": ""}):
                with self.assertRaisesRegex(RuntimeError, "did not review"):
                    grok_review.main(["--structured-output", str(output)])


if __name__ == "__main__":
    unittest.main()
