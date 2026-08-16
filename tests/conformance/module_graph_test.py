#!/usr/bin/env python3

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ASSEMBLY_PATH = REPO_ROOT / "products" / "lmdj" / "assembly.json"
NEUTRAL_ROOTS = ("packages",)
HOST_ROOT = REPO_ROOT / "apps"
PROVIDER_ROOT = REPO_ROOT / "providers"
FORBIDDEN_PACKAGE_REFERENCES = ("products/lmdj/", "apps/creator-web/")
EXPECTED_WEB_HOST_DEPENDENCIES = {
    "web-runtime-platform": "0.3.0",
}


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def manifest_paths(root: Path) -> list[Path]:
    return sorted(root.glob("*/module.json"))


def load_manifests(paths: list[Path]) -> dict[str, tuple[Path, dict]]:
    loaded: dict[str, tuple[Path, dict]] = {}
    for path in paths:
        manifest = load_object(path)
        assert set(manifest) == {
            "contract",
            "module",
            "version",
            "api_version",
            "dependencies",
        }, path
        assert manifest["contract"] == "lmdj.module.v1", path
        module_id = manifest["module"]
        assert isinstance(module_id, str) and module_id, path
        assert module_id not in loaded, module_id
        assert isinstance(manifest["version"], str), path
        assert (
            isinstance(manifest["api_version"], int)
            and not isinstance(manifest["api_version"], bool)
            and manifest["api_version"] >= 1
        ), path
        assert isinstance(manifest["dependencies"], dict), path
        loaded[module_id] = (path, manifest)
    return loaded


def assert_acyclic(graph: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        assert node not in visiting, f"dependency cycle at {node}"
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def inventory(assembly: dict, field: str) -> dict[str, str]:
    components = assembly[field]
    assert isinstance(components, list)
    result: dict[str, str] = {}
    for component in components:
        assert isinstance(component, dict)
        component_id = component["id"]
        assert component_id not in result, (field, component_id)
        result[component_id] = component["version"]
    return result


package_manifests = load_manifests(
    manifest_paths(REPO_ROOT / "packages")
)
host_manifests = load_manifests(manifest_paths(HOST_ROOT))
provider_manifests = load_manifests(manifest_paths(PROVIDER_ROOT))
all_manifests = {
    **package_manifests,
    **host_manifests,
    **provider_manifests,
}
assert len(all_manifests) == (
    len(package_manifests) + len(host_manifests) + len(provider_manifests)
)

graph: dict[str, set[str]] = {}
for module_id, (path, manifest) in all_manifests.items():
    dependencies = manifest["dependencies"]
    graph[module_id] = set(dependencies)
    for dependency_id, dependency_version in dependencies.items():
        assert dependency_id in all_manifests, (
            path,
            "unknown dependency",
            dependency_id,
        )
        target = all_manifests[dependency_id][1]
        assert dependency_version == target["version"], (
            path,
            dependency_id,
            dependency_version,
            target["version"],
        )
assert_acyclic(graph)

neutral_ids = set(package_manifests)
for module_id, (path, manifest) in package_manifests.items():
    assert "product" not in manifest and "product_id" not in manifest, path
    assert set(manifest["dependencies"]) <= neutral_ids, (path, module_id)

for _, (path, manifest) in host_manifests.items():
    assert "project-io" not in manifest["dependencies"], path

assert "web-runtime-host" in host_manifests, "Web Host manifest is missing"
web_host_path, web_host_manifest = host_manifests["web-runtime-host"]
assert web_host_path == REPO_ROOT / "apps/web-runtime-host/module.json"
assert web_host_manifest == {
    "contract": "lmdj.module.v1",
    "module": "web-runtime-host",
    "version": "1.2.9",
    "api_version": 1,
    "dependencies": EXPECTED_WEB_HOST_DEPENDENCIES,
}
creator_path, creator_manifest = host_manifests["creator-web"]
assert creator_path == REPO_ROOT / "apps/creator-web/module.json"
assert creator_manifest == {
    "contract": "lmdj.module.v1",
    "module": "creator-web",
    "version": "1.3.0",
    "api_version": 1,
    "dependencies": EXPECTED_WEB_HOST_DEPENDENCIES,
}

for _, (path, manifest) in provider_manifests.items():
    assert "authoring-domain" not in manifest["dependencies"], path
    assert "application-facade" not in manifest["dependencies"], path

for root_name in NEUTRAL_ROOTS:
    root = REPO_ROOT / root_name
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {
            ".c",
            ".cc",
            ".cpp",
            ".cxx",
            ".h",
            ".hh",
            ".hpp",
            ".hxx",
        }:
            continue
        source = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_PACKAGE_REFERENCES:
            assert forbidden not in source, (path, forbidden)

assembly = load_object(ASSEMBLY_PATH)
assert assembly["contract"] == "lmdj.assembly.v2"
assert inventory(assembly, "modules") == {
    module_id: manifest["version"]
    for module_id, (_, manifest) in package_manifests.items()
}
assert inventory(assembly, "hosts") == {
    module_id: manifest["version"]
    for module_id, (_, manifest) in host_manifests.items()
}
assert inventory(assembly, "providers") == {
    module_id: manifest["version"]
    for module_id, (_, manifest) in provider_manifests.items()
}

product_cmake = (
    REPO_ROOT / "products/lmdj/CMakeLists.txt"
).read_text(encoding="utf-8")
web_host_link = re.search(
    r"if\s*\(TARGET\s+lmdj_web_runtime_host\s*\)"
    r".*?target_link_libraries\s*\(\s*lmdj_web_runtime_host\s+PRIVATE\s+"
    r"lmdj_product_lmdj_assembly\s*\).*?endif\s*\(\s*\)",
    product_cmake,
    re.DOTALL,
)
assert web_host_link is not None, (
    "Product Assembly must link the compiled catalog only when the "
    "Emscripten Web Host target exists"
)
# Derive the expected compile-time identities from the Host manifests rather
# than repeating them. These definitions are baked into the wasm Runtime as the
# manifest gate's allowlist, so a Host version bump that misses them ships a
# distribution the Runtime refuses at boot with HOST_PROTOCOL_MISMATCH — a
# failure that names nothing about versions. Deriving here fails loudly and
# points at the real cause instead.
for identity in (
    'LMDJ_WEB_CREATOR_HOST_ID="creator-web"',
    f'LMDJ_WEB_CREATOR_HOST_VERSION="{creator_manifest["version"]}"',
    'LMDJ_WEB_DIAGNOSTIC_HOST_ID="web-runtime-host"',
    f'LMDJ_WEB_DIAGNOSTIC_HOST_VERSION="{web_host_manifest["version"]}"',
):
    assert identity in product_cmake, identity

# Exercise the graph checker against cases that the current tree does not
# naturally contain, so future refactors cannot make these gates vacuous.
try:
    assert_acyclic({"a": {"b"}, "b": {"a"}})
except AssertionError:
    pass
else:
    raise AssertionError("cycle checker accepted a cycle")

print("module graph conformance: PASS")
