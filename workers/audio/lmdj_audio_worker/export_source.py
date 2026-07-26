from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lmdj_audio_worker.music_metadata import KeyEstimate
from lmdj_core_models.model import Patch, Pattern

SCHEMA = "lmdj.creator-export-source.v1"
OUTPUT_NAME = "export-source.json"
MISSING_KEY_WARNING = "key analysis unavailable"


def _safe_relative_path(package_root: Path, value: str | Path) -> str:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe export source path: {value}")
    resolved = (package_root / relative).resolve()
    if resolved == package_root or not resolved.is_relative_to(package_root):
        raise ValueError(f"unsafe export source path: {value}")
    return resolved.relative_to(package_root).as_posix()


def _active_pattern(patch: Patch) -> Pattern:
    if not patch.scenes or not patch.scenes[0].pattern_ids:
        raise ValueError("Patch has no active scene pattern")
    active_pattern_id = patch.scenes[0].pattern_ids[0]
    try:
        return next(
            pattern for pattern in patch.patterns
            if pattern.pattern_id == active_pattern_id
        )
    except StopIteration as error:
        raise ValueError(
            f"active scene references unknown pattern: {active_pattern_id}",
        ) from error


def build_export_source(
    package_dir: Path,
    patch: Patch,
    key: KeyEstimate | None,
    warnings: list[str],
) -> dict[str, Any]:
    package_root = package_dir.resolve()
    patch_path = _safe_relative_path(package_root, "patch.json")
    samples = sorted({
        _safe_relative_path(package_root, element.source_path)
        for element in patch.elements
    })
    midi = sorted({
        _safe_relative_path(package_root, pattern.source["path"])
        for pattern in patch.patterns
        if pattern.source.get("kind") == "midi" and pattern.source.get("path")
    })
    stems = sorted(
        _safe_relative_path(package_root, stem.relative_to(package_root))
        for stem in (package_root / "stems").glob("*.wav")
        if stem.is_file()
    )
    timing = (
        [_safe_relative_path(package_root, "timing.json")]
        if (package_root / "timing.json").is_file()
        else []
    )
    active_pattern = _active_pattern(patch)
    steps = active_pattern.length_steps
    source_warnings = list(warnings)
    if key is None and MISSING_KEY_WARNING not in source_warnings:
        source_warnings.append(MISSING_KEY_WARNING)
    return {
        "schema": SCHEMA,
        "patch": patch_path,
        "stems": stems,
        "samples": samples,
        "midi": midi,
        "timing": timing,
        "provenance": {
            "pipeline": patch.metadata.get("pipeline", "legacy"),
            "extraction_config_version": patch.metadata.get(
                "extraction_config_version"
            ),
        },
        "music": {
            "bpm": patch.bpm,
            "key": (
                {"value": key.value, "confidence": key.confidence}
                if key is not None
                else None
            ),
            "time_signature": {
                "numerator": 4,
                "denominator": 4,
                "source": "fixed-v1",
            },
            "loop": {
                "seconds": patch.loop_seconds,
                "steps": steps,
                "beats": steps / 4,
                "bars": steps / 16,
            },
        },
        "warnings": source_warnings,
    }


def write_export_source(package_dir: Path, source: dict[str, Any]) -> Path:
    output = package_dir / OUTPUT_NAME
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(output)
    return output
