#!/usr/bin/env python3
"""Contract tests for the Pull Request body closing-directive lint.

Each historical fixture is the exact sentence the merged Pull Request carried,
so a future relaxation of the lint fails against the real recurrence rather
than against a paraphrase of it. See
`.agents/pitfalls/github-closing-keyword-negation.md`.
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LINT = REPO_ROOT / "tests/build/ci_pr_body_lint.py"
SKILL = REPO_ROOT / ".agents/skills/issue-done/SKILL.md"
PITFALL = REPO_ROOT / ".agents/pitfalls/github-closing-keyword-negation.md"

_SPEC = importlib.util.spec_from_file_location("ci_pr_body_lint", LINT)
assert _SPEC is not None and _SPEC.loader is not None
lint = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = lint
_SPEC.loader.exec_module(lint)


# The bodies that actually closed a retained Issue. #493, #494 and #495 are the
# corrective design Pull Requests that closed #464, #467 and #471; #477 is the
# 2026-09-03 audit finding that closed #466 after saying it delivered the
# design half only.
RECURRENCES = {
    477: (
        "- Relates to #466 and umbrella #472. This PR delivers the design half "
        "only and does not close #466, whose acceptance also requires the "
        "committed fixtures and report tooling.",
        "466",
    ),
    493: (
        "- Relates to #464, #465, and #471. This corrective design PR does not "
        "close #464; its implementation-plan acceptance remains open.",
        "464",
    ),
    494: (
        "- Relates to #467, #466, and #471. This corrective design PR does not "
        "close #467; its implementation plan and issue split remain open.",
        "467",
    ),
    495: (
        "- Relates to #471, #467, and #431. This corrective design PR does not "
        "close #471; its implementation plan remains open.",
        "471",
    ),
}

FAILURE_CONTRACT = (
    "why: a fail-closed check must name the violated invariant and the "
    "concrete action that corrects it; remedy: keep both a `why:` clause and a "
    "`remedy:` clause naming `Relates to #N` in every diagnostic "
    "check_pr_body returns -- see .agents/pitfalls/gate-failure-readability.md"
)


class ClosingDirectiveRecurrenceTest(unittest.TestCase):
    def assert_names_why_and_remedy(self, error: str, number: str) -> None:
        self.assertIn("why:", error, FAILURE_CONTRACT)
        self.assertIn("remedy:", error, FAILURE_CONTRACT)
        self.assertIn(f"Relates to #{number}", error, FAILURE_CONTRACT)

    def test_every_recorded_recurrence_is_rejected(self):
        for pull_request, (body, number) in RECURRENCES.items():
            with self.subTest(pull_request=pull_request):
                errors = lint.check_pr_body(body)
                self.assertEqual(
                    len(errors), 1,
                    "why: the body that closed a retained Issue on PR "
                    f"#{pull_request} must produce exactly one diagnostic "
                    f"naming #{number}, and produced {errors}; remedy: keep the "
                    "negated-closing-directive rule in "
                    "tests/build/ci_pr_body_lint.py able to read "
                    "`does not close #N`",
                )
                self.assertIn(f"#{number}", errors[0])
                self.assert_names_why_and_remedy(errors[0], number)

    def test_each_negation_form_binds_to_an_adjacent_closing_keyword(self):
        for body, number in (
            ("This Pull Request does not close #466.", "466"),
            ("It doesn't fix #493 either.", "493"),
            ("The design will never resolve #471 on its own.", "471"),
            ("Landing it cannot close #464.", "464"),
            ("Neither of these close #467.", "467"),
            ("Merging this does not close https://github.com/endaye/lmdj/issues/477.", "477"),
            ("This does not close endaye/lmdj#495.", "495"),
            ("This does not close GH-494.", "494"),
        ):
            with self.subTest(body=body):
                errors = lint.check_pr_body(body)
                self.assertEqual(len(errors), 1, body)
                self.assert_names_why_and_remedy(errors[0], number)

    def test_a_retained_relation_and_a_closing_directive_cannot_coexist(self):
        # The contradiction rule stands on the declared vocabulary alone, with
        # no negation anywhere, so a body that says both things plainly is
        # still caught.
        errors = lint.check_pr_body(
            "Relates to #466 and #472.\n\n## Summary\nCloses #466\n"
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("#466 is declared retained and closed", errors[0])
        self.assert_names_why_and_remedy(errors[0], "466")

        for relation in ("Relates to", "Related to", "Part of", "Refs"):
            with self.subTest(relation=relation):
                self.assertEqual(
                    lint.retained_issue_numbers(f"{relation} #466, #472 and #431."),
                    {"466", "472", "431"},
                )

    def test_one_diagnostic_per_issue_even_when_both_rules_match(self):
        errors = lint.check_pr_body(
            "Relates to #466. This Pull Request does not close #466."
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("negated closing directive for #466", errors[0])


class LegitimateBodyTest(unittest.TestCase):
    def test_final_delivery_closing_directives_are_preserved(self):
        for body in (
            "## Summary\nCloses #578\n",
            "Fixes #578 — the gate and its regression coverage land together.",
            "Resolves #578.",
            "closes endaye/lmdj#578",
            "Closes https://github.com/endaye/lmdj/issues/578",
        ):
            with self.subTest(body=body):
                self.assertEqual(lint.check_pr_body(body), [])

    def test_a_distant_negation_does_not_bind_to_the_closing_keyword(self):
        # A gate that fails a correct final-delivery body gets switched off
        # rather than obeyed, so the negation window stays adjacent.
        self.assertEqual(
            lint.check_pr_body(
                "This does not change runtime behaviour and closes #578."
            ),
            [],
        )
        self.assertEqual(
            lint.check_pr_body(
                "No portal page changed in this Task.\n\nCloses #578\n"
            ),
            [],
        )

    def test_partial_delivery_stated_in_the_safe_vocabulary_passes(self):
        self.assertEqual(
            lint.check_pr_body(
                "Relates to #466 and umbrella #472. This Pull Request delivers "
                "the design half only; the committed fixtures and the report "
                "tooling remain outstanding acceptance for #466."
            ),
            [],
        )

    def test_the_repository_pull_request_template_passes_unmodified(self):
        # The template's own instruction comment carries both `Closes #123` and
        # `Relates to #123`; GitHub renders neither, so neither may be scanned.
        template = (REPO_ROOT / ".github/pull_request_template.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(lint.check_pr_body(template), [])

    def test_unrendered_regions_are_not_scanned(self):
        for body in (
            "<!-- Write exactly one: Closes #123 | Relates to #123 -->",
            "Relates to #578\n\n```\nCloses #578\n```\n",
            "~~~text\nThis does not close #578.\n~~~\n",
        ):
            with self.subTest(body=body):
                self.assertEqual(lint.check_pr_body(body), [])


class CommandLineTest(unittest.TestCase):
    def run_cli(self, argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        saved, sys.stdin = sys.stdin, io.StringIO(stdin)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = lint.main(argv)
        finally:
            sys.stdin = saved
        return code, out.getvalue(), err.getvalue()

    def test_a_clean_body_exits_zero_and_a_violation_exits_one(self):
        code, out, _ = self.run_cli(["--body-file", "-"], "Closes #578\n")
        self.assertEqual(code, 0)
        self.assertIn("valid", out)

        body, number = RECURRENCES[477]
        code, _, err = self.run_cli(["--body-file", "-"], body)
        self.assertEqual(code, 1)
        self.assertIn(f"Relates to #{number}", err)
        self.assertIn("why:", err)
        self.assertIn("remedy:", err)

    def test_an_unreadable_body_fails_closed_with_a_remedy(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.md"
            code, _, err = self.run_cli(["--body-file", str(missing)])
        self.assertEqual(code, 2)
        self.assertIn("why:", err)
        self.assertIn("remedy:", err)

    def test_the_lint_runs_as_a_standalone_script(self):
        completed = subprocess.run(
            [sys.executable, str(LINT), "--body-file", "-"],
            input=RECURRENCES[493][0], text=True, capture_output=True,
            cwd=REPO_ROOT, check=False,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("Relates to #464", completed.stderr)


class ShippingContractTest(unittest.TestCase):
    """The lint only closes the pitfall while the shipping flow invokes it."""

    def test_the_issue_done_skill_mandates_the_lint(self):
        skill = SKILL.read_text(encoding="utf-8")
        for required in (
            "tests/build/ci_pr_body_lint.py",
            "Relates to #<number>",
            "Closes #<issue_id>",
        ):
            # `assertTrue` rather than `assertIn`: the file is thousands of
            # characters, and a diagnostic that dumps all of them buries the
            # sentence that says what to do.
            self.assertTrue(
                required in skill,
                "why: the closing-directive lint is only reachable through the "
                "shipping flow, so a skill that stops naming it leaves the "
                "pitfall unenforced; remedy: restore the Related-Issue "
                f"vocabulary section in {SKILL.relative_to(REPO_ROOT)} naming "
                f"{required!r}",
            )

    def test_the_pitfall_entry_records_this_gate_as_its_exit(self):
        entry = PITFALL.read_text(encoding="utf-8")
        for required in (
            "status: absorbed",
            "exit: gate:tests/build/ci_pr_body_lint_test.py",
        ):
            self.assertTrue(
                required in entry,
                "why: docs/governance/pitfall-ledger.md requires a recurrence-2 "
                "entry to record the mechanism that absorbed it, and this suite "
                "is that mechanism; remedy: keep "
                f"{required!r} in {PITFALL.relative_to(REPO_ROOT)}, or remove "
                "this gate and reopen the entry with a linked escalation Issue",
            )


if __name__ == "__main__":
    unittest.main()
