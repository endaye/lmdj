#!/usr/bin/env python3
"""Exercise the real urllib GET admission policy against a loopback server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest

from kit_test import live_get


class LiveGetTest(unittest.TestCase):
    def setUp(self):
        self.requests = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.path in ("/object/blob/redirect", "/health"):
                    self.send_response(302)
                    self.send_header("Location", "/mirror")
                elif self.path == "/created":
                    self.send_response(201)
                else:
                    self.send_response(200)
                self.end_headers()
                self.wfile.write(b"expected bytes")

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_direct_200_returns_original_bytes(self):
        with live_get(self.origin + "/object/blob/direct") as response:
            self.assertEqual(response.read(), b"expected bytes")

    def test_object_redirect_is_refused_without_fetching_mirror(self):
        with self.assertRaisesRegex(ValueError, "observed 302.*Serve the object directly"):
            live_get(self.origin + "/object/blob/redirect")
        self.assertEqual(self.requests, ["/object/blob/redirect"])

    def test_health_redirect_is_refused_without_fetching_mirror(self):
        with self.assertRaisesRegex(ValueError, "observed 302.*Serve the object directly"):
            live_get(self.origin + "/health")
        self.assertEqual(self.requests, ["/health"])

    def test_other_success_status_is_refused(self):
        with self.assertRaisesRegex(ValueError, "observed 201.*Serve the object directly"):
            live_get(self.origin + "/created")


if __name__ == "__main__":
    unittest.main()
