from __future__ import annotations

import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps/core-mcp"))

from lmdj_core_mcp import server  # noqa: E402
from performance_mcp_test import (  # noqa: E402
    expected_performance_output_schemas,
)


PROTOCOL_VERSION = "2025-11-25"
TIMEOUT_SECONDS = 15.0
PROJECT_ID = "00000000-0000-4000-8000-000000000001"
PATTERN_ID = "00000000-0000-4000-8000-000000000010"
PERFORMANCE_OUTPUT_SCHEMAS = expected_performance_output_schemas()
EXPECTED_PERFORMANCE_OPERATIONS = {
    name.removeprefix("lmdj.") for name in PERFORMANCE_OUTPUT_SCHEMAS
}
OBSERVED_SUCCESS_OPERATIONS: set[str] = set()


def uuid(suffix: int) -> str:
    return f"00000000-0000-4000-8000-{suffix:012d}"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def assert_locked_success(operation: str, envelope: dict) -> None:
    schema = PERFORMANCE_OUTPUT_SCHEMAS.get(f"lmdj.{operation}")
    if schema is None:
        return
    assert server.validates(schema, envelope), (operation, envelope, schema)
    OBSERVED_SUCCESS_OPERATIONS.add(operation)


def assert_recovery_candidate(
    result: dict,
    session_id: str,
    performance_id: str,
    reason: str,
    pending_event_count: int,
) -> None:
    assert set(result) == {"candidates"}, result
    assert len(result["candidates"]) == 1, result
    candidate = dict(result["candidates"][0])
    assert set(candidate) == {
        "session_id",
        "performance_id",
        "reason",
        "durable_event_count",
        "pending_event_count",
        "fingerprint",
    }, candidate
    fingerprint = candidate.pop("fingerprint")
    assert len(fingerprint) == 64
    assert all(character in "0123456789abcdef" for character in fingerprint)
    assert candidate == {
        "session_id": session_id,
        "performance_id": performance_id,
        "reason": reason,
        "durable_event_count": 0,
        "pending_event_count": pending_event_count,
    }, candidate


def host_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPO_ROOT / "apps/core-mcp")
    sanitizer_runtime = environment.get("LMDJ_ASAN_RUNTIME")
    if sanitizer_runtime:
        if sys.platform == "darwin":
            environment["DYLD_INSERT_LIBRARIES"] = sanitizer_runtime
        elif sys.platform.startswith("linux"):
            environment["LD_PRELOAD"] = sanitizer_runtime
    return environment


def cli_request_raw(
    cli: Path,
    workspace: Path,
    assembly: Path,
    surface: str,
    request: dict,
) -> tuple[dict, bytes]:
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
    assert completed.returncode in (0, 2), (
        request,
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )
    assert completed.stderr == b""
    decoded = completed.stdout.decode("utf-8", errors="strict")
    response = json.loads(decoded)
    assert decoded == canonical_json(response) + "\n"
    assert completed.returncode == (0 if response["ok"] else 2)
    return response, completed.stdout


def cli_ok(
    cli: Path,
    workspace: Path,
    assembly: Path,
    surface: str,
    request: dict,
    revision: int | None,
) -> dict:
    response, _ = cli_request_raw(cli, workspace, assembly, surface, request)
    assert response["ok"] is True, response
    assert set(response) == {"ok", "result", "project_revision"}
    assert response["project_revision"] == revision, response
    assert_locked_success(request["operation"], response)
    return response["result"]


class MCPProcess:
    def __init__(
        self,
        library: Path,
        workspace: Path,
        assembly: Path,
    ) -> None:
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
            env=host_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        initialized = self.request(
            1,
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "lmdj-stage10", "version": "1"},
            },
        )
        assert initialized["result"]["protocolVersion"] == PROTOCOL_VERSION
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assert_silent()
        self.next_identifier = 2

    def send(self, message: dict) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(
            canonical_json(message).encode("utf-8") + b"\n"
        )
        self.process.stdin.flush()

    def receive(self) -> dict:
        assert self.process.stdout is not None
        ready, _, _ = select.select(
            [self.process.stdout], [], [], TIMEOUT_SECONDS
        )
        assert ready, (self.process.poll(), self.stderr())
        line = self.process.stdout.readline()
        assert line, (self.process.poll(), self.stderr())
        decoded = line.decode("utf-8", errors="strict")
        response = json.loads(decoded)
        assert decoded == canonical_json(response) + "\n"
        return response

    def request(
        self,
        identifier: int,
        method: str,
        params: dict | None = None,
    ) -> dict:
        message: dict[str, object] = {
            "jsonrpc": "2.0",
            "id": identifier,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self.send(message)
        response = self.receive()
        assert response["id"] == identifier, response
        return response

    def tool(self, name: str, arguments: dict) -> dict:
        identifier = self.next_identifier
        self.next_identifier += 1
        response = self.request(
            identifier,
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        assert set(response) == {"jsonrpc", "id", "result"}, response
        result = response["result"]
        assert set(result) == {"content", "structuredContent", "isError"}
        envelope = result["structuredContent"]
        assert result["content"] == [
            {"type": "text", "text": canonical_json(envelope)}
        ]
        assert result["isError"] is (envelope["ok"] is False)
        return envelope

    def tool_ok(self, name: str, arguments: dict, revision: int | None) -> dict:
        response = self.tool(name, arguments)
        assert response["ok"] is True, response
        assert set(response) == {"ok", "result", "project_revision"}
        assert response["project_revision"] == revision, response
        assert_locked_success(name.removeprefix("lmdj."), response)
        return response["result"]

    def assert_silent(self, timeout: float = 0.1) -> None:
        assert self.process.stdout is not None
        ready, _, _ = select.select([self.process.stdout], [], [], timeout)
        assert not ready

    def stderr(self) -> bytes:
        if self.process.poll() is None or self.process.stderr is None:
            return b""
        return self.process.stderr.read()

    def close(self) -> None:
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        self.process.stdin = None
        assert self.process.wait(timeout=TIMEOUT_SECONDS) == 0
        assert self.process.stdout is not None
        assert self.process.stdout.read() == b""
        assert self.process.stderr is not None
        assert self.process.stderr.read() == b""

    def kill(self) -> None:
        self.process.send_signal(signal.SIGKILL)
        assert self.process.wait(timeout=TIMEOUT_SECONDS) == -signal.SIGKILL
        if self.process.stdin is not None:
            self.process.stdin.close()
        self.process.stdin = None


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
        ready = self.receive()
        assert ready["ok"] is True, ready

    def receive(self) -> dict:
        assert self.process.stdout is not None
        ready, _, _ = select.select(
            [self.process.stdout], [], [], TIMEOUT_SECONDS
        )
        assert ready, (self.process.poll(), self.stderr())
        line = self.process.stdout.readline()
        assert line, (self.process.poll(), self.stderr())
        decoded = line.decode("utf-8", errors="strict")
        response = json.loads(decoded)
        assert decoded == canonical_json(response) + "\n"
        return response

    def request(self, request: dict) -> dict:
        assert self.process.stdin is not None
        self.process.stdin.write(
            canonical_json(request).encode("utf-8") + b"\n"
        )
        self.process.stdin.flush()
        return self.receive()

    def ok(self, request: dict, revision: int | None) -> dict:
        response = self.request(request)
        assert response["ok"] is True, response
        assert set(response) == {"ok", "result", "project_revision"}
        assert response["project_revision"] == revision, response
        assert_locked_success(request["operation"], response)
        return response["result"]

    def stderr(self) -> bytes:
        if self.process.poll() is None or self.process.stderr is None:
            return b""
        return self.process.stderr.read()

    def close(self) -> None:
        response = self.request({"operation": "quit"})
        assert response["ok"] is True, response
        assert self.process.stdin is not None
        self.process.stdin.close()
        assert self.process.wait(timeout=TIMEOUT_SECONDS) == 0
        assert self.process.stderr is not None
        assert self.process.stderr.read() == b""


def create_project(
    cli: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
    suffix: int,
) -> None:
    cli_ok(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "project.create",
            "project_path": str(project),
            "project_id": uuid(suffix),
            "bpm": 240,
            "initial_pattern": {
                "pattern_id": PATTERN_ID,
                "bars": 1,
                "events": [],
            },
        },
        0,
    )


def inspect_bytes(
    cli: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
) -> tuple[dict, bytes]:
    response, encoded = cli_request_raw(
        cli,
        workspace,
        assembly,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )
    assert response["ok"] is True, response
    return response, encoded


def full_cross_host_journey(
    cli: Path,
    library: Path,
    native: Path,
    assembly: Path,
    workspace: Path,
) -> None:
    project = workspace / "full-cross-host.lmdj"
    create_project(cli, workspace, assembly, project, 1)
    imported = cli_ok(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "asset.import",
            "project_path": str(project),
            "command_id": uuid(2),
            "expected_revision": 0,
            "asset_id": uuid(3),
            "source_path": str(REPO_ROOT / "tests/fixtures/audio/stereo.wav"),
            "media_type": "audio/wav",
        },
        1,
    )
    artifact = imported["artifact"]
    assert set(artifact) == {"sha256", "media_type", "byte_length"}

    session_id = uuid(10)
    performance_id = uuid(11)
    mcp = MCPProcess(library, workspace, assembly)
    try:
        begun = mcp.tool_ok(
            "lmdj.performance.record.begin",
            {
                "project_path": str(project),
                "command_id": uuid(12),
                "expected_revision": 1,
                "session_id": session_id,
                "performance_id": performance_id,
            },
            2,
        )
        assert begun == {
            "performance_id": performance_id,
            "committed_revision": 2,
            "replayed": False,
        }
        listed = mcp.tool_ok(
            "lmdj.performance.list", {"project_path": str(project)}, 2
        )
        assert [item["performance_id"] for item in listed["performances"]] == [
            performance_id
        ]

        hold_on = mcp.tool_ok(
            "lmdj.performance.record.event",
            {
                "project_path": str(project),
                "session_id": session_id,
                "event_id": uuid(13),
                "event": {"kind": "hold_on"},
            },
            None,
        )
        assert set(hold_on) == {
            "event_id",
            "accepted_tick",
            "input_sequence",
            "coalesced",
            "replayed",
        }
        assert hold_on["input_sequence"] == 1
        assert hold_on["replayed"] is False
        hold_off = mcp.tool_ok(
            "lmdj.performance.record.event",
            {
                "project_path": str(project),
                "session_id": session_id,
                "event_id": uuid(14),
                "event": {"kind": "hold_off"},
            },
            None,
        )
        assert hold_off["input_sequence"] == 2

        launch_arguments = {
            "project_path": str(project),
            "session_id": session_id,
            "request_id": uuid(15),
            "pattern_slot": 7,
        }
        launch = mcp.tool_ok(
            "lmdj.performance.record.launch-request",
            launch_arguments,
            None,
        )
        assert set(launch) == {"request_id", "state", "target_tick"}
        assert launch["state"] == "pending"
        pending = mcp.tool_ok(
            "lmdj.performance.record.status",
            {"project_path": str(project)},
            None,
        )
        assert pending["pending_launch"]["request_id"] == uuid(15)
        assert pending["last_launch_ack"] is None

        deadline = time.monotonic() + 3.0
        acknowledged = pending
        while time.monotonic() < deadline:
            time.sleep(0.05)
            repeated_launch = mcp.tool_ok(
                "lmdj.performance.record.launch-request",
                launch_arguments,
                None,
            )
            assert repeated_launch == launch
            acknowledged = mcp.tool_ok(
                "lmdj.performance.record.status",
                {"project_path": str(project)},
                None,
            )
            if acknowledged["last_launch_ack"] is not None:
                break
        assert acknowledged["pending_launch"] is None, acknowledged
        assert acknowledged["last_launch_ack"] == {
            "request_id": uuid(15),
            "pattern_slot": 7,
            "effective_tick": launch["target_tick"],
        }

        flush_id = uuid(16)
        flushed = mcp.tool_ok(
            "lmdj.performance.record.flush",
            {
                "project_path": str(project),
                "session_id": session_id,
                "command_id": flush_id,
            },
            3,
        )
        assert flushed == {
            "performance_id": performance_id,
            "committed_revision": 3,
            "replayed": False,
        }
        before_replay, before_replay_bytes = inspect_bytes(
            cli, workspace, assembly, project
        )
        replayed = cli_ok(
            cli,
            workspace,
            assembly,
            "command",
            {
                "operation": "performance.record.flush",
                "project_path": str(project),
                "session_id": session_id,
                "command_id": flush_id,
            },
            3,
        )
        assert replayed == {
            "performance_id": performance_id,
            "committed_revision": 3,
            "replayed": True,
        }
        after_replay, after_replay_bytes = inspect_bytes(
            cli, workspace, assembly, project
        )
        assert after_replay_bytes == before_replay_bytes
        assert after_replay["project_revision"] == before_replay["project_revision"] == 3

        stopped = mcp.tool_ok(
            "lmdj.performance.record.stop",
            {
                "project_path": str(project),
                "session_id": session_id,
                "request_id": uuid(17),
            },
            None,
        )
        assert stopped["state"] == "stopped"
        status = mcp.tool_ok(
            "lmdj.performance.record.status",
            {"project_path": str(project)},
            None,
        )
        assert status["state"] == "stopped"
        saved = mcp.tool_ok(
            "lmdj.performance.save",
            {
                "project_path": str(project),
                "command_id": uuid(18),
                "expected_revision": 3,
                "performance_id": performance_id,
                "name": "Cross Host Take",
                "recording_artifact": None,
            },
            4,
        )
        assert saved["committed_revision"] == 4
        inspected = mcp.tool_ok(
            "lmdj.performance.inspect",
            {"project_path": str(project), "performance_id": performance_id},
            4,
        )["performance"]
        assert inspected["name"] == "Cross Host Take"
        assert inspected["recording_artifact"] is None
        assert [event["kind"] for event in inspected["events"]] == [
            "hold_on",
            "hold_off",
            "pattern_launch",
        ]
    finally:
        mcp.close()

    native_process = NativeProcess(native, workspace, assembly, project)
    try:
        replay_id = uuid(19)
        replay = native_process.ok(
            {
                "operation": "performance.replay.begin",
                "project_path": str(project),
                "replay_id": replay_id,
                "performance_id": performance_id,
            },
            None,
        )
        assert replay["replay_id"] == replay_id
        assert replay["resolved_revision"] == 4
        status_request = {
            "operation": "performance.replay.status",
            "project_path": str(project),
            "replay_id": replay_id,
        }
        deadline = time.monotonic() + 3.0
        observed = native_process.ok(status_request, None)
        while observed["event_cursor"] == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
            observed = native_process.ok(status_request, None)
        assert 0 < observed["event_cursor"] <= observed["event_count"] == 3, observed

        stop_request = {
            "operation": "performance.replay.stop",
            "project_path": str(project),
            "replay_id": replay_id,
            "request_id": uuid(20),
        }
        deadline = time.monotonic() + 3.0
        terminal = native_process.ok(stop_request, None)
        while terminal["state"] == "playing" and time.monotonic() < deadline:
            time.sleep(0.01)
            terminal = native_process.ok(stop_request, None)
        assert terminal["state"] in ("stopped", "complete"), terminal
        assert terminal["request_id"] == uuid(20)

        bound = native_process.ok(
            {
                "operation": "performance.recording.bind",
                "project_path": str(project),
                "command_id": uuid(21),
                "expected_revision": 4,
                "performance_id": performance_id,
                "recording_artifact": artifact,
            },
            5,
        )
        assert bound["committed_revision"] == 5
        after_bind = native_process.ok(
            {
                "operation": "performance.inspect",
                "project_path": str(project),
                "performance_id": performance_id,
            },
            5,
        )["performance"]
        assert after_bind["recording_artifact"] == artifact

        resampled = native_process.ok(
            {
                "operation": "performance.resample.commit",
                "project_path": str(project),
                "command_id": uuid(22),
                "expected_revision": 5,
                "performance_id": performance_id,
                "source_start_frame": 1,
                "source_end_frame": 3,
                "target_slot": {"bank": 1, "pad": 2},
            },
            6,
        )
        assert resampled == {
            "performance_id": performance_id,
            "committed_revision": 6,
            "runtime_prepare_required": True,
        }
    finally:
        native_process.close()

    project_result, _ = inspect_bytes(cli, workspace, assembly, project)
    truth = project_result["result"]["project"]
    assert truth["banks"][1]["pads"][2]["asset_id"] == uuid(22)
    lineage = truth["assets"][uuid(22)]["lineage"]
    assert lineage["source"] == {
        "kind": "asset_artifact",
        "artifact_sha256": artifact["sha256"],
        "project_revision": 1,
    }, lineage["source"]
    assert lineage["derivation"] == {
        "kind": "resample",
        "performance_id": performance_id,
        "range": {"start_frame": 1, "end_frame": 3},
    }, lineage["derivation"]
    resampled_artifact = truth["assets"][uuid(22)]["artifact"]
    assert len(resampled_artifact["sha256"]) == 64
    assert resampled_artifact["byte_length"] == 52
    assert resampled_artifact["media_type"] == "audio/wav"


def owner_loss_apply_journey(
    cli: Path,
    library: Path,
    assembly: Path,
    workspace: Path,
) -> None:
    project = workspace / "owner-loss-apply.lmdj"
    create_project(cli, workspace, assembly, project, 101)
    session_id = uuid(110)
    performance_id = uuid(111)
    mcp = MCPProcess(library, workspace, assembly)
    mcp.tool_ok(
        "lmdj.performance.record.begin",
        {
            "project_path": str(project),
            "command_id": uuid(112),
            "expected_revision": 0,
            "session_id": session_id,
            "performance_id": performance_id,
        },
        1,
    )
    mcp.tool_ok(
        "lmdj.performance.record.event",
        {
            "project_path": str(project),
            "session_id": session_id,
            "event_id": uuid(113),
            "event": {"kind": "hold_on"},
        },
        None,
    )
    active_status = cli_ok(
        cli,
        workspace,
        assembly,
        "query",
        {"operation": "performance.record.status", "project_path": str(project)},
        None,
    )
    assert active_status["state"] == "active"
    _, before_live_apply = inspect_bytes(cli, workspace, assembly, project)
    live_apply, _ = cli_request_raw(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "performance.recovery.apply",
            "project_path": str(project),
            "command_id": uuid(114),
            "expected_revision": 1,
            "session_id": session_id,
        },
    )
    assert live_apply["ok"] is False, live_apply
    assert live_apply["error"]["details"]["reason"] == "recording_session_active"
    _, after_live_apply = inspect_bytes(cli, workspace, assembly, project)
    assert after_live_apply == before_live_apply

    mcp.kill()
    active_journal = project / "recovery/active/performance.jsonl"
    before_list = active_journal.read_bytes()
    listed = cli_ok(
        cli,
        workspace,
        assembly,
        "query",
        {"operation": "performance.recovery.list", "project_path": str(project)},
        None,
    )
    assert_recovery_candidate(listed, session_id, performance_id, "active", 2)
    assert active_journal.read_bytes() == before_list
    applied = cli_ok(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "performance.recovery.apply",
            "project_path": str(project),
            "command_id": uuid(115),
            "expected_revision": 1,
            "session_id": session_id,
        },
        2,
    )
    assert applied == {
        "performance_id": performance_id,
        "committed_revision": 2,
        "replayed": False,
    }
    inspected = cli_ok(
        cli,
        workspace,
        assembly,
        "query",
        {
            "operation": "performance.inspect",
            "project_path": str(project),
            "performance_id": performance_id,
        },
        2,
    )["performance"]
    event_kinds = [event["kind"] for event in inspected["events"]]
    assert event_kinds == [
        "hold_on",
        "hold_off",
    ], inspected["events"]
    assert active_journal.exists()
    assert not (project / "recovery/active/performance.lock").exists()
    remaining_recovery = cli_ok(
        cli,
        workspace,
        assembly,
        "query",
        {"operation": "performance.recovery.list", "project_path": str(project)},
        None,
    )
    assert_recovery_candidate(
        remaining_recovery, session_id, performance_id, "stopped", 0
    )
    stopped_journal = active_journal.read_bytes()
    replayed = cli_ok(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "performance.recovery.apply",
            "project_path": str(project),
            "command_id": uuid(115),
            "expected_revision": 1,
            "session_id": session_id,
        },
        2,
    )
    assert replayed == applied | {"replayed": True}
    assert active_journal.read_bytes() == stopped_journal


def owner_loss_discard_journey(
    cli: Path,
    library: Path,
    assembly: Path,
    workspace: Path,
) -> None:
    project = workspace / "owner-loss-discard.lmdj"
    create_project(cli, workspace, assembly, project, 201)
    session_id = uuid(210)
    performance_id = uuid(211)
    mcp = MCPProcess(library, workspace, assembly)
    mcp.tool_ok(
        "lmdj.performance.record.begin",
        {
            "project_path": str(project),
            "command_id": uuid(212),
            "expected_revision": 0,
            "session_id": session_id,
            "performance_id": performance_id,
        },
        1,
    )
    mcp.tool_ok(
        "lmdj.performance.record.event",
        {
            "project_path": str(project),
            "session_id": session_id,
            "event_id": uuid(213),
            "event": {"kind": "hold_on"},
        },
        None,
    )
    mcp.kill()
    before, before_bytes = inspect_bytes(cli, workspace, assembly, project)
    active_journal = project / "recovery/active/performance.jsonl"
    before_list = active_journal.read_bytes()
    listed = cli_ok(
        cli,
        workspace,
        assembly,
        "query",
        {"operation": "performance.recovery.list", "project_path": str(project)},
        None,
    )
    assert_recovery_candidate(listed, session_id, performance_id, "active", 2)
    assert active_journal.read_bytes() == before_list
    discarded = cli_ok(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "performance.recovery.discard",
            "project_path": str(project),
            "session_id": session_id,
            "request_id": uuid(214),
        },
        None,
    )
    assert discarded == {
        "request_id": uuid(214),
        "session_id": session_id,
        "performance_id": performance_id,
        "state": "stopped",
        "pending_event_count": 0,
        "replayed": False,
    }
    after, after_bytes = inspect_bytes(cli, workspace, assembly, project)
    assert after_bytes == before_bytes
    assert after["project_revision"] == before["project_revision"] == 1
    inspected = cli_ok(
        cli,
        workspace,
        assembly,
        "query",
        {
            "operation": "performance.inspect",
            "project_path": str(project),
            "performance_id": performance_id,
        },
        1,
    )["performance"]
    assert inspected["events"] == []
    assert active_journal.exists()
    assert not (project / "recovery/active/performance.lock").exists()
    remaining_recovery = cli_ok(
        cli,
        workspace,
        assembly,
        "query",
        {"operation": "performance.recovery.list", "project_path": str(project)},
        None,
    )
    assert_recovery_candidate(
        remaining_recovery, session_id, performance_id, "stopped", 0
    )
    stopped = cli_ok(
        cli,
        workspace,
        assembly,
        "query",
        {"operation": "performance.record.status", "project_path": str(project)},
        None,
    )
    assert stopped["state"] == "stopped", stopped
    stopped_journal = active_journal.read_bytes()
    replayed = cli_ok(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "performance.recovery.discard",
            "project_path": str(project),
            "session_id": session_id,
            "request_id": uuid(214),
        },
        None,
    )
    assert replayed == discarded | {"replayed": True}
    assert active_journal.read_bytes() == stopped_journal


def remaining_locked_surface_journey(
    cli: Path,
    library: Path,
    assembly: Path,
    workspace: Path,
) -> None:
    pattern_project = workspace / "locked-pattern-slots.lmdj"
    create_project(cli, workspace, assembly, pattern_project, 301)
    assigned = cli_ok(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "pattern.slot.assign",
            "project_path": str(pattern_project),
            "command_id": uuid(302),
            "expected_revision": 0,
            "pattern_slot": 0,
            "pattern_id": PATTERN_ID,
        },
        1,
    )
    assert assigned == {
        "pattern_slot": 0,
        "pattern_id": PATTERN_ID,
        "committed_revision": 1,
        "replayed": False,
    }
    moved = cli_ok(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "pattern.slot.move",
            "project_path": str(pattern_project),
            "command_id": uuid(303),
            "expected_revision": 1,
            "from_slot": 0,
            "to_slot": 1,
        },
        2,
    )
    assert moved == {
        "from_slot": 0,
        "to_slot": 1,
        "pattern_id": PATTERN_ID,
        "committed_revision": 2,
        "replayed": False,
    }
    cleared = cli_ok(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "pattern.slot.clear",
            "project_path": str(pattern_project),
            "command_id": uuid(304),
            "expected_revision": 2,
            "pattern_slot": 1,
        },
        3,
    )
    assert cleared == {
        "pattern_slot": 1,
        "pattern_id": None,
        "committed_revision": 3,
        "replayed": False,
    }

    lifecycle_project = workspace / "locked-performance-lifecycle.lmdj"
    create_project(cli, workspace, assembly, lifecycle_project, 310)
    mcp = MCPProcess(library, workspace, assembly)
    try:
        first_session = uuid(311)
        first_performance = uuid(312)
        begun = mcp.tool_ok(
            "lmdj.performance.record.begin",
            {
                "project_path": str(lifecycle_project),
                "command_id": uuid(313),
                "expected_revision": 0,
                "session_id": first_session,
                "performance_id": first_performance,
            },
            1,
        )
        assert begun["performance_id"] == first_performance
        mcp.tool_ok(
            "lmdj.performance.record.stop",
            {
                "project_path": str(lifecycle_project),
                "session_id": first_session,
                "request_id": uuid(314),
            },
            None,
        )
        saved = mcp.tool_ok(
            "lmdj.performance.save",
            {
                "project_path": str(lifecycle_project),
                "command_id": uuid(315),
                "expected_revision": 1,
                "performance_id": first_performance,
                "name": "Lifecycle Take",
                "recording_artifact": None,
            },
            2,
        )
        assert saved["committed_revision"] == 2
        renamed = mcp.tool_ok(
            "lmdj.performance.rename",
            {
                "project_path": str(lifecycle_project),
                "command_id": uuid(316),
                "expected_revision": 2,
                "performance_id": first_performance,
                "name": "Renamed Take",
            },
            3,
        )
        assert renamed["committed_revision"] == 3
        deleted = mcp.tool_ok(
            "lmdj.performance.delete",
            {
                "project_path": str(lifecycle_project),
                "command_id": uuid(317),
                "expected_revision": 3,
                "performance_id": first_performance,
            },
            4,
        )
        assert deleted["committed_revision"] == 4

        second_session = uuid(318)
        second_performance = uuid(319)
        mcp.tool_ok(
            "lmdj.performance.record.begin",
            {
                "project_path": str(lifecycle_project),
                "command_id": uuid(320),
                "expected_revision": 4,
                "session_id": second_session,
                "performance_id": second_performance,
            },
            5,
        )
        mcp.tool_ok(
            "lmdj.performance.record.stop",
            {
                "project_path": str(lifecycle_project),
                "session_id": second_session,
                "request_id": uuid(321),
            },
            None,
        )
        discarded = mcp.tool_ok(
            "lmdj.performance.discard",
            {
                "project_path": str(lifecycle_project),
                "command_id": uuid(322),
                "expected_revision": 5,
                "performance_id": second_performance,
            },
            6,
        )
        assert discarded["committed_revision"] == 6
    finally:
        mcp.close()


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: cross_host_performance_idempotency_test.py "
            "CLI C_API_LIBRARY NATIVE_HOST ASSEMBLY_JSON"
        )
    cli = Path(sys.argv[1]).resolve(strict=True)
    library = Path(sys.argv[2]).resolve(strict=True)
    native = Path(sys.argv[3]).resolve(strict=True)
    assembly = Path(sys.argv[4]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="lmdj-stage10-cross-host-") as root:
        workspace = Path(root).resolve()
        full_cross_host_journey(
            cli, library, native, assembly, workspace
        )
        owner_loss_apply_journey(cli, library, assembly, workspace)
        owner_loss_discard_journey(cli, library, assembly, workspace)
        remaining_locked_surface_journey(cli, library, assembly, workspace)
        assert OBSERVED_SUCCESS_OPERATIONS == EXPECTED_PERFORMANCE_OPERATIONS, (
            EXPECTED_PERFORMANCE_OPERATIONS - OBSERVED_SUCCESS_OPERATIONS,
            OBSERVED_SUCCESS_OPERATIONS - EXPECTED_PERFORMANCE_OPERATIONS,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
