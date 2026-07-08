import json
import re
from pathlib import Path

import pytest

from lmdj_audio_worker.status import STATES, JobStatus, read_status, write_status

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_write_and_read_roundtrip(tmp_path: Path):
    status = JobStatus(job_id="job1", state="queued", created_at="2026-07-08T00:00:00Z")
    written = write_status(tmp_path, status)

    assert ISO_Z.match(written.updated_at)
    loaded = read_status(tmp_path)
    assert loaded == written
    assert loaded.created_at == "2026-07-08T00:00:00Z"


def test_write_rejects_unknown_state(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown job state"):
        write_status(tmp_path, JobStatus(job_id="job1", state="doing_stuff"))


def test_states_is_full_infra_enum():
    assert STATES == {
        "queued", "generating", "separating", "extracting", "patchifying",
        "rendering", "completed", "failed", "cancelled",
    }


def test_write_is_atomic_no_tmp_leftover_and_valid_json(tmp_path: Path):
    for _ in range(5):
        write_status(tmp_path, JobStatus(job_id="job1", state="separating"))
        data = json.loads((tmp_path / "status.json").read_text())
        assert data["state"] == "separating"
    assert list(tmp_path.glob("*.tmp")) == []
