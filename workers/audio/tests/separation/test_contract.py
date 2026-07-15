from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmdj_audio_worker.separation import contract


def make_completed(**overrides) -> dict:
    data = {
        "schema_version": "lmdj.separation.v1",
        "status": "completed",
        "source": "runner",
        "input_sha256": "a" * 64,
        "separator": {"id": "htdemucs", "family": "demucs",
                      "checkpoint_sha256": "b" * 64, "runner_version": "0.1.0"},
        "requested_device": "mps",
        "actual_device": "mps",
        "stems": {k: f"stems/{k}.wav"
                  for k in ("drums", "bass", "vocals", "other")},
        "audio": {"sample_rate": 44100, "channels": 2, "duration_seconds": 30.0},
        "performance": {"model_load_seconds": 1.0, "inference_seconds": 5.0,
                        "wall_seconds": 6.5, "peak_rss_bytes": 1024,
                        "peak_device_memory_bytes": 0},
    }
    data.update(overrides)
    return data


def make_failed(**overrides) -> dict:
    data = {
        "schema_version": "lmdj.separation.v1",
        "status": "failed",
        "source": "orchestrator",
        "input_sha256": "a" * 64,
        "separator": {"id": "htdemucs", "family": "demucs",
                      "checkpoint_sha256": "b" * 64, "runner_version": "unknown"},
        "requested_device": "mps",
        "error": {"category": "oom", "exit_code": 137, "stage": "inference",
                  "stderr_tail": "killed", "elapsed_seconds": 12.5},
    }
    data.update(overrides)
    return data


def test_valid_completed_passes():
    assert contract.validate_result_dict(make_completed()) == []


def test_valid_failed_passes():
    assert contract.validate_result_dict(make_failed()) == []


def test_error_categories_match_spec_order():
    assert contract.ERROR_CATEGORIES == (
        "download", "checksum", "license", "unsupported_device",
        "timeout", "oom", "inference", "invalid_stems", "downstream", "metric")


@pytest.mark.parametrize("mutate,fragment", [
    ({"schema_version": "lmdj.separation.v2"}, "schema_version"),
    ({"status": "done"}, "status"),
    ({"source": "worker"}, "source"),
    ({"input_sha256": "xyz"}, "input_sha256"),
])
def test_top_level_field_errors(mutate, fragment):
    errors = contract.validate_result_dict(make_completed(**mutate))
    assert any(fragment in e for e in errors)


def test_completed_requires_all_canonical_stems():
    data = make_completed()
    del data["stems"]["vocals"]
    errors = contract.validate_result_dict(data)
    assert any("vocals" in e for e in errors)


def test_completed_rejects_extra_stem():
    data = make_completed()
    data["stems"]["piano"] = "stems/piano.wav"
    errors = contract.validate_result_dict(data)
    assert any("piano" in e for e in errors)


def test_completed_requires_performance_keys():
    data = make_completed()
    del data["performance"]["peak_device_memory_bytes"]
    errors = contract.validate_result_dict(data)
    assert any("peak_device_memory_bytes" in e for e in errors)


def test_failed_rejects_stems_field():
    data = make_failed(stems={"drums": "stems/drums.wav"})
    errors = contract.validate_result_dict(data)
    assert any("stems" in e for e in errors)


def test_failed_rejects_unknown_error_category():
    data = make_failed()
    data["error"]["category"] = "mystery"
    errors = contract.validate_result_dict(data)
    assert any("category" in e for e in errors)


def test_non_dict_input():
    assert contract.validate_result_dict([1, 2]) != []


def test_round_trip_write_and_load(tmp_path: Path):
    result = contract.SeparationResult.from_dict(make_failed())
    path = tmp_path / "separation.json"
    contract.write_result(path, result)
    loaded = contract.load_result_file(path)
    assert loaded == result
    assert json.loads(path.read_text())["status"] == "failed"


def test_from_dict_raises_with_errors_attribute():
    with pytest.raises(contract.ContractError) as exc:
        contract.SeparationResult.from_dict(make_completed(status="done"))
    assert exc.value.errors
