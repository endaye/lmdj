"""Owned server readiness and unmodified official Creator security headers."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import urlopen


def main():
    repo, run, ready = map(Path, sys.argv[1:4])
    pid, nonce = int(sys.argv[4]), sys.argv[5]
    deadline = time.monotonic() + 30
    value = None
    while time.monotonic() < deadline:
        os.kill(pid, 0)
        if ready.exists():
            value = json.loads(ready.read_text())
            break
        time.sleep(0.05)
    if (not isinstance(value, dict) or set(value) != {"host", "nonce", "pid", "port"}
            or value["host"] != "127.0.0.1" or value["pid"] != pid
            or value["nonce"] != nonce or type(value["port"]) is not int
            or not 1 <= value["port"] <= 65535):
        raise RuntimeError("owned server did not prove its PID, nonce and loopback port")
    spec = importlib.util.spec_from_file_location("count_in_official_server", repo / "tools/web-runtime/serve_distribution.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    headers = {**server.SECURITY_HEADERS, "Content-Security-Policy": server.CREATOR_CSP}
    evidence = []
    for name in ("index.html", "host-manifest.json"):
        url = f"http://127.0.0.1:{value['port']}/{name}"
        with urlopen(url, timeout=5) as response:
            if response.status != 200 or response.geturl() != url:
                raise RuntimeError(f"unexpected readiness response: {name}")
            for key, expected in headers.items():
                if response.headers.get_all(key) != [expected]:
                    raise RuntimeError(f"official security header mismatch: {key}")
            data = response.read()
        if data != run.joinpath("dist", name).read_bytes():
            raise RuntimeError(f"served candidate bytes changed: {name}")
        evidence.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    run.joinpath("server-readiness.json").write_text(json.dumps({
        "ready": value, "headers": headers, "served": evidence,
    }, indent=2, sort_keys=True) + "\n")
    print("owned server readiness, complete bytes and official Creator CSP: PASS")


if __name__ == "__main__":
    main()
