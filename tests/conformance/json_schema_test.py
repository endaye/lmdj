#!/usr/bin/env python3
"""Unit tests for the minimal Contract schema validator."""

from pathlib import Path
import json
import sys


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "tests" / "conformance"))

import json_schema  # noqa: E402


def valid(instance, schema) -> None:
    errors = json_schema.validate(instance, schema)
    assert errors == [], errors


def invalid(instance, schema, fragment: str) -> None:
    errors = json_schema.validate(instance, schema)
    assert errors, f"expected a violation mentioning {fragment!r}"
    assert any(fragment in error for error in errors), (fragment, errors)


# type, including the JSON/Python boolean-is-not-integer trap
valid(3, {"type": "integer"})
valid(3.5, {"type": "number"})
valid(3, {"type": "number"})
invalid(True, {"type": "integer"}, "expected type")
invalid(True, {"type": "number"}, "expected type")
invalid(3, {"type": "boolean"}, "expected type")
invalid("3", {"type": "integer"}, "expected type")
valid(None, {"type": "null"})
invalid(None, {"type": "string"}, "expected type")
valid("x", {"type": ["string", "null"]})

# const and enum
valid("lmdj.capability.v2", {"const": "lmdj.capability.v2"})
invalid("lmdj.capability.v1", {"const": "lmdj.capability.v2"}, "expected const")
valid("b", {"enum": ["a", "b"]})
invalid("c", {"enum": ["a", "b"]}, "not one of the allowed options")

# strings
valid("audio_left", {"pattern": "^[a-z][a-z0-9_]*$"})
invalid("Audio-Left", {"pattern": "^[a-z][a-z0-9_]*$"}, "does not match pattern")
invalid("", {"minLength": 1}, "shorter than minLength")

# numbers
invalid(0, {"minimum": 1}, "below minimum")
invalid(5, {"maximum": 4}, "above maximum")
valid(1, {"minimum": 1, "maximum": 1})

# objects
person = {
    "type": "object",
    "required": ["name"],
    "properties": {"name": {"type": "string"}},
    "additionalProperties": False,
}
valid({"name": "a"}, person)
invalid({}, person, "missing required property 'name'")
invalid({"name": "a", "extra": 1}, person, "'extra' is not allowed")
invalid({"name": 1}, person, "expected type")

# additionalProperties as a schema, and propertyNames
counted = {"type": "object", "additionalProperties": {"type": "integer"}}
valid({"a": 1}, counted)
invalid({"a": "no"}, counted, "expected type")
named = {"type": "object", "propertyNames": {"pattern": "^[a-z]+$"}}
valid({"ok": 1}, named)
invalid({"NotOk": 1}, named, "does not match pattern")

# arrays
listed = {"type": "array", "items": {"type": "integer"}, "minItems": 1}
valid([1, 2], listed)
invalid([], listed, "fewer than minItems")
invalid([1, "x"], listed, "expected type")
invalid([1, 2, 3], {"type": "array", "maxItems": 2}, "more than maxItems")

# uniqueItems must compare structurally, not by identity
unique = {"type": "array", "uniqueItems": True}
valid([{"a": 1}, {"a": 2}], unique)
invalid([{"a": 1}, {"a": 1}], unique, "duplicate item")
invalid([{"a": 1, "b": 2}, {"b": 2, "a": 1}], unique, "duplicate item")

# contains / minContains / maxContains
containing = {
    "type": "array",
    "contains": {"const": "x"},
    "minContains": 2,
    "maxContains": 3,
}
valid(["x", "x", "y"], containing)
invalid(["x", "y"], containing, "needs at least 2")
invalid(["x", "x", "x", "x"], containing, "allows at most 3")

# $ref against local pointers
referenced = {
    "$defs": {"port": {"type": "string", "pattern": "^[a-z]+$"}},
    "type": "object",
    "properties": {"p": {"$ref": "#/$defs/port"}},
}
valid({"p": "drums"}, referenced)
invalid({"p": "Drums"}, referenced, "does not match pattern")

# allOf / oneOf / if-then
valid(4, {"allOf": [{"type": "integer"}, {"minimum": 4}]})
invalid(3, {"allOf": [{"type": "integer"}, {"minimum": 4}]}, "below minimum")
one_of = {"oneOf": [{"const": "a"}, {"const": "b"}]}
valid("a", one_of)
invalid("c", one_of, "matched 0")
invalid("a", {"oneOf": [{"const": "a"}, {"type": "string"}]}, "matched 2")
conditional = {
    "if": {"properties": {"kind": {"const": "sized"}}, "required": ["kind"]},
    "then": {"required": ["size"]},
}
valid({"kind": "sized", "size": 1}, conditional)
valid({"kind": "other"}, conditional)
invalid({"kind": "sized"}, conditional, "missing required property 'size'")

# An unimplemented keyword must fail loudly rather than be ignored.
try:
    json_schema.validate(1, {"multipleOf": 2})
except json_schema.SchemaError as error:
    assert "multipleOf" in str(error), error
else:  # pragma: no cover
    raise AssertionError("unsupported keyword was silently ignored")

# An unresolvable reference must fail loudly.
try:
    json_schema.validate({}, {"$ref": "#/$defs/missing"})
except json_schema.SchemaError as error:
    assert "unresolvable reference" in str(error), error
else:  # pragma: no cover
    raise AssertionError("dangling reference was silently ignored")

# Every shipped Contract must stay inside the implemented keyword subset.
contract_root = repo_root / "contracts"
contracts = sorted(contract_root.rglob("*.schema.json"))
assert contracts, "no Contract schemas were found"
for path in contracts:
    json_schema.assert_supported(
        json.loads(path.read_text(encoding="utf-8")),
        path.relative_to(repo_root).as_posix(),
    )

bundle_schema = json.loads(
    (contract_root / "project" / "lmdj.project-bundle.v1.schema.json").read_text(
        encoding="utf-8"
    )
)
project_v2_schema = json.loads(
    (contract_root / "project" / "lmdj.project.v2.schema.json").read_text(
        encoding="utf-8"
    )
)
bundle_fixture_root = repo_root / "tests" / "fixtures" / "contracts"
valid(
    json.loads(
        (bundle_fixture_root / "project-v2-valid.json").read_text(
            encoding="utf-8"
        )
    ),
    project_v2_schema,
)
invalid(
    json.loads(
        (bundle_fixture_root / "project-v2-invalid-playback.json").read_text(
            encoding="utf-8"
        )
    ),
    project_v2_schema,
    "above maximum 6000",
)
valid(
    json.loads(
        (bundle_fixture_root / "project-bundle-valid.json").read_text(
            encoding="utf-8"
        )
    ),
    bundle_schema,
)
invalid(
    json.loads(
        (
            bundle_fixture_root / "project-bundle-invalid-traversal.json"
        ).read_text(encoding="utf-8")
    ),
    bundle_schema,
    "does not match pattern",
)

print("contract schema validator tests: PASS")
