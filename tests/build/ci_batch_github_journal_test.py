#!/usr/bin/env python3
"""Source-shaped protocol fixtures, not a remote GitHub acceptance rehearsal."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import batch_github_journal as github
from incremental_batch_journal import IssueBodyAnchor, Journal, JournalBlocked

# Read-only observation 2026-09-08: #782/comment5573637240. Bot GraphQL
# login github-actions differs from REST github-actions[bot]; stable node ID
# below is shared. BigInt fullDatabaseId is JSON text. No production body copied.
BOT = {"__typename": "Bot", "id": "MDM6Qm90NDE4OTgyODI="}
PATH = ".github/workflows/self-test-report.yml"
WRITER = {"repository": "endaye/lmdj", "issue_number": 782, "run_id": 17, "run_attempt": 1,
          "control_sha": "a" * 40, "workflow_path": PATH, "workflow_id": 7, "job_name": "Journal writer"}


def wrapped(kind, payload, writer=None):
    return json.dumps({"schema": github.SCHEMA, "kind": kind, "writer": writer or WRITER, "payload": payload})


class FakeApi:
    def __init__(self):
        self.issue = {"number": 782, "id": "fixed-issue-node", "body": wrapped("checkpoint", {"head": None, "pending": None}),
                      "author": deepcopy(BOT), "editor": None, "lastEditedAt": None}
        self.comments = []
        self.calls = []
        self.run_changes = {}
        self.latest_attempt = 1
        self.job_changes = {}
        self.graph_errors = False
        self.truncated = False
        self.missing_cursor = False
        self.transport_error = False
        self.lose_post = False
        self.compare_status = "ahead"
        self.main_sha = "b" * 40
        self.extra_jobs = []
        self.comment_pages = 1

    def comment(self, envelope):
        return {"id": "comment-node", "fullDatabaseId": str(5573637240 + len(self.comments)),
                "body": wrapped("event", envelope), "author": deepcopy(BOT), "editor": None, "lastEditedAt": None}

    def _request(self, method, path, *, body=None, raw=False):
        if raw:
            raise AssertionError("why: raw downloads permit redirects; remedy: JSON-only API")
        self.calls.append((method, path, deepcopy(body)))
        if self.transport_error:
            raise RuntimeError("SECRET-RAW-BODY-MUST-NOT-ESCAPE")
        if method == "POST" and path == "/graphql":
            if self.graph_errors:
                return {"errors": [{"message": "SECRET-RAW-BODY-MUST-NOT-ESCAPE"}], "data": None}
            issue = deepcopy(self.issue)
            if body["query"] == github.COMMENTS_QUERY:
                after = body["variables"]["after"]
                start = int(after or 0)
                nodes = deepcopy(self.comments[start:start + self.comment_pages])
                next_index = start + len(nodes)
                more = next_index < len(self.comments)
                issue["comments"] = {"totalCount": len(self.comments) + int(self.truncated), "nodes": nodes,
                                     "pageInfo": {"hasNextPage": more,
                                                  "endCursor": None if self.missing_cursor else str(next_index)}}
            if body["query"] == github.LAST_QUERY:
                issue["comments"] = {"totalCount": len(self.comments) + int(self.truncated),
                                     "nodes": deepcopy(self.comments[-1:])}
            return {"data": {"repository": {"nameWithOwner": "endaye/lmdj", "issue": issue}}}
        prefix = "/repos/endaye/lmdj"
        if method == "GET" and path in (prefix + "/actions/runs/17", prefix + "/actions/runs/17/attempts/1"):
            return {"id": 17, "run_attempt": 1 if path.endswith("/attempts/1") else self.latest_attempt,
                    "workflow_id": 7, "head_sha": "a" * 40,
                    "head_branch": "main", "path": PATH, "status": "in_progress", "event": "workflow_run",
                    "repository": {"full_name": "endaye/lmdj"}, "head_repository": {"full_name": "endaye/lmdj"},
                    "actor": {"login": "endaye"}, **self.run_changes}
        if method == "GET" and path == prefix + "/actions/workflows/7":
            return {"id": 7, "path": PATH}
        if method == "GET" and path == prefix + "/git/ref/heads/main":
            return {"object": {"sha": self.main_sha}}
        if method == "GET" and path == prefix + f"/compare/{'a' * 40}...{self.main_sha}?per_page=1&page=2":
            return {"status": self.compare_status, "base_commit": {"sha": "a" * 40}, "merge_base_commit": {"sha": "a" * 40}}
        if method == "GET" and path == prefix + f"/contents/{PATH}?ref={'a' * 40}":
            return {"type": "file", "path": PATH, "encoding": "base64", "content": base64.b64encode(b"name: Trusted control\n").decode()}
        jobs_prefix = prefix + "/actions/runs/17/attempts/1/jobs?per_page=100&page="
        if method == "GET" and path.startswith(jobs_prefix):
            page = int(path[len(jobs_prefix):])
            jobs = self.extra_jobs + [{"id": 1001, "run_id": 17, "run_attempt": 1,
                                       "name": "Journal writer", "status": "in_progress", **self.job_changes}]
            return {"total_count": len(jobs), "jobs": jobs[(page - 1) * 100:page * 100]}
        if method == "PATCH" and path == prefix + "/issues/782":
            self.issue.update(body=body["body"], editor=deepcopy(BOT), lastEditedAt="2026-09-08T00:00:00Z")
            return {"number": 782}
        if method == "POST" and path == prefix + "/issues/782/comments":
            document = github.decode(body["body"])
            self.comments.append(self.comment(document["payload"]))
            if self.lose_post:
                raise OSError("SECRET-RAW-BODY-MUST-NOT-ESCAPE")
            return {"id": int(self.comments[-1]["fullDatabaseId"])}
        raise AssertionError("why: fake API received undeclared method/path; remedy: check the exact GitHub endpoint contract")


class GitHubJournalTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.lock = True
        self.transport = github.GitHubJournalTransport(repository="endaye/lmdj", issue_number=782,
            issue_node_id="fixed-issue-node", bot_node_id=BOT["id"], workflows={PATH: 7},
            writer=WRITER, api=self.api, lock_held=lambda: self.lock)
        self.anchor = IssueBodyAnchor(782, self.transport, self.transport.authenticate, lambda: self.lock)
        self.journal = Journal(782, self.transport, self.anchor, self.transport.authenticate, lambda: self.lock)

    def test_writer_ancestry_uses_metadata_page_not_changed_files(self):
        self.assertEqual(self.transport._writer(WRITER), WRITER)
        comparisons = [path for method, path, _ in self.api.calls if '/compare/' in path]
        self.assertEqual(comparisons, [f"/repos/endaye/lmdj/compare/{'a'*40}...{'b'*40}?per_page=1&page=2"])
        self.assertTrue(all(method == 'GET' for method, _, _ in self.api.calls))

    def test_empty_commit_page_preserves_ahead_and_identical_metadata(self):
        for status in ('ahead', 'identical'):
            with self.subTest(status=status):
                self.setUp()
                if status == 'identical':
                    self.api.main_sha = WRITER['control_sha']
                original = self.api._request
                def request(method, path, **kwargs):
                    value = original(method, path, **kwargs)
                    if '/compare/' in path:
                        value.update(status=status, commits=[])
                    return value
                self.api._request = request
                self.assertEqual(self.transport._writer(WRITER), WRITER)

    def test_metadata_page_rejects_invalid_ancestry_without_caching(self):
        for failure in ('behind', 'diverged', 'unknown', 'missing-status',
                        'missing-base', 'wrong-base', 'missing-merge-base', 'wrong-merge-base'):
            with self.subTest(failure=failure):
                self.setUp()
                original = self.api._request
                def request(method, path, **kwargs):
                    value = original(method, path, **kwargs)
                    if '/compare/' in path:
                        if failure == 'missing-status': value.pop('status')
                        elif failure == 'missing-base': value.pop('base_commit')
                        elif failure == 'wrong-base': value['base_commit']['sha'] = 'c'*40
                        elif failure == 'missing-merge-base': value.pop('merge_base_commit')
                        elif failure == 'wrong-merge-base': value['merge_base_commit']['sha'] = 'c'*40
                        else: value['status'] = failure
                    return value
                self.api._request = request
                with self.assertRaisesRegex(JournalBlocked, 'why:.*remedy:'):
                    self.transport._writer(WRITER)
                self.assertFalse(self.transport._checked_writers)
                self.assertTrue(all(method == 'GET' for method, _, _ in self.api.calls))

    def test_failed_metadata_get_is_not_cached_or_retried(self):
        original = self.api._request
        failed = []
        def request(method, path, **kwargs):
            if '/compare/' in path:
                failed.append(path)
                raise OSError('private diagnostic')
            return original(method, path, **kwargs)
        self.api._request = request
        with self.assertRaisesRegex(JournalBlocked, 'why:.*remedy:'):
            self.transport._writer(WRITER)
        self.assertEqual(len(failed), 1)
        self.assertFalse(self.transport._checked_writers)
        self.api._request = original
        self.assertEqual(self.transport._writer(WRITER), WRITER)
        self.assertTrue(all(method == 'GET' for method, _, _ in self.api.calls))

    def multiple_writers(self, ids):
        self.api.comment_pages = 100
        for index, run_id in enumerate(ids):
            node = self.api.comment({"id": str(index)})
            node["body"] = wrapped("event", {"id": str(index)}, {**WRITER, "run_id": run_id})
            self.api.comments.append(node)
        original = self.api._request
        mutex = threading.Lock()

        def request(method, path, **kwargs):
            import re
            match = re.search(r"/actions/runs/(\d+)/attempts/1", path)
            normalized = path if match is None else path.replace(match.group(0), "/actions/runs/17/attempts/1")
            with mutex:
                result = original(method, normalized, **kwargs)
            if match is not None:
                run_id = int(match[1])
                if "jobs?" in path:
                    for job in result["jobs"]:
                        job.update(run_id=run_id, id=1000 + run_id)
                else:
                    result["id"] = run_id
            return result

        self.api._request = request
        return request

    def linked_writer_history(self):
        from incremental_batch import digest
        self.multiple_writers(range(17, 23))
        self.api.comment_pages = 2
        previous = None
        for index, node in enumerate(self.api.comments):
            envelope = {"previous": previous, "event": {"id": str(index)}}
            envelope["digest"] = digest(envelope)
            node["body"] = wrapped("event", envelope, {**WRITER, "run_id": 17 + index})
            previous = envelope["digest"]
        self.api.issue["body"] = wrapped("checkpoint", {"head": previous, "pending": None})

    def test_complete_journal_read_authenticates_each_page_once(self):
        self.linked_writer_history()
        self.journal.load()
        attempt_reads = sum(method == "GET" and path.endswith("/attempts/1")
                            for method, path, _ in self.api.calls)
        self.assertEqual(attempt_reads, 7,
                         "why: earlier pages repeated writer HTTP authentication; "
                         "remedy: verify each page before its transport proofs expire")

    def test_later_page_failure_does_not_publish_verified_prefix(self):
        self.linked_writer_history()
        document = json.loads(self.api.comments[-1]["body"])
        document["payload"]["digest"] = "0" * 64
        self.api.comments[-1]["body"] = json.dumps(document)
        with self.assertRaisesRegex(JournalBlocked, "digest mismatch"):
            self.journal.load()
        self.assertIsNone(self.journal._verified,
                          "why: failed complete read published a partial prefix; "
                          "remedy: commit reuse only after all pages verify")

    def test_page_authentication_overlaps_four_readers_and_keeps_record_order(self):
        request = self.multiple_writers([17, 18, 19, 20, 21, 22, 23, 24])
        barrier = threading.Barrier(4, timeout=5)
        mutex = threading.Lock()
        active = peak = 0

        def synchronized(method, path, **kwargs):
            nonlocal active, peak
            if path.endswith("/attempts/1"):
                with mutex:
                    active += 1
                    peak = max(peak, active)
                try:
                    barrier.wait()
                    return request(method, path, **kwargs)
                finally:
                    with mutex:
                        active -= 1
            return request(method, path, **kwargs)

        self.api._request = synchronized
        owner = threading.get_ident()
        test = self

        class OwnerOnlyCache(set):
            def add(self, value):
                test.assertEqual(threading.get_ident(), owner,
                                 "why: worker changed trust cache; remedy: commit proofs on the caller thread")
                super().add(value)

            def update(self, values):
                test.assertEqual(threading.get_ident(), owner,
                                 "why: worker changed trust cache; remedy: commit proofs on the caller thread")
                super().update(values)

        self.transport._checked_writers = OwnerOnlyCache()
        with patch.object(github, "ThreadPoolExecutor", wraps=github.ThreadPoolExecutor) as pool:
            page = self.transport.page(782, None)
        pool.assert_called_once_with(max_workers=4)
        self.assertEqual(peak, 4, "why: reads are serialized or unbounded; remedy: exactly four bounded workers")
        self.assertEqual([row["provenance"]["run_id"] for row in page["comments"]], list(range(17, 25)),
                         "why: completion order changed journal order; remedy: return original page order")
        self.assertEqual(active, 0, "why: authentication escaped the page boundary; remedy: join every reader")

    def test_duplicate_page_writers_are_authenticated_once(self):
        self.multiple_writers([17, 17, 18, 18])
        self.transport.page(782, None)
        self.assertEqual(sum(path.endswith("/attempts/1") for _, path, _ in self.api.calls), 2,
                         "why: duplicate records repeat provenance reads; remedy: deduplicate complete writer identities")

    def test_hundred_writers_share_control_proof_but_not_run_or_job_proof(self):
        self.multiple_writers(range(17, 117))
        page = self.transport.page(782, None)
        reads = [path for method, path, _ in self.api.calls if method == 'GET']
        self.assertEqual(len(page['comments']), 100)
        self.assertEqual(sum(path.endswith('/attempts/1') for path in reads), 100)
        self.assertEqual(sum('/jobs?' in path for path in reads), 100)
        self.assertEqual(len(reads), 204,
                         'why: shared control reread per writer; remedy: share only the four control proof reads')

    def test_failed_shared_control_is_not_retried_within_page_or_retained(self):
        request = self.multiple_writers([17, 18, 19, 20])
        comparisons = []
        def failing(method, path, **kwargs):
            if '/compare/' in path:
                comparisons.append(path)
                raise OSError('unavailable control metadata')
            return request(method, path, **kwargs)
        self.api._request = failing
        with self.assertRaises(JournalBlocked):
            self.transport.page(782, None)
        self.assertEqual(len(comparisons), 1,
                         'why: one unavailable control caused duplicate requests; remedy: share the failed page result')
        self.assertFalse(self.transport._checked_writers)
        self.api._request = request
        self.assertEqual(len(self.transport.page(782, None)['comments']), 4)

    def diverse_controls(self, count):
        ids = list(range(17, 17 + count))
        request = self.multiple_writers(ids)
        controls = {run_id: f'{run_id:040x}' for run_id in ids}
        for node, run_id in zip(self.api.comments, ids):
            node['body'] = wrapped('event', {'id': str(run_id)},
                {**WRITER, 'run_id': run_id, 'control_sha': controls[run_id]})
        seen = []

        def distinct(method, path, **kwargs):
            seen.append((method, path))
            normalized = path
            for control in controls.values():
                normalized = normalized.replace(control, 'a' * 40)
            value = request(method, normalized, **kwargs)
            if path.endswith('/attempts/1'):
                value['head_sha'] = controls[value['id']]
            if '/compare/' in path:
                control = path.split('/compare/', 1)[1].split('...', 1)[0]
                value['base_commit']['sha'] = control
                value['merge_base_commit']['sha'] = control
            return value

        self.api._request = distinct
        return distinct, seen

    def test_distinct_hundred_controls_share_only_common_page_proofs(self):
        _, seen = self.diverse_controls(100)
        page = self.transport.page(782, None)
        reads = [path for method, path in seen if method == 'GET']
        self.assertEqual(len(page['comments']), 100)
        self.assertEqual(sum(path.endswith('/attempts/1') for path in reads), 100)
        self.assertEqual(sum('/jobs?' in path for path in reads), 100)
        self.assertEqual(len({path for path in reads if '/compare/' in path}), 100)
        self.assertEqual(len({path for path in reads if '/contents/' in path}), 100)
        self.assertEqual(len(reads), 402,
            'why: different controls reread common page identities; remedy: share only validated main/workflow proofs')

    def test_transaction_reuses_immutable_proofs_across_pages_with_same_history(self):
        def read_pages(reuse):
            self.setUp()
            self.multiple_writers([17, 18, 19, 20])
            self.api.comment_pages = 2
            first = self.transport.page(782, None)
            if not reuse:
                # Executable baseline for the prior page-local proof scope.
                self.transport._page_session['control_proofs'] = github._PageControlProofs()
            second = self.transport.page(782, first['next'])
            return (first['comments'] + second['comments'], second['next']), len(self.api.calls)

        before_output, before_calls = read_pages(False)
        after_output, after_calls = read_pages(True)
        self.assertEqual(before_output, after_output)
        self.assertIsNone(after_output[1])
        self.assertEqual([row['provenance']['run_id'] for row in after_output[0]], [17, 18, 19, 20],
                         'why: proof reuse changed the complete journal history; remedy: preserve every page and record order')
        self.assertEqual(before_calls, 18,
                         'why: baseline no longer measures page-local proof requests; remedy: retain the unoptimized comparator')
        self.assertEqual(after_calls, 15,
                         'why: immutable control proofs were repeated across one read transaction; remedy: retain only immutable transaction proofs')

    def test_shared_main_failure_is_single_attempt_and_retry_reauthenticates_page(self):
        request, _ = self.diverse_controls(4)
        failed = []
        def unavailable(method, path, **kwargs):
            if path.endswith('/git/ref/heads/main'):
                failed.append(path)
                raise OSError('private unavailable main')
            return request(method, path, **kwargs)
        self.api._request = unavailable
        with self.assertRaisesRegex(JournalBlocked, 'why:.*remedy:'):
            self.transport.page(782, None)
        self.assertFalse(self.transport._checked_writers)
        self.assertEqual(len(failed), 1,
            'why: page retried a failed shared main read; remedy: share failure only for this page')
        self.api._request = request
        self.assertEqual(len(self.transport.page(782, None)['comments']), 4)

    def test_distinct_controls_use_one_main_even_when_ref_advances(self):
        request, _ = self.diverse_controls(4)
        original_main, advanced = self.api.main_sha, 'd' * 40
        comparisons, refs = [], []
        def moving(method, path, **kwargs):
            if path.endswith('/git/ref/heads/main'):
                refs.append(path)
                value = request(method, path, **kwargs)
                self.api.main_sha = advanced
                return value
            if '/compare/' in path:
                comparisons.append(path)
                # The fake's endpoint matcher follows main; the actual compare
                # endpoint also accepts the now-historical pinned main SHA.
                path = path.replace('...' + original_main, '...' + advanced)
            return request(method, path, **kwargs)
        self.api._request = moving
        self.transport.page(782, None)
        self.assertEqual(len(refs), 1)
        self.assertEqual(len(comparisons), 4)
        self.assertTrue(all('...' + original_main + '?' in path for path in comparisons),
            'why: one page mixed main observations; remedy: compare every control to the captured page main')

    def test_control_newer_than_page_main_cannot_refresh_its_way_to_trust(self):
        request, _ = self.diverse_controls(2)
        original_main, advanced = self.api.main_sha, 'd' * 40
        refs = []
        def moving(method, path, **kwargs):
            if path.endswith('/git/ref/heads/main'):
                refs.append(path)
                value = request(method, path, **kwargs)
                self.api.main_sha = advanced
                return value
            if '/compare/' in path:
                value = request(method, path.replace('...' + original_main, '...' + advanced), **kwargs)
                if f'/compare/{18:040x}...{original_main}' in path:
                    value['status'] = 'behind'
                return value
            return request(method, path, **kwargs)
        self.api._request = moving
        with self.assertRaisesRegex(JournalBlocked, 'main history'):
            self.transport.page(782, None)
        self.assertFalse(self.transport._checked_writers)
        self.assertEqual(len(refs), 1,
            'why: stale page main was silently replaced; remedy: fail the entire page and retry independently')

    def test_different_workflows_have_separate_common_identity_proofs(self):
        request, _ = self.diverse_controls(2)
        other_path = '.github/workflows/other-writer.yml'
        self.transport.workflows[other_path] = 8
        document = github.decode(self.api.comments[1]['body'])
        document['writer'].update(workflow_path=other_path, workflow_id=8)
        self.api.comments[1]['body'] = json.dumps(document)
        workflows = []
        def other(method, path, **kwargs):
            if '/actions/workflows/' in path:
                workflows.append(path)
                if path.endswith('/8'):
                    return {'id': 8, 'path': other_path}
            value = request(method, path.replace(other_path, PATH), **kwargs)
            if path.endswith('/runs/18/attempts/1'):
                value.update(workflow_id=8, path=other_path)
            if '/contents/' + other_path in path:
                value['path'] = other_path
            return value
        self.api._request = other
        self.assertEqual(len(self.transport.page(782, None)['comments']), 2)
        self.assertEqual(sorted(workflows), ['/repos/endaye/lmdj/actions/workflows/7',
                                           '/repos/endaye/lmdj/actions/workflows/8'])

    def test_malformed_common_proof_blocks_all_writers_and_is_not_retained(self):
        for endpoint in ('main', 'workflow'):
            with self.subTest(endpoint=endpoint):
                self.setUp()
                request, _ = self.diverse_controls(4)
                paths = []
                def malformed(method, path, **kwargs):
                    value = request(method, path, **kwargs)
                    if ((endpoint == 'main' and path.endswith('/git/ref/heads/main')) or
                            (endpoint == 'workflow' and '/actions/workflows/' in path)):
                        paths.append(path)
                        return {'object': {'sha': 'not-a-sha'}} if endpoint == 'main' else {'id': 8, 'path': PATH}
                    return value
                self.api._request = malformed
                with self.assertRaisesRegex(JournalBlocked, 'why:.*remedy:'):
                    self.transport.page(782, None)
                self.assertEqual(len(paths), 1)
                self.assertFalse(self.transport._checked_writers)
                self.api._request = request
                self.assertEqual(len(self.transport.page(782, None)['comments']), 4)

    def test_later_page_reuses_pinned_main_but_refreshes_workflow_identity(self):
        for endpoint in ('main', 'workflow'):
            with self.subTest(endpoint=endpoint):
                self.setUp()
                request, _ = self.diverse_controls(2)
                self.api.comment_pages = 1
                first = self.transport.page(782, None)
                before = len(self.api.calls)
                def changed(method, path, **kwargs):
                    value = request(method, path, **kwargs)
                    if endpoint == 'main' and path.endswith('/git/ref/heads/main'):
                        return {'object': {'sha': None}}
                    if endpoint == 'workflow' and '/actions/workflows/' in path:
                        return {'id': 7, 'path': '.github/workflows/renamed.yml'}
                    return value
                self.api._request = changed
                if endpoint == 'workflow':
                    with self.assertRaisesRegex(JournalBlocked, 'workflow API identity'):
                        self.transport.page(782, first['next'])
                    self.assertEqual(sum('/actions/workflows/' in path for _, path, _ in self.api.calls[before:]), 1)
                else:
                    second = self.transport.page(782, first['next'])
                    self.assertIsNone(second['next'])
                    self.assertFalse(any(path.endswith('/git/ref/heads/main')
                                         for _, path, _ in self.api.calls[before:]),
                                     'why: immutable main proof was repeated; remedy: retain the pinned proof')

    def test_one_bad_distinct_control_proof_discards_whole_page_trust(self):
        for endpoint in ('source', 'ancestry'):
            with self.subTest(endpoint=endpoint):
                self.setUp()
                request, _ = self.diverse_controls(4)
                def invalid(method, path, **kwargs):
                    value = request(method, path, **kwargs)
                    if f'{18:040x}' in path:
                        if endpoint == 'source' and '/contents/' in path:
                            value['content'] = ''
                        if endpoint == 'ancestry' and '/compare/' in path:
                            value['merge_base_commit']['sha'] = 'f' * 40
                    return value
                self.api._request = invalid
                with self.assertRaisesRegex(JournalBlocked, 'why:.*remedy:'):
                    self.transport.page(782, None)
                self.assertFalse(self.transport._checked_writers)

    def test_new_page_does_not_reuse_shared_control_from_failed_writer_page(self):
        request = self.multiple_writers([17, 18])
        def wrong_job(method, path, **kwargs):
            result = request(method, path, **kwargs)
            if '/runs/18/attempts/1/jobs?' in path:
                result['jobs'][0]['name'] = 'untrusted job'
            return result
        self.api._request = wrong_job
        with self.assertRaises(JournalBlocked):
            self.transport.page(782, None)
        self.assertFalse(self.transport._checked_writers)
        before = len(self.api.calls)
        self.api._request = request
        self.transport.page(782, None)
        self.assertEqual(sum('/compare/' in path for _, path, _ in self.api.calls[before:]), 1,
                         'why: failed page retained control proof; remedy: reauthenticate the next page attempt')

    def test_different_controls_do_not_share_source_or_ancestry_proof(self):
        request = self.multiple_writers([17, 18])
        other = 'c' * 40
        self.api.comments[1]['body'] = wrapped('event', {'id': 'second'},
                                              {**WRITER, 'run_id': 18, 'control_sha': other})
        seen = []
        def distinct(method, path, **kwargs):
            seen.append(path)
            normalized = path.replace(other, 'a' * 40)
            result = request(method, normalized, **kwargs)
            if path.endswith('/runs/18/attempts/1'):
                result['head_sha'] = other
            if '/compare/' in path and other in path:
                result['base_commit']['sha'] = other
                result['merge_base_commit']['sha'] = other
            return result
        self.api._request = distinct
        self.transport.page(782, None)
        self.assertEqual(sum('/compare/' in path for path in seen), 2)
        self.assertEqual(sum('/contents/' in path for path in seen), 2)
        self.assertTrue(any('/compare/' + other in path for path in seen))

    def test_later_page_with_new_writer_reuses_control_source_proof(self):
        self.multiple_writers([17, 18])
        self.api.comment_pages = 1
        first = self.transport.page(782, None)
        before = len(self.api.calls)
        self.api.compare_status = 'diverged'
        second = self.transport.page(782, first['next'])
        self.assertIsNone(second['next'])
        self.assertEqual(sum('/actions/workflows/' in path for _, path, _ in self.api.calls[before:]), 1)
        self.assertFalse(any('/compare/' in path or '/contents/' in path
                             for _, path, _ in self.api.calls[before:]),
                         'why: immutable control proof was repeated; remedy: reuse it within this read transaction')

    def test_new_read_transaction_rechecks_mutable_writer_state(self):
        self.multiple_writers([17, 18])
        self.api.comment_pages = 1
        first = self.transport.page(782, None)
        self.assertIsNone(self.transport.page(782, first['next'])['next'])
        self.api.run_changes = {'head_branch': 'untrusted'}
        with self.assertRaisesRegex(JournalBlocked, 'control provenance'):
            self.transport.page(782, None)

    def test_later_page_rechecks_mutable_writer_state(self):
        self.multiple_writers([17, 17])
        self.api.comment_pages = 1
        first = self.transport.page(782, None)
        self.api.run_changes = {'head_branch': 'untrusted'}
        with self.assertRaisesRegex(JournalBlocked, 'control provenance'):
            self.transport.page(782, first['next'])

    def test_later_page_rechecks_mutable_writer_jobs(self):
        self.multiple_writers([17, 17])
        self.api.comment_pages = 1
        first = self.transport.page(782, None)
        self.api.job_changes = {'name': 'untrusted job'}
        with self.assertRaisesRegex(JournalBlocked, 'writer job is missing'):
            self.transport.page(782, first['next'])

    def test_later_page_still_rejects_comment_edit_after_proof_reuse(self):
        self.multiple_writers([17, 18])
        self.api.comment_pages = 1
        first = self.transport.page(782, None)
        self.api.comments[1]['editor'] = {'__typename': 'User', 'id': 'human'}
        with self.assertRaisesRegex(JournalBlocked, 'comment was edited'):
            self.transport.page(782, first['next'])

    def test_reopened_transport_reauthenticates_previously_shared_proof(self):
        self.multiple_writers([17, 18])
        self.transport.page(782, None)
        self.api.compare_status = 'diverged'
        fresh = github.GitHubJournalTransport(repository='endaye/lmdj', issue_number=782,
                    issue_node_id='fixed-issue-node', bot_node_id=BOT['id'],
                    workflows={PATH:7}, writer=WRITER, api=self.api, lock_held=lambda:True)
        with self.assertRaisesRegex(JournalBlocked, 'main history'):
            fresh.page(782, None)
        self.assertFalse(fresh._checked_writers)

    def test_same_run_different_writer_identity_cannot_reuse_proof(self):
        self.multiple_writers([17, 17])
        self.api.comments[1]["body"] = wrapped("event", {"id": "other"},
                                             {**WRITER, "job_name": "Unstarted writer"})
        with self.assertRaisesRegex(JournalBlocked, "writer job is missing"):
            self.transport.page(782, None)
        self.assertFalse(self.transport._checked_writers,
                         "why: run-only dedup trusted another job; remedy: key proofs by the complete writer identity")

    def test_concurrent_completion_cannot_reorder_page(self):
        request = self.multiple_writers([17, 18, 19, 20])
        last_completed = threading.Event()
        completion = []

        def reordered(method, path, **kwargs):
            if "/runs/17/attempts/1/jobs?" in path:
                self.assertTrue(last_completed.wait(5),
                                "why: independent readers did not overlap; remedy: finish other writers concurrently")
            result = request(method, path, **kwargs)
            if "/jobs?" in path:
                completion.append(result["jobs"][0]["run_id"])
                if "/runs/20/" in path:
                    last_completed.set()
            return result

        self.api._request = reordered
        page = self.transport.page(782, None)
        self.assertLess(completion.index(20), completion.index(17),
                        "why: fixture did not reverse completion; remedy: synchronize actual GET completion")
        self.assertEqual([r["provenance"]["run_id"] for r in page["comments"]], [17, 18, 19, 20],
                         "why: journal sorted by network timing; remedy: preserve original record order")

    def test_failed_concurrent_writer_returns_no_page_and_joins_without_writes(self):
        request = self.multiple_writers([17, 18, 19, 20])
        barrier = threading.Barrier(4, timeout=5)
        finished = set()
        jobs_finished = set()
        mutex = threading.Lock()

        def failing(method, path, **kwargs):
            if path.endswith("/attempts/1"):
                barrier.wait()
                result = request(method, path, **kwargs)
                if "/runs/18/" in path:
                    result["head_branch"] = "untrusted"
                with mutex:
                    finished.add(path)
                return result
            result = request(method, path, **kwargs)
            if "/jobs?" in path:
                with mutex:
                    jobs_finished.add(path)
            return result

        self.api._request = failing
        with self.assertRaisesRegex(JournalBlocked, "control provenance"):
            self.transport.page(782, None)
        self.assertEqual(len(finished), 4, "why: failed page left active readers; remedy: join all futures before returning")
        self.assertEqual(len(jobs_finished), 3,
                         "why: failed page returned before other writer proofs completed; remedy: join all futures")
        self.assertFalse(self.transport._checked_writers,
                         "why: partial failed page committed trust cache; remedy: publish authentication only after all succeed")
        self.assertFalse(any(method == "PATCH" or path.endswith("/comments") for method, path, _ in self.api.calls),
                         "why: failed provenance caused mutation; remedy: fail before replay or append")

    def test_cached_writer_does_not_cache_comment_edits_or_anchor(self):
        self.journal.append({"id": "one"})
        self.assertEqual(self.journal.load(), [{"id": "one"}])
        self.api.comments[0]["editor"] = {"__typename": "User", "id": "human"}
        # The edit is behind the prefix this process verified; the next complete
        # replay refuses it rather than adopting it silently.
        fresh = Journal(782, self.transport, self.anchor, self.transport.authenticate, lambda: self.lock)
        with self.assertRaisesRegex(JournalBlocked, "comment was edited"):
            fresh.load()
        self.api.comments[0]["editor"] = None
        self.api.issue["editor"] = {"__typename": "User", "id": "human"}
        with self.assertRaisesRegex(JournalBlocked, "last editor"):
            self.journal.load()

    def test_append_reads_fresh_page_and_checkpoint_after_prior_authentication(self):
        self.journal.append({"id": "one"})
        prior = len(self.api.calls)
        self.journal.append({"id": "two"})
        self.assertEqual(self.journal.load(), [{"id": "one"}, {"id": "two"}],
                         "why: append reused a stale page; remedy: read complete new journal")
        queries = [body["query"] for method, path, body in self.api.calls[prior:] if path == "/graphql"]
        self.assertIn(github.COMMENTS_QUERY, queries, "why: no fresh comments; remedy: retain post-write reads")
        self.assertIn(github.BODY_QUERY, queries, "why: no fresh anchor; remedy: retain post-write reads")

    def test_incomplete_multiwriter_page_is_rejected_before_authentication(self):
        self.multiple_writers([17, 18, 19, 20])
        self.api.truncated = True
        with self.assertRaisesRegex(JournalBlocked, "truncated"):
            self.transport.page(782, None)
        self.assertFalse(any(method == "GET" for method, _, _ in self.api.calls),
                         "why: malformed inventory reached readers; remedy: validate complete page first")

    def test_append_checkpoint_read_and_reopen(self):
        self.journal.append({"id": "one", "payload": "state"})
        self.assertEqual(self.journal.load(), [{"id": "one", "payload": "state"}],
                         "why: write/read journey lost event; remedy: preserve checkpoint and exact comment")
        mutations = [(method, path) for method, path, _ in self.api.calls if method == "PATCH" or path.endswith("/comments")]
        self.assertEqual(mutations, [("PATCH", "/repos/endaye/lmdj/issues/782"),
            ("POST", "/repos/endaye/lmdj/issues/782/comments"), ("PATCH", "/repos/endaye/lmdj/issues/782")],
            "why: journal retried or reordered writes; remedy: intent then single POST then checkpoint")

    def test_body_updated_at_from_comment_does_not_mean_edit(self):
        self.api.issue["updatedAt"] = "later-than-body"
        self.assertEqual(self.transport.read_body(782)["checkpoint"], {"head": None, "pending": None},
                         "why: Issue activity mistaken for body edit; remedy: editor/lastEditedAt only")

    def test_tail_peek_returns_newest_comment_without_writer_trust(self):
        self.journal.append({"id": "one"})
        self.journal.append({"id": "two"})
        prior = len(self.api.calls)
        row = self.transport.last(782)
        self.assertEqual(row["envelope"]["event"], {"id": "two"},
                         "why: tail peek lost the newest event; remedy: read comments(last:1)")
        self.assertFalse(any(method == "GET" for method, _, _ in self.api.calls[prior:]),
                         "why: tail peek spent writer trust; remedy: leave authentication to the full replay")

    def test_tail_peek_empty_journal_returns_none(self):
        self.assertIsNone(self.transport.last(782),
                          "why: empty journal invented a tail; remedy: no comments means no peek row")

    def test_tail_peek_rejects_edited_comment(self):
        self.journal.append({"id": "one"})
        self.api.comments[0]["editor"] = {"__typename": "User", "id": "human"}
        with self.assertRaisesRegex(JournalBlocked, "comment was edited"):
            self.transport.last(782)

    def test_stranded_pending_peek_blocks_fast_and_reconcile_pending_drains(self):
        self.journal.append({"id": "one"})
        self.api.lose_post = True
        with self.assertRaises(JournalBlocked):
            self.journal.append({"id": "two"})
        # The POST outcome was unknown; on this path it never persisted.
        self.api.comments.pop()
        digest = self.anchor.read()["pending"]["digest"]
        prior = len(self.api.calls)
        with self.assertRaisesRegex(JournalBlocked, "uncertain"):
            self.journal.load()
        queries = [body["query"] for _, path, body in self.api.calls[prior:] if path == "/graphql"]
        self.assertNotIn(github.COMMENTS_QUERY, queries,
                         "why: blocked journal full-replays every health tick; remedy: fail fast on the tail peek")
        events = self.journal.reconcile_pending(digest)
        self.assertEqual(events, [{"id": "one"}],
                         "why: drain lost committed history; remedy: clear only the stranded intent")
        self.assertIsNone(self.anchor.read()["pending"],
                          "why: stranded intent survived the drain; remedy: restore the anchor after the absence proof")
        self.api.lose_post = False
        self.journal.append({"id": "two"})
        self.assertEqual(self.journal.load(), [{"id": "one"}, {"id": "two"}],
                         "why: drained journal cannot continue; remedy: append from the retained head")

    def test_page_after_returns_only_new_comments_and_authenticates_them(self):
        self.journal.append({"id": "one"})
        cursor = self.transport.page(782, None)["cursor"]
        self.assertTrue(cursor, "why: complete page walk exposed no resume cursor; remedy: return endCursor")
        self.api.comment_pages = 2
        prior = len(self.api.calls)
        self.journal.append({"id": "two"})
        self.journal.append({"id": "three"})
        delta = self.transport.page_after(782, cursor)
        self.assertEqual([row["envelope"]["event"] for row in delta["comments"]],
                         [{"id": "two"}, {"id": "three"}],
                         "why: delta read returned history the caller already verified; remedy: read after the cursor")
        self.assertIsNone(delta["next"])
        self.assertEqual(delta["total"], 3)
        self.assertTrue(any(method == "GET" and "/actions/runs/17/attempts/1" in path
                            for method, path, _ in self.api.calls[prior:]),
                        "why: delta accepted a comment without writer provenance; remedy: authenticate every node")

    def test_page_after_refuses_an_unauthenticated_cursor(self):
        self.journal.append({"id": "one"})
        with self.assertRaisesRegex(JournalBlocked, "authenticated cursor"):
            self.transport.page_after(782, None)

    def test_page_after_rejects_an_edited_new_comment(self):
        self.journal.append({"id": "one"})
        cursor = self.transport.page(782, None)["cursor"]
        self.journal.append({"id": "two"})
        self.api.comments[-1]["editor"] = {"__typename": "User", "id": "human"}
        with self.assertRaisesRegex(JournalBlocked, "comment was edited"):
            self.transport.page_after(782, cursor)

    def test_reconcile_pending_through_transport_never_clears_a_persisted_event(self):
        self.api.lose_post = True
        with self.assertRaises(JournalBlocked):
            self.journal.append({"id": "one"})
        digest = self.anchor.read()["pending"]["digest"]
        with self.assertRaisesRegex(JournalBlocked, "persisted"):
            self.journal.reconcile_pending(digest)
        self.assertIsNotNone(self.anchor.read()["pending"],
                             "why: committed event cleared by hand; remedy: ordinary load recovery adopts it")
        self.api.lose_post = False
        self.assertEqual(self.journal.load(), [{"id": "one"}],
                         "why: ordinary recovery did not adopt the persisted event; remedy: inspect pending")

    def test_body_trusted_editor_allowed_even_original_author_is_human(self):
        self.api.issue.update(author={"__typename": "User"}, editor=deepcopy(BOT), lastEditedAt="2026-09-08T00:00:00Z")
        self.transport.read_body(782)

    def test_human_body_editor_rejected(self):
        self.api.issue.update(editor={"__typename": "User"}, lastEditedAt="2026-09-08T00:00:00Z")
        with self.assertRaisesRegex(JournalBlocked, "last editor"):
            self.transport.read_body(782)

    def test_missing_edit_metadata_rejected(self):
        del self.api.issue["editor"]
        with self.assertRaisesRegex(JournalBlocked, "metadata was omitted"):
            self.transport.read_body(782)

    def test_display_name_does_not_authorize_wrong_bot(self):
        self.api.issue["author"] = {"__typename": "Bot", "id": "different", "login": "github-actions"}
        with self.assertRaisesRegex(JournalBlocked, "author"):
            self.transport.read_body(782)

    def test_human_comment_edit_rejected(self):
        self.api.comments.append(self.api.comment({}))
        self.api.comments[0]["lastEditedAt"] = "2026-09-08T00:00:00Z"
        with self.assertRaisesRegex(JournalBlocked, "comment was edited"):
            self.transport.page(782, None)

    def test_full_bigint_identity_is_text_and_bool_rejected(self):
        self.api.comments.append(self.api.comment({}))
        self.assertEqual(self.transport.page(782, None)["comments"][0]["id"], 5573637240,
                         "why: BigInt comment identity coerced incorrectly; remedy: decimal text parsing")
        self.api.comments[0]["fullDatabaseId"] = True
        with self.assertRaisesRegex(JournalBlocked, "BigInt"):
            self.transport.page(782, None)

    def test_complete_comment_pagination(self):
        for number in range(3):
            self.journal.append({"id": str(number)})
        self.assertEqual(len(self.journal.load()), 3, "why: first page treated complete; remedy: follow every cursor")

    def test_truncated_comments_fail_closed(self):
        self.api.truncated = True
        with self.assertRaisesRegex(JournalBlocked, "truncated"):
            self.transport.page(782, None)

    def test_missing_next_cursor_does_not_look_terminal(self):
        self.api.comments = [self.api.comment({}), self.api.comment({})]
        self.api.missing_cursor = True
        with self.assertRaisesRegex(JournalBlocked, "missing next"):
            self.transport.page(782, None)

    def test_graphql_error_never_reads_as_absence_or_leaks_response(self):
        self.api.graph_errors = True
        with self.assertRaises(JournalBlocked) as caught:
            self.transport.read_body(782)
        self.assertNotIn("SECRET", str(caught.exception), "why: GraphQL body leaked; remedy: closed diagnostics")

    def test_single_post_response_loss_reconciles(self):
        self.api.lose_post = True
        with self.assertRaises(JournalBlocked) as caught:
            self.journal.append({"id": "one"})
        self.assertNotIn("SECRET", str(caught.exception), "why: transport leaked body; remedy: sanitize errors")
        self.assertEqual(len(self.journal.load()), 1, "why: persisted lost-response comment not adopted; remedy: exact pending lookup")
        self.assertEqual(sum(path.endswith("/comments") for _, path, _ in self.api.calls), 1,
                         "why: lost response retried POST; remedy: reconcile first")

    def test_in_progress_or_later_failed_writer_is_legitimate(self):
        self.api.run_changes.update(status="completed", conclusion="failure")
        self.api.job_changes.update(status="completed", conclusion="failure")
        self.transport.read_body(782)

    def test_queued_parent_preserves_completed_writer_checkpoint(self):
        # O1 run 34155431379: aggregate queued while controller succeeded.
        self.api.run_changes.update(status="queued", conclusion=None)
        self.api.job_changes.update(status="completed", conclusion="success",
                                    started_at="2026-09-07T19:24:10Z", completed_at="2026-09-07T19:24:48Z")
        self.assertEqual(self.transport.read_body(782)["checkpoint"], {"head": None, "pending": None},
            "why: queued product jobs invalidated a completed journal writer; remedy: authenticate the exact started writer job")

    def test_queued_parent_does_not_authorize_unstarted_writer(self):
        self.api.run_changes.update(status="queued", conclusion=None)
        self.api.job_changes.update(status="queued", started_at=None, completed_at=None)
        with self.assertRaises(JournalBlocked):
            self.transport.read_body(782)

    def test_queued_parent_does_not_authorize_skipped_writer(self):
        self.api.run_changes.update(status="queued", conclusion=None)
        self.api.job_changes.update(status="completed", conclusion="skipped",
                                    started_at="2026-09-07T19:24:10Z", completed_at="2026-09-07T19:24:10Z")
        with self.assertRaises(JournalBlocked):
            self.transport.read_body(782)

    def test_queued_parent_requires_start_evidence_for_completed_writer(self):
        self.api.run_changes.update(status="queued", conclusion=None)
        self.api.job_changes.update(status="completed", conclusion="success", started_at=None)
        with self.assertRaisesRegex(JournalBlocked, "proven started writer"):
            self.transport.read_body(782)

    def test_unknown_parent_status_remains_blocked(self):
        self.api.run_changes.update(status="future-unknown")
        with self.assertRaisesRegex(JournalBlocked, "control provenance"):
            self.transport.read_body(782)

    def test_pending_parent_preserves_completed_writer(self):
        # Exact attempt API, O1 34155431379; not merely generic run status.
        self.api.run_changes.update(status="pending", conclusion=None)
        self.api.job_changes.update(status="completed", conclusion="success",
                                    started_at="2026-09-07T19:24:10Z", completed_at="2026-09-07T19:24:48Z")
        self.assertEqual(self.transport.read_body(782)["checkpoint"], {"head": None, "pending": None},
            "why: pending product siblings invalidated a completed writer; remedy: authenticate exact writer start independently")

    def test_known_wait_states_preserve_started_writer(self):
        # Requested/waiting remain fixture coverage, not observed O1 states.
        for state in ("queued", "waiting", "requested", "pending"):
            with self.subTest(state=state):
                self.transport._checked_writers.clear()
                self.api.run_changes.update(status=state, conclusion=None)
                self.api.job_changes.update(status="in_progress", started_at="2026-09-07T19:24:10Z")
                self.transport.read_body(782)

    def test_known_wait_states_reject_unproven_writer(self):
        for state in ("queued", "waiting", "requested", "pending"):
            for job in ({"status": "queued", "started_at": None},
                        {"status": "completed", "conclusion": "skipped", "started_at": "2026-09-07T19:24:10Z"},
                        {"status": "completed", "conclusion": "success", "started_at": None}):
                with self.subTest(state=state, job=job):
                    self.transport._checked_writers.clear()
                    self.api.run_changes.update(status=state, conclusion=None)
                    self.api.job_changes = job
                    with self.assertRaises(JournalBlocked):
                        self.transport.read_body(782)

    def test_later_run_rerun_does_not_invalidate_historical_first_attempt(self):
        self.api.latest_attempt = 2
        self.transport.read_body(782)
        self.assertIn(("GET", "/repos/endaye/lmdj/actions/runs/17/attempts/1", None), self.api.calls,
                      "why: historical journal read mutable latest attempt; remedy: fetch the exact recorded attempt")

    def test_writer_job_must_belong_to_recorded_attempt(self):
        self.api.job_changes["run_attempt"] = 2
        with self.assertRaisesRegex(JournalBlocked, "writer job"):
            self.transport.read_body(782)

    def test_wrong_run_metadata_rejected(self):
        for changes in ({"run_attempt": True}, {"head_sha": "c" * 40}, {"head_branch": "branch"},
                        {"workflow_id": 8}, {"head_repository": {"full_name": "fork/repo"}}, {"event": "pull_request"}):
            with self.subTest(changes=changes):
                self.transport._checked_writers.clear()
                self.api.run_changes = changes
                with self.assertRaisesRegex(JournalBlocked, "run does not match"):
                    self.transport.read_body(782)

    def test_non_main_ancestor_control_rejected(self):
        self.api.compare_status = "diverged"
        with self.assertRaisesRegex(JournalBlocked, "main history"):
            self.transport.read_body(782)

    def test_complete_job_pagination_finds_writer_after_first_page(self):
        self.api.extra_jobs = [{"id": n + 1, "name": f"other-{n}", "run_id": 17, "status": "completed"} for n in range(100)]
        self.transport.read_body(782)
        self.assertTrue(any("jobs?per_page=100&page=2" in path for _, path, _ in self.api.calls),
                        "why: writer job search omitted page two; remedy: enumerate complete jobs")

    def test_duplicate_json_keys_rejected(self):
        self.api.issue["body"] = '{"schema":"one","schema":"two"}'
        with self.assertRaisesRegex(JournalBlocked, "duplicate JSON"):
            self.transport.read_body(782)

    def test_wrong_issue_parameter_never_performs_request(self):
        with self.assertRaises(JournalBlocked):
            self.transport.read_body(783)
        self.assertFalse(self.api.calls, "why: foreign issue reached API; remedy: fixed target preflight")

    def test_writer_wrong_repository_or_boolean_identity_rejected(self):
        for changes in ({"repository": "other/repo"}, {"issue_number": True}, {"run_id": True}, {"run_attempt": True}):
            with self.subTest(changes=changes):
                self.api.issue["body"] = wrapped("checkpoint", {"head": None, "pending": None}, {**WRITER, **changes})
                with self.assertRaises(JournalBlocked):
                    self.transport.read_body(782)

    def test_missing_writer_job_rejected(self):
        self.api.job_changes["name"] = "Not the journal writer"
        with self.assertRaisesRegex(JournalBlocked, "writer job is missing"):
            self.transport.read_body(782)

    def test_transient_transport_error_hides_raw_message(self):
        self.api.transport_error = True
        with self.assertRaises(JournalBlocked) as caught:
            self.transport.read_body(782)
        self.assertNotIn("SECRET", str(caught.exception), "why: API exception exposed raw data; remedy: closed diagnostics")

    def test_oversized_record_is_refused_with_closed_kind_before_any_mutation(self):
        event = {"id": "epoch:0", "epoch": "epoch", "generation": 0, "type": "admit",
                 "data": {"reasons": ["SECRET-RAW-BODY-MUST-NOT-ESCAPE " + "x" * 100] * 700}}
        with self.assertRaises(github.JournalRecordOversized) as caught:
            self.journal.append(event)
        self.assertIsInstance(caught.exception, JournalBlocked)
        self.assertIn("why:", str(caught.exception))
        self.assertIn("remedy:", str(caught.exception))
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertFalse(any(method in ("PATCH", "POST") and path != "/graphql" for method, path, _ in self.api.calls),
                         "why: an oversized record reached a mutation; remedy: refuse before the anchor intent")
        self.assertEqual(json.loads(self.api.issue["body"])["payload"], {"head": None, "pending": None})
        self.assertEqual(self.api.comments, [])

    def test_nonfinite_write_never_reaches_mutation(self):
        with self.assertRaisesRegex(JournalBlocked, "not strict JSON"):
            self.transport.write_body(782, {"head": float("nan"), "pending": None})
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.api.calls),
                         "why: nonfinite state was written; remedy: encode strictly before PATCH")

    def test_unknown_wrapper_key_rejected(self):
        body = json.loads(self.api.issue["body"])
        body["extra"] = True
        self.api.issue["body"] = json.dumps(body)
        with self.assertRaisesRegex(JournalBlocked, "schema is not closed"):
            self.transport.read_body(782)

    def test_wrong_issue_node_blocks_write(self):
        self.api.issue["id"] = "different-node"
        with self.assertRaises(JournalBlocked):
            self.transport.write_body(782, {"head": None, "pending": None})
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.api.calls),
                         "why: foreign checkpoint overwritten; remedy: verify fixed node before write")

    def test_missing_lock_never_mutates(self):
        self.lock = False
        with self.assertRaises(JournalBlocked):
            self.transport.write_body(782, {})
        self.assertFalse(self.api.calls, "why: unlocked write reached service; remedy: require shared short lock")

    def test_missing_body_is_not_automatically_initialized(self):
        self.api.issue["body"] = ""
        with self.assertRaises(JournalBlocked):
            self.transport.write_body(782, {"head": None, "pending": None})
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.api.calls),
                         "why: missing checkpoint silently reset; remedy: explicit audited initialization")


if __name__ == "__main__":
    unittest.main()
