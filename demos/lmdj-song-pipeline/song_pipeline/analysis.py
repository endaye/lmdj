"""调性 + 和声分析：chroma → Krumhansl-Schmuckler 调性 + 逐小节三和弦估计。"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import librosa
import numpy as np

log = logging.getLogger(__name__)

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler 大小调音级权重
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                          2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                          2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


@dataclass
class KeyResult:
    key: str            # 如 "Eb major"
    confidence: float   # 最优与次优相关系数之差（>0.05 算可信）
    all_scores: dict


def _flat_name(i: int) -> str:
    flats = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}
    return flats.get(NOTES[i], NOTES[i])


def detect_key(y: np.ndarray, sr: int) -> KeyResult:
    """全曲平均 chroma 对 24 个调性模板做相关。"""
    harm = librosa.effects.harmonic(y)
    chroma = librosa.feature.chroma_cqt(y=harm, sr=sr).mean(axis=1)
    scores = {}
    for i in range(12):
        rolled = np.roll(chroma, -i)
        scores[f"{_flat_name(i)} major"] = float(np.corrcoef(rolled, MAJOR_PROFILE)[0, 1])
        scores[f"{_flat_name(i)} minor"] = float(np.corrcoef(rolled, MINOR_PROFILE)[0, 1])
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return KeyResult(key=ranked[0][0],
                     confidence=round(ranked[0][1] - ranked[1][1], 4),
                     all_scores=dict(ranked[:5]))


def _triad_templates() -> tuple[list[str], np.ndarray]:
    names, rows = [], []
    for i in range(12):
        for quality, intervals in (("", (0, 4, 7)), ("m", (0, 3, 7))):
            t = np.zeros(12)
            t[[(i + d) % 12 for d in intervals]] = 1.0
            names.append(f"{_flat_name(i)}{quality}")
            rows.append(t / np.linalg.norm(t))
    return names, np.array(rows)


def detect_chords(y: np.ndarray, sr: int,
                  segment_times: np.ndarray) -> list[dict]:
    """按给定边界（如小节线）逐段估计三和弦。segment_times 为绝对秒边界。"""
    harm = librosa.effects.harmonic(y)
    chroma = librosa.feature.chroma_cqt(y=harm, sr=sr)
    names, templates = _triad_templates()
    out = []
    for i in range(len(segment_times) - 1):
        f0 = int(librosa.time_to_frames(segment_times[i], sr=sr))
        f1 = max(f0 + 1, int(librosa.time_to_frames(segment_times[i + 1], sr=sr)))
        v = chroma[:, f0:f1].mean(axis=1)
        v = v / (np.linalg.norm(v) + 1e-9)
        sims = templates @ v
        best = int(np.argmax(sims))
        out.append({"start": round(float(segment_times[i]), 2),
                    "chord": names[best],
                    "confidence": round(float(sims[best]), 3)})
    return out


def analyze(path, bars_seconds: np.ndarray | None = None, sr: int = 22050) -> dict:
    """整曲调性 + （给了小节线就做）逐小节和弦。"""
    y, sr = librosa.load(path, sr=sr, mono=True)
    key = detect_key(y, sr)
    result = {"key": key.key, "key_confidence": key.confidence,
              "key_top5": key.all_scores}
    if bars_seconds is not None:
        result["chords"] = detect_chords(y, sr, bars_seconds)
    return result
