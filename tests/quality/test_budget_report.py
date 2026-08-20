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
ADD_TEST = re.compile(r"lmdj_add_test\((?P<body>.*?)\n\s*\)", re.S)
FIELD = {
    "name": re.compile(r"NAME\s+(\S+)"),
    "tier": re.compile(r"TIER\s+(\S+)"),
    "timeout": re.compile(r"TIMEOUT\s+(\d+)"),
}
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
        for match in ADD_TEST.finditer(text):
            body = match.group("body")
            name = FIELD["name"].search(body)
            tier = FIELD["tier"].search(body)
            if name is None or tier is None:
                continue
            explicit = FIELD["timeout"].search(body)
            base = int(explicit.group(1)) if explicit else tiers.get(tier.group(1))
            if base:
                budgets[name.group(1)] = base * multiplier
    return budgets


def parse_run(text: str, budgets: dict[str, float]) -> tuple[list[Observation], float]:
    observations = [
        Observation(
            name=m.group("name"),
            status=m.group("status").lstrip("*"),
            seconds=float(m.group("seconds")),
            budget=budgets.get(m.group("name")),
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
