from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps/core-mcp"))

from lmdj_core_mcp import server  # noqa: E402


UUID_PATTERN = (
    "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    "[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def object_schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def expected_performance_tools() -> dict[str, tuple[str, str, dict]]:
    path = {"type": "string", "minLength": 1}
    uuid = {"type": "string", "pattern": UUID_PATTERN}
    uint = {"type": "integer", "minimum": 0}
    pattern_slot = {"type": "integer", "minimum": 0, "maximum": 15}
    pad_slot = object_schema(
        {
            "bank": {"type": "integer", "minimum": 0, "maximum": 3},
            "pad": {"type": "integer", "minimum": 0, "maximum": 15},
        },
        ["bank", "pad"],
    )
    artifact = object_schema(
        {
            "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "media_type": {"const": "audio/wav"},
            "byte_length": uint,
        },
        ["sha256", "media_type", "byte_length"],
    )
    nullable_artifact = {"oneOf": [artifact, {"type": "null"}]}
    fx = {
        "type": "string",
        "enum": [
            "filter",
            "delay",
            "reverb",
            "stutter",
            "gate",
            "reverse",
            "crush",
            "cutter",
        ],
    }
    gesture = {
        "oneOf": [
            object_schema(
                {
                    "kind": {"const": "pad_press"},
                    "gesture_id": uuid,
                    "slot": {"type": "integer", "minimum": 0, "maximum": 63},
                    "velocity": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 127,
                    },
                },
                ["kind", "gesture_id", "slot", "velocity"],
            ),
            object_schema(
                {
                    "kind": {"const": "pad_release"},
                    "gesture_id": uuid,
                    "slot": {"type": "integer", "minimum": 0, "maximum": 63},
                },
                ["kind", "gesture_id", "slot"],
            ),
            object_schema(
                {
                    "kind": {"const": "fx_engage"},
                    "gesture_id": uuid,
                    "fx": fx,
                    "value": {"type": "integer", "minimum": 0, "maximum": 1000},
                },
                ["kind", "gesture_id", "fx", "value"],
            ),
            object_schema(
                {
                    "kind": {"const": "fx_move"},
                    "gesture_id": uuid,
                    "fx": fx,
                    "value": {"type": "integer", "minimum": 0, "maximum": 1000},
                },
                ["kind", "gesture_id", "fx", "value"],
            ),
            object_schema(
                {
                    "kind": {"const": "fx_release"},
                    "gesture_id": uuid,
                    "fx": fx,
                },
                ["kind", "gesture_id", "fx"],
            ),
            object_schema({"kind": {"const": "hold_on"}}, ["kind"]),
            object_schema({"kind": {"const": "hold_off"}}, ["kind"]),
        ]
    }

    def request(properties: dict, required: list[str]) -> dict:
        return object_schema(properties, required)

    entries: tuple[tuple[str, str, str, dict], ...] = (
        (
            "lmdj.pattern.slot.assign",
            "pattern.slot.assign",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "pattern_slot": pattern_slot,
                    "pattern_id": uuid,
                },
                [
                    "project_path",
                    "command_id",
                    "expected_revision",
                    "pattern_slot",
                    "pattern_id",
                ],
            ),
        ),
        (
            "lmdj.pattern.slot.clear",
            "pattern.slot.clear",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "pattern_slot": pattern_slot,
                },
                ["project_path", "command_id", "expected_revision", "pattern_slot"],
            ),
        ),
        (
            "lmdj.pattern.slot.move",
            "pattern.slot.move",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "from_slot": pattern_slot,
                    "to_slot": pattern_slot,
                },
                [
                    "project_path",
                    "command_id",
                    "expected_revision",
                    "from_slot",
                    "to_slot",
                ],
            ),
        ),
        (
            "lmdj.performance.list",
            "performance.list",
            "query",
            request({"project_path": path}, ["project_path"]),
        ),
        (
            "lmdj.performance.inspect",
            "performance.inspect",
            "query",
            request(
                {"project_path": path, "performance_id": uuid},
                ["project_path", "performance_id"],
            ),
        ),
        (
            "lmdj.performance.record.begin",
            "performance.record.begin",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "session_id": uuid,
                    "performance_id": uuid,
                },
                [
                    "project_path",
                    "command_id",
                    "expected_revision",
                    "session_id",
                    "performance_id",
                ],
            ),
        ),
        (
            "lmdj.performance.record.event",
            "performance.record.event",
            "command",
            request(
                {
                    "project_path": path,
                    "session_id": uuid,
                    "event_id": uuid,
                    "event": gesture,
                },
                ["project_path", "session_id", "event_id", "event"],
            ),
        ),
        (
            "lmdj.performance.record.launch-request",
            "performance.record.launch-request",
            "command",
            request(
                {
                    "project_path": path,
                    "session_id": uuid,
                    "request_id": uuid,
                    "pattern_slot": pattern_slot,
                },
                ["project_path", "session_id", "request_id", "pattern_slot"],
            ),
        ),
        (
            "lmdj.performance.record.flush",
            "performance.record.flush",
            "command",
            request(
                {"project_path": path, "session_id": uuid, "command_id": uuid},
                ["project_path", "session_id", "command_id"],
            ),
        ),
        (
            "lmdj.performance.record.stop",
            "performance.record.stop",
            "command",
            request(
                {"project_path": path, "session_id": uuid, "request_id": uuid},
                ["project_path", "session_id", "request_id"],
            ),
        ),
        (
            "lmdj.performance.record.status",
            "performance.record.status",
            "query",
            request({"project_path": path}, ["project_path"]),
        ),
        (
            "lmdj.performance.save",
            "performance.save",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "performance_id": uuid,
                    "name": {"type": "string", "minLength": 1, "maxLength": 64},
                    "recording_artifact": nullable_artifact,
                },
                [
                    "project_path",
                    "command_id",
                    "expected_revision",
                    "performance_id",
                    "name",
                    "recording_artifact",
                ],
            ),
        ),
        (
            "lmdj.performance.discard",
            "performance.discard",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "performance_id": uuid,
                },
                ["project_path", "command_id", "expected_revision", "performance_id"],
            ),
        ),
        (
            "lmdj.performance.recovery.list",
            "performance.recovery.list",
            "query",
            request({"project_path": path}, ["project_path"]),
        ),
        (
            "lmdj.performance.recovery.apply",
            "performance.recovery.apply",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "session_id": uuid,
                },
                ["project_path", "command_id", "expected_revision", "session_id"],
            ),
        ),
        (
            "lmdj.performance.recovery.discard",
            "performance.recovery.discard",
            "command",
            request(
                {"project_path": path, "session_id": uuid, "request_id": uuid},
                ["project_path", "session_id", "request_id"],
            ),
        ),
        (
            "lmdj.performance.rename",
            "performance.rename",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "performance_id": uuid,
                    "name": {"type": "string", "minLength": 1, "maxLength": 64},
                },
                [
                    "project_path",
                    "command_id",
                    "expected_revision",
                    "performance_id",
                    "name",
                ],
            ),
        ),
        (
            "lmdj.performance.delete",
            "performance.delete",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "performance_id": uuid,
                },
                ["project_path", "command_id", "expected_revision", "performance_id"],
            ),
        ),
        (
            "lmdj.performance.recording.bind",
            "performance.recording.bind",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "performance_id": uuid,
                    "recording_artifact": artifact,
                },
                [
                    "project_path",
                    "command_id",
                    "expected_revision",
                    "performance_id",
                    "recording_artifact",
                ],
            ),
        ),
        (
            "lmdj.performance.replay.begin",
            "performance.replay.begin",
            "command",
            request(
                {"project_path": path, "replay_id": uuid, "performance_id": uuid},
                ["project_path", "replay_id", "performance_id"],
            ),
        ),
        (
            "lmdj.performance.replay.stop",
            "performance.replay.stop",
            "command",
            request(
                {"project_path": path, "replay_id": uuid, "request_id": uuid},
                ["project_path", "replay_id", "request_id"],
            ),
        ),
        (
            "lmdj.performance.replay.status",
            "performance.replay.status",
            "query",
            request(
                {"project_path": path, "replay_id": uuid},
                ["project_path", "replay_id"],
            ),
        ),
        (
            "lmdj.performance.resample.commit",
            "performance.resample.commit",
            "command",
            request(
                {
                    "project_path": path,
                    "command_id": uuid,
                    "expected_revision": uint,
                    "performance_id": uuid,
                    "source_start_frame": uint,
                    "source_end_frame": uint,
                    "target_slot": pad_slot,
                },
                [
                    "project_path",
                    "command_id",
                    "expected_revision",
                    "performance_id",
                    "source_start_frame",
                    "source_end_frame",
                    "target_slot",
                ],
            ),
        ),
    )
    assert len(entries) == 23
    return {
        name: (operation, surface, schema)
        for name, operation, surface, schema in entries
    }


def facade_output_schema(result: dict, project_revision: dict) -> dict:
    success = object_schema(
        {
            "ok": {"const": True},
            "result": result,
            "project_revision": project_revision,
        },
        ["ok", "result", "project_revision"],
    )
    error = object_schema(
        {
            "ok": {"const": False},
            "error": object_schema(
                {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "details": {"type": "object"},
                },
                ["code", "message", "details"],
            ),
        },
        ["ok", "error"],
    )
    return {"type": "object", "oneOf": [success, error]}


def expected_performance_output_schemas() -> dict[str, dict]:
    uuid = {"type": "string", "pattern": UUID_PATTERN}
    uint = {"type": "integer", "minimum": 0}
    null = {"type": "null"}
    boolean = {"type": "boolean"}
    pattern_slot = {"type": "integer", "minimum": 0, "maximum": 15}
    nullable_uuid = {"oneOf": [uuid, null]}
    recording_artifact = object_schema(
        {
            "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "media_type": {"const": "audio/wav"},
            "byte_length": uint,
        },
        ["sha256", "media_type", "byte_length"],
    )
    nullable_recording_artifact = {
        "oneOf": [recording_artifact, null],
    }
    canonical_event = {
        "oneOf": [
            object_schema(
                {
                    "kind": {"const": "pad_hit"},
                    "slot": {"type": "integer", "minimum": 0, "maximum": 63},
                    "onset_tick": uint,
                    "duration_tick": {"type": "integer", "minimum": 1},
                    "velocity": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 127,
                    },
                },
                ["kind", "slot", "onset_tick", "duration_tick", "velocity"],
            ),
            object_schema(
                {
                    "kind": {"const": "pattern_launch"},
                    "pattern_slot": pattern_slot,
                    "effective_tick": uint,
                },
                ["kind", "pattern_slot", "effective_tick"],
            ),
            object_schema(
                {
                    "kind": {"const": "fx_engage"},
                    "fx": {"type": "integer", "minimum": 0, "maximum": 7},
                    "value": {"type": "integer", "minimum": 0, "maximum": 1000},
                    "tick": uint,
                },
                ["kind", "fx", "value", "tick"],
            ),
            object_schema(
                {
                    "kind": {"const": "fx_move"},
                    "fx": {"type": "integer", "minimum": 0, "maximum": 7},
                    "value": {"type": "integer", "minimum": 0, "maximum": 1000},
                    "tick": uint,
                },
                ["kind", "fx", "value", "tick"],
            ),
            object_schema(
                {
                    "kind": {"const": "fx_release"},
                    "fx": {"type": "integer", "minimum": 0, "maximum": 7},
                    "tick": uint,
                },
                ["kind", "fx", "tick"],
            ),
            object_schema(
                {"kind": {"const": "hold_on"}, "tick": uint},
                ["kind", "tick"],
            ),
            object_schema(
                {"kind": {"const": "hold_off"}, "tick": uint},
                ["kind", "tick"],
            ),
        ]
    }
    lifecycle = object_schema(
        {
            "performance_id": uuid,
            "committed_revision": uint,
            "replayed": boolean,
        },
        ["performance_id", "committed_revision", "replayed"],
    )
    pattern_assignment = object_schema(
        {
            "pattern_slot": pattern_slot,
            "pattern_id": nullable_uuid,
            "committed_revision": uint,
            "replayed": boolean,
        },
        ["pattern_slot", "pattern_id", "committed_revision", "replayed"],
    )
    pattern_move = object_schema(
        {
            "from_slot": pattern_slot,
            "to_slot": pattern_slot,
            "pattern_id": uuid,
            "committed_revision": uint,
            "replayed": boolean,
        },
        ["from_slot", "to_slot", "pattern_id", "committed_revision", "replayed"],
    )
    record_event = object_schema(
        {
            "event_id": uuid,
            "accepted_tick": uint,
            "input_sequence": uint,
            "coalesced": boolean,
            "replayed": boolean,
        },
        ["event_id", "accepted_tick", "input_sequence", "coalesced", "replayed"],
    )
    launch_request = object_schema(
        {
            "request_id": uuid,
            "state": {"const": "pending"},
            "target_tick": uint,
        },
        ["request_id", "state", "target_tick"],
    )
    stop = object_schema(
        {
            "request_id": uuid,
            "session_id": uuid,
            "performance_id": uuid,
            "state": {"const": "stopped"},
            "pending_event_count": uint,
            "replayed": boolean,
        },
        [
            "request_id",
            "session_id",
            "performance_id",
            "state",
            "pending_event_count",
            "replayed",
        ],
    )
    pending_launch = object_schema(
        {
            "request_id": uuid,
            "pattern_slot": pattern_slot,
            "target_tick": uint,
            "claimed": boolean,
        },
        ["request_id", "pattern_slot", "target_tick", "claimed"],
    )
    launch_ack = object_schema(
        {
            "request_id": uuid,
            "pattern_slot": pattern_slot,
            "effective_tick": uint,
        },
        ["request_id", "pattern_slot", "effective_tick"],
    )
    record_status = object_schema(
        {
            "state": {
                "type": "string",
                "enum": ["idle", "active", "stopped", "recovery_required"],
            },
            "session_id": nullable_uuid,
            "performance_id": nullable_uuid,
            "journal_revision": uint,
            "next_flush_seq": uint,
            "pending_event_count": uint,
            "open_pad_gestures": uint,
            "open_fx_gestures": uint,
            "hold": boolean,
            "pending_launch": {"oneOf": [pending_launch, null]},
            "last_launch_ack": {"oneOf": [launch_ack, null]},
        },
        [
            "state",
            "session_id",
            "performance_id",
            "journal_revision",
            "next_flush_seq",
            "pending_event_count",
            "open_pad_gestures",
            "open_fx_gestures",
            "hold",
            "pending_launch",
            "last_launch_ack",
        ],
    )
    recovery_candidate = object_schema(
        {
            "session_id": uuid,
            "performance_id": uuid,
            "reason": {"type": "string"},
            "durable_event_count": uint,
            "pending_event_count": uint,
            "fingerprint": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
        },
        [
            "session_id",
            "performance_id",
            "reason",
            "durable_event_count",
            "pending_event_count",
            "fingerprint",
        ],
    )
    recovery_list = object_schema(
        {"candidates": {"type": "array", "items": recovery_candidate}},
        ["candidates"],
    )
    replay_status = object_schema(
        {
            "replay_id": uuid,
            "state": {
                "type": "string",
                "enum": ["playing", "stopped", "complete"],
            },
            "resolved_revision": uint,
            "event_cursor": uint,
            "event_count": uint,
        },
        ["replay_id", "state", "resolved_revision", "event_cursor", "event_count"],
    )
    replay_stop = object_schema(
        replay_status["properties"]
        | {"request_id": uuid, "replayed": boolean},
        replay_status["required"] + ["request_id", "replayed"],
    )
    performance_summary = object_schema(
        {
            "performance_id": uuid,
            "name": {"type": "string", "minLength": 1, "maxLength": 64},
            "created_bpm": {"type": "integer", "minimum": 40, "maximum": 240},
            "recording_artifact": nullable_recording_artifact,
            "event_count": uint,
        },
        [
            "performance_id",
            "name",
            "created_bpm",
            "recording_artifact",
            "event_count",
        ],
    )
    performance_list = object_schema(
        {"performances": {"type": "array", "items": performance_summary}},
        ["performances"],
    )
    performance = object_schema(
        {
            "id": uuid,
            "name": {"type": "string", "minLength": 1, "maxLength": 64},
            "created_bpm": {"type": "integer", "minimum": 40, "maximum": 240},
            "recording_artifact": nullable_recording_artifact,
            "events": {"type": "array", "items": canonical_event},
        },
        ["id", "name", "created_bpm", "recording_artifact", "events"],
    )
    performance_inspect = object_schema(
        {"performance": performance}, ["performance"]
    )
    resample = object_schema(
        {
            "performance_id": uuid,
            "committed_revision": uint,
            "runtime_prepare_required": {"const": True},
        },
        ["performance_id", "committed_revision", "runtime_prepare_required"],
    )
    by_name: dict[str, tuple[dict, bool]] = {
        "lmdj.pattern.slot.assign": (pattern_assignment, True),
        "lmdj.pattern.slot.clear": (pattern_assignment, True),
        "lmdj.pattern.slot.move": (pattern_move, True),
        "lmdj.performance.list": (performance_list, True),
        "lmdj.performance.inspect": (performance_inspect, True),
        "lmdj.performance.record.begin": (lifecycle, True),
        "lmdj.performance.record.event": (record_event, False),
        "lmdj.performance.record.launch-request": (launch_request, False),
        "lmdj.performance.record.flush": (lifecycle, True),
        "lmdj.performance.record.stop": (stop, False),
        "lmdj.performance.record.status": (record_status, False),
        "lmdj.performance.save": (lifecycle, True),
        "lmdj.performance.discard": (lifecycle, True),
        "lmdj.performance.recovery.list": (recovery_list, False),
        "lmdj.performance.recovery.apply": (lifecycle, True),
        "lmdj.performance.recovery.discard": (stop, False),
        "lmdj.performance.rename": (lifecycle, True),
        "lmdj.performance.delete": (lifecycle, True),
        "lmdj.performance.recording.bind": (lifecycle, True),
        "lmdj.performance.replay.begin": (replay_status, False),
        "lmdj.performance.replay.stop": (replay_stop, False),
        "lmdj.performance.replay.status": (replay_status, False),
        "lmdj.performance.resample.commit": (resample, True),
    }
    assert len(by_name) == 23
    return {
        name: facade_output_schema(result, uint if has_revision else null)
        for name, (result, has_revision) in by_name.items()
    }


def test_locked_tool_set_kind_and_schema() -> None:
    expected = expected_performance_tools()
    expected_outputs = expected_performance_output_schemas()
    actual = {
        tool.name: (
            tool.operation,
            tool.surface,
            tool.input_schema,
            tool.output_schema,
        )
        for tool in server.TOOLS
        if tool.operation.startswith("performance.")
        or tool.operation.startswith("pattern.slot.")
    }
    assert actual == {
        name: (*route, expected_outputs[name])
        for name, route in expected.items()
    }
    assert set(actual) == set(expected)
    assert all("*" not in name for name in actual)


def main() -> int:
    test_locked_tool_set_kind_and_schema()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
