"""SCNet-large runner：MSST(pinned clone) demix -> canonical four stems（spec §5）。

MSST 不是 pip 包：sys.path 注入 workers/audio/.msst（LMDJ_MSST_DIR 可覆盖）。
只读使用，不修改其源码；API 以 config/msst.lock 的 commit 为准。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .common import (CANONICAL_SR, DeviceMemorySampler, PerfTracker,
                     RunnerError, RunnerOutput, load_stereo_44k,
                     resolve_device, run_runner_main)

RUNNER_ID = "scnet-large"
FAMILY = "scnet"
RUNNER_VERSION = "0.1.0"
ARTIFACT = "SCNet-large_starrytong_fixed.ckpt"
MODEL_TYPE = "scnet"
_WORKER_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = _WORKER_ROOT / "config" / "scnet" / "config_musdb18_scnet_large_starrytong.yaml"
_CANONICAL_FROM_MSST = {"drums": "drums", "bass": "bass",
                        "vocals": "vocals", "other": "other"}


def _msst_dir() -> Path:
    return Path(os.environ.get("LMDJ_MSST_DIR", _WORKER_ROOT / ".msst"))


def _work(args) -> RunnerOutput:
    msst = _msst_dir()
    if not (msst / "utils").exists():
        raise RunnerError(
            f"MSST clone 缺失: {msst} — 先运行 scripts/dev.sh setup-sep-scnet",
            category="inference")
    sys.path.insert(0, str(msst))
    import torch
    from utils.model_utils import demix
    from utils.settings import get_model_from_config  # pinned commit 核对

    device = resolve_device(args.device)
    torch.manual_seed(args.seed)
    tracker = PerfTracker()

    artifact = Path(args.checkpoint_dir) / ARTIFACT
    if not artifact.exists():
        raise RunnerError(f"checkpoint 缺失: {artifact}", category="checksum")
    with tracker.phase("model_load"):
        model, config = get_model_from_config(MODEL_TYPE, str(CONFIG_PATH))
        state = torch.load(artifact, map_location="cpu", weights_only=False)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state)
        model.to(device)
        model.eval()

    wav = load_stereo_44k(args.input)          # (frames, 2) float32, 44.1k
    mix = wav.T                                # MSST demix 期望 (2, frames)

    sampler = DeviceMemorySampler(device)
    sampler.start()
    with tracker.phase("inference"), torch.no_grad():
        separated = demix(config, model, mix, torch.device(device),
                          model_type=MODEL_TYPE, pbar=False)
    memory = sampler.stop()

    stems = {}
    for canonical, msst_name in _CANONICAL_FROM_MSST.items():
        if msst_name not in separated:
            raise RunnerError(
                f"MSST 输出缺少 {msst_name}（收到 {sorted(separated)}）",
                category="invalid_stems")
        arr = separated[msst_name]
        if arr.ndim == 2 and arr.shape[0] == 2:   # (2, frames) -> (frames, 2)
            arr = arr.T
        stems[canonical] = arr.astype("float32")
    performance = tracker.snapshot() | memory
    return RunnerOutput(stems=stems, actual_device=device,
                        performance=performance)


def main(argv: list[str] | None = None) -> int:
    return run_runner_main(argv, runner_id=RUNNER_ID, family=FAMILY,
                           runner_version=RUNNER_VERSION, work=_work)


if __name__ == "__main__":
    sys.exit(main())
