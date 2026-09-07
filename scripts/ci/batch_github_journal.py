#!/usr/bin/env python3
"""Fixed-Issue transport for incremental_batch_journal; no automatic setup.

The repository's controlled Actions writers share one trusted bot identity.
Claimed run metadata is checked against GitHub, but GitHub does not attest that
a particular Issue write originated from that run. This is not a signature.
All writes are single-attempt; uncertainty belongs to the journal's pending
protocol. API failures never mean absence and never include response bodies.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import json
import re

from incremental_batch_journal import JournalBlocked
from self_test_report import UrllibGitHubApi

SCHEMA = "lmdj.ci-journal-object.v1"
LIMIT = 60000
WAITING_RUN_STATUSES = ("queued", "waiting", "requested", "pending")
KNOWN_RUN_STATUSES = WAITING_RUN_STATUSES + ("in_progress", "completed")
ACTOR = "{ __typename ... on Bot { id } }"
METADATA = f"id body author {ACTOR} editor {ACTOR} lastEditedAt"
BODY_QUERY = f"""query($owner:String!,$name:String!,$number:Int!) {{
 repository(owner:$owner,name:$name) {{ nameWithOwner issue(number:$number) {{ number {METADATA} }} }} }}"""
COMMENTS_QUERY = f"""query($owner:String!,$name:String!,$number:Int!,$after:String) {{
 repository(owner:$owner,name:$name) {{ nameWithOwner issue(number:$number) {{ number id
 comments(first:100,after:$after) {{ totalCount pageInfo {{ hasNextPage endCursor }}
 nodes {{ fullDatabaseId {METADATA} }} }} }} }} }}"""


def require(condition, why):
    if not condition:
        raise JournalBlocked(f"why: {why}; remedy: stop admission and reconcile authenticated fixed-Issue state")


def positive(value):
    return type(value) is int and value > 0


def _pairs(pairs):
    document = {}
    for key, value in pairs:
        require(key not in document, "duplicate JSON key in journal payload")
        document[key] = value
    return document


def decode(body):
    require(isinstance(body, str), "journal body missing")
    try:
        require(len(body.encode("utf-8")) <= LIMIT, "journal body oversized")
        value = json.loads(body, object_pairs_hook=_pairs,
                           parse_constant=lambda _: require(False, "nonfinite journal JSON"))
    except JournalBlocked:
        raise
    except Exception:
        raise JournalBlocked("why: journal body is not strict JSON; remedy: reconcile original record, never repair evidence by guessing") from None
    require(isinstance(value, dict) and set(value) == {"schema", "kind", "writer", "payload"}, "journal object schema is not closed")
    require(value["schema"] == SCHEMA and value["kind"] in ("checkpoint", "event"), "unsupported journal object kind")
    require(isinstance(value["payload"], dict), "journal payload must be an object")
    return value


class GitHubJournalTransport:
    def __init__(self, *, repository, issue_number, issue_node_id, bot_node_id,
                 workflows, writer, api=None, token=None, lock_held):
        require(isinstance(repository, str) and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository), "invalid fixed repository")
        require(positive(issue_number), "invalid fixed Issue number")
        require(all(isinstance(value, str) and value for value in (issue_node_id, bot_node_id)), "missing stable Issue/Bot node ID")
        require(isinstance(workflows, dict) and workflows and all(
            isinstance(path, str) and re.fullmatch(r"\.github/workflows/[a-zA-Z0-9_-]+\.ya?ml", path)
            and positive(workflow_id) for path, workflow_id in workflows.items()), "invalid trusted workflow inventory")
        self.repository, self.number, self.issue_node_id = repository, issue_number, issue_node_id
        self.bot_node_id, self.workflows = bot_node_id, deepcopy(workflows)
        self.writer, self.lock_held = deepcopy(writer), lock_held
        try:
            self.api = api if api is not None else UrllibGitHubApi(repository, token)
        except Exception:
            raise JournalBlocked("why: journal API credentials unavailable; remedy: restore scoped GitHub access") from None
        self._page_session = None
        self._checked_writers = set()  # one short controller transaction only

    def _call(self, method, path, body=None):
        try:
            # raw=False is intentional: reporter raw downloads allow artifact
            # redirects. Normal JSON requests use its NoRedirect opener.
            return self.api._request(method, path, body=body, raw=False)
        except Exception:
            raise JournalBlocked("why: GitHub journal request unavailable or write outcome unknown; remedy: reconcile existing intent without repeating a write") from None

    def _repo(self, suffix):
        return f"/repos/{self.repository}{suffix}"

    def _fixed(self, number):
        require(type(number) is int and number == self.number, "journal request targets a different Issue")

    def _query(self, query, after=None):
        owner, name = self.repository.split("/")
        variables = {"owner": owner, "name": name, "number": self.number}
        if query == COMMENTS_QUERY:
            variables["after"] = after
        response = self._call("POST", "/graphql", {"query": query, "variables": variables})
        require(isinstance(response, dict) and not response.get("errors"), "GraphQL journal query has errors")
        data = response.get("data")
        require(isinstance(data, dict) and isinstance(data.get("repository"), dict), "GraphQL repository unavailable")
        repository = data["repository"]
        require(repository.get("nameWithOwner") == self.repository, "GraphQL repository identity differs")
        issue = repository.get("issue")
        require(isinstance(issue, dict) and type(issue.get("number")) is int
                and issue["number"] == self.number and issue.get("id") == self.issue_node_id, "GraphQL fixed Issue identity differs")
        return issue

    def _bot(self, actor):
        return isinstance(actor, dict) and actor.get("__typename") == "Bot" and actor.get("id") == self.bot_node_id

    def _metadata(self, node, *, comment):
        require({"author", "editor", "lastEditedAt", "body", "id"} <= set(node), "edit metadata was omitted")
        edited = node["lastEditedAt"] is not None or node["editor"] is not None
        if comment:
            require(not edited and self._bot(node["author"]), "journal comment was edited or is not from the trusted bot")
        elif edited:
            require(isinstance(node["lastEditedAt"], str) and bool(node["lastEditedAt"])
                    and self._bot(node["editor"]), "checkpoint last editor is not the trusted bot")
        else:
            require(self._bot(node["author"]), "checkpoint author is not the trusted bot")

    def _writer(self, writer):
        require(isinstance(writer, dict) and set(writer) == {
            "repository", "issue_number", "run_id", "run_attempt", "control_sha", "workflow_path", "workflow_id", "job_name"},
            "writer identity schema is not closed")
        require(writer["repository"] == self.repository and type(writer["issue_number"]) is int
                and writer["issue_number"] == self.number, "writer repository or Issue differs")
        require(positive(writer["run_id"]) and type(writer["run_attempt"]) is int and writer["run_attempt"] == 1,
                "writer run identity is not a fresh first attempt")
        path = writer["workflow_path"]
        require(isinstance(path, str) and positive(writer["workflow_id"])
                and self.workflows.get(path) == writer["workflow_id"], "writer workflow is not explicitly trusted")
        control = writer["control_sha"]
        require(isinstance(control, str) and re.fullmatch(r"[0-9a-f]{40}", control), "writer control is not an exact SHA")
        require(isinstance(writer["job_name"], str) and writer["job_name"], "writer job name is missing")
        cache_key = json.dumps(writer, sort_keys=True)
        if cache_key in self._checked_writers:
            return deepcopy(writer)
        # The generic run endpoint changes when somebody reruns an old run.
        # Historical first-attempt journal writes remain valid observations.
        run = self._call("GET", self._repo(f"/actions/runs/{writer['run_id']}/attempts/1"))
        require(isinstance(run, dict) and type(run.get("id")) is int and run["id"] == writer["run_id"]
                and type(run.get("run_attempt")) is int and run["run_attempt"] == 1
                and type(run.get("workflow_id")) is int and run["workflow_id"] == writer["workflow_id"]
                and run.get("head_sha") == control and run.get("head_branch") == "main"
                and run.get("path") == path and run.get("status") in KNOWN_RUN_STATUSES
                and run.get("event") in ("push", "workflow_dispatch", "workflow_run", "schedule")
                and isinstance(run.get("repository"), dict) and run["repository"].get("full_name") == self.repository
                and isinstance(run.get("head_repository"), dict) and run["head_repository"].get("full_name") == self.repository,
                "writer run does not match trusted control provenance")
        workflow = self._call("GET", self._repo(f"/actions/workflows/{writer['workflow_id']}"))
        require(isinstance(workflow, dict) and type(workflow.get("id")) is int
                and workflow["id"] == writer["workflow_id"] and workflow.get("path") == path, "workflow API identity differs")
        ref = self._call("GET", self._repo("/git/ref/heads/main"))
        ref_object = ref.get("object") if isinstance(ref, dict) else None
        main = ref_object.get("sha") if isinstance(ref_object, dict) else None
        require(isinstance(main, str) and re.fullmatch(r"[0-9a-f]{40}", main), "main ref is unavailable")
        comparison = self._call("GET", self._repo(f"/compare/{control}...{main}"))
        require(isinstance(comparison, dict) and comparison.get("status") in ("ahead", "identical")
                and isinstance(comparison.get("base_commit"), dict) and comparison["base_commit"].get("sha") == control
                and isinstance(comparison.get("merge_base_commit"), dict)
                and comparison["merge_base_commit"].get("sha") == control, "writer control is not proven main history")
        source = self._call("GET", self._repo(f"/contents/{path}?ref={control}"))
        require(isinstance(source, dict) and source.get("type") == "file" and source.get("path") == path
                and source.get("encoding") == "base64" and isinstance(source.get("content"), str), "trusted workflow source unavailable")
        try:
            require(bool(base64.b64decode("".join(source["content"].split()), validate=True)), "trusted workflow source is empty")
        except JournalBlocked:
            raise
        except Exception:
            raise JournalBlocked("why: trusted workflow source is malformed; remedy: restore exact-control source visibility") from None
        jobs, total, seen = [], None, set()
        for page in range(1, 101):
            document = self._call("GET", self._repo(f"/actions/runs/{writer['run_id']}/attempts/1/jobs?per_page=100&page={page}"))
            require(isinstance(document, dict) and type(document.get("total_count")) is int
                    and document["total_count"] >= 0 and isinstance(document.get("jobs"), list), "jobs pagination malformed")
            require(total in (None, document["total_count"]), "jobs changed during pagination")
            total = document["total_count"]
            require(len(document["jobs"]) <= 100, "job page exceeds requested size")
            for job in document["jobs"]:
                require(isinstance(job, dict) and positive(job.get("id")) and job["id"] not in seen, "duplicate or invalid job identity")
                seen.add(job["id"])
                jobs.append(job)
            require(len(jobs) <= total, "jobs exceed declared total")
            if len(jobs) == total:
                break
            require(bool(document["jobs"]), "jobs pagination truncated")
        require(len(jobs) == total, "jobs pagination limit reached")
        matches = [job for job in jobs if job.get("name") == writer["job_name"]]
        require(len(matches) == 1 and type(matches[0].get("run_id")) is int
                and matches[0]["run_id"] == writer["run_id"]
                and type(matches[0].get("run_attempt")) is int and matches[0]["run_attempt"] == 1
                and matches[0].get("status") in ("in_progress", "completed"), "writer job is missing or ambiguous")
        if run["status"] in WAITING_RUN_STATUSES:
            # Aggregate status can return to waiting while product siblings wait.
            # It never proves this writer ran: authenticate its own start too.
            job = matches[0]
            require(isinstance(job.get("started_at"), str) and bool(job["started_at"])
                    and (job["status"] == "in_progress" or job.get("conclusion") in {
                        "success", "failure", "cancelled", "timed_out", "action_required", "neutral", "stale"}),
                    "waiting parent has no proven started writer")
        self._checked_writers.add(cache_key)
        return deepcopy(writer)

    def _unpack(self, node, kind):
        self._metadata(node, comment=kind == "event")
        document = decode(node["body"])
        require(document["kind"] == kind, "journal object is stored in the wrong location")
        writer = self._writer(document["writer"])
        return document["payload"], writer

    def read_body(self, issue_id):
        self._fixed(issue_id)
        payload, writer = self._unpack(self._query(BODY_QUERY), "checkpoint")
        return {"checkpoint": payload, "provenance": writer}

    def page(self, issue_id, cursor):
        self._fixed(issue_id)
        if cursor is None:
            self._page_session = {"count": 0, "total": None, "next": None, "seen": set()}
        session = self._page_session
        require(session is not None and cursor == session["next"], "comment pagination cursor is out of sequence")
        issue = self._query(COMMENTS_QUERY, cursor)
        connection = issue.get("comments")
        require(isinstance(connection, dict) and type(connection.get("totalCount")) is int
                and connection["totalCount"] >= 0 and isinstance(connection.get("nodes"), list)
                and isinstance(connection.get("pageInfo"), dict), "comment pagination malformed")
        require(session["total"] in (None, connection["totalCount"]), "comment inventory changed during pagination")
        session["total"] = connection["totalCount"]
        info = connection["pageInfo"]
        require(type(info.get("hasNextPage")) is bool, "comment pagination completion is not boolean")
        next_cursor = info.get("endCursor") if info["hasNextPage"] else None
        require(not info["hasNextPage"] or isinstance(next_cursor, str) and bool(next_cursor), "missing next comment cursor")
        require(not info["hasNextPage"] or next_cursor not in session["seen"], "comment pagination loop")
        comments = []
        require(len(connection["nodes"]) <= 100, "comment page exceeds requested size")
        for node in connection["nodes"]:
            require(isinstance(node, dict), "null or malformed comment node")
            raw_id = node.get("fullDatabaseId")
            require(isinstance(raw_id, str) and re.fullmatch(r"[1-9][0-9]*", raw_id), "comment BigInt identity is not decimal text")
            payload, writer = self._unpack(node, "event")
            comments.append({"id": int(raw_id), "edited": False, "envelope": payload, "provenance": writer})
        session["count"] += len(comments)
        require(session["count"] <= session["total"], "comment inventory exceeds total")
        require(info["hasNextPage"] or session["count"] == session["total"], "comment inventory is truncated")
        require(not info["hasNextPage"] or comments and session["count"] < session["total"], "comment continuation contradicts total")
        session["next"] = next_cursor
        session["seen"].add(next_cursor)
        return {"comments": comments, "next": next_cursor}

    def authenticate(self, record, issue_id):
        self._fixed(issue_id)
        # Transport already checked platform metadata on this read. Journal
        # records are private in-process projections, never caller input.
        self._writer(record.get("provenance"))
        return True

    def _write(self, issue_id, kind, payload):
        self._fixed(issue_id)
        require(self.lock_held() is True, "journal write lacks short writer lock")
        self.read_body(issue_id)  # never overwrite a missing/manual/foreign checkpoint
        writer = self._writer(self.writer)
        try:
            body = json.dumps({"schema": SCHEMA, "kind": kind, "writer": writer, "payload": payload},
                              sort_keys=True, separators=(",", ":"), allow_nan=False)
        except Exception:
            raise JournalBlocked("why: journal write is not strict JSON; remedy: validate the event before persisting") from None
        decode(body)
        suffix = f"/issues/{self.number}" + ("/comments" if kind == "event" else "")
        self._call("POST" if kind == "event" else "PATCH", self._repo(suffix), {"body": body})

    def write_body(self, issue_id, checkpoint):
        self._write(issue_id, "checkpoint", checkpoint)

    def append(self, issue_id, envelope):
        self._write(issue_id, "event", envelope)
