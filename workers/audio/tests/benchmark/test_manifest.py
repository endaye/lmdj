from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmdj_audio_worker.benchmark import manifest


def make_manifest(**overrides) -> dict:
    data = {
        "schema_version": "lmdj.benchmark-manifest.v1",
        "dataset_id": "suno-v1",
        "tracks": [
            {"id": "boom-bap-01", "input": "suno/boom-bap/boom-bap-01.mp3",
             "split": "full", "tags": ["hiphop", "drums-heavy"],
             "has_ground_truth": False, "ground_truth": None},
            {"id": "gt-track", "input": "musdb/mix.wav", "split": "perf",
             "tags": [], "has_ground_truth": True,
             "ground_truth": {k: f"musdb/stems/{k}.wav"
                              for k in ("drums", "bass", "vocals", "other")}},
        ],
    }
    data.update(overrides)
    return data


def write(tmp_path, data) -> Path:
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data))
    return path


def test_valid_manifest_loads(tmp_path):
    m = manifest.load_manifest(write(tmp_path, make_manifest()))
    assert m.dataset_id == "suno-v1"
    assert m.tracks[0].id == "boom-bap-01"
    assert m.tracks[1].ground_truth["drums"] == "musdb/stems/drums.wav"


def test_duplicate_track_ids_rejected(tmp_path):
    data = make_manifest()
    data["tracks"].append(dict(data["tracks"][0]))
    with pytest.raises(manifest.ManifestError) as exc:
        manifest.load_manifest(write(tmp_path, data))
    assert any("boom-bap-01" in e for e in exc.value.errors)


def test_absolute_path_rejected(tmp_path):
    data = make_manifest()
    data["tracks"][0]["input"] = "/etc/passwd"
    with pytest.raises(manifest.ManifestError):
        manifest.load_manifest(write(tmp_path, data))


def test_dotdot_path_rejected(tmp_path):
    data = make_manifest()
    data["tracks"][0]["input"] = "../outside.mp3"
    with pytest.raises(manifest.ManifestError):
        manifest.load_manifest(write(tmp_path, data))


def test_bad_split_rejected(tmp_path):
    data = make_manifest()
    data["tracks"][0]["split"] = "extra"
    with pytest.raises(manifest.ManifestError):
        manifest.load_manifest(write(tmp_path, data))


def test_ground_truth_requires_four_stems(tmp_path):
    data = make_manifest()
    del data["tracks"][1]["ground_truth"]["vocals"]
    with pytest.raises(manifest.ManifestError) as exc:
        manifest.load_manifest(write(tmp_path, data))
    assert any("vocals" in e for e in exc.value.errors)


def test_no_gt_requires_null(tmp_path):
    data = make_manifest()
    data["tracks"][0]["ground_truth"] = {"drums": "x.wav"}
    with pytest.raises(manifest.ManifestError):
        manifest.load_manifest(write(tmp_path, data))


def test_wrong_schema_version_rejected(tmp_path):
    with pytest.raises(manifest.ManifestError):
        manifest.load_manifest(
            write(tmp_path, make_manifest(schema_version="v2")))


def test_data_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(tmp_path))
    assert manifest.data_root() == tmp_path
    monkeypatch.delenv("LMDJ_BENCH_DATA_ROOT")
    with pytest.raises(manifest.ManifestError):
        manifest.data_root()


def test_resolve_input(monkeypatch, tmp_path):
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(tmp_path))
    track = manifest.load_manifest(write(tmp_path, make_manifest())).tracks[0]
    with pytest.raises(manifest.ManifestError):
        manifest.resolve_input(track)          # 文件不存在
    target = tmp_path / "suno" / "boom-bap" / "boom-bap-01.mp3"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"mp3")
    assert manifest.resolve_input(track) == target


def test_shipped_example_manifest_valid():
    shipped = (Path(__file__).resolve().parents[2]
               / "config" / "benchmark" / "example.manifest.json")
    m = manifest.load_manifest(shipped)
    assert m.dataset_id == "example"
    assert all(t.split in manifest.SPLITS for t in m.tracks)
