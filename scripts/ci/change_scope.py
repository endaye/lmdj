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
import uuid
from typing import Any
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ChangedFile:
    status: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class QueueInputs:
    ticket: str
    pr_number: int
    base_sha: str
    head_sha: str


@dataclass(frozen=True)
class QueueEvaluation:
    classification: str
    observed_base_sha: str
    observed_head_sha: str
    pull_request_body: str
    reason: str


ALLOWED_MANIFEST_KEYS = {
    "schema", "base_sha", "head_sha", "mode", "reasons",
    "changed_files", "lanes", "required_jobs", "trusted_head",
}
QUEUE_MANIFEST_KEYS = ALLOWED_MANIFEST_KEYS | {"queue"}
QUEUE_VALIDATION_KEYS = {
    "schema", "classification", "queue_ticket", "queue_pr_number",
    "queue_base_sha", "queue_head_sha", "observed_base_sha",
    "observed_head_sha", "manifest_mode", "trusted_head",
}
QUEUE_CLASSIFICATIONS = {
    "valid", "queue-base-drift", "queue-head-drift", "invalid",
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
    # Routed by the static `ci-core` role on the shared host, which retired
    # the Linux runner selector: these four were its last consumers, so no
    # Linux lane has a runner-selector support job any more.
    "core_ubuntu": ("core-ubuntu",),
    "core_asan": ("core-asan",),
    "core_coverage": ("core-coverage",),
    "core_macos": ("select-macos-runner", "macos-primary", "core-macos", "core-asan-macos"),
    "web_toolchain": ("web-toolchain-conformance",),
    # Routed by the static `ci-web-heavy` netcup role, so no runner selector
    # is a support job of this lane.
    "web_runtime_host": ("web-runtime-host",),
    "creator": ("creator-web",),
    "web_runtime_lab": ("web-runtime-lab",),
    "deploy_contract": ("deploy-contract",),
    "chameleon_lab": ("chameleon-lab",),
    "package": ("package",),
}
# The closed set of formal jobs a self-hosted role may ever execute. Change
# Scope, the PR Gate and the surviving macOS runner selector stay on the
# GitHub-hosted control plane, and the macOS lane keeps its own runner policy,
# so none of them belong here.
_CANONICAL_SELF_HOSTED_JOBS = (
    "docs-static", "portal", "ci-contract", "core-ubuntu", "core-asan",
    "core-coverage", "web-toolchain-conformance", "web-runtime-host",
    "creator-web", "web-runtime-lab", "deploy-contract", "chameleon-lab",
    "package",
)
# The exact reason recorded on a `push` whose event-supplied base range cannot
# be verified; it is a full-mode upgrade reason, never a lane input.
UNVERIFIABLE_PUSH_BASE = "unverifiable push base"
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


def parse_queue_inputs(
    ticket: str, pr_number: str, base_sha: str, head_sha: str
) -> QueueInputs | None:
    values = (ticket, pr_number, base_sha, head_sha)
    if not any(values):
        return None
    if not all(values):
        raise ValueError("queue inputs must all be provided or all be empty")
    if not re.fullmatch(r"mq:[1-9][0-9]*:[1-3]", ticket):
        raise ValueError("invalid queue ticket")
    if not pr_number.isdigit() or int(pr_number) <= 0:
        raise ValueError("invalid queue PR number")
    return QueueInputs(
        ticket=ticket,
        pr_number=int(pr_number),
        base_sha=_validate_sha(base_sha),
        head_sha=_validate_sha(head_sha),
    )


def evaluate_queue_context(
    queue: QueueInputs,
    repository: str,
    main_ref_sha: str,
    pull: Mapping[str, object],
) -> QueueEvaluation:
    observed_base = _validate_sha(main_ref_sha)
    base = pull.get("base")
    head = pull.get("head")
    labels = pull.get("labels")
    if not isinstance(base, Mapping) or not isinstance(head, Mapping):
        raise ValueError("queue Pull Request base/head is invalid")
    observed_head = _validate_sha(head.get("sha"))
    body = pull.get("body")
    if body is None:
        body = ""
    if not isinstance(body, str):
        raise ValueError("queue Pull Request body is invalid")
    if observed_base != queue.base_sha:
        return QueueEvaluation(
            "queue-base-drift", observed_base, observed_head, body,
            "canonical main ref advanced before Change Scope",
        )
    if observed_head != queue.head_sha:
        return QueueEvaluation(
            "queue-head-drift", observed_base, observed_head, body,
            "Pull Request head advanced before Change Scope",
        )
    label_names = set()
    if isinstance(labels, list):
        for label in labels:
            if isinstance(label, Mapping) and isinstance(label.get("name"), str):
                label_names.add(label["name"])
            else:
                raise ValueError("queue Pull Request label is invalid")
    else:
        raise ValueError("queue Pull Request labels are invalid")
    head_repo = head.get("repo")
    invalid = (
        pull.get("number") != queue.pr_number
        or pull.get("state") != "open"
        or pull.get("merged") is not False
        or pull.get("draft") is not False
        or base.get("ref") != "main"
        or base.get("sha") != queue.base_sha
        or not isinstance(head_repo, Mapping)
        or head_repo.get("full_name") != repository
        or "merge:queue" not in label_names
    )
    if invalid:
        return QueueEvaluation(
            "invalid", observed_base, observed_head, body,
            "queue Pull Request eligibility changed",
        )
    return QueueEvaluation(
        "valid", observed_base, observed_head, body, "queue context is valid"
    )


def queue_validation_document(
    queue: QueueInputs,
    evaluation: QueueEvaluation,
    *,
    manifest_mode: str | None,
    trusted_head: bool,
) -> dict[str, object]:
    if evaluation.classification not in QUEUE_CLASSIFICATIONS:
        raise ValueError("unknown queue validation classification")
    if manifest_mode not in {None, "full"}:
        raise ValueError("queue manifest mode must be null or full")
    document = {
        "schema": "lmdj.queue-validation.v1",
        "classification": evaluation.classification,
        "queue_ticket": queue.ticket,
        "queue_pr_number": queue.pr_number,
        "queue_base_sha": queue.base_sha,
        "queue_head_sha": queue.head_sha,
        "observed_base_sha": evaluation.observed_base_sha,
        "observed_head_sha": evaluation.observed_head_sha,
        "manifest_mode": manifest_mode,
        "trusted_head": trusted_head,
    }
    if set(document) != QUEUE_VALIDATION_KEYS:
        raise ValueError("queue validation schema is not closed")
    return document


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
    trusted_head: bool = True, unverifiable_base: str | None = None,
    queue: QueueInputs | None = None,
) -> dict[str, object]:
    """Return a deterministic closed v2 scope manifest as a dictionary.

    ``trusted_head`` defaults to the non-Pull-Request branch of
    :func:`derive_trusted_head`, which is exactly what an in-repository caller
    such as the local pre-flight is. Every CI path derives and passes it
    explicitly from the event.

    ``unverifiable_base`` carries the concrete reason a push range could not be
    verified. It only exists for ``push``, because that is the one event whose
    base is an untrusted event field rather than a resolved Pull Request base,
    and it forces full with no path inventory at all: an unverifiable range is
    never used to guess which lanes a change owns.
    """
    _validate_policy(policy)
    if not isinstance(trusted_head, bool):
        raise ValueError("trusted head must be a boolean")
    if queue is not None:
        if event_name != "workflow_dispatch" or draft or requested_lanes:
            raise ValueError("queue validation must be a full workflow_dispatch")
        if base_sha.lower() != queue.base_sha or head_sha.lower() != queue.head_sha:
            raise ValueError("queue manifest SHA inputs do not match")
        if not trusted_head:
            raise ValueError("queue validation head must be trusted")
    if unverifiable_base is not None:
        if not isinstance(unverifiable_base, str) or not unverifiable_base:
            raise ValueError("unverifiable push base reason must be a nonempty string")
        if event_name != "push":
            raise ValueError("an unverifiable base is only defined for a push")
        if changed:
            raise ValueError("an unverifiable push base carries no path inventory")
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
    if "merge:queue" in label_set:
        full_reasons.add("merge:queue label")
    requested = set(requested_lanes or ())
    if requested:
        if event_name != "workflow_dispatch":
            raise ValueError("lane selection is only valid for workflow_dispatch")
        unknown = sorted(requested - lanes)
        if unknown:
            raise ValueError(f"unknown requested lane(s): {', '.join(unknown)}")
    # An empty `workflow_dispatch` is the explicit operator request for full
    # CI, so it stays unconditional. A `push` is classified from its exact
    # verified range exactly like a Ready Pull Request; the central-CI,
    # Contract, Product Assembly, unknown-path and expensive-family rules above
    # already upgrade every unsafe main change to full on their own.
    if event_name == "workflow_dispatch" and not requested:
        full_reasons.add(f"full event: {event_name}")
    if unverifiable_base is not None:
        full_reasons.add(UNVERIFIABLE_PUSH_BASE)
        full_reasons.add(f"{UNVERIFIABLE_PUSH_BASE}: {unverifiable_base}")
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
    if queue is not None:
        manifest["queue"] = {
            "ticket": queue.ticket,
            "pr_number": queue.pr_number,
            "base_sha": queue.base_sha,
            "head_sha": queue.head_sha,
        }
    validate_manifest(manifest, policy)
    return manifest


def validate_manifest(manifest: Mapping[str, object], policy: Mapping[str, object]) -> None:
    if frozenset(manifest) not in {frozenset(ALLOWED_MANIFEST_KEYS), frozenset(QUEUE_MANIFEST_KEYS)}:
        raise ValueError("manifest schema is not closed")
    if manifest["schema"] != policy["manifest_schema"]:
        raise ValueError("unknown manifest schema")
    _validate_sha(manifest["base_sha"])
    _validate_sha(manifest["head_sha"])
    if manifest["mode"] not in ALLOWED_MODES:
        raise ValueError("unknown manifest mode")
    if not isinstance(manifest["trusted_head"], bool):
        raise ValueError("manifest trusted head must be a boolean")
    if "queue" in manifest:
        queue = manifest["queue"]
        if not isinstance(queue, Mapping) or set(queue) != {
            "ticket", "pr_number", "base_sha", "head_sha"
        }:
            raise ValueError("manifest queue metadata is not closed")
        parsed = parse_queue_inputs(
            queue["ticket"], str(queue["pr_number"]),
            queue["base_sha"], queue["head_sha"],
        )
        if parsed is None or manifest["mode"] != "full" or not manifest["trusted_head"]:
            raise ValueError("queue manifest must be trusted full evidence")
        if parsed.base_sha != manifest["base_sha"] or parsed.head_sha != manifest["head_sha"]:
            raise ValueError("queue manifest metadata SHA mismatch")
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
    if frozenset(manifest) not in {frozenset(ALLOWED_MANIFEST_KEYS), frozenset(QUEUE_MANIFEST_KEYS)}:
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


def _is_commit(repository: str | Path, sha: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=repository,
        capture_output=True,
    ).returncode == 0


def resolve_push_inventory(
    repository: str | Path, base_sha: str, head_sha: str,
) -> tuple[tuple[ChangedFile, ...] | None, str | None]:
    """Return the exact push inventory, or ``None`` plus a concrete reason.

    A push carries its base in `github.event.before`, which is absent for the
    first push, zero after a branch is created, and an unrelated revision after
    a force push. Every one of those is reported as an unverifiable base so the
    caller runs full CI; none of them is silently narrowed to a guessed range.
    """
    head_sha = _validate_sha(head_sha)
    if not isinstance(base_sha, str) or _SHA_RE.fullmatch(base_sha) is None:
        return None, "before SHA is absent or is not a 40-character revision"
    base_sha = base_sha.lower()
    if base_sha == "0" * 40:
        return None, "before SHA is the zero object"
    if not _is_commit(repository, head_sha):
        raise RuntimeError(f"Git commit object unavailable: {head_sha}")
    if not _is_commit(repository, base_sha):
        return None, "before SHA is not an available commit object"
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, head_sha], cwd=repository,
        capture_output=True,
    )
    if ancestry.returncode != 0:
        return None, "before SHA is not an ancestor of the pushed head"
    try:
        return read_git_inventory(repository, base_sha, head_sha), None
    except (ValueError, RuntimeError, subprocess.SubprocessError):
        return None, "changed-file inventory is incomplete"


def fetch_pr_metadata(repository: str, pr_number: str) -> tuple[bool, set[str], str]:
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
    if (
        not isinstance(metadata, dict)
        or not isinstance(metadata.get("draft"), bool)
        or not isinstance(metadata.get("labels"), list)
        or metadata.get("body") is not None
        and not isinstance(metadata.get("body"), str)
    ):
        raise ValueError("invalid PR metadata")
    labels: set[str] = set()
    for label in metadata["labels"]:
        if not isinstance(label, dict) or not isinstance(label.get("name"), str):
            raise ValueError("invalid PR label")
        labels.add(label["name"])
    return metadata["draft"], labels, metadata.get("body") or ""


def fetch_queue_evaluation(
    repository: str, queue: QueueInputs
) -> QueueEvaluation:
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repository):
        raise ValueError("repository is required for queue validation")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    documents = []
    for url in (
        f"https://api.github.com/repos/{repository}/git/ref/heads/main",
        f"https://api.github.com/repos/{repository}/pulls/{queue.pr_number}",
    ):
        with urlopen(Request(url, headers=headers), timeout=15) as response:
            documents.append(json.load(response, object_pairs_hook=reject_duplicates))
    ref, pull = documents
    if (
        not isinstance(ref, Mapping)
        or ref.get("ref") != "refs/heads/main"
        or not isinstance(ref.get("object"), Mapping)
    ):
        raise ValueError("invalid canonical main ref response")
    if not isinstance(pull, Mapping):
        raise ValueError("invalid queue Pull Request response")
    return evaluate_queue_context(queue, repository, ref["object"].get("sha"), pull)


def _write(path: str | Path, contents: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")


def _write_output_value(output_file, name: str, value: str) -> None:
    if "\n" not in value and "\r" not in value:
        output_file.write(f"{name}={value}\n")
        return
    delimiter = f"lmdj_{uuid.uuid4().hex}"
    while delimiter in value:
        delimiter = f"lmdj_{uuid.uuid4().hex}"
    output_file.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


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
    parser.add_argument("--queue-ticket", default="")
    parser.add_argument("--queue-pr-number", default="")
    parser.add_argument("--queue-base-sha", default="")
    parser.add_argument("--queue-head-sha", default="")
    parser.add_argument("--queue-validation-out", default="")
    parser.add_argument(
        "--lanes", default="",
        help="comma-separated lanes for a focused workflow_dispatch",
    )
    args = parser.parse_args(argv)
    queue: QueueInputs | None = None
    queue_evaluation: QueueEvaluation | None = None
    try:
        policy = load_policy(args.policy)
        queue = parse_queue_inputs(
            args.queue_ticket,
            args.queue_pr_number,
            args.queue_base_sha,
            args.queue_head_sha,
        )
        pull_request_body = ""
        if queue is not None:
            if not args.queue_validation_out:
                raise ValueError("queue validation output path is required")
            if args.event != "workflow_dispatch" or args.lanes:
                raise ValueError("queue validation must be a full workflow_dispatch")
            if args.base_sha.lower() != queue.base_sha or args.head_sha.lower() != queue.head_sha:
                raise ValueError("queue CLI SHA inputs do not match")
            queue_evaluation = fetch_queue_evaluation(args.repository, queue)
            pull_request_body = queue_evaluation.pull_request_body
            if queue_evaluation.classification != "valid":
                _write(
                    args.queue_validation_out,
                    json.dumps(
                        queue_validation_document(
                            queue,
                            queue_evaluation,
                            manifest_mode=None,
                            trusted_head=False,
                        ),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                raise ValueError(queue_evaluation.reason)
        unverifiable_base: str | None = None
        if args.event == "push":
            inventory, unverifiable_base = resolve_push_inventory(
                Path.cwd(), args.base_sha, args.head_sha,
            )
            inventory = inventory or ()
        else:
            inventory = read_git_inventory(Path.cwd(), args.base_sha, args.head_sha)
        draft, labels = (False, set())
        if args.event == "pull_request":
            draft, labels, pull_request_body = fetch_pr_metadata(
                args.repository, args.pr_number
            )
        trusted_head = derive_trusted_head(
            args.event, args.head_repository, args.repository
        )
        if queue is not None:
            trusted_head = queue_evaluation is not None and queue_evaluation.classification == "valid"
        manifest = classify(
            policy, inventory, base_sha=args.base_sha, head_sha=args.head_sha,
            event_name=args.event, draft=draft, labels=labels,
            requested_lanes=[
                lane.strip() for lane in args.lanes.split(",") if lane.strip()
            ],
            trusted_head=trusted_head,
            unverifiable_base=unverifiable_base,
            queue=queue,
        )
        compact = encode_manifest(manifest)
        _write(args.manifest_out, compact)
        with Path(args.github_output).open("a", encoding="utf-8") as output_file:
            _write_output_value(output_file, "manifest", compact)
            _write_output_value(
                output_file, "trusted-head", "true" if trusted_head else "false"
            )
            _write_output_value(
                output_file, "queue-mode", "true" if queue is not None else "false"
            )
            _write_output_value(output_file, "pull-request-body", pull_request_body)
            _write_output_value(output_file, "resolved-base-sha", manifest["base_sha"])
            _write_output_value(output_file, "resolved-head-sha", manifest["head_sha"])
        if queue is not None and queue_evaluation is not None:
            _write(
                args.queue_validation_out,
                json.dumps(
                    queue_validation_document(
                        queue,
                        queue_evaluation,
                        manifest_mode=manifest["mode"],
                        trusted_head=trusted_head,
                    ),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        _write(args.summary, _summary(manifest, policy))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        if queue is not None and args.queue_validation_out and not Path(args.queue_validation_out).is_file():
            fallback = QueueEvaluation(
                "invalid",
                queue_evaluation.observed_base_sha if queue_evaluation else queue.base_sha,
                queue_evaluation.observed_head_sha if queue_evaluation else queue.head_sha,
                queue_evaluation.pull_request_body if queue_evaluation else "",
                str(error),
            )
            _write(
                args.queue_validation_out,
                json.dumps(
                    queue_validation_document(
                        queue, fallback, manifest_mode=None, trusted_head=False
                    ),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        print(f"change scope failed closed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
