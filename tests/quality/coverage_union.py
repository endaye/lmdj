#!/usr/bin/env python3
"""Union warning-free per-module LLVM LCOV exports by source identity."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


source_prefixes = (
    "packages/",
    "providers/",
    "products/lmdj/",
    "apps/core-cli/",
)
LineKey = int
BranchKey = tuple[int, int, int]


class CoverageError(RuntimeError):
    """Coverage fragments cannot form an authoritative first-party union."""


@dataclass
class FileCoverage:
    lines: dict[LineKey, int] = field(default_factory=dict)
    branches: dict[BranchKey, int] = field(default_factory=dict)

    def add_line(self, line: LineKey, count: int) -> None:
        self.lines[line] = self.lines.get(line, 0) + count

    def add_branch(self, branch: BranchKey, count: int) -> None:
        self.branches[branch] = self.branches.get(branch, 0) + count


def source_path(filename: str, repo_root: Path) -> str | None:
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


def parse_lcov(path: Path, repo_root: Path) -> dict[str, FileCoverage]:
    files: dict[str, FileCoverage] = {}
    current: FileCoverage | None = None

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if raw_line.startswith("SF:"):
            relative_path = source_path(raw_line[3:], repo_root)
            current = (
                files.setdefault(relative_path, FileCoverage())
                if relative_path is not None
                else None
            )
            continue
        if current is None:
            continue
        if raw_line.startswith("DA:"):
            fields = raw_line[3:].split(",")
            if len(fields) < 2:
                raise CoverageError(
                    f"{path}:{line_number}: malformed LCOV line record"
                )
            current.add_line(int(fields[0]), int(fields[1]))
            continue
        if raw_line.startswith("BRDA:"):
            fields = raw_line[5:].split(",")
            if len(fields) != 4:
                raise CoverageError(
                    f"{path}:{line_number}: malformed LCOV branch record"
                )
            taken = 0 if fields[3] == "-" else int(fields[3])
            current.add_branch(
                (int(fields[0]), int(fields[1]), int(fields[2])),
                taken,
            )

    return files


def percentage(covered: int, count: int) -> float:
    if count == 0:
        return 0.0
    return covered * 100.0 / count


def metric(counts: dict[int | tuple[int, int, int], int]) -> dict[str, int | float]:
    count = len(counts)
    covered = sum(value > 0 for value in counts.values())
    return {
        "count": count,
        "covered": covered,
        "notcovered": count - covered,
        "percent": percentage(covered, count),
    }


def validate_and_union(
    topology: dict[str, FileCoverage],
    fragments: list[dict[str, FileCoverage]],
) -> dict[str, FileCoverage]:
    if not topology:
        raise CoverageError("coverage topology contains no first-party source")
    if not fragments:
        raise CoverageError("coverage union requires at least one fragment")

    measured: dict[str, FileCoverage] = {}
    for fragment in fragments:
        for path, coverage in fragment.items():
            destination = measured.setdefault(path, FileCoverage())
            for line, count in coverage.lines.items():
                destination.add_line(line, count)
            for branch, count in coverage.branches.items():
                destination.add_branch(branch, count)

    missing: list[str] = []
    extra: list[str] = []
    for path in sorted(set(topology) | set(measured)):
        expected = topology.get(path, FileCoverage())
        actual = measured.get(path, FileCoverage())
        missing_lines = sorted(set(expected.lines) - set(actual.lines))
        missing_branches = sorted(set(expected.branches) - set(actual.branches))
        extra_lines = sorted(set(actual.lines) - set(expected.lines))
        extra_branches = sorted(set(actual.branches) - set(expected.branches))
        if missing_lines or missing_branches:
            missing.append(
                f"{path} "
                f"(lines={len(missing_lines)}, branches={len(missing_branches)})"
            )
        if extra_lines or extra_branches:
            extra.append(
                f"{path} "
                f"(lines={len(extra_lines)}, branches={len(extra_branches)})"
            )

    if missing:
        raise CoverageError(
            "coverage fragments are missing topology regions: "
            + "; ".join(missing)
        )
    if extra:
        raise CoverageError(
            "coverage fragments contain regions outside topology: "
            + "; ".join(extra)
        )

    return measured


def build_summary(
    coverage: dict[str, FileCoverage],
    repo_root: Path,
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    total_lines: dict[tuple[str, LineKey], int] = {}
    total_branches: dict[tuple[str, BranchKey], int] = {}

    for path, file_coverage in sorted(coverage.items()):
        lines = metric(file_coverage.lines)
        branches = metric(file_coverage.branches)
        files.append(
            {
                "filename": str(repo_root / path),
                "summary": {
                    "lines": lines,
                    "branches": branches,
                },
            }
        )
        total_lines.update(
            {(path, key): value for key, value in file_coverage.lines.items()}
        )
        total_branches.update(
            {
                (path, key): value
                for key, value in file_coverage.branches.items()
            }
        )

    return {
        "type": "llvm.coverage.json.export",
        "version": "3.0.1",
        "data": [
            {
                "files": files,
                "totals": {
                    "lines": metric(total_lines),
                    "branches": metric(total_branches),
                },
            }
        ],
    }


def display_percentage(covered: int, count: int) -> str:
    return f"{percentage(covered, count):.2f}%"


def build_report(coverage: dict[str, FileCoverage]) -> str:
    rows: list[tuple[str, int, int, int, int]] = []
    for path, file_coverage in sorted(coverage.items()):
        line_count = len(file_coverage.lines)
        line_covered = sum(value > 0 for value in file_coverage.lines.values())
        branch_count = len(file_coverage.branches)
        branch_covered = sum(
            value > 0 for value in file_coverage.branches.values()
        )
        rows.append(
            (path, line_count, line_covered, branch_count, branch_covered)
        )

    filename_width = max(
        len("Filename"),
        len("TOTAL"),
        *(len(row[0]) for row in rows),
    )
    header = (
        f"{'Filename':<{filename_width}}  "
        f"{'Lines':>7}  {'Missed Lines':>12}  {'Cover':>7}  "
        f"{'Branches':>8}  {'Missed Branches':>15}  {'Cover':>7}"
    )
    separator = "-" * len(header)
    output = [header, separator]
    for path, line_count, line_covered, branch_count, branch_covered in rows:
        output.append(
            f"{path:<{filename_width}}  "
            f"{line_count:>7}  {line_count - line_covered:>12}  "
            f"{display_percentage(line_covered, line_count):>7}  "
            f"{branch_count:>8}  {branch_count - branch_covered:>15}  "
            f"{display_percentage(branch_covered, branch_count):>7}"
        )

    total_line_count = sum(row[1] for row in rows)
    total_line_covered = sum(row[2] for row in rows)
    total_branch_count = sum(row[3] for row in rows)
    total_branch_covered = sum(row[4] for row in rows)
    output.extend(
        [
            separator,
            f"{'TOTAL':<{filename_width}}  "
            f"{total_line_count:>7}  "
            f"{total_line_count - total_line_covered:>12}  "
            f"{display_percentage(total_line_covered, total_line_count):>7}  "
            f"{total_branch_count:>8}  "
            f"{total_branch_count - total_branch_covered:>15}  "
            f"{display_percentage(total_branch_covered, total_branch_count):>7}",
        ]
    )
    return "\n".join(output) + "\n"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--fragment", type=Path, action="append", default=[])
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    args.summary.unlink(missing_ok=True)
    args.report.unlink(missing_ok=True)
    try:
        repo_root = args.repo_root.resolve()
        topology = parse_lcov(args.topology, repo_root)
        fragments = [
            parse_lcov(fragment, repo_root) for fragment in args.fragment
        ]
        coverage = validate_and_union(topology, fragments)
        summary = build_summary(coverage, repo_root)
        report = build_report(coverage)
    except (CoverageError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"coverage union failed: {error}", file=sys.stderr)
        return 1

    atomic_write(
        args.summary,
        json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n",
    )
    atomic_write(args.report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
