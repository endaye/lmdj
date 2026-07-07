from __future__ import annotations

import hashlib
from pathlib import Path

from lmdj_core_models.model import Patch, Pattern, RenderRef, Scene, write_patch_json
from lmdj_patchify.package_loader import load_package
from lmdj_patchify.pad_mapper import detect_profile, map_focus_pads


def patchify_package(package_dir: Path, out_path: Path | None = None) -> Patch:
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


def _content_hash(root: Path) -> str:
    """patch_id 的内容派生部分：同输入必得同 id（worker 重跑幂等的地基）。"""
    digest = hashlib.sha256()
    digest.update((root / "lanes.json").read_bytes())
    digest.update((root / "chart.mid").read_bytes())
    return digest.hexdigest()[:8]


def _discover_renders(root: Path) -> list[RenderRef]:
    renders: list[RenderRef] = []
    for kind, filename in [
        ("loop_preview", "loop_preview.wav"),
        ("render_preview", "render_preview.wav"),
    ]:
        if (root / filename).exists():
            renders.append(RenderRef(kind=kind, path=filename))
    return renders
