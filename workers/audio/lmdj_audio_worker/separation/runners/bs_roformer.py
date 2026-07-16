"""BS-RoFormer 4-stem runner：MSST(pinned clone) demix -> canonical four stems。

checkpoint：MSST release v1.0.12（ZFTurbo 训练，MUSDB SDR 9.65，MIT）。
实现在 runners/_msst.py；本模块只保留家族常量与 CLI 入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

from ._msst import msst_work
from .common import run_runner_main

RUNNER_ID = "bs-roformer-4stem"
FAMILY = "bs_roformer"
RUNNER_VERSION = "0.1.0"
ARTIFACT = "model_bs_roformer_ep_17_sdr_9.6568.ckpt"
MODEL_TYPE = "bs_roformer"
_WORKER_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = _WORKER_ROOT / "config" / "bs_roformer" / "config_bs_roformer_384_8_2_485100.yaml"


def _work(args):
    return msst_work(args, model_type=MODEL_TYPE, config_path=CONFIG_PATH,
                     artifact_name=ARTIFACT,
                     setup_hint="scripts/dev.sh setup-sep-bs-roformer")


def main(argv: list[str] | None = None) -> int:
    return run_runner_main(argv, runner_id=RUNNER_ID, family=FAMILY,
                           runner_version=RUNNER_VERSION, work=_work)


if __name__ == "__main__":
    sys.exit(main())
