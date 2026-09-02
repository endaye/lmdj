"""Read-only verification of one Host deployment run as Channel promotion evidence.

A Host deployment workflow uploads `evidence.json` describing the exact tag,
target revision, Product Build, and the immutable and production HTTP and
browser checks it ran. Promotion to `dev` requires that evidence for every Host
in the profile's deployment set, so this module projects one recorded run and
fails closed on every identity mismatch. It never mutates anything.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from tools.release.model import HostDeploymentPolicy

DEPLOYMENT_EVIDENCE_SOURCES: tuple[str, ...] = ("github-actions-run", "github-actions-artifact")
EVIDENCE_MEMBER = "evidence.json"
_EVIDENCE_SIZE_CAP = 1024 * 1024
_CODES = frozenset(("ok", "missing", "conflict", "unverifiable", "external-error"))
_PASSED = "passed"


@dataclass(frozen=True)
class DeploymentEvidenceResult:
    code: str
    message: str
    sources: tuple[str, ...] = ()
    evidence_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.code not in _CODES:
            raise ValueError("deployment evidence result code is not closed")
        if not self.message:
            raise ValueError("deployment evidence result must describe its outcome")
        if (self.code == "ok") != (self.evidence_sha256 is not None):
            raise ValueError("deployment evidence digest accompanies exactly the ok result")


def verify_deployment_run(
    github: object,
    *,
    repository: str,
    branch: str,
    host: str,
    host_policy: HostDeploymentPolicy,
    tag: str,
    target_revision: str,
    identity: str,
    run_id: int,
) -> DeploymentEvidenceResult:
    """Verify one Host deployment run and its retained evidence against the exact release."""
    try:
        run = github.get_run(repository, run_id)
    except Exception as error:
        text = str(error)
        if "404" in text or "not found" in text.lower():
            return DeploymentEvidenceResult(
                "missing", f"{host} deployment run {run_id} is absent", DEPLOYMENT_EVIDENCE_SOURCES,
            )
        return DeploymentEvidenceResult(
            "external-error", f"{host} deployment run projection is unavailable",
            DEPLOYMENT_EVIDENCE_SOURCES,
        )
    if run.path != host_policy.workflow_path:
        return _conflict(host, f"run {run_id} belongs to a different workflow than the {host} deploy workflow")
    if run.event != "workflow_dispatch":
        return _conflict(host, f"run {run_id} was not a manual exact-tag workflow_dispatch")
    if run.head_branch != branch:
        return _conflict(host, f"run {run_id} was not dispatched from {branch}")
    if run.status != "completed" or run.conclusion != "success":
        return _conflict(host, f"run {run_id} did not complete successfully")

    try:
        payload = github.get_run_artifact_member(
            repository, run_id, host_policy.artifact, EVIDENCE_MEMBER, size_cap=_EVIDENCE_SIZE_CAP,
        )
    except Exception as error:
        text = str(error)
        if "absent" in text or "expired" in text:
            return DeploymentEvidenceResult(
                "unverifiable", f"{host} deployment run {run_id} retains no readable {EVIDENCE_MEMBER}",
                DEPLOYMENT_EVIDENCE_SOURCES,
            )
        if "ambiguous" in text or "conflicts" in text or "size cap" in text or "unreadable" in text or "exactly one" in text:
            return _conflict(host, f"run {run_id} deployment evidence artifact is invalid")
        return DeploymentEvidenceResult(
            "external-error", f"{host} deployment evidence artifact is unavailable",
            DEPLOYMENT_EVIDENCE_SOURCES,
        )
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _conflict(host, f"run {run_id} deployment evidence is not valid JSON")
    problem = _evidence_problem(
        document, host_policy=host_policy, tag=tag, target_revision=target_revision,
        identity=identity, run_id=run_id,
    )
    if problem is not None:
        return _conflict(host, f"run {run_id} deployment evidence {problem}")
    return DeploymentEvidenceResult(
        "ok", f"{host} deployment run {run_id} evidence matches the exact release",
        DEPLOYMENT_EVIDENCE_SOURCES, hashlib.sha256(payload).hexdigest(),
    )


def _evidence_problem(
    document: object,
    *,
    host_policy: HostDeploymentPolicy,
    tag: str,
    target_revision: str,
    identity: str,
    run_id: int,
) -> str | None:
    if not isinstance(document, dict):
        return "is not an object"
    contract = document.get("contract")
    if not isinstance(contract, str) or not contract.startswith(host_policy.contract_prefix):
        return "declares a foreign contract"
    if document.get("tag") != tag:
        return "names a different tag"
    if document.get("git_revision") != target_revision:
        return "names a different target revision"
    if document.get("product_build") != identity:
        return "names a different Product Build"
    actions = document.get("github_actions")
    if not isinstance(actions, dict) or str(actions.get("run_id")) != str(run_id):
        return "does not name its own run"
    for stage in ("immutable", "production"):
        section = document.get(stage)
        if not isinstance(section, dict):
            return f"has no {stage} verification"
        for check in ("http", "browser"):
            result = section.get(check)
            if not isinstance(result, dict) or result.get("status") != _PASSED:
                return f"{stage} {check} check did not pass"
    return None


def _conflict(host: str, message: str) -> DeploymentEvidenceResult:
    return DeploymentEvidenceResult("conflict", f"{host} {message}", DEPLOYMENT_EVIDENCE_SOURCES)
