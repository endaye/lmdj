#!/usr/bin/env python3
"""Automatic event adapter for the existing short-lock controller and outbox.

No dispatch, initialization, new scheduler or daily product request. Workflow
wiring must publish control output before an independent reporting step; report
errors must not turn a durably claimed execution into a skipped heavy DAG.
"""
from __future__ import annotations

import argparse
import json
from http.client import HTTPMessage
import os
from pathlib import Path
import subprocess
from urllib.error import HTTPError

import batch_runtime
from api_observation import observe
import incremental_completion
import incremental_batch as batch
import report_runtime
import self_test
from incremental_batch_journal import JournalBlocked
from test_scope import ScopeError
from self_test_report import GitHubApiError

STORAGE_PATH = "scripts/ci/incremental_storage.json"
REPORT_SCHEMA = "lmdj.ci-incremental-entry-report.v1"
WORKFLOWS = {
    batch_runtime.WORKFLOW: "batch",
    ".github/workflows/ci.yml": "legacy",
    ".github/workflows/pr-review.yml": "review",
}
EVENTS = {"push", "schedule", "workflow_run"}
SCHEDULER_HEALTH = "7,22,37,52 * * * *"
REPORT_HEALTH = "9,24,39,54 * * * *"
DIAGNOSTIC_STAGES = frozenset({
    "output-preflight", "entry-construction", "event-read", "output-write",
    "authenticate", "auth-lock", "auth-checkout", "auth-main-refresh",
    "auth-current-run", "auth-journal-writer", "auth-current-job", "auth-event",
    "event-authenticate", "reconcile", "scheduler-read", "report-construction", "report",
})


def http_diagnostic(error):
    """Bounded known-wrapper inspection, numeric metadata only; no text/URL."""
    seen = set()
    for _ in range(4):
        if id(error) in seen:
            break
        seen.add(id(error))
        if type(error) is HTTPError:
            result = {}
            if type(error.code) is int and 100 <= error.code <= 599:
                result['status'] = error.code
            if type(error.headers) is HTTPMessage:
                for header, key in (('x-ratelimit-remaining', 'remaining'),
                                    ('x-ratelimit-reset', 'reset'), ('retry-after', 'retry_after')):
                    values = error.headers.get_all(header, [])
                    if len(values) == 1:
                        value = values[0]
                        if type(value) is str and 1 <= len(value) <= 12 and value.isascii() and value.isdecimal():
                            result[key] = int(value)
            return result
        if type(error) is GitHubApiError:
            result = {}
            if type(error.status) is int and 100 <= error.status <= 599:
                result['status'] = error.status
            for attr, key in (('remaining', 'remaining'), ('reset', 'reset'), ('retry_after', 'retry_after')):
                value = getattr(error, attr, None)
                if type(value) is int and 0 <= value <= 10**12:
                    result[key] = value
            if len(result) > 1:
                return result
        if type(error) not in (batch.BatchError, JournalBlocked, GitHubApiError):
            break
        error = error.__context__
    return {}


def diagnostic(operation, stage, error):
    """Closed diagnostic only. Never inspect exception text or dynamic names."""
    kinds = {JournalBlocked: "journal-blocked", batch.BatchError: "batch-error",
             ScopeError: "scope-error", json.JSONDecodeError: "json-error", OSError: "os-error",
             GitHubApiError: "github-api-error", HTTPError: "http-error"}
    answer = {"schema": "lmdj.ci-entry-diagnostic.v1",
            "operation": operation if type(operation) is str and operation in {"control", "reports"} else "unknown",
            "stage": stage if type(stage) is str and stage in DIAGNOSTIC_STAGES else "unknown",
            "error_kind": kinds.get(type(error), "unknown")}
    http = http_diagnostic(error)
    if http:
        answer['http'] = http
    return answer


def emit_diagnostic(operation, stage, error):
    print(self_test.canonical_json(diagnostic(operation, stage, error)), flush=True)


def require(ok, why):
    batch.require(ok, why, "restore exact trusted event/storage inputs; do not initialize, dispatch or replay a claimed execution")


def load_storage(root, environment):
    """Read only the fixed committed Git blob; callers still authenticate main.

    No operator-selected file or dirty working-tree configuration is accepted.
    Returned data is the closed {scheduler, outbox} six-field Runtime pair.
    Actual Issue/editor/writer/main provenance is verified by the Runtime.
    """
    control = batch.exact_sha(environment.get("GITHUB_SHA"))
    def git(*args):
        try:
            return subprocess.run(["git", "--no-replace-objects", "-C", str(root), *args],
                check=True, capture_output=True, timeout=120).stdout
        except (OSError, subprocess.SubprocessError):
            require(False, "fixed committed storage manifest is unavailable")
    require(git("rev-parse", "HEAD").decode().strip() == control, "checkout differs from exact control")
    require(git("cat-file", "-t", control).strip() == b"commit", "control is not an exact commit")
    require(git("rev-parse", "--is-shallow-repository").strip() == b"false", "storage authority needs complete history")
    require(git("cat-file", "-t", f"{control}:{STORAGE_PATH}").strip() == b"blob", "storage manifest is not a Git blob")
    config = batch_runtime.strict_json(git("show", f"{control}:{STORAGE_PATH}"))
    require(isinstance(config, dict) and set(config) == {"scheduler", "outbox"}, "storage roles are not closed")
    keys = {"repository", "issue_number", "issue_node_id", "bot_node_id", "workflow_id", "epoch"}
    for role, number in (("scheduler", 807), ("outbox", 817)):
        row = config[role]
        require(isinstance(row, dict) and set(row) == keys, "storage identity fields are not closed")
        require(row["repository"] == "endaye/lmdj" == environment.get("GITHUB_REPOSITORY")
                and type(row["issue_number"]) is int and row["issue_number"] == number
                and type(row["workflow_id"]) is int and row["workflow_id"] > 0
                and all(isinstance(row[k], str) and bool(row[k]) for k in ("issue_node_id", "bot_node_id", "epoch")),
                "storage identity does not describe the fixed main journals")
    require(all(config["scheduler"][k] == config["outbox"][k] for k in ("repository", "bot_node_id", "workflow_id"))
            and config["scheduler"]["issue_node_id"] != config["outbox"]["issue_node_id"], "storage authority aliases or differs")
    return config


class Entry:
    def __init__(self, *, root, environment=None, api=None):
        self.root = Path(root)
        self.env = dict(os.environ if environment is None else environment)
        self.config = load_storage(self.root, self.env)
        self.runtime = batch_runtime.Runtime(self.config["scheduler"], root=self.root, environment=self.env, api=api)

    def event(self, payload):
        self.relay_witness = None
        kind = self.env.get("GITHUB_EVENT_NAME")
        require(kind in EVENTS and isinstance(payload, dict), "automatic event is outside the closed entry set")
        require(isinstance(payload.get("repository"), dict)
                and payload["repository"].get("full_name") == self.config["scheduler"]["repository"], "event repository differs")
        if kind == "push":
            require(payload.get("ref") == "refs/heads/main" and payload.get("deleted") is False
                    and payload.get("after") == self.runtime.control, "push is not exact nondeleted main control")
        if kind == "schedule":
            schedule = payload.get("schedule")
            require(type(schedule) is str and schedule in (SCHEDULER_HEALTH, REPORT_HEALTH),
                    "schedule is not an exact scheduler or report health role")
            return ("report-health" if schedule == REPORT_HEALTH else kind), None
        if kind != "workflow_run":
            return kind, None
        require(payload.get("action") == "completed" and isinstance(payload.get("workflow_run"), dict), "callback is not a completed run event")
        hint = payload["workflow_run"]
        if hint.get("path") == incremental_completion.WORKFLOW:
            # The relay is only an authenticated parent association, never
            # a new executor or generic settlement permission. Preserve
            # active-parent ownership and independently check idle main below,
            # along with the Runtime's stable
            # writer workflow identity.
            parent, self.relay_witness = incremental_completion.resolve(self.runtime, hint)
            return "batch", parent
        require(type(hint.get("id")) is int and hint["id"] > 0 and type(hint.get("run_attempt")) is int
                and hint["run_attempt"] > 0, "callback run/attempt is invalid")
        run = self.runtime.call("GET", self.runtime.repo(f"/actions/runs/{hint['id']}/attempts/{hint['run_attempt']}"))
        require(isinstance(run, dict) and all(type(run.get(k)) is int and run[k] == hint[k] for k in ("id", "run_attempt"))
                and run.get("status") == "completed", "actual callback attempt is not terminal")
        require(run.get("path") in WORKFLOWS, "callback workflow is not an owned source")
        for key in ("workflow_id", "head_sha", "head_branch", "path", "event", "status", "conclusion"):
            require(key in hint and type(hint[key]) is type(run.get(key)) and hint[key] == run.get(key), "callback metadata differs from actual exact attempt")
        repo = self.runtime.call("GET", self.runtime.repo(""))
        workflow = self.runtime.call("GET", self.runtime.repo("/actions/workflows/" + run["path"].rsplit("/", 1)[1]))
        require(isinstance(repo, dict) and type(repo.get("id")) is int and repo["id"] > 0
                and repo.get("full_name") == self.config["scheduler"]["repository"], "source repository identity is unavailable")
        require(isinstance(workflow, dict) and type(run.get("workflow_id")) is int
                and type(workflow.get("id")) is int and workflow["id"] == run["workflow_id"]
                and workflow.get("path") == run["path"], "source workflow identity conflicts")
        source_repo = run.get("repository")
        require(isinstance(source_repo, dict) and type(source_repo.get("id")) is int
                and source_repo["id"] == repo["id"] and source_repo.get("full_name") == repo["full_name"], "callback belongs to another repository")
        source = WORKFLOWS[run["path"]]
        if source == "batch":
            # get_run independently binds the existing stable workflow, main,
            # canonical head repository and closed originating event set.
            observed = self.runtime.get_run(run["id"], run["run_attempt"])
            require(observed == run and self.runtime.run_state({"run_id": run["id"], "attempt": run["run_attempt"]}) == "terminal",
                    "batch source changed while authenticating")
            self.runtime.inputs.verify_target(run["head_sha"])
        # Legacy/review source, producer, target and artifact proof are owned
        # by their existing planners. In particular PR heads need not be main.
        return source, run

    def state(self):
        return report_runtime.scheduler_state(self.runtime)

    def authenticate(self):
        self.diagnostic_stage = "authenticate"
        self.runtime.authenticate_current()
        self.diagnostic_stage = "auth-event"
        run = self.runtime.get_run(self.runtime.current["run_id"], 1)
        require(run.get("event") == self.env.get("GITHUB_EVENT_NAME"), "current API event differs from workflow context")

    def control(self, payload):
        self.authenticate()
        self.diagnostic_stage = "event-authenticate"
        source, run = self.event(payload)
        require(source != "report-health", "report health cannot authorize product control")
        # Read-only provenance for actual callback-chain audits. This proves
        # authenticated source identity, not admission, health or chain depth.
        # Never print the raw event, credentials or unvalidated source hints.
        witness = {
            "schema": "lmdj.ci-source-witness.v1",
            "current": {"run_id": self.runtime.current["run_id"],
                        "attempt": self.runtime.current["attempt"],
                        "control": self.runtime.control, "event": self.env["GITHUB_EVENT_NAME"]},
            "source_family": source,
            "source_run": {"id": run["id"], "attempt": run["run_attempt"]} if run is not None else None,
        }
        if self.relay_witness is not None:
            witness.update(schema="lmdj.ci-source-witness.v2", relay=self.relay_witness)
        print(self_test.canonical_json(witness), flush=True)
        if source in {"push", "schedule"}:
            self.diagnostic_stage = "reconcile"
            return self.runtime.reconcile(execute=True)
        if source == "batch":
            self.diagnostic_stage = "scheduler-read"
            state = self.state()
            identity = {"run_id": run["id"], "attempt": run["run_attempt"]}
            if state["active"] is not None and state["active"]["executor_run"] == identity:
                # Includes none: its previous idle answer still held a claim.
                self.diagnostic_stage = "reconcile"
                return self.runtime.reconcile(execute=True)
            if state["active"] is None:
                # Coalescing can cancel a push before it claims a batch. Its
                # authenticated completion is still a wakeup, not test evidence.
                # Recover only independently observed new main; unchanged idle
                # callbacks must not write or generate another execution chain.
                self.diagnostic_stage = "reconcile"
                if self.runtime.read_main() != state["processed"]:
                    return self.runtime.reconcile(execute=True)
            return self.runtime.answer("idle", "callback is not the authenticated active executor", None, state)
        return self.runtime.answer("idle", "report-only source cannot authorize execution", None, None)

    def reports(self, payload):
        self.authenticate()
        outcomes = []
        try:
            self.diagnostic_stage = "event-authenticate"
            source, run = self.event(payload)
            if source == "batch":
                self.diagnostic_stage = "scheduler-read"
                state = self.state()
                identity = {"run_id": run["id"], "attempt": run["run_attempt"]}
                active = state["active"] is not None and state["active"]["executor_run"] == identity
                settled = any(row["run"] == identity for row in state["results"].values())
                if not (active or settled):
                    return {"schema": REPORT_SCHEMA, "status": "ignored", "source": source, "outcomes": []}
            operations = [source] if source in {"legacy", "review"} else ["batches"]
        except Exception as error:
            emit_diagnostic("reports", self.diagnostic_stage, error)
            # Current writer/config were authenticated above. Unknown source
            # cannot queue a new report, but must not strand an old durable
            # outbox payload. A definite unrelated callback still exits above.
            source, run, operations = "unverified", None, []
            outcomes.append({"operation": "source", "result": {"status": "error",
                "why": "callback source or authenticated scheduler history is unresolved",
                "remedy": "restore exact source evidence; existing outbox recovery is independent"}})
        self.diagnostic_stage = "report-construction"
        reporter = report_runtime.ReportRuntime(self.config, root=self.root, environment=self.env, api=self.runtime.api)
        # A source-planning failure must not strand an already frozen outbox
        # payload. Each operation has its own visible result; no execute path.
        for operation in [*operations, "drain"]:
            try:
                self.diagnostic_stage = "report"
                result = reporter.execute(operation, limit=1, **({"run_id": run["id"], "attempt": run["run_attempt"]}
                    if operation in {"legacy", "review"} else {}))
            except Exception as error:
                emit_diagnostic("reports", self.diagnostic_stage, error)
                result = {"status": "error", "why": "authenticated report source or outbox state is unresolved",
                          "remedy": "inspect exact source and durable pending record; do not replay a claimed POST"}
            outcomes.append({"operation": operation, "result": result})
        failed = any(row["result"].get("status") in {"error", "needs-reconciliation"} for row in outcomes)
        return {"schema": REPORT_SCHEMA, "status": "error" if failed else "ready", "source": source, "outcomes": outcomes}


@observe('entry')
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("control", "reports"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    entry = None
    stage = "output-preflight"
    try:
        require(not args.output.exists(), "output exists; stale execution or report output must not be reused")
        stage = "entry-construction"
        entry = Entry(root=args.root)
        stage = "event-read"
        payload = batch_runtime.strict_json(Path(entry.env["GITHUB_EVENT_PATH"]).read_bytes())
        stage = "operation"
        answer = getattr(entry, args.operation)(payload)
        stage = "output-write"
        with args.output.open("x") as stream:
            stream.write(self_test.canonical_json(answer) + "\n")
        return 1 if args.operation == "reports" and answer["status"] == "error" else 0
    except Exception as error:
        if stage == "operation":
            stage = getattr(entry, "diagnostic_stage", None)
            runtime_stage = getattr(getattr(entry, "runtime", None), "diagnostic_stage", None)
            if runtime_stage is not None:
                stage = runtime_stage
        emit_diagnostic(args.operation, stage, error)
        print("why: automatic entry could not authenticate or persist its result; remedy: retain exact source and reconcile; never reuse an old execute output")
        if args.operation == "reports" and not args.output.exists():
            # A report error is a separate diagnostic, never a replacement
            # runtime result or authority to launch tests.
            try:
                with args.output.open("x") as stream:
                    stream.write(self_test.canonical_json({"schema": REPORT_SCHEMA, "status": "error",
                        "source": "unverified", "outcomes": [], "why": "automatic reporting input or storage is unresolved",
                        "remedy": "inspect exact source and durable outbox; do not replay a claimed POST"}) + "\n")
            except OSError:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
