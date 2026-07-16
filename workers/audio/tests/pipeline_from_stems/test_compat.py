from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lmdj_audio_worker.pipeline_from_stems import compat
from lmdj_audio_worker.pipeline_from_stems.config import PipelineConfig

SR = 44100
PCM16_TOL = 2 / 32768  # 兼容层沿用 demo 的 sf.write 默认 subtype（PCM_16）


def write_canonical(tmp_path: Path, values: dict[str, float]) -> Path:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    for name in ("drums", "bass", "vocals", "other"):
        data = np.full((SR, 2), values.get(name, 0.1), dtype=np.float32)
        sf.write(canonical / f"{name}.wav", data, SR, subtype="FLOAT")
    return canonical


def test_melody_is_vocals_plus_other(tmp_path):
    canonical = write_canonical(tmp_path, {"vocals": 0.2, "other": 0.3})
    out = compat.map_canonical_to_legacy(canonical, tmp_path / "legacy")
    melody, _ = sf.read(out["melody"], always_2d=True)
    assert np.allclose(melody, 0.5, atol=PCM16_TOL)
    assert set(out) == {"drums", "bass", "melody"}


def test_peak_over_one_scaled_to_one(tmp_path):
    canonical = write_canonical(tmp_path, {"vocals": 0.9, "other": 0.9})
    out = compat.map_canonical_to_legacy(canonical, tmp_path / "legacy")
    melody, _ = sf.read(out["melody"], always_2d=True)
    assert np.abs(melody).max() <= 1.0 + PCM16_TOL
    assert np.allclose(melody, 1.0, atol=PCM16_TOL)  # 1.8 缩放到 1.0


def test_peak_under_one_untouched(tmp_path):
    canonical = write_canonical(tmp_path, {"drums": 0.4})
    out = compat.map_canonical_to_legacy(canonical, tmp_path / "legacy")
    drums, _ = sf.read(out["drums"], always_2d=True)
    assert np.allclose(drums, 0.4, atol=PCM16_TOL)


def test_vocals_strategy_drop_rejected(tmp_path):
    canonical = write_canonical(tmp_path, {})
    cfg = PipelineConfig(vocals_strategy="drop")
    with pytest.raises(ValueError, match="merge"):
        compat.map_canonical_to_legacy(canonical, tmp_path / "legacy", cfg)


def test_same_dir_rejected(tmp_path):
    canonical = write_canonical(tmp_path, {})
    with pytest.raises(ValueError, match="同一"):
        compat.map_canonical_to_legacy(canonical, canonical)


def test_missing_canonical_stem_rejected(tmp_path):
    canonical = write_canonical(tmp_path, {})
    (canonical / "other.wav").unlink()
    with pytest.raises(FileNotFoundError, match="other"):
        compat.map_canonical_to_legacy(canonical, tmp_path / "legacy")


def test_originals_not_modified(tmp_path):
    canonical = write_canonical(tmp_path, {"vocals": 0.9, "other": 0.9})
    before = (canonical / "vocals.wav").read_bytes()
    compat.map_canonical_to_legacy(canonical, tmp_path / "legacy")
    assert (canonical / "vocals.wav").read_bytes() == before
