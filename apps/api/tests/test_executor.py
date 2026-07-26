import shutil
import threading
from pathlib import Path

from lmdj_api.executor import JobExecutor
from lmdj_audio_worker.status import JobStatus, read_status, write_status

from tests.conftest import FakeRunner

MATERIAL_GOLDEN = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "patchify"
    / "tests"
    / "fixtures"
    / "material-package"
)


class QueuedMaterialRunner:
    pipeline_id = "materials-v1"

    def __init__(self, barrier: threading.Event, extracting: threading.Event) -> None:
        self.barrier = barrier
        self.extracting = extracting

    def run_with_stages(self, audio, out_dir, song_id, on_stage):
        on_stage("extracting")
        self.extracting.set()
        self.barrier.wait(timeout=5)
        destination = out_dir / song_id
        shutil.copytree(MATERIAL_GOLDEN, destination)
        return destination

    def run(self, audio, out_dir, song_id):
        raise AssertionError("materials-v1 must use stage-aware execution")


def queued(
    jobs_root: Path,
    job_id: str,
    *,
    pipeline: str | None = None,
) -> JobStatus:
    return write_status(
        jobs_root / job_id,
        JobStatus(
            job_id=job_id,
            state="queued",
            submission_id=f"submission-{job_id}",
            original_filename=f"{job_id}.wav",
            pipeline=pipeline,
            created_at="2026-07-26T00:00:00Z",
        ),
    )


def test_submit_runs_process_job_to_completed(tmp_path: Path, golden_audio: Path):
    jobs_root = tmp_path / "jobs"
    executor = JobExecutor(runner=FakeRunner(), jobs_root=jobs_root)

    executor.submit(golden_audio, queued(jobs_root, "jobA"))
    executor.wait_idle()

    status = read_status(jobs_root / "jobA")
    assert status.state == "completed"
    assert status.patch_id and status.patch_id.startswith("testsong-")
    assert status.submission_id == "submission-jobA"


def test_completed_job_reclaims_its_owned_upload_directory(
    tmp_path: Path,
):
    jobs_root = tmp_path / "jobs"
    upload_dir = tmp_path / "lmdj-upload-owned"
    upload_dir.mkdir()
    audio = upload_dir / "upload.wav"
    audio.write_bytes(b"RIFF....WAVEfmt fake-audio")
    executor = JobExecutor(runner=FakeRunner(), jobs_root=jobs_root)

    executor.submit(
        audio,
        queued(jobs_root, "jobA"),
        cleanup_dir=upload_dir,
    )
    executor.wait_idle()

    assert not upload_dir.exists()
    assert read_status(jobs_root / "jobA").state == "completed"


def test_jobs_run_serially_not_concurrently(tmp_path: Path, golden_audio: Path):
    jobs_root = tmp_path / "jobs"
    barrier = threading.Event()
    started = threading.Event()
    # 第一个 job 卡在 barrier；若并发，第二个也会 start
    slow = FakeRunner(barrier=barrier, started=started)
    executor = JobExecutor(runner=slow, jobs_root=jobs_root)

    executor.submit(golden_audio, queued(jobs_root, "jobA"))
    assert started.wait(timeout=5)  # jobA 进入 runner
    started.clear()
    executor.submit(golden_audio, queued(jobs_root, "jobB"))
    # jobA 仍卡着 → jobB 不应 start（锁串行）
    assert not started.wait(timeout=0.5)

    barrier.set()  # 放行 jobA
    executor.wait_idle()
    assert read_status(jobs_root / "jobA").state == "completed"
    assert read_status(jobs_root / "jobB").state == "completed"


def test_snapshot_reports_active_capacity_and_fifo_positions(
    tmp_path: Path,
    golden_audio: Path,
):
    jobs_root = tmp_path / "jobs"
    barrier = threading.Event()
    started = threading.Event()
    executor = JobExecutor(
        runner=FakeRunner(barrier=barrier, started=started),
        jobs_root=jobs_root,
    )

    executor.submit(golden_audio, queued(jobs_root, "jobA"))
    assert started.wait(timeout=5)
    executor.submit(golden_audio, queued(jobs_root, "jobB"))
    executor.submit(golden_audio, queued(jobs_root, "jobC"))

    snapshot = executor.snapshot()
    assert snapshot.active_job_id == "jobA"
    assert snapshot.capacity.max_concurrency == 1
    assert snapshot.capacity.processing == 1
    assert snapshot.capacity.waiting == 2
    assert snapshot.positions == {"jobB": 1, "jobC": 2}

    barrier.set()
    executor.wait_idle()


def test_cancel_queued_removes_it_and_reclaims_owned_upload(
    tmp_path: Path,
    golden_audio: Path,
):
    jobs_root = tmp_path / "jobs"
    barrier = threading.Event()
    started = threading.Event()
    executor = JobExecutor(
        runner=FakeRunner(barrier=barrier, started=started),
        jobs_root=jobs_root,
    )
    executor.submit(golden_audio, queued(jobs_root, "jobA"))
    assert started.wait(timeout=5)
    upload_dir = tmp_path / "lmdj-upload-waiting"
    upload_dir.mkdir()
    waiting_audio = upload_dir / "upload.wav"
    waiting_audio.write_bytes(golden_audio.read_bytes())
    executor.submit(
        waiting_audio,
        queued(jobs_root, "jobB"),
        cleanup_dir=upload_dir,
    )

    assert executor.cancel_queued("jobB") is True

    assert not upload_dir.exists()
    assert executor.snapshot().positions == {}
    barrier.set()
    executor.wait_idle()


def test_material_jobs_remain_fifo_while_active_job_is_extracting(
    tmp_path: Path,
    golden_audio: Path,
):
    jobs_root = tmp_path / "jobs"
    barrier = threading.Event()
    extracting = threading.Event()
    executor = JobExecutor(
        runner=QueuedMaterialRunner(barrier, extracting),
        jobs_root=jobs_root,
    )

    executor.submit(
        golden_audio,
        queued(jobs_root, "material-a", pipeline="materials-v1"),
    )
    assert extracting.wait(timeout=5)
    executor.submit(
        golden_audio,
        queued(jobs_root, "material-b", pipeline="materials-v1"),
    )

    snapshot = executor.snapshot()
    active = read_status(jobs_root / "material-a")
    waiting = read_status(jobs_root / "material-b")
    assert snapshot.active_job_id == "material-a"
    assert snapshot.positions == {"material-b": 1}
    assert active.state == "extracting"
    assert active.pipeline == "materials-v1"
    assert waiting.state == "queued"
    assert waiting.pipeline == "materials-v1"

    barrier.set()
    executor.wait_idle()
    assert read_status(jobs_root / "material-a").state == "completed"
    assert read_status(jobs_root / "material-b").state == "completed"


def test_runner_failure_persists_failed_not_crash(tmp_path: Path, golden_audio: Path):
    from lmdj_audio_worker.runner import PipelineRunError

    jobs_root = tmp_path / "jobs"
    executor = JobExecutor(runner=FakeRunner(fail_with=PipelineRunError("boom", stderr_tail="x")),
                           jobs_root=jobs_root)
    executor.submit(golden_audio, queued(jobs_root, "jobA"))
    executor.wait_idle()

    assert read_status(jobs_root / "jobA").state == "failed"
