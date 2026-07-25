from __future__ import annotations

import shutil
import uuid
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Callable

from lmdj_patchify.patchify import patchify_package

from lmdj_audio_worker.export_source import build_export_source, write_export_source
from lmdj_audio_worker.music_metadata import KeyAnalyzer, KeyEstimate, PfsKeyAnalyzer
from lmdj_audio_worker.runner import PipelineRunError, PipelineRunner
from lmdj_audio_worker.status import JobStatus, utc_now, write_status


def _source_id(audio: Path) -> str:
    digest = sha256()
    with audio.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return f"source-{digest.hexdigest()}"


def process_job(
    audio: Path,
    *,
    jobs_root: Path,
    runner: PipelineRunner,
    job_id: str | None = None,
    on_state: Callable[[JobStatus], None] | None = None,
    key_analyzer: KeyAnalyzer | None = None,
    initial_status: JobStatus | None = None,
) -> JobStatus:
    """同步执行一个 audio job：input 拷贝 → pipeline → patchify → 终态。

    所有状态转移先落盘（status.json 原子写）；任何异常落为 failed，不吞。
    v1 发射 queued → separating → patchifying → completed | failed。
    """
    if not audio.exists():
        raise FileNotFoundError(f"input audio not found: {audio}")
    if initial_status is not None and job_id is None:
        job_id = initial_status.job_id
    job_id = job_id or uuid.uuid4().hex[:12]
    if (
        initial_status is not None
        and (
            initial_status.job_id != job_id
            or initial_status.state != "queued"
        )
    ):
        raise ValueError("initial status must be queued for the selected job_id")
    job_dir = jobs_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    def emit(status: JobStatus) -> JobStatus:
        written = write_status(job_dir, status)
        if on_state:
            on_state(written)
        return written

    status = emit(
        initial_status
        or JobStatus(job_id=job_id, state="queued", created_at=utc_now()),
    )
    try:
        source_id = _source_id(audio)
        input_copy = job_dir / "input" / audio.name
        input_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(audio, input_copy)
        status = emit(replace(status, state="separating"))
        package_dir = runner.run(input_copy, job_dir, source_id)
        status = emit(replace(status, state="patchifying", package_dir=package_dir.name))
        patch = patchify_package(package_dir)
        analyzer = key_analyzer or PfsKeyAnalyzer()
        key: KeyEstimate | None = None
        warnings: list[str] = []
        try:
            key = analyzer.analyze(input_copy)
        except Exception as error:  # noqa: BLE001 — metadata 退化不能使 playable Job 失败
            warnings.append(f"key analysis failed: {error}")
        source = build_export_source(package_dir, patch, key, warnings)
        write_export_source(package_dir, source)
        quality = str(patch.metadata.get("status") or "unknown")
        return emit(replace(status, state="completed", patch_id=patch.patch_id, quality=quality))
    except PipelineRunError as error:
        detail = str(error)
        if error.stderr_tail:
            detail += f"\nstderr tail:\n{error.stderr_tail}"
        return emit(replace(status, state="failed", error=detail))
    except Exception as error:  # noqa: BLE001 — 失败必须落盘可查（patchify ValueError 等）
        return emit(replace(status, state="failed", error=str(error)))
