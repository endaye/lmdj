"""Read-only release identity and drift audit."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Callable, Iterable, Iterator

from .commands import sanitize_diagnostic
from .github_api import GitHubAsset, GitHubEnvironment, GitHubRelease
from .model import (
    Disposition,
    HistoricalException,
    ReleaseIntent,
    ReleaseLedger,
    ReleaseModelError,
    ReleasePolicy,
    canonical_json,
    classify_tag,
)
from .openpgp import OpenPgpError, OpenPgpVerifier
from .prepare import LocalTag, ProductProof
from .profiles import AssetBuild, ProfileBuild
from scripts.version import _provider_source_package_sha256


_REPORT_SCHEMA = "lmdj.release-audit.v1"
_SUCCESS_CODES = frozenset(("ok", "ok-with-historical-exception"))
_CODES = frozenset((*_SUCCESS_CODES, "missing", "conflict", "unauthorized", "unverifiable", "external-error"))
_MARKER = re.compile(r"<!-- lmdj\.release-plan-marker\.v1 (\{[^\r\n]*\}) -->")
_STATIC_PROJECTION_MESSAGE = (
    "active Product, Assembly lock or immutable snapshot projection is inconsistent"
)
_STATIC_PROJECTION_FAILURES = (
    OSError, KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError, OpenPgpError,
)
_REASON_LIMIT = 480


@dataclass(frozen=True)
class AuditFinding:
    code: str
    subject: str
    message: str
    sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.code not in _CODES:
            raise ValueError("audit finding code is not closed")
        if not self.subject or not self.message:
            raise ValueError("audit finding must identify its subject and result")

    def to_document(self) -> dict[str, object]:
        return {
            "code": self.code,
            "subject": self.subject,
            "message": self.message,
            "sources": list(self.sources),
        }


@dataclass(frozen=True)
class AuditReport:
    observed_utc: str
    repository: str
    mode: str
    findings: tuple[AuditFinding, ...]
    incomplete_sources: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        return 0 if self.findings and all(item.code in _SUCCESS_CODES for item in self.findings) else 1

    def to_document(self) -> dict[str, object]:
        return {
            "schema": _REPORT_SCHEMA,
            "observed_utc": self.observed_utc,
            "repository": self.repository,
            "mode": self.mode,
            "findings": [item.to_document() for item in self.findings],
            "incomplete_sources": list(self.incomplete_sources),
        }


ProfileVerifier = Callable[[str, Path, Path, ReleaseIntent, tuple[AssetBuild, ...]], None]
ProofReader = Callable[[Path, ReleaseIntent], ProductProof]
TrustAnchorVerifier = Callable[[Path, ReleasePolicy], None]
AuthorityContextBuilder = Callable[[Path, ReleasePolicy, ReleaseLedger], "AuditContext"]


@dataclass(frozen=True)
class AuditContext:
    repo_root: Path
    policy: ReleasePolicy
    ledger: ReleaseLedger
    git: object
    github: object
    profile_verifier: ProfileVerifier
    proof_reader: ProofReader
    tag_signer_fingerprint: str
    checksum_signer_fingerprint: str
    trust_anchor_verifier: TrustAnchorVerifier = lambda root, policy: None
    authority_reader: Callable[[Path], tuple[ReleasePolicy, ReleaseLedger]] | None = None
    authority_context_builder: AuthorityContextBuilder | None = None


@dataclass(frozen=True)
class _ObservedTag:
    object_id: str
    target_revision: str
    signer_fingerprint: str | None


def audit(
    context: AuditContext | object,
    *,
    remote: bool,
    tag: str | None = None,
    observed_at: datetime | None = None,
) -> AuditReport:
    """Audit repository authority and optionally fresh remote state without mutation."""
    observed = _observed_utc(observed_at)
    mode = "remote" if remote else "local"
    policy = context.policy
    ledger = context.ledger
    if tag is not None and (not isinstance(tag, str) or not tag):
        return _report(observed, policy.repository, mode, (
            AuditFinding("unauthorized", "selection", "exact audit tag is invalid"),
        ))

    if not remote:
        selected_entries = [entry for entry in ledger.entries if tag is None or entry.tag == tag]
        selected_exceptions = [item for item in ledger.historical_exceptions if tag is None or item.tag == tag]
        if tag is not None and not selected_entries and not selected_exceptions:
            return _report(observed, policy.repository, mode, (
                AuditFinding("unauthorized", tag, "tag is not authorized by policy or the intent ledger"),
            ))
        findings = _audit_local(context, selected_entries, selected_exceptions)
        return _report(observed, policy.repository, mode, findings)

    try:
        with _load_remote_projection(context) as (resolved, remote_tags, releases, latest_release_id):
            return _remote_report(
                observed, resolved, remote_tags, releases, latest_release_id, tag,
            )
    except OpenPgpError:
        return _report(
            observed, policy.repository, mode,
            (AuditFinding(
                "unverifiable", policy.repository,
                "canonical signing trust or signature projection is inconsistent",
                ("canonical-trust",),
            ),),
        )
    except Exception:
        return _report(
            observed, policy.repository, mode,
            (AuditFinding(
                "external-error", policy.repository,
                "canonical Git/GitHub projection is unavailable or incomplete",
                ("git-remote", "github-api"),
            ),),
            ("git-remote", "github-api"),
        )


def _remote_report(
    observed: str,
    context: object,
    remote_tags: dict[str, _ObservedTag],
    releases: dict[str, GitHubRelease],
    latest_release_id: int | None,
    tag: str | None,
) -> AuditReport:
    policy, ledger = context.policy, context.ledger
    selected_entries = [entry for entry in ledger.entries if tag is None or entry.tag == tag]
    selected_exceptions = [item for item in ledger.historical_exceptions if tag is None or item.tag == tag]
    if tag is not None and not selected_entries and not selected_exceptions:
        return _report(observed, policy.repository, "remote", (
            AuditFinding("unauthorized", tag, "tag is not authorized by canonical policy or the intent ledger"),
        ))

    findings: list[AuditFinding] = []
    environment_issue = _release_environment_finding(context)
    if environment_issue is not None:
        findings.append(environment_issue)
    static_issue = _local_repository_issue(context, list(ledger.entries))
    if static_issue is not None:
        findings.append(static_issue)
    linked_exceptions = {item.tag: item for item in selected_exceptions if ledger.intent_for_tag(item.tag) is not None}
    for entry in selected_entries:
        findings.append(_audit_remote_intent(
            context, entry, remote_tags.get(entry.tag), releases.get(entry.tag),
            linked_exceptions.get(entry.tag), latest_release_id,
        ))
    for exception in selected_exceptions:
        if ledger.intent_for_tag(exception.tag) is None:
            findings.append(_audit_remote_exception(
                context, exception, remote_tags.get(exception.tag), releases.get(exception.tag),
            ))
    if tag is None:
        known = {entry.tag for entry in ledger.entries} | {item.tag for item in ledger.historical_exceptions}
        for unknown in sorted((set(remote_tags) | set(releases)) - known):
            try:
                classify_tag(unknown, policy)
            except ReleaseModelError:
                if unknown not in releases:
                    continue
                description = "GitHub Release has no exact historical exception"
            else:
                description = "formal remote state has no authorized intent"
            findings.append(AuditFinding("unauthorized", unknown, description, ("remote",)))
    return _report(observed, policy.repository, "remote", findings)


def write_report(report: AuditReport, destination: Path | str) -> None:
    """Atomically write canonical report JSON without following a destination symlink."""
    path = Path(destination).expanduser()
    if path.is_symlink():
        raise OSError("release audit JSON destination must not be a symlink")
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise OSError("release audit JSON parent is unsafe")
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json(report.to_document()))
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise OSError("release audit JSON destination changed to a symlink")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def format_report(report: AuditReport) -> str:
    lines = [
        f"release audit: {report.mode} ({report.observed_utc})",
        f"repository: {report.repository}",
    ]
    for item in report.findings:
        lines.append(f"[{item.code}] {item.subject}: {item.message}")
    if report.incomplete_sources:
        lines.append("incomplete sources: " + ", ".join(report.incomplete_sources))
    return "\n".join(lines)


def _audit_local(
    context: object,
    entries: list[ReleaseIntent],
    exceptions: list[HistoricalException],
) -> list[AuditFinding]:
    repository_issue = _local_repository_issue(context, list(context.ledger.entries))
    findings: list[AuditFinding] = []
    if repository_issue is not None:
        findings.append(repository_issue)
    for entry in entries:
        evidence_issue = _evidence_issue(context.repo_root, entry.evidence_paths)
        if evidence_issue is not None:
            findings.append(AuditFinding("unverifiable", entry.tag, evidence_issue, entry.evidence_paths))
        else:
            findings.append(AuditFinding(
                "ok", entry.tag,
                f"local policy, intent and evidence are valid ({entry.disposition.value})",
                entry.evidence_paths,
            ))
    for exception in exceptions:
        evidence_issue = _evidence_issue(context.repo_root, exception.evidence_paths)
        if evidence_issue is not None:
            findings.append(AuditFinding("unverifiable", exception.tag, evidence_issue, exception.evidence_paths))
        else:
            findings.append(_exception_finding(exception, "local exception record is valid"))
    for entry in entries:
        try:
            local_tag = context.git.local_tag_state(entry.tag)
        except Exception:
            local_tag = None
        if local_tag is not None:
            matches = (
                local_tag.target_revision == entry.target_revision
                and local_tag.signer_fingerprint == context.policy.product_fingerprint
            )
            detail = "matches" if matches else "conflicts with"
            findings.append(AuditFinding(
                "ok" if matches else "conflict", f"local:{entry.tag}",
                f"local same-name tag {detail} intent; diagnostic only and not authoritative",
                ("local-tag",),
            ))
    if not findings:
        findings.append(AuditFinding("ok", context.policy.repository, "local authority has no selected release identities"))
    return findings


class _StaticProjectionError(Exception):
    """One named static repository projection failed with a sanitized reason."""

    def __init__(self, projection: str, sources: tuple[str, ...], reason: str) -> None:
        super().__init__(f"{projection}: {reason}")
        self.projection = projection
        self.sources = sources
        self.reason = reason


@contextmanager
def _static_projection(root: Path, projection: str, *sources: str) -> Iterator[None]:
    """Attribute one static repository failure to the exact projection that raised it."""
    try:
        yield
    except _STATIC_PROJECTION_FAILURES as exception:
        raise _StaticProjectionError(projection, sources, _sanitized_reason(root, exception)) from None


def _sanitized_reason(root: Path, exception: BaseException) -> str:
    """Describe a failure without echoing environment values, secrets or absolute paths."""
    text = sanitize_diagnostic(exception, root=root, limit=_REASON_LIMIT)
    return f"{type(exception).__name__}: {text}" if text else type(exception).__name__


def _local_repository_issue(context: object, entries: list[ReleaseIntent]) -> AuditFinding | None:
    policy = context.policy
    if (
        context.tag_signer_fingerprint != policy.product_fingerprint
        or context.checksum_signer_fingerprint != policy.checksum_fingerprint
        or context.tag_signer_fingerprint == context.checksum_signer_fingerprint
    ):
        return AuditFinding("conflict", policy.repository, "configured signing roles conflict with policy trust anchors")
    root = Path(context.repo_root)
    version_path = root / "products/lmdj/version.json"
    if not version_path.is_file() or version_path.is_symlink():
        return AuditFinding(
            "unverifiable", policy.repository,
            "active Product identity manifest is unavailable",
            ("active-manifests",),
        )
    try:
        with _static_projection(root, "signing trust anchors", "canonical-trust"):
            context.trust_anchor_verifier(root, policy)
        assembly_path = root / "products/lmdj/assembly.json"
        lock_path = root / "products/lmdj/assembly.lock.json"
        with _static_projection(root, "active Product identity manifests", "active-manifests"):
            version = _json_file(version_path)
            assembly = _json_file(assembly_path)
            lock = _json_file(lock_path)
            identity = ".".join(str(version[name]) for name in ("milestone", "minor", "build", "patch"))
            if version.get("product") != "lmdj" or assembly.get("product") != {"id": "lmdj", "version": identity}:
                raise ValueError(f"Product manifest or Assembly does not declare {identity}")
            if lock.get("product") != {"id": "lmdj", "version": identity}:
                raise ValueError(f"Assembly lock does not declare {identity}")
            if lock.get("assembly_sha256") != hashlib.sha256(assembly_path.read_bytes()).hexdigest():
                raise ValueError("Assembly lock digest does not match the active Assembly")
        with _static_projection(root, "Assembly lock component digests", "active-manifests"):
            _verify_active_components(root, assembly, lock)
        with _static_projection(root, "active release intent selection", "active-manifests"):
            active = [entry for entry in entries if entry.kind.value == "product" and entry.identity == identity]
            if len(active) != 1:
                raise ValueError(f"ledger holds {len(active)} Product intents for {identity}, expected exactly one")
            active_intent = active[0]
        with _static_projection(root, "exact release target validation", "exact-target", "architecture-portal"):
            context.git.validate_release_target(root, active_intent)
        with _static_projection(root, "immutable Portal snapshot projection", "architecture-portal"):
            snapshot_path = root / "apps/architecture-portal/versioned_metadata" / f"version-{identity}.json"
            versions = _json_file(root / "apps/architecture-portal/versions.json")
            snapshot = _json_file(snapshot_path)
            if identity not in versions or snapshot.get("product_build") != identity:
                raise ValueError(f"Portal snapshot inventory does not carry {identity}")
            if snapshot.get("assembly_lock_sha256") != hashlib.sha256(lock_path.read_bytes()).hexdigest():
                raise ValueError("Portal snapshot lock digest does not match the active Assembly lock")
        with _static_projection(root, "merged-main Proof projection", "architecture-portal"):
            proof = context.proof_reader(root, active_intent)
            if (
                proof.source_branch != policy.branch
                or proof.target_revision != active_intent.target_revision
                or proof.product_build != identity
                or proof.snapshot != active_intent.snapshot
                or proof.snapshot_revision is None
            ):
                raise ValueError(f"Proof projection does not bind {active_intent.tag} to {identity}")
        with _static_projection(root, "release intent target objects", "active-manifests"):
            if (root / ".git").exists():
                for entry in entries:
                    if entry.disposition is Disposition.ABANDONED:
                        continue
                    if subprocess.run(
                        ["git", "-C", str(root), "cat-file", "-e", f"{entry.target_revision}^{{commit}}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                    ).returncode != 0:
                        raise ValueError(f"target commit of {entry.tag} is absent from the local object store")
    except _StaticProjectionError as failure:
        return AuditFinding(
            "unverifiable", policy.repository,
            f"{_STATIC_PROJECTION_MESSAGE}: {failure.projection} ({failure.reason})",
            failure.sources,
        )
    return None


def _audit_remote_intent(
    context: object,
    intent: ReleaseIntent,
    tag_state: _ObservedTag | None,
    release: GitHubRelease | None,
    exception: HistoricalException | None,
    latest_release_id: int | None,
) -> AuditFinding:
    evidence_issue = _evidence_issue(context.repo_root, intent.evidence_paths)
    if evidence_issue is not None:
        return AuditFinding("unverifiable", intent.tag, evidence_issue, intent.evidence_paths)
    if intent.disposition is Disposition.ABANDONED:
        if tag_state is not None or release is not None:
            return AuditFinding(
                "unauthorized", intent.tag,
                f"{intent.disposition.value} intent must not have a remote tag or Release",
                ("remote-tag", "github-release"),
            )
        return AuditFinding("ok", intent.tag, f"{intent.disposition.value} intent has no remote publication state")

    if intent.disposition is Disposition.SUPERSEDED_UNRELEASED:
        if release is not None:
            return AuditFinding("unauthorized", intent.tag, "superseded-unreleased intent must not have a GitHub Release")
        if tag_state is None:
            return AuditFinding("ok", intent.tag, "superseded-unreleased intent has no remote publication state")
        problem = _tag_problem(context, intent, tag_state)
        return AuditFinding("conflict", intent.tag, problem) if problem else AuditFinding(
            "ok", intent.tag, "superseded-unreleased exact tag is retained without a Release",
        )

    try:
        with context.git.detached_worktree(intent.target_revision) as worktree:
            context.git.validate_release_target(Path(worktree), intent)
    except Exception:
        return AuditFinding(
            "unverifiable", intent.tag,
            "exact release target identity or support metadata is invalid",
            ("exact-target",),
        )

    if intent.disposition is Disposition.ALLOCATED:
        if tag_state is not None or release is not None:
            return AuditFinding(
                "unauthorized", intent.tag,
                "allocated intent must not have a remote tag or Release",
                ("remote-tag", "github-release"),
            )
        return AuditFinding("ok", intent.tag, "allocated intent has no remote publication state")

    if intent.disposition is not Disposition.PUBLISHED and release is not None and not release.draft:
        return AuditFinding(
            "unauthorized", intent.tag,
            "non-published intent identifies an already published GitHub Release",
            ("github-release",),
        )

    if intent.disposition is Disposition.PUBLISHED and (tag_state is None or release is None):
        missing = "tag and Release" if tag_state is None and release is None else ("tag" if tag_state is None else "Release")
        return AuditFinding("missing", intent.tag, f"published intent is missing its remote {missing}")
    if tag_state is None:
        if release is not None:
            return AuditFinding("conflict", intent.tag, "GitHub Release exists without its exact remote tag")
        return AuditFinding("ok", intent.tag, "releasable intent has no remote publication state")

    problem = _tag_problem(context, intent, tag_state)
    if problem is not None:
        return AuditFinding("conflict", intent.tag, problem)
    try:
        if not context.git.is_main_ancestor(intent.target_revision):
            return AuditFinding("unauthorized", intent.tag, "release target is outside protected main ancestry")
    except Exception:
        return AuditFinding("external-error", intent.tag, "protected-main ancestry is unavailable", ("git-remote",))

    ci_problem = _ci_problem(context, intent)
    if ci_problem is not None:
        if ci_problem.code == "external-error":
            return ci_problem
        if not _pre_pipeline_ci_exception_matches(context, intent, exception):
            return ci_problem
    if release is None:
        result = AuditFinding("ok", intent.tag, "exact authorized remote tag exists without a Release")
        return _exception_finding(exception, result.message) if exception is not None else result
    metadata_problem = _release_problem(
        context.policy, intent, tag_state, release,
        latest_release_id=latest_release_id,
        allow_missing_marker=(
            exception is not None
            and exception.release_id is not None
            and exception.release_id == release.id
        ),
    )
    if metadata_problem is not None:
        return AuditFinding("conflict", intent.tag, metadata_problem, ("github-release",))
    try:
        asset_problem = _asset_problem(context, intent, release)
    except Exception:
        return AuditFinding("external-error", intent.tag, "GitHub asset projection or download is unavailable", ("github-assets",))
    if asset_problem is not None:
        return AuditFinding("conflict", intent.tag, asset_problem, ("github-assets",))
    if intent.kind.value == "product":
        proof_problem = _proof_problem(context, intent)
        if proof_problem is not None:
            return proof_problem
    message = "remote tag, Release metadata, CI and asset profile match canonical intent"
    return _exception_finding(exception, message) if exception is not None else AuditFinding("ok", intent.tag, message)


def _audit_remote_exception(
    context: object,
    exception: HistoricalException,
    tag_state: _ObservedTag | None,
    release: GitHubRelease | None,
) -> AuditFinding:
    evidence_issue = _evidence_issue(context.repo_root, exception.evidence_paths)
    if evidence_issue is not None:
        return AuditFinding("unverifiable", exception.tag, evidence_issue, exception.evidence_paths)
    if tag_state is None and release is None:
        return AuditFinding("missing", exception.tag, "historical exception state is absent")
    if tag_state is None or tag_state.target_revision != exception.target_revision:
        return AuditFinding("conflict", exception.tag, "historical exception tag target does not match")
    if exception.release_id is not None:
        if release is None or release.id != exception.release_id:
            return AuditFinding("conflict", exception.tag, "historical exception numeric Release ID does not match")
    elif release is not None:
        return AuditFinding("unauthorized", exception.tag, "historical tag-only exception has an unauthorized Release")
    return _exception_finding(exception, "exact pre-cutoff remote state matches")


def _tag_problem(context: object, intent: ReleaseIntent, tag: _ObservedTag) -> str | None:
    if tag.target_revision != intent.target_revision:
        return "remote tag target conflicts with the intent target"
    if tag.signer_fingerprint != context.policy.product_fingerprint:
        return "remote tag signature role conflicts with policy"
    return None


def _verify_active_components(root: Path, assembly: object, lock: object) -> None:
    if not isinstance(assembly, dict) or not isinstance(lock, dict):
        raise ValueError("Assembly or Assembly lock is not a JSON object")
    for assembly_key, lock_key, source_kind in (
        ("modules", "modules", "module"),
        ("hosts", "hosts", "host"),
        ("providers", "providers", "provider"),
        ("contracts", "contracts", "contract"),
    ):
        declared = assembly.get(assembly_key)
        locked = lock.get(lock_key)
        if not isinstance(declared, list) or not isinstance(locked, list):
            raise ValueError(f"{source_kind} inventory is missing from the Assembly or its lock")
        declared_identity = {
            (item.get("id"), item.get("version"))
            for item in declared if isinstance(item, dict)
        }
        locked_identity = {
            (item.get("id"), item.get("version"))
            for item in locked if isinstance(item, dict)
        }
        if len(declared_identity) != len(declared) or declared_identity != locked_identity:
            raise ValueError(f"{source_kind} inventory differs between the Assembly and its lock")
        for item in locked:
            if not isinstance(item, dict) or set(item) != {"id", "version", "sha256"}:
                raise ValueError(f"locked {source_kind} entry has unexpected fields")
            identifier, version, digest = item["id"], item["version"], item["sha256"]
            if not all(isinstance(value, str) and value for value in (identifier, version, digest)):
                raise ValueError(f"locked {source_kind} entry has a non-string identity or digest")
            path = _component_path(root, source_kind, identifier)
            document = _json_file(path)
            if source_kind == "provider":
                observed_digest = _provider_source_package_sha256(
                    identifier, version, path, repo_root=root,
                )
            else:
                observed_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if observed_digest != digest:
                raise ValueError(f"{source_kind} {identifier} source digest does not match the lock")
            if source_kind == "contract":
                if not isinstance(document, dict) or document.get("x-lmdj-contract-version") != version:
                    raise ValueError(f"contract {identifier} does not declare version {version}")
            elif not isinstance(document, dict) or document.get("module") != identifier or document.get("version") != version:
                raise ValueError(f"{source_kind} {identifier} does not declare version {version}")


def _component_path(root: Path, kind: str, identifier: str) -> Path:
    if kind == "module":
        path = root / "packages" / identifier / "module.json"
    elif kind == "host":
        path = root / "apps" / identifier / "module.json"
    elif kind == "provider":
        candidates = [
            path for path in (root / "providers").glob("*/module.json")
            if isinstance(_json_file(path), dict) and _json_file(path).get("module") == identifier
        ]
        if len(candidates) != 1:
            raise ValueError(f"provider {identifier} does not have exactly one manifest")
        path = candidates[0]
    else:
        candidates = list((root / "contracts").glob(f"*/{identifier}.schema.json"))
        if len(candidates) != 1:
            raise ValueError(f"contract {identifier} does not have exactly one schema")
        path = candidates[0]
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{kind} {identifier} manifest is unavailable")
    return path


def _ci_problem(context: object, intent: ReleaseIntent) -> AuditFinding | None:
    if intent.merged_main_run_id is None:
        return AuditFinding("unverifiable", intent.tag, "intent has no exact merged-main CI run")
    try:
        runs = context.github.list_runs_for_sha(context.policy.repository, intent.target_revision)
    except Exception:
        return AuditFinding("external-error", intent.tag, "GitHub Actions run projection is unavailable", ("github-actions",))
    matching = [run for run in runs if run.id == intent.merged_main_run_id]
    if len(matching) != 1:
        return AuditFinding("missing", intent.tag, "recorded merged-main CI run is absent")
    run = matching[0]
    if (
        run.event != "push" or run.head_sha != intent.target_revision
        or run.head_branch != context.policy.branch
        or run.workflow_name != context.policy.blocking_workflow
        or run.status != "completed" or run.conclusion != "success"
    ):
        return AuditFinding("conflict", intent.tag, "recorded merged-main CI run does not satisfy policy")
    return None


def _pre_pipeline_ci_exception_matches(
    context: object,
    intent: ReleaseIntent,
    exception: HistoricalException | None,
) -> bool:
    """Waive only one exact recorded pre-pipeline run whose conclusion was cancelled."""
    if (
        exception is None or exception.code != "pre-pipeline-ci-evidence"
        or intent.merged_main_run_id is None
    ):
        return False
    try:
        runs = context.github.list_runs_for_sha(
            context.policy.repository, intent.target_revision,
        )
    except Exception:
        return False
    matching = [run for run in runs if run.id == intent.merged_main_run_id]
    return len(matching) == 1 and (
        matching[0].event == "push"
        and matching[0].head_sha == intent.target_revision
        and matching[0].head_branch == context.policy.branch
        and matching[0].workflow_name == context.policy.blocking_workflow
        and matching[0].status == "completed"
        and matching[0].conclusion == "cancelled"
    )


def _release_environment_finding(context: object) -> AuditFinding | None:
    subject = "environment:release"
    try:
        environment = context.github.get_release_environment(context.policy.repository)
    except Exception:
        return AuditFinding(
            "external-error", subject,
            "release Environment projection is unavailable",
            ("github-environment",),
        )
    if environment is None:
        return AuditFinding(
            "external-error", subject,
            "release Environment is not configured",
            ("github-environment",),
        )
    if not isinstance(environment, GitHubEnvironment):
        return AuditFinding(
            "external-error", subject,
            "release Environment projection is invalid",
            ("github-environment",),
        )
    if (
        environment.name != "release"
        or environment.required_reviewer_count != 0
        or environment.prevent_self_review not in (None, False)
        or environment.protected_branches
        or not environment.custom_branch_policies
        or len(environment.branch_policies) != 1
        or environment.branch_policies[0].name != context.policy.branch
        or environment.branch_policies[0].type != "branch"
    ):
        return AuditFinding(
            "conflict", subject,
            "release Environment approval or main-only branch policy is unsafe",
            ("github-environment",),
        )
    return None


def _release_problem(
    policy: ReleasePolicy,
    intent: ReleaseIntent,
    tag_state: _ObservedTag,
    release: GitHubRelease,
    *,
    latest_release_id: int | None,
    allow_missing_marker: bool,
) -> str | None:
    if release.tag_name != intent.tag:
        return "GitHub Release tag conflicts with intent"
    expected_name = f"LMDJ {intent.identity}" if intent.kind.value == "product" else f"{intent.kind.value} {intent.identity}"
    if release.name != expected_name:
        return "GitHub Release name conflicts with intent identity"
    prerelease, make_latest = (
        (False, False) if intent.channel is None else policy.channel_release(intent.channel, intent.make_latest)
    )
    if release.prerelease is not prerelease:
        return "GitHub Release prerelease state conflicts with channel policy"
    if release.draft:
        if latest_release_id == release.id:
            return "GitHub latest Release projection identifies a Draft"
    elif make_latest and latest_release_id != release.id:
        return "GitHub latest Release projection conflicts with channel policy"
    elif not make_latest and latest_release_id == release.id:
        return "GitHub latest Release projection conflicts with channel policy"
    if intent.disposition is Disposition.PUBLISHED and release.draft:
        return "published intent still identifies a Draft Release"
    if release.target_commitish not in (intent.target_revision, policy.branch, intent.tag):
        return "GitHub Release target_commitish conflicts with canonical identity"
    markers = _MARKER.findall(release.body)
    if not markers:
        return None if allow_missing_marker else "GitHub Release plan marker is missing"
    if len(markers) != 1:
        return "GitHub Release plan marker is ambiguous"
    try:
        marker = json.loads(markers[0])
    except json.JSONDecodeError:
        return "GitHub Release plan marker is invalid"
    if (
        set(marker) != {
            "schema", "plan_schema", "plan_sha256", "tag", "tag_object",
            "target_revision", "intent",
        }
        or marker.get("schema") != "lmdj.release-plan-marker.v1"
        or marker.get("plan_schema") != "lmdj.release-plan.v1"
        or not isinstance(marker.get("plan_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", marker["plan_sha256"]) is None
        or marker.get("tag") != intent.tag
        or marker.get("tag_object") != tag_state.object_id
        or marker.get("target_revision") != intent.target_revision
        or marker.get("intent") != {
            **{"kind": intent.kind.value, "identity": intent.identity, "profile": intent.profile},
            **({"channel": intent.channel} if intent.channel is not None else {}),
        }
    ):
        return "GitHub Release plan marker conflicts with canonical intent"
    return None


def _asset_problem(context: object, intent: ReleaseIntent, release: GitHubRelease) -> str | None:
    assets = context.github.list_release_assets(context.policy.repository, release.id)
    identifiers = [asset.id for asset in assets]
    names = [asset.name for asset in assets]
    if len(identifiers) != len(set(identifiers)) or len(names) != len(set(names)):
        return "GitHub Release asset inventory is ambiguous"
    if intent.profile == "source-only":
        return None if not assets else "source-only Release contains unauthorized assets"
    if len(assets) != 3:
        return "Product Release asset inventory is incomplete"
    archive_names = [name for name in names if name.endswith(".zip")]
    if len(archive_names) != 1:
        return "Product Release archive inventory is not canonical"
    archive_name = archive_names[0]
    if set(names) != {archive_name, archive_name + ".sha256", archive_name + ".sha256.asc"}:
        return "Product Release asset names conflict with its profile"
    with tempfile.TemporaryDirectory(prefix="lmdj-release-audit-assets-") as directory:
        root = Path(directory)
        builds: list[AssetBuild] = []
        payloads: dict[str, bytes] = {}
        for asset in assets:
            payload = context.github.download_asset(context.policy.repository, release.id, asset)
            if asset.size != len(payload):
                return "GitHub asset size conflicts with downloaded bytes"
            payloads[asset.name] = payload
            path = root / asset.name
            path.write_bytes(payload)
            builds.append(AssetBuild(path, asset.name, len(payload), hashlib.sha256(payload).hexdigest()))
        checksum = payloads[archive_name + ".sha256"]
        expected = f"{hashlib.sha256(payloads[archive_name]).hexdigest()}  {archive_name}\n".encode("ascii")
        if checksum != expected:
            return "Product checksum asset conflicts with downloaded archive bytes"
        try:
            selected = tuple(ProfileBuild(tuple(builds)).assets)
            worktree = _worktree(context, intent.target_revision)
            with worktree as exact_tree:
                context.profile_verifier(intent.profile, Path(exact_tree), root, intent, selected)
        except Exception:
            return "Product asset checksum signature or profile verification failed"
    return None


def _proof_problem(context: object, intent: ReleaseIntent) -> AuditFinding | None:
    if intent.snapshot is None:
        return AuditFinding("unverifiable", intent.tag, "Product intent has no immutable snapshot")
    try:
        with _worktree(context, intent.target_revision) as exact_tree:
            proof = context.proof_reader(Path(exact_tree), intent)
        if (
            proof.source_branch != context.policy.branch
            or proof.target_revision != intent.target_revision
            or proof.product_build != intent.identity
            or proof.snapshot != intent.snapshot
            or proof.snapshot_revision is None
        ):
            raise ValueError
    except Exception:
        return AuditFinding(
            "unverifiable", intent.tag,
            "Product immutable snapshot or provenance does not bind the exact target",
            ("architecture-portal",),
        )
    return None


def _worktree(context: object, target: str):
    factory = getattr(context.git, "detached_worktree", None)
    return factory(target) if callable(factory) else nullcontext(Path(context.repo_root))


@contextmanager
def _load_remote_projection(context: object):
    context.git.fetch_authority(context.policy.repository, context.policy.branch)
    branch = context.github.get_branch(context.policy.repository, context.policy.branch)
    main = context.git.main_revision()
    if branch.name != context.policy.branch or not branch.protected or branch.commit_sha != main:
        raise RuntimeError("canonical protected-main projection conflicts")
    reader = getattr(context, "authority_reader", None)
    if callable(reader):
        with context.git.detached_worktree(main) as authority_tree:
            policy, ledger = reader(Path(authority_tree))
            if policy.repository != context.policy.repository or policy.branch != context.policy.branch:
                raise RuntimeError("canonical release authority conflicts")
            builder = getattr(context, "authority_context_builder", None)
            if not callable(builder):
                raise RuntimeError("canonical audit context builder is unavailable")
            resolved = builder(Path(authority_tree), policy, ledger)
            if (
                resolved.repo_root != Path(authority_tree)
                or resolved.policy != policy or resolved.ledger != ledger
                or resolved.git is not context.git or resolved.github is not context.github
            ):
                raise RuntimeError("canonical audit context is not authority-rooted")
            tags, releases, latest_release_id = _remote_inventories(resolved)
            yield resolved, tags, releases, latest_release_id
            return
    tags, releases, latest_release_id = _remote_inventories(context)
    yield context, tags, releases, latest_release_id


def _remote_inventories(
    context: object,
) -> tuple[dict[str, _ObservedTag], dict[str, GitHubRelease], int | None]:
    tags = _list_remote_tags(context)
    release_items = _list_releases(context.github, context.policy.repository)
    releases: dict[str, GitHubRelease] = {}
    identifiers: set[int] = set()
    for release in release_items:
        if release.tag_name in releases or release.id in identifiers:
            raise RuntimeError("GitHub Release inventory is ambiguous")
        releases[release.tag_name] = release
        identifiers.add(release.id)
    latest = context.github.get_latest_release(context.policy.repository)
    if latest is not None and latest.id not in identifiers:
        raise RuntimeError("GitHub latest Release is absent from complete inventory")
    return tags, releases, latest.id if latest is not None else None


def _list_remote_tags(context: object) -> dict[str, _ObservedTag]:
    git = context.git
    method = getattr(git, "list_remote_tags", None)
    if callable(method):
        return {name: _coerce_tag(value) for name, value in method().items()}
    runner = getattr(git, "runner")
    root = getattr(git, "root")
    result = runner.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/lmdj-release/tags/"],
        cwd=root,
    )
    prefix = "refs/lmdj-release/tags/"
    tags: dict[str, _ObservedTag] = {}
    with tempfile.TemporaryDirectory(prefix="lmdj-release-audit-tags-") as directory:
        verification_home = Path(directory)
        verification_home.chmod(0o700)
        verifier = OpenPgpVerifier(runner=runner)
        verifier.import_public_key(
            verification_home,
            Path(context.repo_root) / ".github/release-signing-keys/lmdj-product.asc",
            context.policy.product_fingerprint,
        )
        for line in result.stdout.splitlines():
            if not line.startswith(prefix) or line == prefix:
                raise RuntimeError("remote tag inventory is invalid")
            name = line[len(prefix):]
            reference = prefix + name
            object_id = runner.run(["git", "rev-parse", "--verify", reference], cwd=root).stdout.strip()
            target = runner.run(["git", "rev-parse", "--verify", f"{reference}^{{commit}}"], cwd=root).stdout.strip()
            object_type = runner.run(["git", "cat-file", "-t", reference], cwd=root).stdout.strip()
            signer: str | None = None
            if object_type == "tag":
                tag_file = verification_home / "tag.object"
                tag_file.write_text(
                    runner.run(["git", "cat-file", "tag", reference], cwd=root).stdout,
                    encoding="utf-8", newline="",
                )
                try:
                    verifier.verify_inline_tag(
                        verification_home, tag_file, context.policy.product_fingerprint,
                    )
                    signer = context.policy.product_fingerprint
                except OpenPgpError:
                    signer = None
                finally:
                    tag_file.unlink(missing_ok=True)
            elif object_type != "commit":
                raise RuntimeError("remote tag object type is invalid")
            tags[name] = _ObservedTag(object_id, target, signer)
    return tags


def _coerce_tag(value: object) -> _ObservedTag:
    if value is None:
        raise RuntimeError("remote tag inventory is incomplete")
    object_id = getattr(value, "object_id", None)
    target = getattr(value, "target_revision", None)
    signer = getattr(value, "signer_fingerprint", None)
    if not _sha(object_id) or not _sha(target) or (signer is not None and not isinstance(signer, str)):
        raise RuntimeError("remote tag inventory is invalid")
    return _ObservedTag(object_id, target, signer)


def _list_releases(github: object, repository: str) -> list[GitHubRelease]:
    method = getattr(github, "list_releases", None)
    if not callable(method):
        raise RuntimeError("typed GitHub Release inventory API is unavailable")
    result = method(repository)
    if not isinstance(result, list) or not all(isinstance(item, GitHubRelease) for item in result):
        raise RuntimeError("GitHub Release inventory is invalid")
    return result


def _evidence_issue(root: Path, paths: Iterable[str]) -> str | None:
    root = Path(root)
    for relative in paths:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            return f"tracked evidence is unavailable: {relative}"
        if (root / ".git").exists():
            result = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if result.returncode != 0:
                return f"evidence is not tracked: {relative}"
    return None


def _exception_finding(exception: HistoricalException | None, prefix: str) -> AuditFinding:
    if exception is None:
        raise ValueError("historical exception is required")
    return AuditFinding(
        "ok-with-historical-exception",
        exception.tag,
        f"{prefix}; {exception.code}: {exception.reason}",
        exception.evidence_paths,
    )


def _report(
    observed: str,
    repository: str,
    mode: str,
    findings: Iterable[AuditFinding],
    incomplete: Iterable[str] = (),
) -> AuditReport:
    ordered = tuple(sorted(findings, key=lambda item: (item.subject, item.code, item.message)))
    incomplete_sources = set(incomplete)
    incomplete_sources.update(
        source
        for item in ordered if item.code == "external-error"
        for source in item.sources
    )
    return AuditReport(observed, repository, mode, ordered, tuple(sorted(incomplete_sources)))


def _observed_utc(value: datetime | None) -> str:
    selected = datetime.now(timezone.utc) if value is None else value
    if selected.tzinfo is None:
        raise ValueError("audit observation time must be timezone-aware")
    return selected.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_file(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)
