"""HT Demucs runner：本地 checkpoint -> canonical four stems（spec §5）。

在 .venv-sep-demucs 中以子进程执行；权重从 cache 的 checkpoint_dir 加载，
不触发 demucs 自身的远程下载。归一化沿用 demo stems.py 的 (x-mean)/std 前处理
（推理后还原），canonical 输出保存模型原始幅度。
"""
from __future__ import annotations

import sys
from pathlib import Path

from .common import (CANONICAL_SR, DeviceMemorySampler, PerfTracker,
                     RunnerError, RunnerOutput, resolve_device,
                     run_runner_main)

RUNNER_ID = "htdemucs"
FAMILY = "demucs"
RUNNER_VERSION = "0.1.0"
ARTIFACT = "955717e8-8726e21a.th"
# registry htdemucs 条目的 inference 字段照抄这里（改动需 bump RUNNER_VERSION）
INFERENCE = {"shifts": 0, "split": True, "overlap": 0.25}


def _work(args) -> RunnerOutput:
    import torch
    from demucs.apply import apply_model
    from demucs.audio import AudioFile
    from demucs.states import load_model

    device = resolve_device(args.device)
    torch.manual_seed(args.seed)
    tracker = PerfTracker()

    artifact = Path(args.checkpoint_dir) / ARTIFACT
    if not artifact.exists():
        raise RunnerError(f"checkpoint 缺失: {artifact}", category="checksum")
    with tracker.phase("model_load"):
        model = load_model(artifact)
        model.to(device)
        model.eval()
    if model.samplerate != CANONICAL_SR:
        raise RunnerError(
            f"模型采样率 {model.samplerate} != {CANONICAL_SR}", category="invalid_stems")

    wav = AudioFile(args.input).read(
        streams=0, samplerate=model.samplerate, channels=model.audio_channels)
    ref = wav.mean(0)
    wav_norm = (wav - ref.mean()) / (ref.std() + 1e-8)

    sampler = DeviceMemorySampler(device)
    sampler.start()
    with tracker.phase("inference"), torch.no_grad():
        sources = apply_model(
            model, wav_norm[None], device=device, shifts=INFERENCE["shifts"],
            split=INFERENCE["split"], overlap=INFERENCE["overlap"],
            progress=False)[0]
    memory = sampler.stop()
    sources = sources * (ref.std() + 1e-8) + ref.mean()

    stems = {name: src.cpu().numpy().T.astype("float32")
             for name, src in zip(model.sources, sources)}
    performance = tracker.snapshot() | memory
    return RunnerOutput(stems=stems, actual_device=device,
                        performance=performance)


def main(argv: list[str] | None = None) -> int:
    return run_runner_main(argv, runner_id=RUNNER_ID, family=FAMILY,
                           runner_version=RUNNER_VERSION, work=_work)


if __name__ == "__main__":
    sys.exit(main())
