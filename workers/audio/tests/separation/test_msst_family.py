from __future__ import annotations

from pathlib import Path

import pytest

from lmdj_audio_worker.separation.runners import _msst, scnet
from lmdj_audio_worker.separation.runners.common import RunnerError


def test_msst_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LMDJ_MSST_DIR", str(tmp_path / "custom"))
    assert _msst.msst_dir() == tmp_path / "custom"


def test_msst_dir_default_under_worker_root(monkeypatch):
    monkeypatch.delenv("LMDJ_MSST_DIR", raising=False)
    assert _msst.msst_dir().name == ".msst"
    assert _msst.msst_dir().parent.name == "audio"


def test_missing_clone_raises_with_hint(monkeypatch, tmp_path):
    monkeypatch.setenv("LMDJ_MSST_DIR", str(tmp_path / "nowhere"))

    class Args:
        input = tmp_path / "in.wav"
        output = tmp_path / "out"
        device = "cpu"
        checkpoint_dir = tmp_path / "ckpt"
        seed = 0

    with pytest.raises(RunnerError) as exc:
        _msst.msst_work(Args(), model_type="scnet",
                        config_path=tmp_path / "cfg.yaml",
                        artifact_name="a.ckpt",
                        setup_hint="scripts/dev.sh setup-sep-scnet")
    assert exc.value.category == "inference"
    assert "setup-sep-scnet" in str(exc.value)


def test_scnet_constants_unchanged():
    # 重构后薄壳的公开常量必须与 1A 验收版本一字不差
    assert scnet.RUNNER_ID == "scnet-large"
    assert scnet.FAMILY == "scnet"
    assert scnet.RUNNER_VERSION == "0.1.0"
    assert scnet.ARTIFACT == "SCNet-large_starrytong_fixed.ckpt"
    assert scnet.MODEL_TYPE == "scnet"
    assert scnet.CONFIG_PATH.name == "config_musdb18_scnet_large_starrytong.yaml"


def test_scnet_work_delegates_to_msst(monkeypatch):
    captured = {}

    def fake_msst_work(args, **kwargs):
        captured.update(kwargs)
        return "SENTINEL"

    monkeypatch.setattr(scnet, "msst_work", fake_msst_work)
    assert scnet._work(object()) == "SENTINEL"
    assert captured["model_type"] == "scnet"
    assert captured["artifact_name"] == scnet.ARTIFACT
    assert captured["config_path"] == scnet.CONFIG_PATH
    assert "setup-sep-scnet" in captured["setup_hint"]
