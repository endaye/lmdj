#!/usr/bin/env python3
"""NEVER MERGE rehearsal: classify a failed Claude run without exposing its text.

These are untrusted SDK error observations, not review or provider attestations.
No arbitrary error text, model text, headers, paths or exception is emitted.
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path

FILENAME = "claude-execution-output.json"
MAX_BYTES = 8 * 1024 * 1024


def outcome(category="unknown", reason="unclassified_error", http_status=None):
    return {"category": category, "reason": reason, "http_status": http_status}


def summarize(document):
    if not isinstance(document, list) or len(document) > 10000:
        return outcome(reason="execution_unreadable")
    texts, statuses = [], set()
    for item in document:
        if not isinstance(item, dict):
            continue
        # Never search ordinary assistant/tool/user content for error-looking text.
        if not ((item.get("type") == "result" and item.get("is_error") is True)
                or (item.get("type") == "assistant" and item.get("isApiErrorMessage") is True)):
            continue
        for key in ("api_error_status", "error_status", "status_code"):
            value = item.get(key)
            if type(value) is int and 100 <= value <= 599:
                statuses.add(value)
        for key in ("result", "error"):
            if isinstance(item.get(key), str):
                texts.append(item[key][:32768])
        errors = item.get("errors")
        if isinstance(errors, list):
            texts.extend(value[:32768] for value in errors[:16] if isinstance(value, str))
        if item.get("isApiErrorMessage") is True:
            message = item.get("message")
            content = message.get("content", []) if isinstance(message, dict) else []
            if isinstance(content, list):
                texts.extend(value["text"][:32768] for value in content[:16]
                             if isinstance(value, dict) and isinstance(value.get("text"), str))
    text = "\n".join(texts).lower()
    statuses.update(int(value) for value in re.findall(r"\bapi error:\s*([1-5][0-9]{2})\b", text))
    if len(statuses) > 1:
        return outcome(reason="conflicting_status")
    status = next(iter(statuses), None)
    if status == 401:
        category = "authentication"
    elif status == 403:
        category = "permission"
    elif any(value in text for value in ("insufficient quota", "quota exceeded", "insufficient balance")):
        category = "quota"
    elif status == 429:
        category = "rate_limit"
    elif any(value in text for value in ("model_not_found", "unknown model", "model does not exist")):
        category = "model_not_found"
    elif status in (400, 404, 422):
        category = "request_invalid"
    elif status is not None and status >= 500:
        category = "upstream"
    elif "timed out" in text or "timeout" in text or status == 408:
        category = "timeout"
    elif "connection error" in text or "econnrefused" in text or "enotfound" in text:
        category = "network"
    else:
        return outcome(http_status=status)
    return outcome(category, "sdk_error_" + category, status)


def closed_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def read_summary(directory):
    descriptor = None
    try:
        # Fixed job-local filename, no caller-supplied execution path. O_NOFOLLOW
        # and fstat also reject symlinks, directories and FIFO/device inputs.
        descriptor = os.open(Path(directory) / FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            return outcome(reason="execution_unreadable")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return outcome(reason="execution_unreadable")
        return summarize(json.loads(raw, object_pairs_hook=closed_object))
    except FileNotFoundError:
        return outcome(reason="execution_missing")
    except (OSError, ValueError, RecursionError):
        return outcome(reason="execution_unreadable")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main():
    identity = {"repository": os.environ.get("GITHUB_REPOSITORY", ""),
                "run_id": os.environ.get("GITHUB_RUN_ID", ""),
                "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
                "head_sha": os.environ.get("REVIEW_HEAD_SHA", ""),
                "backend": os.environ.get("REVIEW_BACKEND", "")}
    valid = (identity["repository"] == "endaye/lmdj"
             and identity["backend"] in ("glm", "kimi")
             and re.fullmatch(r"[1-9][0-9]{0,19}", identity["run_id"])
             and re.fullmatch(r"[1-9][0-9]{0,5}", identity["run_attempt"])
             and re.fullmatch(r"[0-9a-f]{40}", identity["head_sha"])
             and os.environ.get("RUNNER_TEMP"))
    if not valid:
        print("why: diagnostic identity unavailable; remedy: inspect the trusted job identity; NOT REVIEWED", file=sys.stderr)
        return 2
    print(json.dumps({"diagnostic_only": True, **identity,
                      **read_summary(os.environ["RUNNER_TEMP"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
