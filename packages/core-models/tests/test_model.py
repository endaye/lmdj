import json
from pathlib import Path

from lmdj_core_models.model import (
    Element, Note, Pad, Patch, Pattern, RenderRef, Scene, write_patch_json,
)


def _sample_patch() -> Patch:
    element = Element(
        element_id="el_kick", name="kick", kind="drum",
        source_path="samples/kick.wav", pitch=36, lane=0, role="drums",
    )
    pattern = Pattern(
        pattern_id="pattern_original", name="Original",
        source={"kind": "midi", "path": "chart.mid"},
        resolution="1/16", length_steps=64,
        notes=[Note(element_id="el_kick", lane=0, pitch=36, step=0, velocity=100)],
    )
    return Patch(
        patch_id="testsong-abcd1234",
        source={"type": "pipeline_package", "song_id": "testsong"},
        bpm=90.0, loop_seconds=10.667,
        elements=[element],
        patterns=[pattern],
        pads=[Pad(0, "Drums", "kick", "trigger_group", "el_kick",
                  {"trigger": "one_shot", "quantize": "1/16", "element_ids": ["el_kick"]})],
        scenes=[Scene("scene_original", "Original", [0], ["pattern_original"],
                      "Pipeline default scene")],
        renders=[RenderRef(kind="loop_preview", path="loop_preview.wav")],
        metadata={"status": "passed", "score": 0.8},
    )


def test_patch_model_writes_stable_patch_json(tmp_path: Path):
    out_path = tmp_path / "patch.json"
    write_patch_json(_sample_patch(), out_path)
    data = json.loads(out_path.read_text())

    assert data["schema"] == "lmdj.patch.v1"
    assert data["patch_id"] == "testsong-abcd1234"
    assert data["patterns"][0]["length_steps"] == 64
    assert data["patterns"][0]["notes"][0] == {
        "element_id": "el_kick", "lane": 0, "pitch": 36, "step": 0, "velocity": 100,
    }
    assert data["pads"][0]["behavior"]["element_ids"] == ["el_kick"]
    assert data["scenes"][0]["pattern_ids"] == ["pattern_original"]
    assert data["elements"][0]["source_path"] == "samples/kick.wav"


def test_write_patch_json_is_deterministic(tmp_path: Path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    write_patch_json(_sample_patch(), a)
    write_patch_json(_sample_patch(), b)
    assert a.read_bytes() == b.read_bytes()
