import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUEST_LIMIT = 16 * 1024 * 1024
SUBPROCESS_TIMEOUT_SECONDS = 10
PROJECT_ID = "00000000-0000-4000-8000-000000000001"
PATTERN_ID = "00000000-0000-4000-8000-000000000010"
KICK_ASSET_ID = "00000000-0000-4000-8000-000000000101"
SNARE_ASSET_ID = "00000000-0000-4000-8000-000000000102"
TAKE_ID = "00000000-0000-4000-8000-000000000201"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def lmdj_include_headers(source: str) -> list[str]:
    included_headers = re.findall(
        r'#include\s*[<"]([^>"]+)[>"]',
        source,
    )
    return [
        header for header in included_headers if header.startswith("lmdj/")
    ]


def configured_timeout(build_directory: Path, base_timeout: float) -> float:
    cache = (build_directory / "CMakeCache.txt").read_text(encoding="utf-8")
    sanitizer = next(
        (
            line.removeprefix("LMDJ_SANITIZER:STRING=")
            for line in cache.splitlines()
            if line.startswith("LMDJ_SANITIZER:STRING=")
        ),
        "none",
    )
    return base_timeout * {"address": 3.0, "thread": 4.0}.get(sanitizer, 1.0)


def subprocess_timeout(executable: Path) -> float:
    return configured_timeout(
        executable.parent.parent,
        SUBPROCESS_TIMEOUT_SECONDS,
    )


def timeout_policy_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="lmdj-cli-timeout-policy-") as temp:
        build_directory = Path(temp)
        (build_directory / "CMakeCache.txt").write_text(
            "LMDJ_SANITIZER:STRING=address\n",
            encoding="utf-8",
        )
        executable = build_directory / "bin/lmdj-core"
        executable.parent.mkdir()
        executable.touch()
        assert configured_timeout(build_directory, 10.0) == 30.0
        assert subprocess_timeout(executable) == 30.0


def encoded_request(value: object) -> str:
    return canonical_json(value)


def deeply_nested_field(prefix: str, depth: int) -> str:
    return prefix + "[" * depth + "0" + "]" * depth + "}"


def run_raw(executable: Path, arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(executable), *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        timeout=subprocess_timeout(executable),
    )


def run_valid(
    executable: Path,
    workspace: str,
    mode: str,
    source_flag: str,
    source_value: str,
    expected_exit: int,
) -> tuple[dict, bytes]:
    completed = run_raw(
        executable,
        ["--workspace", workspace, mode, source_flag, source_value],
    )
    assert completed.returncode == expected_exit, (
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )
    assert completed.stderr == b""
    stdout = completed.stdout.decode("utf-8", errors="strict")
    parsed = json.loads(stdout)
    assert isinstance(parsed, dict)
    assert stdout == canonical_json(parsed) + "\n"
    return parsed, completed.stdout


def run_request(
    executable: Path,
    workspace: Path,
    mode: str,
    request: dict,
    expected_exit: int = 0,
) -> dict:
    parsed, _ = run_valid(
        executable,
        str(workspace),
        mode,
        "--request",
        encoded_request(request),
        expected_exit,
    )
    return parsed


def check_error(response: dict, code: str) -> None:
    assert set(response) == {"ok", "error"}
    assert response["ok"] is False
    assert set(response["error"]) == {"code", "message", "details"}
    assert response["error"]["code"] == code


def check_success(response: dict, revision: int | None) -> None:
    assert set(response) == {"ok", "result", "project_revision"}
    assert response["ok"] is True
    assert isinstance(response["result"], dict)
    assert response["project_revision"] == revision


def uuid(suffix: int) -> str:
    return f"00000000-0000-4000-8000-{suffix:012d}"


def slot(bank: int, pad: int) -> dict:
    return {"bank": bank, "pad": pad}


def pattern() -> dict:
    return {
        "pattern_id": PATTERN_ID,
        "bars": 1,
        "events": [
            {"slot": slot(0, 0), "step": 0, "velocity": 127},
            {"slot": slot(0, 1), "step": 4, "velocity": 127},
            {"slot": slot(0, 0), "step": 8, "velocity": 127},
            {"slot": slot(0, 1), "step": 12, "velocity": 127},
        ],
    }


def usage_contract(executable: Path, workspace: Path) -> None:
    provider_request = encoded_request({"operation": "provider.list"})
    invalid_arguments = [
        [],
        ["--unknown"],
        ["query", "--workspace", str(workspace), "--request", provider_request],
        [
            "--workspace",
            str(workspace),
            "query",
            "--workspace",
            provider_request,
        ],
        [
            "--workspace",
            str(workspace),
            "query",
            "--request",
            provider_request,
            "extra",
        ],
        [
            "--workspace",
            str(workspace),
            "query",
            "--request",
            provider_request,
            "--request-file",
            str(workspace / "request.json"),
        ],
        ["--workspace", str(workspace), "query", "--request"],
    ]
    for arguments in invalid_arguments:
        completed = run_raw(executable, arguments)
        assert completed.returncode == 64
        assert completed.stdout == b""
        assert completed.stderr
        assert b"\x1b[" not in completed.stderr
        completed.stderr.decode("ascii", errors="strict")


def workspace_contract(executable: Path, temp_root: Path) -> None:
    provider_request = encoded_request({"operation": "provider.list"})
    for workspace in (
        "relative-workspace",
        str(temp_root / "workspace" / ".." / "workspace"),
    ):
        response, _ = run_valid(
            executable,
            workspace,
            "query",
            "--request",
            provider_request,
            2,
        )
        check_error(response, "INVALID_ARGUMENT")

    workspace = temp_root / "workspace"
    workspace.mkdir(exist_ok=True)
    response = run_request(
        executable,
        workspace,
        "query",
        {"operation": "provider.list"},
    )
    check_success(response, None)


def assembly_contract(executable: Path, temp_root: Path) -> None:
    workspace = temp_root / "assembly-workspace"
    workspace.mkdir()
    assembly = (REPO_ROOT / "products/lmdj/assembly.json").resolve()
    completed = run_raw(
        executable,
        [
            "--workspace",
            str(workspace),
            "--assembly",
            str(assembly),
            "query",
            "--request",
            encoded_request({"operation": "provider.list"}),
        ],
    )
    assert completed.returncode == 0, (
        completed.stdout,
        completed.stderr,
    )
    assert completed.stderr == b""
    response = json.loads(completed.stdout)
    check_success(response, None)
    assert [
        provider["id"] for provider in response["result"]["providers"]
    ] == ["local.proof.failure", "local.proof.success"]

    invalid = temp_root / "invalid-assembly.json"
    invalid.write_text("{}", encoding="utf-8")
    completed = run_raw(
        executable,
        [
            "--workspace",
            str(workspace),
            "--assembly",
            str(invalid),
            "query",
            "--request",
            encoded_request({"operation": "provider.list"}),
        ],
    )
    assert completed.returncode == 2
    assert completed.stderr == b""
    response = json.loads(completed.stdout)
    check_error(response, "INVALID_ARGUMENT")

    deep_assembly = temp_root / "deep-assembly.json"
    deep_assembly.write_text(
        deeply_nested_field('{"contract":"lmdj.assembly.v2","nested":', 200_000),
        encoding="utf-8",
    )
    completed = run_raw(
        executable,
        [
            "--workspace",
            str(workspace),
            "--assembly",
            str(deep_assembly),
            "query",
            "--request",
            encoded_request({"operation": "provider.list"}),
        ],
    )
    assert completed.returncode == 2
    assert completed.stderr == b""
    check_error(json.loads(completed.stdout), "INVALID_ARGUMENT")


def request_source_parity(
    executable: Path, workspace: Path, temp_root: Path
) -> None:
    request = {"operation": "provider.list"}
    request_path = temp_root / "provider-list.json"
    request_path.write_text(encoded_request(request), encoding="utf-8")
    inline, inline_bytes = run_valid(
        executable,
        str(workspace),
        "query",
        "--request",
        encoded_request(request),
        0,
    )
    from_file, file_bytes = run_valid(
        executable,
        str(workspace),
        "query",
        "--request-file",
        str(request_path),
        0,
    )
    assert inline_bytes == file_bytes
    assert inline == from_file
    check_success(inline, None)
    assert inline["result"]["providers"] == []


def request_validation(
    executable: Path, workspace: Path, temp_root: Path
) -> None:
    for content in ("", "{", "[]"):
        response, _ = run_valid(
            executable,
            str(workspace),
            "query",
            "--request",
            content,
            2,
        )
        check_error(response, "INVALID_ARGUMENT")

    invalid_utf8 = temp_root / "invalid-utf8.json"
    invalid_utf8.write_bytes(b'{"operation":"provider.list","bad":"\xff"}')
    response, _ = run_valid(
        executable,
        str(workspace),
        "query",
        "--request-file",
        str(invalid_utf8),
        2,
    )
    check_error(response, "INVALID_ARGUMENT")

    accepted_depth_request = temp_root / "accepted-depth-request.json"
    accepted_depth_request.write_text(
        deeply_nested_field('{"operation":"provider.list","nested":', 63),
        encoding="utf-8",
    )
    response, _ = run_valid(
        executable,
        str(workspace),
        "query",
        "--request-file",
        str(accepted_depth_request),
        2,
    )
    check_error(response, "INVALID_ARGUMENT")
    assert response["error"]["message"] == (
        "provider.list request shape is invalid"
    )

    excessive_depth_request = temp_root / "excessive-depth-request.json"
    excessive_depth_request.write_text(
        deeply_nested_field('{"operation":"provider.list","nested":', 64),
        encoding="utf-8",
    )
    response, _ = run_valid(
        executable,
        str(workspace),
        "query",
        "--request-file",
        str(excessive_depth_request),
        2,
    )
    check_error(response, "INVALID_ARGUMENT")
    assert response["error"]["message"] == (
        "request must be a UTF-8 JSON object no larger than 16777216 bytes"
    )

    crash_depth_request = temp_root / "crash-depth-request.json"
    crash_depth_request.write_text(
        deeply_nested_field('{"operation":"provider.list","nested":', 200_000),
        encoding="utf-8",
    )
    response, _ = run_valid(
        executable,
        str(workspace),
        "query",
        "--request-file",
        str(crash_depth_request),
        2,
    )
    check_error(response, "INVALID_ARGUMENT")

    boundary = temp_root / "request-limit.json"
    request_prefix = encoded_request(
        {"operation": "provider.list"}
    ).encode("utf-8")
    boundary.write_bytes(
        request_prefix + b" " * (REQUEST_LIMIT - len(request_prefix))
    )
    response, _ = run_valid(
        executable,
        str(workspace),
        "query",
        "--request-file",
        str(boundary),
        0,
    )
    check_success(response, None)
    with boundary.open("ab") as stream:
        stream.write(b" ")
    response, _ = run_valid(
        executable,
        str(workspace),
        "query",
        "--request-file",
        str(boundary),
        2,
    )
    check_error(response, "INVALID_ARGUMENT")

    for request_path in (
        temp_root / "missing.json",
        temp_root,
    ):
        response, _ = run_valid(
            executable,
            str(workspace),
            "query",
            "--request-file",
            str(request_path),
            2,
        )
        check_error(response, "IO_ERROR")

    if hasattr(os, "mkfifo"):
        fifo = temp_root / "request.fifo"
        os.mkfifo(fifo)
        response, _ = run_valid(
            executable,
            str(workspace),
            "query",
            "--request-file",
            str(fifo),
            2,
        )
        check_error(response, "IO_ERROR")

    regular_target = temp_root / "symlink-target.json"
    regular_target.write_text(
        encoded_request({"operation": "provider.list"}),
        encoding="utf-8",
    )
    symlink_request = temp_root / "symlink-request.json"
    symlink_request.symlink_to(regular_target)
    response, _ = run_valid(
        executable,
        str(workspace),
        "query",
        "--request-file",
        str(symlink_request),
        0,
    )
    check_success(response, None)


def facade_routing_and_exit_mapping(
    executable: Path, workspace: Path, temp_root: Path
) -> None:
    response = run_request(
        executable,
        workspace,
        "query",
        {"operation": "provider.list"},
    )
    check_success(response, None)

    for mode, request in (
        ("query", {"operation": "unknown"}),
        (
            "query",
            {
                "operation": "project.create",
                "project_path": str(temp_root / "wrong-route.lmdj"),
                "project_id": PROJECT_ID,
                "bpm": 120,
            },
        ),
        ("command", {"operation": "provider.list"}),
    ):
        response = run_request(
            executable, workspace, mode, request, expected_exit=2
        )
        check_error(response, "INVALID_ARGUMENT")

    if os.name == "posix":
        read_descriptor, write_descriptor = os.pipe()
        os.close(read_descriptor)
        try:
            process = subprocess.Popen(
                [
                    str(executable),
                    "--workspace",
                    str(workspace),
                    "query",
                    "--request",
                    encoded_request({"operation": "provider.list"}),
                ],
                cwd=REPO_ROOT,
                stdout=write_descriptor,
                stderr=subprocess.PIPE,
            )
        finally:
            os.close(write_descriptor)
        try:
            _, stderr = process.communicate(
                timeout=subprocess_timeout(executable)
            )
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate(
                timeout=subprocess_timeout(executable)
            )
            raise
        assert process.returncode == 2, process.returncode
        assert stderr == b""


def author_golden_project(
    executable: Path, workspace: Path, temp_root: Path
) -> tuple[Path, dict, bytes]:
    project = temp_root / "proof-beat.lmdj"
    requests: list[tuple[str, dict, int]] = [
        (
            "command",
            {
                "operation": "project.create",
                "project_path": str(project),
                "project_id": PROJECT_ID,
                "bpm": 120,
            },
            0,
        ),
        (
            "command",
            {
                "operation": "asset.import",
                "project_path": str(project),
                "command_id": uuid(1),
                "expected_revision": 0,
                "asset_id": KICK_ASSET_ID,
                "source_path": str(
                    REPO_ROOT / "tests/fixtures/audio/kick.wav"
                ),
                "media_type": "audio/wav",
            },
            1,
        ),
        (
            "command",
            {
                "operation": "asset.import",
                "project_path": str(project),
                "command_id": uuid(2),
                "expected_revision": 1,
                "asset_id": SNARE_ASSET_ID,
                "source_path": str(
                    REPO_ROOT / "tests/fixtures/audio/snare.wav"
                ),
                "media_type": "audio/wav",
            },
            2,
        ),
        (
            "command",
            {
                "operation": "pad.assign",
                "project_path": str(project),
                "command_id": uuid(3),
                "expected_revision": 2,
                "slot": slot(0, 0),
                "asset_id": KICK_ASSET_ID,
            },
            3,
        ),
        (
            "command",
            {
                "operation": "pad.assign",
                "project_path": str(project),
                "command_id": uuid(4),
                "expected_revision": 3,
                "slot": slot(0, 1),
                "asset_id": SNARE_ASSET_ID,
            },
            4,
        ),
        (
            "command",
            {
                "operation": "take.begin",
                "project_path": str(project),
                "take_id": TAKE_ID,
                "expected_revision": 4,
                "sample_rate": 48000,
            },
            4,
        ),
    ]
    for mode, request, revision in requests:
        response = run_request(executable, workspace, mode, request)
        check_success(response, revision)

    for pad, frame_offset, event_count in (
        (0, 0, 1),
        (1, 24000, 2),
        (0, 48000, 3),
        (1, 72000, 4),
    ):
        response = run_request(
            executable,
            workspace,
            "command",
            {
                "operation": "take.append",
                "project_path": str(project),
                "take_id": TAKE_ID,
                "event": {
                    "slot": slot(0, pad),
                    "frame_offset": frame_offset,
                    "velocity": 127,
                },
            },
        )
        check_success(response, 4)
        assert response["result"]["event_count"] == event_count

    commit_request = {
        "operation": "take.commit",
        "project_path": str(project),
        "command_id": uuid(5),
        "expected_revision": 4,
        "take_id": TAKE_ID,
        "pattern": pattern(),
    }
    response = run_request(
        executable, workspace, "command", commit_request
    )
    check_success(response, 5)
    assert response["result"]["committed_revision"] == 5
    assert response["result"]["replayed"] is False
    active_journal = (
        project / "recovery" / "active" / f"{TAKE_ID}.jsonl"
    )
    assert not active_journal.exists()

    inspected = run_request(
        executable,
        workspace,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )
    check_success(inspected, 5)
    projected = inspected["result"]["project"]
    assert sum(len(bank["pads"]) for bank in projected["banks"]) == 64
    assert len(projected["assets"]) == 2
    assert len(projected["takes"]) == 1
    assert len(projected["patterns"]) == 1
    assert len(projected["takes"][TAKE_ID]["events"]) == 4
    assert len(projected["patterns"][PATTERN_ID]["events"]) == 4
    return project, commit_request, (project / "manifest.json").read_bytes()


def separate_process_authoring(
    executable: Path, workspace: Path, temp_root: Path
) -> tuple[Path, dict, bytes]:
    return author_golden_project(executable, workspace, temp_root)


def fresh_process_replay(
    executable: Path,
    workspace: Path,
    project: Path,
    commit_request: dict,
) -> None:
    manifest_before = (project / "manifest.json").read_bytes()
    response = run_request(
        executable, workspace, "command", commit_request
    )
    check_success(response, 5)
    assert response["result"]["committed_revision"] == 5
    assert response["result"]["replayed"] is True
    active_journal = (
        project / "recovery" / "active" / f"{TAKE_ID}.jsonl"
    )
    assert not active_journal.exists()
    assert (project / "manifest.json").read_bytes() == manifest_before


def fresh_process_snapshot_render_golden(
    executable: Path,
    workspace: Path,
    temp_root: Path,
    project: Path,
) -> None:
    manifest_before = (project / "manifest.json").read_bytes()
    snapshot = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "snapshot.cook",
            "project_path": str(project),
            "pattern_id": PATTERN_ID,
        },
    )
    check_success(snapshot, 5)
    assert snapshot["result"]["event_count"] == 4
    assert "snapshot_id" not in canonical_json(snapshot)

    output = temp_root / "rendered.wav"
    render_request = {
        "operation": "render.offline",
        "project_path": str(project),
        "pattern_id": PATTERN_ID,
        "output_path": str(output),
    }
    assert "snapshot_id" not in render_request
    rendered = run_request(
        executable, workspace, "command", render_request
    )
    check_success(rendered, 5)
    assert "snapshot_id" not in canonical_json(rendered)
    golden = REPO_ROOT / "tests/fixtures/golden/one_bar_120bpm.wav"
    expected_sha = (
        REPO_ROOT / "tests/fixtures/golden/one_bar_120bpm.sha256"
    ).read_text(encoding="ascii").split()[0]
    assert output.read_bytes() == golden.read_bytes()
    assert hashlib.sha256(output.read_bytes()).hexdigest() == expected_sha
    assert rendered["result"]["artifact"]["sha256"] == expected_sha
    assert (project / "manifest.json").read_bytes() == manifest_before


def host_boundary_and_identity(executable: Path) -> None:
    version = json.loads(
        (REPO_ROOT / "products/lmdj/version.json").read_text(
            encoding="utf-8"
        )
    )
    assert version == {
        "contract": "lmdj.product-version.v1",
        "product": "lmdj",
        "milestone": 1,
        "minor": 0,
        "build": 16,
        "patch": 6,
    }
    manifest = json.loads(
        (REPO_ROOT / "apps/core-cli/module.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest == {
        "contract": "lmdj.module.v1",
        "module": "core-cli",
        "version": "1.0.8",
        "api_version": 2,
        "dependencies": {"application-facade": "1.3.2"},
    }

    root_cmake = (REPO_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    source = (REPO_ROOT / "apps/core-cli/src/main.cpp").read_text(
        encoding="utf-8"
    )
    assert root_cmake.index("add_subdirectory(packages/application-facade)") < (
        root_cmake.index("add_subdirectory(apps/core-cli)")
    )
    build_directory = executable.parent.parent
    link_metadata = (
        build_directory
        / "apps/core-cli/lmdj_core_cli.link-libraries.txt"
    )
    direct_dependencies = [
        dependency
        for dependency in link_metadata.read_text(
            encoding="utf-8"
        ).strip().split(";")
        if dependency and not dependency.startswith("::@")
    ]
    assert direct_dependencies == [
        "lmdj::application",
        "lmdj_product_lmdj_assembly",
    ]

    ctest = subprocess.run(
        [
            "ctest",
            "--test-dir",
            str(build_directory),
            "--show-only=json-v1",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=subprocess_timeout(executable),
    )
    tests = json.loads(ctest.stdout)["tests"]
    host_test = next(test for test in tests if test["name"] == "host.cli")
    assert host_test["command"][1] == str(
        REPO_ROOT / "tests/host/cli_test.py"
    )
    assert Path(host_test["command"][2]).resolve() == executable
    properties = {
        item["name"]: item["value"] for item in host_test["properties"]
    }
    assert properties["TIMEOUT"] == configured_timeout(build_directory, 60.0)

    assert lmdj_include_headers(
        '#include <lmdj/angle.hpp>\n'
        '#include "lmdj/quoted.hpp"\n'
        "#include <vector>\n"
    ) == ["lmdj/angle.hpp", "lmdj/quoted.hpp"]
    lmdj_headers = lmdj_include_headers(source)
    assert lmdj_headers == [
        "lmdj/facade/application.hpp",
        "lmdj/facade/assembly_loader.hpp",
    ]
    for forbidden in (
        "project_io",
        "manifest.json",
        "history/checkpoints",
        "history/transactions",
        "recovery",
        '"operation"',
    ):
        assert forbidden not in source
    assert "std::filesystem::is_regular_file" not in source
    assert "std::ifstream" not in source


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: cli_test.py /absolute/path/to/lmdj-core")
    executable = Path(sys.argv[1]).expanduser().resolve(strict=True)

    passed = 0
    with tempfile.TemporaryDirectory(prefix="lmdj-cli-test-") as temp:
        temp_root = Path(temp).resolve()
        workspace = temp_root / "workspace"
        workspace.mkdir()

        usage_contract(executable, workspace)
        passed += 1
        workspace_contract(executable, temp_root)
        passed += 1
        assembly_contract(executable, temp_root)
        passed += 1
        request_source_parity(executable, workspace, temp_root)
        passed += 1
        request_validation(executable, workspace, temp_root)
        passed += 1
        facade_routing_and_exit_mapping(
            executable, workspace, temp_root
        )
        passed += 1
        project, commit_request, _ = separate_process_authoring(
            executable, workspace, temp_root
        )
        passed += 1
        fresh_process_replay(
            executable, workspace, project, commit_request
        )
        passed += 1
        fresh_process_snapshot_render_golden(
            executable, workspace, temp_root, project
        )
        passed += 1
        host_boundary_and_identity(executable)
        passed += 1
        timeout_policy_contract()
        passed += 1

    assert passed == 11
    print("cli behavior fixtures: 11 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
