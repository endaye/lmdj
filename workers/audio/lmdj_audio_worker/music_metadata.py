from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

STDERR_TAIL_CHARS = 2000


@dataclass(frozen=True)
class KeyEstimate:
    value: str
    confidence: float


class KeyAnalyzer(Protocol):
    def analyze(self, audio: Path) -> KeyEstimate: ...


class KeyAnalysisError(RuntimeError):
    """Key metadata could not be produced at the isolated PFS boundary."""


class PfsKeyAnalyzer:
    """Run Key analysis in the PipelineFromStems virtual environment."""

    def __init__(self, worker_dir: Path | None = None, timeout_sec: float = 120) -> None:
        self.worker_dir = worker_dir or Path(__file__).resolve().parent.parent
        self.timeout_sec = timeout_sec

    @property
    def python(self) -> Path:
        return self.worker_dir / ".venv-pfs" / "bin" / "python"

    def command(self, audio: Path) -> list[str]:
        return [
            str(self.python),
            "-m",
            "lmdj_audio_worker.pipeline_from_stems.key_analysis",
            "--audio",
            str(audio),
        ]

    def analyze(self, audio: Path) -> KeyEstimate:
        if not self.python.exists():
            raise KeyAnalysisError(
                f"pfs venv missing at {self.python} — "
                "先在仓库根目录运行: scripts/dev.sh setup-pfs",
            )
        try:
            process = subprocess.run(
                self.command(audio),
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired as error:
            raise KeyAnalysisError(
                f"key analysis timed out after {self.timeout_sec}s",
            ) from error
        if process.returncode != 0:
            stderr = (process.stderr or "")[-STDERR_TAIL_CHARS:]
            detail = f": {stderr.strip()}" if stderr.strip() else ""
            raise KeyAnalysisError(
                f"key analysis exited with code {process.returncode}{detail}",
            )
        try:
            payload = json.loads(process.stdout)
            value = payload["value"]
            confidence = float(payload["confidence"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise KeyAnalysisError("key analysis returned invalid JSON") from error
        if not isinstance(value, str) or not value.strip():
            raise KeyAnalysisError("key analysis returned an invalid Key value")
        if not 0.0 <= confidence <= 1.0:
            raise KeyAnalysisError("key analysis returned confidence outside 0..1")
        return KeyEstimate(value=value, confidence=confidence)
