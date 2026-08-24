import ast
import ctypes
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import tomllib

from lmdj_core_mcp import __version__, c_api, server


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUEST_LIMIT = 16 * 1024 * 1024
TIMEOUT_SECONDS = 10
PROTOCOL_VERSION = "2025-11-25"
UUID_PATTERN = (
    "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    "[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
FILE_ID_PATTERN = "^[A-Za-z0-9._-]{1,128}$"
# Held independently of server.py on purpose: a change to the advertised port
# domain must be mirrored here deliberately, not inherited silently.
PORT_NAME_PATTERN = "^[a-z][a-z0-9_]*$"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


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


def communicate_with_timeout(
    process: subprocess.Popen,
) -> tuple[bytes, bytes]:
    try:
        return process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=TIMEOUT_SECONDS)
        raise


def object_schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def expected_schemas() -> dict[str, dict]:
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
    port_name = {"type": "string", "pattern": PORT_NAME_PATTERN}
    artifact_binding = object_schema(
        {
            "port": port_name,
            "artifact": artifact,
        },
        ["port", "artifact"],
    )
    playback = object_schema(
        {
            "trim_start_frame": uint,
            "trim_end_frame": {"oneOf": [uint, {"type": "null"}]},
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
                "minimum": -60000,
                "maximum": 6000,
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
        "lmdj.sample.inspect": object_schema(
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
            ["project_path", "command_id", "expected_revision", "slot"],
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


def expected_output_schema() -> dict:
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


class MCPProcess:
    def __init__(
        self,
        library: Path,
        workspace: Path,
        *,
        assembly: Path | None = None,
        stdout=None,
        environment: dict[str, str] | None = None,
    ) -> None:
        env = host_environment()
        if environment:
            env.update(environment)
        arguments = [
            sys.executable,
            "-m",
            "lmdj_core_mcp",
            "--library",
            str(library),
            "--workspace",
            str(workspace),
        ]
        if assembly is not None:
            arguments.extend(["--assembly", str(assembly)])
        self.process = subprocess.Popen(
            arguments,
            cwd=REPO_ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE if stdout is None else stdout,
            stderr=subprocess.PIPE,
        )
        assert self.process.stdin is not None
        if stdout is None:
            assert self.process.stdout is not None

    def send_raw(self, value: bytes) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(value)
        self.process.stdin.flush()

    def send(self, value: object) -> None:
        self.send_raw(canonical_json(value).encode("utf-8") + b"\n")

    def receive_raw(self, timeout: float = TIMEOUT_SECONDS) -> bytes:
        assert self.process.stdout is not None
        ready, _, _ = select.select(
            [self.process.stdout.fileno()],
            [],
            [],
            timeout,
        )
        if not ready:
            self.process.kill()
            _, stderr = communicate_with_timeout(self.process)
            raise AssertionError(
                "timed out waiting for MCP response",
                stderr,
            )
        line = self.process.stdout.readline()
        assert line, (
            "MCP process exited before response",
            self.process.poll(),
            self.read_stderr(),
        )
        return line

    def receive(self, timeout: float = TIMEOUT_SECONDS) -> dict:
        line = self.receive_raw(timeout)
        parsed = json.loads(line.decode("utf-8", errors="strict"))
        assert isinstance(parsed, dict)
        assert line == canonical_json(parsed).encode("utf-8") + b"\n"
        return parsed

    def assert_silent(self, timeout: float = 0.15) -> None:
        assert self.process.stdout is not None
        ready, _, _ = select.select(
            [self.process.stdout.fileno()],
            [],
            [],
            timeout,
        )
        assert not ready, self.process.stdout.readline()

    def request(
        self,
        identifier: str | int,
        method: str,
        params: dict | None = None,
    ) -> dict:
        message = {
            "jsonrpc": "2.0",
            "id": identifier,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self.send(message)
        return self.receive()

    def initialize(self, version: str = PROTOCOL_VERSION) -> dict:
        response = self.request(
            1,
            "initialize",
            {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "lmdj-proof", "version": "0.1.0"},
            },
        )
        self.send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        )
        self.assert_silent()
        return response

    def tool_call(
        self,
        identifier: str | int,
        name: str,
        arguments: dict | None = None,
        *,
        omit_arguments: bool = False,
    ) -> dict:
        params: dict[str, object] = {"name": name}
        if not omit_arguments:
            params["arguments"] = {} if arguments is None else arguments
        return self.request(identifier, "tools/call", params)

    def read_stderr(self) -> bytes:
        assert self.process.stderr is not None
        if self.process.poll() is None:
            return b""
        return self.process.stderr.read()

    def close(self) -> tuple[int, bytes, bytes]:
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        self.process.stdin = None
        stdout, stderr = communicate_with_timeout(self.process)
        return self.process.returncode, stdout or b"", stderr or b""


def assert_error(response: dict, identifier: object, code: int, message: str) -> None:
    assert response == {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": code, "message": message},
    }


def assert_tool_result(response: dict, identifier: object) -> dict:
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == identifier
    assert set(response) == {"jsonrpc", "id", "result"}
    result = response["result"]
    assert set(result) == {"content", "structuredContent", "isError"}
    assert result["content"] == [
        {
            "type": "text",
            "text": canonical_json(result["structuredContent"]),
        }
    ]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert result["isError"] is (result["structuredContent"]["ok"] is False)
    return result


def startup_and_platform(library: Path, temp_root: Path) -> None:
    assert library.is_absolute() and library.is_file()
    module = json.loads(
        (REPO_ROOT / "apps/core-mcp/module.json").read_text(encoding="utf-8")
    )
    assert module == {
        "contract": "lmdj.module.v1",
        "module": "core-mcp",
        "version": "1.1.14",
        "api_version": 2,
        "dependencies": {"application-facade": "1.4.5"},
    }
    pyproject = tomllib.loads(
        (REPO_ROOT / "apps/core-mcp/pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    assert pyproject["project"]["name"] == "lmdj-core-mcp"
    assert pyproject["project"]["version"] == "1.1.14"
    assert __version__ == "1.1.14"
    assert pyproject["project"]["dependencies"] == []
    assert pyproject["tool"]["lmdj"]["c-abi"] == "lmdj_core_c@1"
    host_paths = sorted(
        (REPO_ROOT / "apps/core-mcp/lmdj_core_mcp").glob("*.py")
    )
    host_source = "\n".join(
        path.read_text(encoding="utf-8") for path in host_paths
    )
    for path in host_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", maxsplit=1)[0]
                    for alias in node.names
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
            ):
                imported_roots.add(node.module.split(".", maxsplit=1)[0])
        assert imported_roots <= sys.stdlib_module_names, (
            path,
            imported_roots - sys.stdlib_module_names,
        )
    for forbidden in (
        "manifest.json",
        "project_io",
        "history/checkpoints",
        "history/transactions",
        "recovery/active",
    ):
        assert forbidden not in host_source
    version = json.loads(
        (REPO_ROOT / "products/lmdj/version.json").read_text(encoding="utf-8")
    )
    # Shape and types, not a duplicated copy of the current identity.
    assert set(version) == {
        "contract", "product", "milestone", "minor", "build", "patch",
    }
    assert version["contract"] == "lmdj.product-version.v1"
    assert version["product"] == "lmdj"
    assert all(
        isinstance(version[part], int) and version[part] >= 0
        for part in ("milestone", "minor", "build", "patch")
    )

    workspace = temp_root / "workspace"
    workspace.mkdir()
    missing = temp_root / f"missing{library.suffix}"
    env = host_environment()
    failed = subprocess.run(
        [
            sys.executable,
            "-m",
            "lmdj_core_mcp",
            "--library",
            str(missing),
            "--workspace",
            str(workspace),
        ],
        cwd=REPO_ROOT,
        env=env,
        input=b"",
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert failed.returncode != 0
    assert failed.stdout == b""
    assert failed.stderr

    wrong = temp_root / f"not-a-library{library.suffix}"
    wrong.write_text("not a shared library", encoding="ascii")
    failed = subprocess.run(
        [
            sys.executable,
            "-m",
            "lmdj_core_mcp",
            "--library",
            str(wrong),
            "--workspace",
            str(workspace),
        ],
        cwd=REPO_ROOT,
        env=env,
        input=b"",
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert failed.returncode != 0
    assert failed.stdout == b""
    assert failed.stderr

    non_normal = workspace / ".." / "workspace"
    failed = subprocess.run(
        [
            sys.executable,
            "-m",
            "lmdj_core_mcp",
            "--library",
            str(library),
            "--workspace",
            str(non_normal),
        ],
        cwd=REPO_ROOT,
        env=env,
        input=b"",
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert failed.returncode != 0
    assert failed.stdout == b""
    assert failed.stderr

    host = MCPProcess(library, workspace)
    assert host.request("ping-new", "ping") == {
        "jsonrpc": "2.0",
        "id": "ping-new",
        "result": {},
    }
    code, stdout, stderr = host.close()
    assert (code, stdout, stderr) == (0, b"", b"")

    empty_eof = MCPProcess(library, workspace)
    assert empty_eof.close() == (0, b"", b"")

    assembly = (REPO_ROOT / "products/lmdj/assembly.json").resolve()
    assembled_workspace = temp_root / "assembled-workspace"
    assembled_workspace.mkdir()
    assembled = MCPProcess(
        library,
        assembled_workspace,
        assembly=assembly,
    )
    assembled.initialize()
    result = assert_tool_result(
        assembled.tool_call(2, "lmdj.provider.list", {}),
        2,
    )["structuredContent"]["result"]
    assert [provider["id"] for provider in result["providers"]] == [
        "local.proof.failure",
        "local.proof.success",
    ]
    assert assembled.close() == (0, b"", b"")


def lifecycle(library: Path, temp_root: Path) -> None:
    workspace = temp_root / "lifecycle-workspace"
    workspace.mkdir()
    host = MCPProcess(library, workspace)
    assert host.request(0, "ping")["result"] == {}
    assert_error(
        host.request(2, "tools/list"),
        2,
        -32002,
        "Server not initialized",
    )
    initialized = host.request(
        3,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "client", "version": "1"},
        },
    )
    assert initialized == {
        "jsonrpc": "2.0",
        "id": 3,
        "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "lmdj-core-mcp", "version": "1.1.14"},
        },
    }
    assert host.request(4, "ping")["result"] == {}
    assert_error(
        host.request(
            5,
            "tools/call",
            {"name": "lmdj.provider.list", "arguments": {}},
        ),
        5,
        -32002,
        "Server not initialized",
    )
    assert_error(
        host.request(51, "tools/list", {"unexpected": True}),
        51,
        -32602,
        "Invalid params",
    )
    assert_error(
        host.request(52, "tools/call", {}),
        52,
        -32602,
        "Invalid params",
    )
    assert_error(
        host.request(
            6,
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "client", "version": "1"},
            },
        ),
        6,
        -32600,
        "Invalid Request",
    )
    host.send(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    host.assert_silent()
    assert host.request(7, "tools/list")["result"]["tools"]
    assert_error(
        host.request(
            8,
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "client", "version": "1"},
            },
        ),
        8,
        -32600,
        "Invalid Request",
    )
    assert host.close() == (0, b"", b"")

    premature = MCPProcess(library, workspace)
    premature.send(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    premature.assert_silent()
    assert_error(
        premature.request(1, "tools/list"),
        1,
        -32002,
        "Server not initialized",
    )
    premature.send(
        {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "client", "version": "1"},
            },
        }
    )
    premature.assert_silent()
    assert_error(
        premature.request(2, "tools/list"),
        2,
        -32002,
        "Server not initialized",
    )
    assert premature.close() == (0, b"", b"")

    metadata = MCPProcess(library, workspace)
    initialized = metadata.request(
        "metadata-init",
        "initialize",
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": "client",
                "title": "Human-readable client",
                "version": "1",
                "description": "MCP compatibility fixture",
                "websiteUrl": "https://example.invalid/client",
                "icons": [
                    {
                        "src": "data:image/png;base64,AA==",
                        "mimeType": "image/png",
                        "sizes": ["48x48"],
                        "theme": "dark",
                    }
                ],
            },
            "_meta": {"com.example/trace": "initialize"},
        },
    )
    assert initialized["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert metadata.request(
        "metadata-ping",
        "ping",
        {"_meta": {"com.example/trace": "ping"}},
    )["result"] == {}
    metadata.send(
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {"_meta": {"com.example/trace": "ready"}},
        }
    )
    metadata.assert_silent()
    assert metadata.request(
        "metadata-list",
        "tools/list",
        {"_meta": {"com.example/trace": "list"}},
    )["result"]["tools"]
    assert_tool_result(
        metadata.request(
            "metadata-call",
            "tools/call",
            {
                "name": "lmdj.provider.list",
                "arguments": {},
                "_meta": {"com.example/trace": "call"},
            },
        ),
        "metadata-call",
    )
    assert metadata.close() == (0, b"", b"")

    invalid_metadata = MCPProcess(library, workspace)
    for identifier, params in (
        (
            "bad-meta",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "client", "version": "1"},
                "_meta": [],
            },
        ),
        (
            "bad-client",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "client",
                    "version": "1",
                    "icons": [{"src": "data:image/png;base64,AA==", "theme": {}}],
                },
            },
        ),
    ):
        assert_error(
            invalid_metadata.request(identifier, "initialize", params),
            identifier,
            -32602,
            "Invalid params",
        )
    assert_error(
        invalid_metadata.request("bad-ping-meta", "ping", {"_meta": []}),
        "bad-ping-meta",
        -32602,
        "Invalid params",
    )
    assert invalid_metadata.close() == (0, b"", b"")


def request_shape(library: Path, temp_root: Path) -> None:
    workspace = temp_root / "shape-workspace"
    workspace.mkdir()
    host = MCPProcess(library, workspace)
    for identifier in ("text", 0, -7):
        assert_error(
            host.request(identifier, "unknown"),
            identifier,
            -32601,
            "Method not found",
        )
    for identifier in (None, True, False, 1.5, {}, []):
        host.send(
            {
                "jsonrpc": "2.0",
                "id": identifier,
                "method": "ping",
            }
        )
        assert_error(host.receive(), None, -32600, "Invalid Request")
    for malformed in (
        {"id": 1, "method": "ping"},
        {"jsonrpc": "1.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "id": 3},
        {"jsonrpc": "2.0", "id": 4, "method": 9},
        {"jsonrpc": "2.0", "id": 5, "method": "ping", "params": []},
    ):
        host.send(malformed)
        assert_error(
            host.receive(),
            malformed["id"],
            -32600,
            "Invalid Request",
        )
    host.send({"method": "ping"})
    host.assert_silent()
    assert host.request(6, "ping")["result"] == {}
    assert host.close() == (0, b"", b"")


def parse_and_batch(library: Path, temp_root: Path) -> None:
    workspace = temp_root / "parse-workspace"
    workspace.mkdir()
    host = MCPProcess(library, workspace)
    for raw in (
        b"\xff\n",
        b"{\n",
        (
            b'{"id":1,"jsonrpc":"2.0","method":"ping",'
            b'"params":{"value":NaN}}\n'
        ),
        b"[" * 500_000 + b"0" + b"]" * 500_000 + b"\n",
    ):
        host.send_raw(raw)
        assert_error(host.receive(), None, -32700, "Parse error")
    host.send_raw(
        b'{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}\n'
    )
    assert_error(host.receive(), None, -32600, "Invalid Request")
    assert host.request("surrogate-contained", "ping")["result"] == {}
    host.send_raw(
        b'{"jsonrpc":"2.0","method":"\\ud800"}\n'
    )
    host.assert_silent()
    assert host.request("surrogate-notification-contained", "ping")[
        "result"
    ] == {}
    for value in ([], 1, "value"):
        host.send(value)
        assert_error(host.receive(), None, -32600, "Invalid Request")
    project = temp_root / "batch-project.lmdj"
    host.send(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "lmdj.project.create",
                    "arguments": {
                        "project_path": str(project),
                        "project_id": "00000000-0000-4000-8000-000000000001",
                        "bpm": 120,
                    },
                },
            }
        ]
    )
    assert_error(host.receive(), None, -32600, "Invalid Request")
    assert not project.exists()
    assert host.close() == (0, b"", b"")


def method_and_notification(library: Path, temp_root: Path) -> None:
    workspace = temp_root / "method-workspace"
    workspace.mkdir()
    host = MCPProcess(library, workspace)
    assert_error(
        host.request("unknown", "not/a/method"),
        "unknown",
        -32601,
        "Method not found",
    )
    assert_error(
        host.request("bad-ping", "ping", {"unexpected": True}),
        "bad-ping",
        -32602,
        "Invalid params",
    )
    host.send(
        {
            "jsonrpc": "2.0",
            "method": "not/a/method",
            "params": {"anything": True},
        }
    )
    host.assert_silent()
    host.send(
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": [],
        }
    )
    host.assert_silent()
    assert host.request("alive", "ping")["result"] == {}
    assert host.close() == (0, b"", b"")


def tools_list(library: Path, temp_root: Path) -> None:
    workspace = temp_root / "list-workspace"
    workspace.mkdir()
    host = MCPProcess(library, workspace)
    initialized = host.initialize()
    assert initialized["result"]["capabilities"] == {
        "tools": {"listChanged": False}
    }
    response = host.request("list", "tools/list")
    assert set(response) == {"jsonrpc", "id", "result"}
    assert set(response["result"]) == {"tools"}
    tools = response["result"]["tools"]
    schemas = expected_schemas()
    expected_routes = (
        ("lmdj.project.create", "project.create", "command"),
        ("lmdj.project.inspect", "project.inspect", "query"),
        ("lmdj.sample.inspect", "sample.inspect", "query"),
        ("lmdj.sample.waveform", "sample.waveform", "query"),
        ("lmdj.sample.import.begin", "sample.import.begin", "command"),
        ("lmdj.sample.import.chunk", "sample.import.chunk", "command"),
        ("lmdj.sample.import.commit", "sample.import.commit", "command"),
        ("lmdj.sample.import.abort", "sample.import.abort", "command"),
        ("lmdj.sample.update_pad", "sample.update_pad", "command"),
        ("lmdj.sample.reset_pad", "sample.reset_pad", "command"),
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
    assert tuple(
        (tool.name, tool.operation, tool.surface) for tool in server.TOOLS
    ) == expected_routes
    assert [tool["name"] for tool in tools] == list(schemas)
    output_schema = expected_output_schema()
    for tool in tools:
        assert set(tool) == {"name", "inputSchema", "outputSchema"}
        assert tool["inputSchema"] == schemas[tool["name"]]
        assert tool["outputSchema"] == output_schema
        assert "operation" not in canonical_json(tool["inputSchema"])
    assert host.close() == (0, b"", b"")


def valid_arguments(temp_root: Path) -> dict[str, dict]:
    missing_project = temp_root / "missing.lmdj"
    uuid = "00000000-0000-4000-8000-000000000001"
    slot = {"bank": 0, "pad": 0}
    pattern = {"pattern_id": uuid, "bars": 1, "events": []}
    playback = {
        "trim_start_frame": 0,
        "trim_end_frame": None,
        "trigger_mode": "one_shot",
        "gain_millidb": 0,
        "muted": False,
    }
    return {
        "lmdj.project.create": {
            "project_path": str(temp_root / "route-create.lmdj"),
            "project_id": uuid,
            "bpm": 120,
        },
        "lmdj.project.inspect": {"project_path": str(missing_project)},
        "lmdj.sample.inspect": {
            "project_path": str(missing_project),
            "slot": slot,
        },
        "lmdj.sample.waveform": {
            "project_path": str(missing_project),
            "slot": slot,
            "window": {
                "start_frame": 0,
                "end_frame": 1,
                "bucket_count": 1,
            },
        },
        "lmdj.sample.import.begin": {
            "import_token": uuid,
            "project_path": str(missing_project),
            "command_id": uuid,
            "expected_revision": 0,
            "slot": slot,
            "asset_id": uuid,
            "byte_length": 44,
        },
        "lmdj.sample.import.chunk": {
            "import_token": uuid,
            "offset": 0,
            "final": True,
            "sidecar": {
                "sidecar_bytes": 44,
                "sidecar_sha256": "0" * 64,
            },
        },
        "lmdj.sample.import.commit": {"import_token": uuid},
        "lmdj.sample.import.abort": {"import_token": uuid},
        "lmdj.sample.update_pad": {
            "project_path": str(missing_project),
            "command_id": uuid,
            "expected_revision": 0,
            "slot": slot,
            "playback": playback,
        },
        "lmdj.sample.reset_pad": {
            "project_path": str(missing_project),
            "command_id": uuid,
            "expected_revision": 0,
            "slot": slot,
        },
        "lmdj.asset.import": {
            "project_path": str(missing_project),
            "command_id": uuid,
            "expected_revision": 0,
            "asset_id": uuid,
            "source_path": str(temp_root / "missing.wav"),
            "media_type": "audio/wav",
        },
        "lmdj.pad.assign": {
            "project_path": str(missing_project),
            "command_id": uuid,
            "expected_revision": 0,
            "slot": slot,
            "asset_id": None,
        },
        "lmdj.take.begin": {
            "project_path": str(missing_project),
            "take_id": uuid,
            "expected_revision": 0,
            "sample_rate": 48000,
        },
        "lmdj.take.append": {
            "project_path": str(missing_project),
            "take_id": uuid,
            "event": {
                "slot": slot,
                "frame_offset": 0,
                "velocity": 127,
            },
        },
        "lmdj.take.commit": {
            "project_path": str(missing_project),
            "command_id": uuid,
            "expected_revision": 0,
            "take_id": uuid,
            "pattern": pattern,
        },
        "lmdj.snapshot.cook": {
            "project_path": str(missing_project),
            "pattern_id": uuid,
        },
        "lmdj.render.offline": {
            "project_path": str(missing_project),
            "pattern_id": uuid,
            "output_path": str(temp_root / "missing-render.wav"),
        },
        "lmdj.provider.list": {},
        "lmdj.provider.select": {
            "capability": "proof.candidate.v2",
            "provider_id": "provider",
        },
        "lmdj.provider.run": {
            "attempt_id": "attempt-1",
            "capability": "proof.candidate.v2",
            "inputs": [],
            "parameters": {},
            "data_classification": "local",
            "platform": "macos",
            "region": "local",
            "required_permissions": [],
        },
        "lmdj.attempt.inspect": {"attempt_id": "attempt-1"},
    }


def tools_call_validation(library: Path, temp_root: Path) -> None:
    workspace = temp_root / "call-workspace"
    workspace.mkdir()
    host = MCPProcess(library, workspace)
    host.initialize()
    for index, (name, arguments) in enumerate(
        valid_arguments(temp_root).items(),
        start=10,
    ):
        result = assert_tool_result(
            host.tool_call(index, name, arguments),
            index,
        )
        assert isinstance(result["structuredContent"]["ok"], bool)
    assert_error(
        host.tool_call(
            30,
            "lmdj.provider.list",
            {"operation": "provider.run"},
        ),
        30,
        -32602,
        "Invalid params",
    )
    assert_error(
        host.tool_call(31, "lmdj.unknown", {}),
        31,
        -32602,
        "Invalid params",
    )
    assert_error(
        host.tool_call(
            32,
            "lmdj.project.inspect",
            {},
            omit_arguments=True,
        ),
        32,
        -32602,
        "Invalid params",
    )
    assert_tool_result(
        host.tool_call(
            33,
            "lmdj.provider.list",
            omit_arguments=True,
        ),
        33,
    )
    assert_error(
        host.request(
            34,
            "tools/call",
            {
                "name": "lmdj.provider.list",
                "arguments": {},
                "operation": "provider.run",
            },
        ),
        34,
        -32602,
        "Invalid params",
    )
    assert_error(
        host.request(
            35,
            "tools/call",
            {
                "name": "lmdj.provider.list",
                "arguments": {},
                "_meta": [],
            },
        ),
        35,
        -32602,
        "Invalid params",
    )
    assert_error(
        host.request(36, "tools/list", {"_meta": []}),
        36,
        -32602,
        "Invalid params",
    )
    flat_provider_arguments = valid_arguments(temp_root)[
        "lmdj.provider.run"
    ]
    flat_provider_arguments["inputs"] = [
        {
            "sha256": "a" * 64,
            "media_type": "application/octet-stream",
            "byte_length": 1,
        }
    ]
    assert_error(
        host.tool_call(
            37,
            "lmdj.provider.run",
            flat_provider_arguments,
        ),
        37,
        -32602,
        "Invalid params",
    )
    sample_chunk = valid_arguments(temp_root)["lmdj.sample.import.chunk"]
    assert_error(
        host.tool_call(
            38,
            "lmdj.sample.import.chunk",
            {**sample_chunk, "bytes": [1, 2, 3]},
        ),
        38,
        -32602,
        "Invalid params",
    )
    oversized_chunk = {
        **sample_chunk,
        "sidecar": {
            **sample_chunk["sidecar"],
            "sidecar_bytes": 1_048_577,
        },
    }
    assert_error(
        host.tool_call(39, "lmdj.sample.import.chunk", oversized_chunk),
        39,
        -32602,
        "Invalid params",
    )
    sample_inspect = valid_arguments(temp_root)["lmdj.sample.inspect"]
    assert_error(
        host.tool_call(
            40,
            "lmdj.sample.inspect",
            {**sample_inspect, "filename": "private.wav"},
        ),
        40,
        -32602,
        "Invalid params",
    )
    assert host.close() == (0, b"", b"")


class FakeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *arguments):
        return self.callback(*arguments)


class FakeLibrary:
    def __init__(self) -> None:
        self.buffers: list[ctypes.Array] = []
        self.string_frees = 0
        self.engine_frees = 0
        self.invoke_status = 0
        self.create_status = 0
        self.create_error_bytes: bytes | None = None
        self.create_raises = False
        self.response_bytes = (
            b'{"ok":true,"project_revision":null,'
            b'"result":{"providers":[]}}'
        )
        self.lmdj_engine_create = FakeFunction(self._create)
        self.lmdj_engine_command = FakeFunction(self._invoke)
        self.lmdj_engine_query = FakeFunction(self._invoke)
        self.lmdj_string_free = FakeFunction(self._string_free)
        self.lmdj_engine_free = FakeFunction(self._engine_free)

    @staticmethod
    def _set_pointer(target, value: int | None) -> None:
        ctypes.cast(target, ctypes.POINTER(ctypes.c_void_p))[0] = (
            ctypes.c_void_p(value)
        )

    def _create(self, _config, out_engine, out_error) -> int:
        self._set_pointer(out_engine, 123)
        if self.create_error_bytes is None:
            self._set_pointer(out_error, None)
        else:
            buffer = ctypes.create_string_buffer(self.create_error_bytes)
            self.buffers.append(buffer)
            self._set_pointer(out_error, ctypes.addressof(buffer))
        if self.create_raises:
            raise RuntimeError("injected create failure")
        return self.create_status

    def _invoke(self, _engine, _request, out_response) -> int:
        buffer = ctypes.create_string_buffer(self.response_bytes)
        self.buffers.append(buffer)
        self._set_pointer(out_response, ctypes.addressof(buffer))
        return self.invoke_status

    def _string_free(self, _pointer) -> None:
        self.string_frees += 1

    def _engine_free(self, _engine) -> None:
        self.engine_frees += 1


def result_contract(library: Path, temp_root: Path) -> None:
    workspace = temp_root / "result-workspace"
    workspace.mkdir()
    host = MCPProcess(library, workspace)
    host.initialize()
    success = assert_tool_result(
        host.tool_call(1, "lmdj.provider.list", {}),
        1,
    )
    assert success["isError"] is False
    assert success["structuredContent"] == {
        "ok": True,
        "result": {"providers": []},
        "project_revision": None,
    }
    failure = assert_tool_result(
        host.tool_call(
            2,
            "lmdj.project.inspect",
            {"project_path": str(temp_root / "not-there.lmdj")},
        ),
        2,
    )
    assert failure["isError"] is True
    assert set(failure["structuredContent"]) == {"ok", "error"}
    assert host.close() == (0, b"", b"")
    assert not server.facade_envelope(
        {
            "ok": 1,
            "result": {},
            "project_revision": None,
        }
    )
    assert not server.validates(
        {"type": "object", "oneOf": [{}]},
        [],
    )

    class FailingEngine:
        @staticmethod
        def command(_request):
            raise c_api.CApiError("injected")

        @staticmethod
        def query(_request):
            raise c_api.CApiError("injected")

    contained = server.Server(FailingEngine())
    initialize = canonical_json(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
    ).encode("utf-8")
    assert contained.handle(initialize)["result"]["protocolVersion"] == (
        PROTOCOL_VERSION
    )
    contained.handle(
        canonical_json(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        ).encode("utf-8")
    )
    internal = contained.handle(
        canonical_json(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "lmdj.provider.list",
                    "arguments": {},
                },
            }
        ).encode("utf-8")
    )
    assert_error(internal, 2, -32603, "Internal error")

    fake = FakeLibrary()
    original_cdll = c_api.ctypes.CDLL
    c_api.ctypes.CDLL = lambda _path: fake
    try:
        engine = c_api.Engine(library, workspace)
        assert engine.query({"operation": "provider.list"})["ok"] is True
        engine.close()
        engine.close()
        assert fake.string_frees == 1
        assert fake.engine_frees == 1

        mismatch = FakeLibrary()
        mismatch.invoke_status = 2
        c_api.ctypes.CDLL = lambda _path: mismatch
        engine = c_api.Engine(library, workspace)
        try:
            engine.query({"operation": "provider.list"})
            raise AssertionError("status/pointer mismatch was accepted")
        except c_api.CApiError:
            pass
        finally:
            engine.close()
        assert mismatch.string_frees == 1
        assert mismatch.engine_frees == 1

        invalid = FakeLibrary()
        invalid.response_bytes = b"\xff"
        c_api.ctypes.CDLL = lambda _path: invalid
        engine = c_api.Engine(library, workspace)
        try:
            engine.command({"operation": "provider.list"})
            raise AssertionError("invalid UTF-8 C response was accepted")
        except c_api.CApiError:
            pass
        finally:
            engine.close()
        assert invalid.string_frees == 1
        assert invalid.engine_frees == 1

        invalid_scalar = FakeLibrary()
        invalid_scalar.response_bytes = (
            b'{"error":{"code":"INTERNAL_ERROR","details":{},'
            b'"message":"\\ud800"},"ok":false}'
        )
        c_api.ctypes.CDLL = lambda _path: invalid_scalar
        engine = c_api.Engine(library, workspace)
        try:
            engine.query({"operation": "provider.list"})
            raise AssertionError("invalid Unicode scalar response was accepted")
        except c_api.CApiError:
            pass
        finally:
            engine.close()
        assert invalid_scalar.string_frees == 1
        assert invalid_scalar.engine_frees == 1

        raising = FakeLibrary()
        raising.create_error_bytes = b'{"error":"injected"}'
        raising.create_raises = True
        c_api.ctypes.CDLL = lambda _path: raising
        try:
            c_api.Engine(library, workspace)
            raise AssertionError("create exception was accepted")
        except c_api.CApiError:
            pass
        assert raising.string_frees == 1
        assert raising.engine_frees == 1
    finally:
        c_api.ctypes.CDLL = original_cdll


def bounded_transport(library: Path, temp_root: Path) -> None:
    workspace = temp_root / "bounded-workspace"
    workspace.mkdir()
    host = MCPProcess(library, workspace)
    ping = canonical_json(
        {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    ).encode("utf-8")
    host.send_raw(ping + b" " * (REQUEST_LIMIT - len(ping)) + b"\n")
    assert host.receive()["result"] == {}
    host.send_raw(
        ping + b" " * (REQUEST_LIMIT + 1 - len(ping)) + b"\n"
    )
    assert_error(host.receive(), None, -32600, "Invalid Request")
    assert host.request(2, "ping")["result"] == {}
    assert host.close() == (0, b"", b"")

    class CountingEngine:
        def __init__(self) -> None:
            self.calls = 0

        def command(self, _request):
            self.calls += 1
            raise AssertionError("oversized input reached C command dispatch")

        def query(self, _request):
            self.calls += 1
            raise AssertionError("oversized input reached C query dispatch")

    counting = CountingEngine()
    contained = server.Server(counting)
    assert_error(
        contained.handle(server.OversizedLine()),
        None,
        -32600,
        "Invalid Request",
    )
    assert counting.calls == 0

    unterminated = MCPProcess(library, workspace)
    unterminated.send_raw(ping)
    assert unterminated.process.stdin is not None
    unterminated.process.stdin.close()
    unterminated.process.stdin = None
    stdout, stderr = communicate_with_timeout(unterminated.process)
    assert unterminated.process.returncode == 0
    assert stderr == b""
    assert_error(
        json.loads(stdout.decode("utf-8")),
        None,
        -32600,
        "Invalid Request",
    )


def stdout_purity_and_shutdown(library: Path, temp_root: Path) -> None:
    workspace = temp_root / "purity-workspace"
    workspace.mkdir()
    host = MCPProcess(library, workspace)
    host.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    line = host.receive_raw()
    parsed = json.loads(line)
    assert line == canonical_json(parsed).encode("utf-8") + b"\n"
    assert host.close() == (0, b"", b"")

    read_fd, write_fd = os.pipe()
    broken = MCPProcess(library, workspace, stdout=write_fd)
    os.close(write_fd)
    os.close(read_fd)
    try:
        broken.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    except BrokenPipeError:
        pass
    assert broken.process.stdin is not None
    try:
        broken.process.stdin.close()
    except BrokenPipeError:
        pass
    broken.process.stdin = None
    _, stderr = communicate_with_timeout(broken.process)
    assert b"Traceback" not in stderr


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: mcp_stdio_test.py /absolute/path/to/lmdj-core-c"
        )
    library = Path(sys.argv[1]).expanduser()
    assert library.is_absolute()
    library = library.resolve(strict=True)
    expected_suffixes = {".dylib", ".so"}
    assert library.suffix in expected_suffixes, library
    if "asan" in library.parts:
        sanitizer_runtime = os.environ.get("LMDJ_ASAN_RUNTIME", "")
        assert sanitizer_runtime
        assert "asan" in sanitizer_runtime.lower()
        if sys.platform == "darwin":
            assert "verify_interceptors=0" in os.environ.get(
                "ASAN_OPTIONS",
                "",
            )
        elif sys.platform.startswith("linux"):
            assert "detect_leaks=0" in os.environ.get(
                "ASAN_OPTIONS",
                "",
            ).split(":")

    fixtures = (
        startup_and_platform,
        lifecycle,
        request_shape,
        parse_and_batch,
        method_and_notification,
        tools_list,
        tools_call_validation,
        result_contract,
        bounded_transport,
        stdout_purity_and_shutdown,
    )
    with tempfile.TemporaryDirectory(prefix="lmdj-mcp-stdio-") as temp:
        temp_root = Path(temp).resolve()
        for fixture in fixtures:
            fixture(library, temp_root)
    assert len(fixtures) == 10
    print("mcp stdio fixtures: 10 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
