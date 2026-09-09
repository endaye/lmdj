"""Owner execution through CLI sessions, MCP/C ABI, and Native stdio.

Each case checks the far side of import, execution/refusal, terminal inspection,
Host close, and a new Host's inspection. No Provider byte API is bypassed.
"""
import copy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import tempfile
import wave

from mcp_facade_parity_test import MCP, canonical_json
from native_host_test import HostProcess

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "00000000-0000-4000-8000-000000000001"
ASSET = "00000000-0000-4000-8000-000000000002"
PATTERN = "00000000-0000-4000-8000-000000000010"
OTHER = "00000000-0000-4000-8000-000000000099"
QUERIES = {"project.inspect", "provider.list", "attempt.inspect"}


def success(response):
    assert response["ok"] is True, response
    return response["result"]


def failure(response, code):
    assert response["ok"] is False, response
    assert response["error"]["code"] == code, response


class CliSession:
    def __init__(self, cli, workspace, assembly):
        self.process = subprocess.Popen(
            [str(cli), "--workspace", str(workspace), "--assembly", str(assembly), "session"],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def request(self, request):
        self.process.stdin.write((canonical_json({
            "surface": "query" if request["operation"] in QUERIES else "command",
            "request": request}) + "\n").encode())
        self.process.stdin.flush()
        ready, _, _ = select.select([self.process.stdout], [], [], 20)
        assert ready, ("CLI session timeout", request["operation"])
        line = self.process.stdout.readline()
        assert line, (self.process.poll(), self.process.stderr.read())
        response = json.loads(line)
        assert line == (canonical_json(response) + "\n").encode()
        return response

    def close(self):
        self.process.stdin.close()
        self.process.stdin = None
        out, err = self.process.communicate(timeout=20)
        assert self.process.returncode == 0 and out == b"" and err == b"", (out, err)


class McpSession:
    def __init__(self, library, workspace, assembly):
        self.host = MCP(library, workspace, assembly)

    def request(self, request):
        args = dict(request)
        operation = args.pop("operation")
        return self.host.tool("lmdj." + operation, args)

    def close(self):
        self.host.close()


class NativeSession:
    def __init__(self, native, workspace, assembly, project):
        self.host = HostProcess(native, workspace, assembly, project)
        ready = self.host.read()
        assert ready["operation"] == "ready" and ready["ok"], ready

    def request(self, request):
        return self.host.request(request)

    def close(self):
        success(self.host.request({"operation": "stop"}))
        self.host.quit()


class Fixture:
    def __init__(self, kind, root, cli, native, library):
        self.kind, self.root, self.cli, self.native, self.library = kind, root, cli, native, library
        self.assembly = ROOT / "products/lmdj/assembly.json"
        self.project = root / "source.lmdj"
        self.source_file = root / "input.wav"
        stream = io.BytesIO()
        with wave.open(stream, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000)
            wav.writeframes(struct.pack("<5h", 0, 5000, 0, 8000, 0))
        self.original = stream.getvalue()
        self.source_file.write_bytes(self.original)
        # Native starts from a Facade-authored Project, as its existing Host
        # contract requires. CLI/MCP import through their own real transports.
        author = CliSession(cli, root, self.assembly) if kind == "native" else self.open()
        success(author.request({"operation": "project.create", "project_path": str(self.project),
            "project_id": PROJECT, "bpm": 120,
            "initial_pattern": {"pattern_id": PATTERN, "bars": 1, "events": []}}))
        success(author.request({"operation": "asset.import", "project_path": str(self.project),
            "command_id": "00000000-0000-4000-8000-000000000003", "expected_revision": 0,
            "asset_id": ASSET, "source_path": str(self.source_file), "media_type": "audio/wav"}))
        inspected = success(author.request({"operation": "project.inspect", "project_path": str(self.project)}))["project"]
        self.source = inspected["assets"][ASSET]["artifact"]
        assert self.source == {"sha256": hashlib.sha256(self.original).hexdigest(),
                               "byte_length": len(self.original), "media_type": "audio/wav"}
        assert inspected["revision"] == 1
        if kind == "native":
            author.close(); self.host = self.open()
        else:
            self.host = author
        listed = success(self.host.request({"operation": "provider.list"}))["providers"]
        assert any(provider["id"] == "local.sample.slice" for provider in listed)
        success(self.host.request({"operation": "provider.select", "capability": "sample.slice.v1", "provider_id": "local.sample.slice"}))

    def open(self):
        if self.kind == "cli": return CliSession(self.cli, self.root, self.assembly)
        if self.kind == "mcp": return McpSession(self.library, self.root, self.assembly)
        return NativeSession(self.native, self.root, self.assembly, self.project)

    def grant(self):
        result = success(self.host.request({"operation": "provider.permissions.configure",
                                           "granted_permissions": ["sample.slice.execute"]}))
        assert result["granted_permissions"] == ["sample.slice.execute"]

    def request(self, attempt="owner"):
        return {"operation": "provider.run", "attempt_id": attempt, "capability": "sample.slice.v1",
            "inputs": [{"port": "source_audio", "artifact": copy.deepcopy(self.source)}],
            "input_owners": [{"port": "source_audio", "occurrence": 0, "project_path": str(self.project),
                              "project_id": PROJECT, "asset_id": ASSET}],
            "parameters": {"refractory_frames": 1}, "data_classification": "public", "platform": "test",
            "region": "local", "required_permissions": ["sample.slice.execute"]}

    def inspect(self, attempt="owner"):
        return self.host.request({"operation": "attempt.inspect", "attempt_id": attempt})

    def snapshot(self):
        return {str(path.relative_to(self.project)): path.read_bytes()
                for path in self.project.rglob("*") if path.is_file()}

    def blob(self):
        return self.project / "assets" / (self.source["sha256"] + ".wav")

    def close(self):
        if self.host is not None:
            host, self.host = self.host, None
            host.close()

    def restart(self):
        self.close(); self.host = self.open()


def journey(f, mode):
    if mode != "permission": f.grant()
    request = f.request()
    code, reason = "NOT_FOUND", "input_artifact_unavailable"
    shape = False
    if mode == "permission": code, reason = "PERMISSION_DENIED", None
    if mode == "missing-owner": request.pop("input_owners")
    if mode == "project": request["input_owners"][0]["project_id"] = OTHER
    if mode == "asset": request["input_owners"][0]["asset_id"] = OTHER
    if mode == "reference": request["inputs"][0]["artifact"]["sha256"] = "a" * 64
    if mode == "binding": request["input_owners"][0]["occurrence"] = 1; code, reason, shape = "INVALID_ARGUMENT", None, True
    if mode == "missing-file": f.blob().unlink()
    if mode in ("hash", "length"):
        f.blob().write_bytes(f.original[:-1] + bytes([f.original[-1] ^ 1]) if mode == "hash" else f.original + b"x")
        code, reason = "IO_ERROR", "input_artifact_mismatch"
    if mode == "other-native-path":
        request["input_owners"][0]["project_path"] = str(f.root / "other.lmdj")
        code, reason, shape = "INVALID_ARGUMENT", None, True
    lock = None
    if mode == "busy":
        lease_root = (Path.home() / "Library/Application Support/LMDJ/project-writer-leases"
                      if sys.platform == "darwin" else Path(os.environ["XDG_STATE_HOME"]) / "lmdj/project-writer-leases")
        lease_path = lease_root / (hashlib.sha256(str(f.project.resolve()).encode()).hexdigest() + ".lock")
        assert lease_path.is_file(), lease_path
        lock = lease_path.open("r+b")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    before = f.snapshot()
    try:
        result = f.host.request(request)
    finally:
        if lock is not None: fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
    assert f.snapshot() == before, (f.kind, mode, "Project changed")
    assert str(f.project) not in canonical_json(result)
    if mode == "success":
        output = success(result)["outputs"]
        expected = (canonical_json({"contract": "lmdj.slice-points.v1", "source_sha256": f.source["sha256"],
                                   "frame_rate": 48000, "points": [{"frame": 1}, {"frame": 3}]})).encode()
        assert output == [{"port": "slice_points", "artifact": {
            "sha256": hashlib.sha256(expected).hexdigest(), "byte_length": len(expected), "media_type": "application/json"}}], output
    else:
        failure(result, code)
        if reason: assert result["error"]["details"]["reason"] == reason, result
    terminal = f.inspect()
    if shape:
        failure(terminal, "NOT_FOUND")
    else:
        state = success(terminal)
        assert state["status"] == ("succeeded" if mode == "success" else "failed")
        assert state["request"]["inputs"] == request["inputs"]
        assert str(f.project) not in canonical_json(state)
        if mode == "success": assert state["candidate_outputs"] == result["result"]["outputs"]
        else:
            assert state["candidate_outputs"] == [] and state["minted_outputs"] == []
            assert state["artifacts"] == [binding["artifact"] for binding in request["inputs"]]
    # Native startup validates all Project bytes. Repair only the deliberately
    # damaged fixture bytes after proving the refusal made no changes; the
    # failed Attempt must stay immutable even when its input becomes valid.
    if f.kind == "native" and mode in ("hash", "length", "missing-file"):
        f.blob().write_bytes(f.original)
        before = f.snapshot()
    f.restart()
    assert f.inspect() == terminal, (f.kind, mode, "terminal changed on restart")
    assert f.snapshot() == before
    if mode == "success":
        failure(f.host.request(f.request("no-regrant")), "PERMISSION_DENIED")
        failed = f.inspect("no-regrant")
        assert success(failed)["candidate_outputs"] == []
        f.restart(); assert f.inspect("no-regrant") == failed


def main():
    cli, native, library = map(lambda value: Path(value).resolve(), sys.argv[1:])
    modes = ("success", "permission", "missing-owner", "project", "asset", "reference",
             "binding", "missing-file", "hash", "length", "busy")
    for kind in ("cli", "mcp", "native"):
        for mode in modes + (("other-native-path",) if kind == "native" else ()):
            with tempfile.TemporaryDirectory(prefix=f"lmdj-owner-{kind}-{mode}-") as temporary:
                root = Path(temporary)
                previous_state = os.environ.get("XDG_STATE_HOME")
                os.environ["XDG_STATE_HOME"] = str(root / "state")
                fixture = None
                try:
                    fixture = Fixture(kind, root, cli, native, library)
                    journey(fixture, mode)
                except Exception as failure_detail:
                    raise AssertionError(f"{kind}/{mode}: {failure_detail}") from failure_detail
                finally:
                    if fixture is not None: fixture.close()
                    if previous_state is None: os.environ.pop("XDG_STATE_HOME", None)
                    else: os.environ["XDG_STATE_HOME"] = previous_state
        print(f"{kind}: owner success/refusal/close/restart/inspect passed")


if __name__ == "__main__":
    main()
