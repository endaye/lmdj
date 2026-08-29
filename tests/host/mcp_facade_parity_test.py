import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 20
PROTOCOL_VERSION = "2025-11-25"
PROJECT_ID = "00000000-0000-4000-8000-000000000001"
PATTERN_ID = "00000000-0000-4000-8000-000000000010"
KICK_ASSET_ID = "00000000-0000-4000-8000-000000000101"
SNARE_ASSET_ID = "00000000-0000-4000-8000-000000000102"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def uuid(suffix: int) -> str:
    return f"00000000-0000-4000-8000-{suffix:012d}"


def slot(bank: int, pad: int) -> dict:
    return {"bank": bank, "pad": pad}


def playback(
    start: int = 0,
    end: int | None = None,
    mode: str = "one_shot",
    gain: int = 0,
    muted: bool = False,
) -> dict:
    return {
        "trim_start_frame": start,
        "trim_end_frame": end,
        "trigger_mode": mode,
        "gain_millidb": gain,
        "muted": muted,
    }


def pattern() -> dict:
    return {
        "pattern_id": PATTERN_ID,
        "bars": 1,
        "events": [
            {"slot": slot(0, 0), "onset_tick": 0,
             "duration_tick": 240, "velocity": 127},
            {"slot": slot(0, 1), "onset_tick": 960,
             "duration_tick": 240, "velocity": 127},
            {"slot": slot(0, 0), "onset_tick": 1920,
             "duration_tick": 240, "velocity": 127},
            {"slot": slot(0, 1), "onset_tick": 2880,
             "duration_tick": 240, "velocity": 127},
        ],
    }


def author_requests(project: Path) -> list[tuple[str, dict, int]]:
    requests = [
        (
            "command",
            {
                "operation": "project.create",
                "project_path": str(project),
                "project_id": PROJECT_ID,
                "bpm": 120,
                "initial_pattern": pattern(),
            },
            0,
        ),
        (
            "command",
            {
                "operation": "asset.import",
                "project_path": str(project),
                "command_id": uuid(1),
                "expected_revision": 0,
                "asset_id": KICK_ASSET_ID,
                "source_path": str(
                    REPO_ROOT / "tests/fixtures/audio/kick.wav"
                ),
                "media_type": "audio/wav",
            },
            1,
        ),
        (
            "command",
            {
                "operation": "asset.import",
                "project_path": str(project),
                "command_id": uuid(2),
                "expected_revision": 1,
                "asset_id": SNARE_ASSET_ID,
                "source_path": str(
                    REPO_ROOT / "tests/fixtures/audio/snare.wav"
                ),
                "media_type": "audio/wav",
            },
            2,
        ),
        (
            "command",
            {
                "operation": "pad.assign",
                "project_path": str(project),
                "command_id": uuid(3),
                "expected_revision": 2,
                "slot": slot(0, 0),
                "asset_id": KICK_ASSET_ID,
            },
            3,
        ),
        (
            "command",
            {
                "operation": "pad.assign",
                "project_path": str(project),
                "command_id": uuid(4),
                "expected_revision": 3,
                "slot": slot(0, 1),
                "asset_id": SNARE_ASSET_ID,
            },
            4,
        ),
        (
            "command",
            {
                "operation": "pad.assign",
                "project_path": str(project),
                "command_id": uuid(5),
                "expected_revision": 4,
                "slot": slot(0, 0),
                "asset_id": KICK_ASSET_ID,
            },
            5,
        ),
    ]
    return requests


def check_success(envelope: dict, revision: int | None) -> None:
    assert set(envelope) == {"ok", "result", "project_revision"}
    assert envelope["ok"] is True
    assert envelope["project_revision"] == revision


def communicate_with_timeout(
    process: subprocess.Popen,
) -> tuple[bytes, bytes]:
    try:
        return process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=TIMEOUT_SECONDS)
        raise


def cli_request(
    executable: Path,
    workspace: Path,
    surface: str,
    request: dict,
    assembly: Path | None = None,
) -> dict:
    command = [
        str(executable),
        "--workspace",
        str(workspace),
    ]
    if assembly is not None:
        command.extend(["--assembly", str(assembly)])
    command.extend(
        [
            surface,
            "--request",
            canonical_json(request),
        ]
    )
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert completed.returncode == 0, (
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )
    assert completed.stderr == b""
    envelope = json.loads(completed.stdout)
    assert completed.stdout == (
        canonical_json(envelope) + "\n"
    ).encode("utf-8")
    return envelope


class MCP:
    def __init__(
        self,
        library: Path,
        workspace: Path,
        assembly: Path | None = None,
    ) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(REPO_ROOT / "apps/core-mcp")
        sanitizer_runtime = environment.get("LMDJ_ASAN_RUNTIME")
        if sanitizer_runtime:
            if sys.platform == "darwin":
                environment["DYLD_INSERT_LIBRARIES"] = sanitizer_runtime
            elif sys.platform.startswith("linux"):
                environment["LD_PRELOAD"] = sanitizer_runtime
        command = [
            sys.executable,
            "-m",
            "lmdj_core_mcp",
            "--library",
            str(library),
            "--workspace",
            str(workspace),
        ]
        if assembly is not None:
            command.extend(["--assembly", str(assembly)])
        self.process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.next_id = 1
        initialized = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "parity", "version": "0.1.0"},
            },
        )
        assert initialized["protocolVersion"] == PROTOCOL_VERSION
        self.send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        )
        ready, _, _ = select.select(
            [self.process.stdout.fileno()], [], [], 0.15
        )
        assert not ready

    def send(self, message: dict) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(
            canonical_json(message).encode("utf-8") + b"\n"
        )
        self.process.stdin.flush()

    def request(self, method: str, params: dict) -> dict:
        identifier = self.next_id
        self.next_id += 1
        self.send(
            {
                "jsonrpc": "2.0",
                "id": identifier,
                "method": method,
                "params": params,
            }
        )
        assert self.process.stdout is not None
        ready, _, _ = select.select(
            [self.process.stdout.fileno()],
            [],
            [],
            TIMEOUT_SECONDS,
        )
        if not ready:
            self.process.kill()
            _, stderr = communicate_with_timeout(self.process)
            raise AssertionError(
                "timed out waiting for MCP parity response",
                stderr,
            )
        line = self.process.stdout.readline()
        response = json.loads(line)
        assert line == (canonical_json(response) + "\n").encode("utf-8")
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == identifier
        assert "error" not in response, response
        return response["result"]

    def tool(self, name: str, arguments: dict) -> dict:
        result = self.request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        assert json.loads(result["content"][0]["text"]) == (
            result["structuredContent"]
        )
        assert result["isError"] is (
            result["structuredContent"]["ok"] is False
        )
        return result["structuredContent"]

    def close(self) -> None:
        assert self.process.stdin is not None
        self.process.stdin.close()
        self.process.stdin = None
        stdout, stderr = communicate_with_timeout(self.process)
        assert self.process.returncode == 0
        assert stdout == b""
        assert stderr == b""


def cli_author_mcp_consume(
    cli: Path,
    library: Path,
    workspace: Path,
    temp_root: Path,
) -> None:
    project = temp_root / "cli-authored.lmdj"
    for surface, request, revision in author_requests(project):
        envelope = cli_request(cli, workspace, surface, request)
        check_success(envelope, revision)
    journal = project / "recovery/active/sequence.jsonl"
    assert not journal.exists()
    cli_inspect = cli_request(
        cli,
        workspace,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )
    manifest_before = (project / "manifest.json").read_bytes()

    mcp = MCP(library, workspace)
    mcp_inspect = mcp.tool(
        "lmdj.project.inspect",
        {"project_path": str(project)},
    )
    assert mcp_inspect == cli_inspect
    cooked = mcp.tool(
        "lmdj.snapshot.cook",
        {"project_path": str(project), "pattern_id": PATTERN_ID},
    )
    check_success(cooked, 5)
    assert cooked["result"]["event_count"] == 4
    assert "snapshot_id" not in canonical_json(cooked)
    output = temp_root / "cli-authored-mcp-render.wav"
    rendered = mcp.tool(
        "lmdj.render.offline",
        {
            "project_path": str(project),
            "pattern_id": PATTERN_ID,
            "output_path": str(output),
        },
    )
    check_success(rendered, 5)
    mcp.close()
    assert (project / "manifest.json").read_bytes() == manifest_before
    assert_golden(output, rendered)


def mcp_author_cli_consume(
    cli: Path,
    library: Path,
    workspace: Path,
    temp_root: Path,
) -> None:
    project = temp_root / "mcp-authored.lmdj"
    mcp = MCP(library, workspace)
    for _surface, request, revision in author_requests(project):
        operation = request["operation"]
        arguments = {
            key: value for key, value in request.items() if key != "operation"
        }
        envelope = mcp.tool(f"lmdj.{operation}", arguments)
        check_success(envelope, revision)
    journal = project / "recovery/active/sequence.jsonl"
    assert not journal.exists()
    mcp_inspect = mcp.tool(
        "lmdj.project.inspect",
        {"project_path": str(project)},
    )
    mcp.close()
    manifest_before = (project / "manifest.json").read_bytes()

    cli_inspect = cli_request(
        cli,
        workspace,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )
    assert cli_inspect == mcp_inspect
    cooked = cli_request(
        cli,
        workspace,
        "query",
        {
            "operation": "snapshot.cook",
            "project_path": str(project),
            "pattern_id": PATTERN_ID,
        },
    )
    check_success(cooked, 5)
    assert "snapshot_id" not in canonical_json(cooked)
    output = temp_root / "mcp-authored-cli-render.wav"
    rendered = cli_request(
        cli,
        workspace,
        "command",
        {
            "operation": "render.offline",
            "project_path": str(project),
            "pattern_id": PATTERN_ID,
            "output_path": str(output),
        },
    )
    check_success(rendered, 5)
    assert (project / "manifest.json").read_bytes() == manifest_before
    assert_golden(output, rendered)


def assert_golden(output: Path, rendered: dict) -> None:
    golden = REPO_ROOT / "tests/fixtures/golden/one_bar_120bpm.wav"
    expected_sha = (
        REPO_ROOT / "tests/fixtures/golden/one_bar_120bpm.sha256"
    ).read_text(encoding="ascii").split()[0]
    assert output.read_bytes() == golden.read_bytes()
    assert hashlib.sha256(output.read_bytes()).hexdigest() == expected_sha
    assert rendered["result"]["artifact"]["sha256"] == expected_sha


def sample_facade_parity(
    cli: Path,
    library: Path,
    workspace: Path,
    temp_root: Path,
) -> None:
    project = temp_root / "sample-parity.lmdj"
    for surface, request, revision in (
        (
            "command",
            {
                "operation": "project.create",
                "project_path": str(project),
                "project_id": uuid(701),
                "bpm": 120,
            },
            0,
        ),
        (
            "command",
            {
                "operation": "asset.import",
                "project_path": str(project),
                "command_id": uuid(702),
                "expected_revision": 0,
                "asset_id": uuid(703),
                "source_path": str(
                    REPO_ROOT / "tests/fixtures/audio/mono-44100.wav"
                ),
                "media_type": "audio/wav",
            },
            1,
        ),
        (
            "command",
            {
                "operation": "pad.assign",
                "project_path": str(project),
                "command_id": uuid(704),
                "expected_revision": 1,
                "slot": slot(0, 0),
                "asset_id": uuid(703),
            },
            2,
        ),
    ):
        check_success(
            cli_request(cli, workspace, surface, request), revision
        )

    inspect_request = {
        "operation": "sample.inspect",
        "project_path": str(project),
        "slot": slot(0, 0),
    }
    cli_inspect = cli_request(cli, workspace, "query", inspect_request)
    check_success(cli_inspect, 2)
    mcp = MCP(library, workspace)
    mcp_inspect = mcp.tool(
        "lmdj.sample.inspect",
        {"project_path": str(project), "slot": slot(0, 0)},
    )
    assert mcp_inspect == cli_inspect

    quota_arguments = {
        "project_path": str(project),
        "slot": slot(0, 0),
    }
    cli_quota = cli_request(
        cli,
        workspace,
        "query",
        {"operation": "sample.quota", **quota_arguments},
    )
    mcp_quota = mcp.tool("lmdj.sample.quota", quota_arguments)
    assert mcp_quota == cli_quota
    assert cli_quota["result"]["project_revision"] == 2
    assert cli_quota["result"]["bank_used_bytes"] == 0
    assert cli_quota["result"]["project_used_bytes"] == 0
    assert cli_quota["result"]["effective_remaining_frames"] == 16_777_216
    assert cli_quota["result"]["consumed"] == [
        {
            "slot": slot(0, 0),
            "prepared_bytes": 36,
            "prepared_frames": 9,
        }
    ]

    waveform_arguments = {
        "project_path": str(project),
        "slot": slot(0, 0),
        "window": {
            "start_frame": 0,
            "end_frame": 8,
            "bucket_count": 4,
        },
    }
    cli_waveform = cli_request(
        cli,
        workspace,
        "query",
        {"operation": "sample.waveform", **waveform_arguments},
    )
    mcp_waveform = mcp.tool("lmdj.sample.waveform", waveform_arguments)
    assert mcp_waveform == cli_waveform
    assert [
        bucket["peak_magnitude"]
        for bucket in cli_waveform["result"]["buckets"]
    ] == [32768, 8192, 4096, 0]

    update_arguments = {
        "project_path": str(project),
        "command_id": uuid(705),
        "expected_revision": 2,
        "slot": slot(0, 0),
        "playback": playback(1, 7, "loop_gate", -1200, False),
    }
    cli_update = cli_request(
        cli,
        workspace,
        "command",
        {"operation": "sample.update_pad", **update_arguments},
    )
    check_success(cli_update, 3)
    assert mcp.tool(
        "lmdj.sample.inspect",
        {"project_path": str(project), "slot": slot(0, 0)},
    )["result"]["playback"] == update_arguments["playback"]

    mcp_reset = mcp.tool(
        "lmdj.sample.reset_pad",
        {
            "project_path": str(project),
            "command_id": uuid(706),
            "expected_revision": 3,
            "slot": slot(0, 0),
        },
    )
    check_success(mcp_reset, 4)
    cli_reset_inspect = cli_request(
        cli, workspace, "query", inspect_request
    )
    assert cli_reset_inspect["result"]["playback"] == playback()

    cli_replayed_update = cli_request(
        cli,
        workspace,
        "command",
        {"operation": "sample.update_pad", **update_arguments},
    )
    check_success(cli_replayed_update, 4)
    assert cli_replayed_update["result"]["committed_revision"] == 3
    mcp_replayed_update = mcp.tool(
        "lmdj.sample.update_pad", update_arguments
    )
    assert mcp_replayed_update == cli_replayed_update

    advanced = cli_request(
        cli,
        workspace,
        "command",
        {
            "operation": "sample.update_pad",
            "project_path": str(project),
            "command_id": uuid(707),
            "expected_revision": 4,
            "slot": slot(0, 0),
            "playback": playback(1, 7, "loop_toggle", -600, False),
        },
    )
    check_success(advanced, 5)
    reset_arguments = {
        "project_path": str(project),
        "command_id": uuid(706),
        "expected_revision": 3,
        "slot": slot(0, 0),
    }
    mcp_replayed_reset = mcp.tool(
        "lmdj.sample.reset_pad", reset_arguments
    )
    check_success(mcp_replayed_reset, 5)
    assert mcp_replayed_reset["result"]["committed_revision"] == 4
    cli_replayed_reset = cli_request(
        cli,
        workspace,
        "command",
        {"operation": "sample.reset_pad", **reset_arguments},
    )
    assert cli_replayed_reset == mcp_replayed_reset
    mcp.close()


def provider_binding_parity(
    cli: Path,
    library: Path,
    temp_root: Path,
) -> None:
    assembly = REPO_ROOT / "products/lmdj/assembly.json"
    capability = "proof.candidate.v2"
    provider_id = "local.proof.success"
    arguments = {
        "attempt_id": "attempt-binding-parity",
        "capability": capability,
        "inputs": [
            {
                "port": "inputs",
                "artifact": {
                    "sha256": "a" * 64,
                    "media_type": "application/octet-stream",
                    "byte_length": 1,
                },
            }
        ],
        "parameters": {},
        "data_classification": "public",
        "platform": "test",
        "region": "local",
        "required_permissions": ["proof.execute"],
    }

    cli_workspace = temp_root / "provider-cli-workspace"
    cli_workspace.mkdir()
    check_success(
        cli_request(
            cli,
            cli_workspace,
            "command",
            {
                "operation": "provider.select",
                "capability": capability,
                "provider_id": provider_id,
            },
            assembly,
        ),
        None,
    )
    cli_result = cli_request(
        cli,
        cli_workspace,
        "command",
        {"operation": "provider.run", **arguments},
        assembly,
    )

    mcp_workspace = temp_root / "provider-mcp-workspace"
    mcp_workspace.mkdir()
    mcp = MCP(library, mcp_workspace, assembly)
    check_success(
        mcp.tool(
            "lmdj.provider.select",
            {"capability": capability, "provider_id": provider_id},
        ),
        None,
    )
    mcp_result = mcp.tool("lmdj.provider.run", arguments)
    mcp.close()

    assert mcp_result == cli_result
    assert cli_result["result"]["outputs"][0]["port"] == "candidate"
    assert set(cli_result["result"]["outputs"][0]) == {
        "port",
        "artifact",
    }


def sequence_cross_host_observer(
    cli: Path,
    library: Path,
    temp_root: Path,
) -> None:
    workspace = temp_root / "sequence-observer-workspace"
    workspace.mkdir()
    project = temp_root / "sequence-observer.lmdj"
    session_id = uuid(901)
    mcp = MCP(library, workspace)
    for _surface, request, revision in author_requests(project):
        arguments = {
            key: value for key, value in request.items() if key != "operation"
        }
        check_success(
            mcp.tool(f"lmdj.{request['operation']}", arguments), revision
        )
    begun = mcp.tool(
        "lmdj.sequence.record.begin",
        {
            "project_path": str(project),
            "session_id": session_id,
            "pattern_id": PATTERN_ID,
            "expected_revision": 5,
            "runtime_frame": 0,
            "armed_capture_slot": None,
        },
    )
    check_success(begun, 5)
    observed = cli_request(
        cli,
        workspace,
        "query",
        {
            "operation": "sequence.record.status",
            "project_path": str(project),
        },
    )
    check_success(observed, None)
    assert observed["result"]["state"] == "active"
    assert observed["result"]["session_id"] == session_id
    recorded = mcp.tool(
        "lmdj.sequence.record.event",
        {
            "project_path": str(project),
            "session_id": session_id,
            "event": {
                "slot": slot(0, 0),
                "velocity": 100,
                "runtime_frame": 1,
                "input_sequence": 1,
                "pressed": True,
            },
        },
    )
    check_success(recorded, 5)
    mcp.close()

    restarted_status = cli_request(
        cli,
        workspace,
        "query",
        {
            "operation": "sequence.record.status",
            "project_path": str(project),
        },
    )
    check_success(restarted_status, None)
    assert restarted_status["result"]["state"] == "recoverable"
    assert restarted_status["result"]["session_id"] == session_id
    recovery = cli_request(
        cli,
        workspace,
        "query",
        {
            "operation": "sequence.recovery.list",
            "project_path": str(project),
        },
    )
    check_success(recovery, None)
    assert recovery["result"]["candidates"] == [
        {
            "session_id": session_id,
            "pattern_id": PATTERN_ID,
            "bars": 1,
            "reason": "owner_lost",
            "event_count": 1,
        }
    ]
    discarded = cli_request(
        cli,
        workspace,
        "command",
        {
            "operation": "sequence.recovery.discard",
            "project_path": str(project),
            "session_id": session_id,
        },
    )
    check_success(discarded, None)

    replay_session_id = uuid(904)
    flush_command_id = uuid(905)
    mcp = MCP(library, workspace)
    check_success(
        mcp.tool(
            "lmdj.sequence.record.begin",
            {
                "project_path": str(project),
                "session_id": replay_session_id,
                "pattern_id": PATTERN_ID,
                "expected_revision": 5,
                "runtime_frame": 0,
                "armed_capture_slot": None,
            },
        ),
        5,
    )
    for event in (
        {
            "slot": slot(0, 0),
            "velocity": 95,
            "runtime_frame": 0,
            "input_sequence": 1,
            "pressed": True,
        },
        {
            "slot": slot(0, 0),
            "velocity": 0,
            "runtime_frame": 12_000,
            "input_sequence": 2,
            "pressed": False,
        },
    ):
        check_success(
            mcp.tool(
                "lmdj.sequence.record.event",
                {
                    "project_path": str(project),
                    "session_id": replay_session_id,
                    "event": event,
                },
            ),
            5,
        )
    flushed = mcp.tool(
        "lmdj.sequence.record.flush",
        {
            "project_path": str(project),
            "session_id": replay_session_id,
            "command_id": flush_command_id,
            "runtime_frame": 12_000,
        },
    )
    check_success(flushed, 6)
    assert flushed["result"]["replayed"] is False
    check_success(
        mcp.tool(
            "lmdj.sequence.record.stop",
            {
                "project_path": str(project),
                "session_id": replay_session_id,
                "command_id": uuid(906),
                "runtime_frame": 12_001,
            },
        ),
        6,
    )
    mcp.close()
    before_replay = cli_request(
        cli,
        workspace,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )
    replayed = cli_request(
        cli,
        workspace,
        "command",
        {
            "operation": "sequence.record.flush",
            "project_path": str(project),
            "session_id": replay_session_id,
            "command_id": flush_command_id,
            "runtime_frame": 12_000,
        },
    )
    check_success(replayed, 6)
    assert replayed["result"]["replayed"] is True
    after_replay = cli_request(
        cli,
        workspace,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )
    assert after_replay == before_replay
    assert len(
        after_replay["result"]["project"]["patterns"][PATTERN_ID]["events"]
    ) == 4


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: mcp_facade_parity_test.py "
            "/absolute/path/to/lmdj-core "
            "/absolute/path/to/lmdj-core-c"
        )
    cli = Path(sys.argv[1]).expanduser().resolve(strict=True)
    library = Path(sys.argv[2]).expanduser().resolve(strict=True)
    assert cli.is_absolute() and library.is_absolute()
    with tempfile.TemporaryDirectory(prefix="lmdj-mcp-parity-") as temp:
        temp_root = Path(temp).resolve()
        workspace = temp_root / "workspace"
        workspace.mkdir()
        cli_author_mcp_consume(
            cli, library, workspace, temp_root
        )
        mcp_author_cli_consume(
            cli, library, workspace, temp_root
        )
        sample_facade_parity(cli, library, workspace, temp_root)
        provider_binding_parity(cli, library, temp_root)
        sequence_cross_host_observer(cli, library, temp_root)
    print("cli/mcp facade parity: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
