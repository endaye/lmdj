#!/usr/bin/env python3
"""Bounded PR Review discovery through the existing authenticated Issue journal.

Queues verified report payloads only. Never executes products, initializes an
Issue, sends a business POST, edits scheduler state or treats hashes as identity.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode

import batch_runtime
import report_outbox
import review_discovery as protocol
import review_failure_report as collector
import self_test_report as reporting

CONFIG_PATH = "scripts/ci/review_discovery_storage.json"
MAX_WINDOW_RUNS = 200  # Leaves headroom under the authenticated journal body limit.
MAX_ATTEMPTS = 64


def require(ok, why):
    if not ok:
        raise ValueError(f"why: {why}; remedy: reconcile authenticated discovery inventory and fixed storage; no scheduler or business POST retry is authorized")


def utc(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class EvidenceReads:
    """Record exactly the read-only consumer calls after its own validation.

    Delegates the existing consumer; no copied source/receipt trust decisions.
    """
    def __init__(self, api):
        self.api, self.reads, self.jobs, self.artifacts = api, [], None, None

    def _record(self, name, arguments, value):
        encoded = value if isinstance(value, bytes) else protocol.canonical(value)
        import hashlib
        self.reads.append({"method": name, "arguments": arguments,
                           "digest": hashlib.sha256(encoded).hexdigest()})
        return value

    def _request(self, method, path):
        require(method == "GET", "review evidence consumer attempted a write")
        value = self.api._request(method, path)
        if "/artifacts?" in path:
            self.artifacts = value
        return self._record("GET", [path], value)

    def list_jobs(self, run_id, attempt):
        self.jobs = self.api.list_jobs(run_id, attempt)
        return self._record("jobs", [run_id, attempt], self.jobs)

    def compare(self, base, head):
        return self._record("compare", [base, head], self.api.compare(base, head))

    def download_artifact(self, artifact_id):
        return self._record("artifact", [artifact_id], self.api.download_artifact(artifact_id))


class DiscoveryRuntime:
    def __init__(self, root, environment=None, api=None):
        # Import only the independently owned entry's canonical fixed loader.
        from incremental_entry import load_storage
        self.root = Path(root)
        self.env = dict(os.environ if environment is None else environment)
        shared = load_storage(self.root, self.env)
        control = self.env.get("GITHUB_SHA")
        raw = batch_runtime.batch_execution.git(self.root, "show", f"{control}:{CONFIG_PATH}")
        config = batch_runtime.strict_json(raw)
        protocol.closed(config, {"storage", "source_floor", "review_workflow_id"})
        self.config = config
        self.runtime = batch_runtime.Runtime(config["storage"], root=self.root, environment=self.env, api=api)
        self.outbox_runtime = batch_runtime.Runtime(shared["outbox"], root=self.root, environment=self.env, api=self.runtime.api)
        a, b, scheduler = config["storage"], shared["outbox"], shared["scheduler"]
        require(all(a[k] == b[k] == scheduler[k] for k in ("repository", "workflow_id", "bot_node_id")), "discovery authority differs from existing controller")
        for key in ("issue_number", "issue_node_id", "epoch"):
            require(len({a[key], b[key], scheduler[key]}) == 3, "discovery storage aliases scheduler or outbox")
        self.state_config = {"epoch": a["epoch"], "repository": a["repository"],
                             "workflow_id": config["review_workflow_id"], "source_floor": config["source_floor"]}
        protocol.new_state(**self.state_config)
        self.api, self.repository = self.runtime.api, a["repository"]
        self.repository_id = None
        self.journal = self.runtime.journal()
        self.outbox = report_outbox.Outbox(self.outbox_runtime.journal(), self.outbox_runtime.lock_held, b["epoch"])

    def load(self):
        self.state = protocol.replay(self.state_config, self.journal.load())
        return self.state

    def persist(self, kind, data):
        event = {"id": f"discovery:{self.state['epoch']}:{self.state['generation']}",
                 "epoch": self.state["epoch"], "generation": self.state["generation"], "type": kind, "data": data}
        expected = protocol.reduce(self.state, event)
        self.journal.append(event)
        require(protocol.canonical(self.load()) == protocol.canonical(expected), "discovery append did not confirm exact state")

    def get(self, suffix):
        return self.api._request("GET", f"/repos/{self.repository}{suffix}")

    def metadata(self, value, *, run_id=None, attempt=None):
        if self.repository_id is None:
            repository = self.get("")
            require(isinstance(repository, dict) and repository.get("full_name") == self.repository
                    and type(repository.get("id")) is int and repository["id"] > 0, "fixed repository API identity is unavailable")
            self.repository_id = repository["id"]
        require(isinstance(value, dict) and value.get("workflow_id") == self.config["review_workflow_id"]
                and type(value.get("workflow_id")) is int and value.get("path") == collector.WORKFLOW
                and isinstance(value.get("repository"), dict)
                and value.get("repository", {}).get("full_name") == self.repository
                and type(value["repository"].get("id")) is int and value["repository"]["id"] == self.repository_id
                and value.get("event") in {"pull_request", "workflow_dispatch"}, "review metadata provenance differs")
        protocol.positive(value.get("id"))
        protocol.positive(value.get("run_attempt"))
        protocol.timestamp(value.get("created_at"))
        protocol.hex_value(value.get("head_sha"), 40)
        require(run_id is None or value["id"] == run_id, "review metadata run ID differs")
        require(attempt is None or value["run_attempt"] == attempt, "review metadata exact attempt differs")
        require(value.get("status") in {"queued", "in_progress", "waiting", "requested", "pending", "completed"}, "unknown review run state")
        return value

    def inventory(self, start, end):
        """Return complete immutable run identities or None for a dense window.

        Caller can subdivide before persisting. No partial page is committed.
        """
        query = {"created": start + ".." + utc(protocol.timestamp(end) - timedelta(seconds=1)), "per_page": 100}
        records, total, ids = [], None, set()
        page = 1
        while True:
            document = self.get(f"/actions/workflows/{self.config['review_workflow_id']}/runs?" + urlencode({**query, "page": page}))
            require(isinstance(document, dict) and type(document.get("total_count")) is int and document["total_count"] >= 0
                    and isinstance(document.get("workflow_runs"), list), "review inventory page is malformed")
            if document["total_count"] > MAX_WINDOW_RUNS:
                return None
            total = document["total_count"] if total is None else total
            require(document["total_count"] == total, "review inventory changed during pagination")
            values = document["workflow_runs"]
            require(len(values) <= 100, "review inventory page exceeds API page size")
            for value in values:
                self.metadata(value)
                require(start <= value["created_at"] < end and value["id"] not in ids, "review inventory has duplicate or out-of-window run")
                ids.add(value["id"])
                records.append({"identity": {"run_id": value["id"], "attempt": 1}, "created_at": value["created_at"]})
            require(len(records) <= total, "review inventory exceeds declared total")
            if len(records) == total:
                return sorted(records, key=lambda record: record["identity"]["run_id"])
            require(len(values) == 100, "review inventory is truncated before total_count")
            page += 1

    def scan_window(self, now):
        """At most one persisted inventory/gap window per invocation."""
        start = max([self.state["inventory_frontier"], *[w["end"] for w in self.state["windows"]],
                     *[g["end"] for g in self.state["gaps"]]])
        end = utc(min(protocol.timestamp(start) + timedelta(days=1), now - timedelta(minutes=2)))
        if end <= start:
            return
        while True:
            records = self.inventory(start, end)
            if records is not None:
                self.persist("inventory", {"start": start, "end": end, "runs": records,
                    "total_count": len(records), "inventory_digest": protocol.digest(records), "complete": True})
                return
            seconds = int((protocol.timestamp(end) - protocol.timestamp(start)).total_seconds())
            if seconds <= 1:
                self.persist("inventory-gap", {"start": start, "end": end,
                    "why": "review inventory exceeds bounded per-second capacity", "remedy": "independently recover this complete interval; never truncate it"})
                return
            end = utc(protocol.timestamp(start) + timedelta(seconds=seconds // 2))

    def disposition(self, ident, status, proof):
        prior = self.state["runs"][protocol.identity(ident)]
        if prior["status"] == status and protocol.canonical(prior["proof"]) == protocol.canonical(proof):
            return
        self.persist("disposition", {"identity": ident, "status": status, "proof": proof})

    def next_obligation(self):
        """Least recently registered/visited live obligation, from durable events.

        Reuse closed v1 records; terminal history never occupies this budget.
        New registrations enter behind older obligations, not ahead of retries.
        """
        order = {}
        for event in self.state['seen_events'].values():
            data, generation = event['data'], event['generation']
            if event['type'] == 'inventory':
                for record in data['runs']:
                    order[protocol.identity(record['identity'])] = generation
            elif event['type'] in {'attempt', 'disposition'}:
                order[protocol.identity(data['identity'])] = generation
        pending = [row for row in self.state['runs'].values() if row['status'] in protocol.UNRESOLVED]
        if not pending:
            return None
        row = min(pending, key=lambda row: (order[protocol.identity(row['identity'])],
                  row['identity']['run_id'], row['identity']['attempt']))
        return deepcopy(row['identity'])

    def rotate_obligation(self, ident):
        row = self.state['runs'][protocol.identity(ident)]
        if row['status'] in protocol.UNRESOLVED:
            # Even unchanged/unavailable/live evidence consumes its fair turn.
            # The original disposition/proof is retained, never made successful.
            self.persist('disposition', {key: deepcopy(row[key]) for key in ('identity', 'status', 'proof')})

    def process_attempt(self, run_id, attempt):
        ident = {"run_id": run_id, "attempt": attempt}
        prior = self.state["runs"][protocol.identity(ident)]
        if prior["status"] in protocol.TERMINAL:
            return
        evidence = None
        try:
            run = self.metadata(self.get(f"/actions/runs/{run_id}/attempts/{attempt}"), run_id=run_id, attempt=attempt)
            # Actions' exact-attempt endpoint can report a later creation time
            # even for attempt 1. Only the generic run timestamp owns inventory
            # windows; this timestamp neither rewrites that origin nor proves
            # source identity (the exact run/attempt and collector still do).
            require(protocol.timestamp(run["created_at"]) >= protocol.timestamp(prior["created_at"]),
                    "attempt creation precedes its inventoried run")
            if run["status"] != "completed":
                return  # Existing pending/unresolved obligation remains durable.
            evidence = EvidenceReads(self.api)
            report = collector.collect(evidence, self.repository, run_id, attempt)
        except Exception:
            inventory = evidence.artifacts if evidence else None
            if isinstance(inventory, dict) and isinstance(inventory.get("artifacts"), list) \
                    and type(inventory.get("total_count")) is int and inventory["total_count"] == len(inventory["artifacts"]):
                import re
                matches = [a for a in inventory["artifacts"] if isinstance(a, dict) and isinstance(a.get("name"), str)
                           and re.fullmatch(rf"pr-review-result-[0-9a-f]{{40}}-{run_id}-{attempt}", a["name"])
                           and a.get("workflow_run", {}).get("id") == run_id]
                if len(matches) == 1 and matches[0].get("expired") is True:
                    self.disposition(ident, "retention-lost", {"why": "exact review artifact is explicitly expired",
                        "remedy": "recover original authenticated receipt from retained evidence; expired is not a valid review"})
                    return
            if prior["status"] != "retention-lost":
                self.disposition(ident, "unresolved", {"why": "exact review source or receipt unavailable",
                    "remedy": "restore and authenticate the original attempt receipt; API errors are not absence or backend failure"})
            return
        proof = {"identity": ident, "control_sha": self.runtime.control, "receipt_digest": protocol.digest(evidence.reads)}
        if report is None:
            skipped = any(job.get("name") == "Review fallback" and job.get("conclusion") == "skipped" for job in evidence.jobs)
            self.disposition(ident, "closed-mapping" if skipped else "valid-review", proof)
            return
        state = self.outbox.load()
        key = protocol.digest({"key": report.key, "observation": report.observation})
        payload = report_outbox.freeze(report, reporting.DEFAULT_ASSIGNEE)
        if key not in state["deliveries"]:
            self.outbox._persist("queue", {"delivery": key, "payload": payload})
            state = self.outbox.load()
        require(protocol.canonical(state["deliveries"][key]["payload"]) == protocol.canonical(payload), "queued report differs from authenticated review")
        self.disposition(ident, "failure-queued", {**proof, "outbox_key": key})

    def observe_run(self, run_id):
        run = self.metadata(self.get(f"/actions/runs/{run_id}"), run_id=run_id)
        require(run["created_at"] == self.state["runs"][f"{run_id}/1"]["created_at"], "generic run creation time changed")
        require(run["run_attempt"] <= MAX_ATTEMPTS, "review attempt count exceeds bounded recovery")
        require(run["run_attempt"] >= max(record["identity"]["attempt"] for record in self.state["runs"].values()
                                          if record["identity"]["run_id"] == run_id), "generic latest attempt regressed")
        return run

    def register_attempts(self, run):
        run_id = run["id"]
        for attempt in range(2, run["run_attempt"] + 1):
            ident = {"run_id": run_id, "attempt": attempt}
            if protocol.identity(ident) not in self.state["runs"]:
                self.persist("attempt", {"identity": ident, "created_at": run["created_at"]})

    def run(self, limit=8, run_id=None, attempt=None, *, now=None):
        require(type(limit) is int and 1 <= limit <= 32, "discovery budget must be 1..32")
        require((run_id is None) == (attempt is None), "callback requires both exact run and attempt")
        if run_id is not None:
            protocol.positive(run_id)
            protocol.positive(attempt)
        self.runtime.authenticate_current()
        self.outbox_runtime.authenticate_current()
        self.runtime.inputs.verify_target(self.config["source_floor"]["control_sha"])
        workflow = self.get(f"/actions/workflows/{self.config['review_workflow_id']}")
        require(isinstance(workflow, dict) and type(workflow.get("id")) is int
                and workflow["id"] == self.config["review_workflow_id"] and workflow.get("path") == collector.WORKFLOW,
                "configured review workflow differs")
        self.load()
        now = now or datetime.now(timezone.utc)
        require(now.tzinfo is not None, "discovery clock lacks timezone")
        errors = []
        try:
            self.scan_window(now)
        except Exception:
            errors.append("inventory not committed; exact pages/source unavailable; retry without advancing frontier")
        if run_id is not None:
            require(f"{run_id}/1" in self.state["runs"], "callback run is outside inventoried history; recover its creation interval first")
            observed = self.observe_run(run_id)
            require(attempt <= observed["run_attempt"], "callback names an unobserved future attempt")
            self.register_attempts(observed)
            self.process_attempt(run_id, attempt)
        obligation = self.next_obligation()
        visited = set()
        if self.state["runs"] and self.state["metadata_scan"]["active"] is None:
            self.persist("metadata-start", {"round": self.state["metadata_scan"]["round"],
                "run_ids": sorted({r["identity"]["run_id"] for r in self.state["runs"].values()})})
        for _ in range(limit):
            scan = deepcopy(self.state["metadata_scan"])
            if scan["active"] is None:
                break
            index = scan["active"]["position"]
            number = scan["active"]["run_ids"][index]
            try:
                observed = self.observe_run(number)
                outcome = {"status": "observed", "created_at": observed["created_at"],
                           "latest_attempt": observed["run_attempt"], "receipt_digest": protocol.digest(observed)}
            except Exception:
                outcome = {"status": "unresolved", "why": "run metadata is not authenticated",
                           "remedy": "retry exact run metadata in the next frozen round; do not downgrade prior review"}
            if outcome["status"] == "observed":
                # Journal failures must escape, not become an API metadata error.
                self.register_attempts(observed)
            self.persist("metadata-result", {"round": scan["round"], "position": index, "run_id": number, "outcome": outcome})
            if outcome["status"] == "observed":
                for current in range(1, observed["run_attempt"] + 1):
                    self.process_attempt(number, current)
                    visited.add(f'{number}/{current}')
        if obligation is not None:
            key = protocol.identity(obligation)
            if key not in visited:
                try:
                    observed = self.observe_run(obligation['run_id'])
                except Exception:
                    observed = None  # Exact-attempt authentication still runs below.
                if observed is not None:
                    self.register_attempts(observed)
                self.process_attempt(obligation['run_id'], obligation['attempt'])
            self.rotate_obligation(obligation)
        inventory_pending = protocol.summary(self.state)["latest_inventory_end"] < utc(now - timedelta(minutes=2))
        return {"schema": "lmdj.ci-review-discovery-report.v1", "state": protocol.summary(self.state), "errors": errors,
                "inventory_pending": inventory_pending,
                "status": "incomplete" if errors or self.state["gaps"] or self.state["metadata_scan"]["errors"]
                or self.state["metadata_scan"]["active"] is not None or inventory_pending
                or protocol.summary(self.state)["unresolved"] else "inventoried-only"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--attempt", type=int)
    args = parser.parse_args(argv)
    try:
        result = DiscoveryRuntime(args.root).run(args.limit, args.run_id, args.attempt)
        with args.summary.open("a") as stream:
            stream.write("Review discovery (not scheduler execution):\n```json\n" + json.dumps(result, sort_keys=True) + "\n```\n")
        return 1 if result["status"] == "incomplete" else 0
    except Exception:
        with args.summary.open("a") as stream:
            stream.write("why: review discovery is unresolved; remedy: inspect fixed storage and exact receipts; do not retry a business POST\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
