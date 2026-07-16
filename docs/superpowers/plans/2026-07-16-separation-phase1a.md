# Separation Phase 1A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地前两个真实 separator runner——HT Demucs（`verified` baseline）与 SCNet-large（`experimental`）——registry 填入真实 checkpoint 条目，并在 Mac MPS 上完成 smoke 验收（含 MPS 内存采样算法，spec §5）。

**Architecture:** 每个 runner 是 `lmdj_audio_worker/separation/runners/` 下的一个模块，在**自己的专用 venv**（`.venv-sep-demucs` / `.venv-sep-scnet`）中以子进程执行（Phase 0 的 `protocol.run_separator` 驱动），共享 `runners/common.py` 的 scaffold（CLI 契约、canonical 落盘、失败 JSON 自写、性能与 MPS 内存采集）。SCNet 推理复用 MSST 框架（pinned commit clone，不是 pip 包）。主包 `dependencies` 保持 `[]`；torch 栈只进 runner venv。

**Tech Stack:** torch==2.12.1 / torchaudio==2.11.0（与 demo venv 同版）；demucs==4.0.1；MSST（ZFTurbo/Music-Source-Separation-Training，pinned commit）；soundfile / numpy==1.26.4。

**Spec:** `docs/superpowers/specs/2026-07-15-multi-separator-benchmark-design.md`（§5 runner 协议与 MPS 采样、§6 registry 与首批策略、§10 错误模型）。

**Base branch:** `main`（Phase 0 已合并，968b1818）。分支 `codex/feat-separation-phase1a`。

## 已核实的事实（plan 依据，2026-07-16 调研）

- **htdemucs checkpoint**：`https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th`；本机 torch-hub 缓存实测 SHA-256 = `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`（文件名后缀即 sha 前 8 位，交叉验证一致）。demucs 4.0.1 的 `remote/htdemucs.yaml` = `models: ['955717e8']`（单模型 bag）。代码与权重 license：MIT（adefossez/demucs）。
- **SCNet-large checkpoint**：选 **starrytong 训练的 fixed 版**（MUSDB test SDR 9.70，优于 9.32 的另一版）：`https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.9/SCNet-large_starrytong_fixed.ckpt`；配套 config `config_musdb18_scnet_large_starrytong.yaml`（同 release）。MSST 仓库与 starrytong/SCNet 仓库均为 MIT。SHA-256 实施时下载计算（Task 6）。
- **MSST 推理 API**：`utils/model_utils.py::demix(config, model, mix, device, model_type, pbar=False)` → `dict[str, np.ndarray]`（4-stem 时）。MSST 不是 pip 包 → pinned-commit clone 到 gitignored 目录。
- 本机 `torch.backends.mps.is_available() == True`。

## Global Constraints

- `workers/audio/pyproject.toml` 的 `[project] dependencies` 必须保持 `[]`；torch/demucs/MSST 栈只进 runner 专用 venv。
- **不允许静默设备 fallback**（spec §2/§10）：请求 mps 而不可用 → 失败记录 `unsupported_device`，绝不悄悄转 CPU。
- canonical stems 硬约束（spec §5）：四轨齐全、44100 Hz、双声道、32-bit float、与输入时长误差 ≤1 sample、无 NaN/Inf、峰值 ≤8.0、保存模型原始幅度（不做逐轨归一化/整数 PCM clipping）。
- MPS 内存采集（spec §5）：100 ms 后台采样 `torch.mps.current_allocated_memory()` 与 `driver_allocated_memory()`；`peak_device_memory_bytes` = driver 侧最大值；两个原始最大值与采样间隔都写入 `performance`；CPU 设备固定写 0。
- 失败记录 runner 自写（可捕获异常，`source: "runner"`）；类别取 spec §10 的统一词表。
- registry 条目必须完整：来源 URL + 不可变 revision、artifact SHA-256、license（code+weights）、stems/采样率/声道、devices、inference 推理配置、env_lock_sha256、status。htdemucs 初始 `verified`（spec §6 首批策略表），scnet-large 初始 `experimental`。
- registry `command` 里的 venv 路径是 repo-root 相对路径——**命令必须从 repo root 执行**（`scripts/dev.sh` 保证；Phase 1C orchestrator 需继续保证）。
- `references/demos/` 冻结不动。commit 符合 Conventional Commits v1.0.0。
- MSST clone 是外部代码：只读使用（sys.path 导入），不修改其源码；修 bug 需求出现时升级 pinned commit 而不是打补丁。

## 准备

```bash
cd workers/audio
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -e ../../packages/core-models -e ../../packages/patchify
.venv/bin/pip install -e ".[test,pfs]" -c config/parity-constraints.txt
.venv/bin/python -m pytest tests/ -q   # 基线 101 tests 全绿
```

---

### Task 1: `runners/common.py`（一）— scaffold、canonical 落盘、失败自写

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/runners/__init__.py`
- Create: `workers/audio/lmdj_audio_worker/separation/runners/common.py`
- Test: `workers/audio/tests/separation/test_runners_common.py`

**Interfaces:**
- Consumes: Phase 0 的 `contract`（`SeparationResult`/`SeparatorInfo`/`write_result`/`CANONICAL_STEMS`/`ERROR_CATEGORIES`）、`cache.sha256_file`
- Produces（Task 2–5 依赖）：
  - `class RunnerError(Exception)`，属性 `.category: str`（构造时校验属于 `ERROR_CATEGORIES`）
  - `CANONICAL_SR = 44100`
  - `write_canonical_stems(out_dir: Path, stems: dict[str, np.ndarray]) -> dict[str, str]`：入参 `(frames, 2)` float32，按 `stems/<name>.wav` 写 FLOAT subtype，返回相对路径 dict；缺轨/形状错/dtype 错抛 `RunnerError("invalid_stems")`
  - `load_stereo_44k(path: Path) -> np.ndarray`：soundfile 读取 → `(frames, 2)` float32；采样率非 44100 或读取失败抛 `RunnerError("inference")`（scnet 用；demucs 用自家 AudioFile）
  - `@dataclass RunnerOutput(stems: dict, actual_device: str, performance: dict)`
  - `run_runner_main(argv, *, runner_id: str, family: str, runner_version: str, work: Callable[[argparse.Namespace], RunnerOutput]) -> int`：解析 `--input --output --device --checkpoint-dir --seed`；成功 → 写 completed `separation.json`（`source="runner"`，`input_sha256` 用 `cache.sha256_file`，`checkpoint_sha256` 取 `Path(checkpoint_dir).name`（cache 布局 `<id>/<sha256>/`，非 64 位 hex 时抛 `RunnerError("checksum")`），`audio` 由 stems 帧数推导）→ exit 0；`RunnerError` → 写 failed（对应类别）→ exit 1；其他异常 → 写 failed(`inference`) → exit 1；`MemoryError` → `oom`

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/separation/test_runners_common.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_runners_common.py -q
```

Expected: FAIL（module 不存在）。

- [ ] **Step 3: Write the implementation**

`workers/audio/lmdj_audio_worker/separation/runners/__init__.py`：

```python
"""Separator runners（spec §4/§5）：每个模块在自己的专用 venv 中以子进程执行。"""
```

`workers/audio/lmdj_audio_worker/separation/runners/common.py`：

```python
"""Runner 侧共享 scaffold：CLI 契约、canonical 落盘、失败 JSON 自写（spec §5）。

本模块运行在 runner 专用 venv 中；除性能采集（Task 2）的懒加载 torch 外，
只依赖 numpy/soundfile + 主包 contract/cache。
"""
from __future__ import annotations

import argparse
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..cache import sha256_file
from ..contract import (CANONICAL_STEMS, ERROR_CATEGORIES, SeparationError,
                        SeparationResult, SeparatorInfo, write_result)

CANONICAL_SR = 44100
STDERR_TAIL_CHARS = 2000


class RunnerError(Exception):
    def __init__(self, message: str, category: str) -> None:
        if category not in ERROR_CATEGORIES:
            raise ValueError(f"未知错误类别 {category!r}，必须属于 {ERROR_CATEGORIES}")
        super().__init__(message)
        self.category = category


@dataclass
class RunnerOutput:
    stems: dict
    actual_device: str
    performance: dict


def write_canonical_stems(out_dir: Path, stems: dict) -> dict[str, str]:
    import numpy as np
    import soundfile as sf

    missing = [k for k in CANONICAL_STEMS if k not in stems]
    if missing:
        raise RunnerError(f"缺少 canonical 轨 {missing}", category="invalid_stems")
    rel: dict[str, str] = {}
    for name in CANONICAL_STEMS:
        data = stems[name]
        if data.ndim != 2 or data.shape[1] != 2 or data.dtype != np.float32:
            raise RunnerError(
                f"{name}: 需要 (frames, 2) float32，收到 shape={data.shape} "
                f"dtype={data.dtype}", category="invalid_stems")
        path = out_dir / "stems" / f"{name}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, data, CANONICAL_SR, subtype="FLOAT")
        rel[name] = f"stems/{name}.wav"
    return rel


def load_stereo_44k(path: Path) -> "np.ndarray":
    import numpy as np  # noqa: F401 —— 注解用
    import soundfile as sf

    try:
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:
        raise RunnerError(f"无法读取输入 {path}: {exc}", category="inference") from exc
    if sr != CANONICAL_SR:
        raise RunnerError(
            f"输入采样率 {sr}，v1 runner 只接受 {CANONICAL_SR}", category="inference")
    if data.shape[1] == 1:
        data = data.repeat(2, axis=1)
    return data


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser("separator-runner")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", required=True, choices=("cpu", "mps"))
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args(argv)


def _checkpoint_sha(checkpoint_dir: Path) -> str:
    name = Path(checkpoint_dir).name
    if len(name) == 64 and all(c in "0123456789abcdef" for c in name):
        return name
    raise RunnerError(
        f"checkpoint_dir 目录名不是 SHA-256（cache 布局应为 <id>/<sha256>/）: {name}",
        category="checksum")


def run_runner_main(argv: list[str] | None, *, runner_id: str, family: str,
                    runner_version: str,
                    work: Callable[[argparse.Namespace], RunnerOutput]) -> int:
    args = _parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    input_sha = sha256_file(args.input)
    separator = SeparatorInfo(id=runner_id, family=family,
                              checkpoint_sha256="0" * 64,
                              runner_version=runner_version)

    def fail(category: str, message: str) -> int:
        result = SeparationResult(
            status="failed", source="runner", input_sha256=input_sha,
            separator=separator, requested_device=args.device,
            error=SeparationError(
                category=category, exit_code=None, stage="runner",
                stderr_tail=message[-STDERR_TAIL_CHARS:], elapsed_seconds=0.0))
        write_result(args.output / "separation.json", result)
        return 1

    try:
        separator = SeparatorInfo(id=runner_id, family=family,
                                  checkpoint_sha256=_checkpoint_sha(args.checkpoint_dir),
                                  runner_version=runner_version)
        output = work(args)
        rel = write_canonical_stems(args.output, output.stems)
        frames = len(output.stems["drums"])
        result = SeparationResult(
            status="completed", source="runner", input_sha256=input_sha,
            separator=separator, requested_device=args.device,
            actual_device=output.actual_device, stems=rel,
            audio={"sample_rate": CANONICAL_SR, "channels": 2,
                   "duration_seconds": round(frames / CANONICAL_SR, 6)},
            performance=output.performance)
        write_result(args.output / "separation.json", result)
        return 0
    except RunnerError as exc:
        return fail(exc.category, str(exc))
    except MemoryError:
        return fail("oom", "MemoryError")
    except Exception:  # noqa: BLE001 —— 任何未预期异常都必须落盘为失败记录
        return fail("inference", traceback.format_exc())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_runners_common.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/runners workers/audio/tests/separation/test_runners_common.py
git commit -m "feat(runners): add shared runner scaffold with canonical output and self-written failures"
```

---

### Task 2: `runners/common.py`（二）— PerfTracker、MPS 内存采样、设备解析

**Files:**
- Modify: `workers/audio/lmdj_audio_worker/separation/runners/common.py`（追加）
- Test: `workers/audio/tests/separation/test_runners_perf.py`

**Interfaces:**
- Consumes: Task 1 的 `RunnerError`
- Produces（Task 3/5 依赖）：
  - `class PerfTracker`：`phase(name)` contextmanager（累计 `model_load_seconds` / `inference_seconds`）；`snapshot() -> dict` 补 `wall_seconds`（自构造起）与 `peak_rss_bytes`（`resource.getrusage`，macOS 为字节、Linux 为 KB——归一化为字节）
  - `class DeviceMemorySampler(device: str, interval_s: float = 0.1)`：`start()` / `stop() -> dict`；mps → 后台线程按 interval 采样 `torch.mps.current_allocated_memory()` 与 `torch.mps.driver_allocated_memory()`，返回 `{"peak_device_memory_bytes": <driver 最大值>, "peak_mps_current_allocated_bytes": <current 最大值>, "sample_interval_ms": ...}`；cpu → 全 0（同样带 `sample_interval_ms`）
  - `resolve_device(requested: str) -> str`：`"mps"` 且 `torch.backends.mps.is_available()` 为假 → `RunnerError("unsupported_device")`；返回 requested（懒 import torch）

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/separation/test_runners_perf.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_runners_perf.py -q
```

Expected: FAIL（`AttributeError: PerfTracker`）。

- [ ] **Step 3: Write the implementation**

追加到 `common.py` 末尾：

```python
import contextlib
import resource
import sys as _sys
import threading
import time as _time


class PerfTracker:
    """model_load / inference 分段计时 + wall + peak RSS（spec §5 performance）。"""

    def __init__(self) -> None:
        self._t0 = _time.monotonic()
        self._phases: dict[str, float] = {}

    @contextlib.contextmanager
    def phase(self, name: str):
        start = _time.monotonic()
        try:
            yield
        finally:
            self._phases[name] = self._phases.get(name, 0.0) + (
                _time.monotonic() - start)

    def snapshot(self) -> dict:
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_rss = ru if _sys.platform == "darwin" else ru * 1024  # Linux 为 KB
        return {
            "model_load_seconds": round(self._phases.get("model_load", 0.0), 3),
            "inference_seconds": round(self._phases.get("inference", 0.0), 3),
            "wall_seconds": round(_time.monotonic() - self._t0, 3),
            "peak_rss_bytes": int(peak_rss),
        }


class DeviceMemorySampler:
    """MPS 设备内存采样（spec §5）：100ms 采样 current/driver，峰值取 driver。

    PyTorch MPS 无 peak API；采样式采集会低估真峰值，属已知固有误差——
    门槛判定统一用同一算法即可比。CPU 设备固定写 0。
    """

    def __init__(self, device: str, interval_s: float = 0.1) -> None:
        self.device = device
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._peak_current = 0
        self._peak_driver = 0

    def _sample_loop(self) -> None:
        import torch
        while not self._stop.is_set():
            self._peak_current = max(
                self._peak_current, int(torch.mps.current_allocated_memory()))
            self._peak_driver = max(
                self._peak_driver, int(torch.mps.driver_allocated_memory()))
            self._stop.wait(self.interval_s)

    def start(self) -> None:
        if self.device != "mps":
            return
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=5)
        return {
            "peak_device_memory_bytes": self._peak_driver,
            "peak_mps_current_allocated_bytes": self._peak_current,
            "sample_interval_ms": int(self.interval_s * 1000),
        }


def resolve_device(requested: str) -> str:
    if requested == "mps":
        import torch
        if not torch.backends.mps.is_available():
            raise RunnerError(
                "请求 mps 但 torch.backends.mps 不可用（不允许静默转 CPU，spec §10）",
                category="unsupported_device")
    return requested
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/ -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/runners/common.py \
        workers/audio/tests/separation/test_runners_perf.py
git commit -m "feat(runners): add perf tracker, mps memory sampler and strict device resolve"
```

---

### Task 3: DemucsRunner + venv

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/runners/demucs.py`
- Create: `workers/audio/config/runner-demucs-constraints.txt`
- Modify: `scripts/dev.sh`（`setup-sep-demucs` 命令 + usage + case）

**Interfaces:**
- Consumes: Task 1/2 的 `common`（`run_runner_main`/`RunnerOutput`/`PerfTracker`/`DeviceMemorySampler`/`resolve_device`/`RunnerError`/`CANONICAL_SR`）
- Produces:
  - CLI：`.venv-sep-demucs/bin/python -m lmdj_audio_worker.separation.runners.demucs --input F --output D --device cpu|mps --checkpoint-dir D --seed N`
  - 常量 `RUNNER_ID = "htdemucs"`、`FAMILY = "demucs"`、`RUNNER_VERSION = "0.1.0"`、`ARTIFACT = "955717e8-8726e21a.th"`、`INFERENCE = {"shifts": 0, "split": True, "overlap": 0.25}`（Task 6 registry 条目照抄）

- [ ] **Step 1: 写 constraints 与 dev.sh 命令**

`workers/audio/config/runner-demucs-constraints.txt`：

```text
# DemucsRunner venv 版本锁（与 demo venv 同版 torch 栈，2026-07-16 基准）。
# env_lock_sha256（registry htdemucs 条目）= 本文件的 SHA-256。
demucs==4.0.1
torch==2.12.1
torchaudio==2.11.0
numpy==1.26.4
soundfile==0.14.0
einops==0.8.2
julius==0.2.8
```

`scripts/dev.sh`：变量区追加 `SEP_DEMUCS_VENV="$WORKER/.venv-sep-demucs"`；usage 追加一行 `setup-sep-demucs   创建 HT Demucs runner venv（torch 栈，constraints 锁版本）`；`cmd_setup_pfs` 之后追加：

```bash
cmd_setup_sep_demucs() {
  if [ ! -x "$SEP_DEMUCS_VENV/bin/python" ]; then
    echo "==> 创建 demucs runner venv"
    python3 -m venv "$SEP_DEMUCS_VENV"
  fi
  "$SEP_DEMUCS_VENV/bin/pip" -q install -e "$ROOT/packages/core-models" -c "$WORKER/config/runner-demucs-constraints.txt"
  "$SEP_DEMUCS_VENV/bin/pip" -q install -e "$ROOT/packages/patchify" -c "$WORKER/config/runner-demucs-constraints.txt"
  "$SEP_DEMUCS_VENV/bin/pip" -q install -e "$WORKER" demucs soundfile -c "$WORKER/config/runner-demucs-constraints.txt"
  echo "==> demucs runner venv 就绪"
}
```

case 表加 `setup-sep-demucs) cmd_setup_sep_demucs ;;`。

- [ ] **Step 2: Write the runner**

```python
# workers/audio/lmdj_audio_worker/separation/runners/demucs.py
"""HT Demucs runner：本地 checkpoint -> canonical four stems（spec §5）。

在 .venv-sep-demucs 中以子进程执行；权重从 cache 的 checkpoint_dir 加载，
不触发 demucs 自身的远程下载。归一化沿用 demo stems.py 的 (x-mean)/std 前处理
（推理后还原），canonical 输出保存模型原始幅度。
"""
from __future__ import annotations

import sys
from pathlib import Path

from .common import (CANONICAL_SR, DeviceMemorySampler, PerfTracker,
                     RunnerError, RunnerOutput, resolve_device,
                     run_runner_main)

RUNNER_ID = "htdemucs"
FAMILY = "demucs"
RUNNER_VERSION = "0.1.0"
ARTIFACT = "955717e8-8726e21a.th"
# registry htdemucs 条目的 inference 字段照抄这里（改动需 bump RUNNER_VERSION）
INFERENCE = {"shifts": 0, "split": True, "overlap": 0.25}


def _work(args) -> RunnerOutput:
    import torch
    from demucs.apply import apply_model
    from demucs.audio import AudioFile
    from demucs.states import load_model

    device = resolve_device(args.device)
    torch.manual_seed(args.seed)
    tracker = PerfTracker()

    artifact = Path(args.checkpoint_dir) / ARTIFACT
    if not artifact.exists():
        raise RunnerError(f"checkpoint 缺失: {artifact}", category="checksum")
    with tracker.phase("model_load"):
        model = load_model(artifact)
        model.to(device)
        model.eval()
    if model.samplerate != CANONICAL_SR:
        raise RunnerError(
            f"模型采样率 {model.samplerate} != {CANONICAL_SR}", category="invalid_stems")

    wav = AudioFile(args.input).read(
        streams=0, samplerate=model.samplerate, channels=model.audio_channels)
    ref = wav.mean(0)
    wav_norm = (wav - ref.mean()) / (ref.std() + 1e-8)

    sampler = DeviceMemorySampler(device)
    sampler.start()
    with tracker.phase("inference"), torch.no_grad():
        sources = apply_model(
            model, wav_norm[None], device=device, shifts=INFERENCE["shifts"],
            split=INFERENCE["split"], overlap=INFERENCE["overlap"],
            progress=False)[0]
    memory = sampler.stop()
    sources = sources * (ref.std() + 1e-8) + ref.mean()

    stems = {name: src.cpu().numpy().T.astype("float32")
             for name, src in zip(model.sources, sources)}
    performance = tracker.snapshot() | memory
    return RunnerOutput(stems=stems, actual_device=device,
                        performance=performance)


def main(argv: list[str] | None = None) -> int:
    return run_runner_main(argv, runner_id=RUNNER_ID, family=FAMILY,
                           runner_version=RUNNER_VERSION, work=_work)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 建 venv 并做 import + CLI smoke**

```bash
bash -n scripts/dev.sh && scripts/dev.sh setup-sep-demucs   # torch 下载，数分钟
workers/audio/.venv-sep-demucs/bin/python -c "from lmdj_audio_worker.separation.runners import demucs; print('import ok')"
workers/audio/.venv-sep-demucs/bin/python -m lmdj_audio_worker.separation.runners.demucs --help
```

Expected: `import ok`；`--help` exit 0。真实分离在 Task 8 验收（需要先有 registry 条目喂 checkpoint）。

- [ ] **Step 4: 全量单测无回归**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q
```

Expected: 全绿（主测试 venv 无 torch/demucs——`demucs.py` 顶层不 import torch，全部在 `_work` 内懒加载；若 collection 报错说明有泄漏，修正之）。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/runners/demucs.py \
        workers/audio/config/runner-demucs-constraints.txt scripts/dev.sh
git commit -m "feat(runners): add htdemucs runner with pinned venv"
```

---

### Task 4: SCNet 基建 — MSST pinned clone + venv + vendored config

**Files:**
- Create: `workers/audio/config/msst.lock`
- Create: `workers/audio/config/scnet/config_musdb18_scnet_large_starrytong.yaml`（从 release 下载后入库）
- Create: `workers/audio/config/runner-scnet-constraints.txt`
- Modify: `scripts/dev.sh`（`setup-sep-scnet` + usage + case）
- Modify: `.gitignore`（`workers/audio/.msst`、`workers/audio/.venv-sep-*`）

**Interfaces:**
- Produces: `.venv-sep-scnet` venv；MSST 源码 clone 于 `workers/audio/.msst`（gitignored，pinned commit）；Task 5 的 runner 通过 `sys.path` 导入它

- [ ] **Step 1: 解析并锁定 MSST commit，写 msst.lock**

```bash
git ls-remote https://github.com/ZFTurbo/Music-Source-Separation-Training.git HEAD
```

把输出的 commit hash 写入 `workers/audio/config/msst.lock`（格式如下，`<commit>` 用真实值替换）：

```text
# MSST（SCNet 推理框架）pinned clone 锁。env_lock_sha256（registry scnet-large 条目）= 本文件的 SHA-256。
# 升级方式：改 commit 重跑 setup-sep-scnet + Task 8 验收；不得在 clone 内打补丁。
url=https://github.com/ZFTurbo/Music-Source-Separation-Training.git
commit=<commit>
```

- [ ] **Step 2: 下载并入库 SCNet-large config**

```bash
curl -fsSL --create-dirs -o workers/audio/config/scnet/config_musdb18_scnet_large_starrytong.yaml \
  https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.9/config_musdb18_scnet_large_starrytong.yaml
head -20 workers/audio/config/scnet/config_musdb18_scnet_large_starrytong.yaml
shasum -a 256 workers/audio/config/scnet/config_musdb18_scnet_large_starrytong.yaml   # 记录，Task 6 写进 registry inference.config_sha256
```

确认 yaml 含 `audio:`（sample_rate 44100）与 `model:` 段、instruments 为 4-stem。MSST 与该 config 均为 MIT，可入库。

- [ ] **Step 3: constraints + dev.sh 命令**

`workers/audio/config/runner-scnet-constraints.txt` 初始内容（实施中按 import 失败逐个补齐 MSST 推理路径的最小依赖并 pin 精确版本——**不要**整装 MSST 的 requirements.txt，那是训练全家桶）：

```text
# SCNetRunner venv 版本锁（MSST 推理最小依赖集，2026-07-16 基准）。
# 起始集合；实施中按 pinned commit 的实际 import 需要增删，全部精确 pin。
torch==2.12.1
numpy==1.26.4
soundfile==0.14.0
einops==0.8.2
ml_collections==1.1.0
omegaconf==2.3.0
pyyaml==6.0.2
tqdm==4.67.1
```

`scripts/dev.sh`：变量区追加 `SEP_SCNET_VENV="$WORKER/.venv-sep-scnet"`、`MSST_DIR="$WORKER/.msst"`；usage 追加 `setup-sep-scnet    创建 SCNet runner venv + MSST pinned clone`；新增：

```bash
cmd_setup_sep_scnet() {
  local lock="$WORKER/config/msst.lock"
  local url commit
  url=$(grep '^url=' "$lock" | cut -d= -f2-)
  commit=$(grep '^commit=' "$lock" | cut -d= -f2-)
  if [ ! -d "$MSST_DIR/.git" ]; then
    echo "==> clone MSST @ ${commit}"
    git clone --no-checkout "$url" "$MSST_DIR"
  fi
  (cd "$MSST_DIR" && git fetch -q origin "$commit" && git checkout -q "$commit")
  if [ ! -x "$SEP_SCNET_VENV/bin/python" ]; then
    echo "==> 创建 scnet runner venv"
    python3 -m venv "$SEP_SCNET_VENV"
  fi
  "$SEP_SCNET_VENV/bin/pip" -q install -e "$ROOT/packages/core-models" -c "$WORKER/config/runner-scnet-constraints.txt"
  "$SEP_SCNET_VENV/bin/pip" -q install -e "$ROOT/packages/patchify" -c "$WORKER/config/runner-scnet-constraints.txt"
  # 安装 constraints 里列出的全部包（constraints 同时作为需求清单与版本锁）
  grep -v '^#' "$WORKER/config/runner-scnet-constraints.txt" | sed '/^$/d' > /tmp/scnet-reqs.txt
  "$SEP_SCNET_VENV/bin/pip" -q install -e "$WORKER" -r /tmp/scnet-reqs.txt
  echo "==> scnet runner venv 就绪（MSST @ ${commit}）"
}
```

case 表加 `setup-sep-scnet) cmd_setup_sep_scnet ;;`。`.gitignore` 追加：

```text
workers/audio/.msst
workers/audio/.venv-sep-*
```

- [ ] **Step 4: 建 venv 并验证 MSST 可导入**

```bash
bash -n scripts/dev.sh && scripts/dev.sh setup-sep-scnet
workers/audio/.venv-sep-scnet/bin/python - <<'EOF'
import sys
sys.path.insert(0, "workers/audio/.msst")
from utils.model_utils import demix          # pinned commit 的真实 API；若路径/名字不同，记录实情并调整 Task 5
print("msst import ok")
EOF
```

若 import 失败：按报错补 constraints 依赖（精确 pin）重装；若 `demix` 位置/签名与调研（`utils/model_utils.py::demix(config, model, mix, device, model_type, pbar)`）不符，以 pinned commit 源码为准，把差异记入 task report——Task 5 的代码按真实 API 调整。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/config/msst.lock workers/audio/config/scnet \
        workers/audio/config/runner-scnet-constraints.txt scripts/dev.sh .gitignore
git commit -m "feat(runners): pin msst clone and scnet runner environment"
```

---

### Task 5: SCNetRunner

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/runners/scnet.py`

**Interfaces:**
- Consumes: Task 1/2 `common`；Task 4 的 MSST clone（`utils.model_utils.demix`、`utils.settings.get_model_from_config` —— 以 pinned commit 真实 API 为准）与 vendored config
- Produces: CLI 同 demucs runner；常量 `RUNNER_ID = "scnet-large"`、`FAMILY = "scnet"`、`RUNNER_VERSION = "0.1.0"`、`ARTIFACT = "SCNet-large_starrytong_fixed.ckpt"`、`MODEL_TYPE = "scnet"`

- [ ] **Step 1: Write the runner**

以下代码基于调研的 MSST API；实施时**必须对照 `.msst` pinned commit 的真实源码核对**（`utils/settings.py` 的 config/model 加载函数名、`demix` 返回的 stem 名与数组形状、checkpoint state_dict 的包裹层），差异照实调整并记入 report：

```python
# workers/audio/lmdj_audio_worker/separation/runners/scnet.py
"""SCNet-large runner：MSST(pinned clone) demix -> canonical four stems（spec §5）。

MSST 不是 pip 包：sys.path 注入 workers/audio/.msst（LMDJ_MSST_DIR 可覆盖）。
只读使用，不修改其源码；API 以 config/msst.lock 的 commit 为准。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .common import (CANONICAL_SR, DeviceMemorySampler, PerfTracker,
                     RunnerError, RunnerOutput, load_stereo_44k,
                     resolve_device, run_runner_main)

RUNNER_ID = "scnet-large"
FAMILY = "scnet"
RUNNER_VERSION = "0.1.0"
ARTIFACT = "SCNet-large_starrytong_fixed.ckpt"
MODEL_TYPE = "scnet"
_WORKER_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = _WORKER_ROOT / "config" / "scnet" / "config_musdb18_scnet_large_starrytong.yaml"
_CANONICAL_FROM_MSST = {"drums": "drums", "bass": "bass",
                        "vocals": "vocals", "other": "other"}


def _msst_dir() -> Path:
    return Path(os.environ.get("LMDJ_MSST_DIR", _WORKER_ROOT / ".msst"))


def _work(args) -> RunnerOutput:
    msst = _msst_dir()
    if not (msst / "utils").exists():
        raise RunnerError(
            f"MSST clone 缺失: {msst} — 先运行 scripts/dev.sh setup-sep-scnet",
            category="inference")
    sys.path.insert(0, str(msst))
    import torch
    from utils.model_utils import demix
    from utils.settings import get_model_from_config  # pinned commit 核对

    device = resolve_device(args.device)
    torch.manual_seed(args.seed)
    tracker = PerfTracker()

    artifact = Path(args.checkpoint_dir) / ARTIFACT
    if not artifact.exists():
        raise RunnerError(f"checkpoint 缺失: {artifact}", category="checksum")
    with tracker.phase("model_load"):
        model, config = get_model_from_config(MODEL_TYPE, str(CONFIG_PATH))
        state = torch.load(artifact, map_location="cpu", weights_only=False)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state)
        model.to(device)
        model.eval()

    wav = load_stereo_44k(args.input)          # (frames, 2) float32, 44.1k
    mix = wav.T                                # MSST demix 期望 (2, frames)

    sampler = DeviceMemorySampler(device)
    sampler.start()
    with tracker.phase("inference"), torch.no_grad():
        separated = demix(config, model, mix, torch.device(device),
                          model_type=MODEL_TYPE, pbar=False)
    memory = sampler.stop()

    stems = {}
    for canonical, msst_name in _CANONICAL_FROM_MSST.items():
        if msst_name not in separated:
            raise RunnerError(
                f"MSST 输出缺少 {msst_name}（收到 {sorted(separated)}）",
                category="invalid_stems")
        arr = separated[msst_name]
        if arr.ndim == 2 and arr.shape[0] == 2:   # (2, frames) -> (frames, 2)
            arr = arr.T
        stems[canonical] = arr.astype("float32")
    performance = tracker.snapshot() | memory
    return RunnerOutput(stems=stems, actual_device=device,
                        performance=performance)


def main(argv: list[str] | None = None) -> int:
    return run_runner_main(argv, runner_id=RUNNER_ID, family=FAMILY,
                           runner_version=RUNNER_VERSION, work=_work)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: import + CLI smoke（scnet venv）**

```bash
workers/audio/.venv-sep-scnet/bin/python -m lmdj_audio_worker.separation.runners.scnet --help
```

Expected: exit 0。真实分离在 Task 8 验收。

- [ ] **Step 3: 主测试 venv 全量无回归**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q
```

- [ ] **Step 4: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/runners/scnet.py
git commit -m "feat(runners): add scnet-large runner via pinned msst demix"
```

---

### Task 6: registry 真实条目

**Files:**
- Modify: `workers/audio/config/separators.json`
- Modify: `workers/audio/tests/separation/test_registry.py`（更新 shipped-file 测试）

**Interfaces:**
- Consumes: Task 3/5 的常量（ID/family/ARTIFACT/INFERENCE）、Task 4 的 lock/config 文件
- Produces: registry 两个条目——`htdemucs`（`verified`，spec §6 首批策略表的 baseline）、`scnet-large`（`experimental`）

- [ ] **Step 1: 计算缺失的 SHA-256**

```bash
# scnet checkpoint（数百 MB，下载一次）
curl -fsSL -o /tmp/scnet-large.ckpt \
  https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.9/SCNet-large_starrytong_fixed.ckpt
shasum -a 256 /tmp/scnet-large.ckpt
# env locks 与 vendored config
shasum -a 256 workers/audio/config/runner-demucs-constraints.txt \
              workers/audio/config/msst.lock \
              workers/audio/config/scnet/config_musdb18_scnet_large_starrytong.yaml
```

- [ ] **Step 2: 写入两个条目**

`workers/audio/config/separators.json`（`<...sha...>` 用 Step 1 真实值替换；htdemucs artifact sha 已核实为下方值）：

```json
{
  "schema_version": "lmdj.separators.v1",
  "separators": [
    {
      "id": "htdemucs",
      "family": "demucs",
      "runner": "demucs",
      "command": ["workers/audio/.venv-sep-demucs/bin/python", "-m",
                  "lmdj_audio_worker.separation.runners.demucs",
                  "--input", "{input}", "--output", "{output_dir}",
                  "--device", "{device}", "--checkpoint-dir", "{checkpoint_dir}",
                  "--seed", "{seed}"],
      "source": {"url": "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th",
                 "revision": "hybrid_transformer/955717e8 (demucs 4.0.1 remote)"},
      "artifact_sha256": "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4",
      "license": {"code": "MIT (adefossez/demucs)", "weights": "MIT (adefossez/demucs)"},
      "stems": ["drums", "bass", "other", "vocals"],
      "sample_rate": 44100,
      "channels": 2,
      "devices": ["cpu", "mps"],
      "inference": {"shifts": 0, "split": true, "overlap": 0.25},
      "env_lock_sha256": "<sha256 of runner-demucs-constraints.txt>",
      "status": "verified"
    },
    {
      "id": "scnet-large",
      "family": "scnet",
      "runner": "scnet",
      "command": ["workers/audio/.venv-sep-scnet/bin/python", "-m",
                  "lmdj_audio_worker.separation.runners.scnet",
                  "--input", "{input}", "--output", "{output_dir}",
                  "--device", "{device}", "--checkpoint-dir", "{checkpoint_dir}",
                  "--seed", "{seed}"],
      "source": {"url": "https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.9/SCNet-large_starrytong_fixed.ckpt",
                 "revision": "MSST release v1.0.9 (trained by starrytong, MUSDB SDR 9.70)"},
      "artifact_sha256": "<sha256 of SCNet-large_starrytong_fixed.ckpt>",
      "license": {"code": "MIT (ZFTurbo/MSST + starrytong/SCNet)", "weights": "MIT (MSST release v1.0.9)"},
      "stems": ["drums", "bass", "other", "vocals"],
      "sample_rate": 44100,
      "channels": 2,
      "devices": ["cpu", "mps"],
      "inference": {"model_type": "scnet",
                    "config": "config/scnet/config_musdb18_scnet_large_starrytong.yaml",
                    "config_sha256": "<sha256 of vendored yaml>"},
      "env_lock_sha256": "<sha256 of msst.lock>",
      "status": "experimental"
    }
  ]
}
```

（注：`command` 路径为 repo-root 相对——执行方必须 cwd=repo root，dev.sh 保证。）

- [ ] **Step 3: 更新 shipped-registry 测试（替换原 `test_shipped_registry_file_is_valid`）**

```python
def test_shipped_registry_file_is_valid():
    shipped = Path(__file__).resolve().parents[2] / "config" / "separators.json"
    entries = registry.load_registry(shipped)
    by_id = {e.id: e for e in entries}
    assert set(by_id) == {"htdemucs", "scnet-large"}
    assert by_id["htdemucs"].status == "verified"
    assert by_id["scnet-large"].status == "experimental"


def test_shipped_env_locks_match_files():
    import hashlib
    config_dir = Path(__file__).resolve().parents[2] / "config"
    entries = {e.id: e for e in registry.load_registry(config_dir / "separators.json")}
    lock_files = {"htdemucs": config_dir / "runner-demucs-constraints.txt",
                  "scnet-large": config_dir / "msst.lock"}
    for eid, lock in lock_files.items():
        digest = hashlib.sha256(lock.read_bytes()).hexdigest()
        assert entries[eid].env_lock_sha256 == digest, f"{eid} env lock 漂移"
    config_sha = hashlib.sha256(
        (config_dir / "scnet" / "config_musdb18_scnet_large_starrytong.yaml").read_bytes()
    ).hexdigest()
    assert entries["scnet-large"].inference["config_sha256"] == config_sha
```

- [ ] **Step 4: Run tests**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_registry.py -q
```

Expected: 全部 PASS（含既有 registry 测试）。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/config/separators.json workers/audio/tests/separation/test_registry.py
git commit -m "feat(registry): register htdemucs (verified) and scnet-large (experimental)"
```

---

### Task 7: `separation/smoke.py` + dev.sh `separate` 命令

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/smoke.py`
- Modify: `scripts/dev.sh`（`separate` 命令 + usage + case）
- Test: `workers/audio/tests/separation/test_smoke_cli.py`

**Interfaces:**
- Consumes: Phase 0 的 `registry.load_registry`、`cache.ensure_checkpoint`、`protocol.run_separator`/`SeparationRequest`、`contract.validate_canonical_stems`
- Produces:
  - CLI：`python -m lmdj_audio_worker.separation.smoke --id ID --input F --device cpu|mps [--out DIR] [--registry PATH] [--timeout N]`（主 venv 运行；从 repo root）
  - 流程：registry 取条目（校验 device ∈ entry.devices）→ `ensure_checkpoint`（真实下载+校验）→ `run_separator` → completed 时 `validate_canonical_stems`（`expected_frames` 由 soundfile 读输入帧数得出；输入非 44.1k wav 时打印 warning 并以 drums stem 自身帧数校验其余约束）→ 打印 `actual_device`、performance 摘要 → exit 0；失败/校验不过 → 打印失败记录 → exit 1
- dev.sh：`cmd_separate` 从 repo root 调 smoke CLI

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/separation/test_smoke_cli.py
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from lmdj_audio_worker.separation import smoke

SR = 44100
OK_RUNNER = r"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
import soundfile as sf
out = Path(sys.argv[1]); inp = Path(sys.argv[2])
frames = sf.info(str(inp)).frames
(out / "stems").mkdir(parents=True, exist_ok=True)
for k in ("drums", "bass", "vocals", "other"):
    sf.write(out / "stems" / f"{k}.wav",
             np.zeros((frames, 2), dtype=np.float32), 44100, subtype="FLOAT")
(out / "separation.json").write_text(json.dumps({
    "schema_version": "lmdj.separation.v1", "status": "completed",
    "source": "runner",
    "input_sha256": hashlib.sha256(inp.read_bytes()).hexdigest(),
    "separator": {"id": "fake", "family": "demucs",
                  "checkpoint_sha256": "b" * 64, "runner_version": "0.1.0"},
    "requested_device": "cpu", "actual_device": "cpu",
    "stems": {k: f"stems/{k}.wav" for k in ("drums", "bass", "vocals", "other")},
    "audio": {"sample_rate": 44100, "channels": 2,
              "duration_seconds": frames / 44100},
    "performance": {"model_load_seconds": 0, "inference_seconds": 0,
                    "wall_seconds": 0, "peak_rss_bytes": 0,
                    "peak_device_memory_bytes": 0},
}))
"""


def make_env(tmp_path, monkeypatch):
    payload = b"weights"
    sha = hashlib.sha256(payload).hexdigest()
    weights_file = tmp_path / "weights.bin"
    weights_file.write_bytes(payload)
    registry_path = tmp_path / "separators.json"
    registry_path.write_text(json.dumps({
        "schema_version": "lmdj.separators.v1",
        "separators": [{
            "id": "fake", "family": "demucs", "runner": "demucs",
            "command": [sys.executable, "-c", OK_RUNNER, "{output_dir}", "{input}"],
            "source": {"url": weights_file.as_uri(), "revision": "r1"},
            "artifact_sha256": sha,
            "license": {"code": "MIT", "weights": "MIT"},
            "stems": ["drums", "bass", "other", "vocals"],
            "sample_rate": 44100, "channels": 2, "devices": ["cpu"],
            "inference": {}, "env_lock_sha256": "d" * 64,
            "status": "experimental"}]}))
    input_path = tmp_path / "song.wav"
    sf.write(input_path, np.zeros((SR, 2), dtype=np.float32), SR)
    monkeypatch.setenv("LMDJ_MODEL_CACHE", str(tmp_path / "cache"))
    return registry_path, input_path


def test_smoke_completed_exit_zero(tmp_path, monkeypatch, capsys):
    registry_path, input_path = make_env(tmp_path, monkeypatch)
    code = smoke.main(["--id", "fake", "--input", str(input_path),
                       "--device", "cpu", "--out", str(tmp_path / "run"),
                       "--registry", str(registry_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "actual_device: cpu" in out and "canonical OK" in out


def test_smoke_unknown_id_exit_one(tmp_path, monkeypatch):
    registry_path, input_path = make_env(tmp_path, monkeypatch)
    code = smoke.main(["--id", "nope", "--input", str(input_path),
                       "--device", "cpu", "--out", str(tmp_path / "run"),
                       "--registry", str(registry_path)])
    assert code == 1


def test_smoke_device_not_in_entry_exit_one(tmp_path, monkeypatch):
    registry_path, input_path = make_env(tmp_path, monkeypatch)
    code = smoke.main(["--id", "fake", "--input", str(input_path),
                       "--device", "mps", "--out", str(tmp_path / "run"),
                       "--registry", str(registry_path)])
    assert code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_smoke_cli.py -q
```

Expected: FAIL（module 不存在）。

- [ ] **Step 3: Write the implementation**

```python
# workers/audio/lmdj_audio_worker/separation/smoke.py
"""单个 separator 的 smoke 执行：registry -> cache -> runner -> canonical 校验。

dev.sh `separate` 的实现；也是 Phase 1C orchestrator 之前的手动验收工具。
主 venv 运行（需要 pfs extra 的 soundfile 做 canonical 校验）。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .cache import ensure_checkpoint
from .contract import validate_canonical_stems
from .protocol import SeparationRequest, run_separator
from .registry import load_registry

_WORKER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = _WORKER_ROOT / "config" / "separators.json"


def _input_frames(path: Path) -> int | None:
    import soundfile as sf
    try:
        info = sf.info(str(path))
    except Exception:
        return None
    return info.frames if info.samplerate == 44100 else None


def _stem_frames(out_dir: Path, result) -> int:
    import soundfile as sf
    return sf.info(str(out_dir / result.stems["drums"])).frames


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("separation-smoke", description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--device", required=True, choices=("cpu", "mps"))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args(argv)

    entries = {e.id: e for e in load_registry(args.registry)}
    entry = entries.get(args.id)
    if entry is None:
        print(f"未知 separator id {args.id!r}，registry 有 {sorted(entries)}",
              file=sys.stderr)
        return 1
    if args.device not in entry.devices:
        print(f"{args.id} 不支持设备 {args.device}（registry devices={entry.devices}）",
              file=sys.stderr)
        return 1

    out_dir = args.out or Path(f"separation-smoke-{args.id}-{int(time.time())}")
    checkpoint_dir = ensure_checkpoint(entry)
    request = SeparationRequest(input_path=args.input, output_dir=out_dir,
                                device=args.device)
    result = run_separator(entry, request, checkpoint_dir,
                           timeout_sec=args.timeout)
    if result.status != "completed":
        print(f"FAILED [{result.error.category}] source={result.source} "
              f"exit={result.error.exit_code}\n{result.error.stderr_tail}",
              file=sys.stderr)
        return 1

    expected_frames = _input_frames(args.input)
    if expected_frames is None:
        print("warning: 输入无法用 soundfile 读取或非 44.1k，时长核对退化为 stems 自身帧数")
        expected_frames = _stem_frames(out_dir, result)
    errors = validate_canonical_stems(out_dir, result, expected_frames)
    if errors:
        print("canonical 校验失败：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    perf = result.performance or {}
    print(f"actual_device: {result.actual_device}")
    print(f"canonical OK: 4 stems @ {out_dir}")
    print("performance: " + ", ".join(f"{k}={v}" for k, v in sorted(perf.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

dev.sh：usage 追加 `separate <id> <audio> [device]   跑单个 separator smoke（默认 mps）`；命令：

```bash
cmd_separate() {
  [ $# -ge 2 ] || { echo "用法: scripts/dev.sh separate <id> <audio> [device]" >&2; exit 1; }
  (cd "$ROOT" && "$WORKER/.venv/bin/python" -m lmdj_audio_worker.separation.smoke \
    --id "$1" --input "$2" --device "${3:-mps}")
}
```

case 表加 `separate) cmd_separate "$@" ;;`。

- [ ] **Step 4: Run tests**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q && bash -n scripts/dev.sh
```

Expected: 全绿 + syntax ok。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/smoke.py \
        workers/audio/tests/separation/test_smoke_cli.py scripts/dev.sh
git commit -m "feat(separation): add registry-driven smoke command"
```

---

### Task 8: 真实验收 — Mac MPS smoke（两个 runner）+ 链路 sanity

**Files:** 无新文件（验收任务；发现的问题按性质回改对应模块并随修正 commit）

前置：`scripts/dev.sh setup`、`setup-pfs`、`setup-sep-demucs`、`setup-sep-scnet` 都已运行；testsong 存在（`scripts/dev.sh smoke` 会生成）。

- [ ] **Step 1: htdemucs MPS smoke**

```bash
scripts/dev.sh separate htdemucs references/demos/lmdj-song-pipeline/output/testsong/input.wav mps
```

Expected: 首次真实下载 htdemucs 权重（~80MB）到 `~/.cache/lmdj/separators/htdemucs/<sha>/` 并校验；输出含 `actual_device: mps`、`canonical OK`、performance 里 `peak_device_memory_bytes > 0`、`model_load_seconds/inference_seconds > 0`。exit 0。

- [ ] **Step 2: scnet-large MPS smoke**

```bash
scripts/dev.sh separate scnet-large references/demos/lmdj-song-pipeline/output/testsong/input.wav mps
```

Expected: 同上（权重较大，下载耐心等）。**若 MPS 上推理因 upstream 算子不支持而失败**：这是真实结果——不得静默转 CPU；改跑 `... cpu` 确认 CPU 路径通，然后 STOP 报告 BLOCKED（registry devices 是否收缩为 `["cpu"]` 属于产品决策，交人确认）。

- [ ] **Step 3: 链路 sanity（canonical → compat → pfs → patchify）**

用 Step 1 的输出目录（记为 `$SEP_OUT`，绝对路径）：

```bash
workers/audio/.venv-pfs/bin/python - <<EOF
from pathlib import Path
from lmdj_audio_worker.pipeline_from_stems.compat import map_canonical_to_legacy
map_canonical_to_legacy(Path("$SEP_OUT/stems"), Path("$SEP_OUT/legacy"))
print("compat ok")
EOF
workers/audio/.venv-pfs/bin/python -m lmdj_audio_worker.pipeline_from_stems \
  --stems "$SEP_OUT/legacy" --out "$SEP_OUT/pfs" --song-id mpssmoke
scripts/dev.sh patchify "$SEP_OUT/pfs/mpssmoke"
```

Expected: `compat ok`；pfs 产出 `report.json`（status passed/rejected 均可）；patchify 产出 patch.json 且摘要正常打印。这条链是 spec §4 完整数据通路（真实 MPS 分离产物首次走通）。

- [ ] **Step 4: 记录验收数据**

把两个 runner 的 performance JSON（wall/inference/peak_rss/peak_device_memory）与链路 sanity 输出摘录到 task report，供 Phase 1D 对照。

---

### Task 9: 文档同步

**Files:**
- Modify: `CLAUDE.md` / `AGENTS.md`（命令块加三行；workers/audio 条目追加 runner 一句）
- Modify: `docs/superpowers/2026-07-10-status-and-backlog.md`（里程碑表追加 #8 行）
- Modify: `docs/prd/decision-log.md`（2026-07-16 决策一条）

- [ ] **Step 1: CLAUDE.md / AGENTS.md**

命令块 `scripts/dev.sh parity` 行后各追加：

```text
scripts/dev.sh setup-sep-demucs   # create the HT Demucs runner venv (torch stack, pinned)
scripts/dev.sh setup-sep-scnet    # create the SCNet runner venv + MSST pinned clone
scripts/dev.sh separate <id> <audio> [device]   # run one separator via registry -> canonical stems smoke
```

workers/audio 架构条目末尾各追加：

```text
`separation/runners/` holds per-family separator runners (htdemucs verified, scnet-large experimental), each in its own `.venv-sep-*` venv driven by the registry command; `separation/smoke.py` is the registry→cache→runner→canonical-validation smoke entry.
```

- [ ] **Step 2: status-and-backlog 里程碑表追加**

```text
| #8 | Separation Phase 1A：HT Demucs（verified）+ SCNet-large（experimental）真实 runner 与 registry 条目，MPS 内存采样，`dev.sh separate` smoke（Mac MPS 验收 + canonical→compat→pfs→patchify 链路 sanity）。plan: `docs/superpowers/plans/2026-07-16-separation-phase1a.md` | `workers/audio/separation/runners`、`config/` |
```

- [ ] **Step 3: decision-log 追加**

```markdown
## 2026-07-16

### 已确认：SCNet-large 选 starrytong fixed checkpoint，MSST 以 pinned clone 方式复用

- 结论：SCNet-large 采用 MSST release v1.0.9 的 `SCNet-large_starrytong_fixed.ckpt`（starrytong 训练，MUSDB test SDR 9.70，优于 v1.0.8 的 9.32），config 同 release 入库 vendored；推理复用 MSST 框架的 `demix`，以 `config/msst.lock` pinned commit clone（gitignored），不 pip 安装、不修改其源码。代码与权重 license 均为 MIT。
- 原因：MSST 不是 pip 包；pinned clone + lock 文件哈希进 registry `env_lock_sha256`，与 constraints 方案同构，满足 spec §6 可追溯门禁；两个候选 checkpoint 中选 SDR 更高且训练者可追溯的一个。
- 影响：升级 SCNet 推理代码 = 改 msst.lock 的 commit 并重跑 smoke 验收；registry 条目状态 experimental，双平台验证后方可升 verified（spec §6）。
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md AGENTS.md docs/superpowers/2026-07-10-status-and-backlog.md docs/prd/decision-log.md
git commit -m "docs: record separation phase 1a runners, commands and decisions"
```

---

## 收尾验证（全量）

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q     # 全绿
scripts/dev.sh test && scripts/dev.sh parity                 # Phase 0 门槛无回归
scripts/dev.sh separate htdemucs <testsong input> mps        # exit 0
scripts/dev.sh separate scnet-large <testsong input> mps     # exit 0（或已按 Task 8 上报 BLOCKED）
```

## Spec 覆盖对照（自查）

| Spec 要求 | Task |
|---|---|
| §5 runner 请求契约（input/output/device/checkpoint/seed）与自写失败记录 | 1 |
| §5 canonical 硬约束落盘（float32/44.1k/双声道/原始幅度） | 1 |
| §5 MPS 内存采样算法（100ms、driver 峰值、interval 记录、CPU 置 0） | 2 |
| §2/§10 不允许静默设备 fallback | 2（resolve_device）+ 8 |
| §6 registry 完整条目（来源/revision/sha/license/inference/env lock/status）与首批状态策略 | 3–6 |
| §6 缓存下载真实走通（ensure_checkpoint） | 7–8 |
| §12.2.1 Mac MPS smoke、actual_device 一致 | 8 |
| §4 数据通路（separator → canonical → compat → pfs → patchify） | 8 |

不在本 plan 范围：BS/Mel RoFormer（Phase 1B）、dataset manifests 与 benchmark orchestrator/指标（Phase 1C）、Linux CPU 侧执行（Phase 1D）、生产接入（Phase 2）。
