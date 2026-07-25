from __future__ import annotations

import stat
import sys
import types
from pathlib import Path

import pytest

from lmdj_audio_worker.music_metadata import (
    KeyAnalysisError,
    KeyEstimate,
    PfsKeyAnalyzer,
)
from lmdj_audio_worker.pipeline_from_stems.key_analysis import estimate_key


def _make_fake_pfs_python(tmp_path: Path, body: str) -> Path:
    bin_dir = tmp_path / ".venv-pfs" / "bin"
    bin_dir.mkdir(parents=True)
    executable = bin_dir / "python"
    executable.write_text("#!/bin/sh\n" + body)
    executable.chmod(executable.stat().st_mode | stat.S_IEXEC)
    return executable


def test_estimate_key_matches_synthetic_c_major_chroma(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c_major_profile = [
        6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
        2.52, 5.19, 2.39, 3.66, 2.29, 2.88,
    ]
    fake_librosa = types.SimpleNamespace(
        load=lambda _path, sr, mono: ([0.0], sr),
        feature=types.SimpleNamespace(
            chroma_cqt=lambda y, sr: [[value, value] for value in c_major_profile],
        ),
    )
    monkeypatch.setitem(sys.modules, "librosa", fake_librosa)

    estimate = estimate_key(tmp_path / "c-major.wav")

    assert estimate.value == "C major"
    assert 0.0 <= estimate.confidence <= 1.0


def test_pfs_key_analyzer_uses_fixed_subprocess_command(tmp_path: Path) -> None:
    _make_fake_pfs_python(
        tmp_path,
        """printf '%s\\n' '{"value":"A minor","confidence":0.72}'""",
    )
    audio = tmp_path / "song.wav"
    analyzer = PfsKeyAnalyzer(worker_dir=tmp_path)

    assert analyzer.command(audio) == [
        str(tmp_path / ".venv-pfs" / "bin" / "python"),
        "-m",
        "lmdj_audio_worker.pipeline_from_stems.key_analysis",
        "--audio",
        str(audio),
    ]
    assert analyzer.analyze(audio) == KeyEstimate(value="A minor", confidence=0.72)


def test_pfs_key_analyzer_reports_nonzero_exit(tmp_path: Path) -> None:
    _make_fake_pfs_python(tmp_path, 'echo "analysis exploded" >&2; exit 3')
    analyzer = PfsKeyAnalyzer(worker_dir=tmp_path)

    with pytest.raises(KeyAnalysisError, match="exited with code 3") as error:
        analyzer.analyze(tmp_path / "song.wav")

    assert "analysis exploded" in str(error.value)


def test_pfs_key_analyzer_reports_timeout(tmp_path: Path) -> None:
    _make_fake_pfs_python(tmp_path, "sleep 1")
    analyzer = PfsKeyAnalyzer(worker_dir=tmp_path, timeout_sec=0.01)

    with pytest.raises(KeyAnalysisError, match="timed out"):
        analyzer.analyze(tmp_path / "song.wav")


def test_pfs_key_analyzer_reports_missing_venv(tmp_path: Path) -> None:
    analyzer = PfsKeyAnalyzer(worker_dir=tmp_path)

    with pytest.raises(KeyAnalysisError, match="setup-pfs"):
        analyzer.analyze(tmp_path / "song.wav")
