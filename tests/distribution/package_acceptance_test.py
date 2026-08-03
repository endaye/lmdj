#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_VERSION = "2025-11-25"
PROJECT_ID = "00000000-0000-4000-8000-000000000001"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    sanitizer_runtime = environment.get("LMDJ_ASAN_RUNTIME")
    if sanitizer_runtime:
        if sys.platform == "darwin":
            environment["DYLD_INSERT_LIBRARIES"] = sanitizer_runtime
        elif sys.platform.startswith("linux"):
            environment["LD_PRELOAD"] = sanitizer_runtime
    return environment


def run_cli(
    executable: Path,
    workspace: Path,
    surface: str,
    request: dict,
    environment: dict[str, str],
) -> dict:
    completed = subprocess.run(
        [
            str(executable),
            "--workspace",
            str(workspace),
            surface,
            "--request",
            canonical_json(request),
        ],
        cwd=workspace.parent,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        completed.stdout,
        completed.stderr,
    )
    assert completed.stderr == ""
    response = json.loads(completed.stdout)
    assert completed.stdout == canonical_json(response) + "\n"
    return response


def mcp_provider_list(
    executable: Path,
    workspace: Path,
    environment: dict[str, str],
) -> dict:
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "package-acceptance",
                    "version": "1.0.0",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "lmdj.provider.list",
                "arguments": {},
            },
        },
    ]
    completed = subprocess.run(
        [str(executable), "--workspace", str(workspace)],
        cwd=workspace.parent,
        env=environment,
        input="".join(canonical_json(message) + "\n" for message in messages),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        completed.stdout,
        completed.stderr,
    )
    assert completed.stderr == ""
    responses = [
        json.loads(line)
        for line in completed.stdout.splitlines()
        if line
    ]
    assert [response["id"] for response in responses] == [1, 2]
    assert responses[0]["result"]["protocolVersion"] == PROTOCOL_VERSION
    tool_result = responses[1]["result"]
    assert tool_result["isError"] is False
    assert json.loads(tool_result["content"][0]["text"]) == (
        tool_result["structuredContent"]
    )
    return tool_result["structuredContent"]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-root", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    options = parse_arguments()
    build_root = options.build_root.expanduser().resolve(strict=True)
    unzip = shutil.which("unzip")
    assert unzip is not None, "package acceptance requires unzip"

    with tempfile.TemporaryDirectory(
        prefix="lmdj-core-package-acceptance-"
    ) as temporary:
        temporary_root = Path(temporary).resolve()
        output_dir = temporary_root / "output"
        environment = clean_environment()
        package_environment = environment.copy()
        package_environment["PYTHONPATH"] = "/nonexistent/lmdj-poison"
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/package-core.py"),
                "--build-root",
                str(build_root),
                "--output-dir",
                str(output_dir),
                # This test exercises packaging mechanics, not release
                # provenance, so it runs against a possibly modified tree.
                "--allow-modified-worktree",
            ],
            cwd=REPO_ROOT,
            env=package_environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, (
            completed.stdout,
            completed.stderr,
        )
        assert completed.stderr == ""
        lines = completed.stdout.splitlines()
        assert len(lines) == 1, lines
        archive = Path(lines[0]).resolve(strict=True)
        assert archive.parent == output_dir.resolve()
        assert archive.suffix == ".zip"

        # A detached digest is the only out-of-band integrity signal a consumer
        # has; build-manifest.json ships inside the archive.
        checksum = archive.with_name(archive.name + ".sha256")
        assert checksum.is_file(), checksum
        assert checksum.read_text(encoding="utf-8") == (
            f"{sha256(archive)}  {archive.name}\n"
        )

        extraction = temporary_root / "fresh-extraction"
        extraction.mkdir()
        extracted = subprocess.run(
            [unzip, "-q", str(archive), "-d", str(extraction)],
            cwd=temporary_root,
            check=False,
            capture_output=True,
            text=True,
        )
        assert extracted.returncode == 0, (
            extracted.stdout,
            extracted.stderr,
        )
        roots = list(extraction.iterdir())
        assert len(roots) == 1 and roots[0].is_dir(), roots
        package_root = roots[0]
        library_name = (
            "liblmdj_core_c.dylib"
            if sys.platform == "darwin"
            else "liblmdj_core_c.so"
        )
        expected = {
            "README.md",
            "bin/lmdj-core",
            "bin/lmdj-core-mcp",
            "bin/lmdj-native-host",
            "build-manifest.json",
            f"lib/{library_name}",
            "libexec/lmdj-core",
            "python/lmdj_core_mcp/__init__.py",
            "python/lmdj_core_mcp/__main__.py",
            "python/lmdj_core_mcp/c_api.py",
            "python/lmdj_core_mcp/server.py",
            "share/lmdj/assembly.json",
            "share/lmdj/assembly.lock.json",
            "share/lmdj/contracts/assembly/lmdj.assembly.v2.schema.json",
            "share/lmdj/version.json",
        }
        actual = {
            path.relative_to(package_root).as_posix()
            for path in package_root.rglob("*")
            if path.is_file()
        }
        assert actual == expected, (actual - expected, expected - actual)
        for path in package_root.rglob("*"):
            assert not path.is_symlink(), path
        for relative in (
            "bin/lmdj-core",
            "bin/lmdj-core-mcp",
            "bin/lmdj-native-host",
            "libexec/lmdj-core",
        ):
            mode = (package_root / relative).stat().st_mode
            assert mode & stat.S_IXUSR, relative

        manifest = json.loads(
            (package_root / "build-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        version = json.loads(
            (package_root / "share/lmdj/version.json").read_text(
                encoding="utf-8"
            )
        )
        product_version = (
            f"{version['milestone']}.{version['minor']}."
            f"{version['build']}.{version['patch']}"
        )
        assert manifest["product"] == {
            "id": version["product"],
            "version": product_version,
        }
        assert manifest["assembly_lock_sha256"] == sha256(
            package_root / "share/lmdj/assembly.lock.json"
        )
        assert len(manifest["git_revision"]) == 40
        manifest_artifacts = {
            artifact["path"]: (
                artifact["byte_length"],
                artifact["sha256"],
            )
            for artifact in manifest["artifacts"]
        }
        assert set(manifest_artifacts) == expected - {
            "build-manifest.json"
        }
        for relative, (byte_length, digest) in manifest_artifacts.items():
            path = package_root / relative
            assert byte_length == path.stat().st_size
            assert digest == sha256(path)

        workspace = temporary_root / "workspace"
        workspace.mkdir()
        project = temporary_root / "package-proof.lmdj"
        created = run_cli(
            package_root / "bin/lmdj-core",
            workspace,
            "command",
            {
                "operation": "project.create",
                "project_path": str(project),
                "project_id": PROJECT_ID,
                "bpm": 120,
            },
            environment,
        )
        assert created["ok"] is True
        cli_providers = run_cli(
            package_root / "bin/lmdj-core",
            workspace,
            "query",
            {"operation": "provider.list"},
            environment,
        )
        mcp_workspace = temporary_root / "mcp-workspace"
        mcp_workspace.mkdir()
        mcp_providers = mcp_provider_list(
            package_root / "bin/lmdj-core-mcp",
            mcp_workspace,
            environment,
        )
        assert mcp_providers == cli_providers
        native_usage = subprocess.run(
            [str(package_root / "bin/lmdj-native-host"), "--no-device"],
            cwd=workspace.parent,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert native_usage.returncode == 64
        assert native_usage.stdout == ""
        assert native_usage.stderr.startswith("usage: lmdj-native-host ")
        for launcher in (
            package_root / "bin/lmdj-core",
            package_root / "bin/lmdj-core-mcp",
        ):
            assert str(REPO_ROOT) not in launcher.read_text(encoding="utf-8")

    print("core distribution package acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
