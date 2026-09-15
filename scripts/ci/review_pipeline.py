#!/usr/bin/env python3
"""Adapters for trusted review jobs; model jobs never receive write authority."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import html
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse

import change_scope
import review_scope
import review_scope_codec as codec
import self_test_report as reporting
import test_scope
import pr_agent_review as t2
import pr_agent_input as input_producer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
import pr_review_target


def read(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=change_scope.reject_duplicates)


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def coverage_inventory(directory):
    """Load every immutable coverage receipt referenced by v2 history."""
    inventory = {}
    for path in sorted(directory.glob("coverage-*.json")):
        receipt = read(path)
        inventory[review_scope.coverage_digest(receipt)] = receipt
    # T2's single-attempt name is accepted for direct adapter integration.
    single = directory / "coverage.json"
    if single.exists():
        receipt = read(single)
        inventory[review_scope.coverage_digest(receipt)] = receipt
    return inventory


def coverage_from_environment(directory):
    source = os.environ.get("COVERAGE_JSON", "")
    if source:
        candidate = Path(source)
        if candidate.exists():
            return read(candidate)
        try:
            return json.loads(source, object_pairs_hook=change_scope.reject_duplicates)
        except (TypeError, ValueError) as error:
            raise review_scope.ReviewScopeError("why: coverage receipt input is not valid JSON; remedy: preserve the complete T2 receipt") from error
    path = directory / "coverage.json"
    return read(path) if path.exists() else None


def collector_witness(document):
    """Authenticate the complete T2 input and retain its full hunk partition."""
    try:
        authenticated = t2.authenticate_input(document)
    except t2.EngineError as error:
        raise review_scope.ReviewScopeError(
            "why: T2 collector input failed its authentication contract; remedy: retain the complete immutable input"
        ) from error
    expected = t2.expected_coverage(authenticated)
    return {
        "schema": review_scope.COLLECTOR_SCHEMA,
        "identity": authenticated["identity"],
        "input_sha256": authenticated["input_sha256"],
        "expected_hunks": expected,
        "right_inventory": [{"path": hunk["path"], "line": line}
                             for hunk in expected for line in hunk["right_lines"]],
    }


def _trusted_config_witness(document):
    """Normalize a separately retained T2 config/engine identity witness."""
    review_scope.require(isinstance(document, dict) and set(document) == {
        "schema", "provider_order", "providers", "engine"
    }, "trusted T2 configuration witness is not closed")
    review_scope.require(document["schema"] == review_scope.TRUSTED_CONFIG_SCHEMA,
                         "unsupported trusted T2 configuration witness")
    review_scope.trusted_provider_order(document)
    return document


def trusted_collector(directory):
    source = os.environ.get("T2_INPUT_JSON", "")
    path = Path(source) if source else directory / "t2-input.json"
    review_scope.require(path.exists(),
                         "v2 result has no separately trusted T2 collector input; retain t2-input.json")
    return collector_witness(read(path))


def trusted_collector_t2(directory, publication_witness=None):
    """Consume opt-in collection only with the caller's positive proof.

    The legacy ``trusted_collector`` path remains unchanged for existing
    callers.  Complete-looking files from ``collect-t2`` are not authority
    unless the successful producer returned this separate witness.
    """
    try:
        document, _context, _receipt = input_producer.verify_publication(directory, publication_witness)
    except input_producer.InputCollectionError as error:
        raise review_scope.ReviewScopeError(
            "why: complete-input publication lacks an independently supplied successful-producer witness; "
            "remedy: use the witness returned by collect-t2 and revalidate retained bytes"
        ) from error
    return collector_witness(document)


def trusted_config(directory):
    source = os.environ.get("T2_TRUSTED_CONFIG_JSON", "")
    path = Path(source) if source else directory / "t2-config-witness.json"
    review_scope.require(path.exists(),
                         "v2 result has no separately trusted T2 config witness; retain t2-config-witness.json")
    return _trusted_config_witness(read(path))


def is_v2_history(history):
    return isinstance(history, dict) and history.get("schema") == review_scope.HISTORY_SCHEMA_V2


def adapt_t2_result(result, *, identity, changed_paths, collector, trusted_config):
    """Map one complete T2 engine result; never create a second fallback loop."""
    review_scope.validate_collector(collector, identity=identity)
    backend_order = review_scope.trusted_provider_order(trusted_config)
    review_scope._validate_engine(trusted_config["engine"])
    review_scope.require(isinstance(result, dict) and result.get("schema") == "lmdj.pr-agent-result.v1"
                         and set(result) == {"schema", "status", "error_class", "identity", "input_sha256",
                                            "engine", "selected_attempt", "attempts", "skipped_providers", "elapsed_ms"},
                         "T2 result schema is not closed")
    expected_t2_identity = {
        "repository": identity["repository"], "pull_request": identity["pr_number"],
        "base_sha": identity["base_sha"], "head_sha": identity["head_sha"],
        "control_sha": identity["control_sha"], "run_id": str(identity["run_id"]),
        "run_attempt": identity["run_attempt"]}
    observed_identity = result["identity"]
    review_scope.require(isinstance(observed_identity, dict) and set(observed_identity) == set(expected_t2_identity)
                         and all((str(observed_identity[key]) == value if key == "run_id"
                                  else observed_identity[key] == value)
                                 for key, value in expected_t2_identity.items()),
                         "T2 result identity differs from the exact run")
    review_scope._digest(result["input_sha256"], "T2 input")
    review_scope.require(result["input_sha256"] == collector["input_sha256"],
                         "T2 result input digest differs from the independently authenticated collector")
    review_scope.require(result["engine"] == trusted_config["engine"],
                         "T2 result bundle or runtime identity differs from the trusted engine witness")
    attempts = result["attempts"]
    review_scope.require(isinstance(attempts, list) and attempts, "T2 result has no bounded provider attempts")
    provider_backend = {provider: backend for backend, provider in review_scope.BACKEND_PROVIDERS.items()}
    history_attempts, coverages = [], {}
    previous_index = -1
    for attempt in attempts:
        review_scope.require(isinstance(attempt, dict) and set(attempt) == {
            "status", "error_class", "error", "provider", "model", "engine", "review", "native_review",
            "coverage", "usage", "duration_ms"}, "T2 attempt schema is not closed")
        backend = provider_backend.get(attempt["provider"])
        review_scope.require(backend is not None, "T2 result uses an unsupported provider identity")
        review_scope.require(backend in backend_order, "T2 result uses a disabled provider or untrusted order")
        index = backend_order.index(backend)
        review_scope.require(index > previous_index, "T2 attempts are not in trusted provider order")
        previous_index = index
        coverage = attempt["coverage"]
        coverage_digest = None
        if coverage is not None:
            review_scope._validate_coverage(identity, coverage, require_complete=attempt["status"] == "reviewed",
                                             changed_paths=changed_paths, collector=collector,
                                             trusted_config=trusted_config)
            review_scope.require(attempt["engine"] == coverage["engine"]
                                 and attempt["provider"] == coverage["provider"]
                                 and attempt["model"] == coverage["model"],
                                 "T2 attempt identity differs from its coverage receipt")
            coverage_digest = review_scope.coverage_digest(coverage)
            coverages[coverage_digest] = coverage
        if attempt["status"] == "reviewed":
            review_scope.require(attempt["error_class"] is None and isinstance(attempt["review"], dict),
                                 "T2 reviewed attempt is incomplete")
            mapped = {"schema": review_scope.REVIEW_SCHEMA,
                      "summary": attempt["review"].get("summary", ""),
                      "findings": attempt["review"].get("findings", []),
                      "test_scope": {"labels": ["test:full"],
                                     "reason": "T2 supplies no LMDJ test-scope advice; retain the deterministic full floor."}}
            review_scope.validate_review(test_scope.load_policy(ROOT), mapped, coverage=coverage,
                                         changed_paths=changed_paths, collector=collector,
                                         trusted_config=trusted_config)
            status, error_class = "reviewed", None
        else:
            review_scope.require(attempt["review"] is None and isinstance(attempt["error_class"], str),
                                 "T2 failed attempt lacks its finite error category")
            error_class = {"deadline_exceeded": "timeout", "transient_network": "service_error",
                           "authentication_error": "missing_credential", "incomplete_coverage": "invalid_output",
                           "invalid_parameter": "invalid_output", "unsupported_model": "service_error"}.get(
                               attempt["error_class"], attempt["error_class"])
            review_scope.require(error_class in review_scope.ERRORS, "T2 result has an unsupported error category")
            status = "failed"
        history_attempts.append({"backend": backend, "status": status, "error_class": error_class,
                                 "review": mapped if status == "reviewed" else None,
                                 "engine": attempt["engine"] if coverage is not None else None,
                                 "provider": attempt["provider"] if coverage is not None else None,
                                 "model": attempt["model"] if coverage is not None else None,
                                 "coverage_sha256": coverage_digest})
    review_scope.require((result["selected_attempt"] is None and result["status"] == "not-reviewed")
                         or (type(result["selected_attempt"]) is int
                             and 0 <= result["selected_attempt"] < len(attempts)
                             and result["status"] == "reviewed"
                             and history_attempts[result["selected_attempt"]]["status"] == "reviewed"),
                         "T2 selected attempt contradicts its terminal status")
    history = {"schema": review_scope.HISTORY_SCHEMA_V2, "attempts": history_attempts}
    review_scope.validate_history_v2(test_scope.load_policy(ROOT), history, identity=identity,
                                     coverages=coverages, changed_paths=changed_paths,
                                     collector=collector, trusted_config=trusted_config)
    return history, coverages


def git(*args):
    result = subprocess.run(["git", "--no-replace-objects", "-C", str(ROOT), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    review_scope.require(result.returncode == 0, "Git input or provenance operation failed",
                         "restore complete repository access and retry the current-head review")
    return result.stdout


def fetch(*refs):
    credential = base64.b64encode(("x-access-token:" + os.environ["GITHUB_TOKEN"]).encode()).decode()
    git("-c", "http.extraheader=AUTHORIZATION: basic " + credential, "fetch", "--no-tags", "origin", *refs)


def api(path, store=None):
    if store is not None and path in store:
        return store[path]
    result = pr_review_target._api(path)
    if store is not None:
        store[path] = result
    return result


def pages(path, key=None):
    result = []
    for page in range(1, 101):
        response = api(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
        items = response.get(key) if key and isinstance(response, dict) else response
        review_scope.require(isinstance(items, list), "GitHub returned an incomplete inventory")
        result.extend(items)
        if len(items) < 100:
            return result
    raise review_scope.ReviewScopeError("why: GitHub pagination limit reached; remedy: explicitly reconcile the complete inventory")


def response_schema(policy):
    """Constrain generation to the same vocabulary the trusted validator accepts."""
    return {
        "type": "object", "additionalProperties": False,
        "required": ["schema", "summary", "findings", "test_scope"],
        "properties": {
            "schema": {"const": review_scope.REVIEW_SCHEMA},
            "summary": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["path", "line", "body"],
                    "properties": {"path": {"type": "string"},
                                   "line": {"type": "integer", "minimum": 1},
                                   "body": {"type": "string"}},
                },
            },
            "test_scope": {
                "type": "object", "additionalProperties": False,
                "required": ["labels", "reason"],
                "properties": {
                    "labels": {
                        "type": "array", "minItems": 1,
                        "items": {"type": "string", "enum": ["test:none", "test:full"]
                                  + [f"test:{suite}" for suite in policy.suite_ids]},
                    },
                    "reason": {"type": "string"},
                },
            },
        },
    }


def collect(directory):
    directory.mkdir(parents=True, exist_ok=True)
    repo, number = os.environ["GITHUB_REPOSITORY"], int(os.environ["PR_NUMBER"])
    target = pr_review_target.resolve_target(repo, number)
    review_scope.require(target["review"] == "true" and target["head_sha"] == os.environ["HEAD_SHA"],
                         "PR target moved or is not reviewable")
    control = git("rev-parse", "HEAD").decode().strip()
    fetch(target["base_sha"], target["head_sha"])
    base = git("merge-base", target["base_sha"], target["head_sha"]).decode().strip()
    diff = git("diff", "--no-ext-diff", "--no-textconv", base, target["head_sha"], "--")
    review_scope.require(0 < len(diff) <= 400000, "review diff is empty or exceeds complete-input budget",
                         "split this PR or record explicit human/agent review; never review a truncated diff")
    changed = change_scope.parse_name_status_z(git("diff", "--no-ext-diff", "--no-textconv", "--name-status",
                                                  "-z", "--find-renames", base, target["head_sha"], "--"))
    identity = dict(repository=repo, pr_number=number, head_sha=target["head_sha"], base_sha=base,
                    control_sha=control, backend="deterministic", run_id=int(os.environ["GITHUB_RUN_ID"]),
                    run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]))
    save(directory / "context.json", {"identity": identity, "changed_paths": sorted({p for c in changed for p in c.paths})})
    (directory / "pr.diff").write_bytes(diff)
    (directory / "pr-body.md").write_text(target["body"])
    save(directory / "history.json", [])
    # Only trusted policy enters this single-line action argument; never PR/model text.
    schema = json.dumps(response_schema(test_scope.load_policy(ROOT)), separators=(",", ":"))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write("review_schema=" + schema + "\n")


def repair_mode(document=None):
    """Only the trusted synchronize entry or explicit dispatch may request repair."""
    requested = os.environ.get("RECHECK_COMMENT_ID", "")
    automatic = os.environ.get("AUTO_RECHECK", "")
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    review_scope.require(automatic in ("", "false", "true"), "invalid automatic recheck mode")
    if automatic == "true":
        review_scope.require(not requested and event == "pull_request"
                             and os.environ.get("PR_EVENT_ACTION") == "synchronize",
                             "automatic repair recheck requires the synchronize entry")
        mode = "batch"
    elif requested:
        review_scope.require(event == "workflow_dispatch" and re.fullmatch(r"[1-9][0-9]*", requested),
                             "repair recheck requires an explicit dispatch comment ID")
        mode = "single"
    else:
        mode = "none"
    if document is not None:
        review_scope.require(("repair_request" in document) == (mode == "single")
                             and ("repair_requests" in document) == (mode == "batch"),
                             "repair artifact differs from trusted trigger mode")
        if mode == "single":
            review_scope.require(document["repair_request"].get("comment_id") == int(requested),
                                 "repair artifact differs from explicit dispatch request")
    return mode


def _record_nothing_reviewable(reason: str) -> None:
    """Publish the honest terminal state of a head with no reviewable bytes.

    `reviewable=false` is the workflow's only signal to skip the model and the
    publisher. It is written before the caller returns, so a failed write ends
    the lane red rather than letting the engine run without an input.
    """
    print(reason, file=sys.stderr)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write("reviewable=false\n")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(
                "\n### No reviewable change at this head\n\n"
                "Every changed path is a tool-generated artifact excluded from the review"
                " input, so no model reviewed this head and no review was published.\n\n"
                "Current-head review eligibility is unchanged: this run supplies no review"
                " evidence.\n\n<pre>" + html.escape(reason) + "</pre>\n")


def collect_t2(directory):
    """Opt-in complete-input collection; legacy ``collect`` remains unchanged."""
    input_producer._ensure_fresh_directory(Path(directory))
    repo, number = os.environ["GITHUB_REPOSITORY"], int(os.environ["PR_NUMBER"])
    expected_head = os.environ["HEAD_SHA"]
    target = pr_review_target.resolve_target(repo, number)
    review_scope.require(target["review"] == "true" and target["head_sha"] == expected_head,
                         "PR target moved or is not reviewable")
    control = git("rev-parse", "HEAD").decode("ascii").strip()
    fetch(target["base_sha"], target["head_sha"])
    base = git("merge-base", target["base_sha"], target["head_sha"]).decode("ascii").strip()
    identity = {
        "repository": repo,
        "pull_request": number,
        "base_sha": base,
        "head_sha": target["head_sha"],
        "control_sha": control,
        "run_id": str(int(os.environ["GITHUB_RUN_ID"])),
        "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
    }
    try:
        document = input_producer.build_input(ROOT, identity)
    except input_producer.GeneratedOnlyInput as error:
        # Every excluded path is a Portal snapshot/provenance artifact: publish
        # the control-plane receipt instead of a complete input, emit the
        # generated-only outcome, and let the model steps stay gated off.  No
        # collection-receipt.json (would impersonate a complete input) and no
        # collection-failure.json (fence semantics) are written.
        digest = input_producer.publish_generated_only(directory, error.receipt)
        output_path = os.environ.get("GITHUB_OUTPUT")
        if output_path:
            with Path(output_path).open("a", encoding="utf-8") as output:
                output.write("generated_only=true\n")
                output.write("generated_receipt_sha256=" + digest + "\n")
        return None
    except input_producer.GeneratedOnlyInventory as error:
        # Nothing at this head is reviewable: every changed path is a
        # deterministic rendering excluded from the bounded input (#1365). That
        # is a terminal state of the lane, not a failed review, and no rerun can
        # change it. Failing here made every squash-witness PR permanently red
        # on a condition the PR could not satisfy (#1371), so the run records
        # why, publishes no review, and leaves eligibility exactly where it was:
        # `review_wait` still sees no review evidence and stays pending.
        input_producer.publish_failure(directory, error.result)
        _record_nothing_reviewable(str(error))
        return None
    except input_producer.InputCollectionError as error:
        if error.result is not None:
            input_producer.publish_failure(directory, error.result)
        raise
    latest = pr_review_target.resolve_target(repo, number)
    review_scope.require(
        latest["review"] == "true"
        and latest["head_sha"] == target["head_sha"]
        and latest["base_sha"] == target["base_sha"],
        "PR target moved before complete-input publication",
    )
    mode = repair_mode()
    if mode != "none":
        import review_recheck
        api = review_recheck.client(repo)
        if mode == "single":
            request = review_recheck.collect(api, document, int(os.environ["RECHECK_COMMENT_ID"]), git=git, fetch=fetch)
            review_recheck.attach(document, request)
        else:
            requests, report = review_recheck.collect_batch(api, document, git=git, fetch=fetch)
            review_recheck.attach_batch(document, requests)
            # Operational selection evidence, not model or resolution authority.
            rendered = json.dumps(report, sort_keys=True, ensure_ascii=True)
            print("Automatic repair recheck selection: " + rendered)
            if os.environ.get("GITHUB_STEP_SUMMARY"):
                with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
                    summary.write("\nAutomatic repair recheck selection:\n\n<pre>" + html.escape(rendered) + "</pre>\n")
    changed_paths = review_scope.changed_path_inventory(document["files"])
    context_identity = {
        "repository": repo,
        "pr_number": number,
        "head_sha": target["head_sha"],
        "base_sha": base,
        "control_sha": control,
        "backend": "deterministic",
        "run_id": int(identity["run_id"]),
        "run_attempt": identity["run_attempt"],
    }
    context = {"identity": context_identity, "changed_paths": changed_paths}
    receipt = input_producer.collection_receipt(document, context)
    artifacts = {
        "context.json": input_producer.json_bytes(context),
        "pr.diff": document["diff"]["text"].encode("utf-8"),
        "pr-body.md": latest["body"].encode("utf-8"),
        "history.json": b"[]",
        "t2-input.json": input_producer.json_bytes(document),
        "collection-receipt.json": input_producer.json_bytes(receipt),
    }
    witness = input_producer.publish_collection(directory, artifacts)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        schema = json.dumps(response_schema(test_scope.load_policy(ROOT)), separators=(",", ":"))
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write("review_schema=" + schema + "\n")
            output.write("t2_publication_witness=" + json.dumps(witness, sort_keys=True, separators=(",", ":")) + "\n")
    return witness


ENGINE_FAILURE_CLASSES = {
    "deadline_exceeded": "timeout", "timeout": "timeout",
    "transient_network": "service_error", "unsupported_model": "service_error",
    "configuration_invalid": "service_error", "engine_unavailable": "service_error",
    "authentication_error": "missing_credential",
    "incomplete_coverage": "invalid_output", "invalid_parameter": "invalid_output",
    "input_invalid": "invalid_output", "invalid_output": "invalid_output",
    "rate_limited": "rate_limited", "budget_exhausted": "budget_exhausted",
    "internal_error": "runtime_failure",
}


def _engine_result(path):
    """Return the engine's result document, or None when it produced none."""
    try:
        return read(path)
    except (OSError, ValueError, RecursionError):
        return None


def engine_failure_history(backend, *, result, trusted_config):
    """One failed v2 attempt for an engine process that returned no complete result.

    A crashed, killed or refused engine still ran under the trusted order, so
    the history records that attempt with a finite error class instead of
    leaving the chain unfinished or pretending nothing was tried.
    """
    order = review_scope.trusted_provider_order(trusted_config)
    review_scope.require(order and order[0] == backend, "engine failure attributed to a backend outside the trusted first provider")
    outcome = os.environ.get("BACKEND_OUTCOME", "failure")
    error_class = "service_error"
    if isinstance(result, dict) and isinstance(result.get("error_class"), str):
        error_class = ENGINE_FAILURE_CLASSES.get(result["error_class"], "service_error")
    if outcome == "cancelled":
        error_class = "timeout"
    return {"schema": review_scope.HISTORY_SCHEMA_V2,
            "attempts": [{"backend": backend, "status": "failed", "error_class": error_class, "review": None,
                          "engine": None, "provider": None, "model": None, "coverage_sha256": None}]}


def capture(directory, backend):
    policy = test_scope.load_policy(ROOT)
    history = read(directory / "history.json")
    context = read(directory / "context.json")
    t2_source = os.environ.get("T2_RESULT_JSON", "")
    t2_path = Path(t2_source) if t2_source else directory / "t2-result.json"
    if t2_source or t2_path.exists():
        collector = trusted_collector(directory)
        trusted = trusted_config(directory)
        changed_paths = test_scope._paths(context.get("changed_paths"))
        review_scope.require(changed_paths == review_scope.changed_path_inventory(collector["expected_hunks"]),
                             "collector full hunk partition differs from the independently fetched changed-path inventory")
        t2 = _engine_result(t2_path)
        if isinstance(t2, dict) and isinstance(t2.get("attempts"), list):
            history, inventory = adapt_t2_result(t2, identity=context["identity"],
                                                  changed_paths=changed_paths, collector=collector,
                                                  trusted_config=trusted)
            if backend is not None:
                selected = history["attempts"][t2["selected_attempt"]]["backend"] if t2["selected_attempt"] is not None else None
                review_scope.require(selected is None or backend == selected,
                                     "capture backend disagrees with complete T2 selected attempt")
        else:
            review_scope.require(isinstance(history, list) and not history,
                                 "engine failure cannot be appended to an existing attempt history")
            history = engine_failure_history(backend, result=t2, trusted_config=trusted)
            inventory = {}
            review_scope.validate_history_v2(policy, history, identity=context["identity"], coverages=inventory,
                                             changed_paths=changed_paths, collector=collector, trusted_config=trusted)
        save(directory / "collector.json", collector)
        save(directory / "t2-config-witness.json", trusted)
        for digest, receipt in inventory.items():
            save(directory / f"coverage-{digest}.json", receipt)
        save(directory / "history.json", history)
        attempts = history["attempts"]
        if attempts[-1]["status"] == "reviewed":
            save(directory / "review.json", attempts[-1]["review"])
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write("reviewed=" + str(attempts[-1]["status"] == "reviewed").lower() + "\n")
        return
    coverage = coverage_from_environment(directory)
    inventory = coverage_inventory(directory)
    collector = trusted_collector(directory) if coverage is not None else None
    trusted = trusted_config(directory) if coverage is not None else None
    provider_backend = {provider: backend for backend, provider in review_scope.BACKEND_PROVIDERS.items()}
    expected_backend = (provider_backend.get(coverage["provider"]) if coverage is not None and isinstance(history, list) and not history
                        else review_scope.next_backend(
                            policy, history, identity=context["identity"],
                            coverages=inventory if is_v2_history(history) else None,
                            changed_paths=context["changed_paths"], collector=collector,
                            trusted_config=trusted))
    review_scope.require(expected_backend == backend, "backend ran outside fallback order")
    outcome = os.environ.get("BACKEND_OUTCOME", "failure")
    error = None if outcome == "success" else "runtime_failure"
    if os.environ.get("BACKEND_AVAILABLE") == "false":
        error = "missing_credential"
    if outcome == "cancelled":
        error = "timeout"
    raw = os.environ.get("REVIEW_JSON", "")
    if backend == "grok" and (directory / "grok.json").exists():
        raw = (directory / "grok.json").read_text()
    if coverage is not None:
        if isinstance(history, list):
            review_scope.require(not history, "cannot mix historical v1 attempts with new-engine v2 coverage")
            history = {"schema": review_scope.HISTORY_SCHEMA_V2, "attempts": []}
        review_scope.require(is_v2_history(history), "coverage requires closed v2 history")
        attempt = review_scope.observe_attempt_v2(
            policy, identity=context["identity"], backend=backend,
            returncode=0 if outcome == "success" else 1, output=raw,
            error_class=error, coverage=coverage, collector=collector, trusted_config=trusted)
        history["attempts"].append(attempt)
        save(directory / f"coverage-{backend}.json", coverage)
        save(directory / "history.json", history)
        if attempt["status"] == "reviewed":
            save(directory / "review.json", attempt["review"])
        status = attempt["status"]
    else:
        review_scope.require(isinstance(history, list), "legacy producer must retain v1 history shape")
        attempt = review_scope.observe_attempt(policy, backend=backend, returncode=0 if outcome == "success" else 1,
                                                output=raw, error_class=error)
        history.append(attempt)
        save(directory / "history.json", history)
        if attempt["status"] == "reviewed":
            save(directory / "review.json", attempt["review"])
        status = attempt["status"]
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write("reviewed=" + str(status == "reviewed").lower() + "\n")


def finalize(directory):
    policy = test_scope.load_policy(ROOT)
    context, history = read(directory / "context.json"), read(directory / "history.json")
    inventory = coverage_inventory(directory)
    collector = trusted_collector(directory) if is_v2_history(history) else None
    trusted = trusted_config(directory) if is_v2_history(history) else None
    review_scope.validate_history(policy, history, identity=context["identity"],
                                  coverages=inventory if is_v2_history(history) else None,
                                  changed_paths=context["changed_paths"], collector=collector,
                                  trusted_config=trusted)
    review_scope.require(review_scope.next_backend(
        policy, history, identity=context["identity"],
        coverages=inventory if is_v2_history(history) else None,
        changed_paths=context["changed_paths"], collector=collector, trusted_config=trusted) is None,
                         "review chain did not finish")
    identity = dict(context["identity"])
    attempts = history["attempts"] if is_v2_history(history) else history
    if attempts[-1]["status"] == "reviewed":
        identity["backend"] = attempts[-1]["backend"]
    result = review_scope.prepare_result(policy, identity, changed_paths=context["changed_paths"], history=history,
                                         coverages=inventory if is_v2_history(history) else None,
                                         collector=collector, trusted_config=trusted)
    save(directory / "result.json", result)
    if result["failure"]:
        save(directory / "failure.json", result["failure"])
    # Receipts are written before the status is judged, so a not-reviewed run
    # still uploads its evidence -- the artifact is how a dropped review is
    # recovered later, and #939 showed one sitting intact for hours.
    return result["status"]


def authenticate(identity, store=None, reuse=False):
    token = ("identity", identity["repository"], identity["run_id"], identity["run_attempt"])
    if reuse and store is not None and token in store:
        return store[token]
    repo = identity["repository"]
    run = api(f"/repos/{repo}/actions/runs/{identity['run_id']}/attempts/{identity['run_attempt']}")
    workflow = api(f"/repos/{repo}/actions/workflows/pr-review.yml", store)
    repository = api(f"/repos/{repo}", store)
    pull = api(f"/repos/{repo}/pulls/{identity['pr_number']}")
    jobs = pages(f"/repos/{repo}/actions/runs/{identity['run_id']}/attempts/{identity['run_attempt']}/jobs", "jobs")
    producers = [j for j in jobs if j.get("name") == "Review fallback"]
    review_scope.require(len(producers) == 1, "unique review producer job is missing")
    fetch("main", run["head_sha"], identity["control_sha"])
    ancestor = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", identity["control_sha"], "origin/main"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0
    result = review_scope.authenticate_context(identity, run=run, workflow=workflow, producer_job=producers[0], pull=pull,
        repository_id=repository["id"], workflow_id=workflow["id"], producer_job_name="Review fallback",
        control_is_main_history=ancestor,
        run_workflow_bytes=git("show", run["head_sha"] + ":.github/workflows/pr-review.yml"),
        control_workflow_bytes=git("show", identity["control_sha"] + ":.github/workflows/pr-review.yml"))
    if reuse and store is not None:
        store[token] = result
    return result


def previous_records(identity, policy, store=None):
    """Read immutable same-head records; mutable labels never enter selection."""
    repo, number = identity["repository"], identity["pr_number"]
    bot = api("/users/github-actions%5Bbot%5D", store)
    records, unavailable = [], False
    for posted in pages(f"/repos/{repo}/pulls/{number}/reviews"):
        if posted.get("commit_id") != identity["head_sha"] or posted.get("user", {}).get("id") != bot.get("id"):
            continue
        for receipt in codec.unavailable_identities(posted.get("body", "")):
            if all(receipt[key] == identity[key] for key in ("repository", "pr_number", "head_sha")):
                authenticate(receipt, store, reuse=True)
                unavailable = True
        prior = codec.decode(posted.get("body", ""))
        if prior is None:
            continue
        prior_identity = {key: prior[key] for key in test_scope.IDENTITY_KEYS}
        authenticate(prior_identity, store, reuse=True)
        review_scope.require(all(prior_identity[key] == identity[key]
                                 for key in ("repository", "pr_number", "head_sha", "base_sha")),
                             "prior scope belongs to a different review target")
        if prior_identity["control_sha"] != identity["control_sha"]:
            # Advice under another control/policy cannot be merged as current
            # evidence. Retain it historically and use the existing full-scope
            # fallback instead of suppressing a valid new review publication.
            unavailable = True
            continue
        test_scope.validate_record(prior, policy, prior_identity)
        records.append(prior)
    return records, unavailable


def publish_model(identity, record, model, *, write=None, scope_unavailable=False,
                  coverage=None, history=None):
    """Validate model summary at its original limit; budget metadata separately."""
    payload = {"summary": model["summary"], "findings": model["findings"]}
    try:
        metadata = codec.unavailable(identity) if scope_unavailable else codec.encode(record)
    except review_scope.ReviewScopeError:
        metadata = codec.unavailable(identity)
    history_marker = None
    history_digest = None
    if history is not None and is_v2_history(history):
        history_marker = codec.encode_history(history)
        history_digest = review_scope.history_digest(history)
    reason = "\n\nScope reason: " + html.escape(model["test_scope"]["reason"])
    if codec.UNAVAILABLE.fullmatch(metadata):
        reason += "\n\nScope persistence unavailable: full self-test fallback is required."
    def append_metadata(path, data):
        body = data["body"] + reason + "\n\n" + metadata
        if len(body.encode()) > codec.MAX_COMMENT_BYTES:
            if history_marker is not None:
                raise review_scope.ReviewScopeError(
                    "why: complete v2 history marker does not fit the COMMENT budget; remedy: retain the immutable artifact and review manually")
            # A valid review must still publish. Missing durable scope can
            # only increase future testing, never silently authorize none.
            body = data["body"] + "\n\nScope persistence unavailable: require full tests.\n" + codec.unavailable(identity)
        review_scope.require(len(body.encode()) <= codec.MAX_COMMENT_BYTES, "COMMENT exceeds platform-safe body budget")
        if write is not None:
            return write(path, {**data, "body": body})
        return pr_review_target.github_request("POST", "https://api.github.com" + path, os.environ["GITHUB_TOKEN"], {**data, "body": body})
    return pr_review_target.publish_review(identity["repository"], identity["pr_number"], identity["head_sha"],
        str(identity["run_id"]), str(identity["run_attempt"]), identity["backend"], payload,
        write=append_metadata, coverage=coverage, history_digest=history_digest,
        history_marker=history_marker)


REPAIR_REFUSAL_SCHEMA = "lmdj.pr-agent-recheck-refusal.v1"
MAX_REPAIR_REFUSAL_REASON_BYTES = 1024
REPAIR_REFUSAL_REMEDY = "recheck the current head manually, or recollect the repair context on the next entry"
AUTHORED_REMEDY = "; remedy: "


def bounded_clause(text):
    """One artifact-safe clause: single line, no wrap, bounded in UTF-8 bytes."""
    return " ".join(text.split()).encode("utf-8")[:MAX_REPAIR_REFUSAL_REASON_BYTES].decode("utf-8", "ignore")


def repair_refusal_receipt(error, *, receipts=None):
    """Bounded receipt for an authored repair-recheck refusal.

    The validated review and its labels are already published when the
    rechecks run, so a refused repair-verdict section costs only the rechecks.
    Only authored refusal text is recorded: the recheck protocol keeps model
    output, response bodies, credentials and traces out of those messages, and
    a reporter failure is projected to a literal because its message can embed
    an external error or response body.
    """
    if isinstance(error, reporting.ReportingError):
        text = "the reporting client refused the repair recheck"
    elif isinstance(error, t2.EngineError):
        text = error.safe_message
    else:
        text = str(error)
    # Authored refusals carry their remedy in the same message (`why: ...;
    # remedy: ...`). Bound the clauses separately: bounding the message as one
    # string would let a long `why` truncate the remedy away, leaving only the
    # generic literal for a refusal that named its own next step.
    why, separator, remedy = text.partition(AUTHORED_REMEDY)
    receipt = {"schema": REPAIR_REFUSAL_SCHEMA, "status": "refused",
               "why": bounded_clause(why),
               "remedy": bounded_clause(remedy) if separator and remedy.strip() else REPAIR_REFUSAL_REMEDY}
    if receipts:
        # review_recheck.publish_batch persists each far-side receipt as it
        # lands; recording the refusal must not erase published effects.
        receipt["receipts"] = receipts
    return receipt


def publish(directory):
    context, result = read(directory / "context.json"), read(directory / "result.json")
    history = read(directory / "history.json")
    coverages = coverage_inventory(directory)
    collector = trusted_collector(directory) if is_v2_history(history) else None
    trusted = trusted_config(directory) if is_v2_history(history) else None
    record = result["publication"]["record"]
    identity = {key: record[key] for key in test_scope.IDENTITY_KEYS}
    # The workflow's environment, not downloaded files, fixes this publication.
    review_scope.require(identity["repository"] == os.environ["GITHUB_REPOSITORY"]
        and identity["pr_number"] == int(os.environ["PR_NUMBER"])
        and identity["head_sha"] == os.environ["HEAD_SHA"]
        and identity["run_id"] == int(os.environ["GITHUB_RUN_ID"])
        and identity["run_attempt"] == int(os.environ["GITHUB_RUN_ATTEMPT"])
        and identity["control_sha"] == git("rev-parse", "HEAD").decode().strip(), "artifact identity differs from publisher context")
    store = {}
    authenticate(identity, store)
    policy = test_scope.load_policy(ROOT)
    fetch(identity["base_sha"], identity["head_sha"])
    actual = change_scope.read_git_inventory(ROOT, identity["base_sha"], identity["head_sha"])
    paths = review_scope.changed_path_inventory([
        {"path": changed.paths[-1],
         "old_path": changed.paths[0] if len(changed.paths) == 2 else None}
        for changed in actual
    ])
    review_scope.require(paths == context["changed_paths"] and paths == record["changed_paths"], "artifact changed inventory mismatch")
    expected_changes = sorted({
        ("modified" if hunk["change_kind"] == "binary" else hunk["change_kind"],
         (hunk["old_path"], hunk["path"]) if hunk["old_path"] is not None else (hunk["path"],))
        for hunk in collector["expected_hunks"]
    }) if collector is not None else None
    actual_changes = sorted({
        ({"A": "added", "C": "copied", "D": "deleted", "M": "modified", "R": "renamed", "T": "type_changed"}[changed.status[0]], changed.paths)
        for changed in actual
    })
    review_scope.require(collector is None or actual_changes == expected_changes,
                         "artifact changed-file status/path pairs differ from the independently authenticated collector")
    expected = review_scope.prepare_result(policy, identity, changed_paths=paths, history=history,
                                           coverages=coverages if is_v2_history(history) else None,
                                           collector=collector, trusted_config=trusted)
    review_scope.require(result == expected, "producer result is inconsistent with actual input and validated history")
    prior, scope_unavailable = previous_records(identity, policy, store)
    result = review_scope.prepare_result(policy, identity, changed_paths=paths,
                                        history=history, previous_records=prior,
                                        coverages=coverages if is_v2_history(history) else None,
                                        collector=collector, trusted_config=trusted)
    record = result["publication"]["record"]
    try:
        codec.encode(record)
    except review_scope.ReviewScopeError:
        scope_unavailable = True
    if scope_unavailable:
        # The path inventory is known, but prior review scope inputs are not
        # complete. T1's explicit incomplete-input state is conservatively full.
        record = test_scope.build_record(policy, changed_paths=paths, ai_labels=record["ai_labels"], complete=False, **identity)
        result["publication"]["labels"] = ["test:full"]
    save(directory / "scope.json", record)
    if result["status"] != "reviewed":
        raise review_scope.ReviewScopeError("why: all review backends failed; remedy: inspect failure.json or take over current-head review")
    original = read(directory / "review.json")
    attempts = history["attempts"] if is_v2_history(history) else history
    coverage = coverages.get(attempts[-1]["coverage_sha256"]) if is_v2_history(history) else None
    review_scope.validate_review(policy, original, coverage=coverage, collector=collector, trusted_config=trusted)
    review_scope.require(original == attempts[-1]["review"], "original review artifact mismatch")
    repair_document = read(directory / "t2-input.json") if is_v2_history(history) else {}
    mode = repair_mode(repair_document)
    repair_native = None
    if mode != "none":
        raw_result = read(directory / "t2-result.json")
        raw_history, _ = adapt_t2_result(raw_result, identity=identity, changed_paths=paths,
                                        collector=collector, trusted_config=trusted)
        review_scope.require(raw_history == history, "repair native result differs from authenticated review history")
        selected = raw_result["attempts"][raw_result["selected_attempt"]]
        repair_native = selected["native_review"]
        mapped = t2._validate_native_mapping(repair_native, t2.authenticate_input(repair_document))
        review_scope.require(mapped == selected["review"], "repair native verdict differs from captured review")
    token = os.environ["GITHUB_TOKEN"]
    # Immutable COMMENT review stores the complete scope record beyond artifact
    # retention. The marker is outside untrusted model text and base64 encoded.
    duplicate = [p for p in prior if p["run_id"] == identity["run_id"] and p["run_attempt"] == identity["run_attempt"]]
    review_scope.require(not duplicate or all(p == record for p in duplicate), "existing publication identity has different content")
    if not duplicate:
        publish_model(identity, record, original, scope_unavailable=scope_unavailable,
                      coverage=coverage, history=history)
    authenticate(identity, store)  # Head check immediately before label mutation.
    labels_url = f"https://api.github.com/repos/{identity['repository']}/issues/{identity['pr_number']}/labels"
    # Additive labels cannot remove another session's label. Structured records,
    # not mutable accumulated labels, are authoritative for actual selection.
    pr_review_target.github_request("POST", labels_url, token, {"labels": result["publication"]["labels"]})
    authenticate(identity, store)  # A race remains historical evidence, never current.
    if repair_native is not None:
        import review_recheck
        import review_wait
        api = review_recheck.client(identity["repository"])
        try:
            if mode == "batch":
                receipt = review_recheck.publish_batch(api, repair_document, repair_native, git=git, fetch=fetch,
                            record=lambda value: save(directory / "repair-recheck.json", value))
            else:
                receipt = review_recheck.publish(api, repair_document, repair_native, git=git, fetch=fetch)
        except (review_scope.ReviewScopeError, t2.EngineError, reporting.ReportingError,
                review_wait.Refused) as error:
            # The review and its labels are already published, and
            # review_recheck revalidates every verdict before it touches a
            # thread, so an authored refusal here ends the rechecks only --
            # never the head's review, and never a resolution. `Refused` is the
            # recheck protocol's own authored refusal (a bare ValueError), which
            # collect_batch already reports per candidate. Transport and
            # unresolved-write failures (GitHubApiError, OSError, urllib
            # errors) stay fatal: they need reconciliation, not a receipt.
            persisted = {}
            try:
                persisted = read(directory / "repair-recheck.json")
            except (OSError, ValueError, TypeError, RecursionError):
                persisted = {}
            receipts = persisted.get("receipts") if isinstance(persisted, dict) else None
            refusal = repair_refusal_receipt(
                error, receipts=receipts if isinstance(receipts, list) else None)
            save(directory / "repair-recheck.json", refusal)
            # Exactly one bounded line; the receipt carries the same evidence.
            print(f"Repair recheck refused; the validated review and labels stand. "
                  f"why: {refusal['why']}; remedy: {refusal['remedy']}")
        else:
            save(directory / "repair-recheck.json", receipt)


GENERATED_MARKER = re.compile(
    r"^<!-- lmdj-review-generated-v1 ([\w.-]+/[\w.-]+) ([1-9][0-9]*) ([0-9a-f]{40}) "
    r"([1-9][0-9]*) ([1-9][0-9]*) sha256=([0-9a-f]{64}) -->$", re.M)


def publish_generated(directory):
    """Publish the generated-only receipt COMMENT for a receipt-only REVIEW_DIR.

    The receipt artifact and the workflow environment, not model output, fix
    this publication; the same duplicate-rejection rule as ``publish()``
    applies because concurrency cancellation can rerun the same head.
    """
    path = directory / "generated-only-receipt.json"
    review_scope.require(path.is_file() and not path.is_symlink(),
                         "generated-only receipt artifact is missing")
    receipt = read(path)
    review_scope.require(isinstance(receipt, dict) and set(receipt) == {
        "schema", "status", "identity", "head_sha", "excluded_generated", "receipt_sha256"},
        "generated-only receipt schema is not closed")
    review_scope.require(receipt["schema"] == input_producer.GENERATED_ONLY_RECEIPT_SCHEMA
                         and receipt["status"] == "generated-only", "unsupported generated-only receipt")
    identity = receipt["identity"]
    review_scope.require(isinstance(identity, dict) and set(identity) == set(input_producer.IDENTITY_KEYS),
                         "generated-only receipt identity is not closed")
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    review_scope.require(type(receipt["receipt_sha256"]) is str
                         and receipt["receipt_sha256"] == hashlib.sha256(
                             input_producer.json_bytes(unsigned)).hexdigest(),
                         "generated-only receipt self-describing digest differs")
    excluded = receipt["excluded_generated"]
    review_scope.require(isinstance(excluded, dict) and set(excluded) == {"count", "paths", "entries"}
                         and isinstance(excluded["paths"], list) and excluded["paths"]
                         and excluded["count"] == len(excluded["paths"])
                         and all(isinstance(name, str) and name.startswith(
                                 input_producer.PORTAL_GENERATED_DIRECTORY_PREFIXES)
                                 for name in excluded["paths"]),
                         "generated-only receipt names paths outside the Portal classes")
    review_scope.require(identity["repository"] == os.environ["GITHUB_REPOSITORY"]
        and identity["pull_request"] == int(os.environ["PR_NUMBER"])
        and identity["head_sha"] == receipt["head_sha"] == os.environ["HEAD_SHA"]
        and identity["run_id"] == str(int(os.environ["GITHUB_RUN_ID"]))
        and identity["run_attempt"] == int(os.environ["GITHUB_RUN_ATTEMPT"])
        and identity["control_sha"] == git("rev-parse", "HEAD").decode().strip(),
        "artifact identity differs from publisher context")
    repository, number, head = identity["repository"], identity["pull_request"], identity["head_sha"]
    run, attempt = identity["run_id"], str(identity["run_attempt"])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    authenticate({"repository": repository, "pr_number": number, "head_sha": head,
                  "base_sha": identity["base_sha"], "control_sha": identity["control_sha"],
                  "backend": "deterministic", "run_id": int(run), "run_attempt": identity["run_attempt"]})
    marker = pr_review_target.generated_identity(repository, number, head, run, attempt, digest)
    bot = api("/users/github-actions%5Bbot%5D")
    duplicates = []
    for posted in pages(f"/repos/{repository}/pulls/{number}/reviews"):
        if posted.get("commit_id") != head or posted.get("user", {}).get("id") != bot.get("id"):
            continue
        for found in GENERATED_MARKER.findall(posted.get("body", "")):
            if (found[0], int(found[1]), found[2]) == (repository, number, head) \
                    and found[3] == run and found[4] == attempt:
                duplicates.append(found)
    review_scope.require(all(found[5] == digest for found in duplicates),
                         "existing publication identity has different content")
    if not duplicates:
        pr_review_target.publish_generated(repository, number, head, run, attempt, digest)
    return marker


def http_refusal_evidence(error):
    """Bounded diagnostic hints, never a retry decision or raw response log."""
    endpoint = "unknown"
    numbers = {}
    reason = "unknown"
    try:
        url = urllib.parse.urlsplit(error.url)
        if url.scheme == "https" and url.netloc == "api.github.com":
            repo = r"/repos/[^/]+/[^/]+"
            for pattern, category in (
                (repo + r"/actions/runs/[0-9]+/attempts/[0-9]+", "run-attempt"),
                (repo + r"/actions/runs/[0-9]+(?:/attempts/[0-9]+)?/jobs", "run-jobs"),
                (repo + r"/actions/workflows/[^/]+", "workflow"),
                (repo + r"/pulls/[0-9]+/reviews", "reviews"),
                (repo + r"/pulls/[0-9]+", "pull-request"),
                (repo + r"/issues/[0-9]+/labels", "labels"),
                (repo, "repository"),
                (r"/users/[^/]+", "user"),
            ):
                if re.fullmatch(pattern, url.path):
                    endpoint = category
                    break
        for header, field in (("x-ratelimit-remaining", "remaining"),
                              ("x-ratelimit-reset", "reset"),
                              ("retry-after", "retry-after")):
            value = error.headers.get(header) if error.headers is not None else None
            if isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}", value):
                numbers[field] = str(int(value))
        if numbers.get("remaining") == "0":
            reason = "primary-rate-limit"
        else:
            # Read once, with an extra byte solely to detect overflow. A write
            # adapter may already have consumed this stream: empty is unknown.
            raw = error.read(4097)
            if isinstance(raw, bytes) and len(raw) <= 4096:
                body = json.loads(raw, object_pairs_hook=change_scope.reject_duplicates)
                message = body.get("message") if isinstance(body, dict) else None
                if isinstance(message, str):
                    if message.startswith("You have exceeded a secondary rate limit"):
                        reason = "secondary-rate-limit"
                    elif message == "Resource not accessible by integration":
                        reason = "integration-permission"
                    elif message == "Resource not accessible by personal access token":
                        reason = "token-permission"
    except Exception:
        # Diagnostic parsing failure must neither mask the original HTTP error
        # nor expose its message. Any previously validated fields remain useful.
        pass
    return f" endpoint={endpoint} reason={reason}" + "".join(
        f" {field}={value}" for field, value in numbers.items())


def publisher_error_category(error):
    """Project only closed categories; API wrappers retain an explicit cause.

    Never format an external exception: messages, URLs, commands, HTTP bodies
    and even custom exception class names can carry credentials. The bounded
    walk also terminates for malformed or cyclic cause chains.
    """
    for _ in range(8):
        if isinstance(error, urllib.error.HTTPError):
            code = error.code
            suffix = f" status={code}" if type(code) is int and 100 <= code <= 599 else ""
            if type(code) is int and code in (403, 429):
                suffix += http_refusal_evidence(error)
            return "http-error" + suffix
        for kind, category in (
            (TimeoutError, "timeout"),
            (subprocess.TimeoutExpired, "timeout"),
            (urllib.error.URLError, "network-error"),
            (FileNotFoundError, "file-missing"),
            (PermissionError, "permission-denied"),
            (json.JSONDecodeError, "invalid-json"),
            (UnicodeError, "invalid-encoding"),
            (KeyError, "missing-field"),
            (OSError, "os-error"),
        ):
            if isinstance(error, kind):
                return category
        error = error.__cause__
        if error is None:
            break
    return "unexpected-error"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["collect", "collect-t2", "capture", "finalize", "publish",
                                            "publish-generated"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--backend", choices=review_scope.V2_BACKENDS)
    args = parser.parse_args()
    try:
        if args.command == "capture":
            capture(args.directory, args.backend)
        elif args.command == "collect-t2":
            collect_t2(args.directory)
        elif args.command == "publish-generated":
            publish_generated(args.directory)
        elif args.command == "finalize":
            status = finalize(args.directory)
            if status != "reviewed":
                # The job is named `Review fallback` and its conclusion is what
                # a reader scanning job names sees. Reporting success here for a
                # run where no model reviewed makes that name a lie -- a check
                # whose passing condition is met without the thing it exists to
                # produce. The lane as a whole never lost the distinction: the
                # publisher refuses a not-reviewed result and the workflow's own
                # `Manual takeover` step is guarded on `failure()` and says "NOT
                # REVIEWED", so it was written expecting this exit and did not
                # get it. Receipts are already saved above; only the verdict
                # changes.
                print(f"why: no model reviewed this head (status={status}); "
                      "remedy: rerun the review, restore a backend, or record an "
                      "authorized current-head human/agent review",
                      file=sys.stderr)
                return 1
        else:
            globals()[args.command](args.directory)
    except Exception as error:
        if args.command in ("publish", "publish-generated") and isinstance(error, review_scope.ReviewScopeError):
            # `publish` only, and its refusals are the ones nobody can
            # diagnose. Every `review_scope.require` in `publish()` carries an
            # authored message -- "artifact identity differs from publisher
            # context", "artifact changed inventory mismatch", "producer result
            # is inconsistent with actual input and validated history" -- and
            # the generic line below was discarding all of them. #939: the
            # publisher drops roughly one review in four and no log says which
            # precondition fired, so no remedy can be designed honestly. The
            # messages did not need writing; they needed to stop being
            # destroyed.
            #
            # This deliberately does not extend to the other commands, whose
            # exceptions can describe provider output. `publish` runs after the
            # model is gone -- it reads its own artifacts and the GitHub API --
            # so its refusals are authored literals about identity and
            # inventory, with no provider text in scope to leak. The same holds
            # for `publish-generated`, whose inputs are the receipt artifact
            # and the GitHub API.
            print(str(error), file=sys.stderr)
            return 1
        if args.command == "collect-t2" and isinstance(
                error, (review_scope.ReviewScopeError, input_producer.InputCollectionError,
                        pr_review_target.TargetUnavailable)):
            # collect-t2 runs before the engine exists: no provider text can be
            # in scope, and its refusals are authored literals -- "PR target
            # moved or is not reviewable", "why: changed Git inventory exceeds
            # the file limit after generated artifacts are excluded; remedy:
            # ...". The generic line below destroyed them, so a refused
            # collection surfaced as an unrelated artifact-upload error with no
            # recorded cause (#1310: 2787-file change refused over MAX_FILES).
            print(str(error), file=sys.stderr)
            return 1
        if args.command in ("publish", "publish-generated"):
            print("why: review pipeline operation failed "
                  f"(category={publisher_error_category(error)}); "
                  "remedy: inspect the failure category and reconcile the exact "
                  "run's retained evidence and GitHub state before retrying; "
                  "take over review if unresolved", file=sys.stderr)
            return 1
        # CLI/provider exceptions can contain credentials or raw model text.
        print("why: review pipeline operation failed; remedy: inspect bounded structured receipts and retry or review manually", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
