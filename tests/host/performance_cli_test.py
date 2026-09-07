from __future__ import annotations

import json
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ID = "00000000-0000-4000-8000-000000000001"
PATTERN_ID = "00000000-0000-4000-8000-000000000010"
TIMEOUT_SECONDS = 10.0

PERFORMANCE_OPERATIONS = {
    "pattern.slot.assign": "command",
    "pattern.slot.clear": "command",
    "pattern.slot.move": "command",
    "performance.list": "query",
    "performance.inspect": "query",
    "performance.record.begin": "command",
    "performance.record.event": "command",
    "performance.record.launch-request": "command",
    "performance.record.flush": "command",
    "performance.record.stop": "command",
    "performance.record.status": "query",
    "performance.save": "command",
    "performance.discard": "command",
    "performance.recovery.list": "query",
    "performance.recovery.apply": "command",
    "performance.recovery.discard": "command",
    "performance.rename": "command",
    "performance.delete": "command",
    "performance.recording.bind": "command",
    "performance.replay.begin": "command",
    "performance.replay.stop": "command",
    "performance.replay.status": "query",
    "performance.resample.commit": "command",
}
assert len(PERFORMANCE_OPERATIONS) == 23

# Stage 11's Sound Set surface is a second Facade inventory the Native Host
# forwards, kept apart from the Performance one above so P10-D20 stays exactly
# P10-D20. The Facade's `dispatch()` routes an unlisted operation name to
# `attempt_inspect`, so an operation missing from one of these two tables
# misbehaves quietly instead of erroring: pinning the exact set is what makes
# that loud.
SOUNDSET_OPERATIONS = {
    "soundset.audition": "query",
    "soundset.catalog.list": "query",
    "soundset.inspect": "query",
    "soundset.install": "command",
    "soundset.map.preview": "query",
}
assert len(SOUNDSET_OPERATIONS) == 5


def registered_facade_performance_operations() -> dict[str, str]:
    source = (REPO_ROOT / "packages/application-facade/src/application.cpp").read_text(
        encoding="utf-8"
    )
    start = source.index("const std::map<std::string, OperationKind>& operations()")
    end = source.index("\n  };", start)
    entries = re.findall(
        r'\{"((?:pattern\.slot|performance)\.[^"]+)", '
        r"OperationKind::(command|query)\}",
        source[start:end],
    )
    return dict(entries)


def registered_native_performance_operations() -> dict[str, str]:
    source = (REPO_ROOT / "apps/native-host/src/main.cpp").read_text(
        encoding="utf-8"
    )
    start = source.index("kPerformanceOperations{{")
    end = source.index("}};", start)
    entries = re.findall(
        r'\{"([^"]+)", FacadeSurface::(command|query)\}',
        source[start:end],
    )
    return dict(entries)


def registered_facade_soundset_operations() -> dict[str, str]:
    source = (REPO_ROOT / "packages/application-facade/src/application.cpp").read_text(
        encoding="utf-8"
    )
    start = source.index("const std::map<std::string, OperationKind>& operations()")
    end = source.index("\n  };", start)
    entries = re.findall(
        r'\{"(soundset\.[^"]+)", OperationKind::(command|query)\}',
        source[start:end],
    )
    return dict(entries)


def registered_native_soundset_operations() -> dict[str, str]:
    source = (REPO_ROOT / "apps/native-host/src/main.cpp").read_text(
        encoding="utf-8"
    )
    start = source.index("kSoundSetOperations{{")
    end = source.index("}};", start)
    entries = re.findall(
        r'\{"([^"]+)", FacadeSurface::(command|query)\}',
        source[start:end],
    )
    return dict(entries)


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def cli_request(
    cli: Path,
    workspace: Path,
    assembly: Path,
    surface: str,
    request: dict,
    expected_exit: int = 2,
) -> dict:
    completed = subprocess.run(
        [
            str(cli),
            "--workspace",
            str(workspace),
            "--assembly",
            str(assembly),
            surface,
            "--request",
            canonical_json(request),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert completed.returncode == expected_exit, (
        request,
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )
    assert completed.stderr == b""
    response = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    assert completed.stdout.decode("utf-8") == canonical_json(response) + "\n"
    return response


def author_project(
    cli: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
) -> None:
    response = cli_request(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "project.create",
            "project_path": str(project),
            "project_id": PROJECT_ID,
            "bpm": 120,
            "initial_pattern": {
                "pattern_id": PATTERN_ID,
                "bars": 1,
                "events": [],
            },
        },
        expected_exit=0,
    )
    assert response["ok"] is True, response


class NativeProcess:
    def __init__(
        self,
        native: Path,
        workspace: Path,
        assembly: Path,
        project: Path,
    ) -> None:
        self.process = subprocess.Popen(
            [
                str(native),
                "--workspace",
                str(workspace),
                "--assembly",
                str(assembly),
                "--project",
                str(project),
                "--pattern",
                PATTERN_ID,
                "--no-device",
            ],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ready = self.read("ready")
        assert ready["ok"] is True, ready

    def read(self, operation: str) -> dict:
        assert self.process.stdout is not None
        readable, _, _ = select.select(
            [self.process.stdout], [], [], TIMEOUT_SECONDS
        )
        assert readable, (operation, self.process.poll())
        line = self.process.stdout.readline()
        assert line, (operation, self.process.poll())
        decoded = line.decode("utf-8", errors="strict")
        response = json.loads(decoded)
        assert decoded == canonical_json(response) + "\n"
        return response

    def request(self, request: dict) -> dict:
        assert self.process.stdin is not None
        self.process.stdin.write(canonical_json(request).encode("utf-8") + b"\n")
        self.process.stdin.flush()
        return self.read(str(request.get("operation")))

    def close(self) -> None:
        response = self.request({"operation": "quit"})
        assert response["ok"] is True, response
        assert self.process.stdin is not None
        self.process.stdin.close()
        assert self.process.wait(timeout=TIMEOUT_SECONDS) == 0
        assert self.process.stderr is not None
        assert self.process.stderr.read() == b""


def assert_error_envelope(response: dict) -> None:
    assert set(response) == {"ok", "error"}, response
    assert response["ok"] is False
    assert set(response["error"]) == {"code", "message", "details"}


def assert_facade_envelope(response: dict) -> None:
    if response.get("ok") is False:
        assert_error_envelope(response)
        return
    assert set(response) == {"ok", "result", "project_revision"}, response
    assert response["ok"] is True
    assert isinstance(response["result"], dict)
    assert response["project_revision"] is None or isinstance(
        response["project_revision"], int
    )


def cli_operation_kind_contract(
    cli: Path,
    workspace: Path,
    assembly: Path,
) -> None:
    assert registered_facade_performance_operations() == PERFORMANCE_OPERATIONS
    assert registered_native_performance_operations() == PERFORMANCE_OPERATIONS
    assert registered_facade_soundset_operations() == SOUNDSET_OPERATIONS
    assert registered_native_soundset_operations() == SOUNDSET_OPERATIONS
    for operation, surface in PERFORMANCE_OPERATIONS.items():
        request = {"operation": operation}
        response = cli_request(cli, workspace, assembly, surface, request)
        assert_error_envelope(response)
        assert response["error"]["message"] != "operation is unknown"

        wrong_surface = "query" if surface == "command" else "command"
        wrong = cli_request(cli, workspace, assembly, wrong_surface, request)
        assert_error_envelope(wrong)
        assert (
            wrong["error"]["message"]
            == "operation was sent to the wrong Application method"
        )


def native_operation_registration_contract(
    native: Path,
    cli: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
) -> None:
    author_project(cli, workspace, assembly, project)
    process = NativeProcess(native, workspace, assembly, project)
    try:
        for operation in PERFORMANCE_OPERATIONS:
            response = process.request(
                {"operation": operation, "project_path": str(project)}
            )
            assert_facade_envelope(response)
            if response["ok"] is False:
                assert (
                    response["error"]["message"]
                    != "unknown Native Host operation"
                )
                assert (
                    response["error"]["message"]
                    != "operation was sent to the wrong Application method"
                )
    finally:
        process.close()


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: performance_cli_test.py CLI NATIVE_HOST ASSEMBLY_JSON"
        )
    cli = Path(sys.argv[1]).resolve(strict=True)
    native = Path(sys.argv[2]).resolve(strict=True)
    assembly = Path(sys.argv[3]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="lmdj-performance-hosts-") as root:
        workspace = Path(root).resolve()
        cli_operation_kind_contract(cli, workspace, assembly)
        native_operation_registration_contract(
            native,
            cli,
            workspace,
            assembly,
            workspace / "native-performance.lmdj",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
