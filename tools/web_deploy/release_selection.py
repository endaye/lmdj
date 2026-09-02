"""Fail-closed Host payload selection from a published Product Release."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping


CANONICAL_REPOSITORY = "endaye/lmdj"
CANONICAL_RELEASE_PREFIX = (
    f"https://github.com/{CANONICAL_REPOSITORY}/releases/tag/"
)
PRODUCT_BUILD = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
)
SEMVER = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
)
HOST_IDS = frozenset(("creator-web", "web-runtime-host"))


class ReleaseSelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class HostAssetSelection:
    archive: str
    checksum: str
    signature: str
    release_url: str
    asset_names: tuple[str, ...]


def _asset_triplet(host_id: str, host_version: str, product_build: str) -> tuple[str, ...]:
    archive = f"lmdj-{host_id}-{host_version}-product-{product_build}.zip"
    return archive, f"{archive}.sha256", f"{archive}.sha256.asc"


def _validate_dual_inventory(
    names: tuple[str, ...],
    product_build: str,
) -> None:
    archives: dict[str, str] = {}
    pattern = re.compile(
        r"lmdj-(creator-web|web-runtime-host)-("
        + SEMVER.pattern
        + r")-product-"
        + re.escape(product_build)
        + r"\.zip"
    )
    for name in names:
        match = pattern.fullmatch(name)
        if match is not None:
            if match.group(1) in archives:
                raise ReleaseSelectionError(
                    "GitHub Release Host asset inventory is invalid"
                )
            archives[match.group(1)] = match.group(2)
    if set(archives) != HOST_IDS:
        raise ReleaseSelectionError(
            "GitHub Release Host asset inventory is invalid"
        )
    expected = {
        name
        for identity, version in archives.items()
        for name in _asset_triplet(identity, version, product_build)
    }
    if set(names) != expected:
        raise ReleaseSelectionError(
            "GitHub Release Host asset inventory is invalid"
        )


def select_host_assets(
    release: Mapping[str, object],
    *,
    host_id: str,
    host_version: str,
    product_build: str,
) -> HostAssetSelection:
    if host_id not in HOST_IDS:
        raise ReleaseSelectionError("unknown Web Host identity")
    if SEMVER.fullmatch(host_version) is None:
        raise ReleaseSelectionError("Web Host version is invalid")
    if PRODUCT_BUILD.fullmatch(product_build) is None:
        raise ReleaseSelectionError("Product Build is invalid")
    required = {
        "tagName",
        "isDraft",
        "isPrerelease",
        "targetCommitish",
        "assets",
        "url",
    }
    if set(release) != required:
        raise ReleaseSelectionError("GitHub Release metadata is invalid")
    tag = f"lmdj-v{product_build}"
    if release["tagName"] != tag:
        raise ReleaseSelectionError("GitHub Release tag is invalid")
    if release["isDraft"] is not False:
        raise ReleaseSelectionError(
            "GitHub Release is not the exact published Product tag"
        )
    if release["isPrerelease"] is not True:
        raise ReleaseSelectionError(
            "GitHub Release is not a canary prerelease"
        )
    target = release["targetCommitish"]
    if (
        not isinstance(target, str)
        or not target
        or "\n" in target
        or "\r" in target
    ):
        raise ReleaseSelectionError(
            "GitHub Release target metadata is invalid"
        )
    assets = release["assets"]
    if not isinstance(assets, list) or any(
        not isinstance(asset, Mapping) for asset in assets
    ):
        raise ReleaseSelectionError(
            "GitHub Release Host asset inventory is invalid"
        )
    names = tuple(asset.get("name") for asset in assets)
    if (
        any(not isinstance(name, str) or not name for name in names)
        or len(set(names)) != len(names)
    ):
        raise ReleaseSelectionError(
            "GitHub Release Host asset inventory is invalid"
        )
    selected = _asset_triplet(host_id, host_version, product_build)
    if len(names) == 3:
        if host_id != "web-runtime-host" or set(names) != set(selected):
            raise ReleaseSelectionError(
                "GitHub Release Host asset inventory is invalid"
            )
    elif len(names) == 6:
        _validate_dual_inventory(names, product_build)
        if not set(selected).issubset(names):
            raise ReleaseSelectionError(
                "GitHub Release Host asset identity is invalid"
            )
    else:
        raise ReleaseSelectionError(
            "GitHub Release Host asset inventory is invalid"
        )
    release_url = CANONICAL_RELEASE_PREFIX + tag
    if release["url"] != release_url:
        raise ReleaseSelectionError("GitHub Release URL is invalid")
    return HostAssetSelection(
        archive=selected[0],
        checksum=selected[1],
        signature=selected[2],
        release_url=release_url,
        asset_names=names,
    )
