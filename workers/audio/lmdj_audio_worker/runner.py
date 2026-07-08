from __future__ import annotations

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

    def __init__(self, demo_dir: Path, fast: bool = True, timeout_sec: int = 1800) -> None:
        self.demo_dir = demo_dir.resolve()
        self.fast = fast
        self.timeout_sec = timeout_sec

    @property
    def executable(self) -> Path:
        return self.demo_dir / ".venv" / "bin" / "song-pipeline"

    def command(self, audio: Path, out_dir: Path, song_id: str) -> list[str]:
        cmd = [
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
