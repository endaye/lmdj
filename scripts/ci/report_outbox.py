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


class OutboxBlocked(RuntimeError):
    pass


def require(ok, why):
    if not ok:
        raise OutboxBlocked("why: " + why + "; remedy: inspect exact durable intent and receipts; never blindly repeat a report POST")


def freeze(report, assignee):
    fields = asdict(report)
    fields["labels"] = list(fields["labels"])
    payload = {"fields": fields, "assignee": assignee, "issue_body": report.issue_body(assignee),
               "comment_body": report.comment_body()}
    require(len(json.dumps(payload, ensure_ascii=True).encode()) <= 30000, "frozen report exceeds journal budget")
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


def new_state(epoch):
    require(isinstance(epoch, str) and bool(epoch), "outbox epoch missing")
    return {"schema": SCHEMA, "epoch": epoch, "generation": 0, "deliveries": {}, "buckets": {}, "events": {}}


def reduce(state, event):
    require(set(event) == {"id", "epoch", "generation", "type", "data"}, "outbox event schema is not closed")
    fingerprint = batch.digest(event)
    if event["id"] in state["events"]:
        require(state["events"][event["id"]] == fingerprint, "event ID reused with different bytes")
        return deepcopy(state)
    require(event["epoch"] == state["epoch"] and type(event["generation"]) is int
            and event["generation"] == state["generation"], "outbox epoch or generation differs")
    result, data = deepcopy(state), event["data"]
    require(isinstance(data, dict) and isinstance(data.get("delivery"), str), "outbox delivery identity missing")
    key = data["delivery"]
    if event["type"] == "queue":
        require(set(data) == {"delivery", "payload"}, "queue schema differs")
        payload = data["payload"]
        require(isinstance(payload, dict) and set(payload) == {"fields", "assignee", "issue_body", "comment_body"}, "invalid frozen report")
        report = FrozenReport(payload)
        require(key == batch.digest({"key": report.key, "observation": report.observation}), "delivery identity differs from report")
        require(freeze(report, payload["assignee"]) == payload, "frozen report representation changed")
        if key in result["deliveries"]:
            require(result["deliveries"][key]["payload"] == payload, "report body/labels/assignee changed for the same observation")
        else:
            result["deliveries"][key] = {"payload": deepcopy(payload), "status": "queued", "claim": None, "ack": None, "receipt": None}
    else:
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
    result["events"][event["id"]] = fingerprint
    result["generation"] += 1
    return result


class Outbox:
    def __init__(self, journal, lock_held, epoch):
        self.journal, self.lock_held, self.epoch = journal, lock_held, epoch
        self.state = None

    def load(self):
        require(self.lock_held() is True, "outbox lacks shared short writer lock")
        try:
            state = new_state(self.epoch)
            for event in self.journal.load():
                state = reduce(state, event)
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
            self.journal.append(event)
            committed = self.load()
            require(committed == expected, "outbox commit did not confirm the validated transition")
        except Exception as error:
            raise OutboxBlocked("why: outbox write outcome unresolved; remedy: reload authenticated intent without repeating business POST") from error

    def _receipt(self, api, delivery):
        report = FrozenReport(delivery["payload"])
        issue = reporting._find_issue(api, report.key, sleep=lambda _: None)
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

    def drain_once(self, api):
        """Resume one durable unclaimed payload without reopening old artifacts."""
        pending = self.recover(api)
        if pending["status"] != "ready":
            return pending
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
