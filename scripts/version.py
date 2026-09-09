#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_FIELDS = ("modules", "hosts", "providers", "contracts")
ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(\.[a-z0-9-]+|-[a-z0-9-]+)*$"
)
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PRODUCT_BUILD_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
LOCK_REMEDY = (
    "regenerate the compiled assembly and lock with python3 "
    "scripts/version.py lock --version-file products/lmdj/version.json "
    "--assembly products/lmdj/assembly.json --output "
    "products/lmdj/assembly.lock.json"
)


@dataclass(frozen=True, order=True)
class ProductVersion:
    milestone: int
    minor: int
    build: int
    patch: int

    def __post_init__(self) -> None:
        fields = {
            "milestone": self.milestone,
            "minor": self.minor,
            "build": self.build,
            "patch": self.patch,
        }
        for name, value in fields.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer")
        if self.milestone < 1:
            raise ValueError("milestone must be >= 1")
        if min(self.minor, self.build, self.patch) < 0:
            raise ValueError("minor, build, and patch must be >= 0")
        if self.build == 0 and self.patch != 0:
            raise ValueError("patch requires a non-zero build")

    def __str__(self) -> str:
        return (
            f"{self.milestone}.{self.minor}."
            f"{self.build}.{self.patch}"
        )

    def product_tag(self) -> str:
        return f"lmdj-v{self}"

    def display(self, channel: str, revision: str) -> str:
        if channel not in {"canary", "dev", "beta", "stable"}:
            raise ValueError(f"invalid channel: {channel}")
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("revision must be a full lowercase Git SHA")
        return f"{self} · {channel} · g{revision[:8]}"


def load_version(path: str | Path) -> ProductVersion:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    expected_keys = {
        "contract",
        "product",
        "milestone",
        "minor",
        "build",
        "patch",
    }
    if not isinstance(data, dict) or set(data) != expected_keys:
        raise ValueError("invalid product version document shape")
    if data["contract"] != "lmdj.product-version.v1":
        raise ValueError("unsupported product version contract")
    if data["product"] != "lmdj":
        raise ValueError("unexpected product id")
    return ProductVersion(
        data["milestone"],
        data["minor"],
        data["build"],
        data["patch"],
    )


def _load_object(path: str | Path, label: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("git revision must be a full lowercase SHA")
    return revision


def _repo_relative(path: str | Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return candidate.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        pass
    roots = {"apps", "contracts", "packages", "products", "providers", "scripts", "tools"}
    for index, part in enumerate(candidate.parts):
        if part in roots:
            return PurePosixPath(*candidate.parts[index:]).as_posix()
    return candidate.name


def _product_build_text(value: object) -> str:
    if value is None:
        return "<missing>"
    if not isinstance(value, str) or PRODUCT_BUILD_PATTERN.fullmatch(value) is None:
        return "<invalid>"
    return value


def _product_build_mismatch(
    *,
    expected: ProductVersion,
    authority: str | Path,
    found: object,
    consumer: str | Path,
    remedy: str | None = None,
) -> str:
    message = (
        f"Product Build mismatch: expected {expected} from "
        f"{_repo_relative(authority)}, found {_product_build_text(found)} in "
        f"{_repo_relative(consumer)}"
    )
    if remedy is not None:
        return f"{message}; remedy: {remedy}"
    return message


def _verify_assembly(
    version: ProductVersion,
    assembly_path: str | Path,
    version_path: str | Path = "products/lmdj/version.json",
) -> dict[str, Any]:
    assembly = _load_object(assembly_path, "assembly")
    if assembly.get("contract") != "lmdj.assembly.v2":
        raise ValueError("unsupported assembly contract")
    product = assembly.get("product")
    if not isinstance(product, dict):
        raise ValueError("assembly.product must be an object")
    if product.get("id") != "lmdj":
        raise ValueError("assembly product id does not match lmdj")
    if product.get("version") != str(version):
        raise ValueError(
            _product_build_mismatch(
                expected=version,
                authority=version_path,
                found=product.get("version"),
                consumer=assembly_path,
                remedy=(
                    "update the reviewed products/lmdj/assembly.json "
                    "declaration to the approved Product Build, then "
                    f"{LOCK_REMEDY}"
                ),
            )
        )
    if set(assembly) != {
        "contract",
        "product",
        "modules",
        "hosts",
        "providers",
        "contracts",
        "provider_policy",
    }:
        raise ValueError("invalid assembly document shape")
    if set(product) != {"id", "version"}:
        raise ValueError("invalid assembly product shape")
    _verify_provider_policy(assembly.get("provider_policy"))
    for field in COMPONENT_FIELDS:
        _component_inventory(assembly, field, "assembly")
    return assembly


def _verify_provider_policy(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "allowed_regions",
        "allowed_data_classifications",
        "granted_permissions",
    }:
        raise ValueError("invalid assembly Provider policy shape")
    for field, members in value.items():
        if (
            not isinstance(members, list)
            or any(
                not isinstance(member, str) or not member
                for member in members
            )
            or len(set(members)) != len(members)
        ):
            raise ValueError(f"invalid assembly Provider policy field: {field}")


def _component_inventory(
    document: dict[str, Any],
    field: str,
    label: str,
) -> dict[str, str]:
    components = document.get(field)
    if not isinstance(components, list):
        raise ValueError(f"{label} {field} must be an array")
    inventory: dict[str, str] = {}
    for component in components:
        if not isinstance(component, dict):
            raise ValueError(f"{label} {field} entries must be objects")
        expected_keys = (
            {"id", "version", "capabilities", "model_identity"}
            if field == "providers"
            else {"id", "version"}
        )
        if set(component) != expected_keys:
            raise ValueError(f"{label} {field} entry shape is invalid")
        component_id = component.get("id")
        component_version = component.get("version")
        if (
            not isinstance(component_id, str)
            or ID_PATTERN.fullmatch(component_id) is None
        ):
            raise ValueError(f"{label} {field} entry requires an id")
        if (
            not isinstance(component_version, str)
            or SEMVER_PATTERN.fullmatch(component_version) is None
        ):
            raise ValueError(
                f"{label} {field} entry requires a version"
            )
        if field == "providers":
            capabilities = component["capabilities"]
            if not isinstance(capabilities, list):
                raise ValueError("assembly Provider capabilities are invalid")
            capability_ids: set[tuple[str, str]] = set()
            for capability in capabilities:
                if (
                    not isinstance(capability, dict)
                    or set(capability) != {"id", "version"}
                    or not isinstance(capability["id"], str)
                    or ID_PATTERN.fullmatch(capability["id"]) is None
                    or not isinstance(capability["version"], str)
                    or SEMVER_PATTERN.fullmatch(capability["version"]) is None
                    or (
                        capability["id"],
                        capability["version"],
                    )
                    in capability_ids
                ):
                    raise ValueError(
                        "assembly Provider capability is invalid"
                    )
                capability_ids.add(
                    (capability["id"], capability["version"])
                )
            model = component["model_identity"]
            if model is not None and (
                not isinstance(model, dict)
                or set(model) != {"id", "version", "artifact_sha256"}
                or not isinstance(model["id"], str)
                or ID_PATTERN.fullmatch(model["id"]) is None
                or not isinstance(model["version"], str)
                or not model["version"]
                or not isinstance(model["artifact_sha256"], str)
                or SHA256_PATTERN.fullmatch(model["artifact_sha256"]) is None
            ):
                raise ValueError(
                    "assembly Provider model identity is invalid"
                )
        if component_id in inventory:
            raise ValueError(
                f"{label} {field} contains duplicate id {component_id}"
            )
        inventory[component_id] = component_version
    return inventory


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _source_package_sha256(
    format_name: str,
    identity: dict[str, str],
    paths: list[Path],
    *,
    repo_root: Path | None = None,
    content_overrides: dict[Path, bytes] | None = None,
) -> str:
    resolved_repo_root = REPO_ROOT if repo_root is None else repo_root
    overrides = {} if content_overrides is None else content_overrides
    files = []
    for path in sorted(paths):
        if path not in overrides and (not path.is_file() or path.is_symlink()):
            raise ValueError(f"source-package file is unavailable: {path}")
        if path in overrides and path.is_symlink():
            raise ValueError(f"source-package file is unavailable: {path}")
        try:
            relative = path.relative_to(resolved_repo_root).as_posix()
        except ValueError as error:
            raise ValueError(
                f"source-package file is outside the repository: {path}"
            ) from error
        digest = (
            hashlib.sha256(overrides[path]).hexdigest()
            if path in overrides
            else _sha256(path)
        )
        files.append({"path": relative, "sha256": digest})
    document = {
        "files": files,
        "format": format_name,
        **identity,
    }
    return hashlib.sha256(_canonical_json(document).encode("utf-8")).hexdigest()


def _sanitize_cpp_scope_source(source: str) -> str:
    sanitized: list[str] = []
    index = 0
    state = "code"
    while index < len(source):
        current = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if current == "/" and following == "/":
                sanitized.extend((" ", " "))
                index += 2
                state = "line-comment"
                continue
            if current == "/" and following == "*":
                sanitized.extend((" ", " "))
                index += 2
                state = "block-comment"
                continue
            if current == "R" and following == '"':
                raise ValueError("raw C++ string literals are unsupported")
            if current in {'"', "'"}:
                sanitized.append(" ")
                index += 1
                state = "string" if current == '"' else "character"
                continue
            sanitized.append(current)
            index += 1
            continue
        if state == "line-comment":
            if current == "\n":
                sanitized.append("\n")
                state = "code"
            else:
                sanitized.append(" ")
            index += 1
            continue
        if state == "block-comment":
            if current == "*" and following == "/":
                sanitized.extend((" ", " "))
                index += 2
                state = "code"
                continue
            sanitized.append("\n" if current == "\n" else " ")
            index += 1
            continue
        if current == "\\" and following:
            sanitized.extend((" ", "\n" if following == "\n" else " "))
            index += 2
            continue
        if (
            (state == "string" and current == '"')
            or (state == "character" and current == "'")
        ):
            sanitized.append(" ")
            index += 1
            state = "code"
            continue
        sanitized.append("\n" if current == "\n" else " ")
        index += 1
    if state not in {"code", "line-comment"}:
        raise ValueError("unterminated C++ comment or literal")
    return "".join(sanitized)


def _cpp_brace_depths(source: str) -> list[int]:
    depths: list[int] = []
    depth = 0
    for character in source:
        depths.append(depth)
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced C++ braces")
    if depth != 0:
        raise ValueError("unbalanced C++ braces")
    depths.append(depth)
    return depths


def _provider_registration_symbol(source: str, provider_id: str) -> str:
    scope_error = ValueError(
        f"Provider {provider_id} factory.hpp must declare exactly one "
        "registration symbol directly inside its unique global namespace "
        "lmdj::providers block before assembly lock generation; compiled "
        "assembly and assembly.lock.json were not changed"
    )
    try:
        sanitized = _sanitize_cpp_scope_source(source)
        brace_depths = _cpp_brace_depths(sanitized)
    except ValueError as error:
        raise scope_error from error
    namespace_matches = list(
        re.finditer(
            r"\bnamespace[ \t\r\n]+lmdj[ \t\r\n]*::"
            r"[ \t\r\n]*providers[ \t\r\n]*\{",
            sanitized,
        )
    )
    if len(namespace_matches) != 1:
        raise scope_error
    opening_brace = namespace_matches[0].end() - 1
    if brace_depths[opening_brace] != 0:
        raise scope_error
    closing_brace = next(
        (
            index
            for index in range(opening_brace + 1, len(sanitized))
            if sanitized[index] == "}" and brace_depths[index] == 1
        ),
        None,
    )
    if closing_brace is None:
        raise scope_error

    declaration_pattern = (
        r"(?m)^[ \t]*provider::ProviderRegistration[ \t]+"
        r"([A-Za-z_][A-Za-z0-9_]*)[ \t]*\([ \t]*\)[ \t]*;[ \t]*$"
    )
    declarations = list(re.finditer(declaration_pattern, sanitized))
    if len(declarations) != 1:
        raise scope_error
    declaration = declarations[0]
    if not (
        opening_brace < declaration.start() < closing_brace
        and brace_depths[declaration.start()] == 1
    ):
        raise scope_error
    return declaration.group(1)


def _provider_factory_declaration(
    provider_id: str,
    module_path: Path,
) -> tuple[Path, str, str]:
    provider_root = module_path.parent
    factory_headers = sorted(provider_root.glob("include/**/factory.hpp"))
    if (
        len(factory_headers) != 1
        or not factory_headers[0].is_file()
        or factory_headers[0].is_symlink()
    ):
        raise ValueError(
            f"Provider {provider_id} factory.hpp must resolve exactly once "
            "before assembly lock generation; compiled assembly and "
            "assembly.lock.json were not changed"
        )
    factory_header = factory_headers[0]
    try:
        include_path = factory_header.relative_to(
            provider_root / "include"
        ).as_posix()
    except ValueError as error:
        raise ValueError(
            f"Provider {provider_id} factory.hpp must be inside its include "
            "directory before assembly lock generation; compiled assembly "
            "and assembly.lock.json were not changed"
        ) from error
    source = factory_header.read_text(encoding="utf-8")
    symbol = _provider_registration_symbol(source, provider_id)
    return factory_header, include_path, f"lmdj::providers::{symbol}"


def _provider_source_package_sha256(
    provider_id: str,
    provider_version: str,
    module_path: Path,
    *,
    repo_root: Path | None = None,
) -> str:
    resolved_repo_root = REPO_ROOT if repo_root is None else repo_root
    provider_root = module_path.parent
    factory_header, _, _ = _provider_factory_declaration(
        provider_id,
        module_path,
    )
    return _source_package_sha256(
        "provider-source-package",
        {
            "provider_id": provider_id,
            "provider_version": provider_version,
        },
        sorted({
            factory_header,
            module_path,
            provider_root / "src/provider.cpp",
            *provider_root.glob("include/**/*.hpp"),
            *provider_root.glob("src/**/*.cpp"),
        }),
        repo_root=resolved_repo_root,
    )


def _product_assembly_source_package_sha256(
    version: ProductVersion,
    compiled_assembly_bytes: bytes | None = None,
) -> str:
    compiled_assembly_path = (
        REPO_ROOT / "products/lmdj/src/compiled_assembly.cpp"
    )
    return _source_package_sha256(
        "product-assembly-source-package",
        {
            "product_id": "lmdj",
            "product_version": str(version),
        },
        [
            REPO_ROOT / "products/lmdj/CMakeLists.txt",
            compiled_assembly_path,
        ],
        content_overrides=(
            {}
            if compiled_assembly_bytes is None
            else {compiled_assembly_path: compiled_assembly_bytes}
        ),
    )


def _component_source(field: str, component_id: str) -> Path:
    roots = {
        "modules": REPO_ROOT / "packages",
        "hosts": REPO_ROOT / "apps",
        "providers": REPO_ROOT / "providers",
    }
    if field in roots:
        matches = []
        for candidate in sorted(roots[field].glob("*/module.json")):
            source = _load_object(candidate, f"{field} source")
            if source.get("module") == component_id:
                matches.append(candidate)
        if len(matches) != 1:
            raise ValueError(
                f"{field} component {component_id} must resolve exactly once"
            )
        path = matches[0]
    elif field == "contracts":
        matches = sorted(
            (REPO_ROOT / "contracts").glob(
                f"*/{component_id}.schema.json"
            )
        )
        matches += sorted((REPO_ROOT / "contracts").glob(f"*/{component_id}.md"))
        if len(matches) != 1:
            raise ValueError(
                f"contract {component_id} must resolve to exactly one source; remedy: reconcile schema/profile inventory"
            )
        path = matches[0]
    else:
        raise ValueError(f"unknown assembly component field: {field}")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing component source for {component_id}")
    return path


def _validate_component_source(
    field: str,
    component_id: str,
    component_version: str,
    path: Path,
) -> None:
    if field == "contracts" and path.suffix == ".md":
        match = re.match(r"\A---\ncontract_id: ([a-z0-9.-]+)\ncontract_version: ([0-9]+\.[0-9]+\.[0-9]+)\nmedia_type: ([a-z0-9.+/-]+)\n---\n", path.read_text(encoding="utf-8"))
        if not match or match[1] != component_id or match[2] != component_version or path.stem != component_id:
            raise ValueError(f"contract profile identity mismatch for {component_id}; remedy: restore the approved profile frontmatter")
        return
    source = _load_object(path, f"{field} source")
    if field == "contracts":
        source_id = path.name.removesuffix(".schema.json")
        if source_id != component_id:
            raise ValueError(f"contract source id mismatch for {component_id}")
        if source.get("x-lmdj-contract-version") != component_version:
            raise ValueError(
                f"contract source version mismatch for {component_id}"
            )
        return
    if source.get("contract") != "lmdj.module.v1":
        raise ValueError(f"invalid module manifest for {component_id}")
    if (
        source.get("module") != component_id
        or source.get("version") != component_version
    ):
        raise ValueError(f"module source identity mismatch for {component_id}")


def _cpp_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_compiled_assembly(
    version: ProductVersion,
    assembly: dict[str, Any],
) -> bytes:
    assembly_contract = next(
        (
            component
            for component in assembly["contracts"]
            if component["id"] == assembly["contract"]
        ),
        None,
    )
    if assembly_contract is None:
        raise ValueError(
            "compiled assembly cannot resolve the Assembly Contract before "
            "assembly lock generation; compiled assembly and "
            "assembly.lock.json were not changed"
        )
    assembly_schema = _component_source(
        "contracts",
        assembly_contract["id"],
    )
    _validate_component_source(
        "contracts",
        assembly_contract["id"],
        assembly_contract["version"],
        assembly_schema,
    )

    provider_wiring: list[tuple[dict[str, Any], str, str]] = []
    for provider in assembly["providers"]:
        module_path = _component_source("providers", provider["id"])
        _validate_component_source(
            "providers",
            provider["id"],
            provider["version"],
            module_path,
        )
        _, include_path, symbol = _provider_factory_declaration(
            provider["id"],
            module_path,
        )
        provider_wiring.append((provider, include_path, symbol))

    include_paths = [include for _, include, _ in provider_wiring]
    if len(set(include_paths)) != len(include_paths):
        raise ValueError(
            "Provider factory.hpp include paths must be unique before "
            "assembly lock generation; compiled assembly and "
            "assembly.lock.json were not changed"
        )

    lines = [
        "#include <lmdj/facade/assembly_loader.hpp>",
        "",
        "#include <utility>",
        "",
    ]
    lines.extend(f"#include <{path}>" for path in sorted(include_paths))
    lines.extend(
        [
            "",
            "namespace {",
            "",
            "lmdj::facade::CompiledAssemblyCatalog lmdj_catalog() {",
            "  using lmdj::facade::CompiledComponent;",
            "  using lmdj::facade::CompiledProvider;",
            "  return lmdj::facade::CompiledAssemblyCatalog{",
            f"      {_cpp_string(assembly['product']['id'])},",
            f"      {_cpp_string(str(version))},",
            f"      {_cpp_string(_sha256(assembly_schema))},",
        ]
    )
    for field in ("modules", "hosts", "contracts"):
        lines.append("      {")
        for component in assembly[field]:
            lines.append(
                "          CompiledComponent{"
                f"{_cpp_string(component['id'])}, "
                f"{_cpp_string(component['version'])}"
                "},"
            )
        lines.append("      },")

    lines.append("      {")
    for provider, _, symbol in provider_wiring:
        lines.extend(
            [
                "          CompiledProvider{",
                f"              {_cpp_string(provider['id'])},",
                f"              {_cpp_string(provider['version'])},",
                f"              {symbol},",
            ]
        )
        model = provider["model_identity"]
        if model is None:
            lines.append("              std::nullopt,")
        else:
            lines.extend(
                [
                    "              lmdj::provider::ModelIdentity{",
                    f"                  {_cpp_string(model['id'])},",
                    f"                  {_cpp_string(model['version'])},",
                    "                  "
                    f"{_cpp_string(model['artifact_sha256'])},",
                    "              },",
                ]
            )
        lines.append("          },")
    lines.extend(
        [
            "      },",
            "  };",
            "}",
            "",
            "struct ProductAssemblyInstaller {",
            "  ProductAssemblyInstaller() {",
            "    lmdj::facade::install_compiled_assembly_catalog(lmdj_catalog());",
            "  }",
            "};",
            "",
            "ProductAssemblyInstaller installer;",
            "",
            "}  // namespace",
        ]
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _lock_document(
    version: ProductVersion,
    assembly_path: str | Path,
    assembly: dict[str, Any],
    compiled_assembly_bytes: bytes | None = None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "product": {"id": "lmdj", "version": str(version)},
        "product_assembly": {
            "id": "lmdj",
            "version": str(version),
            "sha256": _product_assembly_source_package_sha256(
                version,
                compiled_assembly_bytes,
            ),
        },
        "assembly_sha256": _sha256(Path(assembly_path)),
    }
    for field in COMPONENT_FIELDS:
        locked: list[dict[str, str]] = []
        components = assembly[field]
        for component in sorted(components, key=lambda value: value["id"]):
            component_id = component["id"]
            component_version = component["version"]
            source = _component_source(field, component_id)
            _validate_component_source(
                field,
                component_id,
                component_version,
                source,
            )
            locked.append(
                {
                    "id": component_id,
                    "version": component_version,
                    "sha256": (
                        _provider_source_package_sha256(
                            component_id,
                            component_version,
                            source,
                        )
                        if field == "providers"
                        else _sha256(source)
                    ),
                }
            )
        document[field] = locked
    return document


def _write_canonical(path: str | Path, value: object) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(_canonical_json(value), encoding="utf-8")
    temporary.replace(output)


def _prepare_temporary_file(target: Path, content: bytes, mode: int) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _write_generated_pair(
    compiled_path: Path,
    compiled_bytes: bytes,
    lock_path: Path,
    lock_bytes: bytes,
) -> None:
    targets = [(compiled_path, compiled_bytes), (lock_path, lock_bytes)]
    if compiled_path.resolve(strict=False) == lock_path.resolve(strict=False):
        raise ValueError(
            "compiled assembly and assembly lock output must be different files"
        )

    originals: dict[Path, tuple[bytes | None, int]] = {}
    temporaries: dict[Path, Path] = {}
    for target, content in targets:
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError(
                f"generated assembly destination must be a real file: {target}"
            )
        original = target.read_bytes() if target.exists() else None
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        originals[target] = (original, mode)
        try:
            temporaries[target] = _prepare_temporary_file(
                target,
                content,
                mode,
            )
        except Exception:
            for temporary in temporaries.values():
                temporary.unlink(missing_ok=True)
            raise

    replaced: list[Path] = []
    try:
        for target, _ in targets:
            temporaries[target].replace(target)
            replaced.append(target)
    except OSError as error:
        rollback_error: OSError | None = None
        for target in reversed(replaced):
            original, mode = originals[target]
            restoration: Path | None = None
            try:
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    restoration = _prepare_temporary_file(
                        target,
                        original,
                        mode,
                    )
                    restoration.replace(target)
            except OSError as current_error:
                rollback_error = current_error
            finally:
                if restoration is not None:
                    restoration.unlink(missing_ok=True)
        if rollback_error is not None:
            raise OSError(
                "failed to roll back compiled assembly and assembly lock"
            ) from rollback_error
        raise error
    finally:
        for temporary in temporaries.values():
            temporary.unlink(missing_ok=True)


def generate_lock(
    version_file: str | Path,
    assembly_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    version = load_version(version_file)
    assembly = _verify_assembly(version, assembly_path, version_file)
    compiled_path = REPO_ROOT / "products/lmdj/src/compiled_assembly.cpp"
    compiled_bytes = _render_compiled_assembly(version, assembly)
    lock = _lock_document(
        version,
        assembly_path,
        assembly,
        compiled_bytes,
    )
    lock_bytes = _canonical_json(lock).encode("utf-8")
    _write_generated_pair(
        compiled_path,
        compiled_bytes,
        Path(output_path),
        lock_bytes,
    )
    return lock


def _verify_lock(
    version: ProductVersion,
    assembly_path: str | Path,
    assembly: dict[str, Any],
    lock_path: str | Path,
    version_path: str | Path = "products/lmdj/version.json",
) -> None:
    lock = _load_object(lock_path, "assembly lock")
    for field in ("product", "product_assembly"):
        identity = lock.get(field)
        found = identity.get("version") if isinstance(identity, dict) else None
        if found != str(version):
            raise ValueError(
                _product_build_mismatch(
                    expected=version,
                    authority=version_path,
                    found=found,
                    consumer=lock_path,
                    remedy=LOCK_REMEDY,
                )
            )

    compiled_path = REPO_ROOT / "products/lmdj/src/compiled_assembly.cpp"
    expected_compiled = _render_compiled_assembly(version, assembly)
    actual_compiled = compiled_path.read_bytes()
    if actual_compiled != expected_compiled:
        try:
            compiled_text = actual_compiled.decode("utf-8")
        except UnicodeDecodeError:
            compiled_text = ""
        match = re.search(
            r'CompiledAssemblyCatalog\{\s*"lmdj",\s*"([^"]+)"',
            compiled_text,
        )
        found = match.group(1) if match is not None else None
        if found != str(version):
            raise ValueError(
                _product_build_mismatch(
                    expected=version,
                    authority=version_path,
                    found=found,
                    consumer=compiled_path,
                    remedy=LOCK_REMEDY,
                )
            )
        raise ValueError(
            "generated compiled assembly is stale in "
            f"{_repo_relative(compiled_path)}; remedy: {LOCK_REMEDY}"
        )

    expected = _lock_document(
        version,
        assembly_path,
        assembly,
        expected_compiled,
    )
    if lock != expected:
        raise ValueError(
            "assembly lock does not match resolved assembly in "
            f"{_repo_relative(lock_path)}; remedy: {LOCK_REMEDY}"
        )


def _artifact_overlays(
    specifications: list[str] | None,
) -> dict[str, Path]:
    overlays: dict[str, Path] = {}
    for specification in specifications or []:
        if "=" not in specification:
            raise ValueError(
                "overlay artifact must use SOURCE=RELATIVE_PATH"
            )
        source_text, relative_text = specification.split("=", 1)
        source = Path(source_text)
        relative = PurePosixPath(relative_text)
        if (
            not source_text
            or not source.is_file()
            or source.is_symlink()
        ):
            raise ValueError("overlay artifact source must be a real file")
        if (
            not relative_text
            or "\\" in relative_text
            or relative.is_absolute()
            or relative.as_posix() != relative_text
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ValueError(
                "overlay artifact destination must be a normalized "
                "relative POSIX path"
            )
        if relative_text in overlays:
            raise ValueError(
                f"duplicate overlay artifact destination: {relative_text}"
            )
        overlays[relative_text] = source
    return overlays


def generate_manifest(
    version_file: str | Path,
    assembly_path: str | Path,
    lock_path: str | Path,
    channel: str,
    artifacts_root: str | Path,
    output_path: str | Path,
    overlay_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    version = verify(version_file, assembly_path, lock_path)
    if channel not in {"canary", "dev", "beta", "stable"}:
        raise ValueError(f"invalid channel: {channel}")
    root = Path(artifacts_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("artifacts root must be a real directory")
    output = Path(output_path).resolve()
    overlays = _artifact_overlays(overlay_artifacts)
    artifacts: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.resolve() == output:
            continue
        if path.is_symlink():
            raise ValueError(f"artifact must not be a symlink: {path}")
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        if (
            relative_path == "build-manifest.json"
            or relative_path in overlays
        ):
            continue
        artifacts.append(
            {
                "path": relative_path,
                "byte_length": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    for relative_path, path in overlays.items():
        artifacts.append(
            {
                "path": relative_path,
                "byte_length": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    artifacts.sort(key=lambda artifact: artifact["path"])
    manifest = {
        "contract": "lmdj.build-manifest.v1",
        "product": {"id": "lmdj", "version": str(version)},
        "channel": channel,
        "git_revision": _git_revision(),
        "assembly_lock_sha256": _sha256(Path(lock_path)),
        "build_time": (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        ),
        "platform": (
            f"{platform.system().lower()}-{platform.machine().lower()}"
        ),
        "artifacts": artifacts,
    }
    _write_canonical(output_path, manifest)
    return manifest


def verify(
    version_file: str | Path,
    assembly_path: str | Path | None = None,
    lock_path: str | Path | None = None,
) -> ProductVersion:
    version = load_version(version_file)
    _git_revision()
    if (assembly_path is None) != (lock_path is None):
        raise ValueError("assembly and lock must be supplied together")
    if assembly_path is not None and lock_path is not None:
        assembly = _verify_assembly(version, assembly_path, version_file)
        _verify_lock(
            version,
            assembly_path,
            assembly,
            lock_path,
            version_file,
        )
    return version


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and verify LMDJ Product Build identity."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    current = subparsers.add_parser("current")
    current.add_argument("--version-file", required=True)
    current.add_argument(
        "--channel",
        choices=("canary", "dev", "beta", "stable"),
        required=True,
    )
    current.add_argument("--revision", required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--version-file", required=True)
    verify_parser.add_argument("--assembly")
    verify_parser.add_argument("--lock")

    tag_name = subparsers.add_parser("tag-name")
    tag_name.add_argument("--version-file", required=True)

    lock_parser = subparsers.add_parser("lock")
    lock_parser.add_argument("--version-file", required=True)
    lock_parser.add_argument("--assembly", required=True)
    lock_parser.add_argument("--output", required=True)

    manifest_parser = subparsers.add_parser("manifest")
    manifest_parser.add_argument("--version-file", required=True)
    manifest_parser.add_argument("--assembly", required=True)
    manifest_parser.add_argument("--lock", required=True)
    manifest_parser.add_argument(
        "--channel",
        choices=("canary", "dev", "beta", "stable"),
        required=True,
    )
    manifest_parser.add_argument("--artifacts-root", required=True)
    manifest_parser.add_argument("--output", required=True)
    manifest_parser.add_argument(
        "--overlay-artifact",
        action="append",
        default=[],
        metavar="SOURCE=RELATIVE_PATH",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "current":
            version = load_version(args.version_file)
            print(version.display(args.channel, args.revision))
        elif args.command == "verify":
            version = verify(
                args.version_file,
                assembly_path=args.assembly,
                lock_path=args.lock,
            )
            print(f"version verification: PASS ({version})")
        elif args.command == "tag-name":
            print(load_version(args.version_file).product_tag())
        elif args.command == "lock":
            generate_lock(
                args.version_file,
                args.assembly,
                args.output,
            )
            print("assembly lock generated")
        elif args.command == "manifest":
            generate_manifest(
                args.version_file,
                args.assembly,
                args.lock,
                args.channel,
                args.artifacts_root,
                args.output,
                args.overlay_artifact,
            )
            print("build manifest generated")
        else:
            parser.error(f"unknown command: {args.command}")
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
    ) as error:
        print(f"version error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
