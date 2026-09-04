#!/usr/bin/env python3
"""Contract tests for the advisory Grok pull-request review workflow."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/grok-review.yml"
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
        cls.script = load_script()
        cls.policy = json.loads(SCOPE_POLICY.read_text(encoding="utf-8"))

    def test_workflow_is_advisory_pull_request_only(self) -> None:
        prefix = self.source.split("jobs:", 1)[0]
        message = (
            "why: Grok review must stay off Core CI and the merge queue; "
            "remedy: trigger only pull_request on main and keep contents: read, "
            "issues: write, and pull-requests: write"
        )
        self.assertIn("pull_request:", prefix, message)
        self.assertNotIn("pull_request_target:", self.source, message)
        self.assertNotIn("push:", prefix, message)
        self.assertNotIn("merge_group:", prefix, message)
        self.assertIn(
            "permissions:\n  contents: read\n  issues: write\n  pull-requests: write",
            prefix,
            message,
        )
        self.assertNotIn("contents: write", self.source, message)
        self.assertNotIn("id-token: write", self.source, message)

    def test_workflow_skips_drafts_and_forks(self) -> None:
        message = (
            "why: fork heads must not receive repository Grok credentials, and "
            "drafts should not spend SuperGrok quota; remedy: keep the draft "
            "and same-repository job guard"
        )
        self.assertIn("github.event.pull_request.draft == false", self.source, message)
        self.assertIn(
            "github.event.pull_request.head.repo.full_name == github.repository",
            self.source,
            message,
        )

    def test_workflow_runs_on_the_general_self_hosted_role(self) -> None:
        message = (
            "why: a GitHub-hosted Grok review job is not in "
            "hosted_runner_policy.json and does not earn a hosted category; "
            "remedy: keep runs-on on the dual-node ci-general role, not "
            "ubuntu-24.04 or ci-core"
        )
        self.assertIn(
            "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general]",
            self.source,
            message,
        )
        self.assertNotIn("runs-on: ubuntu-24.04", self.source, message)
        self.assertNotIn("ci-core", self.source, message)
        self.assertNotIn("ci-web-heavy", self.source, message)

    def test_an_advisory_lane_does_not_paint_the_pull_request_red(self) -> None:
        """Advisory in name has to mean advisory in effect.

        This lane failed red on #610 with `max turns reached` -- a review that
        did not finish, not a change that is wrong. A lane that cannot block a
        merge but can redden every Pull Request devalues every other red check.
        """
        self.assertIn(
            "continue-on-error: true",
            self.source,
            msg=(
                "why: this lane cannot block a merge, so a failure here is a "
                "missing review rather than a defect, and a red check for it "
                "devalues every other red check; remedy: keep continue-on-error "
                "on the review step"
            ),
        )

    def test_the_cli_is_fetched_by_digest_not_piped_from_an_installer(self) -> None:
        """A version names a release; a digest names the bytes.

        The upstream installer publishes no checksum and verifies nothing but
        an HTTP status and a `--version` string, so a changed script would be
        executed unchallenged. This job holds `pull-requests: write` and a
        `GITHUB_TOKEN`, and since it moved to a self-hosted runner it executes
        on our own machine, which raises the cost of that rather than lowering
        it. The CI contract lane already answers the same question the same
        way, with a checksum-verified actionlint release.
        """
        message = (
            "why: the Grok CLI is installed on a self-hosted runner in a job "
            "holding pull-requests: write, so its bytes must be named by a "
            "digest rather than only by a version; remedy: fetch "
            "https://x.ai/cli/grok-${GROK_VERSION}-linux-x86_64 directly and "
            "verify it against GROK_SHA256, the way the CI contract lane pins "
            "actionlint"
        )
        self.assertNotIn("install.sh", self.source, message)
        self.assertNotIn("| bash", self.source, message)
        self.assertRegex(self.source, r'GROK_SHA256: "[0-9a-f]{64}"', message)
        self.assertIn(
            'https://x.ai/cli/grok-${GROK_VERSION}-linux-x86_64', self.source, message
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
        self.assertIn("python3 .github/scripts/grok_review.py", self.source, message)
        command = self.script.grok_command(Path("/tmp/prompt.md"), Path("/tmp/repo"))
        self.assertEqual(command[command.index("--tools") + 1], self.script.READ_ONLY_TOOLS)
        self.assertNotIn("--sandbox", command, message)
        self.assertIn("--disable-web-search", command)
        self.assertIn("--no-subagents", command)
        self.assertIn("Read(**/.grok/**)", command)
        self.assertIn("Read(**/auth.json)", command)

    def test_core_ci_and_merge_queue_do_not_reference_grok_review(self) -> None:
        core = CORE_CI.read_text(encoding="utf-8")
        queue = MERGE_QUEUE.read_text(encoding="utf-8")
        message = (
            "why: Grok review is not merge evidence; remedy: do not add it to "
            "ci.yml, PR Gate, or the merge-queue control-plane path list"
        )
        self.assertNotIn("grok-review", core, message)
        self.assertNotIn("grok_review", core, message)
        self.assertNotIn("grok-review.yml", queue, message)
        self.assertNotIn(".github/scripts/grok_review.py", queue, message)

    def test_scope_policy_classifies_review_files_as_ci_contract_only(self) -> None:
        paths = {
            ".github/workflows/grok-review.yml",
            ".github/scripts/grok_review.py",
        }
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
        self.assertIn("does not block merge", comment)
        self.assertIn("tokens: 12", comment)
        self.assertIn("models: grok-4.6", comment)

    def test_actionable_findings_open_an_issue_and_nits_do_not(self) -> None:
        sample = (
            "## Verdict\n`issues`\n\n## Findings\n"
            "### [critical] Grok can read job credentials\n"
            "- Path: `.github/workflows/grok-review.yml:33`\n"
            "### [important] Sticky comment publishes stdout\n"
            "- Why: the child process inherits the environment\n"
            "### [nit] Prefer a shorter heading\n"
            "- Why: style\n"
        )
        findings = self.script.parse_findings(sample)
        self.assertEqual(
            [item["severity"] for item in findings],
            ["critical", "important", "nit"],
        )
        self.assertEqual(self.script.parse_verdict(sample), "issues")
        self.assertTrue(
            self.script.should_open_issue(verdict="issues", findings=findings)
        )
        self.assertFalse(
            self.script.should_open_issue(
                verdict="issues",
                findings=[item for item in findings if item["severity"] == "nit"],
            )
        )
        self.assertFalse(
            self.script.should_open_issue(verdict="clean", findings=[])
        )
        self.assertTrue(
            self.script.should_open_issue(verdict="issues", findings=[])
        )
        self.assertEqual(self.script.issue_priority(findings), "priority:p1")
        body = self.script.format_issue_body(
            pr_number=12,
            pr_url="https://github.com/endaye/lmdj/pull/12",
            text=sample,
            findings=findings,
        )
        self.assertIn("lmdj-grok-review-pr-12", body)
        self.assertIn("https://github.com/endaye/lmdj/pull/12", body)
        self.assertIn("[critical] Grok can read job credentials", body)
        self.assertNotIn("Prefer a shorter heading", body)
        self.assertIsNone(self.script.CLOSING_KEYWORD.search(body))

    def test_upsert_tracking_issue_creates_updates_and_closes(self) -> None:
        calls = []

        def requester(method, url, token, payload=None):
            calls.append((method, url, payload))
            if method == "GET":
                return {"items": []}
            if method == "POST" and url.endswith("/issues"):
                return {"number": 77}
            return {"number": 77}

        action = self.script.upsert_tracking_issue(
            repository="endaye/lmdj",
            pr_number=12,
            pr_url="https://github.com/endaye/lmdj/pull/12",
            token="token",
            text="## Verdict\nissues\n\n### [important] Missing test\n- Why: no coverage\n",
            findings=[{
                "severity": "important",
                "title": "Missing test",
                "body": "- Why: no coverage",
            }],
            verdict="issues",
            requester=requester,
        )
        self.assertEqual(action, "created #77")
        self.assertEqual(calls[1][0], "POST")
        self.assertEqual(
            calls[1][2]["labels"],
            ["type:bug", "area:ci-release", "priority:p2"],
        )

        calls.clear()

        def updater(method, url, token, payload=None):
            calls.append((method, url, payload))
            if method == "GET":
                return {"items": [{"number": 77, "state": "open"}]}
            return {"number": 77}

        updated = self.script.upsert_tracking_issue(
            repository="endaye/lmdj",
            pr_number=12,
            pr_url="https://github.com/endaye/lmdj/pull/12",
            token="token",
            text="## Verdict\nissues\n\n### [critical] Leak\n- Why: token\n",
            findings=[{
                "severity": "critical",
                "title": "Leak",
                "body": "- Why: token",
            }],
            verdict="issues",
            requester=updater,
        )
        self.assertEqual(updated, "updated #77")
        self.assertEqual(calls[1][0], "PATCH")
        self.assertEqual(calls[1][2]["state"], "open")

        calls.clear()

        def closer(method, url, token, payload=None):
            calls.append((method, url, payload))
            if method == "GET":
                return {"items": [{"number": 77, "state": "open"}]}
            return {"number": 77}

        closed = self.script.upsert_tracking_issue(
            repository="endaye/lmdj",
            pr_number=12,
            pr_url="https://github.com/endaye/lmdj/pull/12",
            token="token",
            text="## Verdict\nclean\n\n## Findings\nNo findings.\n",
            findings=[],
            verdict="clean",
            requester=closer,
        )
        self.assertEqual(closed, "closed #77")
        self.assertEqual(calls[1][0], "POST")
        self.assertIn("/issues/77/comments", calls[1][1])
        self.assertEqual(calls[2][2]["state"], "closed")
        self.assertIsNone(self.script.CLOSING_KEYWORD.search(calls[1][2]["body"]))

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
