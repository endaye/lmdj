from pathlib import Path

import pytest

from lmdj_audio_worker.runner import DemoPipelineRunner, PipelineRunError

from tests.conftest import STUB_EMPTY_BODY, STUB_FAIL_BODY, STUB_OK_BODY, make_stub_demo


def test_command_builds_exact_argv_with_fast(tmp_path: Path):
    runner = DemoPipelineRunner(tmp_path / "demo", fast=True)
    cmd = runner.command(Path("/in/song.wav"), tmp_path / "job", "jobid123")

    assert cmd == [
        str(tmp_path / "demo" / ".venv" / "bin" / "song-pipeline"),
        "run", "/in/song.wav",
        "--out", str(tmp_path / "job"),
        "--song-id", "jobid123",
        "--fast",
    ]


def test_command_omits_fast_when_disabled(tmp_path: Path):
    runner = DemoPipelineRunner(tmp_path / "demo", fast=False)
    cmd = runner.command(Path("/in/song.wav"), tmp_path / "job", "jobid123")
    assert "--fast" not in cmd


def test_run_missing_venv_hints_setup_demo(tmp_path: Path):
    runner = DemoPipelineRunner(tmp_path / "nonexistent-demo")
    with pytest.raises(PipelineRunError, match="setup-demo"):
        runner.run(tmp_path / "song.wav", tmp_path / "job", "jobid123")


def test_run_success_returns_package_dir(tmp_path: Path, sample_audio: Path):
    demo = make_stub_demo(tmp_path, STUB_OK_BODY)
    out_dir = tmp_path / "job"
    out_dir.mkdir()

    package = DemoPipelineRunner(demo).run(sample_audio, out_dir, "jobid123")

    assert package == out_dir / "jobid123"
    assert (package / "lanes.json").exists()


def test_run_nonzero_exit_carries_stderr_tail(tmp_path: Path, sample_audio: Path):
    demo = make_stub_demo(tmp_path, STUB_FAIL_BODY)
    out_dir = tmp_path / "job"
    out_dir.mkdir()

    with pytest.raises(PipelineRunError, match="exited with code 2") as exc_info:
        DemoPipelineRunner(demo).run(sample_audio, out_dir, "jobid123")
    assert "demucs exploded" in exc_info.value.stderr_tail


def test_run_missing_lanes_json_fails(tmp_path: Path, sample_audio: Path):
    demo = make_stub_demo(tmp_path, STUB_EMPTY_BODY)
    out_dir = tmp_path / "job"
    out_dir.mkdir()

    with pytest.raises(PipelineRunError, match="lanes.json"):
        DemoPipelineRunner(demo).run(sample_audio, out_dir, "jobid123")
