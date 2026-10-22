"""Closed batch reference schema. Standard library only; no I/O."""
from collections.abc import Mapping
from copy import deepcopy
import re
from types import MappingProxyType

SCHEMA = "lmdj.ci-batch-release-reference.v1"
# v2: the v1 record of the primary candidate run plus `retries`, exactly one
# lane-scoped retry record (#2422 item 8). Every run is still attempt 1.
SCHEMA_V2 = "lmdj.ci-batch-release-reference.v2"
_RECORD_KEYS = {"schema", "request", "executor_control_revision", "executor_event", "run_attempt",
                "origin_record_digest", "admission_record_digest", "evidence_digest"}
_RETRY_KEYS = (_RECORD_KEYS - {"schema"}) | {"executor_run_id"}
_REQUEST_KEYS = {"id", "kind", "base", "target", "control", "policy", "selection", "origin_run"}
ENVIRONMENTAL_CONCLUSIONS = frozenset({"timed_out", "cancelled"})
DEBT_OUTCOMES = frozenset({"blocked", "cancelled", "infrastructure", "missing"})
EXECUTOR_EVENTS = frozenset({"workflow_dispatch", "push", "workflow_run", "schedule"})
MAX_DOCUMENT = 4000000


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


def _parse_record(value, *, kinds, selection_kinds, extra=frozenset()):
    """One run's record: its frozen request, executor identity and digests."""
    keys = (_RECORD_KEYS - {"schema"}) | set(extra)
    require(isinstance(value, dict) and set(value) == keys, "batch reference schema is not closed")
    require(sha(value["executor_control_revision"]), "batch reference source protocol or control is invalid")
    require(isinstance(value["executor_event"], str) and value["executor_event"] in EXECUTOR_EVENTS, "batch executor event is unknown")
    require(type(value["run_attempt"]) is int and value["run_attempt"] == 1, "batch reference is not a fresh first attempt")
    require(all(digest(value[k]) for k in ("origin_record_digest", "admission_record_digest", "evidence_digest")), "batch reference digest is invalid")
    request = value["request"]
    request_keys = _REQUEST_KEYS | ({"retry_of"} if "retry" in kinds else set())
    require(isinstance(request, dict) and set(request) == request_keys, "frozen request schema is not closed")
    require(isinstance(request["id"], str) and 0 < len(request["id"]) <= 4096
            and isinstance(request["kind"], str) and request["kind"] in kinds, "frozen request kind or ID is invalid")
    require(sha(request["target"]) and sha(request["control"]) and digest(request["policy"]), "frozen request identity is invalid")
    require((request["base"] is None or sha(request["base"])) and (request["kind"] != "auto" or request["base"] is not None), "frozen request baseline is invalid")
    selection = request["selection"]
    require(isinstance(selection, dict) and set(selection) == {"kind", "suites", "reasons"}
            and selection["kind"] in selection_kinds, "focused or none selection cannot certify a candidate")
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


def _parse_retry(record, primary):
    """The retry record composes with the primary: same target and policy, the
    primary's request named, a closed environmental proof per retried suite."""
    _parse_record(record, kinds={"retry"}, selection_kinds={"focused", "full"}, extra={"executor_run_id"})
    require(positive(record["executor_run_id"]), "retry record names no exact executor run")
    request = record["request"]
    require(request["target"] == primary["target"] and request["policy"] == primary["policy"],
            "retry does not share the candidate's target and policy")
    retry_of = request["retry_of"]
    require(isinstance(retry_of, dict) and set(retry_of) == {"request", "environmental"}
            and retry_of["request"] == primary["id"] and isinstance(retry_of["environmental"], dict)
            and set(retry_of["environmental"]) == set(request["selection"]["suites"]),
            "retry proof does not name the candidate and exactly the retried suites")
    for suite, proof in retry_of["environmental"].items():
        require(isinstance(proof, dict) and set(proof) == {"outcome", "jobs"} and isinstance(proof["jobs"], dict)
                and (proof["outcome"] in DEBT_OUTCOMES and not proof["jobs"]
                     or proof["outcome"] == "failed" and bool(proof["jobs"])
                     and all(isinstance(job, str) and bool(job) and conclusion in ENVIRONMENTAL_CONCLUSIONS
                             for job, conclusion in proof["jobs"].items())),
                f"retry proof for {suite} is not a closed environmental proof")
    return record


def parse_reference(value):
    value = thaw(value)
    require(isinstance(value, dict) and value.get("schema") in {SCHEMA, SCHEMA_V2}, "batch reference source protocol or control is invalid")
    composite = value["schema"] == SCHEMA_V2
    require(set(value) == _RECORD_KEYS | ({"retries"} if composite else set()), "batch reference schema is not closed")
    record = {key: item for key, item in value.items() if key not in ("schema", "retries")}
    _parse_record(record, kinds={"auto", "bootstrap", "node", "candidate"}, selection_kinds={"full"})
    if composite:
        retries = value["retries"]
        require(isinstance(retries, list) and len(retries) == 1, "a composite reference carries exactly one retry")
        _parse_retry(retries[0], value["request"])
    return value


def parse_source(value):
    require(isinstance(value, dict) and set(value) == {"repository_id", "workflow_id", "workflow_path", "producer_revision"}, "batch source policy is not closed")
    require(positive(value["repository_id"]) and positive(value["workflow_id"])
            and value["workflow_path"] == ".github/workflows/self-test-report.yml"
            and sha(value["producer_revision"]), "batch source policy identity is invalid")
    return freeze(deepcopy(value))
