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
from api_observation import observe


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
    state = replay._replay(events)
    result_order = [event["data"]["request_id"] for event in events if event.get("type") == "result"]
    require(len(result_order) == len(state["results"]) and set(result_order) == set(state["results"]),
            "scheduler result order is not a complete unique journal projection")
    state["_result_order"] = result_order
    return state


class ScopedReport(reporting.Report):
    def issue_body(self, assignee):
        markers = [self.key_marker]
        if self.management is not None:
            markers.extend([self.managed_marker, self.provenance_marker])
        return "\n".join([*markers, "## " + self.title, "",
            "Filed from an authenticated incremental batch journal result, not full-release evidence.",
            "This is a suite/class bucket; observations may represent different defects.",
            "Unselected suites are not passes. Reporting neither blocks PR merges nor closes existing defects.",
            f"Default assignee `@{assignee}`. Severity **{self.severity}**.", "",
            self.comment_body(first=True)])


class CommonInfrastructureReport(reporting.Report):
    """One Issue report for one authenticated shared dependency event."""

    def issue_body(self, assignee):
        return "\n".join([self.key_marker, "## " + self.title, "",
            "Filed from an authenticated incremental batch shared infrastructure event, not full-release evidence.",
            "This report groups only the selected suite debt blocked by its exact failed control dependency.",
            "Independent test failures, cancellations, unselected suites and unrelated debt remain separate.",
            f"Default assignee `@{assignee}`. Severity **{self.severity}**.", "",
            self.comment_body(first=True)])


def _managed_identity(request, suite, failure_class, order, *, epoch, run):
    """Machine management is opt-in for automatic/bootstrap suite reports."""
    if request["kind"] not in {"auto", "bootstrap"}:
        return None
    key = reporting.managed_bucket_key(epoch, request["policy"], suite, failure_class)
    return {"schema": reporting.MANAGED_BUCKET_SCHEMA, "epoch": epoch,
            "key": key,
            "suite": suite, "failure_class": failure_class,
            "policy": request["policy"], "selection": batch.digest(request["selection"]),
            "target": request["target"], "request": request["id"],
            "run": run["run_id"], "attempt": run["attempt"],
            "order": order}


def plan_batch_reports(repository, state, inputs):
    """Pure reporting projection after complete authenticated historical replay."""
    reports = []
    ordered = state.get("_result_order")
    require(isinstance(ordered, list) and len(ordered) == len(state["results"])
            and set(ordered) == set(state["results"]),
            "causal order must come from complete authenticated scheduler journal results")
    for order, request_id in enumerate(ordered, 1):
        result = state["results"][request_id]
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
            common_events = verdict.get("common_events", [])
        if reference == f"missing:{request_id}":
            common_events = []
        by_suite = {suite["id"]: suite for suite in suites}
        observations_by_suite = {}
        if reference != f"missing:{request_id}":
            for observation in verdict["observations"]:
                observations_by_suite.setdefault(observation["suite"], []).append(observation)
        event_suites = set()
        for event in common_events:
            affected = set(event["blocked_suites"])
            require(affected and affected <= set(selection["suites"]),
                    "common event lists an unselected or empty suite set")
            for suite_id in affected:
                suite = by_suite.get(suite_id)
                blocked_rows = [row for row in observations_by_suite.get(suite_id, [])
                                if row.get("blocked_by") == event["cause"]]
                require(suite is not None and suite["selected"] and suite["verification_debt"]
                        and blocked_rows,
                        "common event is not bound to exact blocked job debt")
            event_suites |= affected
            event_observation = "batch/" + batch.digest({"epoch": state["epoch"],
                "identity": identity, "event": event})
            common = [f"- Request: `{reporting.sanitize(request_id, 200)}` ({request['kind']})",
                f"- Base: `{request['base']}`; target: `{request['target']}`; control: `{request['control']}`",
                f"- Run: https://github.com/{repository}/actions/runs/{run['run_id']}/attempts/{run['attempt']}",
                f"- Scope: **{selection['kind']}**; selected: {', '.join(selection['suites'])}",
                "- Not selected (not passes): " + (", ".join(sorted(set(policy.suite_ids) - set(selection['suites']))) or "none"),
                f"- Policy: `{request['policy']}`; evidence: `{evidence_digest}`",
                f"- Common event: `{event['event_id']}`; kind: **{event['kind']}**; cause: `{event['cause']}`",
                f"- Source: needs job `{event['source']['job']}` result **{event['source']['result']}**; source digest: `{event['source']['digest']}`",
                "- Affected suite debt: " + ", ".join(sorted(affected)),
                "- Next step: repair the shared dependency and rerun the exact target; retain every suite's uncovered work."]
            details = {suite_id: {"jobs": by_suite[suite_id]["jobs"],
                                  "diagnostics": by_suite[suite_id]["diagnostics"]}
                       for suite_id in sorted(affected)}
            detail = "\n".join(["```text", reporting.sanitize(json.dumps({
                "event": event, "suite_debt": details}, sort_keys=True), 5000), "```"])
            reports.append(CommonInfrastructureReport(
                key=reporting.common_event_report_key(event["event_id"]),
                title=f"self-test: shared infrastructure event {event['cause']}",
                observation=event_observation, severity="medium",
                labels=(reporting.REPORT_LABEL, "type:bug", "area:ci-release"),
                summary="\n".join(common), detail=detail))
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
                # A common event only accounts for rows explicitly blocked by
                # its cause. A cancellation can map to the same report class
                # for compatibility, but remains an independent debt.
                if (failure_class == "blocked" and suite["id"] in event_suites
                        and suite["scheduler_outcome"] == "blocked"):
                    continue
                management = _managed_identity(request, suite["id"], failure_class, order,
                                                epoch=state["epoch"], run=run)
                key = (management["key"] if management is not None
                       else f"self-test-{suite['id']}-{failure_class}".replace("_", "-"))
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
                    summary="\n".join(common), detail=detail,
                    management=management, causal_order=(order if management is not None else None)))
    return tuple(reports)


def plan_bucket_recoveries(state, inputs):
    """Project only authenticated, actual, debt-free successes.

    The outbox decides whether the corresponding bucket is a new managed
    bucket. This planner never treats Issue prose or historical numbers as
    evidence and never emits recovery for explicit human/candidate requests.
    """
    recoveries = []
    ordered = state.get("_result_order")
    require(isinstance(ordered, list) and len(ordered) == len(state["results"])
            and set(ordered) == set(state["results"]),
            "causal order must come from complete authenticated scheduler journal results")
    for order, request_id in enumerate(ordered, 1):
        result = state["results"][request_id]
        request = state["requests"][request_id]
        if request["kind"] not in {"auto", "bootstrap"}:
            continue
        reference = result["reference"]
        if reference.startswith("missing:") or reference.startswith("not-required:"):
            continue
        policy = inputs.policy_at(request["control"])
        identity = dict(request_id=request_id, request_kind=request["kind"], base_sha=request["base"],
                        target_sha=request["target"], control_sha=request["control"], policy_digest=request["policy"],
                        run_id=result["run"]["run_id"], run_attempt=result["run"]["attempt"])
        verdict = batch_verdict.validate(batch_runtime.decode_reference(reference), policy, identity, request["selection"])
        for suite in verdict["suites"]:
            if not suite["selected"] or suite["status"] != "passed" or suite["verification_debt"]:
                continue
            for failure_class in reporting.FAILURE_CLASSES:
                key = reporting.managed_bucket_key(state["epoch"], request["policy"], suite["id"], failure_class)
                observation = "recovery/" + batch.digest({"epoch": state["epoch"], "identity": identity,
                    "suite": suite["id"], "class": failure_class, "evidence_digest": verdict["evidence_digest"]})
                recoveries.append(reporting.Recovery(
                    key=key, suite=suite["id"], failure_class=failure_class,
                    observation=observation, target=request["target"], request=request_id,
                    run=result["run"]["run_id"], attempt=result["run"]["attempt"],
                    policy=request["policy"], selection=batch.digest(request["selection"]), order=order,
                    epoch=state["epoch"],
                    evidence=verdict["evidence_digest"], summary="\n".join([
                        f"- Request: `{reporting.sanitize(request_id, 200)}` ({request['kind']})",
                        f"- Target: `{request['target']}`; run: `{result['run']['run_id']}/{result['run']['attempt']}`",
                        f"- Suite: `{suite['id']}`; class: **{failure_class}**",
                        f"- Policy: `{request['policy']}`; selection: `{batch.digest(request['selection'])}`",
                        f"- Evidence digest: `{verdict['evidence_digest']}`",
                        "- Actual result: **passed** with no remaining verification debt."])) )
    return tuple(recoveries)


def causal_floor(state, inputs):
    """Latest authenticated debt ordinal for every managed suite namespace."""
    ordered = state.get("_result_order")
    require(isinstance(ordered, list) and len(ordered) == len(state["results"])
            and set(ordered) == set(state["results"]),
            "causal order must come from complete authenticated scheduler journal results")
    floor = {}
    for order, request_id in enumerate(ordered, 1):
        request = state["requests"][request_id]
        if request["kind"] not in {"auto", "bootstrap"}:
            continue
        policy = inputs.policy_at(request["control"])
        for suite, outcome in state["results"][request_id]["outcomes"].items():
            if outcome == "passed":
                continue
            for failure_class in reporting.FAILURE_CLASSES:
                key = reporting.managed_bucket_key(state["epoch"], request["policy"], suite, failure_class)
                floor[key] = max(floor.get(key, 0), order)
    return floor


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

    def deliver(self, planned, limit, *, recoveries=(), causal_floor=None):
        require(type(limit) is int and 1 <= limit <= 32, "report limit must be 1..32")
        outbox = self.outbox()
        state = outbox.load()
        managed_keys = {(delivery["payload"]["fields"].get("management") or {}).get("key")
                        for delivery in state["deliveries"].values()
                        if delivery["status"] == "delivered"
                        and delivery["payload"]["fields"].get("management") is not None}
        # Only the latest authenticated success per managed key can do useful
        # recovery work; irrelevant historical successes do not cause API
        # lookups or consume the bounded report operation.
        latest_recovery = {}
        for recovery in recoveries:
            # Choose the newest success for each relevant managed key before
            # applying the operation budget. A terminal old success must not
            # occupy the first slot forever while later keys wait.
            if recovery.key in managed_keys and recovery.order >= latest_recovery.get(recovery.key, (0,))[0]:
                latest_recovery[recovery.key] = (recovery.order, recovery)
        terminal = {"closed", "stale", "not-applicable"}
        recoveries = [item[1] for item in latest_recovery.values()
                      if ((row := state["recoveries"].get(item[1].recovery_id)) is None
                          or row["status"] not in terminal)][:limit]
        floor = dict(causal_floor or {})
        if (causal_floor is None and (recoveries or any(
                row["status"] not in {"closed", "stale", "not-applicable"}
                for row in state["recoveries"].values()))):
            floor.update(self._authenticated_causal_floor())
        # A pre-T8b outbox delivery is intentionally unmanaged and uses the
        # historical suite/class key. Match its complete observation before
        # applying the new namespace, so a full replay does not duplicate the
        # old Issue or delivery identity. New observations have no such alias.
        effective_planned = []
        for report in planned:
            legacy = None
            if report.management is not None:
                legacy_key = f"self-test-{report.management['suite']}-{report.management['failure_class']}".replace("_", "-")
                matches = [delivery for delivery in state["deliveries"].values()
                           if delivery["payload"]["fields"].get("key") == legacy_key
                           and delivery["payload"]["fields"].get("observation") == report.observation
                           and delivery["payload"]["fields"].get("management") is None]
                require(len(matches) <= 1, "historical v1 observation has duplicate frozen deliveries")
                legacy = matches[0] if matches else None
            effective_planned.append(report_outbox.FrozenReport(legacy["payload"]) if legacy else report)
        # Validate every body before the first business write. Existing entries
        # never consume the new-observation budget, including ambiguous claims.
        missing = []
        for report in effective_planned:
            key = batch.digest({"key": report.key, "observation": report.observation})
            payload = report_outbox.freeze(report, reporting.DEFAULT_ASSIGNEE)
            if key in state["deliveries"]:
                require(report_outbox.frozen_payload_equal(state["deliveries"][key]["payload"], payload),
                        "report body changed under an existing observation")
            else:
                missing.append(report)
        outcomes = [outbox.deliver(self.api, report) for report in missing[:limit]]
        # Resume one previously queued payload even if its source artifact has
        # expired. Replayed POST claims only authorize receipt reads.
        for report in planned:
            if report.management is not None and report.causal_order is not None:
                floor[report.key] = max(floor.get(report.key, 0), report.causal_order)
        recovery_outcomes = [outbox.recover_success(self.api, recovery, causal_floor=floor) for recovery in recoveries]
        tail = outbox.drain_once(self.api, causal_floor=floor)
        blocked = next((item for item in [*outcomes, *recovery_outcomes, tail]
                        if item["status"] == "needs-reconciliation"), None)
        return {"status": "needs-reconciliation" if blocked else "ready", "queued": min(len(missing), limit),
                "remaining": max(0, len(missing) - limit), "outcomes": outcomes,
                "recoveries": recovery_outcomes, "drain": tail,
                **({"why": blocked["why"], "remedy": blocked["remedy"]} if blocked else {})}

    def _authenticated_causal_floor(self):
        self.scheduler.inputs.refresh()
        state = scheduler_state(self.scheduler)
        return causal_floor(state, self.scheduler.inputs)

    def execute(self, operation, *, run_id=None, attempt=None, limit=8):
        require(operation in {"init-outbox", "review", "legacy", "batches", "drain"}, "unknown report operation")
        if operation == "init-outbox":
            return self.storage.initialize()
        self.storage.authenticate_current()
        if operation == "drain":
            outbox = self.outbox()
            stored = outbox.load()
            has_recovery = any(row["status"] not in {"closed", "stale", "not-applicable"}
                               for row in stored["recoveries"].values())
            if not has_recovery:
                # Legacy queued reports have no scheduler causal namespace;
                # keep their v1 replay reachable when the scheduler Issue is
                # not provisioned in this runtime configuration.
                return outbox.drain_once(self.api)
            # Recovery is a write-adjacent operation: refresh the complete
            # authenticated scheduler projection so a stale queued success
            # cannot close a newer failure while draining old outbox work.
            self.scheduler.inputs.refresh()
            state = scheduler_state(self.scheduler)
            planned = plan_batch_reports(self.repository, state, self.scheduler.inputs)
            floor = causal_floor(state, self.scheduler.inputs)
            return outbox.drain_once(self.api, causal_floor=floor)
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
        return self.deliver(plan_batch_reports(self.repository, state, self.scheduler.inputs), limit,
                            recoveries=plan_bucket_recoveries(state, self.scheduler.inputs),
                            causal_floor=causal_floor(state, self.scheduler.inputs))


@observe('report')
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
