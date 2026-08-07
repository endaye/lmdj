import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from scripts.version import ProductVersion, load_version, verify


expected_modules = {
    "packages/project-cooker/module.json": (
        "project-cooker",
        "0.2.1",
        1,
        {"foundation": "0.2.0", "authoring-domain": "0.1.1"},
    ),
    "packages/project-io/module.json": (
        "project-io",
        "0.4.0",
        1,
        {"foundation": "0.2.0", "authoring-domain": "0.1.1"},
    ),
    "packages/audio-runtime/module.json": (
        "audio-runtime",
        "0.4.0",
        1,
        {"foundation": "0.2.0", "project-cooker": "0.2.1"},
    ),
    "packages/application-facade/module.json": (
        "application-facade",
        "1.2.0",
        2,
        {
            "foundation": "0.2.0",
            "authoring-domain": "0.1.1",
            "project-io": "0.4.0",
            "project-cooker": "0.2.1",
            "audio-runtime": "0.4.0",
            "provider-sdk": "1.1.1",
        },
    ),
    "apps/core-cli/module.json": (
        "core-cli",
        "1.0.5",
        2,
        {"application-facade": "1.2.0"},
    ),
    "apps/core-mcp/module.json": (
        "core-mcp",
        "1.1.2",
        2,
        {"application-facade": "1.2.0"},
    ),
    "apps/native-test-host/module.json": (
        "native-test-host",
        "1.0.3",
        1,
        {"application-facade": "1.2.0", "audio-runtime": "0.4.0"},
    ),
    "apps/web-runtime-host/module.json": (
        "web-runtime-host",
        "1.1.1",
        1,
        {"application-facade": "1.2.0", "audio-runtime": "0.4.0"},
    ),
}
for relative, (
    module_id,
    module_version,
    api_version,
    dependencies,
) in expected_modules.items():
    manifest_path = repo_root / relative
    assert manifest_path.is_file(), f"missing module manifest: {relative}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["contract"] == "lmdj.module.v1"
    assert manifest["module"] == module_id
    assert manifest["version"] == module_version
    assert manifest["api_version"] == api_version
    assert manifest["dependencies"] == dependencies

version = load_version("products/lmdj/version.json")
assert version == ProductVersion(1, 0, 15, 1)
assert str(version) == "1.0.15.1"
assert version.product_tag() == "lmdj-v1.0.15.1"
assert version.display("canary", "a" * 40) == (
    "1.0.15.1 · canary · gaaaaaaaa"
)

for invalid in (
    {"milestone": 0, "minor": 0, "build": 1, "patch": 0},
    {"milestone": 1, "minor": -1, "build": 1, "patch": 0},
    {"milestone": 1, "minor": 0, "build": 0, "patch": 1},
):
    try:
        ProductVersion(**invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(f"accepted invalid product version: {invalid}")

version_script = repo_root / "scripts" / "version.py"

tag_name = subprocess.run(
    [
        sys.executable,
        str(version_script),
        "tag-name",
        "--version-file",
        "products/lmdj/version.json",
    ],
    cwd=repo_root,
    check=True,
    capture_output=True,
    text=True,
)
assert tag_name.stdout == "lmdj-v1.0.15.1\n"
assert tag_name.stderr == ""

current = subprocess.run(
    [
        sys.executable,
        str(version_script),
        "current",
        "--version-file",
        "products/lmdj/version.json",
        "--channel",
        "canary",
        "--revision",
        "a" * 40,
    ],
    cwd=repo_root,
    check=True,
    capture_output=True,
    text=True,
)
assert current.stdout == "1.0.15.1 · canary · gaaaaaaaa\n"
assert current.stderr == ""

verified = subprocess.run(
    [
        sys.executable,
        str(version_script),
        "verify",
        "--version-file",
        "products/lmdj/version.json",
    ],
    cwd=repo_root,
    check=True,
    capture_output=True,
    text=True,
)
assert verified.stdout == "version verification: PASS (1.0.15.1)\n"
assert verified.stderr == ""


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


assembly_path = repo_root / "products" / "lmdj" / "assembly.json"
tracked_lock_path = repo_root / "products" / "lmdj" / "assembly.lock.json"
assembly = json.loads(assembly_path.read_text(encoding="utf-8"))
assert assembly["product"] == {"id": "lmdj", "version": "1.0.15.1"}
assert assembly["providers"] == [
    {
        "id": "local.proof.success",
        "version": "1.0.2",
        "capabilities": [
            {"id": "proof.candidate.v2", "version": "2.0.0"}
        ],
        "model_identity": None,
    },
    {
        "id": "local.proof.failure",
        "version": "1.0.2",
        "capabilities": [
            {"id": "proof.candidate.v2", "version": "2.0.0"}
        ],
        "model_identity": None,
    },
]
assert assembly["contracts"] == [
    {"id": "lmdj.project.v1", "version": "1.0.0"},
    {"id": "lmdj.capability.v2", "version": "2.0.0"},
    {"id": "lmdj.assembly.v2", "version": "2.0.0"},
    {"id": "lmdj.error.v1", "version": "1.0.0"},
    {"id": "lmdj.module.v1", "version": "1.0.0"},
    {"id": "lmdj.product-version.v1", "version": "1.0.0"},
]

expected_contract_sources = {
    "contracts/assembly/lmdj.assembly.v1.schema.json": "1.0.0",
    "contracts/assembly/lmdj.assembly.v2.schema.json": "2.0.0",
    "contracts/capability/lmdj.capability.v1.schema.json": "1.0.0",
    "contracts/capability/lmdj.capability.v2.schema.json": "2.0.0",
    "contracts/error/lmdj.error.v1.schema.json": "1.0.0",
    "contracts/module/lmdj.module.v1.schema.json": "1.0.0",
    "contracts/project/lmdj.project.v1.schema.json": "1.0.0",
    "contracts/version/lmdj.product-version.v1.schema.json": "1.0.0",
}
actual_contract_sources = sorted(
    path.relative_to(repo_root).as_posix()
    for path in (repo_root / "contracts").glob("*/*.schema.json")
)
assert actual_contract_sources == sorted(expected_contract_sources)
for relative, contract_version in expected_contract_sources.items():
    contract = json.loads((repo_root / relative).read_text(encoding="utf-8"))
    assert contract["x-lmdj-contract-version"] == contract_version

expected_provider_manifests = {
    "providers/local-proof-failure/module.json": {
        "contract": "lmdj.module.v1",
        "module": "local.proof.failure",
        "version": "1.0.2",
        "api_version": 2,
        "dependencies": {"provider-sdk": "1.1.1"},
    },
    "providers/local-proof-success/module.json": {
        "contract": "lmdj.module.v1",
        "module": "local.proof.success",
        "version": "1.0.2",
        "api_version": 2,
        "dependencies": {"provider-sdk": "1.1.1"},
    },
}
actual_provider_manifests = sorted(
    path.relative_to(repo_root).as_posix()
    for path in (repo_root / "providers").glob("*/module.json")
)
assert actual_provider_manifests == sorted(expected_provider_manifests)
for relative, expected in expected_provider_manifests.items():
    assert json.loads((repo_root / relative).read_text(encoding="utf-8")) == expected

compiled_source = (
    repo_root / "products/lmdj/src/compiled_assembly.cpp"
).read_text(encoding="utf-8")
compiled_product = re.search(
    r'CompiledAssemblyCatalog\{\s*"lmdj",\s*"([^"]+)"',
    compiled_source,
)
assert compiled_product is not None
assert compiled_product.group(1) == "1.0.15.1"
compiled_components = re.findall(
    r'CompiledComponent\{"([^"]+)",\s*"([^"]+)"\}',
    compiled_source,
)
expected_compiled_components = [
    (component["id"], component["version"])
    for field in ("modules", "hosts", "contracts")
    for component in assembly[field]
]
assert compiled_components == expected_compiled_components
web_manifest = json.loads(
    (repo_root / "apps/web-runtime-host/module.json").read_text(encoding="utf-8")
)
assert (web_manifest["module"], web_manifest["version"]) in compiled_components
compiled_providers = re.findall(
    r'CompiledProvider\{\s*"([^"]+)",\s*"([^"]+)"',
    compiled_source,
)
assert compiled_providers == [
    (provider["id"], provider["version"])
    for provider in assembly["providers"]
]

native_host_source = (
    repo_root / "apps/native-test-host/src/main.cpp"
).read_text(encoding="utf-8")
native_host_cmake = (
    repo_root / "apps/native-test-host/CMakeLists.txt"
).read_text(encoding="utf-8")
assert "1.0.14.0" not in native_host_source
assert re.search(
    r'constexpr std::string_view kProductBuild\s*=\s*LMDJ_NATIVE_PRODUCT_BUILD;',
    native_host_source,
)
assert 'products/lmdj/version.json' in native_host_cmake
assert re.search(
    r'LMDJ_NATIVE_PRODUCT_BUILD="\$\{lmdj_native_product_build\}"',
    native_host_cmake,
)

assert verify(
    "products/lmdj/version.json",
    assembly_path=assembly_path,
    lock_path=tracked_lock_path,
) == version

with tempfile.TemporaryDirectory() as temp_dir:
    temp_root = Path(temp_dir)
    lock_path = temp_root / "assembly.lock.json"
    lock = json.loads(tracked_lock_path.read_text(encoding="utf-8"))
    write_json(lock_path, lock)
    assert verify(
        "products/lmdj/version.json",
        assembly_path=assembly_path,
        lock_path=lock_path,
    ) == version

    for assembly_arg, lock_arg in (
        (assembly_path, None),
        (None, lock_path),
    ):
        try:
            verify(
                "products/lmdj/version.json",
                assembly_path=assembly_arg,
                lock_path=lock_arg,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("accepted an unpaired assembly/lock")

    incomplete_lock = dict(lock)
    incomplete_lock["modules"] = []
    write_json(lock_path, incomplete_lock)
    try:
        verify(
            "products/lmdj/version.json",
            assembly_path=assembly_path,
            lock_path=lock_path,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("accepted an incomplete assembly lock")

print("product version tests: PASS")
