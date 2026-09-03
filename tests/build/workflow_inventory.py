#!/usr/bin/env python3
"""Enumerate the jobs declared by the repository's workflows.

A line scan rather than a YAML load: no test or script in this repository
depends on PyYAML, and the CI contract lane's interpreter is not guaranteed to
provide it. The scan reads only what the routing contracts need — the job's id,
its display name, and its `runs-on` — so it stays small enough to be obviously
correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github/workflows"

_JOBS_KEY = re.compile(r"^jobs:\s*$")
_JOB_START = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
_JOB_NAME = re.compile(r"^    name: (.+?)\s*$")
_RUNS_ON = re.compile(r"^    runs-on: (.+?)\s*$")
_TOP_LEVEL = re.compile(r"^[A-Za-z]")


@dataclass(frozen=True)
class WorkflowJob:
    """One job, addressed the way the routing contracts address it."""

    workflow: str
    job_id: str
    name: str | None
    runs_on: str | None

    @property
    def display_name(self) -> str:
        """The name GitHub shows, which is what the elastic controller matches."""
        return self.name or self.job_id

    @property
    def is_reusable_call(self) -> bool:
        """A `uses:` job carries no `runs-on`; the called workflow declares it."""
        return self.runs_on is None

    @property
    def is_dynamic(self) -> bool:
        """`runs-on` resolved from an expression, so the host is not decidable here."""
        return self.runs_on is not None and "${{" in self.runs_on

    @property
    def is_self_hosted(self) -> bool:
        return self.runs_on is not None and "self-hosted" in self.runs_on

    @property
    def needs_host_justification(self) -> bool:
        """True when this job can consume GitHub-hosted minutes.

        A dynamic `runs-on` counts: it may resolve to a hosted label, and the
        point of the allowlist is that every such site is a recorded decision.
        """
        if self.is_reusable_call or self.is_self_hosted:
            return False
        return True

    def has_role(self, role: str) -> bool:
        return self.runs_on is not None and re.search(rf"\b{re.escape(role)}\b", self.runs_on) is not None


def jobs_in(workflow: Path) -> list[WorkflowJob]:
    """Every job declared by one workflow file, in declaration order."""
    found: list[WorkflowJob] = []
    in_jobs = False
    job_id: str | None = None
    name: str | None = None
    runs_on: str | None = None

    def flush() -> None:
        if job_id is not None:
            found.append(WorkflowJob(workflow.name, job_id, name, runs_on))

    for line in workflow.read_text(encoding="utf-8").splitlines():
        if _JOBS_KEY.match(line):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if _TOP_LEVEL.match(line):
            break  # a new top-level key ends the jobs mapping
        start = _JOB_START.match(line)
        if start:
            flush()
            job_id, name, runs_on = start.group(1), None, None
            continue
        if job_id is None:
            continue
        name_match = _JOB_NAME.match(line)
        if name_match:
            name = name_match.group(1)
            continue
        runs_on_match = _RUNS_ON.match(line)
        if runs_on_match:
            runs_on = runs_on_match.group(1)
    flush()
    return found


def all_jobs() -> list[WorkflowJob]:
    """Every job in every workflow, ordered by workflow file name."""
    return [job for path in sorted(WORKFLOW_DIR.glob("*.yml")) for job in jobs_in(path)]


if __name__ == "__main__":
    for job in all_jobs():
        if job.needs_host_justification:
            print(f"{job.workflow}\t{job.job_id}\t{job.runs_on}")
