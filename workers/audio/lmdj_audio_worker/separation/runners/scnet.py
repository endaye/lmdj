"""SCNet-large runner：MSST(pinned clone) demix -> canonical four stems（spec §5）。

实现在 runners/_msst.py（MSST 家族共享）；本模块只保留家族常量与 CLI 入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

from ._msst import msst_work
from .common import run_runner_main

RUNNER_ID = "scnet-large"
FAMILY = "scnet"
RUNNER_VERSION = "0.1.0"
ARTIFACT = "SCNet-large_starrytong_fixed.ckpt"
MODEL_TYPE = "scnet"
_WORKER_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = _WORKER_ROOT / "config" / "scnet" / "config_musdb18_scnet_large_starrytong.yaml"


def _work(args):
    return msst_work(args, model_type=MODEL_TYPE, config_path=CONFIG_PATH,
                     artifact_name=ARTIFACT,
                     setup_hint="scripts/dev.sh setup-sep-scnet")


def main(argv: list[str] | None = None) -> int:
    return run_runner_main(argv, runner_id=RUNNER_ID, family=FAMILY,
                           runner_version=RUNNER_VERSION, work=_work)


if __name__ == "__main__":
    sys.exit(main())
