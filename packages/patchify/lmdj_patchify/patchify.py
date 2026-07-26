from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from lmdj_core_models.model import Patch, Pattern, RenderRef, Scene, write_patch_json
from lmdj_patchify.material_loader import load_material_package
from lmdj_patchify.material_mapper import map_materials
from lmdj_patchify.material_midi import write_material_midi
from lmdj_patchify.package_loader import load_package
from lmdj_patchify.pad_mapper import detect_profile, map_focus_pads


def patchify_package(package_dir: Path, out_path: Path | None = None) -> Patch:
    root = package_dir.resolve()
    if (root / "materials.json").is_file():
        return _patchify_material_package(root, out_path)

    loaded = load_package(package_dir)
    profile = detect_profile(loaded.elements)
    if profile != "standard":
        raise ValueError(
            f"unsupported package profile: {profile} (v1 only maps standard packages)")

    pads = map_focus_pads(loaded.elements)
    pattern = Pattern(
        pattern_id="pattern_original",
        name="Original",
        source={"kind": "midi", "path": "chart.mid"},
        resolution="1/16",
        length_steps=loaded.beats * 4,
        notes=loaded.notes,
    )
    mapped_ids = {eid for pad in pads for eid in pad.behavior.get("element_ids", [])}
    patch = Patch(
        patch_id=f"{loaded.song_id}-{_content_hash(loaded.root)}",
        source={"type": "pipeline_package", "song_id": loaded.song_id},
        bpm=loaded.bpm,
        loop_seconds=loaded.loop_seconds,
        elements=loaded.elements,
        patterns=[pattern],
        pads=pads,
        scenes=[
            Scene(
                scene_id="scene_original",
                name="Original",
                pad_indexes=[pad.index for pad in pads],
                pattern_ids=[pattern.pattern_id],
                intent="Pipeline default scene",
            )
        ],
        renders=_discover_renders(loaded.root),
        metadata={
            "source_package": loaded.root.name,
            "status": loaded.report.get("status"),
            "score": loaded.report.get("score"),
            "midi_pitches": sorted(loaded.midi_pitches),
            "unmapped_element_ids": sorted(
                e.element_id for e in loaded.elements if e.element_id not in mapped_ids),
        },
    )
    write_patch_json(patch, out_path or loaded.root / "patch.json")
    return patch


def _patchify_material_package(
    package_dir: Path,
    out_path: Path | None,
) -> Patch:
    loaded = load_material_package(package_dir)
    package = loaded.package
    elements, pads, notes = map_materials(package)
    chart_path = loaded.root / "chart.mid"
    write_material_midi(chart_path, bpm=package.timing.bpm, notes=notes)
    pattern = Pattern(
        pattern_id=package.pattern.pattern_id,
        name="Primary",
        source={"kind": "midi", "path": "chart.mid"},
        resolution="1/16",
        length_steps=package.pattern.length_steps,
        notes=notes,
    )
    source_id = f"source-{package.source.audio_sha256}"
    patch = Patch(
        patch_id=f"{source_id}-{_material_hash(package.canonical_identity_bytes())}",
        source={
            "type": "material_package",
            "song_id": source_id,
            "pipeline": package.provenance.pipeline,
        },
        bpm=package.timing.bpm,
        loop_seconds=(
            package.pattern.length_steps
            * 60.0
            / package.timing.bpm
            / package.timing.grid_per_beat
        ),
        elements=elements,
        patterns=[pattern],
        pads=pads,
        scenes=[
            Scene(
                scene_id="scene_primary",
                name="Primary",
                pad_indexes=list(range(16)),
                pattern_ids=[pattern.pattern_id],
                intent="Material pipeline primary scene",
            )
        ],
        renders=_discover_renders(loaded.root),
        metadata={
            "source_package": loaded.root.name,
            "status": (
                "needs_review"
                if any(material.quality.warnings for material in package.materials)
                else "passed"
            ),
            "pipeline": package.provenance.pipeline,
            "material_count": len(package.materials),
            "extraction_config_version": (
                package.provenance.extraction_config_version
            ),
        },
    )
    _write_patch_atomic(patch, out_path or loaded.root / "patch.json")
    return patch


def _content_hash(root: Path) -> str:
    """patch_id 的内容派生部分：同输入必得同 id（worker 重跑幂等的地基）。"""
    digest = hashlib.sha256()
    digest.update((root / "lanes.json").read_bytes())
    digest.update((root / "chart.mid").read_bytes())
    return digest.hexdigest()[:8]


def _material_hash(canonical_identity: bytes) -> str:
    return hashlib.sha256(canonical_identity).hexdigest()[:8]


def _write_patch_atomic(patch: Patch, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(patch.to_dict(), indent=2, ensure_ascii=False) + "\n"
    )
    os.replace(temporary, path)


def _discover_renders(root: Path) -> list[RenderRef]:
    renders: list[RenderRef] = []
    for kind, filename in [
        ("loop_preview", "loop_preview.wav"),
        ("render_preview", "render_preview.wav"),
    ]:
        if (root / filename).exists():
            renders.append(RenderRef(kind=kind, path=filename))
    return renders
