from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from lmdj_audio_worker.separation import protocol
from lmdj_audio_worker.separation.registry import SeparatorEntry

# 各 fake runner 都是 `python -c SCRIPT output_dir` 形态
OK_SCRIPT = r"""
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
(out / "separation.json").write_text(json.dumps({
    "schema_version": "lmdj.separation.v1",
    "status": "completed", "source": "runner",
    "input_sha256": "a" * 64,
    "separator": {"id": "fake", "family": "demucs",
                  "checkpoint_sha256": "b" * 64, "runner_version": "0.1.0"},
    "requested_device": "cpu", "actual_device": "cpu",
    "stems": {k: f"stems/{k}.wav" for k in ("drums", "bass", "vocals", "other")},
    "audio": {"sample_rate": 44100, "channels": 2, "duration_seconds": 1.0},
    "performance": {"model_load_seconds": 0, "inference_seconds": 0,
                    "wall_seconds": 0, "peak_rss_bytes": 0,
                    "peak_device_memory_bytes": 0},
}))
"""
CRASH_SCRIPT = "import sys; print('boom', file=sys.stderr); sys.exit(3)"
KILL_SCRIPT = "import os; os.kill(os.getpid(), 9)"
HANG_SCRIPT = "import time; time.sleep(30)"
CORRUPT_SCRIPT = r"""
import sys
from pathlib import Path
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
(out / "separation.json").write_text("{not json")
"""


def make_entry(script: str) -> SeparatorEntry:
    return SeparatorEntry(
        id="fake", family="demucs", runner="demucs",
        command=(sys.executable, "-c", script, "{output_dir}"),
        source_url="https://example.com/fake.th", source_revision="r1",
        artifact_sha256="c" * 64, license_code="MIT", license_weights="MIT",
        stems=("drums", "bass", "vocals", "other"),
        sample_rate=44100, channels=2, devices=("cpu",),
        inference={}, env_lock_sha256="d" * 64, status="experimental")


@pytest.fixture()
def request_(tmp_path) -> protocol.SeparationRequest:
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"not really audio, sha input")
    return protocol.SeparationRequest(
        input_path=input_path, output_dir=tmp_path / "out", device="cpu")


def test_build_command_substitutes_placeholders(request_, tmp_path):
    entry = make_entry(OK_SCRIPT)
    cmd = protocol.build_command(entry, request_, tmp_path / "ckpt")
    assert cmd[-1] == str(request_.output_dir)


def test_runner_written_result_returned(request_, tmp_path):
    result = protocol.run_separator(make_entry(OK_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=30)
    assert result.status == "completed"
    assert result.source == "runner"


def test_crash_synthesizes_inference_failure(request_, tmp_path):
    result = protocol.run_separator(make_entry(CRASH_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=30)
    assert result.status == "failed"
    assert result.source == "orchestrator"
    assert result.error.category == "inference"
    assert result.error.exit_code == 3
    assert "boom" in result.error.stderr_tail
    # 合成记录必须落盘且 schema 合法
    on_disk = json.loads((request_.output_dir / "separation.json").read_text())
    assert on_disk["source"] == "orchestrator"


def test_sigkill_synthesizes_oom(request_, tmp_path):
    result = protocol.run_separator(make_entry(KILL_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=30)
    assert result.status == "failed"
    assert result.error.category == "oom"


def test_timeout_synthesizes_timeout(request_, tmp_path):
    result = protocol.run_separator(make_entry(HANG_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=1)
    assert result.status == "failed"
    assert result.error.category == "timeout"


def test_corrupt_result_with_zero_exit_synthesizes_invalid_stems(request_, tmp_path):
    result = protocol.run_separator(make_entry(CORRUPT_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=30)
    assert result.status == "failed"
    assert result.error.category == "invalid_stems"
    assert result.error.exit_code == 0


def test_synthesized_input_sha_matches_file(request_, tmp_path):
    import hashlib
    result = protocol.run_separator(make_entry(CRASH_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=30)
    expected = hashlib.sha256(request_.input_path.read_bytes()).hexdigest()
    assert result.input_sha256 == expected
