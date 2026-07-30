#!/usr/bin/env python3

import json
from pathlib import Path
import re


repo_root = Path(__file__).resolve().parents[2]
contract_root = repo_root / "contracts"

schema_paths = {
    "project": contract_root / "project" / "lmdj.project.v1.schema.json",
    "capability": (
        contract_root / "capability" / "lmdj.capability.v1.schema.json"
    ),
    "assembly": contract_root / "assembly" / "lmdj.assembly.v1.schema.json",
    "error": contract_root / "error" / "lmdj.error.v1.schema.json",
    "module": contract_root / "module" / "lmdj.module.v1.schema.json",
    "product_version": (
        contract_root / "version" / "lmdj.product-version.v1.schema.json"
    ),
}


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    assert isinstance(value, dict), f"{path} must contain an object"
    return value


def contained_constants(rules: list[dict], property_name: str) -> set[int]:
    constants = set()
    for rule in rules:
        contains = rule["contains"]
        constants.add(contains["properties"][property_name]["const"])
        assert rule["minContains"] == 1
        assert rule["maxContains"] == 1
    return constants


schemas = {name: load_json(path) for name, path in schema_paths.items()}

for name, schema in schemas.items():
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["x-lmdj-contract-version"] == "1.0.0"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["$id"].endswith(schema_paths[name].name)

project = schemas["project"]
assert set(project["required"]) == {
    "contract",
    "project_id",
    "revision",
    "bpm",
    "banks",
    "assets",
    "takes",
    "patterns",
}
assert project["properties"]["contract"]["const"] == "lmdj.project.v1"
assert project["properties"]["revision"]["minimum"] == 0
assert project["properties"]["bpm"] == {
    "type": "integer",
    "minimum": 40,
    "maximum": 240,
}

banks = project["properties"]["banks"]
assert banks["minItems"] == 4
assert banks["maxItems"] == 4
assert contained_constants(banks["allOf"], "bank") == set(range(4))

bank = project["$defs"]["bank"]
pads = bank["properties"]["pads"]
assert pads["minItems"] == 16
assert pads["maxItems"] == 16
assert contained_constants(pads["allOf"], "pad") == set(range(16))

for collection in ("assets", "takes", "patterns"):
    collection_schema = project["properties"][collection]
    assert collection_schema["type"] == "object"
    assert collection_schema["propertyNames"]["$ref"] == "#/$defs/uuid"

event = project["$defs"]["pattern_event"]
assert set(event["required"]) == {"slot", "step", "velocity"}
assert event["additionalProperties"] is False
assert "asset_id" not in event["properties"]
slot = project["$defs"]["slot"]
assert set(slot["required"]) == {"bank", "pad"}
assert slot["additionalProperties"] is False
assert slot["properties"]["bank"]["minimum"] == 0
assert slot["properties"]["bank"]["maximum"] == 3
assert slot["properties"]["pad"]["minimum"] == 0
assert slot["properties"]["pad"]["maximum"] == 15

capability = schemas["capability"]
assert set(capability["required"]) == {
    "contract",
    "capability_id",
    "contract_version",
    "input_artifacts",
    "output_artifacts",
    "determinism",
    "progress_events",
    "errors",
    "resources",
    "execution",
    "policy",
}
assert capability["properties"]["contract"]["const"] == "lmdj.capability.v1"
artifact_port = capability["$defs"]["artifact_port"]
assert set(artifact_port["required"]) == {
    "name",
    "media_types",
    "schema_id",
    "schema_version",
    "required",
}
assert artifact_port["properties"]["schema_id"]["$ref"] == "#/$defs/id"
assert artifact_port["properties"]["schema_version"]["$ref"] == (
    "#/$defs/semver"
)

assembly = schemas["assembly"]
assert set(assembly["required"]) == {
    "contract",
    "product",
    "modules",
    "hosts",
    "providers",
    "contracts",
}
assert assembly["properties"]["contract"]["const"] == "lmdj.assembly.v1"
for collection in ("modules", "hosts", "providers", "contracts"):
    assert assembly["properties"][collection]["type"] == "array"
    assert assembly["properties"][collection]["uniqueItems"] is True

error_schema = schemas["error"]
assert error_schema["properties"]["contract"]["const"] == "lmdj.error.v1"
public_error_codes = {
    "INVALID_ARGUMENT",
    "NOT_FOUND",
    "REVISION_CONFLICT",
    "DUPLICATE_ID",
    "UNSUPPORTED_AUDIO",
    "MISSING_ASSET",
    "INVALID_PROJECT",
    "COOK_FAILED",
    "PROVIDER_NOT_FOUND",
    "PROVIDER_FAILED",
    "PERMISSION_DENIED",
    "IO_ERROR",
    "INTERNAL_ERROR",
}
assert set(error_schema["properties"]["code"]["enum"]) == public_error_codes
assert capability["properties"]["errors"]["items"]["$ref"] == (
    "#/$defs/error_code"
)
assert set(capability["$defs"]["error_code"]["enum"]) == public_error_codes

pattern = project["$defs"]["pattern"]
step_limits = {}
for rule in pattern["allOf"]:
    bars = rule["if"]["properties"]["bars"]["const"]
    step = rule["then"]["properties"]["events"]["items"]["properties"]["step"]
    step_limits[bars] = step["maximum"]
assert step_limits == {1: 15, 2: 31, 4: 63, 8: 127}

module = schemas["module"]
assert set(module["required"]) == {
    "contract",
    "module",
    "version",
    "api_version",
    "dependencies",
}
semver_pattern = module["$defs"]["semver"]["pattern"]
assert re.fullmatch(semver_pattern, "0.1.0")
assert not re.fullmatch(semver_pattern, "0.1")
assert (
    module["properties"]["dependencies"]["additionalProperties"]["$ref"]
    == "#/$defs/semver"
)

product_version = schemas["product_version"]
assert product_version["properties"]["contract"]["const"] == (
    "lmdj.product-version.v1"
)
assert product_version["properties"]["product"]["const"] == "lmdj"
assert product_version["properties"]["milestone"]["minimum"] == 1
for field in ("minor", "build", "patch"):
    assert product_version["properties"][field]["minimum"] == 0
zero_build_rule = product_version["allOf"][0]
assert zero_build_rule["if"]["properties"]["build"]["const"] == 0
assert zero_build_rule["then"]["properties"]["patch"]["const"] == 0

foundation_manifest = load_json(
    repo_root / "packages" / "foundation" / "module.json"
)
assert foundation_manifest == {
    "contract": "lmdj.module.v1",
    "module": "foundation",
    "version": "0.1.0",
    "api_version": 1,
    "dependencies": {},
}

print("schema contract checks: 6 passed")
