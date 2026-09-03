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

    def test_the_unpinned_marketplace_clone_stays_declared_as_a_gap(self) -> None:
        """The one input this lane does not pin, kept visible rather than tidy.

        `grok-review.yml` verifies its CLI against a digest on the argument that
        anything executing on our own runner beside repository credentials must
        name its bytes. This clone does not meet that bar. It is weaker than the
        Grok case, but it is still an unpinned input, and an accepted gap that
        nobody can see is indistinguishable from one nobody noticed. This test
        exists so removing the note requires deciding to, rather than tidying.
        """
        self.assertIn("plugin_marketplaces", self.source)
        self.assertIn(
            "KNOWN UNPINNED INPUT",
            self.source,
            msg=(
                "why: the marketplace clone is the one runtime input this lane "
                "does not pin, and the note recording that is the only thing "
                "keeping it visible; remedy: either keep the note, or close the "
                "gap by vendoring the skill into .claude/skills/ and removing "
                "plugin_marketplaces along with this assertion"
            ),
        )

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
