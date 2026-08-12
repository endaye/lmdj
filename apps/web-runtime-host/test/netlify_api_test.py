#!/usr/bin/env python3

from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = REPO_ROOT / "apps/web-runtime-host/tools"
sys.path.insert(0, str(TOOLS))
import netlify_api


class RequestRecord:
    def __init__(self, handler: BaseHTTPRequestHandler, body: bytes) -> None:
        self.method = handler.command
        self.path = handler.path
        self.headers = dict(handler.headers.items())
        self.body = body
        if handler.headers.get_content_type() != "application/json":
            self.json = None
            return
        try:
            self.json = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.json = None


class FakeNetlifyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeNetlifyHandler)
        self.requests: list[RequestRecord] = []
        self.create_response: object | None = None
        self.deploy_response: object | None = None
        self.restore_response: object | None = None
        self.site_files_response: object = [
            {
                "id": "file-123",
                "path": "/index.html",
                "sha": "a" * 40,
                "mime_type": "text/html",
                "size": 5,
            }
        ]
        self.site_response: object | None = None
        self.fail_upload = False
        self.poll_states: list[str] = ["ready"]
        self._poll_index = 0

    def response(self, handler: BaseHTTPRequestHandler, status: int, document: object) -> None:
        body = document if isinstance(document, bytes) else json.dumps(document).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        if status >= 400:
            handler.send_header("X-Netlify-Secret", "header-do-not-leak")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def next_state(self) -> str:
        index = min(self._poll_index, len(self.poll_states) - 1)
        self._poll_index += 1
        return self.poll_states[index]


class FakeNetlifyHandler(BaseHTTPRequestHandler):
    server: FakeNetlifyServer

    def log_message(self, format: str, *args) -> None:
        pass

    def _record(self) -> RequestRecord:
        length = int(self.headers.get("Content-Length", "0"))
        record = RequestRecord(self, self.rfile.read(length))
        self.server.requests.append(record)
        return record

    def do_POST(self) -> None:
        self._record()
        path = urlsplit(self.path).path
        if path == "/api/v1/sites/site-123/deploys":
            response = self.server.create_response or {
                "id": "deploy-456",
                "site_id": "site-123",
                "deploy_ssl_url": "https://draft.example/deploy-456",
                "state": "uploading",
                "required": [hashlib.sha1(b"index").hexdigest()],
            }
            self.server.response(self, 200, response)
            return
        if path == "/api/v1/sites/site-123/deploys/deploy-456/restore":
            response = self.server.restore_response or {
                "id": "deploy-456",
                "site_id": "site-123",
                "ssl_url": "https://runtime.example",
                "deploy_ssl_url": "https://deploy-456--runtime.netlify.app",
                "published_at": "2026-08-09T00:00:00Z",
                "state": "ready",
            }
            self.server.response(self, 200, response)
            return
        self.server.response(self, 404, {"error": "not found"})

    def do_PUT(self) -> None:
        self._record()
        if urlsplit(self.path).path == "/api/v1/sites/site-123/disable":
            self.server.response(self, 204, b"")
            return
        if self.server.fail_upload:
            self.server.response(self, 500, {"token": "do-not-leak"})
            return
        self.server.response(self, 200, {})

    def do_GET(self) -> None:
        self._record()
        if urlsplit(self.path).path == "/api/v1/sites/site-123/files":
            self.server.response(self, 200, self.server.site_files_response)
            return
        if urlsplit(self.path).path == "/api/v1/sites/site-123":
            self.server.response(
                self,
                200,
                self.server.site_response
                or {
                    "id": "site-123",
                    "state": "current",
                    "disabled": False,
                    "ssl_url": "https://runtime.example",
                    "published_deploy": {
                        "id": "prior-123",
                        "site_id": "site-123",
                        "deploy_ssl_url": "https://prior-123--runtime.netlify.app",
                        "state": "ready",
                    },
                },
            )
            return
        if urlsplit(self.path).path == "/api/v1/deploys/deploy-456":
            self.server.response(
                self,
                200,
                self.server.deploy_response
                or {
                    "id": "deploy-456",
                    "site_id": "site-123",
                    "deploy_ssl_url": "https://draft.example/deploy-456",
                    "state": self.server.next_state(),
                },
            )
            return
        self.server.response(self, 404, {"error": "not found"})


class NetlifyClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FakeNetlifyServer()
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.client = netlify_api.NetlifyClient(
            token="test-token",
            api_base=f"http://127.0.0.1:{self.server.server_port}/api/v1",
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def create_ready_draft(self, **extra):
        return self.client.create_draft(
            site_id="site-123",
            files={"/index.html": b"index", "/_headers": b"/*\n  X-Robots-Tag: noindex\n"},
            title="LMDJ Product 1.0.15.2 Host 1.1.2",
            **extra,
        )

    def test_create_draft_uploads_only_required_sha1_files(self) -> None:
        draft = self.create_ready_draft()
        create = self.server.requests[0]
        self.assertEqual(create.method, "POST")
        self.assertEqual(
            create.path,
            "/api/v1/sites/site-123/deploys?title=LMDJ%20Product%201.0.15.2%20Host%201.1.2",
        )
        self.assertEqual(create.json["draft"], True)
        self.assertEqual(create.json["files"]["/index.html"], hashlib.sha1(b"index").hexdigest())
        self.assertEqual([request.method for request in self.server.requests[1:]], ["PUT", "GET"])
        self.assertEqual(self.server.requests[1].path, "/api/v1/deploys/deploy-456/files/index.html")
        self.assertEqual(draft.id, "deploy-456")
        self.assertEqual(draft.state, "ready")
        self.assertEqual(self.server.requests[0].headers["Authorization"], "Bearer test-token")

    def test_encodes_nested_upload_path_by_segment(self) -> None:
        payload = b"asset"
        self.server.create_response = {
            "id": "deploy-456",
            "site_id": "site-123",
            "deploy_ssl_url": "https://draft.example/deploy-456",
            "state": "uploading",
            "required": [hashlib.sha1(payload).hexdigest()],
        }
        self.client.create_draft(
            site_id="site-123",
            files={"/assets/a space%?#.wasm": payload},
            title="title",
        )
        self.assertEqual(
            self.server.requests[1].path,
            "/api/v1/deploys/deploy-456/files/assets/a%20space%25%3F%23.wasm",
        )

    def test_uploads_binary_wasm_without_fake_api_decode_failure(self) -> None:
        payload = b"\x00asm\xff\x00binary"
        self.server.create_response = {
            "id": "deploy-456",
            "site_id": "site-123",
            "deploy_ssl_url": "https://draft.example/deploy-456",
            "state": "uploading",
            "required": [hashlib.sha1(payload).hexdigest()],
        }
        self.client.create_draft(
            site_id="site-123",
            files={"/assets/runtime.wasm": payload},
            title="title",
        )
        self.assertEqual(self.server.requests[1].body, payload)
        self.assertIsNone(self.server.requests[1].json)

    def test_accepts_additive_documented_response_fields(self) -> None:
        self.server.create_response = {
            "id": "deploy-456",
            "site_id": "site-123",
            "deploy_ssl_url": "https://draft.example/deploy-456",
            "state": "uploading",
            "required": [hashlib.sha1(b"index").hexdigest()],
            "admin_url": "https://app.netlify.com/sites/runtime/deploys/deploy-456",
        }
        self.server.deploy_response = {
            "id": "deploy-456",
            "site_id": "site-123",
            "deploy_ssl_url": "https://draft.example/deploy-456",
            "state": "ready",
            "summary": {"status": "complete"},
        }
        self.server.restore_response = {
            "id": "deploy-456",
            "site_id": "site-123",
            "ssl_url": "https://runtime.example",
            "state": "ready",
            "deploy_url": "https://deploy-456--runtime.netlify.app",
        }
        self.assertEqual(self.create_ready_draft().id, "deploy-456")
        self.assertEqual(
            self.client.publish_deploy(site_id="site-123", deploy_id="deploy-456")["id"],
            "deploy-456",
        )

    def test_rejects_malformed_or_missing_or_invalid_required_create_fields(self) -> None:
        valid = {
            "id": "deploy-456",
            "site_id": "site-123",
            "deploy_ssl_url": "https://draft.example/deploy-456",
            "state": "uploading",
            "required": [],
        }
        cases = (
            ({"id": "deploy-456"}, "Netlify API response is invalid"),
            ({**valid, "required": [42]}, "Netlify API response is invalid"),
            ({**valid, "id": 42}, "Netlify API response is invalid"),
            ({**valid, "state": 42}, "Netlify API response is invalid"),
        )
        for response, message in cases:
            with self.subTest(response=response):
                self.server.create_response = response
                with self.assertRaisesRegex(netlify_api.NetlifyError, message):
                    self.create_ready_draft()

    def test_json_parse_failures_are_redacted_without_exception_links(self) -> None:
        for response, leaked_body in (
            (b"malformed-json-body-do-not-leak", "malformed-json-body-do-not-leak"),
            (b"\xffinvalid-utf8-body-do-not-leak", "invalid-utf8-body-do-not-leak"),
        ):
            with self.subTest(response=response):
                self.server.create_response = response
                with self.assertRaises(netlify_api.NetlifyError) as raised:
                    self.create_ready_draft()
                self.assertEqual(str(raised.exception), "Netlify API response is invalid")
                self.assertNotIn(leaked_body, str(raised.exception))
                self.assertIsNone(raised.exception.__cause__)
                self.assertIsNone(raised.exception.__context__)

    def test_rejects_foreign_site_or_non_https_draft_url(self) -> None:
        for response in (
            {
                "id": "deploy-456", "site_id": "other", "deploy_ssl_url": "https://draft.example", "state": "uploading", "required": []
            },
            {
                "id": "deploy-456", "site_id": "site-123", "deploy_ssl_url": "http://draft.example", "state": "uploading", "required": []
            },
        ):
            with self.subTest(response=response):
                self.server.create_response = response
                with self.assertRaises(netlify_api.NetlifyError):
                    self.create_ready_draft()

    def test_rejects_required_digest_not_present_locally(self) -> None:
        self.server.create_response = {
            "id": "deploy-456", "site_id": "site-123", "deploy_ssl_url": "https://draft.example", "state": "uploading", "required": ["0" * 40]
        }
        with self.assertRaisesRegex(netlify_api.NetlifyError, "required file is unavailable"):
            self.create_ready_draft()

    def test_api_error_is_redacted_unreachable_and_never_calls_restore(self) -> None:
        self.server.fail_upload = True
        with self.assertRaises(netlify_api.NetlifyError) as raised:
            self.create_ready_draft()
        self.assertNotIn("test-token", str(raised.exception))
        self.assertNotIn("do-not-leak", str(raised.exception))
        self.assertNotIn("header-do-not-leak", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)
        frames = []
        traceback = raised.exception.__traceback__
        while traceback is not None:
            frames.append(traceback.tb_frame)
            traceback = traceback.tb_next
        self.assertFalse(
            any(
                isinstance(value, HTTPError)
                or isinstance(getattr(value, "__self__", None), HTTPError)
                for frame in frames
                for value in frame.f_locals.values()
            )
        )
        self.assertFalse(any(request.path.endswith("/restore") for request in self.server.requests))

    def test_transport_oserror_is_sanitized_without_exception_links(self) -> None:
        with mock.patch.object(netlify_api.request, "urlopen", side_effect=OSError("dns-do-not-leak")):
            with self.assertRaises(netlify_api.NetlifyError) as raised:
                self.client.publish_deploy(site_id="site-123", deploy_id="deploy-456")
        self.assertEqual(str(raised.exception), "Netlify API request failed")
        self.assertNotIn("dns-do-not-leak", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)

    def test_uploads_one_deterministic_path_per_required_digest(self) -> None:
        payload = b"duplicate"
        self.server.create_response = {
            "id": "deploy-456",
            "site_id": "site-123",
            "deploy_ssl_url": "https://draft.example/deploy-456",
            "state": "uploading",
            "required": [hashlib.sha1(payload).hexdigest()],
        }
        self.client.create_draft(
            site_id="site-123",
            files={"/assets/z.wasm": payload, "/assets/a.wasm": payload},
            title="title",
        )
        uploads = [record for record in self.server.requests if record.method == "PUT"]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0].path, "/api/v1/deploys/deploy-456/files/assets/a.wasm")

    def test_waits_through_non_terminal_state(self) -> None:
        self.server.poll_states = ["uploading", "processing", "ready"]
        draft = self.create_ready_draft()
        self.assertEqual(draft.state, "ready")
        self.assertEqual([request.method for request in self.server.requests].count("GET"), 3)

    def test_rejects_error_state_and_deadline_expiry(self) -> None:
        self.server.poll_states = ["error"]
        with self.assertRaisesRegex(netlify_api.NetlifyError, "Netlify draft deploy failed"):
            self.create_ready_draft()
        self.server.requests.clear()
        self.server._poll_index = 0
        self.server.poll_states = ["processing"]
        with self.assertRaisesRegex(netlify_api.NetlifyError, "Netlify draft deploy timed out"):
            self.create_ready_draft(deadline_seconds=0.0)

    def test_publish_uses_restore_and_requires_the_same_deploy_id(self) -> None:
        published = self.client.publish_deploy(site_id="site-123", deploy_id="deploy-456")
        request = self.server.requests[-1]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.path, "/api/v1/sites/site-123/deploys/deploy-456/restore")
        self.assertEqual(published["id"], "deploy-456")
        self.assertEqual(published["state"], "ready")

    def test_get_site_returns_strict_current_published_deploy(self) -> None:
        site = self.client.get_site(site_id="site-123")
        self.assertEqual(site.id, "site-123")
        self.assertEqual(site.state, "current")
        self.assertEqual(site.ssl_url, "https://runtime.example")
        self.assertIsNotNone(site.published_deploy)
        self.assertEqual(site.published_deploy.id, "prior-123")
        self.assertEqual(
            site.published_deploy.deploy_ssl_url,
            "https://prior-123--runtime.netlify.app",
        )
        self.assertEqual(self.server.requests[-1].method, "GET")
        self.assertEqual(self.server.requests[-1].path, "/api/v1/sites/site-123")

    def test_get_site_accepts_no_prior_and_rejects_unusable_or_foreign_prior(self) -> None:
        self.server.site_response = {
            "id": "site-123",
            "state": "current",
            "disabled": False,
            "ssl_url": "https://runtime.example",
            "published_deploy": None,
        }
        self.assertIsNone(self.client.get_site(site_id="site-123").published_deploy)
        for prior in (
            {"id": "prior-123", "site_id": "other", "deploy_ssl_url": "https://prior.example", "state": "ready"},
            {"id": "prior-123", "site_id": "site-123", "deploy_ssl_url": "http://prior.example", "state": "ready"},
            {"id": "prior-123", "site_id": "site-123", "deploy_ssl_url": "https://prior.example", "state": "error"},
        ):
            with self.subTest(prior=prior):
                self.server.site_response = {
                    "id": "site-123",
                    "state": "current",
                    "disabled": False,
                    "ssl_url": "https://runtime.example",
                    "published_deploy": prior,
                }
                with self.assertRaisesRegex(netlify_api.NetlifyError, "published deploy"):
                    self.client.get_site(site_id="site-123")

    def test_get_site_uses_official_disabled_flag_as_serving_state(self) -> None:
        self.server.site_response = {
            "id": "site-123",
            "state": "current",
            "disabled": True,
            "ssl_url": "https://runtime.example",
            "published_deploy": {
                "id": "prior-123",
                "site_id": "site-123",
                "deploy_ssl_url": "https://prior-123--runtime.netlify.app",
                "state": "ready",
            },
        }
        self.assertEqual(self.client.get_site(site_id="site-123").state, "disabled")

    def test_get_site_file_count_accepts_exact_file_inventory(self) -> None:
        self.assertEqual(self.client.get_site_file_count(site_id="site-123"), 1)
        self.assertEqual(self.server.requests[-1].method, "GET")
        self.assertEqual(
            self.server.requests[-1].path, "/api/v1/sites/site-123/files"
        )

        self.server.site_files_response = []
        self.assertEqual(self.client.get_site_file_count(site_id="site-123"), 0)

    def test_get_site_file_count_rejects_malformed_or_duplicate_inventory(self) -> None:
        valid = {
            "id": "file-123",
            "path": "/index.html",
            "sha": "a" * 40,
            "mime_type": "text/html",
            "size": 5,
        }
        for response in (
            {},
            [None],
            [{**valid, "path": "index.html"}],
            [{**valid, "path": "/../index.html"}],
            [{**valid, "sha": "not-a-sha1"}],
            [{**valid, "size": -1}],
            [valid, {**valid, "id": "file-456"}],
        ):
            with self.subTest(response=response):
                self.server.site_files_response = response
                with self.assertRaisesRegex(
                    netlify_api.NetlifyError, "site files are invalid"
                ):
                    self.client.get_site_file_count(site_id="site-123")

    def test_disable_site_uses_official_reversible_endpoint(self) -> None:
        status_code = self.client.disable_site(
            site_id="site-123", reason="failed first publication"
        )
        self.assertEqual(status_code, 204)
        request = self.server.requests[-1]
        self.assertEqual(request.method, "PUT")
        self.assertEqual(
            request.path,
            "/api/v1/sites/site-123/disable?reason=failed%20first%20publication",
        )

    def test_publish_rejects_wrong_identity_or_non_https_production_url(self) -> None:
        for response in (
            {"id": "other", "site_id": "site-123", "ssl_url": "https://runtime.example", "state": "ready"},
            {"id": "deploy-456", "site_id": "site-123", "ssl_url": "http://runtime.example", "state": "ready"},
            {"id": "deploy-456", "site_id": "site-123", "ssl_url": "https://runtime.example", "state": "current"},
        ):
            with self.subTest(response=response):
                self.server.restore_response = response
                with self.assertRaises(netlify_api.NetlifyError):
                    self.client.publish_deploy(site_id="site-123", deploy_id="deploy-456")


if __name__ == "__main__":
    unittest.main()
