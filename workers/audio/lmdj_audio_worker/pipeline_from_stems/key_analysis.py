from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Sequence

from lmdj_audio_worker.music_metadata import KeyEstimate

SAMPLE_RATE = 22_050
PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    numerator = sum(a * b for a, b in zip(left_centered, right_centered))
    denominator = math.sqrt(
        sum(value * value for value in left_centered)
        * sum(value * value for value in right_centered),
    )
    return numerator / denominator if denominator else 0.0


def _rotate_profile(profile: Sequence[float], root: int) -> list[float]:
    return [profile[(pitch - root) % 12] for pitch in range(12)]


def estimate_key(audio: Path) -> KeyEstimate:
    import librosa

    samples, sample_rate = librosa.load(str(audio), sr=SAMPLE_RATE, mono=True)
    chroma = librosa.feature.chroma_cqt(y=samples, sr=sample_rate)
    if len(chroma) != 12 or any(len(pitch_frames) == 0 for pitch_frames in chroma):
        raise ValueError("chroma_cqt must return 12 non-empty pitch classes")
    mean_chroma = [
        sum(float(value) for value in pitch_frames) / len(pitch_frames)
        for pitch_frames in chroma
    ]
    candidates: list[tuple[float, str]] = []
    for root, pitch_name in enumerate(PITCH_NAMES):
        candidates.append((
            _pearson(mean_chroma, _rotate_profile(MAJOR_PROFILE, root)),
            f"{pitch_name} major",
        ))
        candidates.append((
            _pearson(mean_chroma, _rotate_profile(MINOR_PROFILE, root)),
            f"{pitch_name} minor",
        ))
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    best_score, value = candidates[0]
    second_score = candidates[1][0]
    confidence = max(0.0, min(1.0, (best_score - second_score) / 2.0))
    return KeyEstimate(value=value, confidence=confidence)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("key-analysis")
    parser.add_argument("--audio", type=Path, required=True)
    args = parser.parse_args(argv)
    estimate = estimate_key(args.audio)
    print(json.dumps({
        "value": estimate.value,
        "confidence": estimate.confidence,
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
