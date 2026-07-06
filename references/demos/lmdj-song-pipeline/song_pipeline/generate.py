"""阶段1 音乐生成：MusicGen 封装，prompt 模板固定 BPM + 风格。

本地 CPU 用 facebook/musicgen-small（~30s 上限）；云端 GPU 可换 medium/large
或 ACE-Step（接口一致：generate() 返回 wav 路径 + bpm）。
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .audio_utils import write_wav

log = logging.getLogger(__name__)

PROMPT_TEMPLATE = ("{bpm} bpm {style}, steady drum groove, warm bass, "
                   "mellow melody, instrumental, no vocals")

_cached: dict[str, tuple] = {}


def _load(model_name: str):
    if model_name not in _cached:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
        log.info("loading %s ...", model_name)
        processor = AutoProcessor.from_pretrained(model_name)
        model = MusicgenForConditionalGeneration.from_pretrained(model_name)
        model.eval()
        _cached[model_name] = (processor, model)
    return _cached[model_name]


def generate(out_path: Path, bpm: int = 85, style: str = "lofi hiphop beat",
             seconds: float = 30.0, seed: int | None = None,
             model_name: str = "facebook/musicgen-small") -> tuple[Path, int]:
    """生成一段固定 BPM 的音乐写到 out_path，返回 (路径, bpm)。"""
    import torch

    processor, model = _load(model_name)
    prompt = PROMPT_TEMPLATE.format(bpm=bpm, style=style)
    log.info("generating %.0fs: %r", seconds, prompt)
    if seed is not None:
        torch.manual_seed(seed)

    inputs = processor(text=[prompt], padding=True, return_tensors="pt")
    with torch.no_grad():
        audio = model.generate(
            **inputs,
            max_new_tokens=int(seconds * 50),   # musicgen 50 token/s
            do_sample=True,
            guidance_scale=3.0,
        )
    sr = model.config.audio_encoder.sampling_rate
    mono = audio[0, 0].cpu().numpy().astype(np.float32)
    peak = float(np.abs(mono).max())
    if peak > 0:
        mono /= max(1.0, peak)
    write_wav(out_path, np.stack([mono, mono], axis=1), sr)
    log.info("generated %.1fs @ %d Hz -> %s", len(mono) / sr, sr, out_path)
    return out_path, bpm
