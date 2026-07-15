"""canonical 四轨 → legacy 三轨兼容映射（spec §5）。

drums/bass 原样；melody = vocals + other（等价于 demo 的 vocals_strategy="merge"，
v1 只支持 merge，遇 drop 显式报错）。沿用旧实现（demo stems.py）的
"单轨峰值超过 1.0 时缩放到 1.0" 规则。canonical 原始分轨保持未归一化、
不被改写；legacy 输出写到独立目录（两组音频不得复用同一文件）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from .config import PipelineConfig

CANONICAL_STEMS = ("drums", "bass", "vocals", "other")


def map_canonical_to_legacy(canonical_dir: Path, legacy_dir: Path,
                            cfg: PipelineConfig | None = None) -> dict[str, Path]:
    cfg = cfg or PipelineConfig()
    if cfg.vocals_strategy != "merge":
        raise ValueError(
            f"v1 兼容层只支持 vocals_strategy='merge'，收到 {cfg.vocals_strategy!r}"
            "（spec §5：不得静默按 merge 处理）")
    canonical_dir = Path(canonical_dir)
    legacy_dir = Path(legacy_dir)
    if legacy_dir.resolve() == canonical_dir.resolve():
        raise ValueError("legacy 输出不得与 canonical 是同一目录（不得复用同一文件）")

    arrays: dict[str, np.ndarray] = {}
    rates: set[int] = set()
    for name in CANONICAL_STEMS:
        path = canonical_dir / f"{name}.wav"
        if not path.exists():
            raise FileNotFoundError(f"canonical stems 缺少 {name}.wav: {canonical_dir}")
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        arrays[name] = data
        rates.add(sr)
    if len(rates) != 1:
        raise ValueError(f"canonical stems 采样率不一致: {sorted(rates)}")
    if len(arrays["vocals"]) != len(arrays["other"]):
        raise ValueError("vocals 与 other 长度不一致，无法合成 melody")
    sr = rates.pop()

    legacy = {
        "drums": arrays["drums"],
        "bass": arrays["bass"],
        "melody": arrays["vocals"] + arrays["other"],
    }
    legacy_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for name, data in legacy.items():
        peak = float(np.abs(data).max()) if len(data) else 0.0
        if peak > 1.0:
            data = data / peak
        target = legacy_dir / f"{name}.wav"
        sf.write(target, data, sr)  # demo 同款默认 subtype（WAV → PCM_16）
        out[name] = target
    return out
