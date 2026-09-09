import json
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time


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
# The Sound Set fixture corpus, addressed exactly as `tests/host/cli_test.py`
# addresses it. `tests/fixtures/soundset/README.md` is the authority for which
# Set exercises which case.
FOUNDRY_SET_ID = "11111111-1111-4111-8111-111111111111"
FOUNDRY_MANIFEST = (
    "33175f66912a9add3e4e551d19d85072adcd1f0331fcc9fed80ab0bc18dd9111"
)
DEFAULT_RESPONSE_TIMEOUT_SECONDS = 10.0
DURABLE_RECORD_STOP_TIMEOUT_SECONDS = 30.0


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


def response_timeout_seconds(request: dict) -> float:
    # record.stop drains the realtime Capture ring, joins the durable writer,
    # and commits Project Truth before responding. Keep that durability
    # boundary distinct from ordinary protocol responsiveness.
    if request.get("operation") == "record.stop":
        return DURABLE_RECORD_STOP_TIMEOUT_SECONDS
    return DEFAULT_RESPONSE_TIMEOUT_SECONDS


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

    def read(
        self,
        timeout: float = DEFAULT_RESPONSE_TIMEOUT_SECONDS,
        operation: str = "unsolicited response",
    ) -> dict:
        assert self.process.stdout is not None
        readable, _, _ = select.select([self.process.stdout], [], [], timeout)
        assert readable, (
            f"timed out after {timeout:.0f}s waiting for Native Host response "
            f"to {operation}; process_returncode={self.process.poll()}; "
            f"stderr={self.stderr_so_far()!r}"
        )
        line = self.process.stdout.readline()
        assert line, (self.process.poll(), self.stderr_so_far())
        decoded = line.decode("utf-8", errors="strict")
        response = json.loads(decoded)
        assert decoded == canonical_json(response) + "\n"
        return response

    def send_raw(
        self,
        line: bytes,
        timeout: float = DEFAULT_RESPONSE_TIMEOUT_SECONDS,
        operation: str = "raw request",
    ) -> dict:
        assert self.process.stdin is not None
        self.process.stdin.write(line + b"\n")
        self.process.stdin.flush()
        return self.read(timeout, operation)

    def request(self, request: dict) -> dict:
        operation = request.get("operation")
        operation_name = operation if isinstance(operation, str) else "invalid request"
        return self.send_raw(
            canonical_json(request).encode("utf-8"),
            response_timeout_seconds(request),
            operation_name,
        )

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


def native_performance_adapter_wiring_contract() -> None:
    source = (
        REPO_ROOT / "apps" / "native-host" / "src" / "main.cpp"
    ).read_text(encoding="utf-8")
    assert "make_engine_pattern_publication_gateway" in source
    assert "make_engine_performance_adapter" in source
    assert "performance_adapter_.service()" in source
    assert "application_.service_performance()" in source
    assert "performance_service_error_" in source
    assert "service_command_boundary" in source
    assert "service_periodic_control_tick" in source
    runtime_service = source[
        source.index("void service_runtime_locked()") : source.index(
            "Result<void> service_application_locked()"
        )
    ]
    assert "performance_adapter_.service()" in runtime_service
    application_service = source[
        source.index("Result<void> service_application_locked()") : source.index(
            "Result<void> service_command_boundary()"
        )
    ]
    assert "application_.service_performance()" in application_service
    handle = source[source.index("Json handle(") : source.index("bool quitting()")]
    assert "const bool query_operation" in handle
    assert "if (!has_operation || query_operation)" in handle
    assert "service_command_boundary()" in handle
    assert "bridge.performance_clock" not in source
    assert source.index("RealtimeEngine engine_;") < source.index(
        "EnginePerformanceAdapter performance_adapter_;"
    )
    assert source.index("EnginePerformanceAdapter performance_adapter_;") < source.index(
        "Application application_;"
    )
    destructor = source[source.index("~NativeHost()") : source.index("Result<void> startup()")]
    assert "stop_backend()" in destructor


def buffered_input_services_control_tick(
    host: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
) -> None:
    input_path = project.parent / "buffered-native-host-input"
    status = canonical_json({"operation": "status"}).encode("utf-8")
    quit_request = canonical_json({"operation": "quit"}).encode("utf-8")
    input_path.write_bytes(
        status
        + b"\n"
        + b"x" * (COMMAND_LIMIT * 4)
        + b"\n"
        + status
        + b"\n"
        + quit_request
        + b"\n"
    )
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
        "--no-device",
    ]
    with input_path.open("rb") as buffered_input:
        completed = subprocess.run(
            arguments,
            cwd=REPO_ROOT,
            stdin=buffered_input,
            capture_output=True,
            timeout=15,
            check=False,
        )
    assert completed.returncode == 0, (completed.returncode, completed.stderr)
    assert completed.stderr == b""
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(responses) == 5, responses
    assert responses[0]["operation"] == "ready"
    assert responses[1]["operation"] == "status"
    check_error(responses[2], "INVALID_ARGUMENT")
    assert "65536" in responses[2]["error"]["message"]
    assert responses[3]["operation"] == "status"
    assert (
        responses[3]["result"]["engine"]["rendered_frames"]
        > responses[1]["result"]["engine"]["rendered_frames"]
    )
    assert responses[4]["operation"] == "quit"


def short_buffered_lines_service_control_tick(
    host: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
) -> None:
    input_path = project.parent / "short-buffered-native-host-input"
    status = canonical_json({"operation": "status"}).encode("utf-8")
    quit_request = canonical_json({"operation": "quit"}).encode("utf-8")
    input_path.write_bytes(
        status
        + b"\n"
        + b"\n" * 5_000
        + status
        + b"\n"
        + quit_request
        + b"\n"
    )
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
        "--no-device",
    ]
    with input_path.open("rb") as buffered_input:
        completed = subprocess.run(
            arguments,
            cwd=REPO_ROOT,
            stdin=buffered_input,
            capture_output=True,
            timeout=15,
            check=False,
        )
    assert completed.returncode == 0, (completed.returncode, completed.stderr)
    assert completed.stderr == b""
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(responses) == 5_004, len(responses)
    assert responses[0]["operation"] == "ready"
    assert responses[1]["operation"] == "status"
    check_error(responses[2], "INVALID_ARGUMENT")
    check_error(responses[-3], "INVALID_ARGUMENT")
    assert responses[-2]["operation"] == "status"
    assert (
        responses[-2]["result"]["engine"]["rendered_frames"]
        > responses[1]["result"]["engine"]["rendered_frames"]
    )
    assert responses[-1]["operation"] == "quit"


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

    observed = cli_request(
        cli,
        workspace,
        assembly,
        "query",
        {
            "operation": "performance.record.status",
            "project_path": str(project),
        },
    )
    assert observed["ok"] is True, observed
    assert observed["result"]["state"] == "idle", observed
    assert "performance_authority_unavailable" not in canonical_json(observed)
    assert "performance_launch_authority_unavailable" not in canonical_json(observed)
    assert "performance_input_authority_unavailable" not in canonical_json(observed)
    assert "performance_replay_runtime_unavailable" not in canonical_json(observed)

    # The deterministic audio Runtime must keep crossing boundaries while the
    # Host is idle, so the periodic control tick can progress replay and launch
    # acknowledgements without a request acting as an accidental clock.
    time.sleep(0.05)
    idle_status = process.request({"operation": "status"})
    assert idle_status["ok"] is True, idle_status
    assert idle_status["result"]["engine"]["rendered_frames"] > 0

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


def publish_workspace_catalog(workspace: Path) -> None:
    """Point this Workspace at the offline Sound Set fixture Catalog.

    Byte for byte, and nothing injected: the Native Host wires its own
    Workspace-local Catalog (`main.cpp`'s `make_workspace_soundset_catalog`),
    so the Host process reads exactly the objects `tests/fixtures/soundset`
    publishes. Same shape as `tests/host/cli_test.py`'s helper of this name.
    """
    fixtures = REPO_ROOT / "tests/fixtures/soundset"
    catalog = workspace / ".lmdj-host/soundset-catalog"
    (catalog / "objects").mkdir(parents=True)
    for kind in ("manifest", "blob"):
        for source in sorted((fixtures / kind).iterdir()):
            if source.is_file():
                (catalog / "objects" / source.name).write_bytes(
                    source.read_bytes()
                )
    (catalog / "index.json").write_bytes(
        (fixtures / "catalog/index.json").read_bytes()
    )


def soundset_audition_reaches_a_voice(
    host: Path,
    cli: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
) -> None:
    """A Native Host audition reaches a voice, not only a metadata answer.

    #799's plan promises the byte path in "the two Hosts that own an engine".
    Only the Web Host was wired: `soundset.audition` here forwarded to the
    Facade and returned geometry, so the Set was inaudible on this Host. The
    far-side observable is the engine's own telemetry, because a voice can only
    start on the reserved audition Bank after the Facade decoded the Set's
    bytes, this Host published them, and the audio thread applied that
    publication inside `render`.

    Each audition below asserts after the transition, and the refusals assert
    the negative at the same place: the Facade decides, and a refused audition
    must start nothing. `played` (#1059) is asserted on the Host's own reply
    beside the engine telemetry, so a silent audition can no longer read
    exactly like a sounding one -- true for the two accepted legs, false for
    the stopped-backend leg.

    WHAT THIS CANNOT EXPRESS -- audibility. It proves a voice started from the
    audition Bank and ran to completion over the Set's decoded frame count; it
    does not prove the samples leaving a device are the Set's, at the right
    gain, or in the right order. That class needs a captured output buffer,
    which this Host does not expose: `record.begin`/`record.stop` capture
    Pattern events, not audio. It also cannot see a wrong-Set mix-up, because
    every accepted audition looks the same from telemetry.
    """
    process = HostProcess(host, workspace, assembly, project)
    ready = process.read()
    assert ready["ok"] is True, ready

    def engine_state() -> tuple[dict, dict, int]:
        status = process.request({"operation": "status"})
        assert status["ok"] is True, status
        return (
            status["result"]["engine"],
            status["result"]["bank"],
            status["result"]["snapshot"]["project_revision"],
        )

    engine, bank_before, revision_before = engine_state()
    assert engine["started_voices"] == 0, engine
    assert engine["completed_voices"] == 0, engine

    # Leg 0 -- inspect materialises the Set into the Workspace Set Store,
    # which is what audition reads. The Catalog is only the transport.
    listed = process.request({"operation": "soundset.catalog.list"})
    assert listed["ok"] is True, listed
    assert listed["result"]["catalog_available"] is True, listed
    assert FOUNDRY_SET_ID in {
        entry["set_id"] for entry in listed["result"]["sets"]
    }, listed
    inspected = process.request(
        {
            "operation": "soundset.inspect",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        }
    )
    assert inspected["ok"] is True, inspected
    assert len(inspected["result"]["slots"]) == 16, inspected
    # `played` belongs to the one operation that plays. A Set-reading operation
    # that grew it would be claiming an outcome it never produced.
    assert "played" not in inspected["result"], inspected
    engine, bank, revision = engine_state()
    assert engine["started_voices"] == 0, engine
    assert bank == bank_before, (bank_before, bank)

    # Leg 1 -- the set-level demo. No `slot_index`, no Project, no
    # `project_path`: S11-D5's audition is Workspace-scoped.
    demo = process.request(
        {
            "operation": "soundset.audition",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        }
    )
    assert demo["ok"] is True, demo
    assert demo["result"]["slot_index"] is None, demo
    assert demo["result"]["audio"]["prepared_frames"] > 0, demo
    assert demo["result"]["played"] is True, demo
    engine, bank, revision = engine_state()
    assert engine["started_voices"] == 1, (demo, engine)
    assert engine["completed_voices"] == 1, (demo, engine)
    assert engine["voice_drops"] == 0, engine
    # The audition Bank lives outside the Project pool, so no Project
    # publication happened, no Project slot was consumed, and the Pad
    # availability a Project voice reads did not move. `bank` is the whole
    # Project-pool observation this Host reports, so comparing it entire is
    # stricter than naming one counter and cannot miss a new one.
    assert bank == bank_before, (bank_before, bank)
    assert revision == revision_before, (revision_before, revision)

    # Leg 2 -- a slot Artifact rather than the demo, through the same path.
    slot_audition = process.request(
        {
            "operation": "soundset.audition",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
            "slot_index": 0,
        }
    )
    assert slot_audition["ok"] is True, slot_audition
    assert slot_audition["result"]["slot_index"] == 0, slot_audition
    assert slot_audition["result"]["played"] is True, slot_audition
    assert (
        slot_audition["result"]["artifact"]["sha256"]
        != demo["result"]["artifact"]["sha256"]
    ), (demo, slot_audition)
    engine, bank, revision = engine_state()
    assert engine["started_voices"] == 2, (slot_audition, engine)
    assert engine["completed_voices"] == 2, (slot_audition, engine)
    assert bank == bank_before, (bank_before, bank)

    # Leg 3 -- an empty slot. The Facade refuses with the existing
    # `MISSING_ASSET`, and this Host must start nothing.
    empty = process.request(
        {
            "operation": "soundset.audition",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
            "slot_index": 10,
        }
    )
    check_error(empty, "MISSING_ASSET")
    engine, bank, revision = engine_state()
    assert engine["started_voices"] == 2, (empty, engine)
    assert bank == bank_before, (bank_before, bank)

    # Leg 4 -- the Project's own Pads still play after two auditions, which
    # is the far side of "an audition never consumes a Project bank slot".
    triggered = process.request(
        {"operation": "trigger", "slot": slot(0, 0), "velocity": 100}
    )
    assert triggered["ok"] is True, triggered
    engine, bank, revision = engine_state()
    assert engine["started_voices"] == 3, (triggered, engine)
    assert engine["completed_voices"] == 3, (triggered, engine)
    assert engine["voice_drops"] == 0, engine
    assert bank == bank_before, (bank_before, bank)
    assert revision == revision_before, (revision_before, revision)

    # Leg 5 -- a stopped Host answers the query and plays nothing. Playback is
    # gated on the backend, never the answer. Last, because `start` resets the
    # engine's counters and every count above would restart from zero.
    stopped = process.request({"operation": "stop"})
    assert stopped["ok"] is True, stopped
    stopped_audition = process.request(
        {
            "operation": "soundset.audition",
            "set_id": FOUNDRY_SET_ID,
            "version": "1.0.0",
            "manifest_sha256": FOUNDRY_MANIFEST,
        }
    )
    assert stopped_audition["ok"] is True, stopped_audition
    assert stopped_audition["result"]["audio"]["prepared_frames"] > 0, (
        stopped_audition
    )
    # The #1059 branch a caller actually meets: the geometry is right and no
    # sound came out, and the reply says so instead of reading like the two
    # accepted auditions above.
    assert stopped_audition["result"]["played"] is False, stopped_audition
    engine, bank, revision = engine_state()
    assert engine["started_voices"] == 3, (stopped_audition, engine)
    assert bank == bank_before, (bank_before, bank)

    process.quit()

    # Far side in Project Truth, read by a separate process: an audition is a
    # query, so the Project it never named is byte-identical in revision and
    # Asset table.
    truth = cli_request(
        cli,
        workspace,
        assembly,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )
    assert truth["ok"] is True, truth
    assert truth["project_revision"] == revision_before, (
        revision_before,
        truth["project_revision"],
    )
    assert sorted(truth["result"]["project"]["assets"]) == sorted(
        [KICK_ASSET_ID, SNARE_ASSET_ID]
    ), truth["result"]["project"]["assets"]


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
        native_performance_adapter_wiring_contract()
        invocation_contract(host, temp_root, assembly)

        base_project = temp_root / "base.lmdj"
        author_project(cli, workspace, assembly, base_project)
        buffered_project = temp_root / "buffered.lmdj"
        short_buffered_project = temp_root / "short-buffered.lmdj"
        happy_project = temp_root / "happy.lmdj"
        sample_project = temp_root / "sample.lmdj"
        shutil.copytree(base_project, buffered_project)
        shutil.copytree(base_project, short_buffered_project)
        shutil.copytree(base_project, happy_project)
        shutil.copytree(base_project, sample_project)
        buffered_input_services_control_tick(
            host, workspace, assembly, buffered_project
        )
        short_buffered_lines_service_control_tick(
            host, workspace, assembly, short_buffered_project
        )
        happy_path(host, cli, workspace, assembly, happy_project)
        sample_facade_snapshot_path(
            host, cli, workspace, assembly, sample_project
        )
        audition_workspace = temp_root / "audition-workspace"
        audition_workspace.mkdir()
        publish_workspace_catalog(audition_workspace)
        audition_project = temp_root / "audition.lmdj"
        author_project(cli, audition_workspace, assembly, audition_project)
        soundset_audition_reaches_a_voice(
            host, cli, audition_workspace, assembly, audition_project
        )
        non_apple_real_device_contract(
            host, workspace, assembly, base_project
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
