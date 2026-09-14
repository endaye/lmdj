"""Author the Slice UI's pre-existing Pad and recorded Pattern through CLI.

This fixture fixes the facts that adoption must preserve. The general Creator
fixture has an empty Pattern and a long assignment history, neither of which
exercises the Candidate journey's recorded-Pattern preservation requirement.
"""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import wave


def main():
    executable, assembly, output = map(Path, sys.argv[1:])
    repo = Path(__file__).resolve().parents[5]
    with tempfile.TemporaryDirectory(prefix="lmdj-candidate-ui-fixture-") as root:
        root = Path(root)
        project = root / "recorded.lmdj"
        workspace = root / "workspace"
        workspace.mkdir()
        source = root / "original.wav"
        with wave.open(str(source), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(48000)
            stream.writeframes(struct.pack("<48000h", *([-4000] * 48000)))
        project_id = "00000000-0000-4000-8000-000000000001"
        asset_id = "00000000-0000-4000-8000-000000000101"
        pattern_id = "00000000-0000-4000-8000-000000000010"
        event = {"onset_tick": 0, "duration_tick": 240,
                 "slot": {"bank": 0, "pad": 0}, "velocity": 100}

        def invoke(surface, request, revision):
            response = subprocess.run(
                [str(executable), "--workspace", str(workspace), "--assembly",
                 str(assembly), surface, "--request", json.dumps(request)],
                capture_output=True, text=True, check=True,
            )
            value = json.loads(response.stdout)
            assert not response.stderr and value.get("ok") is True, value
            assert value.get("project_revision") == revision, value
            return value["result"]

        invoke("command", {"operation": "project.create", "project_path": str(project),
            "project_id": project_id, "bpm": 120,
            "initial_pattern": {"pattern_id": pattern_id, "bars": 1, "events": [event]}}, 0)
        invoke("command", {"operation": "asset.import", "project_path": str(project),
            "command_id": "00000000-0000-4000-8000-000000000201", "expected_revision": 0,
            "asset_id": asset_id, "source_path": str(source), "media_type": "audio/wav"}, 1)
        invoke("command", {"operation": "pad.assign", "project_path": str(project),
            "command_id": "00000000-0000-4000-8000-000000000202", "expected_revision": 1,
            "slot": {"bank": 0, "pad": 0}, "asset_id": asset_id}, 2)
        inspected = invoke("query", {"operation": "project.inspect",
            "project_path": str(project)}, 2)
        assert inspected["project"]["patterns"][pattern_id]["events"] == [event]
        assert inspected["project"]["banks"][0]["pads"][0]["asset_id"] == asset_id
        subprocess.run([sys.executable, str(repo / "tools/project-bundle/project_bundle.py"),
            "pack", "--source", str(project), "--output", str(output)], check=True)


if __name__ == "__main__":
    main()
