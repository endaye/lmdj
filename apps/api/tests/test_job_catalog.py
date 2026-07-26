from __future__ import annotations

from pathlib import Path

import pytest
from lmdj_audio_worker.status import JobStatus, read_status, write_status

from lmdj_api.job_catalog import JobCatalog, validate_submission_id


def catalog_with_ids(jobs_root: Path, *job_ids: str) -> JobCatalog:
    values = iter(job_ids)
    return JobCatalog(jobs_root, id_factory=lambda: next(values))


def test_get_or_create_is_durable_and_idempotent(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    catalog = catalog_with_ids(jobs_root, "job-a", "job-unused")

    first, created = catalog.get_or_create("submission-123", "music/song.wav")
    second, duplicate = catalog.get_or_create(
        "submission-123",
        "ignored-name.wav",
    )

    assert created is True
    assert duplicate is False
    assert second == first
    assert first.job_id == "job-a"
    assert first.original_filename == "song.wav"
    assert first.submission_id == "submission-123"
    assert first.created_at
    assert read_status(jobs_root / "job-a") == first


def test_idempotent_submission_preserves_selected_pipeline(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    catalog = catalog_with_ids(jobs_root, "job-a", "job-unused")

    first, created = catalog.get_or_create(
        "submission-123",
        "song.wav",
        pipeline="materials-v1",
    )
    duplicate, created_again = catalog.get_or_create(
        "submission-123",
        "song.wav",
        pipeline="legacy",
    )

    assert created is True
    assert created_again is False
    assert duplicate == first
    assert duplicate.pipeline == "materials-v1"


def test_catalog_reloads_submission_mapping_from_status_files(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    created, _ = catalog_with_ids(jobs_root, "job-a").get_or_create(
        "submission-123",
        "song.wav",
    )

    reloaded = JobCatalog(jobs_root)

    assert reloaded.find_by_submission_id("submission-123") == created
    assert reloaded.find_by_submission_id("submission-missing") is None


@pytest.mark.parametrize("state", ["queued", "separating", "extracting", "patchifying"])
def test_restart_marks_nonterminal_jobs_interrupted(tmp_path: Path, state: str):
    jobs_root = tmp_path / "jobs"
    job_dir = jobs_root / f"job-{state}"
    original = write_status(
        job_dir,
        JobStatus(
            job_id=f"job-{state}",
            state=state,
            submission_id=f"submission-{state}",
            original_filename=f"{state}.wav",
            pipeline="materials-v1",
            created_at="2026-07-26T00:00:00Z",
        ),
    )

    recovered = JobCatalog(jobs_root).interrupt_nonterminal()

    assert len(recovered) == 1
    interrupted = read_status(job_dir)
    assert interrupted.state == "interrupted"
    assert interrupted.error_code == "service_interrupted"
    assert "restarted" in (interrupted.error or "")
    assert interrupted.submission_id == original.submission_id
    assert interrupted.pipeline == "materials-v1"
    assert interrupted.created_at == original.created_at


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled", "interrupted"])
def test_restart_does_not_rewrite_terminal_jobs(tmp_path: Path, state: str):
    jobs_root = tmp_path / "jobs"
    job_dir = jobs_root / f"job-{state}"
    original = write_status(
        job_dir,
        JobStatus(job_id=f"job-{state}", state=state),
    )

    assert JobCatalog(jobs_root).interrupt_nonterminal() == []
    assert read_status(job_dir) == original


def test_catalog_skips_unreadable_unrelated_directories(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    (jobs_root / "not-a-job").mkdir(parents=True)
    (jobs_root / "broken-job").mkdir()
    (jobs_root / "broken-job" / "status.json").write_text("{")
    catalog = catalog_with_ids(jobs_root, "job-a")

    status, created = catalog.get_or_create("submission-123", r"C:\fakepath\song.wav")

    assert created is True
    assert status.original_filename == "song.wav"


@pytest.mark.parametrize(
    "value",
    ["short", "space is invalid", "/path-like-id", "x" * 129],
)
def test_submission_id_validation_rejects_unsafe_values(value: str):
    with pytest.raises(ValueError, match="submission ID"):
        validate_submission_id(value)


def test_submission_id_validation_accepts_browser_uuid():
    value = "018f6f75-4a30-7dd5-bf8e-435876a2c000"
    assert validate_submission_id(value) == value
