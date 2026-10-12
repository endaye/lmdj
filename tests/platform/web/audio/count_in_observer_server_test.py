#!/usr/bin/env python3
"""Proof-observer routing only; no product build or audio acceptance claim."""
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
from types import ModuleType
import unittest


ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location(
    "count_in_observer_server", ROOT / "tools/web-runtime/serve_distribution.py"
)
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


class AudioObserverServerTest(unittest.TestCase):
    def test_explicit_frozen_observer_preserves_distribution_and_headers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "dist"
            root.mkdir()
            root = root.resolve()
            (root / "index.html").write_text("verified test shell")
            (root / "host-manifest.json").write_text(json.dumps({"assets": []}))
            observer = Path(temporary) / "observer.js"
            observer.write_text("// owned observer\n")
            verifier = ModuleType("routing_fixture_verifier")
            verifier.DistributionError = ValueError
            calls = []
            verifier.verify_distribution = lambda dist, repo: calls.append((dist, repo))
            server = server_module.make_server(
                root, verifier, ROOT, port=0, test_audio_observer_file=observer
            )
            self.addCleanup(server.server_close)
            self.assertEqual(calls, [(root, ROOT)])
            observer.write_text("// later mutation must not change frozen bytes\n")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(path, headers=None):
                connection = http.client.HTTPConnection(*server.server_address, timeout=2)
                connection.request("GET", path, headers=headers or {})
                response = connection.getresponse()
                result = response.status, dict(response.getheaders()), response.read()
                connection.close()
                return result
            try:
                status, headers, body = request("/__lmdj-test__/audio-observer.js")
                self.assertEqual((status, body), (200, b"// owned observer\n"))
                self.assertEqual(headers["Content-Security-Policy"], server_module.CSP)
                self.assertEqual(headers["Cross-Origin-Embedder-Policy"], "require-corp")
                self.assertEqual(headers["Cache-Control"], "no-store")
                for path in ["/__lmdj-test__/other.js", "/__lmdj-test__/audio-observer.js?x=1",
                             "/__lmdj-test__/%61udio-observer.js", "/observer.js"]:
                    self.assertEqual(request(path)[0], 404, path)
                self.assertEqual(request("/__lmdj-test__/audio-observer.js", {"Range": "bytes=0-1"})[0], 404)
                (root / "index.html").write_text("changed product")
                self.assertEqual(request("/index.html")[0], 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
            default = server_module.make_server(root, verifier, ROOT, port=0)
            self.assertIsNone(default.RequestHandlerClass.keywords["test_audio_observer"])
            default.server_close()
            alias = Path(temporary) / "alias.js"
            alias.symlink_to(observer)
            with self.assertRaises(server_module.ServerError):
                server_module.make_server(root, verifier, ROOT, port=0, test_audio_observer_file=alias)


if __name__ == "__main__":
    unittest.main()
