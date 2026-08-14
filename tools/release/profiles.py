"""Closed release asset profile builders and artifact inventory verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile
from typing import Callable

from .commands import CommandRunner
from .model import AssetRecord, ReleaseIntent
from .openpgp import OpenPgpVerifier


class ProfileError(RuntimeError):
    """A release asset profile did not produce its exact closed inventory."""


@dataclass(frozen=True)
class AssetBuild:
    path: Path
    name: str
    bytes: int
    sha256: str

    def record(self) -> AssetRecord:
        return AssetRecord(self.name, self.bytes, self.sha256)


@dataclass(frozen=True)
class ProfileBuild:
    assets: tuple[AssetBuild, ...] = ()


@dataclass(frozen=True)
class ProfileRuntime:
    runner: CommandRunner
    checksum_verifier: OpenPgpVerifier
    checksum_home: Path
    checksum_fingerprint: str


def build_profile(
    profile: str,
    worktree: Path,
    output: Path,
    intent: ReleaseIntent | None,
    *,
    runtime: ProfileRuntime | None = None,
) -> ProfileBuild:
    builder = PROFILE_BUILDERS.get(profile)
    if builder is None:
        raise ValueError("unknown release profile")
    return builder(worktree, output, intent, runtime)


def build_source_only(
    worktree: Path, output: Path, intent: ReleaseIntent | None, runtime: ProfileRuntime | None,
) -> ProfileBuild:
    return ProfileBuild()


def build_core_package(
    worktree: Path, output: Path, intent: ReleaseIntent | None, runtime: ProfileRuntime | None,
) -> ProfileBuild:
    selected = _require_runtime(runtime)
    selected.runner.run(["bash", "scripts/core.sh", "package"], cwd=worktree)
    archives = sorted((worktree / "build/dist").glob("*.zip"))
    if len(archives) != 1:
        raise ProfileError("Core profile must produce exactly one ZIP")
    archive = _require_regular(archives[0], "Core archive")
    checksum = _require_regular(archive.with_name(archive.name + ".sha256"), "Core checksum")
    _verify_checksum(checksum, archive)
    build = _stage_and_sign(
        (archive, checksum), output, selected,
        worktree / ".github/release-signing-keys/lmdj-release-checksum.asc",
    )
    selected.runner.run([
        "python3", "tests/distribution/package_acceptance_test.py", "--build-root", "build/core/release",
    ], cwd=worktree)
    return build


def build_web_runtime_host(
    worktree: Path, output: Path, intent: ReleaseIntent | None, runtime: ProfileRuntime | None,
) -> ProfileBuild:
    if intent is None or intent.kind.value != "product":
        raise ProfileError("Web Runtime Host profile requires a Product intent")
    selected = _require_runtime(runtime)
    for command in ("configure", "build", "test", "proof"):
        selected.runner.run(["bash", "scripts/web-runtime-host.sh", command], cwd=worktree)
    dist = _require_directory(worktree / "build/web/host/dist", "Web Runtime Host distribution")
    host_version = _host_version(worktree)
    archive = output / f"lmdj-web-runtime-host-{host_version}-product-{intent.identity}.zip"
    output.mkdir(parents=True, exist_ok=True)
    _create_dist_zip(dist, archive)
    checksum = archive.with_name(archive.name + ".sha256")
    checksum.write_text(f"{_sha256_file(archive)}  {archive.name}\n", encoding="ascii", newline="\n")
    build = _stage_and_sign(
        (archive, checksum), output, selected,
        worktree / ".github/release-signing-keys/lmdj-release-checksum.asc",
    )
    _stage_web_bundle(worktree, build, output, intent, host_version, selected)
    return build


PROFILE_BUILDERS: dict[str, Callable[[Path, Path, ReleaseIntent | None, ProfileRuntime | None], ProfileBuild]] = {
    "source-only": build_source_only,
    "core-package": build_core_package,
    "web-runtime-host": build_web_runtime_host,
}


def verify_existing_profile(
    profile: str,
    worktree: Path,
    assets_root: Path,
    intent: ReleaseIntent,
    assets: tuple[AssetBuild, ...],
    runtime: ProfileRuntime,
) -> None:
    """Verify persisted profile assets without rebuilding or signing them."""
    if profile == "source-only":
        if assets:
            raise ProfileError("source-only releases must not create release assets")
        return
    if profile not in {"core-package", "web-runtime-host"}:
        raise ValueError("unknown release profile")
    selected = _require_runtime(runtime)
    archive, checksum, signature = _profile_asset_paths(assets_root, assets)
    _verify_checksum(checksum, archive)
    _verify_detached_checksum_signature(
        checksum, signature,
        worktree / ".github/release-signing-keys/lmdj-release-checksum.asc",
        selected,
    )
    if profile == "web-runtime-host":
        host_version = _host_version(worktree)
        with tempfile.TemporaryDirectory(prefix="lmdj-release-existing-web-") as directory:
            _stage_web_bundle(
                worktree, ProfileBuild(assets), Path(directory), intent, host_version, selected,
            )


def _require_runtime(runtime: ProfileRuntime | None) -> ProfileRuntime:
    if runtime is None:
        raise ProfileError("release checksum signer is unavailable")
    return runtime


def _stage_and_sign(
    inputs: tuple[Path, Path], output: Path, runtime: ProfileRuntime, checksum_public_key_path: Path,
) -> ProfileBuild:
    archive, checksum = inputs
    output.mkdir(parents=True, exist_ok=True)
    staged_archive = output / archive.name
    staged_checksum = output / checksum.name
    for source, destination in ((archive, staged_archive), (checksum, staged_checksum)):
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
    _verify_checksum(staged_checksum, staged_archive)
    signature = staged_checksum.with_name(staged_checksum.name + ".asc")
    runtime.checksum_verifier.sign_detached(
        runtime.checksum_home, staged_checksum, signature, runtime.checksum_fingerprint,
    )
    _verify_detached_checksum_signature(staged_checksum, signature, checksum_public_key_path, runtime)
    return ProfileBuild(tuple(_asset(path) for path in (staged_archive, staged_checksum, signature)))


def _profile_asset_paths(assets_root: Path, assets: tuple[AssetBuild, ...]) -> tuple[Path, Path, Path]:
    paths = {asset.name: asset.path for asset in assets}
    archives = [path for name, path in paths.items() if name.endswith(".zip")]
    if len(archives) != 1:
        raise ProfileError("Product release profile must produce exactly three assets")
    archive = archives[0]
    checksum = paths.get(archive.name + ".sha256")
    signature = paths.get(archive.name + ".sha256.asc")
    if (
        archive.parent != assets_root or checksum is None or signature is None
        or checksum.parent != assets_root or signature.parent != assets_root
    ):
        raise ProfileError("release asset inventory is not canonical")
    return archive, checksum, signature


def _verify_detached_checksum_signature(
    checksum: Path, signature: Path, checksum_public_key_path: Path, runtime: ProfileRuntime,
) -> None:
    with tempfile.TemporaryDirectory(prefix="lmdj-release-checksum-verify-") as directory:
        verification_home = Path(directory)
        verification_home.chmod(0o700)
        runtime.checksum_verifier.import_public_key(
            verification_home, checksum_public_key_path, runtime.checksum_fingerprint,
        )
        runtime.checksum_verifier.verify_detached(
            verification_home, signature, checksum, runtime.checksum_fingerprint,
        )


def _asset(path: Path) -> AssetBuild:
    _require_regular(path, "release asset")
    return AssetBuild(path, path.name, path.stat().st_size, _sha256_file(path))


def _verify_checksum(checksum: Path, archive: Path) -> None:
    try:
        record = checksum.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as error:
        raise ProfileError("release checksum is invalid") from error
    expected = f"{_sha256_file(archive)}  {archive.name}\n"
    if record != expected:
        raise ProfileError("release checksum does not match archive")


def _create_dist_zip(dist: Path, archive: Path) -> None:
    if archive.exists() or archive.is_symlink():
        raise ProfileError("release archive output must be absent")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for source in sorted(dist.rglob("*")):
            relative = PurePosixPath("dist") / source.relative_to(dist).as_posix()
            if source.is_symlink() or any(part in {"", ".", ".."} for part in relative.parts):
                raise ProfileError("Web Runtime Host distribution contains an unsafe member")
            if source.is_dir():
                continue
            if not source.is_file():
                raise ProfileError("Web Runtime Host distribution contains an unsafe member")
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(info, source.read_bytes(), compresslevel=9)
    _verify_dist_zip(archive)


def _verify_dist_zip(archive: Path) -> None:
    with zipfile.ZipFile(archive) as opened:
        names: set[str] = set()
        for item in opened.infolist():
            path = PurePosixPath(item.filename)
            if (
                item.filename in names or not item.filename.startswith("dist/") or "\\" in item.filename
                or item.filename.startswith("/") or any(part in {"", ".", ".."} for part in path.parts)
                or stat.S_IFMT(item.external_attr >> 16) not in {0, stat.S_IFREG}
            ):
                raise ProfileError("release archive member inventory is invalid")
            names.add(item.filename)
        if not names:
            raise ProfileError("release archive must contain a dist tree")


def _stage_web_bundle(
    worktree: Path, build: ProfileBuild, output: Path, intent: ReleaseIntent, host_version: str, runtime: ProfileRuntime,
) -> None:
    tool = worktree / "apps/web-runtime-host/tools/release_bundle.py"
    spec = importlib.util.spec_from_file_location("lmdj_release_bundle", tool)
    if spec is None or spec.loader is None:
        raise ProfileError("Web Runtime Host release verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    archive, checksum, signature = (asset.path for asset in build.assets)
    stage = output / ".verified"
    module.stage_release_bundle(
        repo_root=worktree,
        archive_path=archive,
        checksum_path=checksum,
        signature_path=signature,
        checksum_public_key_path=worktree / ".github/release-signing-keys/lmdj-release-checksum.asc",
        trusted_checksum_fingerprint=runtime.checksum_fingerprint,
        output_root=stage,
        expected_product_build=intent.identity,
        expected_host_version=host_version,
    )
    shutil.rmtree(stage)


def _host_version(worktree: Path) -> str:
    try:
        document = json.loads((worktree / "apps/web-runtime-host/module.json").read_text(encoding="utf-8"))
        version = document["version"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ProfileError("Web Runtime Host version is unavailable") from error
    if not isinstance(version, str) or not version:
        raise ProfileError("Web Runtime Host version is unavailable")
    return version


def _require_regular(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise ProfileError(f"{label} is unavailable")
    return path


def _require_directory(path: Path, label: str) -> Path:
    if not path.is_dir() or path.is_symlink():
        raise ProfileError(f"{label} is unavailable")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()
