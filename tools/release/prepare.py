"""Fail-closed local release preparation; no remote mutation capability exists here."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable, Protocol

from .github_api import BranchProjection, RunProjection
from .model import AssetRecord, Disposition, ReleaseIntent, ReleaseLedger, ReleasePlan, ReleasePolicy, canonical_json, classify_tag
from .profiles import AssetBuild, ProfileBuild, ProfileRuntime, build_profile


class PrepareError(RuntimeError):
    """A local release preparation precondition did not hold."""


@dataclass(frozen=True)
class LocalTag:
    object_id: str
    target_revision: str
    signer_fingerprint: str


@dataclass(frozen=True)
class ProductProof:
    source_branch: str
    target_revision: str
    product_build: str
    snapshot: str


@dataclass(frozen=True)
class PreparedRelease:
    plan: ReleasePlan
    digest: str
    output_root: Path
    reused_local_tag: bool


class ReleaseGit(Protocol):
    def fetch_authority(self, branch: str) -> None: ...
    def is_main_ancestor(self, target: str) -> bool: ...
    def remote_tag_state(self, tag: str) -> LocalTag | None: ...
    def local_tag_state(self, tag: str) -> LocalTag | None: ...
    def detached_worktree(self, target: str): ...
    def create_local_tag(self, tag: str, target: str, signer: str, message: str) -> LocalTag: ...


class ReleaseGitHub(Protocol):
    def get_branch(self, repository: str, branch: str) -> BranchProjection: ...
    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]: ...


ProfileBuilder = Callable[[str, Path, Path, ReleaseIntent], ProfileBuild]
ProofReader = Callable[[Path, ReleaseIntent], ProductProof]


@dataclass
class PrepareContext:
    repo_root: Path
    policy: ReleasePolicy
    ledger: ReleaseLedger
    git: ReleaseGit
    github: ReleaseGitHub
    profile_builder: ProfileBuilder
    proof_reader: ProofReader
    tag_signer_fingerprint: str
    checksum_signer_fingerprint: str


def prepare(tag: str, context: PrepareContext) -> PreparedRelease:
    """Prepare only local verified output and an annotated local tag for one intent."""
    identity = classify_tag(tag, context.policy)
    intent = context.ledger.intent_for_tag(tag)
    if intent is None or intent.kind is not identity.kind:
        raise PrepareError("release tag is not authorized by the intent ledger")
    if intent.disposition is not Disposition.RELEASABLE:
        raise PrepareError("only releasable release intents may be prepared")
    if any(exception.tag == tag for exception in context.ledger.historical_exceptions):
        raise PrepareError("historical exception is audit-only and cannot authorize prepare")
    _verify_key_roles(context, intent)

    try:
        context.git.fetch_authority(context.policy.branch)
        branch = context.github.get_branch(context.policy.repository, context.policy.branch)
    except Exception:
        raise PrepareError("canonical main authority is unavailable") from None
    if branch.name != context.policy.branch or not branch.protected:
        raise PrepareError("canonical main branch must be protected")
    if not context.git.is_main_ancestor(intent.target_revision):
        raise PrepareError("release target does not have canonical main ancestry")
    if context.git.remote_tag_state(tag) is not None:
        raise PrepareError("remote tag already exists; prepare refuses remote tag conflicts")
    _verify_ci(context, intent)

    existing = context.git.local_tag_state(tag)
    if existing is not None and not _matching_tag(existing, intent.target_revision, context.tag_signer_fingerprint):
        raise PrepareError("local tag conflict; formal tags are never moved")

    with context.git.detached_worktree(intent.target_revision) as worktree:
        if intent.kind.value == "product":
            _verify_product_proof(context, Path(worktree), intent)
        with tempfile.TemporaryDirectory(prefix="lmdj-release-profile-") as directory:
            profile_output = Path(directory)
            built = context.profile_builder(intent.profile, Path(worktree), profile_output, intent)
            assets = _verify_profile_assets(intent, built)
            if existing is None:
                tag_state = context.git.create_local_tag(
                    tag,
                    intent.target_revision,
                    context.tag_signer_fingerprint,
                    f"LMDJ release {tag}",
                )
                if not _matching_tag(tag_state, intent.target_revision, context.tag_signer_fingerprint):
                    raise PrepareError("local signed tag verification failed")
            else:
                tag_state = existing
            plan = ReleasePlan(
                schema="lmdj.release-plan.v1",
                repository=context.policy.repository,
                tag=tag,
                tag_object=tag_state.object_id,
                target_revision=intent.target_revision,
                kind=intent.kind,
                identity=intent.identity,
                channel=intent.channel,
                profile=intent.profile,
                assets=tuple(asset.record() for asset in assets),
            )
            document = _plan_document(plan, intent, _matching_run(context, intent), context.policy)
            digest = hashlib.sha256(canonical_json(document)).hexdigest()
            output_root = _write_output(context.repo_root, plan.output_name, document, digest, assets)
    return PreparedRelease(plan, digest, output_root, existing is not None)


def _verify_key_roles(context: PrepareContext, intent: ReleaseIntent) -> None:
    if context.checksum_signer_fingerprint != context.policy.checksum_fingerprint:
        raise PrepareError("release checksum signer does not match the checksum key role")
    if intent.kind.value == "product" and context.tag_signer_fingerprint != context.policy.product_fingerprint:
        raise PrepareError("Product signer does not match the Product key role")
    if intent.kind.value != "product" and context.tag_signer_fingerprint != context.policy.product_fingerprint:
        raise PrepareError("release tag signer does not match the configured key role")
    if context.tag_signer_fingerprint == context.checksum_signer_fingerprint:
        raise PrepareError("release tag and checksum signers must be distinct")


def _verify_ci(context: PrepareContext, intent: ReleaseIntent) -> None:
    run = _matching_run(context, intent)
    if (
        run.event != "push" or run.head_sha != intent.target_revision
        or run.status != "completed" or run.conclusion != "success"
    ):
        raise PrepareError("release intent does not have an exact successful merged-main CI run")


def _matching_run(context: PrepareContext, intent: ReleaseIntent) -> RunProjection:
    if intent.merged_main_run_id is None:
        raise PrepareError("release intent is missing its merged-main CI run")
    try:
        runs = context.github.list_runs_for_sha(context.policy.repository, intent.target_revision)
    except Exception:
        raise PrepareError("exact target CI projection is unavailable") from None
    matching = [run for run in runs if run.id == intent.merged_main_run_id]
    if len(matching) != 1:
        raise PrepareError("release intent does not have an exact successful merged-main CI run")
    return matching[0]


def _verify_product_proof(context: PrepareContext, worktree: Path, intent: ReleaseIntent) -> None:
    if intent.snapshot is None:
        raise PrepareError("Product release intent is missing an immutable snapshot")
    try:
        proof = context.proof_reader(worktree, intent)
    except Exception:
        raise PrepareError("merged-main Proof is unavailable") from None
    if proof.source_branch != context.policy.branch or proof.target_revision != intent.target_revision:
        raise PrepareError("merged-main Proof does not bind canonical main and the release target")
    if proof.product_build != intent.identity:
        raise PrepareError("merged-main Proof Product Build does not match the release tag")
    if proof.snapshot != intent.snapshot:
        raise PrepareError("Product immutable snapshot does not match the release intent")


def _verify_profile_assets(intent: ReleaseIntent, built: ProfileBuild) -> tuple[AssetBuild, ...]:
    assets = tuple(built.assets)
    if intent.profile == "source-only":
        if assets:
            raise PrepareError("source-only releases must not create release assets")
        return assets
    if len(assets) != 3:
        raise PrepareError("Product release profile must produce exactly three assets")
    names = [asset.name for asset in assets]
    if len(names) != len(set(names)) or any(asset.path.name != asset.name for asset in assets):
        raise PrepareError("release asset inventory contains duplicate or renamed assets")
    archive = next((name for name in names if name.endswith(".zip")), None)
    if archive is None or set(names) != {archive, archive + ".sha256", archive + ".sha256.asc"}:
        raise PrepareError("Product release asset inventory is not canonical")
    for asset in assets:
        try:
            if not asset.path.is_file() or asset.path.is_symlink():
                raise OSError
            payload = asset.path.read_bytes()
        except OSError:
            raise PrepareError("release profile asset is unavailable") from None
        if asset.bytes != len(payload) or asset.sha256 != hashlib.sha256(payload).hexdigest():
            raise PrepareError("release profile asset inventory does not match bytes")
    return assets


def _matching_tag(tag: LocalTag, target: str, signer: str) -> bool:
    return (
        _sha(tag.object_id) and tag.target_revision == target
        and tag.signer_fingerprint == signer
    )


def _plan_document(
    plan: ReleasePlan, intent: ReleaseIntent, run: RunProjection, policy: ReleasePolicy,
) -> dict[str, object]:
    prerelease, make_latest = (
        (False, False) if intent.channel is None else policy.channel_release(intent.channel, intent.make_latest)
    )
    document: dict[str, object] = {
        "schema": plan.schema,
        "repository": plan.repository,
        "tag": plan.tag,
        "tag_object": plan.tag_object,
        "target_revision": plan.target_revision,
        "kind": plan.kind.value,
        "identity": plan.identity,
        "profile": plan.profile,
        "ci": {"run_id": run.id, "event": run.event, "head_sha": run.head_sha, "conclusion": run.conclusion},
        "release": {
            "draft": True,
            "prerelease": prerelease,
            "make_latest": make_latest,
            "name": _release_name(plan),
        },
        "assets": [{"name": asset.name, "bytes": asset.bytes, "sha256": asset.sha256} for asset in plan.assets],
    }
    if plan.channel is not None:
        document["channel"] = plan.channel
    if intent.snapshot is not None:
        document["snapshot"] = intent.snapshot
    return document


def _release_name(plan: ReleasePlan) -> str:
    if plan.kind.value == "product":
        return f"LMDJ {plan.identity}"
    return f"{plan.kind.value} {plan.identity}"


def _write_output(
    repo_root: Path,
    encoded_tag: str,
    document: dict[str, object],
    digest: str,
    assets: tuple[AssetBuild, ...],
) -> Path:
    root = repo_root / "build/release"
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise PrepareError("release output root is unsafe")
    output = root / encoded_tag
    if output.exists() or output.is_symlink():
        raise PrepareError("release output already exists; inspect and reconcile before retry")
    staged = Path(tempfile.mkdtemp(prefix=".lmdj-release-plan-", dir=root))
    try:
        assets_root = staged / "assets"
        assets_root.mkdir()
        for asset in assets:
            shutil.copyfile(asset.path, assets_root / asset.name)
        (staged / "release-plan.json").write_bytes(canonical_json(document))
        (staged / "release-plan.sha256").write_text(digest + "\n", encoding="ascii", newline="\n")
        (staged / "release-notes.md").write_text(
            f"# { _release_name_from_document(document) }\n\nPrepared locally for `{document['tag']}`.\n",
            encoding="utf-8", newline="\n",
        )
        os.replace(staged, output)
    except OSError as error:
        raise PrepareError("release output could not be written atomically") from error
    finally:
        if staged.exists() and not staged.is_symlink():
            shutil.rmtree(staged)
    return output


def _release_name_from_document(document: dict[str, object]) -> str:
    release = document["release"]
    return release["name"] if isinstance(release, dict) and isinstance(release.get("name"), str) else "LMDJ release"


def _sha(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def default_profile_builder(runtime: ProfileRuntime) -> ProfileBuilder:
    return lambda profile, worktree, output, intent: build_profile(profile, worktree, output, intent, runtime=runtime)


def unavailable_proof_reader(worktree: Path, intent: ReleaseIntent) -> ProductProof:
    """Fail closed until a structured immutable Proof projection is supplied."""
    raise PrepareError("structured merged-main Proof projection is unavailable")
