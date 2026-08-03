#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.version import generate_manifest, verify


class PackageError(RuntimeError):
    pass


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    # Packaging a modified tree is refused by default because the recorded Git
    # revision would not describe the contents. The acceptance test exercises
    # packaging mechanics rather than release provenance, so it opts out.
    parser.add_argument(
        "--allow-modified-worktree", action="store_true"
    )
    return parser.parse_args()


def normalized_platform() -> tuple[str, str, str]:
    if sys.platform == "darwin":
        platform_name = "macos"
        library_name = "liblmdj_core_c.dylib"
    elif sys.platform.startswith("linux"):
        platform_name = "linux"
        library_name = "liblmdj_core_c.so"
    else:
        raise PackageError(f"unsupported platform: {sys.platform}")
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        architecture = "arm64"
    elif machine in {"x86_64", "amd64"}:
        architecture = "x86_64"
    else:
        raise PackageError(f"unsupported architecture: {machine}")
    return platform_name, architecture, library_name


def require_directory(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise PackageError(f"{label} must be a real directory: {path}")
    return path.resolve()


def require_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise PackageError(f"{label} must be a real file: {path}")
    return path.resolve()


def copy_file(source: Path, destination: Path, mode: int) -> None:
    require_file(source, "package input")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(mode)


def write_file(destination: Path, content: str, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8", newline="\n")
    destination.chmod(mode)


def cli_launcher() -> str:
    return """#!/usr/bin/env sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
package_root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
for argument in "$@"; do
  if [ "$argument" = "--assembly" ]; then
    exec "$package_root/libexec/lmdj-core" "$@"
  fi
done
if [ "$#" -ge 2 ] && [ "$1" = "--workspace" ]; then
  workspace=$2
  shift 2
  exec "$package_root/libexec/lmdj-core" \\
    --workspace "$workspace" \\
    --assembly "$package_root/share/lmdj/assembly.json" "$@"
fi
exec "$package_root/libexec/lmdj-core" "$@"
"""


def mcp_launcher() -> str:
    return """#!/usr/bin/env python3
from pathlib import Path
import runpy
import sys

package_root = Path(__file__).resolve(strict=True).parent.parent
if sys.platform == "darwin":
    library_name = "liblmdj_core_c.dylib"
elif sys.platform.startswith("linux"):
    library_name = "liblmdj_core_c.so"
else:
    raise SystemExit("lmdj-core-mcp: unsupported platform")
library = (package_root / "lib" / library_name).resolve(strict=True)
assembly = (package_root / "share/lmdj/assembly.json").resolve(strict=True)
python_root = (package_root / "python").resolve(strict=True)
arguments = sys.argv[1:]
assembly_arguments = [] if "--assembly" in arguments else [
    "--assembly",
    str(assembly),
]
sys.path.insert(0, str(python_root))
sys.argv = [
    "lmdj-core-mcp",
    "--library",
    str(library),
    *assembly_arguments,
    *arguments,
]
runpy.run_module("lmdj_core_mcp", run_name="__main__")
"""


def stage_package(
    package_root: Path,
    build_root: Path,
    library_name: str,
) -> None:
    copy_file(
        build_root / "bin/lmdj-core",
        package_root / "libexec/lmdj-core",
        0o755,
    )
    copy_file(
        build_root / "lib" / library_name,
        package_root / "lib" / library_name,
        0o644,
    )
    copy_file(
        build_root / "bin/lmdj-native-host",
        package_root / "bin/lmdj-native-host",
        0o755,
    )
    write_file(package_root / "bin/lmdj-core", cli_launcher(), 0o755)
    write_file(
        package_root / "bin/lmdj-core-mcp",
        mcp_launcher(),
        0o755,
    )
    for name in ("__init__.py", "__main__.py", "c_api.py", "server.py"):
        copy_file(
            REPO_ROOT / "apps/core-mcp/lmdj_core_mcp" / name,
            package_root / "python/lmdj_core_mcp" / name,
            0o644,
        )
    for name in ("assembly.json", "assembly.lock.json", "version.json"):
        copy_file(
            REPO_ROOT / "products/lmdj" / name,
            package_root / "share/lmdj" / name,
            0o644,
        )
    copy_file(
        REPO_ROOT / "contracts/assembly/lmdj.assembly.v2.schema.json",
        package_root / "share/lmdj/contracts/assembly/lmdj.assembly.v2.schema.json",
        0o644,
    )
    copy_file(
        REPO_ROOT / "packaging/core/README.md",
        package_root / "README.md",
        0o644,
    )


def validate_manifest(manifest: dict, package_root: Path, version: str) -> None:
    if manifest.get("product") != {"id": "lmdj", "version": version}:
        raise PackageError("Build Manifest Product identity is invalid")
    revision = manifest.get("git_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or any(character not in "0123456789abcdef" for character in revision)
    ):
        raise PackageError("Build Manifest Git revision is invalid")
    staged_lock = package_root / "share/lmdj/assembly.lock.json"
    expected_lock = json.loads(
        (REPO_ROOT / "products/lmdj/assembly.lock.json").read_text(
            encoding="utf-8"
        )
    )
    if json.loads(staged_lock.read_text(encoding="utf-8")) != expected_lock:
        raise PackageError("staged Assembly lock does not match source")


def create_zip(package_root: Path, archive: Path) -> None:
    temporary_archive = package_root.parent / f".{archive.name}.tmp"
    with zipfile.ZipFile(
        temporary_archive,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as output:
        for source in sorted(package_root.rglob("*")):
            if source.is_symlink():
                raise PackageError(f"package contains a symlink: {source}")
            if not source.is_file():
                continue
            relative = source.relative_to(package_root.parent).as_posix()
            if relative.startswith("/") or ".." in Path(relative).parts:
                raise PackageError(f"package path is unsafe: {relative}")
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = stat.S_IMODE(source.stat().st_mode)
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(info, source.read_bytes(), compresslevel=9)
    os.replace(temporary_archive, archive)


def require_clean_worktree() -> None:
    """A package records HEAD as the revision it was built from.

    On a modified tree HEAD does not describe the contents, so the Build
    Manifest would attest to something untrue. This is enforced here rather
    than in generate_manifest() because `core.sh proof` legitimately builds a
    Manifest from a working tree, while a distributable artifact must not.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PackageError(
            "git status failed, so package provenance cannot be established"
        )
    if result.stdout.strip():
        raise PackageError(
            "refusing to package a modified working tree; the recorded Git "
            "revision would not describe the packaged contents:\n"
            + result.stdout.rstrip()
        )


def package(
    build_root_arg: Path,
    output_dir_arg: Path,
    require_clean: bool = True,
) -> Path:
    if require_clean:
        require_clean_worktree()
    build_root = require_directory(
        build_root_arg.expanduser(), "build root"
    )
    output_dir_arg = output_dir_arg.expanduser()
    if output_dir_arg.exists() and output_dir_arg.is_symlink():
        raise PackageError("output directory must not be a symlink")
    output_dir_arg.mkdir(parents=True, exist_ok=True)
    output_dir = require_directory(output_dir_arg, "output directory")
    platform_name, architecture, library_name = normalized_platform()
    version = verify(
        REPO_ROOT / "products/lmdj/version.json",
        assembly_path=REPO_ROOT / "products/lmdj/assembly.json",
        lock_path=REPO_ROOT / "products/lmdj/assembly.lock.json",
    )
    package_name = (
        f"lmdj-core-{version}-{platform_name}-{architecture}"
    )
    archive = output_dir / f"{package_name}.zip"
    with tempfile.TemporaryDirectory(
        prefix=".lmdj-core-package-",
        dir=output_dir,
    ) as temporary:
        package_root = Path(temporary) / package_name
        package_root.mkdir()
        stage_package(package_root, build_root, library_name)
        manifest = generate_manifest(
            REPO_ROOT / "products/lmdj/version.json",
            REPO_ROOT / "products/lmdj/assembly.json",
            REPO_ROOT / "products/lmdj/assembly.lock.json",
            "canary",
            package_root,
            package_root / "build-manifest.json",
        )
        (package_root / "build-manifest.json").chmod(0o644)
        validate_manifest(manifest, package_root, str(version))
        create_zip(package_root, archive)
    # A detached digest is the only out-of-band integrity signal a consumer
    # gets: build-manifest.json lives inside the archive, so anyone who can
    # rewrite the archive can rewrite it too.
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_name(archive.name + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    checksum.chmod(0o644)
    return archive.resolve(strict=True)


def main() -> int:
    options = parse_arguments()
    try:
        archive = package(
            options.build_root,
            options.output_dir,
            require_clean=not options.allow_modified_worktree,
        )
    except (OSError, PackageError, ValueError, zipfile.BadZipFile) as error:
        print(f"package error: {error}", file=sys.stderr)
        return 2
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
