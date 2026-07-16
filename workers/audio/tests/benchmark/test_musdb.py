from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmdj_audio_worker.benchmark import musdb
from lmdj_audio_worker.benchmark.manifest import load_manifest

STEMS = ("mixture", "drums", "bass", "other", "vocals")


def make_musdb_tree(root: Path, subset: str, names: list[str],
                    drop: dict | None = None) -> None:
    """构造假 MUSDB18HQ 目录（wav 内容无所谓，生成器只看文件存在性）。"""
    drop = drop or {}
    for name in names:
        track_dir = root / subset / name
        track_dir.mkdir(parents=True)
        for stem in STEMS:
            if stem in drop.get(name, ()):
                continue
            (track_dir / f"{stem}.wav").write_bytes(b"RIFF")


def test_builds_valid_manifest(tmp_path):
    make_musdb_tree(tmp_path, "test", ["Al James - Schoolboy Facination",
                                       "BKS - Too Much"])
    data = musdb.build_musdb_manifest(tmp_path, subset="test")
    assert data["schema_version"] == "lmdj.benchmark-manifest.v1"
    assert data["dataset_id"] == "musdb18hq-test"
    assert len(data["tracks"]) == 2
    track = data["tracks"][0]
    assert track["id"] == "Al James - Schoolboy Facination"
    assert track["input"] == "test/Al James - Schoolboy Facination/mixture.wav"
    assert track["has_ground_truth"] is True
    assert track["ground_truth"]["drums"] == (
        "test/Al James - Schoolboy Facination/drums.wav")
    assert track["split"] == "full"
    # 产物必须能过正式 loader
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data))
    m = load_manifest(path)
    assert m.dataset_id == "musdb18hq-test"


def test_perf_marks_first_n_alphabetical(tmp_path):
    make_musdb_tree(tmp_path, "test", ["C Track", "A Track", "B Track"])
    data = musdb.build_musdb_manifest(tmp_path, subset="test", perf=2)
    splits = {t["id"]: t["split"] for t in data["tracks"]}
    assert splits == {"A Track": "perf", "B Track": "perf", "C Track": "full"}


def test_missing_stem_rejected(tmp_path):
    make_musdb_tree(tmp_path, "test", ["Broken Track"],
                    drop={"Broken Track": ("bass",)})
    with pytest.raises(musdb.MusdbLayoutError) as exc:
        musdb.build_musdb_manifest(tmp_path, subset="test")
    assert "Broken Track" in str(exc.value) and "bass" in str(exc.value)


def test_missing_subset_dir_rejected(tmp_path):
    with pytest.raises(musdb.MusdbLayoutError):
        musdb.build_musdb_manifest(tmp_path, subset="test")


def test_empty_subset_rejected(tmp_path):
    (tmp_path / "test").mkdir()
    with pytest.raises(musdb.MusdbLayoutError):
        musdb.build_musdb_manifest(tmp_path, subset="test")


def test_cli_writes_manifest(tmp_path, capsys):
    make_musdb_tree(tmp_path, "test", ["Solo Track"])
    out = tmp_path / "musdb.manifest.json"
    code = musdb.main(["--root", str(tmp_path), "--out", str(out),
                       "--perf", "1"])
    assert code == 0
    data = json.loads(out.read_text())
    assert data["tracks"][0]["split"] == "perf"
    assert "Solo Track" in capsys.readouterr().out


def test_cli_layout_error_exit_one(tmp_path, capsys):
    code = musdb.main(["--root", str(tmp_path), "--out",
                       str(tmp_path / "x.json")])
    assert code == 1
    assert capsys.readouterr().err
