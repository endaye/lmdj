#!/usr/bin/env python3
"""Fail-closed admission control for LMDJ native-heavy CI jobs."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys


_SCOPE_SPEC = importlib.util.spec_from_file_location(
    "change_scope", Path(__file__).with_name("change_scope.py")
)
if _SCOPE_SPEC is None or _SCOPE_SPEC.loader is None:
    raise RuntimeError("cannot load change scope validator")
change_scope = importlib.util.module_from_spec(_SCOPE_SPEC)
sys.modules[_SCOPE_SPEC.name] = change_scope
_SCOPE_SPEC.loader.exec_module(change_scope)


FORMAL_RESULTS = frozenset({"success", "failure", "cancelled", "skipped"})
GATING_JOBS = (
    "docs-static", "ci-contract", "deploy-contract", "chameleon-lab",
    "web-toolchain-conformance", "web-runtime-host", "creator-web",
    "web-runtime-lab",
)
HEAVY_JOBS = (
    "portal", "core-ubuntu", "package", "core-coverage", "core-asan",
)
_DISPLAY_NAMES = {
    "docs-static": "Docs / static",
    "ci-contract": "CI contract",
    "deploy-contract": "Deploy contract",
    "chameleon-lab": "Chameleon Lab",
    "web-toolchain-conformance": "Web toolchain conformance",
    "web-runtime-host": "Web Runtime Host",
    "creator-web": "Creator Web",
    "web-runtime-lab": "Web Runtime Lab",
}


@dataclass(frozen=True)
class PhaseGateReport:
    ok: bool
    errors: tuple[str, ...]
    primary_failures: tuple[str, ...]
    unexpected_skips: tuple[str, ...]
    scope_skips: tuple[str, ...]


def _diagnostic(why: str, remedy: str) -> str:
    return f"why: {why}; remedy: {remedy}"


def _invalid(error: Exception | str) -> PhaseGateReport:
    return PhaseGateReport(
        False,
        (_diagnostic(
            f"phase-gate input is invalid ({error})",
            "provide the validated scope manifest and the exact eight job results",
        ),),
        (), (), (),
    )


def normalize_needs(needs: Mapping[str, object]) -> dict[str, str]:
    """Extract direct dependency result strings from GitHub's needs JSON."""
    if not isinstance(needs, Mapping):
        raise ValueError("needs JSON must be an object")
    normalized: dict[str, str] = {}
    for job in sorted(needs):
        entry = needs[job]
        if not isinstance(job, str) or not isinstance(entry, Mapping):
            raise ValueError("needs JSON entries must be job objects")
        if "result" not in entry or not isinstance(entry["result"], str):
            raise ValueError(f"result for {job} must be a string")
        normalized[job] = entry["result"]
    return normalized


def _display(job: str) -> str:
    return f"{_DISPLAY_NAMES.get(job, job)} (`{job}`)"


def _topology_contradiction(job: str, result: object) -> str:
    return _diagnostic(
        f"unselected {_display(job)} reported {result!r} instead of skipped",
        "keep unselected preflight jobs skipped and pass the direct needs result",
    )


def validate_phase_gate(
    policy: Mapping[str, object], manifest: Mapping[str, object],
    results: Mapping[str, str], *, change_scope_result: str = "success",
) -> PhaseGateReport:
    """Validate selected-success/unselected-skipped preflight results."""
    try:
        change_scope._validate_policy(policy)
        change_scope.validate_manifest(manifest, policy)
    except (KeyError, TypeError, ValueError) as error:
        return _invalid(error)

    if change_scope_result != "success":
        return PhaseGateReport(
            False,
            (_diagnostic(
                f"Change Scope produced {change_scope_result!r} instead of success",
                "repair Change Scope and rerun before admitting native-heavy work",
            ),),
            (), (), (),
        )
    if not isinstance(results, Mapping):
        return _invalid("results must be an object")

    errors: list[str] = []
    keys = set(results)
    expected = set(GATING_JOBS)
    for job in sorted(expected - keys):
        errors.append(_diagnostic(
            f"preflight result key set is missing {_display(job)}",
            "pass exactly the eight direct preflight dependency results",
        ))
    for job in sorted(keys - expected):
        errors.append(_diagnostic(
            f"preflight result key set has extra {job!r}",
            "pass exactly the eight direct preflight dependency results",
        ))
    for job in GATING_JOBS:
        if job in results and (
            not isinstance(results[job], str) or results[job] not in FORMAL_RESULTS
        ):
            errors.append(_diagnostic(
                f"{_display(job)} has unknown result {results[job]!r}",
                "pass one of success, failure, cancelled, or skipped",
            ))

    selected = set(manifest["required_jobs"]) & set(GATING_JOBS)
    primary_failures: list[str] = []
    unexpected_skips: list[str] = []
    scope_skips: list[str] = []
    for job in GATING_JOBS:
        if job not in results:
            continue
        result = results[job]
        if not isinstance(result, str) or result not in FORMAL_RESULTS:
            continue
        if job in selected and result == "success":
            continue
        if job in selected and result in {"failure", "cancelled"}:
            primary_failures.append(job)
            errors.append(_diagnostic(
                f"selected {_display(job)} is {result}",
                "repair or rerun that selected preflight job before native-heavy work",
            ))
        elif job in selected and result == "skipped":
            unexpected_skips.append(job)
            errors.append(_diagnostic(
                f"selected {_display(job)} was skipped",
                "ensure its lane and trusted-head guard admit the selected job",
            ))
        elif result == "skipped":
            scope_skips.append(job)
        else:
            errors.append(_topology_contradiction(job, result))

    return PhaseGateReport(
        not errors,
        tuple(errors),
        tuple(sorted(primary_failures)),
        tuple(sorted(unexpected_skips)),
        tuple(sorted(scope_skips)),
    )


def render_summary(report: PhaseGateReport) -> str:
    """Render only observed result categories; never infer a root cause."""
    rows = [
        "| Pre-heavy gate | Value |",
        "| --- | --- |",
        f"| Result | {'pass' if report.ok else 'fail'} |",
        "| Primary failure | "
        f"{', '.join(_display(job) for job in report.primary_failures) or 'none'} |",
        "| Unexpected skip | "
        f"{', '.join(_display(job) for job in report.unexpected_skips) or 'none'} |",
        "| Scope skip | "
        f"{', '.join(_display(job) for job in report.scope_skips) or 'none'} |",
    ]
    rows.extend(f"| Error | {error} |" for error in report.errors)
    return "\n".join(rows) + "\n"


def _load_json(path_or_json: str) -> object:
    return json.loads(path_or_json, object_pairs_hook=change_scope.reject_duplicates)


def _write(path: str | Path, contents: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--manifest-json", required=True)
    parser.add_argument("--results-json", required=True)
    parser.add_argument("--change-scope-result", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args(argv)
    try:
        policy = change_scope.load_policy(args.policy)
        manifest = _load_json(args.manifest_json)
        needs = _load_json(args.results_json)
        if not isinstance(manifest, Mapping):
            raise ValueError("manifest JSON must be an object")
        report = validate_phase_gate(
            policy, manifest, normalize_needs(needs),
            change_scope_result=args.change_scope_result,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        report = _invalid(error)
    _write(args.summary, render_summary(report))
    for error in report.errors:
        print(error, file=sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
