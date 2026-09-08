"""Read-only version advice protocol, not an AI executor or release authority.

The caller authenticates Git/control/policy observations and adapter receipts.
Digests bind bytes, not semantic AI coverage or remote authority. No network,
credential access, model tool execution, filesystem writes or Issue POSTs.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from . import planning, records as r
import review_scope

BACKENDS = review_scope.BACKENDS
MAX_BACKEND_SECONDS = review_scope.MAX_BACKEND_SECONDS
MAX_INPUT_BYTES = 400000
MAX_OUTPUT_BYTES = 64000
INPUT_SCHEMA = "lmdj.canary-assessment-input.v1"
OUTPUT_SCHEMA = "lmdj.canary-assessment-output.v1"
HOSTS = ("creator-web", "web-runtime-host")
MANIFESTS = tuple(f"apps/{host}/module.json" for host in HOSTS) + (
    "products/lmdj/version.json", "products/lmdj/assembly.json", "products/lmdj/assembly.lock.json")


def collect(root, *, base_sha, target_sha, control_sha, policy_digest):
    """Collect one bounded, complete batch; large/bootstrap batches stay blocked.

Every first-parent patch is retained, even if the endpoint diff is empty after
a revert. Binary patches use Git's complete encoding. This initial protocol
has no chunking: it never calls a truncated prompt complete. Existing PR review
text is not collected by this Git-only interface and cannot be cited by advice.
"""
    for sha in (base_sha, target_sha, control_sha):
        r.exact_sha(sha)
    r.exact_digest(policy_digest)
    inputs = planning.batch_controller.GitInputs(root, control_sha, lambda: target_sha)
    try:
        interval = planning.test_scope.collect_interval(root, base_sha, target_sha)
        # Control may be newer than target; validate its object without assuming
        # target is current main. Remote main/control authenticity is caller-owned.
        r.require(inputs._git("cat-file", "-t", control_sha).strip() == b"commit", "control is not a commit")
        materials = []

        def add(identity, raw):
            content = raw.decode("utf-8", errors="strict")
            materials.append({"id": identity, "content": content, "digest": r.digest(content)})
            r.require(len(r.canonical(materials)) <= MAX_INPUT_BYTES, "complete input exceeds assessment budget",
                      "implement reviewed complete chunk coverage or request external assessment; never truncate")

        for commit in interval["commits"]:
            add("commit:" + commit["sha"], inputs._git(
                "diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index", "--find-renames",
                commit["parent_sha"], commit["sha"], "--"))
        for endpoint, sha in (("base", base_sha), ("target", target_sha)):
            for path in MANIFESTS:
                raw = inputs._git("show", f"{sha}:{path}")
                r.require(isinstance(r.decode(raw), dict), "pinned manifest is not a JSON object")
                add(endpoint + ":" + path, raw)
        components = []
        by_id = {item["id"]: item for item in materials}
        for host in HOSTS:
            versions = {}
            for endpoint in ("base", "target"):
                manifest = r.decode(by_id[f"{endpoint}:apps/{host}/module.json"]["content"])
                r.require(isinstance(manifest, dict) and manifest.get("contract") == "lmdj.module.v1"
                          and manifest.get("module") == host, "Host manifest identity differs")
                version = manifest.get("version")
                r.require(isinstance(version, str) and re.fullmatch(
                    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version),
                    "Host version is not supported stable SemVer")
                versions[endpoint + "_version"] = version
            components.append({"id": host, **versions})
        document = r.seal({"schema": INPUT_SCHEMA, "repository": "endaye/lmdj",
                           "admission_evidence": False, "base_sha": base_sha, "target_sha": target_sha,
                           "control_sha": control_sha, "policy_digest": policy_digest,
                           "collector_digest": r.digest(Path(__file__).read_text()),
                           "commits": interval["commits"], "components": components, "inputs": materials})
        return _context(document)
    except (planning.incremental_batch.BatchError, planning.test_scope.ScopeError,
            OSError, UnicodeError) as error:
        raise r.CanaryError("why: complete assessment Git inputs unavailable; remedy: restore pinned history and manifests") from error


def _context(document):
    r.require(isinstance(document, dict) and set(document) == {
        "schema", "repository", "admission_evidence", "base_sha", "target_sha", "control_sha",
        "policy_digest", "collector_digest", "commits", "components", "inputs", "digest"
    }, "assessment context fields are not closed")
    r.verify_seal(document)
    r.require(document["schema"] == INPUT_SCHEMA and document["repository"] == "endaye/lmdj"
              and document["admission_evidence"] is False, "assessment context identity differs")
    for key in ("base_sha", "target_sha", "control_sha"):
        r.exact_sha(document[key])
    for key in ("policy_digest", "collector_digest"):
        r.exact_digest(document[key])
    r.require(len(r.canonical(document)) <= MAX_INPUT_BYTES, "complete context exceeds assessment budget")
    commits = document["commits"]
    r.require(isinstance(commits, list), "commit inventory is invalid")
    previous = document["base_sha"]
    ids = []
    for commit in commits:
        r.require(isinstance(commit, dict) and set(commit) == {"sha", "parent_sha", "changes"},
                  "commit record is not closed")
        r.exact_sha(commit["sha"])
        r.require(commit["parent_sha"] == previous, "commit interval is discontinuous")
        previous = commit["sha"]
        ids.append("commit:" + previous)
    r.require(previous == document["target_sha"], "commit interval does not reach target")
    ids += [endpoint + ":" + path for endpoint in ("base", "target") for path in MANIFESTS]
    materials = document["inputs"]
    r.require(isinstance(materials, list) and len(materials) == len(ids), "input inventory is incomplete")
    for expected, item in zip(ids, materials):
        r.require(isinstance(item, dict) and set(item) == {"id", "content", "digest"}
                  and item["id"] == expected and isinstance(item["content"], str)
                  and item["digest"] == r.digest(item["content"]), "input identity or content digest differs")
    components = document["components"]
    r.require(isinstance(components, list) and len(components) == len(HOSTS), "Host inventory is incomplete")
    for host, component in zip(HOSTS, components):
        r.require(isinstance(component, dict) and set(component) == {"id", "base_version", "target_version"}
                  and component["id"] == host, "Host inventory identity differs")
        for endpoint in ("base", "target"):
            item = materials[ids.index(f"{endpoint}:apps/{host}/module.json")]
            manifest = r.decode(item["content"])
            r.require(isinstance(manifest, dict) and manifest.get("module") == host
                      and manifest.get("contract") == "lmdj.module.v1"
                      and manifest.get("version") == component[endpoint + "_version"], "Host version binding differs")
            version = component[endpoint + "_version"]
            r.require(isinstance(version, str) and re.fullmatch(
                r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version),
                "Host context version is not supported stable SemVer")
    return deepcopy(document)


def _text(value):
    r.require(isinstance(value, str) and 0 < len(value.strip()) <= 4000
              and not any(ord(char) < 32 and char not in "\n\t" for char in value),
              "advice prose is empty, oversized or contains control characters")


def validate_advice(context, advice):
    context = _context(context)
    r.require(isinstance(advice, dict) and set(advice) == {"schema", "input_digest", "coverage", "components"},
              "advice fields are not closed")
    r.require(advice["schema"] == OUTPUT_SCHEMA and advice["input_digest"] == context["digest"],
              "advice input identity differs")
    r.require(advice["coverage"] == [item["id"] for item in context["inputs"]], "advice coverage is incomplete")
    r.require(len(r.canonical(advice)) <= MAX_OUTPUT_BYTES, "advice exceeds output budget")
    known = {commit["sha"] for commit in context["commits"]}

    def references(refs, *, required=False):
        r.require(isinstance(refs, list) and all(isinstance(ref, str) and ref in known for ref in refs)
                  and len(set(refs)) == len(refs) and (bool(refs) or not required),
                  "advice commit references are missing, duplicated or invented")

    components = advice["components"]
    r.require(isinstance(components, list) and len(components) == len(HOSTS), "advice component inventory is incomplete")
    for host, item in zip(HOSTS, components):
        r.require(isinstance(item, dict) and set(item) == {
            "id", "impact", "rationale", "unknowns", "references", "dependency_effects", "changelog"
        } and item["id"] == host, "advice component identity or fields differ")
        r.require(isinstance(item["impact"], str) and item["impact"] in {"none", "patch", "minor", "major"},
                  "advice impact is invalid")
        _text(item["rationale"])
        references(item["references"], required=item["impact"] != "none")
        for key in ("unknowns", "dependency_effects"):
            r.require(isinstance(item[key], list) and len(item[key]) <= 30, "advice prose inventory is invalid")
            for text in item[key]:
                _text(text)
        entries = item["changelog"]
        r.require(isinstance(entries, list) and len(entries) <= 30
                  and (bool(entries) or item["impact"] == "none"), "changelog inventory is missing or oversized")
        r.require(item["impact"] != "none" or not entries,
                  "unchanged component cannot announce versioned changelog entries")
        for entry in entries:
            r.require(isinstance(entry, dict) and set(entry) == {"kind", "text", "references"}
                      and isinstance(entry["kind"], str)
                      and entry["kind"] in {"added", "fixed", "changed", "breaking", "migration"},
                      "changelog entry fields or kind differ")
            _text(entry["text"])
            references(entry["references"], required=True)
    return deepcopy(advice)


def next_backend(context, history):
    _context(context)
    r.require(isinstance(history, list) and len(history) <= len(BACKENDS), "assessment history is invalid")
    for index, attempt in enumerate(history):
        r.require(isinstance(attempt, dict) and set(attempt) == {
            "backend", "model", "input_digest", "status", "error_class", "advice"
        } and attempt["backend"] == BACKENDS[index], "assessment fallback order differs")
        r.require(attempt["input_digest"] == context["digest"], "assessment history belongs to another input")
        r.identifier(attempt["model"])
        if attempt["status"] == "advised":
            r.require(index == len(history) - 1 and attempt["error_class"] is None,
                      "valid advice must stop fallback")
            validate_advice(context, attempt["advice"])
        else:
            r.require(attempt["status"] == "failed" and isinstance(attempt["error_class"], str)
                      and attempt["error_class"] in review_scope.ERRORS and attempt["advice"] is None,
                      "failed attempt lacks a finite infrastructure error")
    return None if len(history) == len(BACKENDS) or history and history[-1]["status"] == "advised" else BACKENDS[len(history)]


def observe(context, history, receipt):
    """Consume a caller-authenticated process receipt, never execute model text.

Like review_pipeline.capture, timeout enforcement belongs to the adapter. This
boundary also rejects late success; it does not pretend a timer field kills a
process. Fixed failure categories retain no raw provider output or exception.
"""
    backend = next_backend(context, history)
    r.require(backend is not None, "assessment is already terminal")
    r.require(isinstance(receipt, dict) and set(receipt) == {
        "backend", "model", "input_digest", "elapsed_seconds", "returncode", "error_class", "output"
    } and receipt["backend"] == backend, "adapter receipt fields or backend differ")
    r.require(receipt["input_digest"] == context["digest"], "adapter receipt belongs to another input")
    r.identifier(receipt["model"])
    elapsed = receipt["elapsed_seconds"]
    r.require(type(elapsed) in (int, float) and 0 <= elapsed < float("inf"), "adapter duration is invalid")
    r.require(type(receipt["returncode"]) is int, "adapter return code is invalid")
    error = receipt["error_class"]
    r.require(error is None or isinstance(error, str) and error in review_scope.ERRORS, "adapter error category is invalid")
    if elapsed > MAX_BACKEND_SECONDS:
        error = "timeout"
    elif error is None and receipt["returncode"] != 0:
        error = "runtime_failure"
    advice = None
    if error is None:
        try:
            raw = receipt["output"]
            r.require(isinstance(raw, str) and len(raw.encode("utf-8")) <= MAX_OUTPUT_BYTES, "output exceeds budget")
            advice = validate_advice(context, r.decode(raw))
        except (r.CanaryError, UnicodeError):
            error = "invalid_output"
    return deepcopy(history) + [{"backend": backend, "model": receipt["model"],
                                "input_digest": context["digest"],
                                "status": "failed" if error else "advised",
                                "error_class": error, "advice": advice}]


def finish(context, history):
    r.require(next_backend(context, history) is None, "assessment fallback is not terminal")
    chosen = history[-1] if history[-1]["status"] == "advised" else None
    reason = "backends_unavailable" if chosen is None else None
    if chosen and any(item["impact"] == "major" or item["unknowns"] or any(
            entry["kind"] in {"breaking", "migration"} for entry in item["changelog"])
            for item in chosen["advice"]["components"]):
        reason = "compatibility_review"
    report = None if reason is None else {
        "schema": "lmdj.canary-assessment-report-intent.v1", "reason": reason,
        "id": "canary-assessment:" + reason + ":" + context["digest"], "input_digest": context["digest"],
        "target_sha": context["target_sha"]}
    return r.seal({"schema": "lmdj.canary-assessment-result.v1", "admission_evidence": False,
                   "input_digest": context["digest"], "state": "blocked" if reason else "advised",
                   "selected_backend": chosen["backend"] if chosen else None,
                   "attempts": deepcopy(history), "report_intent": report})
