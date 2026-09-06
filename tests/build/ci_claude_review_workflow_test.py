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
WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
JOB_ID = "advisory-review"


def job_block(source: str, job_id: str) -> str:
    """The text of one top-level job in a workflow, header to next job."""
    lines = source.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l == f"  {job_id}:\n")
    end = next((i for i in range(start + 1, len(lines))
                if lines[i][:2] == "  " and lines[i][2:3] not in (" ", "#", "\n") and lines[i].rstrip().endswith(":")),
               len(lines))
    return "".join(lines[start:end])
WORKFLOW_SOURCE = REPO_ROOT / ".github/workflows/ci.yml"  # both lanes live here
VENDORED_COMMAND = REPO_ROOT / ".claude/commands/pr-review.md"
SELF_HOSTED_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general]"
)
LIVENESS_SCRIPT = REPO_ROOT / ".github/scripts/advisory_review_liveness.py"

BACKENDS = {
    "glm": ("https://api.z.ai/api/anthropic", "ZAI_CODING_KEY"),
    "kimi": ("https://api.kimi.com/coding/", "KIMI_CODING_KEY"),
}


class ClaudeReviewWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        # Since #659 the review is a job inside ci.yml, so every assertion is
        # scoped to that job's block rather than to a whole workflow file.
        self.source = job_block(WORKFLOW.read_text(encoding="utf-8"), JOB_ID)
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
        self.assertIn(
            "    permissions:\n      contents: read\n      pull-requests: write", self.source,
            msg=("why: posting review threads needs pull-requests: write and nothing "
                 "else in ci.yml does, so the grant is job-level to keep every other "
                 "job's token posture; remedy: keep the job-level permissions block"),
        )

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
                "condition, and keep it identical to the Grok lane's rather "
                "writing a second spelling of the same rule"
            ),
        )
        self.assertIn("github.event.pull_request.draft == false", self.source)
        grok = WORKFLOW_SOURCE.read_text(encoding="utf-8").split(
            "\n  grok-review:\n", 1)[1].split("\n  pre-heavy-gate:", 1)[0]
        self.assertIn(
            condition,
            grok,
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
        # The base URLs and secret names moved into
        # `.github/scripts/advisory_review_liveness.py` when the matrix became
        # a selection (#659): one declaration for the workflow that runs a
        # backend and the check that judges it. The job still names the secret
        # indirectly, through `secrets[matrix.secret_name]`.
        declared = LIVENESS_SCRIPT.read_text(encoding="utf-8")
        for backend, (base_url, secret_name) in BACKENDS.items():
            with self.subTest(backend=backend):
                self.assertIn(base_url, declared)
                self.assertIn(secret_name, declared)
        self.assertIn("secrets[matrix.secret_name]", self.source)

    def test_one_backend_reviews_a_pull_request_not_two(self) -> None:
        """#659 item 3. Two backends duplicated each other; Grok did not.

        The matrix is computed rather than listed, so the workflow cannot
        drift back to running both by an edit that looks like a formatting
        change.
        """
        self.assertIn(
            "matrix: ${{ fromJSON(needs.select-review-backend.outputs.matrix) }}",
            self.source,
            msg=("why: a literal two-entry matrix is what this replaces; remedy: "
                 "keep the matrix coming from the selector job"),
        )
        self.assertNotIn(
            "- backend: glm",
            self.source,
            msg=("why: a hardcoded backend list beside a computed one is two "
                 "sources of truth; remedy: declare backends in "
                 ".github/scripts/advisory_review_liveness.py only"),
        )

    def test_the_workflows_last_resort_matrix_matches_the_declared_primary(self) -> None:
        """The one literal duplicate of the backend table, pinned to its source."""
        import json as _json
        import sys as _sys

        _sys.path.insert(0, str(REPO_ROOT / ".github/scripts"))
        import advisory_review_liveness as liveness  # noqa: PLC0415

        selector = WORKFLOW_SOURCE.read_text(encoding="utf-8").split(
            "\n  select-review-backend:\n", 1)[1].split("\n  advisory-review:", 1)[0]
        literal = selector.split("PRIMARY_MATRIX: '", 1)[1].split("'", 1)[0]
        self.assertEqual(
            _json.loads(literal),
            liveness._selection_matrix([liveness.CLAUDE_BACKENDS[0]["backend"]]),
            msg=("why: the workflow cannot import the script it may be unable to "
                 "run, so this literal is a deliberate second copy; remedy: keep "
                 "it equal to the script's own primary entry"),
        )

    def test_the_selector_decides_from_posted_evidence(self) -> None:
        source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
        selector = source.split("\n  select-review-backend:\n", 1)[1].split(
            "\n  advisory-review:", 1)[0]
        self.assertIn("advisory_review_liveness.py", selector)
        self.assertIn("--select", selector)
        self.assertIn(
            "vars.CLAUDE_REVIEW_ORDER",
            selector,
            msg=("why: the primary must be movable without editing a workflow "
                 "on the protected path; remedy: keep the repository variable"),
        )
        self.assertIn(
            "continue-on-error: true",
            selector.split("\n    steps:", 1)[0],
            msg=("why: advisory-review needs this job, so a crashed selector "
                 "would skip the review and, with it, the gate's ordering; "
                 "remedy: keep continue-on-error at job level"),
        )
        self.assertIn(
            "permissions:\n      contents: read\n      actions: read\n"
            "      issues: read\n      pull-requests: read",
            selector,
            msg=("why: a job-level permissions block makes every omitted scope "
                 "none, so without these the script 403s, the fail-open path "
                 "returns the primary every time, and the handover silently "
                 "never happens; remedy: keep the same read scopes as "
                 "advisory-review-liveness.yml"),
        )
        self.assertIn(
            "ref: ${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.base.sha || github.sha }}",
            selector,
            msg=("why: this job is unconditional, so it runs for forks too, and "
                 "checking out the merge ref would execute a fork's copy of the "
                 "selector script on a trusted runner; remedy: check out the "
                 "base revision -- a Pull Request does not choose its reviewer"),
        )
        self.assertIn(
            "PRIMARY_MATRIX:",
            selector,
            msg=("why: job-level continue-on-error governs the job, not the "
                 "output, so a step that dies without writing a matrix leaves "
                 "fromJSON('') to the review job; remedy: every path in the "
                 "step ends in a matrix"),
        )
        self.assertIn(
            "if: ${{ !cancelled() }}",
            selector,
            msg=("why: advisory-review's strategy.matrix reads this job's "
                 "output, and a skipped selector would leave fromJSON('') to "
                 "be evaluated on push runs of the protected branch; remedy: "
                 "keep the selector unconditional and let the review job's own "
                 "condition keep it to Pull Requests"),
        )

    def test_a_missing_secret_skips_rather_than_fails(self) -> None:
        """A backend nobody has configured must not turn the lane red."""
        self.assertIn("review skipped: no $SECRET_NAME secret", self.source)
        self.assertIn("fail-fast: false", self.source)

    def test_one_operator_knob_chooses_the_backend(self) -> None:
        """Two knobs could disagree, and the disagreement would be silent.

        `CLAUDE_REVIEW_BACKENDS` used to turn one of two matrix legs off. With
        one leg chosen by evidence, a set that does not name the chosen
        backend would skip the whole Claude review -- in exactly the case the
        selector exists for, where the primary is DOWN and it reached for the
        other one.
        """
        whole = WORKFLOW_SOURCE.read_text(encoding="utf-8")
        self.assertIn("vars.CLAUDE_REVIEW_ORDER", whole)
        directives = "\n".join(
            line for line in whole.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertNotIn(
            "CLAUDE_REVIEW_BACKENDS",
            directives,
            msg=("why: an enabled-set that can discard the selected backend "
                 "silently withholds the review; remedy: CLAUDE_REVIEW_ORDER "
                 "is the only knob -- one name pins a backend"),
        )

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
        job = self.source.split("\n    steps:\n", 1)[0]  # job header, before its steps
        self.assertIn(
            "\n    continue-on-error: true\n",
            "\n" + job + "\n",
            msg=(
                "why: inside ci.yml a failed job fails the workflow and skips "
                "Pre-heavy Gate, which needs this job, and the step-level flag "
                "does not cover a job timeout or a failed checkout; remedy: keep "
                "continue-on-error at job level on advisory-review, as macos-primary does"
            ),
        )
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

    def test_a_clean_review_is_an_issue_comment_and_never_a_thread(self) -> None:
        """A thread is an unanswered question; a clean review is not one.

        `main` requires every review thread to be resolved, and Pre-heavy Gate
        counts unresolved threads (#659). A reviewer that files "no issues
        found" as a thread therefore blocks the merge it just approved -- five
        such threads were resolved by hand on 2026-09-06.
        """
        body = VENDORED_COMMAND.read_text(encoding="utf-8")
        self.assertIn(
            "Never post a clean review as a review comment or review thread.",
            body,
            msg=("why: without the prohibition the model files the clean summary "
                 "wherever the available tools allow, and a thread blocks the merge; "
                 "remedy: keep the rule in the vendored command's step 7"),
        )
        self.assertIn(
            "/repos/{owner}/{repo}/issues/{number}/comments",
            body,
            msg=("why: `gh` is absent on ci-general, so without a named REST "
                 "fallback the instruction to post an issue comment is not "
                 "followable; remedy: keep the endpoint in the command"),
        )
        allowed = body.split("---", 2)[1]
        self.assertIn(
            "Bash(curl:*)",
            allowed,
            msg=("why: the REST fallback cannot run unless the tool is allowed; "
                 "remedy: keep Bash(curl:*) in allowed-tools"),
        )
        self.assertIn(
            "Bash(curl:*)",
            self.source,
            msg=("why: claude_args --allowedTools is what the action enforces at "
                 "run time; the command frontmatter alone does not grant it; "
                 "remedy: name the tool in claude_args too"),
        )

    def test_a_clean_thread_is_retired_deterministically_after_the_review(self) -> None:
        """The prompt rule is prevention; this step is the guarantee."""
        self.assertIn("retire_clean_review_threads.py", self.source)
        self.assertIn(
            "<!-- lmdj-review: ${{ matrix.backend }} -->",
            self.source.split("retire_clean_review_threads.py", 1)[1],
            msg=("why: the script may only resolve what this backend signed, so "
                 "the marker has to be passed per backend; remedy: keep the "
                 "signature argument on the step"),
        )
        self.assertIn(
            "if: ${{ always() && steps.backend.outputs.run == 'true' }}",
            self.source,
            msg=("why: the Review step is continue-on-error, so a failed review "
                 "still leaves the step's own outcome behind; the tidy-up must "
                 "run anyway and only for a backend that actually ran; remedy: "
                 "keep always() with the backend condition"),
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
