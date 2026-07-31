#!/usr/bin/env python3
"""Apply per-path line and branch thresholds to LLVM coverage export JSON."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any


repo_root = Path(__file__).resolve().parents[2]
source_prefixes = (
    "packages/",
    "providers/",
    "products/lmdj/",
    "apps/core-cli/",
)


@dataclass
class Totals:
    file_count: int = 0
    line_count: int = 0
    line_covered: int = 0
    branch_count: int = 0
    branch_covered: int = 0

    def add(self, summary: dict[str, Any]) -> None:
        self.file_count += 1
        lines = summary["lines"]
        branches = summary["branches"]
        self.line_count += int(lines["count"])
        self.line_covered += int(lines["covered"])
        self.branch_count += int(branches["count"])
        self.branch_covered += int(branches["covered"])


def source_path(filename: str) -> str | None:
    path = Path(filename)
    if path.is_absolute():
        try:
            path = path.relative_to(repo_root)
        except ValueError:
            return None

    normalized = PurePosixPath(path.as_posix()).as_posix()
    if not normalized.startswith(source_prefixes):
        return None
    if normalized.endswith(".cpp"):
        return normalized
    if normalized.endswith(".hpp") and "/include/" in f"/{normalized}":
        return normalized
    return None


def load_files(summary_path: Path) -> list[tuple[str, dict[str, Any]]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    files: list[tuple[str, dict[str, Any]]] = []
    for data in summary.get("data", []):
        for file_ in data.get("files", []):
            relative_path = source_path(file_["filename"])
            if relative_path is not None:
                files.append((relative_path, file_["summary"]))
    return files


def percentage(covered: int, count: int) -> Decimal:
    return Decimal(covered) * Decimal(100) / Decimal(count)


def display_percentage(value: Decimal) -> str:
    return f"{value:.2f}%"


def evaluate(
    label: str,
    totals: Totals,
    thresholds: dict[str, int | float],
) -> tuple[str, list[str]]:
    line_required = Decimal(str(thresholds["lines"]))
    branch_required = Decimal(str(thresholds["branches"]))
    required_display = (
        f"lines 0.00% required {display_percentage(line_required)}; "
        f"branches 0.00% required {display_percentage(branch_required)}"
    )
    if totals.file_count == 0:
        message = f"{label}: missing configured path ({required_display})"
        return message, [message]
    if totals.line_count == 0:
        message = f"{label}: no executable regions ({required_display})"
        return message, [message]

    line_actual = percentage(totals.line_covered, totals.line_count)
    branch_actual = (
        percentage(totals.branch_covered, totals.branch_count)
        if totals.branch_count
        else Decimal(0)
    )
    row = (
        f"{label}: "
        f"lines {display_percentage(line_actual)} "
        f"({totals.line_covered}/{totals.line_count}, "
        f"required {display_percentage(line_required)}); "
        f"branches {display_percentage(branch_actual)} "
        f"({totals.branch_covered}/{totals.branch_count}, "
        f"required {display_percentage(branch_required)})"
    )
    failures: list[str] = []
    if line_actual < line_required:
        failures.append(
            f"{label}: lines {display_percentage(line_actual)} "
            f"required {display_percentage(line_required)}"
        )
    if branch_actual < branch_required:
        failures.append(
            f"{label}: branches {display_percentage(branch_actual)} "
            f"required {display_percentage(branch_required)}"
        )
    return row, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path, required=True)
    args = parser.parse_args()

    files = load_files(args.summary)
    configured = json.loads(args.thresholds.read_text(encoding="utf-8"))
    rows: list[str] = []
    failures: list[str] = []

    overall = Totals()
    for _, summary in files:
        overall.add(summary)
    row, current_failures = evaluate("overall", overall, configured["overall"])
    rows.append(row)
    failures.extend(current_failures)

    for prefix, thresholds in sorted(configured.get("paths", {}).items()):
        totals = Totals()
        for path, summary in files:
            if path.startswith(prefix):
                totals.add(summary)
        row, current_failures = evaluate(prefix, totals, thresholds)
        rows.append(row)
        failures.extend(current_failures)

    print("\n".join(rows))
    if failures:
        print("Core coverage gate: FAIL")
        print("\n".join(failures))
        return 1

    print("Core coverage gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
