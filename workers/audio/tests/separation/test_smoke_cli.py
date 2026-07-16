from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from lmdj_audio_worker.separation import smoke

SR = 44100
OK_RUNNER = """
import hashlib, json, sys
from pathlib import Path
import numpy as np
import soundfile as sf
out = Path(sys.argv[1]); inp = Path(sys.argv[2])
frames = sf.info(str(inp)).frames
(out / "stems").mkdir(parents=True, exist_ok=True)
for k in ("drums", "bass", "vocals", "other"):
    sf.write(out / "stems" / (k + ".wav"),
             np.zeros((frames, 2), dtype=np.float32), 44100, subtype="FLOAT")
(out / "separation.json").write_text(json.dumps({
    "schema_version": "lmdj.separation.v1", "status": "completed",
    "source": "runner",
    "input_sha256": hashlib.sha256(inp.read_bytes()).hexdigest(),
    "separator": {"id": "fake", "family": "demucs",
                  "checkpoint_sha256": "b" * 64, "runner_version": "0.1.0"},
    "requested_device": "cpu", "actual_device": "cpu",
    "stems": {k: "stems/" + k + ".wav" for k in ("drums", "bass", "vocals", "other")},
    "audio": {"sample_rate": 44100, "channels": 2,
              "duration_seconds": frames / 44100},
    "performance": {"model_load_seconds": 0, "inference_seconds": 0,
                    "wall_seconds": 0, "peak_rss_bytes": 0,
                    "peak_device_memory_bytes": 0},
}))
"""


def make_env(tmp_path, monkeypatch):
    payload = b"weights"
    sha = hashlib.sha256(payload).hexdigest()
    weights_file = tmp_path / "weights.bin"
    weights_file.write_bytes(payload)

    # Write the runner script to a file
    runner_script = tmp_path / "runner.py"
    runner_script.write_text(OK_RUNNER)

    registry_path = tmp_path / "separators.json"
    registry_path.write_text(json.dumps({
        "schema_version": "lmdj.separators.v1",
        "separators": [{
            "id": "fake", "family": "demucs", "runner": "demucs",
            "command": [sys.executable, str(runner_script), "{output_dir}", "{input}"],
            "source": {"url": weights_file.as_uri(), "revision": "r1"},
            "artifact_sha256": sha,
            "license": {"code": "MIT", "weights": "MIT"},
            "stems": ["drums", "bass", "other", "vocals"],
            "sample_rate": 44100, "channels": 2, "devices": ["cpu"],
            "inference": {}, "env_lock_sha256": "d" * 64,
            "status": "experimental"}]}))
    input_path = tmp_path / "song.wav"
    sf.write(input_path, np.zeros((SR, 2), dtype=np.float32), SR)
    monkeypatch.setenv("LMDJ_MODEL_CACHE", str(tmp_path / "cache"))
    return registry_path, input_path


def test_smoke_completed_exit_zero(tmp_path, monkeypatch, capsys):
    registry_path, input_path = make_env(tmp_path, monkeypatch)
    code = smoke.main(["--id", "fake", "--input", str(input_path),
                       "--device", "cpu", "--out", str(tmp_path / "run"),
                       "--registry", str(registry_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "actual_device: cpu" in out and "canonical OK" in out


def test_smoke_unknown_id_exit_one(tmp_path, monkeypatch):
    registry_path, input_path = make_env(tmp_path, monkeypatch)
    code = smoke.main(["--id", "nope", "--input", str(input_path),
                       "--device", "cpu", "--out", str(tmp_path / "run"),
                       "--registry", str(registry_path)])
    assert code == 1


def test_smoke_device_not_in_entry_exit_one(tmp_path, monkeypatch):
    registry_path, input_path = make_env(tmp_path, monkeypatch)
    code = smoke.main(["--id", "fake", "--input", str(input_path),
                       "--device", "mps", "--out", str(tmp_path / "run"),
                       "--registry", str(registry_path)])
    assert code == 1
