from __future__ import annotations

from pathlib import Path

import pytest

from lmdj_audio_worker import envcheck


def test_read_constraints_parses_pins(tmp_path):
    path = tmp_path / "c.txt"
    path.write_text("# 注释\nlibrosa==0.11.0\npretty_midi==0.2.11\n\n")
    assert envcheck.read_constraints(path) == {
        "librosa": "0.11.0", "pretty-midi": "0.2.11"}


def test_read_constraints_rejects_range_pins(tmp_path):
    path = tmp_path / "c.txt"
    path.write_text("librosa>=0.10\n")
    with pytest.raises(ValueError, match="=="):
        envcheck.read_constraints(path)


def test_check_ok():
    pins = {"librosa": "0.11.0"}
    installed = {"librosa": "0.11.0", "extra-pkg": "1.0"}
    assert envcheck.check(pins, installed, "venvA") == []


def test_check_reports_missing_and_mismatch():
    pins = {"librosa": "0.11.0", "numpy": "1.26.4"}
    installed = {"numpy": "2.0.0"}
    errors = envcheck.check(pins, installed, "venvA")
    assert any("librosa" in e and "缺少" in e for e in errors)
    assert any("numpy" in e and "2.0.0" in e for e in errors)


def test_shipped_constraints_file_parses():
    shipped = (Path(__file__).resolve().parents[1]
               / "config" / "parity-constraints.txt")
    pins = envcheck.read_constraints(shipped)
    assert pins["librosa"] == "0.11.0"
    assert pins["numpy"] == "1.26.4"
