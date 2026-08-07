#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


HOST_ID = "creator-web"
HOST_VERSION = "1.0.1"
PLATFORM_VERSION = "0.1.1"
COMPATIBLE_HOSTS = [
    {"host_id": "web-runtime-host", "host_version": "1.2.1"},
]
PROTOCOL_VERSION = 1
HEAP_BYTES = 536_870_912
DISTRIBUTION_CONTRACT = "lmdj.creator-web.distribution.v1"
EMCC_VERSION = (
    "emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) "
    "6.0.5 (1db513782be24469589d7cb8a1f1834e9a33f271)"
)
RESOURCE_LIMITS = {
    "imported_wav_bytes": 1_048_576,
    "decoded_frames_per_pad": 240_000,
    "decoded_float_pcm_bytes_per_bank": 67_108_864,
    "decoded_float_pcm_bytes_total": 134_217_728,
}
TOOLCHAIN_KEYS = {
    "emsdk_tag",
    "emsdk_revision",
    "emscripten_releases_revision",
    "initial_memory",
    "allow_memory_growth",
    "node",
    "playwright",
    "linker_flags",
}
MANIFEST_TOOLCHAIN_KEYS = (
    "emsdk_tag",
    "emsdk_revision",
    "emscripten_releases_revision",
    "emcc_version",
)
EXPECTED_ASSETS = (
    ("assets/main.", ".js", "host_main"),
    ("assets/runtime.", ".js", "runtime_script"),
    ("assets/runtime.", ".wasm", "runtime_wasm"),
    ("assets/styles.", ".css", "host_style"),
)
HASHED_ASSET_PATTERN = re.compile(
    r"^assets/[a-z0-9-]+\.[0-9a-f]{64}\.(?:css|js|mjs|wasm)$"
)
LOCAL_PATH_PATTERN = re.compile(rb"(?:/Users/|file:/+(?:Users|home)/|[A-Za-z]:\\)")
SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".py", ".map",
}


class PackageError(RuntimeError):
    pass


class DistributionError(RuntimeError):
    pass


class UsageError(RuntimeError):
    pass


class UsageParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"package usage error: {message}", file=sys.stderr)
        raise UsageError(message)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageError(f"invalid {label}: {path}") from error
    if not isinstance(value, dict):
        raise PackageError(f"{label} must be an object: {path}")
    return value


def product_build(version: dict) -> str:
    if set(version) != {
        "contract", "product", "milestone", "minor", "build", "patch",
    }:
        raise PackageError("Product version keys are invalid")
    if version["contract"] != "lmdj.product-version.v1" or version["product"] != "lmdj":
        raise PackageError("Product version identity is invalid")
    parts = [version[name] for name in ("milestone", "minor", "build", "patch")]
    if any(type(part) is not int or part < 0 for part in parts):
        raise PackageError("Product Build parts must be non-negative integers")
    return ".".join(str(part) for part in parts)


def require_clean_source(repo_root: Path) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain=v1", "--untracked-files=all"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or completed.stdout != "":
        raise PackageError("Creator package requires a clean Git source tree")


def validate_identity(repo_root: Path, identity_path: Path) -> dict:
    lock = read_json(repo_root / "tools/web-runtime/emscripten.lock.json", "toolchain lock")
    identity = read_json(identity_path, "toolchain identity")
    if set(lock) != TOOLCHAIN_KEYS:
        raise PackageError("toolchain lock keys are invalid")
    if set(identity) != TOOLCHAIN_KEYS | {"emcc_version"}:
        raise PackageError("toolchain identity keys are invalid")
    for key in TOOLCHAIN_KEYS:
        if type(identity[key]) is not type(lock[key]) or identity[key] != lock[key]:
            raise PackageError(f"toolchain identity mismatch for {key}")
    if identity["emcc_version"] != EMCC_VERSION:
        raise PackageError("toolchain identity mismatch for emcc_version")
    if identity["initial_memory"] != HEAP_BYTES or identity["allow_memory_growth"] is not False:
        raise PackageError("toolchain identity mismatch for fixed heap")
    return identity


def require_file(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except OSError as error:
        raise PackageError(f"{label} is missing: {path}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PackageError(f"{label} is unsafe: {path}")
    return path


def write_hashed_asset(
    assets_root: Path,
    stem: str,
    suffix: str,
    payload: bytes,
    role: str,
) -> dict:
    digest = sha256(payload)
    path = assets_root / f"{stem}.{digest}{suffix}"
    path.write_bytes(payload)
    return {
        "path": f"assets/{path.name}",
        "bytes": len(payload),
        "sha256": digest,
        "role": role,
    }


def unique_vite_asset(index: str, suffix: str) -> str:
    matches = re.findall(r'(?:src|href)="(/assets/[^"]+\.' + re.escape(suffix) + r')"', index)
    if len(matches) != 1:
        raise PackageError(f"Vite index must bind exactly one {suffix} asset")
    return matches[0].removeprefix("/")


def safe_dist_root(path: Path, repo_root: Path) -> tuple[Path, os.stat_result | None]:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested.parent.mkdir(parents=True, exist_ok=True)
    resolved = requested.parent.resolve(strict=True) / requested.name
    if resolved in {Path("/"), repo_root}:
        raise PackageError(f"unsafe distribution root: {resolved}")
    try:
        initial = os.lstat(resolved)
    except FileNotFoundError:
        initial = None
    if initial is not None:
        if stat.S_ISLNK(initial.st_mode):
            raise PackageError(f"distribution root is a symlink: {resolved}")
        if not stat.S_ISDIR(initial.st_mode):
            raise PackageError(f"unsafe existing distribution root: {resolved}")
        try:
            verify_distribution(resolved, repo_root)
        except DistributionError as error:
            raise PackageError(f"existing distribution is not replaceable: {resolved}") from error
    return resolved, initial


def build_distribution(
    repo_root: Path,
    ui_root: Path,
    runtime_root: Path,
    identity_path: Path,
    dist_root: Path,
) -> None:
    repo_root = repo_root.expanduser().resolve(strict=True)
    ui_root = ui_root.expanduser().resolve(strict=True)
    runtime_root = runtime_root.expanduser().resolve(strict=True)
    identity_path = identity_path.expanduser().resolve(strict=True)
    require_clean_source(repo_root)
    dist_root, initial_target = safe_dist_root(dist_root, repo_root)
    identity = validate_identity(repo_root, identity_path)
    active_product_build = product_build(
        read_json(repo_root / "products/lmdj/version.json", "Product version")
    )

    source_index = require_file(ui_root / "index.html", "Vite index").read_text(
        encoding="utf-8"
    )
    source_main_relative = unique_vite_asset(source_index, "js")
    source_style_relative = unique_vite_asset(source_index, "css")
    source_main = require_file(ui_root / source_main_relative, "Vite main")
    source_style = require_file(ui_root / source_style_relative, "Vite style")
    runtime_js = require_file(runtime_root / "lmdj-web-runtime.js", "Runtime JavaScript")
    runtime_wasm = require_file(runtime_root / "lmdj-web-runtime.wasm", "Runtime Wasm")

    with tempfile.TemporaryDirectory(prefix=".lmdj-creator-dist-", dir=dist_root.parent) as temporary:
        staged = Path(temporary)
        assets_root = staged / "assets"
        assets_root.mkdir()
        main_entry = write_hashed_asset(
            assets_root, "main", ".js", source_main.read_bytes(), "host_main"
        )
        style_entry = write_hashed_asset(
            assets_root, "styles", ".css", source_style.read_bytes(), "host_style"
        )
        wasm_entry = write_hashed_asset(
            assets_root, "runtime", ".wasm", runtime_wasm.read_bytes(), "runtime_wasm"
        )
        try:
            runtime_text = runtime_js.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise PackageError("Runtime JavaScript is not UTF-8") from error
        if runtime_text.count("lmdj-web-runtime.wasm") != 1:
            raise PackageError("Runtime Wasm binding must occur exactly once")
        runtime_text = runtime_text.replace(
            "lmdj-web-runtime.wasm", Path(wasm_entry["path"]).name, 1
        )
        runtime_entry = write_hashed_asset(
            assets_root,
            "runtime",
            ".js",
            runtime_text.encode("utf-8"),
            "runtime_script",
        )
        entries = [main_entry, runtime_entry, wasm_entry, style_entry]
        manifest = {
            "assets": entries,
            "compatible_hosts": COMPATIBLE_HOSTS,
            "distribution_contract": DISTRIBUTION_CONTRACT,
            "emscripten": {key: identity[key] for key in MANIFEST_TOOLCHAIN_KEYS},
            "heap_bytes": HEAP_BYTES,
            "host_id": HOST_ID,
            "host_version": HOST_VERSION,
            "manifest_version": 1,
            "platform_version": PLATFORM_VERSION,
            "product_build": active_product_build,
            "protocol_version": PROTOCOL_VERSION,
            "resource_limits": RESOURCE_LIMITS,
        }
        manifest_bytes = canonical_json(manifest)
        (staged / "host-manifest.json").write_bytes(manifest_bytes)
        manifest_digest = sha256(manifest_bytes)

        index = source_index.replace(
            f'/{source_main_relative}', f'./{main_entry["path"]}', 1
        ).replace(
            f'/{source_style_relative}', f'./{style_entry["path"]}', 1
        )
        charset = re.search(r"<meta charset=\"UTF-8\"\s*/?>", index)
        if charset is None:
            raise PackageError("Vite index charset metadata is missing")
        metadata = (
            f'\n    <meta name="lmdj-host-manifest-sha256" content="{manifest_digest}">'
            '\n    <meta name="lmdj-host-manifest-path" content="./host-manifest.json">'
            f'\n    <meta name="lmdj-product-build" content="{active_product_build}">'
            f'\n    <meta name="lmdj-host-id" content="{HOST_ID}">'
            f'\n    <meta name="lmdj-host-version" content="{HOST_VERSION}">'
            f'\n    <meta name="lmdj-web-runtime-platform-version" content="{PLATFORM_VERSION}">'
            f'\n    <meta name="lmdj-host-protocol-version" content="{PROTOCOL_VERSION}">'
        )
        index = index[:charset.end()] + metadata + index[charset.end():]
        (staged / "index.html").write_text(index, encoding="utf-8", newline="\n")
        verify_distribution(staged, repo_root)

        try:
            current_target = os.lstat(dist_root)
        except FileNotFoundError:
            current_target = None
        if initial_target is None and current_target is not None:
            raise PackageError("distribution target appeared during packaging")
        if initial_target is not None:
            if (
                current_target is None
                or stat.S_ISLNK(current_target.st_mode)
                or not stat.S_ISDIR(current_target.st_mode)
                or (current_target.st_dev, current_target.st_ino)
                != (initial_target.st_dev, initial_target.st_ino)
            ):
                raise PackageError("distribution target changed during packaging")
            verify_distribution(dist_root, repo_root)
        backup = Path(tempfile.mkdtemp(prefix=".lmdj-creator-backup-", dir=dist_root.parent))
        backup.rmdir()
        try:
            if initial_target is not None:
                os.replace(dist_root, backup)
            try:
                os.replace(staged, dist_root)
            except OSError as error:
                if initial_target is not None:
                    os.replace(backup, dist_root)
                raise PackageError("distribution replacement failed") from error
            if backup.exists():
                shutil.rmtree(backup)
        finally:
            if backup.exists() and not backup.is_symlink():
                shutil.rmtree(backup)


def verify_distribution(dist_root: Path, repo_root: Path) -> None:
    try:
        requested = dist_root.expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        info = os.lstat(requested)
        if stat.S_ISLNK(info.st_mode):
            raise DistributionError("distribution root is a symlink")
        dist_root = requested.resolve(strict=True)
        repo_root = repo_root.expanduser().resolve(strict=True)
    except OSError as error:
        raise DistributionError("distribution root is missing") from error
    if not dist_root.is_dir() or any(path.is_symlink() for path in dist_root.rglob("*")):
        raise DistributionError("distribution root is unsafe")
    manifest_path = dist_root / "host-manifest.json"
    index_path = dist_root / "index.html"
    if not manifest_path.is_file() or not index_path.is_file():
        raise DistributionError("index or manifest is missing")
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DistributionError("manifest is malformed") from error
    if not isinstance(manifest, dict) or canonical_json(manifest) != manifest_bytes:
        raise DistributionError("manifest is not exact canonical JSON")
    if set(manifest) != {
        "assets", "compatible_hosts", "distribution_contract", "emscripten",
        "heap_bytes", "host_id", "host_version", "manifest_version",
        "platform_version", "product_build", "protocol_version", "resource_limits",
    }:
        raise DistributionError("manifest root schema is invalid")
    version = read_json(repo_root / "products/lmdj/version.json", "Product version")
    lock = read_json(repo_root / "tools/web-runtime/emscripten.lock.json", "toolchain lock")
    if (
        manifest["distribution_contract"] != DISTRIBUTION_CONTRACT
        or manifest["manifest_version"] != 1
        or manifest["product_build"] != product_build(version)
        or manifest["host_id"] != HOST_ID
        or manifest["host_version"] != HOST_VERSION
        or manifest["platform_version"] != PLATFORM_VERSION
        or manifest["compatible_hosts"] != COMPATIBLE_HOSTS
        or manifest["protocol_version"] != PROTOCOL_VERSION
        or manifest["heap_bytes"] != HEAP_BYTES
        or manifest["resource_limits"] != RESOURCE_LIMITS
        or manifest["emscripten"] != {
            "emcc_version": EMCC_VERSION,
            "emscripten_releases_revision": lock["emscripten_releases_revision"],
            "emsdk_revision": lock["emsdk_revision"],
            "emsdk_tag": lock["emsdk_tag"],
        }
    ):
        raise DistributionError("manifest identity is invalid")
    assets = manifest["assets"]
    if not isinstance(assets, list) or len(assets) != len(EXPECTED_ASSETS):
        raise DistributionError("manifest production inventory is invalid")
    expected_files = {"index.html", "host-manifest.json"}
    for entry, (prefix, suffix, role) in zip(assets, EXPECTED_ASSETS, strict=True):
        if not isinstance(entry, dict) or set(entry) != {"path", "bytes", "sha256", "role"}:
            raise DistributionError("manifest asset entry is invalid")
        relative = entry["path"]
        if (
            not isinstance(relative, str)
            or HASHED_ASSET_PATTERN.fullmatch(relative) is None
            or entry["role"] != role
            or type(entry["bytes"]) is not int
            or entry["bytes"] < 1
            or not isinstance(entry["sha256"], str)
            or relative != f"{prefix}{entry['sha256']}{suffix}"
        ):
            raise DistributionError("manifest production inventory is invalid")
        path = dist_root / relative
        if not path.is_file():
            raise DistributionError(f"missing asset: {relative}")
        payload = path.read_bytes()
        digest = sha256(payload)
        if entry["bytes"] != len(payload) or entry["sha256"] != digest:
            raise DistributionError(f"asset content mismatch: {relative}")
        if LOCAL_PATH_PATTERN.search(payload) is not None or str(repo_root).encode() in payload:
            raise DistributionError(f"absolute local path in asset: {relative}")
        expected_files.add(relative)
    actual_files = {
        path.relative_to(dist_root).as_posix()
        for path in dist_root.rglob("*") if path.is_file()
    }
    if actual_files != expected_files:
        raise DistributionError("distribution inventory mismatch")
    for relative in actual_files:
        path = Path(relative)
        if path.suffix.lower() in SOURCE_SUFFIXES:
            raise DistributionError(f"source or source map shipped: {relative}")
        if {part.lower() for part in path.parts} & {
            "test", "tests", "fixture", "fixtures", "node_modules",
        }:
            raise DistributionError(f"development content shipped: {relative}")
    index = index_path.read_text(encoding="utf-8")
    digest = sha256(manifest_bytes)
    for exact in (
        f'<meta name="lmdj-host-manifest-sha256" content="{digest}">',
        '<meta name="lmdj-host-manifest-path" content="./host-manifest.json">',
        f'<meta name="lmdj-product-build" content="{manifest["product_build"]}">',
        f'<meta name="lmdj-host-id" content="{HOST_ID}">',
        f'<meta name="lmdj-host-version" content="{HOST_VERSION}">',
        f'<meta name="lmdj-web-runtime-platform-version" content="{PLATFORM_VERSION}">',
        f'<meta name="lmdj-host-protocol-version" content="{PROTOCOL_VERSION}">',
    ):
        if index.count(exact) != 1:
            raise DistributionError("index identity metadata mismatch")
    main = next(entry for entry in assets if entry["role"] == "host_main")
    style = next(entry for entry in assets if entry["role"] == "host_style")
    if index.count(f'./{main["path"]}') != 1 or index.count(f'./{style["path"]}') != 1:
        raise DistributionError("index production asset binding mismatch")
    if re.search(r"<script(?![^>]*\bsrc=)[^>]*>", index, re.IGNORECASE):
        raise DistributionError("index contains inline script")
    if LOCAL_PATH_PATTERN.search(index.encode("utf-8")) is not None:
        raise DistributionError("absolute local path in index")


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = UsageParser(description="Build the deterministic Creator distribution")
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--ui-root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--dist-root", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        UsageParser().print_usage(sys.stderr)
        return 64
    try:
        options = parse_arguments(arguments)
        build_distribution(
            options.repo_root,
            options.ui_root,
            options.runtime_root,
            options.identity,
            options.dist_root,
        )
    except UsageError:
        return 64
    except (OSError, PackageError, DistributionError) as error:
        print(f"creator package error: {error}", file=sys.stderr)
        return 2
    print(f"Creator package: PASS ({options.dist_root})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
