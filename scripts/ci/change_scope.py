#!/usr/bin/env python3
"""Classify a complete Git change inventory into the closed LMDJ CI lanes."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ChangedFile:
    status: str
    paths: tuple[str, ...]


ALLOWED_MANIFEST_KEYS = {
    "schema", "base_sha", "head_sha", "mode", "reasons",
    "changed_files", "lanes", "required_jobs",
}
ALLOWED_MODES = {"draft", "focused", "full"}
ALLOWED_RESULTS = {"added", "copied", "deleted", "modified", "renamed", "type_changed"}

_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_STATUS_RESULTS = {
    "A": "added", "C": "copied", "D": "deleted", "M": "modified",
    "R": "renamed", "T": "type_changed",
}
_CANONICAL_LANES = (
    "docs_static", "portal", "ci_contract", "core_ubuntu", "core_asan",
    "core_coverage", "core_macos", "web_toolchain", "web_runtime_host",
    "creator", "web_runtime_lab", "deploy_contract", "chameleon_lab", "package",
)
_CANONICAL_LANE_JOBS = {
    "docs_static": ("docs-static",),
    "portal": ("portal",),
    "ci_contract": ("ci-contract",),
    "core_ubuntu": ("select-ubuntu-runner", "core-ubuntu"),
    "core_asan": ("select-ubuntu-runner", "core-asan"),
    "core_coverage": ("select-ubuntu-runner", "core-coverage"),
    "core_macos": ("select-macos-runner", "macos-primary", "core-macos", "core-asan-macos"),
    "web_toolchain": ("web-toolchain-conformance",),
    "web_runtime_host": ("select-ubuntu-runner", "web-runtime-host"),
    "creator": ("creator-web",),
    "web_runtime_lab": ("select-ubuntu-runner", "web-runtime-lab"),
    "deploy_contract": ("deploy-contract",),
    "chameleon_lab": ("chameleon-lab",),
    "package": ("package",),
}
_MANDATORY_FULL_MATCHES = {
    ("exact", ".github/workflows/ci.yml"),
    ("prefix", "scripts/ci/"),
    ("prefix", ".github/actions/configure-build-acceleration/"),
}
_POLICY_KEYS = {
    "schema", "manifest_schema", "lanes", "lane_jobs", "known_top_levels",
    "full_rules", "rules", "expensive_families", "expensive_family_exemptions",
    "draft_lanes", "slo_seconds",
}


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_sha(sha: str) -> str:
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        raise ValueError("SHA must be exactly 40 hexadecimal characters")
    return sha.lower()


def _validate_path(path: str) -> None:
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
        raise ValueError(f"noncanonical path: {path!r}")
    components = path.split("/")
    if any(component in {"", ".", ".."} for component in components):
        raise ValueError(f"noncanonical path: {path!r}")


def _validate_changed_status(status: object) -> str:
    if not isinstance(status, str) or not status:
        raise ValueError("unsupported changed-file status")
    code = status[0]
    if code in {"A", "D", "M", "T"} and status == code:
        return code
    if code in {"C", "R"} and re.fullmatch(r"[CR](?:[0-9]{1,3})?", status):
        score = status[1:]
        if not score or int(score) <= 100:
            return code
    raise ValueError(f"unsupported changed-file status: {status!r}")


def parse_name_status_z(payload: bytes) -> tuple[ChangedFile, ...]:
    """Parse ``git diff --name-status -z`` without losing rename old paths."""
    if not isinstance(payload, bytes) or not payload:
        return ()
    fields = payload.split(b"\0")
    if fields[-1] != b"":
        raise ValueError("name-status inventory is not NUL terminated")
    fields.pop()
    records: list[ChangedFile] = []
    seen_paths: set[str] = set()
    position = 0
    while position < len(fields):
        try:
            status = fields[position].decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            raise ValueError("status is not UTF-8") from error
        position += 1
        code = _validate_changed_status(status)
        if code in {"R", "C"}:
            if position + 1 >= len(fields):
                raise ValueError(f"invalid rename/copy status: {status!r}")
            raw_paths = fields[position:position + 2]
            position += 2
        else:
            if position >= len(fields):
                raise ValueError(f"invalid status: {status!r}")
            raw_paths = fields[position:position + 1]
            position += 1
        try:
            paths = tuple(item.decode("utf-8", "strict") for item in raw_paths)
        except UnicodeDecodeError as error:
            raise ValueError("path is not UTF-8") from error
        for path in paths:
            _validate_path(path)
            if path in seen_paths:
                raise ValueError(f"duplicate logical path: {path}")
            seen_paths.add(path)
        records.append(ChangedFile(status, paths))
    return tuple(records)


def _validate_match(match: object) -> None:
    if not isinstance(match, dict) or set(match) != {"kind", "value"}:
        raise ValueError("match must contain only kind and value")
    if match["kind"] not in {"exact", "prefix", "suffix"}:
        raise ValueError(f"unknown match kind: {match['kind']!r}")
    if not isinstance(match["value"], str) or not match["value"]:
        raise ValueError("match value must be a nonempty string")


def _validate_policy(policy: Mapping[str, object]) -> None:
    if set(policy) != _POLICY_KEYS:
        raise ValueError("policy schema is not closed")
    if policy["schema"] != "lmdj.ci-scope-policy.v1" or policy["manifest_schema"] != "lmdj.ci-scope.v1":
        raise ValueError("unknown policy schema")
    lanes = policy["lanes"]
    if not isinstance(lanes, list) or tuple(lanes) != _CANONICAL_LANES:
        raise ValueError("lanes do not match the closed v1 allowlist")
    lane_set = set(lanes)
    lane_jobs = policy["lane_jobs"]
    if not isinstance(lane_jobs, dict) or {
        lane: tuple(jobs) if isinstance(jobs, list) else jobs
        for lane, jobs in lane_jobs.items()
    } != _CANONICAL_LANE_JOBS:
        raise ValueError("lane jobs do not match the closed v1 mapping")
    known = policy["known_top_levels"]
    if not isinstance(known, list) or len(known) != len(set(known)) or not all(isinstance(item, str) and item for item in known):
        raise ValueError("invalid known top levels")
    for rule in policy["rules"]:
        if not isinstance(rule, dict) or set(rule) != {"match", "lanes"}:
            raise ValueError("rule schema is not closed")
        _validate_match(rule["match"])
        if not isinstance(rule["lanes"], list) or not rule["lanes"] or not set(rule["lanes"]).issubset(lane_set):
            raise ValueError("rule references unknown lane")
    for rule in policy["full_rules"]:
        if not isinstance(rule, dict) or set(rule) != {"match", "reason"}:
            raise ValueError("full rule schema is not closed")
        _validate_match(rule["match"])
        if not isinstance(rule["reason"], str) or not rule["reason"]:
            raise ValueError("invalid full rule reason")
    full_matches = {
        (rule["match"]["kind"], rule["match"]["value"])
        for rule in policy["full_rules"]
    }
    if not _MANDATORY_FULL_MATCHES.issubset(full_matches):
        raise ValueError("mandatory full-control rules are missing")
    families = policy["expensive_families"]
    if not isinstance(families, dict) or set(families) != {"core", "web-runtime", "creator", "deploy-package"}:
        raise ValueError("invalid expensive families")
    if any(not isinstance(value, list) or not value or not set(value).issubset(lane_set) for value in families.values()):
        raise ValueError("expensive family references unknown lane")
    exemptions = policy["expensive_family_exemptions"]
    if not isinstance(exemptions, list) or not all(isinstance(path, str) and path for path in exemptions):
        raise ValueError("invalid expensive family exemptions")
    if not isinstance(policy["draft_lanes"], list) or set(policy["draft_lanes"]) != {"docs_static", "ci_contract"}:
        raise ValueError("invalid draft lanes")
    if not isinstance(policy["slo_seconds"], dict) or any(not isinstance(value, int) or value <= 0 for value in policy["slo_seconds"].values()):
        raise ValueError("invalid SLO values")


def load_policy(path: str | Path) -> dict[str, object]:
    with Path(path).open(encoding="utf-8") as policy_file:
        policy = json.load(policy_file, object_pairs_hook=reject_duplicates)
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    _validate_policy(policy)
    return policy


def _matches(match: Mapping[str, str], path: str) -> bool:
    kind, value = match["kind"], match["value"]
    return ((kind == "exact" and path == value) or
            (kind == "prefix" and path.startswith(value)) or
            (kind == "suffix" and path.endswith(value)))


def _changed_file_json(record: ChangedFile) -> dict[str, object]:
    result = _STATUS_RESULTS[record.status[0]]
    if result not in ALLOWED_RESULTS:
        raise ValueError("unknown changed file result")
    return {"result": result, "paths": list(record.paths)}


def classify(
    policy: Mapping[str, object], changed: Sequence[ChangedFile], *, base_sha: str,
    head_sha: str, event_name: str, draft: bool, labels: Collection[str],
    force_full: bool = False,
) -> dict[str, object]:
    """Return a deterministic closed v1 scope manifest as a dictionary."""
    _validate_policy(policy)
    base_sha, head_sha = _validate_sha(base_sha), _validate_sha(head_sha)
    lanes = set(policy["lanes"])
    selected: set[str] = set()
    family_selected: set[str] = set()
    reasons: set[str] = set()
    all_paths: set[str] = set()
    for record in changed:
        if not isinstance(record, ChangedFile):
            raise ValueError("invalid changed-file record")
        code = _validate_changed_status(record.status)
        required_paths = 2 if code in {"R", "C"} else 1
        if len(record.paths) != required_paths:
            raise ValueError("invalid changed-file path count")
        for path in record.paths:
            _validate_path(path)
            if path in all_paths:
                raise ValueError(f"duplicate logical path: {path}")
            all_paths.add(path)
            top_level = path.split("/", 1)[0]
            if top_level not in policy["known_top_levels"]:
                reasons.add(f"unknown top-level: {top_level}")
            path_lanes = set()
            for rule in policy["rules"]:
                if _matches(rule["match"], path):
                    path_lanes.update(rule["lanes"])
            if not path_lanes:
                reasons.add(f"unclassified path: {path}")
            selected.update(path_lanes)
            if path not in policy["expensive_family_exemptions"]:
                family_selected.update(path_lanes)
            for rule in policy["full_rules"]:
                if _matches(rule["match"], path):
                    reasons.add(f"full rule: {rule['reason']}")
    full_reasons = set(reasons)
    label_set = set(labels)
    if not all(isinstance(label, str) for label in label_set):
        raise ValueError("labels must be strings")
    if force_full:
        full_reasons.add("forced full")
    if "ci:full" in label_set:
        full_reasons.add("ci:full label")
    if event_name in {"push", "workflow_dispatch"}:
        full_reasons.add(f"full event: {event_name}")
    families = policy["expensive_families"]
    active_families = sorted(
        name for name, family_lanes in families.items() if family_selected.intersection(family_lanes)
    )
    if len(active_families) >= 3:
        full_reasons.add("three expensive families: " + ", ".join(active_families))
    if full_reasons:
        mode = "full"
        true_lanes = lanes
    else:
        mode = "focused"
        true_lanes = selected
    if draft:
        if full_reasons:
            reasons.add("deferred full reason: " + "; ".join(sorted(full_reasons)))
        elif selected - set(policy["draft_lanes"]):
            reasons.add("deferred focused lanes for Ready PR")
        mode = "draft"
        true_lanes = set(policy["draft_lanes"])
    lane_map = {lane: lane in true_lanes for lane in sorted(lanes)}
    required_jobs = sorted({
        job for lane in true_lanes for job in policy["lane_jobs"][lane]
    })
    manifest = {
        "schema": policy["manifest_schema"],
        "base_sha": base_sha,
        "head_sha": head_sha,
        "mode": mode,
        "reasons": sorted(full_reasons if not draft else reasons),
        "changed_files": [_changed_file_json(record) for record in changed],
        "lanes": lane_map,
        "required_jobs": required_jobs,
    }
    validate_manifest(manifest, policy)
    return manifest


def validate_manifest(manifest: Mapping[str, object], policy: Mapping[str, object]) -> None:
    if set(manifest) != ALLOWED_MANIFEST_KEYS:
        raise ValueError("manifest schema is not closed")
    if manifest["schema"] != policy["manifest_schema"]:
        raise ValueError("unknown manifest schema")
    _validate_sha(manifest["base_sha"])
    _validate_sha(manifest["head_sha"])
    if manifest["mode"] not in ALLOWED_MODES:
        raise ValueError("unknown manifest mode")
    lanes = policy["lanes"]
    if not isinstance(manifest["lanes"], dict) or set(manifest["lanes"]) != set(lanes) or not all(isinstance(value, bool) for value in manifest["lanes"].values()):
        raise ValueError("manifest lanes are not closed")
    if not isinstance(manifest["reasons"], list) or not all(isinstance(reason, str) for reason in manifest["reasons"]):
        raise ValueError("invalid manifest reasons")
    if not isinstance(manifest["changed_files"], list):
        raise ValueError("invalid manifest changed files")
    for entry in manifest["changed_files"]:
        if not isinstance(entry, dict) or set(entry) != {"result", "paths"} or entry["result"] not in ALLOWED_RESULTS:
            raise ValueError("invalid manifest changed file")
    expected_jobs = sorted({job for lane, enabled in manifest["lanes"].items() if enabled for job in policy["lane_jobs"][lane]})
    if manifest["required_jobs"] != expected_jobs:
        raise ValueError("required jobs do not derive from lanes")


def encode_manifest(manifest: Mapping[str, object]) -> str:
    # The standalone encoder intentionally validates schema closure too.
    if set(manifest) != ALLOWED_MANIFEST_KEYS:
        raise ValueError("manifest schema is not closed")
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def read_git_inventory(repository: str | Path, base_sha: str, head_sha: str) -> tuple[ChangedFile, ...]:
    base_sha, head_sha = _validate_sha(base_sha), _validate_sha(head_sha)
    for sha in (base_sha, head_sha):
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=repository,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git commit object unavailable: {sha}")
    result = subprocess.run(
        ["git", "diff", "--name-status", "-z", base_sha, head_sha], cwd=repository,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError("git diff --name-status failed")
    return parse_name_status_z(result.stdout)


def fetch_pr_metadata(repository: str, pr_number: str) -> tuple[bool, set[str]]:
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repository) or not str(pr_number).isdigit():
        raise ValueError("repository and PR number are required for PR metadata")
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        f"https://api.github.com/repos/{repository}/pulls/{pr_number}", headers=headers
    )
    with urlopen(request, timeout=15) as response:
        metadata = json.load(response, object_pairs_hook=reject_duplicates)
    if not isinstance(metadata, dict) or not isinstance(metadata.get("draft"), bool) or not isinstance(metadata.get("labels"), list):
        raise ValueError("invalid PR metadata")
    labels: set[str] = set()
    for label in metadata["labels"]:
        if not isinstance(label, dict) or not isinstance(label.get("name"), str):
            raise ValueError("invalid PR label")
        labels.add(label["name"])
    return metadata["draft"], labels


def _write(path: str | Path, contents: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")


def _summary(manifest: Mapping[str, object]) -> str:
    enabled = [lane for lane, selected in manifest["lanes"].items() if selected]
    rows = ["| Field | Value |", "| --- | --- |"]
    rows.extend([
        f"| Mode | `{manifest['mode']}` |",
        f"| Base | `{manifest['base_sha']}` |",
        f"| Head | `{manifest['head_sha']}` |",
        f"| Lanes | {', '.join(enabled) or 'none'} |",
        f"| Required jobs | {', '.join(manifest['required_jobs']) or 'none'} |",
        f"| Reasons | {'; '.join(manifest['reasons']) or 'path ownership'} |",
    ])
    return "\n".join(rows) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--manifest-out", required=True)
    parser.add_argument("--github-output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        inventory = read_git_inventory(Path.cwd(), args.base_sha, args.head_sha)
        draft, labels = (False, set())
        if args.event == "pull_request":
            draft, labels = fetch_pr_metadata(args.repository, args.pr_number)
        manifest = classify(
            policy, inventory, base_sha=args.base_sha, head_sha=args.head_sha,
            event_name=args.event, draft=draft, labels=labels,
        )
        compact = encode_manifest(manifest)
        _write(args.manifest_out, compact)
        with Path(args.github_output).open("a", encoding="utf-8") as output_file:
            output_file.write(f"manifest={compact}\n")
        _write(args.summary, _summary(manifest))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"change scope failed closed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
