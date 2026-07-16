# Separation Phase 1C-a（benchmark 执行层）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 benchmark 执行层：dataset manifest（`lmdj.benchmark-manifest.v1`）、输入归一化、orchestrator（组合遍历 + 全链执行 + 缓存/resume + 快照）、`lmdj-audio-worker benchmark` CLI，并用 suno 语料完成真实 mini-run 验收。指标/评分/报告/盲听是 1C-b（另一个 plan）。

**Architecture:** 新子包 `workers/audio/lmdj_audio_worker/benchmark/`（manifest / normalize / cache_key / snapshots / orchestrator + cli 扩展），运行在 workers/audio 主 venv（依赖 `pfs` extra 的 soundfile/numpy + 系统 ffmpeg；torch 永不进入——runner 仍是子进程）。每个组合（dataset×track×separator×device×repeat）执行完整链：归一化输入 → `protocol.run_separator` → canonical 校验 → `compat.map_canonical_to_legacy`（主 venv 内直调）→ `PipelineFromStemsRunner` 子进程 → `patchify_package` 直调；产物落 `benchmarks/<run-id>/results/<dataset>/<track>/<separator>/<device>/<repeat>/`，每组合写 `combo.json`（阶段状态/耗时/错误类别/缓存标记）。单组合失败不中断整批（spec §4/§10）。

**Tech Stack:** stdlib + soundfile/numpy（已有 pfs extra）+ 系统 ffmpeg（仓库既有依赖）；无新 Python 依赖。

**Spec:** `docs/superpowers/specs/2026-07-15-multi-separator-benchmark-design.md` §7（manifest）、§8（执行/缓存/输出结构）、§4/§10（orchestrator/错误模型）。

**Base branch:** `main`（Phase 1B 已合并）。分支 `codex/feat-separation-phase1c-exec`。

## 已核实的事实

- suno 语料：`testdata/audio/suno/{boom-bap,city-pop,g-funk,jazzy-hip-hop}/*.mp3`（11 首，MP3，gitignored——manifest 的 `LMDJ_BENCH_DATA_ROOT` 指向仓库的 `testdata/audio` 即可用）。
- MSST 家族 runner 只接受 44.1k wav（`load_stereo_44k`）；demucs runner 用 ffmpeg 什么都吃——**归一化层让所有 runner 吃同一个 44.1k 立体声 wav**，同时统一 `input_sha256` 与 `expected_frames` 基准。
- 已有接口：`protocol.SeparationRequest(input_path, output_dir, device, seed=0, repeat_id=0)` / `run_separator(entry, request, checkpoint_dir, timeout_sec)`；`cache.ensure_checkpoint(entry)`；`contract.validate_canonical_stems(package_dir, result, expected_frames)`；`compat.map_canonical_to_legacy(canonical_dir, legacy_dir)`（主 venv 可直调，只需 numpy/soundfile）；`PipelineFromStemsRunner(worker_dir=None, timeout_sec=600).run(stems_dir, out_dir, song_id) -> Path`；`patchify_package(package_dir: Path, out_path=None) -> Patch`（core-models/patchify 已装进主 venv）。
- runner 模块常量（`RUNNER_VERSION` 等）顶层无 torch import——主 venv 可安全 import 读取（缓存 key 需要 runner version，spec §8）。
- 现有 CLI `lmdj_audio_worker/cli.py` 是 argparse 子命令结构（`run`/`status`）——`benchmark` 作为新子命令加入。

## Global Constraints

- 缓存 key（spec §8，六元组缺一不可）：`input sha256 + checkpoint sha256 + runner version + config hash + device + seed/repeat`。config hash = registry 条目推理相关字段的规范化 JSON 的 sha256（定义见 Task 3）。
- 缓存命中不得计入性能指标：命中组合保留原 `combo.json`（含原 performance），仅把顶层 `cache_hit` 记录进 run 汇总；`--fresh` 强制全部重跑。
- 一个组合失败不得中止整批；失败按 spec §10 类别记录（model/checkpoint/device/track/stage、退出码、stderr tail、已用时间）。
- 设备强制：请求设备不在 entry.devices → 该组合记为 `unsupported_device` 失败（不是跳过、不是降级）。
- manifest：路径相对 `LMDJ_BENCH_DATA_ROOT`（env），拒绝绝对路径与 `..`；仓库只提交 schema + 匿名示例 manifest；报告/快照不得含绝对主机路径（run.json 里 data root 只记环境变量名）。
- run 目录结构（spec §8）：`benchmarks/<run-id>/{run.json, manifest.snapshot.json, registry.snapshot.json, environment.json, results/...}`（`summary.json`/`listening-test/` 属 1C-b）。`benchmarks/` gitignored。
- `workers/audio` 主包 `dependencies` 保持 `[]`；无新 pip 依赖；torch 不进主 venv。
- commit 符合 Conventional Commits v1.0.0；`references/demos/` 与 MSST clone 不动。

## 准备

```bash
cd workers/audio
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -e ../../packages/core-models -e ../../packages/patchify
.venv/bin/pip install -e ".[test,pfs]" -c config/parity-constraints.txt
.venv/bin/python -m pytest tests/ -q   # 基线 127 tests 全绿
```

---

### Task 1: `benchmark/manifest.py` — schema 与 loader

**Files:**
- Create: `workers/audio/lmdj_audio_worker/benchmark/__init__.py`（docstring：benchmark 执行层，spec §7/§8）
- Create: `workers/audio/lmdj_audio_worker/benchmark/manifest.py`
- Create: `workers/audio/config/benchmark/example.manifest.json`（匿名示例，入库）
- Test: `workers/audio/tests/benchmark/__init__.py`（空）+ `workers/audio/tests/benchmark/test_manifest.py`

**Interfaces:**
- Produces:
  - `MANIFEST_SCHEMA_VERSION = "lmdj.benchmark-manifest.v1"`；`SPLITS = ("full", "perf", "smoke")`
  - `@dataclass(frozen=True) Track(id, input, split, tags: tuple[str, ...], has_ground_truth: bool, ground_truth: dict | None)`
  - `@dataclass(frozen=True) Manifest(dataset_id: str, tracks: tuple[Track, ...])`
  - `class ManifestError(ValueError)`（`.errors` 列表）
  - `load_manifest(path: Path) -> Manifest`：校验 schema_version、track 必填字段、id 唯一、split 合法、路径相对且无 `..`、`has_ground_truth=True` 时 ground_truth 四轨齐全、`has_ground_truth=False` 时 ground_truth 必须为 null
  - `data_root() -> Path`：`LMDJ_BENCH_DATA_ROOT` env，未设抛 `ManifestError`
  - `resolve_input(track: Track) -> Path`：`data_root()/track.input`，不存在抛 `ManifestError`

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/benchmark/test_manifest.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmdj_audio_worker.benchmark import manifest


def make_manifest(**overrides) -> dict:
    data = {
        "schema_version": "lmdj.benchmark-manifest.v1",
        "dataset_id": "suno-v1",
        "tracks": [
            {"id": "boom-bap-01", "input": "suno/boom-bap/boom-bap-01.mp3",
             "split": "full", "tags": ["hiphop", "drums-heavy"],
             "has_ground_truth": False, "ground_truth": None},
            {"id": "gt-track", "input": "musdb/mix.wav", "split": "perf",
             "tags": [], "has_ground_truth": True,
             "ground_truth": {k: f"musdb/stems/{k}.wav"
                              for k in ("drums", "bass", "vocals", "other")}},
        ],
    }
    data.update(overrides)
    return data


def write(tmp_path, data) -> Path:
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data))
    return path


def test_valid_manifest_loads(tmp_path):
    m = manifest.load_manifest(write(tmp_path, make_manifest()))
    assert m.dataset_id == "suno-v1"
    assert m.tracks[0].id == "boom-bap-01"
    assert m.tracks[1].ground_truth["drums"] == "musdb/stems/drums.wav"


def test_duplicate_track_ids_rejected(tmp_path):
    data = make_manifest()
    data["tracks"].append(dict(data["tracks"][0]))
    with pytest.raises(manifest.ManifestError) as exc:
        manifest.load_manifest(write(tmp_path, data))
    assert any("boom-bap-01" in e for e in exc.value.errors)


def test_absolute_path_rejected(tmp_path):
    data = make_manifest()
    data["tracks"][0]["input"] = "/etc/passwd"
    with pytest.raises(manifest.ManifestError):
        manifest.load_manifest(write(tmp_path, data))


def test_dotdot_path_rejected(tmp_path):
    data = make_manifest()
    data["tracks"][0]["input"] = "../outside.mp3"
    with pytest.raises(manifest.ManifestError):
        manifest.load_manifest(write(tmp_path, data))


def test_bad_split_rejected(tmp_path):
    data = make_manifest()
    data["tracks"][0]["split"] = "extra"
    with pytest.raises(manifest.ManifestError):
        manifest.load_manifest(write(tmp_path, data))


def test_ground_truth_requires_four_stems(tmp_path):
    data = make_manifest()
    del data["tracks"][1]["ground_truth"]["vocals"]
    with pytest.raises(manifest.ManifestError) as exc:
        manifest.load_manifest(write(tmp_path, data))
    assert any("vocals" in e for e in exc.value.errors)


def test_no_gt_requires_null(tmp_path):
    data = make_manifest()
    data["tracks"][0]["ground_truth"] = {"drums": "x.wav"}
    with pytest.raises(manifest.ManifestError):
        manifest.load_manifest(write(tmp_path, data))


def test_wrong_schema_version_rejected(tmp_path):
    with pytest.raises(manifest.ManifestError):
        manifest.load_manifest(
            write(tmp_path, make_manifest(schema_version="v2")))


def test_data_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(tmp_path))
    assert manifest.data_root() == tmp_path
    monkeypatch.delenv("LMDJ_BENCH_DATA_ROOT")
    with pytest.raises(manifest.ManifestError):
        manifest.data_root()


def test_resolve_input(monkeypatch, tmp_path):
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(tmp_path))
    track = manifest.load_manifest(write(tmp_path, make_manifest())).tracks[0]
    with pytest.raises(manifest.ManifestError):
        manifest.resolve_input(track)          # 文件不存在
    target = tmp_path / "suno" / "boom-bap" / "boom-bap-01.mp3"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"mp3")
    assert manifest.resolve_input(track) == target


def test_shipped_example_manifest_valid():
    shipped = (Path(__file__).resolve().parents[2]
               / "config" / "benchmark" / "example.manifest.json")
    m = manifest.load_manifest(shipped)
    assert m.dataset_id == "example"
    assert all(t.split in manifest.SPLITS for t in m.tracks)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/benchmark/test_manifest.py -q
```

Expected: FAIL（module 不存在）。

- [ ] **Step 3: Write the implementation**

`workers/audio/lmdj_audio_worker/benchmark/manifest.py`：

```python
"""benchmark dataset manifest（spec §7）：lmdj.benchmark-manifest.v1。

路径一律相对 LMDJ_BENCH_DATA_ROOT；仓库只提交 schema 与匿名示例，
真实歌曲数据 gitignored；报告不得出现绝对主机路径。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

MANIFEST_SCHEMA_VERSION = "lmdj.benchmark-manifest.v1"
SPLITS = ("full", "perf", "smoke")
_GT_STEMS = ("drums", "bass", "vocals", "other")
_TRACK_FIELDS = ("id", "input", "split", "tags", "has_ground_truth", "ground_truth")


class ManifestError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Track:
    id: str
    input: str
    split: str
    tags: tuple[str, ...]
    has_ground_truth: bool
    ground_truth: dict | None


@dataclass(frozen=True)
class Manifest:
    dataset_id: str
    tracks: tuple[Track, ...]


def _check_rel_path(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label}: 必须是非空相对路径字符串")
        return
    if value.startswith("/") or value.startswith("~"):
        errors.append(f"{label}: 不得是绝对路径（{value!r}）")
    if ".." in Path(value).parts:
        errors.append(f"{label}: 不得包含 ..（{value!r}）")


def load_manifest(path: Path) -> Manifest:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError([f"无法读取 manifest {path}: {exc}"]) from exc
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {MANIFEST_SCHEMA_VERSION!r}")
    dataset_id = data.get("dataset_id") if isinstance(data, dict) else None
    if not isinstance(dataset_id, str) or not dataset_id:
        errors.append("dataset_id 必须是非空字符串")
    raw_tracks = data.get("tracks") if isinstance(data, dict) else None
    if not isinstance(raw_tracks, list) or not raw_tracks:
        errors.append("tracks 必须是非空列表")
        raise ManifestError(errors)

    tracks: list[Track] = []
    for i, raw in enumerate(raw_tracks):
        prefix = f"tracks[{i}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix}: 必须是 object")
            continue
        missing = [f for f in _TRACK_FIELDS if f not in raw]
        if missing:
            errors.append(f"{prefix}: 缺少字段 {missing}")
            continue
        tid = raw["id"]
        if not isinstance(tid, str) or not tid:
            errors.append(f"{prefix}: id 必须是非空字符串")
        _check_rel_path(raw["input"], f"{prefix}({tid}).input", errors)
        if raw["split"] not in SPLITS:
            errors.append(f"{prefix}({tid}): split 必须属于 {SPLITS}")
        if not isinstance(raw["tags"], list):
            errors.append(f"{prefix}({tid}): tags 必须是列表")
        gt = raw["ground_truth"]
        if raw["has_ground_truth"]:
            if not isinstance(gt, dict):
                errors.append(f"{prefix}({tid}): has_ground_truth 时 ground_truth 必须是 object")
            else:
                for stem in _GT_STEMS:
                    if stem not in gt:
                        errors.append(f"{prefix}({tid}): ground_truth 缺少 {stem}")
                    else:
                        _check_rel_path(gt[stem],
                                        f"{prefix}({tid}).ground_truth.{stem}", errors)
        elif gt is not None:
            errors.append(f"{prefix}({tid}): has_ground_truth=False 时 ground_truth 必须为 null")
        tracks.append(Track(
            id=tid, input=raw["input"], split=raw["split"],
            tags=tuple(raw["tags"]) if isinstance(raw["tags"], list) else (),
            has_ground_truth=bool(raw["has_ground_truth"]),
            ground_truth=dict(gt) if isinstance(gt, dict) else None))

    ids = [t.id for t in tracks]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"manifest: 重复 track id {dup!r}")
    if errors:
        raise ManifestError(errors)
    return Manifest(dataset_id=dataset_id, tracks=tuple(tracks))


def data_root() -> Path:
    root = os.environ.get("LMDJ_BENCH_DATA_ROOT")
    if not root:
        raise ManifestError(["环境变量 LMDJ_BENCH_DATA_ROOT 未设置（spec §7.2）"])
    return Path(root)


def resolve_input(track: Track) -> Path:
    path = data_root() / track.input
    if not path.exists():
        raise ManifestError([f"track {track.id}: 输入不存在 {track.input}"
                             "（相对 LMDJ_BENCH_DATA_ROOT）"])
    return path
```

`workers/audio/config/benchmark/example.manifest.json`（匿名示例——路径虚构）：

```json
{
  "schema_version": "lmdj.benchmark-manifest.v1",
  "dataset_id": "example",
  "tracks": [
    {"id": "song-a", "input": "songs/song-a.mp3", "split": "full",
     "tags": ["electronic", "drums-heavy"], "has_ground_truth": false,
     "ground_truth": null},
    {"id": "song-b", "input": "songs/song-b.wav", "split": "perf",
     "tags": ["rock"], "has_ground_truth": true,
     "ground_truth": {"drums": "songs/song-b/drums.wav",
                      "bass": "songs/song-b/bass.wav",
                      "vocals": "songs/song-b/vocals.wav",
                      "other": "songs/song-b/other.wav"}}
  ]
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/benchmark/ -q
```

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/benchmark workers/audio/tests/benchmark \
        workers/audio/config/benchmark
git commit -m "feat(benchmark): add dataset manifest schema and loader"
```

---

### Task 2: `benchmark/normalize.py` — 输入归一化

**Files:**
- Create: `workers/audio/lmdj_audio_worker/benchmark/normalize.py`
- Test: `workers/audio/tests/benchmark/test_normalize.py`

**Interfaces:**
- Consumes: 系统 ffmpeg（subprocess）、`separation.cache.sha256_file`
- Produces:
  - `class NormalizeError(RuntimeError)`
  - `@dataclass(frozen=True) NormalizedInput(path: Path, sha256: str, frames: int, duration_seconds: float)`
  - `normalize_input(src: Path, dest_dir: Path) -> NormalizedInput`：ffmpeg 解码任意输入 → `dest_dir/<src stem>.wav`（44100Hz、双声道、`pcm_f32le`）；幂等（目标已存在则复用不重写）；失败（缺文件/坏音频）→ `NormalizeError` 带 ffmpeg stderr tail

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/benchmark/test_normalize.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lmdj_audio_worker.benchmark import normalize

SR = 44100


def make_src(tmp_path: Path, sr: int = 22050, seconds: float = 0.5,
             channels: int = 1) -> Path:
    src = tmp_path / "src.wav"
    frames = int(sr * seconds)
    shape = (frames, channels) if channels > 1 else (frames,)
    sf.write(src, np.random.default_rng(0).uniform(-0.3, 0.3, shape)
             .astype(np.float32), sr)
    return src


def test_normalizes_to_44k_stereo_float(tmp_path):
    src = make_src(tmp_path)
    result = normalize.normalize_input(src, tmp_path / "norm")
    info = sf.info(str(result.path))
    assert info.samplerate == SR and info.channels == 2
    assert info.subtype == "FLOAT"
    assert result.frames == info.frames
    assert abs(result.duration_seconds - 0.5) < 0.05
    assert len(result.sha256) == 64


def test_idempotent_reuse(tmp_path):
    src = make_src(tmp_path)
    first = normalize.normalize_input(src, tmp_path / "norm")
    mtime = first.path.stat().st_mtime_ns
    second = normalize.normalize_input(src, tmp_path / "norm")
    assert second.path.stat().st_mtime_ns == mtime    # 未重写
    assert second.sha256 == first.sha256


def test_missing_source_raises(tmp_path):
    with pytest.raises(normalize.NormalizeError):
        normalize.normalize_input(tmp_path / "nope.mp3", tmp_path / "norm")


def test_corrupt_audio_raises_with_stderr(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(normalize.NormalizeError) as exc:
        normalize.normalize_input(bad, tmp_path / "norm")
    assert str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/benchmark/test_normalize.py -q
```

- [ ] **Step 3: Write the implementation**

```python
# workers/audio/lmdj_audio_worker/benchmark/normalize.py
"""输入归一化：任意音频 -> 44.1kHz 双声道 float32 wav（benchmark 统一输入基准）。

所有 separator 组合吃同一个归一化产物；input_sha256 与 expected_frames
都以它为准。依赖系统 ffmpeg（仓库既有前置）。
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..separation.cache import sha256_file

_STDERR_TAIL = 2000


class NormalizeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizedInput:
    path: Path
    sha256: str
    frames: int
    duration_seconds: float


def normalize_input(src: Path, dest_dir: Path) -> NormalizedInput:
    import soundfile as sf

    src = Path(src)
    if not src.exists():
        raise NormalizeError(f"输入不存在: {src}")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (src.stem + ".wav")
    if not dest.exists():
        tmp = dest.with_suffix(".tmp.wav")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-ar", "44100", "-ac", "2",
             "-c:a", "pcm_f32le", str(tmp)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise NormalizeError(
                f"ffmpeg 解码失败 {src.name}: "
                f"{(proc.stderr or '')[-_STDERR_TAIL:]}")
        tmp.replace(dest)
    info = sf.info(str(dest))
    return NormalizedInput(path=dest, sha256=sha256_file(dest),
                           frames=info.frames,
                           duration_seconds=round(info.frames / info.samplerate, 6))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/benchmark/ -q
```

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/benchmark/normalize.py \
        workers/audio/tests/benchmark/test_normalize.py
git commit -m "feat(benchmark): normalize inputs to canonical 44k stereo wav via ffmpeg"
```

---

### Task 3: `benchmark/cache_key.py` — 缓存 key 与 runner version 解析

**Files:**
- Create: `workers/audio/lmdj_audio_worker/benchmark/cache_key.py`
- Test: `workers/audio/tests/benchmark/test_cache_key.py`

**Interfaces:**
- Consumes: `registry.SeparatorEntry`；runner 模块常量（`importlib` 按 `entry.runner` 解析 `lmdj_audio_worker.separation.runners.<runner>` 的 `RUNNER_VERSION`——模块顶层无 torch，主 venv 可 import）
- Produces:
  - `runner_version(entry: SeparatorEntry) -> str`（模块缺失/无常量 → `ValueError`）
  - `config_hash(entry: SeparatorEntry) -> str`：`sha256(json.dumps({"inference": entry.inference, "env_lock": entry.env_lock_sha256, "artifact": entry.artifact_sha256}, sort_keys=True))`
  - `describe(input_sha256, entry, device, seed, repeat) -> dict`（六成分明文，写进 combo.json 供审计）
  - `combo_cache_key(input_sha256, entry, device, seed, repeat) -> str`（describe 的规范化 JSON 的 sha256）

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/benchmark/test_cache_key.py
from __future__ import annotations

import pytest

from lmdj_audio_worker.benchmark import cache_key
from lmdj_audio_worker.separation.registry import SeparatorEntry


def make_entry(**overrides) -> SeparatorEntry:
    fields = dict(
        id="htdemucs", family="demucs", runner="demucs",
        command=("x", "{input}", "{output_dir}"),
        source_url="https://example.com/a.th", source_revision="r1",
        artifact_sha256="c" * 64, license_code="MIT", license_weights="MIT",
        stems=("drums", "bass", "other", "vocals"),
        sample_rate=44100, channels=2, devices=("cpu", "mps"),
        inference={"shifts": 0, "overlap": 0.25},
        env_lock_sha256="d" * 64, status="verified")
    fields.update(overrides)
    return SeparatorEntry(**fields)


def test_runner_version_resolves_real_module():
    assert cache_key.runner_version(make_entry()) == "0.1.0"


def test_runner_version_unknown_module():
    with pytest.raises(ValueError):
        cache_key.runner_version(make_entry(runner="nonexistent"))


def test_config_hash_changes_with_inference():
    a = cache_key.config_hash(make_entry())
    b = cache_key.config_hash(make_entry(inference={"shifts": 1, "overlap": 0.25}))
    assert a != b and len(a) == 64


def test_config_hash_stable_under_key_order():
    a = cache_key.config_hash(make_entry(inference={"a": 1, "b": 2}))
    b = cache_key.config_hash(make_entry(inference={"b": 2, "a": 1}))
    assert a == b


def test_combo_key_varies_on_each_component():
    base = dict(input_sha256="a" * 64, entry=make_entry(), device="mps",
                seed=0, repeat=0)
    key = cache_key.combo_cache_key(**base)
    assert key != cache_key.combo_cache_key(**{**base, "input_sha256": "b" * 64})
    assert key != cache_key.combo_cache_key(**{**base, "device": "cpu"})
    assert key != cache_key.combo_cache_key(**{**base, "seed": 1})
    assert key != cache_key.combo_cache_key(**{**base, "repeat": 1})
    assert key != cache_key.combo_cache_key(
        **{**base, "entry": make_entry(artifact_sha256="e" * 64)})


def test_describe_lists_six_components():
    entry = make_entry()
    desc = cache_key.describe("a" * 64, entry, "mps", 0, 2)
    assert set(desc) == {"input_sha256", "checkpoint_sha256", "runner_version",
                         "config_hash", "device", "seed_repeat"}
    assert desc["seed_repeat"] == "0/2"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/benchmark/test_cache_key.py -q
```

- [ ] **Step 3: Write the implementation**

```python
# workers/audio/lmdj_audio_worker/benchmark/cache_key.py
"""benchmark 结果缓存 key（spec §8）：六元组，缺一不可。

input sha256 + checkpoint sha256 + runner version + config hash + device + seed/repeat
"""
from __future__ import annotations

import hashlib
import importlib
import json

from ..separation.registry import SeparatorEntry

_RUNNER_PKG = "lmdj_audio_worker.separation.runners"


def runner_version(entry: SeparatorEntry) -> str:
    try:
        module = importlib.import_module(f"{_RUNNER_PKG}.{entry.runner}")
    except ImportError as exc:
        raise ValueError(f"未知 runner 模块 {entry.runner!r}") from exc
    version = getattr(module, "RUNNER_VERSION", None)
    if not isinstance(version, str):
        raise ValueError(f"runner 模块 {entry.runner!r} 缺少 RUNNER_VERSION")
    return version


def config_hash(entry: SeparatorEntry) -> str:
    payload = json.dumps(
        {"inference": entry.inference, "env_lock": entry.env_lock_sha256,
         "artifact": entry.artifact_sha256},
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def describe(input_sha256: str, entry: SeparatorEntry, device: str,
             seed: int, repeat: int) -> dict:
    return {
        "input_sha256": input_sha256,
        "checkpoint_sha256": entry.artifact_sha256,
        "runner_version": runner_version(entry),
        "config_hash": config_hash(entry),
        "device": device,
        "seed_repeat": f"{seed}/{repeat}",
    }


def combo_cache_key(input_sha256: str, entry: SeparatorEntry, device: str,
                    seed: int, repeat: int) -> str:
    desc = describe(input_sha256, entry, device, seed, repeat)
    payload = json.dumps(desc, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/benchmark/ -q
```

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/benchmark/cache_key.py \
        workers/audio/tests/benchmark/test_cache_key.py
git commit -m "feat(benchmark): add six-component combo cache key"
```

---

### Task 4: `benchmark/snapshots.py` — run 目录与快照

**Files:**
- Create: `workers/audio/lmdj_audio_worker/benchmark/snapshots.py`
- Modify: `.gitignore`（追加 `benchmarks/`）
- Test: `workers/audio/tests/benchmark/test_snapshots.py`

**Interfaces:**
- Produces:
  - `RUN_ID_RE`：run_id 只允许 `[A-Za-z0-9_-]+`；`init_run` 对非法 run_id 抛 `ValueError`（路径注入防护）
  - `init_run(out_root: Path, run_id: str, manifest_paths: list[Path], registry_path: Path, args: dict) -> Path`：建 `out_root/<run-id>/`，写四个文件——`run.json`（run_id、`created_at`（`time.strftime("%Y-%m-%dT%H:%M:%S")`）、`args`、`data_root: "LMDJ_BENCH_DATA_ROOT"`（**只记环境变量名，不记其值**））、`manifest.snapshot.json`（`{path.name: 解析后的 JSON 内容}`）、`registry.snapshot.json`（registry 文件原文 JSON）、`environment.json`（`platform.platform()`/`platform.machine()`/python 版本 + `parity-constraints.txt`、`runner-scnet-constraints.txt`、`msst.lock` 三个文件的 sha256，路径以 `Path(__file__).resolve().parents[2]/"config"` 定位）；返回 run 目录
  - `combo_dir(run_dir, dataset_id, track_id, separator_id, device, repeat) -> Path`：`run_dir/results/<dataset>/<track>/<separator>/<device>/<repeat>`（spec §8 层级；不自动创建）
  - `write_combo(path: Path, record: dict) -> None`（`path/combo.json`，原子写 tmp+`os.replace`，`indent=2, ensure_ascii=False`）
  - `read_combo(path: Path) -> dict | None`（不存在或 JSON 损坏 → None）
  - `finalize_run(run_dir: Path, summary: dict) -> None`：把 counts/failures 合并写回 `run.json`

- [ ] **Step 1: Write the failing tests**（要点，每条一个测试函数，实现者按 Task 1–3 测试风格撰写完整代码：
  1. `init_run` 产出四个 JSON 文件；`run.json` 的 `data_root` 字段值 == `"LMDJ_BENCH_DATA_ROOT"` 且整个文件序列化文本不含 `str(tmp_path)`（无绝对路径泄漏）；
  2. `environment.json` 的三个 sha256 与对实际 config 文件 `hashlib.sha256` 重算一致；
  3. `manifest.snapshot.json` 以文件名为 key、内容为解析后 JSON；`registry.snapshot.json` 与 registry 文件内容等价；
  4. `combo_dir` 返回 `results/ds/t1/sep/mps/0` 层级；
  5. `write_combo`/`read_combo` 往返相等；目录不存在时 write 自动建；损坏 JSON → `read_combo` 返回 None；
  6. 非法 run_id（`"../evil"`、`"a b"`）→ `ValueError`；
  7. `finalize_run` 后 `run.json` 含 summary 字段且原字段保留。）

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Write the implementation**（按 Interfaces 逐条实现；全部 JSON `indent=2, ensure_ascii=False`；`.gitignore` 追加一行 `benchmarks/`。）

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/benchmark/ -q
```

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/benchmark/snapshots.py \
        workers/audio/tests/benchmark/test_snapshots.py .gitignore
git commit -m "feat(benchmark): add run directory snapshots and combo records"
```

---

### Task 5: `benchmark/orchestrator.py` — 组合遍历与全链执行

**Files:**
- Create: `workers/audio/lmdj_audio_worker/benchmark/orchestrator.py`
- Test: `workers/audio/tests/benchmark/test_orchestrator.py`

**Interfaces:**
- Consumes: Task 1–4 全部；`separation.protocol`/`cache`/`contract`、`pipeline_from_stems.compat`、`runner.PipelineFromStemsRunner`、`lmdj_patchify.patchify.patchify_package`
- Produces:
  - `@dataclass OrchestratorDeps(normalize, ensure_checkpoint, separate, validate_stems, compat, pfs_run, patchify)`——可注入执行函数集；`default_deps() -> OrchestratorDeps` 绑定真实实现（**单测全部注入 fake，不碰真实 runner**）
  - `@dataclass RunConfig(manifests: list, separator_ids: list, device: str, repeats: int = 1, seed: int = 0, fresh: bool = False, timeout_sec: int = 1800, out_root: Path = Path("benchmarks"), run_id: str | None = None, registry_path: Path | None = None)`
  - `@dataclass RunSummary(run_dir: Path, total: int = 0, completed: int = 0, failed: int = 0, cache_hits: int = 0, failures: list = field(default_factory=list))`
  - `run_benchmark(cfg, *, deps=None) -> RunSummary`
  - `combo.json` 记录规范：`{"status": "completed"|"failed", "cache_key": str, "cache_key_components": dict, "track": id, "separator": id, "device": str, "repeat": int, "stages": {name: {"status": "ok"|"failed"|"skipped", "seconds": float, "error": str?}}, "failed_stage": str?, "error_category": str?, "performance": dict?, "cached": bool}`；阶段顺序 `normalize→separate→validate→compat→pfs→patchify`
  - 行为规则（Global Constraints 的落点）：未知 separator id → `ValueError`（run 前置校验）；设备不在 entry.devices → 组合记 `unsupported_device` 失败且 separate 不被调用；separate 返回 failed → category 取 `result.error.category`、下游 skipped；validate 有 errors → `invalid_stems`；compat/pfs/patchify 异常 → `downstream`；normalize 失败 → 该 track 所有组合记 `inference` 失败（stage=normalize）；缓存命中（combo.json 存在 + cache_key 相同 + status=completed + not fresh）→ 不执行任何阶段、`cached=true` 只进 run 汇总计数；所有失败进 `summary.failures`（含 spec §10 要求的 model/checkpoint/device/track/stage/exit/stderr tail/elapsed）

- [ ] **Step 1: Write the failing tests**（全 fake 注入，无真实音频/torch/子进程。要点，每条一个测试：
  1. happy path：2 tracks × 2 separators → 4 组合 completed；combo.json 六阶段 ok、层级正确、`RunSummary(total=4, completed=4, failed=0)`；
  2. 一个组合 separate 返回 failed SeparationResult（fake 按 track+separator 定向失败）→ 该组合 `failed_stage="separate"`、`error_category` 取 result 的类别、下游三阶段 `skipped`，其余 3 组合 completed；
  3. entry.devices=("cpu",) 请求 mps → `unsupported_device`，fake separate 调用计数为 0；
  4. fake pfs 抛异常 → `failed_stage="pfs"`、`error_category="downstream"`；
  5. resume：同 cfg 跑两遍 → 第二遍 `cache_hits==4` 且 fake separate 第二遍零调用；`fresh=True` 第三遍 → 重新调用；
  6. fake normalize 第二遍返回不同 sha → 缓存不命中；
  7. 未知 separator id → `ValueError`。
  fake 构造建议：registry 写 tmp separators.json（entry dict 结构照抄 tests/separation/test_smoke_cli.py 的 make_env，command 内容无所谓——separate 被注入替换）；fake normalize 返回 `NormalizedInput(path=tmp wav, sha256=固定值, frames=100, duration_seconds=1.0)`；fake separate 在 output_dir 写最小 completed `separation.json`（借 contract dataclass 构造）并返回该 SeparationResult；validate_stems 注入返回 `[]`；compat/pfs/patchify 返回哑值。完整测试代码由实现者撰写。）

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Write the implementation**

核心骨架（`_run_combo`/`_finalize` 由实现者按 Interfaces 的记录规范补全）：

```python
# workers/audio/lmdj_audio_worker/benchmark/orchestrator.py
"""benchmark orchestrator（spec §4/§8/§10）：组合遍历 + 全链执行 + 缓存/resume。

组合 = dataset×track×separator×device×repeat。一个组合失败不得中止整批；
设备不支持记 unsupported_device 失败（不跳过不降级）；缓存命中不重跑、
不计入性能指标。orchestrator 不 import 任何模型框架（runner 是子进程）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..separation.protocol import SeparationRequest
from ..separation.registry import load_registry
from . import cache_key as ck
from . import snapshots
from .manifest import load_manifest, resolve_input

_WORKER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = _WORKER_ROOT / "config" / "separators.json"


@dataclass
class OrchestratorDeps:
    normalize: Callable
    ensure_checkpoint: Callable
    separate: Callable
    validate_stems: Callable
    compat: Callable
    pfs_run: Callable
    patchify: Callable


def default_deps() -> OrchestratorDeps:
    from lmdj_patchify.patchify import patchify_package

    from ..pipeline_from_stems.compat import map_canonical_to_legacy
    from ..runner import PipelineFromStemsRunner
    from ..separation.cache import ensure_checkpoint
    from ..separation.contract import validate_canonical_stems
    from ..separation.protocol import run_separator
    from .normalize import normalize_input

    pfs = PipelineFromStemsRunner()
    return OrchestratorDeps(
        normalize=normalize_input,
        ensure_checkpoint=ensure_checkpoint,
        separate=run_separator,
        validate_stems=validate_canonical_stems,
        compat=map_canonical_to_legacy,
        pfs_run=pfs.run,
        patchify=patchify_package,
    )


@dataclass
class RunConfig:
    manifests: list
    separator_ids: list
    device: str
    repeats: int = 1
    seed: int = 0
    fresh: bool = False
    timeout_sec: int = 1800
    out_root: Path = Path("benchmarks")
    run_id: str | None = None
    registry_path: Path | None = None


@dataclass
class RunSummary:
    run_dir: Path
    total: int = 0
    completed: int = 0
    failed: int = 0
    cache_hits: int = 0
    failures: list = field(default_factory=list)


def run_benchmark(cfg: RunConfig, *, deps: OrchestratorDeps | None = None) -> RunSummary:
    deps = deps or default_deps()
    registry_path = Path(cfg.registry_path or DEFAULT_REGISTRY)
    entries = {e.id: e for e in load_registry(registry_path)}
    unknown = [s for s in cfg.separator_ids if s not in entries]
    if unknown:
        raise ValueError(f"未知 separator id: {unknown}（registry 有 {sorted(entries)}）")

    run_id = cfg.run_id or time.strftime("run-%Y%m%d-%H%M%S")
    run_dir = snapshots.init_run(
        Path(cfg.out_root), run_id, [Path(m) for m in cfg.manifests],
        registry_path,
        {"separators": list(cfg.separator_ids), "device": cfg.device,
         "repeats": cfg.repeats, "seed": cfg.seed, "fresh": cfg.fresh,
         "timeout_sec": cfg.timeout_sec})
    summary = RunSummary(run_dir=run_dir)

    for manifest_path in cfg.manifests:
        m = load_manifest(Path(manifest_path))
        for track in m.tracks:
            normalized = None
            norm_error = None
            try:
                # 按 track.id 分目录：不同 track 同名源文件（如都叫 vocal.mp3）
                # 若共用一个目录会因幂等复用静默拿到第一首的音频
                normalized = deps.normalize(
                    resolve_input(track),
                    run_dir / "normalized" / m.dataset_id / track.id)
            except Exception as exc:  # noqa: BLE001 —— 记录后继续其他 track
                norm_error = str(exc)[-2000:]
            for sep_id in cfg.separator_ids:
                entry = entries[sep_id]
                for repeat in range(cfg.repeats):
                    summary.total += 1
                    _run_combo(cfg, deps, summary, run_dir, m.dataset_id,
                               track, entry, repeat, normalized, norm_error)
    _finalize(run_dir, summary)
    return summary
```

`_run_combo` 实现要点：目录 = `snapshots.combo_dir(run_dir, dataset_id, track.id, entry.id, cfg.device, repeat)`；norm_error 非 None → 记 stage=normalize 失败（category `inference`）；设备检查在缓存检查之前之后均可但必须在 separate 之前；缓存检查用 `snapshots.read_combo` + `ck.combo_cache_key(normalized.sha256, entry, cfg.device, cfg.seed, repeat)`；成功链路各阶段 `time.monotonic()` 计时并 try/except；`SeparationRequest(input_path=normalized.path, output_dir=combo/"separation", device=cfg.device, seed=cfg.seed, repeat_id=repeat)`；pfs 输出 `combo/"pfs"`，song_id=track.id，patchify 输入 `combo/"pfs"/track.id`；失败记录 append 进 `summary.failures`：`{"track", "separator", "device", "repeat", "stage", "category", "error"(tail), "elapsed_seconds"}`；`_finalize` 调 `snapshots.finalize_run(run_dir, {...counts, "failures": summary.failures})`。

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/benchmark/ -q && .venv/bin/python -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/benchmark/orchestrator.py \
        workers/audio/tests/benchmark/test_orchestrator.py
git commit -m "feat(benchmark): add orchestrator with full-chain execution and resume"
```

---

### Task 6: CLI 子命令 + dev.sh `bench` + 真实 suno manifest

**Files:**
- Modify: `workers/audio/lmdj_audio_worker/cli.py`（`benchmark` 子命令）
- Modify: `scripts/dev.sh`（`bench` 命令 + usage + case）
- Create: `testdata/audio/suno-full.manifest.json`（真实 manifest：11 首 suno；每风格第 1 首 `split: "smoke"`，其余 `full`；tags 用风格名；`has_ground_truth: false`、`ground_truth: null`；先 `ls testdata/audio/suno/*/` 取真实文件名）
- Modify: `.gitignore`（如 `testdata/audio` 规则挡住 json，加 `!testdata/audio/suno-full.manifest.json` 放行——manifest 无隐私路径，符合 spec 匿名示例精神）
- Test: `workers/audio/tests/test_cli_benchmark.py`

**Interfaces:**
- CLI：`lmdj-audio-worker benchmark --dataset M.json [--dataset N.json] --separators a,b --device cpu|mps [--repeats N] [--seed N] [--fresh] [--timeout N] [--out DIR] [--run-id ID] [--registry PATH]`（spec §8 命令形态）；结束打印 `run_dir` 与 `total/completed/failed/cache_hits` 各一行；`failed > 0` → exit 1，否则 exit 0
- dev.sh：

```bash
cmd_bench() {
  (cd "$ROOT" && LMDJ_BENCH_DATA_ROOT="${LMDJ_BENCH_DATA_ROOT:-$ROOT/testdata/audio}" \
    "$WORKER/.venv/bin/python" -m lmdj_audio_worker.cli benchmark "$@")
}
```

usage 追加 `bench --dataset M.json --separators a,b --device mps   benchmark 执行层（data root 默认 testdata/audio）`；case 表加 `bench) cmd_bench "$@" ;;`。
- 测试：monkeypatch `run_benchmark` 为 fake（捕获 RunConfig、返回构造的 RunSummary），断言：`--separators a,b` 拆成列表、多 `--dataset` 聚合、`--fresh` 传布尔、failed>0 → SystemExit(1)、全成功 → 0。不跑真实 orchestrator。

- [ ] **Step 1: Write the failing tests** → **Step 2: fail** → **Step 3: implement**（按既有 cli.py 的 sub.add_parser 风格；`bash -n scripts/dev.sh`）→ **Step 4: pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q && bash -n ../../scripts/dev.sh
```

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/cli.py workers/audio/tests/test_cli_benchmark.py \
        scripts/dev.sh testdata/audio/suno-full.manifest.json .gitignore
git commit -m "feat(benchmark): add cli subcommand, dev.sh bench and suno manifest"
```

---

### Task 7: 真实验收 — suno mini-run（Mac MPS）+ resume + 失败连续性

**Files:** 无新文件（验收；修正随性质单独 commit）

前置（本 worktree）：`scripts/dev.sh setup`、`setup-pfs`、`setup-sep-demucs`、`setup-sep-mel-roformer`（checkpoint 已在 `~/.cache/lmdj/separators`，无需重新下载）。**不需要 demo venv**（benchmark 链不经过 demo）。

- [ ] **Step 1: mini-run**：写临时 2-track manifest（`suno/boom-bap/boom-bap-01.mp3` + `suno/city-pop/city-pop-01.mp3`，split smoke，放 /tmp）：

```bash
scripts/dev.sh bench --dataset /tmp/mini.manifest.json \
  --separators htdemucs,mel-roformer-4stem --device mps --run-id accept-1c
```

Expected: exit 0；`benchmarks/accept-1c/` 含 run.json + 三个 snapshot；4 个组合目录各含 combo.json（completed、六成分、performance 非空）、`separation/stems/*.wav`×4、`legacy/`、`pfs/<track>/report.json`、patch.json。

- [ ] **Step 2: resume**：重跑同命令 → `cache_hits: 4` 秒回；`--fresh` → 真实重算（combo.json mtime 变化）。

- [ ] **Step 3: 失败连续性**：manifest 加一条指向不存在文件的 track → exit 1；该 track 组合记 normalize 失败（stage=normalize），原 4 组合 cache-hit 不受影响；run.json failures 记录完整（stage/category/error）。

- [ ] **Step 4: 无绝对路径**：`grep -rl "$HOME" benchmarks/accept-1c --include="*.json"` 只允许命中 combo.json 里 runner 写的 stderr tail（如有）；run.json/environment.json/snapshots 必须零命中——不满足则修 snapshots/记录逻辑。

- [ ] **Step 5: 记录验收数据到 task report**（每组合 stage 计时表）；清理 /tmp manifest；`git status` 干净。

---

### Task 8: 文档同步

**Files:** `CLAUDE.md` / `AGENTS.md`、`docs/superpowers/2026-07-10-status-and-backlog.md`

- [ ] **Step 1: CLAUDE.md / AGENTS.md** — 命令块 `separate` 行后各追加：

```text
scripts/dev.sh bench --dataset M.json --separators a,b --device mps   # benchmark executor: full chain + cache/resume (data root defaults to testdata/audio)
```

workers/audio 条目末尾各追加：

```text
`benchmark/` is the benchmark execution layer (spec §7/§8): manifest loader (`lmdj.benchmark-manifest.v1`, paths relative to LMDJ_BENCH_DATA_ROOT), ffmpeg input normalization, and an orchestrator that runs each dataset×separator×device×repeat combo through the full separation→compat→pfs→patchify chain with six-component cache keys and resume; one combo's failure never aborts the batch. Metrics/scoring/reports are phase 1C-b.
```

- [ ] **Step 2: status-and-backlog** — 里程碑表追加：

```text
| #10 | Separation Phase 1C-a：benchmark 执行层——manifest schema/loader、ffmpeg 输入归一化、orchestrator（全链 + 六元组缓存 key + resume + 单组合失败不中断）、`dev.sh bench` CLI；suno mini-run 真实验收。plan: `docs/superpowers/plans/2026-07-16-separation-phase1c-exec.md` | `workers/audio/benchmark`、`testdata/` |
```

后续候选（下一步）注明：1C-b（§9 指标/评分/summary/盲听打包）；1D 前置物料（MUSDB18HQ 下载 ~30GB 需注册、真实歌曲集扩充至 10–20 首——suno 现 11 首可作起点）。

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md AGENTS.md docs/superpowers/2026-07-10-status-and-backlog.md
git commit -m "docs: record separation phase 1c-a benchmark executor"
```

---

## 收尾验证（全量）

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q   # 全绿（127 + 新增）
scripts/dev.sh test
scripts/dev.sh bench --dataset /tmp/mini.manifest.json --separators htdemucs,mel-roformer-4stem --device mps --run-id accept-1c   # exit 0
# 重跑同命令 → cache_hits 全命中
```

## Spec 覆盖对照（自查）

| Spec 要求 | Task |
|---|---|
| §7 manifest schema/相对路径/匿名示例入库/真实数据不入库 | 1, 6 |
| §8 CLI 命令形态 | 6 |
| §8 输出结构（run.json/snapshots/environment/results 层级） | 4, 5 |
| §8 缓存 key 六元组 / 默认复用 / --fresh / 命中不计性能 | 3, 5, 7 |
| §4/§10 单组合失败不中止 / 错误类别与 stage 记录 / 设备强制 | 5, 7 |
| §12.2.6 快照可重建实验身份、无绝对主机路径 | 4, 7 |
| 全链数据通路（normalize→separator→compat→pfs→patchify） | 5, 7 |

不在本 plan 范围（1C-b plan）：§9 指标/评分/硬门槛、summary.json/csv、盲听打包、稳定性重复子集策略；（1D 物料）MUSDB18HQ 下载、真实歌曲集扩充。
