#!/usr/bin/env python3

import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from unittest import mock


SERVER_PATH = Path(__file__).with_name("server.py")


def load_server_module():
    spec = importlib.util.spec_from_file_location("web_toolchain_server", SERVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_loopback_bind_does_not_resolve_hostname() -> None:
    module = load_server_module()

    with mock.patch.object(
        socket,
        "getfqdn",
        side_effect=AssertionError("loopback bind must not perform reverse DNS"),
    ):
        server = module.ConformanceServer(("127.0.0.1", 0), module.ConformanceHandler)
    try:
        assert server.server_name == "127.0.0.1"
        assert 1 <= server.server_port <= 65_535
    finally:
        server.server_close()


def await_written_port(process: subprocess.Popen, port_file: Path) -> int:
    for _ in range(200):
        if port_file.exists():
            encoded = port_file.read_text(encoding="utf-8")
            if encoded.endswith("\n"):
                return int(encoded)
        assert process.poll() is None, "the conformance server exited early"
        time.sleep(0.05)
    raise AssertionError(f"no port was published to {port_file}")


def assert_health(port: int) -> None:
    deadline = time.monotonic() + 10.0
    while True:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health.json", timeout=0.5
            ) as response:
                payload = json.load(response)
            break
        except (OSError, urllib.error.URLError):
            assert time.monotonic() < deadline, f"port {port} never served health"
            time.sleep(0.05)
    assert payload == {"ok": True, "service": "web-toolchain-conformance"}, payload


def start_server(root: Path, port_file: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            str(SERVER_PATH),
            "--root",
            str(root),
            "--port",
            "0",
            "--write-port",
            str(port_file),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def assert_concurrent_servers_never_contend_for_a_port() -> None:
    """Two lanes on one host, and a lane after a leaked server, both start.

    The Proof used to let Playwright manage the server on a fixed port, so a
    second runner service on the same host -- or a server leaked by a crashed
    lane still holding that port -- failed the next lane at startup instead of
    proving anything (issue #297). An ephemeral port per owner removes the
    shared resource entirely.
    """
    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace)
        processes: list[subprocess.Popen] = []
        try:
            first = start_server(root, root / "first.port")
            processes.append(first)
            second = start_server(root, root / "second.port")
            processes.append(second)
            first_port = await_written_port(first, root / "first.port")
            second_port = await_written_port(second, root / "second.port")
            assert first_port != second_port, (
                f"concurrent owners share port {first_port}"
            )
            assert_health(first_port)
            assert_health(second_port)

            # The first server stays up as the leaked one; a later lane must
            # still get a private port and serve on it.
            second.terminate()
            second.wait(timeout=10)
            third = start_server(root, root / "third.port")
            processes.append(third)
            third_port = await_written_port(third, root / "third.port")
            assert third_port != first_port, (
                f"a later lane inherited the leaked port {first_port}"
            )
            assert_health(third_port)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)


def main() -> int:
    assert_loopback_bind_does_not_resolve_hostname()
    assert_concurrent_servers_never_contend_for_a_port()
    print("Web toolchain server tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
