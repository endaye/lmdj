from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

# infra spec 全枚举：legacy v1 只发射
# queued/separating/patchifying/completed/failed。interrupted 是 API 在服务重启时
# 为无法恢复的旧非终态 Job 写入的明确终态。
STATES = frozenset({
    "queued", "generating", "separating", "extracting", "patchifying",
    "rendering", "completed", "failed", "cancelled", "interrupted",
})
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "interrupted"})
NONTERMINAL_STATES = STATES - TERMINAL_STATES

STATUS_FILENAME = "status.json"


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    state: str
    error: str | None = None
    error_code: str | None = None
    patch_id: str | None = None
    package_dir: str | None = None
    quality: str | None = None
    submission_id: str | None = None
    original_filename: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_status(job_dir: Path, status: JobStatus) -> JobStatus:
    """原子写（tmp + os.replace）：外部任意时刻读到的都是完整 JSON。"""
    if status.state not in STATES:
        raise ValueError(f"unknown job state: {status.state}")
    stamped = replace(status, updated_at=utc_now())
    job_dir.mkdir(parents=True, exist_ok=True)
    tmp = job_dir / (STATUS_FILENAME + ".tmp")
    tmp.write_text(json.dumps(stamped.to_dict(), ensure_ascii=False, indent=2))
    os.replace(tmp, job_dir / STATUS_FILENAME)
    return stamped


def read_status(job_dir: Path) -> JobStatus:
    data = json.loads((job_dir / STATUS_FILENAME).read_text())
    return JobStatus(**data)
