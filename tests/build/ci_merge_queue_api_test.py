#!/usr/bin/env python3
"""Contract tests for the Merge Queue GitHub REST boundary."""

from __future__ import annotations

import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))

import github_queue_api as api  # noqa: E402
import change_scope as scope  # noqa: E402
import merge_queue as mq  # noqa: E402


SHA_A = "a" * 40
SHA_B = "b" * 40


def json_response(status, document, headers=None):
    return status, headers or {}, json.dumps(document).encode("utf-8")


def validation_zip(document):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("queue-validation.json", json.dumps(document))
    return buffer.getvalue()


def scope_zip(document):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ci-scope.json", json.dumps(document))
    return buffer.getvalue()


class RecordingTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        response = self.responses.pop(0)
        if callable(response):
            return response(request)
        return response


class GitHubQueueApiTest(unittest.TestCase):
    def client(self, responses, **kwargs):
        transport = RecordingTransport(responses)
        client = api.GitHubQueueClient(
            "endaye/lmdj",
            "secret-token",
            transport=transport,
            clock=kwargs.get("clock", lambda: 0.0),
            sleeper=kwargs.get("sleeper", lambda _seconds: None),
        )
        return client, transport

    def test_main_sha_comes_from_the_canonical_git_ref(self):
        client, transport = self.client([
            json_response(200, {"ref": "refs/heads/main", "object": {"sha": SHA_A}}),
        ])
        self.assertEqual(client.get_main_sha(), SHA_A)
        request = transport.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertTrue(request.url.endswith("/git/ref/heads/main"))
        self.assertEqual(request.headers["X-GitHub-Api-Version"], "2026-03-10")
        self.assertEqual(request.headers["Authorization"], "Bearer secret-token")

    def test_bounded_get_passes_remaining_deadline_to_transport(self):
        now = [0.0]

        def timeout(request):
            self.assertEqual(request.timeout_seconds, 5.0)
            now[0] += request.timeout_seconds
            raise TimeoutError("transport deadline reached")

        client, transport = self.client(
            [timeout, json_response(200, {"ref": "refs/heads/main", "object": {"sha": SHA_A}})],
            clock=lambda: now[0],
            sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
        )
        with self.assertRaises(TimeoutError):
            client.get_main_sha(timeout_seconds=5)
        self.assertEqual(len(transport.requests), 1)

    def test_urllib_transport_never_automatically_follows_redirects(self):
        class Handler(BaseHTTPRequestHandler):
            redirected_requests = 0

            def do_GET(self):
                if self.path == "/artifact":
                    self.send_response(302)
                    self.send_header(
                        "Location",
                        f"http://127.0.0.1:{self.server.server_port}/redirected",
                    )
                    self.end_headers()
                    return
                type(self).redirected_requests += 1
                self.send_response(200)
                self.end_headers()

            def log_message(self, _format, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, _, _ = api._urllib_transport(api.HttpRequest(
                "GET",
                f"http://127.0.0.1:{server.server_port}/artifact",
                {"Authorization": "Bearer must-not-be-forwarded"},
                None,
            ))
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(status, 302)
        self.assertEqual(Handler.redirected_requests, 0)

    def test_pull_permission_and_changed_files_are_closed_and_paginated(self):
        pull = {
            "number": 220,
            "state": "open",
            "merged": False,
            "draft": False,
            "base": {"ref": "main", "sha": SHA_A},
            "head": {"ref": "feat/queue", "sha": SHA_B, "repo": {"full_name": "endaye/lmdj"}},
            "title": "feat(ci): queue",
            "labels": [{"name": "merge:queue"}],
            "mergeable": True,
            "merge_commit_sha": None,
        }
        client, transport = self.client([
            json_response(200, {"permission": "maintain"}),
            json_response(200, pull),
            json_response(
                200,
                [{"filename": "a.py"}],
                {"link": '<https://api.github.com/repositories/1/pulls/220/files?page=2>; rel="next"'},
            ),
            json_response(200, [{"filename": "b.py"}]),
        ])
        self.assertEqual(client.get_permission("endaye"), "maintain")
        parsed = client.get_pull(220)
        self.assertEqual(parsed.head_repository, "endaye/lmdj")
        self.assertEqual(parsed.head_ref, "feat/queue")
        self.assertEqual(parsed.labels, ("merge:queue",))
        self.assertEqual(client.list_changed_paths(220), ("a.py", "b.py"))
        self.assertEqual(len(transport.requests), 4)

    def test_dispatch_requires_200_and_a_numeric_workflow_run_id(self):
        client, transport = self.client([
            json_response(200, {"workflow_run_id": 991, "run_url": "https://api/run/991"}),
        ])
        run_id = client.dispatch_validation(
            220,
            SHA_B,
            {
                "lanes": "",
                "queue_ticket": "mq:123:1",
                "queue_pr_number": "220",
                "queue_base_sha": SHA_A,
                "queue_head_sha": SHA_B,
            },
        )
        self.assertEqual(run_id, 991)
        request = transport.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertTrue(request.url.endswith("/actions/workflows/ci.yml/dispatches"))
        payload = json.loads(request.body)
        self.assertEqual(payload["ref"], SHA_B)
        self.assertEqual(payload["inputs"]["queue_ticket"], "mq:123:1")

        for document in ({}, {"workflow_run_id": "991"}, {"workflow_run_id": True}):
            with self.subTest(document=document):
                invalid, _ = self.client([json_response(200, document)])
                with self.assertRaises(mq.DispatchContractError):
                    invalid.dispatch_validation(220, SHA_B, {"lanes": ""})

    def test_cancel_validation_posts_the_exact_run_endpoint(self):
        client, transport = self.client([(202, {}, b"")])
        client.cancel_validation(991)
        request = transport.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            request.url,
            "https://api.github.com/repos/endaye/lmdj/actions/runs/991/cancel",
        )
        self.assertIsNone(request.body)

    def test_cancel_validation_rejects_a_non_success_response(self):
        client, _ = self.client([json_response(409, {"message": "cannot cancel"})])
        with self.assertRaises(api.GitHubApiError):
            client.cancel_validation(991)

    def test_update_branch_maps_expected_head_conflict_and_accepted_poll(self):
        drift, _ = self.client([json_response(422, {"message": "head changed"})])
        self.assertEqual(drift.update_branch(220, SHA_B, 60).status, "drift")

        accepted_pull = {
            "number": 220,
            "state": "open",
            "merged": False,
            "draft": False,
            "base": {"ref": "main", "sha": SHA_A},
            "head": {"ref": "feat/queue", "sha": SHA_B, "repo": {"full_name": "endaye/lmdj"}},
            "title": "feat(ci): queue",
            "labels": [{"name": "merge:queue"}],
            "mergeable": True,
            "merge_commit_sha": None,
        }
        updated_pull = json.loads(json.dumps(accepted_pull))
        updated_pull["head"]["sha"] = "c" * 40
        clock_values = iter((0.0, 1.0))
        accepted, transport = self.client(
            [
                json_response(202, {"message": "Updating pull request branch."}),
                json_response(200, updated_pull),
            ],
            clock=lambda: next(clock_values),
        )
        result = accepted.update_branch(220, SHA_B, 60)
        self.assertEqual(result, mq.UpdateResult("accepted", "c" * 40))
        self.assertEqual(json.loads(transport.requests[0].body), {"expected_head_sha": SHA_B})

    def test_sync_validation_is_exactly_bound_approved_and_reconciled(self):
        run = {
            "id": 9101,
            "event": "pull_request",
            "path": ".github/workflows/ci.yml",
            "head_sha": SHA_B,
            "status": "completed",
            "conclusion": "action_required",
            "actor": {"login": "github-actions[bot]"},
            "pull_requests": [{"number": 220}],
        }
        client, transport = self.client([
            json_response(200, {"workflow_runs": [run]}),
            (201, {}, b""),
            json_response(200, run),
            json_response(200, {**run, "status": "queued", "conclusion": None}),
        ], clock=iter((0.0, 1.0, 2.0, 3.0)).__next__)
        self.assertEqual(
            client.authorize_sync_validation(220, SHA_A, SHA_B, 60),
            9101,
        )
        self.assertTrue(transport.requests[0].url.endswith(
            "/actions/workflows/ci.yml/runs?event=pull_request&per_page=100"
        ))
        self.assertTrue(transport.requests[1].url.endswith("/actions/runs/9101/approve"))
        self.assertEqual(transport.requests[1].method, "POST")

    def test_pull_request_validation_reads_the_exact_scope_manifest(self):
        manifest = scope.classify(
            scope.load_policy(ROOT / "scripts/ci/scope_policy.json"),
            (scope.ChangedFile("M", ("docs/guide.md",)),),
            base_sha=SHA_A,
            head_sha=SHA_B,
            event_name="pull_request",
            draft=False,
            labels={"merge:queue"},
            trusted_head=True,
        )
        redirect = (
            "https://productionresultssa12.blob.core.windows.net/"
            "actions-results/scope?sig=fixture"
        )
        client, _ = self.client([
            json_response(200, {
                "id": 9101,
                "status": "completed",
                "conclusion": "success",
                "event": "pull_request",
                "path": ".github/workflows/ci.yml",
                "head_sha": SHA_B,
                "check_suite_id": 778,
                "created_at": "2026-08-21T00:00:00Z",
                "run_started_at": "2026-08-21T00:00:10Z",
                "updated_at": "2026-08-21T00:00:30Z",
            }),
            json_response(200, {"total_count": 3, "jobs": [
                {"name": "core (ubuntu-latest)", "conclusion": "success"},
                {"name": "core (macos-latest)", "conclusion": "success"},
                {"name": "PR Gate", "conclusion": "success"},
            ]}),
            json_response(200, {"total_count": 3, "check_runs": [
                {"name": "core (ubuntu-latest)", "conclusion": "success", "app": {"id": 15368}},
                {"name": "core (macos-latest)", "conclusion": "success", "app": {"id": 15368}},
                {"name": "PR Gate", "conclusion": "success", "app": {"id": 15368}},
            ]}),
            json_response(200, {"total_count": 1, "artifacts": [
                {"id": 43, "name": f"ci-scope-{SHA_B}", "expired": False},
            ]}),
            (302, {"Location": redirect}, b""),
            (200, {"Content-Type": "application/zip"}, scope_zip(manifest)),
        ])
        result = client.wait_validation(9101, 60)
        self.assertEqual(result.run_event, "pull_request")
        self.assertEqual(result.base_sha, SHA_A)
        self.assertEqual(result.head_sha, SHA_B)
        self.assertIsNone(result.ticket)
        self.assertEqual(result.classification, "valid")

    def test_scope_artifact_rejects_open_or_inconsistent_manifests(self):
        policy = scope.load_policy(ROOT / "scripts/ci/scope_policy.json")
        manifest = scope.classify(
            policy,
            (scope.ChangedFile("M", ("docs/guide.md",)),),
            base_sha=SHA_A,
            head_sha=SHA_B,
            event_name="pull_request",
            draft=False,
            labels={"merge:queue"},
            trusted_head=True,
        )
        opened = dict(manifest)
        opened["extra"] = True
        wrong_lanes = json.loads(json.dumps(manifest))
        wrong_lanes["lanes"][next(iter(wrong_lanes["lanes"]))] = False
        wrong_jobs = dict(manifest)
        wrong_jobs["required_jobs"] = []
        for document in (opened, wrong_lanes, wrong_jobs):
            with self.subTest(keys=sorted(document)):
                with self.assertRaises(ValueError):
                    api.parse_scope_manifest_zip(scope_zip(document), SHA_B)
        wrong_head = dict(manifest)
        wrong_head["head_sha"] = SHA_A
        with self.assertRaises(ValueError):
            api.parse_scope_manifest_zip(scope_zip(wrong_head), SHA_B)

    def test_validation_binds_run_jobs_check_suite_and_secret_safe_artifact_redirect(self):
        validation = {
            "schema": "lmdj.queue-validation.v1",
            "classification": "valid",
            "queue_ticket": "mq:123:1",
            "queue_pr_number": 220,
            "queue_base_sha": SHA_A,
            "queue_head_sha": SHA_B,
            "observed_base_sha": SHA_A,
            "observed_head_sha": SHA_B,
            "manifest_mode": "full",
            "trusted_head": True,
        }
        artifact_redirect = (
            "https://productionresultssa12.blob.core.windows.net/"
            "actions-results/fixture?sig=fixture"
        )
        client, transport = self.client([
            json_response(200, {
                "id": 991,
                "status": "completed",
                "conclusion": "success",
                "event": "workflow_dispatch",
                "path": ".github/workflows/ci.yml",
                "head_sha": SHA_B,
                "check_suite_id": 777,
                "created_at": "2026-08-21T00:00:00Z",
                "run_started_at": "2026-08-21T00:00:10Z",
                "updated_at": "2026-08-21T00:00:30Z",
            }),
            json_response(200, {"total_count": 4, "jobs": [
                {"name": "core (ubuntu-latest)", "conclusion": "success"},
                {"name": "core (macos-latest)", "conclusion": "success"},
                {"name": "PR Gate", "conclusion": "success"},
                {"name": "Docs / static", "conclusion": "success"},
            ]}),
            json_response(200, {"total_count": 4, "check_runs": [
                {"name": "core (ubuntu-latest)", "conclusion": "success", "app": {"id": 15368}},
                {"name": "core (macos-latest)", "conclusion": "success", "app": {"id": 15368}},
                {"name": "PR Gate", "conclusion": "success", "app": {"id": 15368}},
                {"name": "Docs / static", "conclusion": "success", "app": {"id": 15368}},
            ]}),
            json_response(200, {"total_count": 1, "artifacts": [
                {"id": 42, "name": "queue-validation-mq-123-1", "expired": False},
            ]}),
            (302, {"Location": artifact_redirect}, b""),
            (200, {"Content-Type": "application/zip"}, validation_zip(validation)),
        ])
        result = client.wait_validation(991, 60)
        self.assertEqual(result.classification, "valid")
        self.assertEqual(result.ticket, "mq:123:1")
        self.assertEqual(result.required_checks[0].app_id, 15368)
        self.assertEqual({check.name for check in result.required_checks}, set(mq.REQUIRED_CHECKS))
        self.assertEqual(result.queue_seconds, 10)
        self.assertEqual(result.execution_seconds, 20)
        self.assertEqual(transport.requests[-1].url, artifact_redirect)
        self.assertNotIn("Authorization", transport.requests[-1].headers)

    def test_artifact_redirect_requires_one_nonempty_signature(self):
        valid = (
            "https://productionresultssa12.blob.core.windows.net/"
            "actions-results/fixture?se=2026-08-21&sig=fixture&sp=r"
        )
        self.assertTrue(api._trusted_artifact_redirect(valid))
        for invalid in (
            valid.replace("https://", "http://"),
            valid.replace("productionresultssa12", "productionresultssa12.evil"),
            valid.replace("?se=2026-08-21&sig=fixture&sp=r", "?foo=bar"),
            valid.replace("sig=fixture", "sig="),
            valid + "&sig=duplicate",
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(api._trusted_artifact_redirect(invalid))

    def test_artifact_download_rejects_a_direct_success_response(self):
        client, _ = self.client([
            (200, {"Content-Type": "application/zip"}, b"PK\x03\x04fixture"),
        ])
        with self.assertRaises(api.GitHubApiError):
            client._download_validation_artifact(42)

    def test_validation_artifact_rejects_extra_keys_and_duplicate_entries(self):
        base = {
            "schema": "lmdj.queue-validation.v1",
            "classification": "invalid",
            "queue_ticket": "mq:123:1",
            "queue_pr_number": 220,
            "queue_base_sha": SHA_A,
            "queue_head_sha": SHA_B,
            "observed_base_sha": SHA_A,
            "observed_head_sha": SHA_B,
            "manifest_mode": None,
            "trusted_head": False,
        }
        with self.assertRaises(ValueError):
            api.parse_queue_validation_json({**base, "unexpected": True})
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("one/queue-validation.json", json.dumps(base))
            archive.writestr("two/queue-validation.json", json.dumps(base))
        with self.assertRaises(ValueError):
            api.parse_queue_validation_zip(buffer.getvalue())

    def test_remove_label_accepts_200_with_remaining_labels(self):
        client, transport = self.client([
            json_response(200, [{"name": "still-present"}]),
        ])
        client.remove_label(220, "merge:queue")
        request = transport.requests[0]
        self.assertEqual(request.method, "DELETE")
        self.assertEqual(
            request.url,
            "https://api.github.com/repos/endaye/lmdj/issues/220/labels/merge%3Aqueue",
        )
        self.assertIsNone(request.body)

    def test_remove_label_non_200_is_typed_and_redacts_secrets_and_body(self):
        response_secret = "ghp_RESPONSE_BODY_MUST_NOT_LEAK"
        client, _ = self.client([
            json_response(422, {"message": response_secret}),
        ])
        with self.assertRaises(api.GitHubApiError) as context:
            client.remove_label(220, "merge:queue")
        self.assertEqual(context.exception.status, 422)
        rendered = str(context.exception)
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn(response_secret, rendered)

    def test_merge_label_and_issue_comment_mutations_are_structured(self):
        client, transport = self.client([
            json_response(200, {"merged": True, "sha": SHA_B, "message": "merged"}),
            json_response(200, []),
            json_response(201, {"id": 8}),
        ])
        payload = {
            "merge_method": "squash",
            "sha": SHA_A,
            "commit_title": "feat: title (#220)",
            "commit_message": "",
        }
        self.assertTrue(client.merge_pull(220, payload).merged)
        client.remove_label(220, "merge:queue")
        client.create_review_comment(220, "stable report")
        self.assertEqual(json.loads(transport.requests[0].body), payload)
        self.assertTrue(transport.requests[2].url.endswith("/issues/220/comments"))
        self.assertEqual(json.loads(transport.requests[2].body), {"body": "stable report"})

    def test_watchdog_reads_live_label_timeline_runs_and_review_markers(self):
        pull = {
            "number": 220,
            "state": "open",
            "merged": False,
            "draft": False,
            "base": {"ref": "main", "sha": SHA_A},
            "head": {"ref": "docs/stall", "sha": SHA_B, "repo": {"full_name": "endaye/lmdj"}},
            "title": "docs: stall",
            "labels": [{"name": "merge:queue"}],
            "mergeable": True,
            "merge_commit_sha": None,
        }
        client, transport = self.client([
            json_response(200, [{"number": 220}]),
            json_response(200, pull),
            json_response(200, [
                {"id": 88, "event": "labeled", "label": {"name": "merge:queue"}, "created_at": "1970-01-01T00:01:40Z"},
            ]),
            json_response(200, {"workflow_runs": [
                {"status": "queued", "created_at": "1970-01-01T00:02:00Z", "pull_requests": [{"number": 220}]},
            ]}),
            json_response(200, [{"body": "<!-- marker -->"}]),
        ])
        self.assertEqual(client.list_labeled_pulls("merge:queue")[0].number, 220)
        self.assertEqual(client.latest_label_event(220, "merge:queue").event_id, 88)
        self.assertTrue(client.has_active_queue_run(220, 100.0))
        self.assertEqual(client.list_review_comments(220), ("<!-- marker -->",))
        self.assertIn("status=queued", transport.requests[3].url)

    def test_api_errors_never_expose_the_token(self):
        client, _ = self.client([json_response(403, {"message": "forbidden"})])
        with self.assertRaises(api.GitHubApiError) as context:
            client.get_main_sha()
        self.assertNotIn("secret-token", str(context.exception))

    def test_get_transport_failure_is_retried_but_mutations_are_not(self):
        sleeps = []

        def transport_failure(_request):
            raise OSError("temporary network failure")

        client, transport = self.client(
            [
                transport_failure,
                json_response(200, {"ref": "refs/heads/main", "object": {"sha": SHA_A}}),
            ],
            sleeper=sleeps.append,
        )
        self.assertEqual(client.get_main_sha(), SHA_A)
        self.assertEqual(sleeps, [1.0])
        mutation, mutation_transport = self.client([transport_failure])
        with self.assertRaises(OSError):
            mutation.dispatch_validation(220, "feat/queue", {"lanes": ""})
        self.assertEqual(len(mutation_transport.requests), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
