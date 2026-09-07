"""Closed, inactive batch reference schema. Standard library only; no I/O."""
from collections.abc import Mapping
from copy import deepcopy
import re
from types import MappingProxyType

SCHEMA = "lmdj.ci-batch-release-reference.v1"
EXECUTOR_EVENTS = frozenset({"workflow_dispatch", "push", "workflow_run", "schedule"})
MAX_DOCUMENT = 1000000


class BatchEvidenceError(ValueError):
    def __init__(self, code, why):
        self.code = code
        super().__init__(f"why: {why}; remedy: obtain complete authenticated full-batch evidence for the exact candidate and review a new reference; do not repair artifacts or substitute a settlement snapshot")


def require(condition, why, code="conflict"):
    if not condition:
        raise BatchEvidenceError(code, why)


def positive(value):
    return type(value) is int and value > 0


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def thaw(value):
    """Produce detached JSON values from deeply immutable model storage."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    return deepcopy(value)


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def parse_reference(value):
    value = thaw(value)
    require(isinstance(value, dict) and set(value) == {
        "schema", "request", "executor_control_revision", "executor_event", "run_attempt",
        "origin_record_digest", "admission_record_digest", "evidence_digest"}, "batch reference schema is not closed")
    require(value["schema"] == SCHEMA and sha(value["executor_control_revision"]), "batch reference source protocol or control is invalid")
    require(isinstance(value["executor_event"], str) and value["executor_event"] in EXECUTOR_EVENTS, "batch executor event is unknown")
    require(type(value["run_attempt"]) is int and value["run_attempt"] == 1, "batch reference is not a fresh first attempt")
    require(all(digest(value[k]) for k in ("origin_record_digest", "admission_record_digest", "evidence_digest")), "batch reference digest is invalid")
    request = value["request"]
    require(isinstance(request, dict) and set(request) == {
        "id", "kind", "base", "target", "control", "policy", "selection", "origin_run"}, "frozen request schema is not closed")
    require(isinstance(request["id"], str) and 0 < len(request["id"]) <= 4096
            and isinstance(request["kind"], str) and request["kind"] in {"auto", "bootstrap", "node", "candidate"}, "frozen request kind or ID is invalid")
    require(sha(request["target"]) and sha(request["control"]) and digest(request["policy"]), "frozen request identity is invalid")
    require((request["base"] is None or sha(request["base"])) and (request["kind"] != "auto" or request["base"] is not None), "frozen request baseline is invalid")
    selection = request["selection"]
    require(isinstance(selection, dict) and set(selection) == {"kind", "suites", "reasons"}
            and selection["kind"] == "full", "focused or none selection cannot certify a candidate")
    for field in ("suites", "reasons"):
        items = selection[field]
        require(isinstance(items, list) and all(isinstance(item, str) and bool(item) for item in items)
                and items == sorted(set(items)), "selection lists must be canonical unique strings")
    require(bool(selection["suites"]), "full selection has no suites")
    origin = request["origin_run"]
    require(isinstance(origin, dict) and set(origin) == {"run_id", "attempt"}
            and positive(origin["run_id"]) and type(origin["attempt"]) is int and origin["attempt"] == 1,
            "origin is not an exact fresh run")
    return value


def parse_source(value):
    require(isinstance(value, dict) and set(value) == {"repository_id", "workflow_id", "workflow_path", "producer_revision"}, "batch source policy is not closed")
    require(positive(value["repository_id"]) and positive(value["workflow_id"])
            and value["workflow_path"] == ".github/workflows/self-test-report.yml"
            and sha(value["producer_revision"]), "batch source policy identity is invalid")
    return freeze(deepcopy(value))
