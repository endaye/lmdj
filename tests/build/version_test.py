import json
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from scripts.version import (
    ProductVersion,
    _provider_source_package_sha256,
    load_version,
    verify,
)


expected_modules = {
    "packages/authoring-domain/module.json": (
        "authoring-domain",
        "0.2.0",
        1,
        {"foundation": "0.2.0"},
    ),
    "packages/project-cooker/module.json": (
        "project-cooker",
        "0.3.0",
        1,
        {"foundation": "0.2.0", "authoring-domain": "0.2.0"},
    ),
    "packages/project-io/module.json": (
        "project-io",
        "0.6.1",
        1,
        {"foundation": "0.2.0", "authoring-domain": "0.2.0"},
    ),
    "packages/audio-runtime/module.json": (
        "audio-runtime",
        "0.5.0",
        1,
        {"foundation": "0.2.0", "project-cooker": "0.3.0"},
    ),
    "packages/application-facade/module.json": (
        "application-facade",
        "1.4.4",
        2,
        {
            "foundation": "0.2.0",
            "authoring-domain": "0.2.0",
            "project-io": "0.6.1",
            "project-cooker": "0.3.0",
            "audio-runtime": "0.5.0",
            "provider-sdk": "1.1.4",
        },
    ),
    "packages/web-runtime-platform/module.json": (
        "web-runtime-platform",
        "0.3.4",
        1,
        {"application-facade": "1.4.4", "audio-runtime": "0.5.0"},
    ),
    "apps/core-cli/module.json": (
        "core-cli",
        "1.0.16",
        2,
        {"application-facade": "1.4.4"},
    ),
    "apps/core-mcp/module.json": (
        "core-mcp",
        "1.1.13",
        2,
        {"application-facade": "1.4.4"},
    ),
    "apps/native-test-host/module.json": (
        "native-test-host",
        "1.0.14",
        1,
        {"application-facade": "1.4.4", "audio-runtime": "0.5.0"},
    ),
    "apps/web-runtime-host/module.json": (
        "web-runtime-host",
        "1.2.13",
        1,
        {"web-runtime-platform": "0.3.4"},
    ),
    "apps/creator-web/module.json": (
        "creator-web",
        "1.5.1",
        1,
        {"web-runtime-platform": "0.3.4"},
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

# The current identity is read from source; what is asserted is that every
# derived form agrees with it. Pinning the literal here bought nothing and cost
# a CI cycle on each bump.
raw_version = json.loads(
    (repo_root / "products/lmdj/version.json").read_text(encoding="utf-8")
)
current = (
    f"{raw_version['milestone']}.{raw_version['minor']}"
    f".{raw_version['build']}.{raw_version['patch']}"
)
version = load_version("products/lmdj/version.json")
assert version == ProductVersion(
    raw_version["milestone"], raw_version["minor"],
    raw_version["build"], raw_version["patch"],
)
assert str(version) == current
assert version.product_tag() == f"lmdj-v{current}"
assert version.display("canary", "a" * 40) == f"{current} · canary · gaaaaaaaa"

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
assert tag_name.stdout == f"lmdj-v{current}\n"
assert tag_name.stderr == ""

current_run = subprocess.run(
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
assert current_run.stdout == f"{current} · canary · gaaaaaaaa\n"
assert current_run.stderr == ""

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
assert verified.stdout == f"version verification: PASS ({current})\n"
assert verified.stderr == ""


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def assert_product_build_mismatch(
    message: str,
    *,
    expected: str,
    found: str,
    consumer: str,
) -> None:
    assert "Product Build mismatch" in message, message
    assert f"expected {expected}" in message, message
    assert f"found {found}" in message, message
    assert "products/lmdj/version.json" in message, message
    assert consumer in message, message


assembly_path = repo_root / "products" / "lmdj" / "assembly.json"
tracked_lock_path = repo_root / "products" / "lmdj" / "assembly.lock.json"
assembly = json.loads(assembly_path.read_text(encoding="utf-8"))
tracked_lock = json.loads(tracked_lock_path.read_text(encoding="utf-8"))
assert assembly["product"] == {"id": "lmdj", "version": current}
assert assembly["providers"] == [
    {
        "id": "local.proof.success",
        "version": "1.0.5",
        "capabilities": [
            {"id": "proof.candidate.v2", "version": "2.0.0"}
        ],
        "model_identity": None,
    },
    {
        "id": "local.proof.failure",
        "version": "1.0.5",
        "capabilities": [
            {"id": "proof.candidate.v2", "version": "2.0.0"}
        ],
        "model_identity": None,
    },
]
provider_module = repo_root / "providers/local-proof-success/module.json"
provider_digest = _provider_source_package_sha256(
    "local.proof.success", "1.0.5", provider_module,
)
assert provider_digest == next(
    item["sha256"] for item in tracked_lock["providers"]
    if item["id"] == "local.proof.success"
)
with tempfile.TemporaryDirectory() as temp_dir:
    authority_root = Path(temp_dir)
    copied_provider = authority_root / "providers/local-proof-success"
    shutil.copytree(provider_module.parent, copied_provider)
    assert _provider_source_package_sha256(
        "local.proof.success", "1.0.5", copied_provider / "module.json",
        repo_root=authority_root,
    ) == provider_digest
assert assembly["contracts"] == [
    {"id": "lmdj.project.v1", "version": "1.0.0"},
    {"id": "lmdj.project.v2", "version": "2.0.0"},
    {"id": "lmdj.project-bundle.v1", "version": "1.0.0"},
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
    "contracts/project/lmdj.project.v2.schema.json": "2.0.0",
    "contracts/project/lmdj.project-bundle.v1.schema.json": "1.0.0",
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
        "version": "1.0.5",
        "api_version": 2,
        "dependencies": {"provider-sdk": "1.1.4"},
    },
    "providers/local-proof-success/module.json": {
        "contract": "lmdj.module.v1",
        "module": "local.proof.success",
        "version": "1.0.5",
        "api_version": 2,
        "dependencies": {"provider-sdk": "1.1.4"},
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
assert compiled_product.group(1) == current
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
    fixture_product_root = temp_root / "products/lmdj"
    stale_assembly_path = fixture_product_root / "assembly.json"
    stale_assembly = json.loads(assembly_path.read_text(encoding="utf-8"))
    stale_assembly["product"]["version"] = "9.8.7.5"
    write_json(stale_assembly_path, stale_assembly)
    try:
        verify(
            "products/lmdj/version.json",
            assembly_path=stale_assembly_path,
            lock_path=tracked_lock_path,
        )
    except ValueError as error:
        assert_product_build_mismatch(
            str(error),
            expected=current,
            found="9.8.7.5",
            consumer="products/lmdj/assembly.json",
        )
    else:
        raise AssertionError("accepted an Assembly Product Build mismatch")

    lock_path = fixture_product_root / "assembly.lock.json"
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

    for field in ("product", "product_assembly"):
        stale_lock = json.loads(tracked_lock_path.read_text(encoding="utf-8"))
        stale_lock[field]["version"] = "9.8.7.5"
        write_json(lock_path, stale_lock)
        try:
            verify(
                "products/lmdj/version.json",
                assembly_path=assembly_path,
                lock_path=lock_path,
            )
        except ValueError as error:
            assert_product_build_mismatch(
                str(error),
                expected=current,
                found="9.8.7.5",
                consumer="products/lmdj/assembly.lock.json",
            )
        else:
            raise AssertionError(f"accepted a stale lock {field} identity")

runtime_identity_generator_path = (
    repo_root / "tools/web-runtime/generate_runtime_identity.py"
)
assert runtime_identity_generator_path.is_file(), "missing Runtime identity generator"
generator_spec = importlib.util.spec_from_file_location(
    "lmdj_runtime_identity_generator", runtime_identity_generator_path
)
assert generator_spec is not None and generator_spec.loader is not None
runtime_identity_generator = importlib.util.module_from_spec(generator_spec)
generator_spec.loader.exec_module(runtime_identity_generator)

with tempfile.TemporaryDirectory() as temp_dir:
    fixture_root = Path(temp_dir) / "repo"
    for relative in (
        "products/lmdj/version.json",
        "products/lmdj/assembly.json",
        "products/lmdj/assembly.lock.json",
        "packages/web-runtime-platform/module.json",
        "apps/creator-web/module.json",
        "apps/web-runtime-host/module.json",
        "tools/web-runtime/emscripten.lock.json",
        "tools/web-runtime/runtime-identity.json",
    ):
        destination = fixture_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo_root / relative, destination)

    baseline = runtime_identity_generator.generate(fixture_root)
    for relative, mutate in (
        (
            "products/lmdj/assembly.json",
            lambda value: value["product"].__setitem__(
                "version", "9.8.7.5"
            ),
        ),
        (
            "products/lmdj/assembly.lock.json",
            lambda value: value["product"].__setitem__(
                "version", "9.8.7.5"
            ),
        ),
        (
            "products/lmdj/assembly.lock.json",
            lambda value: value["product_assembly"].__setitem__(
                "version", "9.8.7.5"
            ),
        ),
    ):
        path = fixture_root / relative
        original = path.read_bytes()
        value = json.loads(original)
        mutate(value)
        write_json(path, value)
        try:
            runtime_identity_generator.generate(fixture_root)
        except runtime_identity_generator.IdentityError as error:
            assert_product_build_mismatch(
                str(error),
                expected=current,
                found="9.8.7.5",
                consumer=relative,
            )
        else:
            raise AssertionError(
                f"Runtime identity accepted a stale consumer: {relative}"
            )
        finally:
            path.write_bytes(original)

    mutations = (
        ("products/lmdj/version.json", "patch", 10),
        ("apps/creator-web/module.json", "version", "9.9.9"),
        ("packages/web-runtime-platform/module.json", "version", "9.9.9"),
        ("products/lmdj/assembly.lock.json", "assembly_sha256", "f" * 64),
        (
            "tools/web-runtime/runtime-identity.json",
            ("resource_limits", "imported_wav_bytes"),
            1,
        ),
        (
            "tools/web-runtime/emscripten.lock.json",
            "emcc_version",
            "emcc changed",
        ),
    )
    for relative, key, replacement in mutations:
        path = fixture_root / relative
        original = path.read_bytes()
        value = json.loads(original)
        if isinstance(key, tuple):
            value[key[0]][key[1]] = replacement
        else:
            value[key] = replacement
        write_json(path, value)
        try:
            try:
                changed = runtime_identity_generator.generate(fixture_root)
            except runtime_identity_generator.IdentityError:
                pass
            else:
                assert changed != baseline, f"identity mutation had no effect: {relative}"
        finally:
            path.write_bytes(original)

    runtime_identity_generator.write_or_check(fixture_root, check=False)
    runtime_outputs = (
        fixture_root / "products/lmdj/generated/web-runtime-identity.json",
        fixture_root / "products/lmdj/generated/web-runtime-identity.mjs",
    )
    for output_path in runtime_outputs:
        original = output_path.read_bytes()
        output_path.write_bytes(
            original.replace(
                f'"product_build":"{current}"'.encode("utf-8"),
                b'"product_build":"9.8.7.5"',
                1,
            )
        )
        assert output_path.read_bytes() != original
        try:
            runtime_identity_generator.write_or_check(
                fixture_root,
                check=True,
            )
        except runtime_identity_generator.IdentityError as error:
            assert_product_build_mismatch(
                str(error),
                expected=current,
                found="9.8.7.5",
                consumer=output_path.relative_to(fixture_root).as_posix(),
            )
            assert "generate_runtime_identity.py" in str(error)
        else:
            raise AssertionError(
                f"stale Runtime Product Build was accepted: {output_path}"
            )
        finally:
            output_path.write_bytes(original)

    invalid_mjs = runtime_outputs[1]
    original_mjs = invalid_mjs.read_bytes()
    invalid_mjs.write_text("export const nope = true;\n", encoding="utf-8")
    try:
        runtime_identity_generator.write_or_check(fixture_root, check=True)
    except runtime_identity_generator.IdentityError as error:
        message = str(error)
        assert "found <invalid>" in message, message
        assert invalid_mjs.relative_to(fixture_root).as_posix() in message
        assert "generate_runtime_identity.py" in message
    else:
        raise AssertionError("invalid Runtime identity MJS was accepted")
    finally:
        invalid_mjs.write_bytes(original_mjs)

for host_main, package_tool in (
    ("apps/creator-web/src/main.tsx", "apps/creator-web/tools/package.py"),
    ("apps/web-runtime-host/src/main.mjs", "apps/web-runtime-host/tools/package.py"),
):
    assert "ASSEMBLY_IDENTITY = Object.freeze" not in (
        repo_root / host_main
    ).read_text(encoding="utf-8")
    package_source = (repo_root / package_tool).read_text(encoding="utf-8")
    for copied_name in (
        "HOST_VERSION =",
        "PLATFORM_VERSION =",
        "PROTOCOL_VERSION =",
        "HEAP_BYTES =",
        "EMCC_VERSION =",
        "RESOURCE_LIMITS =",
    ):
        assert copied_name not in package_source, (
            f"copied Runtime identity remains in {package_tool}: {copied_name}"
        )

cmake_source = (
    repo_root / "packages/web-runtime-platform/CMakeLists.txt"
).read_text(encoding="utf-8")
assert "products/lmdj/generated/web-runtime-identity.json" in cmake_source
assert re.search(
    r'"product_build":"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"',
    cmake_source,
) is None

print("product version tests: PASS")
