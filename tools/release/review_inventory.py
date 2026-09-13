"""Complete private review input, not review eligibility or merge authority."""

from copy import deepcopy
import re

from .batch_reference import positive, sha
from .model import canonical_json, canonical_sha256


class ReviewInventoryError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise ReviewInventoryError(f"why: release review inventory {reason}; remedy: restore complete stable exact-head API visibility and recollect; do not infer approval from missing evidence")


def text(value):
    return type(value) is str and bool(value.strip())


BOUNDARY = """id databaseId number headRefOid baseRefName state isDraft merged
  mergeCommit { oid } headRepository { databaseId nameWithOwner }"""
PAGE = "totalCount pageInfo { hasNextPage endCursor }"
FIELDS = {
    "reviews": "id databaseId body state submittedAt updatedAt commit { oid } author { login }",
    "comments": "id databaseId body createdAt updatedAt author { login }",
    "reviewThreads": "id isResolved isOutdated path comments { totalCount }",
    "closingIssuesReferences": "id databaseId number repository { databaseId nameWithOwner }",
    "threadComments": """id databaseId body createdAt updatedAt author { login }
      originalCommit { oid } commit { oid } path diffHunk originalLine line
      pullRequest { databaseId number } pullRequestReview { id databaseId }""",
}


def query_document(number, kind, cursor=None, thread_id=None):
    """Only these read queries can cross the release HTTP transport boundary."""
    require(positive(number) and type(kind) is str and kind in FIELDS, "query target is invalid")
    require(cursor is None or (text(cursor) and len(cursor) <= 1024), "cursor is invalid")
    require((kind == "threadComments" and text(thread_id) and len(thread_id) <= 256)
            or (kind != "threadComments" and thread_id is None), "thread selection is invalid")
    variables = {"number": number, "cursor": cursor}
    selection = f"{kind}(first:100,after:$cursor) {{ {PAGE} nodes {{ {FIELDS[kind]} }} }}"
    extra, arguments = "", "$number:Int!,$cursor:String"
    if kind == "threadComments":
        selection = ""
        arguments += ",$thread:ID!"
        variables["thread"] = thread_id
        extra = ("node(id:$thread) { __typename ... on PullRequestReviewThread { id "
                 f"comments(first:100,after:$cursor) {{ {PAGE} nodes {{ {FIELDS[kind]} }} }} " + "} }")
    query = (f"query({arguments}) {{ repository(owner:\"endaye\",name:\"lmdj\") {{ "
             f"databaseId nameWithOwner pullRequest(number:$number) {{ {BOUNDARY} {selection} }} "
             "} " + extra + " }")
    return {"query": query, "variables": variables}


class ReviewInventory:
    """Call with the authenticated GitHubClient, never arbitrary PR query text.

    Returned bodies are private decision inputs. Do not publish or log them.
    Identity/count/content consistency is not semantic review disposition.
    """
    MAX_CALLS = 1024

    def __init__(self, client):
        self.client = client

    def collect(self, repository_id, number, head):
        require(positive(repository_id) and positive(number) and sha(head), "scope is invalid")
        calls, observed_bytes, boundary = 0, 0, None

        def page(kind, cursor=None, thread=None):
            nonlocal calls, observed_bytes, boundary
            calls += 1
            require(calls <= self.MAX_CALLS, "read budget exhausted")
            try:
                doc = self.client.get_release_review_page(number, kind, cursor, thread)
            except ReviewInventoryError:
                raise
            except Exception:
                raise ReviewInventoryError("why: release review API unavailable; remedy: restore API access and recollect without treating unavailable as approval") from None
            require(type(doc) is dict and not doc.get("errors") and type(doc.get("data")) is dict,
                    "GraphQL response is incomplete")
            observed_bytes += len(canonical_json(doc))
            require(observed_bytes <= 64 * 1024 * 1024, "content budget exhausted")
            repo = doc["data"].get("repository")
            require(type(repo) is dict and type(repo.get("databaseId")) is int
                    and repo["databaseId"] == repository_id and repo.get("nameWithOwner") == "endaye/lmdj",
                    "repository identity differs")
            pr = repo.get("pullRequest")
            require(type(pr) is dict and text(pr.get("id")) and positive(pr.get("databaseId"))
                    and type(pr.get("number")) is int and pr["number"] == number
                    and pr.get("headRefOid") == head and pr.get("baseRefName") == "main"
                    and pr.get("state") == "OPEN" and pr.get("isDraft") is False
                    and pr.get("merged") is False and "mergeCommit" in pr
                    and type(pr.get("headRepository")) is dict
                    and type(pr["headRepository"].get("databaseId")) is int
                    and pr["headRepository"]["databaseId"] == repository_id
                    and pr["headRepository"].get("nameWithOwner") == "endaye/lmdj", "PR is not the exact open same-repository main target")
            # mergeCommit can be GitHub's provisional merge commit before merge;
            # it is not part of review input identity or actual squash proof.
            identity = {key: pr[key] for key in ("id", "databaseId", "number", "headRefOid",
                "baseRefName", "state", "isDraft", "merged", "headRepository")}
            require(boundary is None or boundary == identity, "PR identity changed during collection")
            boundary = identity
            if kind != "threadComments":
                return pr.get(kind)
            node = doc["data"].get("node")
            require(type(node) is dict and node.get("__typename") == "PullRequestReviewThread"
                    and node.get("id") == thread, "nested thread identity differs")
            return node.get("comments")

        def inventory(kind, thread=None, expected_count=None):
            rows, ids, database_ids, cursor, cursors, count = [], set(), set(), None, set(), expected_count
            for _ in range(100):
                value = page(kind, cursor, thread)
                require(type(value) is dict and type(value.get("totalCount")) is int
                        and value["totalCount"] >= 0 and (count is None or value["totalCount"] == count),
                        "connection count changed or is missing")
                count = value["totalCount"]
                nodes, info = value.get("nodes"), value.get("pageInfo")
                require(type(nodes) is list and len(nodes) <= 100 and type(info) is dict
                        and type(info.get("hasNextPage")) is bool and "endCursor" in info,
                        "connection page is malformed")
                for node in nodes:
                    validate_node(kind, node, number, boundary["databaseId"])
                    require(node["id"] not in ids, "connection repeats an object")
                    ids.add(node["id"])
                    if "databaseId" in node:
                        require(node["databaseId"] not in database_ids, "connection repeats a database identity")
                        database_ids.add(node["databaseId"])
                    rows.append(deepcopy(node))
                require(len(rows) <= count, "connection exceeds its count")
                if not info["hasNextPage"]:
                    require(len(rows) == count, "connection is truncated")
                    return sorted(rows, key=lambda row: row["id"])
                cursor = info["endCursor"]
                require(nodes and len(rows) < count and text(cursor) and len(cursor) <= 1024
                        and cursor not in cursors, "connection cursor does not advance")
                cursors.add(cursor)
            raise ReviewInventoryError("why: release review pagination budget exhausted; remedy: reconcile the complete original inventory without claiming approval")

        def snapshot():
            result = {kind: inventory(kind) for kind in FIELDS if kind != "threadComments"}
            for thread in result["reviewThreads"]:
                thread["comments"] = inventory("threadComments", thread["id"], thread["comments"]["totalCount"])
            reviews = {row["id"]: row["databaseId"] for row in result["reviews"]}
            seen_comments, seen_comment_database_ids = set(), set()
            for thread in result["reviewThreads"]:
                for comment in thread["comments"]:
                    review = comment["pullRequestReview"]
                    require(reviews.get(review["id"]) == review["databaseId"], "thread review is absent from complete review inventory")
                    require(comment["id"] not in seen_comments, "comment appears in multiple threads")
                    require(comment["databaseId"] not in seen_comment_database_ids,
                            "comment database identity appears in multiple threads")
                    seen_comments.add(comment["id"])
                    seen_comment_database_ids.add(comment["databaseId"])
            return {"schema": "lmdj.release-review-inventory.v1", "repository_id": repository_id,
                    "repository": "endaye/lmdj", "pr": deepcopy(boundary), **result}

        first, second = snapshot(), snapshot()
        require(canonical_json(first) == canonical_json(second), "content changed between complete observations")
        return {"inventory": second, "sha256": canonical_sha256(second)}


def validate_node(kind, node, number, pr_id):
    require(type(node) is dict and text(node.get("id")), "object lacks node identity")
    if kind == "reviewThreads":
        require(type(node.get("isResolved")) is bool and type(node.get("isOutdated")) is bool
                and text(node.get("path")) and type(node.get("comments")) is dict
                and type(node["comments"].get("totalCount")) is int and node["comments"]["totalCount"] > 0,
                "thread metadata is incomplete")
        return
    require(positive(node.get("databaseId")), "object lacks database identity")
    if kind == "closingIssuesReferences":
        repo = node.get("repository")
        require(positive(node.get("number")) and type(repo) is dict and positive(repo.get("databaseId"))
                and type(repo.get("nameWithOwner")) is str
                and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo["nameWithOwner"]),
                "closing Issue identity is incomplete")
        return
    require(type(node.get("body")) is str and "author" in node
            and (node["author"] is None or (type(node["author"]) is dict and text(node["author"].get("login"))))
            and text(node.get("updatedAt")), "comment content or authorship is incomplete")
    if kind == "reviews":
        require(node.get("state") in ("PENDING", "COMMENTED", "APPROVED", "CHANGES_REQUESTED", "DISMISSED")
                and "submittedAt" in node and (node["submittedAt"] is None or text(node["submittedAt"]))
                and "commit" in node and (node["commit"] is None or
                    (type(node["commit"]) is dict and sha(node["commit"].get("oid")))), "review metadata is incomplete")
    else:
        require(text(node.get("createdAt")), "comment creation time is missing")
    if kind == "threadComments":
        pr, review = node.get("pullRequest"), node.get("pullRequestReview")
        require(type(pr) is dict and type(pr.get("number")) is int and pr["number"] == number
                and type(pr.get("databaseId")) is int and pr["databaseId"] == pr_id
                and type(review) is dict and text(review.get("id")) and positive(review.get("databaseId")),
                "comment belongs to another PR or lacks review identity")
        require(text(node.get("path")) and type(node.get("diffHunk")) is str
                and all(key in node and (node[key] is None or positive(node[key])) for key in ("line", "originalLine"))
                and all(key in node and (node[key] is None or
                    (type(node[key]) is dict and sha(node[key].get("oid")))) for key in ("commit", "originalCommit")),
                "inline source context is incomplete")
