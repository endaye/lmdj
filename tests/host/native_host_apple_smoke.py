from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True

from native_host_test import (
    HostProcess,
    REPO_ROOT,
    author_project,
)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: native_host_apple_smoke.py HOST")
    if sys.platform != "darwin":
        return 0
    host = Path(sys.argv[1]).resolve(strict=True)
    cli = (host.parent / "lmdj-core").resolve(strict=True)
    assembly = (REPO_ROOT / "products/lmdj/assembly.json").resolve(strict=True)

    with tempfile.TemporaryDirectory(prefix="lmdj-native-host-apple-") as root:
        temp_root = Path(root).resolve()
        workspace = temp_root / "workspace"
        workspace.mkdir()
        project = temp_root / "apple-smoke.lmdj"
        author_project(cli, workspace, assembly, project)
        process = HostProcess(
            host, workspace, assembly, project, no_device=False
        )
        ready = process.read()
        assert ready["ok"] is True, ready
        assert ready["result"]["backend"] == "coreaudio"
        status = process.request({"operation": "status"})
        assert status["ok"] is True, status
        assert status["result"]["host"]["state"] == "running"
        assert process.request({"operation": "stop"})["ok"] is True
        assert process.request({"operation": "start"})["ok"] is True
        process.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
