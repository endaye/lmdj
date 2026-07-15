from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lmdj_audio_worker.pipeline_from_stems import runner


def test_load_legacy_stems_reports_missing(tmp_path):
    sf.write(tmp_path / "drums.wav", np.zeros((100, 2), dtype=np.float32), 44100)
    with pytest.raises(FileNotFoundError) as exc:
        runner.load_legacy_stems(tmp_path, 44100)
    assert "bass" in str(exc.value) and "melody" in str(exc.value)


def test_load_legacy_stems_returns_all_three(tmp_path):
    for name in runner.LEGACY_STEMS:
        sf.write(tmp_path / f"{name}.wav",
                 np.zeros((100, 2), dtype=np.float32), 44100)
    stems = runner.load_legacy_stems(tmp_path, 44100)
    assert set(stems) == set(runner.LEGACY_STEMS)


def test_cli_help_exits_zero():
    from lmdj_audio_worker.pipeline_from_stems.__main__ import main
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
