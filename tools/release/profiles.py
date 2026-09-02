"""Closed release asset profile builders and artifact inventory verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Callable

from .commands import CommandRunner
from .model import AssetRecord, ReleaseIntent
from .openpgp import OpenPgpVerifier
from .web_host_bundle import (
    BundleError,
    WebHostReleaseSpec,
    create_dist_zip,
)


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


CREATOR_WEB_SPEC = WebHostReleaseSpec(
    host_id="creator-web",
    script="scripts/creator-web.sh",
    dist_relative="build/web/creator/dist",
    module_relative="apps/creator-web/module.json",
    archive_prefix="lmdj-creator-web",
    verifier_relative="apps/creator-web/tools/package.py",
)

WEB_RUNTIME_SPEC = WebHostReleaseSpec(
    host_id="web-runtime-host",
    script="scripts/web-runtime-host.sh",
    dist_relative="build/web/host/dist",
    module_relative="apps/web-runtime-host/module.json",
    archive_prefix="lmdj-web-runtime-host",
    verifier_relative="apps/web-runtime-host/tools/package.py",
)


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
    manifest = _require_regular(
        archive.with_name(archive.name[: -len(".zip")] + ".build-manifest.json"),
        "Core Build Manifest",
    )
    build = _stage_and_sign(
        (archive, checksum), output, selected,
        worktree / ".github/release-signing-keys/lmdj-release-checksum.asc",
        extra=(manifest,),
    )
    selected.runner.run([
        "python3", "tests/distribution/package_acceptance_test.py", "--build-root", "build/core/release",
    ], cwd=worktree)
    return build


def build_web_runtime_host(
    worktree: Path, output: Path, intent: ReleaseIntent | None, runtime: ProfileRuntime | None,
) -> ProfileBuild:
    _require_product_intent(intent)
    selected = _require_runtime(runtime)
    _install_web_dependencies(worktree, selected, include_creator=False)
    return _build_web_host(WEB_RUNTIME_SPEC, worktree, output, intent, selected)


def build_web_hosts(
    worktree: Path,
    output: Path,
    intent: ReleaseIntent | None,
    runtime: ProfileRuntime | None,
) -> ProfileBuild:
    _require_product_intent(intent)
    selected = _require_runtime(runtime)
    _install_web_dependencies(worktree, selected, include_creator=True)
    creator = _build_web_host(
        CREATOR_WEB_SPEC,
        worktree,
        output,
        intent,
        selected,
    )
    runtime_host = _build_web_host(
        WEB_RUNTIME_SPEC,
        worktree,
        output,
        intent,
        selected,
    )
    return ProfileBuild(
        tuple(
            sorted(
                (*creator.assets, *runtime_host.assets),
                key=lambda asset: asset.name,
            )
        )
    )


def _require_product_intent(intent: ReleaseIntent | None) -> None:
    if intent is None or intent.kind.value != "product":
        raise ProfileError("Web Host profile requires a Product intent")


def _install_web_dependencies(
    worktree: Path,
    runtime: ProfileRuntime,
    *,
    include_creator: bool,
) -> None:
    node = os.environ.get("EMSDK_NODE")
    environment = (
        {"PATH": str(Path(node).parent) + os.pathsep + os.environ.get("PATH", "")}
        if node else None
    )
    runtime.runner.run(
        ["npm", "--prefix", "tests/platform/web", "ci"],
        cwd=worktree,
        environment=environment,
    )
    if include_creator:
        runtime.runner.run(
            ["npm", "--prefix", "apps/creator-web", "ci"],
            cwd=worktree,
            environment=environment,
        )


def _build_web_host(
    spec: WebHostReleaseSpec,
    worktree: Path,
    output: Path,
    intent: ReleaseIntent,
    runtime: ProfileRuntime,
) -> ProfileBuild:
    for command in ("configure", "build", "test", "proof"):
        runtime.runner.run(["bash", spec.script, command], cwd=worktree)
    dist = _require_directory(
        worktree / spec.dist_relative,
        f"{spec.host_id} distribution",
    )
    host_version = _host_version(worktree, spec)
    archive = output / (
        f"{spec.archive_prefix}-{host_version}-product-{intent.identity}.zip"
    )
    output.mkdir(parents=True, exist_ok=True)
    _create_dist_zip(dist, archive)
    checksum = archive.with_name(archive.name + ".sha256")
    checksum.write_text(f"{_sha256_file(archive)}  {archive.name}\n", encoding="ascii", newline="\n")
    build = _stage_and_sign(
        (archive, checksum), output, runtime,
        worktree / ".github/release-signing-keys/lmdj-release-checksum.asc",
    )
    _stage_web_bundle(
        spec,
        worktree,
        build,
        output,
        intent,
        host_version,
        runtime,
    )
    return build


PROFILE_BUILDERS: dict[str, Callable[[Path, Path, ReleaseIntent | None, ProfileRuntime | None], ProfileBuild]] = {
    "source-only": build_source_only,
    "core-package": build_core_package,
    "web-runtime-host": build_web_runtime_host,
    "web-hosts": build_web_hosts,
}


def canonical_product_asset_names(
    profile: str,
    names: tuple[str, ...] | list[str],
    product_build: str,
) -> frozenset[str]:
    """Return the exact allowed inventory for a Product binary profile."""
    archives = [name for name in names if name.endswith(".zip")]
    if profile in {"core-package", "web-runtime-host"}:
        if len(archives) != 1:
            raise ProfileError(
                "Product release profile must produce exactly one archive"
            )
        archive = archives[0]
        expected = {
            archive,
            f"{archive}.sha256",
            f"{archive}.sha256.asc",
        }
        if profile == "core-package":
            expected.add(
                archive[: -len(".zip")] + ".build-manifest.json"
            )
        return frozenset(expected)
    if profile == "web-hosts":
        if len(archives) != 2:
            raise ProfileError(
                "dual Web Host profile must produce exactly two archives"
            )
        matched: dict[str, str] = {}
        for archive in archives:
            match = re.fullmatch(
                r"lmdj-(creator-web|web-runtime-host)-"
                r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
                r"(?:0|[1-9][0-9]*)-product-"
                + re.escape(product_build)
                + r"\.zip",
                archive,
            )
            if match is None or match.group(1) in matched:
                raise ProfileError(
                    "dual Web Host archive names are not canonical"
                )
            matched[match.group(1)] = archive
        if set(matched) != {"creator-web", "web-runtime-host"}:
            raise ProfileError(
                "dual Web Host archive names are not canonical"
            )
        return frozenset(
            name
            for archive in matched.values()
            for name in (
                archive,
                f"{archive}.sha256",
                f"{archive}.sha256.asc",
            )
        )
    raise ProfileError("unknown release profile")


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
    if profile not in {"core-package", "web-runtime-host", "web-hosts"}:
        raise ValueError("unknown release profile")
    selected = _require_runtime(runtime)
    if profile == "web-hosts":
        _verify_existing_web_hosts(
            worktree,
            assets_root,
            intent,
            assets,
            selected,
        )
        return
    archive, checksum, signature, manifest = _profile_asset_paths(assets_root, assets, profile)
    _verify_checksum(checksum, archive)
    _verify_detached_checksum_signature(
        checksum, signature,
        worktree / ".github/release-signing-keys/lmdj-release-checksum.asc",
        selected,
    )
    if manifest is not None:
        _verify_core_manifest(manifest, intent)
    if profile == "web-runtime-host":
        host_version = _host_version(worktree, WEB_RUNTIME_SPEC)
        with tempfile.TemporaryDirectory(prefix="lmdj-release-existing-web-") as directory:
            _stage_web_bundle(
                WEB_RUNTIME_SPEC,
                worktree,
                ProfileBuild(assets),
                Path(directory),
                intent,
                host_version,
                selected,
            )


def _require_runtime(runtime: ProfileRuntime | None) -> ProfileRuntime:
    if runtime is None:
        raise ProfileError("release checksum signer is unavailable")
    return runtime


def _verify_existing_web_hosts(
    worktree: Path,
    assets_root: Path,
    intent: ReleaseIntent,
    assets: tuple[AssetBuild, ...],
    runtime: ProfileRuntime,
) -> None:
    names = tuple(asset.name for asset in assets)
    expected: list[str] = []
    versions: dict[str, str] = {}
    for spec in (CREATOR_WEB_SPEC, WEB_RUNTIME_SPEC):
        version = _host_version(worktree, spec)
        versions[spec.host_id] = version
        archive = (
            f"{spec.archive_prefix}-{version}-product-{intent.identity}.zip"
        )
        expected.extend((archive, f"{archive}.sha256", f"{archive}.sha256.asc"))
    if len(set(names)) != len(names) or set(names) != set(expected):
        raise ProfileError("dual Web Host release asset inventory is not canonical")
    by_name = {asset.name: asset for asset in assets}
    for spec in (CREATOR_WEB_SPEC, WEB_RUNTIME_SPEC):
        archive_name = (
            f"{spec.archive_prefix}-{versions[spec.host_id]}-product-"
            f"{intent.identity}.zip"
        )
        selected_assets = tuple(
            by_name[name]
            for name in (
                archive_name,
                f"{archive_name}.sha256",
                f"{archive_name}.sha256.asc",
            )
        )
        archive, checksum, signature = (asset.path for asset in selected_assets)
        if any(path.parent != assets_root for path in (archive, checksum, signature)):
            raise ProfileError("dual Web Host release asset inventory is not canonical")
        _verify_checksum(checksum, archive)
        _verify_detached_checksum_signature(
            checksum,
            signature,
            worktree / ".github/release-signing-keys/lmdj-release-checksum.asc",
            runtime,
        )
        with tempfile.TemporaryDirectory(
            prefix=f"lmdj-release-existing-{spec.host_id}-"
        ) as directory:
            _stage_web_bundle(
                spec,
                worktree,
                ProfileBuild(selected_assets),
                Path(directory),
                intent,
                versions[spec.host_id],
                runtime,
            )


def _stage_and_sign(
    inputs: tuple[Path, Path], output: Path, runtime: ProfileRuntime, checksum_public_key_path: Path,
    extra: tuple[Path, ...] = (),
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
    staged_extra: list[Path] = []
    for source in extra:
        destination = output / source.name
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
        staged_extra.append(destination)
    return ProfileBuild(tuple(_asset(path) for path in (staged_archive, staged_checksum, signature, *staged_extra)))


def _profile_asset_paths(
    assets_root: Path, assets: tuple[AssetBuild, ...], profile: str
) -> tuple[Path, Path, Path, Path | None]:
    paths = {asset.name: asset.path for asset in assets}
    archives = [path for name, path in paths.items() if name.endswith(".zip")]
    if len(archives) != 1:
        raise ProfileError("Product release profile must produce exactly one archive")
    archive = archives[0]
    checksum = paths.get(archive.name + ".sha256")
    signature = paths.get(archive.name + ".sha256.asc")
    if (
        archive.parent != assets_root or checksum is None or signature is None
        or checksum.parent != assets_root or signature.parent != assets_root
    ):
        raise ProfileError("release asset inventory is not canonical")
    manifest: Path | None = None
    if profile == "core-package":
        manifest = paths.get(archive.name[: -len(".zip")] + ".build-manifest.json")
        if manifest is None or manifest.parent != assets_root:
            raise ProfileError("Core release profile must produce a detached Build Manifest")
    return archive, checksum, signature, manifest


def _verify_core_manifest(manifest: Path, intent: ReleaseIntent) -> None:
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProfileError("Core Build Manifest is not readable JSON") from error
    if not isinstance(document, dict) or document.get("contract") != "lmdj.build-manifest.v1":
        raise ProfileError("Core Build Manifest contract identity is invalid")
    product = document.get("product")
    if not isinstance(product, dict) or product.get("id") != "lmdj" or product.get("version") != intent.identity:
        raise ProfileError("Core Build Manifest Product identity conflicts with the release intent")
    if document.get("git_revision") != intent.target_revision:
        raise ProfileError("Core Build Manifest Git revision conflicts with the release intent")


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
    try:
        create_dist_zip(dist, archive)
    except BundleError as error:
        raise ProfileError(str(error)) from error


def _stage_web_bundle(
    host: WebHostReleaseSpec,
    worktree: Path,
    build: ProfileBuild,
    output: Path,
    intent: ReleaseIntent,
    host_version: str,
    runtime: ProfileRuntime,
) -> None:
    tool = worktree / host.verifier_relative.replace("package.py", "release_bundle.py")
    module_name = "lmdj_release_bundle_" + host.host_id.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, tool)
    if spec is None or spec.loader is None:
        raise ProfileError(f"{host.host_id} release verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
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


def _host_version(worktree: Path, host: WebHostReleaseSpec) -> str:
    try:
        document = json.loads(
            (worktree / host.module_relative).read_text(encoding="utf-8")
        )
        version = document["version"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ProfileError(f"{host.host_id} version is unavailable") from error
    if not isinstance(version, str) or not version:
        raise ProfileError(f"{host.host_id} version is unavailable")
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
