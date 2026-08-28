import json
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
# Derived, not pinned: the Host reports the live Product Build, so a
# literal here turns every allocation into an unrelated Host test failure.
_VERSION = json.loads(
    (REPO_ROOT / "products/lmdj/version.json").read_text(encoding="utf-8"))
PRODUCT_BUILD = ".".join(
    str(_VERSION[key]) for key in ("milestone", "minor", "build", "patch"))
USAGE = (
    "usage: lmdj-native-host --workspace ABSOLUTE_PATH "
    "--assembly ABSOLUTE_ASSEMBLY_JSON "
    "--project ABSOLUTE_PROJECT_BUNDLE --pattern UUID [--no-device]\n"
)
COMMAND_LIMIT = 64 * 1024
PROJECT_ID = "00000000-0000-4000-8000-000000000001"
STARTUP_PATTERN_ID = "00000000-0000-4000-8000-000000000010"
KICK_ASSET_ID = "00000000-0000-4000-8000-000000000101"
SNARE_ASSET_ID = "00000000-0000-4000-8000-000000000102"
RECORDED_SESSION_ID = "00000000-0000-4000-8000-000000000202"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def uuid(suffix: int) -> str:
    return f"00000000-0000-4000-8000-{suffix:012d}"


def slot(bank: int, pad: int) -> dict:
    return {"bank": bank, "pad": pad}


def check_error(response: dict, code: str | None = None) -> None:
    assert set(response) == {"ok", "error"}, response
    assert response["ok"] is False
    assert set(response["error"]) == {"code", "message", "details"}
    if code is not None:
        assert response["error"]["code"] == code, response


def cli_request(
    cli: Path,
    workspace: Path,
    assembly: Path,
    mode: str,
    request: dict,
    expected_exit: int = 0,
) -> dict:
    completed = subprocess.run(
        [
            str(cli),
            "--workspace",
            str(workspace),
            "--assembly",
            str(assembly),
            mode,
            "--request",
            canonical_json(request),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == expected_exit, (
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )
    assert completed.stderr == b""
    response = json.loads(completed.stdout.decode("utf-8"))
    assert completed.stdout.decode("utf-8") == canonical_json(response) + "\n"
    return response


def cli_success(
    cli: Path,
    workspace: Path,
    assembly: Path,
    mode: str,
    request: dict,
    revision: int | None,
) -> dict:
    response = cli_request(cli, workspace, assembly, mode, request)
    assert response["ok"] is True, response
    assert response["project_revision"] == revision
    return response["result"]


def startup_pattern() -> dict:
    return {
        "pattern_id": STARTUP_PATTERN_ID,
        "bars": 1,
        "events": [
            {"slot": slot(0, 0), "onset_tick": 0,
             "duration_tick": 240, "velocity": 127},
            {"slot": slot(0, 1), "onset_tick": 960,
             "duration_tick": 240, "velocity": 127},
        ],
    }


def author_project(
    cli: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
) -> None:
    cli_success(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "project.create",
            "project_path": str(project),
            "project_id": PROJECT_ID,
            "bpm": 120,
            "initial_pattern": startup_pattern(),
        },
        0,
    )
    for revision, asset_id, source_name in (
        (0, KICK_ASSET_ID, "kick.wav"),
        (1, SNARE_ASSET_ID, "snare.wav"),
    ):
        cli_success(
            cli,
            workspace,
            assembly,
            "command",
            {
                "operation": "asset.import",
                "project_path": str(project),
                "command_id": uuid(revision + 1),
                "expected_revision": revision,
                "asset_id": asset_id,
                "source_path": str(
                    REPO_ROOT / "tests" / "fixtures" / "audio" / source_name
                ),
                "media_type": "audio/wav",
            },
            revision + 1,
        )
    for revision, pad, asset_id in (
        (2, 0, KICK_ASSET_ID),
        (3, 1, SNARE_ASSET_ID),
    ):
        cli_success(
            cli,
            workspace,
            assembly,
            "command",
            {
                "operation": "pad.assign",
                "project_path": str(project),
                "command_id": uuid(revision + 1),
                "expected_revision": revision,
                "slot": slot(0, pad),
                "asset_id": asset_id,
            },
            revision + 1,
        )
    cli_success(
        cli,
        workspace,
        assembly,
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
    )


class HostProcess:
    def __init__(
        self,
        host: Path,
        workspace: Path,
        assembly: Path,
        project: Path,
        no_device: bool = True,
    ) -> None:
        arguments = [
            str(host),
            "--workspace",
            str(workspace),
            "--assembly",
            str(assembly),
            "--project",
            str(project),
            "--pattern",
            STARTUP_PATTERN_ID,
        ]
        if no_device:
            arguments.append("--no-device")
        self.process = subprocess.Popen(
            arguments,
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def read(self, timeout: float = 10.0) -> dict:
        assert self.process.stdout is not None
        readable, _, _ = select.select([self.process.stdout], [], [], timeout)
        assert readable, "timed out waiting for Native Host response"
        line = self.process.stdout.readline()
        assert line, (self.process.poll(), self.stderr_so_far())
        decoded = line.decode("utf-8", errors="strict")
        response = json.loads(decoded)
        assert decoded == canonical_json(response) + "\n"
        return response

    def send_raw(self, line: bytes) -> dict:
        assert self.process.stdin is not None
        self.process.stdin.write(line + b"\n")
        self.process.stdin.flush()
        return self.read()

    def request(self, request: dict) -> dict:
        return self.send_raw(canonical_json(request).encode("utf-8"))

    def stderr_so_far(self) -> bytes:
        if self.process.poll() is None or self.process.stderr is None:
            return b""
        return self.process.stderr.read()

    def quit(self) -> dict:
        response = self.request({"operation": "quit"})
        assert response["ok"] is True, response
        assert self.process.stdin is not None
        self.process.stdin.close()
        return_code = self.process.wait(timeout=10)
        assert return_code == 0
        assert self.process.stderr is not None
        assert self.process.stderr.read() == b""
        return response


def invocation_contract(host: Path, temp_root: Path, assembly: Path) -> None:
    completed = subprocess.run([str(host)], check=False, capture_output=True)
    assert completed.returncode == 64
    assert completed.stdout == b""
    assert completed.stderr.decode("ascii") == USAGE

    structural_errors = [
        ["--unknown"],
        [
            "--workspace",
            str(temp_root),
            "--workspace",
            str(temp_root),
            "--assembly",
            str(assembly),
            "--project",
            str(temp_root / "missing.lmdj"),
            "--pattern",
            STARTUP_PATTERN_ID,
        ],
    ]
    for arguments in structural_errors:
        rejected = subprocess.run(
            [str(host), *arguments], check=False, capture_output=True
        )
        assert rejected.returncode == 64
        assert rejected.stdout == b""
        assert rejected.stderr.decode("ascii") == USAGE

    invalid_path = subprocess.run(
        [
            str(host),
            "--workspace",
            "relative",
            "--assembly",
            str(assembly),
            "--project",
            str(temp_root / "missing.lmdj"),
            "--pattern",
            STARTUP_PATTERN_ID,
            "--no-device",
        ],
        check=False,
        capture_output=True,
    )
    assert invalid_path.returncode == 2
    assert invalid_path.stderr == b""
    check_error(json.loads(invalid_path.stdout), "INVALID_ARGUMENT")


def command_validation(process: HostProcess) -> None:
    check_error(process.send_raw(b"{"), "INVALID_ARGUMENT")
    check_error(
        process.request({"operation": "status", "extra": True}),
        "INVALID_ARGUMENT",
    )
    check_error(
        process.send_raw(
            b'{"operation":"status","nested":' + b"[" * 33 + b"0" + b"]" * 33 + b"}"
        ),
        "INVALID_ARGUMENT",
    )

    prefix = b'{"operation":"status","padding":"'
    suffix = b'"}'
    boundary = prefix + b"x" * (COMMAND_LIMIT - len(prefix) - len(suffix)) + suffix
    assert len(boundary) == COMMAND_LIMIT
    boundary_response = process.send_raw(boundary)
    check_error(boundary_response, "INVALID_ARGUMENT")
    assert boundary_response["error"]["message"] == "status request shape is invalid"

    oversized = prefix + b"x" * (COMMAND_LIMIT + 1 - len(prefix) - len(suffix)) + suffix
    assert len(oversized) == COMMAND_LIMIT + 1
    oversized_response = process.send_raw(oversized)
    check_error(oversized_response, "INVALID_ARGUMENT")
    assert "65536" in oversized_response["error"]["message"]
    assert process.request({"operation": "status"})["ok"] is True


def happy_path(
    host: Path,
    cli: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
) -> None:
    process = HostProcess(host, workspace, assembly, project)
    ready = process.read()
    assert ready["ok"] is True
    assert ready["operation"] == "ready"
    assert set(ready["result"]) == {
        "backend",
        "host_version",
        "product_build",
        "project_id",
        "project_revision",
        "resolved_pad_count",
    }
    assert ready["result"]["resolved_pad_count"] == 2
    assert ready["result"]["project_revision"] == 5
    assert ready["result"]["host_version"] == "2.0.0"
    assert ready["result"]["product_build"] == PRODUCT_BUILD, (
        "Product Build mismatch: expected "
        f"{PRODUCT_BUILD} from products/lmdj/version.json, found "
        f"{ready['result']['product_build']} in native Host ready response"
    )

    for pad in (0, 1):
        triggered = process.request(
            {"operation": "trigger", "slot": slot(0, pad), "velocity": 100}
        )
        assert triggered["ok"] is True, triggered
        assert triggered["result"] == {
            "sequence": pad + 1,
            "status": "accepted",
        }
    status = process.request({"operation": "status"})
    assert status["ok"] is True, status
    assert set(status["result"]["engine"]) == {
        "active_voices",
        "callback_count",
        "cancelled_events",
        "cancelled_voices",
        "completed_voices",
        "dequeued_events",
        "enqueued_events",
        "queue_drops",
        "queued_events",
        "rendered_frames",
        "started_voices",
        "voice_drops",
    }
    assert status["result"]["engine"]["enqueued_events"] == 2
    assert status["result"]["engine"]["completed_voices"] == 2
    assert status["result"]["capture"]["captured_events"] == 0
    assert status["result"]["engine"]["queue_drops"] == 0
    assert status["result"]["engine"]["voice_drops"] == 0

    command_validation(process)
    failed_reload = process.request(
        {"operation": "snapshot.reload", "pattern_id": uuid(999)}
    )
    assert failed_reload["ok"] is False
    assert process.request(
        {"operation": "trigger", "slot": slot(0, 0), "velocity": 100}
    )["ok"] is True

    begun = process.request(
        {
            "operation": "record.begin",
            "session_id": RECORDED_SESSION_ID,
            "expected_revision": 5,
        }
    )
    assert begun["ok"] is True, begun
    for index in range(21):
        triggered = process.request(
            {
                "operation": "trigger",
                "slot": slot(0, index % 2),
                "velocity": 80 + index,
            }
        )
        assert triggered["ok"] is True, (index, triggered)
    stopped_recording = process.request(
        {"operation": "record.stop", "command_id": uuid(6)})
    assert stopped_recording["ok"] is True, stopped_recording
    assert stopped_recording["result"]["clean"] is True
    assert stopped_recording["result"]["captured_events"] == 21
    assert stopped_recording["result"]["persisted_events"] == 21
    assert stopped_recording["result"]["writer_failures"] == 0

    reloaded = process.request(
        {"operation": "snapshot.reload", "pattern_id": STARTUP_PATTERN_ID}
    )
    assert reloaded["ok"] is True, reloaded
    assert reloaded["result"]["project_revision"] == 6
    assert reloaded["result"]["resolved_pad_count"] == 2

    assert process.request({"operation": "stop"})["ok"] is True
    check_error(
        process.request(
            {"operation": "trigger", "slot": slot(0, 0), "velocity": 100}
        ),
        "INVALID_ARGUMENT",
    )
    assert process.request({"operation": "start"})["ok"] is True
    assert process.request(
        {"operation": "trigger", "slot": slot(0, 0), "velocity": 100}
    )["ok"] is True
    process.quit()

    inspected = cli_success(
        cli,
        workspace,
        assembly,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
        6,
    )["project"]
    assert len(inspected["patterns"][STARTUP_PATTERN_ID]["events"]) >= 2


def sample_facade_snapshot_path(
    host: Path,
    cli: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
) -> None:
    updated = cli_success(
        cli,
        workspace,
        assembly,
        "command",
        {
            "operation": "sample.update_pad",
            "project_path": str(project),
            "command_id": uuid(801),
            "expected_revision": 5,
            "slot": slot(0, 0),
            "playback": {
                "trim_start_frame": 1,
                "trim_end_frame": 100,
                "trigger_mode": "one_shot",
                "gain_millidb": -600,
                "muted": False,
            },
        },
        6,
    )
    assert updated == {
        "committed_revision": 6,
        "runtime_prepare_required": True,
    }
    inspected = cli_success(
        cli,
        workspace,
        assembly,
        "query",
        {
            "operation": "sample.inspect",
            "project_path": str(project),
            "slot": slot(0, 0),
        },
        6,
    )
    assert inspected["playback"]["trim_end_frame"] == 100

    quota_request = {
        "operation": "sample.quota",
        "project_path": str(project),
        "slot": slot(0, 0),
    }
    cli_quota = cli_success(
        cli,
        workspace,
        assembly,
        "query",
        quota_request,
        6,
    )

    process = HostProcess(host, workspace, assembly, project)
    ready = process.read()
    assert ready["ok"] is True, ready
    assert ready["result"]["project_revision"] == 6
    assert ready["result"]["resolved_pad_count"] == 2
    native_quota = process.request(quota_request)
    assert native_quota["ok"] is True, native_quota
    assert native_quota["project_revision"] == 6
    assert native_quota["result"] == cli_quota
    triggered = process.request(
        {"operation": "trigger", "slot": slot(0, 0), "velocity": 100}
    )
    assert triggered["ok"] is True, triggered
    process.quit()


def non_apple_real_device_contract(
    host: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
) -> None:
    if sys.platform == "darwin":
        return
    process = HostProcess(
        host, workspace, assembly, project, no_device=False
    ).process
    assert process.stdout is not None
    line = process.stdout.readline()
    response = json.loads(line.decode("utf-8"))
    check_error(response, "UNSUPPORTED_AUDIO")
    assert process.wait(timeout=10) == 2
    assert process.stderr is not None
    assert process.stderr.read() == b""


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: native_host_test.py HOST CLI ASSEMBLY")
    host = Path(sys.argv[1]).resolve(strict=True)
    cli = Path(sys.argv[2]).resolve(strict=True)
    assembly = Path(sys.argv[3]).resolve(strict=True)

    with tempfile.TemporaryDirectory(prefix="lmdj-native-host-") as root:
        temp_root = Path(root).resolve()
        workspace = temp_root / "workspace"
        workspace.mkdir()
        invocation_contract(host, temp_root, assembly)

        base_project = temp_root / "base.lmdj"
        author_project(cli, workspace, assembly, base_project)
        happy_project = temp_root / "happy.lmdj"
        sample_project = temp_root / "sample.lmdj"
        shutil.copytree(base_project, happy_project)
        shutil.copytree(base_project, sample_project)
        happy_path(host, cli, workspace, assembly, happy_project)
        sample_facade_snapshot_path(
            host, cli, workspace, assembly, sample_project
        )
        non_apple_real_device_contract(
            host, workspace, assembly, base_project
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
