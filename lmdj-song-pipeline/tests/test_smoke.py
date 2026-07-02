"""冒烟测试：合成已知 BPM 的测试曲，跑阶段 3-6，验证 PRD 的关键断言。

跑法: .venv/bin/python -m pytest tests/ -q
"""
import json
import sys
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from song_pipeline.config import PipelineConfig
from song_pipeline.pipeline import run_pipeline


@pytest.fixture(scope="module")
def report_and_dir(tmp_path_factory):
    import make_test_song
    out_root = tmp_path_factory.mktemp("out")
    song_dir = out_root / "testsong"
    make_test_song.main(song_dir)  # 预置 stems 缓存，跳过 demucs
    report = run_pipeline(song_dir / "input.wav", out_root, "testsong",
                          PipelineConfig())
    return report, song_dir


def test_pipeline_passes(report_and_dir):
    report, _ = report_and_dir
    assert report["status"] == "passed"
    assert report["score"] >= 0.5


def test_bpm_no_octave_error(report_and_dir):
    report, _ = report_and_dir
    assert 80 <= report["bpm"] <= 100  # 合成曲 90 bpm，不应测成 180


def test_loop_duration(report_and_dir):
    # loop 时长 = 4 小节 × 4 拍 × (60/BPM)，容差 5%（beat 跟踪有抖动）
    report, _ = report_and_dir
    expect = 4 * 4 * 60 / report["bpm"]
    assert abs(report["loop_seconds"] - expect) / expect < 0.05


def test_sample_budget(report_and_dir):
    report, song_dir = report_and_dir
    wavs = list((song_dir / "samples").glob("*.wav"))
    assert 1 <= len(wavs) <= 6
    assert report["n_samples"] == len(wavs)


def test_lanes_midi_consistency(report_and_dir):
    """lanes.json 的 pitch/文件/键位三方一致，chart.mid 可解析且 pitch 都有 lane。"""
    _, song_dir = report_and_dir
    lanes = json.loads((song_dir / "lanes.json").read_text())
    lane_pitches = set()
    for lane in lanes["lanes"]:
        assert (song_dir / lane["sample"]).exists()
        lane_pitches.add(lane["pitch"])
    pm = pretty_midi.PrettyMIDI(str(song_dir / "chart.mid"))
    midi_pitches = {n.pitch for n in pm.instruments[0].notes}
    assert midi_pitches <= lane_pitches
    assert all(n.start < lanes["loop_seconds"] for n in pm.instruments[0].notes)


def test_oneshots_clean(report_and_dir):
    """one-shot 无截断音头（开头即有能量）且尾部安静。"""
    _, song_dir = report_and_dir
    for wav in (song_dir / "samples").glob("*.wav"):
        data, sr = sf.read(wav, always_2d=True)
        mono = np.abs(data).mean(axis=1)
        assert mono.max() > 0.01, f"{wav.name} 是静音"
        tail = mono[-int(0.002 * sr):]
        assert tail.max() < 0.1, f"{wav.name} 尾部未衰减"
