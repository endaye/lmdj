#!/usr/bin/env python3

import json
from pathlib import Path
import re


repo_root = Path(__file__).resolve().parents[2]
contract_root = repo_root / "contracts"

schema_paths = {
    "project": contract_root / "project" / "lmdj.project.v1.schema.json",
    "project_v2": contract_root / "project" / "lmdj.project.v2.schema.json",
    "project_v3": contract_root / "project" / "lmdj.project.v3.schema.json",
    "project_v4": contract_root / "project" / "lmdj.project.v4.schema.json",
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
        "1.2.0"
        if name == "project_bundle"
        else (
        "1.1.0"
        if name in {"error", "soundset"}
        else (
            "4.1.0"
            if name == "project_v4"
            else (
                "3.0.0"
                if name == "project_v3"
                else (
                    "2.0.0"
                    if name in {"assembly", "capability_v2", "project_v2"}
                    else "1.0.0"
                )
            )
        )
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

project_v3 = schemas["project_v3"]
assert set(project_v3["required"]) == {
    "contract",
    "project_id",
    "revision",
    "bpm",
    "sequence_settings",
    "banks",
    "assets",
    "patterns",
}
assert project_v3["properties"]["contract"]["const"] == "lmdj.project.v3"
assert project_v3["properties"]["bpm"] == project["properties"]["bpm"]
assert project_v3["properties"]["assets"]["type"] == "array"
assert project_v3["properties"]["patterns"]["type"] == "array"
assert "takes" not in project_v3["properties"]
settings_v3 = project_v3["$defs"]["sequence_settings"]
assert settings_v3["properties"]["quantize_enabled"] == {"type": "boolean"}
assert settings_v3["properties"]["swing_percent"] == {
    "type": "integer",
    "minimum": 50,
    "maximum": 75,
}
event_v3 = project_v3["$defs"]["pattern_event"]
assert set(event_v3["required"]) == {
    "slot",
    "onset_tick",
    "duration_tick",
    "velocity",
}
assert "step" not in event_v3["properties"]
assert event_v3["properties"]["duration_tick"]["minimum"] == 1
assert event_v3["properties"]["velocity"] == {
    "type": "integer",
    "minimum": 1,
    "maximum": 127,
}
tick_limits = {}
for rule in project_v3["$defs"]["pattern"]["allOf"]:
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

project_v4 = schemas["project_v4"]
assert set(project_v4["required"]) == set(project_v3["required"]) | {
    "pattern_slots",
    "performances",
}, (
    "why: Project v4 must add the required Pattern slots and Performances; "
    "remedy: derive the root fields from v3 and add both fields"
)
assert project_v4["properties"]["contract"]["const"] == "lmdj.project.v4", (
    "why: a v4 document must self-identify as lmdj.project.v4; "
    "remedy: set the v4 contract const"
)
assert project_v4["properties"]["performances"] == {
    "type": "array",
    "items": {"$ref": "#/$defs/performance"},
    "uniqueItems": True,
}, (
    "why: Project Truth stores Performances as an identity-bearing collection; "
    "remedy: restore the array of performance definitions"
)
assert project_v4["properties"]["pattern_slots"] == {
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
performance_v4 = project_v4["$defs"]["performance"]
assert set(performance_v4["required"]) == {
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
performance_name_v4 = performance_v4["properties"]["name"]
assert performance_name_v4["type"] == "string"
assert performance_name_v4["minLength"] == 1
assert "pattern" in performance_name_v4, (
    "why: the repository validator needs an executable Unicode-aware upper "
    "bound for Performance names; remedy: restore the strict one-to-64-code-"
    "point constraint and its boundary behavior below"
)
asset_v4 = project_v4["$defs"]["asset"]
assert set(asset_v4["required"]) == {"asset_id", "artifact", "lineage"}, (
    "why: every v4 Asset must explicitly declare its optional Lineage; "
    "remedy: require lineage and encode ordinary assets as null"
)
assert asset_v4["properties"]["lineage"] == {
    "oneOf": [
        {"$ref": "#/$defs/asset_lineage"},
        {"type": "null"},
    ]
}
asset_lineage_v4 = project_v4["$defs"]["asset_lineage"]
assert set(asset_lineage_v4["required"]) == {"source", "derivation"}
assert asset_lineage_v4["additionalProperties"] is False
assert asset_lineage_v4["properties"]["source"] == {
    "oneOf": [
        {"$ref": "#/$defs/asset_artifact_lineage_source"},
        {"$ref": "#/$defs/soundset_lineage_source"},
    ]
}, (
    "why: Contract 4.1.0 adds the S11-D9 soundset Lineage source beside the "
    "existing asset_artifact source on the same Lineage carrier; remedy: keep "
    "both variants in one closed oneOf and never add a second Lineage field"
)
assert asset_lineage_v4["properties"]["derivation"] == {
    "oneOf": [
        {"$ref": "#/$defs/resample_lineage_derivation"},
        {"$ref": "#/$defs/soundset_install_lineage_derivation"},
    ]
}, (
    "why: an installed Sound Set slot derives through soundset_install, not "
    "resample; remedy: keep both derivation variants in one closed oneOf"
)
for lineage_variant in (
    "asset_artifact_lineage_source",
    "soundset_lineage_source",
    "resample_lineage_derivation",
    "soundset_install_lineage_derivation",
):
    variant_schema = project_v4["$defs"][lineage_variant]
    assert variant_schema["additionalProperties"] is False, (
        f"why: {lineage_variant} must stay closed so an unknown key fails; "
        "remedy: restore additionalProperties false"
    )
    assert "const" in variant_schema["properties"]["kind"], (
        f"why: {lineage_variant} is discriminated by a constant kind; "
        "remedy: restore the const discriminator"
    )
    assert "kind" in variant_schema["required"]
assert project_v4["$defs"]["soundset_lineage_source"]["properties"]["kind"][
    "const"
] == "soundset"
assert set(
    project_v4["$defs"]["soundset_lineage_source"]["required"]
) == {
    "kind",
    "set_id",
    "set_version",
    "manifest_sha256",
    "slot_index",
    "artifact_sha256",
}, (
    "why: S11-D9 requires every typed soundset source field, not only kind; "
    "remedy: require all six keys"
)
assert project_v4["$defs"]["soundset_install_lineage_derivation"][
    "properties"
]["kind"]["const"] == "soundset_install"
assert set(
    project_v4["$defs"]["soundset_install_lineage_derivation"]["required"]
) == {"kind"}
event_definitions_v4 = [
    "performance_pad_hit_event",
    "performance_pattern_launch_event",
    "performance_fx_engage_event",
    "performance_fx_move_event",
    "performance_fx_release_event",
    "performance_hold_on_event",
    "performance_hold_off_event",
]
assert project_v4["$defs"]["performance_event"]["oneOf"] == [
    {"$ref": f"#/$defs/{name}"} for name in event_definitions_v4
], (
    "why: the v4 event union and kind ordinals follow the locked vocabulary; "
    "remedy: restore the seven per-kind references in ordinal order"
)
assert [
    project_v4["$defs"][name]["properties"]["kind"]["const"]
    for name in event_definitions_v4
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
pad_hit_v4 = project_v4["$defs"]["performance_pad_hit_event"]
assert pad_hit_v4["properties"]["slot"] == {
    "type": "integer",
    "minimum": 0,
    "maximum": 63,
}, (
    "why: pad_hit references one of the 64 Pad Slots; "
    "remedy: restore the global slot range 0 through 63"
)
pattern_launch_v4 = project_v4["$defs"]["performance_pattern_launch_event"]
assert pattern_launch_v4["properties"]["pattern_slot"] == {
    "type": "integer",
    "minimum": 0,
    "maximum": 15,
}, (
    "why: PATTERN_SLOT_MIN/MAX are 0 and 15; "
    "remedy: restore the Pattern Slot index bounds"
)
for fx_event_name in (
    "performance_fx_engage_event",
    "performance_fx_move_event",
):
    assert project_v4["$defs"][fx_event_name]["properties"]["value"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 1000,
    }, (
        "why: FX_VALUE_MIN/MAX are 0 and 1000; "
        f"remedy: restore the integer value bounds on {fx_event_name}"
    )
for event_name in event_definitions_v4:
    event_schema = project_v4["$defs"][event_name]
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
valid_project_v2 = load_json(fixture_root / "project-v2-valid.json")
invalid_project_v2 = load_json(
    fixture_root / "project-v2-invalid-playback.json"
)
valid_project_v3 = load_json(fixture_root / "project-v3-valid.json")
invalid_project_v3 = load_json(
    fixture_root / "project-v3-invalid-event.json"
)
valid_project_v4 = load_json(fixture_root / "project-v4-valid.json")
invalid_project_v4 = load_json(
    fixture_root / "project-v4-invalid-event.json"
)
invalid_project_v4["pattern_slots"] = valid_project_v4["pattern_slots"]
invalid_pattern_slots_v4 = load_json(
    fixture_root / "project-v4-invalid-pattern-slots.json"
)
migration_project_v4 = load_json(
    fixture_root / "project-v3-to-v4-migration.json"
)
valid_soundset_lineage_project_v4 = load_json(
    fixture_root / "project-v4-soundset-lineage-valid.json"
)
invalid_soundset_lineage_project_v4 = load_json(
    fixture_root / "project-v4-soundset-lineage-invalid.json"
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
assert project_bundle["properties"]["contract_version"]["const"] == "1.2.0"
assert project_bundle["properties"]["compression"]["const"] == "none"
# S11/#784: every Project Contract level the repository defines must be
# nameable, or a Project the writer produces cannot be packed at all.
assert project_bundle["properties"]["project_contract"]["enum"] == [
    "lmdj.project.v1",
    "lmdj.project.v2",
    "lmdj.project.v3",
    "lmdj.project.v4",
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
json_schema.check(valid_project_v2, project_v2, "project-v2-valid")
json_schema.check(valid_project_v3, project_v3, "project-v3-valid")
json_schema.check(valid_project_v4, project_v4, "project-v4-valid")

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
json_schema.check(
    migration_project_v4,
    project_v4,
    "project-v3-to-v4-migration output",
)
migration_project_v3 = json.loads(json.dumps(migration_project_v4))
migration_project_v3["contract"] = "lmdj.project.v3"
del migration_project_v3["performances"]
del migration_project_v3["pattern_slots"]
for asset in migration_project_v3["assets"]:
    del asset["lineage"]
json_schema.check(
    migration_project_v3,
    project_v3,
    "project-v3-to-v4-migration input",
)
for key, value in migration_project_v3.items():
    if key == "contract":
        continue
    if key == "assets":
        assert len(migration_project_v4[key]) == len(value)
        for asset_v4, asset_v3 in zip(migration_project_v4[key], value):
            assert asset_v4 == {**asset_v3, "lineage": None}, (
                "why: v3-to-v4 migration adds only explicit null Lineage to "
                "each Asset; remedy: preserve every legacy Asset field"
            )
        continue
    assert migration_project_v4[key] == value, (
        "why: v3-to-v4 migration must preserve every non-contract field; "
        f"remedy: restore the byte-identical {key} value in the golden vector"
    )
assert migration_project_v4["performances"] == [], (
    "why: every migrated v3 Project starts with no Performances; "
    "remedy: restore an empty performances array in the golden vector"
)
assert migration_project_v4["pattern_slots"] == [None] * 16, (
    "why: every migrated v3 Project starts with 16 empty Pattern slots; "
    "remedy: restore the all-null Pattern slot migration vector"
)
v3_with_lineage = json.loads(json.dumps(migration_project_v3))
v3_with_lineage["assets"][0]["lineage"] = None
assert json_schema.validate(v3_with_lineage, project_v3), (
    "why: a v3-declared Asset must not carry v4 Lineage; "
    "remedy: keep the legacy Asset shape closed"
)
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
json_schema.check(
    mutated(valid_project_v4, ["assets", 0, "lineage"], valid_lineage),
    project_v4,
    "project-v4-valid resample Lineage",
)
missing_asset_lineage = json.loads(json.dumps(valid_project_v4))
del missing_asset_lineage["assets"][0]["lineage"]
assert json_schema.validate(missing_asset_lineage, project_v4), (
    "why: every v4 Asset must explicitly encode Lineage or null; "
    "remedy: keep lineage required"
)
for case_name, path, value in (
    ("missing source", ["source"], None),
    ("uppercase SHA-256", ["source", "artifact_sha256"], "B" * 64),
    ("short SHA-256", ["source", "artifact_sha256"], "b" * 63),
    ("malformed Performance UUID", ["derivation", "performance_id"], "bad"),
):
    malformed_lineage = json.loads(json.dumps(valid_lineage))
    if value is None:
        del malformed_lineage[path[0]]
    else:
        target = malformed_lineage
        for segment in path[:-1]:
            target = target[segment]
        target[path[-1]] = value
    project_with_lineage = mutated(
        valid_project_v4,
        ["assets", 0, "lineage"],
        malformed_lineage,
    )
    assert json_schema.validate(project_with_lineage, project_v4), (
        f"why: Project v4 must reject {case_name} Lineage; "
        "remedy: preserve the exact closed Lineage shape"
    )
for extra_path in (["source"], ["derivation"], []):
    extra_lineage = json.loads(json.dumps(valid_lineage))
    target = extra_lineage
    for segment in extra_path:
        target = target[segment]
    target["unexpected"] = True
    project_with_lineage = mutated(
        valid_project_v4,
        ["assets", 0, "lineage"],
        extra_lineage,
    )
    assert json_schema.validate(project_with_lineage, project_v4), (
        "why: Lineage objects must reject extra keys; "
        "remedy: keep every nested object closed"
    )
json_schema.check(
    valid_soundset_lineage_project_v4,
    project_v4,
    "project-v4-soundset-lineage-valid",
)
assert (
    valid_soundset_lineage_project_v4["assets"][0]["lineage"]["source"]["kind"]
    == "soundset"
)
assert (
    valid_soundset_lineage_project_v4["assets"][0]["lineage"]["derivation"]
    == {"kind": "soundset_install"}
)
assert json_schema.validate(
    invalid_soundset_lineage_project_v4, project_v4
), (
    "why: a soundset Lineage source missing manifest_sha256 must fail; "
    "remedy: keep every typed soundset source field required"
)
soundset_lineage = valid_soundset_lineage_project_v4["assets"][0]["lineage"]
for case_name, path, value in (
    ("malformed set UUID", ["source", "set_id"], "bad"),
    ("non-SemVer set version", ["source", "set_version"], "1.2"),
    ("uppercase manifest SHA-256", ["source", "manifest_sha256"], "C" * 64),
    ("uppercase artifact SHA-256", ["source", "artifact_sha256"], "A" * 64),
    ("out-of-range slot index", ["source", "slot_index"], 16),
    ("negative slot index", ["source", "slot_index"], -1),
    ("unknown source kind", ["source", "kind"], "soundset_v2"),
    ("unknown derivation kind", ["derivation", "kind"], "soundset_apply"),
):
    malformed_soundset = json.loads(json.dumps(soundset_lineage))
    target = malformed_soundset
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = value
    assert json_schema.validate(
        mutated(
            valid_project_v4, ["assets", 0, "lineage"], malformed_soundset
        ),
        project_v4,
    ), (
        f"why: Project v4 must reject {case_name} soundset Lineage; "
        "remedy: preserve the exact closed soundset Lineage shape"
    )
for mixed_name, mixed in (
    (
        "soundset source with a resample derivation",
        {
            "source": soundset_lineage["source"],
            "derivation": valid_lineage["derivation"],
        },
    ),
    (
        "asset_artifact source with a soundset_install derivation",
        {
            "source": valid_lineage["source"],
            "derivation": soundset_lineage["derivation"],
        },
    ),
):
    json_schema.check(
        mutated(valid_project_v4, ["assets", 0, "lineage"], mixed),
        project_v4,
        f"project-v4-valid {mixed_name}",
    )
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
    malformed_performance = json.loads(json.dumps(valid_project_v4))
    mutator(malformed_performance)
    assert json_schema.validate(malformed_performance, project_v4), (
        f"why: Project v4 must reject {case_name}; "
        "remedy: require a non-negative recording revision"
    )
v3_with_pattern_slots = json.loads(json.dumps(migration_project_v3))
v3_with_pattern_slots["pattern_slots"] = [None] * 16
assert json_schema.validate(v3_with_pattern_slots, project_v3), (
    "why: a v3-declared Project must not carry pre-existing Pattern slots; "
    "remedy: keep v3 additionalProperties closed"
)
for case_name in ("wrong_length", "invalid_pattern_id"):
    malformed_slots = mutated(
        valid_project_v4,
        ["pattern_slots"],
        invalid_pattern_slots_v4[case_name],
    )
    assert json_schema.validate(malformed_slots, project_v4), (
        f"why: Project v4 must reject {case_name} Pattern slots; "
        "remedy: restore the exact 16-item nullable UUID schema"
    )
invalid_project_v4_violations = json_schema.validate(
    invalid_project_v4, project_v4
)
assert any(
    "expected exactly one oneOf branch to match, matched 0" in violation
    for violation in invalid_project_v4_violations
), (
    "why: Performance pattern_launch events reference slots, never pattern_id; "
    "remedy: retain per-event additionalProperties false"
)
overlong_performance_name = mutated(
    valid_project_v4,
    ["performances", 0, "name"],
    "x" * 65,
)
assert any(
    "does not match pattern" in violation
    for violation in json_schema.validate(overlong_performance_name, project_v4)
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
            valid_project_v4,
            ["performances", 0, "name"],
            accepted_name,
        ),
        project_v4,
        f"project-v4 64-code-point {case_name} Performance name",
    )
    violations = json_schema.validate(
        mutated(
            valid_project_v4,
            ["performances", 0, "name"],
            rejected_name,
        ),
        project_v4,
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
        valid_project_v4,
        ["performances", 0, "name"],
        non_bmp_name_64,
    ),
    project_v4,
    "project-v4 64-code-point non-BMP Performance name",
)
assert json_schema.validate(
    mutated(
        valid_project_v4,
        ["performances", 0, "name"],
        non_bmp_name_65,
    ),
    project_v4,
), (
    "why: PERFORMANCE_NAME_MAX counts Unicode code points, not UTF-8 bytes; "
    "remedy: reject a 65-code-point non-BMP name while accepting 64"
)
invalid_project_v3_violations = json_schema.validate(
    invalid_project_v3, project_v3
)
assert any(
    "duration_tick: above maximum 3840" in violation
    for violation in invalid_project_v3_violations
), invalid_project_v3_violations
assert any(
    "velocity: above maximum 127" in violation
    for violation in invalid_project_v3_violations
), invalid_project_v3_violations
invalid_event_v3 = invalid_project_v3["patterns"][0]["events"][0]
assert invalid_event_v3["duration_tick"] > (
    invalid_project_v3["patterns"][0]["bars"] * 3840
    - invalid_event_v3["onset_tick"]
)
invalid_project_v2_violations = json_schema.validate(
    invalid_project_v2, project_v2
)
assert any(
    "#/banks/0/pads/0/playback/gain_millidb: above maximum 6000" in violation
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
