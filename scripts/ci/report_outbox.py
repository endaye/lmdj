"""Durable report POST fencing over an independently configured Issue Journal.

The caller owns the same short writer lock used by every report writer. This
module never initializes storage or retries a claimed POST. Claim-after-crash
without a visible receipt is genuinely ambiguous, including before-send death.
"""
from copy import deepcopy
from dataclasses import asdict
import json

import incremental_batch as batch
import self_test_report as reporting

SCHEMA = "lmdj.report-outbox.v1"
_FROZEN_FIELD_DEFAULTS = {"management": None, "causal_order": None}
_EVENT_TYPES = frozenset({
    "queue", "claim", "ack", "delivered", "refused",
    "recovery-queue", "recovery-comment-claim", "recovery-comment-ack",
    "recovery-comment-delivered", "recovery-close-claim", "recovery-abandon",
    "recovery-stale", "recovery-close-ack", "recovery-close-delivered",
})


class OutboxBlocked(RuntimeError):
    pass


def require(ok, why):
    if not ok:
        raise OutboxBlocked("why: " + why + "; remedy: inspect exact durable intent and receipts; never blindly repeat a report POST")


def freeze(report, assignee):
    frozen = getattr(report, "payload", None)
    if isinstance(frozen, dict):
        require(frozen.get("assignee") == assignee, "frozen assignee changed")
        return deepcopy(frozen)
    if report.key.startswith(reporting.COMMON_EVENT_REPORT_PREFIX):
        event_id = report.key[len(reporting.COMMON_EVENT_REPORT_PREFIX):]
        require(event_id in report.summary,
                "common event identity is not retained in the frozen report")
    fields = asdict(report)
    fields["labels"] = list(fields["labels"])
    payload = {"fields": fields, "assignee": assignee, "issue_body": report.issue_body(assignee),
               "comment_body": report.comment_body()}
    require(len(json.dumps(payload, ensure_ascii=True).encode()) <= 30000, "frozen report exceeds journal budget")
    return payload


def frozen_payload_equal(left, right):
    """Compare old and current frozen reports without rewriting old bytes."""
    def normalized(payload):
        value = deepcopy(payload)
        fields = value.get("fields") if isinstance(value, dict) else None
        require(isinstance(fields, dict), "frozen report fields are not an object")
        for name, default in _FROZEN_FIELD_DEFAULTS.items():
            fields.setdefault(name, default)
        return value
    return normalized(left) == normalized(right)


def freeze_recovery(recovery):
    require(isinstance(recovery, reporting.Recovery), "recovery payload is not the authenticated protocol object")
    payload = {"identity": recovery.identity, "recovery_id": recovery.recovery_id,
               "key": recovery.key, "suite": recovery.suite, "failure_class": recovery.failure_class,
               "observation": recovery.observation, "target": recovery.target, "request": recovery.request,
               "run": recovery.run, "attempt": recovery.attempt, "policy": recovery.policy,
               "selection": recovery.selection, "epoch": recovery.epoch, "order": recovery.order, "evidence": recovery.evidence,
               "comment_body": recovery.comment_body()}
    require(recovery.recovery_id == batch.digest(recovery.identity), "recovery identity digest differs")
    require(len(json.dumps(payload, ensure_ascii=True).encode()) <= 30000, "frozen recovery exceeds journal budget")
    return payload


class FrozenReport(reporting.Report):
    def __init__(self, payload):
        fields = deepcopy(payload["fields"])
        fields["labels"] = tuple(fields["labels"])
        super().__init__(**fields)
        object.__setattr__(self, "payload", deepcopy(payload))

    def issue_body(self, assignee):
        require(assignee == self.payload["assignee"], "frozen assignee changed")
        return self.payload["issue_body"]

    def comment_body(self, *, first=False):
        require(not first, "frozen first observation is already inside the issue body")
        return self.payload["comment_body"]


class FrozenRecovery:
    def __init__(self, payload):
        for name in ("key", "suite", "failure_class", "policy", "epoch", "order"):
            setattr(self, name, payload[name])


def _validate_recovery_payload(payload):
    """Validate the closed recovery wire object before reducing it."""
    fields = {"identity", "recovery_id", "key", "suite", "failure_class", "observation",
              "target", "request", "run", "attempt", "policy", "selection", "epoch", "order",
              "evidence", "comment_body"}
    require(isinstance(payload, dict) and set(payload) == fields, "recovery payload is not closed")
    identity = payload["identity"]
    identity_fields = {"schema", "key", "suite", "class", "observation", "target", "request", "run",
                       "attempt", "policy", "selection", "epoch", "order", "evidence"}
    require(isinstance(identity, dict) and set(identity) == identity_fields
            and identity["schema"] == reporting.RECOVERY_SCHEMA,
            "recovery identity schema differs")
    correspondence = {"key": "key", "suite": "suite", "class": "failure_class", "observation": "observation",
                      "target": "target", "request": "request", "run": "run", "attempt": "attempt",
                      "policy": "policy", "selection": "selection", "epoch": "epoch", "order": "order",
                      "evidence": "evidence"}
    require(all(identity[source] == payload[target] for source, target in correspondence.items()),
            "recovery identity does not correspond to its payload")
    require(isinstance(payload["epoch"], str) and bool(payload["epoch"])
            and isinstance(payload["key"], str)
            and reporting._KEY.fullmatch(payload["key"])
            and isinstance(payload["suite"], str) and reporting._KEY.fullmatch(payload["suite"])
            and payload["key"] == reporting.managed_bucket_key(payload["epoch"], payload["policy"],
                                                                 payload["suite"], payload["failure_class"]),
            "recovery bucket identity is invalid")
    require(payload["failure_class"] in reporting.FAILURE_CLASSES
            and isinstance(payload["observation"], str) and bool(payload["observation"])
            and isinstance(payload["request"], str) and bool(payload["request"]),
            "recovery identity values are invalid")
    require(reporting._SHA.fullmatch(payload["target"] or "")
            and all(isinstance(payload[name], str) and reporting._MANAGED_HEX.fullmatch(payload[name])
                    for name in ("policy", "selection", "evidence")),
            "recovery provenance digest is invalid")
    require(all(type(payload[name]) is int and payload[name] > 0
                for name in ("run", "attempt", "order")),
            "recovery causal values are invalid")
    marker = " ".join([f"schema={reporting.RECOVERY_SCHEMA}", f"key={payload['key']}",
                        f"suite={payload['suite']}", f"class={payload['failure_class']}",
                        f"target={payload['target']}", f"request={payload['request']}",
                        f"run={payload['run']}", f"attempt={payload['attempt']}",
                        f"policy={payload['policy']}", f"selection={payload['selection']}",
                        f"epoch={payload['epoch']}", f"order={payload['order']}",
                        f"evidence={payload['evidence']}"])
    require(isinstance(payload["comment_body"], str)
            and payload["comment_body"].startswith(
                f"<!-- lmdj-self-test: recovery=v1 {marker} -->\n### Recovery observation"),
            "recovery comment does not carry its exact identity marker")


def new_state(epoch):
    require(isinstance(epoch, str) and bool(epoch), "outbox epoch missing")
    return {"schema": SCHEMA, "epoch": epoch, "generation": 0, "deliveries": {}, "buckets": {},
            "latest": {}, "recoveries": {}, "events": {}}


def reduce(state, event):
    require(set(event) == {"id", "epoch", "generation", "type", "data"}, "outbox event schema is not closed")
    require(type(event["type"]) is str and event["type"] in _EVENT_TYPES,
            "unknown outbox transition")
    fingerprint = batch.digest(event)
    if event["id"] in state["events"]:
        require(state["events"][event["id"]] == fingerprint, "event ID reused with different bytes")
        return deepcopy(state)
    require(event["epoch"] == state["epoch"] and type(event["generation"]) is int
            and event["generation"] == state["generation"], "outbox epoch or generation differs")
    result, data = deepcopy(state), event["data"]
    require(isinstance(data, dict), "outbox event data is not an object")
    if event["type"].startswith("recovery-"):
        key = None
    else:
        require(isinstance(data.get("delivery"), str), "outbox delivery identity missing")
        key = data["delivery"]
    if event["type"] == "queue":
        require(set(data) == {"delivery", "payload"}, "queue schema differs")
        payload = data["payload"]
        require(isinstance(payload, dict) and set(payload) == {"fields", "assignee", "issue_body", "comment_body"}, "invalid frozen report")
        report = FrozenReport(payload)
        require(key == batch.digest({"key": report.key, "observation": report.observation}), "delivery identity differs from report")
        normalized_frozen = freeze(report, payload["assignee"])
        require(frozen_payload_equal(normalized_frozen, payload), "frozen report representation changed")
        if key in result["deliveries"]:
            existing = result["deliveries"][key]["payload"]
            require(frozen_payload_equal(existing, payload), "report body/labels/assignee changed for the same observation")
        else:
            result["deliveries"][key] = {"payload": deepcopy(payload), "status": "queued", "claim": None, "ack": None, "receipt": None}
        order = report.causal_order
        if order is not None:
            require(type(order) is int and order > 0, "report causal order is invalid")
            prior = result["latest"].get(report.key)
            require(prior is None or order >= prior["order"], "stale report cannot override a newer failure")
            if prior is not None and order == prior["order"]:
                require(prior["observation"] == report.observation, "causal order reused for a different report")
            result["latest"][report.key] = {"order": order, "observation": report.observation}
    elif event["type"] in {"claim", "ack", "delivered", "refused"}:
        require(key in result["deliveries"], "outbox event has no queued report")
        delivery = result["deliveries"][key]
        report = FrozenReport(delivery["payload"])
        if event["type"] == "claim":
            require(set(data) == {"delivery", "operation"} and delivery["status"] == "queued", "report POST already claimed")
            operation = data["operation"]
            require(isinstance(operation, dict) and set(operation) == {"kind", "issue_number", "payload", "digest"}, "claim schema differs")
            require(operation["digest"] == batch.digest({k: v for k, v in operation.items() if k != "digest"}), "claim payload digest differs")
            number = operation["issue_number"]
            if operation["kind"] == "create-issue":
                require(number is None and report.key not in result["buckets"], "known issue bucket cannot be created again")
                expected = {"title": report.title, "body": report.issue_body(delivery["payload"]["assignee"]),
                            "labels": list(report.labels), "assignees": [delivery["payload"]["assignee"]]}
            else:
                require(operation["kind"] == "create-comment" and type(number) is int and number > 0,
                        "comment target is not an exact issue")
                require(result["buckets"].get(report.key, number) == number, "comment changed the known bucket target")
                expected = {"body": report.comment_body()}
            require(operation["payload"] == expected, "claimed body/target differs from frozen report")
            delivery["claim"], delivery["status"] = deepcopy(operation), "claimed"
        elif event["type"] in {"ack", "delivered"}:
            require(set(data) == {"delivery", "receipt"} and delivery["status"] in {"queued", "claimed", "acknowledged"}, "receipt transition is invalid")
            receipt = data["receipt"]
            require(isinstance(receipt, dict) and set(receipt) == {"issue_number", "comment_id"}
                    and type(receipt["issue_number"]) is int and receipt["issue_number"] > 0
                    and (receipt["comment_id"] is None or type(receipt["comment_id"]) is int and receipt["comment_id"] > 0), "invalid exact report receipt")
            claim = delivery["claim"]
            if claim:
                require((claim["kind"] == "create-issue") == (receipt["comment_id"] is None), "receipt changed POST kind")
                require(claim["issue_number"] in (None, receipt["issue_number"]), "receipt changed POST target")
            require(delivery["ack"] in (None, receipt), "receipt differs from acknowledged write ID")
            require(result["buckets"].get(report.key, receipt["issue_number"]) == receipt["issue_number"], "receipt changed durable bucket identity")
            result["buckets"][report.key] = receipt["issue_number"]
            if event["type"] == "ack":
                require(delivery["status"] == "claimed", "ack has no POST claim")
                delivery["ack"], delivery["status"] = deepcopy(receipt), "acknowledged"
            else:
                delivery["receipt"], delivery["status"] = deepcopy(receipt), "delivered"
        elif event["type"] == "refused":
            require(set(data) == {"delivery", "http_status"} and delivery["status"] == "claimed"
                    and type(data["http_status"]) is int and 400 <= data["http_status"] < 500, "refusal is not an explicit HTTP rejection")
            delivery["status"] = "refused"
        else:
            require(False, "unknown outbox transition")
    elif event["type"].startswith("recovery-"):
        recovery_data = data.get("recovery")
        if event["type"] == "recovery-queue":
            require(set(data) == {"recovery", "issue_number", "bucket_body"} and type(data["issue_number"]) is int
                    and data["issue_number"] > 0, "recovery queue schema differs")
            payload = recovery_data
            # The event envelope is authenticated by the outbox epoch above;
            # this payload epoch belongs to the scheduler source namespace.
            _validate_recovery_payload(payload)
            require(payload["recovery_id"] == batch.digest(payload["identity"]), "recovery ID differs from identity")
            bucket = next((delivery for delivery in result["deliveries"].values()
                           if delivery["status"] == "delivered"
                           and delivery["payload"]["fields"].get("management") is not None
                           and delivery["payload"]["fields"]["management"].get("key") == payload["key"]
                           and delivery["receipt"]["issue_number"] == data["issue_number"]
                           and delivery["payload"]["issue_body"] == data["bucket_body"]), None)
            require(bucket is not None, "recovery target is not the exact delivered managed bucket")
            rid = payload["recovery_id"]
            if rid in result["recoveries"]:
                require(result["recoveries"][rid]["payload"] == payload
                        and result["recoveries"][rid]["issue_number"] == data["issue_number"],
                        "recovery identity or target changed")
            else:
                require(isinstance(data["bucket_body"], str) and data["bucket_body"], "recovery bucket body is missing")
                result["recoveries"][rid] = {"payload": deepcopy(payload), "issue_number": data["issue_number"],
                    "bucket_body": data["bucket_body"],
                    "status": "queued", "comment_claim": None, "comment_receipt": None,
                    "close_claim": None, "close_receipt": None}
        else:
            rid = data.get("recovery_id")
            require(type(rid) is str and rid in result["recoveries"], "recovery transition has no queued intent")
            row = result["recoveries"][rid]
            issue_number = row["issue_number"]
            if event["type"] == "recovery-comment-claim":
                require(set(data) == {"recovery_id", "operation"} and row["status"] == "queued",
                        "recovery comment claim is not first")
                op = data["operation"]
                require(isinstance(op, dict) and set(op) == {"kind", "issue_number", "payload", "digest"}
                        and op["kind"] == "recovery-comment" and op["issue_number"] == issue_number
                        and op["payload"] == {"body": row["payload"]["comment_body"]}
                        and op["digest"] == batch.digest({k: v for k, v in op.items() if k != "digest"}),
                        "recovery comment intent differs")
                row["comment_claim"], row["status"] = deepcopy(op), "comment-claimed"
            elif event["type"] in {"recovery-comment-ack", "recovery-comment-delivered"}:
                require(set(data) == {"recovery_id", "receipt"}, "recovery comment receipt schema differs")
                receipt = data["receipt"]
                require(isinstance(receipt, dict) and set(receipt) == {"issue_number", "comment_id"}
                        and receipt["issue_number"] == issue_number and type(receipt["comment_id"]) is int
                        and receipt["comment_id"] > 0, "recovery comment receipt is not exact")
                require(row["status"] in {"comment-claimed", "comment-acknowledged"}
                        and row["comment_claim"] is not None
                        and row["comment_receipt"] in (None, receipt), "recovery comment receipt transition is invalid")
                row["comment_receipt"] = deepcopy(receipt)
                row["status"] = "comment-acknowledged" if event["type"] == "recovery-comment-ack" else "comment-delivered"
            elif event["type"] == "recovery-close-claim":
                require(set(data) == {"recovery_id", "operation"}
                        and row["status"] == "comment-delivered", "recovery close must follow comment receipt")
                op = data["operation"]
                require(isinstance(op, dict) and set(op) == {"kind", "issue_number", "state", "digest"}
                        and op["kind"] == "recovery-close" and op["issue_number"] == issue_number
                        and op["state"] == "closed"
                        and op["digest"] == batch.digest({k: v for k, v in op.items() if k != "digest"}),
                        "recovery close intent differs")
                row["close_claim"], row["status"] = deepcopy(op), "close-claimed"
            elif event["type"] == "recovery-abandon":
                require(set(data) == {"recovery_id", "why"}
                        and isinstance(data["why"], str) and data["why"]
                        and row["status"] in {"queued", "comment-claimed", "comment-acknowledged", "comment-delivered"},
                        "recovery abandon transition is invalid")
                row["status"] = "not-applicable"
            elif event["type"] == "recovery-stale":
                require(set(data) == {"recovery_id", "why"}
                        and isinstance(data["why"], str) and data["why"]
                        and row["status"] in {"queued", "comment-claimed", "comment-acknowledged", "comment-delivered"},
                        "recovery stale transition is invalid")
                row["status"] = "stale"
            elif event["type"] in {"recovery-close-ack", "recovery-close-delivered"}:
                require(set(data) == {"recovery_id", "receipt"}, "recovery close receipt schema differs")
                receipt = data["receipt"]
                require(isinstance(receipt, dict) and set(receipt) == {"issue_number", "state"}
                        and receipt["issue_number"] == issue_number and receipt["state"] == "closed",
                        "recovery close receipt is not exact")
                require(row["status"] in {"close-claimed", "close-acknowledged"}
                        and row["close_claim"] is not None
                        and row["close_receipt"] in (None, receipt), "recovery close receipt transition is invalid")
                row["close_receipt"] = deepcopy(receipt)
                row["status"] = "close-acknowledged" if event["type"] == "recovery-close-ack" else "closed"
            else:
                require(False, "unknown recovery transition")
    else:
        require(False, "unknown outbox transition")
    result["events"][event["id"]] = fingerprint
    result["generation"] += 1
    return result


class Outbox:
    def __init__(self, journal, lock_held, epoch):
        self.journal, self.lock_held, self.epoch = journal, lock_held, epoch
        self.state = None

    def _replay(self, events):
        require(self.lock_held() is True, "outbox replay lacks shared short writer lock")
        require(isinstance(events, list), "outbox requires complete authenticated journal events")
        state = new_state(self.epoch)
        for event in events:
            state = reduce(state, event)
        return state

    def load(self):
        require(self.lock_held() is True, "outbox lacks shared short writer lock")
        try:
            state = self._replay(self.journal.load())
            self.state = state
            return state
        except Exception as error:
            raise OutboxBlocked("why: durable outbox unavailable; remedy: reconcile its exact journal/anchor before any report write") from error

    def _persist(self, kind, data):
        require(self.lock_held() is True, "outbox write lacks shared short writer lock")
        event = {"id": f"outbox:{self.epoch}:{self.state['generation']}", "epoch": self.epoch,
                 "generation": self.state["generation"], "type": kind, "data": deepcopy(data)}
        expected = reduce(self.state, event)
        try:
            # Journal.append returns its authenticated, checkpoint-confirmed
            # full history after the write, not the attempted event or POST
            # response. Replay that far-side proof, as Controller does; retain
            # all Journal pre/post reads without a redundant third history read.
            committed = self._replay(self.journal.append(event))
            require(committed == expected, "outbox commit did not confirm the validated transition")
            self.state = committed
        except Exception as error:
            raise OutboxBlocked("why: outbox write outcome unresolved; remedy: reload authenticated intent without repeating business POST") from error

    def _receipt(self, api, delivery):
        report = FrozenReport(delivery["payload"])
        issue = reporting._find_issue(api, report.key, sleep=lambda _: None, managed=report.management)
        if issue is None:
            return None
        known = self.state["buckets"].get(report.key)
        require(known in (None, issue["number"]), "visible issue changed durable bucket identity")
        receipt = reporting._observation_receipt(api, issue, report, sleep=lambda _: None)
        if receipt is None:
            return None
        number, comment = receipt
        expected_body = delivery["payload"]["issue_body"] if comment is None else delivery["payload"]["comment_body"]
        if comment is None:
            require(issue.get("body") == expected_body, "visible issue body differs from frozen payload")
        else:
            matches = [c for c in api.list_comments(number) if c.get("id") == comment]
            require(len(matches) == 1 and matches[0].get("body") == expected_body and reporting._trusted_marker_author(matches[0]),
                    "visible comment body/author differs from frozen payload")
        value = {"issue_number": number, "comment_id": comment}
        require(delivery["ack"] in (None, value), "visible receipt differs from acknowledged exact ID")
        claim = delivery["claim"]
        if claim:
            require(claim["issue_number"] in (None, number) and (claim["kind"] == "create-issue") == (comment is None),
                    "visible receipt differs from claimed POST target or kind")
        return value

    def _managed_issue(self, api, recovery, *, expected_body=None, expected_number=None):
        """Find only a new, affirmative, untouched machine-managed bucket."""
        managed = {"schema": reporting.MANAGED_BUCKET_SCHEMA, "epoch": recovery.epoch,
                   "key": recovery.key, "suite": recovery.suite,
                   "failure_class": recovery.failure_class, "policy": recovery.policy}
        # Filter by the stable namespace before selecting an Issue. A legacy
        # same-key bucket may precede the managed bucket in the API response.
        issue = reporting._find_issue(api, recovery.key, sleep=lambda _: None, managed=managed)
        if issue is None:
            return None
        if expected_number is not None and issue.get("number") != expected_number:
            return None
        metadata = reporting.parse_managed_marker(issue, recovery.key)
        if metadata is None:
            return None
        if expected_body is not None and issue.get("body") != expected_body:
            return None
        require(metadata["suite"] == recovery.suite
                and metadata["failure_class"] == recovery.failure_class
                and metadata["policy"] == recovery.policy
                and metadata["epoch"] == recovery.epoch
                and metadata["order"] < recovery.order,
                "managed bucket provenance or causal order does not admit recovery")
        # A human-authored comment or body edit is a handoff to a maintainer,
        # not evidence that machine recovery remains safe.
        if issue.get("editor") is not None or issue.get("updated_by") is not None:
            return None
        comments = reporting.with_retry(lambda: api.list_comments(int(issue["number"])), sleep=lambda _: None)
        if any(not reporting._trusted_marker_author(comment) for comment in comments):
            return None
        return issue

    def _recovery_receipt(self, api, row):
        comments = reporting.with_retry(lambda: api.list_comments(row["issue_number"]), sleep=lambda _: None)
        marker = row["payload"]["comment_body"]
        matches = [comment for comment in comments
                   if reporting._trusted_marker_author(comment) and comment.get("body") == marker]
        require(len(matches) <= 1, "duplicate trusted recovery comments")
        if not matches:
            return None
        comment = matches[0]
        require(type(comment.get("id")) is int and comment["id"] > 0, "recovery comment receipt lacks exact ID")
        return {"issue_number": row["issue_number"], "comment_id": comment["id"]}

    def _close_receipt(self, api, row):
        issue = self._managed_issue(api, FrozenRecovery(row["payload"]),
                                    expected_body=row["bucket_body"], expected_number=row["issue_number"])
        if issue is None or issue.get("state") != "closed":
            return None
        return {"issue_number": row["issue_number"], "state": "closed"}

    def _reconcile_recovery(self, api, rid, *, causal_floor=None):
        row = self.state["recoveries"][rid]
        payload = row["payload"]
        if row["status"] in {"closed", "stale", "not-applicable"}:
            return {"status": row["status"], "recovery_id": rid,
                    **({"issue_number": row["issue_number"]} if row["status"] == "closed" else {})}
        latest = self.state["latest"].get(payload["key"])
        floor = (causal_floor or {}).get(payload["key"])
        stale = ((latest is not None and latest["order"] >= payload["order"])
                 or (floor is not None and floor >= payload["order"]))

        # A stale recovery may already have claimed the close PATCH. Reconcile
        # that exact write first; recovery-stale is not a legal transition from
        # close-claimed/acknowledged and must not erase its evidence.
        if row["status"] in {"close-claimed", "close-acknowledged"}:
            receipt = self._close_receipt(api, row)
            if receipt is None:
                return {"status": "needs-reconciliation", "recovery_id": rid,
                        "why": "recovery close PATCH has no exact closed-state receipt",
                        "remedy": "inspect the exact Issue state; never replay an unknown PATCH"}
            if row["status"] == "close-claimed":
                self._persist("recovery-close-ack", {"recovery_id": rid, "receipt": receipt})
            self._persist("recovery-close-delivered", {"recovery_id": rid, "receipt": receipt})
            return {"status": "closed", "recovery_id": rid, "issue_number": row["issue_number"]}

        if stale and row["status"] in {"queued", "comment-delivered"}:
            answer = {"status": "stale", "recovery_id": rid,
                      "why": "newer authenticated failure already owns this bucket",
                      "remedy": "retain the newer failure; do not close it from a stale success"}
            if row["status"] in {"queued", "comment-claimed", "comment-acknowledged", "comment-delivered"}:
                self._persist("recovery-stale", {"recovery_id": rid, "why": answer["why"]})
            return answer
        if row["status"] in {"queued", "comment-claimed", "comment-acknowledged"}:
            receipt = self._recovery_receipt(api, row)
            if receipt is None:
                if row["status"] != "queued":
                    return {"status": "needs-reconciliation", "recovery_id": rid,
                            "why": "recovery comment claim has no visible receipt",
                            "remedy": "inspect the exact comment; never repeat the comment POST"}
                operation = {"kind": "recovery-comment", "issue_number": row["issue_number"],
                             "payload": {"body": payload["comment_body"]}}
                operation["digest"] = batch.digest(operation)
                self._persist("recovery-comment-claim", {"recovery_id": rid, "operation": operation})
                try:
                    response = api.create_comment(row["issue_number"], payload["comment_body"])
                except Exception:
                    raise
                require(isinstance(response, dict) and type(response.get("id")) is int and response["id"] > 0
                        and response.get("number", row["issue_number"]) == row["issue_number"]
                        and reporting._trusted_marker_author(response)
                        and response.get("body") == payload["comment_body"],
                        "recovery comment response is not an exact trusted receipt")
                receipt = {"issue_number": row["issue_number"], "comment_id": response["id"]}
                self._persist("recovery-comment-ack", {"recovery_id": rid, "receipt": receipt})
            if self.state["recoveries"][rid]["status"] != "comment-delivered":
                receipt = self._recovery_receipt(api, self.state["recoveries"][rid])
                if receipt is None:
                    return {"status": "needs-reconciliation", "recovery_id": rid,
                            "why": "recovery comment receipt is not independently visible",
                            "remedy": "reconcile the exact comment without repeating its POST"}
                self._persist("recovery-comment-delivered", {"recovery_id": rid, "receipt": receipt})
        if stale:
            # A comment claim/ack has an unresolved write obligation. First
            # reconcile its far-side receipt above; only then terminally mark
            # the now-stale recovery without erasing that evidence.
            answer = {"status": "stale", "recovery_id": rid,
                      "why": "newer authenticated failure already owns this bucket",
                      "remedy": "retain the newer failure; do not close it from a stale success"}
            self._persist("recovery-stale", {"recovery_id": rid, "why": answer["why"]})
            return answer
        row = self.state["recoveries"][rid]
        if row["status"] == "comment-delivered":
            # Revalidate exact bot-authored body and comments immediately
            # before the close claim/PATCH; a human handoff wins over liveness.
            if self._managed_issue(api, FrozenRecovery(row["payload"]),
                                   expected_body=row["bucket_body"], expected_number=row["issue_number"]) is None:
                answer = {"status": "not-applicable", "recovery_id": rid,
                          "why": "managed bucket was edited or handed to a human",
                          "remedy": "retain the bucket for human investigation"}
                self._persist("recovery-abandon", {"recovery_id": rid, "why": answer["why"]})
                return answer
            operation = {"kind": "recovery-close", "issue_number": row["issue_number"], "state": "closed"}
            operation["digest"] = batch.digest(operation)
            self._persist("recovery-close-claim", {"recovery_id": rid, "operation": operation})
            try:
                response = api.set_issue_state(row["issue_number"], "closed")
            except Exception:
                raise
            require(isinstance(response, dict) and response.get("number") == row["issue_number"]
                    and response.get("state") == "closed", "recovery close response is not an exact receipt")
            receipt = {"issue_number": row["issue_number"], "state": "closed"}
            self._persist("recovery-close-ack", {"recovery_id": rid, "receipt": receipt})
        row = self.state["recoveries"][rid]
        if row["status"] == "close-acknowledged":
            receipt = self._close_receipt(api, row)
            if receipt is None:
                return {"status": "needs-reconciliation", "recovery_id": rid,
                        "why": "recovery close PATCH is not independently visible",
                        "remedy": "inspect the exact Issue state; never repeat an unknown PATCH"}
            self._persist("recovery-close-delivered", {"recovery_id": rid, "receipt": receipt})
        return {"status": "closed", "recovery_id": rid, "issue_number": row["issue_number"]}

    def recover_success(self, api, recovery, *, causal_floor=None):
        self.load()
        payload = freeze_recovery(recovery)
        rid = payload["recovery_id"]
        if rid not in self.state["recoveries"]:
            latest = self.state["latest"].get(recovery.key)
            if latest is not None and latest["order"] >= recovery.order:
                return {"status": "stale", "recovery_id": rid,
                        "why": "newer authenticated failure already owns this bucket",
                        "remedy": "retain newer failure; do not close from stale success"}
            # A durable report delivery is the provenance chain that binds a
            # same-key Issue to this new managed namespace. Never adopt an old
            # Issue merely because its title/key happens to match.
            bucket = next((delivery for delivery in self.state["deliveries"].values()
                           if delivery["status"] == "delivered"
                           and delivery["payload"]["fields"].get("management") is not None
                           and delivery["payload"]["fields"].get("management", {}).get("key") == recovery.key), None)
            if bucket is None:
                return {"status": "not-applicable", "recovery_id": rid}
            issue = self._managed_issue(api, recovery, expected_body=bucket["payload"]["issue_body"],
                                        expected_number=int(bucket["receipt"]["issue_number"]))
            if issue is None or issue.get("state") != "open":
                # Reserve the candidate against this already delivered bucket
                # before recording that it is inapplicable. Without a durable
                # terminal row, a human-edited bucket is reconsidered on every
                # bounded tick and can starve later recovery keys forever.
                self._persist("recovery-queue", {
                    "recovery": payload,
                    "issue_number": int(bucket["receipt"]["issue_number"]),
                    "bucket_body": bucket["payload"]["issue_body"]})
                why = "managed bucket was edited, handed to a human, closed, or is no longer eligible"
                self._persist("recovery-abandon", {"recovery_id": rid, "why": why})
                return {"status": "not-applicable", "recovery_id": rid}
            self._persist("recovery-queue", {"recovery": payload, "issue_number": int(issue["number"]),
                                               "bucket_body": bucket["payload"]["issue_body"]})
        return self._reconcile_recovery(api, rid, causal_floor=causal_floor)

    def recover(self, api):
        """Bounded read reconciliation; missing receipts do not authorize POST."""
        self.load()
        for key, delivery in self.state["deliveries"].items():
            if delivery["status"] in {"claimed", "acknowledged", "refused"}:
                try:
                    receipt = self._receipt(api, delivery)
                    if receipt is not None and delivery["status"] != "refused":
                        self._persist("delivered", {"delivery": key, "receipt": receipt})
                        continue
                except Exception:
                    pass
                return {"status": "needs-reconciliation", "delivery": key,
                        "why": "a prior POST claim has no confirmed durable delivery, including possible death before sending",
                        "remedy": "inspect exact issue/comment IDs and intent; do not automatically repeat or reset this claim"}
        return {"status": "ready"}

    def deliver(self, api, report, *, assignee=reporting.DEFAULT_ASSIGNEE):
        self.load()
        key = batch.digest({"key": report.key, "observation": report.observation})
        payload = freeze(report, assignee)
        if report.causal_order is not None:
            prior = self.state["latest"].get(report.key)
            if prior is not None and report.causal_order < prior["order"]:
                return {"status": "stale", "delivery": key,
                        "why": "stale report cannot override a newer failure",
                        "remedy": "retain the newer authenticated report"}
        if key in self.state["deliveries"]:
            require(self.state["deliveries"][key]["payload"] == payload, "delivery body changed under the same observation identity")
        else:
            self._persist("queue", {"delivery": key, "payload": payload})
        pending = self.recover(api)
        if pending["status"] != "ready":
            return pending
        if self.state["deliveries"][key]["status"] == "delivered":
            return {"status": "delivered", "receipt": deepcopy(self.state["deliveries"][key]["receipt"])}
        proxy = _PostingApi(api, self, key)
        # Seed durable bucket identities so stale list reads cannot create a
        # second issue for a previously acknowledged/delivered bucket.
        reporting._write_state(proxy).buckets.update(self.state["buckets"])
        reporting.apply_report(proxy, FrozenReport(payload), assignee=assignee, sleep=lambda _: None)
        receipt = self._receipt(api, self.state["deliveries"][key])
        require(receipt is not None, "successful adapter return lacks an exact visible receipt")
        self._persist("delivered", {"delivery": key, "receipt": receipt})
        return {"status": "delivered", "receipt": receipt}

    def drain_once(self, api, *, causal_floor=None):
        """Resume one durable unclaimed payload without reopening old artifacts."""
        pending = self.recover(api)
        if pending["status"] != "ready":
            return pending
        active = {}
        for rid, row in self.state["recoveries"].items():
            if row["status"] in {"closed", "stale", "not-applicable"}:
                continue
            key = row["payload"]["key"]
            if (key not in active or row["payload"]["order"] >
                    self.state["recoveries"][active[key]]["payload"]["order"]):
                active[key] = rid
        for rid in active.values():
            answer = self._reconcile_recovery(api, rid, causal_floor=causal_floor)
            if answer["status"] == "needs-reconciliation":
                return answer
            if answer["status"] in {"closed", "stale", "not-applicable"}:
                continue
            return answer
        for delivery in self.state["deliveries"].values():
            if delivery["status"] == "queued":
                payload = delivery["payload"]
                return self.deliver(api, FrozenReport(payload), assignee=payload["assignee"])
        return {"status": "idle"}


class _PostingApi:
    def __init__(self, api, outbox, key):
        self.api, self.outbox, self.key = api, outbox, key

    def __getattr__(self, name):
        return getattr(self.api, name)

    def create_issue(self, *, title, body, labels, assignees):
        return self._post("create-issue", None, {"title": title, "body": body, "labels": list(labels), "assignees": list(assignees)})

    def create_comment(self, number, body):
        return self._post("create-comment", number, {"body": body})

    def _post(self, kind, number, payload):
        operation = {"kind": kind, "issue_number": number, "payload": payload}
        operation["digest"] = batch.digest(operation)
        self.outbox._persist("claim", {"delivery": self.key, "operation": operation})
        # This local continuation only follows a newly committed claim. A
        # process restarted from that claim can only call recover, never here.
        try:
            response = self.api.create_issue(**payload) if number is None else self.api.create_comment(number, payload["body"])
        except reporting.GitHubApiError as error:
            if 400 <= error.status < 500:
                self.outbox._persist("refused", {"delivery": self.key, "http_status": error.status})
            raise
        id_key = "number" if number is None else "id"
        if (isinstance(response, dict) and reporting._positive_id(response.get(id_key))
                and reporting._trusted_marker_author(response) and response.get("body") == payload["body"]):
            receipt = {"issue_number": response["number"] if number is None else number,
                       "comment_id": None if number is None else response["id"]}
            self.outbox._persist("ack", {"delivery": self.key, "receipt": receipt})
        return response
