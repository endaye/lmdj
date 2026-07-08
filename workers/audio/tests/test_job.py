import json
import shutil
from pathlib import Path

import pytest

from lmdj_audio_worker.job import process_job
from lmdj_audio_worker.runner import PipelineRunError
from lmdj_audio_worker.status import read_status

from tests.conftest import GOLDEN, FakeRunner


def test_happy_path_completes_with_patch(tmp_path: Path, sample_audio: Path, fake_runner: FakeRunner):
    jobs_root = tmp_path / "jobs"

    final = process_job(sample_audio, jobs_root=jobs_root, runner=fake_runner, job_id="jobtest")

    assert final.state == "completed"
    assert final.quality == "passed"
    assert final.package_dir == "jobtest"
    assert final.patch_id and final.patch_id.startswith("testsong-")  # fixture 的 report.song_id
    job_dir = jobs_root / "jobtest"
    assert (job_dir / "input" / sample_audio.name).exists()
    assert (job_dir / "jobtest" / "patch.json").exists()
    assert read_status(job_dir).state == "completed"


def test_state_sequence_is_persisted_per_transition(tmp_path: Path, sample_audio: Path):
    jobs_root = tmp_path / "jobs"
    job_dir = jobs_root / "jobtest"
    seen: list[str] = []
    # FakeRunner 运行期间读盘：此刻必须已是 separating
    runner = FakeRunner(on_run=lambda: seen.append(read_status(job_dir).state))

    transitions: list[str] = []
    process_job(
        sample_audio, jobs_root=jobs_root, runner=runner, job_id="jobtest",
        on_state=lambda s: transitions.append(s.state),
    )

    assert transitions == ["queued", "separating", "patchifying", "completed"]
    assert seen == ["separating"]


def test_rejected_pipeline_is_completed_with_quality_flag(tmp_path: Path, sample_audio: Path):
    rejected_pkg = tmp_path / "rejected-pkg"
    shutil.copytree(GOLDEN, rejected_pkg)
    report = json.loads((rejected_pkg / "report.json").read_text())
    report["status"] = "rejected"
    (rejected_pkg / "report.json").write_text(json.dumps(report))

    final = process_job(
        sample_audio, jobs_root=tmp_path / "jobs",
        runner=FakeRunner(package_source=rejected_pkg), job_id="jobtest",
    )

    assert final.state == "completed"
    assert final.quality == "rejected"


def test_runner_failure_lands_failed_with_stderr_tail(tmp_path: Path, sample_audio: Path):
    runner = FakeRunner(fail_with=PipelineRunError("pipeline exited with code 2", stderr_tail="demucs exploded"))

    final = process_job(sample_audio, jobs_root=tmp_path / "jobs", runner=runner, job_id="jobtest")

    assert final.state == "failed"
    assert "demucs exploded" in (final.error or "")
    assert read_status(tmp_path / "jobs" / "jobtest").state == "failed"


def test_patchify_failure_lands_failed(tmp_path: Path, sample_audio: Path):
    broken_pkg = tmp_path / "broken-pkg"
    shutil.copytree(GOLDEN, broken_pkg)
    lanes = json.loads((broken_pkg / "lanes.json").read_text())
    (broken_pkg / lanes["lanes"][0]["sample"]).unlink()  # 缺 sample → patchify loader 抛错

    final = process_job(
        sample_audio, jobs_root=tmp_path / "jobs",
        runner=FakeRunner(package_source=broken_pkg), job_id="jobtest",
    )

    assert final.state == "failed"
    assert "Missing sample file" in (final.error or "")


def test_missing_input_raises_before_creating_job(tmp_path: Path, fake_runner: FakeRunner):
    jobs_root = tmp_path / "jobs"
    with pytest.raises(FileNotFoundError):
        process_job(tmp_path / "ghost.wav", jobs_root=jobs_root, runner=fake_runner, job_id="jobtest")
    assert not (jobs_root / "jobtest").exists()


def test_default_job_id_is_generated(tmp_path: Path, sample_audio: Path, fake_runner: FakeRunner):
    final = process_job(sample_audio, jobs_root=tmp_path / "jobs", runner=fake_runner)
    assert len(final.job_id) == 12


def test_queued_status_written_before_input_copy(tmp_path: Path, sample_audio: Path):
    jobs_root = tmp_path / "jobs"
    job_dir = jobs_root / "jobtest"
    seen_state: list[str] = []
    # 首次 emit(queued) 时 input 尚未拷贝 —— 用 on_state 在 queued 时刻检查磁盘
    def probe(s):
        if s.state == "queued":
            seen_state.append("status.json" if (job_dir / "status.json").exists() else "none")
            seen_state.append("input-present" if (job_dir / "input" / sample_audio.name).exists() else "input-absent")
    process_job(sample_audio, jobs_root=jobs_root, runner=FakeRunner(), job_id="jobtest", on_state=probe)
    assert seen_state == ["status.json", "input-absent"]
