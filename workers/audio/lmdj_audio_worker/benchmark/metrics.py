"""客观分轨指标（spec §9.2）。

SDR 用 museval（BSSEval v4，1s framewise median，MUSDB 惯例）；
SI-SDR / mixture consistency / 泄漏为自实现纯 numpy——精确定义见
docs/superpowers/plans/2026-07-16-separation-phase1c-metrics.md
（fast_bss_eval 0.1.4 无 torch 时 si_sdr 损坏，弃用）。
注意：SI_SDR_CEIL_DB 只 clip 精确重建（den<eps）；float32 舍入噪声可产生 >120dB 的值——聚合侧需知。
"""
from __future__ import annotations

import numpy as np

STEMS = ("drums", "bass", "vocals", "other")
MC_FLOOR_DB = -120.0
SI_SDR_CEIL_DB = 120.0
_EPS = 1e-12


def _per_channel(func, reference: np.ndarray, estimate: np.ndarray):
    values = []
    for ch in range(reference.shape[1]):
        v = func(reference[:, ch].astype(np.float64),
                 estimate[:, ch].astype(np.float64))
        if v is not None:
            values.append(v)
    return float(np.mean(values)) if values else None


def _si_sdr_1d(s: np.ndarray, s_hat: np.ndarray) -> float | None:
    energy = float(np.dot(s, s))
    if energy < _EPS:
        return None
    alpha = float(np.dot(s_hat, s)) / energy
    e_t = alpha * s
    e_r = s_hat - e_t
    num = float(np.dot(e_t, e_t))
    den = float(np.dot(e_r, e_r))
    if den < _EPS:
        return SI_SDR_CEIL_DB              # 完美重建，clip 对称上限
    return 10.0 * np.log10(max(num, _EPS) / den)


def si_sdr(reference: np.ndarray, estimate: np.ndarray) -> float | None:
    return _per_channel(_si_sdr_1d, reference, estimate)


def mixture_consistency(estimates: dict, mix: np.ndarray) -> float:
    total = sum(estimates[k] for k in STEMS)
    residual = float(np.sum((total.astype(np.float64)
                             - mix.astype(np.float64)) ** 2))
    mix_energy = float(np.sum(mix.astype(np.float64) ** 2))
    if mix_energy < _EPS:
        return MC_FLOOR_DB
    value = 10.0 * np.log10(max(residual, _EPS) / mix_energy)
    return max(value, MC_FLOOR_DB)


def leakage(estimates: dict, references: dict) -> dict:
    out: dict = {}
    for i in STEMS:
        est = estimates[i].astype(np.float64)
        est_energy = float(np.sum(est ** 2))
        if est_energy < _EPS:
            out[i] = None
            continue
        worst = 0.0
        for j in STEMS:
            if j == i:
                continue
            ref = references[j].astype(np.float64)
            ref_energy = float(np.sum(ref ** 2))
            if ref_energy < _EPS:
                continue
            beta = float(np.sum(est * ref)) / ref_energy
            worst = max(worst, beta * beta * ref_energy)
        out[i] = 10.0 * np.log10(max(worst, _EPS) / est_energy)
    return out
