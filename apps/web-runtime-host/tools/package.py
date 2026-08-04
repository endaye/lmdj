#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path


HOST_VERSION = "1.0.0"
PROTOCOL_VERSION = 1
HEAP_BYTES = 536_870_912
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
    if not isinstance(emcc_version, str) or re.search(
        r"(?<![0-9.])6\.0\.5(?![0-9.])", emcc_version
    ) is None:
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
    dist_root = dist_root.expanduser().resolve(strict=False)
    if not repo_root.is_dir() or not runtime_root.is_dir():
        raise PackageError("repository and runtime roots must be directories")
    if dist_root == Path("/") or dist_root == repo_root:
        raise PackageError(f"unsafe distribution root: {dist_root}")
    if dist_root.exists():
        if dist_root.is_symlink() or not dist_root.is_dir():
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
    runtime_js_path = require_file(runtime_root / "lmdj-web-runtime-host.js")
    runtime_wasm_path = require_file(runtime_root / "lmdj-web-runtime-host.wasm")

    dist_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".lmdj-web-dist-", dir=dist_root.parent
    ) as temporary:
        staged = Path(temporary)
        assets_root = staged / "assets"
        assets_root.mkdir()
        assets: list[dict] = []

        leaf_assets: dict[str, dict] = {}
        for name in (
            "input_adapters.mjs",
            "preflight.mjs",
            "protocol.mjs",
            "state_machine.mjs",
        ):
            payload = require_file(host_root / "src" / name).read_bytes()
            entry = write_hashed_asset(
                assets_root,
                Path(name).stem.replace("_", "-"),
                ".mjs",
                payload,
                "host_module",
            )
            leaf_assets[name] = entry
            assets.append(entry)

        main_text = require_file(host_root / "src/main.mjs").read_text(
            encoding="utf-8"
        )
        for name, entry in leaf_assets.items():
            main_text = main_text.replace(
                f'"./{name}"', f'"./{Path(entry["path"]).name}"'
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
        original_wasm_name = "lmdj-web-runtime-host.wasm"
        if original_wasm_name not in runtime_text:
            raise PackageError("runtime JavaScript does not bind its Wasm asset")
        runtime_text = runtime_text.replace(
            original_wasm_name, Path(wasm_entry["path"]).name
        )
        runtime_entry = write_hashed_asset(
            assets_root,
            "runtime",
            ".js",
            runtime_text.encode("utf-8"),
            "runtime_script",
        )
        assets.append(runtime_entry)

        manifest = {
            "manifest_version": 1,
            "product_build": active_product_build,
            "host_version": HOST_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "heap_bytes": HEAP_BYTES,
            "resource_limits": RESOURCE_LIMITS,
            "emscripten": {
                key: identity[key] for key in MANIFEST_TOOLCHAIN_KEYS
            },
            "assets": sorted(assets, key=lambda entry: entry["path"]),
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
            f'\n    <meta name="lmdj-host-version" content="{HOST_VERSION}">'
            f'\n    <meta name="lmdj-host-protocol-version" content="{PROTOCOL_VERSION}">'
        )
        digest_tag = (
            f'<meta name="lmdj-host-manifest-sha256" content="{manifest_digest}">'
        )
        index = index.replace(digest_tag, digest_tag + identity_meta, 1)
        index = index.replace(
            'href="./styles.css"', f'href="./{style_entry["path"]}"', 1
        )
        index = index.replace(
            'src="./src/main.mjs"', f'src="./{main_entry["path"]}"', 1
        )
        (staged / "index.html").write_text(
            index, encoding="utf-8", newline="\n"
        )
        verify_distribution(staged, repo_root)

        if dist_root.exists():
            try:
                verify_distribution(dist_root, repo_root)
            except DistributionError as error:
                raise PackageError(
                    f"existing distribution is not replaceable: {dist_root}"
                ) from error
            shutil.rmtree(dist_root)
        shutil.copytree(staged, dist_root)


def verify_distribution(dist_root: Path, repo_root: Path) -> None:
    try:
        dist_root = dist_root.expanduser().resolve(strict=True)
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
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise DistributionError("manifest assets are missing")
    expected_files = {"index.html", "host-manifest.json"}
    seen_paths: set[str] = set()
    for entry in assets:
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
