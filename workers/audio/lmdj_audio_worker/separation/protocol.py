"""SeparatorRunner 协议（spec §5、§10）。

orchestrator 不 import 任何模型框架：按 registry 条目模板拼命令、子进程执行、
读取 separation.json。失败记录两级产生——runner 自写可捕获异常；文件缺失/损坏/
timeout/SIGKILL 由这里合成规范化失败记录（source="orchestrator"）并落盘。
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .cache import sha256_file
from .contract import (ContractError, SeparationError, SeparationResult,
                       SeparatorInfo, load_result_file, write_result)
from .registry import SeparatorEntry

STDERR_TAIL_CHARS = 2000


@dataclass(frozen=True)
class SeparationRequest:
    input_path: Path
    output_dir: Path
    device: str
    seed: int = 0
    repeat_id: int = 0


def build_command(entry: SeparatorEntry, request: SeparationRequest,
                  checkpoint_dir: Path) -> list[str]:
    mapping = {
        "input": str(request.input_path),
        "output_dir": str(request.output_dir),
        "device": request.device,
        "checkpoint_dir": str(checkpoint_dir),
        "seed": str(request.seed),
        "repeat_id": str(request.repeat_id),
    }
    result = []
    for part in entry.command:
        for key, value in mapping.items():
            part = part.replace(f"{{{key}}}", value)
        result.append(part)
    return result


def _tail(stream: object) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        stream = stream.decode("utf-8", errors="replace")
    return str(stream)[-STDERR_TAIL_CHARS:]


def _synthesize(entry: SeparatorEntry, request: SeparationRequest,
                category: str, exit_code: int | None, stderr_tail: str,
                elapsed: float) -> SeparationResult:
    result = SeparationResult(
        status="failed", source="orchestrator",
        input_sha256=sha256_file(request.input_path),
        separator=SeparatorInfo(
            id=entry.id, family=entry.family,
            checkpoint_sha256=entry.artifact_sha256,
            runner_version="unknown"),  # runner 已消失，版本不可知
        requested_device=request.device,
        error=SeparationError(
            category=category, exit_code=exit_code, stage="runner",
            stderr_tail=stderr_tail, elapsed_seconds=round(elapsed, 3)),
    )
    write_result(request.output_dir / "separation.json", result)
    return result


def run_separator(entry: SeparatorEntry, request: SeparationRequest,
                  checkpoint_dir: Path, timeout_sec: int = 3600) -> SeparationResult:
    request.output_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_command(entry, request, checkpoint_dir)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        return _synthesize(entry, request, "timeout", None,
                           _tail(exc.stderr), time.monotonic() - t0)
    elapsed = time.monotonic() - t0

    result_path = request.output_dir / "separation.json"
    try:
        result = load_result_file(result_path)
    except ContractError:
        result = None
    if result is not None and result.source == "runner":
        return result

    # 文件缺失/损坏/schema 不合法 → 按退出码合成（spec §5 orchestrator 合成）
    if proc.returncode in (-9, 137):
        category = "oom"          # SIGKILL：spec §5 的典型合成场景
    elif proc.returncode != 0:
        category = "inference"
    else:
        category = "invalid_stems"  # 退出 0 但结果不合法 = 契约违反
    return _synthesize(entry, request, category, proc.returncode,
                       _tail(proc.stderr), elapsed)
