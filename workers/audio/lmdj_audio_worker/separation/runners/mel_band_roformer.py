"""Mel-Band RoFormer 4-stem runner：MSST(pinned clone) demix -> canonical four stems。

checkpoint：MSST release v1.0.11 ep_1（SDR 8.22，MIT）。同 release 的 ep_5（8.94）
是多分卷 zip，与单 artifact 缓存契约冲突——升级路径见 decision-log 2026-07-16。
实现在 runners/_msst.py；本模块只保留家族常量与 CLI 入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

from ._msst import msst_work
from .common import run_runner_main

RUNNER_ID = "mel-roformer-4stem"
FAMILY = "mel_band_roformer"
RUNNER_VERSION = "0.1.0"
ARTIFACT = "model_mel_band_roformer_ep_1_sdr_8.2175.ckpt"
MODEL_TYPE = "mel_band_roformer"
_WORKER_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = (_WORKER_ROOT / "config" / "mel_band_roformer"
               / "model_mel_band_roformer_ep_1_sdr_8.2175.yaml")


def _work(args):
    return msst_work(args, model_type=MODEL_TYPE, config_path=CONFIG_PATH,
                     artifact_name=ARTIFACT,
                     setup_hint="scripts/dev.sh setup-sep-mel-roformer")


def main(argv: list[str] | None = None) -> int:
    return run_runner_main(argv, runner_id=RUNNER_ID, family=FAMILY,
                           runner_version=RUNNER_VERSION, work=_work)


if __name__ == "__main__":
    sys.exit(main())
