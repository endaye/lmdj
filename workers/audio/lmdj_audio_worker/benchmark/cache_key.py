"""benchmark 结果缓存 key（spec §8）：六元组，缺一不可。

input sha256 + checkpoint sha256 + runner version + config hash + device + seed/repeat
"""
from __future__ import annotations

import hashlib
import importlib
import json

from ..separation.registry import SeparatorEntry

_RUNNER_PKG = "lmdj_audio_worker.separation.runners"


def runner_version(entry: SeparatorEntry) -> str:
    try:
        module = importlib.import_module(f"{_RUNNER_PKG}.{entry.runner}")
    except ImportError as exc:
        raise ValueError(f"未知 runner 模块 {entry.runner!r}") from exc
    version = getattr(module, "RUNNER_VERSION", None)
    if not isinstance(version, str):
        raise ValueError(f"runner 模块 {entry.runner!r} 缺少 RUNNER_VERSION")
    return version


def config_hash(entry: SeparatorEntry) -> str:
    payload = json.dumps(
        {"inference": entry.inference, "env_lock": entry.env_lock_sha256,
         "artifact": entry.artifact_sha256},
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def describe(input_sha256: str, entry: SeparatorEntry, device: str,
             seed: int, repeat: int) -> dict:
    return {
        "input_sha256": input_sha256,
        "checkpoint_sha256": entry.artifact_sha256,
        "runner_version": runner_version(entry),
        "config_hash": config_hash(entry),
        "device": device,
        "seed_repeat": f"{seed}/{repeat}",
    }


def combo_cache_key(input_sha256: str, entry: SeparatorEntry, device: str,
                    seed: int, repeat: int) -> str:
    desc = describe(input_sha256, entry, device, seed, repeat)
    payload = json.dumps(desc, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()
