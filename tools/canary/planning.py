"""Read-only pinned canary preview, NOT release/test/deployment admission.

Only trusted locally installed CI code is imported. Candidate/control Git
objects supply JSON and history, never executable Python. Caller authenticates
main/control observations and progress receipts; this library proves their
internal consistency and ancestry, not GitHub authority. No fetch, writes,
workflow dispatch, AI, version allocation or external credential access.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import sys

from . import records as r

_CI_ROOT = Path(__file__).resolve().parents[2] / "scripts/ci"
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))

import batch_controller
import incremental_batch
import test_scope

POLICY_PATH = "tools/canary/policy.json"
SCHEMA = "lmdj.canary-plan.v1"
_HOSTS = {"creator": "creator-web", "runtime": "web-runtime-host"}
# Closed v1 mapping. A changed projection needs an explicit versioned policy,
# not removal of a consumer in a historical or caller-supplied JSON document.
_SITE_SUITES = {
    "creator": ["creator", "deploy_contract", "package"],
    "docs": ["docs_static", "portal", "deploy_contract"],
    "runtime": ["web_runtime_host", "web_runtime_lab", "deploy_contract", "package"],
}


def _policy(document, test_policy):
    r.require(isinstance(document, dict) and set(document) == {"schema", "repository", "sites"},
              "canary planning policy is not closed")
    r.require(document["schema"] == "lmdj.canary-planning-policy.v1"
              and document["repository"] == "endaye/lmdj", "canary policy identity mismatch")
    r.require(isinstance(document["sites"], dict) and set(document["sites"]) == set(r.SITES),
              "canary site policy inventory is incomplete")
    for site, config in document["sites"].items():
        manifest = "apps/" + _HOSTS[site] + "/module.json" if site in _HOSTS else None
        r.require(isinstance(config, dict) and set(config) == {"suites", "host_manifest"},
                  "canary site policy is not closed")
        r.require(config["suites"] == _SITE_SUITES[site] and config["host_manifest"] == manifest,
                  "canary v1 site projection changed", "review a new policy version and consumer closure")
        r.require(set(config["suites"]) <= set(test_policy.suite_ids), "site maps an unknown suite")
    return deepcopy(document)


def _affected(selection, interval, policy):
    if selection["kind"] == "full":
        return set(r.SITES)
    affected = {site for site, config in policy["sites"].items()
                if set(config["suites"]) & set(selection["suites"])}
    # Host changelogs are also future docs-site source inputs. Do not mistake
    # a no-test explanatory document for a deployed changelog.
    if any(path.startswith("apps/") and path.endswith("/CHANGELOG.md") for path in interval["paths"]):
        affected.add("docs")
    return affected


def _host(inputs, target, site, policy):
    relative = policy["sites"][site]["host_manifest"]
    document = r.decode(inputs._git("show", f"{target}:{relative}"))
    r.require(isinstance(document, dict) and document.get("contract") == "lmdj.module.v1"
              and document.get("module") == _HOSTS[site], "pinned Host manifest identity is invalid")
    version = document.get("version")
    r.require(isinstance(version, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version),
              "pinned Host version is not a supported stable SemVer")
    return {"site": site, "id": document["module"], "version": version,
            "manifest_path": relative, "manifest_digest": r.digest(document)}


def plan_batch(repository_path, *, main_sha, target_sha, control_sha, progress,
               request_id, kind="daily", sites=None, force=False):
    """Return a deterministic preview and leave all input/progress records alone.

main_sha is an externally authenticated observation, not read from a mutable
branch name. Advancing main while target/control/progress stay pinned does not
change the plan. Missing baseline is an explicit bootstrap result, not a fake
complete interval from the repository's root commit. All intervals retain the
canonical policy floor; no AI advice or debt clearance is represented here.
"""
    r.identifier(request_id)
    for revision in (main_sha, target_sha, control_sha):
        r.exact_sha(revision)
    r.require(isinstance(kind, str) and kind in {"daily", "manual"}, "request kind is invalid")
    r.require(type(force) is bool, "force must be boolean")
    requested = list(r.SITES) if sites is None else sites
    r.require(isinstance(requested, (list, tuple)) and len(requested) > 0
              and all(isinstance(site, str) and site in r.SITES for site in requested)
              and len(set(requested)) == len(requested), "requested site inventory is invalid")
    requested = sorted(requested)
    r.require(kind == "manual" or (not force and requested == list(r.SITES)),
              "daily request cannot be forced or site-filtered")
    try:
        return _plan(repository_path, main_sha, target_sha, control_sha, progress,
                     request_id, kind, requested, force)
    except (incremental_batch.BatchError, test_scope.ScopeError) as error:
        raise r.CanaryError(str(error)) from error
    except (OSError, ValueError, TypeError, KeyError) as error:
        if isinstance(error, r.CanaryError):
            raise
        raise r.CanaryError("why: complete pinned planner inputs unavailable; remedy: restore trusted Git/policy inputs") from None


def _plan(root, main, target, control, progress, request_id, kind, requested, force):
    inputs = batch_controller.GitInputs(root, control, lambda: main)
    inputs.refresh()
    # GitInputs verifies ancestry, while the collector enforces the stronger
    # protected-main first-parent interval required by this planner.
    test_scope.collect_interval(root, target, main)
    test_scope.collect_interval(root, control, main)
    current = inputs.policy_at(control)
    policy = _policy(r.decode(inputs._git("show", f"{control}:{POLICY_PATH}")), current)
    progress = r.validate_progress(progress, repository=policy["repository"])
    cache = {}
    selections = []

    def interval(pointer):
        base = pointer["revision"] if pointer else None
        if base in cache:
            result, selection = cache[base]
        elif base is None:
            result = {"kind": "bootstrap", "base_sha": None, "target_sha": target,
                      "commits": None, "paths": None, "changed_path_digest": None}
            selection = test_scope._selection(current, current.suite_ids,
                                             ["explicit bootstrap requires full scope"])
            cache[base] = result, selection
        else:
            result = {"kind": "complete", **test_scope.collect_interval(root, base, target)}
            if not result["commits"]:
                # History was verified, but there is no new work to classify.
                # An absent old policy cannot invent a deployment on every tick.
                selection = test_scope._selection(current, [], ["verified empty interval"])
            else:
                historical = [current]
                policy_refs = dict.fromkeys([base] + [commit["sha"] for commit in result["commits"]])
                for revision in policy_refs:
                    try:
                        historical.append(inputs.policy_at(revision))
                    except (incremental_batch.BatchError, test_scope.ScopeError, ValueError, TypeError, KeyError):
                        historical.append(None)
                selection = test_scope.select_across_policies(result["paths"], historical, complete=True)
            cache[base] = result, selection
        return deepcopy(result), deepcopy(selection)

    version_interval, version_scope = interval(progress["version_accounted"])
    selections.append(version_scope)
    # Formal summary history is retained, but old formal changes do not rerun
    # every daily test. Formal promotion owns a fresh full-candidate gate.
    formal_interval, _ = interval(progress["formal"])
    site_intervals, site_scopes, affected = {}, {}, set()
    for site in r.SITES:
        history, selection = interval(progress["deployments"][site])
        site_intervals[site], site_scopes[site] = history, selection
        if history["kind"] == "bootstrap" or site in _affected(selection, history, policy):
            affected.add(site)
            selections.append(selection)
    selected = set(requested) if force else affected & set(requested)
    hosts = [_host(inputs, target, site, policy) for site in sorted(_HOSTS)] if selected & set(_HOSTS) else []
    policy_digest = r.digest({"canary": policy, "test_policy_digest": current.digest})
    identity = {"repository": policy["repository"], "channel": "canary", "target_sha": target,
                "control_sha": control, "progress_digest": progress["digest"],
                "policy_digest": policy_digest, "kind": kind, "requested_sites": requested, "force": force}
    return r.seal({"schema": SCHEMA, "purpose": "read-only-preview", "admission_evidence": False,
                   "request_id": request_id, **identity, "input_digest": r.digest(identity),
                   "version_interval": version_interval, "formal_interval": formal_interval,
                   "site_intervals": site_intervals, "site_test_floors": site_scopes,
                   "test_floor": test_scope.union_selections(current, selections),
                   "affected_sites": sorted(affected), "deploy_sites": sorted(selected),
                   "build_hosts": hosts})
