"""阶段6 自动验收：MIDI + samples 重渲染，与原 loop 频谱相似度打分。"""
from __future__ import annotations

import logging

import librosa
import numpy as np

from .audio_utils import to_mono
from .config import PipelineConfig
from .sequencer import Note
from .slicer import Sample

log = logging.getLogger(__name__)


def render(notes: list[Note], samples: list[Sample], cfg: PipelineConfig,
           loop_len: int, sr: int) -> np.ndarray:
    """按谱面把 one-shot/长样本铺进 buffer，模拟全自动回放。"""
    by_pitch = {cfg.lane_pitches[s.name]: s.audio for s in samples}
    ch = max(s.audio.shape[1] for s in samples)
    buf = np.zeros((loop_len, ch), dtype=np.float32)
    for n in notes:
        audio = by_pitch[n.pitch]
        s = int(n.time * sr)
        e = min(s + len(audio), loop_len)
        if e > s:
            buf[s:e] += audio[:e - s]
    peak = float(np.abs(buf).max())
    if peak > 1.0:
        buf /= peak
    return buf


def similarity(rendered: np.ndarray, original: np.ndarray, sr: int) -> float:
    """log-mel 频谱 Pearson 相关，0~1。"""
    n = min(len(rendered), len(original))
    mels = []
    for y in (to_mono(rendered[:n]), to_mono(original[:n])):
        m = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=64, hop_length=512)
        mels.append(librosa.power_to_db(m, ref=np.max).ravel())
    r = float(np.corrcoef(mels[0], mels[1])[0, 1])
    return max(0.0, r)


def validate(notes: list[Note], samples: list[Sample], original_loop: np.ndarray,
             sr: int, cfg: PipelineConfig) -> tuple[float, np.ndarray]:
    rendered = render(notes, samples, cfg, len(original_loop), sr)
    score = similarity(rendered, original_loop, sr)
    log.info("验收相似度 %.3f（阈值 %.2f）", score, cfg.similarity_threshold)
    return score, rendered
