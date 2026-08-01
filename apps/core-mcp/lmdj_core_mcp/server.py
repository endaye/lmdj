"""Dependency-free MCP 2025-11-25 JSON-RPC stdio adapter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
import re
from typing import BinaryIO, Iterator

from .c_api import (
    CApiError,
    Engine,
    REQUEST_LIMIT,
    has_only_unicode_scalars,
)


PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "lmdj-core-mcp"
SERVER_VERSION = "0.1.1"
UUID_PATTERN = (
    "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    "[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
FILE_ID_PATTERN = "^[A-Za-z0-9._-]{1,128}$"


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
    velocity = {"type": "integer", "minimum": 1, "maximum": 127}
    raw_event = object_schema(
        {
            "slot": slot,
            "frame_offset": {
                "type": "integer",
                "minimum": 0,
                "maximum": 4294967295,
            },
            "velocity": velocity,
        },
        ["slot", "frame_offset", "velocity"],
    )
    pattern_event = object_schema(
        {
            "slot": slot,
            "step": {"type": "integer", "minimum": 0, "maximum": 127},
            "velocity": velocity,
        },
        ["slot", "step", "velocity"],
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
            },
            ["project_path", "project_id", "bpm"],
        ),
        "lmdj.project.inspect": object_schema(
            {"project_path": path},
            ["project_path"],
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
        "lmdj.take.begin": object_schema(
            {
                "project_path": path,
                "take_id": uuid,
                "expected_revision": uint,
                "sample_rate": {"type": "integer", "const": 48000},
            },
            [
                "project_path",
                "take_id",
                "expected_revision",
                "sample_rate",
            ],
        ),
        "lmdj.take.append": object_schema(
            {
                "project_path": path,
                "take_id": uuid,
                "event": raw_event,
            },
            ["project_path", "take_id", "event"],
        ),
        "lmdj.take.commit": object_schema(
            {
                "project_path": path,
                "command_id": uuid,
                "expected_revision": uint,
                "take_id": uuid,
                "pattern": pattern,
            },
            [
                "project_path",
                "command_id",
                "expected_revision",
                "take_id",
                "pattern",
            ],
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
                "inputs": {"type": "array", "items": artifact},
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


def tool_table() -> tuple[Tool, ...]:
    schemas = input_schemas()
    routes = (
        ("lmdj.project.create", "project.create", "command"),
        ("lmdj.project.inspect", "project.inspect", "query"),
        ("lmdj.asset.import", "asset.import", "command"),
        ("lmdj.pad.assign", "pad.assign", "command"),
        ("lmdj.take.begin", "take.begin", "command"),
        ("lmdj.take.append", "take.append", "command"),
        ("lmdj.take.commit", "take.commit", "command"),
        ("lmdj.snapshot.cook", "snapshot.cook", "query"),
        ("lmdj.render.offline", "render.offline", "command"),
        ("lmdj.provider.list", "provider.list", "query"),
        ("lmdj.provider.select", "provider.select", "command"),
        ("lmdj.provider.run", "provider.run", "command"),
        ("lmdj.attempt.inspect", "attempt.inspect", "query"),
    )
    return tuple(
        Tool(name, operation, surface, schemas[name])
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
                        "outputSchema": OUTPUT_SCHEMA,
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
        if not facade_envelope(envelope):
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
