from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path

from lmdj_audio_worker import PipelineRunner, process_job
from lmdj_audio_worker.status import JobStatus, write_status

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueueCapacity:
    max_concurrency: int
    processing: int
    waiting: int


@dataclass(frozen=True)
class QueueSnapshot:
    capacity: QueueCapacity
    positions: dict[str, int]
    active_job_id: str | None


@dataclass(frozen=True)
class _QueuedJob:
    audio_path: Path
    initial_status: JobStatus


class JobExecutor:
    """严格 FIFO 的后台单槽执行器。

    一个 daemon worker 从显式 deque 取任务，因此等待顺序、容量和位置都能被
    API 如实观测；等待任务不会提前进入 ``separating``。
    """

    def __init__(self, runner: PipelineRunner, jobs_root: Path) -> None:
        self.runner = runner
        self.jobs_root = jobs_root
        self._condition = threading.Condition()
        self._pending: deque[_QueuedJob] = deque()
        self._active_job_id: str | None = None
        self._worker = threading.Thread(
            target=self._work,
            name="lmdj-job-executor",
            daemon=True,
        )
        self._worker.start()

    def submit(self, audio_path: Path, initial_status: JobStatus) -> None:
        if initial_status.state != "queued":
            raise ValueError("submitted JobStatus must be queued")
        with self._condition:
            if (
                self._active_job_id == initial_status.job_id
                or any(
                    item.initial_status.job_id == initial_status.job_id
                    for item in self._pending
                )
            ):
                raise ValueError(f"job already submitted: {initial_status.job_id}")
            self._pending.append(_QueuedJob(audio_path, initial_status))
            self._condition.notify_all()

    def snapshot(self) -> QueueSnapshot:
        with self._condition:
            positions = {
                item.initial_status.job_id: index
                for index, item in enumerate(self._pending, start=1)
            }
            return QueueSnapshot(
                capacity=QueueCapacity(
                    max_concurrency=1,
                    processing=1 if self._active_job_id else 0,
                    waiting=len(self._pending),
                ),
                positions=positions,
                active_job_id=self._active_job_id,
            )

    def wait_idle(self, timeout: float = 30) -> None:
        """测试辅助：等待显式队列和执行槽同时为空。"""
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._active_job_id is not None or self._pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("job executor did not become idle")
                self._condition.wait(timeout=remaining)

    def _work(self) -> None:
        while True:
            with self._condition:
                while not self._pending:
                    self._condition.wait()
                item = self._pending.popleft()
                self._active_job_id = item.initial_status.job_id
                self._condition.notify_all()

            try:
                process_job(
                    item.audio_path,
                    jobs_root=self.jobs_root,
                    runner=self.runner,
                    job_id=item.initial_status.job_id,
                    initial_status=item.initial_status,
                )
            except Exception as error:  # noqa: BLE001 — process_job 外的失败也必须落盘
                log.exception(
                    "job %s crashed outside process_job",
                    item.initial_status.job_id,
                )
                write_status(
                    self.jobs_root / item.initial_status.job_id,
                    replace(
                        item.initial_status,
                        state="failed",
                        error_code="executor_error",
                        error=str(error),
                    ),
                )
            finally:
                with self._condition:
                    self._active_job_id = None
                    self._condition.notify_all()
