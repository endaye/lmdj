from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import librosa
import numpy as np

from lmdj_audio_worker.materials.audio import mono, read_audio
from lmdj_audio_worker.materials.config import (
    DEFAULT_MATERIAL_CONFIG,
    MaterialExtractionConfig,
)

TIMING_SCHEMA = "lmdj.timing.v1"


@dataclass(frozen=True)
class TimeWindow:
    start: float
    end: float


@dataclass(frozen=True)
class TimingArtifact:
    bpm: float
    confidence: float
    beats_per_bar: int
    grid_per_beat: int
    length_steps: int
    beats: tuple[float, ...]
    bars: tuple[float, ...]
    grid: tuple[float, ...]
    primary_window: TimeWindow
    alternate_windows: tuple[TimeWindow, ...]
    version: str
    schema: str = TIMING_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "bpm": self.bpm,
            "confidence": self.confidence,
            "beats_per_bar": self.beats_per_bar,
            "grid_per_beat": self.grid_per_beat,
            "length_steps": self.length_steps,
            "beats": list(self.beats),
            "bars": list(self.bars),
            "grid": list(self.grid),
            "primary_window": asdict(self.primary_window),
            "alternate_windows": [
                asdict(window) for window in self.alternate_windows
            ],
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimingArtifact":
        artifact = cls(
            schema=data["schema"],
            bpm=float(data["bpm"]),
            confidence=float(data["confidence"]),
            beats_per_bar=int(data["beats_per_bar"]),
            grid_per_beat=int(data["grid_per_beat"]),
            length_steps=int(data["length_steps"]),
            beats=tuple(float(value) for value in data["beats"]),
            bars=tuple(float(value) for value in data["bars"]),
            grid=tuple(float(value) for value in data["grid"]),
            primary_window=TimeWindow(**data["primary_window"]),
            alternate_windows=tuple(
                TimeWindow(**row) for row in data["alternate_windows"]
            ),
            version=data["version"],
        )
        artifact.validate()
        return artifact

    def validate(self) -> None:
        if self.schema != TIMING_SCHEMA:
            raise ValueError(f"timing schema must be {TIMING_SCHEMA}")
        if self.bpm <= 0 or not 0 <= self.confidence <= 1:
            raise ValueError("invalid timing bpm/confidence")
        if self.length_steps < 16 or self.length_steps % 16:
            raise ValueError("timing length_steps must contain whole 4/4 bars")
        if len(self.grid) < self.length_steps + 1:
            raise ValueError("timing grid does not cover primary pattern")
        if self.primary_window.end <= self.primary_window.start:
            raise ValueError("invalid primary timing window")


class TimingAnalyzer:
    def __init__(
        self,
        config: MaterialExtractionConfig = DEFAULT_MATERIAL_CONFIG,
    ) -> None:
        self.config = config

    def analyze(self, audio_path: Path, output_path: Path) -> TimingArtifact:
        audio = read_audio(audio_path, self.config.sample_rate)
        duration = len(audio) / self.config.sample_rate
        signal = mono(audio)
        onset_envelope = librosa.onset.onset_strength(
            y=signal,
            sr=self.config.sample_rate,
        )
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_envelope,
            sr=self.config.sample_rate,
            units="frames",
        )
        bpm = float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else 0.0
        while bpm > self.config.bpm_max:
            bpm /= 2.0
        while 0 < bpm < self.config.bpm_min:
            bpm *= 2.0
        if not np.isfinite(bpm) or bpm <= 0:
            bpm = self.config.default_bpm
        detected = librosa.frames_to_time(
            beat_frames,
            sr=self.config.sample_rate,
        )
        beat_seconds = 60.0 / bpm
        phase = float(detected[0]) if len(detected) else 0.0
        phase = max(0.0, min(phase, beat_seconds))
        available_beats = max(4, int((duration - phase) / beat_seconds))
        primary_bars = max(
            1,
            min(self.config.primary_bars, available_beats // 4),
        )
        primary_beats = primary_bars * 4
        length_steps = primary_beats * 4
        primary_end = min(duration, phase + primary_beats * beat_seconds)
        if primary_end - phase < beat_seconds * 4 * 0.98:
            phase = 0.0
            primary_end = min(duration, primary_beats * beat_seconds)
        if primary_end <= phase:
            raise ValueError("audio is too short for a one-bar Timing artifact")

        grid_count = max(
            length_steps + 1,
            int(np.floor((duration - phase) / (beat_seconds / 4))) + 1,
        )
        grid = tuple(
            round(phase + index * beat_seconds / 4, 9)
            for index in range(grid_count)
        )
        beats = tuple(grid[index] for index in range(0, grid_count, 4))
        bars = tuple(grid[index] for index in range(0, grid_count, 16))
        windows = []
        window_seconds = primary_beats * beat_seconds
        start = phase + window_seconds
        while start + window_seconds <= duration + 1e-9:
            windows.append(
                TimeWindow(round(start, 9), round(start + window_seconds, 9))
            )
            start += window_seconds
        confidence = float(
            min(1.0, len(detected) / max(1, available_beats))
        )
        artifact = TimingArtifact(
            bpm=round(bpm, 6),
            confidence=round(confidence, 6),
            beats_per_bar=4,
            grid_per_beat=4,
            length_steps=length_steps,
            beats=beats,
            bars=bars,
            grid=grid,
            primary_window=TimeWindow(round(phase, 9), round(primary_end, 9)),
            alternate_windows=tuple(windows),
            version=self.config.timing_version,
        )
        artifact.validate()
        _write_timing(output_path, artifact)
        return artifact


def load_timing(path: Path) -> TimingArtifact:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"unable to read timing artifact: {error}") from error
    return TimingArtifact.from_dict(data)


def _write_timing(path: Path, artifact: TimingArtifact) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            artifact.to_dict(),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )
    temporary.replace(path)
