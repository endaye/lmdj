"""Project the LMDJ MCP tool table onto a surface a 45M model can answer for.

The MCP schemas mix two kinds of parameter:

* **Host-owned plumbing** - `project_path`, `command_id` (a fresh UUID per
  command), `expected_revision` (optimistic-concurrency token), `runtime_frame`,
  and the session handles `session_id` / `import_token` / `attempt_id`. None of
  these are in an utterance, and a small model asked to invent a UUID will
  hallucinate one that fails the schema pattern.
* **Entity references** - any field whose schema is a UUID string, such as
  `pattern_id` or `asset_id`. A person says "the drum loop", not a UUID, so
  resolving a name to an identifier is the Host's job. Leaving these on the
  model's surface costs context and buys only hallucinated identifiers.
* **Authoring payloads** - optional nested objects like `initial_pattern`, a
  whole pattern of tick-accurate events. A one-line utterance cannot specify
  one, and each is optional in production, so omitting it is legal.
* **Intent parameters** - `bpm`, `slot`, `bars`, `swing_percent`, `playback`
  and friends. These are the only fields a person actually says out loud.

The spike therefore hides the first three kinds from the model, lets Needle fill
only the intent fields, then composes the halves back into a payload that is
validated against the unmodified production schema.

Hiding them is not only a correctness choice. The engine has a fixed context
budget, and the production schemas are verbose: every hidden UUID field is a
~90-character regex that would otherwise crowd out a real tool.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
MCP_PACKAGE_ROOT = REPO_ROOT / "apps" / "core-mcp"

# Injected by the Host before dispatch, never by the model.
HOST_OWNED_PARAMETERS = frozenset(
    {
        "project_path",
        "command_id",
        "expected_revision",
        "runtime_frame",
        "session_id",
        "import_token",
        "attempt_id",
    }
)

#: Recognises the UUID pattern the MCP schemas use for every entity identifier.
_UUID_PATTERN_MARKER = re.compile(r"\[0-9a-f\]\{8\}")


#: Optional authoring payloads that a one-line utterance cannot specify - whole
#: patterns of tick-accurate events, byte sidecars, provider input sets. A Host
#: composes these from a separate flow; showing them to the model only burns
#: context. Each is optional in its production schema, so omitting them is legal.
MODEL_EXCLUDED_PARAMETERS = frozenset(
    {
        "initial_pattern",
        "sidecar",
        "event",
        "inputs",
        "parameters",
        "required_permissions",
    }
)


def is_entity_reference(schema: dict) -> bool:
    """Whether a property schema is a UUID identifier (possibly nullable)."""
    if not isinstance(schema, dict):
        return False
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and _UUID_PATTERN_MARKER.search(pattern):
        return True
    return any(is_entity_reference(branch) for branch in schema.get("oneOf", []))

# The subset a performance-facing assistant would expose. Byte-level import
# chunking, recovery plumbing and raw provider dispatch are host workflows with
# no natural-language phrasing, so they only appear on the "full" surface.
PERFORMANCE_SURFACE = (
    "lmdj.project.create",
    "lmdj.project.inspect",
    "lmdj.sample.inspect",
    "lmdj.sample.update_pad",
    "lmdj.sample.reset_pad",
    "lmdj.pad.assign",
    "lmdj.pattern.create",
    "lmdj.sequence.record.begin",
    "lmdj.sequence.record.stop",
    "lmdj.sequence.record.status",
    "lmdj.sequence.settings.update",
    "lmdj.snapshot.cook",
    "lmdj.render.offline",
    "lmdj.provider.list",
    "lmdj.provider.select",
)

# Verb-shaped names for the model to route on. The MCP wire identifiers are
# dotted namespaces (`lmdj.sequence.settings.update`), which read as paths
# rather than actions; measured against these aliases they cost 13-22 points of
# routing accuracy. The wire name stays authoritative - this is a display layer
# the adapter maps back before anything is dispatched.
MODEL_TOOL_NAMES = {
    "lmdj.project.create": "create_project",
    "lmdj.project.inspect": "inspect_project",
    "lmdj.sample.inspect": "inspect_pad",
    "lmdj.sample.quota": "check_storage_quota",
    "lmdj.sample.waveform": "read_pad_waveform",
    "lmdj.sample.import.begin": "begin_sample_import",
    "lmdj.sample.import.chunk": "upload_sample_chunk",
    "lmdj.sample.import.commit": "finish_sample_import",
    "lmdj.sample.import.abort": "cancel_sample_import",
    "lmdj.sample.update_pad": "set_pad_playback",
    "lmdj.sample.reset_pad": "reset_pad",
    "lmdj.asset.import": "import_audio_file",
    "lmdj.pad.assign": "assign_pad",
    "lmdj.pattern.create": "create_pattern",
    "lmdj.sequence.record.begin": "start_recording",
    "lmdj.sequence.record.event": "record_pad_hit",
    "lmdj.sequence.record.flush": "flush_recording",
    "lmdj.sequence.record.stop": "stop_recording",
    "lmdj.sequence.record.switch-request": "queue_pattern_switch",
    "lmdj.sequence.record.status": "recording_status",
    "lmdj.sequence.settings.update": "set_tempo_and_groove",
    "lmdj.sequence.recovery.list": "list_recoverable_takes",
    "lmdj.sequence.recovery.apply": "restore_take",
    "lmdj.sequence.recovery.discard": "discard_take",
    "lmdj.snapshot.cook": "cook_snapshot",
    "lmdj.render.offline": "render_to_file",
    "lmdj.provider.list": "list_providers",
    "lmdj.provider.select": "select_provider",
    "lmdj.provider.run": "run_provider",
    "lmdj.attempt.inspect": "inspect_attempt",
}

# One line per tool. The MCP table carries no prose, and a 45M model routes on
# wording alone, so the spike supplies its own descriptions rather than letting
# the tool name carry the whole signal.
TOOL_DESCRIPTIONS = {
    "lmdj.project.create": "Create a new project at a tempo.",
    "lmdj.project.inspect": "Read the current project state.",
    "lmdj.sample.inspect": "Read the sample loaded on one pad.",
    "lmdj.sample.quota": "Read remaining sample storage quota.",
    "lmdj.sample.waveform": "Read waveform peaks for one pad.",
    "lmdj.sample.import.begin": "Start a chunked sample import.",
    "lmdj.sample.import.chunk": "Upload one chunk of a sample import.",
    "lmdj.sample.import.commit": "Finish a chunked sample import.",
    "lmdj.sample.import.abort": "Cancel a chunked sample import.",
    "lmdj.sample.update_pad": "Change how a pad plays back: gain, mute, trigger mode, trim.",
    "lmdj.sample.reset_pad": "Reset one pad's playback settings to defaults.",
    "lmdj.asset.import": "Import an audio file from disk as an asset.",
    "lmdj.pad.assign": "Put an asset onto a pad slot.",
    "lmdj.pattern.create": "Create a new pattern of a given length in bars.",
    "lmdj.sequence.record.begin": "Start recording a performance into a pattern.",
    "lmdj.sequence.record.event": "Record one pad hit into the take.",
    "lmdj.sequence.record.flush": "Flush buffered recorded events.",
    "lmdj.sequence.record.stop": "Stop recording the current take.",
    "lmdj.sequence.record.switch-request": "Queue a pattern switch while recording.",
    "lmdj.sequence.record.status": "Read whether recording is running.",
    "lmdj.sequence.settings.update": "Change tempo, quantize or swing.",
    "lmdj.sequence.recovery.list": "List recoverable unfinished takes.",
    "lmdj.sequence.recovery.apply": "Restore a recovered take into a pattern.",
    "lmdj.sequence.recovery.discard": "Throw away a recovered take.",
    "lmdj.snapshot.cook": "Build the runtime snapshot for a pattern.",
    "lmdj.render.offline": "Bounce a pattern to an audio file.",
    "lmdj.provider.list": "List available providers.",
    "lmdj.provider.select": "Choose which provider serves a capability.",
    "lmdj.provider.run": "Run a provider capability.",
    "lmdj.attempt.inspect": "Read the result of a provider attempt.",
}


class ToolSurfaceError(RuntimeError):
    """The MCP tool table could not be read."""


def _load_mcp_server() -> Any:
    if not MCP_PACKAGE_ROOT.is_dir():
        raise ToolSurfaceError(f"apps/core-mcp not found at {MCP_PACKAGE_ROOT}")
    if str(MCP_PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(MCP_PACKAGE_ROOT))
    try:
        from lmdj_core_mcp import server
    except ImportError as error:  # pragma: no cover - environment failure
        raise ToolSurfaceError(f"cannot import lmdj_core_mcp.server: {error}") from error
    return server


#: Imported once; `server.TOOLS` is a frozen table with no engine dependency.
SERVER = _load_mcp_server()

#: LMDJ's own validator, reused verbatim so the spike measures conformance to
#: the production contract rather than to a second implementation of it.
validates = SERVER.validates


@dataclass(frozen=True)
class SpikeTool:
    """One MCP tool split into the half the model fills and the half the Host does."""

    name: str
    surface: str
    production_schema: dict
    model_schema: dict
    host_parameters: tuple[str, ...]
    reference_parameters: tuple[str, ...]

    def model_name(self, naming: str = "verb") -> str:
        """The name the model sees. `naming` is "verb" or "mcp"."""
        if naming == "mcp":
            return self.name
        if naming == "verb":
            return MODEL_TOOL_NAMES.get(self.name, self.name)
        raise ValueError(f"unknown naming: {naming!r} (expected verb or mcp)")

    def needle_tool(self, naming: str = "verb") -> dict:
        """The schema handed to Needle, in the engine's tool format."""
        return {
            "name": self.model_name(naming),
            "description": TOOL_DESCRIPTIONS.get(self.name, self.name),
            "parameters": self.model_schema,
        }


def _strip_nested_references(schema: dict) -> None:
    """Drop UUID identifiers from nested objects, in place."""
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    dropped = [key for key, member in properties.items() if is_entity_reference(member)]
    for key in dropped:
        properties.pop(key)
    if dropped:
        required = [key for key in schema.get("required", []) if key not in dropped]
        if required:
            schema["required"] = required
        else:
            schema.pop("required", None)
    for member in properties.values():
        if isinstance(member, dict):
            _strip_nested_references(member)
            items = member.get("items")
            if isinstance(items, dict):
                _strip_nested_references(items)


def _project_schema(schema: dict) -> tuple[dict, tuple[str, ...], tuple[str, ...]]:
    """Split one production schema into the model's half and the Host's half."""
    model_schema = copy.deepcopy(schema)
    properties = model_schema.get("properties", {})

    host = sorted(key for key in properties if key in HOST_OWNED_PARAMETERS)
    references = sorted(
        key
        for key, member in properties.items()
        if key not in HOST_OWNED_PARAMETERS and is_entity_reference(member)
    )
    excluded = sorted(key for key in properties if key in MODEL_EXCLUDED_PARAMETERS)

    for key in (*host, *references, *excluded):
        properties.pop(key, None)
    hidden = {*host, *references, *excluded}
    required = [key for key in model_schema.get("required", []) if key not in hidden]
    if required:
        model_schema["required"] = required
    else:
        model_schema.pop("required", None)

    _strip_nested_references(model_schema)
    return model_schema, tuple(host), tuple(references)


def build_tools(surface: str = "performance") -> tuple[SpikeTool, ...]:
    """Build the spike tool set. `surface` is "performance" or "full"."""
    if surface == "performance":
        selected = PERFORMANCE_SURFACE
    elif surface == "full":
        selected = tuple(tool.name for tool in SERVER.TOOLS)
    else:
        raise ValueError(f"unknown surface: {surface!r} (expected performance or full)")

    tools = []
    for name in selected:
        entry = SERVER.TOOLS_BY_NAME[name]
        model_schema, host_parameters, reference_parameters = _project_schema(
            entry.input_schema
        )
        tools.append(
            SpikeTool(
                name=name,
                surface=entry.surface,
                production_schema=entry.input_schema,
                model_schema=model_schema,
                host_parameters=host_parameters,
                reference_parameters=reference_parameters,
            )
        )
    return tuple(tools)


def compose(tool: SpikeTool, model_arguments: dict, host_context: dict) -> dict:
    """Merge model-filled intent with Host-owned plumbing into a real payload.

    Host values win: a model that hallucinates a `command_id` cannot smuggle it
    past the Host.
    """
    hidden = HOST_OWNED_PARAMETERS | MODEL_EXCLUDED_PARAMETERS
    payload = {
        key: value
        for key, value in model_arguments.items()
        if key not in hidden and key not in tool.reference_parameters
    }
    for key in (*tool.host_parameters, *tool.reference_parameters):
        if key in host_context:
            payload[key] = host_context[key]
    return payload


def schema_report(tool: SpikeTool, payload: dict) -> tuple[bool, tuple[str, ...]]:
    """Validate a composed payload and describe why it failed, if it did."""
    if validates(tool.production_schema, payload):
        return True, ()

    reasons = []
    properties = tool.production_schema.get("properties", {})
    for key in tool.production_schema.get("required", []):
        if key not in payload:
            reasons.append(f"missing required field: {key}")
    if tool.production_schema.get("additionalProperties") is False:
        for key in payload:
            if key not in properties:
                reasons.append(f"unknown field: {key}")
    for key, value in payload.items():
        member = properties.get(key)
        if member is not None and not validates(member, value):
            reasons.append(f"field {key} does not satisfy its schema: {value!r}")
    if not reasons:
        reasons.append("payload rejected by the production schema")
    return False, tuple(reasons)


def dump_surface(surface: str = "performance", naming: str = "verb") -> str:
    """Render the surface as JSON; useful for eyeballing what the model sees."""
    return json.dumps(
        [tool.needle_tool(naming) for tool in build_tools(surface)], indent=2
    )
