#!/usr/bin/env python3
"""Fail closed when PR jobs do not exactly match the scope manifest."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_SCOPE_SPEC = importlib.util.spec_from_file_location(
    "change_scope", Path(__file__).with_name("change_scope.py")
)
if _SCOPE_SPEC is None or _SCOPE_SPEC.loader is None:
    raise RuntimeError("cannot load change scope validator")
change_scope = importlib.util.module_from_spec(_SCOPE_SPEC)
sys.modules[_SCOPE_SPEC.name] = change_scope
_SCOPE_SPEC.loader.exec_module(change_scope)


FORMAL_RESULTS = {"success", "failure", "cancelled", "skipped"}


@dataclass(frozen=True)
class GateReport:
    ok: bool
    errors: tuple[str, ...]
    requested_jobs: tuple[str, ...]
    skipped_jobs: tuple[str, ...]


def normalize_needs(needs: Mapping[str, object]) -> dict[str, str]:
    """Extract only direct dependency result values from GitHub needs JSON."""
    if not isinstance(needs, Mapping):
        raise ValueError("needs JSON must be an object")
    normalized: dict[str, str] = {}
    for job in sorted(needs):
        entry = needs[job]
        if not isinstance(job, str) or not isinstance(entry, Mapping):
            raise ValueError("needs JSON entries must be job objects")
        if "result" not in entry:
            raise ValueError(f"missing result for {job}")
        if not isinstance(entry["result"], str):
            raise ValueError(f"result for {job} must be a string")
        normalized[job] = entry["result"]
    return normalized


def _invalid(error: Exception) -> GateReport:
    return GateReport(False, (f"invalid policy or manifest: {error}",), (), ())


def _formal_jobs(policy: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(sorted({
        job for jobs in policy["lane_jobs"].values() for job in jobs
    }))


def validate_gate(
    policy: Mapping[str, object], manifest: Mapping[str, object],
    results: Mapping[str, str], expected_head_sha: str,
) -> GateReport:
    """Return the exact selected-success/unselected-skipped gate decision."""
    try:
        change_scope._validate_policy(policy)
        change_scope.validate_manifest(manifest, policy)
        expected_head = change_scope._validate_sha(expected_head_sha)
    except (KeyError, TypeError, ValueError) as error:
        return _invalid(error)

    requested = tuple(sorted(manifest["required_jobs"]))
    expected_requested = tuple(sorted({
        job for lane, enabled in manifest["lanes"].items() if enabled
        for job in policy["lane_jobs"][lane]
    }))
    if requested != expected_requested:
        return GateReport(
            False, ("required jobs do not derive from selected lanes",), (), (),
        )
    skipped = tuple(job for job in _formal_jobs(policy) if job not in requested)
    errors: list[str] = []
    if manifest["head_sha"].lower() != expected_head:
        errors.append(
            f"manifest head SHA {manifest['head_sha']} does not match expected {expected_head}"
        )
    if not isinstance(results, Mapping):
        errors.append("results must be an object")
        return GateReport(False, tuple(errors), requested, skipped)
    formal = _formal_jobs(policy)
    result_keys = set(results)
    expected_keys = set(formal)
    for job in sorted(expected_keys - result_keys):
        errors.append(f"result key set mismatch: missing {job}")
    for job in sorted(result_keys - expected_keys):
        errors.append(f"result key set mismatch: extra {job}")
    if errors:
        return GateReport(False, tuple(errors), requested, skipped)
    for job in formal:
        result = results[job]
        if not isinstance(result, str) or result not in FORMAL_RESULTS:
            errors.append(f"unknown result for {job}: {result}")
    if errors:
        return GateReport(False, tuple(errors), requested, skipped)
    for job in requested:
        if results[job] != "success":
            errors.append(f"selected job {job} is {results[job]}, expected success")
    for job in skipped:
        if results[job] != "skipped":
            errors.append(f"unselected job {job} is {results[job]}, expected skipped")
    return GateReport(not errors, tuple(errors), requested, skipped)


def read_actions_jobs(repository: str, run_id: str, token: str | None = None) -> list[dict[str, object]]:
    """Read every job for an Actions run with the standard library only."""
    if not repository or not run_id:
        raise ValueError("repository and run ID are required for timing")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    jobs: list[dict[str, object]] = []
    page = 1
    while True:
        query = urlencode({"per_page": 100, "page": page})
        request = Request(
            f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs?{query}",
            headers=headers,
        )
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ValueError("invalid Actions jobs response")
        batch = payload["jobs"]
        if not all(isinstance(job, dict) for job in batch):
            raise ValueError("invalid Actions job")
        jobs.extend(batch)
        if len(batch) < 100:
            return jobs
        page += 1


def _seconds(start: str, end: str) -> float:
    return (datetime.fromisoformat(end.replace("Z", "+00:00")) -
            datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()


def _job_slo(policy: Mapping[str, object], job_name: str) -> int | None:
    values = [policy["slo_seconds"][lane] for lane, jobs in policy["lane_jobs"].items()
              if job_name in jobs and lane in policy["slo_seconds"]]
    return min(values) if values else None


def render_summary(
    report: GateReport, policy: Mapping[str, object],
    timing_reader: Callable[[], Sequence[Mapping[str, object]]] | None = None,
) -> str:
    """Render gate evidence; timing observations are intentionally non-blocking."""
    rows = ["| PR gate | Value |", "| --- | --- |",
            f"| Result | {'pass' if report.ok else 'fail'} |",
            f"| Required jobs | {', '.join(report.requested_jobs) or 'none'} |",
            f"| Skipped jobs | {', '.join(report.skipped_jobs) or 'none'} |"]
    for error in report.errors:
        rows.append(f"| Error | {error} |")
    if timing_reader is None:
        rows.append("| Timing | timing unavailable |")
        return "\n".join(rows) + "\n"
    try:
        jobs = timing_reader()
        if not isinstance(jobs, Sequence):
            raise ValueError("jobs response is not a sequence")
        formal = set(_formal_jobs(policy))
        timing_rows = 0
        timing_incomplete = False
        for job in jobs:
            name = job.get("name")
            if not isinstance(name, str) or name not in formal:
                continue
            created, started, completed = (job.get("created_at"), job.get("started_at"), job.get("completed_at"))
            if not all(isinstance(value, str) for value in (created, started, completed)):
                timing_incomplete = True
                continue
            queue_seconds = _seconds(created, started)
            execution_seconds = _seconds(started, completed)
            slo = _job_slo(policy, name)
            status = "SLO missed" if slo is not None and max(queue_seconds, execution_seconds) > slo else "within SLO"
            rows.append(f"| Timing {name} | queue {queue_seconds:.0f}s; execution {execution_seconds:.0f}s; {status} |")
            timing_rows += 1
        if not timing_rows or timing_incomplete:
            rows.append("| Timing | timing unavailable |")
    except (OSError, ValueError, TypeError, KeyError):
        rows.append("| Timing | timing unavailable |")
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
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args(argv)
    try:
        policy = change_scope.load_policy(args.policy)
        manifest = _load_json(args.manifest_json)
        needs = _load_json(args.results_json)
        if not isinstance(manifest, Mapping):
            raise ValueError("manifest JSON must be an object")
        report = validate_gate(policy, manifest, normalize_needs(needs), args.head_sha)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        report = GateReport(False, (f"PR gate failed closed: {error}",), (), ())
    repository, run_id = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    timing_reader = None
    if repository and run_id and 'policy' in locals():
        timing_reader = lambda: read_actions_jobs(repository, run_id, os.environ.get("GITHUB_TOKEN"))
    _write(args.summary, render_summary(report, policy if 'policy' in locals() else {}, timing_reader))
    for error in report.errors:
        print(error, file=sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
