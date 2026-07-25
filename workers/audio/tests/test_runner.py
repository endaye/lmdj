import hashlib
from pathlib import Path

import pytest

from lmdj_audio_worker.runner import DemoPipelineRunner, PipelineRunError

from tests.conftest import STUB_EMPTY_BODY, STUB_FAIL_BODY, STUB_OK_BODY, make_stub_demo


def test_command_builds_exact_argv_with_fast(tmp_path: Path):
    demo = make_stub_demo(tmp_path, STUB_OK_BODY)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"exact command audio")
    runner = DemoPipelineRunner(demo, fast=True)
    cmd = runner.command(audio, tmp_path / "job", "jobid123")

    assert cmd == [
        str(demo / ".venv" / "bin" / "python"),
        str(runner.bootstrap),
        str(int.from_bytes(hashlib.sha256(audio.read_bytes()).digest(), "big")),
        str(demo / ".venv" / "bin" / "song-pipeline"),
        "run", str(audio),
        "--out", str(tmp_path / "job"),
        "--song-id", "jobid123",
        "--fast",
    ]


def test_command_omits_fast_when_disabled(tmp_path: Path):
    runner = DemoPipelineRunner(tmp_path / "demo", fast=False)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    cmd = runner.command(audio, tmp_path / "job", "jobid123")
    assert "--fast" not in cmd


def test_content_seed_is_path_independent_and_separates_different_audio(tmp_path: Path):
    first = tmp_path / "first.wav"
    same_bytes_elsewhere = tmp_path / "nested" / "second.wav"
    different = tmp_path / "different.wav"
    first.write_bytes(b"same audio bytes")
    same_bytes_elsewhere.parent.mkdir()
    same_bytes_elsewhere.write_bytes(first.read_bytes())
    different.write_bytes(b"different audio bytes")

    assert DemoPipelineRunner.seed_for_audio(first) == DemoPipelineRunner.seed_for_audio(
        same_bytes_elsewhere,
    )
    assert DemoPipelineRunner.seed_for_audio(first) != DemoPipelineRunner.seed_for_audio(different)


def test_child_random_sequence_is_repeatable_from_audio_content(tmp_path: Path, sample_audio: Path):
    body = '''
import argparse, random
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("cmd"); p.add_argument("input", type=Path)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--song-id", required=True)
p.add_argument("--fast", action="store_true")
a = p.parse_args()
package = a.out / a.song_id
package.mkdir()
(package / "lanes.json").write_text("{}")
(package / "random.txt").write_text(",".join(str(random.randrange(1_000_000)) for _ in range(3)))
'''
    demo = make_stub_demo(tmp_path, body)
    runner = DemoPipelineRunner(demo)

    first_out = tmp_path / "first-job"
    second_out = tmp_path / "second-job"
    first_out.mkdir()
    second_out.mkdir()
    first = runner.run(sample_audio, first_out, "first")
    second = runner.run(sample_audio, second_out, "second")

    assert (first / "random.txt").read_text() == (second / "random.txt").read_text()


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
