#!/usr/bin/env python3
"""Reject a Pull Request body that closes an Issue it declares as retained.

GitHub's closing-keyword parser reads `close`, `closes`, `closed`, `fix`,
`fixes`, `fixed`, `resolve`, `resolves` and `resolved` immediately before an
Issue reference as a closing directive. The parser has no notion of the
surrounding sentence, so "this PR does not close #466" closes #466 on merge.
That cost four Issues their open state (#464, #467 and #471 through the
corrective Pull Requests #493, #494 and #495; #466 through #477) and is
recorded as `.agents/pitfalls/github-closing-keyword-negation.md`.

The lint decides two contradictions and nothing else. Both are settled,
mechanically decidable and deterministic, which is what
`docs/governance/pitfall-ledger.md` requires before a pitfall may graduate to a
gate. Judging whether prose *means* partial delivery is none of those things,
so this file never tries: it reads the declared vocabulary instead.

Run it against a Pull Request body before `gh pr create`:

    python3 tests/build/ci_pr_body_lint.py --body-file pr-body.md
    gh pr view 578 --json body -q .body | python3 tests/build/ci_pr_body_lint.py -
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence

# GitHub's own closing keywords, in the exact set its parser accepts.
CLOSING_KEYWORDS = (
    "close", "closes", "closed",
    "fix", "fixes", "fixed",
    "resolve", "resolves", "resolved",
)

# The positive forms that reference an Issue without asking GitHub to close it.
# `Relates to #N` is the required form for a Pull Request that intentionally
# delivers only part of an Issue; the rest are accepted synonyms so an existing
# body does not have to be rewritten to be checked.
RETAINED_RELATION_FORMS = (
    "Relates to #N", "Part of #N", "Refs #N",
)

_KEYWORDS = "|".join(sorted(CLOSING_KEYWORDS, key=len, reverse=True))

# `#123`, `GH-123`, `owner/repo#123` and the full issue URL are all references
# the parser resolves. The Issue number is the trailing run of digits in every
# one of them.
_REFERENCE = (
    r"(?:#\d+"
    r"|GH-\d+"
    r"|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+"
    r"|https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/\d+)"
)
_TRAILING_NUMBER = re.compile(r"(\d+)$")

_CLOSING_DIRECTIVE = re.compile(
    rf"\b(?P<keyword>{_KEYWORDS})\b[ \t]*:?[ \t]*(?P<reference>{_REFERENCE})",
    re.IGNORECASE,
)

# A negation binds to the keyword only when it is adjacent to it. Allowing at
# most two words between the two keeps "does not close #466" and "will never
# resolve #471" in scope while leaving a sentence that merely contains "not"
# somewhere earlier -- "this does not change behaviour and closes #578" -- out
# of it. A wider window would fail bodies whose closing directive is correct,
# and a gate that cries wolf gets disabled rather than obeyed.
_NEGATED_CLOSING_DIRECTIVE = re.compile(
    r"(?P<negation>\b(?:not|never|neither|nor|without|cannot)\b|n[o']t)"
    r"(?P<gap>(?:[ \t]+[A-Za-z][A-Za-z'-]*){0,2}[ \t]+)"
    rf"(?P<keyword>{_KEYWORDS})\b[ \t]*:?[ \t]*(?P<reference>{_REFERENCE})",
    re.IGNORECASE,
)

_RETAINED_RELATION = re.compile(
    r"\b(?:relates?[ \t]+to|related[ \t]+to|part[ \t]+of|refs?|references?)\b"
    r"(?P<references>(?:[ \t]*(?:,|and|&)?[ \t]*(?:#\d+|GH-\d+))+)",
    re.IGNORECASE,
)
_BARE_REFERENCE = re.compile(r"(?:#|GH-)(\d+)")

# GitHub renders neither HTML comments nor fenced code, so its parser never
# sees a reference inside them. The repository Pull Request template carries
# `<!-- Write exactly one: Closes #123 | Relates to #123 | ... -->`, which is a
# contradiction on its face and an instruction in fact; scanning it would fail
# every Pull Request that kept the template.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCED_CODE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", re.DOTALL | re.MULTILINE)


def parsed_body(body: str) -> str:
    """Return only the body text GitHub's closing-keyword parser can see."""
    return _FENCED_CODE.sub("\n", _HTML_COMMENT.sub(" ", body))


def _issue_number(reference: str) -> str:
    match = _TRAILING_NUMBER.search(reference)
    if match is None:  # pragma: no cover - the reference pattern always ends in digits
        raise ValueError(f"reference carries no Issue number: {reference}")
    return match.group(1)


def _quote(text: str) -> str:
    return " ".join(text.split())


def retained_issue_numbers(body: str) -> set[str]:
    """Return every Issue number the body declares as a retained relation."""
    retained: set[str] = set()
    for match in _RETAINED_RELATION.finditer(parsed_body(body)):
        retained.update(_BARE_REFERENCE.findall(match.group("references")))
    return retained


def closing_directives(body: str) -> list[tuple[str, str]]:
    """Return every `(issue number, quoted directive)` GitHub would act on."""
    return [
        (_issue_number(match.group("reference")), _quote(match.group(0)))
        for match in _CLOSING_DIRECTIVE.finditer(parsed_body(body))
    ]


def check_pr_body(body: str) -> list[str]:
    """Return one diagnostic per closing directive that contradicts the body."""
    errors: list[str] = []
    text = parsed_body(body)
    reported: set[str] = set()

    for match in _NEGATED_CLOSING_DIRECTIVE.finditer(text):
        number = _issue_number(match.group("reference"))
        reported.add(number)
        errors.append(
            f"negated closing directive for #{number}: "
            f'"{_quote(match.group(0))}"\n'
            f"  why: GitHub's parser reads "
            f"`{match.group('keyword')} #{number}` as a closing directive and "
            f"has no notion of the `{_quote(match.group('negation'))}` in front "
            f"of it, so merging this Pull Request closes #{number} even though "
            "the sentence says it does not.\n"
            f"  remedy: delete the closing keyword and state the retained "
            f"relation positively as `Relates to #{number}`, then describe the "
            "outstanding acceptance without any of "
            f"{', '.join(CLOSING_KEYWORDS)} in front of an Issue reference."
        )

    retained = retained_issue_numbers(body)
    for number, directive in closing_directives(body):
        if number not in retained or number in reported:
            continue
        reported.add(number)
        errors.append(
            f"#{number} is declared retained and closed in the same body: "
            f'"{directive}"\n'
            f"  why: the body already references #{number} as a retained "
            f"relation, which states the Issue stays open, while "
            f'"{directive}" is a live closing directive GitHub applies on '
            f"merge, so #{number} would close against the declared intent.\n"
            f"  remedy: keep exactly one. Use `Relates to #{number}` alone when "
            "this Pull Request delivers only part of the Issue, or drop the "
            f"retained-relation reference and keep `Closes #{number}` only when "
            f"this Pull Request completes every acceptance item of #{number}."
        )
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail closed when a Pull Request body closes an Issue it declares "
            "as retained."
        ),
    )
    parser.add_argument(
        "--body-file", default="-", metavar="FILE",
        help="the Pull Request body to check; `-` reads standard input",
    )
    args = parser.parse_args(argv)

    if args.body_file == "-":
        body = sys.stdin.read()
    else:
        try:
            with open(args.body_file, encoding="utf-8") as handle:
                body = handle.read()
        except (OSError, UnicodeDecodeError) as error:
            print(
                "cannot read the Pull Request body\n"
                f"  why: {error}\n"
                "  remedy: pass a readable UTF-8 file to --body-file, or pipe "
                "the body to `--body-file -`.",
                file=sys.stderr,
            )
            return 2

    errors = check_pr_body(body)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Pull Request body closing directives: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
