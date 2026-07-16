# Separation Phase 0 (0A+0B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立多分轨 benchmark 的地基——`lmdj.separation.v1` contract、checkpoint registry、runner 协议（Phase 0A），以及 `PipelineFromStemsRunner` 与 frozen-stems parity 门槛（Phase 0B）。

**Architecture:** 所有新代码落在 `workers/audio/lmdj_audio_worker/` 下的两个子包：`separation/`（contract/registry/cache/protocol，主包内、零依赖）和 `pipeline_from_stems/`（从冻结 demo 逐行迁移的阶段 3–6 + 兼容映射 + parity 比较器，运行在专用 `.venv-pfs` venv、以子进程调用）。DSP 依赖通过 pyproject 的 `pfs` optional extra + 入库的 `parity-constraints.txt` 锁版本，主包 `dependencies` 保持为空。

**Tech Stack:** Python 3.11+（parity venv 与 demo venv 同 Python minor 版本，当前 3.12）；stdlib（主包）；librosa 0.11.0 / numpy 1.26.4 / scikit-learn 1.9.0 / soundfile 0.14.0 / pretty_midi 0.2.11（pfs venv，全部由 constraints pin 死）；pytest。

**Spec:** `docs/superpowers/specs/2026-07-15-multi-separator-benchmark-design.md`（引用简写 spec §N）。

**Base branch:** PR #10（spec）合并后从 `main` 拉新分支（建议 `codex/feat-separation-phase0`），用 `superpowers:using-git-worktrees` 建隔离 worktree。

## Global Constraints

- `workers/audio/pyproject.toml` 的 `[project] dependencies` 必须保持 `[]`（spec §3.1；DSP 栈只进 optional extra `pfs`，防止经 `apps/api` 的 path dep 传染 API venv）。
- `references/demos/lmdj-song-pipeline/` 冻结：不改其中任何代码；`scripts/dev.sh` 不属于 demo，可以改。
- 迁移的阶段 3–6 模块必须与 demo 源文件**逐字节一致**（`cp` 原样拷贝，靠相对 import 直接工作）；行为改动必须先过 parity。
- parity 容差（spec §3.2）：validation score |Δ| ≤ `1e-4`；音频最大绝对差 ≤ `1e-5`；其余字段一致。耗时字段除外。
- canonical stems 硬约束（spec §5）：`drums/bass/vocals/other` 四轨齐全、44100 Hz、双声道、32-bit float、与输入时长误差 ≤1 sample、无 NaN/Inf/空音频、绝对峰值 ≤ `8.0`。
- 统一错误类别（spec §10，顺序固定）：`download checksum license unsupported_device timeout oom inference invalid_stems downstream metric`。
- 失败记录两级产生（spec §5）：runner 自写可捕获异常；文件缺失/损坏/timeout 由 orchestrator 合成，`source` 字段区分 `runner`/`orchestrator`。
- 兼容映射（spec §5）：`melody = vocals + other`，只支持 `vocals_strategy = "merge"`，遇 `drop` 显式报错；单轨峰值 >1.0 缩放到 1.0；canonical 与 legacy 两组音频不得复用同一文件。
- commit 必须符合 Conventional Commits v1.0.0。
- 模型权重缓存（spec §6）：`${LMDJ_MODEL_CACHE:-~/.cache/lmdj/separators}/<checkpoint-id>/<sha256>/`，临时文件 + SHA-256 校验 + 原子 rename，checksum 不符立即删除。

## 准备：workers/audio 测试 venv

实施前在 worktree 里准备测试环境（Task 2 之前 `pfs` extra 尚不存在，先装 `[test]`，后续任务按提示重装）：

```bash
cd workers/audio
python3 -m venv .venv
.venv/bin/pip install -e ../../packages/core-models -e ../../packages/patchify
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest tests/ -q   # 现有测试全绿（基线）
```

---

### Task 1: `separation/contract.py` — 数据模型与 schema 校验

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/__init__.py`
- Create: `workers/audio/lmdj_audio_worker/separation/contract.py`
- Test: `workers/audio/tests/separation/__init__.py`（空文件）
- Test: `workers/audio/tests/separation/test_contract.py`

**Interfaces:**
- Consumes: 无（stdlib only）
- Produces（后续任务依赖，签名精确）：
  - 常量 `SCHEMA_VERSION = "lmdj.separation.v1"`、`CANONICAL_STEMS = ("drums", "bass", "vocals", "other")`、`CANONICAL_SAMPLE_RATE = 44100`、`CANONICAL_CHANNELS = 2`、`MAX_ABS_PEAK = 8.0`、`STATUSES`、`SOURCES`、`ERROR_CATEGORIES`
  - `@dataclass(frozen=True) SeparatorInfo(id, family, checkpoint_sha256, runner_version)`
  - `@dataclass(frozen=True) SeparationError(category, exit_code: int | None, stage, stderr_tail, elapsed_seconds)`
  - `@dataclass(frozen=True) SeparationResult(status, source, input_sha256, separator: SeparatorInfo, requested_device, actual_device=None, stems=None, audio=None, performance=None, error=None)`，方法 `to_dict() -> dict`、`classmethod from_dict(data) -> SeparationResult`（不合法抛 `ContractError`）
  - `class ContractError(ValueError)`，属性 `.errors: list[str]`
  - `validate_result_dict(data: object) -> list[str]`（空列表 = 合法）
  - `write_result(path: Path, result: SeparationResult) -> None` / `load_result_file(path: Path) -> SeparationResult`

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/separation/test_contract.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmdj_audio_worker.separation import contract


def make_completed(**overrides) -> dict:
    data = {
        "schema_version": "lmdj.separation.v1",
        "status": "completed",
        "source": "runner",
        "input_sha256": "a" * 64,
        "separator": {"id": "htdemucs", "family": "demucs",
                      "checkpoint_sha256": "b" * 64, "runner_version": "0.1.0"},
        "requested_device": "mps",
        "actual_device": "mps",
        "stems": {k: f"stems/{k}.wav"
                  for k in ("drums", "bass", "vocals", "other")},
        "audio": {"sample_rate": 44100, "channels": 2, "duration_seconds": 30.0},
        "performance": {"model_load_seconds": 1.0, "inference_seconds": 5.0,
                        "wall_seconds": 6.5, "peak_rss_bytes": 1024,
                        "peak_device_memory_bytes": 0},
    }
    data.update(overrides)
    return data


def make_failed(**overrides) -> dict:
    data = {
        "schema_version": "lmdj.separation.v1",
        "status": "failed",
        "source": "orchestrator",
        "input_sha256": "a" * 64,
        "separator": {"id": "htdemucs", "family": "demucs",
                      "checkpoint_sha256": "b" * 64, "runner_version": "unknown"},
        "requested_device": "mps",
        "error": {"category": "oom", "exit_code": 137, "stage": "inference",
                  "stderr_tail": "killed", "elapsed_seconds": 12.5},
    }
    data.update(overrides)
    return data


def test_valid_completed_passes():
    assert contract.validate_result_dict(make_completed()) == []


def test_valid_failed_passes():
    assert contract.validate_result_dict(make_failed()) == []


def test_error_categories_match_spec_order():
    assert contract.ERROR_CATEGORIES == (
        "download", "checksum", "license", "unsupported_device",
        "timeout", "oom", "inference", "invalid_stems", "downstream", "metric")


@pytest.mark.parametrize("mutate,fragment", [
    ({"schema_version": "lmdj.separation.v2"}, "schema_version"),
    ({"status": "done"}, "status"),
    ({"source": "worker"}, "source"),
    ({"input_sha256": "xyz"}, "input_sha256"),
])
def test_top_level_field_errors(mutate, fragment):
    errors = contract.validate_result_dict(make_completed(**mutate))
    assert any(fragment in e for e in errors)


def test_completed_requires_all_canonical_stems():
    data = make_completed()
    del data["stems"]["vocals"]
    errors = contract.validate_result_dict(data)
    assert any("vocals" in e for e in errors)


def test_completed_rejects_extra_stem():
    data = make_completed()
    data["stems"]["piano"] = "stems/piano.wav"
    errors = contract.validate_result_dict(data)
    assert any("piano" in e for e in errors)


def test_completed_requires_performance_keys():
    data = make_completed()
    del data["performance"]["peak_device_memory_bytes"]
    errors = contract.validate_result_dict(data)
    assert any("peak_device_memory_bytes" in e for e in errors)


def test_failed_rejects_stems_field():
    data = make_failed(stems={"drums": "stems/drums.wav"})
    errors = contract.validate_result_dict(data)
    assert any("stems" in e for e in errors)


def test_failed_rejects_unknown_error_category():
    data = make_failed()
    data["error"]["category"] = "mystery"
    errors = contract.validate_result_dict(data)
    assert any("category" in e for e in errors)


def test_non_dict_input():
    assert contract.validate_result_dict([1, 2]) != []


def test_round_trip_write_and_load(tmp_path: Path):
    result = contract.SeparationResult.from_dict(make_failed())
    path = tmp_path / "separation.json"
    contract.write_result(path, result)
    loaded = contract.load_result_file(path)
    assert loaded == result
    assert json.loads(path.read_text())["status"] == "failed"


def test_from_dict_raises_with_errors_attribute():
    with pytest.raises(contract.ContractError) as exc:
        contract.SeparationResult.from_dict(make_completed(status="done"))
    assert exc.value.errors
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_contract.py -q
```

Expected: FAIL / ERROR（`No module named 'lmdj_audio_worker.separation'`）。

- [ ] **Step 3: Write the implementation**

`workers/audio/lmdj_audio_worker/separation/__init__.py`：

```python
"""lmdj separation 层：contract / registry / cache / runner 协议（spec §4–§6）。"""
```

`workers/audio/lmdj_audio_worker/separation/contract.py`：

```python
"""lmdj.separation.v1 —— separator runner 输出契约。

字段与硬约束的规范文本：
docs/superpowers/specs/2026-07-15-multi-separator-benchmark-design.md §5。
只用 stdlib；canonical stems 的音频级校验（需 numpy/soundfile）见
validate_canonical_stems，调用方须安装 `pfs` extra。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = "lmdj.separation.v1"
CANONICAL_STEMS = ("drums", "bass", "vocals", "other")
CANONICAL_SAMPLE_RATE = 44100
CANONICAL_CHANNELS = 2
MAX_ABS_PEAK = 8.0
STATUSES = ("completed", "failed")
SOURCES = ("runner", "orchestrator")
# spec §10 统一错误类别，顺序固定
ERROR_CATEGORIES = (
    "download", "checksum", "license", "unsupported_device",
    "timeout", "oom", "inference", "invalid_stems", "downstream", "metric",
)
_SEPARATOR_KEYS = ("id", "family", "checkpoint_sha256", "runner_version")
_AUDIO_KEYS = ("sample_rate", "channels", "duration_seconds")
_PERFORMANCE_KEYS = ("model_load_seconds", "inference_seconds", "wall_seconds",
                     "peak_rss_bytes", "peak_device_memory_bytes")
_ERROR_KEYS = ("category", "stage", "stderr_tail", "elapsed_seconds")


class ContractError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class SeparatorInfo:
    id: str
    family: str
    checkpoint_sha256: str
    runner_version: str


@dataclass(frozen=True)
class SeparationError:
    category: str
    exit_code: int | None
    stage: str
    stderr_tail: str
    elapsed_seconds: float


@dataclass(frozen=True)
class SeparationResult:
    status: str
    source: str
    input_sha256: str
    separator: SeparatorInfo
    requested_device: str
    actual_device: str | None = None
    stems: dict[str, str] | None = None
    audio: dict | None = None
    performance: dict | None = None
    error: SeparationError | None = None

    def to_dict(self) -> dict:
        data: dict = {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "source": self.source,
            "input_sha256": self.input_sha256,
            "separator": {
                "id": self.separator.id,
                "family": self.separator.family,
                "checkpoint_sha256": self.separator.checkpoint_sha256,
                "runner_version": self.separator.runner_version,
            },
            "requested_device": self.requested_device,
        }
        if self.actual_device is not None:
            data["actual_device"] = self.actual_device
        if self.stems is not None:
            data["stems"] = dict(self.stems)
        if self.audio is not None:
            data["audio"] = dict(self.audio)
        if self.performance is not None:
            data["performance"] = dict(self.performance)
        if self.error is not None:
            data["error"] = {
                "category": self.error.category,
                "exit_code": self.error.exit_code,
                "stage": self.error.stage,
                "stderr_tail": self.error.stderr_tail,
                "elapsed_seconds": self.error.elapsed_seconds,
            }
        return data

    @classmethod
    def from_dict(cls, data: object) -> "SeparationResult":
        errors = validate_result_dict(data)
        if errors:
            raise ContractError(errors)
        assert isinstance(data, dict)
        sep = data["separator"]
        error = None
        if "error" in data:
            e = data["error"]
            error = SeparationError(
                category=e["category"], exit_code=e.get("exit_code"),
                stage=e["stage"], stderr_tail=e["stderr_tail"],
                elapsed_seconds=e["elapsed_seconds"])
        return cls(
            status=data["status"], source=data["source"],
            input_sha256=data["input_sha256"],
            separator=SeparatorInfo(
                id=sep["id"], family=sep["family"],
                checkpoint_sha256=sep["checkpoint_sha256"],
                runner_version=sep["runner_version"]),
            requested_device=data["requested_device"],
            actual_device=data.get("actual_device"),
            stems=data.get("stems"),
            audio=data.get("audio"),
            performance=data.get("performance"),
            error=error,
        )


def _is_sha256(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def validate_result_dict(data: object) -> list[str]:
    """dict 级校验；返回错误列表，空列表即合法。"""
    if not isinstance(data, dict):
        return ["separation.json 顶层必须是 JSON object"]
    errors: list[str] = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {SCHEMA_VERSION!r}，"
                      f"收到 {data.get('schema_version')!r}")
    status = data.get("status")
    if status not in STATUSES:
        errors.append(f"status 必须属于 {STATUSES}，收到 {status!r}")
    if data.get("source") not in SOURCES:
        errors.append(f"source 必须属于 {SOURCES}，收到 {data.get('source')!r}")
    if not _is_sha256(data.get("input_sha256")):
        errors.append("input_sha256 必须是 64 位十六进制字符串")
    sep = data.get("separator")
    if not isinstance(sep, dict):
        errors.append("separator 必须是 object")
    else:
        for key in _SEPARATOR_KEYS:
            if not isinstance(sep.get(key), str) or not sep.get(key):
                errors.append(f"separator.{key} 必须是非空字符串")
    if not isinstance(data.get("requested_device"), str):
        errors.append("requested_device 必须是字符串")

    if status == "completed":
        if not isinstance(data.get("actual_device"), str):
            errors.append("completed 记录必须带 actual_device")
        stems = data.get("stems")
        if not isinstance(stems, dict):
            errors.append("completed 记录必须带 stems object")
        else:
            for name in CANONICAL_STEMS:
                if not isinstance(stems.get(name), str):
                    errors.append(f"stems 缺少 canonical 轨 {name!r}")
            for name in stems:
                if name not in CANONICAL_STEMS:
                    errors.append(f"stems 含非 canonical 轨 {name!r}")
        audio = data.get("audio")
        if not isinstance(audio, dict):
            errors.append("completed 记录必须带 audio object")
        else:
            for key in _AUDIO_KEYS:
                if key not in audio:
                    errors.append(f"audio 缺少 {key}")
        perf = data.get("performance")
        if not isinstance(perf, dict):
            errors.append("completed 记录必须带 performance object")
        else:
            for key in _PERFORMANCE_KEYS:
                if key not in perf:
                    errors.append(f"performance 缺少 {key}")
    elif status == "failed":
        if "stems" in data:
            errors.append("失败记录不得包含 stems 字段（spec §5）")
        err = data.get("error")
        if not isinstance(err, dict):
            errors.append("failed 记录必须带 error object")
        else:
            for key in _ERROR_KEYS:
                if key not in err:
                    errors.append(f"error 缺少 {key}")
            if err.get("category") not in ERROR_CATEGORIES:
                errors.append(
                    f"error.category 必须属于 {ERROR_CATEGORIES}，"
                    f"收到 {err.get('category')!r}")
    return errors


def write_result(path: Path, result: SeparationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


def load_result_file(path: Path) -> SeparationResult:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError([f"无法读取 {path}: {exc}"]) from exc
    return SeparationResult.from_dict(data)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_contract.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation workers/audio/tests/separation
git commit -m "feat(separation): add lmdj.separation.v1 contract dataclasses and validation"
```

---

### Task 2: canonical stems 音频级校验

**Files:**
- Modify: `workers/audio/lmdj_audio_worker/separation/contract.py`（追加函数）
- Modify: `workers/audio/pyproject.toml`（新增 `pfs` extra，先只含 numpy/soundfile，Task 6 补齐其余条目）
- Test: `workers/audio/tests/separation/test_canonical_stems.py`

**Interfaces:**
- Consumes: Task 1 的 `SeparationResult`、`CANONICAL_STEMS`、`CANONICAL_SAMPLE_RATE`、`CANONICAL_CHANNELS`、`MAX_ABS_PEAK`
- Produces: `validate_canonical_stems(package_dir: Path, result: SeparationResult, expected_frames: int) -> list[str]`（函数内 import numpy/soundfile；主包 import contract 本身仍零依赖）

- [ ] **Step 1: 给 pyproject 加 `pfs` extra 并重装测试 venv**

`workers/audio/pyproject.toml` 的 `[project.optional-dependencies]` 改为：

```toml
[project.optional-dependencies]
test = [
  "pytest>=8,<9",
]
# pipeline-from-stems / canonical stems 校验的 DSP 依赖。
# 版本由 workers/audio/config/parity-constraints.txt 锁定（安装时 -c 传入）。
pfs = [
  "numpy",
  "soundfile",
]
```

```bash
cd workers/audio && .venv/bin/pip install -e ".[test,pfs]"
```

（constraints 文件 Task 6 才创建；本任务先装未 pin 版本跑单测，Task 6 落 constraints 后按 constraints 重装。）

- [ ] **Step 2: Write the failing tests**

```python
# workers/audio/tests/separation/test_canonical_stems.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lmdj_audio_worker.separation import contract

SR = contract.CANONICAL_SAMPLE_RATE
FRAMES = SR  # 1 秒


def write_stem(path: Path, data: np.ndarray, sr: int = SR,
               subtype: str = "FLOAT") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data, sr, subtype=subtype)


def make_package(tmp_path: Path, mutate=None) -> tuple[Path, contract.SeparationResult]:
    rng = np.random.default_rng(0)
    for name in contract.CANONICAL_STEMS:
        data = rng.uniform(-0.5, 0.5, size=(FRAMES, 2)).astype(np.float32)
        if mutate:
            data = mutate(name, data)
        write_stem(tmp_path / "stems" / f"{name}.wav", data)
    result = contract.SeparationResult.from_dict({
        "schema_version": contract.SCHEMA_VERSION,
        "status": "completed", "source": "runner",
        "input_sha256": "a" * 64,
        "separator": {"id": "htdemucs", "family": "demucs",
                      "checkpoint_sha256": "b" * 64, "runner_version": "0.1.0"},
        "requested_device": "cpu", "actual_device": "cpu",
        "stems": {k: f"stems/{k}.wav" for k in contract.CANONICAL_STEMS},
        "audio": {"sample_rate": SR, "channels": 2, "duration_seconds": 1.0},
        "performance": {"model_load_seconds": 0.0, "inference_seconds": 0.0,
                        "wall_seconds": 0.0, "peak_rss_bytes": 0,
                        "peak_device_memory_bytes": 0},
    })
    return tmp_path, result


def test_valid_package_passes(tmp_path):
    pkg, result = make_package(tmp_path)
    assert contract.validate_canonical_stems(pkg, result, FRAMES) == []


def test_missing_stem_file(tmp_path):
    pkg, result = make_package(tmp_path)
    (pkg / "stems" / "other.wav").unlink()
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("other" in e for e in errors)


def test_wrong_sample_rate(tmp_path):
    pkg, result = make_package(tmp_path)
    data, _ = sf.read(pkg / "stems" / "drums.wav", always_2d=True)
    write_stem(pkg / "stems" / "drums.wav", data, sr=48000)
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("drums" in e and "44100" in e for e in errors)


def test_mono_rejected(tmp_path):
    pkg, result = make_package(tmp_path)
    write_stem(pkg / "stems" / "bass.wav",
               np.zeros(FRAMES, dtype=np.float32) + 0.1)
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("bass" in e for e in errors)


def test_pcm16_subtype_rejected(tmp_path):
    pkg, result = make_package(tmp_path)
    data, _ = sf.read(pkg / "stems" / "vocals.wav", always_2d=True)
    write_stem(pkg / "stems" / "vocals.wav", data, subtype="PCM_16")
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("vocals" in e and "float" in e.lower() for e in errors)


def test_nan_rejected(tmp_path):
    def poison(name, data):
        if name == "drums":
            data[0, 0] = np.nan
        return data
    pkg, result = make_package(tmp_path, mutate=poison)
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("drums" in e and "NaN" in e for e in errors)


def test_peak_over_limit_rejected(tmp_path):
    def loud(name, data):
        if name == "other":
            data[0, 0] = 9.0
        return data
    pkg, result = make_package(tmp_path, mutate=loud)
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("other" in e and "8.0" in e for e in errors)


def test_duration_off_by_two_rejected(tmp_path):
    pkg, result = make_package(tmp_path)
    errors = contract.validate_canonical_stems(pkg, result, FRAMES + 2)
    assert len(errors) == 4  # 四轨全部超差


def test_duration_off_by_one_allowed(tmp_path):
    pkg, result = make_package(tmp_path)
    assert contract.validate_canonical_stems(pkg, result, FRAMES + 1) == []


def test_empty_audio_rejected(tmp_path):
    pkg, result = make_package(tmp_path)
    write_stem(pkg / "stems" / "drums.wav",
               np.zeros((0, 2), dtype=np.float32))
    errors = contract.validate_canonical_stems(pkg, result, FRAMES)
    assert any("drums" in e for e in errors)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_canonical_stems.py -q
```

Expected: FAIL（`AttributeError: ... has no attribute 'validate_canonical_stems'`）。

- [ ] **Step 4: Write the implementation**

追加到 `contract.py` 末尾：

```python
def validate_canonical_stems(package_dir: Path, result: SeparationResult,
                             expected_frames: int) -> list[str]:
    """canonical package 音频级硬约束（spec §5）。需要 `pfs` extra。

    expected_frames：输入音频的帧数（44.1 kHz 下），由调用方解码输入后提供。
    """
    import numpy as np
    import soundfile as sf

    errors: list[str] = []
    stems = result.stems or {}
    for name in CANONICAL_STEMS:
        rel = stems.get(name)
        if rel is None:
            errors.append(f"{name}: result.stems 缺少该轨")
            continue
        path = package_dir / rel
        if not path.exists():
            errors.append(f"{name}: 文件不存在 {rel}")
            continue
        try:
            info = sf.info(str(path))
            data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        except Exception as exc:  # noqa: BLE001 —— 损坏文件统一转错误条目
            errors.append(f"{name}: 无法读取（{exc}）")
            continue
        if info.subtype != "FLOAT":
            errors.append(f"{name}: subtype={info.subtype}，要求 32-bit float (FLOAT)")
        if sr != CANONICAL_SAMPLE_RATE:
            errors.append(f"{name}: sample_rate={sr}，要求 {CANONICAL_SAMPLE_RATE}")
        if data.shape[1] != CANONICAL_CHANNELS:
            errors.append(f"{name}: channels={data.shape[1]}，要求 {CANONICAL_CHANNELS}")
        if len(data) == 0:
            errors.append(f"{name}: 空音频")
            continue
        if abs(len(data) - expected_frames) > 1:
            errors.append(f"{name}: 长度 {len(data)} frames，"
                          f"与输入 {expected_frames} 误差超过 1 sample")
        if not np.isfinite(data).all():
            errors.append(f"{name}: 含 NaN/Inf")
        else:
            peak = float(np.abs(data).max())
            if peak > MAX_ABS_PEAK:
                errors.append(f"{name}: 峰值 {peak:.3f} 超过 {MAX_ABS_PEAK}")
    return errors
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/ -q
```

Expected: 全部 PASS（含 Task 1 的测试）。

- [ ] **Step 6: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/contract.py \
        workers/audio/tests/separation/test_canonical_stems.py \
        workers/audio/pyproject.toml
git commit -m "feat(separation): validate canonical stem audio hard constraints"
```

---

### Task 3: `separation/registry.py` + `config/separators.json`

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/registry.py`
- Create: `workers/audio/config/separators.json`
- Test: `workers/audio/tests/separation/test_registry.py`

**Interfaces:**
- Consumes: 无（stdlib only）
- Produces:
  - `REGISTRY_SCHEMA_VERSION = "lmdj.separators.v1"`、`ENTRY_STATUSES = ("experimental", "verified", "production")`、`ALLOWED_DEVICES = ("cpu", "mps")`、`COMMAND_PLACEHOLDERS = ("input", "output_dir", "device", "checkpoint_dir", "seed", "repeat_id")`
  - `@dataclass(frozen=True) SeparatorEntry(id, family, runner, command: tuple[str, ...], source_url, source_revision, artifact_sha256, license_code, license_weights, stems: tuple[str, ...], sample_rate: int, channels: int, devices: tuple[str, ...], inference: dict, env_lock_sha256, status)`
  - `class RegistryError(ValueError)`，属性 `.errors: list[str]`
  - `load_registry(path: Path) -> tuple[SeparatorEntry, ...]`
  - `benchmark_entries(entries) -> tuple[SeparatorEntry, ...]`（全部状态）/ `production_entries(entries) -> tuple[SeparatorEntry, ...]`

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/separation/test_registry.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmdj_audio_worker.separation import registry


def entry_dict(**overrides) -> dict:
    d = {
        "id": "htdemucs",
        "family": "demucs",
        "runner": "demucs",
        "command": ["{checkpoint_dir}/run", "--input", "{input}",
                    "--output", "{output_dir}", "--device", "{device}",
                    "--seed", "{seed}"],
        "source": {"url": "https://example.com/htdemucs.th", "revision": "v4.0.1"},
        "artifact_sha256": "c" * 64,
        "license": {"code": "MIT", "weights": "MIT"},
        "stems": ["drums", "bass", "vocals", "other"],
        "sample_rate": 44100,
        "channels": 2,
        "devices": ["cpu", "mps"],
        "inference": {"segment_seconds": 7.8, "overlap": 0.25},
        "env_lock_sha256": "d" * 64,
        "status": "verified",
    }
    d.update(overrides)
    return d


def write_registry(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "separators.json"
    path.write_text(json.dumps(
        {"schema_version": "lmdj.separators.v1", "separators": entries}))
    return path


def test_valid_registry_loads(tmp_path):
    entries = registry.load_registry(write_registry(tmp_path, [entry_dict()]))
    assert entries[0].id == "htdemucs"
    assert entries[0].command[1] == "--input"
    assert entries[0].inference["overlap"] == 0.25


def test_empty_registry_loads(tmp_path):
    assert registry.load_registry(write_registry(tmp_path, [])) == ()


def test_duplicate_ids_rejected(tmp_path):
    path = write_registry(tmp_path, [entry_dict(), entry_dict()])
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(path)
    assert any("htdemucs" in e and "重复" in e for e in exc.value.errors)


@pytest.mark.parametrize("field", [
    "artifact_sha256", "license", "source", "inference",
    "env_lock_sha256", "status", "command",
])
def test_missing_required_field_rejected(tmp_path, field):
    d = entry_dict()
    del d[field]
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(write_registry(tmp_path, [d]))
    assert any(field in e for e in exc.value.errors)


def test_unknown_field_rejected(tmp_path):
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(
            write_registry(tmp_path, [entry_dict(surprise=1)]))
    assert any("surprise" in e for e in exc.value.errors)


def test_bad_status_rejected(tmp_path):
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(
            write_registry(tmp_path, [entry_dict(status="beta")]))
    assert any("status" in e for e in exc.value.errors)


def test_unknown_command_placeholder_rejected(tmp_path):
    d = entry_dict(command=["run", "--model", "{model_path}"])
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(write_registry(tmp_path, [d]))
    assert any("model_path" in e for e in exc.value.errors)


def test_bad_device_rejected(tmp_path):
    with pytest.raises(registry.RegistryError) as exc:
        registry.load_registry(
            write_registry(tmp_path, [entry_dict(devices=["cuda"])]))
    assert any("cuda" in e for e in exc.value.errors)


def test_production_filter(tmp_path):
    entries = registry.load_registry(write_registry(tmp_path, [
        entry_dict(),
        entry_dict(id="scnet-large", status="production"),
    ]))
    assert [e.id for e in registry.production_entries(entries)] == ["scnet-large"]
    assert len(registry.benchmark_entries(entries)) == 2


def test_shipped_registry_file_is_valid():
    shipped = Path(__file__).resolve().parents[2] / "config" / "separators.json"
    assert registry.load_registry(shipped) == ()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_registry.py -q
```

Expected: FAIL（`No module named ...registry`）。

- [ ] **Step 3: Write the implementation**

`workers/audio/config/separators.json`：

```json
{
  "schema_version": "lmdj.separators.v1",
  "separators": []
}
```

（真实 checkpoint 条目在 Phase 1A 随各 runner 落地：需要真实 artifact 的 SHA-256 与双平台 smoke，0A 无法诚实填写。）

`workers/audio/lmdj_audio_worker/separation/registry.py`：

```python
"""checkpoint registry（spec §6）：workers/audio/config/separators.json 的加载与门禁校验。"""
from __future__ import annotations

import json
import string
from dataclasses import dataclass
from pathlib import Path

REGISTRY_SCHEMA_VERSION = "lmdj.separators.v1"
ENTRY_STATUSES = ("experimental", "verified", "production")
ALLOWED_DEVICES = ("cpu", "mps")
COMMAND_PLACEHOLDERS = ("input", "output_dir", "device",
                        "checkpoint_dir", "seed", "repeat_id")
_REQUIRED_FIELDS = ("id", "family", "runner", "command", "source",
                    "artifact_sha256", "license", "stems", "sample_rate",
                    "channels", "devices", "inference", "env_lock_sha256",
                    "status")


class RegistryError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class SeparatorEntry:
    id: str
    family: str
    runner: str
    command: tuple[str, ...]
    source_url: str
    source_revision: str
    artifact_sha256: str
    license_code: str
    license_weights: str
    stems: tuple[str, ...]
    sample_rate: int
    channels: int
    devices: tuple[str, ...]
    inference: dict
    env_lock_sha256: str
    status: str


def _is_sha256(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def _command_placeholders(command: list) -> set[str]:
    names: set[str] = set()
    for part in command:
        for _, field_name, _, _ in string.Formatter().parse(part):
            if field_name:
                names.add(field_name)
    return names


def _validate_entry(raw: object, index: int) -> list[str]:
    prefix = f"separators[{index}]"
    if not isinstance(raw, dict):
        return [f"{prefix}: 必须是 object"]
    errors = []
    for f in _REQUIRED_FIELDS:
        if f not in raw:
            errors.append(f"{prefix}: 缺少必填字段 {f}")
    for f in raw:
        if f not in _REQUIRED_FIELDS:
            errors.append(f"{prefix}: 未知字段 {f!r}")
    if errors:
        return errors
    eid = raw["id"]
    if not isinstance(eid, str) or not eid:
        errors.append(f"{prefix}: id 必须是非空字符串")
    if not _is_sha256(raw["artifact_sha256"]):
        errors.append(f"{prefix}({eid}): artifact_sha256 必须是 64 位十六进制")
    if not _is_sha256(raw["env_lock_sha256"]):
        errors.append(f"{prefix}({eid}): env_lock_sha256 必须是 64 位十六进制")
    src = raw["source"]
    if not isinstance(src, dict) or not src.get("url") or not src.get("revision"):
        errors.append(f"{prefix}({eid}): source 必须含 url 与不可变 revision")
    lic = raw["license"]
    if not isinstance(lic, dict) or not lic.get("code") or not lic.get("weights"):
        errors.append(f"{prefix}({eid}): license 必须含 code 与 weights 说明")
    if raw["status"] not in ENTRY_STATUSES:
        errors.append(f"{prefix}({eid}): status 必须属于 {ENTRY_STATUSES}，"
                      f"收到 {raw['status']!r}")
    cmd = raw["command"]
    if (not isinstance(cmd, list) or not cmd
            or not all(isinstance(p, str) for p in cmd)):
        errors.append(f"{prefix}({eid}): command 必须是非空字符串列表")
    else:
        unknown = _command_placeholders(cmd) - set(COMMAND_PLACEHOLDERS)
        if unknown:
            errors.append(f"{prefix}({eid}): command 含未知占位符 {sorted(unknown)}，"
                          f"允许 {COMMAND_PLACEHOLDERS}")
    if (not isinstance(raw["stems"], list) or not raw["stems"]
            or not all(isinstance(s, str) for s in raw["stems"])):
        errors.append(f"{prefix}({eid}): stems 必须是非空字符串列表")
    devices = raw["devices"]
    if not isinstance(devices, list) or not devices:
        errors.append(f"{prefix}({eid}): devices 必须是非空列表")
    else:
        for d in devices:
            if d not in ALLOWED_DEVICES:
                errors.append(f"{prefix}({eid}): 不支持的设备 {d!r}"
                              f"（首轮只有 {ALLOWED_DEVICES}）")
    if not isinstance(raw["inference"], dict):
        errors.append(f"{prefix}({eid}): inference 推理配置必须是 object（spec §6）")
    return errors


def load_registry(path: Path) -> tuple[SeparatorEntry, ...]:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError([f"无法读取 registry {path}: {exc}"]) from exc
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        errors.append(f"registry schema_version 必须是 {REGISTRY_SCHEMA_VERSION!r}")
    raw_entries = data.get("separators") if isinstance(data, dict) else None
    if not isinstance(raw_entries, list):
        errors.append("registry 必须含 separators 列表")
        raise RegistryError(errors)
    for i, raw in enumerate(raw_entries):
        errors.extend(_validate_entry(raw, i))
    ids = [e["id"] for e in raw_entries if isinstance(e, dict) and "id" in e]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"registry: 重复 ID {dup!r}")
    if errors:
        raise RegistryError(errors)
    return tuple(
        SeparatorEntry(
            id=e["id"], family=e["family"], runner=e["runner"],
            command=tuple(e["command"]),
            source_url=e["source"]["url"], source_revision=e["source"]["revision"],
            artifact_sha256=e["artifact_sha256"],
            license_code=e["license"]["code"], license_weights=e["license"]["weights"],
            stems=tuple(e["stems"]), sample_rate=e["sample_rate"],
            channels=e["channels"], devices=tuple(e["devices"]),
            inference=e["inference"], env_lock_sha256=e["env_lock_sha256"],
            status=e["status"],
        )
        for e in raw_entries
    )


def benchmark_entries(entries: tuple[SeparatorEntry, ...]) -> tuple[SeparatorEntry, ...]:
    """internal benchmark 允许全部状态（spec §6 状态语义）。"""
    return tuple(entries)


def production_entries(entries: tuple[SeparatorEntry, ...]) -> tuple[SeparatorEntry, ...]:
    return tuple(e for e in entries if e.status == "production")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_registry.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/registry.py \
        workers/audio/config/separators.json \
        workers/audio/tests/separation/test_registry.py
git commit -m "feat(separation): add checkpoint registry loader with gate validation"
```

---

### Task 4: `separation/cache.py` — 权重缓存与原子下载

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/cache.py`
- Test: `workers/audio/tests/separation/test_cache.py`

**Interfaces:**
- Consumes: Task 3 的 `SeparatorEntry`
- Produces:
  - `class ChecksumError(RuntimeError)`
  - `sha256_file(path: Path) -> str`（Task 5 复用）
  - `cache_root() -> Path`（`LMDJ_MODEL_CACHE` env 覆盖，默认 `~/.cache/lmdj/separators`）
  - `checkpoint_dir(entry: SeparatorEntry) -> Path`（`cache_root()/<id>/<sha256>/`）
  - `ensure_checkpoint(entry: SeparatorEntry, fetcher: Callable[[str, Path], None] | None = None) -> Path`

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/separation/test_cache.py
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from lmdj_audio_worker.separation import cache
from lmdj_audio_worker.separation.registry import SeparatorEntry

PAYLOAD = b"fake checkpoint weights"
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()


def make_entry(sha: str = PAYLOAD_SHA) -> SeparatorEntry:
    return SeparatorEntry(
        id="htdemucs", family="demucs", runner="demucs",
        command=("run", "{input}", "{output_dir}"),
        source_url="https://example.com/weights/htdemucs.th",
        source_revision="v4.0.1", artifact_sha256=sha,
        license_code="MIT", license_weights="MIT",
        stems=("drums", "bass", "vocals", "other"),
        sample_rate=44100, channels=2, devices=("cpu",),
        inference={}, env_lock_sha256="d" * 64, status="verified")


@pytest.fixture(autouse=True)
def cache_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LMDJ_MODEL_CACHE", str(tmp_path / "cache"))
    return tmp_path / "cache"


def good_fetcher(url: str, dest: Path) -> None:
    dest.write_bytes(PAYLOAD)


def test_checkpoint_dir_layout(cache_env):
    entry = make_entry()
    assert cache.checkpoint_dir(entry) == cache_env / "htdemucs" / PAYLOAD_SHA


def test_download_verifies_and_places_artifact(cache_env):
    dest = cache.ensure_checkpoint(make_entry(), fetcher=good_fetcher)
    artifact = dest / "htdemucs.th"
    assert artifact.read_bytes() == PAYLOAD
    assert not list(cache_env.glob("tmp*"))  # 无残留临时文件


def test_checksum_mismatch_deletes_and_raises(cache_env):
    entry = make_entry(sha="0" * 64)
    with pytest.raises(cache.ChecksumError):
        cache.ensure_checkpoint(entry, fetcher=good_fetcher)
    assert not cache.checkpoint_dir(entry).exists()
    assert not list(cache_env.rglob("*.th"))


def test_cached_artifact_skips_fetch(cache_env):
    cache.ensure_checkpoint(make_entry(), fetcher=good_fetcher)

    def exploding_fetcher(url, dest):
        raise AssertionError("命中缓存时不得重新下载")

    dest = cache.ensure_checkpoint(make_entry(), fetcher=exploding_fetcher)
    assert (dest / "htdemucs.th").exists()


def test_fetcher_failure_propagates_and_cleans_tmp(cache_env):
    def broken(url, dest):
        dest.write_bytes(b"partial")
        raise OSError("connection reset")

    with pytest.raises(OSError):
        cache.ensure_checkpoint(make_entry(), fetcher=broken)
    assert not list(cache_env.glob("tmp*"))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_cache.py -q
```

Expected: FAIL（module 不存在）。

- [ ] **Step 3: Write the implementation**

```python
# workers/audio/lmdj_audio_worker/separation/cache.py
"""模型权重缓存（spec §6）：${LMDJ_MODEL_CACHE:-~/.cache/lmdj/separators}/<id>/<sha256>/。

下载 = 临时文件 + SHA-256 校验 + 原子 rename；checksum 不符立即删除，不得运行。
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from .registry import SeparatorEntry

DEFAULT_CACHE = "~/.cache/lmdj/separators"


class ChecksumError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_root() -> Path:
    return Path(os.environ.get("LMDJ_MODEL_CACHE", DEFAULT_CACHE)).expanduser()


def checkpoint_dir(entry: SeparatorEntry) -> Path:
    return cache_root() / entry.id / entry.artifact_sha256


def _artifact_name(entry: SeparatorEntry) -> str:
    return entry.source_url.rstrip("/").rsplit("/", 1)[-1] or "artifact"


def _urllib_fetch(url: str, dest: Path) -> None:
    urllib.request.urlretrieve(url, dest)  # noqa: S310 —— registry 已校验来源


def ensure_checkpoint(entry: SeparatorEntry,
                      fetcher: Callable[[str, Path], None] | None = None) -> Path:
    dest = checkpoint_dir(entry)
    artifact = dest / _artifact_name(entry)
    if artifact.exists():
        return dest
    fetch = fetcher or _urllib_fetch
    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="tmp", dir=root)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        fetch(entry.source_url, tmp)
        digest = sha256_file(tmp)
        if digest != entry.artifact_sha256:
            raise ChecksumError(
                f"{entry.id}: 下载 artifact SHA-256 {digest} "
                f"与 registry {entry.artifact_sha256} 不符，已删除")
        dest.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, artifact)
    finally:
        tmp.unlink(missing_ok=True)
    return dest
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_cache.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/cache.py \
        workers/audio/tests/separation/test_cache.py
git commit -m "feat(separation): add checkpoint weight cache with atomic verified download"
```

---

### Task 5: `separation/protocol.py` — runner 执行与失败合成

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/protocol.py`
- Test: `workers/audio/tests/separation/test_protocol.py`

**Interfaces:**
- Consumes: Task 1 contract（`SeparationResult`、`SeparatorInfo`、`SeparationError`、`write_result`、`load_result_file`、`ContractError`）、Task 3 `SeparatorEntry`、Task 4 `sha256_file`
- Produces:
  - `@dataclass(frozen=True) SeparationRequest(input_path: Path, output_dir: Path, device: str, seed: int = 0, repeat_id: int = 0)`
  - `build_command(entry: SeparatorEntry, request: SeparationRequest, checkpoint_dir: Path) -> list[str]`
  - `run_separator(entry, request, checkpoint_dir, timeout_sec: int = 3600) -> SeparationResult`（不因 runner 失败抛异常；失败以 `SeparationResult(status="failed")` 返回并落盘）
  - `STDERR_TAIL_CHARS = 2000`

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/separation/test_protocol.py
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from lmdj_audio_worker.separation import protocol
from lmdj_audio_worker.separation.registry import SeparatorEntry

# 各 fake runner 都是 `python -c SCRIPT output_dir` 形态
OK_SCRIPT = r"""
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
(out / "separation.json").write_text(json.dumps({
    "schema_version": "lmdj.separation.v1",
    "status": "completed", "source": "runner",
    "input_sha256": "a" * 64,
    "separator": {"id": "fake", "family": "demucs",
                  "checkpoint_sha256": "b" * 64, "runner_version": "0.1.0"},
    "requested_device": "cpu", "actual_device": "cpu",
    "stems": {k: f"stems/{k}.wav" for k in ("drums", "bass", "vocals", "other")},
    "audio": {"sample_rate": 44100, "channels": 2, "duration_seconds": 1.0},
    "performance": {"model_load_seconds": 0, "inference_seconds": 0,
                    "wall_seconds": 0, "peak_rss_bytes": 0,
                    "peak_device_memory_bytes": 0},
}))
"""
CRASH_SCRIPT = "import sys; print('boom', file=sys.stderr); sys.exit(3)"
KILL_SCRIPT = "import os; os.kill(os.getpid(), 9)"
HANG_SCRIPT = "import time; time.sleep(30)"
CORRUPT_SCRIPT = r"""
import sys
from pathlib import Path
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
(out / "separation.json").write_text("{not json")
"""


def make_entry(script: str) -> SeparatorEntry:
    return SeparatorEntry(
        id="fake", family="demucs", runner="demucs",
        command=(sys.executable, "-c", script, "{output_dir}"),
        source_url="https://example.com/fake.th", source_revision="r1",
        artifact_sha256="c" * 64, license_code="MIT", license_weights="MIT",
        stems=("drums", "bass", "vocals", "other"),
        sample_rate=44100, channels=2, devices=("cpu",),
        inference={}, env_lock_sha256="d" * 64, status="experimental")


@pytest.fixture()
def request_(tmp_path) -> protocol.SeparationRequest:
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"not really audio, sha input")
    return protocol.SeparationRequest(
        input_path=input_path, output_dir=tmp_path / "out", device="cpu")


def test_build_command_substitutes_placeholders(request_, tmp_path):
    entry = make_entry(OK_SCRIPT)
    cmd = protocol.build_command(entry, request_, tmp_path / "ckpt")
    assert cmd[-1] == str(request_.output_dir)


def test_runner_written_result_returned(request_, tmp_path):
    result = protocol.run_separator(make_entry(OK_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=30)
    assert result.status == "completed"
    assert result.source == "runner"


def test_crash_synthesizes_inference_failure(request_, tmp_path):
    result = protocol.run_separator(make_entry(CRASH_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=30)
    assert result.status == "failed"
    assert result.source == "orchestrator"
    assert result.error.category == "inference"
    assert result.error.exit_code == 3
    assert "boom" in result.error.stderr_tail
    # 合成记录必须落盘且 schema 合法
    on_disk = json.loads((request_.output_dir / "separation.json").read_text())
    assert on_disk["source"] == "orchestrator"


def test_sigkill_synthesizes_oom(request_, tmp_path):
    result = protocol.run_separator(make_entry(KILL_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=30)
    assert result.status == "failed"
    assert result.error.category == "oom"


def test_timeout_synthesizes_timeout(request_, tmp_path):
    result = protocol.run_separator(make_entry(HANG_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=1)
    assert result.status == "failed"
    assert result.error.category == "timeout"


def test_corrupt_result_with_zero_exit_synthesizes_invalid_stems(request_, tmp_path):
    result = protocol.run_separator(make_entry(CORRUPT_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=30)
    assert result.status == "failed"
    assert result.error.category == "invalid_stems"
    assert result.error.exit_code == 0


def test_synthesized_input_sha_matches_file(request_, tmp_path):
    import hashlib
    result = protocol.run_separator(make_entry(CRASH_SCRIPT), request_,
                                    tmp_path / "ckpt", timeout_sec=30)
    expected = hashlib.sha256(request_.input_path.read_bytes()).hexdigest()
    assert result.input_sha256 == expected
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_protocol.py -q
```

Expected: FAIL（module 不存在）。

- [ ] **Step 3: Write the implementation**

```python
# workers/audio/lmdj_audio_worker/separation/protocol.py
"""SeparatorRunner 协议（spec §5、§10）。

orchestrator 不 import 任何模型框架：按 registry 条目模板拼命令、子进程执行、
读取 separation.json。失败记录两级产生——runner 自写可捕获异常；文件缺失/损坏/
timeout/SIGKILL 由这里合成规范化失败记录（source="orchestrator"）并落盘。
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .cache import sha256_file
from .contract import (ContractError, SeparationError, SeparationResult,
                       SeparatorInfo, load_result_file, write_result)
from .registry import SeparatorEntry

STDERR_TAIL_CHARS = 2000


@dataclass(frozen=True)
class SeparationRequest:
    input_path: Path
    output_dir: Path
    device: str
    seed: int = 0
    repeat_id: int = 0


def build_command(entry: SeparatorEntry, request: SeparationRequest,
                  checkpoint_dir: Path) -> list[str]:
    mapping = {
        "input": str(request.input_path),
        "output_dir": str(request.output_dir),
        "device": request.device,
        "checkpoint_dir": str(checkpoint_dir),
        "seed": str(request.seed),
        "repeat_id": str(request.repeat_id),
    }
    # 不用 str.format：command 元素可能含字面量 {}（如内嵌脚本/JSON），只做 {key} 精确替换
    result = []
    for part in entry.command:
        for key, value in mapping.items():
            part = part.replace(f"{{{key}}}", value)
        result.append(part)
    return result


def _tail(stream: object) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        stream = stream.decode("utf-8", errors="replace")
    return str(stream)[-STDERR_TAIL_CHARS:]


def _synthesize(entry: SeparatorEntry, request: SeparationRequest,
                category: str, exit_code: int | None, stderr_tail: str,
                elapsed: float) -> SeparationResult:
    result = SeparationResult(
        status="failed", source="orchestrator",
        input_sha256=sha256_file(request.input_path),
        separator=SeparatorInfo(
            id=entry.id, family=entry.family,
            checkpoint_sha256=entry.artifact_sha256,
            runner_version="unknown"),  # runner 已消失，版本不可知
        requested_device=request.device,
        error=SeparationError(
            category=category, exit_code=exit_code, stage="runner",
            stderr_tail=stderr_tail, elapsed_seconds=round(elapsed, 3)),
    )
    write_result(request.output_dir / "separation.json", result)
    return result


def run_separator(entry: SeparatorEntry, request: SeparationRequest,
                  checkpoint_dir: Path, timeout_sec: int = 3600) -> SeparationResult:
    request.output_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_command(entry, request, checkpoint_dir)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        return _synthesize(entry, request, "timeout", None,
                           _tail(exc.stderr), time.monotonic() - t0)
    elapsed = time.monotonic() - t0

    result_path = request.output_dir / "separation.json"
    try:
        result = load_result_file(result_path)
    except ContractError:
        result = None
    if result is not None and result.source == "runner":
        return result

    # 文件缺失/损坏/schema 不合法 → 按退出码合成（spec §5 orchestrator 合成）
    if proc.returncode in (-9, 137):
        category = "oom"          # SIGKILL：spec §5 的典型合成场景
    elif proc.returncode != 0:
        category = "inference"
    else:
        category = "invalid_stems"  # 退出 0 但结果不合法 = 契约违反
    return _synthesize(entry, request, category, proc.returncode,
                       _tail(proc.stderr), elapsed)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/ -q
```

Expected: 全部 PASS。timeout 测试会等 1 秒，正常。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/protocol.py \
        workers/audio/tests/separation/test_protocol.py
git commit -m "feat(separation): run separator subprocess with orchestrator-synthesized failures"
```

---

### Task 6: `pipeline_from_stems/` 模块迁移 + parity constraints

**Files:**
- Create: `workers/audio/config/parity-constraints.txt`
- Create: `workers/audio/lmdj_audio_worker/pipeline_from_stems/__init__.py`
- Create（逐字节拷贝，勿手改）: `workers/audio/lmdj_audio_worker/pipeline_from_stems/{config,audio_utils,loop_finder,slicer,sequencer,validate}.py`
- Modify: `workers/audio/pyproject.toml`（补齐 `pfs` extra）

**Interfaces:**
- Consumes: demo 源文件 `references/demos/lmdj-song-pipeline/song_pipeline/*.py`（全部相对 import，拷贝后作为子包直接工作）
- Produces: `lmdj_audio_worker.pipeline_from_stems.{config.PipelineConfig, audio_utils, loop_finder, slicer, sequencer, validate}` —— 与 demo `song_pipeline` 同名同签名（Task 7/8/11 依赖）

- [ ] **Step 1: 写入 parity constraints（单一版本锁来源，spec §3.1）**

`workers/audio/config/parity-constraints.txt`：

```text
# Parity 关键库版本锁——demo baseline venv 与 pipeline-from-stems venv 的单一来源。
# 基准：references/demos/lmdj-song-pipeline/.venv（Python 3.12）2026-07-15 pip freeze。
# 修改任何 pin 都会使 frozen-stems parity 基线失效，必须重跑 scripts/dev.sh parity。
audioread==3.1.0
decorator==5.3.1
joblib==1.5.3
librosa==0.11.0
llvmlite==0.48.0
mido==1.3.3
msgpack==1.2.1
numba==0.66.0
numpy==1.26.4
packaging==26.2
platformdirs==4.10.0
pooch==1.9.0
pretty_midi==0.2.11
scikit-learn==1.9.0
scipy==1.17.1
six==1.17.0
soundfile==0.14.0
soxr==1.1.0
threadpoolctl==3.6.0
```

- [ ] **Step 2: 逐字节拷贝阶段 3–6 模块（不拷 stems.py / generate.py / pipeline.py）**

```bash
cd <repo-root>
mkdir -p workers/audio/lmdj_audio_worker/pipeline_from_stems
for m in config audio_utils loop_finder slicer sequencer validate; do
  cp references/demos/lmdj-song-pipeline/song_pipeline/$m.py \
     workers/audio/lmdj_audio_worker/pipeline_from_stems/$m.py
done
```

`workers/audio/lmdj_audio_worker/pipeline_from_stems/__init__.py`：

```python
"""Pipeline 阶段 3–6（beat/loop/slicer/sequencer/validation），LMDJ-owned。

config/audio_utils/loop_finder/slicer/sequencer/validate 六个模块逐字节迁移自
references/demos/lmdj-song-pipeline/song_pipeline/（demo 保持冻结，只作 parity
基线）。本子包运行在专用 venv（workers/audio/.venv-pfs）中、以子进程调用；
DSP 依赖版本由 workers/audio/config/parity-constraints.txt 锁定（spec §3.1）。
任何行为改动必须先通过 scripts/dev.sh parity（spec §3.2）。
"""
```

- [ ] **Step 3: 验证拷贝逐字节一致且无 torch/demucs 依赖**

```bash
cd <repo-root>
for m in config audio_utils loop_finder slicer sequencer validate; do
  diff references/demos/lmdj-song-pipeline/song_pipeline/$m.py \
       workers/audio/lmdj_audio_worker/pipeline_from_stems/$m.py
done
grep -rn "torch\|demucs" workers/audio/lmdj_audio_worker/pipeline_from_stems/ || echo "clean"
```

Expected: diff 无输出；grep 输出 `clean`。

- [ ] **Step 4: 补齐 `pfs` extra 并按 constraints 重装测试 venv**

`workers/audio/pyproject.toml` 的 `pfs` extra 改为：

```toml
pfs = [
  "numpy",
  "soundfile",
  "librosa",
  "scikit-learn",
  "pretty_midi",
]
```

```bash
cd workers/audio
.venv/bin/pip install -e ".[test,pfs]" -c config/parity-constraints.txt
.venv/bin/python -c "from lmdj_audio_worker.pipeline_from_stems import config, audio_utils, loop_finder, slicer, sequencer, validate; print('import ok')"
.venv/bin/python -m pytest tests/ -q
```

Expected: `import ok`；全部测试 PASS。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/config/parity-constraints.txt \
        workers/audio/lmdj_audio_worker/pipeline_from_stems \
        workers/audio/pyproject.toml
git commit -m "feat(pfs): migrate pipeline stages 3-6 verbatim with pinned parity constraints"
```

---

### Task 7: `pipeline_from_stems/runner.py` + `__main__.py` — 阶段 3–6 编排

**Files:**
- Create: `workers/audio/lmdj_audio_worker/pipeline_from_stems/runner.py`
- Create: `workers/audio/lmdj_audio_worker/pipeline_from_stems/__main__.py`
- Test: `workers/audio/tests/pipeline_from_stems/__init__.py`（空）
- Test: `workers/audio/tests/pipeline_from_stems/test_runner.py`

**Interfaces:**
- Consumes: Task 6 迁移的六个模块
- Produces:
  - `LEGACY_STEMS = ("drums", "bass", "melody")`
  - `load_legacy_stems(stems_dir: Path, sr: int) -> dict[str, np.ndarray]`（缺轨抛 `FileNotFoundError`）
  - `run_from_stems(stems_dir: Path, out_root: Path, song_id: str, cfg: PipelineConfig | None = None) -> dict`（返回 report dict，写 `{out_root}/{song_id}/` 包）
  - CLI：`python -m lmdj_audio_worker.pipeline_from_stems --stems DIR --out DIR --song-id ID`（`passed`/`rejected` → exit 0；`failed` → exit 1）

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/pipeline_from_stems/test_runner.py
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
```

（`run_from_stems` 的完整功能验证由 parity（Task 12）承担——它跑真实 testsong stems；这里只测入口与错误边界，不复测 librosa 行为。）

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/pipeline_from_stems/ -q
```

Expected: FAIL（module 不存在）。

- [ ] **Step 3: Write the implementation**

`runner.py` —— 阶段 3–6 逐行取自 demo `pipeline.py::run_pipeline`（第 111–195 行），仅把阶段 2 换成读目录；不要"顺手改进"：

```python
# workers/audio/lmdj_audio_worker/pipeline_from_stems/runner.py
"""从已有 legacy stems（drums/bass/melody）运行 pipeline 阶段 3–6。

阶段 3–6 的编排逐行来自 demo pipeline.py::run_pipeline（stage 2 分轨替换为
直接读 stems 目录）。行为改动必须先过 scripts/dev.sh parity。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np

from . import audio_utils as au
from . import loop_finder, sequencer, slicer, validate
from .config import PipelineConfig

log = logging.getLogger(__name__)

LEGACY_STEMS = ("drums", "bass", "melody")


def load_legacy_stems(stems_dir: Path, sr: int) -> dict[str, np.ndarray]:
    stems_dir = Path(stems_dir)
    expected = {k: stems_dir / f"{k}.wav" for k in LEGACY_STEMS}
    missing = [k for k, p in expected.items() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"stems 目录缺少 {missing}（需要 {list(LEGACY_STEMS)}）: {stems_dir}")
    return {k: au.load_wav(p, sr)[0] for k, p in expected.items()}


def run_from_stems(stems_dir: Path, out_root: Path, song_id: str,
                   cfg: PipelineConfig | None = None) -> dict:
    cfg = cfg or PipelineConfig()
    t0 = time.time()
    out_dir = Path(out_root) / song_id
    out_dir.mkdir(parents=True, exist_ok=True)
    sr = cfg.sample_rate

    # 阶段2 替换：直接读 stems 目录（demo: stems.separate）
    stem_audio = load_legacy_stems(stems_dir, sr)
    mix_mono = sum(au.to_mono(a) for a in stem_audio.values())

    # 阶段3 候选窗口 —— 以下与 demo run_pipeline 逐行一致
    stems_mono = {k: au.to_mono(a) for k, a in stem_audio.items()}
    windows = loop_finder.find_loop_windows(mix_mono, stems_mono, sr, cfg)

    best = None  # (score, artifacts)
    attempts = []
    for wi, window in enumerate(windows[: cfg.n_candidate_windows]):
        try:
            loops = {k: loop_finder.cut_loop(a, sr, window, cfg)
                     for k, a in stem_audio.items()}
            loop_mix = sum(loops.values())

            # 阶段4 切片
            drums, longs = slicer.slice_all(loops, sr, window, cfg)
            samples = drums.samples + longs

            # 阶段5 MIDI
            grid = window.grid_times(cfg.grid_per_beat) - window.start
            notes = sequencer.drum_notes(drums, grid, cfg)
            notes += sequencer.long_notes(longs, loops, sr, grid, cfg)

            # 阶段6 验收
            score, rendered = validate.validate(notes, samples, loop_mix, sr, cfg)
        except RuntimeError as e:
            log.warning("窗口 %d (%.2fs) 失败：%s", wi, window.start, e)
            attempts.append({"window": wi, "start": round(window.start, 2),
                             "error": str(e)})
            continue

        attempts.append({"window": wi, "start": round(window.start, 2),
                         "score": round(score, 4)})
        artifacts = (window, samples, notes, loop_mix, rendered)
        if best is None or score > best[0]:
            best = (score, artifacts)
        if score >= cfg.similarity_threshold:
            break

    if best is None:
        report = {"song_id": song_id, "status": "failed",
                  "error": "所有候选窗口均无法切片", "attempts": attempts}
        (out_dir / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False))
        return report

    score, (window, samples, notes, loop_mix, rendered) = best
    passed = score >= cfg.similarity_threshold

    # 落盘
    for s in samples:
        au.write_wav(out_dir / "samples" / f"{s.name}.wav", s.audio, sr)
    sequencer.write_chart(notes, window, out_dir / "chart.mid")
    lanes = sequencer.write_lanes(samples, window, cfg, out_dir / "lanes.json")
    au.write_wav(out_dir / "loop_preview.wav", loop_mix, sr)
    au.write_wav(out_dir / "render_preview.wav", rendered, sr)

    report = {
        "song_id": song_id,
        "status": "passed" if passed else "rejected",
        "score": round(score, 4),
        "threshold": cfg.similarity_threshold,
        "bpm": round(window.bpm, 2),
        "loop_start_sec": round(window.start, 3),
        "loop_seconds": round(window.end - window.start, 3),
        "n_samples": len(samples),
        "n_notes": len(notes),
        "lanes": lanes["lanes"],
        "attempts": attempts,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False))
    log.info("song %s %s score=%.3f (%.1fs)", song_id, report["status"],
             score, report["elapsed_sec"])
    return report
```

`__main__.py`：

```python
# workers/audio/lmdj_audio_worker/pipeline_from_stems/__main__.py
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import PipelineConfig
from .runner import run_from_stems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        "pipeline-from-stems",
        description="legacy stems (drums/bass/melody) -> pipeline 阶段 3-6 -> 包目录")
    parser.add_argument("--stems", type=Path, required=True,
                        help="含 drums.wav/bass.wav/melody.wav 的目录")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--song-id", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run_from_stems(args.stems, args.out, args.song_id, PipelineConfig())
    return 0 if report.get("status") in ("passed", "rejected") else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/pipeline_from_stems/ -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/pipeline_from_stems/runner.py \
        workers/audio/lmdj_audio_worker/pipeline_from_stems/__main__.py \
        workers/audio/tests/pipeline_from_stems
git commit -m "feat(pfs): add run_from_stems orchestration and CLI entry"
```

---

### Task 8: `pipeline_from_stems/compat.py` — canonical → legacy 兼容映射

**Files:**
- Create: `workers/audio/lmdj_audio_worker/pipeline_from_stems/compat.py`
- Test: `workers/audio/tests/pipeline_from_stems/test_compat.py`

**Interfaces:**
- Consumes: Task 6 的 `config.PipelineConfig`
- Produces: `map_canonical_to_legacy(canonical_dir: Path, legacy_dir: Path, cfg: PipelineConfig | None = None) -> dict[str, Path]`（返回 `{"drums"|"bass"|"melody": 写出的路径}`）

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/pipeline_from_stems/test_compat.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lmdj_audio_worker.pipeline_from_stems import compat
from lmdj_audio_worker.pipeline_from_stems.config import PipelineConfig

SR = 44100
PCM16_TOL = 2 / 32768  # 兼容层沿用 demo 的 sf.write 默认 subtype（PCM_16）


def write_canonical(tmp_path: Path, values: dict[str, float]) -> Path:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    for name in ("drums", "bass", "vocals", "other"):
        data = np.full((SR, 2), values.get(name, 0.1), dtype=np.float32)
        sf.write(canonical / f"{name}.wav", data, SR, subtype="FLOAT")
    return canonical


def test_melody_is_vocals_plus_other(tmp_path):
    canonical = write_canonical(tmp_path, {"vocals": 0.2, "other": 0.3})
    out = compat.map_canonical_to_legacy(canonical, tmp_path / "legacy")
    melody, _ = sf.read(out["melody"], always_2d=True)
    assert np.allclose(melody, 0.5, atol=PCM16_TOL)
    assert set(out) == {"drums", "bass", "melody"}


def test_peak_over_one_scaled_to_one(tmp_path):
    canonical = write_canonical(tmp_path, {"vocals": 0.9, "other": 0.9})
    out = compat.map_canonical_to_legacy(canonical, tmp_path / "legacy")
    melody, _ = sf.read(out["melody"], always_2d=True)
    assert np.abs(melody).max() <= 1.0 + PCM16_TOL
    assert np.allclose(melody, 1.0, atol=PCM16_TOL)  # 1.8 缩放到 1.0


def test_peak_under_one_untouched(tmp_path):
    canonical = write_canonical(tmp_path, {"drums": 0.4})
    out = compat.map_canonical_to_legacy(canonical, tmp_path / "legacy")
    drums, _ = sf.read(out["drums"], always_2d=True)
    assert np.allclose(drums, 0.4, atol=PCM16_TOL)


def test_vocals_strategy_drop_rejected(tmp_path):
    canonical = write_canonical(tmp_path, {})
    cfg = PipelineConfig(vocals_strategy="drop")
    with pytest.raises(ValueError, match="merge"):
        compat.map_canonical_to_legacy(canonical, tmp_path / "legacy", cfg)


def test_same_dir_rejected(tmp_path):
    canonical = write_canonical(tmp_path, {})
    with pytest.raises(ValueError, match="同一"):
        compat.map_canonical_to_legacy(canonical, canonical)


def test_missing_canonical_stem_rejected(tmp_path):
    canonical = write_canonical(tmp_path, {})
    (canonical / "other.wav").unlink()
    with pytest.raises(FileNotFoundError, match="other"):
        compat.map_canonical_to_legacy(canonical, tmp_path / "legacy")


def test_originals_not_modified(tmp_path):
    canonical = write_canonical(tmp_path, {"vocals": 0.9, "other": 0.9})
    before = (canonical / "vocals.wav").read_bytes()
    compat.map_canonical_to_legacy(canonical, tmp_path / "legacy")
    assert (canonical / "vocals.wav").read_bytes() == before
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/pipeline_from_stems/test_compat.py -q
```

Expected: FAIL（module 不存在）。

- [ ] **Step 3: Write the implementation**

```python
# workers/audio/lmdj_audio_worker/pipeline_from_stems/compat.py
"""canonical 四轨 → legacy 三轨兼容映射（spec §5）。

drums/bass 原样；melody = vocals + other（等价于 demo 的 vocals_strategy="merge"，
v1 只支持 merge，遇 drop 显式报错）。沿用旧实现（demo stems.py）的
"单轨峰值超过 1.0 时缩放到 1.0" 规则。canonical 原始分轨保持未归一化、
不被改写；legacy 输出写到独立目录（两组音频不得复用同一文件）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from .config import PipelineConfig

CANONICAL_STEMS = ("drums", "bass", "vocals", "other")


def map_canonical_to_legacy(canonical_dir: Path, legacy_dir: Path,
                            cfg: PipelineConfig | None = None) -> dict[str, Path]:
    cfg = cfg or PipelineConfig()
    if cfg.vocals_strategy != "merge":
        raise ValueError(
            f"v1 兼容层只支持 vocals_strategy='merge'，收到 {cfg.vocals_strategy!r}"
            "（spec §5：不得静默按 merge 处理）")
    canonical_dir = Path(canonical_dir)
    legacy_dir = Path(legacy_dir)
    if legacy_dir.resolve() == canonical_dir.resolve():
        raise ValueError("legacy 输出不得与 canonical 是同一目录（不得复用同一文件）")

    arrays: dict[str, np.ndarray] = {}
    rates: set[int] = set()
    for name in CANONICAL_STEMS:
        path = canonical_dir / f"{name}.wav"
        if not path.exists():
            raise FileNotFoundError(f"canonical stems 缺少 {name}.wav: {canonical_dir}")
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        arrays[name] = data
        rates.add(sr)
    if len(rates) != 1:
        raise ValueError(f"canonical stems 采样率不一致: {sorted(rates)}")
    if len(arrays["vocals"]) != len(arrays["other"]):
        raise ValueError("vocals 与 other 长度不一致，无法合成 melody")
    sr = rates.pop()

    legacy = {
        "drums": arrays["drums"],
        "bass": arrays["bass"],
        "melody": arrays["vocals"] + arrays["other"],
    }
    legacy_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for name, data in legacy.items():
        peak = float(np.abs(data).max()) if len(data) else 0.0
        if peak > 1.0:
            data = data / peak
        target = legacy_dir / f"{name}.wav"
        sf.write(target, data, sr)  # demo 同款默认 subtype（WAV → PCM_16）
        out[name] = target
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/pipeline_from_stems/ -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/pipeline_from_stems/compat.py \
        workers/audio/tests/pipeline_from_stems/test_compat.py
git commit -m "feat(pfs): map canonical four stems to legacy layout with merge-only guard"
```

---

### Task 9: `envcheck.py` — 环境指纹校验

**Files:**
- Create: `workers/audio/lmdj_audio_worker/envcheck.py`
- Test: `workers/audio/tests/test_envcheck.py`

**Interfaces:**
- Consumes: 无（stdlib only，主包内、零依赖）
- Produces:
  - `read_constraints(path: Path) -> dict[str, str]`（非 `==` pin 抛 `ValueError`；包名统一 lower + `_`→`-`）
  - `check(pins: dict[str, str], installed: dict[str, str], label: str) -> list[str]`（纯函数）
  - `freeze(venv: Path) -> dict[str, str]` / `python_version(venv: Path) -> str`（subprocess 薄封装）
  - CLI：`python -m lmdj_audio_worker.envcheck VENV [VENV ...] --constraints FILE`（不符 exit 1）

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/test_envcheck.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/test_envcheck.py -q
```

Expected: FAIL（module 不存在）。

- [ ] **Step 3: Write the implementation**

```python
# workers/audio/lmdj_audio_worker/envcheck.py
"""parity 环境指纹校验（spec §3.2）：venv 的关键库版本必须与 constraints 完全一致。

指纹不符即中止，不得带病比较。stdlib only，可在任意 venv 中运行。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _norm(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def read_constraints(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, version = line.partition("==")
        if not sep or not version:
            raise ValueError(f"constraints 只允许 == 精确 pin：{line!r}")
        pins[_norm(name)] = version.strip()
    return pins


def check(pins: dict[str, str], installed: dict[str, str],
          label: str) -> list[str]:
    errors: list[str] = []
    for name, version in sorted(pins.items()):
        got = installed.get(name)
        if got is None:
            errors.append(f"{label}: 缺少 {name}=={version}")
        elif got != version:
            errors.append(f"{label}: {name}=={got}，constraints 要求 {version}")
    return errors


def freeze(venv: Path) -> dict[str, str]:
    proc = subprocess.run([str(venv / "bin" / "pip"), "freeze"],
                          capture_output=True, text=True, check=True)
    installed: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        name, sep, version = line.partition("==")
        if sep:
            installed[_norm(name)] = version.strip()
    return installed


def python_version(venv: Path) -> str:
    proc = subprocess.run(
        [str(venv / "bin" / "python"), "-c",
         "import sys; print('%d.%d' % sys.version_info[:2])"],
        capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("envcheck", description=__doc__)
    parser.add_argument("venvs", nargs="+", type=Path)
    parser.add_argument("--constraints", type=Path, required=True)
    args = parser.parse_args(argv)

    pins = read_constraints(args.constraints)
    failures: list[str] = []
    for venv in args.venvs:
        failures += check(pins, freeze(venv), str(venv))
    versions = {str(v): python_version(v) for v in args.venvs}
    if len(set(versions.values())) > 1:
        failures.append(f"python minor 版本不一致: {versions}")
    if failures:
        print("环境指纹校验失败：", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"环境指纹 OK: {', '.join(str(v) for v in args.venvs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/test_envcheck.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/envcheck.py workers/audio/tests/test_envcheck.py
git commit -m "feat(pfs): add environment fingerprint verification against parity constraints"
```

---

### Task 10: 主包 `PipelineFromStemsRunner` 子进程封装

**Files:**
- Modify: `workers/audio/lmdj_audio_worker/runner.py`（追加类；现有 `DemoPipelineRunner`、`PipelineRunError` 不动）
- Test: `workers/audio/tests/test_pfs_runner.py`

**Interfaces:**
- Consumes: 现有 `PipelineRunError`（`runner.py:10`）、`STDERR_TAIL_CHARS`（`runner.py:7`）；Task 7 的 CLI 入口
- Produces: `PipelineFromStemsRunner(worker_dir: Path | None = None, timeout_sec: int = 600)`，方法 `command(stems_dir, out_dir, song_id) -> list[str]`、`run(stems_dir: Path, out_dir: Path, song_id: str) -> Path`（返回包目录；失败抛 `PipelineRunError`）

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/test_pfs_runner.py
from __future__ import annotations

import stat
from pathlib import Path

import pytest

from lmdj_audio_worker.runner import PipelineFromStemsRunner, PipelineRunError


def make_fake_venv(tmp_path: Path, script_body: str) -> Path:
    """伪 .venv-pfs：bin/python 是一个 shell 脚本。"""
    bin_dir = tmp_path / ".venv-pfs" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text(f"#!/bin/sh\n{script_body}\n")
    python.chmod(python.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def test_command_shape(tmp_path):
    runner = PipelineFromStemsRunner(worker_dir=tmp_path)
    cmd = runner.command(Path("/s"), Path("/o"), "song1")
    assert cmd[1:3] == ["-m", "lmdj_audio_worker.pipeline_from_stems"]
    assert "--song-id" in cmd and "song1" in cmd


def test_missing_venv_raises_with_hint(tmp_path):
    runner = PipelineFromStemsRunner(worker_dir=tmp_path)
    with pytest.raises(PipelineRunError, match="setup-pfs"):
        runner.run(tmp_path, tmp_path / "out", "song1")


def test_run_returns_package_dir(tmp_path):
    # 伪 python：在 out/song1 写出 lanes.json 后退出 0
    worker_dir = make_fake_venv(tmp_path, (
        'while [ "$1" != "--out" ]; do shift; done; out="$2"\n'
        'mkdir -p "$out/song1" && echo "{}" > "$out/song1/lanes.json"'))
    runner = PipelineFromStemsRunner(worker_dir=worker_dir)
    package = runner.run(tmp_path / "stems", tmp_path / "out", "song1")
    assert package == tmp_path / "out" / "song1"


def test_nonzero_exit_raises_with_stderr(tmp_path):
    worker_dir = make_fake_venv(tmp_path, 'echo "kaput" >&2; exit 1')
    runner = PipelineFromStemsRunner(worker_dir=worker_dir)
    with pytest.raises(PipelineRunError) as exc:
        runner.run(tmp_path / "stems", tmp_path / "out", "song1")
    assert "kaput" in exc.value.stderr_tail
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/test_pfs_runner.py -q
```

Expected: FAIL（`ImportError: cannot import name 'PipelineFromStemsRunner'`）。

- [ ] **Step 3: Write the implementation**

追加到 `workers/audio/lmdj_audio_worker/runner.py` 末尾：

```python
class PipelineFromStemsRunner:
    """子进程调用 pipeline-from-stems（专用 .venv-pfs，DSP 依赖隔离，spec §3.1）。"""

    def __init__(self, worker_dir: Path | None = None, timeout_sec: int = 600) -> None:
        self.worker_dir = (worker_dir or Path(__file__).resolve().parent.parent)
        self.timeout_sec = timeout_sec

    @property
    def python(self) -> Path:
        return self.worker_dir / ".venv-pfs" / "bin" / "python"

    def command(self, stems_dir: Path, out_dir: Path, song_id: str) -> list[str]:
        return [str(self.python), "-m", "lmdj_audio_worker.pipeline_from_stems",
                "--stems", str(stems_dir), "--out", str(out_dir),
                "--song-id", song_id]

    def run(self, stems_dir: Path, out_dir: Path, song_id: str) -> Path:
        if not self.python.exists():
            raise PipelineRunError(
                f"pfs venv missing at {self.python} — "
                "先在仓库根目录运行: scripts/dev.sh setup-pfs")
        try:
            proc = subprocess.run(
                self.command(stems_dir, out_dir, song_id),
                capture_output=True, text=True, timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired as error:
            raise PipelineRunError(
                f"pipeline-from-stems timed out after {self.timeout_sec}s") from error
        if proc.returncode != 0:
            raise PipelineRunError(
                f"pipeline-from-stems exited with code {proc.returncode}",
                stderr_tail=(proc.stderr or "")[-STDERR_TAIL_CHARS:],
            )
        package_dir = out_dir / song_id
        if not (package_dir / "lanes.json").exists():
            raise PipelineRunError(
                f"pipeline-from-stems produced no lanes.json in {package_dir}")
        return package_dir
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q
```

Expected: 全部 PASS（含既有 runner/job/status/cli 测试）。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/runner.py workers/audio/tests/test_pfs_runner.py
git commit -m "feat(worker): add PipelineFromStemsRunner subprocess wrapper"
```

---

### Task 11: `pipeline_from_stems/parity.py` — parity 比较器

**Files:**
- Create: `workers/audio/lmdj_audio_worker/pipeline_from_stems/parity.py`
- Test: `workers/audio/tests/pipeline_from_stems/test_parity.py`

**Interfaces:**
- Consumes: 两个包目录（demo 输出布局：`report.json`、`lanes.json`、`chart.mid`、`loop_preview.wav`、`render_preview.wav`、`samples/*.wav`）
- Produces:
  - 常量 `SCORE_TOL = 1e-4`、`AUDIO_TOL = 1e-5`、`MIDI_TIME_TOL = 1e-6`
  - `compare_reports(old: dict, new: dict) -> list[str]` / `compare_lanes(old_path, new_path) -> list[str]` / `compare_midi(old_path, new_path) -> list[str]` / `compare_audio(old_dir, new_dir) -> list[str]`
  - `compare_packages(old_dir: Path, new_dir: Path) -> list[str]`（汇总）
  - CLI：`python -m lmdj_audio_worker.pipeline_from_stems.parity OLD_DIR NEW_DIR`（差异 → exit 1）

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/pipeline_from_stems/test_parity.py
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from lmdj_audio_worker.pipeline_from_stems import parity

SR = 44100


def make_package(root: Path, score: float = 0.61) -> Path:
    root.mkdir(parents=True)
    (root / "report.json").write_text(json.dumps({
        "song_id": "t", "status": "passed", "score": score, "threshold": 0.5,
        "bpm": 90.0, "loop_start_sec": 1.234, "loop_seconds": 10.667,
        "n_samples": 2, "n_notes": 3,
        "lanes": [{"lane": 0, "name": "kick"}, {"lane": 1, "name": "bass"}],
        "attempts": [], "elapsed_sec": 5.0}))
    (root / "lanes.json").write_text(json.dumps({
        "bpm": 90.0, "bars": 4.0, "beats": 16, "loop_seconds": 10.667,
        "lanes": [{"lane": 0, "name": "kick", "kind": "drum", "pitch": 36,
                   "sample": "samples/kick.wav"},
                  {"lane": 1, "name": "bass", "kind": "long", "pitch": 48,
                   "sample": "samples/bass.wav"}]}))
    pm = pretty_midi.PrettyMIDI(initial_tempo=90.0)
    inst = pretty_midi.Instrument(program=0, name="lmdj-chart")
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=0.0, end=0.1))
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=48, start=0.5, end=1.0))
    pm.instruments.append(inst)
    pm.write(str(root / "chart.mid"))
    rng = np.random.default_rng(7)
    for rel in ("loop_preview.wav", "render_preview.wav",
                "samples/kick.wav", "samples/bass.wav"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, rng.uniform(-0.5, 0.5, (SR, 2)).astype(np.float32),
                 SR, subtype="FLOAT")
    return root


@pytest.fixture()
def twin_packages(tmp_path):
    old = make_package(tmp_path / "old")
    new = tmp_path / "new"
    shutil.copytree(old, new)
    return old, new


def test_identical_packages_pass(twin_packages):
    old, new = twin_packages
    assert parity.compare_packages(old, new) == []


def test_score_within_tolerance_passes(twin_packages):
    old, new = twin_packages
    report = json.loads((new / "report.json").read_text())
    report["score"] = 0.61005  # |Δ|=5e-5 ≤ 1e-4
    (new / "report.json").write_text(json.dumps(report))
    assert parity.compare_packages(old, new) == []


def test_score_beyond_tolerance_fails(twin_packages):
    old, new = twin_packages
    report = json.loads((new / "report.json").read_text())
    report["score"] = 0.62
    (new / "report.json").write_text(json.dumps(report))
    assert any("score" in e for e in parity.compare_packages(old, new))


def test_lane_name_mismatch_fails(twin_packages):
    old, new = twin_packages
    lanes = json.loads((new / "lanes.json").read_text())
    lanes["lanes"][0]["name"] = "snare"
    (new / "lanes.json").write_text(json.dumps(lanes))
    assert any("lanes" in e for e in parity.compare_packages(old, new))


def test_audio_perturbation_fails(twin_packages):
    old, new = twin_packages
    data, sr = sf.read(new / "samples" / "kick.wav", dtype="float32",
                       always_2d=True)
    data[100, 0] += 1e-3  # 超过 1e-5 容差
    sf.write(new / "samples" / "kick.wav", data, sr, subtype="FLOAT")
    assert any("kick" in e for e in parity.compare_packages(old, new))


def test_sample_set_mismatch_fails(twin_packages):
    old, new = twin_packages
    (new / "samples" / "bass.wav").unlink()
    assert any("bass" in e for e in parity.compare_packages(old, new))


def test_midi_note_mismatch_fails(twin_packages):
    old, new = twin_packages
    pm = pretty_midi.PrettyMIDI(initial_tempo=90.0)
    inst = pretty_midi.Instrument(program=0, name="lmdj-chart")
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=38, start=0.0, end=0.1))
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=48, start=0.5, end=1.0))
    pm.instruments.append(inst)
    pm.write(str(new / "chart.mid"))
    assert any("MIDI" in e for e in parity.compare_packages(old, new))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/pipeline_from_stems/test_parity.py -q
```

Expected: FAIL（module 不存在）。

- [ ] **Step 3: Write the implementation**

```python
# workers/audio/lmdj_audio_worker/pipeline_from_stems/parity.py
"""frozen-stems parity 比较（spec §3.2）：旧 demo 输出 vs PipelineFromStems 输出。

比较项：report 字段（除耗时）、validation score |Δ|≤1e-4、lanes.json、
标准化 MIDI note events、preview/samples 音频（长度一致、最大绝对差 ≤1e-5）。
在 .venv-pfs 中运行（需要 numpy/soundfile/pretty_midi）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

SCORE_TOL = 1e-4
AUDIO_TOL = 1e-5
MIDI_TIME_TOL = 1e-6
# 耗时字段（elapsed_sec）与 attempts（含逐窗口过程记录，最终 score 单独比）除外
REPORT_EXACT_FIELDS = ("status", "bpm", "loop_start_sec", "loop_seconds",
                       "n_samples", "n_notes")


def compare_reports(old: dict, new: dict) -> list[str]:
    errors = []
    for field in REPORT_EXACT_FIELDS:
        if old.get(field) != new.get(field):
            errors.append(f"report.{field}: {old.get(field)!r} != {new.get(field)!r}")
    if abs(old.get("score", 0.0) - new.get("score", 0.0)) > SCORE_TOL:
        errors.append(f"report.score: |{old.get('score')} - {new.get('score')}|"
                      f" > {SCORE_TOL}")
    old_names = [l["name"] for l in old.get("lanes", [])]
    new_names = [l["name"] for l in new.get("lanes", [])]
    if old_names != new_names:
        errors.append(f"report.lanes 名称: {old_names} != {new_names}")
    return errors


def compare_lanes(old_path: Path, new_path: Path) -> list[str]:
    old = json.loads(old_path.read_text())
    new = json.loads(new_path.read_text())
    return [] if old == new else [f"lanes.json 不一致: {old_path} vs {new_path}"]


def _note_events(path: Path) -> list[tuple[int, int, float, float]]:
    pm = pretty_midi.PrettyMIDI(str(path))
    events = [(n.pitch, n.velocity, n.start, n.end)
              for inst in pm.instruments for n in inst.notes]
    return sorted(events)


def compare_midi(old_path: Path, new_path: Path) -> list[str]:
    old, new = _note_events(old_path), _note_events(new_path)
    if len(old) != len(new):
        return [f"MIDI note 数量: {len(old)} != {len(new)}"]
    errors = []
    for i, ((op, ov, os_, oe), (np_, nv, ns, ne)) in enumerate(zip(old, new)):
        if (op, ov) != (np_, nv):
            errors.append(f"MIDI note[{i}] pitch/velocity: "
                          f"({op},{ov}) != ({np_},{nv})")
        elif abs(os_ - ns) > MIDI_TIME_TOL or abs(oe - ne) > MIDI_TIME_TOL:
            errors.append(f"MIDI note[{i}] 时间偏差超过 {MIDI_TIME_TOL}")
    return errors


def compare_audio(old_dir: Path, new_dir: Path) -> list[str]:
    errors = []
    old_samples = {p.name for p in (old_dir / "samples").glob("*.wav")}
    new_samples = {p.name for p in (new_dir / "samples").glob("*.wav")}
    if old_samples != new_samples:
        errors.append(f"samples 集合不一致: {sorted(old_samples ^ new_samples)}")
    rels = ["loop_preview.wav", "render_preview.wav"]
    rels += [f"samples/{name}" for name in sorted(old_samples & new_samples)]
    for rel in rels:
        old_path, new_path = old_dir / rel, new_dir / rel
        if not old_path.exists() or not new_path.exists():
            errors.append(f"{rel}: 文件缺失")
            continue
        a, _ = sf.read(old_path, dtype="float64", always_2d=True)
        b, _ = sf.read(new_path, dtype="float64", always_2d=True)
        if a.shape != b.shape:
            errors.append(f"{rel}: 长度/形状 {a.shape} != {b.shape}")
            continue
        diff = float(np.abs(a - b).max()) if len(a) else 0.0
        if diff > AUDIO_TOL:
            errors.append(f"{rel}: 最大绝对差 {diff:.2e} > {AUDIO_TOL}")
    return errors


def compare_packages(old_dir: Path, new_dir: Path) -> list[str]:
    old_dir, new_dir = Path(old_dir), Path(new_dir)
    old_report = json.loads((old_dir / "report.json").read_text())
    new_report = json.loads((new_dir / "report.json").read_text())
    errors = compare_reports(old_report, new_report)
    errors += compare_lanes(old_dir / "lanes.json", new_dir / "lanes.json")
    errors += compare_midi(old_dir / "chart.mid", new_dir / "chart.mid")
    errors += compare_audio(old_dir, new_dir)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("parity", description=__doc__)
    parser.add_argument("old_dir", type=Path)
    parser.add_argument("new_dir", type=Path)
    args = parser.parse_args(argv)
    errors = compare_packages(args.old_dir, args.new_dir)
    if errors:
        print("parity FAIL：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("parity PASS（spec §3.2 全部比较项通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/pipeline_from_stems/ -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/pipeline_from_stems/parity.py \
        workers/audio/tests/pipeline_from_stems/test_parity.py
git commit -m "feat(pfs): add parity comparator for frozen-stems gate"
```

---

### Task 12: `dev.sh` 接线 + 真实 parity 验收

**Files:**
- Modify: `scripts/dev.sh`

**Interfaces:**
- Consumes: Task 6 constraints、Task 7 CLI、Task 9 envcheck、Task 11 parity CLI、现有 `cmd_smoke` 的 testsong fixture 逻辑
- Produces: `scripts/dev.sh setup-pfs`（创建 `.venv-pfs`）、`scripts/dev.sh parity`（指纹 → 旧管线 → 新管线 → 比较 → Patchify 两侧 → patch_id 一致）；`setup-demo` 改为带 `-c` constraints 安装

- [ ] **Step 1: 修改 `scripts/dev.sh`**

顶部变量区（`TESTSONG=` 行之后）追加：

```bash
WORKER="$ROOT/workers/audio"
PFS_VENV="$WORKER/.venv-pfs"
CONSTRAINTS="$WORKER/config/parity-constraints.txt"
```

usage 里 `setup-demo` 行后追加两行：

```text
  setup-pfs          创建 pipeline-from-stems venv（librosa 等 DSP 栈，constraints 锁版本）
  parity             frozen-stems parity 门槛：旧 demo pipeline vs PipelineFromStems（spec §3.2）
```

`cmd_setup_demo` 中安装行改为（constraints 成为 demo baseline venv 的版本来源，spec §3.1；只作用于安装期，不改 demo 代码）：

```bash
"$DEMO/.venv/bin/pip" -q install -e "$DEMO" -c "$CONSTRAINTS"
```

新增命令函数（放在 `cmd_smoke` 之后）：

```bash
cmd_setup_pfs() {
  if [ ! -x "$PFS_VENV/bin/python" ]; then
    echo "==> 创建 pipeline-from-stems venv"
    python3 -m venv "$PFS_VENV"
  fi
  # lmdj_audio_worker/__init__.py 会 import job -> lmdj_patchify，
  # 所以 pfs venv 也要装两个轻量 path dep（顺序：core-models 先）
  "$PFS_VENV/bin/pip" -q install -e "$CORE" -c "$CONSTRAINTS"
  "$PFS_VENV/bin/pip" -q install -e "$PATCHIFY" -c "$CONSTRAINTS"
  "$PFS_VENV/bin/pip" -q install -e "$WORKER[pfs]" -c "$CONSTRAINTS"
  echo "==> pfs venv 就绪"
}

ensure_testsong() {
  if [ ! -f "$TESTSONG/lanes.json" ]; then
    ensure_demo_venv
    echo "==> 生成 testsong（合成曲，stems 预置，跳过 demucs）"
    (cd "$DEMO" && .venv/bin/python scripts/make_test_song.py output/testsong \
      && .venv/bin/song-pipeline run output/testsong/input.wav --song-id testsong --fast)
  fi
}

cmd_parity() {
  ensure_demo_venv
  ensure_pkg_venvs
  [ -x "$PFS_VENV/bin/python" ] || { echo "先运行: scripts/dev.sh setup-pfs" >&2; exit 1; }
  ensure_testsong

  echo "==> 环境指纹校验（不符即中止，spec §3.2）"
  "$PFS_VENV/bin/python" -m lmdj_audio_worker.envcheck \
    "$DEMO/.venv" "$PFS_VENV" --constraints "$CONSTRAINTS"

  local tmp; tmp="$(mktemp -d)"
  echo "==> 旧 pipeline（demo venv，cached stems 跳过 demucs）"
  mkdir -p "$tmp/old/parity/stems"
  cp "$TESTSONG/stems/"*.wav "$tmp/old/parity/stems/"
  (cd "$DEMO" && .venv/bin/song-pipeline run "$TESTSONG/input.wav" \
    --out "$tmp/old" --song-id parity --fast)

  echo "==> 新 PipelineFromStems（pfs venv，同一组 stems）"
  "$PFS_VENV/bin/python" -m lmdj_audio_worker.pipeline_from_stems \
    --stems "$tmp/old/parity/stems" --out "$tmp/new" --song-id parity

  echo "==> parity 比较"
  "$PFS_VENV/bin/python" -m lmdj_audio_worker.pipeline_from_stems.parity \
    "$tmp/old/parity" "$tmp/new/parity"

  echo "==> Patchify 两侧 + patch_id 一致性"
  "$PATCHIFY/.venv/bin/lmdj-patchify" "$tmp/old/parity"
  "$PATCHIFY/.venv/bin/lmdj-patchify" "$tmp/new/parity"
  "$PATCHIFY/.venv/bin/python" - "$tmp/old/parity/patch.json" "$tmp/new/parity/patch.json" <<'EOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
assert a["patch_id"] == b["patch_id"], f"patch_id 不一致: {a['patch_id']} vs {b['patch_id']}"
print(f"patch_id 一致: {a['patch_id']}")
EOF
  echo "==> parity PASS（临时输出保留在 $tmp）"
}
```

`cmd_smoke` 中原有的 testsong 生成块替换为 `ensure_testsong`（去重）：

```bash
cmd_smoke() {
  ensure_pkg_venvs
  ensure_testsong
  "$PATCHIFY/.venv/bin/lmdj-patchify" "$TESTSONG"
  summarize "$TESTSONG/patch.json"
}
```

case 分发表加两行：

```bash
  setup-pfs)  cmd_setup_pfs ;;
  parity)     cmd_parity ;;
```

- [ ] **Step 2: 语法检查**

```bash
bash -n scripts/dev.sh && echo syntax-ok
```

Expected: `syntax-ok`。

- [ ] **Step 3: 真实验收——运行 parity 门槛**

```bash
scripts/dev.sh setup-demo    # worktree 首次需要；demo baseline venv 从 constraints 创建（10min+）
scripts/dev.sh setup-pfs
scripts/dev.sh parity
```

Expected 末尾输出（顺序）：

```text
环境指纹 OK: .../references/demos/lmdj-song-pipeline/.venv, .../workers/audio/.venv-pfs
...
parity PASS（spec §3.2 全部比较项通过）
patch_id 一致: parity-XXXXXXXX
==> parity PASS（临时输出保留在 /var/folders/.../T/tmp.XXXX）
```

若指纹校验失败：删除对应 venv 重建（`rm -rf <venv>` 后重跑 `setup-demo`/`setup-pfs`），不得放宽 constraints。
若 parity 比较失败：这是 spec §3.2 的硬门槛——排查迁移差异（先 `diff` 六个模块确认逐字节一致，再查两侧 config 差异），不得调整容差。

- [ ] **Step 4: Commit**

```bash
git add scripts/dev.sh
git commit -m "feat(dev): wire setup-pfs and parity gate into dev helper"
```

---

### Task 13: 文档同步

**Files:**
- Modify: `CLAUDE.md`（Commands 的 Product stack 代码块 + workers/audio 架构条目）
- Modify: `AGENTS.md`（与 CLAUDE.md 同步的对应位置）
- Modify: `docs/superpowers/2026-07-10-status-and-backlog.md`（追加 milestone 条目）

- [ ] **Step 1: CLAUDE.md / AGENTS.md**

两个文件的 Product stack 命令块中，`scripts/dev.sh setup-demo` 行后各追加：

```text
scripts/dev.sh setup-pfs    # create the pipeline-from-stems venv (DSP deps pinned by parity-constraints.txt)
scripts/dev.sh parity       # frozen-stems parity gate: demo pipeline vs PipelineFromStems (spec §3.2)
```

两个文件 `workers/audio/` 架构条目末尾各追加一句：

```text
`separation/` holds the lmdj.separation.v1 contract + checkpoint registry + runner protocol (orchestrator synthesizes failure records when the runner dies); `pipeline_from_stems/` is the stages-3–6 migration (runs in its own `.venv-pfs`, versions pinned by `config/parity-constraints.txt`; behavior changes must pass `scripts/dev.sh parity` first).
```

- [ ] **Step 2: status-and-backlog**

在 shipped milestones 列表末尾追加：

```markdown
- **Separation Phase 0（0A+0B）**：`lmdj.separation.v1` contract / checkpoint registry / runner 协议（orchestrator 合成失败记录）+ `pipeline_from_stems`（阶段 3–6 逐字节迁移，专用 `.venv-pfs`，constraints 锁版本）+ frozen-stems parity 门槛（`scripts/dev.sh parity`，testsong 全项通过、两侧 patch_id 一致）。spec: `docs/superpowers/specs/2026-07-15-multi-separator-benchmark-design.md`；plan: `docs/superpowers/plans/2026-07-15-separation-phase0.md`。下一步：Phase 1A（HT Demucs + SCNet runners，registry 落真实条目）。
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md AGENTS.md docs/superpowers/2026-07-10-status-and-backlog.md
git commit -m "docs: record separation phase 0 commands and milestone"
```

---

## 收尾验证（全量）

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q   # 全绿
scripts/dev.sh test                                        # core-models + patchify 回归
scripts/dev.sh parity                                      # parity 门槛 PASS
scripts/dev.sh smoke                                       # 既有链路无回归
```

## Spec 覆盖对照（自查）

| Spec 要求 | Task |
|---|---|
| §3.1 依赖归属 / 独立 venv / constraints 单一来源 | 6, 9, 12 |
| §3.2 parity 前提（同版本指纹 + 同平台）与全部比较项 | 9, 11, 12 |
| §4 代码边界（separation/ + pipeline_from_stems/ + config/） | 1–8 |
| §5 separation.json 成功/失败形态、source 两级、canonical 硬约束、兼容映射与 merge-only、峰值缩放、两组文件不复用 | 1, 2, 5, 8 |
| §6 registry 必填字段（含推理配置）、状态语义、缓存布局与原子下载 | 3, 4 |
| §10 错误类别、退出码/stderr tail 记录 | 1, 5 |
| §12.1 相关自动测试条目（contract 边界、合成记录、指纹中止、drop 拒绝、registry 校验、缓存 checksum、canonical 校验、parity） | 各任务测试 + 12 |
| §13 Phase 0A / 0B 独立提交 | 每任务单独 commit |

不在本 plan 范围（后续 plan）：§7 数据集 manifests、§8 benchmark CLI/缓存 key、§9 指标与评分、四个真实 runner（Phase 1A/1B）、§11 生产接入（Phase 2）。MPS 内存采样算法（spec §5）属于真实 runner 的实现细节，随 Phase 1A 落地。
