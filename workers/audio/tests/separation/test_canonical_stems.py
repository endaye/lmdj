from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lmdj_audio_worker.separation import contract

SR = contract.CANONICAL_SAMPLE_RATE
FRAMES = SR  # 1 秒


def write_stem(path: Path, data: np.ndarray, sr: int = SR,
               subtype: str = "FLOAT") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data, sr, subtype=subtype)


def make_package(tmp_path: Path, mutate=None) -> tuple[Path, contract.SeparationResult]:
    rng = np.random.default_rng(0)
    for name in contract.CANONICAL_STEMS:
        data = rng.uniform(-0.5, 0.5, size=(FRAMES, 2)).astype(np.float32)
        if mutate:
            data = mutate(name, data)
        write_stem(tmp_path / "stems" / f"{name}.wav", data)
    result = contract.SeparationResult.from_dict({
        "schema_version": contract.SCHEMA_VERSION,
        "status": "completed", "source": "runner",
        "input_sha256": "a" * 64,
        "separator": {"id": "htdemucs", "family": "demucs",
                      "checkpoint_sha256": "b" * 64, "runner_version": "0.1.0"},
        "requested_device": "cpu", "actual_device": "cpu",
        "stems": {k: f"stems/{k}.wav" for k in contract.CANONICAL_STEMS},
        "audio": {"sample_rate": SR, "channels": 2, "duration_seconds": 1.0},
        "performance": {"model_load_seconds": 0.0, "inference_seconds": 0.0,
                        "wall_seconds": 0.0, "peak_rss_bytes": 0,
                        "peak_device_memory_bytes": 0},
    })
    return tmp_path, result


def test_valid_package_passes(tmp_path):
    pkg, result = make_package(tmp_path)
    assert contract.validate_canonical_stems(pkg, result, FRAMES) == []


def test_missing_stem_file(tmp_path):
    pkg, result = make_package(tmp_path)
    (pkg / "stems" / "other.wav").unlink()
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("other" in e for e in errors)


def test_wrong_sample_rate(tmp_path):
    pkg, result = make_package(tmp_path)
    data, _ = sf.read(pkg / "stems" / "drums.wav", always_2d=True)
    write_stem(pkg / "stems" / "drums.wav", data, sr=48000)
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("drums" in e and "44100" in e for e in errors)


def test_mono_rejected(tmp_path):
    pkg, result = make_package(tmp_path)
    write_stem(pkg / "stems" / "bass.wav",
               np.zeros(FRAMES, dtype=np.float32) + 0.1)
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("bass" in e for e in errors)


def test_pcm16_subtype_rejected(tmp_path):
    pkg, result = make_package(tmp_path)
    data, _ = sf.read(pkg / "stems" / "vocals.wav", always_2d=True)
    write_stem(pkg / "stems" / "vocals.wav", data, subtype="PCM_16")
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("vocals" in e and "float" in e.lower() for e in errors)


def test_nan_rejected(tmp_path):
    def poison(name, data):
        if name == "drums":
            data[0, 0] = np.nan
        return data
    pkg, result = make_package(tmp_path, mutate=poison)
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("drums" in e and "NaN" in e for e in errors)


def test_peak_over_limit_rejected(tmp_path):
    def loud(name, data):
        if name == "other":
            data[0, 0] = 9.0
        return data
    pkg, result = make_package(tmp_path, mutate=loud)
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("other" in e and "8.0" in e for e in errors)


def test_duration_off_by_two_rejected(tmp_path):
    pkg, result = make_package(tmp_path)
    errors = contract.validate_canonical_stems(pkg, result, FRAMES + 2)
    assert len(errors) == 4  # 四轨全部超差


def test_duration_off_by_one_allowed(tmp_path):
    pkg, result = make_package(tmp_path)
    assert contract.validate_canonical_stems(pkg, result, FRAMES + 1) == []


def test_empty_audio_rejected(tmp_path):
    pkg, result = make_package(tmp_path)
    write_stem(pkg / "stems" / "drums.wav",
               np.zeros((0, 2), dtype=np.float32))
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("drums" in e for e in errors)
