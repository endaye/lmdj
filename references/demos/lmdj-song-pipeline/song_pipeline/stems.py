"""阶段2 分轨：Demucs → drums / bass / melody(other [+vocals])"""
from __future__ import annotations

from hashlib import sha256
import logging
import os
from pathlib import Path
import random
import threading

import numpy as np
import soundfile as sf

from .config import PipelineConfig

log = logging.getLogger(__name__)

_models: dict[str, object] = {}
_demucs_random_lock = threading.Lock()


def _device() -> str:
    import torch
    forced = os.environ.get("SONG_PIPELINE_DEVICE")
    if forced:
        return forced
    return "cuda" if torch.cuda.is_available() else "cpu"


def _get_model(name: str):
    if name not in _models:
        from demucs.pretrained import get_model
        log.info("loading demucs model %s ...", name)
        model = get_model(name)
        model.eval()
        _models[name] = model
    return _models[name]


def _audio_seed(audio_path: Path) -> int:
    digest = sha256()
    with audio_path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return int.from_bytes(digest.digest(), "big")


def _apply_model_deterministically(audio_path: Path, model, wav, *, device: str):
    from demucs.apply import apply_model

    with _demucs_random_lock:
        previous_random_state = random.getstate()
        try:
            random.seed(_audio_seed(audio_path))
            return apply_model(model, wav, device=device, progress=True, split=True)
        finally:
            random.setstate(previous_random_state)


def separate(audio_path: Path, work_dir: Path, cfg: PipelineConfig) -> dict[str, Path]:
    """整曲分轨，返回 {"drums"|"bass"|"melody": wav路径}。

    vocals 按 cfg.vocals_strategy 并进 melody 或丢弃。
    结果缓存在 work_dir/stems 下，已存在则直接复用。
    """
    out_dir = work_dir / "stems"
    expected = {k: out_dir / f"{k}.wav" for k in ("drums", "bass", "melody")}
    if all(p.exists() for p in expected.values()):
        log.info("stems cached, skip demucs")
        return expected

    import torch
    from demucs.audio import AudioFile

    model = _get_model(cfg.demucs_model)
    wav = AudioFile(audio_path).read(
        streams=0, samplerate=model.samplerate, channels=model.audio_channels)
    ref = wav.mean(0)
    wav_norm = (wav - ref.mean()) / (ref.std() + 1e-8)

    device = _device()
    log.info("demucs separating on %s ...", device)
    with torch.no_grad():
        sources = _apply_model_deterministically(
            audio_path, model, wav_norm[None], device=device)[0]
    sources = sources * (ref.std() + 1e-8) + ref.mean()

    stems = {name: src for name, src in zip(model.sources, sources)}
    melody = stems["other"]
    if cfg.vocals_strategy == "merge" and "vocals" in stems:
        melody = melody + stems["vocals"]

    out_dir.mkdir(parents=True, exist_ok=True)
    arrays = {"drums": stems["drums"], "bass": stems["bass"], "melody": melody}
    for name, tensor in arrays.items():
        data = tensor.cpu().numpy().T.astype(np.float32)  # (samples, channels)
        peak = float(np.abs(data).max())
        if peak > 1.0:
            data /= peak
        sf.write(expected[name], data, model.samplerate)
        log.info("stem %s -> %s", name, expected[name])
    return expected
