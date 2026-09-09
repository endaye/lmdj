#!/usr/bin/env python3

import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_ROOT = (REPO_ROOT / "build/core").resolve()
REQUEST_ROOT = Path(__file__).resolve().parent / "requests"
TIMEOUT_SECONDS = 20
PATTERN_ID = "00000000-0000-4000-8000-000000000010"
RECOVERY_SESSION_ID = "00000000-0000-4000-8000-000000000301"
SWITCH_PATTERN_ID = "00000000-0000-4000-8000-000000000310"
KICK_ASSET_ID = "00000000-0000-4000-8000-000000000101"
CAPABILITY = "proof.candidate.v2"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def replace_placeholders(value: object, replacements: dict[str, str]) -> object:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [
            replace_placeholders(member, replacements) for member in value
        ]
    if isinstance(value, dict):
        return {
            key: replace_placeholders(member, replacements)
            for key, member in value.items()
        }
    return value


def request_fixture(name: str, replacements: dict[str, str]) -> dict:
    value = json.loads(
        (REQUEST_ROOT / name).read_text(encoding="utf-8")
    )
    rendered = replace_placeholders(value, replacements)
    assert isinstance(rendered, dict)
    return rendered


def cli_request(
    executable: Path,
    workspace: Path,
    assembly: Path,
    surface: str,
    request: dict,
    expected_exit: int = 0,
) -> dict:
    completed = subprocess.run(
        [
            str(executable),
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
        completed.returncode,
        completed.stdout,
        completed.stderr,
        request,
    )
    assert completed.stderr == b""
    text = completed.stdout.decode("utf-8", errors="strict")
    response = json.loads(text)
    assert isinstance(response, dict)
    assert text == canonical_json(response) + "\n"
    return response


def assert_success(response: dict, revision: int | None) -> dict:
    assert set(response) == {"ok", "result", "project_revision"}
    assert response["ok"] is True
    assert response["project_revision"] == revision
    assert isinstance(response["result"], dict)
    return response["result"]


def assert_error(response: dict, code: str) -> dict:
    assert set(response) == {"ok", "error"}
    assert response["ok"] is False
    assert response["error"]["code"] == code
    return response["error"]


def bundle_state(project: Path) -> dict[str, tuple[int, str]]:
    state: dict[str, tuple[int, str]] = {}
    for path in sorted(project.rglob("*")):
        assert not path.is_symlink(), path
        if not path.is_file():
            continue
        payload = path.read_bytes()
        state[path.relative_to(project).as_posix()] = (
            len(payload),
            hashlib.sha256(payload).hexdigest(),
        )
    return state


def communicate(process: subprocess.Popen) -> tuple[bytes, bytes]:
    try:
        return process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=TIMEOUT_SECONDS)
        raise


def _proof_scope(path: Path) -> tuple[str, ...]:
    value = os.fspath(path)
    if (
        not path.is_absolute()
        or os.path.normpath(value) != value
        or path == Path("/")
    ):
        raise ValueError("proof mutation path must be normalized and absolute")
    resolved = path.resolve(strict=False)
    try:
        relative = resolved.relative_to(BUILD_ROOT)
    except ValueError as error:
        raise ValueError("proof mutation path must stay under build/core") from error
    parts = relative.parts
    markers = [
        index
        for index, part in enumerate(parts)
        if part in {"proof-runs", "proof-ctest"}
    ]
    if len(markers) != 1 or markers[0] + 1 >= len(parts):
        raise ValueError("proof mutation path is outside a unique proof scope")
    current = BUILD_ROOT
    for part in parts:
        current /= part
        if current.exists() and current.is_symlink():
            raise ValueError("proof mutation path must not traverse symlinks")
    marker = markers[0]
    return (
        parts[: marker + 2]
        if parts[marker] == "proof-runs"
        else parts[: marker + 1]
    )


def validate_mutation_paths(run_root: Path, output_wav: Path) -> None:
    if _proof_scope(run_root) != _proof_scope(output_wav):
        raise ValueError("proof run root and output must share one proof scope")


class MCP:
    def __init__(
        self,
        library: Path,
        workspace: Path,
        assembly: Path,
    ) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(REPO_ROOT / "apps/core-mcp")
        sanitizer_runtime = environment.get("LMDJ_ASAN_RUNTIME")
        if sanitizer_runtime:
            if sys.platform == "darwin":
                environment["DYLD_INSERT_LIBRARIES"] = sanitizer_runtime
            elif sys.platform.startswith("linux"):
                environment["LD_PRELOAD"] = sanitizer_runtime
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "lmdj_core_mcp",
                "--library",
                str(library),
                "--workspace",
                str(workspace),
                "--assembly",
                str(assembly),
            ],
            cwd=REPO_ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.identifier = 0
        initialized = self.request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "proof", "version": "1.0.0"},
            },
        )
        assert initialized["protocolVersion"] == "2025-11-25"
        self.send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        )
        self.assert_silent()

    def send(self, message: dict) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(
            (canonical_json(message) + "\n").encode("utf-8")
        )
        self.process.stdin.flush()

    def receive(self) -> dict:
        assert self.process.stdout is not None
        ready, _, _ = select.select(
            [self.process.stdout.fileno()],
            [],
            [],
            TIMEOUT_SECONDS,
        )
        if not ready:
            self.process.kill()
            _, stderr = communicate(self.process)
            raise AssertionError("MCP response timeout", stderr)
        line = self.process.stdout.readline()
        assert line, communicate(self.process)
        response = json.loads(line)
        assert line == (canonical_json(response) + "\n").encode("utf-8")
        return response

    def assert_silent(self) -> None:
        assert self.process.stdout is not None
        ready, _, _ = select.select(
            [self.process.stdout.fileno()],
            [],
            [],
            0.15,
        )
        assert not ready

    def request(self, method: str, params: dict) -> dict:
        self.identifier += 1
        self.send(
            {
                "jsonrpc": "2.0",
                "id": self.identifier,
                "method": method,
                "params": params,
            }
        )
        response = self.receive()
        assert response["id"] == self.identifier
        assert "error" not in response, response
        return response["result"]

    def tool(self, name: str, arguments: dict) -> dict:
        result = self.request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        envelope = result["structuredContent"]
        assert result["content"] == [
            {"type": "text", "text": canonical_json(envelope)}
        ]
        return envelope

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        self.process.stdin = None
        stdout, stderr = communicate(self.process)
        assert self.process.returncode == 0
        assert stdout == b""
        assert stderr == b""


def proof(
    executable: Path,
    library: Path,
    assembly: Path,
    run_root: Path,
    output_wav: Path,
) -> None:
    validate_mutation_paths(run_root, output_wav)
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    workspace.mkdir()
    project = run_root / "proof-beat.lmdj"
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    output_wav.unlink(missing_ok=True)
    replacements = {
        "$PROJECT_PATH": str(project),
        "$KICK_PATH": str(
            (REPO_ROOT / "tests/fixtures/audio/kick.wav").resolve()
        ),
        "$SNARE_PATH": str(
            (REPO_ROOT / "tests/fixtures/audio/snare.wav").resolve()
        ),
    }

    for name, expected_revision in (
        ("create-project.json", 0),
        ("import-kick.json", 1),
        ("import-snare.json", 2),
        ("assign-kick.json", 3),
        ("assign-snare.json", 4),
    ):
        result = cli_request(
            executable,
            workspace,
            assembly,
            "command",
            request_fixture(name, replacements),
        )
        assert_success(result, expected_revision)

    recorded = request_fixture("record-pattern.json", replacements)
    assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "command",
            recorded["create"],
        ),
        5,
    )
    recorder = MCP(library, workspace, assembly)
    begin = dict(recorded["begin"])
    begin.pop("operation")
    begun = assert_success(
        recorder.tool("lmdj.sequence.record.begin", begin),
        5,
    )
    assert begun["state"] == "active"
    cross_host = assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "query",
            {
                "operation": "sequence.record.status",
                "project_path": str(project),
            },
        ),
        None,
    )
    assert cross_host["session_id"] == recorded["begin"]["session_id"]
    for event in recorded["events"]:
        assert_success(
            recorder.tool(
                "lmdj.sequence.record.event",
                {
                    "project_path": str(project),
                    "session_id": recorded["begin"]["session_id"],
                    "event": event,
                },
            ),
            5,
        )
    flush = dict(recorded["flush"])
    flush.pop("operation")
    committed = assert_success(
        recorder.tool("lmdj.sequence.record.flush", flush),
        6,
    )
    assert committed["replayed"] is False
    replayed = assert_success(
        recorder.tool("lmdj.sequence.record.flush", flush),
        6,
    )
    assert replayed["replayed"] is True
    stop = dict(recorded["stop"])
    stop.pop("operation")
    assert_success(recorder.tool("lmdj.sequence.record.stop", stop), 6)
    recorder.close()

    inspected = cli_request(
        executable,
        workspace,
        assembly,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )
    project_result = assert_success(inspected, 6)["project"]
    assert sum(len(bank["pads"]) for bank in project_result["banks"]) == 64

    cooked = assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "query",
            {
                "operation": "snapshot.cook",
                "project_path": str(project),
                "pattern_id": PATTERN_ID,
            },
        ),
        6,
    )
    assert cooked["event_count"] == 4
    assert len(cooked["artifact_sha256s"]) == 2
    assert "snapshot_id" not in cooked

    rendered = assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "command",
            {
                "operation": "render.offline",
                "project_path": str(project),
                "pattern_id": PATTERN_ID,
                "output_path": str(output_wav),
            },
        ),
        6,
    )
    expected_sha = (
        REPO_ROOT / "tests/fixtures/golden/one_bar_120bpm.sha256"
    ).read_text(encoding="ascii").split()[0]
    golden = REPO_ROOT / "tests/fixtures/golden/one_bar_120bpm.wav"
    assert output_wav.read_bytes() == golden.read_bytes()
    assert hashlib.sha256(output_wav.read_bytes()).hexdigest() == expected_sha
    assert rendered["artifact"]["sha256"] == expected_sha

    mcp = MCP(library, workspace, assembly)
    mcp_inspected = mcp.tool(
        "lmdj.project.inspect",
        {"project_path": str(project)},
    )
    assert mcp_inspected == inspected

    mcp_providers = assert_success(
        mcp.tool("lmdj.provider.list", {}),
        None,
    )["providers"]
    assert_success(
        mcp.tool(
            "lmdj.provider.select",
            {
                "capability": CAPABILITY,
                "provider_id": "local.proof.success",
            },
        ),
        None,
    )
    provider_arguments = request_fixture(
        "run-failing-provider.json", replacements
    )
    provider_arguments.pop("operation")
    denied_attempt = {
        **provider_arguments,
        "attempt_id": "attempt-proof-policy-denied",
        "region": "remote",
    }
    assert_error(
        mcp.tool("lmdj.provider.run", denied_attempt),
        "PERMISSION_DENIED",
    )
    success_attempt = {
        **provider_arguments,
        "attempt_id": "attempt-proof-success",
    }
    success_candidate = assert_success(
        mcp.tool("lmdj.provider.run", success_attempt),
        None,
    )
    assert success_candidate["outputs"] == [
        {
            "port": "candidate",
            "artifact": {
                "sha256": (
                    "e3b0c44298fc1c149afbf4c8996fb924"
                    "27ae41e4649b934ca495991b7852b855"
                ),
                "media_type": "application/x-lmdj-proof",
                "byte_length": 0,
            },
        }
    ]
    mcp.close()

    providers = assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "query",
            {"operation": "provider.list"},
        ),
        None,
    )["providers"]
    assert [provider["id"] for provider in providers] == [
        "local.proof.failure",
        "local.proof.success",
        "local.sample.slice",
    ]
    assert providers == mcp_providers
    provider_locks = {
        provider["id"]: provider["sha256"]
        for provider in json.loads(
            assembly.with_name("assembly.lock.json").read_text(
                encoding="utf-8"
            )
        )["providers"]
    }
    assert {
        provider["id"]: provider["artifact_sha256"]
        for provider in providers
    } == provider_locks

    assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "command",
            {
                "operation": "provider.select",
                "capability": CAPABILITY,
                "provider_id": "local.proof.failure",
            },
        ),
        None,
    )
    before_failure = bundle_state(project)
    before_revision = project_result["revision"]
    failed = cli_request(
        executable,
        workspace,
        assembly,
        "command",
        request_fixture("run-failing-provider.json", replacements),
        expected_exit=2,
    )
    assert_error(failed, "PROVIDER_FAILED")
    assert bundle_state(project) == before_failure
    after_failure = assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "query",
            {"operation": "project.inspect", "project_path": str(project)},
        ),
        before_revision,
    )["project"]
    assert after_failure["revision"] == before_revision
    terminal = assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "query",
            {
                "operation": "attempt.inspect",
                "attempt_id": "attempt-proof-failure",
            },
        ),
        None,
    )
    assert terminal["status"] == "failed"
    attempt_path = (
        workspace
        / ".lmdj-workspace/attempts/attempt-proof-failure.json"
    )
    assert attempt_path.is_file()
    assert project not in attempt_path.parents

    assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "command",
            {
                "operation": "pattern.create",
                "project_path": str(project),
                "command_id": "00000000-0000-4000-8000-000000000311",
                "expected_revision": 6,
                "pattern_id": SWITCH_PATTERN_ID,
                "bars": 1,
            },
        ),
        7,
    )
    owner = MCP(library, workspace, assembly)
    begun = assert_success(
        owner.tool(
            "lmdj.sequence.record.begin",
            {
                "project_path": str(project),
                "session_id": RECOVERY_SESSION_ID,
                "pattern_id": PATTERN_ID,
                "expected_revision": 7,
                "runtime_frame": 0,
            },
        ),
        7,
    )
    assert begun["state"] == "active"
    assert_success(
        owner.tool(
            "lmdj.sequence.record.event",
            {
                "project_path": str(project),
                "session_id": RECOVERY_SESSION_ID,
                "event": {
                    "slot": {"bank": 0, "pad": 0},
                    "velocity": 100,
                    "runtime_frame": 0,
                    "input_sequence": 1,
                    "pressed": True,
                },
            },
        ),
        7,
    )
    assert_success(
        owner.tool(
            "lmdj.sequence.record.event",
            {
                "project_path": str(project),
                "session_id": RECOVERY_SESSION_ID,
                "event": {
                    "slot": {"bank": 0, "pad": 0},
                    "velocity": 0,
                    "runtime_frame": 12000,
                    "input_sequence": 2,
                    "pressed": False,
                },
            },
        ),
        7,
    )
    rebased = assert_success(
        owner.tool(
            "lmdj.sequence.settings.update",
            {
                "project_path": str(project),
                "command_id": "00000000-0000-4000-8000-000000000312",
                "expected_revision": 7,
                "session_id": RECOVERY_SESSION_ID,
                "runtime_frame": 12000,
                "bpm": 140,
                "quantize_enabled": True,
                "swing_percent": 50,
            },
        ),
        8,
    )
    assert rebased["bpm"] == 140
    switching = assert_success(
        owner.tool(
            "lmdj.sequence.record.switch-request",
            {
                "project_path": str(project),
                "session_id": RECOVERY_SESSION_ID,
                "next_pattern_id": SWITCH_PATTERN_ID,
            },
        ),
        8,
    )
    boundary = switching["effective_runtime_frame"]
    assert switching["pending_pattern_id"] == SWITCH_PATTERN_ID
    switched = assert_success(
        owner.tool(
            "lmdj.sequence.record.flush",
            {
                "project_path": str(project),
                "session_id": RECOVERY_SESSION_ID,
                "command_id": "00000000-0000-4000-8000-000000000313",
                "runtime_frame": boundary,
            },
        ),
        9,
    )
    assert switched["pattern_id"] == SWITCH_PATTERN_ID
    assert switched["pending_pattern_id"] is None
    for sequence, (frame, velocity, pressed) in enumerate(
        ((boundary + 1, 90, True), (boundary + 12000, 0, False)),
        start=3,
    ):
        assert_success(
            owner.tool(
                "lmdj.sequence.record.event",
                {
                    "project_path": str(project),
                    "session_id": RECOVERY_SESSION_ID,
                    "event": {
                        "slot": {"bank": 0, "pad": 1},
                        "velocity": velocity,
                        "runtime_frame": frame,
                        "input_sequence": sequence,
                        "pressed": pressed,
                    },
                },
            ),
            9,
        )
    observed = assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "query",
            {
                "operation": "sequence.record.status",
                "project_path": str(project),
            },
        ),
        None,
    )
    assert observed["session_id"] == RECOVERY_SESSION_ID
    assert observed["pattern_id"] == SWITCH_PATTERN_ID
    owner.close()
    recoverable = assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "query",
            {
                "operation": "sequence.recovery.list",
                "project_path": str(project),
            },
        ),
        None,
    )["candidates"]
    candidate = next(
        item for item in recoverable
        if item["session_id"] == RECOVERY_SESSION_ID
    )
    assert candidate["pattern_id"] == SWITCH_PATTERN_ID
    assert candidate["reason"] == "owner_lost"
    recovered = assert_success(
        cli_request(
            executable,
            workspace,
            assembly,
            "command",
            {
                "operation": "sequence.recovery.apply",
                "project_path": str(project),
                "session_id": RECOVERY_SESSION_ID,
                "destination_pattern_id": None,
            },
        ),
        10,
    )
    assert recovered["committed_revision"] == 10

    print("Project pads: 64")
    print("Golden audio: MATCH")
    print("CLI/MCP state parity: MATCH")
    print("Failed attempt project mutation: NONE")
    print("Sequence flush replay: IDEMPOTENT")
    print("Next-Bar switch: ACKNOWLEDGED")
    print("Owner-loss recovery: APPLIED")


def main() -> int:
    if len(sys.argv) != 6:
        raise SystemExit(
            "usage: headless_core_proof.py CLI LIBRARY ASSEMBLY RUN_ROOT OUTPUT_WAV"
        )
    paths = [Path(value).expanduser() for value in sys.argv[1:]]
    if not all(path.is_absolute() for path in paths):
        raise SystemExit("all proof paths must be absolute")
    executable, library, assembly, run_root, output_wav = paths
    executable.resolve(strict=True)
    library.resolve(strict=True)
    assembly.resolve(strict=True)
    proof(executable, library, assembly, run_root, output_wav)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
