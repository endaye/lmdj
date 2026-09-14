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
                    {"id": "T", "isResolved": self.resolved, "comments": {"nodes": [{"databaseId": 70, "path": "src/example.py", "author": {"databaseId": 20}}]}}])}}}}
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


class BatchPlatform(Platform):
    """Two original authenticated findings plus independent live thread states."""
    def __init__(self):
        super().__init__()
        self.history.pull["head"]["sha"] = history.A
        self.history.render_v2([
            {"path": "src/example.py", "line": 2, "body": "Return value must be two."},
            {"path": "src/example.py", "line": 2, "body": "Returning one loses the second item."}])
        self.history.pull["head"]["sha"] = "c" * 40
        self.states, self.thread_comments = {}, {}
        for comment_id in (70, 71):
            thread = "T" + str(comment_id)
            self.states[thread] = False
            self.thread_comments[thread] = [{**deepcopy(self.root), "id": "C" + str(comment_id),
                "databaseId": comment_id, "body": self.history.inline_details[comment_id]["body"]}]
        self.extra_threads = []
        self.reads = []
        self.after_batch_reply = None

    def _request(self, method, path, *, body=None, raw=False):
        self.reads.append((method, path))
        if path == "/graphql":
            q, v = body["query"], body["variables"]
            if q == recheck.THREADS:
                rows = [{"id": t, "isResolved": resolved,
                         "comments": {"nodes": [{"databaseId": int(t[1:]), "path": "src/example.py", "author": {"databaseId": 20}}]}}
                        for t, resolved in self.states.items()] + self.extra_threads
                return {"data": {"repository": {"pullRequest": {"reviewThreads": self.connection(rows)}}}}
            thread = v["thread"]
            if q == recheck.COMMENTS:
                return {"data": {"node": {"id": thread, "comments": self.connection(self.thread_comments[thread])}}}
            if q == recheck.STATE:
                return {"data": {"node": {"id": thread, "isResolved": self.states[thread],
                    "pullRequest": {"number": 7, "repository": {"nameWithOwner": history.REPO}}}}}
            assert q.startswith("mutation")
            operation = "unresolveReviewThread" if "unresolveReviewThread" in q else "resolveReviewThread"
            self.states[thread] = operation == "resolveReviewThread"
            self.writes.append((operation, thread))
            return {"data": {operation: {"thread": {"id": thread, "isResolved": self.states[thread]}}}}
        if method == "POST" and path.endswith("/replies"):
            comment_id = int(path.split("/")[-2])
            thread = "T" + str(comment_id)
            self.writes.append(("reply", thread))
            self.thread_comments[thread].append({**deepcopy(self.root), "id": "reply" + str(comment_id),
                "databaseId": comment_id + 1000, "body": body["body"]})
            if self.after_batch_reply:
                self.after_batch_reply(thread)
            return {"id": comment_id + 1000}
        return super()._request(method, path, body=body, raw=raw)

    def collect_batch(self):
        requests, report = recheck.collect_batch(self, self.document, git=self.git, fetch=lambda ref: None)
        recheck.attach_batch(self.document, requests)
        return requests, report

    def native(self):
        review = native_fixture()["review"]
        verdict = review.pop("repair_recheck")
        review["repair_rechecks"] = [{**verdict, "comment_id": r["comment_id"]}
                                     for r in self.document["repair_requests"]]
        return {"review": review}

    def publish_batch(self, native=None, record=None):
        return recheck.publish_batch(self, self.document, native or self.native(),
                                    git=self.git, fetch=lambda ref: None, record=record)


class BatchRecheckTests(unittest.TestCase):
    def setUp(self):
        self.api = BatchPlatform()
        self.addCleanup(self.api.history.source.tearDown)

    def test_batch_resolves_each_authenticated_thread_and_retries_without_duplicate_reply(self):
        requests, report = self.api.collect_batch()
        self.assertEqual([r["comment_id"] for r in requests], [70, 71])
        self.assertEqual([r["status"] for r in report["candidates"]], ["collected", "collected"])
        result = self.api.publish_batch()
        self.assertEqual(self.api.states, {"T70": True, "T71": True})
        self.assertEqual(self.api.publish_batch(), result)
        self.assertEqual(self.api.writes, [("reply", "T70"), ("resolveReviewThread", "T70"),
                                          ("reply", "T71"), ("resolveReviewThread", "T71")])

    def test_shared_original_artifact_is_downloaded_once_per_collection(self):
        self.api.collect_batch()
        downloads = [p for m, p in self.api.reads if p.endswith("/zip")]
        self.assertEqual(len(set(downloads)), 1)
        self.assertEqual(len(downloads), 1)

    def test_human_and_resolved_threads_are_excluded(self):
        self.api.states["T71"] = True
        self.api.extra_threads = [{"id": "human", "isResolved": False,
            "comments": {"nodes": [{"databaseId": 90, "path": "src/example.py", "author": {"databaseId": 10}}]}}]
        requests, _ = self.api.collect_batch()
        self.assertEqual([r["comment_id"] for r in requests], [70])
        self.api.publish_batch()
        self.assertEqual(self.api.writes, [("reply", "T70"), ("resolveReviewThread", "T70")])

    def test_no_candidates_preserves_ordinary_review(self):
        self.api.states = {t: True for t in self.api.states}
        self.assertEqual(self.api.collect_batch()[0], [])
        native = native_fixture()
        del native["review"]["repair_recheck"]
        engine._validate_native_mapping(native, engine.authenticate_input(self.api.document))
        self.assertEqual(self.api.publish_batch(native), {"receipts": []})
        self.assertEqual(self.api.writes, [])

    def test_invalid_original_is_reported_without_resolving(self):
        self.api.history.inline_details[70]["body"] = "forged body"
        requests, report = self.api.collect_batch()
        self.assertEqual(requests, [])
        self.assertTrue(all(r["status"] == "not_rechecked" for r in report["candidates"]))
        self.assertEqual(self.api.writes, [])

    def test_unchanged_source_is_reported_without_paid_recheck_context(self):
        git = self.api.git
        self.api.git = lambda *args: b"" if args[0] == "diff" else git(*args)
        requests, report = self.api.collect_batch()
        self.assertEqual(requests, [])
        self.assertTrue(all("unchanged" in r["reason"] for r in report["candidates"]))

    def test_candidate_bound_reports_overflow_instead_of_silently_truncating(self):
        self.api.extra_threads = [{"id": "T" + str(i), "isResolved": False,
            "comments": {"nodes": [{"databaseId": i, "path": "src/example.py", "author": {"databaseId": 20}}]}}
            for i in (72, 73, 74)]
        # Invalid third/fourth bot roots must consume the authentication bound too.
        original = self.api._request
        def request(method, path, **kwargs):
            if path in ("/repos/endaye/lmdj/pulls/comments/72", "/repos/endaye/lmdj/pulls/comments/73"):
                return {"user": {"id": 10}}
            return original(method, path, **kwargs)
        self.api._request = request
        requests, report = self.api.collect_batch()
        self.assertEqual(len(requests), 2)
        self.assertEqual(report["candidates"][-1]["status"], "deferred")
        self.assertEqual(report["candidates"][-1]["comment_id"], 74)

    def test_combined_context_overflow_is_deferred_with_manual_remedy(self):
        git = self.api.git
        self.api.git = lambda *args: (git(*args) + b"# " + b"x" * 600000 + b"\n") if args[0] == "show" else git(*args)
        requests, report = self.api.collect_batch()
        self.assertEqual(len(requests), 1)
        self.assertEqual(report["candidates"][1]["status"], "deferred")
        self.assertIn("manual", report["candidates"][1]["reason"])

    def test_missing_duplicate_or_foreign_verdict_cannot_publish_any_thread(self):
        self.api.collect_batch()
        for mutation in (lambda v: v.pop(), lambda v: v.append(v[0]), lambda v: v[0].update(comment_id=900)):
            native = self.api.native()
            mutation(native["review"]["repair_rechecks"])
            with self.assertRaisesRegex(engine.EngineError, "inventory"):
                self.api.publish_batch(native)
        self.assertEqual(self.api.writes, [])

    def test_nonresolved_sibling_stays_open(self):
        self.api.collect_batch()
        native = self.api.native()
        native["review"]["repair_rechecks"][1].update(verdict="insufficient_evidence", original_quote="", current_quote="", start_line=0, end_line=0)
        self.api.publish_batch(native)
        self.assertEqual(self.api.states, {"T70": True, "T71": False})

    def test_partial_publication_keeps_receipt_and_retry_reconciles_first_thread(self):
        self.api.collect_batch()
        receipts = []
        original = self.api._request
        def refuse_second(method, path, **kwargs):
            if path == "/graphql" and kwargs["body"].get("variables", {}).get("thread") == "T71":
                raise recheck.Refused("temporary second-thread read refusal")
            return original(method, path, **kwargs)
        self.api._request = refuse_second
        with self.assertRaisesRegex(recheck.Refused, "second-thread"):
            self.api.publish_batch(record=lambda r: receipts.append(deepcopy(r)))
        self.assertEqual([r["comment_id"] for r in receipts[-1]["receipts"]], [70])
        self.assertEqual(self.api.states, {"T70": True, "T71": False})
        self.api._request = original
        self.api.publish_batch()
        self.assertEqual(self.api.writes.count(("reply", "T70")), 1)
        self.assertEqual(self.api.states, {"T70": True, "T71": True})

    def test_new_head_after_first_reply_prevents_all_resolutions(self):
        self.api.collect_batch()
        self.api.after_batch_reply = lambda thread: self.api.history.pull["head"].update(sha="d" * 40)
        with self.assertRaisesRegex(recheck.Refused, "different head"):
            self.api.publish_batch()
        self.assertFalse(any(self.api.states.values()))

    def test_batch_input_rejects_mixed_single_and_batch_modes(self):
        requests, _ = self.api.collect_batch()
        self.api.document["repair_request"] = requests[0]
        with self.assertRaisesRegex(engine.EngineError, "mixed"):
            recheck.reseal(self.api.document)

    def test_batch_input_rejects_duplicate_threads(self):
        requests, _ = self.api.collect_batch()
        requests[1]["thread_id"] = requests[0]["thread_id"]
        with self.assertRaisesRegex(engine.EngineError, "duplicate"):
            recheck.attach_batch(self.api.document, requests)

    def test_batch_input_enforces_total_bytes_not_only_individual_request_bound(self):
        requests, _ = self.api.collect_batch()
        files = engine.authenticate_input(self.api.document)["files"]
        for request in requests:
            request["body"] = "x" * 300000
            request["conversation"][0]["body"] = request["body"]
            engine.validate_repair_request(request, files)
        with self.assertRaisesRegex(engine.EngineError, "bound"):
            recheck.attach_batch(self.api.document, requests)

    def test_batch_discovery_refuses_incomplete_thread_inventory(self):
        self.api.truncate = True
        with self.assertRaisesRegex(recheck.Refused, "truncated"):
            self.api.collect_batch()
        self.assertEqual(self.api.writes, [])

    def test_repair_source_numbers_context_lines_outside_the_pr_right_inventory(self):
        self.api.collect_batch()
        auth = engine.authenticate_input(self.api.document)
        blocks = engine.repair_source_blocks(auth)
        self.assertEqual(len(blocks), 1)  # two threads in one file share its source
        payload = json.loads(blocks[0].split("\n", 2)[1])
        self.assertEqual(payload["lines"][0], {"line": 1, "text": "def value():"})
        right = {line for file in auth["files"] for hunk in file["hunks"] for line in hunk["right_lines"]}
        self.assertNotIn(1, right)
        self.assertIn(blocks[0], engine.render_prompt_input(auth))

    def test_missing_numbered_repair_source_refuses_complete_coverage(self):
        self.api.collect_batch()
        auth = engine.authenticate_input(self.api.document)
        prompt = engine.render_prompt_input(auth).replace(engine.repair_source_blocks(auth)[0], "")
        coverage = engine._make_coverage(auth, provider="deepseek", model={}, prompt=prompt, usage=None)
        self.assertFalse(coverage["complete"])

    def test_each_request_must_reach_prompt_coverage(self):
        self.api.collect_batch()
        auth = engine.authenticate_input(self.api.document)
        prompt = engine.render_prompt_input(auth)
        prompt = prompt.replace(engine.repair_prompt_block(auth["repair_requests"][1]), "")
        coverage = engine._make_coverage(auth, provider="deepseek", model={}, prompt=prompt, usage=None)
        self.assertFalse(coverage["complete"])


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
