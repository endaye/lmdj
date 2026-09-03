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
            "remedy: trigger only pull_request on main and keep contents: read "
            "plus pull-requests: write"
        )
        self.assertIn("pull_request:", prefix, message)
        self.assertNotIn("pull_request_target:", self.source, message)
        self.assertNotIn("push:", prefix, message)
        self.assertNotIn("merge_group:", prefix, message)
        self.assertIn("permissions:\n  contents: read\n  pull-requests: write", prefix, message)
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

    def test_workflow_runs_hosted_ubuntu_not_self_hosted(self) -> None:
        message = (
            "why: advisory Grok review must not consume trusted self-hosted "
            "roles; remedy: keep runs-on: ubuntu-24.04"
        )
        self.assertIn("runs-on: ubuntu-24.04", self.source, message)
        self.assertNotIn("self-hosted", self.source, message)
        self.assertNotIn("ci-core", self.source, message)
        self.assertNotIn("ci-general", self.source, message)

    def test_workflow_pins_grok_cli_and_read_only_tools(self) -> None:
        message = (
            "why: CI must not float the Grok CLI or grant write/shell tools; "
            "remedy: pin GROK_VERSION to the script constant and keep the "
            "read-only tool allowlist without --sandbox, because GitHub-hosted "
            "Ubuntu cannot resolve Grok's runtime-socket deny path"
        )
        self.assertIn(f'GROK_VERSION: "{self.script.PINNED_GROK_VERSION}"', self.source, message)
        self.assertIn("bash -s \"$GROK_VERSION\"", self.source, message)
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
