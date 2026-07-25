from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


def read_audio(path: Path, sample_rate: int) -> np.ndarray:
    try:
        audio, _ = librosa.load(
            str(path),
            sr=sample_rate,
            mono=False,
            dtype=np.float32,
        )
    except Exception as error:  # noqa: BLE001 - normalize decoder failures
        raise ValueError(f"unable to decode audio {path}: {error}") from error
    if audio.ndim == 1:
        audio = np.stack((audio, audio), axis=1)
    else:
        audio = audio.T
        if audio.shape[1] == 1:
            audio = np.repeat(audio, 2, axis=1)
        elif audio.shape[1] > 2:
            audio = audio[:, :2]
    if len(audio) == 0 or not np.isfinite(audio).all():
        raise ValueError(f"invalid decoded audio: {path}")
    return np.asarray(audio, dtype=np.float32)


def mono(audio: np.ndarray) -> np.ndarray:
    return np.mean(audio, axis=1, dtype=np.float32)


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


def clipping_ratio(audio: np.ndarray) -> float:
    return float(np.mean(np.abs(audio) >= 0.999))


def normalize_and_fade(
    audio: np.ndarray,
    sample_rate: int,
    fade_seconds: float,
) -> np.ndarray:
    result = np.asarray(audio, dtype=np.float32).copy()
    result -= np.mean(result, axis=0, keepdims=True, dtype=np.float64)
    peak = float(np.max(np.abs(result)))
    if peak > 0:
        result *= np.float32(min(0.95 / peak, 8.0))
    fade = min(int(round(fade_seconds * sample_rate)), len(result) // 2)
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade, endpoint=True, dtype=np.float32)
        result[:fade] *= ramp[:, None]
        result[-fade:] *= ramp[::-1, None]
    return result


def crossfade_loop(
    audio: np.ndarray,
    sample_rate: int,
    seconds: float,
) -> np.ndarray:
    result = np.asarray(audio, dtype=np.float32).copy()
    count = min(int(round(seconds * sample_rate)), len(result) // 8)
    if count <= 0:
        return result
    angle = np.linspace(0, np.pi / 2, count, dtype=np.float32)
    fade_in = np.sin(angle)[:, None]
    fade_out = np.cos(angle)[:, None]
    blend = result[:count] * fade_in + result[-count:] * fade_out
    result[:count] = blend
    result[-count:] = blend
    return result


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".wav.tmp")
    sf.write(
        str(temporary),
        np.asarray(audio, dtype=np.float32),
        sample_rate,
        format="WAV",
        # libsndfile FLOAT WAV writes a PEAK chunk with a wall-clock timestamp,
        # which changes the file hash across otherwise identical runs.
        subtype="PCM_24",
    )
    temporary.replace(path)


def spectral_features(audio: np.ndarray, sample_rate: int) -> tuple[float, ...]:
    signal = mono(audio)
    if len(signal) < 32:
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    window = np.hanning(len(signal))
    spectrum = np.abs(np.fft.rfft(signal * window))
    power = np.square(spectrum, dtype=np.float64)
    frequencies = np.fft.rfftfreq(len(signal), 1.0 / sample_rate)
    total = float(np.sum(power)) + 1e-12
    low = float(np.sum(power[frequencies < 180]) / total)
    mid = float(
        np.sum(power[(frequencies >= 180) & (frequencies < 3_000)]) / total
    )
    high = float(np.sum(power[frequencies >= 3_000]) / total)
    centroid = float(np.sum(frequencies * power) / total / (sample_rate / 2))
    envelope = np.abs(signal)
    transient = float(
        min(
            1.0,
            (float(np.max(envelope)) + 1e-12)
            / (float(np.mean(envelope)) + 1e-12)
            / 12.0,
        )
    )
    return low, mid, high, centroid, transient


def normalized_feature_difference(
    left: tuple[float, ...],
    right: tuple[float, ...],
) -> float:
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    return float(min(1.0, np.linalg.norm(a - b) / np.sqrt(len(a))))
