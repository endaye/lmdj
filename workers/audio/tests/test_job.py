import json
import shutil
from hashlib import sha256
from pathlib import Path

import pytest

from lmdj_audio_worker.job import process_job
from lmdj_audio_worker.music_metadata import KeyEstimate
from lmdj_audio_worker.runner import PipelineRunError
from lmdj_audio_worker.status import JobStatus, read_status

from tests.conftest import GOLDEN, FakeRunner

MATERIAL_GOLDEN = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "patchify"
    / "tests"
    / "fixtures"
    / "material-package"
)


class StageAwareFakeRunner:
    pipeline_id = "materials-v1"

    def run_with_stages(self, audio, out_dir, song_id, on_stage):
        on_stage("extracting")
        destination = out_dir / song_id
        shutil.copytree(MATERIAL_GOLDEN, destination)
        return destination

    def run(self, audio, out_dir, song_id):
        raise AssertionError("stage-aware runner must use run_with_stages")


class FakeKeyAnalyzer:
    def __init__(
        self,
        estimate: KeyEstimate | None = None,
        error: Exception | None = None,
    ) -> None:
        self.estimate = estimate or KeyEstimate("C major", 0.8)
        self.error = error
        self.calls: list[Path] = []

    def analyze(self, audio: Path) -> KeyEstimate:
        self.calls.append(audio)
        if self.error:
            raise self.error
        return self.estimate


class ReportSongIdRunner(FakeRunner):
    """模拟 demo：report.json 记录 PipelineRunner 收到的 song_id。"""

    def run(self, audio: Path, out_dir: Path, song_id: str) -> Path:
        package_dir = super().run(audio, out_dir, song_id)
        report_path = package_dir / "report.json"
        report = json.loads(report_path.read_text())
        report["song_id"] = song_id
        report_path.write_text(json.dumps(report))
        return package_dir


def test_happy_path_completes_with_patch(tmp_path: Path, sample_audio: Path, fake_runner: FakeRunner):
    jobs_root = tmp_path / "jobs"

    final = process_job(sample_audio, jobs_root=jobs_root, runner=fake_runner, job_id="jobtest")

    assert final.state == "completed"
    assert final.quality == "passed"
    assert final.package_dir == f"source-{sha256(sample_audio.read_bytes()).hexdigest()}"
    assert final.patch_id and final.patch_id.startswith("testsong-")  # fixture 的 report.song_id
    job_dir = jobs_root / "jobtest"
    assert (job_dir / "input" / sample_audio.name).exists()
    assert (job_dir / (final.package_dir or "") / "patch.json").exists()
    assert read_status(job_dir).state == "completed"


def test_initial_status_metadata_survives_to_completed(
    tmp_path: Path,
    sample_audio: Path,
):
    initial = JobStatus(
        job_id="jobtest",
        state="queued",
        submission_id="submission-1",
        original_filename="song.wav",
        created_at="2026-07-26T00:00:00Z",
    )

    final = process_job(
        sample_audio,
        jobs_root=tmp_path / "jobs",
        runner=FakeRunner(),
        job_id="jobtest",
        initial_status=initial,
    )

    assert final.submission_id == "submission-1"
    assert final.original_filename == "song.wav"
    assert final.created_at == "2026-07-26T00:00:00Z"


@pytest.mark.parametrize(
    "initial",
    [
        JobStatus(job_id="other", state="queued"),
        JobStatus(job_id="jobtest", state="separating"),
    ],
)
def test_initial_status_must_be_queued_for_selected_job(
    tmp_path: Path,
    sample_audio: Path,
    initial: JobStatus,
):
    with pytest.raises(ValueError, match="initial status"):
        process_job(
            sample_audio,
            jobs_root=tmp_path / "jobs",
            runner=FakeRunner(),
            job_id="jobtest",
            initial_status=initial,
        )


def test_same_audio_across_jobs_uses_stable_source_identity_for_full_patch_id(
    tmp_path: Path,
    sample_audio: Path,
) -> None:
    runner = ReportSongIdRunner()
    jobs_root = tmp_path / "jobs"

    first = process_job(sample_audio, jobs_root=jobs_root, runner=runner, job_id="job-one")
    second = process_job(sample_audio, jobs_root=jobs_root, runner=runner, job_id="job-two")
    different_audio = tmp_path / "different.wav"
    different_audio.write_bytes(b"RIFF....WAVEfmt different-audio")
    third = process_job(different_audio, jobs_root=jobs_root, runner=runner, job_id="job-three")

    expected_source_id = f"source-{sha256(sample_audio.read_bytes()).hexdigest()}"
    received_source_ids = [call[2] for call in runner.calls]
    assert received_source_ids[:2] == [expected_source_id, expected_source_id]
    assert received_source_ids[2] != expected_source_id
    assert first.patch_id == second.patch_id
    assert third.patch_id != first.patch_id


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


def test_export_source_is_written_before_completed(
    tmp_path: Path,
    sample_audio: Path,
) -> None:
    jobs_root = tmp_path / "jobs"
    job_dir = jobs_root / "jobtest"
    key_analyzer = FakeKeyAnalyzer(KeyEstimate("A minor", 0.72))
    inventory_seen: list[bool] = []

    final = process_job(
        sample_audio,
        jobs_root=jobs_root,
        runner=FakeRunner(),
        job_id="jobtest",
        key_analyzer=key_analyzer,
        on_state=lambda status: (
            inventory_seen.append(
                (job_dir / (status.package_dir or "") / "export-source.json").exists(),
            )
            if status.state == "completed"
            else None
        ),
    )

    source = json.loads((job_dir / (final.package_dir or "") / "export-source.json").read_text())
    assert final.state == "completed"
    assert inventory_seen == [True]
    assert key_analyzer.calls == [job_dir / "input" / sample_audio.name]
    assert source["music"]["key"] == {"value": "A minor", "confidence": 0.72}


def test_key_analysis_failure_keeps_playable_job_completed_with_partial_inventory(
    tmp_path: Path,
    sample_audio: Path,
) -> None:
    jobs_root = tmp_path / "jobs"

    final = process_job(
        sample_audio,
        jobs_root=jobs_root,
        runner=FakeRunner(),
        job_id="jobtest",
        key_analyzer=FakeKeyAnalyzer(error=RuntimeError("metadata unavailable")),
    )

    source = json.loads(
        (jobs_root / "jobtest" / (final.package_dir or "") / "export-source.json").read_text(),
    )
    assert final.state == "completed"
    assert source["music"]["key"] is None
    assert "metadata unavailable" in source["warnings"][0]


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


def test_stage_aware_runner_emits_extracting_and_records_pipeline(
    tmp_path: Path,
    sample_audio: Path,
):
    states = []
    final = process_job(
        sample_audio,
        jobs_root=tmp_path / "jobs",
        runner=StageAwareFakeRunner(),
        job_id="materialsjob",
        on_state=lambda status: states.append(status.state),
    )
    assert states == [
        "queued",
        "separating",
        "extracting",
        "patchifying",
        "completed",
    ]
    assert final.pipeline == "materials-v1"
    assert final.patch_id is not None
