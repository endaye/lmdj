"""Score Needle over a fixed intent set and report where it breaks.

Three things are measured separately, because they fail for different reasons:

* **routing** - did it pick the right tool (and stay silent when it should)?
* **schema** - once Host plumbing is merged in, does the production schema
  accept the payload?
* **arguments** - are the values the ones the utterance actually named?

A run that routes perfectly but fills `bpm: 120` for "set the tempo to 96" is
useless, so argument accuracy is never folded into the routing number.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from .runtime import HostContext, NeedleRouter, Resolution

DEFAULT_PROMPTS = Path(__file__).resolve().parents[1] / "prompts" / "performance_intents.jsonl"


@dataclass(frozen=True)
class Case:
    utterance: str
    expect_tool: str | None
    expect_args: dict


def load_cases(path: Path) -> tuple[Case, ...]:
    cases = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{number}: {error}") from error
        cases.append(
            Case(
                utterance=row["utterance"],
                expect_tool=row.get("expect_tool"),
                expect_args=row.get("expect_args") or {},
            )
        )
    if not cases:
        raise ValueError(f"{path}: no cases")
    return tuple(cases)


def _matches_subset(expected: dict, actual: object) -> bool:
    """Expected args are a subset check, recursing into nested objects."""
    if not isinstance(actual, dict):
        return False
    for key, value in expected.items():
        if key not in actual:
            return False
        if isinstance(value, dict):
            if not _matches_subset(value, actual[key]):
                return False
        elif isinstance(value, bool) or isinstance(actual[key], bool):
            if value is not actual[key]:
                return False
        elif actual[key] != value:
            return False
    return True


@dataclass
class Scored:
    case: Case
    resolution: Resolution
    routed: bool
    args_ok: bool | None  # None when the case declares no argument expectation


def score(case: Case, resolution: Resolution) -> Scored:
    routed = resolution.tool_name == case.expect_tool
    args_ok: bool | None = None
    if case.expect_args:
        args_ok = routed and _matches_subset(case.expect_args, resolution.model_arguments)
    return Scored(case=case, resolution=resolution, routed=routed, args_ok=args_ok)


def run(
    surface: str, prompts: Path, repeats: int = 1, naming: str = "verb"
) -> tuple[list[Scored], NeedleRouter]:
    router = NeedleRouter(surface=surface, naming=naming)
    host = HostContext()
    scored: list[Scored] = []
    for _ in range(repeats):
        for case in load_cases(prompts):
            # Each utterance is independent; without a reset the engine would
            # carry the previous turn and the scores would not be per-case.
            router.reset()
            scored.append(score(case, router.resolve(case.utterance, host)))
    return scored, router


def report(scored: list[Scored], router: NeedleRouter, verbose: bool) -> dict:
    total = len(scored)
    routed = [item for item in scored if item.routed]
    tool_cases = [item for item in scored if item.case.expect_tool is not None]
    silent_cases = [item for item in scored if item.case.expect_tool is None]
    schema_cases = [item for item in scored if item.resolution.payload is not None]
    schema_ok = [item for item in schema_cases if item.resolution.schema_valid]
    arg_cases = [item for item in scored if item.args_ok is not None]
    arg_ok = [item for item in arg_cases if item.args_ok]
    latencies = sorted(item.resolution.latency_ms for item in scored)
    peaks = [
        item.resolution.peak_ram_mb
        for item in scored
        if item.resolution.peak_ram_mb is not None
    ]

    def pct(part: list, whole: list) -> str:
        return f"{len(part)}/{len(whole)}" + (
            f" ({100.0 * len(part) / len(whole):.0f}%)" if whole else ""
        )

    print(f"surface           {router.surface} ({len(router.tools)} tools), {router.naming} names")
    print(f"package / engine  cactus-needle {router.package_version} / {router.engine_version}")
    print(f"agent init        {router.init_ms:.0f} ms")
    print()
    print(f"routing           {pct(routed, scored)}")
    print(f"  tool expected   {pct([i for i in tool_cases if i.routed], tool_cases)}")
    print(f"  silence wanted  {pct([i for i in silent_cases if i.routed], silent_cases)}")
    print(f"schema valid      {pct(schema_ok, schema_cases)}  (of calls that proposed a payload)")
    print(f"arguments correct {pct(arg_ok, arg_cases)}")
    print()
    if latencies:
        print(
            f"latency ms        p50 {statistics.median(latencies):.0f}"
            f"  p95 {latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]:.0f}"
            f"  max {latencies[-1]:.0f}"
        )
    if peaks:
        print(f"peak rss mb       {max(peaks):.1f}")

    # The number that decides whether this is shippable: of everything the
    # model got wrong, how much would have reached Project Truth unattended?
    misrouted = [item for item in scored if not item.routed]
    escaping = [item for item in misrouted if item.resolution.auto_dispatchable]
    commands_gated = [
        item
        for item in misrouted
        if item.resolution.tool_surface == "command" and item.resolution.schema_valid
    ]
    print()
    print("query/command gate")
    print(f"  misroutes              {len(misrouted)}")
    print(f"  gated as commands      {len(commands_gated)} (need player confirmation)")
    print(f"  auto-dispatched wrong  {len(escaping)} (read-only, no state change)")

    if router.naming == "verb" and any(
        item.resolution.confidence is not None for item in scored
    ):
        correct = [
            item.resolution.confidence
            for item in scored
            if item.routed and item.resolution.confidence is not None
        ]
        wrong = [
            item.resolution.confidence
            for item in misrouted
            if item.resolution.confidence is not None
        ]
        if correct and wrong:
            print(
                f"  confidence median      correct {statistics.median(correct):.3f}"
                f"  wrong {statistics.median(wrong):.3f}"
            )

    failures = [
        item
        for item in scored
        if not item.routed
        or item.args_ok is False
        or (item.resolution.payload is not None and not item.resolution.schema_valid)
    ]
    if failures:
        print()
        print(f"failures ({len(failures)})")
        for item in failures:
            got = item.resolution.tool_name or f"<{item.resolution.envelope_type}>"
            print(f"  {item.case.utterance!r}")
            print(f"      expected {item.case.expect_tool}  got {got}")
            if item.args_ok is False:
                print(
                    f"      args     wanted {item.case.expect_args}"
                    f"  got {item.resolution.model_arguments}"
                )
            for reason in item.resolution.schema_reasons:
                print(f"      schema   {reason}")
            if item.resolution.error:
                print(f"      error    {item.resolution.error}")

    if verbose:
        print()
        print("all cases")
        for item in scored:
            mark = "ok " if item.routed and item.args_ok is not False else "BAD"
            confidence = item.resolution.confidence
            shown = f"{confidence:.2f}" if confidence is not None else "  - "
            print(
                f"  {mark} conf {shown}  {item.resolution.latency_ms:6.0f}ms"
                f"  {item.resolution.tool_name or '-':38s} {item.case.utterance}"
            )

    return {
        "total": total,
        "routed": len(routed),
        "schema_valid": len(schema_ok),
        "schema_checked": len(schema_cases),
        "arguments_correct": len(arg_ok),
        "arguments_checked": len(arg_cases),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="needle-spike-bench",
        description="Score the Needle 45M model over the LMDJ MCP tool surface.",
    )
    parser.add_argument("--surface", choices=("performance", "full"), default="performance")
    parser.add_argument(
        "--naming",
        choices=("verb", "mcp"),
        default="verb",
        help="verb aliases (default) or raw MCP wire names",
    )
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON too")
    arguments = parser.parse_args(argv)

    scored, router = run(
        arguments.surface, arguments.prompts, arguments.repeats, arguments.naming
    )
    summary = report(scored, router, arguments.verbose)
    if arguments.json:
        print()
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
