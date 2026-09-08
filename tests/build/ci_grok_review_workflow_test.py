#!/usr/bin/env python3
"""Contract tests for the advisory Grok pull-request review workflow."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
# Runtime workflow checks follow the independent review entry. Script behavior
# tests below remain unchanged when the retired Core CI copy is removed.
WORKFLOW = REPO_ROOT / ".github/workflows/pr-review.yml"
SCRIPT = REPO_ROOT / ".github/scripts/grok_review.py"
MERGE_QUEUE = REPO_ROOT / "scripts/ci/merge_queue.py"
SCOPE_POLICY = REPO_ROOT / "scripts/ci/scope_policy.json"
CORE_CI = REPO_ROOT / ".github/workflows/ci.yml"


def load_script():
    spec = importlib.util.spec_from_file_location("grok_review", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load grok_review.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GrokReviewWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.job = re.search(r"(?ms)^  review:\n(.*?)(?=^  [a-zA-Z][\w-]*:\n|\Z)", cls.source).group(1)
        cls.script = load_script()
        cls.policy = json.loads(SCOPE_POLICY.read_text(encoding="utf-8"))

    def test_the_job_is_read_only_in_the_independent_review_entry(self) -> None:
        header = self.job.split("    steps:", 1)[0]
        self.assertIn("contents: read", header)
        self.assertIn("pull-requests: read", header)
        self.assertNotIn(": write", header,
                         "why: a model holds mutation authority; remedy: keep it only in the independent publisher")
        self.assertNotIn("pull_request_target:", self.source)
        self.assertIn("needs.target.outputs.review == 'true'", self.job)

    def test_the_job_has_no_product_ci_dependency(self) -> None:
        core = CORE_CI.read_text()
        self.assertNotIn("\n  grok-review:\n", core,
                         "why: Core CI still executes advisory review; remedy: use pr-review.yml only")
        self.assertNotIn("pre-heavy-gate", self.job,
                         "why: review depends on product admission; remedy: keep independent DAGs")

    def test_workflow_skips_drafts_and_forks(self) -> None:
        target = (REPO_ROOT / ".github/scripts/pr_review_target.py").read_text()
        self.assertIn("draft", target)
        self.assertIn("fork", target)
        self.assertIn("needs.target.outputs.review == 'true'", self.job,
                      "why: model bypasses trusted PR admission; remedy: honor target's review output")

    def test_workflow_runs_on_the_general_self_hosted_role(self) -> None:
        message = (
            "why: a GitHub-hosted Grok review job is not in "
            "hosted_runner_policy.json and does not earn a hosted category; "
            "remedy: keep runs-on on the dual-node ci-general role, not "
            "ubuntu-24.04 or ci-core"
        )
        self.assertIn(
            "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general]",
            self.job,
            message,
        )
        # Job-scoped: the separate publisher may use a different runner.
        self.assertNotIn("runs-on: ubuntu-24.04", self.job, message)
        self.assertNotIn("ci-core", self.job, message)
        self.assertNotIn("ci-web-heavy", self.job, message)

    def test_model_failure_is_not_hidden_by_job_level_continue_on_error(self) -> None:
        header = self.job.split("    steps:", 1)[0]
        self.assertNotIn("continue-on-error: true", header,
                         "why: unavailable review would be presented as complete; remedy: report honest review state")

    def test_the_cli_is_fetched_by_digest_not_piped_from_an_installer(self) -> None:
        """A version names a release; a digest names the bytes.

        The upstream installer publishes no checksum and verifies nothing but
        an HTTP status and a `--version` string, so a changed script would be
        executed unchallenged. This job holds `pull-requests: read` and a
        `GITHUB_TOKEN`, and since it moved to a self-hosted runner it executes
        on our own machine, which raises the cost of that rather than lowering
        it. The CI contract lane already answers the same question the same
        way, with a checksum-verified actionlint release.
        """
        message = (
            "why: the Grok CLI is installed on a self-hosted runner in a job "
            "holding backend credentials, so its bytes must be named by a "
            "digest rather than only by a version; remedy: fetch "
            "https://x.ai/cli/grok-${GROK_VERSION}-linux-x86_64 directly and "
            "verify it against GROK_SHA256, the way the CI contract lane pins "
            "actionlint"
        )
        self.assertNotIn("install.sh", self.source, message)
        self.assertNotIn("| bash", self.source, message)
        self.assertRegex(self.source, r'GROK_SHA256: "[0-9a-f]{64}"', message)
        self.assertIn(
            'https://x.ai/cli/grok-$GROK_VERSION-linux-x86_64', self.source, message
        )
        self.assertIn("sha256sum --check --strict -", self.source, message)

    def test_workflow_pins_grok_cli_and_read_only_tools(self) -> None:
        message = (
            "why: CI must not float the Grok CLI or grant write/shell tools; "
            "remedy: pin GROK_VERSION to the script constant and keep the "
            "read-only tool allowlist without --sandbox, because GitHub-hosted "
            "Ubuntu cannot resolve Grok's runtime-socket deny path"
        )
        self.assertIn(f'GROK_VERSION: "{self.script.PINNED_GROK_VERSION}"', self.source, message)
        adapter = REPO_ROOT / "scripts/ci/review_pipeline.py"
        self.assertIn("review_pipeline.py grok", self.source, message)
        self.assertIn("grok_review.grok_command", adapter.read_text(), message)
        command = self.script.grok_command(Path("/tmp/prompt.md"), Path("/tmp/repo"))
        self.assertEqual(command[command.index("--model") + 1], self.script.PINNED_GROK_MODEL)
        self.assertEqual(command[command.index("--effort") + 1], "medium")
        self.assertEqual(command[command.index("--tools") + 1], self.script.READ_ONLY_TOOLS)
        self.assertNotIn("--sandbox", command, message)
        self.assertIn("--disable-web-search", command)
        self.assertIn("--no-subagents", command)
        self.assertIn("Read(**/.grok/**)", command)
        self.assertIn("Read(**/auth.json)", command)

    def test_grok_stays_outside_product_and_merge_evidence(self) -> None:
        core = CORE_CI.read_text(encoding="utf-8")
        queue = MERGE_QUEUE.read_text(encoding="utf-8")
        self.assertNotIn("\n  grok-review:\n", core,
                         "why: retired model job keeps product write permissions; remedy: use the independent PR Review entry")
        self.assertNotIn("grok", str(self.policy["lane_jobs"]))
        self.assertNotIn("grok-review", self.policy["self_hosted_jobs"])
        self.assertNotIn("\n  pr-gate:\n", core)
        self.assertNotIn("grok-review", core)
        self.assertNotIn("grok-review.yml", queue)
        self.assertNotIn(".github/scripts/grok_review.py", queue)

    def test_scope_policy_classifies_review_files_as_ci_contract_only(self) -> None:
        paths = {".github/scripts/grok_review.py"}
        matched = {
            rule["match"]["value"]: set(rule["lanes"])
            for rule in self.policy["rules"]
            if rule["match"]["kind"] == "exact" and rule["match"]["value"] in paths
        }
        message = (
            "why: an unclassified Grok review path upgrades the PR to full CI; "
            "remedy: add exact ci_contract rules for the workflow and script"
        )
        self.assertEqual(set(matched), paths, message)
        for path, lanes in matched.items():
            self.assertEqual(lanes, {"ci_contract"}, f"{path}: {lanes}")
        full_values = {
            rule["match"]["value"]
            for rule in self.policy["full_rules"]
            if rule["match"]["kind"] in {"exact", "prefix"}
        }
        self.assertNotIn(".github/workflows/grok-review.yml", full_values, message)

    def test_skip_reason_covers_credential_and_diff_guards(self) -> None:
        skip = self.script.skip_reason
        diff = b"diff --git a/x b/x\n"
        self.assertEqual(
            skip(
                draft=True, labels=[], auth_json="{}", api_key="",
                diff=diff, same_repository=True,
            ),
            "draft pull request",
        )
        self.assertEqual(
            skip(
                draft=False, labels=[], auth_json="{}", api_key="",
                diff=diff, same_repository=False,
            ),
            "fork pull request; repository secrets are not used on forks",
        )
        self.assertEqual(
            skip(
                draft=False, labels=["skip-grok-review"], auth_json="{}",
                api_key="", diff=diff, same_repository=True,
            ),
            "skip-grok-review label",
        )
        self.assertEqual(
            skip(
                draft=False, labels=[], auth_json="", api_key="",
                diff=diff, same_repository=True,
            ),
            "no GROK_AUTH_JSON or XAI_API_KEY secret",
        )
        self.assertEqual(
            skip(
                draft=False, labels=[], auth_json="{}", api_key="",
                diff=b"   ", same_repository=True,
            ),
            "empty diff",
        )
        oversized = b"a" * (self.script.MAX_DIFF_BYTES + 1)
        self.assertEqual(
            skip(
                draft=False, labels=[], auth_json="{}", api_key="",
                diff=oversized, same_repository=True,
            ),
            f"diff exceeds {self.script.MAX_DIFF_BYTES} bytes",
        )
        self.assertIsNone(
            skip(
                draft=False, labels=[], auth_json="{}", api_key="",
                diff=diff, same_repository=True,
            )
        )
        self.assertIsNone(
            skip(
                draft=False, labels=[], auth_json="", api_key="xai-test",
                diff=diff, same_repository=True,
            )
        )

    def test_format_comment_is_sticky_and_advisory(self) -> None:
        comment = self.script.format_comment(
            text="## Verdict\nclean\n",
            grok_payload={"usage": {"total_tokens": 12}, "modelUsage": {"grok-4.6": {}}},
        )
        self.assertIn(self.script.COMMENT_MARKER, comment)
        self.assertIn("advisory", comment.lower())
        self.assertIn("review threads", comment)
        self.assertIn("conversation-resolution", comment)
        self.assertIn("tokens: 12", comment)
        self.assertIn("models: grok-4.6", comment)

    SAMPLE = (
        "## Verdict\n`issues`\n\n## Findings\n"
        "### [critical] Grok can read job credentials\n"
        "- Path: `.github/workflows/grok-review.yml:33`\n"
        "- Why: the child inherits the environment\n"
        "### [important] Range finding\n"
        "- Path: `scripts/ci/change_scope.py:10-14`\n"
        "### [important] No location given\n"
        "- Why: the child process inherits the environment\n"
        "### [nit] Prefer a shorter heading\n"
        "- Why: style\n"
    )

    def test_parse_location_handles_lines_ranges_and_bare_paths(self) -> None:
        parse = self.script.parse_location
        self.assertEqual(parse("- Path: `a/b.py:7`"), ("a/b.py", 7, 7))
        self.assertEqual(parse("- Path: `a/b.py:10-14`"), ("a/b.py", 10, 14))
        self.assertEqual(parse("- Path: `a/b.py`"), ("a/b.py", None, None))
        self.assertIsNone(parse("- Why: no path here"))

    def test_actionable_findings_become_threads_and_nits_do_not(self) -> None:
        """Same severity rule as before; the sink moved from an Issue to threads.

        A thread must be resolved before merge, so a nit is not worth one and
        stays on the summary comment. An Issue per Pull Request was tried
        first: four of them stayed open and unread while the thread-posting
        lanes' findings were acted on the same day.
        """
        findings = self.script.parse_findings(self.SAMPLE)
        self.assertEqual(
            [item["severity"] for item in findings],
            ["critical", "important", "important", "nit"],
        )
        calls = []

        def requester(method, url, token, payload=None):
            calls.append((method, url, payload))
            return {"id": 1}

        action = self.script.post_review(
            repository="endaye/lmdj", pr_number=12, head_sha="abcdef0123456789",
            token="token", findings=findings, verdict="issues", requester=requester,
        )
        self.assertEqual(action, "posted 2 inline, 1 in body")
        self.assertEqual(len(calls), 1)
        method, url, payload = calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/pulls/12/reviews"), url)
        self.assertEqual(payload["event"], "COMMENT",
                         "why: a REQUEST_CHANGES verdict would make the lane a "
                         "reviewer with veto rather than an advisor; remedy: keep "
                         "event COMMENT and let conversation resolution do the holding")
        self.assertEqual(payload["commit_id"], "abcdef0123456789")
        inline = {c["path"]: c for c in payload["comments"]}
        self.assertEqual(set(inline), {".github/workflows/grok-review.yml", "scripts/ci/change_scope.py"})
        self.assertEqual(inline[".github/workflows/grok-review.yml"]["line"], 33)
        ranged = inline["scripts/ci/change_scope.py"]
        self.assertEqual((ranged["start_line"], ranged["line"]), (10, 14))
        for comment in payload["comments"]:
            self.assertIn(self.script.THREAD_MARKER, comment["body"])
            self.assertIn("abcdef012", comment["body"])
        self.assertIn("No location given", payload["body"])
        self.assertNotIn("Prefer a shorter heading", payload["body"],
                         "why: a nit thread would have to be resolved before merge; "
                         "remedy: keep nits on the summary comment only")

    def test_post_review_skips_when_only_nits_and_posts_one_thread_when_unstructured(self) -> None:
        calls = []
        requester = lambda m, u, t, p=None: calls.append((m, u, p)) or {"id": 1}  # noqa: E731
        nits = [{"severity": "nit", "title": "style", "body": "- Why: style"}]
        self.assertTrue(self.script.post_review(
            repository="endaye/lmdj", pr_number=1, head_sha="0" * 40, token="t",
            findings=nits, verdict="issues", requester=requester,
        ).startswith("skipped"))
        self.assertEqual(calls, [])
        action = self.script.post_review(
            repository="endaye/lmdj", pr_number=1, head_sha="0" * 40, token="t",
            findings=[], verdict="issues", requester=requester,
        )
        self.assertEqual(action, "posted 0 inline, 1 in body")
        self.assertIn("without structured", calls[0][2]["body"])

    def test_post_review_folds_inline_comments_into_the_body_on_422(self) -> None:
        """A line the diff does not touch is rejected; the finding is still real."""
        findings = self.script.parse_findings(self.SAMPLE)
        calls = []

        def requester(method, url, token, payload=None):
            calls.append(payload)
            if len(calls) == 1:
                raise RuntimeError("GitHub POST ... failed: 422 line not in diff")
            return {"id": 2}

        action = self.script.post_review(
            repository="endaye/lmdj", pr_number=12, head_sha="f" * 40,
            token="token", findings=findings, verdict="issues", requester=requester,
        )
        self.assertEqual(action, "posted 0 inline, 3 in body after 422")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["comments"], [])
        self.assertIn("`.github/workflows/grok-review.yml:33`", calls[1]["body"])
        self.assertIn("`scripts/ci/change_scope.py:10`", calls[1]["body"])
        self.assertIn("No location given", calls[1]["body"])

    def test_a_non_422_failure_is_not_swallowed(self) -> None:
        def requester(method, url, token, payload=None):
            raise RuntimeError("GitHub POST ... failed: 403 forbidden")
        with self.assertRaises(RuntimeError):
            self.script.post_review(
                repository="endaye/lmdj", pr_number=12, head_sha="f" * 40, token="t",
                findings=self.script.parse_findings(self.SAMPLE), verdict="issues",
                requester=requester,
            )

    def test_the_lane_no_longer_opens_issues(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        directives = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        for symbol in ("upsert_tracking_issue", "format_issue_body", "should_open_issue",
                       "find_tracking_issue", "ISSUE_MARKER", "POST_ISSUE"):
            self.assertNotIn(
                symbol, directives,
                msg=(f"why: the tracking-Issue sink produced findings nobody read, and "
                     f"a surviving {symbol} would be the path back to it; remedy: post "
                     f"findings as review threads through post_review only"),
            )
        self.assertNotIn("POST_ISSUE", self.source)

    def test_upsert_updates_existing_sticky_comment(self) -> None:
        calls = []

        def requester(method, url, token, payload=None):
            calls.append((method, url, token, payload))
            if method == "GET":
                return [{"id": 9, "body": self.script.COMMENT_MARKER + " old"}]
            return {"id": 9}

        action = self.script.upsert_sticky_comment(
            repository="endaye/lmdj",
            pr_number=12,
            token="token",
            body="new-body",
            requester=requester,
        )
        self.assertEqual(action, "updated")
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[1][0], "PATCH")
        self.assertIn("/issues/comments/9", calls[1][1])
        self.assertEqual(calls[1][3], {"body": "new-body"})

    def test_main_skips_without_credentials_and_does_not_call_grok(self) -> None:
        env = {
            "GROK_AUTH_JSON": "",
            "XAI_API_KEY": "",
            "GITHUB_TOKEN": "",
            "PR_SAME_REPOSITORY": "true",
            "PR_DRAFT": "false",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(self.script, "run_grok") as run_grok:
                code = self.script.main([
                    "--diff-file", str(SCRIPT),
                    "--no-post-comment",
                ])
        self.assertEqual(code, 0)
        run_grok.assert_not_called()

    def test_write_auth_json_is_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth.json"
            self.script.write_auth_json('{"token":"x"}', path)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"token":"x"}\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
