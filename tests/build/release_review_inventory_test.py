#!/usr/bin/env python3
"""Real collector/client with paginated GraphQL fixtures; no review approval."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.github_api import GitHubClient, GitHubApiError, HttpResponse
from tools.release.model import canonical_sha256
from tools.release.review_inventory import ReviewInventory, ReviewInventoryError, query_document


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.head = "a" * 40
        self.repo = {"databaseId": 12, "nameWithOwner": "endaye/lmdj"}
        self.pr = dict(id="PR_1", databaseId=41, number=42, headRefOid=self.head,
            baseRefName="main", state="OPEN", isDraft=False, merged=False, mergeCommit=None,
            headRepository=deepcopy(self.repo))
        self.rows = {}
        self.rows["reviews"] = [dict(id=f"R_{n}", databaseId=100+n, body=f"finding {n}",
            state="DISMISSED" if n == 1 else "COMMENTED", submittedAt="2026-09-13T01:00:00Z",
            updatedAt="2026-09-13T01:00:00Z", commit={"oid": "b"*40 if n == 1 else self.head},
            author={"login": "reviewer"}) for n in (1, 2)]
        self.rows["comments"] = [dict(id=f"IC_{n}", databaseId=200+n, body=f"discussion {n}",
            createdAt="2026-09-13T01:00:00Z", updatedAt="2026-09-13T01:00:00Z", author=None) for n in (1, 2)]
        self.rows["reviewThreads"] = [dict(id=f"T_{n}", isResolved=(n == 1), isOutdated=(n == 1),
            path="tools/release/example.py", comments={"totalCount": 2}) for n in (1, 2)]
        self.rows["closingIssuesReferences"] = [dict(id=f"I_{n}", databaseId=300+n, number=n,
            repository={"databaseId": 90+n, "nameWithOwner": f"owner/repo{n}"}) for n in (1, 2)]
        for n in (1, 2):
            self.rows[f"T_{n}"] = [dict(id=f"RC_{n}_{m}", databaseId=400+n*10+m,
                body=f"thread {n} comment {m}", createdAt="2026-09-13T01:00:00Z",
                updatedAt="2026-09-13T01:00:00Z", author={"login": "reviewer"},
                originalCommit={"oid":"b"*40}, commit={"oid":self.head}, path="tools/release/example.py",
                diffHunk="@@ -1 +1 @@\n-old\n+new", originalLine=1, line=None,
                pullRequest={"databaseId":41,"number":42}, pullRequestReview={"id":f"R_{n}","databaseId":100+n}) for m in (1, 2)]
        self.calls, self.snapshots = [], 0
        self.mutate = lambda kind, cursor, doc: None
        self.client = GitHubClient(http_transport=self.http, token="private-fixture-token")

    def http(self, method, url, headers, raw):
        self.assertEqual((method, url), ("POST", "/graphql"))
        self.assertEqual(headers["Authorization"], "Bearer private-fixture-token")
        request = json.loads(raw)
        self.assertTrue(request["query"].startswith("query("))
        self.assertNotIn("mutation", request["query"])
        variables = request["variables"]
        cursor, thread = variables["cursor"], variables.get("thread")
        kind = "threadComments" if thread else next(k for k in self.rows if f"{k}(first:" in request["query"])
        self.assertEqual(request, query_document(42, kind, cursor, thread))
        if kind == "reviews" and cursor is None:
            self.snapshots += 1
        rows = self.rows[thread or kind]
        index = 0 if cursor is None else int(cursor)
        nodes = deepcopy(rows[index:index+1])
        has_next = index + len(nodes) < len(rows)
        connection = {"totalCount":len(rows), "nodes":nodes,
                      "pageInfo":{"hasNextPage":has_next, "endCursor":str(index+1) if nodes else None}}
        pr = deepcopy(self.pr)
        doc = {"data":{"repository":{**self.repo,"pullRequest":pr}}}
        if thread:
            doc["data"]["node"] = {"__typename":"PullRequestReviewThread","id":thread,"comments":connection}
        else:
            pr[kind] = connection
        self.calls.append((kind, cursor, thread))
        self.mutate(kind, cursor, doc)
        return HttpResponse(200, {}, json.dumps(doc).encode())

    def collect(self):
        return ReviewInventory(self.client).collect(12, 42, self.head)

    def connection(self, kind, doc):
        return doc["data"]["node"]["comments"] if kind == "threadComments" else doc["data"]["repository"]["pullRequest"][kind]

    def rejected(self, expected):
        with self.assertRaisesRegex(ReviewInventoryError, expected) as caught:
            self.collect()
        self.assertIn("remedy:", str(caught.exception))
        self.assertNotIn("private-fixture-token", str(caught.exception))

    def test_complete_two_pass_inventory_retains_all_old_resolved_and_qualified_content(self):
        result = self.collect()
        inventory = result["inventory"]
        self.assertEqual(result["sha256"], canonical_sha256(inventory))
        self.assertEqual(len(self.calls), 24)
        self.assertEqual(inventory["reviews"], self.rows["reviews"])
        self.assertEqual(inventory["comments"], self.rows["comments"])
        self.assertEqual(inventory["closingIssuesReferences"], self.rows["closingIssuesReferences"])
        for thread in inventory["reviewThreads"]:
            self.assertEqual(thread["comments"], self.rows[thread["id"]])
        self.assertNotIn("eligible", result)
        self.assertNotIn("merge_authorized", result)

    def test_empty_inventory_is_not_review_approval(self):
        self.rows = {key: [] for key in ("reviews","comments","reviewThreads","closingIssuesReferences")}
        result = self.collect()
        self.assertEqual(len(self.calls), 8)
        self.assertEqual(result["inventory"]["reviews"], [])
        self.assertNotIn("eligible", result)

    def test_partial_graphql_errors_cannot_be_accepted(self):
        self.mutate = lambda k,c,d: d.update(errors=[{"message":"private-fixture-token"}])
        self.rejected("GraphQL response is incomplete")

    def test_repository_mismatch_rejected(self):
        self.mutate = lambda k,c,d: d["data"]["repository"].update(databaseId=13)
        self.rejected("repository identity differs")

    def test_same_head_another_pr_identity_on_later_page_rejected(self):
        def mutate(k,c,d):
            if c:
                d["data"]["repository"]["pullRequest"]["databaseId"] = 99
        self.mutate = mutate
        self.rejected("PR identity changed")

    def test_head_changes_between_observations_rejected(self):
        def mutate(k,c,d):
            if self.snapshots == 2:
                d["data"]["repository"]["pullRequest"]["headRefOid"] = "c"*40
        self.mutate = mutate
        self.rejected("exact open same-repository main target")

    def test_same_count_body_edit_on_second_observation_rejected(self):
        def mutate(k,c,d):
            if self.snapshots == 2 and k == "threadComments":
                self.connection(k,d)["nodes"][0]["body"] = "changed"
        self.mutate = mutate
        self.rejected("content changed")

    def test_resolved_flag_change_does_not_hide_finding(self):
        def mutate(k,c,d):
            if self.snapshots == 2 and k == "reviewThreads":
                self.connection(k,d)["nodes"][0]["isResolved"] = False
        self.mutate = mutate
        self.rejected("content changed")

    def test_changed_count_rejected(self):
        def mutate(k,c,d):
            if c:
                self.connection(k,d)["totalCount"] = 3
        self.mutate = mutate
        self.rejected("count changed")

    def test_truncated_connection_rejected(self):
        self.mutate = lambda k,c,d: self.connection(k,d)["pageInfo"].update(hasNextPage=False)
        self.rejected("truncated")

    def test_duplicate_node_across_pages_rejected(self):
        def mutate(k,c,d):
            if c:
                self.connection(k,d)["nodes"][0]["id"] = "R_1"
        self.mutate = mutate
        self.rejected("repeats an object")

    def test_duplicate_database_identity_across_pages_rejected(self):
        def mutate(k,c,d):
            if c:
                self.connection(k,d)["nodes"][0]["databaseId"] = 101
        self.mutate = mutate
        self.rejected("repeats a database identity")

    def test_cursor_loop_rejected(self):
        self.rows["reviews"].append({**self.rows["reviews"][1], "id":"R_3", "databaseId":103})
        def mutate(k,c,d):
            if c:
                self.connection(k,d)["pageInfo"]["endCursor"] = "1"
        self.mutate = mutate
        self.rejected("cursor does not advance")

    def test_nested_comments_cannot_switch_thread(self):
        def mutate(k,c,d):
            if k == "threadComments":
                d["data"]["node"]["id"] = "OTHER"
        self.mutate = mutate
        self.rejected("nested thread identity differs")

    def test_nested_comments_must_match_pr(self):
        def mutate(k,c,d):
            if k == "threadComments":
                self.connection(k,d)["nodes"][0]["pullRequest"]["databaseId"] = 999
        self.mutate = mutate
        self.rejected("comment belongs to another PR")

    def test_nested_count_must_match_parent_thread_inventory(self):
        def mutate(k,c,d):
            if k == "threadComments":
                self.connection(k,d)["totalCount"] = 3
        self.mutate = mutate
        self.rejected("count changed")

    def test_comment_review_must_be_in_complete_inventory(self):
        def mutate(k,c,d):
            if k == "threadComments":
                self.connection(k,d)["nodes"][0]["pullRequestReview"]["id"] = "UNKNOWN"
        self.mutate = mutate
        self.rejected("thread review is absent")

    def test_read_budget_is_shared_by_all_nested_connections_and_both_passes(self):
        collector = ReviewInventory(self.client)
        collector.MAX_CALLS = 13
        with self.assertRaisesRegex(ReviewInventoryError, "read budget exhausted"):
            collector.collect(12,42,self.head)
        self.assertEqual(len(self.calls), 13)

    def test_numeric_comment_identity_cannot_appear_in_multiple_threads(self):
        self.rows["T_2"][0]["databaseId"] = self.rows["T_1"][0]["databaseId"]
        self.rejected("comment database identity appears in multiple threads")

    def test_transport_errors_are_secret_safe(self):
        def fail(*args):
            raise RuntimeError("private-fixture-token")
        self.client = GitHubClient(http_transport=fail)
        self.rejected("API unavailable")

    def test_query_interface_rejects_arbitrary_query_without_network(self):
        for kind in ("mutation", "reviewThreads) { viewer { login } }", None, {}):
            with self.subTest(kind=kind), self.assertRaises(ReviewInventoryError):
                self.client.get_release_review_page(42, kind)
        self.assertEqual(self.calls, [])

    def test_duplicate_json_keys_rejected_by_real_client(self):
        client = GitHubClient(http_transport=lambda *args:HttpResponse(200,{},b'{"data":null,"data":{}}'))
        with self.assertRaisesRegex(GitHubApiError,"duplicate JSON fields"):
            client.get_release_review_page(42,"reviews")


if __name__ == "__main__":
    unittest.main(verbosity=2)
