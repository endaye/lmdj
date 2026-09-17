#!/usr/bin/env python3
"""One short, externally locked journal transaction; no workflow dispatch.

Ports supply authenticated main/run/result observations, never PR/model claims.
An execute action is returned only AFTER a new durable claim. Losing that return
can sacrifice execution, but cannot cause a duplicate: terminal reconciliation
records missing coverage. Calling code must never retry an execute action.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import change_scope
import incremental_batch as batch
import test_scope

# A journal object (writer, envelope and event) must stay under the
# batch_github_journal.LIMIT of 60,000 bytes, and a checkpoint carries the whole
# pending admit. The interval explanation is the only request field that grows
# with the unprocessed backlog (one reason per changed path: 2,355 reasons and
# 261 KB after 261 commits), so it is bounded here. Suites are the decision and
# are never touched; reasons only explain it.
REASON_BUDGET = 16000
OMISSION = ("why: {count} further selection reasons were omitted so the admit record stays within the journal "
            "object limit; remedy: recompute the interval selection from Git history and policy for the "
            "complete explanation")


def _encoded_size(reasons):
    return len(json.dumps(reasons, separators=(",", ":")).encode("utf-8"))


def bounded_reasons(reasons, budget=REASON_BUDGET):
    """Canonical (sorted, unique) reasons whose encoding fits the budget.

    Reasons are kept in canonical order until the next one would no longer fit
    beside a single counted omission reason; that omission then stands for the
    rest. Applying the bound to its own output changes nothing, so a stored
    request rebuilds to itself and the journal replay stays exact.
    """
    ordered = sorted(set(reasons))
    if _encoded_size(ordered) <= budget:
        return ordered
    kept = []
    for reason in ordered:
        candidate = sorted([*kept, reason, OMISSION.format(count=len(ordered) - len(kept) - 1)])
        if _encoded_size(candidate) > budget:
            break
        kept.append(reason)
    return sorted([*kept, OMISSION.format(count=len(ordered) - len(kept))])


class GitInputs:
    """Read immutable Git data, not historical Python code.

read_main must fetch/authenticate the actual repository main, returning its full
SHA. advice, when supplied, authenticates every interval PR mapping and returns
{complete: bool, labels: [...]}; it cannot replace actual Git path classification.
Absent/incomplete advice does not mean that independently verified Git history
is incomplete. Complete paths and trusted policies still define the floor.
"""
    def __init__(self, repository, control_sha, read_main, advice=None):
        self.repository = Path(repository)
        self.control_sha = batch.exact_sha(control_sha)
        self.read_main, self.advice = read_main, advice
        self.main = None
        self._policies = {}

    def _git(self, *args):
        try:
            return subprocess.run(["git", "--no-replace-objects", "-C", str(self.repository), *args],
                                  check=True, capture_output=True, timeout=120).stdout
        except (OSError, subprocess.SubprocessError):
            raise batch.BatchError("why: complete trusted Git input unavailable; remedy: fetch history and reconcile") from None

    def refresh(self):
        self.main = batch.exact_sha(self.read_main())
        self.verify_target(self.main)
        batch.require(self.ancestor(self.control_sha, self.main), "control is not authenticated main history")
        return self.main

    def ancestor(self, base, target):
        base, target = batch.exact_sha(base), batch.exact_sha(target)
        return self._git("merge-base", base, target).decode().strip() == base

    def verify_target(self, target):
        batch.exact_sha(target)
        batch.require(self._git("rev-parse", "--is-shallow-repository").strip() == b"false",
                      "shallow history cannot prove admission", "fetch complete history before reconciling")
        batch.require(self._git("cat-file", "-t", target).strip() == b"commit", "target is not a commit")
        batch.require(bool(self._git("rev-list", "--first-parent", target)), "target history is unavailable")
        batch.require(self.main is not None and self.ancestor(target, self.main),
                      "target is not verified main history")

    def policy_at(self, control):
        batch.exact_sha(control)
        batch.require(self.main is not None and self.ancestor(control, self.main),
                      "historical control is not verified main history")
        if control in self._policies:
            return self._policies[control]
        documents = [json.loads(self._git("show", f"{control}:scripts/ci/{name}"),
                                object_pairs_hook=change_scope.reject_duplicates)
                     for name in ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json")]
        self._policies[control] = test_scope.parse_policy(*documents)
        return self._policies[control]

    def interval_selection(self, base, target, policy):
        interval = test_scope.collect_interval(self.repository, base, target)
        policies = [policy]
        for sha in dict.fromkeys([base] + [c["sha"] for c in interval["commits"]]):
            try:
                policies.append(self.policy_at(sha))
            except (batch.BatchError, test_scope.ScopeError, ValueError):
                policies.append(None)
        advice = self.advice(deepcopy(interval)) if self.advice else {"complete": False, "labels": []}
        batch.require(isinstance(advice, dict) and set(advice) == {"complete", "labels"}
                      and type(advice["complete"]) is bool and isinstance(advice["labels"], list),
                      "scope mapping observation is malformed")
        # collect_interval independently proved the full first-parent union.
        # Missing advice cannot turn that proof into an incomplete path list:
        # spec 3.3 calls for actual-file fallback, not unconditional full runs.
        # Retain every authenticated partial suggestion. Missing old policies,
        # unknown paths/dependencies or valid full advice still select full.
        selection = test_scope.select_across_policies(interval["paths"], policies,
                                                     advice["labels"], complete=True)
        if not advice["complete"]:
            selection["reasons"].append(
                "why: review scope records are incomplete; remedy: restore authenticated review evidence; "
                "complete Git and historical-policy rules define the fallback scope")
        return test_scope._selection(policy, selection["suites"], bounded_reasons(selection["reasons"]))


class Controller:
    """Callable composition of the existing T3 Journal and reducer.

run_state(run) -> 'terminal' | 'running' | 'unknown', from actual executor API.
result_for(request, run) -> {status: 'pending'|'missing'} or
{status: 'ready', outcomes: {...}, reference: durable_reference}. The ready port
MUST authenticate/recompute scoped evidence against the complete request and
executor identity. Missing means confirmed loss, not an API error/visibility lag.
old_runs_terminal() must inventory all pre-existing controlled heavy runs, and
exclude this current lightweight controller (which has not admitted work yet).
All methods must be invoked inside the SAME externally managed short lock.
"""
    def __init__(self, journal, inputs, current_run, *, run_state, result_for,
                 old_runs_terminal, lock_held, epoch=None):
        self.journal, self.inputs = journal, inputs
        self.run = batch.identity(current_run)
        self.run_state, self.result_for = run_state, result_for
        self.old_runs_terminal, self.lock_held = old_runs_terminal, lock_held
        self.epoch = epoch
        self.state = None
        self.policy = None

    def _guard(self):
        batch.require(self.lock_held() is True, "controller lacks the shared short writer lock")

    def _replay(self, events):
        epoch = events[0].get("epoch") if events else self.epoch
        batch.require(self.epoch is None or self.epoch == epoch, "configured epoch disagrees with journal")
        state = batch.new_state(epoch)
        for event in events:
            policy = self.policy
            if event.get("type") in {"enqueue", "admit"}:
                request = event["data"] if event["type"] == "enqueue" else event["data"]["request"]
                policy = self.inputs.policy_at(request["control"])
            state = batch.reduce(state, event, policy)
        return state

    def _persist(self, kind, data, policy=None):
        self._guard()
        event = {"id": f"{self.state['epoch']}:{self.state['generation']}",
                 "epoch": self.state["epoch"], "generation": self.state["generation"],
                 "type": kind, "data": deepcopy(data)}
        expected = batch.reduce(self.state, event, policy or self.policy)
        # append may throw AFTER storing. No action escapes on an uncertain write.
        committed = self._replay(self.journal.append(event))
        batch.require(committed == expected, "journal commit differs from validated transition")
        self.state = committed

    def _answer(self, action, reason, request=None):
        return {"action": action, "reason": reason, "request": deepcopy(request), "state": deepcopy(self.state)}

    def _settle_active(self, allow_execution=True):
        active = self.state["active"]
        if active is None:
            return None
        request = self.state["requests"][active["request_id"]]
        executor = active["executor_run"]
        status = self.run_state(deepcopy(executor))
        batch.require(isinstance(status, str) and status in {"terminal", "running", "unknown"},
                      "invalid executor state observation")
        if status != "terminal":
            # A prior admit whose response was lost can still claim in its own
            # run; an already committed claim can NEVER reissue execution.
            if allow_execution and status == "running" and executor == self.run and active["claim"] is None:
                self._persist("claim", {"request_id": request["id"], "run": executor})
                return self._answer("execute" if request["selection"]["suites"] else "idle",
                                    "new durable claim; none waits for real executor completion", request)
            return self._answer("waiting", "active executor not proven terminal", request)
        if request["id"] not in self.state["results"]:
            if active["claim"] is None:
                # Journal recovery, not a launch: the old run is proven dead.
                self._persist("claim", {"request_id": request["id"], "run": executor})
                receipt = {"status": "missing"}
            elif not request["selection"]["suites"]:
                receipt = {"status": "ready", "outcomes": {}, "reference": f"not-required:{request['id']}"}
            else:
                receipt = self.result_for(deepcopy(request), deepcopy(executor))
            batch.require(isinstance(receipt, dict) and isinstance(receipt.get("status"), str)
                          and receipt["status"] in {"ready", "missing", "pending"},
                          "result availability observation is malformed")
            status = receipt["status"]
            batch.require(set(receipt) == ({"status", "outcomes", "reference"} if status == "ready" else {"status"}),
                          "result availability schema is not closed")
            if status == "pending":
                return self._answer("waiting", "terminal executor evidence is not yet available", request)
            outcomes = receipt["outcomes"] if status == "ready" else {
                suite: "missing" for suite in request["selection"]["suites"]}
            reference = receipt["reference"] if status == "ready" else f"missing:{request['id']}"
            self._persist("result", {"request_id": request["id"], "run": executor,
                                    "target": request["target"], "policy": request["policy"],
                                    "outcomes": outcomes, "reference": reference, "terminal": True})
        self._persist("advance", {"request_id": request["id"]})
        return None

    def reconcile(self, *, explicit=None, resume=None, allow_execution=True):
        """At most one execution action; no loops chasing changing main.

explicit is a complete T3 node/candidate request authenticated by the caller;
its caller-provided stable ID makes redelivery idempotent. resume is an explicit
{suites,reason,id} command, journal-id fenced so redelivery cannot reset budgets.
Report retries only read state.results; they never call this method to re-test.
allow_execution=False is settlement-only: it also forbids recovering a live
same-run claim into execution, not just creating new admissions.
"""
        self._guard()
        batch.require(type(allow_execution) is bool, "execution authorization must be boolean")
        events = self.journal.load()
        latest = self.inputs.refresh()
        self.policy = self.inputs.policy_at(self.inputs.control_sha)
        self.state = self._replay(events)
        if self.state["pending"] != latest:
            prior = self.state["pending"]
            self._persist("observe", {"target": latest,
                                      "descends_pending": prior is None or self.inputs.ancestor(prior, latest)})
        if explicit is not None:
            batch.require(isinstance(explicit, dict) and "control" in explicit,
                          "explicit request lacks a frozen control identity")
            policy = self.inputs.policy_at(explicit["control"])
            self._persist("enqueue", explicit, policy)
        if resume is not None:
            batch.require(isinstance(resume, dict) and set(resume) == {"id", "suites", "reason"}
                          and isinstance(resume["id"], str) and bool(resume["id"]), "resume needs stable command identity")
            command = {"id": "resume:" + resume["id"], "epoch": self.state["epoch"],
                       "generation": self.state["generation"], "type": "resume",
                       "data": {k: resume[k] for k in ("suites", "reason")}}
            existing = next((e for e in events if e["id"] == command["id"]), None)
            if existing:
                batch.require(existing["data"] == command["data"], "resume identity reused with different command")
            else:
                expected = batch.reduce(self.state, command, self.policy)
                self.state = self._replay(self.journal.append(command))
                batch.require(self.state == expected, "resume was not durably committed")
        waiting = self._settle_active(allow_execution)
        if waiting is not None:
            return waiting
        if not allow_execution:
            return self._answer("idle", "settlement-only; no execution authorized")
        if self.state["blocked"]:
            return self._answer("waiting", "admission explicitly blocked")
        # Completion-to-new-admission boundary observes main again, not the
        # event payload or the earlier pre-result snapshot.
        latest = self.inputs.refresh()
        if self.state["pending"] != latest:
            self._persist("observe", {"target": latest,
                                      "descends_pending": self.inputs.ancestor(self.state["pending"], latest)})
        if self.state["queue"]:
            request = self.state["requests"][self.state["queue"][0]]
            policy = self.inputs.policy_at(request["control"])
        else:
            base = self.state["processed"]
            if base == latest and not self.state["recovery_requested"]:
                return self._answer("idle", "no main changes or explicit recovery")
            kind = "bootstrap" if base is None else "auto"
            if base is None:
                selection = test_scope._selection(self.policy, self.policy.suite_ids, ["bootstrap requires full"])
            elif base == latest:
                selection = test_scope._selection(self.policy, [], ["explicit debt recovery without new changes"])
            else:
                selection = self.inputs.interval_selection(base, latest, self.policy)
            selection = batch.required_selection(self.state, self.policy, selection)
            request = batch.make_request(self.policy, request_id=f"batch:{self.state['epoch']}:{self.state['generation']}",
                kind=kind, base_sha=base, target_sha=latest, control_sha=self.inputs.control_sha,
                selection=selection, origin_run=self.run)
            policy = self.policy
        self.inputs.verify_target(request["target"])
        old_terminal = self.old_runs_terminal() if self.state["processed"] is None else True
        if old_terminal is not True:
            return self._answer("waiting", "old controlled executions not confirmed terminal")
        # A completion-only workflow must not admit work into its already dead
        # executor identity; the invoking controller run itself must be live.
        if self.run_state(deepcopy(self.run)) != "running":
            return self._answer("waiting", "current controller run is not authenticated running")
        ancestor = request["base"] is None or self.inputs.ancestor(request["base"], request["target"])
        self._persist("admit", {"request": request, "executor_run": self.run,
                               "history_complete": True, "ancestor": ancestor,
                               "old_runs_terminal": old_terminal}, policy)
        self._persist("claim", {"request_id": request["id"], "run": self.run})
        return self._answer("execute" if request["selection"]["suites"] else "idle",
                            "new durable claim; none waits for real executor completion", request)
