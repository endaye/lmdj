"""Read-only, versioned release qualification from exact-target CI evidence.

Release authority never infers that a target was fully tested from its path
type, its workflow conclusion, or the fact that it reached `main`. It reads
independent projections of the trusted control run and complete target verdict.
The old scope verifier remains explicit for immutable legacy history and its
pre-cutover regression matrix, never as a current prospective fallback.

The result is closed and read-only. `audit.py` maps it to an audit finding and
`prepare.py` maps every non-success to a refusal; neither is allowed to invent
a fourth outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
# Reuse the producer's pure, closed validator; never load executable target code.
from .self_test_protocol import protocol as self_test, validate_verdict_document, SelfTestEvidenceError
from .model import Disposition, ReleaseIntent, ReleasePolicy

from .github_api import (
    CI_SCOPE_LANES,
    CiScopeConflictError,
    CiScopeUnavailableError,
    RunJobProjection,
    RunProjection,
    SelfTestRunProjection,
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
    run: RunProjection | SelfTestRunProjection | None = None

    def __post_init__(self) -> None:
        if self.code not in _CODES:
            raise ValueError("CI evidence result code is not closed")
        if not self.message:
            raise ValueError("CI evidence result must describe its outcome")


def verify_release_ci(github: object, *, policy: ReleasePolicy, intent: ReleaseIntent) -> CiEvidenceResult:
    """Select explicitly between immutable legacy history and new candidate proof.

    Published self-test references survive artifact expiry. The protected intent
    records the exact digest/identity used to construct the immutable release
    plan; historical audit still verifies tag, release marker and assets.
    """
    prospective = intent.disposition is Disposition.RELEASABLE
    if policy.prospective_ci_protocol not in ("self-test-v1", "ci-scope-v2"):
        return _self_test_conflict("unknown prospective CI evidence protocol")
    reference = intent.self_test_evidence
    if reference is None:
        if prospective and policy.prospective_ci_protocol == "self-test-v1":
            return CiEvidenceResult("unverifiable", "why: new candidates require an explicit complete self-test reference; remedy: validate a complete self-test for the exact target and separately review its intent reference", CI_EVIDENCE_SOURCES)
        return verify_exact_main_ci(
            github, repository=policy.repository, branch=policy.branch,
            workflow=policy.blocking_workflow, target_revision=intent.target_revision,
            run_id=intent.merged_main_run_id, require_full_scope=prospective,
        )
    try:
        if prospective:
            # Reject a latest rerun, including a failed rerun of a once-green
            # batch. Current candidates cannot reuse an earlier attempt.
            run = github.get_self_test_run(policy.repository, intent.merged_main_run_id)
        else:
            # Publication froze this attempt in its plan digest. An unrelated
            # later rerun must not rewrite that historical observation.
            run = github.get_self_test_run(policy.repository, intent.merged_main_run_id,
                                           run_attempt=reference["run_attempt"])
        if (
            not isinstance(run, SelfTestRunProjection)
            or run.id != intent.merged_main_run_id or run.workflow_name != policy.blocking_workflow
            or run.head_branch != policy.branch or run.head_sha != reference["control_revision"]
            or run.run_attempt != reference["run_attempt"] or run.run_attempt != 1
            or run.event not in ("schedule", "workflow_dispatch")
            or (run.event == "schedule") != (reference["request_kind"] == "schedule")
            or run.status != "completed" or run.conclusion != "success"
        ):
            return _self_test_conflict("self-test run/control/attempt/event does not match the recorded successful batch")
        authority_revision = github.verify_self_test_provenance(policy.repository, run, intent.target_revision)
        if not prospective:
            return CiEvidenceResult("ok", "published self-test identity matches its durable reference; retention is not re-adjudicated", CI_EVIDENCE_SOURCES, run)
        # Both documents come from trusted main history. Requiring the current
        # applicable policy prevents an older/weaker suite list self-certifying.
        applicable = github.get_self_test_policy(policy.repository, authority_revision)
        producing = github.get_self_test_policy(policy.repository, run.head_sha)
        required = CI_SCOPE_LANES | {"core_tsan_stress", "core_release_stress"}
        if {suite.id for suite in applicable.suites} != required:
            return _self_test_conflict("current policy does not enumerate exactly the 16 required release suites", "repair the reviewed main policy before obtaining new evidence")
        if producing.revision != applicable.revision:
            return _self_test_conflict("control revision used a different policy from the current complete release protocol")
        if reference["policy_revision"] != applicable.revision:
            return _self_test_conflict("intent reference names a different policy from the current complete release protocol")
        expected = self_test.Identity(self_test.EVIDENCE_SCHEMA, reference["request_kind"],
                                     run.head_sha, intent.target_revision, run.id, run.run_attempt,
                                     applicable.revision)
        document = validate_verdict_document(
            github.get_self_test_verdict(policy.repository, run, intent.target_revision),
            policy=applicable, expected_identity=expected,
        )
        if document["status"] != "passed" or document["evidence_digest"] != reference["evidence_digest"]:
            return _self_test_conflict("self-test verdict is not passed or differs from the Owner's exact digest reference")
    except CiScopeUnavailableError:
        return CiEvidenceResult("unverifiable", "why: self-test artifact is absent or expired; remedy: create a new dispatch on main for the same target, not Re-run jobs, and separately review the intent reference", CI_EVIDENCE_SOURCES)
    except (CiScopeConflictError, SelfTestEvidenceError, self_test.SelfTestPolicyError) as error:
        # These exceptions contain closed local diagnostics, not HTTP bodies,
        # signed download URLs or raw transport exceptions. Keep the actual
        # failed invariant actionable instead of hiding it behind 'conflict'.
        detail = str(error).replace("\r", " ").replace("\n", " ")[:1500]
        return _self_test_conflict(detail)
    except Exception:
        return _outage("why: self-test evidence projection is unavailable; remedy: restore GitHub read access and retry the exact candidate verification; no release authority granted")
    return CiEvidenceResult("ok", "exact target has one retained, complete 16-suite self-test verdict", CI_EVIDENCE_SOURCES, run)


def _self_test_conflict(why: str, remedy: str = "create a new dispatch on main for the same target, not Re-run jobs; validate it and separately review the intent reference") -> CiEvidenceResult:
    if why.startswith("why:") and "; remedy:" in why:
        return _conflict(why)
    return _conflict(f"why: {why}; remedy: {remedy}")


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
    if run.workflow_name != workflow:
        return _conflict(
            "recorded merged-main CI run resolves to a different stable workflow; "
            "record an exact-main full run from the policy workflow"
        )
    if (
        run.event not in _ALLOWED_EVENTS or run.head_sha != target_revision
        or run.head_branch != branch or run.status != "completed"
        or run.conclusion != "success"
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
    gate_problem = _gate_problem(jobs, run)
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
    jobs: object, run: RunProjection,
) -> str | None:
    if not isinstance(jobs, list) or not all(
        isinstance(job, RunJobProjection) for job in jobs
    ):
        return "recorded merged-main CI job projection is invalid"
    for job in jobs:
        if job.run_id != run.id or job.head_sha != run.head_sha:
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
    "verify_release_ci",
]
