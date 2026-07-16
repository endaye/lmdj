from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from lmdj_audio_worker.pipeline_from_stems import parity

SR = 44100


def make_package(root: Path, score: float = 0.61) -> Path:
    root.mkdir(parents=True)
    (root / "report.json").write_text(json.dumps({
        "song_id": "t", "status": "passed", "score": score, "threshold": 0.5,
        "bpm": 90.0, "loop_start_sec": 1.234, "loop_seconds": 10.667,
        "n_samples": 2, "n_notes": 3,
        "lanes": [{"lane": 0, "name": "kick"}, {"lane": 1, "name": "bass"}],
        "attempts": [], "elapsed_sec": 5.0}))
    (root / "lanes.json").write_text(json.dumps({
        "bpm": 90.0, "bars": 4.0, "beats": 16, "loop_seconds": 10.667,
        "lanes": [{"lane": 0, "name": "kick", "kind": "drum", "pitch": 36,
                   "sample": "samples/kick.wav"},
                  {"lane": 1, "name": "bass", "kind": "long", "pitch": 48,
                   "sample": "samples/bass.wav"}]}))
    pm = pretty_midi.PrettyMIDI(initial_tempo=90.0)
    inst = pretty_midi.Instrument(program=0, name="lmdj-chart")
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=0.0, end=0.1))
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=48, start=0.5, end=1.0))
    pm.instruments.append(inst)
    pm.write(str(root / "chart.mid"))
    rng = np.random.default_rng(7)
    for rel in ("loop_preview.wav", "render_preview.wav",
                "samples/kick.wav", "samples/bass.wav"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, rng.uniform(-0.5, 0.5, (SR, 2)).astype(np.float32),
                 SR, subtype="FLOAT")
    return root


@pytest.fixture()
def twin_packages(tmp_path):
    old = make_package(tmp_path / "old")
    new = tmp_path / "new"
    shutil.copytree(old, new)
    return old, new


def test_identical_packages_pass(twin_packages):
    old, new = twin_packages
    assert parity.compare_packages(old, new) == []


def test_score_within_tolerance_passes(twin_packages):
    old, new = twin_packages
    report = json.loads((new / "report.json").read_text())
    report["score"] = 0.61005  # |Δ|=5e-5 ≤ 1e-4
    (new / "report.json").write_text(json.dumps(report))
    assert parity.compare_packages(old, new) == []


def test_score_beyond_tolerance_fails(twin_packages):
    old, new = twin_packages
    report = json.loads((new / "report.json").read_text())
    report["score"] = 0.62
    (new / "report.json").write_text(json.dumps(report))
    assert any("score" in e for e in parity.compare_packages(old, new))


def test_lane_name_mismatch_fails(twin_packages):
    old, new = twin_packages
    lanes = json.loads((new / "lanes.json").read_text())
    lanes["lanes"][0]["name"] = "snare"
    (new / "lanes.json").write_text(json.dumps(lanes))
    assert any("lanes" in e for e in parity.compare_packages(old, new))


def test_audio_perturbation_fails(twin_packages):
    old, new = twin_packages
    data, sr = sf.read(new / "samples" / "kick.wav", dtype="float32",
                       always_2d=True)
    data[100, 0] += 1e-3  # 超过 1e-5 容差
    sf.write(new / "samples" / "kick.wav", data, sr, subtype="FLOAT")
    assert any("kick" in e for e in parity.compare_packages(old, new))


def test_sample_set_mismatch_fails(twin_packages):
    old, new = twin_packages
    (new / "samples" / "bass.wav").unlink()
    assert any("bass" in e for e in parity.compare_packages(old, new))


def test_midi_note_mismatch_fails(twin_packages):
    old, new = twin_packages
    pm = pretty_midi.PrettyMIDI(initial_tempo=90.0)
    inst = pretty_midi.Instrument(program=0, name="lmdj-chart")
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=38, start=0.0, end=0.1))
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=48, start=0.5, end=1.0))
    pm.instruments.append(inst)
    pm.write(str(new / "chart.mid"))
    assert any("MIDI" in e for e in parity.compare_packages(old, new))
