#!/usr/bin/env python3

from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest
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
        try:
            self.json = json.loads(body)
        except json.JSONDecodeError:
            self.json = None


class FakeNetlifyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeNetlifyHandler)
        self.requests: list[RequestRecord] = []
        self.create_response: object | None = None
        self.deploy_response: object | None = None
        self.restore_response: object | None = None
        self.fail_upload = False
        self.poll_states: list[str] = ["ready"]
        self._poll_index = 0

    def response(self, handler: BaseHTTPRequestHandler, status: int, document: object) -> None:
        body = document if isinstance(document, bytes) else json.dumps(document).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
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
                "state": "current",
            }
            self.server.response(self, 200, response)
            return
        self.server.response(self, 404, {"error": "not found"})

    def do_PUT(self) -> None:
        self._record()
        if self.server.fail_upload:
            self.server.response(self, 500, {"token": "do-not-leak"})
            return
        self.server.response(self, 200, {})

    def do_GET(self) -> None:
        self._record()
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

    def test_rejects_malformed_or_nonconforming_create_response(self) -> None:
        cases = (
            (b"not-json", "Netlify API response is invalid"),
            ({"id": "deploy-456"}, "Netlify API response is invalid"),
            (
                {
                    "id": "deploy-456",
                    "site_id": "site-123",
                    "deploy_ssl_url": "https://draft.example/deploy-456",
                    "state": "uploading",
                    "required": [],
                    "unexpected": True,
                },
                "Netlify API response is invalid",
            ),
        )
        for response, message in cases:
            with self.subTest(response=response):
                self.server.create_response = response
                with self.assertRaisesRegex(netlify_api.NetlifyError, message):
                    self.create_ready_draft()

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

    def test_api_error_is_redacted_and_never_calls_restore(self) -> None:
        self.server.fail_upload = True
        with self.assertRaises(netlify_api.NetlifyError) as raised:
            self.create_ready_draft()
        self.assertNotIn("test-token", str(raised.exception))
        self.assertNotIn("do-not-leak", str(raised.exception))
        self.assertFalse(any(request.path.endswith("/restore") for request in self.server.requests))

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
        self.assertEqual(published["state"], "current")

    def test_publish_rejects_wrong_identity_or_non_https_production_url(self) -> None:
        for response in (
            {"id": "other", "site_id": "site-123", "ssl_url": "https://runtime.example", "state": "current"},
            {"id": "deploy-456", "site_id": "site-123", "ssl_url": "http://runtime.example", "state": "current"},
        ):
            with self.subTest(response=response):
                self.server.restore_response = response
                with self.assertRaises(netlify_api.NetlifyError):
                    self.client.publish_deploy(site_id="site-123", deploy_id="deploy-456")


if __name__ == "__main__":
    unittest.main()
