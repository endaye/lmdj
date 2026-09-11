#!/usr/bin/env python3
"""Minimal JSON Schema validator for LMDJ Contract documents.

The repository deliberately keeps the Python side free of third-party
dependencies, so this implements exactly the JSON Schema 2020-12 subset that
`contracts/**/*.schema.json` actually uses. Every supported keyword is listed
in SUPPORTED_KEYWORDS, and `assert_supported` fails loudly when a Contract
starts using a keyword this validator would otherwise ignore. Silently
ignoring an unknown keyword would make a Contract look enforced when it is not.
"""

from __future__ import annotations

import json
import re
from typing import Any


class SchemaError(RuntimeError):
    """The schema document itself is unusable."""


# Keywords that constrain an instance.
ASSERTION_KEYWORDS = frozenset(
    {
        "type",
        "const",
        "enum",
        "properties",
        "required",
        "additionalProperties",
        "propertyNames",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "contains",
        "minContains",
        "maxContains",
        "pattern",
        "minLength",
        "minimum",
        "maximum",
        "allOf",
        "anyOf",
        "oneOf",
        "if",
        "then",
        "else",
        "$ref",
    }
)

# Keywords carrying no assertion. Listed so they are knowingly ignored.
ANNOTATION_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$defs",
        "definitions",
        "title",
        "description",
        "examples",
        "default",
        "x-lmdj-contract-version",
    }
)

SUPPORTED_KEYWORDS = ASSERTION_KEYWORDS | ANNOTATION_KEYWORDS

_TYPES: dict[str, Any] = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _is_type(value: Any, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    expected = _TYPES.get(name)
    if expected is None:
        raise SchemaError(f"unsupported type: {name}")
    if expected is bool:
        return isinstance(value, bool)
    if expected is type(None):
        return value is None
    if expected is dict or expected is list:
        return isinstance(value, expected)
    return isinstance(value, expected) and not isinstance(value, bool)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def assert_supported(schema: Any, where: str = "#") -> None:
    """Fail if the schema uses a keyword this validator does not implement."""
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise SchemaError(f"{where}: schema must be an object or boolean")
    for key, value in schema.items():
        if key not in SUPPORTED_KEYWORDS:
            raise SchemaError(f"{where}: unsupported schema keyword: {key}")
        child = f"{where}/{key}"
        if key in ("properties", "$defs", "definitions"):
            if not isinstance(value, dict):
                raise SchemaError(f"{child}: expected an object")
            for name, sub in value.items():
                assert_supported(sub, f"{child}/{name}")
        elif key in ("allOf", "anyOf", "oneOf"):
            if not isinstance(value, list):
                raise SchemaError(f"{child}: expected an array")
            for index, sub in enumerate(value):
                assert_supported(sub, f"{child}/{index}")
        elif key in (
            "items",
            "contains",
            "propertyNames",
            "if",
            "then",
            "else",
        ):
            assert_supported(value, child)
        elif key == "additionalProperties" and not isinstance(value, bool):
            assert_supported(value, child)


def _resolve(root: Any, ref: str) -> Any:
    if not ref.startswith("#/"):
        raise SchemaError(f"only local JSON pointers are supported: {ref}")
    node = root
    for raw in ref[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or token not in node:
            raise SchemaError(f"unresolvable reference: {ref}")
        node = node[token]
    return node


def _validate(
    instance: Any,
    schema: Any,
    root: Any,
    path: str,
    errors: list[str],
) -> None:
    if schema is True or schema == {}:
        return
    if schema is False:
        errors.append(f"{path}: no value is allowed here")
        return

    if "$ref" in schema:
        # 2020-12 allows siblings alongside $ref; keep checking them below.
        _validate(instance, _resolve(root, schema["$ref"]), root, path, errors)

    if "type" in schema:
        declared = schema["type"]
        names = declared if isinstance(declared, list) else [declared]
        if not any(_is_type(instance, name) for name in names):
            errors.append(f"{path}: expected type {declared}")
            return

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and not any(
        instance == option for option in schema["enum"]
    ):
        errors.append(f"{path}: value is not one of the allowed options")

    if isinstance(instance, str):
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, instance) is None:
            errors.append(f"{path}: does not match pattern {pattern}")
        minimum_length = schema.get("minLength")
        if minimum_length is not None and len(instance) < minimum_length:
            errors.append(f"{path}: shorter than minLength {minimum_length}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            errors.append(f"{path}: below minimum {minimum}")
        maximum = schema.get("maximum")
        if maximum is not None and instance > maximum:
            errors.append(f"{path}: above maximum {maximum}")

    if isinstance(instance, dict):
        _validate_object(instance, schema, root, path, errors)
    if isinstance(instance, list):
        _validate_array(instance, schema, root, path, errors)

    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword not in schema:
            continue
        matched = 0
        for index, sub in enumerate(schema[keyword]):
            branch: list[str] = []
            _validate(instance, sub, root, f"{path}/{keyword}/{index}", branch)
            if branch:
                if keyword == "allOf":
                    errors.extend(branch)
            else:
                matched += 1
        if keyword == "anyOf" and matched == 0:
            errors.append(
                f"{path}: expected at least one anyOf branch to match"
            )
        if keyword == "oneOf" and matched != 1:
            errors.append(
                f"{path}: expected exactly one oneOf branch to match, "
                f"matched {matched}"
            )

    if "if" in schema:
        probe: list[str] = []
        _validate(instance, schema["if"], root, path, probe)
        follow = "then" if not probe else "else"
        if follow in schema:
            _validate(instance, schema[follow], root, path, errors)


def _validate_object(
    instance: dict,
    schema: dict,
    root: Any,
    path: str,
    errors: list[str],
) -> None:
    properties = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in instance:
            errors.append(f"{path}: missing required property {name!r}")

    for name, value in instance.items():
        child = f"{path}/{name}"
        if name in properties:
            _validate(value, properties[name], root, child, errors)
            continue
        additional = schema.get("additionalProperties")
        if additional is False:
            errors.append(f"{path}: property {name!r} is not allowed")
        elif isinstance(additional, dict):
            _validate(value, additional, root, child, errors)

    names_schema = schema.get("propertyNames")
    if names_schema is not None:
        for name in instance:
            _validate(name, names_schema, root, f"{path}/{name}", errors)


def _validate_array(
    instance: list,
    schema: dict,
    root: Any,
    path: str,
    errors: list[str],
) -> None:
    item_schema = schema.get("items")
    if item_schema is not None:
        for index, value in enumerate(instance):
            _validate(value, item_schema, root, f"{path}/{index}", errors)

    minimum_items = schema.get("minItems")
    if minimum_items is not None and len(instance) < minimum_items:
        errors.append(f"{path}: fewer than minItems {minimum_items}")
    maximum_items = schema.get("maxItems")
    if maximum_items is not None and len(instance) > maximum_items:
        errors.append(f"{path}: more than maxItems {maximum_items}")

    if schema.get("uniqueItems") is True:
        seen: set[str] = set()
        for value in instance:
            key = _canonical(value)
            if key in seen:
                errors.append(f"{path}: duplicate item {key}")
                break
            seen.add(key)

    contains = schema.get("contains")
    if contains is None:
        return
    matches = 0
    for value in instance:
        probe: list[str] = []
        _validate(value, contains, root, path, probe)
        if not probe:
            matches += 1
    minimum_contains = schema.get("minContains", 1)
    maximum_contains = schema.get("maxContains")
    if matches < minimum_contains:
        errors.append(
            f"{path}: matched contains {matches} times, "
            f"needs at least {minimum_contains}"
        )
    if maximum_contains is not None and matches > maximum_contains:
        errors.append(
            f"{path}: matched contains {matches} times, "
            f"allows at most {maximum_contains}"
        )


def validate(instance: Any, schema: Any) -> list[str]:
    """Return a list of violation messages; empty means the instance is valid."""
    assert_supported(schema)
    errors: list[str] = []
    _validate(instance, schema, schema, "#", errors)
    return errors


def check(instance: Any, schema: Any, label: str) -> None:
    """Raise AssertionError with every violation if the instance is invalid."""
    errors = validate(instance, schema)
    assert not errors, f"{label} failed schema validation:\n  " + "\n  ".join(
        errors
    )
