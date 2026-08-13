#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.release.openpgp import OpenPgpError, OpenPgpVerifier


@dataclass(frozen=True)
class StagedBundle:
    dist_root: Path
    product_build: str
    host_version: str
    archive_sha256: str


class BundleError(RuntimeError):
    pass


class UsageError(RuntimeError):
    pass


class UsageParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"release bundle usage error: {message}", file=sys.stderr)
        raise UsageError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_detached_checksum(path: Path, expected_name: str) -> str:
    try:
        fields = path.read_text(encoding="utf-8").strip().split()
    except (OSError, UnicodeDecodeError) as error:
        raise BundleError("release checksum record is invalid") from error
    if len(fields) != 2 or fields[1].removeprefix("*") != expected_name:
        raise BundleError("release checksum record is invalid")
    digest = fields[0].lower()
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise BundleError("release checksum digest is invalid")
    return digest


def verify_detached_checksum_signature(
    checksum_path: Path,
    signature_path: Path,
    checksum_public_key_path: Path,
    trusted_checksum_fingerprint: str,
    *,
    gpg_program: str = "gpg",
) -> None:
    """Verify a checksum signature in a keyring containing only its role key."""
    fingerprint = trusted_checksum_fingerprint.upper()
    if re.fullmatch(r"[0-9A-F]{40}", fingerprint) is None:
        raise BundleError("trusted checksum signing key fingerprint is invalid")
    try:
        signature_text = signature_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as error:
        raise BundleError("release checksum signature is invalid") from error
    if not signature_text.startswith("-----BEGIN PGP SIGNATURE-----\n"):
        raise BundleError("release checksum signature is not armored")
    with tempfile.TemporaryDirectory(prefix=".lmdj-checksum-signature-") as directory:
        home = Path(directory)
        home.chmod(0o700)
        try:
            verifier = OpenPgpVerifier(gpg_program=gpg_program)
            verifier.import_public_key(home, checksum_public_key_path, fingerprint)
            verifier.verify_detached(home, signature_path, checksum_path, fingerprint)
        except OpenPgpError as error:
            raise BundleError("release checksum signature verification failed") from error


def canonical_json(bundle: StagedBundle) -> str:
    return json.dumps(
        {
            "archive_sha256": bundle.archive_sha256,
            "dist_root": str(bundle.dist_root),
            "host_version": bundle.host_version,
            "product_build": bundle.product_build,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def normalized_member_path(info: zipfile.ZipInfo) -> PurePosixPath:
    name = info.filename
    if not name or "\\" in name or name.startswith("/"):
        raise BundleError("unsafe release archive entry")
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise BundleError("unsafe release archive entry")
    mode = info.external_attr >> 16
    kind = stat.S_IFMT(mode)
    is_directory = info.is_dir()
    if is_directory:
        if kind not in {0, stat.S_IFDIR}:
            raise BundleError("unsafe release archive entry")
    elif kind not in {0, stat.S_IFREG}:
        raise BundleError("unsafe release archive entry")
    return path


def validate_archive_entries(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    entries: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    seen: set[PurePosixPath] = set()
    for info in archive.infolist():
        path = normalized_member_path(info)
        if path in seen:
            raise BundleError("duplicate release archive entry")
        seen.add(path)
        if path.parts[0] != "dist":
            raise BundleError("release archive must contain exactly one dist tree")
        entries.append((info, path))
    if not entries or not any(path.parts[0] == "dist" for _, path in entries):
        raise BundleError("release archive must contain exactly one dist tree")
    return entries


def default_verifier(dist_root: Path, repo_root: Path) -> None:
    package_path = repo_root / "apps/web-runtime-host/tools/package.py"
    if not package_path.is_file() or package_path.is_symlink():
        raise RuntimeError("distribution verifier is unavailable")
    spec = importlib.util.spec_from_file_location("lmdj_web_package", package_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("distribution verifier cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError, SyntaxError) as error:
        raise RuntimeError("distribution verifier cannot be loaded") from error
    verify_distribution = getattr(module, "verify_distribution", None)
    if not callable(verify_distribution):
        raise RuntimeError("distribution verifier cannot be loaded")
    verify_distribution(dist_root, repo_root)


def read_manifest_identity(dist_root: Path) -> tuple[str, str]:
    try:
        manifest = json.loads(
            (dist_root / "host-manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError("release bundle manifest is invalid") from error
    if not isinstance(manifest, dict):
        raise BundleError("release bundle manifest is invalid")
    product_build = manifest.get("product_build")
    host_version = manifest.get("host_version")
    if not isinstance(product_build, str) or not isinstance(host_version, str):
        raise BundleError("release bundle manifest is invalid")
    return product_build, host_version


def stage_release_bundle(
    *,
    repo_root: Path,
    archive_path: Path,
    checksum_path: Path,
    signature_path: Path,
    checksum_public_key_path: Path,
    trusted_checksum_fingerprint: str,
    output_root: Path,
    expected_product_build: str,
    expected_host_version: str,
    verifier: Callable[[Path, Path], None] | None = None,
    checksum_authorizer: Callable[[Path, Path, Path, str], None] | None = None,
    gpg_program: str = "gpg",
) -> StagedBundle:
    """Validate and atomically stage exactly one dist/ tree."""
    try:
        repo_root = repo_root.expanduser().resolve(strict=True)
        archive_path = archive_path.expanduser().resolve(strict=True)
        checksum_path = checksum_path.expanduser().resolve(strict=True)
        signature_path = signature_path.expanduser().resolve(strict=True)
        checksum_public_key_path = checksum_public_key_path.expanduser().resolve(strict=True)
        requested_output = output_root.expanduser()
        if not requested_output.is_absolute():
            requested_output = Path.cwd() / requested_output
        output_parent = requested_output.parent.resolve(strict=True)
        output_root = output_parent / requested_output.name
    except OSError as error:
        raise BundleError("release bundle input is unavailable") from error
    if (
        not repo_root.is_dir()
        or not archive_path.is_file()
        or not checksum_path.is_file()
        or not signature_path.is_file()
        or not checksum_public_key_path.is_file()
    ):
        raise BundleError("release bundle input is unavailable")
    if output_root.exists() or output_root.is_symlink():
        raise BundleError("release bundle output root must be absent")

    if signature_path.name != f"{checksum_path.name}.asc":
        raise BundleError("release checksum signature name is not canonical")
    selected_authorizer = checksum_authorizer or (
        lambda checksum, signature, key, fingerprint: verify_detached_checksum_signature(
            checksum,
            signature,
            key,
            fingerprint,
            gpg_program=gpg_program,
        )
    )
    try:
        selected_authorizer(
            checksum_path,
            signature_path,
            checksum_public_key_path,
            trusted_checksum_fingerprint,
        )
    except BundleError:
        raise
    except Exception:
        raise BundleError("release checksum signature verification failed") from None
    expected_digest = parse_detached_checksum(checksum_path, archive_path.name)
    actual_digest = sha256_file(archive_path)
    if actual_digest != expected_digest:
        raise BundleError("release archive checksum mismatch")

    staged = Path(tempfile.mkdtemp(prefix=".lmdj-release-bundle-", dir=output_parent))
    try:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                entries = validate_archive_entries(archive)
                for info, relative in entries:
                    destination = staged / relative
                    if info.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("xb") as target:
                        shutil.copyfileobj(source, target)
        except BundleError:
            raise
        except (
            OSError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
        ) as error:
            raise BundleError("release archive is invalid") from error

        dist_root = staged / "dist"
        if not dist_root.is_dir() or dist_root.is_symlink():
            raise BundleError("release archive must contain exactly one dist tree")
        selected_verifier = verifier or default_verifier
        try:
            selected_verifier(dist_root, repo_root)
        except Exception as error:
            raise BundleError("release bundle verification failed") from error
        product_build, host_version = read_manifest_identity(dist_root)
        if product_build != expected_product_build:
            raise BundleError("release bundle Product Build mismatch")
        if host_version != expected_host_version:
            raise BundleError("release bundle Host version mismatch")
        os.replace(staged, output_root)
        bundle = StagedBundle(
            dist_root=output_root / "dist",
            product_build=product_build,
            host_version=host_version,
            archive_sha256=actual_digest,
        )
        return bundle
    finally:
        if staged.exists() and not staged.is_symlink():
            shutil.rmtree(staged)


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = UsageParser(description="Validate and stage a released Web Runtime Host bundle")
    commands = parser.add_subparsers(
        dest="command", required=True, parser_class=UsageParser
    )
    stage = commands.add_parser("stage")
    stage.add_argument("--repo-root", required=True, type=Path)
    stage.add_argument("--archive", required=True, type=Path)
    stage.add_argument("--checksum", required=True, type=Path)
    stage.add_argument("--checksum-signature", required=True, type=Path)
    stage.add_argument("--checksum-public-key", required=True, type=Path)
    stage.add_argument("--trusted-checksum-fingerprint", required=True)
    stage.add_argument("--gpg-program", default="gpg")
    stage.add_argument("--output-root", required=True, type=Path)
    stage.add_argument("--expected-product-build", required=True)
    stage.add_argument("--expected-host-version", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        options = parse_arguments(arguments)
        bundle = stage_release_bundle(
            repo_root=options.repo_root,
            archive_path=options.archive,
            checksum_path=options.checksum,
            signature_path=options.checksum_signature,
            checksum_public_key_path=options.checksum_public_key,
            trusted_checksum_fingerprint=options.trusted_checksum_fingerprint,
            output_root=options.output_root,
            expected_product_build=options.expected_product_build,
            expected_host_version=options.expected_host_version,
            gpg_program=options.gpg_program,
        )
    except UsageError:
        return 64
    except (BundleError, OSError) as error:
        print(f"Web Runtime deployment bundle error: {error}", file=sys.stderr)
        return 2
    print(canonical_json(bundle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
