#!/usr/bin/env python3
"""Deterministic HTTP fixture for scripts/tests/test_creator_smoke.sh."""

from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH = json.loads(
    (ROOT / "apps/web/public/example-patch/patch.json").read_text()
)
EXPORT_BYTES = b"PK\x03\x04creator-smoke-fixture"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    export_requests = 0
    status_requests: dict[str, int] = {}

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str = "application/json",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: object) -> None:
        self._send(status, json.dumps(value).encode())

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/uploads":
            self._json(404, {"detail": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        if b"scene-contract-fail.wav" in payload:
            job_id = "scene-contract-fail"
        elif b"contract-fail.wav" in payload:
            job_id = "contract-fail"
        elif b"http-fail.wav" in payload:
            job_id = "http-fail"
        elif b"nondeterministic.wav" in payload:
            job_id = "nondeterministic"
        elif b"generating.wav" in payload:
            job_id = "generating"
        elif b"failed.wav" in payload:
            job_id = "failed"
        elif b"cancelled.wav" in payload:
            job_id = "cancelled"
        elif b"unknown-state.wav" in payload:
            job_id = "unknown-state"
        elif b"hanging.wav" in payload:
            job_id = "hanging"
        else:
            job_id = "job-smoke"
        self._json(200, {"job_id": job_id, "state": "queued"})

    def do_GET(self) -> None:  # noqa: N802
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "jobs":
            job_id = parts[1]
            if job_id == "hanging":
                time.sleep(5)
            Handler.status_requests[job_id] = (
                Handler.status_requests.get(job_id, 0) + 1
            )
            state = "completed"
            if job_id == "generating" and Handler.status_requests[job_id] == 1:
                state = "generating"
            elif job_id == "failed":
                state = "failed"
            elif job_id == "cancelled":
                state = "cancelled"
            elif job_id == "unknown-state":
                state = "mystery"
            self._json(
                200,
                {
                    "job_id": job_id,
                    "state": state,
                    "patch_id": PATCH["patch_id"],
                    "package_dir": job_id,
                },
            )
            return
        if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "patch":
            patch = PATCH
            if parts[1] == "contract-fail":
                patch = {**PATCH, "pads": PATCH["pads"][:15]}
            elif parts[1] == "scene-contract-fail":
                patch = {
                    **PATCH,
                    "scenes": [
                        {
                            **scene,
                            "pad_indexes": scene["pad_indexes"][:15],
                        }
                        for scene in PATCH["scenes"]
                    ],
                }
            self._json(200, patch)
            return
        if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "export":
            if parts[1] == "http-fail":
                self._json(500, {"detail": "fixture export failure"})
                return
            body = EXPORT_BYTES
            if parts[1] == "nondeterministic":
                Handler.export_requests += 1
                body += str(Handler.export_requests).encode()
            self._send(200, body, "application/zip")
            return
        self._json(404, {"detail": "not found"})

    def log_message(self, _format: str, *_args: object) -> None:
        pass


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: creator_smoke_server.py <port-file>")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Path(sys.argv[1]).write_text(str(server.server_address[1]))
    server.serve_forever()


if __name__ == "__main__":
    main()
