#!/usr/bin/env python3
"""Opt-in O1 response suppression, not a claim of spontaneous GitHub failure.

Storage must already be independently reserved and initialized. This adapter
cannot initialize it, launch tests, dispatch Actions or recover its own fault.
Ordinary fresh, unwrapped runtime/outbox drivers own positive-receipt recovery.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import re

import batch_github_journal as storage
import batch_runtime
import incremental_batch as batch
from incremental_batch_journal import Journal
import report_outbox
import report_runtime
import review_failure_report
import self_test_report as reporting

SCHEMA = "lmdj.o1-response-probe.v1"
A = "journal-append-response"
B = "outbox-business-response"
DISABLED = "disabled"
FAULT = "after-successful-post"
PROTECTED = {807, 817, 819}


def require(ok, why):
    if not ok:
        raise ValueError("why: " + why + "; remedy: stop the probe and reconcile the isolated identity/receipt; never repeat an uncertain POST")


class ControlledFailure(SystemExit):
    """BaseException deliberately bypasses normal unknown-response recovery."""
    def __init__(self, operation):
        self.operation = operation
        super().__init__(86)


def intent(value):
    require(isinstance(value, dict), "probe intent is not an object")
    operation = value.get("operation")
    required = {"operation"} | ({"review_run_id", "review_attempt"} if operation == B else set())
    require(operation in {A, B} and set(value) in (required, required | {"fault"}), "probe intent is not closed")
    result = {**value, "fault": value.get("fault", DISABLED)}
    require(result["fault"] in {DISABLED, FAULT}, "unknown fault mode")
    if operation == B:
        batch.identity({"run_id": result["review_run_id"], "attempt": result["review_attempt"]})
    return result


class ReadOnlyApi:
    def __init__(self, api):
        self.api = api

    def __getattr__(self, name):
        if name in {"list_jobs", "compare", "download_artifact"}:
            return getattr(self.api, name)
        raise AttributeError(name)

    def _request(self, method, path, *, body=None, raw=False):
        query = (method == "POST" and path == "/graphql" and isinstance(body, dict)
                 and isinstance(body.get("query"), str) and body["query"].lstrip().startswith("query("))
        require(method == "GET" or query, "prepare attempted a remote write")
        return self.api._request(method, path, body=body, raw=raw)


def empty(runtime):
    source = runtime.journal()
    journal = Journal(source.issue_id, source.transport, report_runtime.ReadOnlyAnchor(source.anchor),
                      source.authenticate, source.lock_held)
    require(source.anchor.read() == {"head": None, "pending": None}, "probe storage is pending or nonempty")
    require(journal.load() == [], "probe storage has prior history")


def observe_only(runtime):
    source = runtime.journal()
    journal = Journal(source.issue_id, source.transport, report_runtime.ReadOnlyAnchor(source.anchor),
                      source.authenticate, source.lock_held)
    checkpoint = source.anchor.read()
    require(checkpoint["pending"] is None, "scheduler pending append needs ordinary recovery")
    events = journal.load()
    require(all(event.get("type") == "observe" for event in events), "scheduler history is not observe-only")
    state = report_runtime.scheduler_state(runtime)
    require(state["processed"] is None and state["active"] is None,
            "scheduler history already contains execution or progress")
    return {"checkpoint": checkpoint, "events": events}


def namespace_empty(api, repository, namespace):
    """All-state, unfiltered, bounded complete pagination; errors are not absence."""
    seen = set()
    for page in range(1, 101):
        rows = api._request("GET", f"/repos/{repository}/issues?state=all&per_page=100&page={page}")
        require(isinstance(rows, list) and len(rows) <= 100, "Issue inventory is incomplete")
        for row in rows:
            require(isinstance(row, dict) and storage.positive(row.get("number"))
                    and row["number"] not in seen and "body" in row
                    and (row["body"] is None or isinstance(row["body"], str)), "Issue inventory identity/body is invalid")
            seen.add(row["number"])
            require(namespace not in (row["body"] or ""), "diagnostic namespace already has a bucket")
        if len(rows) < 100:
            return
    require(False, "Issue inventory exceeded complete pagination budget")


def document(writer, kind, payload):
    return json.dumps(dict(schema=storage.SCHEMA, kind=kind, writer=writer, payload=payload),
                      sort_keys=True, separators=(",", ":"), allow_nan=False)


def writes_for(runtime, events):
    """Exact existing journal wire sequence, not a new persistence protocol."""
    prefix = runtime.repo(f"/issues/{runtime.config['issue_number']}")
    previous, writes = None, []
    for event in events:
        envelope = {"previous": previous, "event": event}
        envelope["digest"] = batch.digest(envelope)
        writes.extend([
            ["PATCH", prefix, {"body": document(runtime.writer, "checkpoint", {"head": previous, "pending": envelope})}],
            ["POST", prefix + "/comments", {"body": document(runtime.writer, "event", envelope)}],
            ["PATCH", prefix, {"body": document(runtime.writer, "checkpoint", {"head": envelope["digest"], "pending": None})}],
        ])
        previous = envelope["digest"]
    return writes


class Probe:
    def __init__(self, config, *, root, environment=None, api=None):
        self.config, self.root, self.environment = deepcopy(config), root, environment
        require(isinstance(config, dict) and set(config) == {"scheduler", "outbox"}, "probe requires the closed isolated storage pair")
        for item in config.values():
            require(isinstance(item, dict) and item.get("issue_number") not in PROTECTED
                    and isinstance(item.get("epoch"), str)
                    and re.fullmatch(r"o1-recovery-[a-z0-9-]{1,80}", item["epoch"]), "storage is not an explicitly isolated recovery identity")
        base = report_runtime.ReportRuntime(config, root=root, environment=environment, api=api)
        require(config["scheduler"]["epoch"] != config["outbox"]["epoch"], "recovery storage epochs alias")
        self.api = base.api

    def runtimes(self, api):
        return report_runtime.ReportRuntime(self.config, root=self.root, environment=self.environment, api=api)

    def prepare(self, request):
        request = intent(request)
        if request["fault"] == DISABLED:
            return {"schema": SCHEMA, "status": DISABLED, "intent": request}
        api = ReadOnlyApi(self.api)
        runtimes = self.runtimes(api)
        for runtime in (runtimes.scheduler, runtimes.storage):
            runtime.authenticate_current()
            require(runtime.read_main() == runtime.control, "main advanced beyond the probe controller")
        empty(runtimes.storage)
        if request["operation"] == A:
            empty(runtimes.scheduler)
        scheduler_snapshot = observe_only(runtimes.scheduler)
        runtime = runtimes.scheduler if request["operation"] == A else runtimes.storage
        epoch = runtime.config["epoch"]
        if request["operation"] == A:
            event = dict(id=f"{epoch}:0", epoch=epoch, generation=0, type="observe",
                         data={"target": runtime.control, "descends_pending": True})
            writes = writes_for(runtime, [event])[:2]
            expected = {"epoch": epoch, "event": event, "writes": writes}
        else:
            source = review_failure_report.collect(api, runtimes.repository,
                request["review_run_id"], request["review_attempt"])
            require(source is not None, "review is not an authenticated all-backend failure")
            namespace = f"o1-recovery/{epoch}/"
            namespace_empty(api, runtimes.repository, namespace)
            report = replace(source, key=namespace + source.key,
                title="O1 recovery diagnostic: " + source.title,
                summary="Controlled O1 recovery observation of a real source failure; not another product defect.\n\n" + source.summary)
            frozen = report_outbox.freeze(report, reporting.DEFAULT_ASSIGNEE)
            delivery = batch.digest({"key": report.key, "observation": report.observation})
            payload = {"title": report.title, "body": frozen["issue_body"],
                       "labels": list(report.labels), "assignees": [reporting.DEFAULT_ASSIGNEE]}
            operation = {"kind": "create-issue", "issue_number": None, "payload": payload}
            operation["digest"] = batch.digest(operation)
            events = [dict(id=f"outbox:{epoch}:{i}", epoch=epoch, generation=i, type=kind, data=data)
                for i, (kind, data) in enumerate((
                    ("queue", {"delivery": delivery, "payload": frozen}),
                    ("claim", {"delivery": delivery, "operation": operation})))]
            writes = writes_for(runtime, events) + [["POST", runtime.repo("/issues"), payload]]
            expected = {"epoch": epoch, "namespace": namespace, "source_observation": source.observation,
                        "delivery": delivery, "frozen": frozen, "writes": writes}
        expected["scheduler_snapshot"] = scheduler_snapshot
        return {"schema": SCHEMA, "intent": request,
                "controller": {**runtime.current, "control_sha": runtime.control},
                "expected": expected, "digest": batch.digest(expected)}

    def execute(self, prepared):
        require(isinstance(prepared, dict) and "intent" in prepared, "prepared request is missing")
        # Fresh authentication and exact full-byte equality; hashes grant no authority.
        current = self.prepare(prepared["intent"])
        require(prepared == current, "prepared snapshot or controller changed")
        if current.get("status") == DISABLED:
            return {"status": DISABLED, "remote_writes": 0}
        api = SuppressingApi(self.api, current, self.config)
        runtimes = self.runtimes(api)
        if current["intent"]["operation"] == A:
            runtimes.scheduler.reconcile(execute=False)
        else:
            runtimes.storage.authenticate_current()
            runtimes.outbox().deliver(api, report_outbox.FrozenReport(current["expected"]["frozen"]))
        require(False, "probe returned without the expected response-suppression boundary")


class SuppressingApi(ReadOnlyApi):
    def __init__(self, api, prepared, config):
        super().__init__(api)
        self.prepared, self.writes, self.index = deepcopy(prepared), deepcopy(prepared["expected"]["writes"]), 0
        role = "scheduler" if prepared["intent"]["operation"] == A else "outbox"
        self.bot = config[role]["bot_node_id"]
        self.repository = config[role]["repository"]
        self.target = len(self.writes) - 1

    def _request(self, method, path, *, body=None, raw=False):
        if method == "GET" or path == "/graphql":
            answer = super()._request(method, path, body=body, raw=raw)
            if path == f"/repos/{self.repository}/git/ref/heads/main":
                require(isinstance(answer, dict) and answer.get("object", {}).get("sha") == self.prepared["controller"]["control_sha"], "main drifted before append")
            return answer
        require(not raw and self.index < len(self.writes)
                and [method, path, body] == self.writes[self.index], "unexpected remote write or payload")
        self.index += 1  # Fence before call: even a failed call cannot be blindly repeated.
        target = self.index - 1 == self.target
        try:
            answer = self.api._request(method, path, body=body, raw=raw)
        except reporting.GitHubApiError as error:
            if target and self.prepared["intent"]["operation"] == B and 400 <= error.status < 500:
                # Preserve the existing driver's definite-refusal journal leg;
                # never suppress or replace the original HTTP failure.
                prior = json.loads(self.writes[-2][2]["body"])
                previous = prior["payload"]["head"]
                epoch = self.prepared["expected"]["epoch"]
                event = dict(id=f"outbox:{epoch}:2", epoch=epoch, generation=2, type="refused",
                    data={"delivery": self.prepared["expected"]["delivery"], "http_status": error.status})
                envelope = {"previous": previous, "event": event}
                envelope["digest"] = batch.digest(envelope)
                prefix = self.writes[0][1]
                writer = prior["writer"]
                self.writes.extend([
                    ["PATCH", prefix, {"body": document(writer, "checkpoint", {"head": previous, "pending": envelope})}],
                    ["POST", prefix + "/comments", {"body": document(writer, "event", envelope)}],
                    ["PATCH", prefix, {"body": document(writer, "checkpoint", {"head": envelope["digest"], "pending": None})}],
                ])
            raise
        if target:
            require(isinstance(answer, dict) and storage.positive(answer.get("id"))
                    and answer.get("body") == body["body"] and isinstance(answer.get("user"), dict)
                    and answer["user"].get("node_id") == self.bot
                    and reporting._trusted_marker_author(answer), "POST returned no exact authenticated success receipt")
            if self.prepared["intent"]["operation"] == B:
                require(storage.positive(answer.get("number")) and answer["number"] not in PROTECTED,
                        "diagnostic Issue receipt identity is invalid")
                labels, assignees = answer.get("labels"), answer.get("assignees")
                require(answer.get("title") == body["title"] and isinstance(labels, list)
                        and all(isinstance(label, dict) and isinstance(label.get("name"), str) for label in labels)
                        and sorted(label["name"] for label in labels) == sorted(body["labels"])
                        and isinstance(assignees, list)
                        and all(isinstance(user, dict) and isinstance(user.get("login"), str) for user in assignees)
                        and sorted(user["login"] for user in assignees) == sorted(body["assignees"]),
                        "diagnostic Issue returned different title/labels/assignees")
            raise ControlledFailure(self.prepared["intent"]["operation"])
        return answer

    # Reuse real reporter HTTP endpoints; no bound underlying method may bypass
    # the exact write fence. Reads retain its complete pagination semantics.
    _repo = reporting.UrllibGitHubApi._repo
    list_issues = reporting.UrllibGitHubApi.list_issues
    list_comments = reporting.UrllibGitHubApi.list_comments
    create_issue = reporting.UrllibGitHubApi.create_issue
    create_comment = reporting.UrllibGitHubApi.create_comment
    set_issue_state = reporting.UrllibGitHubApi.set_issue_state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "request", "summary", "root"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    code = 0
    try:
        probe = Probe(batch_runtime.strict_json(args.config.read_bytes()), root=args.root)
        answer = probe.execute(probe.prepare(batch_runtime.strict_json(args.request.read_bytes())))
    except ControlledFailure as failure:
        answer = {"status": "controlled-response-suppression", "operation": failure.operation,
                  "why": "successful remote POST response deliberately suppressed, not a spontaneous GitHub fault",
                  "remedy": "inspect exact isolated receipt, then use a fresh ordinary unwrapped recovery run"}
        code = failure.code
    except Exception:
        answer = {"status": "error", "why": "probe authentication, snapshot or original HTTP outcome is unresolved; no successful injection claimed",
                  "remedy": "inspect isolated pending intent and exact receipt; do not blindly repeat a POST"}
        code = 1
    with args.summary.open("a") as stream:
        stream.write("O1 recovery probe: " + json.dumps(answer, sort_keys=True) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
