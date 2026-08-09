#!/usr/bin/env python3

import json
from pathlib import Path
import re


repo_root = Path(__file__).resolve().parents[2]
contract_root = repo_root / "contracts"

schema_paths = {
    "project": contract_root / "project" / "lmdj.project.v1.schema.json",
    "project_v2": contract_root / "project" / "lmdj.project.v2.schema.json",
    "project_bundle": (
        contract_root / "project" / "lmdj.project-bundle.v1.schema.json"
    ),
    "capability": (
        contract_root / "capability" / "lmdj.capability.v1.schema.json"
    ),
    "capability_v2": (
        contract_root / "capability" / "lmdj.capability.v2.schema.json"
    ),
    "assembly_v1": (
        contract_root / "assembly" / "lmdj.assembly.v1.schema.json"
    ),
    "assembly": contract_root / "assembly" / "lmdj.assembly.v2.schema.json",
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

contract_versions = {
    name: (
        "2.0.0"
        if name in {"assembly", "capability_v2", "project_v2"}
        else "1.0.0"
    )
    for name in schemas
}
for name, schema in schemas.items():
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["x-lmdj-contract-version"] == contract_versions[name]
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

project_v2 = schemas["project_v2"]
assert set(project_v2["required"]) == set(project["required"])
assert project_v2["properties"]["contract"]["const"] == "lmdj.project.v2"
assert project_v2["properties"]["bpm"] == project["properties"]["bpm"]

pad_v2 = project_v2["$defs"]["pad"]
assert set(pad_v2["required"]) == {"pad", "asset_id", "playback"}
assert set(pad_v2["properties"]) == {"pad", "asset_id", "playback"}
assert pad_v2["additionalProperties"] is False
assert pad_v2["properties"]["playback"]["$ref"] == "#/$defs/playback"

playback = project_v2["$defs"]["playback"]
assert set(playback["required"]) == {
    "trim_start_frame",
    "trim_end_frame",
    "trigger_mode",
    "gain_millidb",
    "muted",
}
assert set(playback["properties"]) == set(playback["required"])
assert playback["additionalProperties"] is False
assert playback["properties"]["trim_start_frame"] == {
    "type": "integer",
    "minimum": 0,
}
assert playback["properties"]["trim_end_frame"] == {
    "type": ["integer", "null"],
    "minimum": 1,
}
assert playback["properties"]["trigger_mode"] == {
    "enum": ["one_shot", "gate", "loop_gate", "loop_toggle"]
}
assert playback["properties"]["gain_millidb"] == {
    "type": "integer",
    "minimum": -60000,
    "maximum": 6000,
}
assert playback["properties"]["muted"] == {"type": "boolean"}

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

capability_v2 = schemas["capability_v2"]
assert capability_v2["properties"]["contract"]["const"] == (
    "lmdj.capability.v2"
)
assert capability_v2["properties"]["output_artifacts"]["minItems"] == 1
artifact_port_v2 = capability_v2["$defs"]["artifact_port"]
assert set(artifact_port_v2["required"]) == {
    "name",
    "media_types",
    "schema_id",
    "schema_version",
    "required",
    "max_count",
}
assert artifact_port_v2["properties"]["max_count"] == {
    "type": "integer",
    "minimum": 1,
}
binding = capability_v2["$defs"]["artifact_binding"]
assert set(binding["required"]) == {"port", "artifact"}
assert binding["additionalProperties"] is False
assert binding["properties"]["artifact"]["$ref"] == (
    "#/$defs/artifact_ref"
)
request_v2 = capability_v2["$defs"]["capability_request"]
assert set(request_v2["required"]) == {
    "capability",
    "inputs",
    "parameters",
    "data_classification",
    "platform",
    "region",
    "required_permissions",
}
assert request_v2["properties"]["inputs"]["items"]["$ref"] == (
    "#/$defs/artifact_binding"
)
assert request_v2["properties"]["inputs"]["uniqueItems"] is True
candidate_v2 = capability_v2["$defs"]["candidate"]
assert set(candidate_v2["required"]) == {"candidate_id", "outputs", "provenance"}
assert candidate_v2["properties"]["outputs"]["items"]["$ref"] == (
    "#/$defs/artifact_binding"
)
assert candidate_v2["properties"]["outputs"]["uniqueItems"] is True

fixture_root = repo_root / "tests" / "fixtures" / "contracts"
valid_project_v2 = load_json(fixture_root / "project-v2-valid.json")
invalid_project_v2 = load_json(
    fixture_root / "project-v2-invalid-playback.json"
)
assert valid_project_v2["banks"][0]["pads"][0]["asset_id"] == (
    valid_project_v2["banks"][0]["pads"][1]["asset_id"]
)
assert {
    pad["playback"]["trigger_mode"]
    for pad in valid_project_v2["banks"][0]["pads"][:4]
} == {"one_shot", "gate", "loop_gate", "loop_toggle"}
assert valid_project_v2["banks"][0]["pads"][0]["playback"][
    "gain_millidb"
] == -60000
assert valid_project_v2["banks"][0]["pads"][1]["playback"][
    "gain_millidb"
] == 6000
assert valid_project_v2["banks"][0]["pads"][0]["playback"][
    "trim_end_frame"
] is None

valid_capability_v2 = load_json(
    fixture_root / "capability-v2-valid.json"
)
valid_descriptor = valid_capability_v2["descriptor"]
assert valid_descriptor["contract"] == "lmdj.capability.v2"
assert [
    port["name"] for port in valid_descriptor["input_artifacts"]
] == ["source", "reference"]
assert [
    binding["port"] for binding in valid_capability_v2["request"]["inputs"]
] == ["reference", "source"]
assert [
    port["name"] for port in valid_descriptor["output_artifacts"]
] == ["drums", "bass"]
assert [
    binding["port"]
    for binding in valid_capability_v2["candidate"]["outputs"]
] == ["bass", "drums"]
assert {
    port["media_types"][0]
    for port in valid_descriptor["output_artifacts"]
} == {"application/x-lmdj-proof"}

invalid_capability_v2 = load_json(
    fixture_root / "capability-v2-invalid.json"
)
invalid_descriptor = invalid_capability_v2["descriptor"]
assert invalid_descriptor["output_artifacts"] == []
assert invalid_descriptor["input_artifacts"][0]["max_count"] == 0
assert "port" not in invalid_capability_v2["request"]["inputs"][0]

assembly = schemas["assembly"]
assert set(assembly["required"]) == {
    "contract",
    "product",
    "modules",
    "hosts",
    "providers",
    "contracts",
    "provider_policy",
}
assert assembly["properties"]["contract"]["const"] == "lmdj.assembly.v2"
for collection in ("modules", "hosts", "providers", "contracts"):
    assert assembly["properties"][collection]["type"] == "array"
    assert assembly["properties"][collection]["uniqueItems"] is True
provider_policy = assembly["$defs"]["provider_policy"]
assert set(provider_policy["required"]) == {
    "allowed_regions",
    "allowed_data_classifications",
    "granted_permissions",
}
assert provider_policy["additionalProperties"] is False

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

project_bundle = schemas["project_bundle"]
assert set(project_bundle["required"]) == {
    "bundle_digest",
    "compression",
    "contract",
    "contract_version",
    "entries",
    "project_contract",
    "project_id",
    "uncompressed_bytes",
}
assert project_bundle["properties"]["contract"]["const"] == (
    "lmdj.project-bundle.v1"
)
assert project_bundle["properties"]["contract_version"]["const"] == "1.0.0"
assert project_bundle["properties"]["compression"]["const"] == "none"
assert project_bundle["properties"]["project_contract"]["const"] == (
    "lmdj.project.v1"
)
assert project_bundle["properties"]["entries"]["maxItems"] == 4096
assert project_bundle["$defs"]["entry"]["properties"]["bytes"]["maximum"] == (
    67_108_864
)
assert project_bundle["properties"]["uncompressed_bytes"]["maximum"] == (
    536_870_912
)

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
    "version": "0.2.0",
    "api_version": 1,
    "dependencies": {},
}

# --------------------------------------------------------------------------
# Execute the Contracts.
#
# Everything above inspects the schema documents. Nothing above ever ran a
# schema against an instance, so a Contract could disagree with the code that
# implements it and no gate would notice. The checks below close that.
# --------------------------------------------------------------------------

import json_schema  # noqa: E402  (sibling module in tests/conformance)

_DELETE = object()

capability_v2_defs = capability_v2["$defs"]


def as_root(definition: dict) -> dict:
    """Make a $defs entry validatable on its own, keeping local references."""
    return {**definition, "$defs": capability_v2_defs}


def mutated(base: dict, pointer: list, value) -> dict:
    """Deep-copy base and set one location, or delete it when value is _DELETE."""
    clone = json.loads(json.dumps(base))
    node = clone
    for token in pointer[:-1]:
        node = node[token]
    if value is _DELETE:
        del node[pointer[-1]]
    else:
        node[pointer[-1]] = value
    return clone


request_schema = as_root(capability_v2_defs["capability_request"])
candidate_schema = as_root(capability_v2_defs["candidate"])

# The valid fixture must satisfy every part of the Contract it claims.
json_schema.check(
    valid_descriptor, capability_v2, "capability-v2-valid descriptor"
)
json_schema.check(
    valid_capability_v2["request"], request_schema, "capability-v2-valid request"
)
json_schema.check(
    valid_capability_v2["candidate"],
    candidate_schema,
    "capability-v2-valid candidate",
)

# Every shipped Product artifact must satisfy its Contract.
json_schema.check(
    load_json(repo_root / "products" / "lmdj" / "assembly.json"),
    assembly,
    "products/lmdj/assembly.json",
)
json_schema.check(
    load_json(repo_root / "products" / "lmdj" / "version.json"),
    product_version,
    "products/lmdj/version.json",
)
json_schema.check(
    load_json(fixture_root / "project-bundle-valid.json"),
    project_bundle,
    "project-bundle-valid",
)
json_schema.check(valid_project_v2, project_v2, "project-v2-valid")
invalid_project_v2_violations = json_schema.validate(
    invalid_project_v2, project_v2
)
assert any(
    "gain_millidb: value 6001 is above maximum 6000" in violation
    for violation in invalid_project_v2_violations
), invalid_project_v2_violations
for unknown_target in (
    mutated(valid_project_v2, ["banks", 0, "pads", 0, "compat"], True),
    mutated(
        valid_project_v2,
        ["banks", 0, "pads", 0, "playback", "compat"],
        True,
    ),
):
    violations = json_schema.validate(unknown_target, project_v2)
    assert any(
        "'compat' is not allowed" in violation for violation in violations
    ), violations
assert json_schema.validate(
    load_json(fixture_root / "project-bundle-invalid-traversal.json"),
    project_bundle,
)
module_manifests = sorted(repo_root.glob("*/*/module.json"))
assert len(module_manifests) >= 11, module_manifests
for manifest_path in module_manifests:
    json_schema.check(
        load_json(manifest_path),
        module,
        manifest_path.relative_to(repo_root).as_posix(),
    )

# One named negative case per rule. The bundled invalid fixture mixes several
# violations into one document, so no test could show which rule fired.
negative_cases = [
    (
        "descriptor: max_count below one",
        capability_v2,
        mutated(valid_descriptor, ["input_artifacts", 0, "max_count"], 0),
        "below minimum 1",
    ),
    (
        "descriptor: no output ports",
        capability_v2,
        mutated(valid_descriptor, ["output_artifacts"], []),
        "fewer than minItems 1",
    ),
    (
        "descriptor: port name is not lowercase",
        capability_v2,
        mutated(valid_descriptor, ["input_artifacts", 0, "name"], "Source"),
        "does not match pattern",
    ),
    (
        "descriptor: port drops a required field",
        capability_v2,
        mutated(valid_descriptor, ["input_artifacts", 0, "required"], _DELETE),
        "missing required property 'required'",
    ),
    (
        "descriptor: port carries an unknown field",
        capability_v2,
        mutated(valid_descriptor, ["input_artifacts", 0, "compat"], True),
        "'compat' is not allowed",
    ),
    (
        "descriptor: contract identifies v1",
        capability_v2,
        mutated(valid_descriptor, ["contract"], "lmdj.capability.v1"),
        "expected const",
    ),
    (
        "request: binding omits its port",
        request_schema,
        mutated(valid_capability_v2["request"], ["inputs", 0, "port"], _DELETE),
        "missing required property 'port'",
    ),
    (
        "request: binding port is not lowercase",
        request_schema,
        mutated(valid_capability_v2["request"], ["inputs", 0, "port"], "Source"),
        "does not match pattern",
    ),
    (
        "request: binding uses a compatibility shorthand",
        request_schema,
        mutated(
            valid_capability_v2["request"], ["inputs", 0, "compatibility"], "x"
        ),
        "'compatibility' is not allowed",
    ),
    (
        "request: artifact hash is not a sha256",
        request_schema,
        mutated(
            valid_capability_v2["request"],
            ["inputs", 0, "artifact", "sha256"],
            "abc",
        ),
        "does not match pattern",
    ),
    (
        "candidate: output binding omits its port",
        candidate_schema,
        mutated(valid_capability_v2["candidate"], ["outputs", 0, "port"], _DELETE),
        "missing required property 'port'",
    ),
]

for case_name, case_schema, case_instance, expected in negative_cases:
    violations = json_schema.validate(case_instance, case_schema)
    assert violations, f"{case_name}: expected the Contract to reject this"
    assert any(expected in violation for violation in violations), (
        case_name,
        expected,
        violations,
    )

# The retained bundled fixture must still be rejected as a whole.
assert json_schema.validate(invalid_descriptor, capability_v2)
assert json_schema.validate(invalid_capability_v2["request"], request_schema)

# Rules the Contract cannot express, recorded so they are not assumed covered.
#
# Unique port names: `uniqueItems` only rejects identical port objects, so two
# ports sharing a name but differing elsewhere satisfy the Schema. Enforced by
# `valid_ports()` in packages/provider-sdk/src/registry.cpp.
duplicate_named_ports = mutated(
    valid_descriptor,
    ["input_artifacts", 1, "name"],
    valid_descriptor["input_artifacts"][0]["name"],
)
assert json_schema.validate(duplicate_named_ports, capability_v2) == [], (
    "expected the Schema to accept duplicate port names; if this now fails the "
    "Schema gained the rule and registry.cpp is no longer its only enforcer"
)

# Candidate outputs satisfying the descriptor's required ports is a
# cross-document rule; the candidate Schema alone cannot see the descriptor.
# Enforced by `valid_output_bindings()` in provider-sdk/src/attempt_store.cpp.
assert (
    json_schema.validate(
        mutated(valid_capability_v2["candidate"], ["outputs"], []),
        candidate_schema,
    )
    == []
), "expected the Schema to accept empty candidate outputs"

print(
    f"schema contract checks: {len(schemas)} passed, "
    f"{len(negative_cases)} negative cases, "
    f"{len(module_manifests) + 2} Product artifacts validated"
)
