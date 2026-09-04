#!/usr/bin/env python3
"""Contract for the advisory Claude review lane on a substituted backend.

Four properties carry this lane, and each would look fine while being wrong:

* it runs self-hosted, or every Pull Request buys at least one billed minute
  and the reason this lane is affordable disappears;
* it passes `github_token` explicitly, or `claude-code-action` falls back to
  authenticating as the Claude GitHub App and attaches an employer-owned Claude
  organisation to a personal repository;
* it excludes fork Pull Requests, because it runs an agent holding repository
  write scope on our own machine;
* it pins the action to a commit, because a moving tag names a release rather
  than the code that will run.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/claude-review.yml"
GROK = REPO_ROOT / ".github/workflows/grok-review.yml"
VENDORED_COMMAND = REPO_ROOT / ".claude/commands/pr-review.md"
SELF_HOSTED_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general]"
)
BACKENDS = {
    "glm": ("https://api.z.ai/api/anthropic", "ZAI_CODING_KEY"),
    "kimi": ("https://api.kimi.com/coding/", "KIMI_CODING_KEY"),
}


class ClaudeReviewWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = WORKFLOW.read_text(encoding="utf-8")
        # Absence assertions read the directives only. A rationale comment is
        # free to name what the lane is *not* -- and this scan matching its own
        # explanation is a recurring way to write a gate that is wrong about
        # itself. See `.agents/pitfalls/gate-matches-its-own-prose.md`.
        self.directives = "\n".join(
            line for line in self.source.splitlines()
            if not line.lstrip().startswith("#")
        )

    def test_the_lane_is_advisory_and_not_a_formal_result(self) -> None:
        self.assertNotIn("PR Gate", self.directives)
        self.assertNotIn("pr_gate.py", self.directives)
        self.assertNotIn("merge:queue", self.directives)
        self.assertIn("permissions:\n  contents: read\n  pull-requests: write", self.source)

    def test_the_lane_runs_self_hosted(self) -> None:
        self.assertIn(
            SELF_HOSTED_ROLE,
            self.source,
            msg=(
                "why: a hosted runner bills at least one whole minute per Pull "
                "Request, which is the entire cost argument this lane rests on; "
                "remedy: keep runs-on naming the ci-general role"
            ),
        )
        self.assertNotIn("runs-on: ubuntu-24.04", self.directives)
        self.assertNotIn("ci-core", self.directives)
        self.assertNotIn("ci-web-heavy", self.directives)

    def test_fork_pull_requests_are_excluded_using_the_established_condition(self) -> None:
        """One spelling of the rule, shared with the other advisory lane."""
        condition = (
            "github.event.pull_request.head.repo.full_name == github.repository"
        )
        self.assertIn(
            condition,
            self.source,
            msg=(
                "why: this lane runs an agent with repository write scope on a "
                "self-hosted runner, so an untrusted trigger would execute fork "
                "code beside our credentials; remedy: keep the head-repository "
                "condition, and keep it identical to grok-review.yml rather than "
                "writing a second spelling of the same rule"
            ),
        )
        self.assertIn("github.event.pull_request.draft == false", self.source)
        self.assertIn(
            condition,
            GROK.read_text(encoding="utf-8"),
            msg="the two advisory lanes must share one trust condition",
        )

    def test_the_github_token_is_passed_explicitly(self) -> None:
        """Omitting it silently authenticates as the Claude GitHub App.

        That App install binds a Claude organisation to this repository. The
        Claude subscription available here is an employer's, and this
        repository is personal, so the fallback is a governance failure rather
        than a configuration detail -- and it is the *default*, which is what
        makes it worth a test.
        """
        self.assertIn(
            "github_token: ${{ secrets.GITHUB_TOKEN }}",
            self.source,
            msg=(
                "why: claude-code-action authenticates as the Claude GitHub App "
                "when github_token is omitted, which attaches an employer-owned "
                "Claude organisation to this personal repository; remedy: pass "
                "github_token explicitly"
            ),
        )

    def test_the_action_is_pinned_to_a_commit(self) -> None:
        match = re.search(
            r"uses: anthropics/claude-code-action@(\S+)", self.source
        )
        self.assertIsNotNone(match, "the review step must use claude-code-action")
        assert match is not None
        self.assertRegex(
            match.group(1),
            r"^[0-9a-f]{40}$",
            msg=(
                "why: a moving tag names a release rather than the code that "
                "will run on a self-hosted runner holding pull-requests: write; "
                "remedy: pin the action to the commit the tag resolves to, the "
                "way grok-review.yml pins its CLI binary by digest"
            ),
        )

    def test_no_anthropic_credential_is_used(self) -> None:
        """The point of the substitution: the Claude tooling, none of its keys."""
        self.assertIn("ANTHROPIC_BASE_URL", self.source)
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", self.directives)
        self.assertNotIn("claude_code_oauth_token", self.directives)
        self.assertNotIn("ANTHROPIC_API_KEY:", self.directives)
        for backend, (base_url, secret_name) in BACKENDS.items():
            with self.subTest(backend=backend):
                self.assertIn(base_url, self.source)
                self.assertIn(secret_name, self.source)

    def test_a_missing_secret_skips_rather_than_fails(self) -> None:
        """A backend nobody has configured must not turn the lane red."""
        self.assertIn("review skipped: no $SECRET_NAME secret", self.source)
        self.assertIn("fail-fast: false", self.source)

    def test_the_backend_set_is_narrowable_without_editing_the_workflow(self) -> None:
        """The exit if two reviewers prove too noisy."""
        self.assertIn("vars.CLAUDE_REVIEW_BACKENDS", self.source)
        self.assertIn("not in CLAUDE_REVIEW_BACKENDS", self.source)

    def test_the_review_procedure_is_vendored_not_cloned_at_run_time(self) -> None:
        """The marketplace clone failed in production, so it is gone.

        `claude-code-action` clones a plugin marketplace on every invocation.
        Unauthenticated, repeated per Pull Request, from a self-hosted runner,
        GitHub rate-limited it and both backends failed before either reached a
        model. A checked-out copy has no runtime dependency to be rate-limited
        or tampered with, and it meets the bar `grok-review.yml` already sets
        for anything executing beside repository credentials.
        """
        message = (
            "why: cloning the plugin marketplace at run time is unauthenticated "
            "and rate-limited by GitHub on a self-hosted runner, which failed "
            "every review before it reached a model; remedy: keep the procedure "
            "vendored at .claude/commands/pr-review.md and invoke it as "
            "/pr-review"
        )
        self.assertNotIn("plugin_marketplaces", self.directives, message)
        self.assertNotIn("plugins:", self.directives, message)
        self.assertIn("/pr-review", self.source, message)
        self.assertTrue(
            VENDORED_COMMAND.is_file(),
            msg=(
                "why: the workflow invokes /pr-review, which resolves to "
                ".claude/commands/pr-review.md in the checked-out tree; without "
                "the file the review cannot start; remedy: keep the vendored "
                "command in the repository"
            ),
        )

    def test_the_vendored_command_records_where_it_came_from(self) -> None:
        """A copy with no provenance cannot be synced or audited."""
        body = VENDORED_COMMAND.read_text(encoding="utf-8")
        for marker in ("VENDORED", "Blob:", "Repo HEAD at retrieval:", "Retrieved:"):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    body,
                    msg=(
                        "why: a vendored file without its source and revision "
                        "cannot be compared against upstream, so it silently "
                        "diverges; remedy: keep the provenance header, and "
                        "update it whenever the body is refreshed"
                    ),
                )
        self.assertTrue(
            body.startswith("---\n"),
            "the command's frontmatter must stay first or it stops being a command",
        )

    def test_an_advisory_lane_does_not_paint_the_pull_request_red(self) -> None:
        """Advisory in name has to mean advisory in effect.

        A failed run posts no findings, which is a degraded review rather than a
        broken change. A red check on every Pull Request from a lane that cannot
        block one teaches people to ignore red.
        """
        self.assertIn(
            "continue-on-error: true",
            self.source,
            msg=(
                "why: this lane cannot block a merge, so a failure here is a "
                "missing review rather than a defect, and a red check for it "
                "devalues every other red check; remedy: keep "
                "continue-on-error on the review step"
            ),
        )

    def test_the_vendored_command_has_a_token_for_its_gh_calls(self) -> None:
        """It drives `gh pr diff`, `gh pr view` and `gh pr comment`."""
        self.assertIn("GH_TOKEN:", self.source)
        allowed = VENDORED_COMMAND.read_text(encoding="utf-8").split("---", 2)[1]
        self.assertIn("Bash(gh pr diff:*)", allowed)

    def test_the_review_posts_findings_rather_than_only_logging_them(self) -> None:
        self.assertIn("--comment", self.source)
        self.assertIn(
            "mcp__github_inline_comment__create_inline_comment",
            self.source,
            msg=(
                "why: the action starts the MCP server that posts inline "
                "comments only when --allowedTools names it, so without this the "
                "review runs and its findings stay in the job log; remedy: keep "
                "the tool named in claude_args"
            ),
        )


if __name__ == "__main__":
    unittest.main()
