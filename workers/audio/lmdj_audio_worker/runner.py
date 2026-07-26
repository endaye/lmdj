from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Protocol

STDERR_TAIL_CHARS = 2000


class PipelineRunError(RuntimeError):
    def __init__(self, message: str, stderr_tail: str = "") -> None:
        super().__init__(message)
        self.stderr_tail = stderr_tail


class PipelineRunner(Protocol):
    def run(self, audio: Path, out_dir: Path, song_id: str) -> Path: ...


class DemoPipelineRunner:
    """子进程调用冻结的参考 demo pipeline（demo 自己的 venv，依赖完全隔离）。"""

    pipeline_id = "legacy"

    def __init__(self, demo_dir: Path, fast: bool = True, timeout_sec: int = 1800) -> None:
        self.demo_dir = demo_dir.resolve()
        self.fast = fast
        self.timeout_sec = timeout_sec

    @property
    def executable(self) -> Path:
        return self.demo_dir / ".venv" / "bin" / "song-pipeline"

    @property
    def python(self) -> Path:
        return self.demo_dir / ".venv" / "bin" / "python"

    @property
    def bootstrap(self) -> Path:
        return Path(__file__).with_name("deterministic_bootstrap.py")

    @staticmethod
    def seed_for_audio(audio: Path) -> int:
        digest = hashlib.sha256()
        with audio.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return int.from_bytes(digest.digest(), "big")

    def command(self, audio: Path, out_dir: Path, song_id: str) -> list[str]:
        cmd = [
            str(self.python), str(self.bootstrap), str(self.seed_for_audio(audio)),
            str(self.executable), "run", str(audio),
            "--out", str(out_dir), "--song-id", song_id,
        ]
        if self.fast:
            cmd.append("--fast")
        return cmd

    def run(self, audio: Path, out_dir: Path, song_id: str) -> Path:
        if not self.executable.exists():
            raise PipelineRunError(
                f"demo venv missing at {self.executable} — "
                "先在仓库根目录运行: scripts/dev.sh setup-demo"
            )
        try:
            proc = subprocess.run(
                self.command(audio, out_dir, song_id),
                capture_output=True, text=True, timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired as error:
            raise PipelineRunError(
                f"pipeline timed out after {self.timeout_sec}s") from error
        if proc.returncode != 0:
            raise PipelineRunError(
                f"pipeline exited with code {proc.returncode}",
                stderr_tail=(proc.stderr or "")[-STDERR_TAIL_CHARS:],
            )
        package_dir = out_dir / song_id
        if not (package_dir / "lanes.json").exists():
            raise PipelineRunError(f"pipeline produced no lanes.json in {package_dir}")
        return package_dir


class PipelineFromStemsRunner:
    """子进程调用 pipeline-from-stems（专用 .venv-pfs，DSP 依赖隔离，spec §3.1）。"""

    pipeline_id = "legacy-pfs"

    def __init__(self, worker_dir: Path | None = None, timeout_sec: int = 600) -> None:
        self.worker_dir = (worker_dir or Path(__file__).resolve().parent.parent)
        self.timeout_sec = timeout_sec

    @property
    def python(self) -> Path:
        return self.worker_dir / ".venv-pfs" / "bin" / "python"

    def command(self, stems_dir: Path, out_dir: Path, song_id: str) -> list[str]:
        return [str(self.python), "-m", "lmdj_audio_worker.pipeline_from_stems",
                "--stems", str(stems_dir), "--out", str(out_dir),
                "--song-id", song_id]

    def run(self, stems_dir: Path, out_dir: Path, song_id: str) -> Path:
        if not self.python.exists():
            raise PipelineRunError(
                f"pfs venv missing at {self.python} — "
                "先在仓库根目录运行: scripts/dev.sh setup-pfs")
        try:
            proc = subprocess.run(
                self.command(stems_dir, out_dir, song_id),
                capture_output=True, text=True, timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired as error:
            raise PipelineRunError(
                f"pipeline-from-stems timed out after {self.timeout_sec}s") from error
        if proc.returncode != 0:
            raise PipelineRunError(
                f"pipeline-from-stems exited with code {proc.returncode}",
                stderr_tail=(proc.stderr or "")[-STDERR_TAIL_CHARS:],
            )
        package_dir = out_dir / song_id
        if not (package_dir / "lanes.json").exists():
            raise PipelineRunError(
                f"pipeline-from-stems produced no lanes.json in {package_dir}")
        return package_dir
