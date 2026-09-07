#!/usr/bin/env python3
"""Claude runtime safety in the independent PR Review entry.

Retired Core CI assertions become active boundary checks: read-only models,
trusted checkout, pinned runtime and separate publisher. Vendored command
provenance/content checks remain although product CI no longer runs it.
"""
from pathlib import Path
import re
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/pr-review.yml"
CORE = REPO_ROOT / ".github/workflows/ci.yml"
VENDORED_COMMAND = REPO_ROOT / ".claude/commands/pr-review.md"


def job_block(source, name):
    return re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-zA-Z][\w-]*:\n|\Z)", source).group(1)


class ClaudeReviewWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.source = WORKFLOW.read_text(encoding="utf-8")
        self.model = job_block(self.source, "review")
        self.directives = "\n".join(line for line in self.model.splitlines()
                                    if not line.lstrip().startswith("#"))

    def test_core_ci_no_longer_executes_a_claude_model(self):
        directives = "\n".join(line for line in CORE.read_text().splitlines()
                               if not line.lstrip().startswith("#"))
        self.assertNotIn("anthropics/claude-code-action@", directives,
                         "why: product tests still invoke advisory AI; remedy: use only pr-review.yml")

    def test_models_run_on_the_general_self_hosted_role(self):
        self.assertIn("runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general]", self.model,
                      "why: review moved off its reviewed runner role; remedy: retain ci-general")

    def test_model_tokens_are_read_only(self):
        header = self.model.split("    steps:", 1)[0]
        self.assertIn("contents: read", header)
        self.assertIn("pull-requests: read", header)
        self.assertNotRegex(header, r"(?m)^\s+[a-z-]+: write$",
                            "why: model holds a repository mutation token; remedy: keep writes in the trusted publisher")

    def test_model_checkout_is_trusted_control_not_pr_head(self):
        self.assertIn("github.event.pull_request.base.sha || github.sha", self.model)
        self.assertIn("persist-credentials: false", self.model)
        self.assertNotIn("ref: ${{ needs.target.outputs.head_sha }}", self.directives,
                         "why: untrusted PR code would execute beside credentials; remedy: check out trusted control")

    def test_github_token_is_explicit_not_the_claude_app(self):
        self.assertIn("github_token: ${{ secrets.GITHUB_TOKEN }}", self.model,
                      "why: implicit Claude App auth changes the credential boundary; remedy: pass the repository token explicitly")

    def test_every_claude_action_is_pinned_to_exact_commit(self):
        pins = re.findall(r"uses: anthropics/claude-code-action@(\S+)", self.model)
        self.assertTrue(pins, "why: model runtime pin is absent; remedy: retain the reviewed Claude action")
        for pin in pins:
            self.assertRegex(pin, r"^[0-9a-f]{40}$",
                             "why: moving action ref is not reviewed code; remedy: pin an exact commit")

    def test_substituted_backend_does_not_use_anthropic_credentials(self):
        self.assertIn("ANTHROPIC_BASE_URL", self.model)
        self.assertIn("ANTHROPIC_AUTH_TOKEN", self.model)
        for forbidden in ("CLAUDE_CODE_OAUTH_TOKEN", "claude_code_oauth_token", "ANTHROPIC_API_KEY:"):
            self.assertNotIn(forbidden, self.directives,
                             "why: substitution must not consume unrelated Anthropic credentials; remedy: use configured GLM/Kimi credentials")

    def test_model_has_only_read_tools(self):
        self.assertIn('--tools "Read" --allowedTools "Read" --disable-slash-commands', self.model,
                      "why: model may execute commands or post its own review; remedy: retain read-only tools")
        self.assertNotIn("mcp__github_inline_comment__create_inline_comment", self.directives)

    def test_no_runtime_plugin_marketplace_clone(self):
        self.assertNotIn("plugin_marketplaces", self.directives)
        self.assertNotIn("plugins:", self.directives,
                         "why: review gains an unpinned runtime plugin dependency; remedy: use the trusted structured prompt")

    def test_independent_target_refuses_forks_and_drafts(self):
        target = (REPO_ROOT / ".github/scripts/pr_review_target.py").read_text()
        self.assertIn("draft", target)
        self.assertIn("fork", target)
        self.assertIn("needs.target.outputs.review == 'true'", self.model,
                      "why: model bypasses the trusted target admission; remedy: require its review decision")

    def test_model_failure_is_not_hidden_by_job_level_continue_on_error(self):
        header = self.model.split("    steps:", 1)[0]
        self.assertNotIn("continue-on-error: true", header,
                         "why: unavailable review would look successful; remedy: publish honest completion or failure")
        # Per-backend step continuation is legitimate only for bounded fallback.

    def test_vendored_command_keeps_provenance(self):
        body = VENDORED_COMMAND.read_text()
        self.assertTrue(body.startswith("---\n"))
        for marker in ("VENDORED", "Blob:", "Repo HEAD at retrieval:", "Retrieved:"):
            self.assertIn(marker, body,
                          "why: vendored procedure cannot be audited; remedy: retain its retrieval provenance")

    def test_vendored_clean_review_rule_is_not_deleted_with_old_job(self):
        body = VENDORED_COMMAND.read_text()
        self.assertIn("Never post a clean review as a review comment or review thread.", body)
        self.assertIn("/repos/{owner}/{repo}/issues/{number}/comments", body)
        allowed = body.split("---", 2)[1]
        self.assertIn("Bash(curl:*)", allowed)
        self.assertIn("Bash(gh pr diff:*)", allowed)


if __name__ == "__main__":
    unittest.main()
