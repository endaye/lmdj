# Patchify Core Prototype 实施计划

> **状态：历史参考 / 不再建议执行。** 2026-07-07 已确认 `references/demos/lmdj-song-pipeline/` 只作为参考 demo，不纳入正式产品源码边界。Patchify 需要在 LMDJ 正式目录中重新编写；新的执行计划见 `docs/plans/2026-07-07-patchify-core-path-b.md`。

> **给 agentic workers：** Follow repository `AGENTS.md` and execute the approved plan task-by-task.步骤使用 checkbox（`- [ ]`）语法追踪状态。

**目标：** 构建第一版可测试的 Patchify core：把现有 `lmdj-song-pipeline` package 转换成稳定的 `patch.json`，其中包含产品层的 patch、scene、pad 和 element objects。

**架构：** 保持当前 audio pipeline 不变，只在 `lanes.json`、`chart.mid` 和 `report.json` 已经生成之后增加一个很窄的 adapter layer。这个新层负责验证 package，把 pipeline lanes 映射到默认 8-pad Focus View，输出 `patch.json`，并通过 CLI/API 暴露出来；本计划不修改 `PipelineConfig.lane_pitches`。

**技术栈：** Python 3.10+、dataclasses、JSON stdlib、`pretty_midi`、现有 `song_pipeline` package、pytest。

## 计划状态

本计划是 **adapter prototype 方案**，默认把 Patchify Core 加在 `lmdj-song-pipeline` 内部，用最快路径验证参考 pipeline 输出如何转成 LMDJ 产品对象。

新的项目边界判断是：`lmdj-song-pipeline` 是高嘉丰提供的参考项目和可复用技术素材库，不是 LMDJ 最终系统源码边界。因此，执行本计划前需要先确认采用哪条路径：

```text
Path A: 继续按本计划在 lmdj-song-pipeline 内做 Patchify adapter prototype
Path B: 新建 LMDJ backend/shared package，把 lmdj-song-pipeline 当作输入来源或可迁移代码
```

如果当前目标是尽快验证 `patch.json` contract，选 Path A。  
如果当前目标是建立云端产品代码骨架，选 Path B，并需要重写本计划的文件结构。

## 全局约束

- 实现和测试都在 `/Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline` 内完成。
- 该路径只适用于 Path A：参考项目内 adapter prototype。
- 使用 `.venv/bin/python -m pytest tests/ -q` 做验证。
- 不要升级 `numpy`；它因为 demucs/numba compatibility 固定为 `<2`。
- 保留现有 pipeline 输出文件：`samples/*.wav`、`chart.mid`、`lanes.json`、`report.json`、`loop_preview.wav`、`render_preview.wav`。
- `lanes.json` 仍然是 pitch-to-sample mapping 的事实来源；不要从文件名推断 lane order。
- 本计划不修改 `PipelineConfig.lane_pitches`。
- V1 默认 pad surface 是 8-pad Focus View，固定槽位为：`Drums`、`Bass`、`Harmony`、`Lead/Vocal`、`Fill`、`Drop`、`Mute`、`FX/Variation`。
- 第一版实现对 uploaded-song 和 generated-audio pipeline packages 一视同仁；完整 LLM idea generation 属于单独计划。

---

## 文件结构

下面文件结构只适用于 Path A。如果选择 Path B，应改为在新的 LMDJ backend/shared package 中创建同名职责模块，并把 `lmdj-song-pipeline` 的输出作为测试 fixture 或 adapter input。

- 新建 `references/demos/lmdj-song-pipeline/song_pipeline/patch_model.py`
  - 负责可序列化的产品对象：`Patch`、`Scene`、`Pad`、`Element`、`RenderRef`。
  - 提供 `to_dict()` methods 和 `write_patch_json()`。
- 新建 `references/demos/lmdj-song-pipeline/song_pipeline/package_loader.py`
  - 负责 package validation 和解析后的 package data。
  - 读取 `lanes.json`、`report.json` 和 `chart.mid`。
  - 确认 sample files 存在，并确认 MIDI pitches 都存在于 `lanes.json`。
- 新建 `references/demos/lmdj-song-pipeline/song_pipeline/pad_mapper.py`
  - 负责从 pipeline lanes 到产品 pads 的默认 8-pad Focus View mapping。
  - 不访问 filesystem。
- 新建 `references/demos/lmdj-song-pipeline/song_pipeline/patchify.py`
  - 编排 loader + mapper + model。
  - 为已有 pipeline package directory 生成 `patch.json`。
- 修改 `references/demos/lmdj-song-pipeline/song_pipeline/pipeline.py`
  - package artifacts 成功写入后，调用 `patchify_package(out_dir)`。
  - 如果 patchify 失败，不阻塞既有 `report.json` 生成；只在需要时把失败写入 `report["patchify_error"]`。
- 修改 `references/demos/lmdj-song-pipeline/song_pipeline/cli.py`
  - 增加 `song-pipeline patchify <song_dir>`，用于从已有 package 重新生成 `patch.json`。
- 修改 `references/demos/lmdj-song-pipeline/song_pipeline/api.py`
  - 如果 `patch.json` 存在，将它包含进 package zip。
- 新建 `references/demos/lmdj-song-pipeline/tests/test_patch_model.py`
- 新建 `references/demos/lmdj-song-pipeline/tests/test_package_loader.py`
- 新建 `references/demos/lmdj-song-pipeline/tests/test_pad_mapper.py`
- 新建 `references/demos/lmdj-song-pipeline/tests/test_patchify.py`

---

### 任务 1：产品 Patch Model

**文件：**
- 新建：`references/demos/lmdj-song-pipeline/song_pipeline/patch_model.py`
- 测试：`references/demos/lmdj-song-pipeline/tests/test_patch_model.py`

**接口：**
- 产出：`Patch`、`Scene`、`Pad`、`Element`、`RenderRef`、`write_patch_json(patch: Patch, out_path: Path) -> None`
- 消费：不依赖前置任务

- [ ] **步骤 1：编写失败测试**

创建 `tests/test_patch_model.py`：

```python
import json
from pathlib import Path

from song_pipeline.patch_model import Element, Pad, Patch, RenderRef, Scene, write_patch_json


def test_patch_model_serializes_product_objects(tmp_path: Path):
    patch = Patch(
        patch_id="testsong",
        source={"type": "upload", "song_id": "testsong"},
        bpm=90.0,
        loop_seconds=10.667,
        pads=[
            Pad(
                index=0,
                slot="Drums",
                label="kick",
                action="trigger_element",
                element_id="el_kick",
                behavior={"trigger": "one_shot", "quantize": "1/16"},
            )
        ],
        scenes=[
            Scene(
                scene_id="scene_original",
                name="Original",
                pad_indexes=[0],
                intent="Pipeline default scene",
            )
        ],
        elements=[
            Element(
                element_id="el_kick",
                name="kick",
                kind="drum",
                source_path="samples/kick.wav",
                pitch=36,
                lane=0,
            )
        ],
        renders=[
            RenderRef(kind="loop_preview", path="loop_preview.wav"),
            RenderRef(kind="render_preview", path="render_preview.wav"),
        ],
        metadata={"status": "passed", "score": 0.8},
    )

    out_path = tmp_path / "patch.json"
    write_patch_json(patch, out_path)
    data = json.loads(out_path.read_text())

    assert data["schema"] == "lmdj.patch.v1"
    assert data["patch_id"] == "testsong"
    assert data["pads"][0]["slot"] == "Drums"
    assert data["pads"][0]["behavior"]["quantize"] == "1/16"
    assert data["scenes"][0]["scene_id"] == "scene_original"
    assert data["elements"][0]["source_path"] == "samples/kick.wav"
    assert data["renders"][1]["kind"] == "render_preview"
```

- [ ] **步骤 2：运行测试，确认它失败**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_patch_model.py::test_patch_model_serializes_product_objects -q
```

预期：FAIL，报错为 `ModuleNotFoundError: No module named 'song_pipeline.patch_model'`。

- [ ] **步骤 3：编写最小实现**

创建 `song_pipeline/patch_model.py`：

```python
"""Product-level Patchify data model.

This module is intentionally independent of audio analysis. It represents the
stable product object that UI, export, and later community flows can consume.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "lmdj.patch.v1"


@dataclass(frozen=True)
class Element:
    element_id: str
    name: str
    kind: str
    source_path: str
    pitch: int
    lane: int
    role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Pad:
    index: int
    slot: str
    label: str
    action: str
    element_id: str | None
    behavior: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Scene:
    scene_id: str
    name: str
    pad_indexes: list[int]
    intent: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RenderRef:
    kind: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Patch:
    patch_id: str
    source: dict[str, Any]
    bpm: float
    loop_seconds: float
    pads: list[Pad]
    scenes: list[Scene]
    elements: list[Element]
    renders: list[RenderRef]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "patch_id": self.patch_id,
            "source": self.source,
            "bpm": self.bpm,
            "loop_seconds": self.loop_seconds,
            "pads": [p.to_dict() for p in self.pads],
            "scenes": [s.to_dict() for s in self.scenes],
            "elements": [e.to_dict() for e in self.elements],
            "renders": [r.to_dict() for r in self.renders],
            "metadata": self.metadata,
        }


def write_patch_json(patch: Patch, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(patch.to_dict(), indent=2, ensure_ascii=False))
```

- [ ] **步骤 4：运行测试，确认它通过**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_patch_model.py::test_patch_model_serializes_product_objects -q
```

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
git add song_pipeline/patch_model.py tests/test_patch_model.py
git commit -m "feat(patchify): add product patch model"
```

---

### 任务 2：Package Loader 和 Validator

**文件：**
- 新建：`references/demos/lmdj-song-pipeline/song_pipeline/package_loader.py`
- 测试：`references/demos/lmdj-song-pipeline/tests/test_package_loader.py`

**接口：**
- 消费：不依赖前置 runtime objects
- 产出：`PipelinePackage`、`load_pipeline_package(song_dir: Path) -> PipelinePackage`

- [ ] **步骤 1：编写失败测试**

创建 `tests/test_package_loader.py`：

```python
import json
from pathlib import Path

import pretty_midi
import pytest

from song_pipeline.package_loader import PackageValidationError, load_pipeline_package


def _write_chart(path: Path, pitches: list[int]) -> None:
    pm = pretty_midi.PrettyMIDI(initial_tempo=90)
    inst = pretty_midi.Instrument(program=0, name="lmdj-chart")
    for i, pitch in enumerate(pitches):
        inst.notes.append(pretty_midi.Note(velocity=100, pitch=pitch, start=i * 0.25, end=i * 0.25 + 0.1))
    pm.instruments.append(inst)
    pm.write(str(path))


def _write_minimal_package(song_dir: Path, midi_pitches: list[int] | None = None) -> None:
    (song_dir / "samples").mkdir(parents=True)
    (song_dir / "samples" / "kick.wav").write_bytes(b"fake wav")
    (song_dir / "lanes.json").write_text(json.dumps({
        "bpm": 90.0,
        "loop_seconds": 10.667,
        "lanes": [{"lane": 0, "name": "kick", "kind": "drum", "pitch": 36, "sample": "samples/kick.wav"}],
    }))
    (song_dir / "report.json").write_text(json.dumps({
        "song_id": "testsong",
        "status": "passed",
        "score": 0.75,
        "threshold": 0.5,
    }))
    _write_chart(song_dir / "chart.mid", midi_pitches or [36])


def test_load_pipeline_package_reads_required_contract(tmp_path: Path):
    song_dir = tmp_path / "testsong"
    song_dir.mkdir()
    _write_minimal_package(song_dir)

    package = load_pipeline_package(song_dir)

    assert package.song_id == "testsong"
    assert package.bpm == 90.0
    assert package.loop_seconds == 10.667
    assert package.lanes[0]["name"] == "kick"
    assert package.report["status"] == "passed"
    assert package.midi_pitches == {36}


def test_load_pipeline_package_rejects_unknown_midi_pitch(tmp_path: Path):
    song_dir = tmp_path / "testsong"
    song_dir.mkdir()
    _write_minimal_package(song_dir, midi_pitches=[99])

    with pytest.raises(PackageValidationError, match="MIDI pitches missing from lanes.json: \\[99\\]"):
        load_pipeline_package(song_dir)
```

- [ ] **步骤 2：运行测试，确认它们失败**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_package_loader.py -q
```

预期：FAIL，报错为 `ModuleNotFoundError: No module named 'song_pipeline.package_loader'`。

- [ ] **步骤 3：编写实现**

创建 `song_pipeline/package_loader.py`：

```python
"""Load and validate existing song-pipeline packages."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pretty_midi


class PackageValidationError(RuntimeError):
    """Raised when a pipeline package cannot become a product patch."""


@dataclass(frozen=True)
class PipelinePackage:
    song_dir: Path
    song_id: str
    bpm: float
    loop_seconds: float
    lanes: list[dict[str, Any]]
    report: dict[str, Any]
    midi_pitches: set[int]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PackageValidationError(f"missing required file: {path.name}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise PackageValidationError(f"invalid JSON in {path.name}: {e}") from e


def _midi_pitches(chart_path: Path) -> set[int]:
    if not chart_path.exists():
        raise PackageValidationError("missing required file: chart.mid")
    pm = pretty_midi.PrettyMIDI(str(chart_path))
    pitches: set[int] = set()
    for inst in pm.instruments:
        for note in inst.notes:
            pitches.add(int(note.pitch))
    return pitches


def load_pipeline_package(song_dir: Path) -> PipelinePackage:
    lanes_json = _read_json(song_dir / "lanes.json")
    report = _read_json(song_dir / "report.json")

    lanes = lanes_json.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise PackageValidationError("lanes.json must contain a non-empty lanes array")

    lane_pitches = set()
    for lane in lanes:
        for key in ("lane", "name", "kind", "pitch", "sample"):
            if key not in lane:
                raise PackageValidationError(f"lane is missing required key: {key}")
        sample_path = song_dir / lane["sample"]
        if not sample_path.exists():
            raise PackageValidationError(f"missing sample file: {lane['sample']}")
        lane_pitches.add(int(lane["pitch"]))

    midi_pitches = _midi_pitches(song_dir / "chart.mid")
    missing = sorted(midi_pitches - lane_pitches)
    if missing:
        raise PackageValidationError(f"MIDI pitches missing from lanes.json: {missing}")

    status = report.get("status")
    if status not in {"passed", "rejected", "failed"}:
        raise PackageValidationError("report.json status must be passed, rejected, or failed")

    song_id = str(report.get("song_id") or song_dir.name)
    bpm = float(lanes_json.get("bpm") or report.get("bpm") or 0)
    loop_seconds = float(lanes_json.get("loop_seconds") or report.get("loop_seconds") or 0)
    if bpm <= 0:
        raise PackageValidationError("package BPM must be greater than zero")
    if loop_seconds <= 0:
        raise PackageValidationError("package loop_seconds must be greater than zero")

    return PipelinePackage(
        song_dir=song_dir,
        song_id=song_id,
        bpm=bpm,
        loop_seconds=loop_seconds,
        lanes=lanes,
        report=report,
        midi_pitches=midi_pitches,
    )
```

- [ ] **步骤 4：运行测试，确认它们通过**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_package_loader.py -q
```

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
git add song_pipeline/package_loader.py tests/test_package_loader.py
git commit -m "feat(patchify): validate pipeline packages"
```

---

### 任务 3：默认 8-Pad Focus Mapper

**文件：**
- 新建：`references/demos/lmdj-song-pipeline/song_pipeline/pad_mapper.py`
- 测试：`references/demos/lmdj-song-pipeline/tests/test_pad_mapper.py`

**接口：**
- 消费：`PipelinePackage.lanes`
- 产出：`build_focus_pads(lanes: list[dict[str, Any]]) -> tuple[list[Element], list[Pad]]`

- [ ] **步骤 1：编写失败测试**

创建 `tests/test_pad_mapper.py`：

```python
from song_pipeline.pad_mapper import FOCUS_SLOTS, build_focus_pads


def test_build_focus_pads_maps_pipeline_lanes_to_fixed_slots():
    lanes = [
        {"lane": 0, "name": "kick", "kind": "drum", "pitch": 36, "sample": "samples/kick.wav"},
        {"lane": 1, "name": "bass", "kind": "long", "pitch": 48, "sample": "samples/bass.wav"},
        {"lane": 2, "name": "melody_a", "kind": "long", "pitch": 50, "sample": "samples/melody_a.wav"},
        {"lane": 3, "name": "hat", "kind": "drum", "pitch": 42, "sample": "samples/hat.wav"},
    ]

    elements, pads = build_focus_pads(lanes)

    assert FOCUS_SLOTS == ["Drums", "Bass", "Harmony", "Lead/Vocal", "Fill", "Drop", "Mute", "FX/Variation"]
    assert [pad.slot for pad in pads] == FOCUS_SLOTS
    assert pads[0].label == "kick"
    assert pads[0].element_id == "el_kick"
    assert pads[1].label == "bass"
    assert pads[2].label == "melody_a"
    assert pads[4].action == "scene_fill"
    assert pads[6].action == "mute_toggle"
    assert elements[0].role == "drums"


def test_build_focus_pads_keeps_empty_control_slots_when_material_is_missing():
    lanes = [
        {"lane": 0, "name": "loop_a", "kind": "loop", "pitch": 60, "sample": "samples/loop_a.wav"},
    ]

    elements, pads = build_focus_pads(lanes)

    assert len(elements) == 1
    assert len(pads) == 8
    assert pads[0].slot == "Drums"
    assert pads[0].element_id == "el_loop_a"
    assert pads[3].action == "empty"
    assert pads[7].action == "ai_variation"
```

- [ ] **步骤 2：运行测试，确认它们失败**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_pad_mapper.py -q
```

预期：FAIL，报错为 `ModuleNotFoundError: No module named 'song_pipeline.pad_mapper'`。

- [ ] **步骤 3：编写实现**

创建 `song_pipeline/pad_mapper.py`：

```python
"""Map pipeline lanes into the product 8-pad Focus View."""
from __future__ import annotations

from typing import Any

from .patch_model import Element, Pad

FOCUS_SLOTS = ["Drums", "Bass", "Harmony", "Lead/Vocal", "Fill", "Drop", "Mute", "FX/Variation"]


def _element_id(name: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")
    return f"el_{safe}"


def _role_for_lane(lane: dict[str, Any]) -> str:
    name = str(lane["name"]).lower()
    kind = str(lane["kind"]).lower()
    if kind == "drum" or name in {"kick", "snare", "hat", "drum_low", "drum_high"}:
        return "drums"
    if "bass" in name:
        return "bass"
    if "melody" in name or "chord" in name:
        return "harmony"
    if "vocal" in name or "lead" in name:
        return "lead_vocal"
    if kind == "loop":
        return "loop"
    return "texture"


def _make_element(lane: dict[str, Any]) -> Element:
    return Element(
        element_id=_element_id(str(lane["name"])),
        name=str(lane["name"]),
        kind=str(lane["kind"]),
        source_path=str(lane["sample"]),
        pitch=int(lane["pitch"]),
        lane=int(lane["lane"]),
        role=_role_for_lane(lane),
    )


def _first(elements: list[Element], *roles: str) -> Element | None:
    for role in roles:
        for element in elements:
            if element.role == role:
                return element
    return None


def _trigger_pad(index: int, slot: str, element: Element | None) -> Pad:
    if element is None:
        return Pad(index=index, slot=slot, label=slot, action="empty", element_id=None, behavior={})
    trigger = "one_shot" if element.kind == "drum" else "loop"
    return Pad(
        index=index,
        slot=slot,
        label=element.name,
        action="trigger_element",
        element_id=element.element_id,
        behavior={"trigger": trigger, "quantize": "1/16"},
    )


def build_focus_pads(lanes: list[dict[str, Any]]) -> tuple[list[Element], list[Pad]]:
    elements = [_make_element(lane) for lane in lanes]
    primary_loop = _first(elements, "loop", "texture")
    drums = _first(elements, "drums", "loop", "texture")
    bass = _first(elements, "bass")
    harmony = _first(elements, "harmony")
    lead = _first(elements, "lead_vocal")

    pads = [
        _trigger_pad(0, "Drums", drums),
        _trigger_pad(1, "Bass", bass),
        _trigger_pad(2, "Harmony", harmony),
        _trigger_pad(3, "Lead/Vocal", lead),
        Pad(4, "Fill", "Fill", "scene_fill", primary_loop.element_id if primary_loop else None, {"quantize": "1 bar"}),
        Pad(5, "Drop", "Drop", "scene_drop", primary_loop.element_id if primary_loop else None, {"quantize": "1 bar"}),
        Pad(6, "Mute", "Mute", "mute_toggle", drums.element_id if drums else None, {"target": "primary"}),
        Pad(7, "FX/Variation", "Variation", "ai_variation", primary_loop.element_id if primary_loop else None, {"assist_mode": "guided"}),
    ]
    return elements, pads
```

- [ ] **步骤 4：运行测试，确认它们通过**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_pad_mapper.py -q
```

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
git add song_pipeline/pad_mapper.py tests/test_pad_mapper.py
git commit -m "feat(patchify): map lanes to focus pads"
```

---

### 任务 4：Patchify Orchestrator

**文件：**
- 新建：`references/demos/lmdj-song-pipeline/song_pipeline/patchify.py`
- 测试：`references/demos/lmdj-song-pipeline/tests/test_patchify.py`

**接口：**
- 消费：`load_pipeline_package(song_dir: Path) -> PipelinePackage`、`build_focus_pads(lanes) -> tuple[list[Element], list[Pad]]`
- 产出：`build_patch(song_dir: Path, source_type: str = "pipeline") -> Patch`、`patchify_package(song_dir: Path) -> Path`

- [ ] **步骤 1：编写失败测试**

创建 `tests/test_patchify.py`：

```python
import json
from pathlib import Path

import pretty_midi

from song_pipeline.patchify import build_patch, patchify_package


def _write_chart(path: Path) -> None:
    pm = pretty_midi.PrettyMIDI(initial_tempo=90)
    inst = pretty_midi.Instrument(program=0, name="lmdj-chart")
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=0, end=0.1))
    pm.instruments.append(inst)
    pm.write(str(path))


def _write_package(song_dir: Path) -> None:
    (song_dir / "samples").mkdir(parents=True)
    (song_dir / "samples" / "kick.wav").write_bytes(b"fake wav")
    (song_dir / "lanes.json").write_text(json.dumps({
        "bpm": 90.0,
        "loop_seconds": 10.667,
        "lanes": [{"lane": 0, "name": "kick", "kind": "drum", "pitch": 36, "sample": "samples/kick.wav"}],
    }))
    (song_dir / "report.json").write_text(json.dumps({
        "song_id": "testsong",
        "status": "passed",
        "score": 0.75,
        "threshold": 0.5,
    }))
    (song_dir / "loop_preview.wav").write_bytes(b"loop")
    (song_dir / "render_preview.wav").write_bytes(b"render")
    _write_chart(song_dir / "chart.mid")


def test_build_patch_creates_original_scene_and_metadata(tmp_path: Path):
    song_dir = tmp_path / "testsong"
    song_dir.mkdir()
    _write_package(song_dir)

    patch = build_patch(song_dir, source_type="upload")

    assert patch.patch_id == "testsong"
    assert patch.source == {"type": "upload", "song_id": "testsong"}
    assert patch.scenes[0].name == "Original"
    assert patch.scenes[0].pad_indexes == list(range(8))
    assert patch.metadata["status"] == "passed"
    assert patch.renders[0].path == "loop_preview.wav"


def test_patchify_package_writes_patch_json(tmp_path: Path):
    song_dir = tmp_path / "testsong"
    song_dir.mkdir()
    _write_package(song_dir)

    out_path = patchify_package(song_dir)
    data = json.loads(out_path.read_text())

    assert out_path == song_dir / "patch.json"
    assert data["schema"] == "lmdj.patch.v1"
    assert data["pads"][0]["slot"] == "Drums"
```

- [ ] **步骤 2：运行测试，确认它们失败**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_patchify.py -q
```

预期：FAIL，报错为 `ModuleNotFoundError: No module named 'song_pipeline.patchify'`。

- [ ] **步骤 3：编写实现**

创建 `song_pipeline/patchify.py`：

```python
"""Patchify pipeline packages into product-level patch.json files."""
from __future__ import annotations

from pathlib import Path

from .package_loader import load_pipeline_package
from .pad_mapper import build_focus_pads
from .patch_model import Patch, RenderRef, Scene, write_patch_json


def _renders(song_dir: Path) -> list[RenderRef]:
    refs: list[RenderRef] = []
    if (song_dir / "loop_preview.wav").exists():
        refs.append(RenderRef(kind="loop_preview", path="loop_preview.wav"))
    if (song_dir / "render_preview.wav").exists():
        refs.append(RenderRef(kind="render_preview", path="render_preview.wav"))
    return refs


def build_patch(song_dir: Path, source_type: str = "pipeline") -> Patch:
    package = load_pipeline_package(song_dir)
    elements, pads = build_focus_pads(package.lanes)
    scene = Scene(
        scene_id="scene_original",
        name="Original",
        pad_indexes=[pad.index for pad in pads],
        intent="Initial Patchify scene from pipeline package",
    )
    metadata = {
        "status": package.report.get("status"),
        "score": package.report.get("score"),
        "threshold": package.report.get("threshold"),
        "n_lanes": len(package.lanes),
        "n_midi_pitches": len(package.midi_pitches),
    }
    return Patch(
        patch_id=package.song_id,
        source={"type": source_type, "song_id": package.song_id},
        bpm=package.bpm,
        loop_seconds=package.loop_seconds,
        pads=pads,
        scenes=[scene],
        elements=elements,
        renders=_renders(song_dir),
        metadata=metadata,
    )


def patchify_package(song_dir: Path) -> Path:
    patch = build_patch(song_dir)
    out_path = song_dir / "patch.json"
    write_patch_json(patch, out_path)
    return out_path
```

- [ ] **步骤 4：运行测试，确认它们通过**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_patchify.py -q
```

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
git add song_pipeline/patchify.py tests/test_patchify.py
git commit -m "feat(patchify): build patch json from packages"
```

---

### 任务 5：Pipeline、CLI 和 API 集成

**文件：**
- 修改：`references/demos/lmdj-song-pipeline/song_pipeline/pipeline.py`
- 修改：`references/demos/lmdj-song-pipeline/song_pipeline/cli.py`
- 修改：`references/demos/lmdj-song-pipeline/song_pipeline/api.py`
- 测试：`references/demos/lmdj-song-pipeline/tests/test_smoke.py`
- 测试：`references/demos/lmdj-song-pipeline/tests/test_patchify.py`

**接口：**
- 消费：`patchify_package(song_dir: Path) -> Path`
- 产出：普通 pipeline run 后生成 `patch.json`；CLI 提供 `song-pipeline patchify <song_dir>`；package zip 在 `patch.json` 存在时包含它

- [ ] **步骤 1：为自动生成 `patch.json` 增加失败 smoke assertion**

修改 `tests/test_smoke.py`，在 `test_lanes_midi_consistency` 后增加这个测试：

```python
def test_pipeline_writes_patch_json(report_and_dir):
    """pipeline output includes product-level patch.json for the workstation UI."""
    _, song_dir = report_and_dir
    patch_path = song_dir / "patch.json"
    assert patch_path.exists()
    patch = json.loads(patch_path.read_text())
    assert patch["schema"] == "lmdj.patch.v1"
    assert patch["patch_id"] == "testsong"
    assert [pad["slot"] for pad in patch["pads"]] == [
        "Drums", "Bass", "Harmony", "Lead/Vocal",
        "Fill", "Drop", "Mute", "FX/Variation",
    ]
```

- [ ] **步骤 2：增加失败的 CLI 覆盖**

把这个测试追加到 `tests/test_patchify.py`：

```python
def test_cli_patchify_command_writes_patch_json(tmp_path: Path, capsys):
    from song_pipeline.cli import main
    import sys

    song_dir = tmp_path / "testsong"
    song_dir.mkdir()
    _write_package(song_dir)

    old_argv = sys.argv
    try:
        sys.argv = ["song-pipeline", "patchify", str(song_dir)]
        main()
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr()
    assert str(song_dir / "patch.json") in captured.out
    assert (song_dir / "patch.json").exists()
```

- [ ] **步骤 3：运行测试，确认它们失败**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_smoke.py::test_pipeline_writes_patch_json tests/test_patchify.py::test_cli_patchify_command_writes_patch_json -q
```

预期：FAIL，因为 pipeline 还不会写入 `patch.json`，并且 `patchify` 还不是可识别的 CLI command。

- [ ] **步骤 4：把 patchify 集成进 pipeline**

修改 `song_pipeline/pipeline.py`：

```python
# add import near existing imports
from .patchify import patchify_package
```

在 `run_pipeline` 中，`report.json` 写入之后、`log.info(...)` 之前，插入：

```python
    try:
        patchify_package(out_dir)
    except Exception as e:  # noqa: BLE001 patchify failure should not hide pipeline report
        report["patchify_error"] = str(e)
        (out_dir / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False))
```

在 `run_pipeline_abc` 中，`report.json` 写入之后、`log.info(...)` 之前，插入同一段：

```python
    try:
        patchify_package(out_dir)
    except Exception as e:  # noqa: BLE001 patchify failure should not hide pipeline report
        report["patchify_error"] = str(e)
        (out_dir / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False))
```

- [ ] **步骤 5：增加 CLI command**

修改 `song_pipeline/cli.py`，在 `gen` 定义之后增加 parser：

```python
    patchify = sub.add_parser("patchify", help="从已有 pipeline package 生成 patch.json")
    patchify.add_argument("song_dir", type=Path)
```

在 `elif args.cmd == "serve"` 之前增加这个分支：

```python
    elif args.cmd == "patchify":
        from .patchify import patchify_package
        out_path = patchify_package(args.song_dir)
        print(out_path)
```

- [ ] **步骤 6：在 API zip 中包含 `patch.json`**

修改 `song_pipeline/api.py` 的 package endpoint zip 创建逻辑：

```python
            for f in ["chart.mid", "lanes.json", "report.json", "patch.json"]:
                path = song_dir / f
                if path.exists():
                    z.write(path, f)
```

- [ ] **步骤 7：运行 targeted tests**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_smoke.py::test_pipeline_writes_patch_json tests/test_patchify.py::test_cli_patchify_command_writes_patch_json -q
```

预期：PASS。

- [ ] **步骤 8：运行完整 smoke suite**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/ -q
```

预期：所有测试 PASS。

- [ ] **步骤 9：Commit**

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
git add song_pipeline/pipeline.py song_pipeline/cli.py song_pipeline/api.py tests/test_smoke.py tests/test_patchify.py
git commit -m "feat(patchify): emit patch json from pipeline"
```

---

### 任务 6：Patchify Contract 文档

**文件：**
- 修改：`references/demos/lmdj-song-pipeline/README.md`
- 修改：`references/demos/lmdj-song-pipeline/SETUP_AND_USAGE.md`

**接口：**
- 消费：Tasks 1-5 产出的 `patch.json` schema
- 产出：面向未来 UI 和 community plans 的产品层 package contract 文档

- [ ] **步骤 1：更新 README output format**

把 `references/demos/lmdj-song-pipeline/README.md` 中的 output block 修改为：

```text
output/{song_id}/
├── samples/*.wav
├── chart.mid
├── lanes.json
├── patch.json
├── loop_preview.wav
├── render_preview.wav
└── report.json
```

在 `lanes.json` 段落后增加这段：

```markdown
`patch.json` 是给 LMDJ workstation clients 使用的产品层 Patchify contract。它把 pipeline artifacts 适配为 `Patch`、`Scene`、`Pad` 和 `Element` objects。`lanes.json` 仍然是 pitch-to-sample 的权威来源；`patch.json` 是 UI/product adapter layer。
```

- [ ] **步骤 2：记录 CLI patchify command**

把这个命令加入 `references/demos/lmdj-song-pipeline/README.md` 的 common command section：

```bash
# 从已有 package 重新生成产品层 patch.json。
.venv/bin/song-pipeline patchify output/mysong
```

- [ ] **步骤 3：更新 SETUP_AND_USAGE contract section**

在 `references/demos/lmdj-song-pipeline/SETUP_AND_USAGE.md` 中，在 output contract section 附近增加一个简短的 `patch.json` subsection：

```markdown
### patch.json

`patch.json` 在 `lanes.json`、`chart.mid` 和 `report.json` 之后生成。
它是未来 workstation UI 消费的产品层 Patchify object：

- `pads`：默认 8-pad Focus View。
- `scenes`：初始 `Original` scene。
- `elements`：package 中可复用的 samples、loops、chops、stems 或 patterns。
- `renders`：preview audio references。
- `metadata`：validation status 和 score context。

不要把 `patch.json` 当作 pitch authority。pitch/sample truth 读取 `lanes.json`；product layout 使用 `patch.json`。
```

- [ ] **步骤 4：运行 docs sanity check**

运行：

```bash
cd /Users/endaye/Projects/lmdj
rg -n "patch.json|Patchify" references/demos/lmdj-song-pipeline/README.md references/demos/lmdj-song-pipeline/SETUP_AND_USAGE.md
```

预期：输出中包含 README 和 SETUP_AND_USAGE 对 `patch.json` 与 `Patchify` 的引用。

- [ ] **步骤 5：运行测试，确保文档变更没有影响代码**

运行：

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
.venv/bin/python -m pytest tests/ -q
```

预期：PASS。

- [ ] **步骤 6：Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add references/demos/lmdj-song-pipeline/README.md references/demos/lmdj-song-pipeline/SETUP_AND_USAGE.md
git commit -m "docs(patchify): document patch json contract"
```

---

## 自查记录

Spec 覆盖情况：

- Idea/upload convergence 通过一个 package-to-patch adapter 覆盖：generated audio 或 uploaded audio 变成 pipeline package 之后，都会走同一个 adapter。
- Patch View 通过 8-pad Focus View model 和默认 pad slots 覆盖。
- Scene Variation 先用第一个 `Original` scene 表达；后续 generated scenes 作为独立计划处理。
- AI Talk 本计划不实现，因为它需要 UI 和 speech/input orchestration；本计划准备它未来要操作的 patch/history object surface。
- Sharing/community 本计划不实现，因为它需要 platform 和 render/export plans；本计划增加这些流程未来要消费的产品 contract。

完整性扫描：

- 本计划只包含完整的 Patchify Core tasks。UI、AI Talk、sharing 和 community implementation 明确拆到单独计划，因为它们不属于 Patchify Core。

类型一致性：

- `patch_model.Patch` 由 `patchify.build_patch()` 产出。
- `package_loader.PipelinePackage` 只被 `patchify.py` 消费。
- `pad_mapper.build_focus_pads()` 返回 `tuple[list[Element], list[Pad]]`，与 `Patch(elements=..., pads=...)` 匹配。
