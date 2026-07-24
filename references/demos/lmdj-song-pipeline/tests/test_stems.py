import random
import sys
import types
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import pytest

from song_pipeline import stems


def _install_fake_apply_model(monkeypatch, apply_model) -> None:
    demucs = types.ModuleType("demucs")
    demucs_apply = types.ModuleType("demucs.apply")
    demucs_apply.apply_model = apply_model
    monkeypatch.setitem(sys.modules, "demucs", demucs)
    monkeypatch.setitem(sys.modules, "demucs.apply", demucs_apply)


def test_deterministic_apply_uses_audio_content_seed_and_restores_random_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.wav"
    same_bytes_elsewhere = tmp_path / "nested" / "second.wav"
    different = tmp_path / "different.wav"
    first.write_bytes(b"same audio bytes")
    same_bytes_elsewhere.parent.mkdir()
    same_bytes_elsewhere.write_bytes(first.read_bytes())
    different.write_bytes(b"different audio bytes")

    shifts: list[int] = []
    _install_fake_apply_model(
        monkeypatch,
        lambda *args, **kwargs: shifts.append(random.randint(0, 1_000_000)) or "sources",
    )
    seeds: list[int] = []
    original_seed = random.seed
    random.seed(8192)
    caller_state = random.getstate()

    def record_seed(value: int, *args, **kwargs) -> None:
        seeds.append(value)
        original_seed(value, *args, **kwargs)

    monkeypatch.setattr(stems.random, "seed", record_seed)

    assert stems._apply_model_deterministically(first, object(), object(), device="cpu") == "sources"
    assert random.getstate() == caller_state
    assert stems._apply_model_deterministically(
        same_bytes_elsewhere, object(), object(), device="cpu",
    ) == "sources"
    assert stems._apply_model_deterministically(different, object(), object(), device="cpu") == "sources"

    assert shifts[0] == shifts[1]
    assert seeds[0] == seeds[1]
    assert seeds[2] != seeds[0]


def test_separate_uses_deterministic_apply_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"audio input")
    model = types.SimpleNamespace(samplerate=44_100, audio_channels=2, sources=())
    monkeypatch.setattr(stems, "_get_model", lambda name: model)
    monkeypatch.setattr(stems, "_device", lambda: "cpu")

    demucs = types.ModuleType("demucs")
    demucs_audio = types.ModuleType("demucs.audio")

    class FakeAudioFile:
        def __init__(self, path: Path) -> None:
            assert path == audio

        def read(self, **kwargs) -> np.ndarray:
            return np.ones((2, 32), dtype=np.float32)

    demucs_audio.AudioFile = FakeAudioFile
    monkeypatch.setitem(sys.modules, "demucs", demucs)
    monkeypatch.setitem(sys.modules, "demucs.audio", demucs_audio)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(no_grad=lambda: nullcontext()))

    calls: list[tuple[Path, object, str]] = []

    def wrapper(audio_path: Path, received_model: object, wav: object, *, device: str):
        calls.append((audio_path, received_model, device))
        raise RuntimeError("wrapper called")

    monkeypatch.setattr(stems, "_apply_model_deterministically", wrapper)

    with pytest.raises(RuntimeError, match="wrapper called"):
        stems.separate(audio, tmp_path / "work", stems.PipelineConfig())

    assert calls == [(audio, model, "cpu")]
