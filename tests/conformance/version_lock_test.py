#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts import version as version_module


VERSION_PATH = REPO_ROOT / "products" / "lmdj" / "version.json"
ASSEMBLY_PATH = REPO_ROOT / "products" / "lmdj" / "assembly.json"
VERSION_SCRIPT = REPO_ROOT / "scripts" / "version.py"
LOCK_PATH = REPO_ROOT / "products" / "lmdj" / "assembly.lock.json"
FORBIDDEN_LOCK_KEYS = {
    "git_revision",
    "revision",
    "channel",
    "build_time",
    "platform",
}


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def source_package_identity(
    *,
    format_name: str,
    identity: dict[str, str],
    paths: list[Path],
    root: Path = REPO_ROOT,
) -> str:
    document = {
        "files": [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256(path),
            }
            for path in sorted(paths)
        ],
        "format": format_name,
        **identity,
    }
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def provider_source_package_identity(
    component_id: str,
    component_version: str,
    root: Path = REPO_ROOT,
) -> str:
    provider_root = next(
        path.parent
        for path in sorted((root / "providers").glob("*/module.json"))
        if load_object(path)["module"] == component_id
    )
    return source_package_identity(
        format_name="provider-source-package",
        identity={
            "provider_id": component_id,
            "provider_version": component_version,
        },
        paths=[
            provider_root / "module.json",
            *provider_root.glob("include/**/*.hpp"),
            *provider_root.glob("src/**/*.cpp"),
        ],
        root=root,
    )


def product_assembly_source_identity(root: Path = REPO_ROOT) -> str:
    version = load_object(root / "products/lmdj/version.json")
    product_version = ".".join(
        str(version[field])
        for field in ("milestone", "minor", "build", "patch")
    )
    return source_package_identity(
        format_name="product-assembly-source-package",
        identity={
            "product_id": "lmdj",
            "product_version": product_version,
        },
        paths=[
            root / "products/lmdj/CMakeLists.txt",
            root / "products/lmdj/src/compiled_assembly.cpp",
        ],
        root=root,
    )


def component_source(field: str, component_id: str) -> Path:
    roots = {
        "modules": REPO_ROOT / "packages",
        "hosts": REPO_ROOT / "apps",
        "providers": REPO_ROOT / "providers",
    }
    if field in roots:
        matches = []
        for candidate in sorted(roots[field].glob("*/module.json")):
            if load_object(candidate).get("module") == component_id:
                matches.append(candidate)
        assert len(matches) == 1, (field, component_id, matches)
        return matches[0]
    if field == "contracts":
        matches = sorted(
            (REPO_ROOT / "contracts").glob(
                f"*/{component_id}.schema.json"
            )
        )
        matches += sorted((REPO_ROOT / "contracts").glob(f"*/{component_id}.md"))
        assert len(matches) == 1, (component_id, matches)
        return matches[0]
    raise AssertionError(field)


def generate(
    output: Path,
    assembly_path: Path = ASSEMBLY_PATH,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(VERSION_SCRIPT),
            "lock",
            "--version-file",
            str(VERSION_PATH),
            "--assembly",
            str(assembly_path),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def copy_lock_repository(destination_root: Path) -> dict:
    copied_assembly = load_object(ASSEMBLY_PATH)
    for relative in (
        "scripts/version.py",
        "products/lmdj/version.json",
        "products/lmdj/assembly.json",
        "products/lmdj/CMakeLists.txt",
        "products/lmdj/src/compiled_assembly.cpp",
    ):
        source = REPO_ROOT / relative
        destination = destination_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for field in ("modules", "hosts", "providers", "contracts"):
        for component in copied_assembly[field]:
            source = component_source(field, component["id"])
            destination = destination_root / source.relative_to(REPO_ROOT)
            if field == "providers":
                shutil.copytree(source.parent, destination.parent)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    return copied_assembly


assert LOCK_PATH.is_file(), "assembly.lock.json must be generated and tracked"
assembly = load_object(ASSEMBLY_PATH)
lock = load_object(LOCK_PATH)
assert assembly["provider_policy"] == {
    "allowed_regions": ["local"],
    "allowed_data_classifications": ["public"],
    "granted_permissions": ["proof.execute"],
}
assert set(lock) == {
    "product",
    "product_assembly",
    "assembly_sha256",
    "modules",
    "hosts",
    "providers",
    "contracts",
}
assert lock["product"] == assembly["product"]
assert lock["assembly_sha256"] == sha256(ASSEMBLY_PATH)
assert lock["product_assembly"] == {
    "id": "lmdj",
    "version": assembly["product"]["version"],
    "sha256": product_assembly_source_identity(),
}

for field in ("modules", "hosts", "providers", "contracts"):
    expected = {
        component["id"]: component["version"]
        for component in assembly[field]
    }
    locked = lock[field]
    assert isinstance(locked, list)
    assert [component["id"] for component in locked] == sorted(expected)
    for component in locked:
        assert set(component) == {"id", "version", "sha256"}
        component_id = component["id"]
        assert component["version"] == expected[component_id]
        source = component_source(field, component_id)
        assert source.is_file(), source
        expected_sha256 = (
            provider_source_package_identity(
                component_id,
                component["version"],
            )
            if field == "providers"
            else sha256(source)
        )
        assert component["sha256"] == expected_sha256
        if field == "providers":
            assert component["sha256"] != sha256(source)


def visit(value: object) -> None:
    if isinstance(value, dict):
        assert not (set(value) & FORBIDDEN_LOCK_KEYS), value
        for member in value.values():
            visit(member)
    elif isinstance(value, list):
        for member in value:
            visit(member)


visit(lock)
canonical = json.dumps(
    lock,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
) + "\n"
assert LOCK_PATH.read_text(encoding="utf-8") == canonical

with tempfile.TemporaryDirectory(prefix="lmdj-version-lock-") as temp:
    temp_root = Path(temp)
    first = temp_root / "first.json"
    second = temp_root / "second.json"
    for output in (first, second):
        completed = generate(output)
        assert completed.returncode == 0, (
            completed.stdout,
            completed.stderr,
        )
        assert completed.stdout == "assembly lock generated\n"
        assert completed.stderr == ""
    assert first.read_bytes() == second.read_bytes() == LOCK_PATH.read_bytes()

    ordering_root = temp_root / "ordering-repository"
    ordering_assembly = copy_lock_repository(ordering_root)
    ordering_script = ordering_root / "scripts/version.py"
    ordering_assembly_path = ordering_root / "products/lmdj/assembly.json"
    ordering_output = ordering_root / "products/lmdj/assembly.lock.json"
    ordering_source = (
        ordering_root / "products/lmdj/src/compiled_assembly.cpp"
    )

    def run_ordering_lock() -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(ordering_script),
                "lock",
                "--version-file",
                str(ordering_root / "products/lmdj/version.json"),
                "--assembly",
                str(ordering_assembly_path),
                "--output",
                str(ordering_output),
            ],
            cwd=ordering_root,
            check=False,
            capture_output=True,
            text=True,
        )

    completed = run_ordering_lock()
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert completed.stdout == "assembly lock generated\n"
    assert completed.stderr == ""
    authoritative_source = ordering_source.read_bytes()
    authoritative_lock = ordering_output.read_bytes()
    assert authoritative_source == (
        REPO_ROOT / "products/lmdj/src/compiled_assembly.cpp"
    ).read_bytes()
    assert authoritative_lock == LOCK_PATH.read_bytes()

    stale_product = ordering_assembly["product"]["version"]
    stale_source = authoritative_source.decode("utf-8").replace(
        f'CompiledAssemblyCatalog{{\n      "lmdj",\n      "{stale_product}",',
        'CompiledAssemblyCatalog{\n      "lmdj",\n      "9.8.7.5",',
        1,
    )
    assert stale_source.encode("utf-8") != authoritative_source
    ordering_source.write_text(stale_source, encoding="utf-8")
    original_repo_root = version_module.REPO_ROOT
    version_module.REPO_ROOT = ordering_root
    try:
        try:
            version_module._verify_lock(
                version_module.load_version(
                    ordering_root / "products/lmdj/version.json"
                ),
                ordering_assembly_path,
                ordering_assembly,
                ordering_output,
                ordering_root / "products/lmdj/version.json",
            )
        except ValueError as error:
            stale_message = str(error)
        else:
            raise AssertionError("stale compiled Product Build was accepted")
    finally:
        version_module.REPO_ROOT = original_repo_root
    assert "Product Build mismatch" in stale_message
    assert f"expected {stale_product}" in stale_message
    assert "found 9.8.7.5" in stale_message
    assert "products/lmdj/version.json" in stale_message
    assert "products/lmdj/src/compiled_assembly.cpp" in stale_message
    assert "scripts/version.py lock" in stale_message
    ordering_source.write_bytes(authoritative_source)

    source_text = authoritative_source.decode("utf-8")
    swapped_factories = source_text.replace(
        "local_proof_success_registration",
        "factory_swap_placeholder",
        1,
    ).replace(
        "local_proof_failure_registration",
        "local_proof_success_registration",
        1,
    ).replace(
        "factory_swap_placeholder",
        "local_proof_failure_registration",
        1,
    )
    assert swapped_factories != source_text
    ordering_source.write_text(swapped_factories, encoding="utf-8")
    completed = run_ordering_lock()
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert completed.stdout == "assembly lock generated\n"
    assert completed.stderr == ""
    assert ordering_source.read_bytes() == authoritative_source
    assert ordering_output.read_bytes() == authoritative_lock

    model = {
        "id": "proof.model",
        "version": "weights-v1",
        "artifact_sha256": "b" * 64,
    }
    ordering_assembly["providers"][0]["model_identity"] = model
    ordering_assembly_path.write_bytes(canonical_bytes(ordering_assembly))
    completed = run_ordering_lock()
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    model_source = ordering_source.read_text(encoding="utf-8")
    assert (
        """              lmdj::provider::ModelIdentity{
                  "proof.model",
                  "weights-v1",
                  "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
              },"""
        in model_source
    )
    model_source_bytes = ordering_source.read_bytes()
    model_lock_bytes = ordering_output.read_bytes()
    assert load_object(ordering_output)["product_assembly"]["sha256"] == (
        product_assembly_source_identity(ordering_root)
    )
    completed = run_ordering_lock()
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert ordering_source.read_bytes() == model_source_bytes
    assert ordering_output.read_bytes() == model_lock_bytes

    factory_header = (
        ordering_root
        / "providers/local-proof-success/include/lmdj/providers"
        / "local_proof_success/factory.hpp"
    )
    valid_factory_header = factory_header.read_text(encoding="utf-8")
    ambiguous_header = valid_factory_header.replace(
        "\n}  // namespace lmdj::providers",
        "\nprovider::ProviderRegistration ambiguous_registration();"
        "\n\n}  // namespace lmdj::providers",
    )
    assert ambiguous_header != factory_header.read_text(encoding="utf-8")
    factory_header.write_text(ambiguous_header, encoding="utf-8")
    completed = run_ordering_lock()
    assert completed.returncode == 2, (completed.stdout, completed.stderr)
    assert completed.stdout == ""
    assert "Provider local.proof.success factory.hpp" in completed.stderr
    assert "exactly one registration symbol" in completed.stderr
    assert "before assembly lock generation" in completed.stderr
    assert "compiled assembly" in completed.stderr
    assert "assembly.lock.json were not changed" in completed.stderr
    assert ordering_source.read_bytes() == model_source_bytes
    assert ordering_output.read_bytes() == model_lock_bytes

    registration_declaration = (
        "provider::ProviderRegistration local_proof_success_registration();"
    )
    outside_namespace_header = valid_factory_header.replace(
        f"\n{registration_declaration}\n",
        "\n/* ignored closing brace: }\n"
        "provider::ProviderRegistration commented_registration();\n"
        "ignored opening brace: { */\n",
    ).replace(
        "}  // namespace lmdj::providers",
        "}  // namespace lmdj::providers"
        f"\n\n{registration_declaration}",
    )
    assert outside_namespace_header != valid_factory_header
    factory_header.write_text(outside_namespace_header, encoding="utf-8")
    completed = run_ordering_lock()
    assert completed.returncode == 2, (completed.stdout, completed.stderr)
    assert completed.stdout == ""
    assert "Provider local.proof.success factory.hpp" in completed.stderr
    assert (
        "directly inside its unique global namespace lmdj::providers block"
        in completed.stderr
    )
    assert "before assembly lock generation" in completed.stderr
    assert ordering_source.read_bytes() == model_source_bytes
    assert ordering_output.read_bytes() == model_lock_bytes

    nested_declaration_header = valid_factory_header.replace(
        f"\n{registration_declaration}\n",
        "\nnamespace detail {\n"
        f"{registration_declaration}\n"
        "}  // namespace detail\n",
    )
    outer_wrapped_header = valid_factory_header.replace(
        "namespace lmdj::providers {",
        "namespace outer {\n\nnamespace lmdj::providers {",
    ).replace(
        "}  // namespace lmdj::providers",
        "}  // namespace lmdj::providers\n\n}  // namespace outer",
    )
    scope_results = []
    for name, invalid_header in (
        ("nested-declaration", nested_declaration_header),
        ("outer-wrapped-target", outer_wrapped_header),
    ):
        assert invalid_header != valid_factory_header
        factory_header.write_text(invalid_header, encoding="utf-8")
        completed = run_ordering_lock()
        scope_results.append(
            (
                name,
                completed,
                ordering_source.read_bytes(),
                ordering_output.read_bytes(),
            )
        )
    assert [
        (name, completed.returncode)
        for name, completed, _, _ in scope_results
    ] == [
        ("nested-declaration", 2),
        ("outer-wrapped-target", 2),
    ], [
        (name, completed.stdout, completed.stderr)
        for name, completed, _, _ in scope_results
    ]
    for name, completed, source_bytes, lock_bytes in scope_results:
        assert completed.stdout == "", name
        assert "Provider local.proof.success factory.hpp" in completed.stderr
        assert (
            "directly inside its unique global namespace "
            "lmdj::providers block" in completed.stderr
        )
        assert "before assembly lock generation" in completed.stderr
        assert source_bytes == model_source_bytes, name
        assert lock_bytes == model_lock_bytes, name

    rollback_root = temp_root / "generated-pair-rollback"
    rollback_root.mkdir()
    rollback_source = rollback_root / "compiled_assembly.cpp"
    rollback_lock = rollback_root / "assembly.lock.json"
    old_source_bytes = b"old compiled assembly\n"
    old_lock_bytes = b"old assembly lock\n"
    rollback_source.write_bytes(old_source_bytes)
    rollback_lock.write_bytes(old_lock_bytes)
    original_replace = Path.replace
    replace_calls = [0]

    def fail_second_generated_replace(
        source: Path,
        target: Path,
    ) -> Path:
        replace_calls[0] += 1
        if replace_calls[0] == 2:
            raise OSError("injected second generated-pair replace failure")
        return original_replace(source, target)

    Path.replace = fail_second_generated_replace
    try:
        try:
            version_module._write_generated_pair(
                rollback_source,
                b"new compiled assembly\n",
                rollback_lock,
                b"new assembly lock\n",
            )
        except OSError as error:
            assert str(error) == (
                "injected second generated-pair replace failure"
            )
        else:
            raise AssertionError(
                "second generated-pair replace failure was not propagated"
            )
    finally:
        Path.replace = original_replace
    assert rollback_source.read_bytes() == old_source_bytes
    assert rollback_lock.read_bytes() == old_lock_bytes
    assert sorted(
        path.name
        for path in rollback_root.iterdir()
        if path.name.endswith(".tmp")
    ) == []

    isolated_root = temp_root / "isolated-repository"
    for relative in (
        "providers/local-proof-success",
        "products/lmdj/CMakeLists.txt",
        "products/lmdj/src/compiled_assembly.cpp",
    ):
        source = REPO_ROOT / relative
        destination = isolated_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
    isolated_assembly = {
        "contract": "lmdj.assembly.v2",
        "product": {"id": "lmdj", "version": "1.0.7.0"},
        "modules": [],
        "hosts": [],
        "providers": [
            {
                "id": "local.proof.success",
                "version": "2.0.1",
                "capabilities": [],
                "model_identity": None,
            }
        ],
        "contracts": [],
        "provider_policy": {
            "allowed_regions": ["local"],
            "allowed_data_classifications": ["public"],
            "granted_permissions": ["proof.execute"],
        },
    }
    isolated_assembly_path = isolated_root / "products/lmdj/assembly.json"
    isolated_assembly_path.write_bytes(canonical_bytes(isolated_assembly))
    original_repo_root = version_module.REPO_ROOT
    version_module.REPO_ROOT = isolated_root
    try:
        product_version = version_module.ProductVersion(1, 0, 6, 0)
        stale_lock = version_module._lock_document(
            product_version,
            isolated_assembly_path,
            isolated_assembly,
        )
        stale_lock_path = isolated_root / "products/lmdj/assembly.lock.json"
        stale_lock_path.write_bytes(canonical_bytes(stale_lock))
        provider_source = (
            isolated_root
            / "providers/local-proof-success/src/provider.cpp"
        )
        provider_source.write_bytes(provider_source.read_bytes() + b"\n")
        try:
            version_module._verify_lock(
                product_version,
                isolated_assembly_path,
                isolated_assembly,
                stale_lock_path,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Provider source mutation did not invalidate the old lock"
            )
    finally:
        version_module.REPO_ROOT = original_repo_root

    for name, mutate in (
        (
            "extra-module-key",
            lambda value: value["modules"][0].__setitem__("extra", True),
        ),
        (
            "invalid-provider-semver",
            lambda value: value["providers"][0].__setitem__(
                "version", "0.1"
            ),
        ),
        (
            "missing-provider-model",
            lambda value: value["providers"][0].pop("model_identity"),
        ),
        (
            "duplicate-provider-policy-region",
            lambda value: value["provider_policy"].__setitem__(
                "allowed_regions", ["local", "local"]
            ),
        ),
    ):
        invalid = json.loads(ASSEMBLY_PATH.read_text(encoding="utf-8"))
        mutate(invalid)
        invalid_path = temp_root / f"{name}.json"
        invalid_path.write_text(
            json.dumps(invalid),
            encoding="utf-8",
        )
        invalid_output = temp_root / f"{name}.lock.json"
        completed = generate(invalid_output, invalid_path)
        assert completed.returncode == 2, (
            name,
            completed.stdout,
            completed.stderr,
        )
        assert completed.stdout == ""
        assert completed.stderr.startswith("version error: ")
        assert not invalid_output.exists()

    artifacts_root = temp_root / "artifacts"
    (artifacts_root / "bin").mkdir(parents=True)
    (artifacts_root / "bin" / "lmdj-core").write_bytes(b"core")
    (artifacts_root / "lib.dat").write_bytes(b"library")
    (artifacts_root / "proof-output").mkdir()
    (artifacts_root / "proof-output" / "beat.wav").write_bytes(b"stale")
    (artifacts_root / "build-manifest.json").write_bytes(b"old-manifest")
    overlay_beat = temp_root / "new-beat.wav"
    overlay_beat.write_bytes(b"new-beat")
    manifest_path = temp_root / "build-manifest.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(VERSION_SCRIPT),
            "manifest",
            "--version-file",
            str(VERSION_PATH),
            "--assembly",
            str(ASSEMBLY_PATH),
            "--lock",
            str(LOCK_PATH),
            "--channel",
            "canary",
            "--artifacts-root",
            str(artifacts_root),
            "--output",
            str(manifest_path),
            "--overlay-artifact",
            f"{overlay_beat}=proof-output/beat.wav",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        completed.stdout,
        completed.stderr,
    )
    assert completed.stdout == "build manifest generated\n"
    assert completed.stderr == ""
    manifest = load_object(manifest_path)
    assert set(manifest) == {
        "contract",
        "product",
        "channel",
        "git_revision",
        "assembly_lock_sha256",
        "build_time",
        "platform",
        "artifacts",
    }
    assert manifest["contract"] == "lmdj.build-manifest.v1"
    assert manifest["product"] == assembly["product"]
    assert manifest["channel"] == "canary"
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["git_revision"])
    assert manifest["assembly_lock_sha256"] == sha256(LOCK_PATH)
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
        manifest["build_time"],
    )
    assert manifest["platform"] == (
        f"{platform.system().lower()}-{platform.machine().lower()}"
    )
    assert manifest["artifacts"] == [
        {
            "path": "bin/lmdj-core",
            "byte_length": 4,
            "sha256": hashlib.sha256(b"core").hexdigest(),
        },
        {
            "path": "lib.dat",
            "byte_length": 7,
            "sha256": hashlib.sha256(b"library").hexdigest(),
        },
        {
            "path": "proof-output/beat.wav",
            "byte_length": 8,
            "sha256": hashlib.sha256(b"new-beat").hexdigest(),
        },
    ]
    assert manifest_path.read_text(encoding="utf-8") == (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )

print("version lock conformance: PASS")
