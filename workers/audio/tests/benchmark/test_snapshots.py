from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from lmdj_audio_worker.benchmark import snapshots

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def make_manifest(tmp_path, name="m.manifest.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({
        "schema_version": "lmdj.benchmark-manifest.v1",
        "dataset_id": "example",
        "tracks": [],
    }))
    return path


def make_registry(tmp_path, name="separators.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({
        "schema_version": "lmdj.separators.v1",
        "separators": [],
    }))
    return path


def test_init_run_writes_four_files_no_leaked_absolute_path(tmp_path):
    manifest_path = make_manifest(tmp_path)
    registry_path = make_registry(tmp_path)
    out_root = tmp_path / "benchmarks"

    run_dir = snapshots.init_run(
        out_root, "run-001", [manifest_path], registry_path, {"device": "mps"})

    assert run_dir == out_root / "run-001"
    for name in ("run.json", "manifest.snapshot.json",
                 "registry.snapshot.json", "environment.json"):
        assert (run_dir / name).exists()

    run_json_text = (run_dir / "run.json").read_text()
    run_json = json.loads(run_json_text)
    assert run_json["run_id"] == "run-001"
    assert run_json["args"] == {"device": "mps"}
    assert run_json["data_root"] == "LMDJ_BENCH_DATA_ROOT"
    assert "created_at" in run_json
    # 不得泄漏绝对主机路径
    assert str(tmp_path) not in run_json_text


def test_environment_json_sha256_matches_recomputed_hashes(tmp_path):
    manifest_path = make_manifest(tmp_path)
    registry_path = make_registry(tmp_path)
    run_dir = snapshots.init_run(
        tmp_path / "benchmarks", "run-001", [manifest_path], registry_path, {})

    env = json.loads((run_dir / "environment.json").read_text())
    for fname in ("parity-constraints.txt", "runner-scnet-constraints.txt", "msst.lock"):
        expected = hashlib.sha256((_CONFIG_DIR / fname).read_bytes()).hexdigest()
        assert env["config_sha256"][fname] == expected
    assert "platform" in env
    assert "machine" in env
    assert "python_version" in env


def test_manifest_snapshot_keyed_by_filename_with_parsed_content(tmp_path):
    manifest_a = make_manifest(tmp_path, "a.manifest.json")
    manifest_b = make_manifest(tmp_path, "b.manifest.json")
    registry_path = make_registry(tmp_path)
    run_dir = snapshots.init_run(
        tmp_path / "benchmarks", "run-001", [manifest_a, manifest_b], registry_path, {})

    manifest_snapshot = json.loads((run_dir / "manifest.snapshot.json").read_text())
    assert set(manifest_snapshot) == {"a.manifest.json", "b.manifest.json"}
    assert manifest_snapshot["a.manifest.json"] == json.loads(manifest_a.read_text())
    assert manifest_snapshot["b.manifest.json"] == json.loads(manifest_b.read_text())

    registry_snapshot = json.loads((run_dir / "registry.snapshot.json").read_text())
    assert registry_snapshot == json.loads(registry_path.read_text())


def test_combo_dir_layout(tmp_path):
    run_dir = tmp_path / "benchmarks" / "run-001"
    path = snapshots.combo_dir(run_dir, "ds", "t1", "sep", "mps", 0)
    assert path == run_dir / "results" / "ds" / "t1" / "sep" / "mps" / "0"
    # 不自动创建
    assert not path.exists()


def test_write_combo_and_read_combo_roundtrip(tmp_path):
    combo_path = tmp_path / "results" / "ds" / "t1" / "sep" / "mps" / "0"
    record = {"status": "ok", "sdr": 5.5}
    snapshots.write_combo(combo_path, record)
    assert (combo_path / "combo.json").exists()
    assert snapshots.read_combo(combo_path) == record


def test_read_combo_missing_returns_none(tmp_path):
    assert snapshots.read_combo(tmp_path / "nope") is None


def test_read_combo_corrupt_json_returns_none(tmp_path):
    combo_path = tmp_path / "corrupt"
    combo_path.mkdir(parents=True)
    (combo_path / "combo.json").write_text("{not valid json")
    assert snapshots.read_combo(combo_path) is None


@pytest.mark.parametrize("bad_run_id", ["../evil", "a b"])
def test_init_run_rejects_illegal_run_id(tmp_path, bad_run_id):
    manifest_path = make_manifest(tmp_path)
    registry_path = make_registry(tmp_path)
    with pytest.raises(ValueError):
        snapshots.init_run(
            tmp_path / "benchmarks", bad_run_id, [manifest_path], registry_path, {})


def test_run_id_re_matches_only_allowed_charset():
    assert snapshots.RUN_ID_RE.fullmatch("run-001_A")
    assert not snapshots.RUN_ID_RE.fullmatch("a b")
    assert not snapshots.RUN_ID_RE.fullmatch("../evil")


def test_finalize_run_merges_summary_and_preserves_existing_fields(tmp_path):
    manifest_path = make_manifest(tmp_path)
    registry_path = make_registry(tmp_path)
    run_dir = snapshots.init_run(
        tmp_path / "benchmarks", "run-001", [manifest_path], registry_path,
        {"device": "mps"})

    snapshots.finalize_run(run_dir, {"counts": {"total": 1, "ok": 1}, "failures": []})

    run_json = json.loads((run_dir / "run.json").read_text())
    assert run_json["run_id"] == "run-001"
    assert run_json["args"] == {"device": "mps"}
    assert run_json["counts"] == {"total": 1, "ok": 1}
    assert run_json["failures"] == []
