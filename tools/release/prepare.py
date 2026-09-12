"""Fail-closed local release preparation; no remote mutation capability exists here."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable, Protocol

from .ci_evidence import verify_release_ci
from .batch_reference import thaw
from .changelog import ChangelogError, render as render_changelog, verify_source as verify_changelog_source
from .github_api import (
    BranchProjection,
    CiScopeProjection,
    RunJobProjection,
    RunProjection,
)
from .model import CANONICAL_BRANCH, CANONICAL_REPOSITORY, Disposition, ReleaseIntent, ReleaseLedger, ReleaseModelError, ReleasePlan, ReleasePolicy, canonical_json, classify_tag, load_ledger, load_policy
from .profiles import (
    AssetBuild,
    ProfileBuild,
    ProfileError,
    ProfileRuntime,
    build_profile,
    canonical_product_asset_names,
    verify_existing_profile,
)


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
    snapshot_revision: str | None = None


@dataclass(frozen=True)
class PreparedRelease:
    plan: ReleasePlan
    digest: str
    output_root: Path
    reused_local_tag: bool


class ReleaseGit(Protocol):
    def fetch_authority(self, repository: str, branch: str) -> None: ...
    def main_revision(self) -> str: ...
    def is_main_ancestor(self, target: str) -> bool: ...
    def is_revision_ancestor(self, ancestor: str, descendant: str) -> bool: ...
    def remote_tag_state(self, tag: str) -> LocalTag | None: ...
    def local_tag_state(self, tag: str) -> LocalTag | None: ...
    def detached_worktree(self, target: str): ...
    def validate_release_target(self, worktree: Path, intent: ReleaseIntent) -> None: ...
    def create_local_tag(self, tag: str, target: str, signer: str, message: str) -> LocalTag: ...


class ReleaseGitHub(Protocol):
    def get_branch(self, repository: str, branch: str) -> BranchProjection: ...
    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]: ...
    def list_run_jobs(self, repository: str, run_id: int) -> list[RunJobProjection]: ...
    def get_ci_scope_manifest(
        self, repository: str, run: RunProjection,
    ) -> CiScopeProjection: ...


ProfileBuilder = Callable[[str, Path, Path, ReleaseIntent], ProfileBuild]
ProfileVerifier = Callable[[str, Path, Path, ReleaseIntent, tuple[AssetBuild, ...]], None]
ProofReader = Callable[[Path, ReleaseIntent], ProductProof]
AuthorityReader = Callable[[Path], tuple[ReleasePolicy, ReleaseLedger]]


@dataclass
class PrepareContext:
    repo_root: Path
    policy: ReleasePolicy
    ledger: ReleaseLedger
    git: ReleaseGit
    github: ReleaseGitHub
    profile_builder: ProfileBuilder
    profile_verifier: ProfileVerifier
    proof_reader: ProofReader
    tag_signer_fingerprint: str
    checksum_signer_fingerprint: str
    authority_reader: AuthorityReader | None = None


def prepare(tag: str, context: PrepareContext) -> PreparedRelease:
    """Prepare only local verified output and an annotated local tag for one intent."""
    policy, ledger, branch = _load_canonical_authority(context)
    resolved = replace(context, policy=policy, ledger=ledger, authority_reader=None)
    identity = classify_tag(tag, policy)
    intent = ledger.intent_for_tag(tag)
    if intent is None or intent.kind is not identity.kind:
        raise PrepareError("release tag is not authorized by the intent ledger")
    if intent.disposition is not Disposition.RELEASABLE:
        raise PrepareError("only releasable release intents may be prepared")
    if any(exception.tag == tag for exception in ledger.historical_exceptions):
        raise PrepareError("historical exception is audit-only and cannot authorize prepare")
    _verify_key_roles(resolved, intent)
    if not resolved.git.is_main_ancestor(intent.target_revision):
        raise PrepareError("release target does not have canonical main ancestry")
    if resolved.git.remote_tag_state(tag) is not None:
        raise PrepareError("remote tag already exists; prepare refuses remote tag conflicts")
    run = _verify_ci(resolved, intent)
    if intent.changelog is not None:
        try:
            verify_changelog_source(resolved.repo_root, intent, ledger, thaw(intent.changelog))
        except ChangelogError as error:
            raise PrepareError(str(error)) from None

    existing = resolved.git.local_tag_state(tag)
    if existing is not None and not _matching_tag(existing, intent.target_revision, resolved.tag_signer_fingerprint):
        raise PrepareError("local tag conflict; formal tags are never moved")

    with resolved.git.detached_worktree(intent.target_revision) as worktree:
        try:
            resolved.git.validate_release_target(Path(worktree), intent)
        except Exception:
            raise PrepareError("exact release target identity or support metadata is invalid") from None
        if intent.kind.value == "product":
            _verify_product_proof(resolved, Path(worktree), intent)
        existing_output = _existing_output_root(resolved.repo_root, identity.output_name)
        if existing_output is not None:
            if existing is None:
                raise PrepareError("existing release output has no matching local signed tag")
            return _reconcile_existing_output(
                resolved, intent, existing, run, Path(worktree), existing_output,
            )
        with tempfile.TemporaryDirectory(prefix="lmdj-release-profile-") as directory:
            profile_output = Path(directory)
            built = resolved.profile_builder(intent.profile, Path(worktree), profile_output, intent)
            assets = _verify_profile_assets(intent, built)
            if existing is None:
                tag_state = resolved.git.create_local_tag(
                    tag,
                    intent.target_revision,
                    resolved.tag_signer_fingerprint,
                    f"LMDJ release {tag}",
                )
                if not _matching_tag(tag_state, intent.target_revision, resolved.tag_signer_fingerprint):
                    raise PrepareError("local signed tag verification failed")
            else:
                tag_state = existing
            plan = _release_plan(policy, tag, tag_state, intent, assets)
            document = _plan_document(plan, intent, run, policy)
            digest = hashlib.sha256(canonical_json(document)).hexdigest()
            output_root = _write_output(resolved.repo_root, plan.output_name, document, digest, assets)
    return PreparedRelease(plan, digest, output_root, existing is not None)


def _load_canonical_authority(context: PrepareContext) -> tuple[ReleasePolicy, ReleaseLedger, BranchProjection]:
    try:
        context.git.fetch_authority(CANONICAL_REPOSITORY, CANONICAL_BRANCH)
        branch = context.github.get_branch(CANONICAL_REPOSITORY, CANONICAL_BRANCH)
        main_revision = context.git.main_revision()
    except Exception:
        raise PrepareError("canonical main authority is unavailable") from None
    if branch.name != CANONICAL_BRANCH or not branch.protected:
        raise PrepareError("canonical main branch must be protected")
    if main_revision != branch.commit_sha:
        raise PrepareError("canonical main revision does not match GitHub branch projection")
    reader = context.authority_reader or load_authority_documents
    try:
        with context.git.detached_worktree(main_revision) as authority_tree:
            policy, ledger = reader(Path(authority_tree))
    except (OSError, ReleaseModelError, PrepareError):
        raise PrepareError("canonical release policy and intent ledger are unavailable") from None
    if policy.repository != CANONICAL_REPOSITORY or policy.branch != CANONICAL_BRANCH:
        raise PrepareError("canonical release policy does not bind the fetched authority")
    return policy, ledger, branch


def _verify_key_roles(context: PrepareContext, intent: ReleaseIntent) -> None:
    if context.checksum_signer_fingerprint != context.policy.checksum_fingerprint:
        raise PrepareError("release checksum signer does not match the checksum key role")
    if intent.kind.value == "product" and context.tag_signer_fingerprint != context.policy.product_fingerprint:
        raise PrepareError("Product signer does not match the Product key role")
    if intent.kind.value != "product" and context.tag_signer_fingerprint != context.policy.product_fingerprint:
        raise PrepareError("release tag signer does not match the configured key role")
    if context.tag_signer_fingerprint == context.checksum_signer_fingerprint:
        raise PrepareError("release tag and checksum signers must be distinct")


def _verify_ci(context: PrepareContext, intent: ReleaseIntent) -> RunProjection:
    """Require full exact-main evidence before any prospective release step.

    `prepare` only ever reaches this with a `releasable` intent, so current
    policy requires its retained complete self-test verdict. The shared
    transition path also verifies an already `published` intent, which is read
    from immutable tag, Release, assets and plan marker instead: its artifact
    has a bounded retention and must not be able to invalidate history.
    """
    result = verify_release_ci(context.github, policy=context.policy, intent=intent, git_root=context.repo_root)
    if result.code == "external-error":
        raise PrepareError("exact target CI projection is unavailable")
    if result.code == "unverifiable":
        if intent.merged_main_run_id is None:
            raise PrepareError("release intent is missing its merged-main CI run")
        raise PrepareError(
            "release intent has no retained full merged-main CI evidence: " + result.message
        )
    if result.code != "ok" or result.run is None:
        raise PrepareError(
            "release intent does not have an exact successful merged-main CI run: "
            + result.message
        )
    return result.run


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
    if proof.snapshot_revision is None:
        raise PrepareError("Product immutable snapshot has no authenticated source revision")


def _verify_profile_assets(intent: ReleaseIntent, built: ProfileBuild) -> tuple[AssetBuild, ...]:
    assets = tuple(built.assets)
    if intent.profile == "source-only":
        if assets:
            raise PrepareError("source-only releases must not create release assets")
        return assets
    names = [asset.name for asset in assets]
    if len(names) != len(set(names)) or any(asset.path.name != asset.name for asset in assets):
        raise PrepareError("release asset inventory contains duplicate or renamed assets")
    try:
        expected = canonical_product_asset_names(
            intent.profile,
            names,
            intent.identity,
        )
    except ProfileError:
        raise PrepareError(
            "Product release asset inventory is not canonical for its profile"
        ) from None
    if set(names) != expected:
        raise PrepareError("Product release asset inventory is not canonical for its profile")
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
    if intent.self_test_evidence is not None:
        document["ci"]["self_test_evidence"] = dict(intent.self_test_evidence)
        document["ci"]["target_revision"] = intent.target_revision
    if intent.batch_test_evidence is not None:
        document["ci"]["batch_test_evidence"] = thaw(intent.batch_test_evidence)
        document["ci"]["target_revision"] = intent.target_revision
    if intent.changelog is not None:
        document["changelog"] = thaw(intent.changelog)
    return document


def notes_for_plan(document: dict[str, object]) -> str:
    if "changelog" in document:
        return render_changelog(document["changelog"])
    # Preserve historical plans byte-for-byte; new orchestration admission must
    # require a frozen changelog. Legacy callers are not cut over here.
    return f"# { _release_name_from_document(document) }\n\nPrepared locally for `{document['tag']}`.\n"


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
            notes_for_plan(document),
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


def _release_plan(
    policy: ReleasePolicy,
    tag: str,
    tag_state: LocalTag,
    intent: ReleaseIntent,
    assets: tuple[AssetBuild, ...],
) -> ReleasePlan:
    return ReleasePlan(
        schema="lmdj.release-plan.v1",
        repository=policy.repository,
        tag=tag,
        tag_object=tag_state.object_id,
        target_revision=intent.target_revision,
        kind=intent.kind,
        identity=intent.identity,
        channel=intent.channel,
        profile=intent.profile,
        assets=tuple(asset.record() for asset in assets),
    )


def _existing_output_root(repo_root: Path, encoded_tag: str) -> Path | None:
    root = repo_root / "build/release"
    if root.exists() or root.is_symlink():
        if root.is_symlink() or not root.is_dir():
            raise PrepareError("release output root is unsafe")
    output = root / encoded_tag
    if output.exists() or output.is_symlink():
        return output
    return None


def _reconcile_existing_output(
    context: PrepareContext,
    intent: ReleaseIntent,
    tag_state: LocalTag,
    run: RunProjection,
    worktree: Path,
    output: Path,
) -> PreparedRelease:
    if not output.is_dir() or output.is_symlink():
        raise PrepareError("existing release output is unsafe")
    assets_root = output / "assets"
    try:
        assets = _existing_profile_assets(assets_root)
        assets = _verify_profile_assets(intent, ProfileBuild(assets))
        context.profile_verifier(intent.profile, worktree, assets_root, intent, assets)
    except (OSError, ValueError, RuntimeError):
        raise PrepareError("existing release profile assets are invalid") from None
    plan = _release_plan(context.policy, intent.tag, tag_state, intent, assets)
    document = _plan_document(plan, intent, run, context.policy)
    digest = hashlib.sha256(canonical_json(document)).hexdigest()
    if not _matches_existing_output(output, document, digest, assets):
        raise PrepareError("existing release output does not reconcile")
    return PreparedRelease(plan, digest, output, True)


def _existing_profile_assets(assets_root: Path) -> tuple[AssetBuild, ...]:
    if not assets_root.is_dir() or assets_root.is_symlink():
        raise PrepareError("existing release assets are unavailable")
    assets: list[AssetBuild] = []
    for path in sorted(assets_root.iterdir()):
        if not path.is_file() or path.is_symlink():
            raise PrepareError("existing release assets are unavailable")
        payload = path.read_bytes()
        assets.append(AssetBuild(path, path.name, len(payload), hashlib.sha256(payload).hexdigest()))
    return tuple(assets)


def _sha(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def default_profile_builder(runtime: ProfileRuntime) -> ProfileBuilder:
    return lambda profile, worktree, output, intent: build_profile(profile, worktree, output, intent, runtime=runtime)


def default_profile_verifier(runtime: ProfileRuntime) -> ProfileVerifier:
    return lambda profile, worktree, assets_root, intent, assets: verify_existing_profile(
        profile, worktree, assets_root, intent, assets, runtime,
    )


def load_authority_documents(worktree: Path) -> tuple[ReleasePolicy, ReleaseLedger]:
    policy = load_policy(worktree / "tools/release/policy.json")
    return policy, load_ledger(worktree / "docs/release-evidence/release-intents.json", policy)


def read_product_snapshot_proof(worktree: Path, intent: ReleaseIntent) -> ProductProof:
    """Read the immutable Portal snapshot recorded in the exact target tree."""
    if intent.snapshot is None:
        raise PrepareError("Product release intent is missing an immutable snapshot")
    path = worktree / "apps/architecture-portal/versioned_metadata" / f"version-{intent.snapshot}.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        product = document["product"]
        product_build = document["product_build"]
        snapshot = product["version"]
        revision = document["revision"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        raise PrepareError("structured merged-main Proof projection is unavailable") from None
    if (
        not isinstance(product_build, str) or not isinstance(snapshot, str)
        or not isinstance(revision, str) or not _sha(revision)
        or product_build != snapshot
    ):
        raise PrepareError("structured merged-main Proof projection is unavailable")
    return ProductProof("main", intent.target_revision, product_build, snapshot, revision)


def _matches_existing_output(
    output: Path, document: dict[str, object], digest: str, assets: tuple[AssetBuild, ...],
) -> bool:
    if not output.is_dir() or output.is_symlink():
        return False
    try:
        if (output / "release-plan.json").read_bytes() != canonical_json(document):
            return False
        if (output / "release-plan.sha256").read_text(encoding="ascii") != digest + "\n":
            return False
        expected_notes = notes_for_plan(document)
        if (output / "release-notes.md").read_text(encoding="utf-8") != expected_notes:
            return False
        assets_root = output / "assets"
        if not assets_root.is_dir() or assets_root.is_symlink():
            return False
        expected_names = {asset.name for asset in assets}
        actual_names = {path.name for path in assets_root.iterdir() if path.is_file() and not path.is_symlink()}
        if actual_names != expected_names or len(list(assets_root.iterdir())) != len(actual_names):
            return False
        for asset in assets:
            saved = assets_root / asset.name
            if saved.read_bytes() != asset.path.read_bytes():
                return False
    except (OSError, UnicodeDecodeError):
        return False
    return True
