from pathlib import Path
import subprocess
import sys

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from scripts.version import ProductVersion, load_version


version = load_version("products/lmdj/version.json")
assert version == ProductVersion(1, 0, 1, 0)
assert str(version) == "1.0.1.0"
assert version.product_tag() == "lmdj-v1.0.1.0"
assert version.display("dev", "a" * 40) == "1.0.1.0 · dev · gaaaaaaaa"

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
assert tag_name.stdout == "lmdj-v1.0.1.0\n"
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
assert current.stdout == "1.0.1.0 · dev · gaaaaaaaa\n"
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
assert verified.stdout == "version verification: PASS (1.0.1.0)\n"
assert verified.stderr == ""

print("product version tests: PASS")
