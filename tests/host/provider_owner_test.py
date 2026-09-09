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
from native_host_test import HostProcess, candidate_audition_reaches_a_voice

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "00000000-0000-4000-8000-000000000001"
ASSET = "00000000-0000-4000-8000-000000000002"
PATTERN = "00000000-0000-4000-8000-000000000010"
OTHER = "00000000-0000-4000-8000-000000000099"
QUERIES = {"project.inspect", "provider.list", "attempt.inspect",
           "candidate.job.inspect", "candidate.audition"}


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
        assert ready.get("operation") == "ready" and ready["ok"], ready

    def request(self, request):
        return self.host.request(request)

    def close(self):
        success(self.host.request({"operation": "stop"}))
        self.host.quit()


class Fixture:
    def __init__(self, kind, root, cli, native, library, candidate=False):
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
            "initial_pattern": {"pattern_id": PATTERN, "bars": 1, "events": [
                {"slot": {"bank": 0, "pad": 3}, "onset_tick": 0,
                 "duration_tick": 240, "velocity": 100}] if candidate else []}}))
        success(author.request({"operation": "asset.import", "project_path": str(self.project),
            "command_id": "00000000-0000-4000-8000-000000000003", "expected_revision": 0,
            "asset_id": ASSET, "source_path": str(self.source_file), "media_type": "audio/wav"}))
        inspected = success(author.request({"operation": "project.inspect", "project_path": str(self.project)}))["project"]
        self.source = inspected["assets"][ASSET]["artifact"]
        assert self.source == {"sha256": hashlib.sha256(self.original).hexdigest(),
                               "byte_length": len(self.original), "media_type": "audio/wav"}
        assert inspected["revision"] == 1
        if candidate:
            success(author.request({"operation": "pad.assign", "project_path": str(self.project),
                "command_id": "00000000-0000-4000-8000-000000000019", "expected_revision": 1,
                "slot": {"bank": 0, "pad": 3}, "asset_id": ASSET}))
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



def candidate_journey(f, mode):
    f.grant()
    request = {"operation": "candidate.job.run", "job_id": "slice", "attempt_id": "slice-first",
        "project_path": str(f.project), "project_id": PROJECT, "asset_id": ASSET,
        "expected_revision": 2, "parameters": {"refractory_frames": 1},
        "data_classification": "public", "platform": "test", "region": "local",
        "required_permissions": ["sample.slice.execute"]}

    def project():
        # Native has no generic Project inspect route; inspect its saved Truth
        # through the actual CLI Facade, never parse the Project bundle here.
        reader = CliSession(f.cli, f.root, f.assembly) if f.kind == "native" else f.host
        try:
            return success(reader.request({"operation": "project.inspect",
                                           "project_path": str(f.project)}))["project"]
        finally:
            if reader is not f.host: reader.close()

    if f.kind == "mcp":
        sys.path.insert(0, str(ROOT / "apps/core-mcp"))
        from lmdj_core_mcp.server import TOOLS_BY_NAME
        listed = {tool["name"]: tool for tool in f.host.host.request("tools/list", {})["tools"]}
        for name, tool in TOOLS_BY_NAME.items():
            if name.startswith("lmdj.candidate."):
                assert listed[name]["inputSchema"] == tool.input_schema
                assert listed[name]["outputSchema"] == tool.output_schema
        assert "lmdj.candidate.audition.stop" not in listed
    before = f.snapshot()
    original = project()
    assert original["patterns"][PATTERN]["events"], "Pattern leg must be nonempty"
    if mode == "zero": request["parameters"]["threshold_pcm16"] = 32767
    job = success(f.host.request(request))
    assert f.snapshot() == before
    inspection = {"operation": "candidate.job.inspect", "job_id": "slice"}
    assert success(f.host.request(inspection)) == job
    candidate_set = next(item for item in job["sets"] if item["set_id"] == job["active_set_id"])
    assert candidate_set["status"] == "active"
    assert "played" not in job
    terminal = f.inspect("slice-first")
    assert success(terminal)["status"] == "succeeded"
    if mode == "zero":
        assert candidate_set["recipes"] == []
        f.restart()
        assert success(f.host.request(inspection)) == job
        assert f.snapshot() == before and project() == original
        return
    recipes = candidate_set["recipes"]
    assert [(r["start_frame"], r["end_frame"]) for r in recipes] == [(0, 1), (1, 3), (3, 5)]
    preview = {"operation": "candidate.audition", "project_path": str(f.project),
        "project_id": PROJECT, "expected_revision": 2, "job_id": "slice",
        "set_id": candidate_set["set_id"], "candidate_id": recipes[1]["candidate_id"]}
    adopt = {key: value for key, value in preview.items() if key != "candidate_id"}
    adopt.update(operation="candidate.adopt", command_id="00000000-0000-4000-8000-000000000021",
        selections=[{"candidate_id": recipes[1]["candidate_id"], "bank": 2, "pad": 4},
                    {"candidate_id": recipes[1]["candidate_id"], "bank": 0, "pad": 3}])
    code = "NOT_FOUND"
    if mode == "stale": preview["expected_revision"] = adopt["expected_revision"] = 0; code = "REVISION_CONFLICT"
    if mode == "project": preview["project_id"] = adopt["project_id"] = OTHER; code = "REVISION_CONFLICT"
    if mode == "unknown":
        preview["candidate_id"] = "unknown"
        adopt["selections"][0]["candidate_id"] = "unknown"
    if mode == "missing": f.blob().unlink()
    if mode == "corrupt": f.blob().write_bytes(f.original[:-1] + b"x"); code = "COOK_FAILED"
    if mode == "discarded":
        discarded = success(f.host.request({"operation": "candidate.set.discard",
            "job_id": "slice", "set_id": candidate_set["set_id"]}))
        assert discarded["active_set_id"] is None
    if mode == "superseded":
        replacement = success(f.host.request({**request, "attempt_id": "slice-second"}))
        assert replacement["active_set_id"] != candidate_set["set_id"]
    if mode == "other-native-path":
        preview["project_path"] = adopt["project_path"] = str(f.root / "other.lmdj")
        code = "INVALID_ARGUMENT"
    if mode != "success":
        stable = f.snapshot()
        native_before = success(f.host.request({"operation": "status"})) if f.kind == "native" else None
        failure(f.host.request(preview), code)
        assert f.snapshot() == stable
        failure(f.host.request(adopt), code)
        assert f.snapshot() == stable
        if native_before is not None:
            native_after = success(f.host.request({"operation": "status"}))
            assert native_after["engine"]["started_voices"] == native_before["engine"]["started_voices"]
            assert native_after["bank"] == native_before["bank"]
        if mode in ("missing", "corrupt"): f.blob().write_bytes(f.original)
        state = success(f.host.request(inspection))
        f.restart()
        assert success(f.host.request(inspection)) == state
        assert f.inspect("slice-first") == terminal
        assert f.snapshot() == before and project() == original
        return
    # Preview twice, with actual Native voice admission and explicit stop.
    for _ in range(2):
        response = (candidate_audition_reaches_a_voice(f.host.host, preview)
                    if f.kind == "native" else f.host.request(preview))
        result = success(response)
        assert response["project_revision"] == 2
        expected_keys = {"job_id", "set_id", "candidate_id", "artifact", "sample_rate", "channels", "source_frames"}
        assert set(result) == expected_keys | ({"played"} if f.kind == "native" else set())
        assert (result["sample_rate"], result["channels"], result["source_frames"]) == (48000, 1, 2)
        assert result["artifact"]["byte_length"] == 48
        assert f.snapshot() == before and project() == original
        assert success(f.host.request(inspection)) == job
    # A repeated target is a refusal, whereas one recipe on distinct explicit
    # targets below is one sorted atomic commit with two independent Assets.
    duplicate = copy.deepcopy(adopt); duplicate["selections"][1] = duplicate["selections"][0]
    failure(f.host.request(duplicate), "INVALID_ARGUMENT")
    assert f.snapshot() == before and project() == original
    cancelled = f.host.request({"operation": "candidate.job.cancel", "job_id": "slice", "attempt_id": "slice-first"})
    failure(cancelled, "INVALID_ARGUMENT")
    assert cancelled["error"]["details"]["reason"] == "job_already_completed"
    assert success(f.host.request(inspection)) == job and f.snapshot() == before
    adopted_response = f.host.request(adopt)
    adopted = success(adopted_response)["adopted"]
    assert adopted_response["project_revision"] == 3
    assert [(item["bank"], item["pad"]) for item in adopted] == [(0, 3), (2, 4)]
    assert len({item["asset_id"] for item in adopted}) == 2
    committed = project()
    assert committed["revision"] == 3 and len(committed["assets"]) == len(original["assets"]) + 2
    assert committed["patterns"] == original["patterns"]
    assert committed["assets"][ASSET] == original["assets"][ASSET]
    assert f.blob().read_bytes() == f.original
    recipe = {key: value for key, value in recipes[1].items() if key != "candidate_id"}
    expected_lineage = {
        "source": {"kind": "asset_artifact", "artifact_sha256": f.source["sha256"], "project_revision": 2},
        "derivation": {"kind": "capability_adoption", "capability": candidate_set["capability"],
            "provider": candidate_set["provider"], "model_identity": candidate_set["model_identity"],
            "parameters_sha256": candidate_set["parameters_sha256"], "attempt_id": "slice-first",
            "source_asset_id": ASSET, "output_artifact": candidate_set["output_artifact"], "recipe": recipe}}
    for target in adopted:
        asset = committed["assets"][target["asset_id"]]
        assert asset["lineage"] == expected_lineage
        assert committed["banks"][target["bank"]]["pads"][target["pad"]]["asset_id"] == target["asset_id"]
        blob = f.project / "assets" / (asset["artifact"]["sha256"] + ".wav")
        encoded = blob.read_bytes()
        assert asset["artifact"] == {"sha256": hashlib.sha256(encoded).hexdigest(),
            "byte_length": len(encoded), "media_type": "audio/wav"}
        with wave.open(io.BytesIO(encoded), "rb") as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getnframes()) == (48000, 1, 2)
            assert wav.readframes(2) == struct.pack("<2h", 5000, 0)
    saved = f.snapshot()
    failure(f.host.request(adopt), "REVISION_CONFLICT")
    assert f.snapshot() == saved and project() == committed
    f.restart()
    assert project() == committed and f.snapshot() == saved
    assert success(f.host.request(inspection)) == job and f.inspect("slice-first") == terminal
    # Discard affects eligibility, never the already adopted Project Truth.
    success(f.host.request({"operation": "candidate.set.discard", "job_id": "slice", "set_id": candidate_set["set_id"]}))
    failure(f.host.request({**preview, "expected_revision": 2}), "NOT_FOUND")
    assert project() == committed and f.snapshot() == saved
    f.restart()
    assert project() == committed and f.snapshot() == saved

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
        candidate_modes = ("success", "zero", "stale", "project", "unknown", "missing", "corrupt", "discarded", "superseded")
        for mode in candidate_modes + (("other-native-path",) if kind == "native" else ()):
            with tempfile.TemporaryDirectory(prefix=f"lmdj-candidate-{kind}-{mode}-") as temporary:
                fixture = None
                previous_state = os.environ.get("XDG_STATE_HOME")
                os.environ["XDG_STATE_HOME"] = str(Path(temporary) / "state")
                try:
                    fixture = Fixture(kind, Path(temporary), cli, native, library, candidate=True)
                    candidate_journey(fixture, mode)
                except Exception as failure_detail:
                    raise AssertionError(f"candidate {kind}/{mode}: {failure_detail}") from failure_detail
                finally:
                    if fixture is not None: fixture.close()
                    if previous_state is None: os.environ.pop("XDG_STATE_HOME", None)
                    else: os.environ["XDG_STATE_HOME"] = previous_state
        print(f"{kind}: Candidate analyze/preview/adopt/refusal/reopen passed")


if __name__ == "__main__":
    main()
