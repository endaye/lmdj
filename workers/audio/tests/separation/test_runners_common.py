from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lmdj_audio_worker.separation.runners import common

SR = 44100


def make_stems(frames: int = SR) -> dict:
    rng = np.random.default_rng(1)
    return {k: rng.uniform(-0.5, 0.5, (frames, 2)).astype(np.float32)
            for k in ("drums", "bass", "vocals", "other")}


def test_runner_error_validates_category():
    err = common.RunnerError("boom", category="inference")
    assert err.category == "inference"
    with pytest.raises(ValueError):
        common.RunnerError("boom", category="mystery")


def test_write_canonical_stems_float_subtype(tmp_path):
    rel = common.write_canonical_stems(tmp_path, make_stems())
    assert rel["drums"] == "stems/drums.wav"
    info = sf.info(tmp_path / "stems" / "vocals.wav")
    assert info.subtype == "FLOAT" and info.samplerate == SR and info.channels == 2


def test_write_canonical_stems_rejects_missing_track(tmp_path):
    stems = make_stems()
    del stems["other"]
    with pytest.raises(common.RunnerError) as exc:
        common.write_canonical_stems(tmp_path, stems)
    assert exc.value.category == "invalid_stems"


def test_write_canonical_stems_rejects_mono(tmp_path):
    stems = make_stems()
    stems["bass"] = np.zeros((SR,), dtype=np.float32)
    with pytest.raises(common.RunnerError) as exc:
        common.write_canonical_stems(tmp_path, stems)
    assert exc.value.category == "invalid_stems"


def test_load_stereo_44k_roundtrip(tmp_path):
    data = make_stems()["drums"]
    sf.write(tmp_path / "in.wav", data, SR, subtype="FLOAT")
    loaded = common.load_stereo_44k(tmp_path / "in.wav")
    assert loaded.shape == data.shape and loaded.dtype == np.float32


def test_load_stereo_44k_rejects_wrong_rate(tmp_path):
    sf.write(tmp_path / "in.wav", np.zeros((100, 2), dtype=np.float32), 48000)
    with pytest.raises(common.RunnerError) as exc:
        common.load_stereo_44k(tmp_path / "in.wav")
    assert exc.value.category == "inference"


def _argv(tmp_path, ckpt_name="a" * 64):
    input_path = tmp_path / "input.wav"
    sf.write(input_path, np.zeros((SR, 2), dtype=np.float32), SR)
    ckpt = tmp_path / "htdemucs" / ckpt_name
    ckpt.mkdir(parents=True)
    return ["--input", str(input_path), "--output", str(tmp_path / "out"),
            "--device", "cpu", "--checkpoint-dir", str(ckpt), "--seed", "0"]


def test_main_success_writes_completed(tmp_path):
    def work(args):
        return common.RunnerOutput(
            stems=make_stems(), actual_device="cpu",
            performance={"model_load_seconds": 0.1, "inference_seconds": 0.2,
                         "wall_seconds": 0.3, "peak_rss_bytes": 1,
                         "peak_device_memory_bytes": 0})

    code = common.run_runner_main(
        _argv(tmp_path), runner_id="fake", family="demucs",
        runner_version="0.1.0", work=work)
    assert code == 0
    data = json.loads((tmp_path / "out" / "separation.json").read_text())
    assert data["status"] == "completed" and data["source"] == "runner"
    assert data["actual_device"] == "cpu"
    assert data["audio"]["duration_seconds"] == pytest.approx(1.0)
    assert (tmp_path / "out" / "stems" / "drums.wav").exists()


def test_main_runner_error_writes_failed_category(tmp_path):
    def work(args):
        raise common.RunnerError("no mps", category="unsupported_device")

    code = common.run_runner_main(
        _argv(tmp_path), runner_id="fake", family="demucs",
        runner_version="0.1.0", work=work)
    assert code == 1
    data = json.loads((tmp_path / "out" / "separation.json").read_text())
    assert data["status"] == "failed" and data["source"] == "runner"
    assert data["error"]["category"] == "unsupported_device"


def test_main_unexpected_exception_maps_inference(tmp_path):
    def work(args):
        raise ValueError("surprise")

    code = common.run_runner_main(
        _argv(tmp_path), runner_id="fake", family="demucs",
        runner_version="0.1.0", work=work)
    assert code == 1
    data = json.loads((tmp_path / "out" / "separation.json").read_text())
    assert data["error"]["category"] == "inference"
    assert "surprise" in data["error"]["stderr_tail"]


def test_main_memoryerror_maps_oom(tmp_path):
    def work(args):
        raise MemoryError()

    code = common.run_runner_main(
        _argv(tmp_path), runner_id="fake", family="demucs",
        runner_version="0.1.0", work=work)
    data = json.loads((tmp_path / "out" / "separation.json").read_text())
    assert data["error"]["category"] == "oom"


def test_main_bad_checkpoint_dir_name_maps_checksum(tmp_path):
    def work(args):  # pragma: no cover - 不应执行到
        raise AssertionError

    code = common.run_runner_main(
        _argv(tmp_path, ckpt_name="not-a-sha"), runner_id="fake",
        family="demucs", runner_version="0.1.0", work=work)
    assert code == 1
    data = json.loads((tmp_path / "out" / "separation.json").read_text())
    assert data["error"]["category"] == "checksum"
