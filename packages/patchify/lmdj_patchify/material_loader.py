from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import jsonschema

from lmdj_core_models.materials import (
    MaterialPackage,
    load_material_schema,
    material_package_from_dict,
)


@dataclass(frozen=True)
class LoadedMaterialPackage:
    root: Path
    package: MaterialPackage


def load_material_package(package_dir: Path) -> LoadedMaterialPackage:
    root = package_dir.resolve()
    manifest = root / "materials.json"
    if not manifest.is_file():
        raise ValueError("Missing required file: materials.json")
    try:
        raw = json.loads(manifest.read_text())
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError(f"invalid materials.json: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("materials.json must contain an object")
    try:
        jsonschema.validate(raw, load_material_schema())
        package = material_package_from_dict(raw)
    except (
        jsonschema.ValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(f"invalid materials.json: {error}") from error

    _resolve_required(root, package.timing.artifact, "timing artifact")
    for material in package.materials:
        _resolve_required(root, material.audio_path, "material audio")
    return LoadedMaterialPackage(root=root, package=package)


def _resolve_required(root: Path, relative: str, label: str) -> Path:
    resolved = (root / relative).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError(f"{label} escapes package root: {relative}")
    if not resolved.is_file():
        raise ValueError(f"missing {label}: {relative}")
    return resolved
