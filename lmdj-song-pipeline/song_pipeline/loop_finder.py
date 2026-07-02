"""阶段3 截 4 小节 loop：beat/downbeat 检测 + 候选窗口打分 + 无缝化。

beat 检测默认 librosa（PRD 中 madmom 的兜底路径，对新版 Python 友好）。
downbeat 用鼓轨低频能量在 4 个相位里投票确定。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import librosa
import numpy as np

from .config import PipelineConfig

log = logging.getLogger(__name__)

HOP = 512


@dataclass
class LoopWindow:
    start: float
    end: float
    beats: np.ndarray          # 窗口内 16 个 beat 的绝对时间
    bpm: float
    score: float
    detail: dict = field(default_factory=dict)

    def grid_times(self, grid_per_beat: int) -> np.ndarray:
        """16 分音符网格的绝对时间（含窗口末端边界）。"""
        bounds = np.append(self.beats, self.end)
        grid = [
            np.linspace(bounds[i], bounds[i + 1], grid_per_beat, endpoint=False)
            for i in range(len(bounds) - 1)
        ]
        return np.append(np.concatenate(grid), self.end)


def detect_beats(mix: np.ndarray, stems: dict[str, np.ndarray], sr: int,
                 cfg: PipelineConfig) -> tuple[float, np.ndarray, np.ndarray]:
    """返回 (bpm, beat_times, downbeat_times)。

    downbeat 相位三路投票：和声变化（和弦换在小节头，弱起骗不了它）
    + 贝斯根音落点 + kick 低频能量。
    """
    kwargs = {"bpm": cfg.bpm_hint} if cfg.bpm_hint else {}
    tempo, beat_frames = librosa.beat.beat_track(
        y=mix, sr=sr, hop_length=HOP, trim=False, **kwargs)
    bpm = float(np.atleast_1d(tempo)[0])
    # 倍频误检（如 8 分 hat 把 90 测成 180）：折半后用固定 bpm 重新跟拍
    if not cfg.bpm_hint and bpm > cfg.max_bpm:
        while bpm > cfg.max_bpm:
            bpm /= 2
        log.info("bpm 超出 %.0f，折半为 %.1f 重新跟拍", cfg.max_bpm, bpm)
        tempo, beat_frames = librosa.beat.beat_track(
            y=mix, sr=sr, hop_length=HOP, trim=False, bpm=bpm)
        bpm = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP)
    if len(beat_times) < cfg.beats_per_bar * (cfg.bars + 1):
        raise RuntimeError(f"beat 太少（{len(beat_times)}），曲子过短或节拍检测失败")
    bpb = cfg.beats_per_bar

    def z(x: np.ndarray) -> np.ndarray:
        return (x - x.mean()) / (x.std() + 1e-9)

    # ① 和声变化：beat 同步 chroma 的相邻余弦距离，小节头变化最大
    chroma = librosa.feature.chroma_stft(y=mix, sr=sr, hop_length=HOP)
    beat_chroma = librosa.util.sync(chroma, beat_frames)
    bc = beat_chroma / (np.linalg.norm(beat_chroma, axis=0, keepdims=True) + 1e-9)
    chord_change = np.zeros(bc.shape[1])
    chord_change[1:] = 1.0 - np.sum(bc[:, 1:] * bc[:, :-1], axis=0)

    # ② 贝斯根音落点 ③ kick 低频能量
    def at_beats(y: np.ndarray, fmax: float) -> np.ndarray:
        env = librosa.onset.onset_strength(
            y=y, sr=sr, hop_length=HOP, fmax=fmax, aggregate=np.median)
        return env[np.clip(beat_frames, 0, len(env) - 1)]

    bass_on = at_beats(stems["bass"], 300)
    kick_on = at_beats(stems["drums"], 200)

    n = min(len(chord_change), len(bass_on), len(kick_on))
    vote = (0.4 * z(chord_change[:n]) + 0.3 * z(bass_on[:n]) + 0.3 * z(kick_on[:n]))
    phase_scores = [float(vote[p::bpb].mean()) for p in range(bpb)]
    phase = int(np.argmax(phase_scores))
    downbeats = beat_times[phase::bpb]
    log.info("bpm=%.1f beats=%d downbeat_phase=%d 相位得分=%s",
             bpm, len(beat_times), phase,
             [round(s, 3) for s in phase_scores])
    return bpm, beat_times, downbeats


def find_loop_windows(mix: np.ndarray, stems: dict[str, np.ndarray], sr: int,
                      cfg: PipelineConfig, n_beats: int | None = None,
                      start_phase: int = 0,
                      precomputed: tuple | None = None) -> list[LoopWindow]:
    """枚举候选窗口并打分，按分数降序返回。

    n_beats: 窗口拍数（默认 bars×beats_per_bar）
    start_phase: 起拍在小节内的偏移（0=小节头，2=后半小节）
    precomputed: 复用 detect_beats 的 (bpm, beat_times, downbeats)
    """
    bpm, beat_times, downbeats = precomputed or detect_beats(mix, stems, sr, cfg)
    bpb, bars = cfg.beats_per_bar, cfg.bars
    if n_beats is None:
        n_beats = bpb * bars
        # loop 时长上限：拍数折半（16→8→4→2）直到塞进 max_loop_seconds
        if cfg.max_loop_seconds:
            while n_beats > 2 and n_beats * 60 / bpm > cfg.max_loop_seconds:
                n_beats //= 2
            log.info("loop 上限 %.1fs @ %.1fbpm → %d 拍（%.2gs）",
                     cfg.max_loop_seconds, bpm, n_beats, n_beats * 60 / bpm)

    rms = librosa.feature.rms(y=mix, hop_length=HOP)[0]
    mel = librosa.feature.melspectrogram(y=mix, sr=sr, hop_length=HOP, n_mels=64)
    logmel = librosa.power_to_db(mel)
    onset_env = librosa.onset.onset_strength(y=mix, sr=sr, hop_length=HOP)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, hop_length=HOP)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=HOP)

    def frame(t: float) -> int:
        return int(librosa.time_to_frames(t, sr=sr, hop_length=HOP))

    # 把每个 downbeat 映射回 beat 序列下标，再加起拍相位偏移
    db_idx = np.searchsorted(beat_times, downbeats - 1e-4) + start_phase

    windows: list[LoopWindow] = []
    for i, bi in enumerate(db_idx):
        if bi + n_beats >= len(beat_times):
            break
        start, end = beat_times[bi], beat_times[bi + n_beats]
        beats = beat_times[bi:bi + n_beats]

        # 真 4 拍保证：拍距均匀（±6%）且窗口总长符合名义 BPM（±10%）
        intervals = np.diff(np.append(beats, end))
        med = float(np.median(intervals))
        nominal = n_beats * 60 / bpm
        if (np.abs(intervals - med).max() > 0.06 * med
                or abs((end - start) - nominal) > 0.10 * nominal):
            continue

        f0, f1 = frame(start), frame(end)
        if f1 - f0 < 8 or f1 >= logmel.shape[1] - 4:
            continue
        seg_rms = rms[f0:f1]
        if seg_rms.mean() < 1e-4:
            continue

        # 能量稳定：变异系数越小越好
        stability = 1.0 / (1.0 + seg_rms.std() / (seg_rms.mean() + 1e-9))
        # 首尾频谱相似：窗口开头 1 beat vs 窗口结束位置后 1 beat（wrap 是否顺滑）
        bw = max(2, frame(beats[1]) - f0)
        a = logmel[:, f0:f0 + bw].mean(axis=1)
        b = logmel[:, f1:f1 + bw].mean(axis=1)
        seam = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        # onset 密度适中：目标每 beat 1~3 个
        density = np.sum((onset_times >= start) & (onset_times < end)) / n_beats
        density_score = float(np.exp(-((density - 2.0) ** 2) / 8.0))
        # 切口干净：头有清晰音头，头尾边界前能量低（没有音跨小节线延续）
        env_peak = onset_env[f0:f1].max() + 1e-9
        head_attack = float(onset_env[max(0, f0 - 1):f0 + 2].max() / env_peak)
        rms_peak = seg_rms.max() + 1e-9
        head_quiet = 1.0 - float(rms[max(0, f0 - 3):f0].mean() / rms_peak)
        tail_quiet = 1.0 - float(rms[max(0, f1 - 3):f1].mean() / rms_peak)

        score = (0.25 * stability + 0.25 * max(seam, 0.0) + 0.1 * density_score
                 + 0.2 * min(head_attack, 1.0)
                 + 0.12 * tail_quiet + 0.08 * head_quiet)
        windows.append(LoopWindow(
            start=float(start), end=float(end), beats=beats, bpm=bpm, score=score,
            detail={"stability": round(stability, 3), "seam": round(seam, 3),
                    "density": round(density, 2),
                    "head_attack": round(head_attack, 3),
                    "head_quiet": round(head_quiet, 3),
                    "tail_quiet": round(tail_quiet, 3)}))

    windows.sort(key=lambda w: w.score, reverse=True)
    if not windows:
        raise RuntimeError("没有可用的 4 小节候选窗口")
    log.info("候选窗口 %d 个，最佳 score=%.3f @ %.2fs", len(windows),
             windows[0].score, windows[0].start)
    return windows


def cut_loop(stem: np.ndarray, sr: int, window: LoopWindow,
             cfg: PipelineConfig) -> np.ndarray:
    """按窗口切出 loop 并做首尾 crossfade 无缝化。stem 为 (samples, ch)。"""
    s, e = int(window.start * sr), int(window.end * sr)
    fade = int(cfg.crossfade_ms / 1000 * sr)
    from .audio_utils import crossfade_loop
    seg = stem[s:min(e + fade, len(stem))].copy()
    return crossfade_loop(seg, fade) if len(seg) > e - s else seg
