from __future__ import annotations

import stat
from pathlib import Path

import pytest

from lmdj_audio_worker.runner import PipelineFromStemsRunner, PipelineRunError


def make_fake_venv(tmp_path: Path, script_body: str) -> Path:
    """伪 .venv-pfs：bin/python 是一个 shell 脚本。"""
    bin_dir = tmp_path / ".venv-pfs" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text(f"#!/bin/sh\n{script_body}\n")
    python.chmod(python.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def test_command_shape(tmp_path):
    runner = PipelineFromStemsRunner(worker_dir=tmp_path)
    cmd = runner.command(Path("/s"), Path("/o"), "song1")
    assert cmd[1:3] == ["-m", "lmdj_audio_worker.pipeline_from_stems"]
    assert "--song-id" in cmd and "song1" in cmd


def test_missing_venv_raises_with_hint(tmp_path):
    runner = PipelineFromStemsRunner(worker_dir=tmp_path)
    with pytest.raises(PipelineRunError, match="setup-pfs"):
        runner.run(tmp_path, tmp_path / "out", "song1")


def test_run_returns_package_dir(tmp_path):
    # 伪 python：在 out/song1 写出 lanes.json 后退出 0
    worker_dir = make_fake_venv(tmp_path, (
        'while [ "$1" != "--out" ]; do shift; done; out="$2"\n'
        'mkdir -p "$out/song1" && echo "{}" > "$out/song1/lanes.json"'))
    runner = PipelineFromStemsRunner(worker_dir=worker_dir)
    package = runner.run(tmp_path / "stems", tmp_path / "out", "song1")
    assert package == tmp_path / "out" / "song1"


def test_nonzero_exit_raises_with_stderr(tmp_path):
    worker_dir = make_fake_venv(tmp_path, 'echo "kaput" >&2; exit 1')
    runner = PipelineFromStemsRunner(worker_dir=worker_dir)
    with pytest.raises(PipelineRunError) as exc:
        runner.run(tmp_path / "stems", tmp_path / "out", "song1")
    assert "kaput" in exc.value.stderr_tail
