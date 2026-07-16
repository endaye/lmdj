"""客观分轨指标（spec §9.2）。

SDR 用 museval（BSSEval v4，1s framewise median，MUSDB 惯例）；
SI-SDR / mixture consistency / 泄漏为自实现纯 numpy——精确定义见
docs/superpowers/plans/2026-07-16-separation-phase1c-metrics.md
（fast_bss_eval 0.1.4 无 torch 时 si_sdr 损坏，弃用）。
注意：SI_SDR_CEIL_DB 只 clip 精确重建（den<eps）；float32 舍入噪声可产生 >120dB 的值——聚合侧需知。
"""
from __future__ import annotations

import warnings
from pathlib import Path

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


def _finite_or_none(value: float | None, label: str, problems: list[str]) -> float | None:
    """non-finite（NaN/inf）值统一收敛到 None，并记录 warnings（2026-07-16 review 追加）。

    carry-forward from Task 2 review: si_sdr / mixture_consistency 在遇到损坏
    （含 NaN）音频时会静默传播 NaN；objective_for_combo 里每个数值都要经过
    这一守卫，命中时把该值置 None 并在 warnings 里记录是哪个 stem/metric。
    """
    if value is None:
        return None
    if not np.isfinite(value):
        problems.append(f"{label}: 非有限值（NaN/inf），已置 None")
        return None
    return float(value)


def sdr_framewise_median(references: dict, estimates: dict) -> dict[str, float | None]:
    """museval BSSEval v4：堆叠 (4, samples, ch)，window=hop=44100（1s 帧），
    逐 stem 帧 nanmedian；某 stem 全 NaN → None（不抛异常）。
    """
    from museval.metrics import bss_eval  # 懒加载：主包 dependencies 保持 []

    ref_stack = np.stack([references[stem].astype(np.float64) for stem in STEMS])
    est_stack = np.stack([estimates[stem].astype(np.float64) for stem in STEMS])
    sdr, _isr, _sir, _sar, _perms = bss_eval(ref_stack, est_stack, window=44100, hop=44100)

    out: dict[str, float | None] = {}
    for i, stem in enumerate(STEMS):
        with warnings.catch_warnings():
            # nanmedian 对全 NaN 切片会发 RuntimeWarning，这里是预期路径，不需要冒泡。
            warnings.simplefilter("ignore", category=RuntimeWarning)
            value = np.nanmedian(sdr[i])
        out[stem] = None if np.isnan(value) else float(value)
    return out


def load_stems_dir(dir: Path) -> dict[str, np.ndarray]:
    """4 canonical wav（drums/bass/vocals/other）→ (frames, 2) float32；缺轨 ValueError。"""
    import soundfile as sf  # 懒加载：与 separation/contract.py 同惯例

    dir = Path(dir)
    missing: list[str] = []
    out: dict[str, np.ndarray] = {}
    for stem in STEMS:
        path = dir / f"{stem}.wav"
        if not path.exists():
            missing.append(stem)
            continue
        data, _sr = sf.read(str(path), dtype="float32", always_2d=True)
        out[stem] = data
    if missing:
        raise ValueError(f"{dir}: 缺少 stem 音频 {missing}")
    return out


def load_gt(track) -> dict[str, np.ndarray]:
    """按 `manifest.data_root()` 解析 `track.ground_truth`；采样率非 44100 → ValueError。

    与估计的长度对齐（差 ≤1 sample 截齐 / 超差 ValueError）在 `objective_for_combo`
    内完成——这里只负责按 GT 自身采样率装载，不做跨数组对齐。
    """
    import soundfile as sf  # 懒加载：与 separation/contract.py 同惯例

    from .manifest import data_root

    root = data_root()
    out: dict[str, np.ndarray] = {}
    for stem in STEMS:
        rel = track.ground_truth[stem]
        path = root / rel
        info = sf.info(str(path))
        if info.samplerate != 44100:
            raise ValueError(
                f"{stem}: GT 采样率 {info.samplerate} != 44100（{path}）")
        data, _sr = sf.read(str(path), dtype="float32", always_2d=True)
        out[stem] = data
    return out


def _align_gt_estimates(gt: dict, estimates: dict) -> tuple[dict, dict]:
    """GT 与估计逐 stem 对齐：长度差 ≤1 sample 截齐到较短者；超差 ValueError。"""
    aligned_gt: dict[str, np.ndarray] = {}
    aligned_est: dict[str, np.ndarray] = {}
    for stem in STEMS:
        g = gt[stem]
        e = estimates[stem]
        diff = abs(g.shape[0] - e.shape[0])
        if diff > 1:
            raise ValueError(
                f"{stem}: GT/估计长度差 {diff} samples 超过 ≤1 容差"
                f"（gt={g.shape[0]}, est={e.shape[0]}）")
        n = min(g.shape[0], e.shape[0])
        aligned_gt[stem] = g[:n]
        aligned_est[stem] = e[:n]
    return aligned_gt, aligned_est


def objective_for_combo(combo_dir: Path, track, mix: np.ndarray) -> dict:
    """逐组合客观指标（spec §9.2）。

    无 GT：只出 `{"has_gt": False, "mixture_consistency": ...}`。
    有 GT：再补 `sdr`/`si_sdr`（逐 stem + mean，mean 对 None 跳过）/`leakage`。
    每个数值都经 `_finite_or_none` 守卫：非有限（NaN/inf）→ None，并在
    `warnings` 里记录是哪个 stem/metric（不抛异常）。
    """
    combo_dir = Path(combo_dir)
    estimates = load_stems_dir(combo_dir / "separation" / "stems")

    problems: list[str] = []
    mc = _finite_or_none(mixture_consistency(estimates, mix), "mixture_consistency", problems)

    result: dict = {"has_gt": bool(track.has_ground_truth)}

    if not track.has_ground_truth:
        result["mixture_consistency"] = mc
        if problems:
            result["warnings"] = problems
        return result

    gt_raw = load_gt(track)
    gt, est = _align_gt_estimates(gt_raw, estimates)

    sdr_raw = sdr_framewise_median(gt, est)
    sdr: dict[str, float | None] = {}
    sdr_values: list[float] = []
    for stem in STEMS:
        v = _finite_or_none(sdr_raw.get(stem), f"sdr.{stem}", problems)
        sdr[stem] = v
        if v is not None:
            sdr_values.append(v)
    sdr["mean"] = float(np.mean(sdr_values)) if sdr_values else None

    si_sdr_out: dict[str, float | None] = {}
    si_sdr_values: list[float] = []
    for stem in STEMS:
        v = _finite_or_none(si_sdr(gt[stem], est[stem]), f"si_sdr.{stem}", problems)
        si_sdr_out[stem] = v
        if v is not None:
            si_sdr_values.append(v)
    si_sdr_out["mean"] = float(np.mean(si_sdr_values)) if si_sdr_values else None

    leak_raw = leakage(est, gt)
    leak = {stem: _finite_or_none(leak_raw.get(stem), f"leakage.{stem}", problems)
            for stem in STEMS}

    result["mixture_consistency"] = mc
    result["sdr"] = sdr
    result["si_sdr"] = si_sdr_out
    result["leakage"] = leak
    if problems:
        result["warnings"] = problems
    return result
