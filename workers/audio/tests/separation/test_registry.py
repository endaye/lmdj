from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmdj_audio_worker.separation import registry


def entry_dict(**overrides) -> dict:
    d = {
        "id": "htdemucs",
        "family": "demucs",
        "runner": "demucs",
        "command": ["{checkpoint_dir}/run", "--input", "{input}",
                    "--output", "{output_dir}", "--device", "{device}",
                    "--seed", "{seed}"],
        "source": {"url": "https://example.com/htdemucs.th", "revision": "v4.0.1"},
        "artifact_sha256": "c" * 64,
        "license": {"code": "MIT", "weights": "MIT"},
        "stems": ["drums", "bass", "vocals", "other"],
        "sample_rate": 44100,
        "channels": 2,
        "devices": ["cpu", "mps"],
        "inference": {"segment_seconds": 7.8, "overlap": 0.25},
        "env_lock_sha256": "d" * 64,
        "status": "verified",
    }
    d.update(overrides)
    return d


def write_registry(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "separators.json"
    path.write_text(json.dumps(
        {"schema_version": "lmdj.separators.v1", "separators": entries}))
    return path


def test_valid_registry_loads(tmp_path):
    entries = registry.load_registry(write_registry(tmp_path, [entry_dict()]))
    assert entries[0].id == "htdemucs"
    assert entries[0].command[1] == "--input"
    assert entries[0].inference["overlap"] == 0.25


def test_empty_registry_loads(tmp_path):
    assert registry.load_registry(write_registry(tmp_path, [])) == ()


def test_duplicate_ids_rejected(tmp_path):
    path = write_registry(tmp_path, [entry_dict(), entry_dict()])
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(path)
    assert any("htdemucs" in e and "重复" in e for e in exc.value.errors)


@pytest.mark.parametrize("field", [
    "artifact_sha256", "license", "source", "inference",
    "env_lock_sha256", "status", "command",
])
def test_missing_required_field_rejected(tmp_path, field):
    d = entry_dict()
    del d[field]
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(write_registry(tmp_path, [d]))
    assert any(field in e for e in exc.value.errors)


def test_unknown_field_rejected(tmp_path):
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(
            write_registry(tmp_path, [entry_dict(surprise=1)]))
    assert any("surprise" in e for e in exc.value.errors)


def test_bad_status_rejected(tmp_path):
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(
            write_registry(tmp_path, [entry_dict(status="beta")]))
    assert any("status" in e for e in exc.value.errors)


def test_unknown_command_placeholder_rejected(tmp_path):
    d = entry_dict(command=["run", "--model", "{model_path}"])
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(write_registry(tmp_path, [d]))
    assert any("model_path" in e for e in exc.value.errors)


def test_bad_device_rejected(tmp_path):
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(
            write_registry(tmp_path, [entry_dict(devices=["cuda"])]))
    assert any("cuda" in e for e in exc.value.errors)


def test_production_filter(tmp_path):
    entries = registry.load_registry(write_registry(tmp_path, [
        entry_dict(),
        entry_dict(id="scnet-large", status="production"),
    ]))
    assert [e.id for e in registry.production_entries(entries)] == ["scnet-large"]
    assert len(registry.benchmark_entries(entries)) == 2


def test_shipped_registry_file_is_valid():
    shipped = Path(__file__).resolve().parents[2] / "config" / "separators.json"
    entries = registry.load_registry(shipped)
    by_id = {e.id: e for e in entries}
    assert set(by_id) == {"htdemucs", "scnet-large"}
    assert by_id["htdemucs"].status == "verified"
    assert by_id["scnet-large"].status == "experimental"


def test_shipped_env_locks_match_files():
    import hashlib
    config_dir = Path(__file__).resolve().parents[2] / "config"
    entries = {e.id: e for e in registry.load_registry(config_dir / "separators.json")}
    lock_files = {"htdemucs": config_dir / "runner-demucs-constraints.txt",
                  "scnet-large": config_dir / "msst.lock"}
    for eid, lock in lock_files.items():
        digest = hashlib.sha256(lock.read_bytes()).hexdigest()
        assert entries[eid].env_lock_sha256 == digest, f"{eid} env lock 漂移"
    config_sha = hashlib.sha256(
        (config_dir / "scnet" / "config_musdb18_scnet_large_starrytong.yaml").read_bytes()
    ).hexdigest()
    assert entries["scnet-large"].inference["config_sha256"] == config_sha
