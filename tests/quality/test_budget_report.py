#!/usr/bin/env python3
"""Report how much of its timeout budget each test used, machine speed aside.

A test's raw seconds cannot say whether the test got slower or the machine
did. This session watched build.release_prepare go from 14.9s to a timeout
while project_io.project_store went from 25.5s to 13.7s on the same runs --
one of those was a real regression and the other was a fix, and raw seconds
told neither story.

The suite's own total run time is the machine's speed for that run. Dividing
by it turns "seconds" into "share of the run", which is comparable across
machines and across load. A test whose share rises got slower; a test whose
seconds rose while its share held was carried by a slower machine.

Budgets remain absolute, because CTest enforces them in absolute seconds. So
this reports both: the absolute headroom that decides whether CI goes red, and
the normalised share that decides whether anyone should look at the test.

Reads CTest output on stdin or from a file. Never fails a build: a guardrail
that can stop a Pull Request is one more source of the randomness it exists to
remove.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


TEST_LINE = re.compile(
    r"Test\s+#\d+:\s+(?P<name>\S+)\s+\.+\s*"
    r"(?P<status>Passed|\*\*\*Timeout|\*\*\*Failed|\*\*\*Not Run)\s+"
    r"(?P<seconds>[\d.]+)\s+sec"
)
TOTAL_LINE = re.compile(r"Total Test time \(real\)\s*=\s*(?P<seconds>[\d.]+)\s*sec")
TIER_LINE = re.compile(r"set\(lmdj_test_timeout_(?P<tier>\w+)\s+(?P<seconds>\d+)\)")
# lmdj_add_test's cmake_parse_arguments keywords (cmake/LmdjTesting.cmake).
ONE_VALUE = frozenset({"NAME", "TIER", "TIMEOUT", "WORKING_DIRECTORY"})
MULTI_VALUE = frozenset({"COMMAND", "LABELS"})
BRACKET_OPEN = re.compile(r"\[(=*)\[")
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
VARIABLE = re.compile(r"\$\{[^}]*\}")
# The multipliers LmdjTesting.cmake applies. Coverage gets none, which is why
# a coverage run is the tightest budget in the repository.
SANITIZER_MULTIPLIER = {"none": 1, "coverage": 1, "address": 3, "thread": 4}


@dataclass(frozen=True)
class Observation:
    name: str
    status: str
    seconds: float
    budget: float | None

    @property
    def used(self) -> float | None:
        if self.budget is None or self.budget <= 0:
            return None
        return self.seconds / self.budget * 100.0


def tier_budgets(repo_root: Path) -> dict[str, int]:
    text = (repo_root / "cmake/LmdjTesting.cmake").read_text(encoding="utf-8")
    return {m.group("tier"): int(m.group("seconds")) for m in TIER_LINE.finditer(text)}


def _skip_bracket(text: str, index: int) -> int | None:
    """Return the index after a bracket argument/comment opening at index."""
    opening = BRACKET_OPEN.match(text, index)
    if opening is None:
        return None
    close = text.find("]" + opening.group(1) + "]", opening.end())
    return len(text) if close < 0 else close + len(opening.group(1)) + 2


def _skip_comment(text: str, index: int) -> int:
    """Return the index after the comment whose '#' sits at index."""
    end = _skip_bracket(text, index + 1)
    if end is not None:
        return end
    newline = text.find("\n", index)
    return len(text) if newline < 0 else newline


def _skip_quoted(text: str, index: int) -> int:
    """Return the index after the quoted argument whose '"' sits at index."""
    cursor = index + 1
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
        elif text[cursor] == '"':
            return cursor + 1
        else:
            cursor += 1
    return len(text)


def _arguments(text: str, index: int) -> tuple[list[str], int]:
    """Split the arguments of the call whose '(' sits at index.

    Scans to the balancing ')' so the layout of the call -- closing parenthesis
    on its own line, on the last argument's line, or the whole call on one line
    -- cannot change what is read. Nested parentheses, quoted and bracket
    arguments and comments are consumed whole, so a ')' inside them never ends
    the call early.
    """
    tokens: list[str] = []
    depth = 1
    cursor = index + 1
    while cursor < len(text):
        char = text[cursor]
        if char.isspace():
            cursor += 1
        elif char == "#":
            cursor = _skip_comment(text, cursor)
        elif char == '"':
            end = _skip_quoted(text, cursor)
            tokens.append(text[cursor + 1:end - 1])
            cursor = end
        elif char == "(":
            depth += 1
            tokens.append(char)
            cursor += 1
        elif char == ")":
            depth -= 1
            cursor += 1
            if depth == 0:
                return tokens, cursor
            tokens.append(char)
        else:
            bracket = _skip_bracket(text, cursor)
            if bracket is not None:
                tokens.append(text[cursor:bracket])
                cursor = bracket
                continue
            start = cursor
            while (cursor < len(text) and not text[cursor].isspace()
                   and text[cursor] not in '()#"'):
                cursor += 1 + (text[cursor] == "\\")
            tokens.append(text[start:cursor])
    return tokens, len(text)


def cmake_calls(text: str, command: str) -> list[list[str]]:
    """Every invocation of command in CMake source, as its argument tokens.

    Text inside comments and quoted or bracket arguments is never read as a
    call, so `message("lmdj_add_test(...)")` registers nothing.
    """
    calls: list[list[str]] = []
    wanted = command.lower()
    cursor = 0
    while cursor < len(text):
        char = text[cursor]
        if char == "#":
            cursor = _skip_comment(text, cursor)
        elif char == '"':
            cursor = _skip_quoted(text, cursor)
        elif char == "[" and (bracket := _skip_bracket(text, cursor)) is not None:
            cursor = bracket
        elif (identifier := IDENTIFIER.match(text, cursor)) is not None and (
                cursor == 0 or not (text[cursor - 1].isalnum()
                                    or text[cursor - 1] in "_$")):
            cursor = identifier.end()
            while cursor < len(text) and text[cursor] in " \t":
                cursor += 1
            if cursor < len(text) and text[cursor] == "(":
                if identifier.group(0).lower() == wanted:
                    arguments, cursor = _arguments(text, cursor)
                    calls.append(arguments)
                else:
                    cursor += 1
        else:
            cursor += 1
    return calls


def registration_fields(arguments: list[str]) -> dict[str, list[str]]:
    """Group lmdj_add_test arguments by keyword, as cmake_parse_arguments does."""
    fields: dict[str, list[str]] = {}
    keyword: str | None = None
    for token in arguments:
        if token in ONE_VALUE or token in MULTI_VALUE:
            keyword = token
            fields.setdefault(keyword, [])
        elif keyword is not None:
            if keyword in MULTI_VALUE or not fields[keyword]:
                fields[keyword].append(token)
    return fields


def budget_for(name: str, budgets: dict[str, float]) -> float | None:
    """Budget of a CTest name, matching names registered inside foreach loops.

    A registration such as `platform.cardputer.lcd.${scenario}` declares the
    budget of every name its loop expands to, so a variable matches any
    non-empty text. An exact registration wins; otherwise the declaration with
    the most literal text does.
    """
    if name in budgets:
        return budgets[name]
    best: tuple[int, float] | None = None
    for declared, budget in budgets.items():
        if "${" not in declared:
            continue
        parts = VARIABLE.split(declared)
        pattern = ".+".join(re.escape(part) for part in parts)
        if re.fullmatch(pattern, name):
            literal = sum(len(part) for part in parts)
            if best is None or literal > best[0]:
                best = (literal, budget)
    return None if best is None else best[1]


def declared_budgets(repo_root: Path, multiplier: int) -> dict[str, float]:
    tiers = tier_budgets(repo_root)
    budgets: dict[str, float] = {}
    for path in repo_root.rglob("CMakeLists.txt"):
        # Skip generated trees and nested checkouts, but only *below* the root
        # being scanned - the root itself is often a worktree, and excluding it
        # by absolute path would silently find no declarations at all.
        relative = path.relative_to(repo_root).as_posix()
        if relative.startswith("build/") or relative.startswith(".worktrees/"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "lmdj_add_test" not in text:
            continue
        for arguments in cmake_calls(text, "lmdj_add_test"):
            fields = registration_fields(arguments)
            name = fields.get("NAME")
            tier = fields.get("TIER")
            if not name or not tier:
                continue
            explicit = fields.get("TIMEOUT")
            if explicit:
                # A TIMEOUT this scan cannot evaluate has no known budget;
                # falling back to the tier default would report a wrong one.
                base = int(explicit[0]) if explicit[0].isdigit() else None
            else:
                base = tiers.get(tier[0])
            if base:
                budgets[name[0]] = base * multiplier
    return budgets


def parse_run(text: str, budgets: dict[str, float]) -> tuple[list[Observation], float]:
    observations = [
        Observation(
            name=m.group("name"),
            status=m.group("status").lstrip("*"),
            seconds=float(m.group("seconds")),
            budget=budget_for(m.group("name"), budgets),
        )
        for m in TEST_LINE.finditer(text)
    ]
    totals = TOTAL_LINE.findall(text)
    return observations, float(totals[-1]) if totals else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ctest-log", type=Path)
    # parents[2] is the repository root for tests/quality/<file>. Resolving the
    # symlink-free real path keeps this correct inside a git worktree.
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--sanitizer",
        default="none",
        choices=sorted(SANITIZER_MULTIPLIER),
        help="Selects the timeout multiplier LmdjTesting.cmake applies.",
    )
    parser.add_argument(
        "--warn-percent",
        type=float,
        default=70.0,
        help="Report tests at or above this share of their absolute budget.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="A previous --json report. Enables the normalised comparison that "
             "separates a slower test from a slower machine.",
    )
    parser.add_argument("--json", type=Path, help="Write this run as a baseline.")
    args = parser.parse_args()

    text = args.ctest_log.read_text(encoding="utf-8") if args.ctest_log else sys.stdin.read()
    budgets = declared_budgets(args.repo_root, SANITIZER_MULTIPLIER[args.sanitizer])
    observations, total = parse_run(text, budgets)
    if not observations:
        print("test budget report: no CTest results found", file=sys.stderr)
        return 0

    ranked = sorted(
        (o for o in observations if o.used is not None),
        key=lambda o: o.used or 0.0,
        reverse=True,
    )
    print(f"test budget report: {len(observations)} tests, {total:.1f}s total, "
          f"{args.sanitizer} multiplier ×{SANITIZER_MULTIPLIER[args.sanitizer]}")

    unbudgeted = sorted(o.name for o in observations if o.budget is None)
    if unbudgeted:
        # Name them: a test with no readable budget can never reach the
        # warning list, so silence here would read as headroom.
        print(f"no declared budget found for {len(unbudgeted)} tests: "
              + ", ".join(unbudgeted))

    hot = [o for o in ranked if (o.used or 0.0) >= args.warn_percent]
    if hot:
        print(f"\nat or above {args.warn_percent:.0f}% of budget:")
        for o in hot:
            print(f"  {o.used:5.0f}%  {o.seconds:7.2f}s of {o.budget:.0f}s  "
                  f"{o.name}{'' if o.status == 'Passed' else '  [' + o.status + ']'}")
    else:
        print(f"\nno test reached {args.warn_percent:.0f}% of its budget")

    if args.baseline and args.baseline.is_file():
        previous = json.loads(args.baseline.read_text(encoding="utf-8"))
        prior_total = float(previous.get("total_seconds") or 0.0)
        prior_tests = previous.get("tests") or {}
        if prior_total > 0 and total > 0:
            scale = total / prior_total
            print(f"\nmachine speed versus baseline: ×{scale:.2f} "
                  f"({prior_total:.1f}s → {total:.1f}s for the same suite)")
            drifted = []
            for o in observations:
                before = prior_tests.get(o.name)
                # Sub-second tests are dominated by process start-up, so their
                # ratios are noise; comparing them would bury the real signal.
                if not before or before < 0.5:
                    continue
                ratio = o.seconds / (before * scale)
                if ratio >= 1.25:
                    drifted.append((ratio, o, before))
            if drifted:
                print("\nslower than the machine explains:")
                for ratio, o, before in sorted(drifted, reverse=True, key=lambda x: x[0]):
                    print(f"  ×{ratio:.2f}  {before:.2f}s → {o.seconds:.2f}s  {o.name}")
            else:
                print("\nno test is slower than the machine explains")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "total_seconds": total,
                    "sanitizer": args.sanitizer,
                    "tests": {o.name: o.seconds for o in observations},
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
