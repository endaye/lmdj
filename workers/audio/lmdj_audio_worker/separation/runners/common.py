"""Runner 侧共享 scaffold：CLI 契约、canonical 落盘、失败 JSON 自写（spec §5）。

本模块运行在 runner 专用 venv 中；除性能采集（Task 2）的懒加载 torch 外，
只依赖 numpy/soundfile + 主包 contract/cache。
"""
from __future__ import annotations

import argparse
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..cache import sha256_file
from ..contract import (CANONICAL_STEMS, ERROR_CATEGORIES, SeparationError,
                        SeparationResult, SeparatorInfo, write_result)

CANONICAL_SR = 44100
STDERR_TAIL_CHARS = 2000


class RunnerError(Exception):
    def __init__(self, message: str, category: str) -> None:
        if category not in ERROR_CATEGORIES:
            raise ValueError(f"未知错误类别 {category!r}，必须属于 {ERROR_CATEGORIES}")
        super().__init__(message)
        self.category = category


@dataclass
class RunnerOutput:
    stems: dict
    actual_device: str
    performance: dict


def write_canonical_stems(out_dir: Path, stems: dict) -> dict[str, str]:
    import numpy as np
    import soundfile as sf

    missing = [k for k in CANONICAL_STEMS if k not in stems]
    if missing:
        raise RunnerError(f"缺少 canonical 轨 {missing}", category="invalid_stems")
    rel: dict[str, str] = {}
    for name in CANONICAL_STEMS:
        data = stems[name]
        if data.ndim != 2 or data.shape[1] != 2 or data.dtype != np.float32:
            raise RunnerError(
                f"{name}: 需要 (frames, 2) float32，收到 shape={data.shape} "
                f"dtype={data.dtype}", category="invalid_stems")
        path = out_dir / "stems" / f"{name}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, data, CANONICAL_SR, subtype="FLOAT")
        rel[name] = f"stems/{name}.wav"
    return rel


def load_stereo_44k(path: Path) -> "np.ndarray":
    import numpy as np  # noqa: F401 —— 注解用
    import soundfile as sf

    try:
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:
        raise RunnerError(f"无法读取输入 {path}: {exc}", category="inference") from exc
    if sr != CANONICAL_SR:
        raise RunnerError(
            f"输入采样率 {sr}，v1 runner 只接受 {CANONICAL_SR}", category="inference")
    if data.shape[1] == 1:
        data = data.repeat(2, axis=1)
    return data


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser("separator-runner")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", required=True, choices=("cpu", "mps"))
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args(argv)


def _checkpoint_sha(checkpoint_dir: Path) -> str:
    name = Path(checkpoint_dir).name
    if len(name) == 64 and all(c in "0123456789abcdef" for c in name):
        return name
    raise RunnerError(
        f"checkpoint_dir 目录名不是 SHA-256（cache 布局应为 <id>/<sha256>/）: {name}",
        category="checksum")


def run_runner_main(argv: list[str] | None, *, runner_id: str, family: str,
                    runner_version: str,
                    work: Callable[[argparse.Namespace], RunnerOutput]) -> int:
    args = _parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    input_sha = sha256_file(args.input)
    separator = SeparatorInfo(id=runner_id, family=family,
                              checkpoint_sha256="0" * 64,
                              runner_version=runner_version)

    def fail(category: str, message: str) -> int:
        result = SeparationResult(
            status="failed", source="runner", input_sha256=input_sha,
            separator=separator, requested_device=args.device,
            error=SeparationError(
                category=category, exit_code=None, stage="runner",
                stderr_tail=message[-STDERR_TAIL_CHARS:], elapsed_seconds=0.0))
        write_result(args.output / "separation.json", result)
        return 1

    try:
        separator = SeparatorInfo(id=runner_id, family=family,
                                  checkpoint_sha256=_checkpoint_sha(args.checkpoint_dir),
                                  runner_version=runner_version)
        output = work(args)
        rel = write_canonical_stems(args.output, output.stems)
        frames = len(output.stems["drums"])
        result = SeparationResult(
            status="completed", source="runner", input_sha256=input_sha,
            separator=separator, requested_device=args.device,
            actual_device=output.actual_device, stems=rel,
            audio={"sample_rate": CANONICAL_SR, "channels": 2,
                   "duration_seconds": round(frames / CANONICAL_SR, 6)},
            performance=output.performance)
        write_result(args.output / "separation.json", result)
        return 0
    except RunnerError as exc:
        return fail(exc.category, str(exc))
    except MemoryError:
        return fail("oom", "MemoryError")
    except Exception:  # noqa: BLE001 —— 任何未预期异常都必须落盘为失败记录
        return fail("inference", traceback.format_exc())


import contextlib
import resource
import sys as _sys
import threading
import time as _time


class PerfTracker:
    """model_load / inference 分段计时 + wall + peak RSS（spec §5 performance）。"""

    def __init__(self) -> None:
        self._t0 = _time.monotonic()
        self._phases: dict[str, float] = {}

    @contextlib.contextmanager
    def phase(self, name: str):
        start = _time.monotonic()
        try:
            yield
        finally:
            self._phases[name] = self._phases.get(name, 0.0) + (
                _time.monotonic() - start)

    def snapshot(self) -> dict:
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_rss = ru if _sys.platform == "darwin" else ru * 1024  # Linux 为 KB
        return {
            "model_load_seconds": round(self._phases.get("model_load", 0.0), 3),
            "inference_seconds": round(self._phases.get("inference", 0.0), 3),
            "wall_seconds": round(_time.monotonic() - self._t0, 3),
            "peak_rss_bytes": int(peak_rss),
        }


class DeviceMemorySampler:
    """MPS 设备内存采样（spec §5）：100ms 采样 current/driver，峰值取 driver。

    PyTorch MPS 无 peak API；采样式采集会低估真峰值，属已知固有误差——
    门槛判定统一用同一算法即可比。CPU 设备固定写 0。
    """

    def __init__(self, device: str, interval_s: float = 0.1) -> None:
        self.device = device
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._peak_current = 0
        self._peak_driver = 0

    def _sample_loop(self) -> None:
        import torch
        while not self._stop.is_set():
            self._peak_current = max(
                self._peak_current, int(torch.mps.current_allocated_memory()))
            self._peak_driver = max(
                self._peak_driver, int(torch.mps.driver_allocated_memory()))
            self._stop.wait(self.interval_s)

    def start(self) -> None:
        if self.device != "mps":
            return
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=5)
        return {
            "peak_device_memory_bytes": self._peak_driver,
            "peak_mps_current_allocated_bytes": self._peak_current,
            "sample_interval_ms": int(self.interval_s * 1000),
        }


def resolve_device(requested: str) -> str:
    if requested == "mps":
        import torch
        if not torch.backends.mps.is_available():
            raise RunnerError(
                "请求 mps 但 torch.backends.mps 不可用（不允许静默转 CPU，spec §10）",
                category="unsupported_device")
    return requested
