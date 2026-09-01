#!/usr/bin/env python3
"""Validate the model/Host parameter split. Runs without the engine or weights."""

from __future__ import annotations

import json
import sys
from pathlib import Path

spike_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(spike_root))

from needle_spike.tool_surface import (  # noqa: E402
    HOST_OWNED_PARAMETERS,
    MODEL_EXCLUDED_PARAMETERS,
    MODEL_TOOL_NAMES,
    PERFORMANCE_SURFACE,
    SERVER,
    build_tools,
    compose,
    is_entity_reference,
    schema_report,
)

# Every curated name must exist in the production table, or the surface is
# silently drifting away from the Core it claims to drive.
for name in PERFORMANCE_SURFACE:
    assert name in SERVER.TOOLS_BY_NAME, f"performance surface names unknown tool: {name}"

# Only the surface the spike actually drives must be fully aliased. Requiring
# an alias for all 30 MCP tools would make every new Core tool break this
# spike, and a parallel validation must not become a tax on product work -
# `model_name` degrades to the wire name for anything unaliased.
for name in PERFORMANCE_SURFACE:
    assert name in MODEL_TOOL_NAMES, f"no verb alias for {name}"

aliases = list(MODEL_TOOL_NAMES.values())
assert len(aliases) == len(set(aliases)), "verb aliases must be unique"
assert set(MODEL_TOOL_NAMES).issubset(
    set(SERVER.TOOLS_BY_NAME)
), "alias map names a tool the MCP table does not have"

performance = build_tools("performance")
full = build_tools("full")
assert len(performance) == len(PERFORMANCE_SURFACE)
assert len(full) == len(SERVER.TOOLS)

for tool in full:
    properties = tool.model_schema.get("properties", {})

    # Nothing the Host owns, and no UUID identifier, may reach the model.
    for hidden in HOST_OWNED_PARAMETERS | MODEL_EXCLUDED_PARAMETERS:
        assert hidden not in properties, f"{tool.name} still exposes {hidden}"
    for key, member in properties.items():
        assert not is_entity_reference(member), f"{tool.name}.{key} is a raw UUID field"

    # Whatever the model is still asked for must be genuinely required, not a
    # leftover from a stripped field.
    for key in tool.model_schema.get("required", []):
        assert key in properties, f"{tool.name} requires stripped field {key}"

    assert tool.production_schema is SERVER.TOOLS_BY_NAME[tool.name].input_schema
    assert tool.model_name("mcp") == tool.name
    # Unaliased tools fall back to the wire name rather than raising.
    expected_alias = MODEL_TOOL_NAMES.get(tool.name, tool.name)
    assert tool.needle_tool("verb")["name"] == expected_alias

# Deep-copied, so projecting the surface cannot mutate the MCP table in place.
assert build_tools("full")[0].production_schema == SERVER.TOOLS[0].input_schema
assert "project_path" in SERVER.TOOLS_BY_NAME["lmdj.pad.assign"].input_schema["properties"]

by_name = {tool.name: tool for tool in full}

# A model that fills only intent still produces a schema-valid command once the
# Host merges its half back in.
assign = by_name["lmdj.pad.assign"]
host_context = {
    "project_path": "/tmp/x.lmdj",
    "command_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
    "expected_revision": 3,
    "asset_id": "b7e21c48-9f30-4a6d-92c1-5e8047af3d6b",
}
payload = compose(assign, {"slot": {"bank": 1, "pad": 4}}, host_context)
valid, reasons = schema_report(assign, payload)
assert valid, reasons
assert payload["asset_id"] == host_context["asset_id"]

# A model that hallucinates Host plumbing cannot smuggle it past the Host.
hallucinated = compose(
    assign,
    {
        "slot": {"bank": 1, "pad": 4},
        "command_id": "not-a-uuid",
        "expected_revision": 999,
        "asset_id": "also-not-a-uuid",
        "project_path": "/etc/passwd",
    },
    host_context,
)
assert hallucinated == payload, "host context must win over model-supplied plumbing"

# Missing intent is reported as a schema failure with a usable reason, not a crash.
incomplete = compose(assign, {}, host_context)
valid, reasons = schema_report(assign, incomplete)
assert not valid
assert any("slot" in reason for reason in reasons), reasons

# Every tool that carries plumbing in production must hide it here.
for tool in full:
    production = set(tool.production_schema.get("properties", {}))
    expected_host = production & HOST_OWNED_PARAMETERS
    assert set(tool.host_parameters) == expected_host, tool.name

# The engine has a fixed context budget and these schemas are verbose, so the
# projection has to buy real room, not just tidy the surface up.
raw_bytes = sum(len(json.dumps(tool.production_schema)) for tool in performance)
model_bytes = sum(len(json.dumps(tool.needle_tool())) for tool in performance)
assert model_bytes < raw_bytes * 0.75, (
    f"projection saved too little context: {raw_bytes} -> {model_bytes} bytes"
)

print("needle spike tool surface tests: PASS")
