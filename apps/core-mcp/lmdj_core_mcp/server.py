"""Dependency-free MCP 2025-11-25 JSON-RPC stdio adapter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
import re
from typing import BinaryIO, Iterator

from . import __version__
from .c_api import (
    CApiError,
    Engine,
    REQUEST_LIMIT,
    has_only_unicode_scalars,
)


PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "lmdj-core-mcp"
SERVER_VERSION = __version__
UUID_PATTERN = (
    "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    "[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
FILE_ID_PATTERN = "^[A-Za-z0-9._-]{1,128}$"
# A port name is not a file identifier. This mirrors the `port_name` rule in
# contracts/capability/lmdj.capability.v2.schema.json and the C++
# lmdj::provider::valid_port_name, so the advertised tool Schema describes the
# domain the Core actually accepts.
PORT_NAME_PATTERN = "^[a-z][a-z0-9_]*$"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def object_schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def output_schema() -> dict:
    success = object_schema(
        {
            "ok": {"const": True},
            "result": {"type": "object"},
            "project_revision": {
                "oneOf": [
                    {"type": "integer", "minimum": 0},
                    {"type": "null"},
                ]
            },
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


def performance_output_schemas() -> dict[str, dict]:
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
    nullable_recording_artifact = {"oneOf": [recording_artifact, null]}
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
            "fingerprint": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
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
            "state": {"type": "string", "enum": ["playing", "stopped", "complete"]},
            "resolved_revision": uint,
            "event_cursor": uint,
            "event_count": uint,
        },
        ["replay_id", "state", "resolved_revision", "event_cursor", "event_count"],
    )
    replay_stop = object_schema(
        replay_status["properties"] | {"request_id": uuid, "replayed": boolean},
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
        ["performance_id", "name", "created_bpm", "recording_artifact", "event_count"],
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
    result_schemas: dict[str, tuple[dict, bool]] = {
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
    return {
        name: {
            "type": "object",
            "oneOf": [
                object_schema(
                    {
                        "ok": {"const": True},
                        "result": result,
                        "project_revision": uint if has_revision else null,
                    },
                    ["ok", "result", "project_revision"],
                ),
                error,
            ],
        }
        for name, (result, has_revision) in result_schemas.items()
    }


def input_schemas() -> dict[str, dict]:
    path = {"type": "string", "minLength": 1}
    uuid = {"type": "string", "pattern": UUID_PATTERN}
    file_id = {
        "type": "string",
        "minLength": 1,
        "maxLength": 128,
        "pattern": FILE_ID_PATTERN,
    }
    uint = {"type": "integer", "minimum": 0}
    slot = object_schema(
        {
            "bank": {"type": "integer", "minimum": 0, "maximum": 3},
            "pad": {"type": "integer", "minimum": 0, "maximum": 15},
        },
        ["bank", "pad"],
    )
    playback = object_schema(
        {
            "trim_start_frame": uint,
            "trim_end_frame": {
                "oneOf": [uint, {"type": "null"}],
            },
            "trigger_mode": {
                "type": "string",
                "enum": [
                    "one_shot",
                    "gate",
                    "loop_gate",
                    "loop_toggle",
                ],
            },
            "gain_millidb": {
                "type": "integer",
                "minimum": -60_000,
                "maximum": 6_000,
            },
            "muted": {"type": "boolean"},
        },
        [
            "trim_start_frame",
            "trim_end_frame",
            "trigger_mode",
            "gain_millidb",
            "muted",
        ],
    )
    waveform_window = object_schema(
        {
            "start_frame": uint,
            "end_frame": uint,
            "bucket_count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 512,
            },
        },
        ["start_frame", "end_frame", "bucket_count"],
    )
    sidecar = object_schema(
        {
            "sidecar_bytes": {
                "type": "integer",
                "minimum": 0,
                "maximum": 1_048_576,
            },
            "sidecar_sha256": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
        },
        ["sidecar_bytes", "sidecar_sha256"],
    )
    velocity = {"type": "integer", "minimum": 1, "maximum": 127}
    sequence_velocity = {"type": "integer", "minimum": 0, "maximum": 127}
    sequence_event = object_schema(
        {
            "slot": slot,
            "velocity": sequence_velocity,
            "runtime_frame": uint,
            "input_sequence": uint,
            "pressed": {"type": "boolean"},
        },
        ["slot", "velocity", "runtime_frame", "input_sequence", "pressed"],
    )
    pattern_event = object_schema(
        {
            "slot": slot,
            "onset_tick": uint,
            "duration_tick": {"type": "integer", "minimum": 1},
            "velocity": velocity,
        },
        ["slot", "onset_tick", "duration_tick", "velocity"],
    )
    pattern = object_schema(
        {
            "pattern_id": uuid,
            "bars": {"type": "integer", "enum": [1, 2, 4, 8]},
            "events": {"type": "array", "items": pattern_event},
        },
        ["pattern_id", "bars", "events"],
    )
    artifact = object_schema(
        {
            "sha256": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
            "media_type": {"type": "string", "minLength": 1},
            "byte_length": uint,
        },
        ["sha256", "media_type", "byte_length"],
    )
    recording_artifact = object_schema(
        {
            "sha256": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
            "media_type": {"const": "audio/wav"},
            "byte_length": uint,
        },
        ["sha256", "media_type", "byte_length"],
    )
    pattern_slot = {"type": "integer", "minimum": 0, "maximum": 15}
    performance_fx = {
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
    performance_event = {
        "oneOf": [
            object_schema(
                {
                    "kind": {"const": "pad_press"},
                    "gesture_id": uuid,
                    "slot": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 63,
                    },
                    "velocity": velocity,
                },
                ["kind", "gesture_id", "slot", "velocity"],
            ),
            object_schema(
                {
                    "kind": {"const": "pad_release"},
                    "gesture_id": uuid,
                    "slot": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 63,
                    },
                },
                ["kind", "gesture_id", "slot"],
            ),
            object_schema(
                {
                    "kind": {"const": "fx_engage"},
                    "gesture_id": uuid,
                    "fx": performance_fx,
                    "value": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                },
                ["kind", "gesture_id", "fx", "value"],
            ),
            object_schema(
                {
                    "kind": {"const": "fx_move"},
                    "gesture_id": uuid,
                    "fx": performance_fx,
                    "value": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                },
                ["kind", "gesture_id", "fx", "value"],
            ),
            object_schema(
                {
                    "kind": {"const": "fx_release"},
                    "gesture_id": uuid,
                    "fx": performance_fx,
                },
                ["kind", "gesture_id", "fx"],
            ),
            object_schema({"kind": {"const": "hold_on"}}, ["kind"]),
            object_schema({"kind": {"const": "hold_off"}}, ["kind"]),
        ]
    }
    port_name = {"type": "string", "pattern": PORT_NAME_PATTERN}
    artifact_binding = object_schema(
        {
            "port": port_name,
            "artifact": artifact,
        },
        ["port", "artifact"],
    )
    return {
        "lmdj.project.create": object_schema(
            {
                "project_path": path,
                "project_id": uuid,
                "bpm": {
                    "type": "integer",
                    "minimum": 40,
                    "maximum": 240,
                },
                "initial_pattern": pattern,
            },
            ["project_path", "project_id", "bpm"],
        ),
        "lmdj.project.inspect": object_schema(
            {"project_path": path},
            ["project_path"],
        ),
        "lmdj.sample.inspect": object_schema(
            {"project_path": path, "slot": slot},
            ["project_path", "slot"],
        ),
        "lmdj.sample.quota": object_schema(
            {"project_path": path, "slot": slot},
            ["project_path", "slot"],
        ),
        "lmdj.sample.waveform": object_schema(
            {
                "project_path": path,
                "slot": slot,
                "window": waveform_window,
            },
            ["project_path", "slot", "window"],
        ),
        "lmdj.sample.import.begin": object_schema(
            {
                "import_token": uuid,
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "slot": slot,
                "asset_id": uuid,
                "byte_length": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1_048_576,
                },
            },
            [
                "import_token",
                "project_path",
                "command_id",
                "expected_revision",
                "slot",
                "asset_id",
                "byte_length",
            ],
        ),
        "lmdj.sample.import.chunk": object_schema(
            {
                "import_token": uuid,
                "offset": uint,
                "final": {"type": "boolean"},
                "sidecar": sidecar,
            },
            ["import_token", "offset", "final", "sidecar"],
        ),
        "lmdj.sample.import.commit": object_schema(
            {"import_token": uuid},
            ["import_token"],
        ),
        "lmdj.sample.import.abort": object_schema(
            {"import_token": uuid},
            ["import_token"],
        ),
        "lmdj.sample.update_pad": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "slot": slot,
                "playback": playback,
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "slot",
                "playback",
            ],
        ),
        "lmdj.sample.reset_pad": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "slot": slot,
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "slot",
            ],
        ),
        "lmdj.asset.import": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "asset_id": uuid,
                "source_path": path,
                "media_type": {"type": "string", "minLength": 1},
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "asset_id",
                "source_path",
                "media_type",
            ],
        ),
        "lmdj.pad.assign": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "slot": slot,
                "asset_id": {"oneOf": [uuid, {"type": "null"}]},
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "slot",
                "asset_id",
            ],
        ),
        "lmdj.pattern.create": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "pattern_id": uuid,
                "bars": {"type": "integer", "enum": [1, 2, 4, 8]},
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "pattern_id",
                "bars",
            ],
        ),
        "lmdj.pattern.slot.assign": object_schema(
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
        "lmdj.pattern.slot.clear": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "pattern_slot": pattern_slot,
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "pattern_slot",
            ],
        ),
        "lmdj.pattern.slot.move": object_schema(
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
        "lmdj.performance.list": object_schema(
            {"project_path": path}, ["project_path"],
        ),
        "lmdj.performance.inspect": object_schema(
            {"project_path": path, "performance_id": uuid},
            ["project_path", "performance_id"],
        ),
        "lmdj.performance.record.begin": object_schema(
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
        "lmdj.performance.record.event": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "event_id": uuid,
                "event": performance_event,
            },
            ["project_path", "session_id", "event_id", "event"],
        ),
        "lmdj.performance.record.launch-request": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "request_id": uuid,
                "pattern_slot": pattern_slot,
            },
            ["project_path", "session_id", "request_id", "pattern_slot"],
        ),
        "lmdj.performance.record.flush": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "command_id": uuid,
            },
            ["project_path", "session_id", "command_id"],
        ),
        "lmdj.performance.record.stop": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "request_id": uuid,
            },
            ["project_path", "session_id", "request_id"],
        ),
        "lmdj.performance.record.status": object_schema(
            {"project_path": path}, ["project_path"],
        ),
        "lmdj.performance.save": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "performance_id": uuid,
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 64,
                },
                "recording_artifact": {
                    "oneOf": [recording_artifact, {"type": "null"}],
                },
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
        "lmdj.performance.discard": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "performance_id": uuid,
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "performance_id",
            ],
        ),
        "lmdj.performance.recovery.list": object_schema(
            {"project_path": path}, ["project_path"],
        ),
        "lmdj.performance.recovery.apply": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "session_id": uuid,
            },
            ["project_path", "command_id", "expected_revision", "session_id"],
        ),
        "lmdj.performance.recovery.discard": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "request_id": uuid,
            },
            ["project_path", "session_id", "request_id"],
        ),
        "lmdj.performance.rename": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "performance_id": uuid,
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 64,
                },
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "performance_id",
                "name",
            ],
        ),
        "lmdj.performance.delete": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "performance_id": uuid,
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "performance_id",
            ],
        ),
        "lmdj.performance.recording.bind": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "performance_id": uuid,
                "recording_artifact": recording_artifact,
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "performance_id",
                "recording_artifact",
            ],
        ),
        "lmdj.performance.replay.begin": object_schema(
            {
                "project_path": path,
                "replay_id": uuid,
                "performance_id": uuid,
            },
            ["project_path", "replay_id", "performance_id"],
        ),
        "lmdj.performance.replay.stop": object_schema(
            {
                "project_path": path,
                "replay_id": uuid,
                "request_id": uuid,
            },
            ["project_path", "replay_id", "request_id"],
        ),
        "lmdj.performance.replay.status": object_schema(
            {"project_path": path, "replay_id": uuid},
            ["project_path", "replay_id"],
        ),
        "lmdj.performance.resample.commit": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "performance_id": uuid,
                "source_start_frame": uint,
                "source_end_frame": uint,
                "target_slot": slot,
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
        "lmdj.sequence.record.begin": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "pattern_id": uuid,
                "expected_revision": uint,
                "runtime_frame": uint,
            },
            [
                "project_path",
                "session_id",
                "pattern_id",
                "expected_revision",
                "runtime_frame",
            ],
        ),
        "lmdj.sequence.record.event": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "event": sequence_event,
            },
            ["project_path", "session_id", "event"],
        ),
        "lmdj.sequence.record.flush": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "command_id": uuid,
                "runtime_frame": uint,
            },
            ["project_path", "session_id", "command_id", "runtime_frame"],
        ),
        "lmdj.sequence.record.stop": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "command_id": uuid,
                "runtime_frame": uint,
            },
            ["project_path", "session_id", "command_id", "runtime_frame"],
        ),
        "lmdj.sequence.record.switch-request": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "next_pattern_id": uuid,
            },
            ["project_path", "session_id", "next_pattern_id"],
        ),
        "lmdj.sequence.record.status": object_schema(
            {"project_path": path}, ["project_path"],
        ),
        "lmdj.sequence.settings.update": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "session_id": {"oneOf": [uuid, {"type": "null"}]},
                "runtime_frame": uint,
                "bpm": {
                    "oneOf": [
                        {"type": "integer", "minimum": 40, "maximum": 240},
                        {"type": "null"},
                    ]
                },
                "quantize_enabled": {
                    "oneOf": [{"type": "boolean"}, {"type": "null"}]
                },
                "swing_percent": {
                    "oneOf": [
                        {"type": "integer", "minimum": 50, "maximum": 75},
                        {"type": "null"},
                    ]
                },
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "session_id",
                "runtime_frame",
                "bpm",
                "quantize_enabled",
                "swing_percent",
            ],
        ),
        "lmdj.sequence.recovery.list": object_schema(
            {"project_path": path}, ["project_path"],
        ),
        "lmdj.sequence.recovery.apply": object_schema(
            {
                "project_path": path,
                "session_id": uuid,
                "destination_pattern_id": {"oneOf": [uuid, {"type": "null"}]},
            },
            ["project_path", "session_id", "destination_pattern_id"],
        ),
        "lmdj.sequence.recovery.discard": object_schema(
            {"project_path": path, "session_id": uuid},
            ["project_path", "session_id"],
        ),
        "lmdj.snapshot.cook": object_schema(
            {"project_path": path, "pattern_id": uuid},
            ["project_path", "pattern_id"],
        ),
        "lmdj.render.offline": object_schema(
            {
                "project_path": path,
                "pattern_id": uuid,
                "output_path": path,
            },
            ["project_path", "pattern_id", "output_path"],
        ),
        "lmdj.provider.list": object_schema({}, []),
        "lmdj.provider.select": object_schema(
            {"capability": file_id, "provider_id": file_id},
            ["capability", "provider_id"],
        ),
        "lmdj.provider.run": object_schema(
            {
                "attempt_id": file_id,
                "capability": file_id,
                "inputs": {
                    "type": "array",
                    "items": artifact_binding,
                },
                "parameters": {"type": "object"},
                "data_classification": file_id,
                "platform": file_id,
                "region": file_id,
                "required_permissions": {
                    "type": "array",
                    "items": file_id,
                },
            },
            [
                "attempt_id",
                "capability",
                "inputs",
                "parameters",
                "data_classification",
                "platform",
                "region",
                "required_permissions",
            ],
        ),
        "lmdj.attempt.inspect": object_schema(
            {"attempt_id": file_id},
            ["attempt_id"],
        ),
    }


@dataclass(frozen=True)
class Tool:
    name: str
    operation: str
    surface: str
    input_schema: dict
    output_schema: dict


def tool_table() -> tuple[Tool, ...]:
    schemas = input_schemas()
    default_output = output_schema()
    performance_outputs = performance_output_schemas()
    routes = (
        ("lmdj.project.create", "project.create", "command"),
        ("lmdj.project.inspect", "project.inspect", "query"),
        ("lmdj.sample.inspect", "sample.inspect", "query"),
        ("lmdj.sample.quota", "sample.quota", "query"),
        ("lmdj.sample.waveform", "sample.waveform", "query"),
        ("lmdj.sample.import.begin", "sample.import.begin", "command"),
        ("lmdj.sample.import.chunk", "sample.import.chunk", "command"),
        ("lmdj.sample.import.commit", "sample.import.commit", "command"),
        ("lmdj.sample.import.abort", "sample.import.abort", "command"),
        ("lmdj.sample.update_pad", "sample.update_pad", "command"),
        ("lmdj.sample.reset_pad", "sample.reset_pad", "command"),
        ("lmdj.asset.import", "asset.import", "command"),
        ("lmdj.pad.assign", "pad.assign", "command"),
        ("lmdj.pattern.create", "pattern.create", "command"),
        ("lmdj.pattern.slot.assign", "pattern.slot.assign", "command"),
        ("lmdj.pattern.slot.clear", "pattern.slot.clear", "command"),
        ("lmdj.pattern.slot.move", "pattern.slot.move", "command"),
        ("lmdj.performance.list", "performance.list", "query"),
        ("lmdj.performance.inspect", "performance.inspect", "query"),
        (
            "lmdj.performance.record.begin",
            "performance.record.begin",
            "command",
        ),
        (
            "lmdj.performance.record.event",
            "performance.record.event",
            "command",
        ),
        (
            "lmdj.performance.record.launch-request",
            "performance.record.launch-request",
            "command",
        ),
        (
            "lmdj.performance.record.flush",
            "performance.record.flush",
            "command",
        ),
        (
            "lmdj.performance.record.stop",
            "performance.record.stop",
            "command",
        ),
        (
            "lmdj.performance.record.status",
            "performance.record.status",
            "query",
        ),
        ("lmdj.performance.save", "performance.save", "command"),
        ("lmdj.performance.discard", "performance.discard", "command"),
        (
            "lmdj.performance.recovery.list",
            "performance.recovery.list",
            "query",
        ),
        (
            "lmdj.performance.recovery.apply",
            "performance.recovery.apply",
            "command",
        ),
        (
            "lmdj.performance.recovery.discard",
            "performance.recovery.discard",
            "command",
        ),
        ("lmdj.performance.rename", "performance.rename", "command"),
        ("lmdj.performance.delete", "performance.delete", "command"),
        (
            "lmdj.performance.recording.bind",
            "performance.recording.bind",
            "command",
        ),
        (
            "lmdj.performance.replay.begin",
            "performance.replay.begin",
            "command",
        ),
        (
            "lmdj.performance.replay.stop",
            "performance.replay.stop",
            "command",
        ),
        (
            "lmdj.performance.replay.status",
            "performance.replay.status",
            "query",
        ),
        (
            "lmdj.performance.resample.commit",
            "performance.resample.commit",
            "command",
        ),
        ("lmdj.sequence.record.begin", "sequence.record.begin", "command"),
        ("lmdj.sequence.record.event", "sequence.record.event", "command"),
        ("lmdj.sequence.record.flush", "sequence.record.flush", "command"),
        ("lmdj.sequence.record.stop", "sequence.record.stop", "command"),
        (
            "lmdj.sequence.record.switch-request",
            "sequence.record.switch-request",
            "command",
        ),
        ("lmdj.sequence.record.status", "sequence.record.status", "query"),
        ("lmdj.sequence.settings.update", "sequence.settings.update", "command"),
        ("lmdj.sequence.recovery.list", "sequence.recovery.list", "query"),
        ("lmdj.sequence.recovery.apply", "sequence.recovery.apply", "command"),
        ("lmdj.sequence.recovery.discard", "sequence.recovery.discard", "command"),
        ("lmdj.snapshot.cook", "snapshot.cook", "query"),
        ("lmdj.render.offline", "render.offline", "command"),
        ("lmdj.provider.list", "provider.list", "query"),
        ("lmdj.provider.select", "provider.select", "command"),
        ("lmdj.provider.run", "provider.run", "command"),
        ("lmdj.attempt.inspect", "attempt.inspect", "query"),
    )
    return tuple(
        Tool(
            name,
            operation,
            surface,
            schemas[name],
            performance_outputs.get(name, default_output),
        )
        for name, operation, surface in routes
    )


TOOLS = tool_table()
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
OUTPUT_SCHEMA = output_schema()


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validates(schema: dict, value: object) -> bool:
    if "oneOf" in schema and (
        sum(validates(option, value) for option in schema["oneOf"]) != 1
    ):
        return False
    if "const" in schema:
        expected = schema["const"]
        if isinstance(expected, bool):
            if value is not expected:
                return False
        elif value != expected:
            return False
    if "enum" in schema and value not in schema["enum"]:
        return False

    value_type = schema.get("type")
    if value_type == "null":
        return value is None
    if value_type == "boolean" and not isinstance(value, bool):
        return False
    if value_type == "integer" and not _is_integer(value):
        return False
    if value_type == "number" and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        return False
    if value_type == "string" and not isinstance(value, str):
        return False
    if value_type == "array" and not isinstance(value, list):
        return False
    if value_type == "object" and not isinstance(value, dict):
        return False

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            return False
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return False
        if "pattern" in schema and re.fullmatch(
            schema["pattern"], value
        ) is None:
            return False
    if _is_integer(value) or (
        isinstance(value, float) and not isinstance(value, bool)
    ):
        if "minimum" in schema and value < schema["minimum"]:
            return False
        if "maximum" in schema and value > schema["maximum"]:
            return False
    if isinstance(value, list) and "items" in schema:
        if not all(validates(schema["items"], item) for item in value):
            return False
    if isinstance(value, dict) and value_type == "object":
        required = schema.get("required", [])
        if any(key not in value for key in required):
            return False
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and any(
            key not in properties for key in value
        ):
            return False
        for key, member in value.items():
            if key in properties and not validates(properties[key], member):
                return False
    return True


class State(Enum):
    NEW = "new"
    AWAIT_INITIALIZED = "await_initialized"
    READY = "ready"


@dataclass(frozen=True)
class OversizedLine:
    pass


@dataclass(frozen=True)
class UnterminatedLine:
    pass


def bounded_lines(file_descriptor: int) -> Iterator[bytes | object]:
    buffer = bytearray()
    oversized = False
    while True:
        try:
            chunk = os.read(file_descriptor, 64 * 1024)
        except InterruptedError:
            continue
        if not chunk:
            if oversized or buffer:
                yield UnterminatedLine()
            return
        start = 0
        while start < len(chunk):
            newline = chunk.find(b"\n", start)
            end = len(chunk) if newline < 0 else newline
            if not oversized:
                remaining = REQUEST_LIMIT + 1 - len(buffer)
                buffer.extend(chunk[start : min(end, start + remaining)])
                if len(buffer) > REQUEST_LIMIT or end - start > remaining:
                    oversized = True
                    buffer.clear()
            if newline < 0:
                break
            if oversized:
                yield OversizedLine()
            else:
                yield bytes(buffer)
            buffer.clear()
            oversized = False
            start = newline + 1


def error_response(identifier: object, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": code, "message": message},
    }


def success_response(identifier: object, result: object) -> dict:
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def valid_id(value: object) -> bool:
    return isinstance(value, str) or _is_integer(value)


def valid_meta(value: object) -> bool:
    return isinstance(value, dict)


def valid_meta_only_params(params: dict | None) -> bool:
    return (
        params is None
        or (
            isinstance(params, dict)
            and set(params) <= {"_meta"}
            and ("_meta" not in params or valid_meta(params["_meta"]))
        )
    )


def valid_icon(value: object) -> bool:
    if not isinstance(value, dict) or not {"src"} <= set(value):
        return False
    if set(value) - {"src", "mimeType", "sizes", "theme"}:
        return False
    if not isinstance(value["src"], str) or not value["src"]:
        return False
    if "mimeType" in value and not isinstance(value["mimeType"], str):
        return False
    if "sizes" in value and (
        not isinstance(value["sizes"], list)
        or not all(isinstance(size, str) for size in value["sizes"])
    ):
        return False
    return "theme" not in value or (
        isinstance(value["theme"], str)
        and value["theme"] in {"light", "dark"}
    )


def valid_implementation(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if not {"name", "version"} <= set(value) or set(value) - {
        "name",
        "title",
        "version",
        "description",
        "websiteUrl",
        "icons",
    }:
        return False
    if (
        not isinstance(value["name"], str)
        or not value["name"]
        or not isinstance(value["version"], str)
        or not value["version"]
    ):
        return False
    if any(
        field in value and not isinstance(value[field], str)
        for field in ("title", "description", "websiteUrl")
    ):
        return False
    return "icons" not in value or (
        isinstance(value["icons"], list)
        and all(valid_icon(icon) for icon in value["icons"])
    )


def valid_initialize_params(params: dict | None) -> bool:
    if (
        not isinstance(params, dict)
        or not {"protocolVersion", "capabilities", "clientInfo"} <= set(params)
        or set(params)
        - {"protocolVersion", "capabilities", "clientInfo", "_meta"}
    ):
        return False
    return (
        isinstance(params["protocolVersion"], str)
        and isinstance(params["capabilities"], dict)
        and valid_implementation(params["clientInfo"])
        and ("_meta" not in params or valid_meta(params["_meta"]))
    )


def facade_envelope(value: object) -> bool:
    return validates(OUTPUT_SCHEMA, value)


class Server:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._state = State.NEW

    def handle(self, encoded: bytes | object) -> dict | None:
        if isinstance(encoded, OversizedLine):
            return error_response(None, -32600, "Invalid Request")
        if isinstance(encoded, UnterminatedLine):
            return error_response(None, -32600, "Invalid Request")
        try:
            text = encoded.decode("utf-8", errors="strict")
            message = json.loads(
                text,
                parse_constant=reject_nonstandard_constant,
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
            RecursionError,
        ):
            return error_response(None, -32700, "Parse error")
        if not isinstance(message, dict):
            return error_response(None, -32600, "Invalid Request")

        notification = "id" not in message
        if not has_only_unicode_scalars(message):
            if notification:
                return None
            return error_response(None, -32600, "Invalid Request")
        if notification:
            self._handle_notification(message)
            return None

        identifier = message.get("id")
        if not valid_id(identifier):
            return error_response(None, -32600, "Invalid Request")
        if (
            set(message) - {"jsonrpc", "id", "method", "params"}
            or message.get("jsonrpc") != "2.0"
            or not isinstance(message.get("method"), str)
            or (
                "params" in message
                and not isinstance(message["params"], dict)
            )
        ):
            return error_response(identifier, -32600, "Invalid Request")
        try:
            return self._dispatch_request(
                identifier,
                message["method"],
                message.get("params"),
            )
        except Exception:
            return error_response(identifier, -32603, "Internal error")

    def _handle_notification(self, message: dict) -> None:
        if (
            set(message) - {"jsonrpc", "method", "params"}
            or message.get("jsonrpc") != "2.0"
            or not isinstance(message.get("method"), str)
            or (
                "params" in message
                and not isinstance(message["params"], dict)
            )
        ):
            return
        params = message.get("params")
        if (
            message["method"] == "notifications/initialized"
            and self._state is State.AWAIT_INITIALIZED
            and valid_meta_only_params(params)
        ):
            self._state = State.READY

    def _dispatch_request(
        self,
        identifier: str | int,
        method: str,
        params: dict | None,
    ) -> dict:
        if method == "ping":
            if not valid_meta_only_params(params):
                return error_response(identifier, -32602, "Invalid params")
            return success_response(identifier, {})
        if method == "initialize":
            if self._state is not State.NEW:
                return error_response(identifier, -32600, "Invalid Request")
            if not valid_initialize_params(params):
                return error_response(identifier, -32602, "Invalid params")
            self._state = State.AWAIT_INITIALIZED
            return success_response(
                identifier,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                },
            )
        if method == "tools/list":
            if not valid_meta_only_params(params):
                return error_response(identifier, -32602, "Invalid params")
            if self._state is not State.READY:
                return error_response(
                    identifier,
                    -32002,
                    "Server not initialized",
                )
            return self._list_tools(identifier)
        if method == "tools/call":
            parsed = self._parse_tool_call(params)
            if parsed is None:
                return error_response(identifier, -32602, "Invalid params")
            if self._state is not State.READY:
                return error_response(
                    identifier,
                    -32002,
                    "Server not initialized",
                )
            tool, arguments = parsed
            return self._call_tool(identifier, tool, arguments)
        return error_response(identifier, -32601, "Method not found")

    @staticmethod
    def _list_tools(identifier: str | int) -> dict:
        return success_response(
            identifier,
            {
                "tools": [
                    {
                        "name": tool.name,
                        "inputSchema": tool.input_schema,
                        "outputSchema": tool.output_schema,
                    }
                    for tool in TOOLS
                ]
            },
        )

    @staticmethod
    def _parse_tool_call(
        params: dict | None,
    ) -> tuple[Tool, dict] | None:
        if (
            not isinstance(params, dict)
            or set(params) - {"name", "arguments", "_meta"}
            or "name" not in params
            or not isinstance(params["name"], str)
            or ("_meta" in params and not valid_meta(params["_meta"]))
        ):
            return None
        tool = TOOLS_BY_NAME.get(params["name"])
        if tool is None:
            return None
        arguments = params.get("arguments", {})
        if not validates(tool.input_schema, arguments):
            return None
        return tool, arguments

    def _call_tool(
        self,
        identifier: str | int,
        tool: Tool,
        arguments: dict,
    ) -> dict:
        request = {"operation": tool.operation, **arguments}
        if len(canonical_json(request).encode("utf-8")) > REQUEST_LIMIT:
            return error_response(identifier, -32602, "Invalid params")
        try:
            if tool.surface == "command":
                envelope = self._engine.command(request)
            else:
                envelope = self._engine.query(request)
        except CApiError:
            return error_response(identifier, -32603, "Internal error")
        if not validates(tool.output_schema, envelope):
            return error_response(identifier, -32603, "Internal error")
        return success_response(
            identifier,
            {
                "content": [
                    {"type": "text", "text": canonical_json(envelope)}
                ],
                "structuredContent": envelope,
                "isError": envelope["ok"] is False,
            },
        )


def write_response(stdout: BinaryIO, response: dict) -> None:
    encoded = canonical_json(response).encode("utf-8") + b"\n"
    stdout.write(encoded)
    stdout.flush()


def serve(engine: Engine, stdin_fd: int, stdout: BinaryIO) -> int:
    server = Server(engine)
    try:
        for encoded in bounded_lines(stdin_fd):
            response = server.handle(encoded)
            if response is not None:
                write_response(stdout, response)
    except BrokenPipeError:
        return 0
    return 0
