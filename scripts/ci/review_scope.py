#!/usr/bin/env python3
"""Trusted review/fallback protocol; no model, GitHub writes or credentials.

Adapters supply process receipts, complete Git paths and independently fetched
GitHub identity. Model JSON is only data. T2b owns execution timeout enforcement,
API pagination, immutable artifact upload and guarded COMMENT/label writes.
"""
from __future__ import annotations

import hashlib
import json
import re

import change_scope
import test_scope

# v1 remains the historical producer order.  The v2 registry is deliberately
# separate: old receipts must remain readable, but they are not evidence for a
# PR-Agent attempt.  Keeping both names also lets the inactive T3 adapter read
# old workflow artifacts until T6 activates v2 emission.
BACKENDS = ("glm", "kimi", "grok")
LEGACY_BACKENDS = BACKENDS
V2_BACKENDS = ("deepseek", "glm", "grok", "kimi")
BACKEND_PROVIDERS = {"deepseek": "deepseek", "glm": "zai", "grok": "xai", "kimi": "moonshot"}
HISTORY_SCHEMA_V2 = "lmdj.ci-review-history.v2"
COVERAGE_SCHEMA = "lmdj.pr-agent-coverage.v1"
COLLECTOR_SCHEMA = "lmdj.pr-agent-collector.v1"
TRUSTED_CONFIG_SCHEMA = "lmdj.pr-agent-config-witness.v1"
REVIEW_SCHEMA = "lmdj.ci-review-output.v1"
FAILURE_SCHEMA = "lmdj.ci-review-failure.v1"
ERRORS = frozenset({"missing_credential", "rate_limited", "service_error", "timeout",
                    "invalid_output", "runtime_failure", "budget_exhausted"})
MAX_BACKEND_SECONDS = 300
MAX_TOTAL_SECONDS = MAX_BACKEND_SECONDS * len(BACKENDS)


class ReviewScopeError(ValueError):
    pass


def canonical_json(value):
    """Canonical bytes used by every v2 receipt and marker digest."""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ReviewScopeError("why: protocol evidence is not finite JSON; remedy: regenerate the complete receipt") from error


def digest_of(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def history_digest(history):
    """Digest the complete history object, not a caller-selected attempt."""
    return digest_of(history)


def coverage_digest(receipt):
    return digest_of(receipt)


def _digest(value, label):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
            f"{label} is not an exact SHA-256 digest")
    return value


def _validate_engine(engine):
    require(isinstance(engine, dict), "engine identity is missing")
    require(isinstance(engine.get("name"), str) and engine["name"] == "pr-agent",
            "engine identity is not PR-Agent")
    if "source_commit" in engine:
        require(isinstance(engine["source_commit"], str)
                and re.fullmatch(r"[0-9a-f]{40}", engine["source_commit"]),
                "engine source identity is not exact")
    if "version" in engine:
        require(isinstance(engine["version"], str) and 0 < len(engine["version"]) <= 100,
                "engine version identity is invalid")
    # T2's deployment identity intentionally mixes digests with paths and byte
    # lengths.  Validate each closed shape without mistaking a relative path
    # for a digest or silently dropping the bundle identity.
    if "bundle" in engine:
        bundle = engine["bundle"]
        require(isinstance(bundle, dict) and set(bundle) == {
            "archive_sha256", "archive_byte_length", "manifest_sha256", "adapter_sha256",
            "default_config_sha256", "requirements_lock_sha256", "stock_tokenizer_asset_sha256"
        },
                "engine bundle identity is not closed")
        for key in ("archive_sha256", "manifest_sha256", "adapter_sha256", "default_config_sha256",
                    "requirements_lock_sha256", "stock_tokenizer_asset_sha256"):
            require(re.fullmatch(r"[0-9a-f]{64}", bundle[key]), "engine bundle digest is invalid")
        require(type(bundle["archive_byte_length"]) is int and bundle["archive_byte_length"] >= 0,
                "engine archive identity is invalid")
    if "runtime_config" in engine:
        config = engine["runtime_config"]
        require(isinstance(config, dict) and set(config) == {"sha256", "byte_length"}
                and re.fullmatch(r"[0-9a-f]{64}", config["sha256"])
                and type(config["byte_length"]) is int and config["byte_length"] >= 0,
                "engine runtime configuration identity is invalid")
    return engine


def _identity_matches(source, identity):
    return (source["repository"] == identity["repository"]
            and source["pull_request"] == identity["pr_number"]
            and source["base_sha"] == identity["base_sha"]
            and source["head_sha"] == identity["head_sha"]
            and source["control_sha"] == identity["control_sha"]
            and str(source["run_id"]) == str(identity["run_id"])
            and source["run_attempt"] == identity["run_attempt"])


def _validate_hunk_collection(values, label):
    require(isinstance(values, list), f"{label} hunk inventory is invalid")
    for hunk in values:
        require(isinstance(hunk, dict) and set(hunk) == {
            "id", "path", "old_path", "change_kind", "old_blob", "new_blob", "patch", "right_lines"
        }, f"{label} hunk identity is not closed")
        require(isinstance(hunk["id"], str) and isinstance(hunk["path"], str)
                and isinstance(hunk["change_kind"], str) and isinstance(hunk["right_lines"], list),
                f"{label} hunk fields are invalid")
        old_path = hunk["old_path"]
        require(old_path is None or isinstance(old_path, str) and bool(old_path),
                f"{label} hunk old path is invalid")
        if hunk["change_kind"] == "renamed":
            require(old_path is not None and old_path != hunk["path"],
                    f"{label} rename hunk lacks a distinct old path")
        else:
            require(old_path is None, f"{label} non-rename hunk carries an old path")
        for blob_key in ("old_blob", "new_blob"):
            blob = hunk[blob_key]
            if blob is not None:
                require(isinstance(blob, dict) and set(blob) == {"object_id", "sha256", "byte_length"},
                        f"{label} blob identity is not closed")
                require(isinstance(blob["object_id"], str) and re.fullmatch(r"[0-9a-f]{40}", blob["object_id"])
                        and isinstance(blob["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", blob["sha256"])
                        and type(blob["byte_length"]) is int and blob["byte_length"] >= 0,
                        f"{label} blob identity is invalid")
        patch = hunk["patch"]
        require(isinstance(patch, dict) and set(patch) == {"sha256", "byte_length"}
                and re.fullmatch(r"[0-9a-f]{64}", patch["sha256"])
                and type(patch["byte_length"]) is int and patch["byte_length"] >= 0,
                f"{label} patch identity is invalid")
        for line in hunk["right_lines"]:
            require(type(line) is int and line > 0, f"{label} RIGHT-side line identity is invalid")


def changed_path_inventory(values):
    """Return the complete logical path union, retaining both rename sides."""
    require(isinstance(values, list), "changed path inventory is invalid")
    paths = set()
    for value in values:
        require(isinstance(value, dict)
                and isinstance(value.get("path"), str) and bool(value["path"]),
                "changed path inventory item is invalid")
        old_path = value.get("old_path")
        require(old_path is None or isinstance(old_path, str) and bool(old_path),
                "changed path inventory old path is invalid")
        paths.add(value["path"])
        if old_path is not None:
            paths.add(old_path)
    return sorted(paths)


def validate_collector(collector, *, identity=None):
    """Validate the independently authenticated T2 collector witness."""
    require(isinstance(collector, dict) and set(collector) == {
        "schema", "identity", "input_sha256", "expected_hunks", "right_inventory"
    }, "collector witness schema is not closed")
    require(collector["schema"] == COLLECTOR_SCHEMA, "unsupported collector witness schema")
    source = collector["identity"]
    require(isinstance(source, dict) and set(source) == {
        "repository", "pull_request", "base_sha", "head_sha", "control_sha", "run_id", "run_attempt"
    }, "collector identity is not closed")
    if identity is not None:
        require(_identity_matches(source, identity), "collector identity differs from the exact run")
    _digest(collector["input_sha256"], "collector input")
    _validate_hunk_collection(collector["expected_hunks"], "collector")
    inventory = collector["right_inventory"]
    require(isinstance(inventory, list) and all(isinstance(item, dict) and set(item) == {"path", "line"}
                                                for item in inventory),
            "collector RIGHT-side inventory is not closed")
    expected_inventory = [{"path": hunk["path"], "line": line}
                         for hunk in collector["expected_hunks"] for line in hunk["right_lines"]]
    require(inventory == expected_inventory, "collector RIGHT-side inventory differs from its full hunk partition")
    return collector


def trusted_provider_order(trusted_config=None):
    """Return backend order from the separately authenticated T2 config."""
    if trusted_config is None:
        return list(V2_BACKENDS)
    require(isinstance(trusted_config, dict) and set(trusted_config) == {
        "schema", "provider_order", "providers", "engine"
    }, "trusted T2 configuration witness is not closed")
    require(trusted_config["schema"] == TRUSTED_CONFIG_SCHEMA, "unsupported trusted T2 configuration witness")
    provider_order = trusted_config["provider_order"]
    providers = trusted_config["providers"]
    allowed = {"deepseek", "glm", "xai", "kimi"}
    require(isinstance(provider_order, list) and len(provider_order) == len(set(provider_order))
            and all(provider in allowed for provider in provider_order),
            "trusted T2 provider order is invalid")
    require(isinstance(providers, dict) and set(providers) == {"deepseek", "glm", "xai", "kimi"},
            "trusted T2 provider registry is not closed")
    enabled = []
    for provider in provider_order:
        config = providers[provider]
        require(isinstance(config, dict) and isinstance(config.get("enabled"), bool),
                "trusted T2 provider activation is invalid")
        if config["enabled"]:
            require(isinstance(config.get("model"), str) and bool(config["model"].strip()),
                    "trusted T2 provider model identity is missing")
            enabled.append(provider)
    require(enabled and enabled[0] == "deepseek", "trusted T2 provider order must start with DeepSeek")
    _validate_engine(trusted_config["engine"])
    reverse = {"deepseek": "deepseek", "glm": "glm", "xai": "grok", "kimi": "kimi"}
    return [reverse[provider] for provider in enabled]


def _validate_trusted_binding(receipt, *, trusted_config=None):
    if trusted_config is None:
        return
    order = trusted_provider_order(trusted_config)
    backend = next((backend for backend, provider in BACKEND_PROVIDERS.items()
                    if provider == receipt["provider"]), None)
    require(backend in order, "coverage provider is not enabled in the trusted T2 configuration")
    configured = trusted_config["providers"][BACKEND_PROVIDERS[backend]]
    require(receipt["model"]["requested"] == configured["model"],
            "coverage requested model differs from the trusted T2 configuration")
    require(receipt["engine"] == trusted_config["engine"],
            "coverage bundle or runtime identity differs from the trusted T2 configuration")


def _validate_coverage(identity, receipt, *, require_complete=False, changed_paths=None,
                       collector=None, trusted_config=None):
    """Validate T2's closed coverage receipt at the first consumer boundary."""
    require(isinstance(receipt, dict) and set(receipt) == {
        "schema", "identity", "engine", "provider", "model", "input_sha256",
        "expected_hunks", "observed_hunks", "remaining_files", "failed_chunks",
        "complete", "usage"
    }, "coverage receipt schema is not closed")
    require(receipt["schema"] == COVERAGE_SCHEMA, "unsupported coverage receipt schema")
    source = receipt["identity"]
    require(isinstance(source, dict) and set(source) == {
        "repository", "pull_request", "base_sha", "head_sha", "control_sha", "run_id", "run_attempt"
    }, "coverage identity is not closed")
    if identity is not None:
        require(source["repository"] == identity["repository"]
                and source["pull_request"] == identity["pr_number"]
                and source["base_sha"] == identity["base_sha"]
                and source["head_sha"] == identity["head_sha"]
                and source["control_sha"] == identity["control_sha"]
                and str(source["run_id"]) == str(identity["run_id"])
                and source["run_attempt"] == identity["run_attempt"],
                "coverage identity does not bind the exact repository, head or run attempt")
    require(isinstance(source["run_id"], (str, int)) and not isinstance(source["run_id"], bool),
            "coverage run identity is invalid")
    require(type(source["run_attempt"]) is int and source["run_attempt"] > 0,
            "coverage run attempt is invalid")
    for key in ("base_sha", "head_sha", "control_sha"):
        require(isinstance(source[key], str) and re.fullmatch(r"[0-9a-f]{40}", source[key]),
                "coverage revision identity is invalid")
    _validate_engine(receipt["engine"])
    require(isinstance(receipt["provider"], str) and receipt["provider"] in set(BACKEND_PROVIDERS.values()),
            "coverage provider identity is invalid")
    model = receipt["model"]
    require(isinstance(model, dict) and set(model) == {"requested", "actual", "response_version", "pricing_revision"},
            "coverage model identity is not closed")
    require(isinstance(model["requested"], str) and bool(model["requested"].strip()),
            "coverage requested model identity is missing")
    require(model["actual"] is None or isinstance(model["actual"], str) and bool(model["actual"].strip()),
            "coverage actual model identity is invalid")
    require(model["response_version"] is None or isinstance(model["response_version"], str),
            "coverage response version is invalid")
    require(isinstance(model["pricing_revision"], str) and bool(model["pricing_revision"].strip()),
            "coverage pricing revision is missing")
    _digest(receipt["input_sha256"], "coverage input")
    for collection in ("expected_hunks", "observed_hunks"):
        _validate_hunk_collection(receipt[collection], "coverage")
    require(isinstance(receipt["remaining_files"], list) and all(isinstance(p, str) for p in receipt["remaining_files"])
            and isinstance(receipt["failed_chunks"], list) and all(isinstance(c, str) for c in receipt["failed_chunks"])
            and type(receipt["complete"]) is bool and isinstance(receipt["usage"], dict),
            "coverage completion fields are invalid")
    if require_complete:
        require(receipt["complete"] is True and receipt["expected_hunks"] == receipt["observed_hunks"]
                and receipt["remaining_files"] == [] and receipt["failed_chunks"] == [],
                "coverage is incomplete at the model handler boundary")
        require("source_commit" in receipt["engine"] and "bundle" in receipt["engine"]
                and "runtime_config" in receipt["engine"],
                "reviewed coverage lacks the immutable PR-Agent bundle/runtime identity")
        require(isinstance(model["actual"], str) and bool(model["actual"].strip()),
                "reviewed coverage lacks the actual served model identity")
    if changed_paths is not None:
        require(sorted(set(changed_paths)) == changed_path_inventory(receipt["expected_hunks"]),
                "coverage expected partition does not bind the authenticated changed-path inventory")
    if collector is not None:
        validate_collector(collector, identity=identity)
        require(receipt["input_sha256"] == collector["input_sha256"],
                "coverage input digest differs from the independently authenticated collector")
        require(receipt["expected_hunks"] == collector["expected_hunks"],
                "coverage expected partition differs from the independently authenticated collector")
        expected_inventory = [{"path": hunk["path"], "line": line}
                              for hunk in receipt["expected_hunks"] for line in hunk["right_lines"]]
        require(expected_inventory == collector["right_inventory"],
                "coverage RIGHT-side inventory differs from the independently authenticated collector")
    _validate_trusted_binding(receipt, trusted_config=trusted_config)
    return receipt


def validate_coverage(identity, receipt, *, require_complete=False, changed_paths=None,
                      collector=None, trusted_config=None):
    """Public consumer entry point for T2's immutable coverage witness."""
    return _validate_coverage(identity, receipt, require_complete=require_complete, changed_paths=changed_paths,
                              collector=collector, trusted_config=trusted_config)


def validate_history_v2(policy, history, *, identity=None, coverages=None, changed_paths=None,
                        collector=None, trusted_config=None):
    """Validate closed v2 history and re-bind every referenced receipt digest."""
    require(isinstance(history, dict) and set(history) == {"schema", "attempts"}
            and history["schema"] == HISTORY_SCHEMA_V2, "history v2 schema is not closed")
    attempts = history["attempts"]
    backend_order = trusted_provider_order(trusted_config)
    require(isinstance(attempts, list) and len(attempts) <= len(backend_order), "invalid v2 fallback history")
    coverage_inventory_supplied = coverages is not None
    coverages = coverages or {}
    previous_backend_index = -1
    for index, attempt in enumerate(attempts):
        require(isinstance(attempt, dict) and set(attempt) == {
            "backend", "status", "error_class", "review", "engine", "provider", "model", "coverage_sha256"
        }, "v2 attempt schema is not closed")
        backend = attempt["backend"]
        require(backend in backend_order, "v2 attempt uses a disabled or unknown trusted backend")
        backend_index = backend_order.index(backend)
        require(backend_index > previous_backend_index, "v2 attempts are not in the trusted enabled-provider order")
        previous_backend_index = backend_index
        status = attempt["status"]
        require(status in {"failed", "reviewed"}, "v2 attempt status is invalid")
        if status == "reviewed":
            require(index == len(attempts) - 1 and attempt["error_class"] is None,
                    "a reviewed v2 attempt must terminate fallback")
            if policy is None:
                require(isinstance(attempt["review"], dict)
                        and attempt["review"].get("schema") == REVIEW_SCHEMA,
                        "v2 reviewed attempt lacks the normalized review schema")
            else:
                validate_review(policy, attempt["review"])
            require(attempt["provider"] == BACKEND_PROVIDERS[backend], "actual provider identity disagrees with backend")
            require(isinstance(attempt["model"], dict), "actual model identity is missing")
            _digest(attempt["coverage_sha256"], "coverage")
        else:
            require(isinstance(attempt["error_class"], str) and attempt["error_class"] in ERRORS,
                    "failed v2 attempt must retain a finite infrastructure error")
            require(attempt["review"] is None, "failed v2 attempt cannot claim a review")
        if attempt["coverage_sha256"] is None:
            require(attempt["engine"] is None and attempt["provider"] is None and attempt["model"] is None,
                    "attempt without coverage cannot fabricate engine/provider/model identity")
        else:
            receipt = coverages.get(attempt["coverage_sha256"])
            if coverage_inventory_supplied:
                require(identity is not None, "v2 history consumer identity is required to authenticate coverage")
                require(receipt is not None, "history references an absent coverage receipt")
                require(coverage_digest(receipt) == attempt["coverage_sha256"], "coverage receipt digest mismatch")
                _validate_coverage(identity, receipt, require_complete=status == "reviewed", changed_paths=changed_paths,
                                   collector=collector, trusted_config=trusted_config)
                require(attempt["engine"] == receipt["engine"] and attempt["provider"] == receipt["provider"]
                        and attempt["model"] == receipt["model"],
                        "history does not preserve the referenced bundle/provider/model identity")
                if status == "reviewed" and policy is not None:
                    validate_review(policy, attempt["review"], coverage=receipt, collector=collector,
                                    trusted_config=trusted_config)
    return history


def require(condition, why, remedy="regenerate review from the current trusted run and complete inputs"):
    if not condition:
        raise ReviewScopeError(f"why: {why}; remedy: {remedy}")


def validate_review(policy, payload, *, coverage=None, changed_paths=None, collector=None, trusted_config=None):
    require(isinstance(payload, dict) and set(payload) == {"schema", "summary", "findings", "test_scope"},
            "review output schema is not closed")
    require(payload["schema"] == REVIEW_SCHEMA, "unsupported review output schema")
    require(isinstance(payload["summary"], str) and 0 < len(payload["summary"].strip()) <= 12000,
            "review summary is empty or oversized")
    # Reject the known empty stub, not substantive text discussing placeholders.
    # This exact-token check does not establish semantic review quality.
    require(payload["summary"].strip().casefold() != "placeholder",
            "review summary is a known placeholder", "provide a summary of the current diff review")
    findings = payload["findings"]
    require(isinstance(findings, list) and len(findings) <= 30, "invalid findings array")
    right_lines = set()
    if coverage is not None:
        _validate_coverage(None, coverage, require_complete=True, changed_paths=changed_paths,
                           collector=collector, trusted_config=trusted_config)
        for hunk in coverage["observed_hunks"]:
            right_lines.update((hunk["path"], line) for line in hunk["right_lines"])
    for finding in findings:
        require(isinstance(finding, dict) and set(finding) == {"path", "line", "body"},
                "finding schema is not closed")
        try:
            test_scope._paths([finding["path"]])
        except test_scope.ScopeError as error:
            raise ReviewScopeError(str(error)) from error
        require(type(finding["line"]) is int and finding["line"] > 0,
                "finding line is not a positive integer")
        if coverage is not None:
            require((finding["path"], finding["line"]) in right_lines,
                    "finding is not anchored to an observed changed RIGHT-side line",
                    "emit a clean review or cite an observed changed line")
        require(isinstance(finding["body"], str) and 0 < len(finding["body"].strip()) <= 12000,
                "finding body is empty or oversized")
    advice = payload["test_scope"]
    require(isinstance(advice, dict) and set(advice) == {"labels", "reason"},
            "test_scope advice schema is not closed")
    require(isinstance(advice["labels"], list) and bool(advice["labels"]),
            "review must explicitly recommend test:none, test:full or suite labels")
    try:
        test_scope.labels_to_suites(policy, advice["labels"])
    except test_scope.ScopeError as error:
        raise ReviewScopeError(str(error)) from error
    require(isinstance(advice["reason"], str) and 0 < len(advice["reason"].strip()) <= 4000,
            "test scope reason is empty or oversized")
    require(advice["reason"].strip().casefold() != "placeholder",
            "test scope reason is a known placeholder", "explain the recommended test scope for the current diff")
    return payload


def parse_review(policy, text):
    require(isinstance(text, (str, bytes)) and len(text) <= 400000, "review payload is missing or oversized")
    try:
        payload = json.loads(text, object_pairs_hook=change_scope.reject_duplicates)
    except (ValueError, UnicodeError) as error:
        # Never put arbitrary model output or backend stderr in diagnostics.
        raise ReviewScopeError("why: malformed review JSON; remedy: request a complete structured review") from error
    return validate_review(policy, payload)


def observe_attempt(policy, *, backend, returncode, output=None, error_class=None):
    """A trusted process adapter reports exit/timeout; JSON cannot certify itself.

    Findings are successful review completion, not a reason to change models.
    All returned errors are finite categories, never captured stderr or secrets.
    """
    require(backend in BACKENDS, "unknown backend")
    require(type(returncode) is int, "adapter must supply actual process return code")
    require(error_class is None or (isinstance(error_class, str) and error_class in ERRORS),
            "unknown backend error category")
    if error_class or returncode != 0:
        return {"backend": backend, "status": "failed", "error_class": error_class or "runtime_failure", "review": None}
    try:
        review = parse_review(policy, output)
    except ReviewScopeError:
        return {"backend": backend, "status": "failed", "error_class": "invalid_output", "review": None}
    return {"backend": backend, "status": "reviewed", "error_class": None, "review": review}


def observe_attempt_v2(policy, *, identity, backend, returncode, output=None,
                       error_class=None, coverage=None, collector=None, trusted_config=None):
    """Capture one PR-Agent attempt without treating its engine as its model."""
    require(isinstance(identity, dict) and set(identity) == test_scope.IDENTITY_KEYS,
            "v2 capture identity is not closed")
    require(backend in trusted_provider_order(trusted_config), "unknown or disabled v2 backend")
    require(type(returncode) is int, "adapter must supply actual process return code")
    require(error_class is None or (isinstance(error_class, str) and error_class in ERRORS),
            "unknown backend error category")
    if coverage is not None:
        _validate_coverage(identity, coverage, require_complete=False, collector=collector,
                           trusted_config=trusted_config)
        require(coverage["provider"] == BACKEND_PROVIDERS[backend],
                "coverage provider does not match the selected backend")
        digest = coverage_digest(coverage)
        engine, provider, model = coverage["engine"], coverage["provider"], coverage["model"]
    else:
        digest = engine = provider = model = None
    if error_class or returncode != 0:
        return {"backend": backend, "status": "failed", "error_class": error_class or "runtime_failure",
                "review": None, "engine": engine, "provider": provider, "model": model,
                "coverage_sha256": digest}
    try:
        review = parse_review(policy, output)
    except ReviewScopeError:
        return {"backend": backend, "status": "failed", "error_class": "invalid_output",
                "review": None, "engine": engine, "provider": provider, "model": model,
                "coverage_sha256": digest}
    require(coverage is not None, "reviewed v2 attempt lacks a coverage receipt",
            "retain the complete T2 coverage receipt before publishing")
    require(coverage.get("complete") is True, "reviewed v2 attempt has incomplete coverage")
    return {"backend": backend, "status": "reviewed", "error_class": None, "review": review,
            "engine": engine, "provider": provider, "model": model, "coverage_sha256": digest}


def validate_history(policy, history, **kwargs):
    if isinstance(history, dict) and history.get("schema") == HISTORY_SCHEMA_V2:
        return validate_history_v2(policy, history, **kwargs)
    require(isinstance(history, list) and len(history) <= len(BACKENDS), "invalid fallback history")
    for index, attempt in enumerate(history):
        require(isinstance(attempt, dict) and set(attempt) == {"backend", "status", "error_class", "review"},
                "attempt schema is not closed")
        require(attempt["backend"] == BACKENDS[index], "fallback order must be GLM then Kimi then Grok")
        if attempt["status"] == "reviewed":
            require(index == len(history) - 1 and attempt["error_class"] is None,
                    "a valid review must stop the fallback chain")
            validate_review(policy, attempt["review"])
        else:
            require(attempt["status"] == "failed" and isinstance(attempt["error_class"], str)
                    and attempt["error_class"] in ERRORS and attempt["review"] is None,
                    "failed attempt must retain a finite infrastructure error category")
    return history


def next_backend(policy, history, *, identity=None, coverages=None, changed_paths=None,
                 collector=None, trusted_config=None):
    if isinstance(history, dict) and history.get("schema") == HISTORY_SCHEMA_V2:
        validate_history_v2(policy, history, identity=identity, coverages=coverages, changed_paths=changed_paths,
                            collector=collector, trusted_config=trusted_config)
        # T2 owns provider fallback and returns one complete bounded attempt
        # history.  T3 must never select an outer provider or fabricate a
        # disabled attempt; a nonempty v2 object is already terminal.
        return None
    validate_history(policy, history)
    if len(history) == len(BACKENDS) or (history and history[-1]["status"] == "reviewed"):
        return None
    return BACKENDS[len(history)]


def failure_document(policy, identity, history, *, coverages=None, changed_paths=None,
                     collector=None, trusted_config=None):
    """Only the independent issues-capable reporter consumes this artifact.

    No finding text, backend stderr, token, PR body or diff enters the failure
    artifact. A failed review remains failed even when deterministic scope exists.
    """
    if isinstance(history, dict) and history.get("schema") == HISTORY_SCHEMA_V2:
        validate_history_v2(policy, history, identity=identity, coverages=coverages, changed_paths=changed_paths,
                            collector=collector, trusted_config=trusted_config)
        attempts = history["attempts"]
        backend_order = trusted_provider_order(trusted_config)
    else:
        validate_history(policy, history)
        attempts = history
        backend_order = BACKENDS
    if isinstance(history, dict) and history.get("schema") == HISTORY_SCHEMA_V2:
        require(bool(attempts) and all(a["status"] == "failed" for a in attempts),
                "failure artifact requires actual failed attempts from the bounded engine")
    else:
        require(len(attempts) == len(backend_order) and all(a["status"] == "failed" for a in attempts),
                "failure artifact requires an actual failed or budget-blocked outcome for every backend")
    test_scope._identity(identity)
    require(identity["backend"] == "deterministic", "failed review has no successful model identity")
    core = {key: value for key, value in identity.items() if key != "backend"}
    request_id = test_scope.self_test.digest_of(core)
    return {"schema": FAILURE_SCHEMA, **core, "request_id": request_id,
            "policy_digest": policy.digest, "status": "not-reviewed",
            "attempts": [{"backend": a["backend"], "error_class": a["error_class"]} for a in attempts],
            "why": "all configured review backends are unavailable or returned invalid output",
            "remedy": "restore a backend or record authorized current-head human/agent review; keep deterministic test scope"}


def authenticate_context(identity, *, run, workflow, producer_job, pull,
                         repository_id, workflow_id, producer_job_name,
                         control_is_main_history, run_workflow_bytes, control_workflow_bytes):
    """Check API facts supplied independently of the downloaded model artifact.

    T2b must fetch the actual run attempt and workflow source bytes from trusted
    GitHub/Git endpoints. Display titles are never identities. Workflow code at
    the actual run SHA must equal the independently trusted control workflow;
    edited PR workflow code cannot mint scope authority even if it returns green.
    """
    test_scope._identity(identity)
    require(type(repository_id) is int and repository_id > 0 and type(workflow_id) is int and workflow_id > 0,
            "trusted repository and workflow numeric identities are required")
    require(isinstance(run, dict) and isinstance(workflow, dict) and isinstance(producer_job, dict)
            and isinstance(pull, dict), "independent API identity objects are missing")
    repository = run.get("repository")
    require(isinstance(repository, dict) and repository.get("id") == repository_id
            and repository.get("full_name") == identity["repository"], "run repository identity mismatch")
    require(run.get("id") == identity["run_id"] and run.get("run_attempt") == identity["run_attempt"],
            "run attempt identity mismatch")
    require(workflow.get("id") == workflow_id and run.get("workflow_id") == workflow_id
            and workflow.get("path") == ".github/workflows/pr-review.yml",
            "run is not the independently resolved review workflow")
    require(run.get("event") in {"pull_request", "workflow_dispatch"}, "unsupported review event")
    require(control_is_main_history is True, "control revision is not authenticated main history")
    require(isinstance(run_workflow_bytes, bytes) and bool(run_workflow_bytes)
            and run_workflow_bytes == control_workflow_bytes,
            "run workflow differs from trusted control code", "use the trusted main dispatch entry for this PR")
    require(producer_job.get("run_id") == identity["run_id"]
            and producer_job.get("run_attempt") == identity["run_attempt"]
            and producer_job.get("name") == producer_job_name
            and producer_job.get("status") == "completed" and producer_job.get("conclusion") == "success",
            "producer job did not complete under this exact run attempt")
    head, base = pull.get("head"), pull.get("base")
    require(isinstance(head, dict) and isinstance(base, dict), "PR head/base objects are missing")
    require(pull.get("number") == identity["pr_number"] and pull.get("state") == "open"
            and pull.get("draft") is False and pull.get("merged") is False
            and head.get("sha") == identity["head_sha"] and base.get("ref") == "main",
            "PR is stale or no longer reviewable")
    require(isinstance(head.get("repo"), dict) and head["repo"].get("id") == repository_id
            and head["repo"].get("full_name") == identity["repository"], "fork head cannot use repository review credentials")
    if run["event"] == "workflow_dispatch":
        require(run.get("head_branch") == "main" and run.get("head_sha") == identity["control_sha"],
                "manual review was not dispatched from exact trusted main control")
    else:
        pulls = run.get("pull_requests")
        require(isinstance(pulls, list) and any(isinstance(p, dict) and p.get("number") == identity["pr_number"]
                and isinstance(p.get("head"), dict) and p["head"].get("sha") == identity["head_sha"] for p in pulls),
                "PR event is not bound to the reviewed head")
    return dict(identity)


def _previous_labels(policy, identity, changed_paths, previous_records):
    """An unavailable new backend cannot erase already authenticated advice."""
    labels = set()
    for previous in previous_records:
        require(isinstance(previous, dict), "previous record is not an object")
        expected = {key: previous.get(key) for key in test_scope.IDENTITY_KEYS}
        for key in ("repository", "pr_number", "head_sha", "base_sha", "control_sha"):
            require(expected[key] == identity[key], "cannot combine reviews from different targets or controls")
        test_scope.validate_record(previous, policy, expected)
        require(previous["changed_paths"] == sorted(set(changed_paths)), "prior review diff inventory mismatch")
        labels.update(previous["ai_labels"])
    return labels


def prepare_publication(policy, identity, *, changed_paths, review, previous_records=(), coverage=None,
                        collector=None, trusted_config=None):
    """Create data for a separately guarded publisher, after authentication.

    previous_records are independently authenticated same-head records validated
    against their own retained policy by the caller. Revalidate current-policy
    records here; policy changes belong to the main interval consumer, not model
    evidence merging. Labels are only a display projection, never authority.
    """
    validate_review(policy, review, coverage=coverage, changed_paths=changed_paths,
                    collector=collector, trusted_config=trusted_config)
    labels = _previous_labels(policy, identity, changed_paths, previous_records)
    labels.update(review["test_scope"]["labels"])
    record = test_scope.build_record(policy, changed_paths=changed_paths, ai_labels=sorted(labels), **identity)
    kind = record["effective"]["kind"]
    projection = [f"test:{kind}"] if kind in {"none", "full"} else [f"test:{s}" for s in record["effective"]["suites"]]
    # Legacy publisher remains summary/findings compatible during staging.
    legacy_review = {"summary": review["summary"], "findings": review["findings"]}
    return {"record": record, "labels": projection, "review": legacy_review}


def prepare_result(policy, identity, *, changed_paths, history, previous_records=(), coverages=None,
                   collector=None, trusted_config=None):
    """Bind the publisher result to the actual stopped fallback history."""
    if isinstance(history, dict) and history.get("schema") == HISTORY_SCHEMA_V2:
        validate_history_v2(policy, history, identity=identity, coverages=coverages, changed_paths=changed_paths,
                            collector=collector, trusted_config=trusted_config)
        attempts = history["attempts"]
    else:
        validate_history(policy, history)
        attempts = history
    require(bool(attempts) and next_backend(policy, history, identity=identity, coverages=coverages,
                                            changed_paths=changed_paths, collector=collector,
                                            trusted_config=trusted_config) is None,
            "fallback is not terminal", "finish the bounded backend chain before publishing")
    last = attempts[-1]
    if last["status"] == "reviewed":
        require(identity.get("backend") == last["backend"], "successful backend identity mismatch")
        coverage = None
        if isinstance(history, dict) and history.get("schema") == HISTORY_SCHEMA_V2:
            require(coverages is not None and last["coverage_sha256"] in coverages,
                    "reviewed v2 history lacks its complete coverage receipt")
            coverage = coverages[last["coverage_sha256"]]
        return {"status": "reviewed", "failure": None,
                "publication": prepare_publication(policy, identity, changed_paths=changed_paths,
                                                     review=last["review"], previous_records=previous_records,
                                                     coverage=coverage, collector=collector,
                                                     trusted_config=trusted_config)}
    failure = failure_document(policy, identity, history, coverages=coverages, changed_paths=changed_paths,
                               collector=collector, trusted_config=trusted_config)
    labels = _previous_labels(policy, identity, changed_paths, previous_records)
    fallback = test_scope.build_record(policy, changed_paths=changed_paths,
                                      ai_labels=sorted(labels), **identity)
    return {"status": "not-reviewed", "failure": failure,
            "publication": {"record": fallback, "labels": [], "review": None}}
