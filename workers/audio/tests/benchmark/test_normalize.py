from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lmdj_audio_worker.benchmark import normalize

SR = 44100


def make_src(tmp_path: Path, sr: int = 22050, seconds: float = 0.5,
             channels: int = 1) -> Path:
    src = tmp_path / "src.wav"
    frames = int(sr * seconds)
    shape = (frames, channels) if channels > 1 else (frames,)
    sf.write(src, np.random.default_rng(0).uniform(-0.3, 0.3, shape)
             .astype(np.float32), sr)
    return src


def test_normalizes_to_44k_stereo_float(tmp_path):
    src = make_src(tmp_path)
    result = normalize.normalize_input(src, tmp_path / "norm")
    info = sf.info(str(result.path))
    assert info.samplerate == SR and info.channels == 2
    assert info.subtype == "FLOAT"
    assert result.frames == info.frames
    assert abs(result.duration_seconds - 0.5) < 0.05
    assert len(result.sha256) == 64


def test_idempotent_reuse(tmp_path):
    src = make_src(tmp_path)
    first = normalize.normalize_input(src, tmp_path / "norm")
    mtime = first.path.stat().st_mtime_ns
    second = normalize.normalize_input(src, tmp_path / "norm")
    assert second.path.stat().st_mtime_ns == mtime    # 未重写
    assert second.sha256 == first.sha256


def test_missing_source_raises(tmp_path):
    with pytest.raises(normalize.NormalizeError):
        normalize.normalize_input(tmp_path / "nope.mp3", tmp_path / "norm")


def test_corrupt_audio_raises_with_stderr(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(normalize.NormalizeError) as exc:
        normalize.normalize_input(bad, tmp_path / "norm")
    assert str(exc.value)


def test_missing_ffmpeg_raises(tmp_path, monkeypatch):
    src = make_src(tmp_path)
    import subprocess
    def raise_file_not_found(*args, **kwargs):
        raise FileNotFoundError("ffmpeg not found")
    monkeypatch.setattr(subprocess, "run", raise_file_not_found)
    with pytest.raises(normalize.NormalizeError) as exc:
        normalize.normalize_input(src, tmp_path / "norm")
    assert "ffmpeg" in str(exc.value)
