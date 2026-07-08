from __future__ import annotations

import shutil
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Callable

from lmdj_patchify.patchify import patchify_package

from lmdj_audio_worker.runner import PipelineRunError, PipelineRunner
from lmdj_audio_worker.status import JobStatus, utc_now, write_status


def process_job(
    audio: Path,
    *,
    jobs_root: Path,
    runner: PipelineRunner,
    job_id: str | None = None,
    on_state: Callable[[JobStatus], None] | None = None,
) -> JobStatus:
    """同步执行一个 audio job：input 拷贝 → pipeline → patchify → 终态。

    所有状态转移先落盘（status.json 原子写）；任何异常落为 failed，不吞。
    v1 发射 queued → separating → patchifying → completed | failed。
    """
    if not audio.exists():
        raise FileNotFoundError(f"input audio not found: {audio}")
    job_id = job_id or uuid.uuid4().hex[:12]
    job_dir = jobs_root / job_id
    (job_dir / "input").mkdir(parents=True, exist_ok=True)
    input_copy = job_dir / "input" / audio.name
    shutil.copy2(audio, input_copy)

    def emit(status: JobStatus) -> JobStatus:
        written = write_status(job_dir, status)
        if on_state:
            on_state(written)
        return written

    status = emit(JobStatus(job_id=job_id, state="queued", created_at=utc_now()))
    try:
        status = emit(replace(status, state="separating"))
        package_dir = runner.run(input_copy, job_dir, job_id)
        status = emit(replace(status, state="patchifying", package_dir=package_dir.name))
        patch = patchify_package(package_dir)
        quality = str(patch.metadata.get("status") or "unknown")
        return emit(replace(status, state="completed", patch_id=patch.patch_id, quality=quality))
    except PipelineRunError as error:
        detail = str(error)
        if error.stderr_tail:
            detail += f"\nstderr tail:\n{error.stderr_tail}"
        return emit(replace(status, state="failed", error=detail))
    except Exception as error:  # noqa: BLE001 — 失败必须落盘可查（patchify ValueError 等）
        return emit(replace(status, state="failed", error=str(error)))
