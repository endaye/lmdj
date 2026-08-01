import json
from pathlib import Path
import subprocess
import sys
import tempfile

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from scripts.version import ProductVersion, load_version, verify


core_cli_manifest_path = repo_root / "apps" / "core-cli" / "module.json"
core_cli_manifest = json.loads(
    core_cli_manifest_path.read_text(encoding="utf-8")
)
assert core_cli_manifest == {
    "contract": "lmdj.module.v1",
    "module": "core-cli",
    "version": "1.0.0",
    "api_version": 2,
    "dependencies": {"application-facade": "1.0.0"},
}

version = load_version("products/lmdj/version.json")
assert version == ProductVersion(1, 0, 8, 0)
assert str(version) == "1.0.8.0"
assert version.product_tag() == "lmdj-v1.0.8.0"
assert version.display("dev", "a" * 40) == "1.0.8.0 · dev · gaaaaaaaa"

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
assert tag_name.stdout == "lmdj-v1.0.8.0\n"
assert tag_name.stderr == ""

current = subprocess.run(
    [
        sys.executable,
        str(version_script),
        "current",
        "--version-file",
        "products/lmdj/version.json",
        "--channel",
        "dev",
        "--revision",
        "a" * 40,
    ],
    cwd=repo_root,
    check=True,
    capture_output=True,
    text=True,
)
assert current.stdout == "1.0.8.0 · dev · gaaaaaaaa\n"
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
assert verified.stdout == "version verification: PASS (1.0.8.0)\n"
assert verified.stderr == ""


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


assembly_path = repo_root / "products" / "lmdj" / "assembly.json"
tracked_lock_path = repo_root / "products" / "lmdj" / "assembly.lock.json"
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
