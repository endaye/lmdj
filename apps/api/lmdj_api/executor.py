from __future__ import annotations

import logging
import threading
from pathlib import Path

from lmdj_audio_worker import PipelineRunner, process_job

log = logging.getLogger(__name__)


class JobExecutor:
    """后台单槽执行器：daemon 线程跑 process_job，一个 Lock 串行化。

    demucs 现在走子进程，串行不是线程安全需要，而是避免并发子进程抢爆 CPU/内存。
    """

    def __init__(self, runner: PipelineRunner, jobs_root: Path) -> None:
        self.runner = runner
        self.jobs_root = jobs_root
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    def submit(self, audio_path: Path, job_id: str) -> None:
        thread = threading.Thread(target=self._run, args=(audio_path, job_id), daemon=True)
        self._threads.append(thread)
        thread.start()

    def _run(self, audio_path: Path, job_id: str) -> None:
        with self._lock:
            try:
                process_job(audio_path, jobs_root=self.jobs_root, runner=self.runner, job_id=job_id)
            except Exception:  # noqa: BLE001 — process_job 已落盘 failed；此处仅兜底不崩线程
                log.exception("job %s crashed outside process_job", job_id)

    def wait_idle(self, timeout: float = 30) -> None:
        """测试辅助：阻塞至所有已提交线程结束。"""
        for thread in list(self._threads):
            thread.join(timeout=timeout)
