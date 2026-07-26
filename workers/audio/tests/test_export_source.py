from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from lmdj_audio_worker.export_source import build_export_source, write_export_source
from lmdj_audio_worker.music_metadata import KeyEstimate
from lmdj_core_models.model import Pattern
from lmdj_patchify.patchify import patchify_package

from tests.conftest import GOLDEN


def _package_with_patch(tmp_path: Path):
    package_dir = tmp_path / "package"
    shutil.copytree(GOLDEN, package_dir)
    stems = package_dir / "stems"
    stems.mkdir()
    (stems / "drums.wav").write_bytes(b"real drums")
    (stems / "notes.txt").write_text("not a stem")
    return package_dir, patchify_package(package_dir)


def test_build_export_source_inventories_patch_and_real_files(tmp_path: Path) -> None:
    package_dir, patch = _package_with_patch(tmp_path)

    source = build_export_source(
        package_dir,
        patch,
        KeyEstimate(value="A minor", confidence=0.72),
        [],
    )

    assert source["schema"] == "lmdj.creator-export-source.v1"
    assert source["patch"] == "patch.json"
    assert source["stems"] == ["stems/drums.wav"]
    assert source["samples"] == sorted({element.source_path for element in patch.elements})
    assert source["midi"] == ["chart.mid"]
    assert source["timing"] == []
    assert source["provenance"] == {
        "pipeline": "legacy",
        "extraction_config_version": None,
    }
    assert source["music"]["bpm"] == patch.bpm
    assert source["music"]["key"] == {"value": "A minor", "confidence": 0.72}
    assert source["music"]["time_signature"] == {
        "numerator": 4,
        "denominator": 4,
        "source": "fixed-v1",
    }
    active_pattern_id = patch.scenes[0].pattern_ids[0]
    active_pattern = next(p for p in patch.patterns if p.pattern_id == active_pattern_id)
    assert source["music"]["loop"] == {
        "seconds": patch.loop_seconds,
        "steps": active_pattern.length_steps,
        "beats": active_pattern.length_steps / 4,
        "bars": active_pattern.length_steps / 16,
    }
    assert source["warnings"] == []


def test_build_export_source_uses_active_scene_pattern_for_loop(tmp_path: Path) -> None:
    package_dir, patch = _package_with_patch(tmp_path)
    decoy = Pattern(
        pattern_id="decoy",
        name="Decoy",
        source={"kind": "midi", "path": "decoy.mid"},
        resolution="1/16",
        length_steps=8,
        notes=[],
    )
    active_patch = replace(patch, patterns=[decoy, *patch.patterns])

    source = build_export_source(
        package_dir,
        active_patch,
        KeyEstimate(value="C major", confidence=0.8),
        [],
    )

    assert source["music"]["loop"]["steps"] == patch.patterns[0].length_steps
    assert source["midi"] == ["chart.mid", "decoy.mid"]


def test_build_export_source_marks_missing_key_with_warning(tmp_path: Path) -> None:
    package_dir, patch = _package_with_patch(tmp_path)

    source = build_export_source(package_dir, patch, None, ["analysis failed"])

    assert source["music"]["key"] is None
    assert source["warnings"] == ["analysis failed", "key analysis unavailable"]


@pytest.mark.parametrize(
    "unsafe_path",
    ["/tmp/outside.wav", "../outside.wav", "samples/../outside.wav"],
)
def test_build_export_source_rejects_unsafe_sample_paths(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    package_dir, patch = _package_with_patch(tmp_path)
    unsafe_element = replace(patch.elements[0], source_path=unsafe_path)
    unsafe_patch = replace(patch, elements=[unsafe_element, *patch.elements[1:]])

    with pytest.raises(ValueError, match="unsafe export source path"):
        build_export_source(package_dir, unsafe_patch, None, [])


def test_build_export_source_rejects_stem_symlink_outside_package(tmp_path: Path) -> None:
    package_dir, patch = _package_with_patch(tmp_path)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"outside")
    (package_dir / "stems" / "escape.wav").symlink_to(outside)

    with pytest.raises(ValueError, match="unsafe export source path"):
        build_export_source(package_dir, patch, None, [])


def test_write_export_source_writes_stable_json_file(tmp_path: Path) -> None:
    package_dir, patch = _package_with_patch(tmp_path)
    source = build_export_source(
        package_dir,
        patch,
        KeyEstimate(value="C major", confidence=0.4),
        [],
    )

    output = write_export_source(package_dir, source)

    assert output == package_dir / "export-source.json"
    assert json.loads(output.read_text()) == source
