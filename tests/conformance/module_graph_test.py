#!/usr/bin/env python3

import json
import re
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ASSEMBLY_PATH = REPO_ROOT / "products" / "lmdj" / "assembly.json"
NEUTRAL_ROOTS = ("packages",)
HOST_ROOT = REPO_ROOT / "apps"
PROVIDER_ROOT = REPO_ROOT / "providers"
FORBIDDEN_PACKAGE_REFERENCES = ("products/lmdj/", "apps/creator-web/")
EXPECTED_WEB_HOST_DEPENDENCIES = {
    "web-runtime-platform": "5.2.2",
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


def identity_text(value: object) -> str:
    if value is None:
        return "<missing>"
    return value if isinstance(value, str) and value else "<invalid>"


def verify_creator_package_identity(root: Path) -> None:
    relative_root = Path("apps/creator-web")
    authority_relative = relative_root / "module.json"
    package_relative = relative_root / "package.json"
    lock_relative = relative_root / "package-lock.json"
    module = load_object(root / authority_relative)
    package = load_object(root / package_relative)
    lock = load_object(root / lock_relative)
    assert module.get("contract") == "lmdj.module.v1", authority_relative
    module_id = module.get("module")
    expected_version = module.get("version")
    assert isinstance(module_id, str) and module_id, authority_relative
    assert isinstance(expected_version, str) and expected_version, authority_relative
    expected_name = f"@lmdj/{module_id}"
    packages = lock.get("packages")
    root_package = packages.get("") if isinstance(packages, dict) else None
    consumers = (
        (package_relative.as_posix(), package),
        (lock_relative.as_posix(), lock),
        (f"{lock_relative.as_posix()}#packages['']", root_package),
    )
    for consumer, document in consumers:
        for identity_kind, expected in (
            ("version", expected_version),
            ("name", expected_name),
        ):
            found = document.get(identity_kind) if isinstance(document, dict) else None
            if found != expected:
                raise AssertionError(
                    f"Creator Host {identity_kind} mismatch: expected {expected} "
                    f"from {authority_relative.as_posix()}, found "
                    f"{identity_text(found)} in {consumer}"
                )


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
    "version": "4.2.4",
    "api_version": 2,
    "dependencies": EXPECTED_WEB_HOST_DEPENDENCIES,
}
creator_path, creator_manifest = host_manifests["creator-web"]
assert creator_path == REPO_ROOT / "apps/creator-web/module.json"
assert creator_manifest == {
    "contract": "lmdj.module.v1",
    "module": "creator-web",
    "version": "4.2.4",
    "api_version": 2,
    "dependencies": EXPECTED_WEB_HOST_DEPENDENCIES,
}
verify_creator_package_identity(REPO_ROOT)

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
}, "registered Provider inventory differs; remedy: reconcile source manifests and approved Assembly"


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
# Compile-time Runtime identities are generated from Product Assembly, then
# read by CMake. This keeps the wasm manifest gate aligned without copying
# mutable version literals into the build definition.
web_identity = load_object(
    REPO_ROOT / "products/lmdj/generated/web-runtime-identity.json"
)
assert web_identity["platform"]["version"] == package_manifests[
    "web-runtime-platform"
][1]["version"]
assert web_identity["hosts"]["creator-web"]["version"] == creator_manifest[
    "version"
]
assert web_identity["hosts"]["web-runtime-host"]["version"] == (
    web_host_manifest["version"]
)
for identity in (
    "generated/web-runtime-identity.json",
    'LMDJ_WEB_CREATOR_HOST_ID="creator-web"',
    'LMDJ_WEB_CREATOR_HOST_VERSION="${lmdj_web_creator_host_version}"',
    'LMDJ_WEB_DIAGNOSTIC_HOST_ID="web-runtime-host"',
    'LMDJ_WEB_DIAGNOSTIC_HOST_VERSION="${lmdj_web_diagnostic_host_version}"',
    'LMDJ_WEB_PLATFORM_VERSION="${lmdj_web_platform_version}"',
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

with tempfile.TemporaryDirectory(prefix="lmdj-creator-identity-") as temp:
    fixture_root = Path(temp)
    creator_root = fixture_root / "apps/creator-web"
    creator_root.mkdir(parents=True)
    valid_module = {
        "contract": "lmdj.module.v1",
        "module": "creator-web",
        "version": "9.8.7",
        "api_version": 1,
        "dependencies": {},
    }
    valid_package = {"name": "@lmdj/creator-web", "version": "9.8.7"}
    valid_lock = {
        "name": "@lmdj/creator-web",
        "version": "9.8.7",
        "packages": {
            "": {"name": "@lmdj/creator-web", "version": "9.8.7"}
        },
    }

    def write_fixture(package: dict, lock: dict) -> None:
        for name, value in (
            ("module.json", valid_module),
            ("package.json", package),
            ("package-lock.json", lock),
        ):
            (creator_root / name).write_text(
                json.dumps(value),
                encoding="utf-8",
            )

    mutations = (
        (
            "package-version",
            lambda package, lock: package.__setitem__("version", "9.8.6"),
            "version",
            "apps/creator-web/package.json",
        ),
        (
            "lock-version",
            lambda package, lock: lock.__setitem__("version", "9.8.6"),
            "version",
            "apps/creator-web/package-lock.json",
        ),
        (
            "lock-root-version",
            lambda package, lock: lock["packages"][""].__setitem__(
                "version", "9.8.6"
            ),
            "version",
            "apps/creator-web/package-lock.json#packages['']",
        ),
        (
            "package-name",
            lambda package, lock: package.__setitem__("name", "@lmdj/wrong"),
            "name",
            "apps/creator-web/package.json",
        ),
        (
            "lock-name",
            lambda package, lock: lock.__setitem__("name", "@lmdj/wrong"),
            "name",
            "apps/creator-web/package-lock.json",
        ),
        (
            "lock-root-name",
            lambda package, lock: lock["packages"][""].__setitem__(
                "name", "@lmdj/wrong"
            ),
            "name",
            "apps/creator-web/package-lock.json#packages['']",
        ),
    )
    for case, mutate, identity_kind, consumer in mutations:
        package = json.loads(json.dumps(valid_package))
        lock = json.loads(json.dumps(valid_lock))
        mutate(package, lock)
        write_fixture(package, lock)
        try:
            verify_creator_package_identity(fixture_root)
        except AssertionError as error:
            message = str(error)
            expected = (
                "9.8.7" if identity_kind == "version" else "@lmdj/creator-web"
            )
            found = "9.8.6" if identity_kind == "version" else "@lmdj/wrong"
            assert f"expected {expected}" in message, (case, message)
            assert f"found {found}" in message, (case, message)
            assert "apps/creator-web/module.json" in message, (case, message)
            assert consumer in message, (case, message)
        else:
            raise AssertionError(f"Creator identity drift was accepted: {case}")

print("module graph conformance: PASS")
