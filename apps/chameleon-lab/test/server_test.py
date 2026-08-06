#!/usr/bin/env python3

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import urlopen


LAB_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = LAB_ROOT / "server.py"


def clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def wait_for_port(port_file: Path, process: subprocess.Popen) -> int:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            raise AssertionError((process.returncode, stdout, stderr))
        if port_file.is_file():
            value = port_file.read_text(encoding="utf-8").strip()
            if value:
                return int(value)
        time.sleep(0.02)
    process.kill()
    stdout, stderr = process.communicate(timeout=2)
    raise AssertionError(("server did not write port", stdout, stderr))


def stop_server(process: subprocess.Popen) -> tuple[str, str]:
    process.terminate()
    try:
        return process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.communicate(timeout=5)


def assert_headers(response) -> None:
    expected = {
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Embedder-Policy": "require-corp",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cache-Control": "no-store",
    }
    for name, value in expected.items():
        assert response.headers[name] == value, (name, response.headers)


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="lmdj-chameleon-server-test-"
    ) as temporary:
        temporary_root = Path(temporary)
        port_file = temporary_root / "port.txt"
        process = subprocess.Popen(
            [
                sys.executable,
                str(SERVER_PATH),
                "--bind",
                "127.0.0.1",
                "--port",
                "0",
                "--write-port",
                str(port_file),
            ],
            cwd=LAB_ROOT,
            env=clean_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        port = wait_for_port(port_file, process)
        base_url = f"http://127.0.0.1:{port}"
        try:
            with urlopen(f"{base_url}/health.json", timeout=5) as response:
                assert response.status == 200
                assert_headers(response)
                assert json.loads(response.read()) == {
                    "ok": True,
                    "service": "chameleon-lab",
                }
            with urlopen(f"{base_url}/package.json", timeout=5) as response:
                assert response.status == 200
                assert_headers(response)
                package = json.loads(response.read())
                assert package["name"] == "@lmdj/chameleon-lab"
            with urlopen(f"{base_url}/index.html", timeout=5) as response:
                assert response.status == 200
                assert_headers(response)
                page = response.read().decode("utf-8")
                assert '<canvas id="stage"' in page
                assert 'src="src/main.js"' in page
            for path in (
                "/../products/lmdj/version.json",
                "/%2e%2e/products/lmdj/version.json",
            ):
                try:
                    urlopen(f"{base_url}{path}", timeout=5)
                except HTTPError as error:
                    assert error.code == 404, (path, error.code)
                    assert_headers(error)
                else:
                    raise AssertionError(f"path traversal was served: {path}")
        finally:
            stdout, stderr = stop_server(process)
        assert stderr == "", stderr
        assert stdout == f"{base_url}\n", stdout

        incomplete_tls = subprocess.run(
            [
                sys.executable,
                str(SERVER_PATH),
                "--cert-file",
                str(temporary_root / "missing-cert.pem"),
            ],
            cwd=LAB_ROOT,
            env=clean_environment(),
            check=False,
            capture_output=True,
            text=True,
        )
        assert incomplete_tls.returncode == 2
        assert incomplete_tls.stdout == ""
        assert incomplete_tls.stderr.startswith("server error:")
        assert "--cert-file and --key-file must be supplied together" in (
            incomplete_tls.stderr
        )

        unsafe_lan = subprocess.run(
            [
                sys.executable,
                str(SERVER_PATH),
                "--bind",
                "0.0.0.0",
                "--port",
                "0",
            ],
            cwd=LAB_ROOT,
            env=clean_environment(),
            check=False,
            capture_output=True,
            text=True,
        )
        assert unsafe_lan.returncode == 2
        assert unsafe_lan.stdout == ""
        assert unsafe_lan.stderr.startswith("server error:")
        assert "non-loopback binding requires TLS" in unsafe_lan.stderr

    print("chameleon lab server tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
