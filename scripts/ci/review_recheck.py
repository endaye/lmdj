#!/usr/bin/env python3
"""Source repair verification and guarded bot-thread publication.

No credentials enter the model. GitHub thread resolution has no head CAS;
fresh boundary checks and compensation detect, but cannot eliminate, races.
"""
from __future__ import annotations

import hashlib
import html
import os
import re

import pr_agent_review as engine
import self_test_report as reporting
from review_scope import ReviewScopeError


class Refused(ReviewScopeError):
    pass


def require(value, reason):
    if not value:
        raise Refused(f"why: {reason}; remedy: recollect and recheck the current head, or review the thread manually")


def digest(value):
    return hashlib.sha256(engine._canonical(value)).hexdigest()


def client(repository):
    from self_test_report import UrllibGitHubApi
    return UrllibGitHubApi(repository, os.environ["GITHUB_TOKEN"])


def graphql(api, query, variables):
    result = api._request("POST", "/graphql", body={"query": query, "variables": variables})
    require(isinstance(result, dict) and not result.get("errors") and isinstance(result.get("data"), dict),
            "GitHub GraphQL response is incomplete")
    return result["data"]


def connection(api, query, variables, select):
    """Bound every page and total count; never take the first 100 as complete."""
    rows, cursor, count, cursors = [], None, None, set()
    for _ in range(100):
        value = select(graphql(api, query, {**variables, "cursor": cursor}))
        require(isinstance(value, dict) and isinstance(value.get("nodes"), list), "missing connection")
        total = value.get("totalCount")
        require(type(total) is int and total >= 0 and (count is None or count == total), "connection count changed")
        count = total
        rows.extend(value["nodes"])
        require(all(isinstance(row, dict) and row.get("id") for row in rows), "connection contains missing nodes")
        require(len({r["id"] for r in rows}) == len(rows), "connection contains duplicate nodes")
        page = value.get("pageInfo", {})
        require(type(page.get("hasNextPage")) is bool, "connection pagination is missing")
        if not page["hasNextPage"]:
            require(len(rows) == count, "connection is truncated")
            return rows
        cursor = page.get("endCursor")
        require(isinstance(cursor, str) and cursor and cursor not in cursors, "connection cursor did not advance")
        cursors.add(cursor)
    raise Refused("why: conversation pagination budget exhausted; remedy: review manually")


THREADS = """query($owner:String!,$name:String!,$number:Int!,$cursor:String){
repository(owner:$owner,name:$name){pullRequest(number:$number){
reviewThreads(first:100,after:$cursor){totalCount pageInfo{hasNextPage endCursor}
nodes{id isResolved comments(first:1){nodes{databaseId path author{... on Bot{databaseId} ... on User{databaseId}}}}}}}}} """

COMMENTS = """query($thread:ID!,$cursor:String){node(id:$thread){
... on PullRequestReviewThread {id comments(first:100,after:$cursor){
totalCount pageInfo{hasNextPage endCursor} nodes{id databaseId body updatedAt
author{login ... on User{databaseId} ... on Bot{databaseId}}}}}}} """

STATE = """query($thread:ID!){node(id:$thread){... on PullRequestReviewThread{
id isResolved pullRequest{number repository{nameWithOwner}}}}} """


def thread_inventory(api, repository, number):
    owner, name = repository.split("/")
    return connection(api, THREADS, {"owner": owner, "name": name, "number": number},
                         lambda d: d.get("repository", {}).get("pullRequest", {}).get("reviewThreads"))


def thread_for(api, repository, number, comment_id, threads=None):
    threads = thread_inventory(api, repository, number) if threads is None else threads
    matching = [t for t in threads if t.get("comments", {}).get("nodes", [{}])
                and t["comments"]["nodes"][0].get("databaseId") == comment_id]
    require(len(matching) == 1, "selected ID is not one original review-thread comment")
    return matching[0]["id"]


def snapshot(api, repository, number, thread):
    before = graphql(api, STATE, {"thread": thread}).get("node")
    require(isinstance(before, dict) and before.get("id") == thread
            and type(before.get("isResolved")) is bool
            and before.get("pullRequest", {}).get("number") == number
            and before.get("pullRequest", {}).get("repository", {}).get("nameWithOwner") == repository,
            "thread belongs to another PR or cannot be read")
    comments = connection(api, COMMENTS, {"thread": thread}, lambda d: d.get("node", {}).get("comments"))
    observed = []
    for c in comments:
        author = c.get("author") or {}
        require(type(c.get("databaseId")) is int and c["databaseId"] > 0
                and type(author.get("databaseId")) is int and author["databaseId"] > 0
                and isinstance(c.get("body"), str) and isinstance(c.get("updatedAt"), str),
                "comment identity or content is unavailable")
        observed.append({"id": c["databaseId"], "author_id": author["databaseId"],
                         "body": c["body"], "updated_at": c["updatedAt"]})
    after = graphql(api, STATE, {"thread": thread}).get("node")
    require(after == before, "thread state changed during collection")
    return before["isResolved"], observed


def current_head(api, repository, number, head):
    pull = api._request("GET", f"/repos/{repository}/pulls/{number}")
    require(pull.get("state") == "open" and pull.get("merged") is False and pull.get("draft") is False
            and pull.get("head", {}).get("sha") == head
            and pull.get("base", {}).get("ref") == "main"
            and pull.get("base", {}).get("repo", {}).get("full_name") == repository,
            "PR is closed, draft, retargeted or has a different head")


def collect(api, document, comment_id, *, git, fetch, allow_resolved=False, reader=None, threads=None):
    """Original review auth is the existing retained-artifact reader, not a bot name."""
    import review_wait
    identity = document["identity"]
    repository, number, head = identity["repository"], identity["pull_request"], identity["head_sha"]
    require(type(comment_id) is int and comment_id > 0, "comment ID must be a positive integer")
    current_head(api, repository, number, head)
    reader = reader or review_wait.Reader(api, repository)
    repo = reader.get(f"/repos/{repository}")
    bot = reader.get("/users/github-actions%5Bbot%5D")
    comment = reader.get(f"/repos/{repository}/pulls/comments/{comment_id}")
    require(comment.get("user", {}).get("id") == bot.get("id") and not comment.get("in_reply_to_id"),
            "selected comment is not an original bot finding")
    review_id = comment.get("pull_request_review_id")
    require(type(review_id) is int and review_id > 0, "original review identity is absent")
    posted = reader.get(f"/repos/{repository}/pulls/{number}/reviews/{review_id}")
    original = posted.get("commit_id")
    require(isinstance(original, str) and re.fullmatch(r"[0-9a-f]{40}", original) and original != head,
            "repair requires a different original reviewed head")
    review_wait.automated(reader, posted, repo, number, original, bot)
    # automated() checks every source finding. Also bind the selected detail to
    # that authenticated inventory, rather than merely to a supplied review ID.
    roots = reader.pages(f"/repos/{repository}/pulls/{number}/reviews/{review_id}/comments")
    require(any(c.get("id") == comment_id for c in roots), "selected comment is absent from authentic findings")
    thread = thread_for(api, repository, number, comment_id, threads)
    resolved, conversation = snapshot(api, repository, number, thread)
    require(allow_resolved or not resolved, "selected thread is already resolved")
    require(conversation and conversation[0]["id"] == comment_id
            and conversation[0]["body"] == comment.get("body")
            and conversation[0]["author_id"] == bot["id"], "thread root differs from authentic finding")
    path = comment.get("path")
    auth = engine.authenticate_input(document)
    require(any(f["path"] == path and f["head_encoding"] == "utf-8" for f in auth["files"]),
            "finding path has no current text source in the complete PR input")
    fetch(original)
    require(git("merge-base", original, head).decode().strip() == original, "original reviewed head is not an ancestor")
    original_content = git("show", original + ":" + path).decode("utf-8")
    fix_diff = git("diff", "--full-index", "--no-ext-diff", "--no-textconv", "--no-renames", "--unified=3", original, head, "--", path).decode("utf-8")
    require(bool(fix_diff.strip()), "finding source is unchanged since the original review")
    request = {"comment_id": comment_id, "thread_id": thread, "original_head": original,
               "path": path, "original_line": comment["original_line"], "body": comment["body"], "original_content": original_content,
               "fix_diff": fix_diff, "conversation": conversation}
    engine.validate_repair_request(request, auth["files"])
    current_head(api, repository, number, head)
    require(snapshot(api, repository, number, thread) == (resolved, conversation), "conversation changed during input collection")
    return request


def collect_batch(api, document, *, git, fetch):
    """Bound costly authentication; absent evidence never turns into resolution."""
    import review_failure_report
    import review_wait
    # Authenticating one candidate downloads and validates its retained producer
    # archive, which carries bounded download and expansion budgets
    # (review_failure_report). That refusal is evidence about this finding, not a
    # defect of the head under review: when it escaped, collect-t2 wrote no
    # complete input at all, no model reviewed the head, and every synchronize
    # push failed the whole lane with one opaque line -- a reviewer that looks
    # dead instead of a finding that was not rechecked. Each owner's class is
    # read from that owner: review_failure_report raises through its own
    # `reporting` alias while the API client raises the class it imports.
    refusals = (ReviewScopeError, review_wait.Refused, engine.EngineError,
                reporting.ReportingError, review_failure_report.reporting.ReportingError)
    identity = document["identity"]
    repository, number, head = identity["repository"], identity["pull_request"], identity["head_sha"]
    current_head(api, repository, number, head)
    threads = thread_inventory(api, repository, number)
    reader = review_wait.Reader(api, repository)
    bot = reader.get("/users/github-actions%5Bbot%5D")
    require(type(bot.get("id")) is int and bot.get("type") == "Bot", "bot identity is unavailable")
    report, candidates, requests = [], [], []
    files = {f["path"] for f in engine.authenticate_input(document)["files"] if f["head_encoding"] == "utf-8"}
    for thread in threads:
        require(type(thread.get("isResolved")) is bool, "thread resolution state is unavailable")
        roots = thread.get("comments", {}).get("nodes", [])
        require(len(roots) == 1 and type(roots[0].get("databaseId")) is int, "thread original comment is unavailable")
        root = roots[0]
        if thread["isResolved"] or (root.get("author") or {}).get("databaseId") != bot["id"]:
            continue
        row = {"comment_id": root["databaseId"], "thread_id": thread["id"]}
        if root.get("path") not in files:
            report.append({**row, "status": "not_rechecked", "reason": "finding path has no current text source in the complete PR input"})
        else:
            candidates.append(row)
    for index, row in enumerate(sorted(candidates, key=lambda r: r["comment_id"])):
        if index >= engine.MAX_REPAIR_REQUESTS:
            report.append({**row, "status": "deferred", "reason": "per-run candidate bound; use manual recheck"})
            continue
        try:
            request = collect(api, document, row["comment_id"], git=git, fetch=fetch, reader=reader, threads=threads)
        except refusals as error:
            report.append({**row, "status": "not_rechecked", "reason": str(error)})
        else:
            if len(engine._canonical([*requests, request])) > engine.MAX_REPAIR_BYTES:
                report.append({**row, "status": "deferred", "reason": "combined repair byte bound; use manual recheck"})
            else:
                requests.append(request)
                report.append({**row, "status": "collected"})
    current_head(api, repository, number, head)
    return requests, {"head_sha": head, "threads_observed": len(threads), "candidates": report}


def attach_batch(document, requests):
    document["repair_requests"] = requests
    reseal(document)


def reseal(document):
    document.pop("input_sha256", None)
    document["input_sha256"] = digest(document)
    engine.authenticate_input(document)


def attach(document, request):
    document["repair_request"] = request
    reseal(document)


def set_resolved(api, thread, resolved):
    operation = "resolveReviewThread" if resolved else "unresolveReviewThread"
    query = "mutation($thread:ID!){" + operation + "(input:{threadId:$thread}){thread{id isResolved}}}"
    data = graphql(api, query, {"thread": thread}).get(operation, {}).get("thread", {})
    require(data.get("id") == thread and data.get("isResolved") is resolved, "thread mutation was not confirmed")


def publish(api, document, native, *, git, fetch, request=None, reader=None, threads=None):
    identity = document["identity"]
    request = document["repair_request"] if request is None else request
    repository, number, head = identity["repository"], identity["pull_request"], identity["head_sha"]
    auth = engine.authenticate_input(document)
    verdicts = engine.validate_repair_verdicts(native, auth)
    require(request in engine.repair_requests(auth), "selected request differs from authenticated input")
    verdict = next(v for v in verdicts if v["comment_id"] == request["comment_id"])
    bot = api._request("GET", "/users/github-actions%5Bbot%5D")
    marker = "<!-- lmdj-repair-recheck-v1 " + head + " " + digest(request) + " -->"
    body = (f"PR-Agent repair recheck: **{verdict['verdict']}** at `{head}`.\n\n"
            + html.escape(verdict["reason"]) + "\n\nSource verification only; no tests were executed by this recheck.\n\n")
    if verdict["verdict"] == "resolved":
        body += (f"Evidence: `{request['path']}` lines {verdict['start_line']}–{verdict['end_line']}.\n\n"
                 + "Original source:\n<pre>" + html.escape(verdict["original_quote"]) + "</pre>\n"
                 + "Current source:\n<pre>" + html.escape(verdict["current_quote"]) + "</pre>\n\n")
    body += marker

    def without_receipt(comments):
        receipts = [c for c in comments if c["author_id"] == bot["id"] and marker in c["body"]]
        require(len(receipts) <= 1 and all(c["body"] == body for c in receipts), "existing recheck receipt differs")
        return [c for c in comments if c not in receipts], receipts

    # Reconstruct source/provenance independently of the downloaded request.
    fresh = collect(api, document, request["comment_id"], git=git, fetch=fetch, allow_resolved=True, reader=reader, threads=threads)
    fresh["conversation"], receipts = without_receipt(fresh["conversation"])
    require(fresh == request, "source finding, fix diff or conversation changed since model input")

    def boundary():
        current_head(api, repository, number, head)
        resolved, comments = snapshot(api, repository, number, request["thread_id"])
        original_comments, found = without_receipt(comments)
        require(original_comments == request["conversation"], "conversation changed after recheck")
        return resolved, found

    resolved, receipts = boundary()
    require(not resolved or bool(receipts), "thread was independently resolved before publication")
    if not receipts:
        try:
            api._request("POST", f"/repos/{repository}/pulls/{number}/comments/{request['comment_id']}/replies", body={"body": body})
        except Exception:
            # A timeout/invalid response can follow an accepted write. Observe
            # its far side, never blindly POST again.
            _, receipts = boundary()
            require(bool(receipts), "reply outcome is unknown and no matching receipt is visible")
        _, receipts = boundary()
        require(bool(receipts), "reply is absent from the complete conversation")
    if verdict["verdict"] != "resolved":
        require(not boundary()[0], "non-resolved verdict cannot certify a closed thread")
        return {"verdict": verdict["verdict"], "resolved": False, "request_sha256": digest(request)}
    if not resolved:
        # No awaited unrelated work between this fresh check and mutation.
        boundary()
        try:
            set_resolved(api, request["thread_id"], True)
        except Exception:
            # An ambiguous mutation is reconciled below using actual state.
            pass
    try:
        require(boundary()[0], "resolved state was not observed after mutation")
    except Exception:
        # Do not treat a partially completed publication as a valid resolution.
        set_resolved(api, request["thread_id"], False)
        require(not snapshot(api, repository, number, request["thread_id"])[0], "race compensation could not be observed")
        raise
    return {"verdict": "resolved", "resolved": True, "request_sha256": digest(request)}


def publish_batch(api, document, native, *, git, fetch, record=None):
    """Persist each far-side receipt; a later refusal cannot erase earlier effects."""
    import review_wait
    auth = engine.authenticate_input(document)
    engine.validate_repair_verdicts(native, auth)
    identity = document["identity"]
    reader = review_wait.Reader(api, identity["repository"])
    threads = thread_inventory(api, identity["repository"], identity["pull_request"])
    receipts = []
    for request in auth["repair_requests"]:
        receipt = publish(api, document, native, git=git, fetch=fetch, request=request,
                          reader=reader, threads=threads)
        receipts.append({"comment_id": request["comment_id"], **receipt})
        if record:
            record({"receipts": receipts})
    return {"receipts": receipts}
