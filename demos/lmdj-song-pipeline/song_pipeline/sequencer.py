"""阶段5 MIDI 还原：onset/互相关 → 16 分网格量化 → chart.mid + lanes.json"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import pretty_midi

from .audio_utils import to_mono
from .config import PipelineConfig
from .loop_finder import LoopWindow
from .slicer import DrumSlices, Sample

log = logging.getLogger(__name__)

HOP = 512


@dataclass
class Note:
    pitch: int
    time: float       # loop 内相对秒
    duration: float


def _quantize(times: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """吸附到最近网格点，返回网格下标（末端边界折回 0）。"""
    idx = np.abs(times[:, None] - grid[None, :]).argmin(axis=1)
    return np.where(idx == len(grid) - 1, 0, idx)


def drum_notes(drums: DrumSlices, grid: np.ndarray,
               cfg: PipelineConfig) -> list[Note]:
    notes: dict[tuple[int, int], Note] = {}
    for t, name in zip(drums.onset_times, drums.labels):
        gi = int(_quantize(np.array([t]), grid)[0])
        pitch = cfg.lane_pitches[name]
        notes[(pitch, gi)] = Note(pitch=pitch, time=float(grid[gi]), duration=0.1)
    out = sorted(notes.values(), key=lambda n: (n.time, n.pitch))
    log.info("鼓 MIDI：%d onsets → %d notes", len(drums.onset_times), len(out))
    return out


def _envelope(mono: np.ndarray, sr: int) -> np.ndarray:
    return librosa.onset.onset_strength(y=mono, sr=sr, hop_length=HOP)


def find_triggers(sample: np.ndarray, stem_loop: np.ndarray, sr: int,
                  threshold: float) -> np.ndarray:
    """长样本在 loop 内所有出现位置：onset 包络滑动归一化互相关。"""
    env_s = _envelope(to_mono(sample), sr)
    env_l = _envelope(to_mono(stem_loop), sr)
    m, n = len(env_s), len(env_l)
    if m < 2 or n <= m:
        return np.array([0.0])

    es = env_s - env_s.mean()
    norm_s = np.linalg.norm(es) + 1e-9
    corr = np.empty(n - m + 1)
    for lag in range(n - m + 1):
        seg = env_l[lag:lag + m]
        seg = seg - seg.mean()
        corr[lag] = float(np.dot(es, seg) / (norm_s * (np.linalg.norm(seg) + 1e-9)))

    min_gap = max(1, int(m * 0.75))
    order = np.argsort(corr)[::-1]
    picked = [int(order[0])]                    # 样本至少出现一次（它就是从这切的）
    for lag in order[1:]:
        if corr[lag] < threshold:
            break
        if all(abs(lag - p) >= min_gap for p in picked):
            picked.append(int(lag))
    times = librosa.frames_to_time(sorted(picked), sr=sr, hop_length=HOP)
    return times


def long_notes(longs: list[Sample], loops: dict[str, np.ndarray], sr: int,
               grid: np.ndarray, cfg: PipelineConfig) -> list[Note]:
    notes: list[Note] = []
    for smp in longs:
        stem = "bass" if smp.name.startswith("bass") else "melody"
        triggers = find_triggers(smp.audio, loops[stem], sr,
                                 cfg.long_sample_corr_threshold)
        gi = np.unique(_quantize(triggers, grid))
        dur = len(smp.audio) / sr
        pitch = cfg.lane_pitches[smp.name]
        notes += [Note(pitch=pitch, time=float(grid[i]), duration=dur) for i in gi]
        log.info("长样本 %s：%d 个触发点", smp.name, len(gi))
    return notes


def write_chart(notes: list[Note], window: LoopWindow, out_path: Path) -> None:
    pm = pretty_midi.PrettyMIDI(initial_tempo=window.bpm)
    inst = pretty_midi.Instrument(program=0, name="lmdj-chart")
    for n in notes:
        inst.notes.append(pretty_midi.Note(
            velocity=100, pitch=n.pitch, start=n.time, end=n.time + n.duration))
    pm.instruments.append(inst)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(out_path))
    log.info("chart.mid：%d notes → %s", len(notes), out_path)


def write_lanes(samples: list[Sample], window: LoopWindow, cfg: PipelineConfig,
                out_path: Path) -> dict:
    """lanes.json：pitch ↔ wav 文件 ↔ 键位（lane 下标）三方映射。"""
    lanes = {
        "bpm": round(window.bpm, 2),
        "bars": len(window.beats) / cfg.beats_per_bar,  # max_loop_seconds 可能切出半小节
        "beats": len(window.beats),
        "loop_seconds": round(window.end - window.start, 4),
        "lanes": [
            {
                "lane": i,
                "name": s.name,
                "kind": s.kind,
                "pitch": cfg.lane_pitches[s.name],
                "sample": f"samples/{s.name}.wav",
            }
            for i, s in enumerate(samples)
        ],
    }
    out_path.write_text(json.dumps(lanes, indent=2, ensure_ascii=False))
    log.info("lanes.json：%d lanes → %s", len(samples), out_path)
    return lanes
