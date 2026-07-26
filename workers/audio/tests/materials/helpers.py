from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from lmdj_core_models.materials import MaterialProvenance

SR = 44_100


def write_fixture_audio(root: Path, *, seconds: float = 16.0) -> tuple[Path, Path]:
    frames = int(seconds * SR)
    time = np.arange(frames, dtype=np.float32) / SR
    drums = np.zeros(frames, dtype=np.float32)
    beat = 0.5
    for index, start in enumerate(np.arange(0, seconds, beat)):
        begin = int(start * SR)
        length = int(0.12 * SR)
        local = np.arange(length, dtype=np.float32) / SR
        if index % 4 == 0:
            burst = np.sin(2 * np.pi * 60 * local) * np.exp(-local * 25)
        elif index % 4 == 1:
            burst = np.sin(2 * np.pi * 900 * local) * np.exp(-local * 30)
        elif index % 4 == 2:
            burst = np.sin(2 * np.pi * 7000 * local) * np.exp(-local * 45)
        else:
            burst = np.sin(2 * np.pi * 420 * local) * np.exp(-local * 28)
        end = min(frames, begin + length)
        drums[begin:end] += burst[: end - begin] * 0.5

    bass = np.sin(2 * np.pi * np.where(time < seconds / 2, 110, 146.83) * time)
    bass = bass.astype(np.float32) * 0.12
    other = (
        np.sin(2 * np.pi * 440 * time)
        + 0.35 * np.sin(2 * np.pi * np.where(time < seconds / 2, 660, 880) * time)
    ).astype(np.float32) * 0.08
    vocals = np.sin(2 * np.pi * 220 * time).astype(np.float32) * 0.07
    original = np.clip(drums + bass + other + vocals, -0.9, 0.9)

    def stereo(signal: np.ndarray) -> np.ndarray:
        return np.stack((signal, signal), axis=1)

    source = root / "source.wav"
    stems = root / "stems"
    stems.mkdir(parents=True)
    sf.write(source, stereo(original), SR, subtype="FLOAT")
    for name, signal in {
        "drums": drums,
        "bass": bass,
        "vocals": vocals,
        "other": other,
    }.items():
        sf.write(stems / f"{name}.wav", stereo(signal), SR, subtype="FLOAT")
    return source, stems


def provenance() -> MaterialProvenance:
    return MaterialProvenance(
        separator_id="fixture",
        separator_checkpoint_sha256="a" * 64,
        separator_runner_version="fixture-v1",
        timing_version="timing-v1",
        extractor_runner_version="extractor-v1",
        extraction_config_version="materials-v1.0.0",
        environment_lock_sha256="b" * 64,
    )
