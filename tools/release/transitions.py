"""Separately authorized exact tag and GitHub Draft release transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping

from .github_api import GitHubAsset, GitHubRelease
from .model import (
    Disposition,
    ReleaseIntent,
    canonical_json,
    classify_tag,
)
from .prepare import (
    PrepareContext,
    _load_canonical_authority,
    _matching_tag,
    _plan_document,
    _release_plan,
    _verify_ci,
    _verify_key_roles,
    _verify_product_proof,
    _verify_profile_assets,
)
from .profiles import AssetBuild, ProfileBuild


class TransitionError(RuntimeError):
    """An exact release transition could not be safely reconciled."""


@dataclass(frozen=True)
class TransitionResult:
    status: str
    plan_sha256: str
    release_id: int | None = None
    release_url: str | None = None
    assets: tuple[GitHubAsset, ...] = ()


@dataclass(frozen=True)
class _Authority:
    context: PrepareContext
    intent: ReleaseIntent
    tag_state: object


@dataclass(frozen=True)
class _VerifiedRelease:
    result: TransitionResult
    authority: _Authority
    release: GitHubRelease
    release_snapshot: tuple[object, ...]
    asset_snapshot: tuple[tuple[object, ...], ...]


_MARKER_SCHEMA = "lmdj.release-plan-marker.v1"
_MARKER_PATTERN = re.compile(r"<!-- (lmdj\.release-plan-marker\.v1) (\{[^\r\n]*\}) -->")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def push_tag(tag: str, context: PrepareContext) -> TransitionResult:
    """Push or reconcile one exact formal tag, then verify freshly fetched state."""
    authority = _formal_authority(tag, context, require_local=True, require_remote=False)
    document, digest, _ = _load_prepared(authority)
    local = authority.context.git.local_tag_state(tag)
    remote = authority.context.git.remote_tag_state(tag)
    if remote is not None and remote != local:
        raise TransitionError("remote tag conflict; formal tags are never moved")
    if authority.intent.disposition is Disposition.PUBLISHED and remote is None:
        raise TransitionError("published release intent cannot authorize a missing remote tag")
    status = "already-pushed"
    transport_detail = ""
    if remote is None:
        _require_releasable(authority, "formal tag push")
        try:
            authority.context.git.push_tag(tag)
        except Exception as error:
            # A transport failure can occur after the server accepted the push.
            transport_detail = getattr(error, "detail", "")
        status = "pushed"

    try:
        refreshed = _formal_authority(tag, context, require_local=True, require_remote=True)
    except TransitionError as error:
        if transport_detail:
            raise TransitionError(f"{error}; tag push transport: {transport_detail}") from None
        raise
    remote = refreshed.context.git.remote_tag_state(tag)
    if remote != local:
        raise TransitionError("remote tag push could not be reconciled")
    _assert_plan_tag(document, remote, refreshed.intent)
    return TransitionResult(status, digest)


def create_draft(tag: str, context: PrepareContext) -> TransitionResult:
    """Create or resume one Draft without editing or clobbering existing state."""
    authority = _formal_authority(tag, context, require_local=True, require_remote=True)
    document, digest, local_assets = _load_prepared(authority)
    remote = authority.context.git.remote_tag_state(tag)
    _assert_plan_tag(document, remote, authority.intent)
    release = _release_by_tag(authority, tag)
    if authority.intent.disposition is Disposition.PUBLISHED and release is None:
        raise TransitionError("published release intent cannot authorize a new Draft")
    if authority.intent.disposition is Disposition.PUBLISHED and release is not None:
        if release.draft:
            raise TransitionError("published release intent is read-only and cannot resume a Draft")
        result = verify_draft(tag, release.id, digest, context)
        return replace(result, status="already-published")
    created = release is None
    if release is None:
        _require_releasable(authority, "Draft creation")
        body = _release_body(authority.context.repo_root, document, digest)
        release_fields = _release_fields(document)
        try:
            release = authority.context.github.create_draft_release(
                authority.context.policy.repository,
                tag=tag,
                name=release_fields["name"],
                body=body,
                prerelease=release_fields["prerelease"],
                make_latest=release_fields["make_latest"],
            )
        except Exception:
            release = _release_by_tag(authority, tag)
            if release is None:
                raise TransitionError("GitHub Draft creation is uncertain and did not reconcile") from None

    _verify_release_metadata(release, document, digest, allow_published=True)
    _verify_latest_projection(authority, release, document)
    if not release.draft:
        result = verify_draft(tag, release.id, digest, context)
        return replace(result, status="already-published")

    _resume_assets(authority, release, document, local_assets)
    verified = verify_draft(tag, release.id, digest, context)
    return replace(verified, status="draft-created" if created else "draft-verified")


def verify_draft(
    tag: str, release_id: int, plan_sha256: str, context: PrepareContext,
) -> TransitionResult:
    """Reconstruct and verify the plan from canonical state and downloaded assets."""
    return _verify_release_state(tag, release_id, plan_sha256, context).result


def _verify_release_state(
    tag: str, release_id: int, plan_sha256: str, context: PrepareContext,
) -> _VerifiedRelease:
    """Return the exact Release projection and assets that passed canonical verification."""
    if type(release_id) is not int or release_id <= 0:
        raise TransitionError("Release ID must be a positive numeric ID")
    if not isinstance(plan_sha256, str) or _DIGEST.fullmatch(plan_sha256) is None:
        raise TransitionError("release plan SHA-256 is invalid")
    authority = _formal_authority(tag, context, require_local=False, require_remote=True)
    release = _release_pair(authority, tag, release_id)
    assets, remote_assets, asset_snapshot = _download_and_verify_assets(authority, release)
    remote = authority.context.git.remote_tag_state(tag)
    plan = _release_plan(
        authority.context.policy, tag, remote, authority.intent, assets,
    )
    run = _safe_ci(authority.context, authority.intent)
    document = _plan_document(plan, authority.intent, run, authority.context.policy)
    digest = hashlib.sha256(canonical_json(document)).hexdigest()
    if digest != plan_sha256:
        raise TransitionError("reconstructed release plan digest does not match caller input")
    _verify_release_metadata(release, document, digest, allow_published=True)
    _verify_latest_projection(authority, release, document)
    status = "draft-verified" if release.draft else "already-published"
    result = TransitionResult(
        status, digest, release.id, release.html_url, remote_assets,
    )
    return _VerifiedRelease(
        result, authority, release, _release_without_draft(release), asset_snapshot,
    )


def publish_draft(
    tag: str,
    release_id: int,
    plan_sha256: str,
    context: PrepareContext,
    *,
    actions_environment: Mapping[str, str] | None = None,
) -> TransitionResult:
    """Publish exact policy fields, then detect and reconcile any concurrent drift."""
    environment = os.environ if actions_environment is None else actions_environment
    if (
        environment.get("GITHUB_ACTIONS") != "true"
        or environment.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
    ):
        raise TransitionError("Draft publication requires Actions workflow_dispatch")

    initial = _verify_release_state(tag, release_id, plan_sha256, context)
    if not initial.release.draft:
        return replace(initial.result, status="already-published")
    _require_releasable(initial.authority, "Draft publication")
    before = _verify_release_state(tag, release_id, plan_sha256, context)
    if initial.release_snapshot != before.release_snapshot:
        raise TransitionError("GitHub Release metadata changed before publication")
    if initial.asset_snapshot != before.asset_snapshot:
        raise TransitionError("GitHub Release assets changed before publication")
    if not before.release.draft:
        raise TransitionError("GitHub Release changed from Draft before publication")
    mutation_authority = _formal_authority(
        tag, context, require_local=False, require_remote=True,
    )
    _require_releasable(mutation_authority, "Draft publication")
    prerelease, make_latest = _publication_fields(mutation_authority)

    try:
        mutation_authority.context.github.publish_release(
            mutation_authority.context.policy.repository, release_id,
            prerelease=prerelease, make_latest=make_latest,
        )
    except Exception:
        # A response can be lost after GitHub accepted the exact PATCH. Numeric-ID
        # reconciliation below is the only recovery path; publication never creates.
        pass

    after = _verify_release_state(tag, release_id, plan_sha256, context)
    if after.release.draft:
        raise TransitionError("GitHub Release publication could not be reconciled")
    if before.release_snapshot != after.release_snapshot:
        raise TransitionError("GitHub Release metadata changed during publication")
    if before.asset_snapshot != after.asset_snapshot:
        raise TransitionError("GitHub Release assets changed during publication")
    expected_url = _published_html_url(
        mutation_authority.context.policy.repository, tag,
    )
    if after.release.html_url != expected_url:
        raise TransitionError("GitHub Release html_url is not the exact published tag URL")
    return replace(after.result, status="published")


def marker_for_plan(document: dict[str, object], digest: str) -> str:
    """Return the one canonical, machine-readable Release body marker."""
    if _DIGEST.fullmatch(digest) is None:
        raise TransitionError("release plan marker digest is invalid")
    try:
        summary = {
            "schema": _MARKER_SCHEMA,
            "plan_schema": document["schema"],
            "plan_sha256": digest,
            "tag": document["tag"],
            "tag_object": document["tag_object"],
            "target_revision": document["target_revision"],
            "intent": {
                key: document[key] for key in ("kind", "identity", "profile")
            },
        }
        if "channel" in document:
            summary["intent"]["channel"] = document["channel"]
    except (KeyError, TypeError):
        raise TransitionError("release plan marker input is invalid") from None
    payload = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"<!-- {_MARKER_SCHEMA} {payload} -->"


def _formal_authority(
    tag: str,
    context: PrepareContext,
    *,
    require_local: bool,
    require_remote: bool,
) -> _Authority:
    try:
        policy, ledger, _ = _load_canonical_authority(context)
        resolved = replace(context, policy=policy, ledger=ledger, authority_reader=None)
        identity = classify_tag(tag, policy)
        intent = ledger.intent_for_tag(tag)
        if intent is None or intent.kind is not identity.kind:
            raise TransitionError("release tag is not authorized by the canonical intent ledger")
        if intent.disposition not in (Disposition.RELEASABLE, Disposition.PUBLISHED):
            raise TransitionError("release intent is not releasable or published")
        if any(exception.tag == tag for exception in ledger.historical_exceptions):
            raise TransitionError("historical exception cannot authorize a transition")
        _verify_key_roles(resolved, intent)
        if not resolved.git.is_main_ancestor(intent.target_revision):
            raise TransitionError("release target does not have canonical main ancestry")
        _safe_ci(resolved, intent)
        with resolved.git.detached_worktree(intent.target_revision) as worktree:
            try:
                resolved.git.validate_release_target(Path(worktree), intent)
            except Exception:
                raise TransitionError("exact release target identity or support metadata is invalid") from None
            if intent.kind.value == "product":
                _verify_product_proof(resolved, Path(worktree), intent)
        local = resolved.git.local_tag_state(tag) if require_local else None
        if require_local and (local is None or not _matching_tag(
            local, intent.target_revision, resolved.tag_signer_fingerprint,
        )):
            raise TransitionError("local signed tag does not match the canonical intent")
        remote = resolved.git.remote_tag_state(tag)
        if require_remote and (remote is None or not _matching_tag(
            remote, intent.target_revision, resolved.tag_signer_fingerprint,
        )):
            raise TransitionError("freshly fetched remote tag is absent or invalid")
        return _Authority(resolved, intent, remote if require_remote else local)
    except TransitionError:
        raise
    except Exception:
        raise TransitionError("canonical release authority could not be verified") from None


def _safe_ci(context: PrepareContext, intent: ReleaseIntent):
    try:
        return _verify_ci(context, intent)
    except Exception:
        raise TransitionError("canonical merged-main CI evidence is invalid") from None


def _load_prepared(authority: _Authority) -> tuple[dict[str, object], str, tuple[AssetBuild, ...]]:
    identity = classify_tag(authority.intent.tag, authority.context.policy)
    output = authority.context.repo_root / "build/release" / identity.output_name
    if not output.is_dir() or output.is_symlink():
        raise TransitionError("verified local release output is unavailable")
    plan_path, digest_path, assets_root = (
        output / "release-plan.json", output / "release-plan.sha256", output / "assets",
    )
    try:
        raw = plan_path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
        digest = digest_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise TransitionError("verified local release plan is unavailable") from None
    if not isinstance(document, dict) or raw != canonical_json(document):
        raise TransitionError("local release plan is not canonical JSON")
    computed = hashlib.sha256(raw).hexdigest()
    if digest != computed + "\n":
        raise TransitionError("local release plan digest does not match canonical bytes")
    asset_documents = document.get("assets")
    if not isinstance(asset_documents, list) or not assets_root.is_dir() or assets_root.is_symlink():
        raise TransitionError("local release asset inventory is invalid")
    builds: list[AssetBuild] = []
    declared_names: set[str] = set()
    for item in asset_documents:
        if not isinstance(item, dict) or set(item) != {"name", "bytes", "sha256"}:
            raise TransitionError("local release asset inventory is invalid")
        name, size, sha256 = item["name"], item["bytes"], item["sha256"]
        if not isinstance(name, str) or name in declared_names:
            raise TransitionError("local release asset inventory is invalid")
        path = assets_root / name
        try:
            payload = path.read_bytes()
        except OSError:
            raise TransitionError("local release asset is unavailable") from None
        if path.is_symlink() or type(size) is not int or size != len(payload) or sha256 != hashlib.sha256(payload).hexdigest():
            raise TransitionError("local release asset digest does not match plan")
        declared_names.add(name)
        builds.append(AssetBuild(path, name, size, sha256))
    actual_names = {path.name for path in assets_root.iterdir() if path.is_file() and not path.is_symlink()}
    if actual_names != declared_names or any(path.is_dir() or path.is_symlink() for path in assets_root.iterdir()):
        raise TransitionError("local release asset inventory contains undeclared entries")
    verified = _verify_profile(authority, tuple(builds), assets_root)
    plan = _release_plan(
        authority.context.policy, authority.intent.tag,
        authority.context.git.local_tag_state(authority.intent.tag), authority.intent, verified,
    )
    expected = _plan_document(
        plan, authority.intent, _safe_ci(authority.context, authority.intent), authority.context.policy,
    )
    if document != expected:
        raise TransitionError("local release plan does not reconcile with canonical authority")
    return document, computed, verified


def _verify_profile(
    authority: _Authority, assets: tuple[AssetBuild, ...], assets_root: Path,
) -> tuple[AssetBuild, ...]:
    try:
        verified = _verify_profile_assets(authority.intent, ProfileBuild(assets))
        with authority.context.git.detached_worktree(authority.intent.target_revision) as worktree:
            authority.context.profile_verifier(
                authority.intent.profile, Path(worktree), assets_root, authority.intent, verified,
            )
        return verified
    except Exception:
        raise TransitionError("release profile assets failed verification") from None


def _assert_plan_tag(document: dict[str, object], tag_state: object, intent: ReleaseIntent) -> None:
    if (
        tag_state is None or document.get("tag") != intent.tag
        or document.get("tag_object") != tag_state.object_id
        or document.get("target_revision") != tag_state.target_revision
    ):
        raise TransitionError("release plan does not match the exact tag object and target")


def _release_body(root: Path, document: dict[str, object], digest: str) -> str:
    identity = str(document["tag"]).replace("/", "%2F")
    path = root / "build/release" / identity / "release-notes.md"
    try:
        notes = path.read_text(encoding="utf-8").rstrip()
    except (OSError, UnicodeDecodeError):
        raise TransitionError("local release notes are unavailable") from None
    if not notes:
        raise TransitionError("local release notes are empty")
    return f"{notes}\n\n{marker_for_plan(document, digest)}"


def _release_fields(document: dict[str, object]) -> dict[str, object]:
    release = document.get("release")
    if not isinstance(release, dict):
        raise TransitionError("release plan metadata is invalid")
    expected = {"draft", "prerelease", "make_latest", "name"}
    if set(release) != expected:
        raise TransitionError("release plan metadata is invalid")
    if (
        release["draft"] is not True or not isinstance(release["prerelease"], bool)
        or not isinstance(release["make_latest"], bool)
        or not isinstance(release["name"], str) or not release["name"]
    ):
        raise TransitionError("release plan metadata is invalid")
    return release


def _release_by_tag(authority: _Authority, tag: str) -> GitHubRelease | None:
    try:
        releases = authority.context.github.list_releases(
            authority.context.policy.repository,
        )
    except Exception:
        raise TransitionError("GitHub Release lookup is unavailable") from None
    matches = [release for release in releases if release.tag_name == tag]
    if len(matches) > 1:
        raise TransitionError("GitHub Release lookup is ambiguous")
    return matches[0] if matches else None


def _require_releasable(authority: _Authority, operation: str) -> None:
    if authority.intent.disposition is not Disposition.RELEASABLE:
        raise TransitionError(
            f"published release intent is read-only and cannot authorize {operation}"
        )


def _publication_fields(authority: _Authority) -> tuple[bool, bool]:
    if authority.intent.channel is None:
        return False, False
    return authority.context.policy.channel_release(
        authority.intent.channel, authority.intent.make_latest,
    )


def _verify_latest_projection(
    authority: _Authority, release: GitHubRelease, document: dict[str, object],
) -> None:
    fields = _release_fields(document)
    try:
        latest = authority.context.github.get_latest_release(
            authority.context.policy.repository,
        )
    except Exception:
        raise TransitionError("authoritative latest Release projection is unavailable") from None
    expected = fields["make_latest"]
    if release.draft:
        if latest is not None and latest.id == release.id:
            raise TransitionError("authoritative latest Release projection identifies a Draft")
        return
    if (expected is True and (latest is None or latest.id != release.id)) or (
        expected is False and latest is not None and latest.id == release.id
    ):
        raise TransitionError("authoritative latest Release projection conflicts with release plan")


def _release_pair(
    authority: _Authority, tag: str, release_id: int,
) -> GitHubRelease:
    try:
        by_id = authority.context.github.get_release(
            authority.context.policy.repository, release_id,
        )
        by_tag = _release_by_tag(authority, tag)
    except Exception:
        raise TransitionError("GitHub Release projection is unavailable") from None
    if (
        by_id is None or by_tag is None or by_id.id != by_tag.id
        or _release_projection(by_id) != _release_projection(by_tag)
    ):
        raise TransitionError("GitHub Release numeric ID and tag do not identify one Release")
    return by_id


def _release_projection(release: GitHubRelease) -> tuple[object, ...]:
    return (_release_without_draft(release), release.draft, release.html_url)


def _release_without_draft(release: GitHubRelease) -> tuple[object, ...]:
    # html_url is not draft-invariant: publication rewrites the untagged draft URL.
    return (
        release.id, release.tag_name, release.target_commitish,
        release.name, release.body,
        release.prerelease, release.make_latest,
        release.upload_url,
    )


def _published_html_url(repository: str, tag: str) -> str:
    return f"https://github.com/{repository}/releases/tag/{tag}"


def _verify_release_metadata(
    release: GitHubRelease, document: dict[str, object], digest: str, *, allow_published: bool,
) -> None:
    fields = _release_fields(document)
    if (
        release.tag_name != document.get("tag") or release.name != fields["name"]
        or release.prerelease is not fields["prerelease"]
        or (release.make_latest is not None and release.make_latest is not fields["make_latest"])
        or (not allow_published and not release.draft)
    ):
        raise TransitionError("GitHub Release metadata conflicts with the release plan")
    expected_marker = marker_for_plan(document, digest)
    markers = _MARKER_PATTERN.findall(release.body)
    if len(markers) != 1 or markers[0][0] != _MARKER_SCHEMA or markers[0][1] != expected_marker.split(" ", 2)[2][:-4]:
        raise TransitionError("GitHub Release plan marker is absent or invalid")
    if release.body.count(_MARKER_SCHEMA) != 2:
        # The schema appears once as marker label and once inside its canonical JSON.
        raise TransitionError("GitHub Release plan marker is duplicated or malformed")


def _resume_assets(
    authority: _Authority,
    release: GitHubRelease,
    document: dict[str, object],
    local_assets: tuple[AssetBuild, ...],
) -> None:
    _require_releasable(authority, "asset upload")
    expected = {asset.name: asset for asset in local_assets}
    existing = _asset_map(authority, release)
    if not set(existing).issubset(expected):
        raise TransitionError("GitHub Release asset inventory contains undeclared assets")
    for name, remote in existing.items():
        _compare_download(authority, release.id, remote, expected[name])
    for name, local in expected.items():
        if name in existing:
            continue
        payload = local.path.read_bytes()
        try:
            authority.context.github.upload_release_asset(
                authority.context.policy.repository, release.id, release.upload_url, name, payload,
            )
        except Exception:
            reconciled = _asset_map(authority, release)
            candidates = [asset for asset_name, asset in reconciled.items() if asset_name == name]
            if len(candidates) != 1:
                raise TransitionError("GitHub asset upload is uncertain and did not reconcile") from None
            _compare_download(authority, release.id, candidates[0], local)


def _asset_map(authority: _Authority, release: GitHubRelease) -> dict[str, GitHubAsset]:
    try:
        assets = authority.context.github.list_release_assets(
            authority.context.policy.repository, release.id,
        )
    except Exception:
        raise TransitionError("GitHub Release asset inventory is unavailable") from None
    by_name: dict[str, GitHubAsset] = {}
    identifiers: set[int] = set()
    for asset in assets:
        if asset.name in by_name or asset.id in identifiers:
            raise TransitionError("GitHub Release asset inventory is ambiguous")
        by_name[asset.name] = asset
        identifiers.add(asset.id)
    return by_name


def _compare_download(
    authority: _Authority, release_id: int, remote: GitHubAsset, expected: AssetBuild,
) -> None:
    try:
        payload = authority.context.github.download_asset(
            authority.context.policy.repository, release_id, remote,
        )
    except Exception:
        raise TransitionError("GitHub Release asset download is unavailable") from None
    if remote.size != len(payload) or expected.bytes != len(payload) or hashlib.sha256(payload).hexdigest() != expected.sha256:
        raise TransitionError("GitHub Release asset digest conflicts with the release plan")


def _download_and_verify_assets(
    authority: _Authority, release: GitHubRelease,
) -> tuple[
    tuple[AssetBuild, ...],
    tuple[GitHubAsset, ...],
    tuple[tuple[object, ...], ...],
]:
    assets = _asset_map(authority, release)
    with tempfile.TemporaryDirectory(prefix="lmdj-release-download-") as directory:
        root = Path(directory)
        builds: list[AssetBuild] = []
        remote_assets: list[GitHubAsset] = []
        snapshots: list[tuple[object, ...]] = []
        for name in sorted(assets):
            asset = assets[name]
            try:
                payload = authority.context.github.download_asset(
                    authority.context.policy.repository, release.id, asset,
                )
            except Exception:
                raise TransitionError("GitHub Release asset download is unavailable") from None
            if asset.size != len(payload):
                raise TransitionError("GitHub Release asset size does not match downloaded bytes")
            sha256 = hashlib.sha256(payload).hexdigest()
            path = root / name
            path.write_bytes(payload)
            builds.append(AssetBuild(path, name, len(payload), sha256))
            remote_assets.append(asset)
            snapshots.append((
                asset.id, asset.name, asset.label, asset.content_type,
                asset.state, asset.size, sha256,
                asset.api_url, asset.browser_download_url, asset.release_id,
            ))
        verified = _verify_profile(authority, tuple(builds), root)
        return verified, tuple(remote_assets), tuple(snapshots)
