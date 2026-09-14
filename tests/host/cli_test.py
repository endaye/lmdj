import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
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
            {
                "slot": slot(0, 0),
                "onset_tick": 0,
                "duration_tick": 240,
                "velocity": 127,
            },
            {
                "slot": slot(0, 1),
                "onset_tick": 960,
                "duration_tick": 240,
                "velocity": 127,
            },
            {
                "slot": slot(0, 0),
                "onset_tick": 1920,
                "duration_tick": 240,
                "velocity": 127,
            },
            {
                "slot": slot(0, 1),
                "onset_tick": 2880,
                "duration_tick": 240,
                "velocity": 127,
            },
        ],
    }


def usage_contract(executable: Path, workspace: Path) -> None:
    provider_request = encoded_request({"operation": "provider.list"})
    expected_usage = (
        b"usage: lmdj-core --workspace WORKSPACE [--assembly ASSEMBLY] "
        b"(command|query|session) (--request JSON|--request-file FILE)\n"
    )
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
        ["--workspace", str(workspace), "session", "extra"],
        [
            "--workspace",
            str(workspace),
            "--assembly",
            str(REPO_ROOT / "products/lmdj/assembly.json"),
            "session",
            "extra",
        ],
    ]
    for arguments in invalid_arguments:
        completed = run_raw(executable, arguments)
        assert completed.returncode == 64
        assert completed.stdout == b""
        assert completed.stderr == expected_usage
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
    ] == ["local.proof.failure", "local.proof.success", "local.sample.slice"]

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
                "initial_pattern": pattern(),
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
                "initial_pattern": pattern(),
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
                "operation": "pad.assign",
                "project_path": str(project),
                "command_id": uuid(5),
                "expected_revision": 4,
                "slot": slot(0, 0),
                "asset_id": KICK_ASSET_ID,
            },
            5,
        ),
    ]
    for mode, request, revision in requests:
        response = run_request(executable, workspace, mode, request)
        check_success(response, revision)

    commit_request = requests[-1][1]
    active_journal = project / "recovery/active/sequence.jsonl"
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
    assert len(projected["patterns"]) == 1
    assert len(projected["patterns"][PATTERN_ID]["events"]) == 4
    return project, commit_request, (project / "manifest.json").read_bytes()


def separate_process_authoring(
    executable: Path, workspace: Path, temp_root: Path
) -> tuple[Path, dict, bytes]:
    return author_golden_project(executable, workspace, temp_root)


def sample_facade_contract(
    executable: Path, workspace: Path, temp_root: Path
) -> None:
    project = temp_root / "cli-sample.lmdj"
    for mode, request, revision in (
        (
            "command",
            {
                "operation": "project.create",
                "project_path": str(project),
                "project_id": uuid(701),
                "bpm": 120,
            },
            0,
        ),
        (
            "command",
            {
                "operation": "asset.import",
                "project_path": str(project),
                "command_id": uuid(702),
                "expected_revision": 0,
                "asset_id": uuid(703),
                "source_path": str(
                    REPO_ROOT / "tests/fixtures/audio/mono-44100.wav"
                ),
                "media_type": "audio/wav",
            },
            1,
        ),
        (
            "command",
            {
                "operation": "pad.assign",
                "project_path": str(project),
                "command_id": uuid(704),
                "expected_revision": 1,
                "slot": slot(0, 0),
                "asset_id": uuid(703),
            },
            2,
        ),
    ):
        check_success(
            run_request(executable, workspace, mode, request), revision
        )

    inspected = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "sample.inspect",
            "project_path": str(project),
            "slot": slot(0, 0),
        },
    )
    check_success(inspected, 2)
    assert inspected["result"]["metadata"] == {
        "sample_rate": 44100,
        "channels": 1,
        "source_frames": 8,
    }
    quota = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "sample.quota",
            "project_path": str(project),
            "slot": slot(0, 0),
        },
    )
    check_success(quota, 2)
    assert quota["result"]["effective_remaining_frames"] == 16_777_216
    assert quota["result"]["consumed"] == [
        {
            "slot": slot(0, 0),
            "prepared_bytes": 36,
            "prepared_frames": 9,
        }
    ]
    waveform = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "sample.waveform",
            "project_path": str(project),
            "slot": slot(0, 0),
            "window": {
                "start_frame": 0,
                "end_frame": 8,
                "bucket_count": 4,
            },
        },
    )
    check_success(waveform, 2)
    assert [
        item["peak_magnitude"] for item in waveform["result"]["buckets"]
    ] == [32768, 8192, 4096, 0]
    updated = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "sample.update_pad",
            "project_path": str(project),
            "command_id": uuid(705),
            "expected_revision": 2,
            "slot": slot(0, 0),
            "playback": {
                "trim_start_frame": 1,
                "trim_end_frame": 7,
                "trigger_mode": "loop_toggle",
                "gain_millidb": -1200,
                "muted": True,
            },
        },
    )
    check_success(updated, 3)
    assert updated["result"] == {
        "committed_revision": 3,
        "runtime_prepare_required": True,
    }
    reset = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "sample.reset_pad",
            "project_path": str(project),
            "command_id": uuid(706),
            "expected_revision": 3,
            "slot": slot(0, 0),
        },
    )
    check_success(reset, 4)

    private_path = temp_root / "private-missing-sample.lmdj"
    missing = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "sample.inspect",
            "project_path": str(private_path),
            "slot": slot(0, 0),
        },
        expected_exit=2,
    )
    check_error(missing, "IO_ERROR")
    assert str(private_path) not in canonical_json(missing)


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
    active_journal = project / "recovery/active/sequence.jsonl"
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


FOUNDRY_SET_ID = "11111111-1111-4111-8111-111111111111"
FOUNDRY_MANIFEST = (
    "33175f66912a9add3e4e551d19d85072adcd1f0331fcc9fed80ab0bc18dd9111"
)
ATTRIBUTION_SET_ID = "22222222-2222-4222-8222-222222222222"
ATTRIBUTION_MANIFEST = (
    "ae578e4f6a383994fb15fd984d7906e346ee7bcb6d7add763c8da9317a313bb4"
)
# S11-D5: Foundry's set-level demo is a blob no slot references, so the Set
# Store holds it as a twelfth object.
FOUNDRY_DEMO_ARTIFACT = (
    "644fe37aef9fcb3d645b87105461b040453523784ce115cf38fd4c539e8813a2"
)
UNSUPPORTED_SET_ID = "33333333-3333-4333-8333-333333333333"
UNSUPPORTED_MANIFEST = (
    "57ab3bf8e01efe6a044639a53ee2e339627e3c3ee5a53b04e387ed640df2e64c"
)
# The Sets the Catalog publishes but the Set Store must refuse, and the token
# each refusal carries. Task 7 asserts the whole partition, not just that the
# happy path is listed: a Set silently promoted from this side of the line
# would be an eligibility regression no positive assertion can see.
#
# Read rather than restated. This used to be a literal here, which meant the
# CLI Host was measured against one copy of the answer, the Native Host
# against nothing, and the browser against a substring check -- so two Hosts
# could disagree and every suite stay green. The file is now the single
# expectation and `host.soundset_catalog_partition` compares the Hosts to each
# other against it.
INELIGIBLE_SETS = {
    set_id: (value["code"], value["reason"])
    for set_id, value in json.loads(
        (REPO_ROOT / "tests/fixtures/soundset/catalog-partition.json").read_text(
            encoding="utf-8"
        )
    )["refused"].items()
}


def project_bundle_module():
    """Load the repository's own Bundle packer, once.

    Export is a tool, not a Facade operation, so the acceptance journey drives
    exactly the packer the product ships rather than reimplementing its
    container format here.
    """
    cached = getattr(project_bundle_module, "module", None)
    if cached is not None:
        return cached
    path = REPO_ROOT / "tools/project-bundle/project_bundle.py"
    spec = importlib.util.spec_from_file_location("project_bundle", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    project_bundle_module.module = module
    return module


def workspace_catalog_root(workspace: Path) -> Path:
    return workspace / ".lmdj-host/soundset-catalog"


def workspace_set_store(workspace: Path) -> Path:
    return workspace / ".lmdj-host/soundsets"


def publish_workspace_catalog(workspace: Path) -> None:
    """Point a Workspace at the offline fixture Catalog, byte for byte.

    Nothing is injected and nothing is rewritten: the Host wires its own
    Workspace-local Catalog, so a Host process here reads exactly the objects
    `tests/fixtures/soundset` publishes.
    """
    catalog = workspace_catalog_root(workspace) / "objects"
    catalog.mkdir(parents=True)
    fixtures = REPO_ROOT / "tests/fixtures/soundset"
    for kind in ("manifest", "blob"):
        for source in sorted((fixtures / kind).iterdir()):
            if source.is_file():
                (catalog / source.name).write_bytes(source.read_bytes())
    (workspace_catalog_root(workspace) / "index.json").write_bytes(
        (fixtures / "catalog/index.json").read_bytes()
    )


def soundset_facade_contract(executable: Path, temp_root: Path) -> None:
    """List, inspect, audition, preview and install a Set across CLI processes.

    Nothing is injected: the Host wires the Workspace-local Catalog, so this
    exercises the same offline path a native Host, the C ABI and the Web Host
    all take, one fresh process per request.
    """
    workspace = temp_root / "soundset-workspace"
    publish_workspace_catalog(workspace)

    listed = run_request(
        executable, workspace, "query", {"operation": "soundset.catalog.list"}
    )
    check_success(listed, None)
    assert listed["result"]["catalog_available"] is True
    published = {entry["set_id"] for entry in listed["result"]["sets"]}
    assert FOUNDRY_SET_ID in published

    inspected = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.inspect",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        },
    )
    check_success(inspected, None)
    assert len(inspected["result"]["slots"]) == 16

    # S11-D5's two audition layers reach the same generic passthrough: no
    # `slot_index` plays the set-level demo, one plays that slot's Artifact.
    demo = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.audition",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        },
    )
    check_success(demo, None)
    assert demo["result"]["slot_index"] is None
    assert demo["result"]["audio"]["prepared_frames"] > 0

    slot_audition = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.audition",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
            "slot_index": 0,
        },
    )
    check_success(slot_audition, None)
    assert slot_audition["result"]["slot_index"] == 0
    assert (
        slot_audition["result"]["artifact"]["sha256"]
        != demo["result"]["artifact"]["sha256"]
    )

    # An empty slot is not a playable source, and the refusal mints no new
    # reason token.
    empty = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.audition",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
            "slot_index": 10,
        },
        expected_exit=2,
    )
    assert empty["ok"] is False
    assert empty["error"]["code"] == "MISSING_ASSET"
    assert empty["error"]["details"] == {}

    # A Project the CLI creates is lmdj.project.v4 from its first persist, so
    # a Sound Set installs into it with no intervening command: this is the
    # path a first-run user takes.
    project = temp_root / "soundset-beat.lmdj"
    run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "project.create",
            "project_path": str(project),
            "project_id": uuid(900),
            "bpm": 120,
            "initial_pattern": {
                "pattern_id": uuid(901),
                "bars": 1,
                "events": [],
            },
        },
    )

    previewed = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.map.preview",
            "project_path": str(project),
            "bank_id": 2,
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        },
    )
    check_success(previewed, 0)
    assert len(previewed["result"]["proposed"]) == 11
    assert previewed["result"]["collisions"] == []
    assert previewed["result"]["kept"] == [10, 11, 13, 14, 15]

    installed = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "soundset.install",
            "project_path": str(project),
            "command_id": uuid(903),
            "expected_revision": 0,
            "bank_id": 2,
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        },
    )
    check_success(installed, 1)
    assert len(installed["result"]["installed"]) == 11

    projected = run_request(
        executable,
        workspace,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )
    check_success(projected, 1)
    pads = projected["result"]["project"]["banks"][2]["pads"]
    assert [pad["pad"] for pad in pads if pad["asset_id"]] == [
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12
    ]
    lineages = [
        projected["result"]["project"]["assets"][pad["asset_id"]]["lineage"]
        for pad in pads
        if pad["asset_id"]
    ]
    assert len(lineages) == 11
    for lineage in lineages:
        assert lineage["source"]["kind"] == "soundset"
        assert lineage["source"]["set_id"] == FOUNDRY_SET_ID
        assert lineage["source"]["manifest_sha256"] == FOUNDRY_MANIFEST
        assert lineage["derivation"]["kind"] == "soundset_install"

    # The install left the Set Store bytes alone: the Set stays inspectable.
    reinspected = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.inspect",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        },
    )
    check_success(reinspected, None)

def project_state(
    executable: Path, workspace: Path, project: Path, bank: int
) -> tuple[int, dict[int, str], dict[str, dict]]:
    """The far side of a leg: revision, this Bank's occupancy, every Asset.

    A Sound Set leg is only proved by what the Project looks like afterwards,
    so every leg below reads this rather than trusting the command's own
    receipt.
    """
    inspected = run_request(
        executable,
        workspace,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )
    assert inspected["ok"] is True
    truth = inspected["result"]["project"]
    occupancy = {
        pad["pad"]: pad["asset_id"]
        for pad in truth["banks"][bank]["pads"]
        if pad["asset_id"]
    }
    return inspected["project_revision"], occupancy, truth["assets"]


def assert_soundset_lineage(
    assets: dict[str, dict],
    asset_id: str,
    set_id: str,
    manifest_sha256: str,
    slot_index: int,
) -> None:
    """S11-D9: one typed `soundset` Lineage, never a second carrier."""
    lineage = assets[asset_id]["lineage"]
    assert lineage["derivation"] == {"kind": "soundset_install"}
    assert lineage["source"]["kind"] == "soundset"
    assert lineage["source"]["set_id"] == set_id
    assert lineage["source"]["manifest_sha256"] == manifest_sha256
    assert lineage["source"]["set_version"] == "1.0.0"
    assert lineage["source"]["slot_index"] == slot_index


def stored_set_objects(workspace: Path, manifest_sha256: str) -> list[str]:
    published = workspace_set_store(workspace) / manifest_sha256
    return sorted(entry.name for entry in published.iterdir())


def soundset_acceptance_journey(executable: Path, temp_root: Path) -> None:
    """Stage 11 acceptance: the Catalog journey a first-run user takes.

    list -> inspect -> map.preview -> install keep -> install replace, one
    fresh CLI process per request, and every leg asserted on its far side --
    the Project revision, the Bank's Pad occupancy, the Asset table and the
    Workspace Set Store -- never on a success code alone. The Project is the
    one `project.create` just made: since #769 that is `lmdj.project.v4` from
    its first persist, so no preparatory command stands between creating a
    Project and installing a Set. A leg that needs one is a regression.
    """
    workspace = temp_root / "acceptance-workspace"
    publish_workspace_catalog(workspace)
    bank = 0

    # Leg 1 -- list. Far side: the Catalog is reachable, exactly the Sets that
    # may be published are published, every other one is refused with its
    # locked token, and the Set Store on disk holds one object per unique
    # Artifact hash (S11-D7). The Attribution Kit's `demo` declares its slot 0
    # hash, so four occupied slots plus a demo are four blobs, not five.
    # Publishable is not installable: S11-D3 keeps the Unsupported Audio Kit
    # on the published side here and refuses it at install, in leg 9.
    listed = run_request(
        executable, workspace, "query", {"operation": "soundset.catalog.list"}
    )
    check_success(listed, None)
    assert listed["result"]["catalog_available"] is True
    published = {entry["set_id"] for entry in listed["result"]["sets"]}
    assert published == {
        FOUNDRY_SET_ID, ATTRIBUTION_SET_ID, UNSUPPORTED_SET_ID
    }
    refused = {
        entry["set_id"]: (entry["code"], entry["reason"])
        for entry in listed["result"]["refused"]
    }
    assert refused == INELIGIBLE_SETS
    attribution = next(
        entry for entry in listed["result"]["sets"]
        if entry["set_id"] == ATTRIBUTION_SET_ID
    )
    assert attribution["license"]["spdx_id"] == "CC-BY-4.0"
    assert attribution["license"]["attribution"] == (
        "Fixture Attribution Kit by Bea Waveform (CC BY 4.0)"
    )
    assert attribution["total_bytes"] == 34788
    assert len(stored_set_objects(workspace, ATTRIBUTION_MANIFEST)) == 5
    # Foundry declares twelve Artifact references -- eleven slots plus a
    # standalone demo -- across eleven unique hashes, because slot 12 reuses
    # slot 0's Artifact.
    assert len(stored_set_objects(workspace, FOUNDRY_MANIFEST)) == 12

    # Leg 2 -- inspect. Far side: the whole 16-slot layout, and a Set Store
    # the query did not touch.
    store_before = stored_set_objects(workspace, FOUNDRY_MANIFEST)
    inspected = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.inspect",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        },
    )
    check_success(inspected, None)
    slots = inspected["result"]["slots"]
    assert len(slots) == 16
    assert [
        slot["slot"] for slot in slots if slot["occupied"]
    ] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12]
    # S11-D12 begins here: an empty slot carries no Artifact at all, so a Host
    # has nothing to render as an action on the target Pad.
    for slot in slots:
        assert ("artifact" in slot) is slot["occupied"]
    assert inspected["result"]["demo"]["sha256"] == FOUNDRY_DEMO_ARTIFACT
    assert stored_set_objects(workspace, FOUNDRY_MANIFEST) == store_before

    project = temp_root / "acceptance-beat.lmdj"
    created = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "project.create",
            "project_path": str(project),
            "project_id": uuid(920),
            "bpm": 120,
            "initial_pattern": {
                "pattern_id": uuid(921), "bars": 1, "events": [],
            },
        },
    )
    check_success(created, 0)
    revision, occupancy, assets = project_state(
        executable, workspace, project, bank
    )
    assert (revision, occupancy, assets) == (0, {}, {})

    # Leg 3 -- install the CC-BY Set into an empty Bank. Nothing collides, so
    # `occupied_pad_policy` is legitimately absent. Far side: revision 0 -> 1,
    # four Pads, four Assets, each carrying typed `soundset` Lineage.
    installed = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "soundset.install",
            "project_path": str(project),
            "command_id": uuid(922),
            "expected_revision": 0,
            "bank_id": bank,
            "set_id": ATTRIBUTION_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": ATTRIBUTION_MANIFEST,
        },
    )
    check_success(installed, 1)
    assert installed["result"]["collisions"] == []
    assert [
        entry["pad"] for entry in installed["result"]["installed"]
    ] == [0, 1, 2, 3]
    revision, attribution_pads, assets = project_state(
        executable, workspace, project, bank
    )
    assert revision == 1
    assert sorted(attribution_pads) == [0, 1, 2, 3]
    assert len(assets) == 4
    for pad, asset_id in attribution_pads.items():
        assert_soundset_lineage(
            assets, asset_id, ATTRIBUTION_SET_ID, ATTRIBUTION_MANIFEST, pad
        )

    # Leg 4 -- map.preview the second Set into the same Bank. Far side: the
    # index-identity mapping with its collisions and its S11-D12 kept list,
    # and a Project the query left exactly where it was.
    previewed = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.map.preview",
            "project_path": str(project),
            "bank_id": bank,
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        },
    )
    check_success(previewed, 1)
    assert [
        entry["pad"] for entry in previewed["result"]["proposed"]
    ] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12]
    for entry in previewed["result"]["proposed"]:
        assert entry["pad"] == entry["slot_index"]
    assert previewed["result"]["collisions"] == [0, 1, 2, 3]
    assert previewed["result"]["kept"] == [10, 11, 13, 14, 15]
    assert project_state(executable, workspace, project, bank) == (
        1, attribution_pads, assets
    )

    # Leg 5 -- install with collisions and no policy. Far side: the locked
    # refusal naming every colliding Pad, and zero Project change: same
    # revision, same Pads, same Assets.
    conflicted = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "soundset.install",
            "project_path": str(project),
            "command_id": uuid(923),
            "expected_revision": 1,
            "bank_id": bank,
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        },
        expected_exit=2,
    )
    check_error(conflicted, "INVALID_ARGUMENT")
    assert conflicted["error"]["details"] == {
        "reason": "soundset_occupied_conflict",
        "collisions": [0, 1, 2, 3],
    }
    assert project_state(executable, workspace, project, bank) == (
        1, attribution_pads, assets
    )

    # Leg 6 -- install keep. Far side: revision 1 -> 2, only the
    # non-colliding proposals written, and the four colliding Pads still
    # holding the exact Asset ids leg 3 gave them.
    kept_install = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "soundset.install",
            "project_path": str(project),
            "command_id": uuid(924),
            "expected_revision": 1,
            "bank_id": bank,
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
            "occupied_pad_policy": "keep",
        },
    )
    check_success(kept_install, 2)
    assert [
        entry["pad"] for entry in kept_install["result"]["installed"]
    ] == [4, 5, 6, 7, 8, 9, 12]
    assert kept_install["result"]["collisions"] == [0, 1, 2, 3]
    assert kept_install["result"]["kept"] == [10, 11, 13, 14, 15]
    revision, keep_pads, keep_assets = project_state(
        executable, workspace, project, bank
    )
    assert revision == 2
    assert sorted(keep_pads) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12]
    for pad, asset_id in attribution_pads.items():
        assert keep_pads[pad] == asset_id
    assert len(keep_assets) == 11
    for pad in (4, 5, 6, 7, 8, 9, 12):
        assert_soundset_lineage(
            keep_assets, keep_pads[pad], FOUNDRY_SET_ID, FOUNDRY_MANIFEST, pad
        )

    # Leg 7 -- install replace. Far side: revision 2 -> 3, every proposal
    # written, and S8-D5: the four Assets the install replaced are still
    # Project Truth, so eleven new Assets bring the table to twenty-two.
    replaced_install = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "soundset.install",
            "project_path": str(project),
            "command_id": uuid(925),
            "expected_revision": 2,
            "bank_id": bank,
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
            "occupied_pad_policy": "replace",
        },
    )
    check_success(replaced_install, 3)
    assert [
        entry["pad"] for entry in replaced_install["result"]["installed"]
    ] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12]
    revision, replace_pads, replace_assets = project_state(
        executable, workspace, project, bank
    )
    assert revision == 3
    assert len(replace_assets) == 22
    for pad, asset_id in attribution_pads.items():
        assert replace_pads[pad] != asset_id
        assert asset_id in replace_assets
    for pad in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12):
        assert_soundset_lineage(
            replace_assets,
            replace_pads[pad],
            FOUNDRY_SET_ID,
            FOUNDRY_MANIFEST,
            pad,
        )
    # Slot 12 reuses slot 0's Artifact. One stored blob, but two Pads and two
    # Assets: S11-D7 deduplicates bytes, never Pad occupancy.
    assert replace_pads[0] != replace_pads[12]
    assert (
        replace_assets[replace_pads[0]]["lineage"]["source"]["artifact_sha256"]
        == replace_assets[
            replace_pads[12]
        ]["lineage"]["source"]["artifact_sha256"]
    )

    # Leg 8 -- S11-D12. Reinstalling the four-slot Set over the same Bank with
    # the most destructive policy there is must still leave every Pad under an
    # empty Set slot exactly as it was: an empty slot is not a wipe.
    d12_install = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "soundset.install",
            "project_path": str(project),
            "command_id": uuid(926),
            "expected_revision": 3,
            "bank_id": bank,
            "set_id": ATTRIBUTION_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": ATTRIBUTION_MANIFEST,
            "occupied_pad_policy": "replace",
        },
    )
    check_success(d12_install, 4)
    assert [
        entry["pad"] for entry in d12_install["result"]["installed"]
    ] == [0, 1, 2, 3]
    assert d12_install["result"]["kept"] == [
        4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15
    ]
    revision, d12_pads, d12_assets = project_state(
        executable, workspace, project, bank
    )
    assert revision == 4
    assert sorted(d12_pads) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12]
    # The four Pads the Set does occupy really moved -- otherwise every
    # assertion below would also hold for an install that wrote nothing.
    for pad in (0, 1, 2, 3):
        assert d12_pads[pad] != replace_pads[pad]
        assert_soundset_lineage(
            d12_assets,
            d12_pads[pad],
            ATTRIBUTION_SET_ID,
            ATTRIBUTION_MANIFEST,
            pad,
        )
    # ...and the Pads under the Set's twelve empty slots did not.
    for pad in (4, 5, 6, 7, 8, 9, 12):
        assert d12_pads[pad] == replace_pads[pad]
    assert len(d12_assets) == 26

    # Leg 9 -- S11-D3. A Set the Catalog publishes can still carry audio that
    # is not S8-D6, and the Facade decides that at install, not at download.
    # Far side: the locked refusal, and a Project that did not move.
    unsupported = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "soundset.install",
            "project_path": str(project),
            "command_id": uuid(928),
            "expected_revision": 4,
            "bank_id": 2,
            "set_id": UNSUPPORTED_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": UNSUPPORTED_MANIFEST,
        },
        expected_exit=2,
    )
    check_error(unsupported, "UNSUPPORTED_AUDIO")
    # Slot 0 of that Set is 22.05 kHz, and the refusal names it.
    assert unsupported["error"]["details"] == {
        "reason": "soundset_audio_unsupported",
        "slot_index": 0,
    }
    assert project_state(executable, workspace, project, bank) == (
        4, d12_pads, d12_assets
    )
    assert project_state(executable, workspace, project, 2)[1] == {}

    # Leg 10 -- S11-D5 audition. #799 made a Set audible before install, and
    # the invariant that makes that safe is that auditioning is a query with
    # respect to Project Truth: no Asset, no Pad, no revision. Asserted after
    # the transition rather than before it, because "nothing changed" is only
    # a claim about a thing that has already happened.
    #
    # Four auditions, chosen so a Project change could come from any of the
    # shapes the operation has: a set-level demo, an occupied slot, a slot the
    # Set leaves empty, and a Set whose audio the Facade refuses.
    demo = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.audition",
            "set_id": ATTRIBUTION_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": ATTRIBUTION_MANIFEST,
        },
    )
    check_success(demo, None)
    # Addressed without a slot, so the set-level demo answered. `sample_rate`
    # is the Artifact's own rate, not the engine's -- this demo is authored at
    # 48 kHz, so its source and prepared frame counts agree and it cannot show
    # a resample. The slot below is the case that can.
    assert demo["result"]["slot_index"] is None
    assert demo["result"]["audio"]["sample_rate"] == 48_000
    assert (demo["result"]["audio"]["prepared_frames"]
            == demo["result"]["audio"]["source_frames"] == 2_880)

    slot = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.audition",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
            "slot_index": 0,
        },
    )
    check_success(slot, None)
    assert slot["result"]["slot_index"] == 0
    assert slot["result"]["artifact"]["sha256"]
    # The load-bearing one. Foundry slot 0 is authored at 44.1 kHz and the
    # engine runs at 48, so `prepared_frames` is the resampled count and
    # `source_frames` is what the Artifact holds: 2646 * 48000 / 44100 = 2880.
    # Handing a Host the source frames would publish 44.1 kHz audio into a
    # 48 kHz engine and play every preview sharp -- a defect that ships and
    # comes back months later as "previews sound wrong". The two fields
    # differing is the only place that is visible.
    foundry_audio = slot["result"]["audio"]
    assert foundry_audio["sample_rate"] == 44_100, foundry_audio
    assert foundry_audio["source_frames"] == 2_646, foundry_audio
    assert foundry_audio["prepared_frames"] == 2_880, foundry_audio

    # An empty Set slot is not a playable thing, and S11-D12 keeps emptiness a
    # property of the absent Artifact rather than a flag. The existing
    # `MISSING_ASSET` carries it, so the locked vocabulary does not grow.
    empty = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.audition",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
            "slot_index": 11,
        },
        expected_exit=2,
    )
    check_error(empty, "MISSING_ASSET")

    # S11-D3 is a whole-Set decision, so it refuses an audition for the same
    # reason it refused the install in leg 9 -- the same code and the same
    # token, decided in the same place.
    unsupported_audition = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.audition",
            "set_id": UNSUPPORTED_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": UNSUPPORTED_MANIFEST,
        },
        expected_exit=2,
    )
    check_error(unsupported_audition, "UNSUPPORTED_AUDIO")
    assert unsupported_audition["error"]["details"]["reason"] == (
        "soundset_audio_unsupported"
    )

    # The far side of all four: the Project is exactly where leg 9 left it.
    # Revision, this Bank's occupancy and the whole Asset table -- an audition
    # that created an Asset would show here even if no Pad moved.
    assert project_state(executable, workspace, project, bank) == (
        4, d12_pads, d12_assets
    )

    soundset_offline_and_export_journey(
        executable, workspace, temp_root, project
    )


def soundset_offline_and_export_journey(
    executable: Path, workspace: Path, temp_root: Path, project: Path
) -> None:
    """An unreachable Catalog hides nothing, and the result is exportable.

    The Catalog directory is removed outright, which is the strongest form of
    unreachable a Workspace-local Host can suffer: no index, no objects. What
    is already in the Set Store must survive it all the way through install.
    """
    shutil.rmtree(workspace_catalog_root(workspace))

    offline = run_request(
        executable, workspace, "query", {"operation": "soundset.catalog.list"}
    )
    check_success(offline, None)
    assert offline["result"]["catalog_available"] is False
    assert offline["result"]["refused"] == []
    assert {entry["set_id"] for entry in offline["result"]["sets"]} == {
        FOUNDRY_SET_ID, ATTRIBUTION_SET_ID, UNSUPPORTED_SET_ID
    }

    inspected = run_request(
        executable,
        workspace,
        "query",
        {
            "operation": "soundset.inspect",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        },
    )
    check_success(inspected, None)
    assert len(inspected["result"]["slots"]) == 16

    # A cached Set installs with the Catalog gone: the Set Store is the source
    # of the bytes, and Bank 1 is empty, so nothing collides.
    offline_install = run_request(
        executable,
        workspace,
        "command",
        {
            "operation": "soundset.install",
            "project_path": str(project),
            "command_id": uuid(927),
            "expected_revision": 4,
            "bank_id": 1,
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        },
    )
    check_success(offline_install, 5)
    revision, offline_pads, offline_assets = project_state(
        executable, workspace, project, 1
    )
    assert revision == 5
    assert sorted(offline_pads) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12]
    for pad, asset_id in offline_pads.items():
        assert_soundset_lineage(
            offline_assets, asset_id, FOUNDRY_SET_ID, FOUNDRY_MANIFEST, pad
        )

    # Export. Until #784 widened `lmdj.project-bundle.v1`, no Project this
    # Build creates could be packed at all, so this is the first journey that
    # can carry an installed Sound Set out of the product.
    bundle = temp_root / "acceptance-beat-bundle.lmdj"
    packed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/project-bundle/project_bundle.py"),
            "pack",
            "--source",
            str(project),
            "--output",
            str(bundle),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert packed.returncode == 0, packed.stderr
    verified = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/project-bundle/project_bundle.py"),
            "verify",
            str(bundle),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert verified.returncode == 0, verified.stderr
    assert verified.stdout.strip() == packed.stdout.strip()

    index, _ = project_bundle_module().read_bundle(bundle)
    assert index["project_contract"] == "lmdj.project.v5"
    payloads = sorted(
        entry["path"] for entry in index["entries"]
        if entry["path"].endswith(".wav")
    )
    # Every Asset in the Project came from a Sound Set slot, and the Bundle is
    # content-addressed: the two Sets contribute fourteen unique Artifact
    # hashes and the export carries exactly fourteen WAV payloads for the
    # thirty-seven Assets that reference them.
    assert len(offline_assets) == 37
    assert payloads == sorted({
        f"assets/{asset['lineage']['source']['artifact_sha256']}.wav"
        for asset in offline_assets.values()
    })
    assert len(payloads) == 14


def host_boundary_and_identity(executable: Path) -> None:
    version = json.loads(
        (REPO_ROOT / "products/lmdj/version.json").read_text(
            encoding="utf-8"
        )
    )
    # Assert the shape and the cross-references, not a second copy of the
    # values: a duplicated literal costs a CI cycle on every identity bump and
    # never catches a real defect, while a stale dependency pin does.
    assert set(version) == {
        "contract", "product", "milestone", "minor", "build", "patch",
    }
    assert version["contract"] == "lmdj.product-version.v1"
    assert version["product"] == "lmdj"
    assert all(
        isinstance(version[part], int) and version[part] >= 0
        for part in ("milestone", "minor", "build", "patch")
    )
    manifest = json.loads(
        (REPO_ROOT / "apps/core-cli/module.json").read_text(
            encoding="utf-8"
        )
    )
    facade = json.loads(
        (REPO_ROOT / "packages/application-facade/module.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(manifest) == {
        "contract", "module", "version", "api_version", "dependencies",
    }
    assert manifest["contract"] == "lmdj.module.v1"
    assert manifest["module"] == "core-cli"
    assert manifest["api_version"] == 2
    assert manifest["dependencies"] == {
        "application-facade": facade["version"]
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
        "lmdj/facade/performance_runtime.hpp",
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
        sample_facade_contract(executable, workspace, temp_root)
        passed += 1
        fresh_process_replay(
            executable, workspace, project, commit_request
        )
        passed += 1
        fresh_process_snapshot_render_golden(
            executable, workspace, temp_root, project
        )
        passed += 1
        soundset_facade_contract(executable, temp_root)
        passed += 1
        soundset_acceptance_journey(executable, temp_root)
        passed += 1
        host_boundary_and_identity(executable)
        passed += 1
        timeout_policy_contract()
        passed += 1

    assert passed == 14
    print("cli behavior fixtures: 14 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
