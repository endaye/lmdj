"""Durable assessment phases over the existing authenticated Journal/outbox.

Configure a separate assessment Journal. Callers authenticate run identities and
hold the real shared short writer lock; a boolean or digest is not authority.
This module never initializes storage, invokes models or resets lost claims.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import zlib

from . import assessment as a, records as r
import self_test_report as reporting

MAX_RAW_BYTES = 600000
MAX_EVENT_BYTES = 45000  # Leave space for the authenticated Issue envelope.
CHUNK_BYTES = 30000
MAX_PACKED_BYTES = 810000
SCHEMA = "lmdj.canary-assessments.v1"


def pack(document):
    raw = r.canonical(document)
    r.require(len(raw) <= MAX_RAW_BYTES, "assessment record exceeds uncompressed budget",
              "implement complete reviewed chunk storage; never truncate assessment evidence")
    value = {"encoding": "zlib-base64", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
             "body": base64.b64encode(zlib.compress(raw)).decode("ascii")}
    r.require(len(r.canonical(value)) <= MAX_PACKED_BYTES, "assessment encoding exceeds its bounded representation")
    return value


def unpack(value):
    r.require(isinstance(value, dict) and set(value) == {"encoding", "bytes", "sha256", "body"}
              and value["encoding"] == "zlib-base64" and type(value["bytes"]) is int
              and 0 < value["bytes"] <= MAX_RAW_BYTES and isinstance(value["body"], str)
              and len(value["body"]) <= MAX_PACKED_BYTES, "packed assessment schema or size differs")
    r.exact_digest(value["sha256"])
    try:
        compressed = base64.b64decode(value["body"], validate=True)
        r.require(base64.b64encode(compressed).decode("ascii") == value["body"], "packed assessment encoding is not canonical")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, value["bytes"] + 1)
        r.require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
                  and len(raw) == value["bytes"] and hashlib.sha256(raw).hexdigest() == value["sha256"],
                  "packed assessment bytes, length or digest differ")
        document = r.decode(raw)
        r.require(r.canonical(document) == raw, "packed assessment JSON is not canonical")
        return document
    except (ValueError, zlib.error):
        raise r.CanaryError("why: packed assessment is corrupt or incomplete; remedy: restore exact retained bytes, never re-execute a claim") from None


def _executor(executor, context):
    r.require(isinstance(executor, dict) and set(executor) == {"run_id", "attempt", "control_sha"}
              and all(type(executor[key]) is int and executor[key] > 0 for key in ("run_id", "attempt"))
              and executor["control_sha"] == context["control_sha"], "assessment executor identity differs")
    return deepcopy(executor)


def _result(context, result):
    r.require(isinstance(result, dict) and "attempts" in result, "terminal assessment result is missing")
    r.require(a.finish(context, result["attempts"]) == result, "terminal assessment differs from validated protocol result")
    return deepcopy(result)


def reduce(state, event):
    r.require(isinstance(event, dict) and set(event) == {"id", "epoch", "generation", "type", "data"}
              and event["epoch"] == state["epoch"], "assessment event schema or epoch differs")
    fingerprint = r.digest(event)
    r.identifier(event["id"])
    if event["id"] in state["events"]:
        r.require(state["events"][event["id"]] == fingerprint, "assessment event ID reused with changed bytes")
        return deepcopy(state)
    r.require(type(event["generation"]) is int and event["generation"] == state["generation"]
              and len(r.canonical(event)) <= MAX_EVENT_BYTES, "assessment event sequence or size differs")
    data = event["data"]
    r.require(isinstance(data, dict), "assessment event data is not an object")
    answer = deepcopy(state)
    if event["type"] == "blob":
        r.require(set(data) == {"blob", "index", "total", "text"}, "assessment chunk schema differs")
        key = r.exact_digest(data["blob"])
        r.require(type(data["total"]) is int and 1 <= data["total"] <= 30
                  and type(data["index"]) is int and 0 <= data["index"] < data["total"]
                  and isinstance(data["text"], str) and data["text"].isascii()
                  and 0 < len(data["text"]) <= CHUNK_BYTES, "assessment chunk inventory or size differs")
        blob = answer["blobs"].setdefault(key, {"total": data["total"], "chunks": [], "document": None})
        r.require(blob["total"] == data["total"] and len(blob["chunks"]) == data["index"]
                  and blob["document"] is None, "assessment chunks were reordered, replaced or repeated")
        blob["chunks"].append(data["text"])
        if len(blob["chunks"]) == blob["total"]:
            encoded = "".join(blob["chunks"])
            r.require(len(encoded) <= MAX_PACKED_BYTES, "assembled assessment exceeds encoded budget")
            value = r.decode(encoded)
            r.require(r.canonical(value).decode("ascii") == encoded and r.digest(value) == key,
                      "assembled assessment encoding or identity differs")
            blob["document"] = unpack(value)
    elif event["type"] == "claim":
        key = r.exact_digest(data.get("input_digest"))
        r.require(set(data) == {"input_digest", "context", "executor"} and key not in answer["assessments"],
                  "assessment input was already claimed")
        context = a._context(_blob(answer, data["context"]))
        r.require(context["digest"] == key, "claim context differs from input identity")
        answer["assessments"][key] = {"context": data["context"], "executor": _executor(data["executor"], context), "result": None}
    elif event["type"] == "complete":
        key = r.exact_digest(data.get("input_digest"))
        r.require(set(data) == {"input_digest", "executor", "result"} and key in answer["assessments"],
                  "terminal assessment has no original claim")
        row = answer["assessments"][key]
        _executor(data["executor"], _blob(answer, row["context"]))
        r.require(data["executor"] == row["executor"] and row["result"] is None,
                  "terminal assessment changed owner or was already persisted")
        _result(_blob(answer, row["context"]), _blob(answer, data["result"]))
        row["result"] = data["result"]
    else:
        r.require(False, "unknown assessment event type")
    answer["generation"] += 1
    answer["events"][event["id"]] = fingerprint
    return answer


def _blob(state, key):
    r.exact_digest(key)
    r.require(key in state["blobs"] and state["blobs"][key]["document"] is not None,
              "assessment payload is missing or only partially persisted")
    return state["blobs"][key]["document"]


def _row(state, key):
    row = state["assessments"][key]
    return {"context": _blob(state, row["context"]), "executor": row["executor"],
            "result": _blob(state, row["result"]) if row["result"] else None}


class AssessmentFailure(reporting.Report):
    def issue_body(self, assignee):
        return "\n".join([self.key_marker, "## " + self.title, "",
            "Persisted version-assessment evidence, not a product test verdict or release permission.",
            "CI reports only; external people/tools handle compatibility decisions and repairs.",
            "No PR merge gate, automatic repair or automatic Issue closure is added.", "",
            f"Default assignee: @{assignee}.", "", self.comment_body(first=True)])


def _report(row):
    context, result = row["context"], row["result"]
    if result is None or result["report_intent"] is None:
        return None
    reason = result["report_intent"]["reason"]
    owner = row["executor"]
    # Prose from models is deliberately not interpolated into a privileged
    # Issue write. Complete advice is retained in the assessment journal.
    lines = [f"- Input: `{context['digest']}`; result: `{result['digest']}`",
             f"- Base: `{context['base_sha']}`; target: `{context['target_sha']}`",
             f"- Control: `{context['control_sha']}`; policy: `{context['policy_digest']}`",
             f"- Executor: https://github.com/endaye/lmdj/actions/runs/{owner['run_id']}/attempts/{owner['attempt']}",
             f"- Reason: `{reason}`"]
    lines += [f"- {attempt['backend']} / requested `{attempt['model']}`: "
              + (attempt["error_class"] or attempt["status"]) for attempt in result["attempts"]]
    lines += ["- Next step: inspect the retained complete assessment; restore a backend or resolve compatibility externally.",
              "- Do not repeat an unknown execution or Issue POST; reconcile exact persisted identities first."]
    return AssessmentFailure(key="canary-assessment-" + reason.replace("_", "-"),
        title="canary assessment: " + reason.replace("_", " "),
        observation="assessment/" + context["digest"] + "/" + result["digest"], severity="medium",
        labels=(reporting.REPORT_LABEL, "area:ci-release"), summary="\n".join(lines),
        detail="Complete input, independent Host advice and terminal attempts remain in the authenticated assessment journal.")


class Assessments:
    def __init__(self, journal, lock_held, epoch):
        r.identifier(epoch)
        self.journal, self.lock_held, self.epoch = journal, lock_held, epoch

    def load(self):
        r.require(self.lock_held() is True, "assessment storage lacks its shared writer lock")
        state = {"schema": SCHEMA, "epoch": self.epoch, "generation": 0, "assessments": {}, "blobs": {}, "events": {}}
        try:
            for event in self.journal.load():
                state = reduce(state, event)
            return state
        except Exception:
            raise r.CanaryError("why: assessment journal cannot be authenticated or replayed; remedy: reconcile its original checkpoint and complete history") from None

    def _persist(self, state, kind, data):
        r.require(self.lock_held() is True, "assessment append lost its shared writer lock")
        event = {"id": f"assessment:{state['generation']}", "epoch": self.epoch,
                 "generation": state["generation"], "type": kind, "data": data}
        expected = reduce(state, event)
        try:
            self.journal.append(event)
            r.require(self.load() == expected, "assessment append lacks confirmed persisted state")
            return expected
        except Exception:
            raise r.CanaryError("why: assessment append outcome is unresolved; remedy: reload and reconcile the original claim/result, never repeat model execution") from None

    def _store(self, state, document):
        value = pack(document)
        key = r.digest(value)
        encoded = r.canonical(value).decode("ascii")
        chunks = [encoded[index:index + CHUNK_BYTES] for index in range(0, len(encoded), CHUNK_BYTES)]
        existing = state["blobs"].get(key)
        if existing:
            r.require(existing["total"] == len(chunks) and existing["chunks"] == chunks[:len(existing["chunks"])],
                      "partially persisted assessment bytes changed")
        for index in range(len(existing["chunks"]) if existing else 0, len(chunks)):
            state = self._persist(state, "blob", {"blob": key, "index": index, "total": len(chunks), "text": chunks[index]})
        r.require(_blob(state, key) == document, "stored assessment does not match complete original bytes")
        return state, key

    @staticmethod
    def _view(row, action):
        return {"action": action, "admission_evidence": False, **deepcopy(row)}

    def claim(self, context, executor):
        context = a._context(context)
        executor = _executor(executor, context)
        state = self.load()
        key = context["digest"]
        if key in state["assessments"]:
            row = _row(state, key)
            r.require(row["context"] == context, "claimed context changed under its digest")
            return self._view(row, "terminal" if row["result"] else "pending")
        state, reference = self._store(state, context)
        self._persist(state, "claim", {"input_digest": key, "context": reference, "executor": executor})
        return self._view({"context": context, "executor": executor, "result": None}, "execute")

    def complete(self, input_digest, executor, result):
        key = r.exact_digest(input_digest)
        state = self.load()
        r.require(key in state["assessments"], "terminal assessment has no persisted claim")
        row = _row(state, key)
        _executor(executor, row["context"])
        r.require(executor == row["executor"], "terminal assessment does not belong to the claimed executor")
        result = _result(row["context"], result)
        if row["result"] is not None:
            r.require(row["result"] == result, "terminal assessment cannot be replaced")
        else:
            state, reference = self._store(state, result)
            self._persist(state, "complete", {"input_digest": key, "executor": executor, "result": reference})
        return self._view({**row, "result": result}, "terminal")

    def pending_reports(self):
        """All retained obligations; the outbox, not this list, owns delivery state."""
        state = self.load()
        return tuple(report for key in state["assessments"] if (report := _report(_row(state, key))) is not None)

    def report(self, input_digest, outbox, api):
        r.require(self.journal.issue_id != outbox.journal.issue_id, "report outbox aliases assessment storage")
        key = r.exact_digest(input_digest)
        state = self.load()
        r.require(key in state["assessments"], "report input has no persisted assessment")
        row = _row(state, key)
        if row["result"] is None:
            return {"status": "pending"}
        report = _report(row)
        return outbox.deliver(api, report) if report is not None else {"status": "not-applicable"}
