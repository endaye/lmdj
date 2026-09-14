"""Far-side recheck journey with authentic review artifacts and strict API shapes."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]
import ci_review_wait_test as history
import pr_agent_review as engine
import review_recheck as recheck


def request_fixture():
    return {"comment_id": 70, "thread_id": "T", "original_head": "a" * 40,
            "path": "src/example.py", "original_line": 2, "body": "Return value must be two.",
            "original_content": "def value():\n    return 1\n", "fix_diff": "@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return 2\n",
            "conversation": [{"id": 70, "author_id": 20, "body": "Return value must be two.", "updated_at": "2026-09-14T00:00:00Z"}]}


def native_fixture():
    return {"review": {"general_comments": "The changed return value is two.", "key_issues_to_review": [],
            "repair_recheck": {"comment_id": 70, "verdict": "resolved", "reason": "The return literal is now two, as required by the original finding.",
                               "original_quote": "    return 1", "current_quote": "    return 2", "start_line": 2, "end_line": 2}}}


class Platform:
    """Real wait reader consumes retained publisher output; only HTTP/Git are seams."""
    def __init__(self):
        self.history = history.AdmissionTests()
        self.history.setUp()
        self.history.render_v2([{"path": "src/example.py", "line": 2, "body": "Return value must be two."}])
        self.document = json.loads((ROOT / "tests/fixtures/ci/pr-agent/complete-input.json").read_text())
        self.document["identity"].update(pull_request=7, head_sha="c" * 40)
        self.document.pop("input_sha256")
        self.document["input_sha256"] = recheck.digest(self.document)
        self.history.pull["head"]["sha"] = "c" * 40
        self.root = {"id": "C70", "databaseId": 70, "body": self.history.inline_details[70]["body"],
                     "updatedAt": "2026-09-14T00:00:00Z", "author": {"login": "github-actions", "databaseId": 20}}
        self.comments = [deepcopy(self.root)]
        self.resolved = False
        self.writes = []
        self.after_reply = None
        self.after_resolve = None
        self.unknown_reply = False
        self.unknown_resolve = False
        self.truncate = False

    def connection(self, rows):
        return {"nodes": deepcopy(rows), "totalCount": len(rows) + int(self.truncate),
                "pageInfo": {"hasNextPage": False, "endCursor": None}}

    def _request(self, method, path, *, body=None, raw=False):
        if path == "/graphql":
            assert method == "POST"
            q, v = body["query"], body["variables"]
            if q == recheck.THREADS:
                return {"data": {"repository": {"pullRequest": {"reviewThreads": self.connection([
                    {"id": "T", "comments": {"nodes": [{"databaseId": 70}]}}])}}}}
            if q == recheck.COMMENTS:
                return {"data": {"node": {"id": "T", "comments": self.connection(self.comments)}}}
            if q == recheck.STATE:
                return {"data": {"node": {"id": "T", "isResolved": self.resolved,
                        "pullRequest": {"number": 7, "repository": {"nameWithOwner": history.REPO}}}}}
            assert q.startswith("mutation") and v == {"thread": "T"}
            operation = "unresolveReviewThread" if "unresolveReviewThread" in q else "resolveReviewThread"
            self.resolved = operation == "resolveReviewThread"
            self.writes.append(operation)
            if self.resolved and self.after_resolve:
                self.after_resolve()
            if self.resolved and self.unknown_resolve:
                raise OSError("response lost after accepted mutation")
            return {"data": {operation: {"thread": {"id": "T", "isResolved": self.resolved}}}}
        if path == "/repos/endaye/lmdj/pulls/7/comments/70/replies":
            assert method == "POST" and set(body) == {"body"}
            self.writes.append("reply")
            self.comments.append({**deepcopy(self.root), "id": "C71", "databaseId": 71, "body": body["body"]})
            if self.after_reply:
                self.after_reply()
            if self.unknown_reply:
                raise OSError("response lost after accepted reply")
            return {"id": 71}
        if path == "/repos/endaye/lmdj/pulls/7/reviews/60":
            return deepcopy(self.history.reviews[0])
        return self.history._request(method, path, raw=raw)

    def git(self, *args):
        if args == ("merge-base", history.A, "c" * 40):
            return (history.A + "\n").encode()
        if args == ("show", history.A + ":src/example.py"):
            return request_fixture()["original_content"].encode()
        if args == ("diff", "--full-index", "--no-ext-diff", "--no-textconv", "--no-renames", "--unified=3", history.A, "c" * 40, "--", "src/example.py"):
            return request_fixture()["fix_diff"].encode()
        raise AssertionError(args)

    def collect(self):
        request = recheck.collect(self, self.document, 70, git=self.git, fetch=lambda ref: None)
        recheck.attach(self.document, request)
        return request

    def publish(self, native=None):
        return recheck.publish(self, self.document, native or native_fixture(), git=self.git, fetch=lambda ref: None)


class RecheckTests(unittest.TestCase):
    def setUp(self):
        self.api = Platform()
        self.addCleanup(self.api.history.source.tearDown)

    def test_collected_artifact_reaches_validated_verdict_and_idempotent_resolved_far_side(self):
        request = self.api.collect()
        auth = engine.authenticate_input(self.api.document)
        self.assertIn(recheck.engine.repair_prompt_block(request), engine.render_prompt_input(auth))
        self.assertEqual(engine.validate_repair_verdict(native_fixture(), auth)["verdict"], "resolved")
        result = self.api.publish()
        self.assertTrue(result["resolved"])
        self.assertTrue(self.api.resolved)
        self.assertEqual(self.api.writes, ["reply", "resolveReviewThread"])
        self.assertEqual(self.api.publish(), result)
        self.assertEqual(self.api.writes, ["reply", "resolveReviewThread"])

    def test_historical_run_accepts_live_pr_association_head_after_fix(self):
        # GitHub refreshes this associated PR object after a synchronize event;
        # the run's own head_sha and retained artifact still identify the review.
        self.api.history.source.run["pull_requests"][0]["head"]["sha"] = "c" * 40
        request = self.api.collect()
        self.assertEqual(request["original_head"], history.A)
        self.assertEqual(self.api.history.source.run["head_sha"], history.A)
        self.assertTrue(self.api.publish()["resolved"])
        self.assertTrue(self.api.resolved)
        self.assertEqual(self.api.writes, ["reply", "resolveReviewThread"])

    def test_fix_diff_is_identical_across_git_object_abbreviation_settings(self):
        with tempfile.TemporaryDirectory(prefix="lmdj-recheck-git-") as temporary:
            repo = Path(temporary)
            def command(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)
            command("-c", "init.defaultBranch=main", "init", "--quiet")
            source = repo / "src/example.py"
            source.parent.mkdir()
            revisions = []
            for content in (request_fixture()["original_content"], "def value():\n    return 2\n"):
                source.write_text(content)
                command("add", "src/example.py")
                command("-c", "user.name=Recheck Test", "-c", "user.email=recheck@example.invalid",
                        "commit", "--quiet", "-m", "source fixture")
                revisions.append(command("rev-parse", "HEAD").decode().strip())
            original_git = self.api.git
            def collect_with(abbreviation):
                def git(*args):
                    if args[0] == "diff":
                        mapped = [revisions[0] if a == history.A else revisions[1] if a == "c" * 40 else a for a in args]
                        return command("-c", "core.abbrev=" + abbreviation, *mapped)
                    return original_git(*args)
                return recheck.collect(self.api, self.api.document, 70, git=git, fetch=lambda ref: None)
            short, long = collect_with("8"), collect_with("12")
            self.assertEqual(short, long)
            self.assertRegex(short["fix_diff"], r"index [0-9a-f]{40}\.\.[0-9a-f]{40} 100644")
            self.assertIn("-    return 1\n+    return 2\n", short["fix_diff"])

    def test_nonresolved_verdict_explains_and_keeps_thread_open(self):
        self.api.collect()
        for value in ("unresolved", "insufficient_evidence"):
            native = native_fixture()
            native["review"]["repair_recheck"].update(verdict=value, original_quote="", current_quote="", start_line=0, end_line=0)
            self.api.comments = [deepcopy(self.api.root)]
            result = self.api.publish(native)
            self.assertFalse(result["resolved"])
            self.assertFalse(self.api.resolved)
        self.assertEqual(self.api.writes, ["reply", "reply"])

    def test_human_root_is_refused_before_model(self):
        self.api.history.inline_details[70]["user"] = {"id": 10, "login": "endaye"}
        with self.assertRaisesRegex(recheck.Refused, "original bot"):
            self.api.collect()
        self.assertEqual(self.api.writes, [])

    def test_forged_bot_body_cannot_pass_retained_artifact_authentication(self):
        self.api.history.inline_details[70]["body"] = "forged finding"
        with self.assertRaises(ValueError):
            self.api.collect()
        self.assertEqual(self.api.writes, [])

    def test_truncated_inventory_never_resolves(self):
        self.api.truncate = True
        with self.assertRaisesRegex(recheck.Refused, "truncated"):
            self.api.collect()
        self.assertFalse(self.api.resolved)

    def test_original_thread_on_second_page_is_collected(self):
        original_request = self.api._request
        def paged(method, path, *, body=None, raw=False):
            if path == "/graphql" and body["query"] == recheck.THREADS:
                second = body["variables"]["cursor"] == "next"
                rows = ([{"id": "T", "comments": {"nodes": [{"databaseId": 70}]}}] if second else
                        [{"id": f"T{i}", "comments": {"nodes": [{"databaseId": 1000+i}]}} for i in range(100)])
                return {"data": {"repository": {"pullRequest": {"reviewThreads": {
                    "nodes": rows, "totalCount": 101, "pageInfo": {"hasNextPage": not second, "endCursor": "next" if not second else None}}}}}}
            return original_request(method, path, body=body, raw=raw)
        self.api._request = paged
        self.assertEqual(self.api.collect()["thread_id"], "T")

    def test_conversation_second_page_survives_reply_and_retry(self):
        self.api.comments.extend({**deepcopy(self.api.root), "id": f"C{i}", "databaseId": i, "body": f"context {i}"}
                                 for i in range(100, 200))
        original_request = self.api._request
        def paged(method, path, *, body=None, raw=False):
            if path == "/graphql" and body["query"] == recheck.COMMENTS:
                second = body["variables"]["cursor"] == "next"
                rows = deepcopy(self.api.comments[100:] if second else self.api.comments[:100])
                return {"data": {"node": {"comments": {"nodes": rows, "totalCount": len(self.api.comments),
                    "pageInfo": {"hasNextPage": not second, "endCursor": "next" if not second else None}}}}}
            return original_request(method, path, body=body, raw=raw)
        self.api._request = paged
        self.assertEqual(len(self.api.collect()["conversation"]), 101)
        self.assertTrue(self.api.publish()["resolved"])
        self.assertTrue(self.api.publish()["resolved"])
        self.assertEqual(len(self.api.comments), 102)
        self.assertEqual(self.api.writes, ["reply", "resolveReviewThread"])

    def test_edited_comment_invalidates_captured_input(self):
        self.api.collect()
        self.api.comments.append({**deepcopy(self.api.root), "id": "C90", "databaseId": 90, "body": "new concern"})
        with self.assertRaisesRegex(recheck.Refused, "changed since"):
            self.api.publish()
        self.assertEqual(self.api.writes, [])

    def test_stale_head_prevents_all_writes(self):
        self.api.collect()
        self.api.history.pull["head"]["sha"] = "d" * 40
        with self.assertRaisesRegex(recheck.Refused, "different head"):
            self.api.publish()
        self.assertEqual(self.api.writes, [])

    def test_missing_verdict_from_older_engine_never_resolves(self):
        self.api.collect()
        native = native_fixture()
        del native["review"]["repair_recheck"]
        with self.assertRaisesRegex(engine.EngineError, "missing or malformed"):
            self.api.publish(native)
        self.assertEqual(self.api.writes, [])

    def test_original_quote_must_cover_the_authenticated_finding_line(self):
        self.api.collect()
        native = native_fixture()
        native["review"]["repair_recheck"]["original_quote"] = "def value():"
        with self.assertRaisesRegex(engine.EngineError, "finding anchor"):
            self.api.publish(native)
        self.assertEqual(self.api.writes, [])

    def test_fabricated_current_quote_fails_before_write(self):
        self.api.collect()
        native = native_fixture()
        native["review"]["repair_recheck"]["current_quote"] = "return 42"
        with self.assertRaisesRegex(engine.EngineError, "differs from exact head"):
            self.api.publish(native)
        self.assertEqual(self.api.writes, [])

    def test_absence_from_new_review_does_not_substitute_for_changed_source(self):
        self.api.collect()
        native = native_fixture()
        native["review"]["repair_recheck"].update(current_quote="def value():", start_line=1, end_line=1)
        with self.assertRaisesRegex(engine.EngineError, "intervening source change"):
            self.api.publish(native)
        self.assertEqual(self.api.writes, [])

    def test_lost_reply_response_reconciles_without_duplicate(self):
        self.api.collect()
        self.api.unknown_reply = True
        self.assertTrue(self.api.publish()["resolved"])
        self.assertEqual(self.api.writes, ["reply", "resolveReviewThread"])

    def test_lost_resolve_response_reconciles_observed_state(self):
        self.api.collect()
        self.api.unknown_resolve = True
        self.assertTrue(self.api.publish()["resolved"])
        self.assertEqual(self.api.writes, ["reply", "resolveReviewThread"])

    def test_head_moves_after_reply_leaves_thread_open(self):
        self.api.collect()
        self.api.after_reply = lambda: self.api.history.pull["head"].update(sha="d" * 40)
        with self.assertRaisesRegex(recheck.Refused, "different head"):
            self.api.publish()
        self.assertFalse(self.api.resolved)
        self.assertEqual(self.api.writes, ["reply"])

    def test_head_moves_after_resolve_compensates_and_observes_open_state(self):
        self.api.collect()
        self.api.after_resolve = lambda: self.api.history.pull["head"].update(sha="d" * 40)
        with self.assertRaisesRegex(recheck.Refused, "different head"):
            self.api.publish()
        self.assertFalse(self.api.resolved)
        self.assertEqual(self.api.writes, ["reply", "resolveReviewThread", "unresolveReviewThread"])

    def test_new_concern_after_resolve_compensates(self):
        self.api.collect()
        self.api.after_resolve = lambda: self.api.comments.append({**deepcopy(self.api.root), "id": "C90", "databaseId": 90, "body": "new concern"})
        with self.assertRaisesRegex(recheck.Refused, "conversation changed"):
            self.api.publish()
        self.assertFalse(self.api.resolved)

    def test_missing_recheck_context_in_actual_prompt_is_incomplete_coverage(self):
        self.api.collect()
        auth = engine.authenticate_input(self.api.document)
        prompt = engine.render_prompt_input(auth).replace(engine.repair_prompt_block(auth["repair_request"]), "")
        coverage = engine._make_coverage(auth, provider="deepseek", model={}, prompt=prompt, usage=None)
        self.assertFalse(coverage["complete"])


if __name__ == "__main__":
    unittest.main()
