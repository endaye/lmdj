#!/usr/bin/env python3
"""Advisory local pre-flight that reuses the CI Change Scope decision.

The pre-flight answers one question: of the lanes CI would select for the
current working tree, which ones pass on this machine right now? It is not
evidence. It does not grant merge or release eligibility, and a green local
run authorizes no push, Pull Request, merge, or later state transition.

Two properties keep it honest. The lane selection comes from
`scripts/ci/change_scope.py` and `scripts/ci/scope_policy.json`, the same
classifier and policy the workflow runs, so the pre-flight cannot select a
different set of lanes than CI would. A lane this machine cannot execute
reports `not-runnable-here`, never `pass`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "scripts/ci/scope_policy.json"
CLASSIFIER_PATH = ROOT / "scripts/ci/change_scope.py"
LANE_COMMANDS_PATH = ROOT / "scripts/ci/local_lanes.json"
DOC_IMPACT_CHECKER = ROOT / "apps/docs-site/scripts/check-doc-impact.mjs"
PR_WORKFLOW = ".github/workflows/pr-contract.yml"
_LANE_GATE = re.compile(r"manifest\)\.lanes\.([a-z_]+)")

LANE_COMMANDS_SCHEMA = "lmdj.ci-local-lanes.v1"
_LANE_KEYS = {"requires", "commands", "ci_only"}
_REQUIRE_KEYS = {"os", "commands", "any_of", "clean_worktree"}
_ANY_OF_KEYS = {"path", "env"}

PASS = "pass"
CACHED_PASS = "cached-pass"
FAIL = "fail"
NOT_RUNNABLE = "not-runnable-here"
NOT_APPLICABLE = "not-applicable"

# The lane whose CI job owns the documentation-impact step. The declaration is
# checked locally only when this lane is selected, because that is the only
# condition under which CI checks it.
DECLARATION_LANE = "portal"

_DELETED = "0" * 40


def load_classifier():
    """Load the production classifier so lane selection cannot diverge."""
    spec = importlib.util.spec_from_file_location(
        "lmdj_change_scope", CLASSIFIER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the Change Scope classifier: {CLASSIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_lane_commands(
    path: str | Path = LANE_COMMANDS_PATH, *, policy: Mapping[str, object] | None = None
) -> dict[str, dict[str, object]]:
    """Load and validate the lane-to-local-command table."""
    classifier = load_classifier()
    with Path(path).open(encoding="utf-8") as table_file:
        table = json.load(table_file, object_pairs_hook=classifier.reject_duplicates)
    if not isinstance(table, dict) or set(table) != {"schema", "lanes"}:
        raise ValueError("lane command table schema is not closed")
    if table["schema"] != LANE_COMMANDS_SCHEMA:
        raise ValueError(f"unknown lane command schema: {table['schema']!r}")
    lanes = table["lanes"]
    if not isinstance(lanes, dict):
        raise ValueError("lane command table must map lanes to entries")
    if policy is not None and set(lanes) != set(policy["lanes"]):
        missing = sorted(set(policy["lanes"]) - set(lanes))
        extra = sorted(set(lanes) - set(policy["lanes"]))
        raise ValueError(
            "lane command table does not cover the policy lanes: "
            f"missing {missing}, extra {extra}"
        )
    for lane, entry in lanes.items():
        if not isinstance(entry, dict) or set(entry) != _LANE_KEYS:
            raise ValueError(f"lane entry schema is not closed: {lane}")
        commands = entry["commands"]
        if not isinstance(commands, list) or not commands or not all(
            isinstance(command, str) and command for command in commands
        ):
            raise ValueError(f"lane must declare nonempty commands: {lane}")
        if not isinstance(entry["ci_only"], list) or not all(
            isinstance(note, str) and note for note in entry["ci_only"]
        ):
            raise ValueError(f"invalid ci_only notes: {lane}")
        _validate_requires(lane, entry["requires"])
    return lanes


def _validate_requires(lane: str, requires: object) -> None:
    if not isinstance(requires, dict) or not set(requires).issubset(_REQUIRE_KEYS):
        raise ValueError(f"requirement schema is not closed: {lane}")
    for key in ("os", "commands"):
        value = requires.get(key, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            raise ValueError(f"invalid {key} requirement: {lane}")
    any_of = requires.get("any_of", [])
    if not isinstance(any_of, list):
        raise ValueError(f"invalid any_of requirement: {lane}")
    for alternative in any_of:
        if (
            not isinstance(alternative, dict)
            or len(alternative) != 1
            or not set(alternative).issubset(_ANY_OF_KEYS)
        ):
            raise ValueError(f"invalid any_of alternative: {lane}")
    if not isinstance(requires.get("clean_worktree", False), bool):
        raise ValueError(f"invalid clean_worktree requirement: {lane}")


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, check=False
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _split_z(payload: bytes) -> list[str]:
    fields = payload.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    return [field.decode("utf-8", "strict") for field in fields]


def resolve_base_sha(root: Path, base_ref: str) -> str:
    """Return the merge base with the integration branch."""
    try:
        merge_base = _git(root, "merge-base", base_ref, "HEAD").decode().strip()
    except RuntimeError:
        merge_base = ""
    if not merge_base:
        raise RuntimeError(
            f"cannot resolve a merge base with {base_ref!r}; "
            "fetch the integration branch or pass --base-ref"
        )
    return merge_base


def read_working_inventory(root: Path, base_sha: str, classifier) -> tuple:
    """Return every change between the base commit and the working tree.

    `git diff` against a single commit compares that commit to the working
    tree, so uncommitted edits are classified exactly like committed ones.
    Untracked files are added explicitly because `git diff` never reports
    them, and an unclassified new file is precisely what upgrades CI to full
    mode.

    The return value pairs the inventory with the untracked path set, so the
    caller can tell an unclassified stale leftover on disk apart from an
    unclassified tracked path.
    """
    tracked = classifier.parse_name_status_z(
        _git(root, "diff", "--name-status", "-z", base_sha)
    )
    seen = {path for record in tracked for path in record.paths}
    untracked_paths = [
        path
        for path in _split_z(
            _git(root, "ls-files", "--others", "--exclude-standard", "-z")
        )
        if path not in seen
    ]
    untracked = [
        classifier.ChangedFile("A", (path,)) for path in untracked_paths
    ]
    return tuple(tracked) + tuple(untracked), frozenset(untracked_paths)


def name_untracked_cause(reason: str, untracked_paths: frozenset) -> str:
    """Name the cause when an unclassified path is an untracked leftover.

    A stale untracked directory left behind by a reorganisation upgrades every
    local classification to full, and a bare `unclassified path` diagnostic
    names the path but not the cause. Untracked files only exist in the local
    working inventory, so this rewrite is local-only and CI wording is
    unchanged.
    """
    prefix = "unclassified path: "
    if not reason.startswith(prefix) or reason[len(prefix):] not in untracked_paths:
        return reason
    return (
        f"unclassified untracked path: {reason[len(prefix):]} "
        "(on disk but not tracked; remove it, ignore it, or give it a scope "
        "policy rule - it upgrades every local classification here to full)"
    )


def repository_blobs(root: Path) -> dict[str, str]:
    """Map every tracked and untracked path to a content identity.

    Index blob identities are read in one call. Only the paths that differ
    from the index, plus untracked files, are hashed individually, so the
    common case costs one `git ls-files` and a short `git hash-object`.
    """
    blobs: dict[str, str] = {}
    for entry in _split_z(_git(root, "ls-files", "-s", "-z")):
        metadata, _, path = entry.partition("\t")
        fields = metadata.split()
        if len(fields) != 3 or not path:
            raise ValueError(f"unexpected index entry: {entry!r}")
        blobs[path] = fields[1]

    dirty = set(_split_z(_git(root, "diff-files", "--name-only", "-z")))
    dirty.update(
        _split_z(_git(root, "ls-files", "--others", "--exclude-standard", "-z"))
    )
    present = sorted(path for path in dirty if (root / path).is_file())
    for path in sorted(dirty):
        if path not in present:
            blobs[path] = _DELETED
    for chunk_start in range(0, len(present), 256):
        chunk = present[chunk_start:chunk_start + 256]
        hashes = _git(root, "hash-object", "--", *chunk).decode().split()
        if len(hashes) != len(chunk):
            raise RuntimeError("git hash-object returned an unexpected count")
        blobs.update(zip(chunk, hashes))
    return blobs


def lane_input_paths(
    policy: Mapping[str, object], paths: Iterable[str], classifier
) -> dict[str, list[str]]:
    """Group repository paths by the lanes whose result they can change.

    A path that matches a full rule, or that matches no rule at all, upgrades
    the whole run to full mode, so it is an input to *every* lane. Leaving
    those out would let a shared CMake or contract edit hit a stale cached
    pass.
    """
    lanes = list(policy["lanes"])
    grouped: dict[str, set[str]] = {lane: set() for lane in lanes}
    for path in paths:
        matched: set[str] = set()
        for rule in policy["rules"]:
            if classifier._matches(rule["match"], path):
                matched.update(rule["lanes"])
        forces_full = not matched or any(
            classifier._matches(rule["match"], path)
            for rule in policy["full_rules"]
        )
        for lane in lanes if forces_full else matched:
            grouped[lane].add(path)
    return {lane: sorted(members) for lane, members in grouped.items()}


def lane_cache_key(
    lane: str, commands: Sequence[str], inputs: Sequence[str],
    blobs: Mapping[str, str],
) -> str:
    """Digest the lane identity, its commands, and every input's content."""
    digest = hashlib.sha256()
    digest.update(lane.encode("utf-8"))
    digest.update(b"\0")
    for command in commands:
        digest.update(command.encode("utf-8"))
        digest.update(b"\0")
    digest.update(b"\0")
    for path in sorted(inputs):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(blobs.get(path, _DELETED).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "lmdj" / "preflight"


def read_cached_keys(cache_dir: Path, lane: str) -> list[dict[str, str]]:
    """Return the lane's recorded passing states, most recent first.

    Several states are kept because editing a file and reverting it is an
    ordinary development move; a single-slot cache would re-run the lane on
    the way back to a state it already proved.
    """
    entry = cache_dir / f"{lane}.json"
    try:
        with entry.open(encoding="utf-8") as cache_file:
            record = json.load(cache_file)
    except (OSError, ValueError):
        return []
    if not isinstance(record, dict) or record.get("verdict") != PASS:
        return []
    passes = record.get("passes")
    if not isinstance(passes, list):
        return []
    return [
        item for item in passes
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    ]


def has_cached_pass(cache_dir: Path, lane: str, key: str) -> bool:
    return any(item["key"] == key for item in read_cached_keys(cache_dir, lane))


def write_cached_pass(
    cache_dir: Path, lane: str, key: str, *, retain: int = 16
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    recorded = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    passes = [
        item for item in read_cached_keys(cache_dir, lane) if item["key"] != key
    ]
    passes.insert(0, {"key": key, "recorded_at": recorded})
    payload = {
        "lane": lane,
        "verdict": PASS,
        "passes": passes[:retain],
    }
    entry = cache_dir / f"{lane}.json"
    entry.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def worktree_is_clean(root: Path) -> bool:
    return not _git(root, "status", "--porcelain", "-z").strip()


def check_requirements(
    root: Path, requires: Mapping[str, object]
) -> tuple[bool, str]:
    """Return whether this machine can execute the lane, and why not."""
    platforms = requires.get("os", [])
    if platforms and not any(sys.platform.startswith(name) for name in platforms):
        return False, f"requires {' or '.join(platforms)}, running on {sys.platform}"
    for command in requires.get("commands", []):
        if shutil.which(command) is None:
            return False, f"{command} is not on PATH"
    any_of = requires.get("any_of", [])
    if any_of and not any(
        (root / alternative["path"]).exists() if "path" in alternative
        else bool(os.environ.get(alternative["env"]))
        for alternative in any_of
    ):
        rendered = " or ".join(
            alternative.get("path") or f"${alternative['env']}"
            for alternative in any_of
        )
        return False, f"needs one of: {rendered}"
    if requires.get("clean_worktree", False) and not worktree_is_clean(root):
        return False, "requires a clean working tree"
    return True, ""


@dataclass
class LaneResult:
    lane: str
    verdict: str
    detail: str = ""
    duration_seconds: float = 0.0


@dataclass
class DeclarationResult:
    """The verdict on a supplied Pull Request body's impact declaration."""

    verdict: str
    detail: str = ""


def changed_paths(inventory: Iterable) -> list[str]:
    """Flatten the classifier inventory to every path it names.

    Rename records carry both the old and the new path, and the
    documentation-impact checker matches paths individually, so both are
    reported rather than only the destination.
    """
    paths = {path for record in inventory for path in record.paths}
    return sorted(paths)


def read_pr_body(path: str | Path) -> str:
    """Read a Pull Request body, failing closed on anything unreadable."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Pull Request body is not valid UTF-8: {path}") from error
    except OSError as error:
        raise ValueError(f"cannot read the Pull Request body: {error}") from error


def check_declaration(
    root: Path, body: str, paths: Sequence[str], *, portal_selected: bool,
    checker: str | Path = DOC_IMPACT_CHECKER,
) -> DeclarationResult:
    """Run CI's own documentation-impact checker against a local body.

    The checker is reused rather than reimplemented: a second implementation
    would be a second opinion, and the point of the pre-check is to answer
    exactly what CI will answer. It imports only Node builtins, so it needs
    `node` but none of the portal lane's installed dependencies.
    """
    if not portal_selected:
        return DeclarationResult(
            NOT_APPLICABLE,
            f"this change does not select the {DECLARATION_LANE} lane, "
            "so CI does not check the declaration either",
        )
    if shutil.which("node") is None:
        return DeclarationResult(NOT_RUNNABLE, "node is not on PATH")
    if not Path(checker).is_file():
        return DeclarationResult(
            NOT_RUNNABLE, f"the documentation impact checker is missing: {checker}"
        )
    completed = subprocess.run(
        ["node", str(checker)],
        cwd=root, capture_output=True, check=False,
        env={
            **os.environ,
            "PORTAL_PR_BODY": body,
            "PORTAL_CHANGED_FILES": "\n".join(paths),
        },
    )
    if completed.returncode == 0:
        return DeclarationResult(PASS)
    reported = (
        completed.stderr.decode("utf-8", "replace").strip()
        or completed.stdout.decode("utf-8", "replace").strip()
        or f"the checker exited {completed.returncode} without a message"
    )
    return DeclarationResult(FAIL, "; ".join(reported.splitlines()))


def run_lane(
    root: Path, lane: str, commands: Sequence[str], substitutions: Mapping[str, str],
    *, echo: bool = True,
) -> LaneResult:
    """Run a lane's checked-in commands in order, stopping at the first failure."""
    started = time.monotonic()
    for command in commands:
        resolved = command.format(**substitutions)
        if echo:
            print(f"    $ {resolved}", flush=True)
        # The command table is checked-in repository content, not user input.
        completed = subprocess.run(resolved, cwd=root, shell=True, check=False)
        if completed.returncode != 0:
            return LaneResult(
                lane, FAIL, f"`{resolved}` exited {completed.returncode}",
                time.monotonic() - started,
            )
    return LaneResult(lane, PASS, "", time.monotonic() - started)


def build_plan(
    root: Path, base_ref: str, *, only: Sequence[str] | None = None,
    pr_body_path: str | Path | None = None,
) -> dict[str, object]:
    """Resolve the manifest CI would produce and the local inputs per lane."""
    classifier = load_classifier()
    policy = classifier.load_policy(POLICY_PATH)
    lane_commands = load_lane_commands(policy=policy)

    base_sha = resolve_base_sha(root, base_ref)
    head_sha = _git(root, "rev-parse", "HEAD").decode().strip()
    inventory, untracked_paths = read_working_inventory(root, base_sha, classifier)
    # The scope policy exemption has to be computed here too. Unlike CI, this
    # advisory pre-flight deliberately classifies the working tree, so compare
    # its policy with the merge-base policy instead of requiring it to match
    # the committed HEAD blob. Revision-bound consumers keep using the stricter
    # repository helper in `change_scope.py`.
    policy_edit_preserving = False
    if any(
        classifier.SCOPE_POLICY_PATH in record.paths for record in inventory
    ):
        base_policy = classifier.read_merge_base_policy(root, base_sha, head_sha)
        tracked_paths = classifier.read_merge_base_tracked_paths(
            root, base_sha, head_sha
        )
        if base_policy is not None and tracked_paths:
            policy_edit_preserving, _ = (
                classifier.policy_edit_is_classification_preserving(
                    base_policy, policy, tracked_paths
                )
            )
    manifest = classifier.classify(
        policy, inventory, base_sha=base_sha, head_sha=head_sha,
        event_name="pull_request", draft=False, labels=(),
        policy_edit_preserving=policy_edit_preserving,
    )
    if untracked_paths:
        manifest = {
            **manifest,
            "reasons": [
                name_untracked_cause(reason, untracked_paths)
                for reason in manifest["reasons"]
            ],
        }

    selected = [lane for lane, on in sorted(manifest["lanes"].items()) if on]
    # Kept before `--lanes` narrows the run: a local restriction says which
    # lanes to execute here, never which lanes CI would select, and the
    # declaration's applicability mirrors CI rather than this invocation.
    ci_lanes = list(selected)
    if only:
        unknown = sorted(set(only) - set(policy["lanes"]))
        if unknown:
            raise ValueError(f"unknown lane(s): {', '.join(unknown)}")
        selected = [lane for lane in selected if lane in set(only)]

    verified_by_pull_request = pull_request_lanes(root)
    blobs = repository_blobs(root)
    grouped = lane_input_paths(policy, blobs, classifier)
    keys = {
        lane: lane_cache_key(
            lane, lane_commands[lane]["commands"], grouped[lane], blobs
        )
        for lane in selected
    }
    return {
        "base_sha": base_sha,
        "head_sha": head_sha,
        "mode": manifest["mode"],
        "reasons": manifest["reasons"],
        "selected": selected,
        # Which of the selected lanes a Pull Request will actually run, and
        # which will not be verified until a main batch picks the change up.
        "pull_request_verified": [
            lane for lane in selected if lane in verified_by_pull_request],
        "batch_only": [
            lane for lane in selected if lane not in verified_by_pull_request],
        "ci_lanes": ci_lanes,
        "lane_commands": lane_commands,
        "cache_keys": keys,
        "input_counts": {lane: len(grouped[lane]) for lane in selected},
        # The declaration check reuses the inventory that selected the lanes,
        # so the two cannot disagree about what changed. It is deliberately a
        # superset of CI's committed-only diff: an uncommitted portal page edit
        # must not let `none` look valid.
        "changed_paths": changed_paths(inventory),
        "pr_body": read_pr_body(pr_body_path) if pr_body_path is not None else None,
    }


def pull_request_lanes(root: Path) -> frozenset[str]:
    """The lanes a Pull Request can actually run, read from its own workflow.

    Every other selected lane belongs to an admitted main batch, so a change
    that only it owns reaches `main` unverified. Derived from the workflow
    rather than listed here, so the two cannot drift apart.
    """
    try:
        source = (root / PR_WORKFLOW).read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    return frozenset(_LANE_GATE.findall(source))


def execute(
    root: Path, plan: Mapping[str, object], *, cache_dir: Path, use_cache: bool,
    echo: bool = True,
) -> list[LaneResult]:
    results: list[LaneResult] = []
    substitutions = {"base": plan["base_sha"], "head": plan["head_sha"]}
    for lane in plan["selected"]:
        entry = plan["lane_commands"][lane]
        runnable, why_not = check_requirements(root, entry["requires"])
        if not runnable:
            results.append(LaneResult(lane, NOT_RUNNABLE, why_not))
            if echo:
                print(f"  {lane}: {NOT_RUNNABLE} ({why_not})", flush=True)
            continue
        key = plan["cache_keys"][lane]
        if use_cache and has_cached_pass(cache_dir, lane, key):
            results.append(LaneResult(lane, CACHED_PASS, "inputs unchanged"))
            if echo:
                print(f"  {lane}: {CACHED_PASS} (inputs unchanged)", flush=True)
            continue
        if echo:
            print(f"  {lane}: running", flush=True)
        result = run_lane(root, lane, entry["commands"], substitutions, echo=echo)
        if result.verdict == PASS:
            write_cached_pass(cache_dir, lane, key)
        results.append(result)
        if echo:
            suffix = f" ({result.detail})" if result.detail else ""
            print(
                f"  {lane}: {result.verdict}{suffix} "
                f"[{result.duration_seconds:.1f}s]",
                flush=True,
            )
    return results


LEGACY_HOOK_TEMPLATE = """#!/usr/bin/env bash
# Installed by scripts/ci/local_preflight.py --install-hook.
# The pre-flight is advisory: the CI workflow remains the only aggregate decision.
# Bypass with `git push --no-verify` when you intend to push anyway.
set -euo pipefail
exec "$(git rev-parse --show-toplevel)/scripts/local-ci.sh"
"""


HOOK_TEMPLATE = """#!/usr/bin/env bash
# Installed by scripts/ci/local_preflight.py --install-hook (optimistic v1).
# Local verification is advisory; it authorizes no push, merge or release.
# Opt in to the complete selected lane set: LMDJ_PRE_PUSH_FULL=1 git push.
# git push --no-verify bypasses hooks; it grants no additional authorization.
set -euo pipefail
if [[ "${LMDJ_PRE_PUSH_FULL:-0}" != "1" ]]; then
  echo "pre-push: heavy verification not requested (LMDJ_PRE_PUSH_FULL=1 opts in)" >&2
  exit 0
fi
exec "$(git rev-parse --show-toplevel)/scripts/local-ci.sh"
"""


def install_hook(root: Path, *, force: bool = False) -> Path:
    # `force` is retained for CLI compatibility, never as authority to replace
    # a personal hook. Git's hooks directory may be shared by linked worktrees;
    # touch only this explicitly requested target, never enumerate worktrees.
    hooks_dir = Path(
        _git(root, "rev-parse", "--git-path", "hooks").decode().strip()
    )
    if not hooks_dir.is_absolute():
        hooks_dir = root / hooks_dir
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "pre-push"
    if hook.is_symlink() or (hook.exists() and not hook.is_file()):
        raise RuntimeError(f"why: hook is not a regular owned file: {hook}; remedy: inspect it manually; it was not changed")
    if hook.exists():
        existing = hook.read_text(encoding="utf-8", errors="replace")
        if existing not in {HOOK_TEMPLATE, LEGACY_HOOK_TEMPLATE}:
            raise RuntimeError(
                f"why: refusing to overwrite a personal or modified hook: {hook}; "
                "remedy: integrate the opt-in manually; --force does not override ownership"
            )
        if existing == LEGACY_HOOK_TEMPLATE:
            backup = hook.with_name("pre-push.lmdj-before-optimistic")
            if backup.is_symlink() or (backup.exists() and
                    (not backup.is_file() or backup.read_text(encoding="utf-8", errors="replace") != existing)):
                raise RuntimeError(f"why: migration backup already differs: {backup}; remedy: inspect and preserve it manually")
            if not backup.exists():
                with backup.open("x", encoding="utf-8") as handle:
                    handle.write(existing)
                backup.chmod(hook.stat().st_mode & 0o777)
            print(f"preserved old hook at {backup}; restore that exact backup manually if rollback is authorized")
    hook.write_text(HOOK_TEMPLATE, encoding="utf-8")
    hook.chmod(0o755)
    return hook


def _declaration_plan(plan: Mapping[str, object]) -> str:
    """Say whether `--list` expects the declaration to be checked."""
    if plan["pr_body"] is None:
        return "not-provided"
    if DECLARATION_LANE not in plan["ci_lanes"]:
        return NOT_APPLICABLE
    return "planned"


def _render(
    plan: Mapping[str, object], results: Sequence[LaneResult],
    declaration: DeclarationResult | None = None,
) -> str:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.verdict] = counts.get(result.verdict, 0) + 1
    summary = ", ".join(f"{count} {verdict}" for verdict, count in sorted(counts.items()))
    if plan["base_sha"] == plan["head_sha"] and not plan.get("changed_paths"):
        summary = "base equals HEAD; no changes to check"
    else:
        summary = summary or "nothing selected"
    lines = [
        "",
        f"pre-flight: mode={plan['mode']} lanes={len(plan['selected'])} "
        f"({summary})",
    ]
    blocked = [result for result in results if result.verdict == FAIL]
    unrunnable = [result for result in results if result.verdict == NOT_RUNNABLE]
    for result in blocked:
        lines.append(f"  FAIL {result.lane}: {result.detail}")
    for result in unrunnable:
        lines.append(f"  not verified here: {result.lane} ({result.detail})")
    if declaration is not None:
        if declaration.verdict == FAIL:
            lines.append(f"  FAIL declaration: {declaration.detail}")
            lines.append(
                "  the Pull Request body must carry `Documentation impact:`, "
                "`Reason:` and, when required, `Affected portal pages:` as bare "
                "lines; bold or a trailing period defeats the pattern."
            )
        elif declaration.verdict != PASS:
            lines.append(
                f"  declaration not verified here: {declaration.detail}"
            )
    lines.append(
        "  advisory only: task verification is not merge/release evidence; this run "
        "authorizes no push or merge."
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the CI lanes this change selects, locally.",
    )
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--lanes", default="")
    parser.add_argument("--cache-dir", default=str(default_cache_dir()))
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--list", action="store_true", help="resolve without running")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict", action="store_true",
        help="treat not-runnable-here as a failure",
    )
    parser.add_argument(
        "--pr-body", default=None, metavar="FILE",
        help=(
            "check a Pull Request body file's documentation impact declaration "
            "with the same checker CI runs"
        ),
    )
    parser.add_argument("--install-hook", action="store_true")
    parser.add_argument("--force", action="store_true", help="compatibility flag; never overwrites a personal hook")
    parser.add_argument("--declaration-only", action="store_true",
                        help="check --pr-body and exit without executing any selected lane")
    args = parser.parse_args(argv)

    root = ROOT
    try:
        if args.declaration_only and not args.pr_body:
            raise ValueError("why: --declaration-only needs --pr-body FILE; remedy: pass the declaration file")
        if args.install_hook:
            print(f"installed {install_hook(root, force=args.force)}")
            return 0
        only = [lane for lane in args.lanes.split(",") if lane]
        plan = build_plan(
            root, args.base_ref, only=only, pr_body_path=args.pr_body
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"pre-flight failed closed: {error}", file=sys.stderr)
        return 2

    if args.list:
        payload = {
            "mode": plan["mode"],
            "reasons": plan["reasons"],
            "selected": plan["selected"],
            "pull_request_verified": plan["pull_request_verified"],
            "batch_only": plan["batch_only"],
            "input_counts": plan["input_counts"],
            "declaration": _declaration_plan(plan),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(
        f"pre-flight: {plan['mode']} mode, "
        f"{len(plan['selected'])} lane(s): {', '.join(plan['selected']) or 'none'}"
    )
    if plan["batch_only"]:
        # Selected is not the same as verified at merge: a Pull Request runs
        # only the lanes its own workflow gates on. Everything else waits for an
        # admitted main batch, so run it here or push it unverified.
        print(
            "  not run by a Pull Request: "
            f"{', '.join(plan['batch_only'])}"
            " -- run them here (--lanes) or they reach main unverified"
        )
    try:
        # Report the uncached declaration before lanes; declaration-only never
        # invokes the lane executor.
        declaration = None
        if plan["pr_body"] is not None:
            declaration = check_declaration(
                root, plan["pr_body"], plan["changed_paths"],
                portal_selected=DECLARATION_LANE in plan["ci_lanes"],
            )
            if not args.json:
                suffix = f" ({declaration.detail})" if declaration.detail else ""
                print(f"  declaration: {declaration.verdict}{suffix}", flush=True)
        results = [] if args.declaration_only else execute(
            root, plan, cache_dir=Path(args.cache_dir),
            use_cache=not args.no_cache, echo=not args.json,
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"pre-flight failed closed: {error}", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "mode": plan["mode"],
            "results": [
                {
                    "lane": result.lane, "verdict": result.verdict,
                    "detail": result.detail,
                    "duration_seconds": round(result.duration_seconds, 3),
                }
                for result in results
            ],
        }
        if declaration is not None:
            payload["declaration"] = {
                "verdict": declaration.verdict, "detail": declaration.detail,
            }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render(plan, results, declaration))

    verdicts = [result.verdict for result in results]
    if declaration is not None:
        verdicts.append(declaration.verdict)
    if FAIL in verdicts:
        return 1
    if args.strict and NOT_RUNNABLE in verdicts:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
