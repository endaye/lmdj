#!/usr/bin/env python3
"""Short-lock reporting composition; never observes or changes scheduler state.

Only the separately configured outbox journal is writable. Workflow wiring and
the reserved Issue's creation are separate tasks. This adapter does not create
release evidence, close defect Issues, launch tests or retry an uncertain POST.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import batch_controller
import batch_runtime
import batch_verdict
import change_scope
import incremental_batch as batch
from incremental_batch_journal import Journal
import report_outbox
import review_failure_report
import self_test_report as reporting


def require(ok, why):
    if not ok:
        raise ValueError("why: " + why + "; remedy: reconcile exact authenticated report inputs; do not replay a business POST or alter scheduler progress")


class ReadOnlyAnchor:
    def __init__(self, anchor):
        self.anchor = anchor

    def read(self):
        return self.anchor.read()

    def replace(self, previous, replacement):
        require(False, "scheduler checkpoint has a pending append; only its controller may recover it")


def scheduler_state(runtime):
    """Authenticate the whole journal; reuse historical-policy replay, not reconcile.

Journal.load normally repairs an already visible pending append. Disallow that
PATCH here as well as all event appends. The outbox has its own writable anchor.
"""
    source = runtime.journal()
    journal = Journal(source.issue_id, source.transport, ReadOnlyAnchor(source.anchor),
                      source.authenticate, source.lock_held)
    events = journal.load()
    def forbidden(*args, **kwargs):
        require(False, "report replay attempted a scheduler side effect")
    replay = batch_controller.Controller(journal, runtime.inputs, runtime.current,
        run_state=forbidden, result_for=forbidden, old_runs_terminal=forbidden,
        lock_held=runtime.lock_held, epoch=runtime.config["epoch"])
    replay.policy = runtime.inputs.policy_at(runtime.control)
    return replay._replay(events)


class ScopedReport(reporting.Report):
    def issue_body(self, assignee):
        return "\n".join([self.key_marker, "## " + self.title, "",
            "Filed from an authenticated incremental batch journal result, not full-release evidence.",
            "This is a suite/class bucket; observations may represent different defects.",
            "Unselected suites are not passes. Reporting neither blocks PR merges nor closes existing defects.",
            f"Default assignee `@{assignee}`. Severity **{self.severity}**.", "",
            self.comment_body(first=True)])


def plan_batch_reports(repository, state, inputs):
    """Pure reporting projection after complete authenticated historical replay."""
    reports = []
    for request_id, result in state["results"].items():
        request = state["requests"][request_id]
        policy = inputs.policy_at(request["control"])
        run = result["run"]
        identity = dict(request_id=request_id, request_kind=request["kind"], base_sha=request["base"],
            target_sha=request["target"], control_sha=request["control"], policy_digest=request["policy"],
            run_id=run["run_id"], run_attempt=run["attempt"])
        reference = result["reference"]
        selection = request["selection"]
        if reference == f"not-required:{request_id}":
            require(not selection["suites"] and not result["outcomes"], "not-required receipt claims selected work")
            continue
        if reference == f"missing:{request_id}":
            require(bool(selection["suites"]) and result["outcomes"] == {
                suite: "missing" for suite in selection["suites"]}, "missing receipt has non-missing outcomes")
            suites = [dict(id=suite, selected=True, failures=[], verification_debt=True,
                           scheduler_outcome="missing", jobs={}, diagnostics=[
                               "Selected execution evidence was confirmed missing; no product verdict is available."])
                      for suite in selection["suites"]]
            evidence_digest = batch.digest({"identity": identity, "reference": reference})
        else:
            require(bool(selection["suites"]), "empty selection must use its exact not-required receipt")
            verdict = batch_verdict.validate(batch_runtime.decode_reference(reference), policy, identity, selection)
            require(result["outcomes"] == batch_verdict.scheduler_outcomes(verdict, policy, identity, selection),
                    "journal outcomes differ from the durable scoped verdict")
            suites, evidence_digest = verdict["suites"], verdict["evidence_digest"]
        for suite in suites:
            if not suite["selected"]:
                continue
            classes = []
            if suite["failures"]:
                classes.append("test_failure")
            if suite["verification_debt"]:
                classes.append({"infrastructure": "infrastructure_failure", "cancelled": "blocked",
                                "blocked": "blocked", "missing": "missing"}[suite["scheduler_outcome"]])
            for failure_class in classes:
                key = f"self-test-{suite['id']}-{failure_class}".replace("_", "-")
                # Digest the complete identity, not just a bucket or target. The
                # plain exact identity remains visible in the human report body.
                observation = "batch/" + batch.digest({"epoch": state["epoch"], "identity": identity,
                    "suite": suite["id"], "class": failure_class, "evidence_digest": evidence_digest})
                common = [f"- Request: `{reporting.sanitize(request_id, 200)}` ({request['kind']})",
                    f"- Base: `{request['base']}`; target: `{request['target']}`; control: `{request['control']}`",
                    f"- Run: https://github.com/{repository}/actions/runs/{run['run_id']}/attempts/{run['attempt']}",
                    f"- Scope: **{selection['kind']}**; selected: {', '.join(selection['suites'])}",
                    "- Not selected (not passes): " + (", ".join(sorted(set(policy.suite_ids) - set(selection['suites']))) or "none"),
                    f"- Policy: `{request['policy']}`; evidence: `{evidence_digest}`",
                    f"- Suite: `{suite['id']}`; class: **{failure_class}**",
                    f"- Actual failed jobs: {', '.join(suite['failures']) or 'none'}",
                    f"- Verification debt: {suite['scheduler_outcome'] if suite['verification_debt'] else 'none'}",
                    "- Next step: investigate the exact target and execution; retain uncovered work and unresolved defects."]
                detail = "\n".join(["```text", reporting.sanitize(json.dumps({
                    "jobs": suite["jobs"], "diagnostics": suite["diagnostics"]}, sort_keys=True), 1800), "```"])
                reports.append(ScopedReport(key=key, title=f"self-test: {suite['id']} {failure_class.replace('_', ' ')}",
                    observation=observation, severity=reporting.severity_of(suite["id"], failure_class),
                    labels=(reporting.REPORT_LABEL, "type:bug", "area:core" if failure_class == "test_failure" else "area:ci-release"),
                    summary="\n".join(common), detail=detail))
    return tuple(reports)


class ReportRuntime:
    def __init__(self, config, *, root, environment=None, api=None):
        require(isinstance(config, dict) and set(config) == {"scheduler", "outbox"}, "report config is not closed")
        self.scheduler = batch_runtime.Runtime(config["scheduler"], root=root, environment=environment, api=api)
        self.storage = batch_runtime.Runtime(config["outbox"], root=root, environment=environment, api=self.scheduler.api)
        a, b = self.scheduler.config, self.storage.config
        require(all(a[key] == b[key] for key in ("repository", "bot_node_id", "workflow_id")),
                "scheduler and outbox do not share the existing writer authority")
        require(a["issue_number"] != b["issue_number"] and a["issue_node_id"] != b["issue_node_id"],
                "outbox storage aliases the scheduler Issue")
        self.api, self.repository = self.storage.api, b["repository"]

    def outbox(self):
        return report_outbox.Outbox(self.storage.journal(), self.storage.lock_held, self.storage.config["epoch"])

    def deliver(self, planned, limit):
        require(type(limit) is int and 1 <= limit <= 32, "report limit must be 1..32")
        outbox = self.outbox()
        state = outbox.load()
        # Validate every body before the first business write. Existing entries
        # never consume the new-observation budget, including ambiguous claims.
        missing = []
        for report in planned:
            key = batch.digest({"key": report.key, "observation": report.observation})
            payload = report_outbox.freeze(report, reporting.DEFAULT_ASSIGNEE)
            if key in state["deliveries"]:
                require(state["deliveries"][key]["payload"] == payload, "report body changed under an existing observation")
            else:
                missing.append(report)
        outcomes = [outbox.deliver(self.api, report) for report in missing[:limit]]
        # Resume one previously queued payload even if its source artifact has
        # expired. Replayed POST claims only authorize receipt reads.
        tail = outbox.drain_once(self.api)
        blocked = next((item for item in [*outcomes, tail] if item["status"] == "needs-reconciliation"), None)
        return {"status": "needs-reconciliation" if blocked else "ready", "queued": min(len(missing), limit),
                "remaining": max(0, len(missing) - limit), "outcomes": outcomes, "drain": tail,
                **({"why": blocked["why"], "remedy": blocked["remedy"]} if blocked else {})}

    def execute(self, operation, *, run_id=None, attempt=None, limit=8):
        require(operation in {"init-outbox", "review", "legacy", "batches", "drain"}, "unknown report operation")
        if operation == "init-outbox":
            return self.storage.initialize()
        self.storage.authenticate_current()
        if operation == "drain":
            return self.outbox().drain_once(self.api)
        if operation == "review":
            planned = review_failure_report.collect(self.api, self.repository, run_id, attempt)
            return self.deliver((planned,), limit) if planned else {"status": "not-applicable"}
        if operation == "legacy":
            metadata, planned = reporting.plan_run(self.api, run_id, attempt=attempt,
                                                   repository=self.repository, sleep=lambda _: None)
            require(metadata.error is None, metadata.error or "legacy planning failed")
            if metadata.skipped is not None:
                return {"status": "not-applicable", "why": metadata.skipped}
            answer = self.deliver(planned, limit)
            return {**answer, "source": "self-test-v1", "run_id": run_id, "attempt": attempt,
                    "target": metadata.target, "verdict_status": metadata.verdict_status}
        # authenticate_current refreshes the outbox Runtime's inputs; scheduler
        # inputs are a separate object and must independently resolve main.
        self.scheduler.inputs.refresh()
        state = scheduler_state(self.scheduler)
        return self.deliver(plan_batch_reports(self.repository, state, self.scheduler.inputs), limit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("init-outbox")
    commands.add_parser("drain")
    review = commands.add_parser("review")
    review.add_argument("--run-id", type=int, required=True)
    review.add_argument("--attempt", type=int, required=True)
    legacy = commands.add_parser("legacy", help="report one exact legacy full attempt through the durable outbox")
    legacy.add_argument("--run-id", type=int, required=True)
    legacy.add_argument("--attempt", type=int, required=True)
    legacy.add_argument("--limit", type=int, default=8)
    batches = commands.add_parser("batches")
    batches.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text(), object_pairs_hook=change_scope.reject_duplicates)
        runtime = ReportRuntime(config, root=args.root)
        answer = runtime.execute(args.operation, run_id=getattr(args, "run_id", None),
                                 attempt=getattr(args, "attempt", None), limit=getattr(args, "limit", 8))
    except Exception:
        # HTTP/git exceptions may include credential-bearing URLs or headers.
        answer = {"status": "error", "why": "authenticated reporting evidence or durable storage is unresolved",
                  "remedy": "inspect exact run/Issue provenance and pending intent; do not retry a claimed POST"}
    with args.summary.open("a") as stream:
        stream.write("Incremental report runtime: " + json.dumps(answer, sort_keys=True) + "\n")
    return 1 if answer.get("status") in {"error", "needs-reconciliation"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
