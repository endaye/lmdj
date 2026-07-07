import json
from pathlib import Path

import pretty_midi
import pytest

from lmdj_patchify.package_loader import load_package


def test_load_package_matches_golden_lanes(golden_package: Path):
    loaded = load_package(golden_package)
    raw = json.loads((golden_package / "lanes.json").read_text())

    assert loaded.song_id == "testsong"
    assert loaded.bpm == float(raw["bpm"])
    assert loaded.beats == int(raw["beats"])
    assert loaded.loop_seconds == float(raw["loop_seconds"])
    # loader 输出与 lanes.json 逐行对应（契约 key 是 sample）
    assert [(e.name, e.pitch, e.lane, e.source_path) for e in loaded.elements] == [
        (r["name"], r["pitch"], r["lane"], r["sample"]) for r in raw["lanes"]
    ]


def test_load_package_parses_normalized_notes(golden_package: Path):
    loaded = load_package(golden_package)
    length_steps = loaded.beats * 4
    element_ids = {e.element_id for e in loaded.elements}

    assert loaded.notes, "golden chart.mid must contain notes"
    for note in loaded.notes:
        assert 0 <= note.step < length_steps
        assert note.element_id in element_ids
        assert note.velocity == 100          # demo 硬编码
    assert loaded.notes == sorted(loaded.notes, key=lambda n: (n.step, n.pitch))


def test_load_package_accepts_legacy_path_key(golden_package: Path):
    raw = json.loads((golden_package / "lanes.json").read_text())
    for row in raw["lanes"]:
        row["path"] = row.pop("sample")      # 兼容读 path
    (golden_package / "lanes.json").write_text(json.dumps(raw))

    loaded = load_package(golden_package)
    assert loaded.elements[0].source_path == raw["lanes"][0]["path"]


def test_load_package_rejects_missing_sample(golden_package: Path):
    raw = json.loads((golden_package / "lanes.json").read_text())
    (golden_package / raw["lanes"][0]["sample"]).unlink()

    with pytest.raises(ValueError, match="Missing sample file"):
        load_package(golden_package)


def test_load_package_rejects_pitch_not_declared_in_lanes(golden_package: Path):
    midi = pretty_midi.PrettyMIDI(initial_tempo=90)
    inst = pretty_midi.Instrument(program=0, name="broken")
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=127, start=0.0, end=0.1))
    midi.instruments.append(inst)
    midi.write(str(golden_package / "chart.mid"))

    with pytest.raises(ValueError, match="MIDI pitches missing from lanes.json"):
        load_package(golden_package)


def test_load_package_rejects_missing_required_file(golden_package: Path):
    (golden_package / "lanes.json").unlink()

    with pytest.raises(ValueError, match="Missing required file"):
        load_package(golden_package)


def test_load_package_rejects_missing_beats_field(golden_package: Path):
    raw = json.loads((golden_package / "lanes.json").read_text())
    del raw["beats"]
    (golden_package / "lanes.json").write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="missing required field: beats"):
        load_package(golden_package)


def test_load_package_rejects_zero_loop_seconds(golden_package: Path):
    raw = json.loads((golden_package / "lanes.json").read_text())
    raw["loop_seconds"] = 0
    (golden_package / "lanes.json").write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="loop_seconds must be > 0"):
        load_package(golden_package)


def test_load_package_rejects_lane_row_missing_pitch(golden_package: Path):
    raw = json.loads((golden_package / "lanes.json").read_text())
    del raw["lanes"][0]["pitch"]
    (golden_package / "lanes.json").write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="missing required field: pitch"):
        load_package(golden_package)
