#!/usr/bin/env python3

import json
import math
from pathlib import Path
import re


repo_root = Path(__file__).resolve().parents[2]
contract_root = repo_root / "contracts"

schema_paths = {
    "slice_points": contract_root / "slice-points" / "lmdj.slice-points.v1.schema.json",
    "project_v5": contract_root / "project" / "lmdj.project.v5.schema.json",
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
    "soundset": contract_root / "soundset" / "lmdj.soundset.v1.schema.json",
    "soundset_catalog": (
        contract_root / "soundset-catalog" / "lmdj.soundset-catalog.v1.schema.json"
    ),
    "runtime_content": (
        contract_root / "runtime-content" / "lmdj.runtime-content.v1.schema.json"
    ),
    "cardputer_transfer": (
        contract_root / "cardputer-transfer" / "lmdj.cardputer-transfer.v1.schema.json"
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
        "5.0.0" if name == "project_v5" else
        "2.0.0"
        if name in {"project_bundle", "assembly", "capability_v2"}
        else (
            "1.1.0" if name in {"error", "soundset"} else "1.0.0"
        )
    )
    for name in schemas
}
for name, schema in schemas.items():
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["x-lmdj-contract-version"] == contract_versions[name]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["$id"].endswith(schema_paths[name].name)

# The retired v1-v4 Project schemas pinned these shared rules through
# cross-level chains; with only v5 shipped, pin them on v5 directly.
project_v5 = schemas["project_v5"]
assert set(project_v5["required"]) == {
    "contract",
    "project_id",
    "revision",
    "bpm",
    "sequence_settings",
    "banks",
    "assets",
    "patterns",
    "pattern_slots",
    "performances",
}
assert project_v5["properties"]["contract"]["const"] == "lmdj.project.v5"
assert project_v5["properties"]["revision"]["minimum"] == 0
assert project_v5["properties"]["bpm"] == {
    "type": "integer",
    "minimum": 40,
    "maximum": 240,
}

banks = project_v5["properties"]["banks"]
assert banks["minItems"] == 4
assert banks["maxItems"] == 4
assert contained_constants(banks["allOf"], "bank") == set(range(4))

bank = project_v5["$defs"]["bank"]
pads = bank["properties"]["pads"]
assert pads["minItems"] == 16
assert pads["maxItems"] == 16
assert pads["uniqueItems"] is True
pad_v5 = project_v5["$defs"]["pad"]
assert pad_v5["properties"]["pad"] == {
    "type": "integer",
    "minimum": 0,
    "maximum": 15,
}
assert pad_v5["properties"]["playback"]["$ref"] == "#/$defs/playback"
assert pad_v5["additionalProperties"] is False

settings_v5 = project_v5["$defs"]["sequence_settings"]
assert settings_v5["properties"]["quantize_enabled"] == {"type": "boolean"}
assert settings_v5["properties"]["swing_percent"] == {
    "type": "integer",
    "minimum": 50,
    "maximum": 75,
}
event_v5 = project_v5["$defs"]["pattern_event"]
assert set(event_v5["required"]) == {
    "slot",
    "onset_tick",
    "duration_tick",
    "velocity",
}
assert "step" not in event_v5["properties"]
assert "asset_id" not in event_v5["properties"]
assert event_v5["properties"]["duration_tick"]["minimum"] == 1
assert event_v5["properties"]["velocity"] == {
    "type": "integer",
    "minimum": 1,
    "maximum": 127,
}
slot = project_v5["$defs"]["slot"]
assert set(slot["required"]) == {"bank", "pad"}
assert slot["additionalProperties"] is False
assert slot["properties"]["bank"]["minimum"] == 0
assert slot["properties"]["bank"]["maximum"] == 3
assert slot["properties"]["pad"]["minimum"] == 0
assert slot["properties"]["pad"]["maximum"] == 15
tick_limits = {}
for rule in project_v5["$defs"]["pattern"]["allOf"]:
    bars = rule["if"]["properties"]["bars"]["const"]
    event_rules = rule["then"]["properties"]["events"]["items"]["properties"]
    tick_limits[bars] = (
        event_rules["onset_tick"]["maximum"],
        event_rules["duration_tick"]["maximum"],
    )
assert tick_limits == {
    1: (3839, 3840),
    2: (7679, 7680),
    4: (15359, 15360),
    8: (30719, 30720),
}

assert project_v5["properties"]["performances"] == {
    "type": "array",
    "items": {"$ref": "#/$defs/performance"},
    "uniqueItems": True,
}, (
    "why: Project Truth stores Performances as an identity-bearing collection; "
    "remedy: restore the array of performance definitions"
)
assert project_v5["properties"]["pattern_slots"] == {
    "type": "array",
    "minItems": 16,
    "maxItems": 16,
    "items": {
        "oneOf": [
            {"$ref": "#/$defs/uuid"},
            {"type": "null"},
        ]
    },
}, (
    "why: Project Truth owns exactly 16 ordered nullable Pattern IDs; "
    "remedy: restore the fixed-length nullable UUID array"
)
performance_v5 = project_v5["$defs"]["performance"]
assert set(performance_v5["required"]) == {
    "performance_id",
    "name",
    "created_bpm",
    "recording_revision",
    "recording_artifact",
    "events",
}, (
    "why: a Performance must carry stable identity, name, BPM anchor, optional "
    "recording reference, and events; remedy: restore every required field"
)
performance_name_v5 = performance_v5["properties"]["name"]
assert performance_name_v5["type"] == "string"
assert performance_name_v5["minLength"] == 1
assert "pattern" in performance_name_v5, (
    "why: the repository validator needs an executable Unicode-aware upper "
    "bound for Performance names; remedy: restore the strict one-to-64-code-"
    "point constraint and its boundary behavior below"
)
pad_hit_v5 = project_v5["$defs"]["performance_pad_hit_event"]
assert pad_hit_v5["properties"]["slot"] == {
    "type": "integer",
    "minimum": 0,
    "maximum": 63,
}, (
    "why: pad_hit references one of the 64 Pad Slots; "
    "remedy: restore the global slot range 0 through 63"
)
pattern_launch_v5 = project_v5["$defs"]["performance_pattern_launch_event"]
assert pattern_launch_v5["properties"]["pattern_slot"] == {
    "type": "integer",
    "minimum": 0,
    "maximum": 15,
}, (
    "why: PATTERN_SLOT_MIN/MAX are 0 and 15; "
    "remedy: restore the Pattern Slot index bounds"
)
event_definitions_v5 = [
    "performance_pad_hit_event",
    "performance_pattern_launch_event",
    "performance_fx_engage_event",
    "performance_fx_move_event",
    "performance_fx_release_event",
    "performance_hold_on_event",
    "performance_hold_off_event",
]
assert project_v5["$defs"]["performance_event"]["oneOf"] == [
    {"$ref": f"#/$defs/{name}"} for name in event_definitions_v5
], (
    "why: the event union and kind ordinals follow the locked vocabulary; "
    "remedy: restore the seven per-kind references in ordinal order"
)
assert [
    project_v5["$defs"][name]["properties"]["kind"]["const"]
    for name in event_definitions_v5
] == [
    "pad_hit",
    "pattern_launch",
    "fx_engage",
    "fx_move",
    "fx_release",
    "hold_on",
    "hold_off",
], (
    "why: the Performance kind vocabulary is a cross-language Contract; "
    "remedy: use the approved seven kind strings in ordinal order"
)
for fx_event_name in (
    "performance_fx_engage_event",
    "performance_fx_move_event",
):
    assert project_v5["$defs"][fx_event_name]["properties"]["value"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 1000,
    }, (
        "why: FX_VALUE_MIN/MAX are 0 and 1000; "
        f"remedy: restore the integer value bounds on {fx_event_name}"
    )
for event_name in event_definitions_v5:
    event_schema = project_v5["$defs"][event_name]
    assert event_schema["additionalProperties"] is False, (
        "why: Performance events must not smuggle Asset, pattern_id, or Bank "
        f"references; remedy: keep additionalProperties false on {event_name}"
    )

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
# Retired-level fixtures survive only as loader checkpoint data; the v4
# soundset Lineage fixture still feeds the legacy-Lineage v5 checks below.
valid_soundset_lineage_project_v4 = load_json(
    fixture_root / "project-v4-soundset-lineage-valid.json"
)

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
    "BANK_QUOTA_EXHAUSTED",
    "PROJECT_QUOTA_EXHAUSTED",
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
assert set(capability["$defs"]["error_code"]["enum"]) == public_error_codes - {
    "BANK_QUOTA_EXHAUSTED",
    "PROJECT_QUOTA_EXHAUSTED",
}

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
assert project_bundle["properties"]["contract_version"]["const"] == "2.0.0"
assert project_bundle["properties"]["compression"]["const"] == "none"
# During development the Bundle names only the writer's current Project
# Contract level; older containers and levels are rejected outright.
# docs/prd/decisions/2026-09-15-project-bundle-current-level-only.md
assert project_bundle["properties"]["project_contract"]["enum"] == [
    "lmdj.project.v5",
]
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

soundset = schemas["soundset"]
assert soundset["properties"]["contract"]["const"] == "lmdj.soundset.v1"
assert set(soundset["required"]) == {
    "contract",
    "set_id",
    "version",
    "name",
    "publisher",
    "license",
    "slots",
}
soundset_slots = soundset["properties"]["slots"]
assert soundset_slots["minItems"] == 16
assert soundset_slots["maxItems"] == 16
assert contained_constants(soundset_slots["allOf"], "slot") == set(range(16))
soundset_roles = [
    "kick",
    "snare",
    "clap",
    "hat_closed",
    "hat_open",
    "perc",
    "cymbal",
    "bass",
    "melody",
    "chord",
    "vocal",
    "fx",
    "other",
]
occupied_slot = soundset["$defs"]["slot"]["oneOf"][1]
assert occupied_slot["properties"]["role"]["enum"] == soundset_roles
# S11-D5: the set-level demo is one optional Artifact ref, and it reuses the
# same $def the slots do rather than restating the shape.
assert soundset["properties"]["demo"] == {"$ref": "#/$defs/artifact_ref"}
assert "demo" not in soundset["required"], (
    "why: S11-D5 makes the set-level demo optional; "
    "remedy: keep demo out of the required list"
)
assert (
    occupied_slot["properties"]["artifact"]["$ref"]
    == soundset["properties"]["demo"]["$ref"]
), (
    "why: a demo Artifact and a slot Artifact are the same kind of reference; "
    "remedy: point both at #/$defs/artifact_ref"
)
license_schema = soundset["$defs"]["license"]
assert set(license_schema["required"]) == {
    "spdx_id",
    "rights_holder",
    "copyright",
    "attribution",
}
assert license_schema["properties"]["spdx_id"] == {
    "type": "string",
    "minLength": 1,
}
assert "enum" not in license_schema["properties"]["spdx_id"], (
    "why: SPDX allowlist is eligibility, not Schema; "
    "remedy: keep license.spdx_id a non-empty string"
)

soundset_catalog = schemas["soundset_catalog"]
assert soundset_catalog["properties"]["contract"]["const"] == (
    "lmdj.soundset-catalog.v1"
)
catalog_license = soundset_catalog["$defs"]["license_summary"]
assert set(catalog_license["required"]) == {"spdx_id", "rights_holder"}
assert catalog_license["additionalProperties"] is False
assert catalog_license["properties"]["spdx_id"] == {
    "type": "string",
    "minLength": 1,
}
assert "enum" not in catalog_license["properties"]["spdx_id"]
assert soundset_catalog["$defs"]["entry"]["properties"]["roles_summary"][
    "items"
]["enum"] == soundset_roles

foundation_manifest = load_json(
    repo_root / "packages" / "foundation" / "module.json"
)
assert foundation_manifest == {
    "contract": "lmdj.module.v1",
    "module": "foundation",
    "version": "0.4.0",
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

valid_soundset = load_json(fixture_root / "soundset-v1-valid.json")
json_schema.check(valid_soundset, soundset, "soundset-v1-valid")
json_schema.check(
    load_json(fixture_root / "soundset-catalog-v1-valid.json"),
    soundset_catalog,
    "soundset-catalog-v1-valid",
)
invalid_soundset_license = load_json(
    fixture_root / "soundset-v1-invalid-license-schema.json"
)
assert json_schema.validate(invalid_soundset_license, soundset), (
    "why: a Sound Set object missing license must fail Schema; "
    "remedy: keep license required"
)
assert "license" not in invalid_soundset_license
empty_rights_holder = mutated(
    valid_soundset, ["license", "rights_holder"], ""
)
assert json_schema.validate(empty_rights_holder, soundset), (
    "why: empty rights_holder is a Schema fault; "
    "remedy: keep license.rights_holder minLength 1"
)
unknown_role = mutated(valid_soundset, ["slots", 0, "role"], "cowbell")
assert json_schema.validate(unknown_role, soundset), (
    "why: role is a closed Schema enum; "
    "remedy: keep occupied slot role on the v1 enum"
)
fifteen_slots = mutated(valid_soundset, ["slots"], valid_soundset["slots"][:15])
seventeen_slots = mutated(
    valid_soundset, ["slots"], valid_soundset["slots"] + [{"slot": 0}]
)
assert json_schema.validate(fifteen_slots, soundset), (
    "why: slots must contain exactly 16 entries; remedy: keep minItems/maxItems 16"
)
assert json_schema.validate(seventeen_slots, soundset), (
    "why: slots must contain exactly 16 entries; remedy: keep minItems/maxItems 16"
)
duplicate_slot = json.loads(json.dumps(valid_soundset))
duplicate_slot["slots"][1] = {"slot": 0}
assert json_schema.validate(duplicate_slot, soundset), (
    "why: each slot index 0-15 must appear exactly once; "
    "remedy: keep the allOf contains minContains/maxContains 1 pattern"
)
uppercase_sha256 = mutated(
    valid_soundset,
    ["slots", 0, "artifact", "sha256"],
    "A" * 64,
)
assert json_schema.validate(uppercase_sha256, soundset), (
    "why: artifact sha256 is lowercase hex; remedy: keep the sha256 pattern"
)
# S11-D5: a manifest carrying the set-level demo validates, and one without
# it stays valid -- `valid_soundset` above is the no-demo case.
valid_soundset_demo = load_json(fixture_root / "soundset-v1-valid-demo.json")
json_schema.check(valid_soundset_demo, soundset, "soundset-v1-valid-demo")
assert "demo" in valid_soundset_demo
assert "demo" not in valid_soundset

# A demo ref carrying a key the Contract never declares is refused, exactly as
# a slot Artifact ref is: artifact_ref is additionalProperties false.
invalid_soundset_demo = load_json(
    fixture_root / "soundset-v1-invalid-demo.json"
)
assert json_schema.validate(invalid_soundset_demo, soundset), (
    "why: a demo ref with an undeclared key must fail Schema; "
    "remedy: keep artifact_ref additionalProperties false"
)
assert "duration_ms" in invalid_soundset_demo["demo"]

for field, value in (
    ("sha256", "A" * 64),
    ("media_type", ""),
    ("byte_length", 0),
):
    assert json_schema.validate(
        mutated(valid_soundset_demo, ["demo", field], value), soundset
    ), (
        f"why: a malformed demo {field} must fail Schema; "
        f"remedy: keep demo on #/$defs/artifact_ref"
    )

# Adding the demo carrier must not open the root object up.
assert json_schema.validate(
    mutated(valid_soundset_demo, ["unexpected"], True), soundset
), (
    "why: unknown top-level keys stay rejected after 1.1.0; "
    "remedy: keep the root additionalProperties false"
)

unknown_spdx = mutated(valid_soundset, ["license", "spdx_id"], "MIT")
json_schema.check(
    unknown_spdx,
    soundset,
    "soundset SPDX allowlist is not a Schema enum",
)
empty_by_attribution = mutated(valid_soundset, ["license", "attribution"], "")
json_schema.check(
    empty_by_attribution,
    soundset,
    "empty CC-BY attribution is eligibility, not Schema",
)
# Legacy (retired v4) Lineage shapes stay loadable: the current v5 schema
# still admits them, exercised by the L3 checks at the end of this file.
valid_lineage = {
    "source": {
        "kind": "asset_artifact",
        "artifact_sha256": "b" * 64,
        "project_revision": 7,
    },
    "derivation": {
        "kind": "resample",
        "range": {"start_frame": 10, "end_frame": 20},
        "performance_id": "40000000-0000-4000-8000-000000000001",
    },
}
assert (
    valid_soundset_lineage_project_v4["assets"][0]["lineage"]["source"]["kind"]
    == "soundset"
)
assert (
    valid_soundset_lineage_project_v4["assets"][0]["lineage"]["derivation"]
    == {"kind": "soundset_install"}
)
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

# Stage 12 K1: formal shape and independent byte/context conformance.
# This is a conformance oracle, not the future production C++ validator.
slice_schema = schemas["slice_points"]
slice_descriptor = load_json(contract_root / "capability" / "sample.slice.v1.json")
json_schema.check(slice_descriptor, capability_v2, "sample.slice descriptor")
assert slice_descriptor["output_artifacts"][0]["schema_id"] == (
    slice_schema["properties"]["contract"]["const"]
)
assert slice_descriptor["output_artifacts"][0]["schema_version"] == (
    slice_schema["x-lmdj-contract-version"]
)
profile_path = contract_root / "artifact-audio" / "lmdj.audio.pcm16-wav.v1.md"
profile = profile_path.read_text(encoding="utf-8")
input_port = slice_descriptor["input_artifacts"][0]
assert f"contract_id: {input_port['schema_id']}" in profile
assert f"contract_version: {input_port['schema_version']}" in profile


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def finite_json_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite JSON number")
    return number


def reject_json_constant(value):
    raise ValueError(f"non-JSON constant: {value}")


def slice_vector_result(raw, context):
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_json_object,
            parse_float=finite_json_float,
            parse_constant=reject_json_constant,
        )
        # Escaped lone surrogates are not valid Unicode strings either.
        json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError) as error:
        return "syntax", [str(error)]
    shape_errors = json_schema.validate(payload, slice_schema)
    if shape_errors:
        return "schema", shape_errors
    if payload["source_sha256"] != context["source_sha256"]:
        return "context", ["source hash mismatch"]
    if payload["frame_rate"] != context["frame_rate"]:
        return "context", ["source rate mismatch"]
    previous = -1
    for point in payload["points"]:
        if point["frame"] >= context["frame_count"]:
            return "context", ["frame outside source"]
        if point["frame"] <= previous:
            return "context", ["frames not strictly increasing"]
        previous = point["frame"]
        if "label" in point and len(point["label"].encode("utf-8")) > 128:
            return "context", ["label exceeds 128 UTF-8 bytes"]
    return "valid", []


def canonical_slice_bytes(payload):
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


slice_fixture_root = repo_root / "tests" / "fixtures" / "contracts" / "slice-points"
slice_cases = []
for filename in ("valid.json", "invalid.json"):
    inventory = load_json(slice_fixture_root / filename)
    assert inventory["cases"], f"{filename}: no Slice vectors discovered"
    slice_cases.extend(inventory["cases"])
assert len({case["name"] for case in slice_cases}) == len(slice_cases)

for case in slice_cases:
    raw = (
        bytes.fromhex(case["raw_hex"]) if "raw_hex" in case else
        case["raw_json"].encode("utf-8") if "raw_json" in case else
        canonical_slice_bytes(case["payload"])
    )
    layer, errors = slice_vector_result(raw, case["context"])
    assert layer == case["expected_layer"], (case["name"], layer, errors)
    if "expected_error" in case:
        assert any(case["expected_error"] in error for error in errors), (
            case["name"], errors,
        )
    if "canonical_utf8" in case:
        assert raw == case["canonical_utf8"].encode("utf-8"), case["name"]
    if layer == "valid":
        assert canonical_slice_bytes(json.loads(raw)) == raw, case["name"]

# Boundaries are generated here rather than bloating the fixture inventory.
slice_base = {
    "contract": "lmdj.slice-points.v1",
    "source_sha256": "a" * 64,
    "frame_rate": 48000,
    "points": [],
}
slice_context = {
    "source_sha256": "a" * 64, "frame_rate": 48000, "frame_count": 5000,
}
slice_boundaries = [
    ("maximum points", [{"frame": i} for i in range(4096)], "valid", None),
    ("point count +1", [{"frame": i} for i in range(4097)],
     "schema", "maxItems 4096"),
    ("128 UTF-8 bytes", [{"frame": 0, "label": "é" * 64}], "valid", None),
    ("129 UTF-8 bytes", [{"frame": 0, "label": "é" * 64 + "a"}],
     "context", "label exceeds 128 UTF-8 bytes"),
]
for name, points, expected_layer, expected_error in slice_boundaries:
    layer, errors = slice_vector_result(
        canonical_slice_bytes({**slice_base, "points": points}), slice_context,
    )
    assert layer == expected_layer, (name, layer, errors)
    if expected_error:
        assert any(expected_error in error for error in errors), (name, errors)

print(
    f"slice-points conformance: {len(slice_cases)} vectors and "
    f"{len(slice_boundaries)} boundary cases passed; "
    "syntax/Schema/context layers checked separately"
)

print(
    f"schema contract checks: {len(schemas)} passed, "
    f"{len(negative_cases)} negative cases, "
    f"{len(module_manifests) + 2} Product artifacts validated"
)

# L3: the successor schema admits only the approved closed Slice evidence.
valid_project_v5 = load_json(repo_root / "tests/fixtures/contracts/project-v5-valid.json")
json_schema.check(valid_project_v5, project_v5, "project-v5-valid")
lineage_v5 = valid_project_v5["assets"][0]["lineage"]
for path in ((), ("source",), ("derivation",), ("derivation", "capability"),
             ("derivation", "provider"), ("derivation", "output_artifact"),
             ("derivation", "recipe")):
    target = lineage_v5
    for key in path:
        target = target[key]
    for missing in target:
        changed = json.loads(json.dumps(valid_project_v5))
        node = changed["assets"][0]["lineage"]
        for key in path:
            node = node[key]
        del node[missing]
        assert json_schema.validate(changed, project_v5), (path, missing)
    changed = json.loads(json.dumps(valid_project_v5))
    node = changed["assets"][0]["lineage"]
    for key in path:
        node = node[key]
    node["extra"] = True
    assert json_schema.validate(changed, project_v5), path
for path, bad in [
    (["derivation", "recipe", "start_frame"], True),
    (["derivation", "recipe", "end_frame"], 9007199254740992),
    (["derivation", "recipe", "frame_rate"], 96000),
    (["derivation", "output_artifact", "byte_length"], 262145),
    (["derivation", "parameters_sha256"], "bad"),
    (["derivation", "attempt_id"], "../attempt"),
    (["derivation", "attempt_id"], ""),
    (["derivation", "attempt_id"], "a" * 129),
    (["derivation", "attempt_id"], "attempt\n"),
    (["derivation", "model_identity"], {}),
    (["derivation", "capability", "id"], "stem.separate.v1"),
]:
    changed = mutated(valid_project_v5, ["assets", 0, "lineage"] + path, bad)
    assert json_schema.validate(changed, project_v5), path
old = dict(valid_project_v5, contract="lmdj.project.v4")
assert json_schema.validate(old, project_v5), (
    "why: a Project labeled with a retired level is not a current document; "
    "remedy: keep the v5 contract const exact"
)
for old_lineage in (valid_lineage, valid_soundset_lineage_project_v4["assets"][0]["lineage"]):
    migrated = mutated(valid_project_v5, ["assets", 0, "lineage"], old_lineage)
    json_schema.check(migrated, project_v5, "legacy-lineage-v5")
modeled = mutated(valid_project_v5, ["assets", 0, "lineage", "derivation", "model_identity"],
                  {"id": "model", "version": "revision-7", "artifact_sha256": "e" * 64})
json_schema.check(modeled, project_v5, "model-lineage-v5")
opaque_attempt = mutated(valid_project_v5,
    ["assets", 0, "lineage", "derivation", "attempt_id"], "slice-job.attempt_1")
json_schema.check(opaque_attempt, project_v5, "sdk-attempt-id-lineage-v5")

# Executable boundaries the retired v4 sections pinned, re-based on v5.
for case_name, mutator in (
    (
        "missing recording revision",
        lambda project: project["performances"][0].pop("recording_revision"),
    ),
    (
        "negative recording revision",
        lambda project: project["performances"][0].__setitem__(
            "recording_revision", -1
        ),
    ),
):
    malformed_performance = json.loads(json.dumps(valid_project_v5))
    mutator(malformed_performance)
    assert json_schema.validate(malformed_performance, project_v5), (
        f"why: Project v5 must reject {case_name}; "
        "remedy: require a non-negative recording revision"
    )
for case_name, bad_slots in (
    ("wrong_length", [None] * 15),
    ("invalid_pattern_id", ["not-a-pattern-id"] + [None] * 15),
):
    assert json_schema.validate(
        mutated(valid_project_v5, ["pattern_slots"], bad_slots),
        project_v5,
    ), (
        f"why: Project v5 must reject {case_name} Pattern slots; "
        "remedy: restore the exact 16-item nullable UUID schema"
    )
smuggled_launch = json.loads(json.dumps(valid_project_v5))
launch_event = next(
    event
    for event in smuggled_launch["performances"][0]["events"]
    if event["kind"] == "pattern_launch"
)
launch_event["pattern_id"] = "30000000-0000-4000-8000-000000000001"
assert any(
    "expected exactly one oneOf branch to match, matched 0" in violation
    for violation in json_schema.validate(smuggled_launch, project_v5)
), (
    "why: Performance pattern_launch events reference slots, never pattern_id; "
    "remedy: retain per-event additionalProperties false"
)
overlong_performance_name = mutated(
    valid_project_v5,
    ["performances", 0, "name"],
    "x" * 65,
)
assert any(
    "does not match pattern" in violation
    for violation in json_schema.validate(overlong_performance_name, project_v5)
), (
    "why: Performance names beyond PERFORMANCE_NAME_MAX must be rejected; "
    "remedy: restore the 64-code-point name pattern"
)
for case_name, accepted_name, rejected_name in (
    ("LF boundary", "x" * 63 + "\n", "x" * 64 + "\n"),
    ("CRLF boundary", "x" * 62 + "\r\n", "x" * 63 + "\r\n"),
):
    assert len(accepted_name) == 64
    assert len(rejected_name) == 65
    json_schema.check(
        mutated(
            valid_project_v5,
            ["performances", 0, "name"],
            accepted_name,
        ),
        project_v5,
        f"project-v5 64-code-point {case_name} Performance name",
    )
    violations = json_schema.validate(
        mutated(
            valid_project_v5,
            ["performances", 0, "name"],
            rejected_name,
        ),
        project_v5,
    )
    assert violations, (
        f"why: 65-code-point {case_name} exceeds PERFORMANCE_NAME_MAX even "
        "when it ends in line terminators; remedy: use a strict end-of-input "
        "1-to-64-code-point constraint"
    )

non_bmp_code_point = "\U0001F39B"
non_bmp_name_64 = non_bmp_code_point * 64
non_bmp_name_65 = non_bmp_code_point * 65
assert len(non_bmp_name_64) == 64
assert len(non_bmp_name_65) == 65
json_schema.check(
    mutated(
        valid_project_v5,
        ["performances", 0, "name"],
        non_bmp_name_64,
    ),
    project_v5,
    "project-v5 64-code-point non-BMP Performance name",
)
assert json_schema.validate(
    mutated(
        valid_project_v5,
        ["performances", 0, "name"],
        non_bmp_name_65,
    ),
    project_v5,
), (
    "why: PERFORMANCE_NAME_MAX counts Unicode code points, not UTF-8 bytes; "
    "remedy: reject a 65-code-point non-BMP name while accepting 64"
)
