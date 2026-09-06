#!/usr/bin/env python3
"""Contract for the clean-review thread retirement (#659).

The dangerous direction here is resolving a finding, not leaving a clean
review open, so every test below asks "would this ever silence a reviewer?"
before it asks "does it tidy the clean case?".
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/retire_clean_review_threads.py"

_spec = importlib.util.spec_from_file_location("retire_clean_review_threads", SCRIPT)
retire = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(retire)

GLM = "<!-- lmdj-review: glm -->"
KIMI = "<!-- lmdj-review: kimi -->"
CLEAN = f"{GLM}\n\n## Code review\n\nNo issues found. Checked for bugs and CLAUDE.md compliance.\n"


def thread(body: str, *, resolved: bool = False, comments: int = 1) -> dict:
    return {
        "id": f"thread-for-{body[:20]!r}",
        "isResolved": resolved,
        "comments": {"totalCount": comments, "nodes": [{"body": body}]},
    }


class IsCleanReviewTest(unittest.TestCase):
    def test_a_signed_clean_review_is_clean(self) -> None:
        self.assertTrue(retire.is_clean_review(CLEAN, GLM))

    def test_another_backends_thread_is_never_touched(self) -> None:
        self.assertFalse(
            retire.is_clean_review(CLEAN, KIMI),
            msg=("why: each backend runs its own job and may only tidy what it "
                 "signed; remedy: match the marker of the backend that just ran"),
        )

    def test_an_unsigned_comment_is_not_clean(self) -> None:
        self.assertFalse(
            retire.is_clean_review(CLEAN.replace(GLM + "\n\n", ""), GLM),
            msg=("why: without the signature the author is unknown, and this "
                 "must never resolve a human's thread; remedy: require the marker "
                 "as the first line"),
        )

    def test_a_finding_that_also_says_no_issues_is_not_clean(self) -> None:
        for marker in ("[critical]", "[important]", "[nit]", "**Bug:", "## Findings"):
            with self.subTest(marker=marker):
                body = CLEAN + f"\n{marker} something is wrong here\n"
                self.assertFalse(
                    retire.is_clean_review(body, GLM),
                    msg=("why: resolving a finding hides it under a rule that "
                         "exists to surface findings; remedy: let any finding "
                         "marker veto the clean reading"),
                )

    def test_a_finding_that_quotes_the_clean_sentence_is_not_clean(self) -> None:
        """The sentence is in this repository's own diff; findings will quote it."""
        for body in (
            f"{GLM}\n\n## Code review\n\nThe matcher treats a comment containing "
            f"\"No issues found. Checked for bugs and CLAUDE.md compliance.\" as clean, "
            f"which resolves this very thread.\n",
            f"{GLM}\n\nThe script's CLEAN_SENTENCE is "
            f"\"No issues found. Checked for bugs and CLAUDE.md compliance.\" and that "
            f"is too loose.\n",
        ):
            with self.subTest(body=body[:60]):
                self.assertFalse(
                    retire.is_clean_review(body, GLM),
                    msg=("why: a finding is free-form prose and may quote the clean "
                         "sentence, so containment resolves real findings; remedy: "
                         "match the clean review's shape -- signature, heading, then "
                         "the sentence -- not its substrings"),
                )

    def test_a_clean_review_with_appended_notes_is_still_clean(self) -> None:
        body = CLEAN + "\nNotes from the pass: checked all 45 ledger entries.\n"
        self.assertTrue(
            retire.is_clean_review(body, GLM),
            msg=("why: real clean reviews append what was checked, and refusing "
                 "them would leave the blocking thread this exists to remove"),
        )

    def test_a_summary_without_the_clean_sentence_is_not_clean(self) -> None:
        self.assertFalse(retire.is_clean_review(f"{GLM}\n\n## Code review\n\nLooks fine.\n", GLM))


class CleanThreadsTest(unittest.TestCase):
    def test_it_selects_only_the_unresolved_unanswered_clean_thread(self) -> None:
        threads = [
            thread(CLEAN),
            thread(CLEAN, resolved=True),
            thread(CLEAN, comments=2),
            thread(CLEAN.replace(GLM, KIMI)),
            thread(f"{GLM}\n\n[important] real finding\n"),
        ]
        self.assertEqual(retire.clean_threads(threads, GLM), [threads[0]["id"]])

    def test_a_replied_thread_is_left_to_the_human_who_replied(self) -> None:
        self.assertEqual(retire.clean_threads([thread(CLEAN, comments=2)], GLM), [])

    def test_no_threads_is_not_an_error(self) -> None:
        self.assertEqual(retire.clean_threads([], GLM), [])


class FailureModeTest(unittest.TestCase):
    def test_it_exits_zero_without_a_token(self) -> None:
        """A tidy-up beside an advisory lane must never redden the run."""
        import os

        saved = os.environ.pop("GITHUB_TOKEN", None)
        try:
            self.assertEqual(retire.main(["endaye/lmdj", "1", GLM]), 0)
        finally:
            if saved is not None:
                os.environ["GITHUB_TOKEN"] = saved

    def test_it_exits_zero_on_bad_arguments(self) -> None:
        self.assertEqual(retire.main([]), 0)


if __name__ == "__main__":
    unittest.main()
