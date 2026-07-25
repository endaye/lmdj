import json

from lmdj_audio_worker.materials.timing import TimingAnalyzer, load_timing

from .helpers import write_fixture_audio


def test_timing_analyzer_writes_aligned_canonical_artifact(tmp_path):
    source, _ = write_fixture_audio(tmp_path)
    path = tmp_path / "timing.json"
    timing = TimingAnalyzer().analyze(source, path)

    assert 60 <= timing.bpm <= 180
    assert timing.beats_per_bar == 4
    assert timing.grid_per_beat == 4
    assert timing.length_steps % 16 == 0
    assert len(timing.grid) >= timing.length_steps + 1
    assert load_timing(path) == timing


def test_timing_output_is_byte_deterministic(tmp_path):
    source, _ = write_fixture_audio(tmp_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    analyzer = TimingAnalyzer()
    assert analyzer.analyze(source, first) == analyzer.analyze(source, second)
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text())["schema"] == "lmdj.timing.v1"
