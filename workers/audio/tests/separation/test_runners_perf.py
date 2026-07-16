from __future__ import annotations

import sys
import time
import types

import pytest

from lmdj_audio_worker.separation.runners import common


def make_fake_torch(mps_available: bool, current=1000, driver=2000):
    torch = types.ModuleType("torch")
    torch.backends = types.SimpleNamespace(
        mps=types.SimpleNamespace(is_available=lambda: mps_available))
    calls = {"n": 0}

    def current_allocated_memory():
        calls["n"] += 1
        return current + calls["n"]          # 递增，峰值 = 最后一次

    torch.mps = types.SimpleNamespace(
        current_allocated_memory=current_allocated_memory,
        driver_allocated_memory=lambda: driver + calls["n"])
    return torch


def test_perf_tracker_phases_and_rss():
    tracker = common.PerfTracker()
    with tracker.phase("model_load"):
        time.sleep(0.01)
    with tracker.phase("inference"):
        time.sleep(0.01)
    snap = tracker.snapshot()
    assert snap["model_load_seconds"] > 0
    assert snap["inference_seconds"] > 0
    assert snap["wall_seconds"] >= snap["model_load_seconds"]
    assert snap["peak_rss_bytes"] > 1024 * 1024  # 进程 RSS 至少 1MB


def test_cpu_sampler_zeroes():
    sampler = common.DeviceMemorySampler("cpu")
    sampler.start()
    result = sampler.stop()
    assert result["peak_device_memory_bytes"] == 0
    assert result["peak_mps_current_allocated_bytes"] == 0
    assert result["sample_interval_ms"] == 100


def test_mps_sampler_records_peaks(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", make_fake_torch(True))
    sampler = common.DeviceMemorySampler("mps", interval_s=0.01)
    sampler.start()
    time.sleep(0.05)
    result = sampler.stop()
    assert result["peak_device_memory_bytes"] > 2000   # driver 侧
    assert result["peak_mps_current_allocated_bytes"] > 1000
    assert result["sample_interval_ms"] == 10


def test_resolve_device_mps_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", make_fake_torch(False))
    with pytest.raises(common.RunnerError) as exc:
        common.resolve_device("mps")
    assert exc.value.category == "unsupported_device"


def test_resolve_device_cpu_ok(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", make_fake_torch(False))
    assert common.resolve_device("cpu") == "cpu"
