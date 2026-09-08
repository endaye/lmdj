"""阶段4 MPC 式切片。

鼓：onset → 特征 → KMeans 聚 3 类（kick/snare/hat），质量差降级 2 键位。
贝斯/旋律：按小节切 phrase → 自相似度选 1-2 段长样本。
总样本数 ≤ cfg.max_samples。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import librosa
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from .audio_utils import fade_in, fade_out, gate, to_mono
from .config import PipelineConfig
from .loop_finder import LoopWindow

log = logging.getLogger(__name__)

HOP = 512


@dataclass
class Sample:
    name: str            # kick / snare / hat / drum_low / bass / melody_a ...
    kind: str            # "drum" | "long"
    audio: np.ndarray    # (samples, ch)


@dataclass
class DrumSlices:
    samples: list[Sample]
    onset_times: np.ndarray   # loop 内相对时间
    labels: list[str]         # 与 onset_times 对齐的样本名


def _onset_features(mono: np.ndarray, sr: int, onset_samples: np.ndarray) -> np.ndarray:
    """每个 onset 取 100ms 窗口：频谱质心 + 频段能量比 + MFCC。"""
    win = int(0.1 * sr)
    feats = []
    for s in onset_samples:
        seg = mono[s:s + win]
        if len(seg) < win // 2:
            seg = np.pad(seg, (0, win - len(seg)))
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        freqs = np.fft.rfftfreq(len(seg), 1 / sr)
        total = spec.sum() + 1e-9
        centroid = (spec * freqs).sum() / total
        low = spec[freqs < 150].sum() / total
        mid = spec[(freqs >= 150) & (freqs < 2000)].sum() / total
        high = spec[freqs >= 4000].sum() / total
        mfcc = librosa.feature.mfcc(y=seg, sr=sr, n_mfcc=8).mean(axis=1)
        feats.append(np.concatenate([[np.log1p(centroid), low, mid, high], mfcc]))
    return np.array(feats)


def slice_drums(drum_loop: np.ndarray, sr: int, cfg: PipelineConfig) -> DrumSlices:
    mono = to_mono(drum_loop)
    onset_frames = librosa.onset.onset_detect(
        y=mono, sr=sr, hop_length=HOP, backtrack=True, units="frames")
    onset_samples = librosa.frames_to_samples(onset_frames, hop_length=HOP)
    onset_samples = onset_samples[onset_samples < len(mono) - int(0.02 * sr)]
    if len(onset_samples) < 4:
        raise RuntimeError(f"鼓轨 onset 太少（{len(onset_samples)}），无法切片")

    feats = StandardScaler().fit_transform(_onset_features(mono, sr, onset_samples))

    def cluster(k: int):
        km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(feats)
        sil = silhouette_score(feats, km.labels_) if len(set(km.labels_)) > 1 else -1
        return km.labels_, sil

    k = min(cfg.drum_clusters, len(onset_samples) - 1)
    labels, sil = cluster(k)
    counts = np.bincount(labels, minlength=k)
    if k == 3 and (sil < cfg.silhouette_floor or counts.min() < cfg.min_cluster_hits):
        log.info("3 类聚类质量差(sil=%.3f counts=%s)，降级 2 键位", sil, counts)
        k = 2
        labels, sil = cluster(k)
    log.info("鼓聚类 k=%d silhouette=%.3f counts=%s", k, sil, np.bincount(labels))

    # 按低频占比给簇命名：kick 最低频，hat 最高频
    low_ratio = feats[:, 1]  # 标准化后的 low band，仍保序
    order = np.argsort([low_ratio[labels == c].mean() for c in range(k)])[::-1]
    names = ["kick", "snare", "hat"] if k == 3 else ["drum_low", "drum_high"]
    cluster_name = {int(c): names[rank] for rank, c in enumerate(order)}

    # 每类选最干净 one-shot：能量大 + 距下一个 onset 远
    energies = np.array([
        float(np.abs(mono[s:s + int(0.1 * sr)]).max()) for s in onset_samples])
    gaps = np.diff(np.append(onset_samples, len(mono))) / sr
    samples: list[Sample] = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        best = idx[np.argmax(energies[idx] * np.minimum(gaps[idx], cfg.oneshot_max_sec))]
        s = int(onset_samples[best])
        e_candidates = onset_samples[onset_samples > s]
        e = int(e_candidates[0]) if len(e_candidates) else len(drum_loop)
        e = min(e, s + int(cfg.oneshot_max_sec * sr), len(drum_loop))
        shot = drum_loop[max(0, s - int(0.002 * sr)):e].copy()
        shot = gate(shot, cfg.gate_db)
        shot = fade_out(shot, int(cfg.oneshot_fade_ms / 1000 * sr))
        samples.append(Sample(name=cluster_name[c], kind="drum", audio=shot))

    samples.sort(key=lambda x: names.index(x.name))
    return DrumSlices(
        samples=samples,
        onset_times=onset_samples / sr,
        labels=[cluster_name[int(l)] for l in labels])


def classify_hits(drum_loop: np.ndarray, sr: int) -> list[tuple[float, str]]:
    """规则式鼓击分类：按低/高频段能量占比判 kick/hat/snare。
    不依赖聚类，半小节只有 3 个击点也能用。返回 [(时间, 标签)]。"""
    mono = to_mono(drum_loop)
    onsets = librosa.onset.onset_detect(y=mono, sr=sr, hop_length=HOP,
                                        backtrack=True, units="samples")
    hits = []
    win = int(0.08 * sr)
    for s in onsets:
        seg = mono[s:s + win]
        if len(seg) < 256 or np.abs(seg).max() < 1e-3:
            continue
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        freqs = np.fft.rfftfreq(len(seg), 1 / sr)
        total = spec.sum() + 1e-9
        low = spec[freqs < 150].sum() / total
        high = spec[freqs >= 4000].sum() / total
        if low > 0.25:
            label = "kick"
        elif high > 0.35:
            label = "hat"
        else:
            label = "snare"
        hits.append((s / sr, label))
    return hits


def _drum_onset_features(mono: np.ndarray, sr: int, s: int) -> dict:
    """单个 onset 的频段/质心/短促度特征（100ms 窗口）。"""
    win = int(0.1 * sr)
    seg = mono[s:s + win]
    if len(seg) < 256:
        seg = np.pad(seg, (0, win - len(seg)))
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freqs = np.fft.rfftfreq(len(seg), 1 / sr)
    tot = spec.sum() + 1e-9
    centroid = float((spec * freqs).sum() / tot)
    energy = seg ** 2
    cum = np.cumsum(energy) / (energy.sum() + 1e-9)
    dur90 = float(np.argmax(cum > 0.9) / sr)        # 90% 能量时长，越短越像 hat
    return {
        "low": float(spec[freqs < 150].sum() / tot),
        "mid": float(spec[(freqs >= 150) & (freqs < 2000)].sum() / tot),
        "high": float(spec[freqs >= 4000].sum() / tot),
        "centroid": centroid,
        "dur90": max(dur90, 1e-3),
        "peak": float(np.abs(seg).max()),
    }


def cut_oneshots_by_label(drum_audio: np.ndarray, sr: int,
                          hits: list[tuple[float, str]],
                          cfg: PipelineConfig) -> dict[str, np.ndarray]:
    """按相对特征各选一发 one-shot（不信任传入标签，重新打分）：
    kick=低频最强、hat=最亮最短、snare=中频 body 强且比 hat 暗。三者取不同 onset。
    """
    onset_samples = np.array(sorted(int(t * sr) for t, _ in hits))
    mono = to_mono(drum_audio)
    gaps = np.diff(np.append(onset_samples, len(mono))) / sr
    feats = [_drum_onset_features(mono, sr, int(s)) for s in onset_samples]
    if not feats:
        return {}

    cen = np.array([f["centroid"] for f in feats])
    cen_n = (cen - cen.min()) / (cen.ptp() + 1e-9)          # 质心归一
    clean = np.array([min(g, cfg.oneshot_max_sec) for g in gaps])  # 距下一击越远越干净
    chosen: dict[str, int] = {}

    def pick(score: np.ndarray) -> int:
        order = np.argsort(score)[::-1]
        for i in order:
            if i not in chosen.values():
                return int(i)
        return int(order[0])

    low = np.array([f["low"] for f in feats])
    high = np.array([f["high"] for f in feats])
    mid = np.array([f["mid"] for f in feats])
    dur = np.array([f["dur90"] for f in feats])
    short = 1.0 - (dur - dur.min()) / (dur.ptp() + 1e-9)    # 越短越接近 1

    chosen["kick"] = pick(low - 0.5 * high + 0.2 * clean)
    # hat：高频占比 + 高质心 + 短促，三者都要
    chosen["hat"] = pick(high + cen_n + short + 0.1 * clean)
    # snare：中频 body 强、有高频噪声、低频不主导（否则是 kick）、暗于 hat、有持续
    chosen["snare"] = pick(mid + 0.4 * high - 1.0 * low - 0.5 * cen_n
                           - 0.3 * short + 0.2 * clean)

    shots: dict[str, np.ndarray] = {}
    for label, i in chosen.items():
        s = int(onset_samples[i])
        nxt = onset_samples[onset_samples > s]
        e = int(nxt[0]) if len(nxt) else len(drum_audio)
        e = min(e, s + int(cfg.oneshot_max_sec * sr), len(drum_audio))
        shot = drum_audio[max(0, s - int(0.002 * sr)):e].copy()
        shot = gate(shot, cfg.gate_db)
        shots[label] = fade_out(shot, int(cfg.oneshot_fade_ms / 1000 * sr))
    return shots


def _phrase_features(phrases: list[np.ndarray], sr: int) -> np.ndarray:
    feats = []
    for p in phrases:
        mfcc = librosa.feature.mfcc(y=to_mono(p), sr=sr, n_mfcc=13).mean(axis=1)
        feats.append(mfcc)
    return np.array(feats)


def slice_long(loop: np.ndarray, sr: int, window: LoopWindow,
               cfg: PipelineConfig, base_name: str, max_n: int) -> list[Sample]:
    """按 downbeat 把 loop 切成小节 phrase，自相似度选出 1-2 段长样本。

    返回的样本不足时（轨道近乎静音）返回空列表。
    """
    mono = to_mono(loop)
    if np.abs(mono).max() < 1e-3:
        log.info("%s 轨近乎静音，跳过", base_name)
        return []

    bpb = cfg.beats_per_bar
    rel_beats = window.beats - window.start
    bar_bounds = np.append(rel_beats[::bpb], window.end - window.start)
    bar_samples = (bar_bounds * sr).astype(int)
    phrases = [loop[bar_samples[i]:bar_samples[i + 1]]
               for i in range(len(bar_samples) - 1)]
    phrases = [p for p in phrases if np.abs(to_mono(p)).max() > 1e-3]
    if not phrases:
        return []

    feats = _phrase_features(phrases, sr)
    sim = np.corrcoef(feats) if len(phrases) > 1 else np.ones((1, 1))

    picks: list[int]
    if max_n == 1 or len(phrases) == 1:
        picks = [int(np.argmax(sim.mean(axis=1)))]      # medoid：最有代表性的一小节
    else:
        a = int(np.argmax(sim.mean(axis=1)))
        b = int(np.argmin(sim[a]))                       # 与 a 差异最大的一小节
        picks = [a] if sim[a, b] > 0.95 else [a, b]      # 都很像就只留一段

    suffix = ["a", "b"]
    out = []
    fade = int(0.015 * sr)
    for i, pi in enumerate(picks[:max_n]):
        audio = phrases[pi].copy()
        audio = fade_in(audio, fade)
        audio = fade_out(audio, fade)
        name = base_name if max_n == 1 else f"{base_name}_{suffix[i]}"
        out.append(Sample(name=name, kind="long", audio=audio))
    log.info("%s 切出 %d 段长样本（小节 %s）", base_name, len(out), picks[:max_n])
    return out


def slice_all(loops: dict[str, np.ndarray], sr: int, window: LoopWindow,
              cfg: PipelineConfig) -> tuple[DrumSlices, list[Sample]]:
    """整体预算分配：鼓 ≤3 + 贝斯 1 + 旋律 ≤2，总数 ≤ cfg.max_samples。"""
    drums = slice_drums(loops["drums"], sr, cfg)
    budget = cfg.max_samples - len(drums.samples)
    bass = slice_long(loops["bass"], sr, window, cfg, "bass", max_n=1)
    budget -= len(bass)
    melody = slice_long(loops["melody"], sr, window, cfg, "melody",
                        max_n=max(0, min(cfg.melody_max_samples, budget)))
    longs = bass + melody
    total = len(drums.samples) + len(longs)
    assert total <= cfg.max_samples, f"样本数 {total} 超出预算"
    log.info("切片完成：%d 鼓 + %d 长样本 = %d (≤%d)",
             len(drums.samples), len(longs), total, cfg.max_samples)
    return drums, longs
