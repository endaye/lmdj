from __future__ import annotations

import re
import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

from lmdj_audio_worker.status import (
    NONTERMINAL_STATES,
    STATUS_FILENAME,
    JobStatus,
    read_status,
    utc_now,
    write_status,
)

_SUBMISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


def validate_submission_id(value: str) -> str:
    if not _SUBMISSION_ID.fullmatch(value):
        raise ValueError("invalid submission ID")
    return value


def _display_filename(value: str) -> str:
    # Browsers commonly send C:\fakepath\name.ext even to non-Windows servers.
    name = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return name or "untitled-audio"


class JobCatalog:
    """File-backed Job identity and restart recovery.

    ``status.json`` remains the durable record. The lock only makes
    lookup-and-create atomic inside this single API process; it is not a
    distributed queue claim.
    """

    def __init__(
        self,
        jobs_root: Path,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.jobs_root = jobs_root
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex[:12])
        self._lock = threading.Lock()

    def get_or_create(
        self,
        submission_id: str,
        original_filename: str,
        *,
        pipeline: str | None = None,
    ) -> tuple[JobStatus, bool]:
        submission_id = validate_submission_id(submission_id)
        with self._lock:
            existing = self._find_by_submission_id(submission_id)
            if existing is not None:
                return existing, False

            self.jobs_root.mkdir(parents=True, exist_ok=True)
            while True:
                job_id = self._id_factory()
                job_dir = self.jobs_root / job_id
                if not job_dir.exists():
                    break
            status = write_status(
                job_dir,
                JobStatus(
                    job_id=job_id,
                    state="queued",
                    submission_id=submission_id,
                    original_filename=_display_filename(original_filename),
                    pipeline=pipeline,
                    created_at=utc_now(),
                ),
            )
            return status, True

    def find_by_submission_id(self, submission_id: str) -> JobStatus | None:
        submission_id = validate_submission_id(submission_id)
        with self._lock:
            return self._find_by_submission_id(submission_id)

    def interrupt_nonterminal(self) -> list[JobStatus]:
        interrupted: list[JobStatus] = []
        with self._lock:
            for status in self._statuses():
                if status.state not in NONTERMINAL_STATES:
                    continue
                interrupted.append(
                    write_status(
                        self.jobs_root / status.job_id,
                        replace(
                            status,
                            state="interrupted",
                            error_code="service_interrupted",
                            error=(
                                "API service restarted before this Job completed. "
                                "Submit the source again to retry."
                            ),
                        ),
                    ),
                )
        return interrupted

    def _find_by_submission_id(self, submission_id: str) -> JobStatus | None:
        for status in self._statuses():
            if status.submission_id == submission_id:
                return status
        return None

    def _statuses(self) -> Iterator[JobStatus]:
        if not self.jobs_root.is_dir():
            return
        for child in sorted(self.jobs_root.iterdir()):
            if not child.is_dir() or not (child / STATUS_FILENAME).is_file():
                continue
            try:
                status = read_status(child)
            except (OSError, ValueError, TypeError):
                continue
            if status.job_id != child.name:
                continue
            yield status
