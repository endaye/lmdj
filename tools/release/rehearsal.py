"""Guarded test-namespace rehearsal with exact-object cleanup."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote

from .github_api import GitHubAsset, GitHubRelease


class RehearsalError(RuntimeError):
    """A rehearsal state or destructive cleanup guard did not match exactly."""


REHEARSAL_ASSET = b"LMDJ release pipeline rehearsal v1\n"
REHEARSAL_TAG_PATTERN = re.compile(
    r"release-rehearsal/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\Z",
)
_FINGERPRINT = re.compile(r"[0-9A-F]{40}\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_STATE_SCHEMA = "lmdj.release-rehearsal-state.v1"
_MARKER_SCHEMA = "lmdj.release-rehearsal-marker.v1"


@dataclass(frozen=True)
class RehearsalState:
    schema: str
    tag: str
    tag_object: str
    signer_fingerprint: str
    release_id: int | None
    asset_name: str
    asset_sha256: str


@dataclass(frozen=True)
class RehearsalContext:
    repo_root: Path
    repository: str
    git: object
    github: object
    production_fingerprints: frozenset[str] = frozenset()


def validate_rehearsal_tag(tag: str) -> str:
    if not isinstance(tag, str) or REHEARSAL_TAG_PATTERN.fullmatch(tag) is None:
        raise RehearsalError("tag is not in the exact release rehearsal namespace")
    return tag


def prepare_rehearsal(
    tag: str, context: RehearsalContext, *, product_fingerprints: set[str],
) -> RehearsalState:
    """Create an isolated ephemeral signer, deterministic asset, and local test tag."""
    validate_rehearsal_tag(tag)
    output = _output_root(context.repo_root, tag)
    if output.exists() or output.is_symlink():
        raise RehearsalError("rehearsal output already exists; reconcile its recorded state")
    try:
        if context.git.remote_tag_object(tag) is not None:
            raise RehearsalError("rehearsal remote tag already exists")
        if _release_by_tag(context, tag) is not None:
            raise RehearsalError("rehearsal Release already exists")
        context.git.fetch_authority(context.repository, "main")
        target = context.git.main_revision()
        runner = context.git.runner
    except RehearsalError:
        raise
    except Exception:
        raise RehearsalError("rehearsal preflight is unavailable") from None

    output.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".lmdj-rehearsal-", dir=output.parent))
    try:
        gpg_home = staged / "gnupg"
        gpg_home.mkdir(mode=0o700)
        runner.run([
            "gpg", "--homedir", gpg_home, "--batch", "--passphrase", "",
            "--quick-generate-key", "LMDJ Release Rehearsal <rehearsal.invalid>",
            "ed25519", "sign", "1d",
        ], cwd=context.repo_root)
        listing = runner.run([
            "gpg", "--homedir", gpg_home, "--batch", "--with-colons",
            "--list-secret-keys",
        ], cwd=context.repo_root).stdout
        signer = _one_fingerprint(listing)
        _require_test_signer(signer, product_fingerprints)
        tag_state = context.git.create_rehearsal_tag(
            tag, target, signer, f"LMDJ release rehearsal {tag}", gpg_home,
        )
        asset_name = "lmdj-release-rehearsal.txt"
        (staged / asset_name).write_bytes(REHEARSAL_ASSET)
        state = RehearsalState(
            _STATE_SCHEMA, tag, tag_state.object_id, signer, None, asset_name,
            hashlib.sha256(REHEARSAL_ASSET).hexdigest(),
        )
        _write_state(staged / "state.json", state)
        os.replace(staged, output)
        return state
    except RehearsalError:
        raise
    except Exception:
        raise RehearsalError("rehearsal preparation failed") from None
    finally:
        if staged.exists() and not staged.is_symlink():
            shutil.rmtree(staged)


def push_rehearsal_tag(
    tag: str, context: RehearsalContext, *, product_fingerprints: set[str],
) -> RehearsalState:
    state = load_rehearsal_state(tag, context.repo_root)
    _require_test_signer(state.signer_fingerprint, product_fingerprints)
    gpg_home = _output_root(context.repo_root, tag) / "gnupg"
    try:
        local = context.git.local_rehearsal_tag_state(tag, gpg_home)
        if (
            local is None or local.object_id != state.tag_object
            or local.signer_fingerprint != state.signer_fingerprint
        ):
            raise RehearsalError("local rehearsal tag does not match recorded state")
        remote = context.git.remote_tag_object(tag)
        if remote is not None and remote != state.tag_object:
            raise RehearsalError("remote rehearsal tag object conflicts with recorded state")
        if remote is None:
            try:
                context.git.push_tag(tag)
            except Exception:
                pass
        if context.git.remote_tag_object(tag) != state.tag_object:
            raise RehearsalError("rehearsal tag push did not reconcile")
        return state
    except RehearsalError:
        raise
    except Exception:
        raise RehearsalError("rehearsal tag transition failed") from None


def create_rehearsal_draft(
    state: RehearsalState,
    context: RehearsalContext,
    *,
    product_fingerprints: set[str] | None = None,
) -> RehearsalState:
    """Create or reconcile one marked Draft and one deterministic small asset."""
    _validate_state(state)
    forbidden = set(context.production_fingerprints) | (product_fingerprints or set())
    _require_test_signer(state.signer_fingerprint, forbidden)
    try:
        if context.git.remote_tag_object(state.tag) != state.tag_object:
            raise RehearsalError("remote rehearsal tag does not match recorded object")
        release = _release_by_tag(context, state.tag)
        if release is None:
            try:
                release = context.github.create_draft_release(
                    context.repository,
                    tag=state.tag,
                    name=f"LMDJ release rehearsal {state.tag}",
                    body=rehearsal_marker(state),
                    prerelease=True,
                    make_latest=False,
                )
            except Exception:
                release = _release_by_tag(context, state.tag)
                if release is None:
                    raise RehearsalError("rehearsal Draft creation did not reconcile")
        if state.release_id is not None and release.id != state.release_id:
            raise RehearsalError("rehearsal Draft ID conflicts with recorded state")
        selected = replace(state, release_id=release.id)
        _validate_release(selected, release, context, require_asset=False)
        if _output_root(context.repo_root, state.tag).is_dir():
            # Persist exact numeric ownership before upload. A failed response or
            # later verification must still leave cleanup a safe retry handle.
            _write_state(_state_path(context.repo_root, state.tag), selected)
        assets = _assets(context, release.id)
        if not assets:
            try:
                context.github.upload_release_asset(
                    context.repository, release.id, release.upload_url,
                    state.asset_name, REHEARSAL_ASSET,
                )
            except Exception:
                pass
            assets = _assets(context, release.id)
        if len(assets) != 1:
            raise RehearsalError("rehearsal Draft asset inventory is not exact")
        _verify_asset(selected, release.id, assets[0], context)
        if _output_root(context.repo_root, state.tag).is_dir():
            _write_state(_state_path(context.repo_root, state.tag), selected)
        return selected
    except RehearsalError:
        raise
    except Exception:
        raise RehearsalError("rehearsal Draft transition failed") from None


def cleanup_rehearsal(state: RehearsalState, context: RehearsalContext) -> None:
    """Delete only the exact recorded Draft and tag, with pre/postcondition proofs."""
    _validate_state(state)
    _require_test_signer(state.signer_fingerprint, set(context.production_fingerprints))
    if state.release_id is None:
        raise RehearsalError("rehearsal cleanup requires an exact numeric Draft ID")
    try:
        release = context.github.get_release(context.repository, state.release_id)
        by_tag = _release_by_tag(context, state.tag)
        if (release is None) != (by_tag is None):
            raise RehearsalError("rehearsal Draft ID and tag do not identify one object")
        if release is not None and by_tag is not None:
            if release.id != by_tag.id:
                raise RehearsalError("rehearsal Draft ID and tag do not identify one object")
            _validate_release(state, release, context, require_asset=True)
        remote_tag = context.git.remote_tag_object(state.tag)
        if remote_tag not in (None, state.tag_object):
            raise RehearsalError("rehearsal remote tag object changed")

        if release is not None:
            context.github.delete_release(context.repository, state.release_id)
            if (
                context.github.get_release(context.repository, state.release_id) is not None
                or _release_by_tag(context, state.tag) is not None
            ):
                raise RehearsalError("rehearsal Draft deletion was not observed")
            if context.git.remote_tag_object(state.tag) != state.tag_object:
                raise RehearsalError("rehearsal tag changed after Draft deletion")
        if remote_tag is not None:
            context.git.delete_remote_tag(state.tag, state.tag_object)
        if context.git.remote_tag_object(state.tag) is not None:
            raise RehearsalError("rehearsal tag deletion was not observed")
        gpg_home = _output_root(context.repo_root, state.tag) / "gnupg"
        if gpg_home.exists():
            if gpg_home.is_symlink() or not gpg_home.is_dir():
                raise RehearsalError("ephemeral rehearsal keyring path is unsafe")
            shutil.rmtree(gpg_home)
    except RehearsalError:
        raise
    except Exception:
        raise RehearsalError("rehearsal cleanup failed") from None


def rehearsal_marker(state: RehearsalState) -> str:
    _validate_state(state)
    payload = json.dumps({
        "schema": _MARKER_SCHEMA,
        "tag": state.tag,
        "tag_object": state.tag_object,
        "signer_fingerprint": state.signer_fingerprint,
        "asset": {"name": state.asset_name, "sha256": state.asset_sha256},
    }, sort_keys=True, separators=(",", ":"))
    return f"<!-- {_MARKER_SCHEMA} {payload} -->"


def load_rehearsal_state(tag: str, root: Path) -> RehearsalState:
    validate_rehearsal_tag(tag)
    try:
        document = json.loads(_state_path(root, tag).read_text(encoding="utf-8"))
        if not isinstance(document, dict) or set(document) != {
            "schema", "tag", "tag_object", "signer_fingerprint", "release_id",
            "asset_name", "asset_sha256",
        }:
            raise ValueError
        state = RehearsalState(**document)
        _validate_state(state)
        if state.tag != tag:
            raise ValueError
        return state
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise RehearsalError("rehearsal state is unavailable or invalid") from None


def _validate_release(
    state: RehearsalState,
    release: GitHubRelease,
    context: RehearsalContext,
    *,
    require_asset: bool,
) -> None:
    if not release.draft:
        raise RehearsalError("published Release is never a rehearsal cleanup target")
    if (
        release.id != state.release_id or release.tag_name != state.tag
        or release.name != f"LMDJ release rehearsal {state.tag}"
        or release.body != rehearsal_marker(state) or not release.prerelease
        or release.make_latest is True
    ):
        raise RehearsalError("rehearsal Draft marker or metadata does not match exact state")
    if require_asset:
        assets = _assets(context, release.id)
        if len(assets) != 1:
            raise RehearsalError("rehearsal Draft asset inventory is not exact")
        _verify_asset(state, release.id, assets[0], context)


def _assets(context: RehearsalContext, release_id: int) -> list[GitHubAsset]:
    return context.github.list_release_assets(context.repository, release_id)


def _release_by_tag(context: RehearsalContext, tag: str) -> GitHubRelease | None:
    releases = context.github.list_releases(context.repository)
    matches = [release for release in releases if release.tag_name == tag]
    if len(matches) > 1:
        raise RehearsalError("rehearsal Release inventory is ambiguous")
    return matches[0] if matches else None


def _verify_asset(
    state: RehearsalState, release_id: int, asset: GitHubAsset, context: RehearsalContext,
) -> None:
    payload = context.github.download_asset(context.repository, release_id, asset)
    if (
        asset.name != state.asset_name or asset.size != len(payload)
        or hashlib.sha256(payload).hexdigest() != state.asset_sha256
    ):
        raise RehearsalError("rehearsal Draft asset does not match deterministic bytes")


def _validate_state(state: RehearsalState) -> None:
    if (
        not isinstance(state, RehearsalState) or state.schema != _STATE_SCHEMA
        or REHEARSAL_TAG_PATTERN.fullmatch(state.tag) is None
        or _SHA40.fullmatch(state.tag_object) is None
        or _FINGERPRINT.fullmatch(state.signer_fingerprint) is None
        or (state.release_id is not None and (type(state.release_id) is not int or state.release_id <= 0))
        or state.asset_name != "lmdj-release-rehearsal.txt"
        or _SHA256.fullmatch(state.asset_sha256) is None
        or state.asset_sha256 != hashlib.sha256(REHEARSAL_ASSET).hexdigest()
    ):
        raise RehearsalError("rehearsal state is invalid")


def _require_test_signer(signer: str, product_fingerprints: set[str]) -> None:
    if _FINGERPRINT.fullmatch(signer) is None or signer in product_fingerprints:
        raise RehearsalError("rehearsal requires an isolated non-Product test signer")


def _one_fingerprint(listing: str) -> str:
    fingerprints = [
        fields[9].upper() for line in listing.splitlines()
        if (fields := line.split(":"))[0] == "fpr" and len(fields) > 9
        and _FINGERPRINT.fullmatch(fields[9].upper()) is not None
    ]
    unique = list(dict.fromkeys(fingerprints))
    if len(unique) != 1:
        raise RehearsalError("ephemeral rehearsal signer projection is ambiguous")
    return unique[0]


def _output_root(root: Path, tag: str) -> Path:
    return root / "build/release-rehearsal" / quote(validate_rehearsal_tag(tag), safe="")


def _state_path(root: Path, tag: str) -> Path:
    return _output_root(root, tag) / "state.json"


def _write_state(path: Path, state: RehearsalState) -> None:
    path.write_text(
        json.dumps(asdict(state), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n",
    )
