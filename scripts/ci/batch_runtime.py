#!/usr/bin/env python3
"""Real short-lock controller runtime. No dispatch, report writes or auto-init.

The workflow owns the lock; its sentinel is a wiring assertion, not a GitHub
lock attestation. Shared repository-controlled Actions bot trust is explicit.
Remote initialization and all scheduler writes require a trusted main workflow.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import zipfile
import zlib

import batch_controller
import batch_execution
from batch_evidence_validation import (PREFIX, PRODUCER_JOB, ALIASES, JOB_NAMES, EXECUTION_SOURCES,
                                       dependencies, producer_uploaded, validate_bundle, validate_job_observations)
import batch_github_journal as storage
import batch_verdict
import change_scope
import incremental_batch as batch
from incremental_batch_journal import IssueBodyAnchor, Journal
from review_merge_map_reader import MergeMapReader
import self_test
from self_test_report import RetryBudget, UrllibGitHubApi, with_retry
import time
import test_scope

SCHEMA = "lmdj.ci-batch-runtime.v1"
WORKFLOW = ".github/workflows/self-test-report.yml"
CONTROLLER_JOB = "Incremental batch controller"
EMPTY_TEMPLATE = "<!-- lmdj-ci-journal-uninitialized-v1 -->\n"
REFERENCE_PREFIX = "batch-verdict-v1:zlib-base64:"
MAX_DOCUMENT = 4000000
# The failure sentence a stalled controller prints: long enough for a closed
# `why:`/`remedy:` pair, short enough that no payload can ride along.
DIAGNOSTIC_LIMIT = 500
MAX_REFERENCE = 40000
ARTIFACT_RETENTION = timedelta(days=30)


def compatible_sources(git, frozen_control, executor_control):
    """Compare immutable workflow data, never execute historical Python.

Caller independently proves both controls belong to actual main history. The
closed source set covers this caller and every reusable product workflow.
"""
    batch.exact_sha(frozen_control)
    batch.exact_sha(executor_control)
    return all(git("show", f"{frozen_control}:{path}") == git("show", f"{executor_control}:{path}")
               for path in EXECUTION_SOURCES)


class EvidenceExpired(batch.BatchError):
    pass


class InvalidEvidence(batch.BatchError):
    pass


def parse_bundle(raw, filenames):
    """Pure bytes boundary; only this layer converts permanent content errors."""
    try:
        require(isinstance(raw, bytes) and len(raw) <= MAX_DOCUMENT * len(filenames), "artifact download exceeds budget")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            require(len(entries) == len(filenames) and {e.filename for e in entries} == set(filenames), "unsafe or unexpected artifact entries")
            require(all(e.file_size <= MAX_DOCUMENT and not e.is_dir() and (e.external_attr >> 16) & 0o170000 != 0o120000
                        for e in entries), "artifact entry exceeds budget or is a symlink")
            return {entry.filename: strict_json(archive.read(entry)) for entry in entries}
    except (ValueError, TypeError, KeyError, RuntimeError, zipfile.BadZipFile, zlib.error, NotImplementedError):
        raise InvalidEvidence("why: downloaded artifact content is not acceptable evidence; remedy: inspect exact-run artifact and retain missing coverage") from None


def require(condition, why):
    batch.require(condition, why, "stop admission and reconcile exact trusted run, journal and artifact identities")


def strict_json(raw):
    require(isinstance(raw, (str, bytes)) and len(raw.encode() if isinstance(raw, str) else raw) <= MAX_DOCUMENT,
            "JSON exceeds bounded document budget")
    return json.loads(raw, object_pairs_hook=change_scope.reject_duplicates,
                      parse_constant=lambda _: require(False, "nonfinite JSON"))


def encode_reference(document):
    raw = self_test.canonical_json(document).encode()
    require(len(raw) <= MAX_DOCUMENT, "durable verdict exceeds raw budget")
    reference = REFERENCE_PREFIX + base64.b64encode(zlib.compress(raw, 9)).decode()
    require(len(reference) <= MAX_REFERENCE, "durable verdict exceeds journal budget")
    return reference


def decode_reference(reference):
    require(isinstance(reference, str) and reference.startswith(REFERENCE_PREFIX)
            and len(reference) <= MAX_REFERENCE, "unsupported durable verdict reference")
    compressed = base64.b64decode(reference[len(REFERENCE_PREFIX):], validate=True)
    inflater = zlib.decompressobj()
    raw = inflater.decompress(compressed, MAX_DOCUMENT + 1)
    require(len(raw) <= MAX_DOCUMENT and inflater.eof and not inflater.unused_data
            and not inflater.unconsumed_tail, "oversized or incomplete durable verdict")
    return strict_json(raw)


class Runtime:
    # Fixed by trusted code, never dispatch/config input. Other journal users
    # can reuse authentication without accepting this scheduler's producers.
    workflow = WORKFLOW
    controller_job = CONTROLLER_JOB

    def __init__(self, config, *, root, environment=None, api=None):
        require(isinstance(config, dict) and set(config) == {
            "repository", "issue_number", "issue_node_id", "bot_node_id", "workflow_id", "epoch"}, "invalid runtime config")
        self.config, self.root = deepcopy(config), Path(root)
        self._journal = None
        self.env = dict(os.environ if environment is None else environment)
        require(config["repository"] == self.env.get("GITHUB_REPOSITORY"), "repository differs from workflow context")
        require(self.env.get("GITHUB_REF") == "refs/heads/main", "runtime only accepts main workflow context")
        self.control = batch.exact_sha(self.env.get("GITHUB_SHA"))
        require(self.env.get("GITHUB_RUN_ID", "").isdigit() and self.env.get("GITHUB_RUN_ATTEMPT") == "1",
                "runtime requires a fresh first-attempt run")
        self.current = batch.identity({"run_id": int(self.env["GITHUB_RUN_ID"]), "attempt": 1})
        batch.new_state(config["epoch"])
        self.api = api if api is not None else UrllibGitHubApi(config["repository"], self.env.get("GITHUB_TOKEN", ""))
        self.retry_budget = RetryBudget()
        self.clock = time.time
        self.writer = {"repository": config["repository"], "issue_number": config["issue_number"],
                       "run_id": self.current["run_id"], "run_attempt": 1, "control_sha": self.control,
                       "workflow_path": self.workflow, "workflow_id": config["workflow_id"], "job_name": self.controller_job}
        self.transport = storage.GitHubJournalTransport(repository=config["repository"],
            issue_number=config["issue_number"], issue_node_id=config["issue_node_id"], bot_node_id=config["bot_node_id"],
            workflows={self.workflow: config["workflow_id"]}, writer=self.writer, api=self.api,
            lock_held=self.lock_held, retry_budget=self.retry_budget, clock=self.clock)
        self.inputs = batch_controller.GitInputs(self.root, self.control, self.read_main)
        self.inputs.advice = self.advice
        self.advice_diagnostics = []

    def advice(self, interval):
        """Read already authenticated merge-map producers; no PR permission."""
        try:
            repository = self.call("GET", self.repo(""))
            workflow = self.call("GET", self.repo("/actions/workflows/pr-review.yml"))
            require(isinstance(repository, dict) and storage.positive(repository.get("id"))
                    and repository.get("full_name") == self.config["repository"], "mapping repository identity is unavailable")
            require(isinstance(workflow, dict) and storage.positive(workflow.get("id"))
                    and workflow.get("path") == ".github/workflows/pr-review.yml", "mapping producer workflow identity is unavailable")
            reader = MergeMapReader(self.config["repository"], repository["id"], workflow["id"], self.inputs,
                lambda path: self.call("GET", path),
                lambda artifact: self.call("GET", self.repo(f"/actions/artifacts/{artifact}/zip"), raw=True))
            answer = reader(interval)
            self.advice_diagnostics = reader.diagnostics
            return answer
        except Exception:
            self.advice_diagnostics = ["why: mapping identity unavailable; remedy: use the independently verified Git and policy floor and restore authenticated advice"]
            return {"complete": False, "labels": []}

    def lock_held(self):
        return self.env.get("BATCH_WRITER_LOCK") == "self-test-report"

    def call(self, method, path, body=None, *, raw=False):
        try:
            call = lambda: self.api._request(method, path, body=body, raw=raw)
            # Writer-lock GETs still wait for a known primary reset; they must
            # not sleep on secondary/transport throttling. A later reset stays
            # unknown for the next health tick, never "controller not live".
            if method == "GET":
                return with_retry(call, sleep=time.sleep, clock=self.clock,
                                  budget=self.retry_budget, secondary=not self.lock_held())
            return call()
        except Exception as error:
            raise batch.BatchError("why: runtime API unavailable or write outcome unknown; remedy: reconcile without replaying the write") from error

    def repo(self, suffix):
        return "/repos/" + self.config["repository"] + suffix

    def git(self, *args):
        return self.inputs._git(*args)

    def pages(self, suffix, key):
        rows, seen, total = [], set(), None
        for page in range(1, 101):
            document = self.call("GET", self.repo(suffix + ("&" if "?" in suffix else "?") + f"per_page=100&page={page}"))
            require(isinstance(document, dict) and type(document.get("total_count")) is int
                    and document["total_count"] >= 0 and isinstance(document.get(key), list), "incomplete API inventory")
            require(total in (None, document["total_count"]), "API inventory changed during paging")
            total, items = document["total_count"], document[key]
            require(len(items) <= 100, "API page exceeds requested size")
            for item in items:
                require(isinstance(item, dict) and storage.positive(item.get("id")) and item["id"] not in seen,
                        "duplicate or invalid inventory identity")
                seen.add(item["id"])
                rows.append(item)
            require(len(rows) <= total, "API inventory exceeds declared total")
            if len(rows) == total:
                return rows
            require(bool(items), "API pagination stopped before complete inventory")
        require(False, "API pagination budget exceeded")

    def read_main(self):
        ref = self.call("GET", self.repo("/git/ref/heads/main"))
        require(isinstance(ref, dict) and isinstance(ref.get("object"), dict)
                and ref["object"].get("type") == "commit", "main ref is not a commit")
        sha = batch.exact_sha(ref["object"].get("sha"))
        token = self.env.get("GITHUB_TOKEN", "")
        require(bool(token), "Git fetch credential is missing")
        credential = base64.b64encode(("x-access-token:" + token).encode()).decode()
        self.git("-c", "http.extraheader=AUTHORIZATION: basic " + credential,
                 "fetch", "--no-tags", "origin", sha)
        return sha

    def get_run(self, run_id, attempt):
        identity = batch.identity({"run_id": run_id, "attempt": attempt})
        document = self.call("GET", self.repo(f"/actions/runs/{run_id}/attempts/{attempt}"))
        require(isinstance(document, dict) and type(document.get("id")) is int and document["id"] == identity["run_id"]
                and type(document.get("run_attempt")) is int and document["run_attempt"] == 1
                and type(document.get("workflow_id")) is int and document["workflow_id"] == self.config["workflow_id"] and document.get("path") == self.workflow
                and document.get("head_branch") == "main" and document.get("event") in {"push", "workflow_dispatch", "workflow_run", "schedule"}
                and isinstance(document.get("repository"), dict) and document["repository"].get("full_name") == self.config["repository"]
                and isinstance(document.get("head_repository"), dict) and document["head_repository"].get("full_name") == self.config["repository"],
                "executor run provenance differs")
        batch.exact_sha(document.get("head_sha"))
        return document

    def run_state(self, identity):
        run = self.get_run(identity["run_id"], identity["attempt"])
        status = run.get("status")
        if status == "completed":
            require(run.get("conclusion") in {"success", "failure", "cancelled", "skipped", "timed_out", "neutral", "action_required", "startup_failure", "stale"},
                    "terminal run has no recognized conclusion")
            return "terminal"
        if status in {"queued", "in_progress", "waiting", "requested", "pending"}:
            return "running"
        return "unknown"

    def authenticate_current(self):
        # Internal failure location only; never evidence or execution authority.
        self.diagnostic_stage = "auth-lock"
        require(self.lock_held(), "runtime lacks short writer lock")
        self.diagnostic_stage = "auth-checkout"
        require(self.git("rev-parse", "HEAD").decode().strip() == self.control, "checkout is not frozen control")
        self.diagnostic_stage = "auth-main-refresh"
        self.inputs.refresh()
        self.diagnostic_stage = "auth-current-run"
        require(self.run_state(self.current) == "running", "current controller run is not live")
        self.diagnostic_stage = "auth-journal-writer"
        self.transport._writer(self.writer)
        self.diagnostic_stage = "auth-current-job"
        jobs = self.pages(f"/actions/runs/{self.current['run_id']}/attempts/1/jobs", "jobs")
        own = [j for j in jobs if j.get("name") == self.controller_job]
        require(len(own) == 1 and own[0].get("status") == "in_progress", "current controller job is not active")
        self.diagnostic_stage = None

    def initialize(self):
        self.authenticate_current()
        owner, name = self.config["repository"].split("/")
        query = "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){nameWithOwner issue(number:$number){id number body state comments{totalCount}}}}"
        document = self.call("POST", "/graphql", {"query": query, "variables": {
            "owner": owner, "name": name, "number": self.config["issue_number"]}})
        require(isinstance(document, dict) and not document.get("errors"), "initial Issue metadata unavailable")
        repository = document.get("data", {}).get("repository")
        require(isinstance(repository, dict) and repository.get("nameWithOwner") == self.config["repository"], "initial repository mismatch")
        issue = repository.get("issue")
        require(isinstance(issue, dict) and issue.get("id") == self.config["issue_node_id"]
                and type(issue.get("number")) is int and issue["number"] == self.config["issue_number"]
                and issue.get("state") == "OPEN" and issue.get("body") == EMPTY_TEMPLATE
                and isinstance(issue.get("comments"), dict) and type(issue["comments"].get("totalCount")) is int
                and issue["comments"]["totalCount"] == 0, "initial Issue is not the exact empty reserved object")
        payload = {"schema": storage.SCHEMA, "kind": "checkpoint", "writer": self.writer,
                   "payload": {"head": None, "pending": None}}
        self.call("PATCH", self.repo(f"/issues/{self.config['issue_number']}"), {"body": self_test.canonical_json(payload)})
        checkpoint = self.transport.read_body(self.config["issue_number"])
        require(checkpoint["checkpoint"] == payload["payload"], "initial checkpoint was not verified")
        # Also detects a concurrent comment without inventing an empty history.
        require(self.journal().load() == [], "initial journal is not empty")
        return self.answer("initialized", "empty journal only; no tested baseline", None, None)

    def journal(self):
        # One instance per process: its verified history is what lets the up to
        # four appends of a single reconcile authenticate the complete journal
        # once instead of once per append. The short writer lock still
        # serializes writers, and any anchor-head mismatch replays in full.
        if self._journal is None:
            number = self.config["issue_number"]
            anchor = IssueBodyAnchor(number, self.transport, self.transport.authenticate, self.lock_held)
            self._journal = Journal(number, self.transport, anchor, self.transport.authenticate, self.lock_held)
        return self._journal

    def old_runs_terminal(self):
        # Query all not-completed states, not a bounded recent completed window.
        for workflow in ("ci.yml", "self-test-report.yml"):
            for status in ("queued", "in_progress", "waiting", "requested", "pending"):
                runs = self.pages(f"/actions/workflows/{workflow}/runs?branch=main&status={status}", "workflow_runs")
                for run in runs:
                    if workflow == "self-test-report.yml" and run["id"] == self.current["run_id"]:
                        continue  # This light controller has not admitted work yet.
                    if workflow == "self-test-report.yml" and self.unadmitted_wakeup(run):
                        continue
                    if run.get("status") != "completed":
                        return False
        return True

    def unadmitted_wakeup(self, listed):
        """Only a never-started controller under this same lock can be ignored.

Same workflow bytes plus this caller's real external lock establish ordering.
A prior completed/in-progress controller, extra jobs, rerun, changed source or
ambiguous inventory is potentially an executor and must hold bootstrap back.
"""
        run = self.get_run(listed["id"], 1)
        if type(listed.get("run_attempt")) is not int or listed["run_attempt"] != 1 \
                or run.get("status") not in {"queued", "requested", "pending", "waiting", "in_progress"}:
            return False
        self.inputs.verify_target(run["head_sha"])
        if self.git("show", f"{run['head_sha']}:{WORKFLOW}") != self.git("show", f"{self.control}:{WORKFLOW}"):
            return False
        jobs = self.pages(f"/actions/runs/{run['id']}/attempts/1/jobs", "jobs")
        if not jobs:
            return run["status"] != "in_progress"
        if not all(type(j.get("run_id")) is int and j["run_id"] == run["id"]
                   and type(j.get("run_attempt")) is int and j["run_attempt"] == 1 for j in jobs):
            return False
        controllers = [j for j in jobs if j.get("name") == CONTROLLER_JOB]
        if len(controllers) != 1:
            return False
        controller = controllers[0]
        if any(j is not controller and (j.get("status") != "completed" or j.get("conclusion") != "skipped") for j in jobs):
            return False
        return controller.get("status") == "queued" and controller.get("started_at", "missing") is None \
            and controller.get("completed_at", "missing") is None

    def upload_retention_elapsed(self, producer):
        step = next(s for s in producer["steps"] if s["name"] == "Retain scoped verdict and raw needs")
        timestamp = step.get("completed_at") or producer.get("completed_at")
        if not isinstance(timestamp, str):
            return False
        try:
            ended = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return False
        return ended.tzinfo is not None and datetime.now(timezone.utc) >= ended + ARTIFACT_RETENTION

    def artifact_bundle(self, run, name, filenames):
        artifacts = self.pages(f"/actions/runs/{run['id']}/artifacts", "artifacts")
        matches = [a for a in artifacts if a.get("name") == name]
        require(len(matches) <= 1, "ambiguous exact-attempt artifact")
        if not matches:
            return None
        artifact = matches[0]
        require(type(artifact.get("expired")) is bool, "artifact expiry metadata missing")
        if artifact["expired"]:
            raise EvidenceExpired("why: exact artifact expired; remedy: retain missing coverage, never reconstruct a pass")
        raw = self.call("GET", self.repo(f"/actions/artifacts/{artifact['id']}/zip"), raw=True)
        return parse_bundle(raw, filenames)

    def result_for(self, request, executor):
        run = self.get_run(executor["run_id"], executor["attempt"])
        if run.get("status") != "completed":
            return {"status": "pending"}
        self.inputs.verify_target(run["head_sha"])
        if not compatible_sources(self.git, request["control"], run["head_sha"]):
            # The callee rejects this before heavy jobs. A genuinely terminal
            # incompatible request has no accepted coverage, but must release
            # its queue slot; it is not an API-unknown infinite wait.
            return {"status": "missing"}
        self.inputs.verify_target(request["target"])
        policy = self.inputs.policy_at(request["control"])
        if (request["kind"] == "candidate"
                and self.inputs.policy_at(run["head_sha"]).digest != request["policy"]):
            # Same terminal missing/advance path as workflow incompatibility.
            # A policy read/authentication error remains an error, not missing.
            return {"status": "missing"}
        jobs = self.pages(f"/actions/runs/{run['id']}/attempts/1/jobs", "jobs")
        require(all(type(j.get("run_id")) is int and j["run_id"] == run["id"] and type(j.get("run_attempt")) is int and j["run_attempt"] == 1
                    and j.get("status") == "completed" for j in jobs), "executor jobs are not all terminal in this attempt")
        producers = [j for j in jobs if j.get("name") == PRODUCER_JOB]
        require(len(producers) <= 1, "ambiguous scoped verdict producer")
        name = f"batch-verdict-{request['target']}-{run['id']}-1"
        try:
            bundle = self.artifact_bundle(run, name, ("verdict.json", "execution.json", "needs.json"))
        except EvidenceExpired:
            return {"status": "missing"}
        except InvalidEvidence:
            require(len(producers) == 1 and producers[0].get("conclusion") in {"success", "failure"}
                    and producer_uploaded(producers[0]), "invalid artifact has no authenticated successful judge and upload")
            print("why: authenticated artifact has invalid content; remedy: inspect the retained exact-run artifact; coverage remains missing")
            return {"status": "missing"}
        if bundle is None:
            # A successful upload may be temporarily invisible: never declare
            # it absent from a read race. Explicit expiry is handled below too.
            if producers and producer_uploaded(producers[0]) and not self.upload_retention_elapsed(producers[0]):
                return {"status": "pending"}
            return {"status": "missing"}
        require(len(producers) == 1 and producers[0].get("conclusion") in {"success", "failure"}
                and producer_uploaded(producers[0]), "artifact has no authenticated successful judge and upload")
        try:
            checked, identity = self.validate_bundle(bundle, request, run, policy)
        except (ValueError, TypeError, KeyError):
            print("why: authenticated artifact contradicts frozen evidence; remedy: inspect the retained exact-run artifact; coverage remains missing")
            return {"status": "missing"}
        validate_job_observations(checked, producers[0], jobs)
        reference = encode_reference(checked)
        return {"status": "ready", "outcomes": batch_verdict.scheduler_outcomes(checked, policy, identity, request["selection"]),
                "reference": reference}

    def validate_bundle(self, bundle, request, run, policy):
        """Pure content validation; no API, Git, journal or downloads here."""
        return validate_bundle(bundle, request, run, policy)

    def answer(self, action, reason, request, state):
        return {"schema": SCHEMA, "action": action, "reason": reason, "request": request,
                "executor": deepcopy(self.current), "state": state}

    def reconcile_pending(self, command):
        """Operator-audited drain of a stranded pending intent; never execution.

        The journal performs the exact-digest binding and the complete
        authenticated absence proof; this layer only closes the command
        schema and authenticates the writer. The answer action can never be
        'execute': the dropped event is re-derived by the next ordinary
        reconcile from actual run state, not replayed here."""
        require(isinstance(command, dict) and set(command) == {"pending_digest"}
                and isinstance(command["pending_digest"], str) and len(command["pending_digest"]) == 64
                and all(character in "0123456789abcdef" for character in command["pending_digest"]),
                "reconcile-pending requires a closed audited pending digest")
        self.authenticate_current()
        self.journal().reconcile_pending(command["pending_digest"])
        return self.answer("reconciled-pending",
                           "stranded pending cleared after exact absence proof; ordinary reconcile re-derives the dropped event",
                           None, None)

    def reconcile(self, *, execute=False, explicit=None, resume=None):
        if resume is not None:
            require(execute is False and explicit is None, "resume cannot authorize execution or an explicit batch")
            require(isinstance(resume, dict) and set(resume) == {'id', 'suites', 'reason'}
                    and all(isinstance(resume[key], str) and bool(resume[key].strip()) for key in ('id', 'reason')),
                    "resume requires a closed command with nonempty id and reason")
            suites = resume['suites']
            require(isinstance(suites, list) and bool(suites)
                    and all(isinstance(suite, str) and bool(suite.strip()) for suite in suites)
                    and len(suites) == len(set(suites)), "resume requires nonempty unique debt suites")
        self.authenticate_current()
        journal = self.journal()
        request = None
        if explicit is not None:
            require(execute and isinstance(explicit, dict) and set(explicit) == {"id", "kind", "target"}
                    and explicit["kind"] in {"node", "candidate"}, "invalid explicit execution command")
            policy = self.inputs.policy_at(self.control)
            request = batch.make_request(policy, request_id=explicit["id"], kind=explicit["kind"], base_sha=None,
                target_sha=explicit["target"], control_sha=self.control,
                selection=test_scope._selection(policy, policy.suite_ids, ["explicit full request"]), origin_run=self.current)
            # A new first-attempt workflow can redeliver a queued command.
            # Its original frozen control/origin are journal truth, not replaced
            # with the retry's run identity. Conflicting command reuse is fatal.
            for event in journal.load():
                if event.get("type") not in {"enqueue", "admit"}:
                    continue
                prior = event["data"] if event["type"] == "enqueue" else event["data"]["request"]
                if prior["id"] == explicit["id"]:
                    require(prior["kind"] == explicit["kind"] and prior["target"] == explicit["target"],
                            "explicit command identity reused for a different request")
                    request = prior
        controller = batch_controller.Controller(journal, self.inputs, self.current,
            run_state=self.run_state, result_for=self.result_for, old_runs_terminal=self.old_runs_terminal,
            lock_held=self.lock_held, epoch=self.config["epoch"])
        if resume is not None:
            # Preflight and replay stay inside the same externally held lock.
            # Do not use settlement-only reconcile as the preflight: even that
            # mode may settle a terminal active executor and clear passed debt.
            events = journal.load()
            controller.policy = self.inputs.policy_at(self.control)
            state = controller._replay(events)
            require(state['active'] is None, "resume requires no active executor; settle separately before resume")
            existing = next((event for event in events if event['id'] == 'resume:' + resume['id']), None)
            if existing is None:
                require(all(suite in state['debts'] for suite in resume['suites']), "resume names unknown debt")
            else:
                require(existing['data'] == {key: resume[key] for key in ('suites', 'reason')},
                        "resume identity reused with different command")
        answer = controller.reconcile(explicit=request, resume=resume, allow_execution=execute)
        return self.answer(answer["action"], answer["reason"], answer["request"], answer["state"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "reconcile", "settle", "resume", "reconcile-pending"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args(argv)
    runtime = None
    try:
        require(not args.output.exists(), "output already exists; a stale execute action must never be reused")
        require(args.request is None or args.command in {'reconcile', 'resume', 'reconcile-pending'},
                "request requires reconcile, resume or reconcile-pending mode")
        require(args.command != 'resume' or args.request is not None, "resume requires its explicit command file")
        require(args.command != 'reconcile-pending' or args.request is not None,
                "reconcile-pending requires the audited pending digest file")
        runtime = Runtime(strict_json(args.config.read_bytes()), root=args.root)
        command = strict_json(args.request.read_bytes()) if args.request else None
        require(args.command != 'resume' or isinstance(command, dict), "resume requires an explicit command object")
        if args.command == "init":
            answer = runtime.initialize()
        elif args.command == "reconcile-pending":
            answer = runtime.reconcile_pending(command)
        else:
            answer = runtime.reconcile(
                execute=args.command == "reconcile", explicit=command if args.command == 'reconcile' else None,
                resume=command if args.command == 'resume' else None)
        with args.output.open("x") as stream:
            stream.write(self_test.canonical_json(answer) + "\n")
    except Exception as error:
        # The remedy tells an operator where to look; without the failure
        # itself they cannot look anywhere. A stalled controller reported only
        # this sentence, and the cause had to be guessed from the journal
        # (#1570 investigation, runs 35533247694 and 35535446673).
        #
        # Only this repository's own refusals carry a message here: a
        # `BatchError` or `JournalBlocked` is built from a `why:`/`remedy:`
        # pair written in `scripts/ci/`, and neither interpolates a response
        # body or a journal payload. Anything else is named by its type alone,
        # because its message may quote whatever a server or a parser handed
        # back. The stage is one of the fixed names the runtime sets around
        # each authentication step. Both are bounded.
        stage = getattr(runtime, "diagnostic_stage", None)
        closed = isinstance(error, (batch.BatchError, storage.JournalBlocked))
        detail = (f"{type(error).__name__}: {error}" if closed else type(error).__name__)[:DIAGNOSTIC_LIMIT]
        print(f"why: batch runtime did not commit an authenticated action ({detail})"
              + (f"; stage: {stage}" if stage else "")
              + "; remedy: inspect exact journal/run identities and reconcile without replaying execution")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
