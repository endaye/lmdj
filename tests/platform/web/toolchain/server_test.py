#!/usr/bin/env python3

import importlib.util
from pathlib import Path
import socket
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


def main() -> int:
    assert_loopback_bind_does_not_resolve_hostname()
    print("Web toolchain server tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
