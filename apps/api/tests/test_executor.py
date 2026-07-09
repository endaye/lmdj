import threading
from pathlib import Path

from lmdj_api.executor import JobExecutor
from lmdj_audio_worker.status import read_status

from tests.conftest import FakeRunner


def test_submit_runs_process_job_to_completed(tmp_path: Path, golden_audio: Path):
    jobs_root = tmp_path / "jobs"
    executor = JobExecutor(runner=FakeRunner(), jobs_root=jobs_root)

    executor.submit(golden_audio, "jobA")
    executor.wait_idle()

    status = read_status(jobs_root / "jobA")
    assert status.state == "completed"
    assert status.patch_id and status.patch_id.startswith("testsong-")


def test_jobs_run_serially_not_concurrently(tmp_path: Path, golden_audio: Path):
    jobs_root = tmp_path / "jobs"
    barrier = threading.Event()
    started = threading.Event()
    # 第一个 job 卡在 barrier；若并发，第二个也会 start
    slow = FakeRunner(barrier=barrier, started=started)
    executor = JobExecutor(runner=slow, jobs_root=jobs_root)

    executor.submit(golden_audio, "jobA")
    assert started.wait(timeout=5)  # jobA 进入 runner
    started.clear()
    executor.submit(golden_audio, "jobB")
    # jobA 仍卡着 → jobB 不应 start（锁串行）
    assert not started.wait(timeout=0.5)

    barrier.set()  # 放行 jobA
    executor.wait_idle()
    assert read_status(jobs_root / "jobA").state == "completed"
    assert read_status(jobs_root / "jobB").state == "completed"


def test_runner_failure_persists_failed_not_crash(tmp_path: Path, golden_audio: Path):
    from lmdj_audio_worker.runner import PipelineRunError

    jobs_root = tmp_path / "jobs"
    executor = JobExecutor(runner=FakeRunner(fail_with=PipelineRunError("boom", stderr_tail="x")),
                           jobs_root=jobs_root)
    executor.submit(golden_audio, "jobA")
    executor.wait_idle()

    assert read_status(jobs_root / "jobA").state == "failed"
