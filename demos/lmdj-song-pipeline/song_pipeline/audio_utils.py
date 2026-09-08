from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def load_wav(path: Path, sr: int) -> tuple[np.ndarray, int]:
    """读 wav，返回 (samples, channels) float32，需要时重采样到 sr。"""
    data, file_sr = sf.read(path, dtype="float32", always_2d=True)
    if file_sr != sr:
        import librosa
        data = librosa.resample(data.T, orig_sr=file_sr, target_sr=sr).T
    return np.ascontiguousarray(data), sr


def to_mono(data: np.ndarray) -> np.ndarray:
    return data.mean(axis=1) if data.ndim == 2 else data


def fade_out(data: np.ndarray, n: int) -> np.ndarray:
    n = min(n, len(data))
    if n > 0:
        env = np.linspace(1.0, 0.0, n, dtype=np.float32)
        data[-n:] *= env[:, None] if data.ndim == 2 else env
    return data


def fade_in(data: np.ndarray, n: int) -> np.ndarray:
    n = min(n, len(data))
    if n > 0:
        env = np.linspace(0.0, 1.0, n, dtype=np.float32)
        data[:n] *= env[:, None] if data.ndim == 2 else env
    return data


def crossfade_loop(data: np.ndarray, fade_samples: int) -> np.ndarray:
    """把尾部 fade_samples 等功率叠进开头，使首尾循环无缝。"""
    n = min(fade_samples, len(data) // 4)
    if n <= 0:
        return data
    body, tail = data[:-n].copy(), data[-n:]
    t = np.linspace(0, np.pi / 2, n, dtype=np.float32)
    up, down = np.sin(t), np.cos(t)
    if body.ndim == 2:
        up, down = up[:, None], down[:, None]
    body[:n] = body[:n] * up + tail * down
    return body


def gate(data: np.ndarray, threshold_db: float) -> np.ndarray:
    """门限降噪：低于阈值的尾部/残留直接静音（按 5ms 块）。"""
    mono = np.abs(to_mono(data))
    block = 220
    thr = 10 ** (threshold_db / 20)
    out = data.copy()
    for i in range(0, len(mono), block):
        if mono[i:i + block].max() < thr:
            out[i:i + block] = 0
    return out


def write_wav(path: Path, data: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = float(np.abs(data).max()) if len(data) else 0.0
    if peak > 1.0:
        data = data / peak
    sf.write(path, data, sr)
