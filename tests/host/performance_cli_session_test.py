from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUEST_LIMIT = 16 * 1024 * 1024
BASE_TIMEOUT_SECONDS = 15.0


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def configured_timeout(executable: Path) -> float:
    cache = (executable.parent.parent / "CMakeCache.txt").read_text(
        encoding="utf-8"
    )
    sanitizer = next(
        (
            line.removeprefix("LMDJ_SANITIZER:STRING=")
            for line in cache.splitlines()
            if line.startswith("LMDJ_SANITIZER:STRING=")
        ),
        "none",
    )
    return BASE_TIMEOUT_SECONDS * {
        "address": 3.0,
        "thread": 4.0,
    }.get(sanitizer, 1.0)


def uuid(suffix: int) -> str:
    return f"82000000-0000-4000-8000-{suffix:012d}"


def check_success(response: dict, revision: int | None = None) -> dict:
    assert response["ok"] is True, response
    assert response["project_revision"] == revision, response
    assert isinstance(response["result"], dict), response
    return response["result"]


def check_invalid(response: dict) -> None:
    assert response["ok"] is False, response
    assert response["error"]["code"] == "INVALID_ARGUMENT", response


def one_shot(
    executable: Path,
    workspace: Path,
    surface: str,
    request: dict,
    expected_exit: int = 0,
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
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        timeout=configured_timeout(executable),
    )
    assert completed.returncode == expected_exit, (
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )
    assert completed.stderr == b""
    decoded = completed.stdout.decode("utf-8", errors="strict")
    response = json.loads(decoded)
    assert decoded == canonical_json(response) + "\n"
    return response


class Session:
    def __init__(
        self, executable: Path, workspace: Path, assembly: Path | None = None
    ) -> None:
        arguments = [
            str(executable),
            "--workspace",
            str(workspace),
        ]
        if assembly is not None:
            arguments.extend(["--assembly", str(assembly)])
        arguments.append("session")
        self.process = subprocess.Popen(
            arguments,
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self.process.stdin is not None
        assert self.process.stdout is not None

    def raw(self, line: bytes) -> dict:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(line + b"\n")
        self.process.stdin.flush()
        encoded = self.process.stdout.readline()
        assert encoded.endswith(b"\n"), encoded
        response = json.loads(encoded.decode("utf-8", errors="strict"))
        assert encoded == (canonical_json(response) + "\n").encode("utf-8")
        return response

    def request(self, surface: str, request: dict) -> dict:
        return self.raw(
            canonical_json({"surface": surface, "request": request}).encode(
                "utf-8"
            )
        )

    def close(self, expected_exit: int = 0) -> None:
        assert self.process.stdin is not None
        self.process.stdin.close()
        self.process.wait(timeout=configured_timeout(Path(self.process.args[0])))
        assert self.process.returncode == expected_exit, self.process.returncode
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        assert self.process.stdout.read() == b""
        assert self.process.stderr.read() == b""

    def kill(self) -> None:
        self.process.send_signal(signal.SIGKILL)
        self.process.wait(timeout=configured_timeout(Path(self.process.args[0])))
        assert self.process.returncode == -signal.SIGKILL


def framing_and_ordering(executable: Path, root: Path) -> None:
    workspace = root / "framing-workspace"
    workspace.mkdir()
    session = Session(executable, workspace)
    malformed = [
        b"",
        b"{",
        b"[]",
        b'{"surface":"query"}',
        b'{"request":{"operation":"provider.list"}}',
        b'{"request":{},"surface":"query","extra":0}',
        b'{"request":{"operation":"provider.list"},"surface":"other"}',
        b'{"request":{"operation":"provider.list"},"surface":"query","bad":"\xff"}',
        b" " * (REQUEST_LIMIT + 1),
    ]
    for line in malformed:
        check_invalid(session.raw(line))

    first = session.request("query", {"operation": "provider.list"})
    second = session.request("query", {"operation": "provider.list"})
    check_success(first)
    check_success(second)
    assert first == second
    session.close()

    assembled = Session(
        executable,
        workspace,
        assembly=(REPO_ROOT / "products/lmdj/assembly.json").resolve(),
    )
    providers = check_success(
        assembled.request("query", {"operation": "provider.list"})
    )["providers"]
    assert [provider["id"] for provider in providers] == [
        "local.proof.failure",
        "local.proof.success",
    ]
    assembled.close()


def stdout_failure_exits_two(executable: Path, root: Path) -> None:
    if os.name != "posix":
        return
    workspace = root / "stdout-failure-workspace"
    workspace.mkdir()
    read_descriptor, write_descriptor = os.pipe()
    os.close(read_descriptor)
    try:
        process = subprocess.Popen(
            [
                str(executable),
                "--workspace",
                str(workspace),
                "session",
            ],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=write_descriptor,
            stderr=subprocess.PIPE,
        )
    finally:
        os.close(write_descriptor)
    assert process.stdin is not None
    process.stdin.write(
        (
            canonical_json(
                {
                    "surface": "query",
                    "request": {"operation": "provider.list"},
                }
            )
            + "\n"
        ).encode("utf-8")
    )
    process.stdin.flush()
    process.stdin.close()
    process.wait(timeout=configured_timeout(executable))
    assert process.returncode == 2, process.returncode
    assert process.returncode != -signal.SIGPIPE
    assert process.stderr is not None
    assert process.stderr.read() == b""


def create_project(
    requester,
    project: Path,
    project_id: str,
    bpm: int = 240,
) -> None:
    check_success(
        requester(
            "command",
            {
                "operation": "project.create",
                "project_path": str(project),
                "project_id": project_id,
                "bpm": bpm,
            },
        ),
        0,
    )


def complete_headless_journey(executable: Path, root: Path) -> None:
    workspace = root / "journey-workspace"
    workspace.mkdir()
    project = root / "journey.lmdj"
    session = Session(executable, workspace)
    request = session.request
    create_project(request, project, uuid(1))

    imported = check_success(
        request(
            "command",
            {
                "operation": "asset.import",
                "project_path": str(project),
                "command_id": uuid(2),
                "expected_revision": 0,
                "asset_id": uuid(3),
                "source_path": str(REPO_ROOT / "tests/fixtures/audio/stereo.wav"),
                "media_type": "audio/wav",
            },
        ),
        1,
    )
    check_success(
        request(
            "command",
            {
                "operation": "pad.assign",
                "project_path": str(project),
                "command_id": uuid(4),
                "expected_revision": 1,
                "slot": {"bank": 0, "pad": 0},
                "asset_id": uuid(3),
            },
        ),
        2,
    )
    session_id = uuid(5)
    performance_id = uuid(6)
    responses = [
        request(
            "command",
            {
                "operation": "performance.record.begin",
                "project_path": str(project),
                "command_id": uuid(7),
                "expected_revision": 2,
                "session_id": session_id,
                "performance_id": performance_id,
            },
        )
    ]
    events = [
        {"kind": "pad_press", "gesture_id": uuid(9), "slot": 0, "velocity": 100},
        {"kind": "pad_release", "gesture_id": uuid(9), "slot": 0},
        {"kind": "fx_engage", "gesture_id": uuid(11), "fx": "filter", "value": 500},
        {"kind": "fx_move", "gesture_id": uuid(11), "fx": "filter", "value": 600},
        {"kind": "fx_release", "gesture_id": uuid(11), "fx": "filter"},
        {"kind": "hold_on"},
        {"kind": "hold_off"},
    ]
    for index, event in enumerate(events, start=20):
        responses.append(
            request(
                "command",
                {
                    "operation": "performance.record.event",
                    "project_path": str(project),
                    "session_id": session_id,
                    "event_id": uuid(index),
                    "event": event,
                },
            )
        )
    launch = request(
        "command",
        {
            "operation": "performance.record.launch-request",
            "project_path": str(project),
            "session_id": session_id,
            "request_id": uuid(30),
            "pattern_slot": 3,
        },
    )
    responses.append(launch)
    target_tick = check_success(launch)["target_tick"]
    pending = request(
        "query",
        {"operation": "performance.record.status", "project_path": str(project)},
    )
    responses.append(pending)
    assert check_success(pending)["pending_launch"]["target_tick"] == target_tick
    time.sleep(1.05)
    journal_path = project / "recovery/active/performance.jsonl"
    before_status = journal_path.read_bytes()
    acknowledged = request(
        "query",
        {"operation": "performance.record.status", "project_path": str(project)},
    )
    responses.append(acknowledged)
    status = check_success(acknowledged)
    assert status["pending_launch"]["target_tick"] == target_tick
    assert status["last_launch_ack"] is None
    assert journal_path.read_bytes() == before_status

    flushed = request(
        "command",
        {
            "operation": "performance.record.flush",
            "project_path": str(project),
            "session_id": session_id,
            "command_id": uuid(31),
        },
    )
    responses.append(flushed)
    assert check_success(flushed, 4)["committed_revision"] == 4
    serviced = request(
        "query",
        {"operation": "performance.record.status", "project_path": str(project)},
    )
    responses.append(serviced)
    serviced_status = check_success(serviced)
    assert serviced_status["pending_launch"] is None
    assert serviced_status["last_launch_ack"]["effective_tick"] == target_tick
    responses.append(
        request(
            "command",
            {
                "operation": "performance.record.stop",
                "project_path": str(project),
                "session_id": session_id,
                "request_id": uuid(32),
            },
        )
    )
    saved = request(
        "command",
        {
            "operation": "performance.save",
            "project_path": str(project),
            "command_id": uuid(33),
            "expected_revision": 4,
            "performance_id": performance_id,
            "name": "CLI Session Take",
            "recording_artifact": imported["artifact"],
        },
    )
    responses.append(saved)
    assert check_success(saved, 5)["committed_revision"] == 5
    replay_id = uuid(34)
    responses.append(
        request(
            "command",
            {
                "operation": "performance.replay.begin",
                "project_path": str(project),
                "replay_id": replay_id,
                "performance_id": performance_id,
            },
        )
    )
    responses.append(
        request(
            "query",
            {
                "operation": "performance.replay.status",
                "project_path": str(project),
                "replay_id": replay_id,
            },
        )
    )
    responses.append(
        request(
            "command",
            {
                "operation": "performance.replay.stop",
                "project_path": str(project),
                "replay_id": replay_id,
                "request_id": uuid(35),
            },
        )
    )
    resampled = request(
        "command",
        {
            "operation": "performance.resample.commit",
            "project_path": str(project),
            "command_id": uuid(36),
            "expected_revision": 5,
            "performance_id": performance_id,
            "source_start_frame": 1,
            "source_end_frame": 3,
            "target_slot": {"bank": 1, "pad": 2},
        },
    )
    responses.append(resampled)
    assert check_success(resampled, 6)["committed_revision"] == 6
    assert all(response["ok"] is True for response in responses), responses
    encoded = canonical_json(responses)
    for unavailable in (
        "performance_clock_unavailable",
        "performance_input_sequencer_unavailable",
        "performance_launch_acknowledger_unavailable",
        "performance_replay_unavailable",
    ):
        assert unavailable not in encoded
    session.close()


def clean_eof_seals_owner(executable: Path, root: Path) -> None:
    workspace = root / "eof-workspace"
    workspace.mkdir()
    project = root / "eof.lmdj"
    session = Session(executable, workspace)
    create_project(session.request, project, uuid(101), bpm=120)
    check_success(
        session.request(
            "command",
            {
                "operation": "performance.record.begin",
                "project_path": str(project),
                "command_id": uuid(102),
                "expected_revision": 0,
                "session_id": uuid(103),
                "performance_id": uuid(104),
            },
        ),
        1,
    )
    session.close()
    assert not (project / "recovery/active/performance.jsonl").exists()
    sealed = list(
        (project / "recovery/sealed").glob("*-performance-owner_lost.json")
    )
    assert len(sealed) == 1, sealed


def flush_replay_cross_process(executable: Path, root: Path) -> None:
    workspace = root / "flush-workspace"
    workspace.mkdir()
    project = root / "flush.lmdj"
    session = Session(executable, workspace)
    create_project(session.request, project, uuid(201), bpm=120)
    session_id = uuid(202)
    performance_id = uuid(203)
    check_success(
        session.request(
            "command",
            {
                "operation": "performance.record.begin",
                "project_path": str(project),
                "command_id": uuid(204),
                "expected_revision": 0,
                "session_id": session_id,
                "performance_id": performance_id,
            },
        ),
        1,
    )
    check_success(
        session.request(
            "command",
            {
                "operation": "performance.record.event",
                "project_path": str(project),
                "session_id": session_id,
                "event_id": uuid(205),
                "event": {"kind": "hold_on"},
            },
        )
    )
    flush_id = uuid(206)
    flushed = session.request(
        "command",
        {
            "operation": "performance.record.flush",
            "project_path": str(project),
            "session_id": session_id,
            "command_id": flush_id,
        },
    )
    assert check_success(flushed, 2)["committed_revision"] == 2
    check_success(
        session.request(
            "command",
            {
                "operation": "performance.record.stop",
                "project_path": str(project),
                "session_id": session_id,
                "request_id": uuid(207),
            },
        )
    )
    check_success(
        session.request(
            "command",
            {
                "operation": "performance.save",
                "project_path": str(project),
                "command_id": uuid(208),
                "expected_revision": 2,
                "performance_id": performance_id,
                "name": "Flush Replay",
                "recording_artifact": None,
            },
        ),
        3,
    )
    session.close()
    inspect_request = {"operation": "project.inspect", "project_path": str(project)}
    before = one_shot(executable, workspace, "query", inspect_request)
    replayed = one_shot(
        executable,
        workspace,
        "command",
        {
            "operation": "performance.record.flush",
            "project_path": str(project),
            "session_id": session_id,
            "command_id": flush_id,
        },
    )
    result = check_success(replayed, 2)
    assert result["replayed"] is True
    assert result["committed_revision"] == 2
    after = one_shot(executable, workspace, "query", inspect_request)
    assert after == before


def project_snapshot(executable: Path, workspace: Path, project: Path) -> dict:
    return one_shot(
        executable,
        workspace,
        "query",
        {"operation": "project.inspect", "project_path": str(project)},
    )


def start_orphan(
    executable: Path,
    workspace: Path,
    project: Path,
    offset: int,
) -> tuple[Session, str, str]:
    session = Session(executable, workspace)
    create_project(session.request, project, uuid(offset), bpm=120)
    session_id = uuid(offset + 1)
    performance_id = uuid(offset + 2)
    check_success(
        session.request(
            "command",
            {
                "operation": "performance.record.begin",
                "project_path": str(project),
                "command_id": uuid(offset + 3),
                "expected_revision": 0,
                "session_id": session_id,
                "performance_id": performance_id,
            },
        ),
        1,
    )
    event = check_success(
        session.request(
            "command",
            {
                "operation": "performance.record.event",
                "project_path": str(project),
                "session_id": session_id,
                "event_id": uuid(offset + 4),
                "event": {"kind": "hold_on"},
            },
        )
    )
    assert event["input_sequence"] == 1
    return session, session_id, performance_id


def owner_loss_apply_and_discard(executable: Path, root: Path) -> None:
    workspace = root / "owner-workspace"
    workspace.mkdir()
    apply_project = root / "owner-apply.lmdj"
    owner, session_id, performance_id = start_orphan(
        executable, workspace, apply_project, 301
    )
    active_bytes = (apply_project / "recovery/active/performance.jsonl").read_bytes()
    refused = one_shot(
        executable,
        workspace,
        "command",
        {
            "operation": "performance.recovery.apply",
            "project_path": str(apply_project),
            "command_id": uuid(306),
            "expected_revision": 1,
            "session_id": session_id,
        },
        expected_exit=2,
    )
    check_invalid(refused)
    assert refused["error"]["details"]["reason"] == "recording_session_active"
    assert (
        apply_project / "recovery/active/performance.jsonl"
    ).read_bytes() == active_bytes
    assert list((apply_project / "recovery/sealed").iterdir()) == []
    owner.kill()

    observed = one_shot(
        executable,
        workspace,
        "query",
        {"operation": "performance.record.status", "project_path": str(apply_project)},
    )
    assert check_success(observed)["state"] == "active"
    applied = one_shot(
        executable,
        workspace,
        "command",
        {
            "operation": "performance.recovery.apply",
            "project_path": str(apply_project),
            "command_id": uuid(307),
            "expected_revision": 1,
            "session_id": session_id,
        },
    )
    assert check_success(applied, 2)["committed_revision"] == 2
    performance = one_shot(
        executable,
        workspace,
        "query",
        {
            "operation": "performance.inspect",
            "project_path": str(apply_project),
            "performance_id": performance_id,
        },
    )
    events = check_success(performance, 2)["performance"]["events"]
    assert [event["kind"] for event in events] == ["hold_on", "hold_off"], events
    assert isinstance(events[0]["tick"], int)
    assert events[1]["tick"] == events[0]["tick"] + 1

    discard_project = root / "owner-discard.lmdj"
    discard_owner, discard_session, _ = start_orphan(
        executable, workspace, discard_project, 401
    )
    before = project_snapshot(executable, workspace, discard_project)
    discard_owner.kill()
    discarded = one_shot(
        executable,
        workspace,
        "command",
        {
            "operation": "performance.recovery.discard",
            "project_path": str(discard_project),
            "session_id": discard_session,
            "request_id": uuid(406),
        },
    )
    discarded_result = check_success(discarded)
    assert discarded_result["state"] == "stopped", discarded_result
    after = project_snapshot(executable, workspace, discard_project)
    assert after == before


def exact_reattach_has_one_cross_process_winner(
    executable: Path, root: Path
) -> None:
    workspace = root / "reattach-workspace"
    workspace.mkdir()
    project = root / "reattach-contention.lmdj"
    owner, session_id, performance_id = start_orphan(
        executable, workspace, project, 501
    )
    owner.kill()

    request = {
        "operation": "performance.record.begin",
        "project_path": str(project),
        "command_id": uuid(504),
        "expected_revision": 0,
        "session_id": session_id,
        "performance_id": performance_id,
    }
    contenders = [Session(executable, workspace), Session(executable, workspace)]
    barrier = threading.Barrier(len(contenders))

    def reattach(candidate: Session) -> dict:
        barrier.wait(timeout=configured_timeout(executable))
        return candidate.request("command", request)

    with ThreadPoolExecutor(max_workers=len(contenders)) as pool:
        responses = list(pool.map(reattach, contenders))

    winners = [index for index, response in enumerate(responses) if response["ok"]]
    assert len(winners) == 1, responses
    winner_index = winners[0]
    loser_index = 1 - winner_index
    check_success(responses[winner_index], 1)
    check_invalid(responses[loser_index])
    assert (
        responses[loser_index]["error"]["details"]["reason"]
        == "recording_session_active"
    )

    status = one_shot(
        executable,
        workspace,
        "query",
        {"operation": "performance.record.status", "project_path": str(project)},
    )
    projected = check_success(status)
    assert projected["state"] == "active", projected
    assert projected["pending_event_count"] == 2, projected
    assert projected["open_pad_gestures"] == 0, projected
    assert projected["open_fx_gestures"] == 0, projected
    assert projected["hold"] is False, projected

    contenders[loser_index].close()
    contenders[winner_index].close()


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: performance_cli_session_test.py /absolute/path/to/lmdj-core"
        )
    executable = Path(sys.argv[1]).expanduser().resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="lmdj-performance-cli-session-") as temp:
        root = Path(temp).resolve()
        framing_and_ordering(executable, root)
        stdout_failure_exits_two(executable, root)
        complete_headless_journey(executable, root)
        clean_eof_seals_owner(executable, root)
        flush_replay_cross_process(executable, root)
        owner_loss_apply_and_discard(executable, root)
        exact_reattach_has_one_cross_process_winner(executable, root)
    print("performance CLI session journeys: 7 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
