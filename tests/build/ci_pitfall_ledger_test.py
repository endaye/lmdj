#!/usr/bin/env python3
"""Lint for the Pitfall Ledger's frontmatter and escalation obligations (#303).

The ledger is the one place every agent brand writes to, and nothing else
reads its frontmatter mechanically. Once agents were writing entries (#302), a
malformed field or a silently skipped escalation would rot it unnoticed. This
is the slice of the contract in `docs/governance/pitfall-ledger.md` that passes
all three gate-admission criteria: the schema is settled, a violation is
mechanically decidable, and the check is deterministic.

Deliberately out of scope, because they fail those criteria: content quality,
near-duplicate detection, and whether a fix Pull Request *should* have declared
a pitfall. `Pitfall impact:` stays a reviewed declaration.

Every failure names the file, the rule, and the remedy.
"""

from __future__ import annotations

from pathlib import Path
import re
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / ".agents/pitfalls"

# Mirrors the repository's `area:*` labels. The ledger contract says an entry's
# `area` is "one existing GitHub area:* label namespace without the prefix";
# this test cannot query GitHub, so the set is pinned here and a label added
# to the repository is added here in the same change.
KNOWN_AREAS = frozenset({
    "ci-release", "contracts", "core", "creator", "docs-governance",
    "native-host", "product", "provider", "web-host",
})
STATUSES = frozenset({"open", "absorbed"})
# `[^\s,]` so `gate:a.py,gate:b.py` -- the list grammar #624 briefly invented -- is
# rejected rather than read as one path with a comma in it.
EXIT = re.compile(r"^(none|skill:(?P<skill>[^\s,]+)|gate:(?P<gate>[^\s,]+))$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# An Actions run is where a CI pitfall is actually observed, and two seed
# entries already link one; the contract sentence is widened to match in
# the same change rather than the entries narrowed to a less exact pointer.
OCCURRENCE = re.compile(
    r"^https://github\.com/[^/\s]+/[^/\s]+/(pull|issues|commit|actions/runs)/\S+$"
)
# A bare `#N` is not an escalation link: entry bodies cite `PR #584` in prose,
# which would let a recurrence-2 entry pass with no Issue behind it. Only the
# full Issue URL counts -- the form every current recurrence-2 entry uses.
ESCALATION_LINK = re.compile(r"github\.com/[^/\s]+/[^/\s]+/issues/\d+")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter, body) from a ledger entry without a YAML library.

    Entries use a fixed, shallow shape: scalar keys plus a `recurrences` list
    of three-key mappings. Anything outside that shape is a lint failure, not
    something to parse leniently.
    """
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter: file must begin with a --- line")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("unterminated frontmatter: no closing --- line")
    block = text[4:end]
    body = text[end + 4:]
    data: dict = {}
    current: dict | None = None
    for raw in block.splitlines():
        if not raw.strip():
            continue
        if raw.startswith("  - "):
            current = {}
            if not isinstance(data.setdefault("recurrences", []), list):
                raise ValueError(
                    "`recurrences:` carries a scalar but is followed by `  - ` items; "
                    "leave the key bare and list the occurrences under it")
            data["recurrences"].append(current)
            raw = "    " + raw[4:]
        if raw.startswith("    ") and current is not None:
            key, _, value = raw.strip().partition(":")
            current[key.strip()] = value.strip()
            continue
        if raw.startswith(" "):
            raise ValueError(f"unexpected indentation: {raw!r}")
        key, _, value = raw.partition(":")
        current = None
        # A bare `recurrences:` opens the list the `  - ` items append to.
        # Every other bare key stays "", so the grammar rules below fail it by
        # name instead of a TypeError aborting the whole ledger scan.
        key = key.strip()
        data[key] = value.strip() if value.strip() else ([] if key == "recurrences" else "")
    return data, body


def lint_entry(path: Path, repo_root: Path = ROOT) -> list[str]:
    """Return every rule this entry violates, each with file, rule and remedy."""
    problems: list[str] = []
    name = path.name

    def fail(rule: str, why: str, remedy: str) -> None:
        problems.append(f"{name}: {rule} -- why: {why}; remedy: {remedy}")

    try:
        data, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except ValueError as error:
        fail("frontmatter", str(error),
             "copy .agents/pitfalls/TEMPLATE and keep the --- delimiters")
        return problems

    for key in ("id", "area", "status", "recurrences", "exit"):
        if key not in data:
            fail("required-field", f"`{key}` is missing",
                 f"add `{key}:` as in .agents/pitfalls/TEMPLATE")
    if problems:
        return problems

    if data["id"] != path.stem:
        fail("id-matches-filename",
             f"id is {data['id']!r} but the file is {path.stem!r}",
             "make `id` the lowercase kebab-case filename stem")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", data["id"]):
        fail("id-kebab-case", f"id {data['id']!r} is not lowercase kebab-case",
             "use lowercase words joined by single hyphens")
    if data["area"] not in KNOWN_AREAS:
        fail("area-is-a-label",
             f"area {data['area']!r} is not an `area:*` label namespace",
             f"use one of {sorted(KNOWN_AREAS)}, or add the label and this set together")
    if data["status"] not in STATUSES:
        fail("status-enum", f"status {data['status']!r} is not open or absorbed",
             "set `status: open` or `status: absorbed`")

    exit_match = EXIT.match(data["exit"])
    if not exit_match:
        fail("exit-grammar",
             f"exit {data['exit']!r} is not `none`, `skill:<path>` or `gate:<path>`",
             "name exactly one mechanism; a second one belongs in the body prose")
    else:
        target = exit_match.group("skill") or exit_match.group("gate")
        if target and not (repo_root / target).exists():
            fail("exit-path-exists", f"exit points at {target!r}, which does not exist",
                 "point `exit` at a file in the repository")
        if data["status"] == "absorbed" and data["exit"] == "none":
            fail("absorbed-has-exit", "status is absorbed but exit is none",
                 "an absorbed entry names the mechanism that absorbed it")

    recurrences = data.get("recurrences")
    if not isinstance(recurrences, list) or not recurrences:
        # a bare `recurrences:` parses to []; a scalar there is also wrong
        fail("recurrences-nonempty", "recurrences is empty",
             "record at least the occurrence that created the entry")
        recurrences = []
    for index, item in enumerate(recurrences, 1):
        for key in ("date", "occurrence", "observed_by"):
            if not item.get(key):
                fail("recurrence-fields", f"recurrence {index} lacks `{key}`",
                     "each recurrence carries date, occurrence and observed_by")
        if item.get("date") and not ISO_DATE.match(item["date"]):
            fail("recurrence-date", f"recurrence {index} date {item['date']!r} is not ISO",
                 "write the date as YYYY-MM-DD")
        if item.get("occurrence") and not OCCURRENCE.match(item["occurrence"]):
            fail("recurrence-occurrence",
                 f"recurrence {index} occurrence {item['occurrence']!r} is not a "
                 "GitHub pull, issue, commit or Actions run URL",
                 "link the Pull Request, Issue, commit or Actions run where it was observed")

    # Contract: at recurrence 2 the Task either lands the exit *and* absorbs, or
    # keeps the entry open *and* links an escalation Issue. An open entry with a
    # named exit and no Issue is the half-done cycle the contract forbids.
    if (len(recurrences) >= 2 and data["status"] == "open"
            and not ESCALATION_LINK.search(body)):
        fail("escalation-at-recurrence-2",
             "two or more recurrences with status open, and the body links no "
             "escalation Issue",
             "land a mechanism and set exit/absorbed, or open an escalation "
             "Issue and link it from the body (pitfall-ledger.md, Recurrence "
             "and escalation)")
    return problems


def lint_ledger(directory: Path, repo_root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for path in sorted(directory.glob("*.md")):
        problems.extend(lint_entry(path, repo_root))
    return problems


class LedgerLintTest(unittest.TestCase):
    def test_every_entry_in_the_ledger_passes(self) -> None:
        problems = lint_ledger(LEDGER)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_ledger_is_not_empty(self) -> None:
        self.assertGreater(len(list(LEDGER.glob("*.md"))), 0)

    def test_the_template_is_not_linted_as_an_entry(self) -> None:
        """TEMPLATE has no .md suffix precisely so this glob skips it."""
        self.assertTrue((LEDGER / "TEMPLATE").exists())
        self.assertNotIn(LEDGER / "TEMPLATE", list(LEDGER.glob("*.md")))


class LedgerLintFixtureTest(unittest.TestCase):
    """Each failure mode, exercised on a synthetic entry, must name file, rule, remedy."""

    GOOD = (
        "---\n"
        "id: {id}\n"
        "area: ci-release\n"
        "status: {status}\n"
        "recurrences:\n"
        "  - date: 2026-09-01\n"
        "    occurrence: https://github.com/endaye/lmdj/pull/1\n"
        "    observed_by: test\n"
        "{extra}"
        "exit: {exit}\n"
        "---\n\n# Title\n\n## Why\n\n{body}\n\n## How to apply\n\n- x\n"
    )

    def entry(self, **kw) -> list[str]:
        kw.setdefault("id", "sample-entry"); kw.setdefault("status", "open")
        kw.setdefault("exit", "none"); kw.setdefault("extra", ""); kw.setdefault("body", "text")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / f"{kw.pop('filename', kw['id'])}.md"
            p.write_text(self.GOOD.format(**kw), encoding="utf-8")
            return lint_entry(p, ROOT)

    def assert_rule(self, problems: list[str], rule: str) -> None:
        hits = [p for p in problems if f": {rule} --" in p]
        self.assertTrue(hits, f"expected rule {rule!r} in {problems}")
        for hit in hits:
            self.assertIn("why:", hit); self.assertIn("remedy:", hit)
            self.assertTrue(hit.startswith("sample-"), f"failure must name the file: {hit}")

    def test_a_well_formed_entry_passes(self) -> None:
        self.assertEqual(self.entry(), [])

    def test_id_must_match_filename(self) -> None:
        self.assert_rule(self.entry(filename="sample-other"), "id-matches-filename")

    def test_area_must_be_a_label(self) -> None:
        problems = self.entry()
        self.assertEqual(problems, [])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sample-entry.md"
            p.write_text(self.GOOD.format(id="sample-entry", status="open", exit="none",
                                          extra="", body="t").replace("area: ci-release", "area: quality-acceptance"))
            self.assert_rule(lint_entry(p, ROOT), "area-is-a-label")

    def test_status_enum(self) -> None:
        self.assert_rule(self.entry(status="closed"), "status-enum")

    def test_exit_grammar_rejects_a_comma_joined_pair(self) -> None:
        """The multi-value exit #624 briefly carried is the case this pins."""
        self.assert_rule(self.entry(exit="gate:a.py,gate:b.py"), "exit-grammar")

    def test_exit_path_must_exist(self) -> None:
        self.assert_rule(self.entry(exit="gate:tests/build/does_not_exist_test.py"),
                         "exit-path-exists")

    def test_absorbed_needs_an_exit(self) -> None:
        self.assert_rule(self.entry(status="absorbed", exit="none"), "absorbed-has-exit")

    def test_recurrence_fields_and_shapes(self) -> None:
        bad = ("  - date: yesterday\n"
               "    occurrence: not-a-url\n"
               "    observed_by: \n")
        problems = self.entry(extra=bad)
        for rule in ("recurrence-fields", "recurrence-date", "recurrence-occurrence"):
            self.assert_rule(problems, rule)

    def raw_entry(self, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sample-entry.md"
            p.write_text(text, encoding="utf-8")
            return lint_entry(p, ROOT)

    def test_a_bare_scalar_key_fails_by_name_instead_of_crashing(self) -> None:
        good = self.GOOD.format(id="sample-entry", status="open", exit="none", extra="", body="text")
        for line, rule in (("exit: none", "exit-grammar"), ("area: ci-release", "area-is-a-label"),
                           ("status: open", "status-enum"), ("id: sample-entry", "id-matches-filename")):
            with self.subTest(line=line):
                bare = line.split(":")[0] + ":"
                problems = self.raw_entry(good.replace(line + "\n", bare + "\n", 1))
                self.assert_rule(problems, rule)

    def test_scalar_recurrences_followed_by_items_is_a_frontmatter_failure(self) -> None:
        good = self.GOOD.format(id="sample-entry", status="open", exit="none", extra="", body="text")
        problems = self.raw_entry(good.replace("recurrences:\n", "recurrences: foo\n", 1))
        self.assert_rule(problems, "frontmatter")

    def test_two_recurrences_open_none_needs_an_escalation_link(self) -> None:
        second = ("  - date: 2026-09-02\n"
                  "    occurrence: https://github.com/endaye/lmdj/pull/2\n"
                  "    observed_by: test\n")
        self.assert_rule(self.entry(extra=second, body="no link here"),
                         "escalation-at-recurrence-2")
        # prose mentions of PRs or bare issue numbers are not an escalation link
        for prose in ("escalated in #654", "landed in PR #584", "see /pull/584"):
            with self.subTest(body=prose):
                self.assert_rule(self.entry(extra=second, body=prose),
                                 "escalation-at-recurrence-2")
        self.assertEqual(self.entry(extra=second,
                                    body="see https://github.com/endaye/lmdj/issues/654"), [])
        # absorbed with an exit is the other complete action
        self.assertEqual(self.entry(extra=second, status="absorbed",
                                    exit="skill:.agents/skills/issue-done/SKILL.md"), [])
        # open with a named exit but no Issue is the half-done cycle: still fails
        self.assert_rule(self.entry(extra=second, exit="gate:tests/build/ci_pitfall_ledger_test.py"),
                         "escalation-at-recurrence-2")


if __name__ == "__main__":
    unittest.main()
