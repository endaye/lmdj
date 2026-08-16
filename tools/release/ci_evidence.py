"""One read-only verifier for full exact-main CI evidence.

Release authority never infers that a target was fully tested from its path
type, its workflow conclusion, or the fact that it reached `main`. It reads
three independent projections of one exact Actions run and requires all of
them: the run identity, its same-run adjudication jobs, and the scope manifest
that run retained for that exact head SHA.

The result is closed and read-only. `audit.py` maps it to an audit finding and
`prepare.py` maps every non-success to a refusal; neither is allowed to invent
a fourth outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from .github_api import (
    CI_SCOPE_LANES,
    CiScopeConflictError,
    CiScopeUnavailableError,
    RunJobProjection,
    RunProjection,
)


CHANGE_SCOPE_JOB = "Change Scope"
PR_GATE_JOB = "PR Gate"
CI_EVIDENCE_SOURCES = ("github-actions",)
SCOPE_EVIDENCE_SOURCES = ("github-actions", "github-ci-scope")
FULL_MODE = "full"
SCOPE_SCHEMA = "lmdj.ci-scope.v2"
_ALLOWED_EVENTS = frozenset(("push", "workflow_dispatch"))
_CODES = frozenset(("ok", "missing", "conflict", "unverifiable", "external-error"))


@dataclass(frozen=True)
class CiEvidenceResult:
    code: str
    message: str
    sources: tuple[str, ...] = ()
    run: RunProjection | None = None

    def __post_init__(self) -> None:
        if self.code not in _CODES:
            raise ValueError("CI evidence result code is not closed")
        if not self.message:
            raise ValueError("CI evidence result must describe its outcome")


def verify_exact_main_ci(
    github: object,
    *,
    repository: str,
    branch: str,
    workflow: str,
    target_revision: str,
    run_id: int | None,
    require_full_scope: bool,
) -> CiEvidenceResult:
    """Verify one recorded run against the exact release target, without mutation.

    ``require_full_scope`` selects the prospective contract. A releasable intent
    must still hold retained `full` scope evidence and a successful same-run
    Gate, because that evidence is what authorizes the next mutation. A terminal
    published intent is audited from immutable tag, Release and asset evidence
    instead: its scope artifact has a bounded retention, and an expired
    ephemeral artifact must not be able to rewrite history.
    """
    if run_id is None:
        return CiEvidenceResult(
            "unverifiable", "intent has no exact merged-main CI run", CI_EVIDENCE_SOURCES,
        )
    try:
        runs = github.list_runs_for_sha(repository, target_revision)
    except Exception:
        return _outage("GitHub Actions run projection is unavailable")
    matching = [run for run in runs if run.id == run_id]
    if len(matching) != 1:
        return CiEvidenceResult(
            "missing", "recorded merged-main CI run is absent", CI_EVIDENCE_SOURCES,
        )
    run = matching[0]
    if (
        run.event not in _ALLOWED_EVENTS or run.head_sha != target_revision
        or run.head_branch != branch or run.workflow_name != workflow
        or run.status != "completed" or run.conclusion != "success"
    ):
        return _conflict("recorded merged-main CI run does not satisfy policy")
    if not require_full_scope:
        return CiEvidenceResult(
            "ok", "recorded merged-main CI run satisfies policy",
            CI_EVIDENCE_SOURCES, run,
        )

    try:
        jobs = github.list_run_jobs(repository, run.id)
    except Exception:
        return _outage("GitHub Actions job projection is unavailable")
    gate_problem = _gate_problem(jobs, run, workflow)
    if gate_problem is not None:
        return _conflict(gate_problem)

    try:
        scope = github.get_ci_scope_manifest(repository, run)
    except CiScopeUnavailableError:
        return CiEvidenceResult(
            "unverifiable",
            "recorded merged-main CI run retains no readable scope manifest",
            SCOPE_EVIDENCE_SOURCES,
        )
    except CiScopeConflictError:
        return CiEvidenceResult(
            "conflict",
            "retained merged-main CI scope manifest conflicts with the release target",
            SCOPE_EVIDENCE_SOURCES,
        )
    except Exception:
        return _outage("GitHub Actions scope artifact projection is unavailable")
    scope_problem = _scope_problem(scope, target_revision)
    if scope_problem is not None:
        return CiEvidenceResult("conflict", scope_problem, SCOPE_EVIDENCE_SOURCES)
    return CiEvidenceResult(
        "ok",
        "recorded merged-main CI run is full for the exact target with a successful Gate",
        SCOPE_EVIDENCE_SOURCES,
        run,
    )


def _gate_problem(
    jobs: object, run: RunProjection, workflow: str,
) -> str | None:
    if not isinstance(jobs, list) or not all(
        isinstance(job, RunJobProjection) for job in jobs
    ):
        return "recorded merged-main CI job projection is invalid"
    for job in jobs:
        if (
            job.run_id != run.id or job.workflow_name != workflow
            or job.head_sha != run.head_sha
        ):
            return "recorded merged-main CI job identity conflicts with its run"
    for name in (CHANGE_SCOPE_JOB, PR_GATE_JOB):
        selected = [job for job in jobs if job.name == name]
        if len(selected) != 1:
            return f"recorded merged-main CI run does not have exactly one {name} job"
        if selected[0].status != "completed" or selected[0].conclusion != "success":
            return f"recorded merged-main CI run {name} job did not succeed"
    return None


def _scope_problem(scope: object, target_revision: str) -> str | None:
    schema = getattr(scope, "schema", None)
    head_sha = getattr(scope, "head_sha", None)
    mode = getattr(scope, "mode", None)
    trusted_head = getattr(scope, "trusted_head", None)
    if schema != SCOPE_SCHEMA:
        return "retained merged-main CI scope manifest schema is not v2"
    if head_sha != target_revision:
        return "retained merged-main CI scope manifest is for another head SHA"
    if mode != FULL_MODE:
        return f"retained merged-main CI scope manifest is {mode}, not full"
    if trusted_head is not True:
        return "retained merged-main CI scope manifest does not record a trusted head"
    # Re-checked on the typed projection as well as at the archive boundary: a
    # manifest that calls itself full while selecting fewer lanes is a claim,
    # not evidence, whichever projection layer produced it.
    if set(getattr(scope, "selected_lanes", ())) != CI_SCOPE_LANES:
        return "retained full merged-main CI scope manifest does not select every lane"
    return None


def _conflict(message: str) -> CiEvidenceResult:
    return CiEvidenceResult("conflict", message, CI_EVIDENCE_SOURCES)


def _outage(message: str) -> CiEvidenceResult:
    # Transport, pagination and download failures are outages, never evidence.
    return CiEvidenceResult("external-error", message, CI_EVIDENCE_SOURCES)


__all__ = [
    "CHANGE_SCOPE_JOB",
    "CI_EVIDENCE_SOURCES",
    "CiEvidenceResult",
    "FULL_MODE",
    "PR_GATE_JOB",
    "SCOPE_EVIDENCE_SOURCES",
    "SCOPE_SCHEMA",
    "verify_exact_main_ci",
]
