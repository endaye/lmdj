#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
JSON_OUTPUT = Path("products/lmdj/generated/web-runtime-identity.json")
MJS_OUTPUT = Path("products/lmdj/generated/web-runtime-identity.mjs")
SAFE_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
PRODUCT_BUILD = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RUNTIME_IDENTITY_REMEDY = (
    "regenerate Runtime identity with python3 "
    "tools/web-runtime/generate_runtime_identity.py --repo-root ."
)
TOOLCHAIN_KEYS = {
    "allow_memory_growth",
    "emcc_version",
    "emscripten_releases_revision",
    "emsdk_revision",
    "emsdk_tag",
    "initial_memory",
    "linker_flags",
    "node",
    "playwright",
}


class IdentityError(RuntimeError):
    pass


def relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(
            repo_root.resolve(strict=False)
        ).as_posix()
    except ValueError:
        return path.name


def product_build_text(value: object) -> str:
    if value is None:
        return "<missing>"
    if not isinstance(value, str) or PRODUCT_BUILD.fullmatch(value) is None:
        return "<invalid>"
    return value


def product_build_mismatch(
    repo_root: Path,
    *,
    expected: str,
    found: object,
    consumer: Path,
    remedy: str | None = None,
) -> IdentityError:
    message = (
        f"Product Build mismatch: expected {expected} from "
        "products/lmdj/version.json, found "
        f"{product_build_text(found)} in {relative_path(repo_root, consumer)}"
    )
    if remedy is not None:
        message = f"{message}; remedy: {remedy}"
    return IdentityError(message)


def read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IdentityError(f"invalid {label}: {path}") from error
    if not isinstance(value, dict):
        raise IdentityError(f"{label} must be an object: {path}")
    return value


def exact_keys(value: dict, expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise IdentityError(f"{label} keys are invalid")


def safe_identity(value: object, label: str) -> str:
    if not isinstance(value, str) or SAFE_IDENTITY.fullmatch(value) is None:
        raise IdentityError(f"{label} is invalid")
    return value


def semver(value: object, label: str) -> str:
    value = safe_identity(value, label)
    if SEMVER.fullmatch(value) is None:
        raise IdentityError(f"{label} is not SemVer")
    return value


def read_product_build(repo_root: Path) -> str:
    value = read_json(repo_root / "products/lmdj/version.json", "Product version")
    exact_keys(
        value,
        {"contract", "product", "milestone", "minor", "build", "patch"},
        "Product version",
    )
    if value["contract"] != "lmdj.product-version.v1" or value["product"] != "lmdj":
        raise IdentityError("Product version identity is invalid")
    parts = [value[key] for key in ("milestone", "minor", "build", "patch")]
    if any(type(part) is not int or part < 0 for part in parts):
        raise IdentityError("Product Build parts are invalid")
    return ".".join(str(part) for part in parts)


def read_module(repo_root: Path, relative: str, expected_id: str) -> dict:
    value = read_json(repo_root / relative, f"{expected_id} manifest")
    exact_keys(
        value,
        {"contract", "module", "version", "api_version", "dependencies"},
        f"{expected_id} manifest",
    )
    if value["contract"] != "lmdj.module.v1" or value["module"] != expected_id:
        raise IdentityError(f"{expected_id} manifest identity is invalid")
    version = semver(value["version"], f"{expected_id} version")
    if type(value["api_version"]) is not int or value["api_version"] < 1:
        raise IdentityError(f"{expected_id} api_version is invalid")
    dependencies = value["dependencies"]
    if not isinstance(dependencies, dict):
        raise IdentityError(f"{expected_id} dependencies are invalid")
    for dependency, dependency_version in dependencies.items():
        safe_identity(dependency, f"{expected_id} dependency")
        semver(dependency_version, f"{expected_id} dependency version")
    return {"id": expected_id, "version": version, "dependencies": dependencies}


def component_versions(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, list):
        raise IdentityError(f"{label} inventory is invalid")
    result: dict[str, str] = {}
    for component in value:
        if not isinstance(component, dict) or not {"id", "version"}.issubset(component):
            raise IdentityError(f"{label} entry is invalid")
        identity = safe_identity(component["id"], f"{label} id")
        version = semver(component["version"], f"{label} version")
        if identity in result:
            raise IdentityError(f"duplicate {label} identity: {identity}")
        result[identity] = version
    return result


def read_assembly_identity(
    repo_root: Path,
    product_build: str,
    components: dict[str, dict],
) -> str:
    assembly_path = repo_root / "products/lmdj/assembly.json"
    assembly = read_json(assembly_path, "Product Assembly")
    lock = read_json(repo_root / "products/lmdj/assembly.lock.json", "Assembly lock")
    exact_keys(
        assembly,
        {"contract", "product", "provider_policy", "modules", "hosts", "providers", "contracts"},
        "Product Assembly",
    )
    exact_keys(
        lock,
        {"assembly_sha256", "contracts", "hosts", "modules", "product", "product_assembly", "providers"},
        "Assembly lock",
    )
    if assembly["contract"] != "lmdj.assembly.v2":
        raise IdentityError("Product Assembly contract is invalid")
    expected_product = {"id": "lmdj", "version": product_build}
    if assembly["product"] != expected_product:
        product = assembly["product"]
        found = product.get("version") if isinstance(product, dict) else None
        raise product_build_mismatch(
            repo_root,
            expected=product_build,
            found=found,
            consumer=assembly_path,
        )
    lock_path = repo_root / "products/lmdj/assembly.lock.json"
    if lock["product"] != expected_product:
        product = lock["product"]
        found = product.get("version") if isinstance(product, dict) else None
        raise product_build_mismatch(
            repo_root,
            expected=product_build,
            found=found,
            consumer=lock_path,
            remedy=(
                "regenerate the compiled assembly and lock with python3 "
                "scripts/version.py lock --version-file "
                "products/lmdj/version.json --assembly "
                "products/lmdj/assembly.json --output "
                "products/lmdj/assembly.lock.json"
            ),
        )
    product_assembly = lock["product_assembly"]
    if not isinstance(product_assembly, dict) or set(product_assembly) != {"id", "version", "sha256"}:
        raise IdentityError("locked Product Assembly identity is invalid")
    if product_assembly["id"] != "lmdj" or product_assembly["version"] != product_build:
        raise product_build_mismatch(
            repo_root,
            expected=product_build,
            found=product_assembly.get("version"),
            consumer=lock_path,
            remedy=(
                "regenerate the compiled assembly and lock with python3 "
                "scripts/version.py lock --version-file "
                "products/lmdj/version.json --assembly "
                "products/lmdj/assembly.json --output "
                "products/lmdj/assembly.lock.json"
            ),
        )
    digest = lock["assembly_sha256"]
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        raise IdentityError("Assembly SHA-256 is invalid")
    actual_digest = hashlib.sha256(assembly_path.read_bytes()).hexdigest()
    if digest != actual_digest:
        raise IdentityError("Assembly lock does not authenticate assembly.json")
    if not isinstance(product_assembly["sha256"], str) or SHA256.fullmatch(product_assembly["sha256"]) is None:
        raise IdentityError("locked Product Assembly SHA-256 is invalid")
    assembly_modules = component_versions(assembly["modules"], "Assembly module")
    assembly_hosts = component_versions(assembly["hosts"], "Assembly Host")
    lock_modules = component_versions(lock["modules"], "locked module")
    lock_hosts = component_versions(lock["hosts"], "locked Host")
    if assembly_modules != lock_modules or assembly_hosts != lock_hosts:
        raise IdentityError("Assembly and lock component inventories differ")
    for identity, component in components.items():
        inventory = assembly_modules if identity == "web-runtime-platform" else assembly_hosts
        if inventory.get(identity) != component["version"]:
            raise IdentityError(f"Assembly version is stale for {identity}")
    platform_version = components["web-runtime-platform"]["version"]
    for host_id in ("creator-web", "web-runtime-host"):
        if components[host_id]["dependencies"].get("web-runtime-platform") != platform_version:
            raise IdentityError(f"{host_id} platform dependency is stale")
    return digest


def read_toolchain(repo_root: Path) -> dict:
    lock = read_json(repo_root / "tools/web-runtime/emscripten.lock.json", "Emscripten lock")
    exact_keys(lock, TOOLCHAIN_KEYS, "Emscripten lock")
    if type(lock["initial_memory"]) is not int or lock["initial_memory"] < 1:
        raise IdentityError("Emscripten initial memory is invalid")
    if type(lock["allow_memory_growth"]) is not bool:
        raise IdentityError("Emscripten memory growth setting is invalid")
    if not isinstance(lock["linker_flags"], list) or not lock["linker_flags"] or not all(
        isinstance(flag, str) and flag for flag in lock["linker_flags"]
    ):
        raise IdentityError("Emscripten linker flags are invalid")
    for key in ("emsdk_tag", "emsdk_revision", "emscripten_releases_revision", "emcc_version", "node", "playwright"):
        if not isinstance(lock[key], str) or not lock[key]:
            raise IdentityError(f"Emscripten lock {key} is invalid")
    return lock


def read_policy(repo_root: Path, components: dict[str, dict], toolchain: dict) -> dict:
    policy = read_json(repo_root / "tools/web-runtime/runtime-identity.json", "Runtime identity policy")
    exact_keys(policy, {"heap_bytes", "hosts", "protocol_version", "resource_limits"}, "Runtime identity policy")
    if type(policy["heap_bytes"]) is not int or policy["heap_bytes"] < 1:
        raise IdentityError("Runtime heap is invalid")
    if policy["heap_bytes"] != toolchain["initial_memory"] or toolchain["allow_memory_growth"] is not False:
        raise IdentityError("Runtime fixed heap differs from Emscripten lock")
    initial_memory_flag = f"-sINITIAL_MEMORY={policy['heap_bytes']}"
    if initial_memory_flag not in toolchain["linker_flags"] or "-sALLOW_MEMORY_GROWTH=0" not in toolchain["linker_flags"]:
        raise IdentityError("Runtime fixed heap linker flags are stale")
    if type(policy["protocol_version"]) is not int or policy["protocol_version"] < 1:
        raise IdentityError("Runtime protocol version is invalid")
    limits = policy["resource_limits"]
    expected_limit_keys = {
        "decoded_float_pcm_bytes_per_bank",
        "decoded_float_pcm_bytes_total",
        "decoded_float_pcm_bytes_resident",
        "ingest_source_bytes",
        "ingest_decoded_frames",
        "ingest_channels",
        "imported_wav_bytes",
        "perform_recording_frames",
        "perform_recording_queue_batches",
    }
    if not isinstance(limits, dict) or set(limits) != expected_limit_keys or any(
        type(value) is not int or value < 1 for value in limits.values()
    ):
        raise IdentityError("Runtime resource limits are invalid")
    hosts = policy["hosts"]
    if not isinstance(hosts, dict) or set(hosts) != {"creator-web", "web-runtime-host"}:
        raise IdentityError("Runtime Host policy is invalid")
    generated_hosts = {}
    for host_id, host_policy in hosts.items():
        if not isinstance(host_policy, dict):
            raise IdentityError(f"{host_id} policy is invalid")
        exact_keys(host_policy, {"compatible_hosts", "distribution_contract", "expected_assets"}, f"{host_id} policy")
        contract = safe_identity(host_policy["distribution_contract"], f"{host_id} distribution contract")
        compatible_ids = host_policy["compatible_hosts"]
        if not isinstance(compatible_ids, list) or len(set(compatible_ids)) != len(compatible_ids):
            raise IdentityError(f"{host_id} compatible Hosts are invalid")
        compatible_hosts = []
        for compatible_id in compatible_ids:
            if compatible_id == host_id or compatible_id not in components:
                raise IdentityError(f"{host_id} compatible Host is invalid")
            compatible_hosts.append({
                "host_id": compatible_id,
                "host_version": components[compatible_id]["version"],
            })
        assets = host_policy["expected_assets"]
        if not isinstance(assets, list) or not assets:
            raise IdentityError(f"{host_id} expected assets are invalid")
        seen_assets = set()
        for asset in assets:
            if not isinstance(asset, dict) or set(asset) != {"prefix", "suffix", "role"}:
                raise IdentityError(f"{host_id} expected asset is invalid")
            entry = tuple(asset[key] for key in ("prefix", "suffix", "role"))
            if not all(isinstance(value, str) and value for value in entry) or entry in seen_assets:
                raise IdentityError(f"{host_id} expected asset is invalid")
            seen_assets.add(entry)
        generated_hosts[host_id] = {
            "compatible_hosts": compatible_hosts,
            "distribution_contract": contract,
            "expected_assets": assets,
            "id": host_id,
            "version": components[host_id]["version"],
        }
    return {
        "heap_bytes": policy["heap_bytes"],
        "hosts": generated_hosts,
        "protocol_version": policy["protocol_version"],
        "resource_limits": limits,
    }


def generate(repo_root: Path) -> dict:
    repo_root = repo_root.resolve(strict=True)
    product_build = read_product_build(repo_root)
    components = {
        "web-runtime-platform": read_module(
            repo_root,
            "packages/web-runtime-platform/module.json",
            "web-runtime-platform",
        ),
        "creator-web": read_module(
            repo_root, "apps/creator-web/module.json", "creator-web"
        ),
        "web-runtime-host": read_module(
            repo_root, "apps/web-runtime-host/module.json", "web-runtime-host"
        ),
    }
    assembly_sha256 = read_assembly_identity(
        repo_root, product_build, components
    )
    toolchain = read_toolchain(repo_root)
    policy = read_policy(repo_root, components, toolchain)
    return {
        "assembly_sha256": assembly_sha256,
        "emscripten": toolchain,
        "heap_bytes": policy["heap_bytes"],
        "hosts": policy["hosts"],
        "platform": {
            "id": "web-runtime-platform",
            "version": components["web-runtime-platform"]["version"],
        },
        "product_build": product_build,
        "protocol_version": policy["protocol_version"],
        "resource_limits": policy["resource_limits"],
    }


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def mjs_bytes(value: object) -> bytes:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (
        "function deepFreeze(value) {\n"
        "  for (const child of Object.values(value)) {\n"
        "    if (child !== null && typeof child === \"object\") deepFreeze(child);\n"
        "  }\n"
        "  return Object.freeze(value);\n"
        "}\n"
        f"export const WEB_RUNTIME_IDENTITY = deepFreeze({encoded});\n"
    ).encode("utf-8")


def output_product_build(path: Path, content: bytes) -> object:
    try:
        if path.suffix == ".json":
            value = json.loads(content)
        elif path.suffix == ".mjs":
            prefix = mjs_bytes({}).split(b"{}", 1)[0]
            suffix = b");\n"
            if not content.startswith(prefix) or not content.endswith(suffix):
                return "<invalid>"
            value = json.loads(content[len(prefix):-len(suffix)])
        else:
            return "<invalid>"
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "<invalid>"
    if not isinstance(value, dict):
        return "<invalid>"
    found = value.get("product_build")
    return found if product_build_text(found) == found else "<invalid>"


def write_or_check(repo_root: Path, check: bool) -> None:
    identity = generate(repo_root)
    outputs = {
        repo_root / JSON_OUTPUT: canonical_json(identity),
        repo_root / MJS_OUTPUT: mjs_bytes(identity),
    }
    for path, expected in outputs.items():
        if check:
            try:
                actual = path.read_bytes()
            except OSError as error:
                raise product_build_mismatch(
                    repo_root,
                    expected=identity["product_build"],
                    found=None,
                    consumer=path,
                    remedy=RUNTIME_IDENTITY_REMEDY,
                ) from error
            if actual != expected:
                found = output_product_build(path, actual)
                if found != identity["product_build"]:
                    raise product_build_mismatch(
                        repo_root,
                        expected=identity["product_build"],
                        found=found,
                        consumer=path,
                        remedy=RUNTIME_IDENTITY_REMEDY,
                    )
                raise IdentityError(
                    "generated Runtime identity is stale in "
                    f"{relative_path(repo_root, path)}; remedy: "
                    f"{RUNTIME_IDENTITY_REMEDY}"
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    try:
        write_or_check(args.repo_root, args.check)
    except (IdentityError, OSError) as error:
        print(f"Runtime identity error: {error}", file=sys.stderr)
        return 2
    action = "verified" if args.check else "generated"
    print(f"Runtime identity: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
