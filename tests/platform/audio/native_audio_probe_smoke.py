#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import sys


TIMEOUT_SECONDS = 10


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def status_result(state: str, stopped_rejections: int = 0) -> dict:
    return {
        "active_voices": 0,
        "callback_count": 10,
        "callback_failures": 0,
        "cancelled_events": 0,
        "cancelled_voices": 0,
        "channels": 2,
        "completed_voices": 1,
        "deadline_overruns": 0,
        "dequeued_events": 1,
        "device_overloads": 0,
        "enqueued_events": 1,
        "invalid_events": 0,
        "max_callback_frames": 128,
        "queue_capacity": 1024,
        "queue_drops": 0,
        "queued_events": 0,
        "rendered_frames": 1280,
        "sample_rate": 48000,
        "started_voices": 1,
        "state": state,
        "stopped_rejections": stopped_rejections,
        "voice_capacity": 128,
        "voice_drops": 0,
    }


def response(command: str, result: dict) -> dict:
    return {"command": command, "ok": True, "result": result}


def run_probe(executable: Path, stdin: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), *arguments],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )


def assert_canonical_lines(completed: subprocess.CompletedProcess[str]) -> list[dict]:
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == "", completed.stderr
    lines = completed.stdout.splitlines()
    parsed = [json.loads(line) for line in lines]
    assert lines == [canonical_json(value) for value in parsed]
    return parsed


def test_protocol(executable: Path) -> None:
    completed = run_probe(
        executable,
        "trigger\nstatus\nstop\ntrigger\nstatus\nstart\ntrigger\nstatus\nquit\n",
        "--no-device",
    )
    expected = [
        response("startup", {"state": "running"}),
        response("trigger", {"sequence": 1, "status": "accepted"}),
        response("status", status_result("running")),
        response("stop", {"state": "stopped"}),
        {
            "command": "trigger",
            "error": {"code": "not_running"},
            "ok": False,
        },
        response("status", status_result("stopped", stopped_rejections=1)),
        response("start", {"state": "running"}),
        response("trigger", {"sequence": 2, "status": "accepted"}),
        response("status", status_result("running")),
        response("quit", {"state": "stopped"}),
    ]
    lines = assert_canonical_lines(completed)
    assert lines == expected


def test_eof_is_clean_quit(executable: Path) -> None:
    lines = assert_canonical_lines(run_probe(executable, "", "--no-device"))
    assert lines == [
        response("startup", {"state": "running"}),
        response("quit", {"state": "stopped"}),
    ]


def test_unknown_command_continues(executable: Path) -> None:
    lines = assert_canonical_lines(
        run_probe(executable, "unexpected\nstatus\nquit\n", "--no-device")
    )
    assert lines[0] == response("startup", {"state": "running"})
    assert lines[1] == {
        "command": "unexpected",
        "error": {"code": "unknown_command"},
        "ok": False,
    }
    assert lines[2] == response(
        "status",
        {
            **status_result("running"),
            "callback_count": 0,
            "completed_voices": 0,
            "dequeued_events": 0,
            "enqueued_events": 0,
            "max_callback_frames": 0,
            "rendered_frames": 0,
            "started_voices": 0,
        },
    )
    assert lines[3] == response("quit", {"state": "stopped"})


def test_invalid_arguments(executable: Path) -> None:
    for arguments in (("--unsupported",), ("--no-device", "extra")):
        completed = run_probe(executable, "", *arguments)
        assert completed.returncode == 64
        assert completed.stdout == ""


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} PROBE", file=sys.stderr)
        return 64
    executable = Path(sys.argv[1]).resolve()
    assert executable.is_file(), executable
    test_protocol(executable)
    test_eof_is_clean_quit(executable)
    test_unknown_command_continues(executable)
    test_invalid_arguments(executable)
    print("native audio probe smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
