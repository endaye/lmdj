#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Mapping


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.web_deploy.release_selection import (  # noqa: E402
    HostAssetSelection,
    ReleaseSelectionError,
    select_host_assets,
)


INITIAL_TAG = "lmdj-v1.0.15.2"
INITIAL_HOST_DIGEST = (
    "d56a7c99a3c489db068b93fcef70a254"
    "b498adf4bc65919253beccb199f3ad5a"
)
HOST_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class DeployOrchestratorError(RuntimeError):
    pass


def _secret_values() -> tuple[str, ...]:
    return tuple(
        value
        for name in ("GITHUB_TOKEN",)
        if (value := os.environ.get(name))
    )


def reject_secret_material(
    value: object, *, secrets: tuple[str, ...] | None = None, label: str
) -> None:
    selected = _secret_values() if secrets is None else tuple(secret for secret in secrets if secret)
    if not selected:
        return

    def visit(current: object) -> None:
        if isinstance(current, str):
            if any(secret in current for secret in selected):
                raise DeployOrchestratorError(f"{label} contains credential material")
            return
        if isinstance(current, Mapping):
            for key, nested in current.items():
                visit(key)
                visit(nested)
            return
        if isinstance(current, (list, tuple, set)):
            for nested in current:
                visit(nested)

    visit(value)


def parse_json_document(source: str, label: str) -> dict[str, object]:
    try:
        value = json.loads(source)
    except (TypeError, json.JSONDecodeError) as error:
        raise DeployOrchestratorError(f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise DeployOrchestratorError(f"{label} is invalid")
    reject_secret_material(value, label=label)
    return value


def read_tag_identity(root: Path, expected_product: str) -> tuple[str, str]:
    try:
        product = json.loads(
            (root / "products/lmdj/version.json").read_text(encoding="utf-8")
        )
        host = json.loads(
            (root / "apps/web-runtime-host/module.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeployOrchestratorError("tag-target identity manifests are invalid") from error
    if not isinstance(product, dict) or set(product) != {
        "contract",
        "product",
        "milestone",
        "minor",
        "build",
        "patch",
    }:
        raise DeployOrchestratorError("tag-target Product identity is invalid")
    if (
        product["contract"] != "lmdj.product-version.v1"
        or product["product"] != "lmdj"
    ):
        raise DeployOrchestratorError("tag-target Product identity is invalid")
    parts = [product[name] for name in ("milestone", "minor", "build", "patch")]
    if any(type(part) is not int or part < 0 for part in parts):
        raise DeployOrchestratorError("tag-target Product identity is invalid")
    observed_product = ".".join(str(part) for part in parts)
    if observed_product != expected_product:
        raise DeployOrchestratorError("tag-target Product Build does not match the tag")
    if (
        not isinstance(host, dict)
        or host.get("contract") != "lmdj.module.v1"
        or host.get("module") != "web-runtime-host"
        or not isinstance(host.get("version"), str)
        or HOST_PATTERN.fullmatch(host["version"]) is None
    ):
        raise DeployOrchestratorError("tag-target Host identity is invalid")
    reject_secret_material(
        (observed_product, host["version"]), label="tag-target identity"
    )
    return observed_product, host["version"]


def parse_release_metadata(
    source: str,
    *,
    tag: str,
    tag_target: str,
    product_build: str,
    host_version: str,
) -> tuple[str, str, str, str]:
    release = parse_json_document(source, "GitHub Release metadata")
    try:
        selected = select_host_assets(
            release,
            host_id="web-runtime-host",
            host_version=host_version,
            product_build=product_build,
        )
    except ReleaseSelectionError as error:
        message = str(error)
        if "asset" in message:
            message = "GitHub Release Host asset identity is invalid"
        raise DeployOrchestratorError(message) from error
    if tag != f"lmdj-v{product_build}":
        raise DeployOrchestratorError("GitHub Release tag is invalid")
    return (
        selected.archive,
        selected.checksum,
        selected.signature,
        selected.release_url,
    )


def release_asset_selection(
    source: str,
    *,
    tag: str,
    tag_target: str,
    product_build: str,
    host_version: str,
) -> HostAssetSelection:
    release = parse_json_document(source, "GitHub Release metadata")
    try:
        selection = select_host_assets(
            release,
            host_id="web-runtime-host",
            host_version=host_version,
            product_build=product_build,
        )
    except ReleaseSelectionError as error:
        message = str(error)
        if "asset" in message:
            message = "GitHub Release Host asset identity is invalid"
        raise DeployOrchestratorError(message) from error
    if tag != f"lmdj-v{product_build}":
        raise DeployOrchestratorError("GitHub Release tag is invalid")
    return selection


def validate_downloaded_assets(
    root: Path,
    archive_name: str,
    checksum_name: str,
    signature_name: str,
    expected_inventory: tuple[str, ...] | None = None,
) -> None:
    expected = sorted(
        expected_inventory
        or (archive_name, checksum_name, signature_name)
    )
    try:
        entries = list(root.iterdir())
    except OSError as error:
        raise DeployOrchestratorError(
            "downloaded GitHub Release asset inventory is invalid"
        ) from error
    actual = sorted(
        path.name for path in entries if path.is_file() and not path.is_symlink()
    )
    if actual != expected or any(path.is_dir() or path.is_symlink() for path in entries):
        raise DeployOrchestratorError(
            "downloaded GitHub Release asset inventory is invalid"
        )


def parse_staged_bundle(
    source: str,
    *,
    stage_root: Path,
    product_build: str,
    host_version: str,
    tag: str,
) -> tuple[Path, str, str, str]:
    staged = parse_json_document(source, "staged Host bundle result")
    if set(staged) != {
        "archive_sha256",
        "dist_root",
        "host_version",
        "product_build",
    }:
        raise DeployOrchestratorError("staged Host bundle result is invalid")
    try:
        resolved_stage = stage_root.resolve()
        dist_root = Path(str(staged["dist_root"])).resolve(strict=True)
    except OSError as error:
        raise DeployOrchestratorError("staged Host bundle root is invalid") from error
    if (
        dist_root != resolved_stage / "dist"
        or not dist_root.is_dir()
        or dist_root.is_symlink()
    ):
        raise DeployOrchestratorError("staged Host bundle root is invalid")
    digest = staged["archive_sha256"]
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        raise DeployOrchestratorError("staged Host archive digest is invalid")
    if (
        staged["product_build"] != product_build
        or staged["host_version"] != host_version
    ):
        raise DeployOrchestratorError("staged Host identity is invalid")
    if tag == INITIAL_TAG and digest != INITIAL_HOST_DIGEST:
        raise DeployOrchestratorError("initial Host archive SHA-256 mismatch")
    try:
        index_sha256 = hashlib.sha256((dist_root / "index.html").read_bytes()).hexdigest()
        manifest_sha256 = hashlib.sha256(
            (dist_root / "host-manifest.json").read_bytes()
        ).hexdigest()
    except OSError as error:
        raise DeployOrchestratorError("staged Host release files are unavailable") from error
    return dist_root, digest, index_sha256, manifest_sha256


def render_deploy_headers(dist_root: Path, headers_path: Path) -> bytes:
    """Append immutable cache rules for every manifest-authorized asset."""
    try:
        dist_root = dist_root.resolve(strict=True)
        headers_path = headers_path.resolve(strict=True)
        base = headers_path.read_text(encoding="utf-8")
        manifest = json.loads(
            (dist_root / "host-manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeployOrchestratorError("Host response rules are unavailable") from error
    if (
        not dist_root.is_dir()
        or dist_root.is_symlink()
        or not headers_path.is_file()
        or headers_path.is_symlink()
        or re.search(r"^/assets/\*$", base, re.MULTILINE) is not None
        or not isinstance(manifest, dict)
        or not isinstance(manifest.get("assets"), list)
        or not manifest["assets"]
    ):
        raise DeployOrchestratorError("Host response rules are invalid")
    paths: list[str] = []
    for asset in manifest["assets"]:
        path = asset.get("path") if isinstance(asset, dict) else None
        if (
            not isinstance(path, str)
            or re.fullmatch(r"assets/[A-Za-z0-9._-]+", path) is None
            or path in paths
            or not (dist_root / path).is_file()
            or (dist_root / path).is_symlink()
        ):
            raise DeployOrchestratorError("Host immutable asset inventory is invalid")
        paths.append(path)
    rendered = base.rstrip() + "\n\n"
    rendered += "\n\n".join(
        f"/{path}\n  Cache-Control: public, max-age=31536000, immutable"
        for path in paths
    )
    return (rendered + "\n").encode("utf-8")


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Web Runtime deployment orchestration")
    commands = parser.add_subparsers(dest="command", required=True)

    identity = commands.add_parser("tag-identity")
    identity.add_argument("root", type=Path)
    identity.add_argument("product_build")

    release = commands.add_parser("release-metadata")
    release.add_argument("tag")
    release.add_argument("tag_target")
    release.add_argument("product_build")
    release.add_argument("host_version")

    downloaded = commands.add_parser("downloaded-assets")
    downloaded.add_argument("root", type=Path)
    downloaded.add_argument("archive")
    downloaded.add_argument("checksum")
    downloaded.add_argument("signature")
    downloaded.add_argument("inventory", nargs="?")

    staged = commands.add_parser("staged-bundle")
    staged.add_argument("stage_root", type=Path)
    staged.add_argument("product_build")
    staged.add_argument("host_version")
    staged.add_argument("tag")
    staged.add_argument("document")

    return parser.parse_args(argv)


def run(options: argparse.Namespace) -> None:
    if options.command == "tag-identity":
        print("\t".join(read_tag_identity(options.root, options.product_build)))
        return
    if options.command == "release-metadata":
        selection = release_asset_selection(
            sys.stdin.read(),
            tag=options.tag,
            tag_target=options.tag_target,
            product_build=options.product_build,
            host_version=options.host_version,
        )
        print(
            "\t".join(
                (
                    selection.archive,
                    selection.checksum,
                    selection.signature,
                    selection.release_url,
                    ",".join(selection.asset_names),
                )
            )
        )
        return
    if options.command == "downloaded-assets":
        inventory = (
            tuple(options.inventory.split(","))
            if options.inventory is not None
            else None
        )
        validate_downloaded_assets(
            options.root,
            options.archive,
            options.checksum,
            options.signature,
            inventory,
        )
        return
    if options.command == "staged-bundle":
        dist_root, digest, index_sha256, manifest_sha256 = parse_staged_bundle(
            options.document,
            stage_root=options.stage_root,
            product_build=options.product_build,
            host_version=options.host_version,
            tag=options.tag,
        )
        print(f"{dist_root}\t{digest}\t{index_sha256}\t{manifest_sha256}")
        return
    raise AssertionError(f"unsupported command: {options.command}")


def redacted_message(error: BaseException) -> str:
    message = str(error)
    for secret in _secret_values():
        message = message.replace(secret, "[REDACTED]")
    return message


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_arguments(sys.argv[1:] if argv is None else argv)
        run(options)
    except (DeployOrchestratorError, OSError) as error:
        print(
            f"Web Runtime deployment orchestration error: {redacted_message(error)}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
