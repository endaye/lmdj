#!/usr/bin/env python3
"""Classify a complete Git change inventory into the closed LMDJ CI lanes."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
import argparse
import html
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
    "changed_files", "lanes", "required_jobs", "trusted_head",
}
ALLOWED_MODES = {"draft", "focused", "full", "requested"}
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
    "package": ("select-ubuntu-runner", "package"),
}
# The closed set of formal jobs a self-hosted role may ever execute. Change
# Scope, the PR Gate and both runner selectors stay on the GitHub-hosted
# control plane, and the macOS lane keeps its own runner policy, so none of
# them belong here.
_CANONICAL_SELF_HOSTED_JOBS = (
    "docs-static", "portal", "ci-contract", "core-ubuntu", "core-asan",
    "core-coverage", "web-toolchain-conformance", "web-runtime-host",
    "creator-web", "web-runtime-lab", "deploy-contract", "chameleon-lab",
    "package",
)
_MANDATORY_FULL_MATCHES = {
    ("exact", ".github/workflows/ci.yml"),
    ("prefix", "scripts/ci/"),
    ("prefix", ".github/actions/configure-build-acceleration/"),
}
_POLICY_KEYS = {
    "schema", "manifest_schema", "lanes", "lane_jobs", "self_hosted_jobs",
    "known_top_levels", "full_rules", "rules", "expensive_families",
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
    if policy["schema"] != "lmdj.ci-scope-policy.v1" or policy["manifest_schema"] != "lmdj.ci-scope.v2":
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
    formal_jobs = {job for jobs in _CANONICAL_LANE_JOBS.values() for job in jobs}
    self_hosted = policy["self_hosted_jobs"]
    if not isinstance(self_hosted, list) or not all(
        isinstance(job, str) for job in self_hosted
    ):
        raise ValueError("self-hosted jobs must be a list of job names")
    if len(self_hosted) != len(set(self_hosted)):
        raise ValueError("duplicate self-hosted job")
    non_formal = sorted(set(self_hosted) - formal_jobs)
    if non_formal:
        raise ValueError(
            "self-hosted jobs reference non-formal job(s): "
            + ", ".join(non_formal)
        )
    if set(self_hosted) != set(_CANONICAL_SELF_HOSTED_JOBS):
        missing = sorted(set(_CANONICAL_SELF_HOSTED_JOBS) - set(self_hosted))
        extra = sorted(set(self_hosted) - set(_CANONICAL_SELF_HOSTED_JOBS))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("extra " + ", ".join(extra))
        raise ValueError(
            "self-hosted jobs do not match the closed v2 set: "
            + "; ".join(details)
        )
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


def _evaluate_ready_paths(
    policy: Mapping[str, object], paths: Sequence[str]
) -> tuple[set[str], set[str]]:
    """Return the exact Ready lane union and any reasons that require full."""
    selected: set[str] = set()
    full_reasons: set[str] = set()
    for path in paths:
        _validate_path(path)
        top_level = path.split("/", 1)[0]
        if top_level not in policy["known_top_levels"]:
            full_reasons.add(f"unknown top-level: {top_level}")
        path_lanes: set[str] = set()
        for rule in policy["rules"]:
            if _matches(rule["match"], path):
                path_lanes.update(rule["lanes"])
        if not path_lanes:
            full_reasons.add(f"unclassified path: {path}")
        selected.update(path_lanes)
        for rule in policy["full_rules"]:
            if _matches(rule["match"], path):
                full_reasons.add(f"full rule: {rule['reason']}")

    active_families = sorted(
        name
        for name, family_lanes in policy["expensive_families"].items()
        if selected.intersection(family_lanes)
    )
    if len(active_families) >= 3:
        full_reasons.add("three expensive families: " + ", ".join(active_families))
    return selected, full_reasons


def derive_trusted_head(
    event_name: str, head_repository: str, repository: str
) -> bool:
    """Trust only a non-PR event or a same-repository Pull Request head.

    Trust is never derived from a title, a label, changed paths or the code
    under test, because a fork controls all of those.
    """
    return (
        event_name != "pull_request"
        or head_repository == repository
    )


def classify(
    policy: Mapping[str, object], changed: Sequence[ChangedFile], *, base_sha: str,
    head_sha: str, event_name: str, draft: bool, labels: Collection[str],
    force_full: bool = False, requested_lanes: Collection[str] | None = None,
    trusted_head: bool = True,
) -> dict[str, object]:
    """Return a deterministic closed v2 scope manifest as a dictionary.

    ``trusted_head`` defaults to the non-Pull-Request branch of
    :func:`derive_trusted_head`, which is exactly what an in-repository caller
    such as the local pre-flight is. Every CI path derives and passes it
    explicitly from the event.
    """
    _validate_policy(policy)
    if not isinstance(trusted_head, bool):
        raise ValueError("trusted head must be a boolean")
    base_sha, head_sha = _validate_sha(base_sha), _validate_sha(head_sha)
    lanes = set(policy["lanes"])
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
    selected, full_reasons = _evaluate_ready_paths(policy, sorted(all_paths))
    reasons = set(full_reasons)
    label_set = set(labels)
    if not all(isinstance(label, str) for label in label_set):
        raise ValueError("labels must be strings")
    if force_full:
        full_reasons.add("forced full")
    if "ci:full" in label_set:
        full_reasons.add("ci:full label")
    requested = set(requested_lanes or ())
    if requested:
        if event_name != "workflow_dispatch":
            raise ValueError("lane selection is only valid for workflow_dispatch")
        unknown = sorted(requested - lanes)
        if unknown:
            raise ValueError(f"unknown requested lane(s): {', '.join(unknown)}")
    if event_name in {"push", "workflow_dispatch"} and not requested:
        full_reasons.add(f"full event: {event_name}")
    if requested:
        full_reasons.discard("forced full")
        reasons.discard("forced full")
        mode = "requested"
        true_lanes = requested
        reasons.add(
            "requested lanes: " + ", ".join(sorted(requested))
        )
    elif full_reasons:
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
        "reasons": sorted(
            reasons if (draft or requested) else full_reasons
        ),
        "changed_files": [_changed_file_json(record) for record in changed],
        "lanes": lane_map,
        "required_jobs": required_jobs,
        "trusted_head": trusted_head,
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
    if not isinstance(manifest["trusted_head"], bool):
        raise ValueError("manifest trusted head must be a boolean")
    lanes = policy["lanes"]
    if not isinstance(manifest["lanes"], dict) or set(manifest["lanes"]) != set(lanes) or not all(isinstance(value, bool) for value in manifest["lanes"].values()):
        raise ValueError("manifest lanes are not closed")
    enabled_lanes = {
        lane for lane, enabled in manifest["lanes"].items() if enabled
    }
    if manifest["mode"] == "full" and enabled_lanes != set(lanes):
        raise ValueError("full manifest must select every lane")
    if manifest["mode"] == "draft" and enabled_lanes != set(policy["draft_lanes"]):
        raise ValueError("draft manifest must select exactly the draft lanes")
    if manifest["mode"] == "requested" and (
        not enabled_lanes or not enabled_lanes.issubset(set(lanes))
    ):
        raise ValueError(
            "requested manifest must select a non-empty subset of the lanes"
        )
    if manifest["mode"] == "focused" and enabled_lanes == set(lanes):
        raise ValueError("focused manifest cannot select every lane")
    if not isinstance(manifest["reasons"], list) or not all(isinstance(reason, str) for reason in manifest["reasons"]):
        raise ValueError("invalid manifest reasons")
    if not isinstance(manifest["changed_files"], list):
        raise ValueError("invalid manifest changed files")
    seen_paths: set[str] = set()
    changed_paths: list[str] = []
    for entry in manifest["changed_files"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"result", "paths"}
            or entry["result"] not in ALLOWED_RESULTS
        ):
            raise ValueError("invalid manifest changed file")
        paths = entry["paths"]
        if not isinstance(paths, list):
            raise ValueError("manifest changed-file paths must be a list")
        required_path_count = 2 if entry["result"] in {"renamed", "copied"} else 1
        if len(paths) != required_path_count:
            raise ValueError("invalid manifest changed-file path count")
        for path in paths:
            _validate_path(path)
            if path in seen_paths:
                raise ValueError(f"duplicate logical path: {path}")
            seen_paths.add(path)
            changed_paths.append(path)
    if manifest["mode"] == "focused":
        expected_lanes, full_reasons = _evaluate_ready_paths(
            policy, changed_paths
        )
        if full_reasons:
            raise ValueError(
                "focused manifest path inventory requires full: "
                + "; ".join(sorted(full_reasons))
            )
        if enabled_lanes != expected_lanes:
            missing = sorted(expected_lanes - enabled_lanes)
            extra = sorted(enabled_lanes - expected_lanes)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if extra:
                details.append("extra " + ", ".join(extra))
            raise ValueError(
                "focused manifest lanes do not match path ownership: "
                + "; ".join(details)
            )
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


def _summary_text(value: object) -> str:
    escaped_controls = json.dumps(str(value), ensure_ascii=True)[1:-1]
    return (
        html.escape(escaped_controls, quote=True)
        .replace("|", "&#124;")
        .replace("`", "&#96;")
    )


def _summary(
    manifest: Mapping[str, object], policy: Mapping[str, object]
) -> str:
    validate_manifest(manifest, policy)
    enabled = [lane for lane, selected in manifest["lanes"].items() if selected]
    rows = ["| Field | Value |", "| --- | --- |"]
    rows.extend([
        f"| Mode | <code>{_summary_text(manifest['mode'])}</code> |",
        f"| Base | <code>{_summary_text(manifest['base_sha'])}</code> |",
        f"| Head | <code>{_summary_text(manifest['head_sha'])}</code> |",
        "| Trust | <code>"
        + _summary_text("trusted" if manifest["trusted_head"] else "untrusted")
        + "</code> |",
        "| Lanes | " + (
            ", ".join(f"<code>{_summary_text(lane)}</code>" for lane in enabled)
            or "none"
        ) + " |",
        "| Required jobs | " + (
            ", ".join(
                f"<code>{_summary_text(job)}</code>"
                for job in manifest["required_jobs"]
            ) or "none"
        ) + " |",
    ])
    rows.extend(["", "### Changed files", ""])
    for entry in manifest["changed_files"]:
        paths = " &rarr; ".join(
            f"<code>{_summary_text(path)}</code>" for path in entry["paths"]
        )
        rows.append(
            f"- <code>{_summary_text(entry['result'])}</code>: {paths}"
        )
    if not manifest["changed_files"]:
        rows.append("- none")

    lane_reasons: dict[str, list[str]] = {lane: [] for lane in enabled}
    if manifest["mode"] == "full":
        upgrade_reasons = list(manifest["reasons"]) or ["full mode"]
        for lane in enabled:
            lane_reasons[lane].extend(
                f"full upgrade: {reason}" for reason in upgrade_reasons
            )
    elif manifest["mode"] == "draft":
        for lane in enabled:
            lane_reasons[lane].append(
                "draft evidence: lightweight Draft lane; Ready rerun required"
            )
        for lane in enabled:
            lane_reasons[lane].extend(
                f"draft deferral: {reason}" for reason in manifest["reasons"]
            )
    elif manifest["mode"] == "requested":
        # A lane enabled here came from the operator's workflow_dispatch
        # `lanes` input, not from path ownership, so it may have no matching
        # path rule at all. Record that explicit selection as its auditable
        # reason; path-derived reasons are added on top when they also apply.
        for lane in enabled:
            lane_reasons[lane].append(
                "operator workflow_dispatch lane selection"
            )
        for entry in manifest["changed_files"]:
            for path in entry["paths"]:
                for rule in policy["rules"]:
                    if not _matches(rule["match"], path):
                        continue
                    match = rule["match"]
                    reason = (
                        f"path {path} matched {match['kind']}: {match['value']}"
                    )
                    for lane in rule["lanes"]:
                        if lane in lane_reasons:
                            lane_reasons[lane].append(reason)
    else:
        for entry in manifest["changed_files"]:
            for path in entry["paths"]:
                for rule in policy["rules"]:
                    if not _matches(rule["match"], path):
                        continue
                    match = rule["match"]
                    reason = (
                        f"path {path} matched {match['kind']}: {match['value']}"
                    )
                    for lane in rule["lanes"]:
                        if lane in lane_reasons:
                            lane_reasons[lane].append(reason)

    rows.extend(["", "### Selected lane reasons", ""])
    for lane in enabled:
        reasons = sorted(set(lane_reasons[lane]))
        if not reasons:
            raise ValueError(f"selected lane lacks an auditable reason: {lane}")
        rendered = "; ".join(
            f"<code>{_summary_text(reason)}</code>" for reason in reasons
        )
        rows.append(f"- <code>{_summary_text(lane)}</code>: {rendered}")
    if not enabled:
        rows.append("- none")
    return "\n".join(rows) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--head-repository", required=True)
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--manifest-out", required=True)
    parser.add_argument("--github-output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument(
        "--lanes", default="",
        help="comma-separated lanes for a focused workflow_dispatch",
    )
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        inventory = read_git_inventory(Path.cwd(), args.base_sha, args.head_sha)
        draft, labels = (False, set())
        if args.event == "pull_request":
            draft, labels = fetch_pr_metadata(args.repository, args.pr_number)
        trusted_head = derive_trusted_head(
            args.event, args.head_repository, args.repository
        )
        manifest = classify(
            policy, inventory, base_sha=args.base_sha, head_sha=args.head_sha,
            event_name=args.event, draft=draft, labels=labels,
            requested_lanes=[
                lane.strip() for lane in args.lanes.split(",") if lane.strip()
            ],
            trusted_head=trusted_head,
        )
        compact = encode_manifest(manifest)
        _write(args.manifest_out, compact)
        with Path(args.github_output).open("a", encoding="utf-8") as output_file:
            output_file.write(f"manifest={compact}\n")
            output_file.write(
                f"trusted-head={'true' if trusted_head else 'false'}\n"
            )
        _write(args.summary, _summary(manifest, policy))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"change scope failed closed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
