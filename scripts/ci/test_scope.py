#!/usr/bin/env python3
"""Commit-bound test selection, not review authority or release evidence.

Labels are projections. Consumers MUST authenticate the publisher/run and PR
mapping independently; a matching digest only establishes internal consistency.
Policy snapshots must likewise be obtained from independently trusted revisions.
No PR text, model output, Git code, or shell command from a record is executed.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess

import change_scope
import self_test

SCHEMA = "lmdj.ci-test-scope.v1"
POLICY_SCHEMA = "lmdj.ci-test-scope-policy.v1"
IDENTITY_KEYS = frozenset({"repository", "pr_number", "head_sha", "base_sha",
                           "control_sha", "backend", "run_id", "run_attempt"})
RECORD_KEYS = IDENTITY_KEYS | {"schema", "policy_digest", "changed_path_digest",
                              "changed_paths", "complete", "rule_floor",
                              "ai_labels", "effective", "record_digest"}


class ScopeError(ValueError):
    """Invalid or incomplete selection evidence; never interpret as none."""


def require(condition, why, remedy="rebuild scope from complete trusted Git and policy inputs"):
    if not condition:
        raise ScopeError(f"why: {why}; remedy: {remedy}")


def _sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value),
            "revision is not an exact lowercase 40-hex commit SHA")
    return value


def _paths(paths):
    require(isinstance(paths, (list, tuple)), "paths must be a complete list")
    for path in paths:
        try:
            change_scope._validate_path(path)
        except ValueError as error:
            require(False, str(error))
        require(not any(ord(c) < 32 or ord(c) == 127 for c in path),
                "path contains control characters")
    return sorted(set(paths))


@dataclass(frozen=True)
class ScopePolicy:
    routing: dict
    inventory: self_test.Policy
    config: dict
    digest: str

    @property
    def suite_ids(self):
        return tuple(suite.id for suite in self.inventory.suites)


def parse_policy(routing, inventory, config):
    require(isinstance(routing, dict) and isinstance(inventory, dict),
            "canonical policies must be objects")
    try:
        change_scope._validate_policy(routing)
        inventory_policy = self_test.parse_policy(inventory)
    except (ValueError, TypeError, KeyError) as error:
        raise ScopeError(f"why: invalid upstream policy: {error}; remedy: restore the trusted canonical policies") from error
    require(isinstance(config, dict) and set(config) == {
        "schema", "none_prefixes", "full_prefixes", "dependencies"}, "scope policy schema is not closed")
    require(config["schema"] == POLICY_SCHEMA, "unsupported scope policy version")
    for key in ("none_prefixes", "full_prefixes"):
        prefixes = config[key]
        require(isinstance(prefixes, list) and all(isinstance(p, str) for p in prefixes),
                f"{key} must be a list of path prefixes")
        require(len(prefixes) == len(set(prefixes)), f"duplicate {key}")
        for prefix in prefixes:
            require(prefix.endswith("/"), "prefix must terminate at a directory boundary")
            _paths([prefix[:-1]])
            if key == "none_prefixes":
                require(prefix.startswith("docs/") and prefix.count("/") >= 2,
                        "none exemptions must name explicit explanatory documentation directories")
    suites = {suite.id for suite in inventory_policy.suites}
    mapped = {suite.scope_lane: suite for suite in inventory_policy.suites if suite.scope_lane}
    require(set(mapped) == set(routing["lanes"]), "inventory does not cover every canonical lane")
    for lane, suite in mapped.items():
        require(tuple(routing["lane_jobs"][lane]) == suite.jobs,
                f"suite jobs drift from canonical lane {lane}")
    deps = config["dependencies"]
    require(isinstance(deps, dict), "dependencies must be an object")
    for source, targets in deps.items():
        require(source in suites and isinstance(targets, list)
                and all(isinstance(t, str) and t in suites for t in targets),
                "dependency references an unknown suite")
        require(len(targets) == len(set(targets)), "duplicate dependency")
    return ScopePolicy(routing, inventory_policy, config,
                       self_test.digest_of({"routing": routing, "inventory": inventory, "scope": config}))


def load_policy(root):
    root = Path(root)
    try:
        documents = [json.loads((root / "scripts/ci" / name).read_text(),
                                object_pairs_hook=change_scope.reject_duplicates)
                     for name in ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json")]
        return parse_policy(*documents)
    except (OSError, ValueError) as error:
        raise ScopeError(f"why: scope policy unavailable: {error}; remedy: fetch complete trusted policy snapshots") from error


def labels_to_suites(policy, labels):
    require(isinstance(labels, (list, tuple)), "AI labels must be a list")
    allowed = {"test:none", "test:full"} | {f"test:{s}" for s in policy.suite_ids}
    require(all(isinstance(label, str) and label in allowed for label in labels),
            "unknown test label", "request valid structured review output or use deterministic fallback")
    if "test:full" in labels:
        return set(policy.suite_ids)
    return {label[5:] for label in labels if label != "test:none"}


def _selection(policy, suites, reasons):
    selected = sorted(set(suites))
    require(set(selected) <= set(policy.suite_ids), "unknown selected suite")
    kind = "none" if not selected else "full" if set(selected) == set(policy.suite_ids) else "focused"
    return {"kind": kind, "suites": selected, "reasons": sorted(set(reasons))}


def _dependency_closure(policies, suites):
    selected = set(suites)
    while True:
        expanded = selected | {target for policy in policies for source in selected
                               for target in policy.config["dependencies"].get(source, [])}
        if expanded == selected:
            return selected
        selected = expanded


def select(policy, paths, ai_labels=(), complete=True):
    paths = _paths(paths)
    require(type(complete) is bool, "inventory completeness must be boolean")
    selected = labels_to_suites(policy, ai_labels)
    reasons = []
    if not complete:
        return _selection(policy, policy.suite_ids,
                          ["why: changed inventory is incomplete; remedy: fetch every page or complete Git history"])
    active = []
    for path in paths:
        lanes, full = change_scope.path_classification(policy.routing, path)
        explicit_none = (path.endswith(".md") and any(path.startswith(p) for p in policy.config["none_prefixes"])
                         and lanes == {"docs_static"} and not full)
        if explicit_none:
            reasons.append(f"explanatory document without routed consumers: {path}")
        else:
            active.append(change_scope.ChangedFile("M", (path,)))
        if full:
            # Older local/PR classification has narrowly proven inert-file
            # exemptions. Incremental records deliberately preserve the old
            # raw full rules rather than inheriting those separate proofs.
            selected.update(policy.suite_ids)
            reasons.extend(sorted(full))
        if any(path.startswith(p) for p in policy.config["full_prefixes"]):
            selected.update(policy.suite_ids)
            reasons.append(f"broad foundational or concurrency impact: {path}")
    if active:
        try:
            manifest = change_scope.classify(policy.routing, active, base_sha="0" * 40,
                                            head_sha="1" * 40, event_name="push", draft=False, labels=[])
        except ValueError as error:
            raise ScopeError(f"why: classification failed: {error}; remedy: restore canonical routing inputs") from error
        if manifest["mode"] == "full":
            selected.update(policy.suite_ids)
        else:
            lane_map = {suite.scope_lane: suite.id for suite in policy.inventory.suites if suite.scope_lane}
            selected.update(lane_map[lane] for lane, enabled in manifest["lanes"].items() if enabled)
        reasons.extend(manifest["reasons"])
    selected = _dependency_closure([policy], selected)
    if ai_labels:
        reasons.append("valid AI suggestions add scope; they never subtract the deterministic floor")
    if not paths:
        reasons.append("complete inventory contains no changed paths")
    return _selection(policy, selected, reasons)


def union_selections(policy, selections):
    suites, reasons = set(), []
    for selection in selections:
        require(isinstance(selection, dict) and set(selection) == {"kind", "suites", "reasons"},
                "selection schema is not closed")
        require(isinstance(selection["suites"], list) and all(isinstance(s, str) for s in selection["suites"])
                and isinstance(selection["reasons"], list) and all(isinstance(r, str) for r in selection["reasons"]),
                "invalid selection fields")
        require(selection == _selection(policy, selection["suites"], selection["reasons"]),
                "selection kind or canonical order disagrees with suites")
        suites.update(selection["suites"])
        reasons.extend(selection["reasons"])
    return _selection(policy, _dependency_closure([policy], suites), reasons)


def select_across_policies(paths, policies, ai_labels=(), complete=True):
    """Pass current policy first, followed by every required trusted old policy.

    None explicitly denotes a missing snapshot. Missing snapshots or inventory
    migration fall back to full; the caller must not silently omit old policies.
    """
    require(isinstance(policies, (list, tuple)) and policies and isinstance(policies[0], ScopePolicy),
            "current policy is required")
    current = policies[0]
    require(all(p is None or isinstance(p, ScopePolicy) for p in policies),
            "historical policies must be validated snapshots or explicitly missing")
    if any(p is None or set(p.suite_ids) != set(current.suite_ids) for p in policies):
        return _selection(current, current.suite_ids,
                          ["why: prior policy unavailable or inventory changed; remedy: run full under current trusted policy"])
    combined = union_selections(current, [select(p, paths, ai_labels, complete) for p in policies])
    return _selection(current, _dependency_closure(policies, combined["suites"]), combined["reasons"])


def collect_interval(repository, base_sha, target_sha):
    """Union each actual first-parent commit delta, including reverted paths.

    A missing/non-first-parent baseline is blocked, never guessed. Git commands
    are read-only, full-SHA argv calls, with replacement objects disabled.
    """
    base_sha, target_sha = _sha(base_sha), _sha(target_sha)

    def git(*args):
        try:
            return subprocess.run(["git", "--no-replace-objects", "-C", str(repository), *args],
                                  check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        except (OSError, subprocess.CalledProcessError) as error:
            raise ScopeError("why: Git history is missing or unreadable; remedy: fetch complete main history and reconcile") from error

    require(git("rev-parse", "--is-shallow-repository").strip() == b"false",
            "shallow history cannot prove interval completeness", "fetch unshallowed main history and reconcile")
    for sha in (base_sha, target_sha):
        require(git("cat-file", "-t", sha).strip() == b"commit", "range endpoint is not a commit")
    commits, paths, cursor = [], set(), target_sha
    while cursor != base_sha:
        parents = git("show", "-s", "--format=%P", cursor).decode("ascii").strip().split()
        require(bool(parents), "baseline is not on target's first-parent history",
                "retain blocked state and explicitly bootstrap the latest target with full tests")
        parent = _sha(parents[0])
        try:
            changes = change_scope.parse_name_status_z(git("diff", "--no-ext-diff", "--no-textconv",
                                                           "--name-status", "-z", "--find-renames", parent, cursor, "--"))
        except ValueError as error:
            raise ScopeError(f"why: invalid Git change inventory: {error}; remedy: restore complete canonical Git paths") from error
        for change in changes:
            paths.update(_paths(list(change.paths)))
        commits.append({"sha": cursor, "parent_sha": parent,
                        "changes": [{"status": c.status, "paths": list(c.paths)} for c in changes]})
        cursor = parent
    return {"base_sha": base_sha, "target_sha": target_sha, "commits": list(reversed(commits)),
            "paths": sorted(paths), "changed_path_digest": self_test.digest_of(sorted(paths))}


def _identity(identity):
    require(isinstance(identity, dict) and set(identity) == IDENTITY_KEYS,
            "record identity fields are missing or unknown")
    require(isinstance(identity["repository"], str) and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", identity["repository"]),
            "invalid repository identity")
    for key in ("head_sha", "base_sha", "control_sha"):
        _sha(identity[key])
    for key in ("pr_number", "run_id", "run_attempt"):
        require(type(identity[key]) is int and identity[key] > 0, f"{key} must be a positive integer")
    # DeepSeek is the new engine route; deterministic remains the explicit
    # publisher/failure identity.  Historical GLM/Kimi/Grok records stay valid.
    require(identity["backend"] in ("deepseek", "glm", "kimi", "grok", "deterministic"), "unknown review backend")


def build_record(policy, *, changed_paths, ai_labels=(), complete=True, **identity):
    _identity(identity)
    paths = _paths(changed_paths)
    effective = select(policy, paths, ai_labels, complete)
    record = {"schema": SCHEMA, **identity, "policy_digest": policy.digest,
              "changed_path_digest": self_test.digest_of(paths), "changed_paths": paths,
              "complete": complete, "rule_floor": select(policy, paths, complete=complete),
              "ai_labels": sorted(set(ai_labels)), "effective": effective}
    record["record_digest"] = self_test.digest_of(record)
    return record


def validate_record(record, policy, expected_identity):
    """Validate consistency against independently authenticated identity.

    This is NOT an authentication primitive. Never populate expected_identity
    from the record itself in production; obtain run/PR/writer evidence first.
    Caller must separately compare changed_path_digest to complete actual Git.
    """
    require(isinstance(record, dict) and set(record) == RECORD_KEYS, "record schema is not closed")
    _identity(expected_identity)
    require(all(record[key] == expected_identity[key] and type(record[key]) is type(expected_identity[key])
                for key in IDENTITY_KEYS), "scope record identity is stale or mismatched",
            "authenticate the current PR head and publisher run, then regenerate its scope record")
    expected = build_record(policy, changed_paths=record["changed_paths"], ai_labels=record["ai_labels"],
                            complete=record["complete"], **expected_identity)
    require(record == expected, "scope record digest, policy or computed selection is inconsistent",
            "regenerate scope with the exact trusted policy and independently verified changed paths")
    return record


def parse_record(payload, policy, expected_identity):
    """Decode a JSON record without silently accepting duplicate object keys."""
    require(isinstance(payload, (str, bytes)), "record payload must be JSON text")
    try:
        record = json.loads(payload, object_pairs_hook=change_scope.reject_duplicates)
    except (ValueError, UnicodeError) as error:
        raise ScopeError(f"why: malformed record JSON: {error}; remedy: regenerate one canonical scope record") from error
    return validate_record(record, policy, expected_identity)
