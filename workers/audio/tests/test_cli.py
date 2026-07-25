import json
import subprocess
import sys
from pathlib import Path

from tests.conftest import STUB_FAIL_BODY, STUB_OK_BODY, make_stub_demo


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "lmdj_audio_worker.cli", *args],
        capture_output=True, text=True,
    )


def test_run_completes_and_status_reads_back(tmp_path: Path, sample_audio: Path):
    demo = make_stub_demo(tmp_path, STUB_OK_BODY)
    jobs_root = tmp_path / "jobs"

    result = run_cli(
        "run", str(sample_audio),
        "--job-id", "clitest",
        "--jobs-root", str(jobs_root),
        "--demo-dir", str(demo),
    )

    assert result.returncode == 0, result.stderr
    assert "-> completed" in result.stdout
    assert "patch.json" in result.stdout

    status = run_cli("status", "clitest", "--jobs-root", str(jobs_root))
    assert status.returncode == 0
    completed = json.loads(status.stdout)
    assert completed["state"] == "completed"
    assert (jobs_root / "clitest" / completed["package_dir"] / "patch.json").exists()


def test_run_failure_exits_1_with_error(tmp_path: Path, sample_audio: Path):
    demo = make_stub_demo(tmp_path, STUB_FAIL_BODY)

    result = run_cli(
        "run", str(sample_audio),
        "--job-id", "clifail",
        "--jobs-root", str(tmp_path / "jobs"),
        "--demo-dir", str(demo),
    )

    assert result.returncode == 1
    assert "demucs exploded" in result.stderr


def test_status_unknown_job_exits_1(tmp_path: Path):
    result = run_cli("status", "ghost", "--jobs-root", str(tmp_path / "jobs"))
    assert result.returncode == 1
    assert "unknown job_id" in result.stderr


def test_run_missing_audio_exits_1_with_clean_error(tmp_path: Path):
    result = run_cli(
        "run", str(tmp_path / "ghost.wav"),
        "--job-id", "cli-ghost",
        "--jobs-root", str(tmp_path / "jobs"),
        "--demo-dir", str(tmp_path / "demo"),
    )
    assert result.returncode == 1
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr  # clean convention, not a raw crash
