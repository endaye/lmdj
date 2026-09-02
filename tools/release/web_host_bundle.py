"""Shared deterministic archive and signed Web Host bundle verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from typing import Callable

from .openpgp import OpenPgpError, OpenPgpVerifier


@dataclass(frozen=True)
class WebHostReleaseSpec:
    host_id: str
    script: str
    dist_relative: str
    module_relative: str
    archive_prefix: str
    verifier_relative: str


@dataclass(frozen=True)
class StagedBundle:
    dist_root: Path
    product_build: str
    host_version: str
    archive_sha256: str


class BundleError(RuntimeError):
    pass


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
            verifier.import_public_key(
                home,
                checksum_public_key_path,
                fingerprint,
            )
            verifier.verify_detached(
                home,
                signature_path,
                checksum_path,
                fingerprint,
            )
        except OpenPgpError as error:
            raise BundleError(
                "release checksum signature verification failed"
            ) from error


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
    if info.is_dir():
        if kind not in {0, stat.S_IFDIR}:
            raise BundleError("unsafe release archive entry")
    elif kind not in {0, stat.S_IFREG}:
        raise BundleError("unsafe release archive entry")
    return path


def validate_archive_entries(
    archive: zipfile.ZipFile,
) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    entries: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    seen: set[PurePosixPath] = set()
    for info in archive.infolist():
        path = normalized_member_path(info)
        if path in seen:
            raise BundleError("duplicate release archive entry")
        seen.add(path)
        if path.parts[0] != "dist":
            raise BundleError(
                "release archive must contain exactly one dist tree"
            )
        entries.append((info, path))
    if not entries:
        raise BundleError("release archive must contain exactly one dist tree")
    return entries


def create_dist_zip(dist: Path, archive: Path) -> None:
    if not dist.is_dir() or dist.is_symlink():
        raise BundleError("Web Host distribution is unavailable")
    if archive.exists() or archive.is_symlink():
        raise BundleError("release archive output must be absent")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as output:
        for source in sorted(dist.rglob("*")):
            relative = PurePosixPath("dist") / source.relative_to(dist).as_posix()
            if source.is_symlink() or any(
                part in {"", ".", ".."} for part in relative.parts
            ):
                raise BundleError(
                    "Web Host distribution contains an unsafe member"
                )
            if source.is_dir():
                continue
            if not source.is_file():
                raise BundleError(
                    "Web Host distribution contains an unsafe member"
                )
            info = zipfile.ZipInfo(
                relative.as_posix(),
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(info, source.read_bytes(), compresslevel=9)
    try:
        with zipfile.ZipFile(archive) as opened:
            validate_archive_entries(opened)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise BundleError("release archive is invalid") from error


def load_distribution_verifier(
    repo_root: Path,
    verifier_relative: str,
) -> Callable[[Path, Path], None]:
    package_path = repo_root / verifier_relative
    if not package_path.is_file() or package_path.is_symlink():
        raise BundleError("distribution verifier is unavailable")
    module_name = (
        "lmdj_web_host_package_"
        + hashlib.sha256(verifier_relative.encode("utf-8")).hexdigest()
    )
    spec = importlib.util.spec_from_file_location(module_name, package_path)
    if spec is None or spec.loader is None:
        raise BundleError("distribution verifier cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError, SyntaxError) as error:
        raise BundleError("distribution verifier cannot be loaded") from error
    finally:
        sys.modules.pop(module_name, None)
    verify_distribution = getattr(module, "verify_distribution", None)
    if not callable(verify_distribution):
        raise BundleError("distribution verifier cannot be loaded")
    return verify_distribution


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


def stage_host_bundle(
    *,
    spec: WebHostReleaseSpec,
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
    try:
        repo_root = repo_root.expanduser().resolve(strict=True)
        archive_path = archive_path.expanduser().resolve(strict=True)
        checksum_path = checksum_path.expanduser().resolve(strict=True)
        signature_path = signature_path.expanduser().resolve(strict=True)
        checksum_public_key_path = checksum_public_key_path.expanduser().resolve(
            strict=True
        )
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
        raise BundleError(
            "release checksum signature verification failed"
        ) from None
    expected_digest = parse_detached_checksum(checksum_path, archive_path.name)
    actual_digest = sha256_file(archive_path)
    if actual_digest != expected_digest:
        raise BundleError("release archive checksum mismatch")

    staged = Path(
        tempfile.mkdtemp(prefix=".lmdj-release-bundle-", dir=output_parent)
    )
    try:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for info, relative in validate_archive_entries(archive):
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
            raise BundleError(
                "release archive must contain exactly one dist tree"
            )
        selected_verifier = verifier or load_distribution_verifier(
            repo_root,
            spec.verifier_relative,
        )
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
        return StagedBundle(
            dist_root=output_root / "dist",
            product_build=product_build,
            host_version=host_version,
            archive_sha256=actual_digest,
        )
    finally:
        if staged.exists() and not staged.is_symlink():
            shutil.rmtree(staged)
