"""Capture allocation refusal must not create a session or stop playback.

Uses the real Host source with a test-only allocator interposer. The no-device
backend proves rendered-frame/Voice progress, not physical audio or hearing.
"""
import hashlib
from pathlib import Path
import sys
import tempfile

from native_host_test import (
    HostProcess, RECORDED_SESSION_ID, STARTUP_PATTERN_ID, author_project,
    check_error, cli_success, slot, uuid,
)


def bundle_identity(project: Path) -> dict:
    return {
        str(path.relative_to(project)): (
            path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()
        )
        for path in project.rglob("*") if path.is_file()
    }


def main() -> None:
    host, cli, assembly = (Path(arg).resolve(strict=True) for arg in sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix="lmdj-capture-allocation-") as root:
        workspace = Path(root) / "workspace"
        workspace.mkdir()
        project = Path(root) / "capture.lmdj"
        author_project(cli, workspace, assembly, project)
        process = HostProcess(host, workspace, assembly, project)
        try:
            ready = process.read()
            assert ready["ok"], ready
            before_files = bundle_identity(project)
            before = process.request({"operation": "status"})["result"]
            request = {
                "operation": "record.begin", "session_id": RECORDED_SESSION_ID,
                "expected_revision": 5,
            }
            failed = process.request(request)
            check_error(failed, "INTERNAL_ERROR")
            assert failed["error"]["message"] == (
                "Insufficient memory for Capture recording buffer"
            ), failed
            assert failed["error"]["details"] == {}, failed
            after = process.request({"operation": "status"})["result"]
            assert after["active_session_id"] is None, after
            assert after["capture"]["state"] == "idle", after
            assert bundle_identity(project) == before_files, "failed begin wrote a session"
            triggered = process.request({
                "operation": "trigger", "slot": slot(0, 0), "velocity": 100,
            })
            assert triggered["ok"], triggered
            after_play = process.request({"operation": "status"})["result"]
            assert after_play["engine"]["rendered_frames"] > before["engine"]["rendered_frames"]
            assert after_play["engine"]["started_voices"] > before["engine"]["started_voices"]
            retried = process.request(request)
            assert retried["ok"], retried  # Same session id/revision, not a fresh identity.
            active = process.request({"operation": "status"})["result"]
            assert active["active_session_id"] == RECORDED_SESSION_ID, active
            assert active["capture"]["state"] == "active", active
            assert process.request({
                "operation": "trigger", "slot": slot(0, 1), "velocity": 101,
            })["ok"]
            stopped = process.request({"operation": "record.stop", "command_id": uuid(6)})
            assert stopped["ok"], stopped
            assert stopped["result"]["clean"] is True, stopped
            assert stopped["result"]["captured_events"] == 1, stopped
            assert stopped["result"]["persisted_events"] == 1, stopped
            assert stopped["result"]["writer_failures"] == 0, stopped
            reloaded = process.request({
                "operation": "snapshot.reload", "pattern_id": STARTUP_PATTERN_ID,
            })
            assert reloaded["ok"], reloaded
            assert reloaded["result"]["project_revision"] == 6, reloaded
            process.quit()
            reopened = cli_success(cli, workspace, assembly, "query", {
                "operation": "project.inspect", "project_path": str(project),
            }, 6)["project"]
            events = reopened["patterns"][STARTUP_PATTERN_ID]["events"]
            assert any(event["velocity"] == 101 and event["slot"] == slot(0, 1)
                       for event in events), events
        finally:
            if process.process.poll() is None:
                process.process.terminate()
                process.process.wait(timeout=10)


if __name__ == "__main__":
    main()
