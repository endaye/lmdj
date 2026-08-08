#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path


HOST_ID = "web-runtime-host"
HOST_VERSION = "1.2.2"
PLATFORM_VERSION = "0.1.2"
PROTOCOL_VERSION = 1
HEAP_BYTES = 536_870_912
DISTRIBUTION_CONTRACT = "lmdj.web-runtime-host.distribution.v1"
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
    ("assets/diagnostic-client.", ".mjs", "platform_module"),
    ("assets/diagnostic-project.", ".mjs", "host_module"),
    ("assets/input-adapters.", ".mjs", "platform_module"),
    ("assets/main.", ".mjs", "host_main"),
    ("assets/preflight.", ".mjs", "platform_module"),
    ("assets/project-bundle-reader.", ".mjs", "platform_module"),
    ("assets/protocol.", ".mjs", "platform_module"),
    ("assets/runtime.", ".js", "runtime_script"),
    ("assets/runtime.", ".wasm", "runtime_wasm"),
    ("assets/runtime-loader.", ".mjs", "platform_module"),
    ("assets/runtime-session.", ".mjs", "platform_module"),
    ("assets/state-machine.", ".mjs", "platform_module"),
    ("assets/styles.", ".css", "host_style"),
)
HASHED_ASSET_PATTERN = re.compile(
    r"^assets/[a-z0-9-]+\.[0-9a-f]{64}\.(?:css|js|mjs|wasm)$"
)
LOCAL_PATH_PATTERN = re.compile(rb"(?:/Users/|file:/+(?:Users|home)/|[A-Za-z]:\\)")
SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".py",
    ".map",
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


def replace_exact_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise PackageError(f"{label} must occur exactly once")
    return source.replace(old, new, 1)


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
        "contract",
        "product",
        "milestone",
        "minor",
        "build",
        "patch",
    }:
        raise PackageError("Product version keys are invalid")
    if version["contract"] != "lmdj.product-version.v1" or version["product"] != "lmdj":
        raise PackageError("Product version identity is invalid")
    parts = [version[name] for name in ("milestone", "minor", "build", "patch")]
    if any(type(part) is not int or part < 0 for part in parts):
        raise PackageError("Product Build parts must be non-negative integers")
    return ".".join(str(part) for part in parts)


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
    emcc_version = identity["emcc_version"]
    if emcc_version != EMCC_VERSION:
        raise PackageError("toolchain identity mismatch for emcc_version")
    if identity["initial_memory"] != HEAP_BYTES or identity["allow_memory_growth"] is not False:
        raise PackageError("toolchain identity mismatch for fixed heap")
    return identity


def write_hashed_asset(
    assets_root: Path,
    stem: str,
    suffix: str,
    payload: bytes,
    role: str,
) -> dict:
    digest = sha256(payload)
    filename = f"{stem}.{digest}{suffix}"
    path = assets_root / filename
    path.write_bytes(payload)
    return {
        "path": f"assets/{filename}",
        "bytes": len(payload),
        "sha256": digest,
        "role": role,
    }


def require_file(path: Path) -> Path:
    if not path.is_file() or path.is_symlink():
        raise PackageError(f"runtime asset is missing or unsafe: {path}")
    return path


def build_distribution(
    repo_root: Path,
    runtime_root: Path,
    identity_path: Path,
    dist_root: Path,
) -> None:
    repo_root = repo_root.expanduser().resolve(strict=True)
    runtime_root = runtime_root.expanduser().resolve(strict=True)
    identity_path = identity_path.expanduser().resolve(strict=True)
    requested_dist_root = dist_root.expanduser()
    if not requested_dist_root.is_absolute():
        requested_dist_root = Path.cwd() / requested_dist_root
    requested_dist_root.parent.mkdir(parents=True, exist_ok=True)
    dist_root = requested_dist_root.parent.resolve(strict=True) / requested_dist_root.name
    if not repo_root.is_dir() or not runtime_root.is_dir():
        raise PackageError("repository and runtime roots must be directories")
    if dist_root == Path("/") or dist_root == repo_root:
        raise PackageError(f"unsafe distribution root: {dist_root}")
    initial_target = None
    try:
        initial_target = os.lstat(dist_root)
    except FileNotFoundError:
        pass
    if initial_target is not None:
        if stat.S_ISLNK(initial_target.st_mode):
            raise PackageError(f"distribution root is a symlink: {dist_root}")
        if not stat.S_ISDIR(initial_target.st_mode):
            raise PackageError(f"unsafe existing distribution root: {dist_root}")
        try:
            verify_distribution(dist_root, repo_root)
        except DistributionError as error:
            raise PackageError(
                f"existing distribution is not replaceable: {dist_root}"
            ) from error

    identity = validate_identity(repo_root, identity_path)
    version = read_json(repo_root / "products/lmdj/version.json", "Product version")
    active_product_build = product_build(version)
    host_root = repo_root / "apps/web-runtime-host"
    platform_root = repo_root / "packages/web-runtime-platform/web"
    runtime_js_path = require_file(runtime_root / "lmdj-web-runtime.js")
    runtime_wasm_path = require_file(runtime_root / "lmdj-web-runtime.wasm")

    dist_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".lmdj-web-dist-", dir=dist_root.parent
    ) as temporary:
        staged = Path(temporary)
        assets_root = staged / "assets"
        assets_root.mkdir()
        assets: list[dict] = []

        def write_module(
            source: Path,
            stem: str,
            role: str,
            dependencies: tuple[tuple[str, dict], ...] = (),
        ) -> dict:
            text = require_file(source).read_text(encoding="utf-8")
            for specifier, dependency in dependencies:
                text = replace_exact_once(
                    text,
                    f'"{specifier}"',
                    f'"./{Path(dependency["path"]).name}"',
                    f"{stem} import {specifier}",
                )
            entry = write_hashed_asset(
                assets_root,
                stem,
                ".mjs",
                text.encode("utf-8"),
                role,
            )
            assets.append(entry)
            return entry

        diagnostic_client_entry = write_module(
            platform_root / "diagnostic_client.mjs",
            "diagnostic-client",
            "platform_module",
        )
        diagnostic_project_entry = write_module(
            host_root / "src/diagnostic_project.mjs",
            "diagnostic-project",
            "host_module",
        )
        input_adapters_entry = write_module(
            platform_root / "input_adapters.mjs",
            "input-adapters",
            "platform_module",
        )
        preflight_entry = write_module(
            platform_root / "preflight.mjs",
            "preflight",
            "platform_module",
        )
        protocol_entry = write_module(
            platform_root / "protocol.mjs",
            "protocol",
            "platform_module",
        )
        project_bundle_reader_entry = write_module(
            platform_root / "project_bundle_reader.mjs",
            "project-bundle-reader",
            "platform_module",
            (("./protocol.mjs", protocol_entry),),
        )
        state_machine_entry = write_module(
            platform_root / "state_machine.mjs",
            "state-machine",
            "platform_module",
        )
        runtime_loader_entry = write_module(
            platform_root / "runtime_loader.mjs",
            "runtime-loader",
            "platform_module",
            (("./protocol.mjs", protocol_entry),),
        )
        runtime_session_entry = write_module(
            platform_root / "runtime_session.mjs",
            "runtime-session",
            "platform_module",
            (
                ("./input_adapters.mjs", input_adapters_entry),
                ("./diagnostic_client.mjs", diagnostic_client_entry),
                ("./project_bundle_reader.mjs", project_bundle_reader_entry),
                ("./runtime_loader.mjs", runtime_loader_entry),
                ("./preflight.mjs", preflight_entry),
                ("./protocol.mjs", protocol_entry),
                ("./state_machine.mjs", state_machine_entry),
            ),
        )

        main_text = require_file(host_root / "src/main.mjs").read_text(
            encoding="utf-8"
        )
        for specifier, entry in (
            (
                "../../../packages/web-runtime-platform/web/diagnostic_client.mjs",
                diagnostic_client_entry,
            ),
            (
                "../../../packages/web-runtime-platform/web/input_adapters.mjs",
                input_adapters_entry,
            ),
            (
                "../../../packages/web-runtime-platform/web/runtime_session.mjs",
                runtime_session_entry,
            ),
            ("./diagnostic_project.mjs", diagnostic_project_entry),
        ):
            main_text = replace_exact_once(
                main_text,
                f'"{specifier}"',
                f'"./{Path(entry["path"]).name}"',
                f"main import {specifier}",
            )
        main_entry = write_hashed_asset(
            assets_root,
            "main",
            ".mjs",
            main_text.encode("utf-8"),
            "host_main",
        )
        assets.append(main_entry)

        style_entry = write_hashed_asset(
            assets_root,
            "styles",
            ".css",
            require_file(host_root / "styles.css").read_bytes(),
            "host_style",
        )
        assets.append(style_entry)

        wasm_payload = runtime_wasm_path.read_bytes()
        wasm_entry = write_hashed_asset(
            assets_root,
            "runtime",
            ".wasm",
            wasm_payload,
            "runtime_wasm",
        )
        assets.append(wasm_entry)
        runtime_payload = runtime_js_path.read_bytes()
        try:
            runtime_text = runtime_payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise PackageError("runtime JavaScript is not UTF-8") from error
        original_wasm_name = "lmdj-web-runtime.wasm"
        runtime_text = replace_exact_once(
            runtime_text,
            original_wasm_name,
            Path(wasm_entry["path"]).name,
            "runtime Wasm binding",
        )
        runtime_entry = write_hashed_asset(
            assets_root,
            "runtime",
            ".js",
            runtime_text.encode("utf-8"),
            "runtime_script",
        )
        assets.append(runtime_entry)

        ordered_assets = []
        for prefix, suffix, role in EXPECTED_ASSETS:
            matches = [
                entry for entry in assets
                if entry["role"] == role
                and entry["path"].startswith(prefix)
                and entry["path"].endswith(suffix)
            ]
            if len(matches) != 1:
                raise PackageError("production asset inventory is invalid")
            ordered_assets.append(matches[0])
        manifest = {
            "distribution_contract": DISTRIBUTION_CONTRACT,
            "manifest_version": 1,
            "product_build": active_product_build,
            "host_id": HOST_ID,
            "host_version": HOST_VERSION,
            "platform_version": PLATFORM_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "heap_bytes": HEAP_BYTES,
            "resource_limits": RESOURCE_LIMITS,
            "emscripten": {
                key: identity[key] for key in MANIFEST_TOOLCHAIN_KEYS
            },
            "assets": ordered_assets,
        }
        manifest_bytes = canonical_json(manifest)
        (staged / "host-manifest.json").write_bytes(manifest_bytes)
        manifest_digest = sha256(manifest_bytes)

        index = require_file(host_root / "index.html").read_text(encoding="utf-8")
        index, digest_replacements = re.subn(
            r'(<meta name="lmdj-host-manifest-sha256" content=")[0-9a-f]{64}(">)',
            rf"\g<1>{manifest_digest}\g<2>",
            index,
        )
        if digest_replacements != 1:
            raise PackageError("source index has no unique manifest digest")
        identity_meta = (
            '\n    <meta name="lmdj-host-manifest-path" content="./host-manifest.json">'
            f'\n    <meta name="lmdj-product-build" content="{active_product_build}">'
            f'\n    <meta name="lmdj-host-id" content="{HOST_ID}">'
            f'\n    <meta name="lmdj-host-version" content="{HOST_VERSION}">'
            '\n    <meta name="lmdj-web-runtime-platform-version" '
            f'content="{PLATFORM_VERSION}">'
            f'\n    <meta name="lmdj-host-protocol-version" content="{PROTOCOL_VERSION}">'
        )
        digest_tag = (
            f'<meta name="lmdj-host-manifest-sha256" content="{manifest_digest}">'
        )
        index = replace_exact_once(
            index,
            digest_tag,
            digest_tag + identity_meta,
            "manifest digest metadata",
        )
        index = replace_exact_once(
            index,
            'href="./styles.css"',
            f'href="./{style_entry["path"]}"',
            "stylesheet reference",
        )
        index = replace_exact_once(
            index,
            'src="./src/main.mjs"',
            f'src="./{main_entry["path"]}"',
            "main module reference",
        )
        (staged / "index.html").write_text(
            index, encoding="utf-8", newline="\n"
        )
        verify_distribution(staged, repo_root)

        current_target = None
        try:
            current_target = os.lstat(dist_root)
        except FileNotFoundError:
            pass
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
            try:
                verify_distribution(dist_root, repo_root)
            except DistributionError as error:
                raise PackageError(
                    f"existing distribution is not replaceable: {dist_root}"
                ) from error
        backup = Path(tempfile.mkdtemp(prefix=".lmdj-web-dist-backup-", dir=dist_root.parent))
        backup.rmdir()
        cleanup_backup = True
        try:
            if initial_target is not None:
                os.replace(dist_root, backup)
            try:
                os.replace(staged, dist_root)
            except OSError as error:
                if initial_target is not None:
                    try:
                        os.replace(backup, dist_root)
                    except OSError as rollback_error:
                        cleanup_backup = False
                        raise PackageError(
                            f"distribution replacement failed and rollback failed; "
                            f"previous distribution retained at {backup}"
                        ) from rollback_error
                raise PackageError("distribution replacement failed; previous distribution restored") from error
            if backup.exists():
                shutil.rmtree(backup)
        finally:
            if cleanup_backup and backup.exists() and not backup.is_symlink():
                shutil.rmtree(backup)


def verify_distribution(dist_root: Path, repo_root: Path) -> None:
    try:
        requested_dist_root = dist_root.expanduser()
        if not requested_dist_root.is_absolute():
            requested_dist_root = Path.cwd() / requested_dist_root
        root_status = os.lstat(requested_dist_root)
        if stat.S_ISLNK(root_status.st_mode):
            raise DistributionError("distribution root is a symlink")
        dist_root = requested_dist_root.resolve(strict=True)
        repo_root = repo_root.expanduser().resolve(strict=True)
    except OSError as error:
        raise DistributionError("distribution root is missing") from error
    if not dist_root.is_dir():
        raise DistributionError("distribution root is missing")
    manifest_path = dist_root / "host-manifest.json"
    index_path = dist_root / "index.html"
    if not manifest_path.is_file() or not index_path.is_file():
        raise DistributionError("index or manifest is missing")
    if any(path.is_symlink() for path in dist_root.rglob("*")):
        raise DistributionError("distribution contains a symlink")
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DistributionError("manifest is malformed") from error
    if not isinstance(manifest, dict) or canonical_json(manifest) != manifest_bytes:
        raise DistributionError("manifest is not exact canonical JSON")
    if set(manifest) != {
        "assets",
        "distribution_contract",
        "emscripten",
        "heap_bytes",
        "host_id",
        "host_version",
        "manifest_version",
        "platform_version",
        "product_build",
        "protocol_version",
        "resource_limits",
    }:
        raise DistributionError("manifest root schema is invalid")
    version = read_json(repo_root / "products/lmdj/version.json", "Product version")
    lock = read_json(repo_root / "tools/web-runtime/emscripten.lock.json", "toolchain lock")
    if (
        manifest["distribution_contract"] != DISTRIBUTION_CONTRACT
        or type(manifest["manifest_version"]) is not int
        or manifest["manifest_version"] != 1
        or manifest["product_build"] != product_build(version)
        or manifest["host_id"] != HOST_ID
        or manifest["host_version"] != HOST_VERSION
        or manifest["platform_version"] != PLATFORM_VERSION
        or type(manifest["protocol_version"]) is not int
        or manifest["protocol_version"] != PROTOCOL_VERSION
        or type(manifest["heap_bytes"]) is not int
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
    seen_paths: set[str] = set()
    for entry, expected_asset in zip(assets, EXPECTED_ASSETS, strict=True):
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "bytes",
            "sha256",
            "role",
        }:
            raise DistributionError("manifest asset entry is invalid")
        relative = entry["path"]
        if not isinstance(relative, str) or HASHED_ASSET_PATTERN.fullmatch(relative) is None:
            raise DistributionError("asset path is not content hashed")
        prefix, suffix, role = expected_asset
        if (
            entry["role"] != role
            or type(entry["bytes"]) is not int
            or entry["bytes"] < 1
            or not isinstance(entry["sha256"], str)
            or relative != f"{prefix}{entry['sha256']}{suffix}"
        ):
            raise DistributionError("manifest production inventory is invalid")
        if relative in seen_paths:
            raise DistributionError("manifest contains duplicate asset")
        seen_paths.add(relative)
        path = dist_root / relative
        if not path.is_file():
            raise DistributionError(f"missing asset: {relative}")
        payload = path.read_bytes()
        if entry["bytes"] != len(payload):
            raise DistributionError(f"asset size mismatch: {relative}")
        digest = sha256(payload)
        if entry["sha256"] != digest or f".{digest}." not in path.name:
            raise DistributionError(f"asset hash mismatch: {relative}")
        if LOCAL_PATH_PATTERN.search(payload) is not None or str(repo_root).encode() in payload:
            raise DistributionError(f"absolute local path in asset: {relative}")
        expected_files.add(relative)
    actual_files = {
        path.relative_to(dist_root).as_posix()
        for path in dist_root.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        unexpected = sorted(actual_files - expected_files)
        missing = sorted(expected_files - actual_files)
        raise DistributionError(
            f"distribution inventory mismatch: unexpected={unexpected}, missing={missing}"
        )
    for relative in actual_files:
        path = Path(relative)
        lowered_parts = {part.lower() for part in path.parts}
        if path.suffix.lower() in SOURCE_SUFFIXES:
            raise DistributionError(f"source or source map shipped: {relative}")
        if lowered_parts & {"test", "tests", "fixture", "fixtures", "node_modules"}:
            raise DistributionError(f"test fixture or development dependency shipped: {relative}")
        if path.name in {"server.py", "package.json", "package-lock.json"}:
            raise DistributionError(f"proof server or development dependency shipped: {relative}")
    index = index_path.read_text(encoding="utf-8")
    digest = sha256(manifest_bytes)
    if (
        f'<meta name="lmdj-host-manifest-sha256" content="{digest}">' not in index
    ):
        raise DistributionError("index manifest digest mismatch")
    for exact_meta in (
        '<meta name="lmdj-host-manifest-path" content="./host-manifest.json">',
        f'<meta name="lmdj-product-build" content="{manifest["product_build"]}">',
        f'<meta name="lmdj-host-id" content="{manifest["host_id"]}">',
        f'<meta name="lmdj-host-version" content="{manifest["host_version"]}">',
        '<meta name="lmdj-web-runtime-platform-version" '
        f'content="{manifest["platform_version"]}">',
        f'<meta name="lmdj-host-protocol-version" content="{manifest["protocol_version"]}">',
    ):
        if index.count(exact_meta) != 1:
            raise DistributionError("index identity metadata mismatch")
    main_asset = next(asset for asset in assets if asset["role"] == "host_main")
    style_asset = next(asset for asset in assets if asset["role"] == "host_style")
    if (
        index.count(f'src="./{main_asset["path"]}"') != 1
        or index.count(f'href="./{style_asset["path"]}"') != 1
    ):
        raise DistributionError("index production asset binding mismatch")
    if re.search(r"<script(?![^>]*\bsrc=)[^>]*>", index, re.IGNORECASE):
        raise DistributionError("index contains inline script")
    if LOCAL_PATH_PATTERN.search(index.encode("utf-8")) is not None:
        raise DistributionError("absolute local path in index")


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = UsageParser(
        description="Build the deterministic formal Web Runtime Host distribution"
    )
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--dist-root", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        parser = UsageParser()
        parser.print_usage(sys.stderr)
        return 64
    try:
        options = parse_arguments(arguments)
        build_distribution(
            options.repo_root,
            options.runtime_root,
            options.identity,
            options.dist_root,
        )
    except UsageError:
        return 64
    except (OSError, PackageError, DistributionError) as error:
        print(f"web package error: {error}", file=sys.stderr)
        return 2
    print(f"Web Runtime Host package: PASS ({options.dist_root})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
