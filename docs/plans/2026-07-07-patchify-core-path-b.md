# Patchify Core Path B Implementation Plan

> **修订版（2026-07-07 评审）：** 本计划经逐项契约评审后重写。相对初版的关键变化：(1) 修正 fixture 与 demo 真实输出的契约不符（`sample` vs `path`、`song_id` 来源）；(2) `patch.json` 增加 normalized `patterns[]`；(3) 新增 `packages/core-models/`，patchify 降为纯 adapter；(4) pad 采用 trigger_group 语义 + profile 检测；(5) patch_id 内容派生；(6) golden fixture 方法论。全部决策依据见 `docs/prd/decision-log.md` 2026-07-07 各条。

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 编写 LMDJ-owned 产品对象模型（core-models）与 Patchify Core（patchify adapter），把 audio pipeline package 转成稳定的 `patch.json`（schema `lmdj.patch.v1`，携带 normalized patterns），作为 Web、CLI、Audio Worker 和云端 API 的共同产品 contract。

**Architecture:** 两个正式 package，不修改 `references/demos/lmdj-song-pipeline/`：

```text
packages/core-models/   lmdj-core-models
  产品对象 dataclass（Patch/Pattern/Pad/Scene/Element/...）
  lmdj.patch.v1 JSON Schema（四方契约的机器可读来源，未来 TS codegen 种子）

packages/patchify/      lmdj-patchify（依赖 lmdj-core-models）
  纯 adapter：package loader + profile 检测 + 8-pad mapper + orchestrator + CLI
  消费 demo 输出 package（samples/*.wav, chart.mid, lanes.json, report.json）
  产出 patch.json
```

**Tech Stack:** Python 3.11+、dataclasses、JSON stdlib、`pretty_midi>=0.2.11`（已实测兼容 numpy 2.5）、`jsonschema`（仅 test）、pytest。

## Global Constraints

- `references/demos/lmdj-song-pipeline/` 只作参考、fixture 或迁移来源，不在其中新增正式产品功能。
- **输入契约以 demo 真实输出为准**（对照 `sequencer.py`/`pipeline.py` 核实）：
  - lane 条目的 wav 路径 key 是 **`sample`**（不是 `path`）；loader 兼容读 `path`，`sample` 优先；内部与输出统一为 `source_path`。
  - `song_id` 取自 **`report.json`**（`lanes.json` 里没有），fallback 到目录名。
  - `lanes.json` 顶层有 `bpm` / `bars` / `beats` / `loop_seconds`；**`length_steps = beats × 4`**，不得用 `bpm × loop_seconds` 反推（浮点），不得用 `bars`（可能为半小节小数）。
  - `chart.mid` velocity 恒为 100（demo 硬编码）；note duration 无音乐语义（鼓为 0.1s 占位、长样本为文件全长），**v1 notes 不带 duration**。
- 输出 `patch.json`，schema 固定 `lmdj.patch.v1`，**必须通过 JSON Schema 校验**；含 `patterns[]`（notes：`{element_id, lane, pitch, step, velocity}`），scene 经 `pattern_ids` 引用；`chart.mid` 作为 pattern 的 source artifact 保留，不进 `renders`。
- `patch_id = {song_id}-{sha256(lanes.json + chart.mid)[:8]}`：内容派生、确定性、幂等；schema 注明其为局部身份，全局 ID 归平台层，不得作数据库主键。
- 默认 pad surface 是 8-pad Focus View：`Drums`、`Bass`、`Harmony`、`Lead/Vocal`、`Fill`、`Drop`、`Mute`、`FX/Variation`。element 槽位用 trigger_group 语义（`behavior.element_ids` + primary `element_id`）；melody 第二候选 fallback 到 Lead/Vocal；未上 pad 的 element 记入 `metadata.unmapped_element_ids`。
- action 完整 enum：`trigger_element` / `trigger_group` / `empty` 为 v1 生效项；`scene_fill` / `scene_drop` / `mute_group` / `ai_variation` 为 **reserved**——消费方遇 unknown/reserved action 必须渲染为禁用态/no-op，不得报错。
- mapper 入口先 `detect_profile()`；v1 只支持 standard profile，ABC/DEF（`loop_*`）包显式 raise unsupported，不静默产出空 pads。
- 只做 deterministic mapping，不接 LLM，不做云端鉴权，不做数据库写入。
- 不改变参考 demo 的 `PipelineConfig.lane_pitches` 或任何 pipeline 输出逻辑。
- **测试 fixture 方法论（golden）：** happy path 必须使用真实 demo 输出（Task 3 一次性提取并提交进 `tests/fixtures/`，wav 用占位字节替换以控制体积）；错误路径 fixture 从 golden 复制后破坏单个字段，不得从零合成。package 测试自身不依赖 Demucs、MusicGen、ffmpeg。
- 安装顺序：先 `pip install -e packages/core-models`，再 `pip install -e "packages/patchify[test]"`（本地 path 依赖不写进 pyproject metadata，v1 以文档约定）。

---

## File Structure

- Create: `packages/core-models/pyproject.toml`
- Create: `packages/core-models/lmdj_core_models/__init__.py`
- Create: `packages/core-models/lmdj_core_models/model.py`
  - `SCHEMA`、`Element`、`Note`、`Pattern`、`Pad`、`Scene`、`RenderRef`、`Patch`、`write_patch_json()`、`load_patch_schema()`。
- Create: `packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json`
- Create: `packages/core-models/tests/test_model.py`
- Create: `packages/core-models/tests/test_schema.py`
- Create: `packages/patchify/tests/fixtures/testsong/`（Task 3 从真实 demo 输出提取）
- Create: `packages/patchify/pyproject.toml`
- Create: `packages/patchify/lmdj_patchify/__init__.py`
- Create: `packages/patchify/lmdj_patchify/package_loader.py`
- Create: `packages/patchify/lmdj_patchify/pad_mapper.py`
- Create: `packages/patchify/lmdj_patchify/patchify.py`
- Create: `packages/patchify/lmdj_patchify/cli.py`
- Create: `packages/patchify/tests/conftest.py`
- Create: `packages/patchify/tests/test_package_loader.py`
- Create: `packages/patchify/tests/test_pad_mapper.py`
- Create: `packages/patchify/tests/test_patchify.py`
- Modify: `packages/README.md`

---

### Task 1: core-models Package Skeleton And Model

**Files:**
- Create: `packages/core-models/pyproject.toml`
- Create: `packages/core-models/lmdj_core_models/__init__.py`
- Create: `packages/core-models/lmdj_core_models/model.py`
- Create: `packages/core-models/tests/test_model.py`

**Interfaces:**
- Consumes: no previous task.
- Produces:
  - `SCHEMA: str`
  - `Element(element_id, name, kind, source_path, pitch, lane, role=None)`
  - `Note(element_id, lane, pitch, step, velocity)`
  - `Pattern(pattern_id, name, source, resolution, length_steps, notes)`
  - `Pad(index, slot, label, action, element_id, behavior)`
  - `Scene(scene_id, name, pad_indexes, pattern_ids, intent)`
  - `RenderRef(kind, path)`
  - `Patch(patch_id, source, bpm, loop_seconds, elements, patterns, pads, scenes, renders, metadata)`
  - `write_patch_json(patch, out_path) -> None`

- [ ] **Step 1: Write the failing test**

Create `packages/core-models/tests/test_model.py`:

```python
import json
from pathlib import Path

from lmdj_core_models.model import (
    Element, Note, Pad, Patch, Pattern, RenderRef, Scene, write_patch_json,
)


def _sample_patch() -> Patch:
    element = Element(
        element_id="el_kick", name="kick", kind="drum",
        source_path="samples/kick.wav", pitch=36, lane=0, role="drums",
    )
    pattern = Pattern(
        pattern_id="pattern_original", name="Original",
        source={"kind": "midi", "path": "chart.mid"},
        resolution="1/16", length_steps=64,
        notes=[Note(element_id="el_kick", lane=0, pitch=36, step=0, velocity=100)],
    )
    return Patch(
        patch_id="testsong-abcd1234",
        source={"type": "pipeline_package", "song_id": "testsong"},
        bpm=90.0, loop_seconds=10.667,
        elements=[element],
        patterns=[pattern],
        pads=[Pad(0, "Drums", "kick", "trigger_group", "el_kick",
                  {"trigger": "one_shot", "quantize": "1/16", "element_ids": ["el_kick"]})],
        scenes=[Scene("scene_original", "Original", [0], ["pattern_original"],
                      "Pipeline default scene")],
        renders=[RenderRef(kind="loop_preview", path="loop_preview.wav")],
        metadata={"status": "passed", "score": 0.8},
    )


def test_patch_model_writes_stable_patch_json(tmp_path: Path):
    out_path = tmp_path / "patch.json"
    write_patch_json(_sample_patch(), out_path)
    data = json.loads(out_path.read_text())

    assert data["schema"] == "lmdj.patch.v1"
    assert data["patch_id"] == "testsong-abcd1234"
    assert data["patterns"][0]["length_steps"] == 64
    assert data["patterns"][0]["notes"][0] == {
        "element_id": "el_kick", "lane": 0, "pitch": 36, "step": 0, "velocity": 100,
    }
    assert data["pads"][0]["behavior"]["element_ids"] == ["el_kick"]
    assert data["scenes"][0]["pattern_ids"] == ["pattern_original"]
    assert data["elements"][0]["source_path"] == "samples/kick.wav"


def test_write_patch_json_is_deterministic(tmp_path: Path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    write_patch_json(_sample_patch(), a)
    write_patch_json(_sample_patch(), b)
    assert a.read_bytes() == b.read_bytes()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/endaye/Projects/lmdj/packages/core-models
python3 -m venv .venv
.venv/bin/pip install pytest jsonschema
.venv/bin/python -m pytest tests/test_model.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lmdj_core_models'`.

- [ ] **Step 3: Add package config and model implementation**

Create `packages/core-models/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "lmdj-core-models"
version = "0.1.0"
description = "LMDJ product object models and contracts"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
test = [
  "pytest>=8,<9",
  "jsonschema>=4,<5",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["lmdj_core_models*"]

[tool.setuptools.package-data]
lmdj_core_models = ["schemas/*.json"]
```

Create `packages/core-models/lmdj_core_models/__init__.py`:

```python
from lmdj_core_models.model import (
    SCHEMA, Element, Note, Pad, Patch, Pattern, RenderRef, Scene,
    load_patch_schema, write_patch_json,
)

__all__ = [
    "SCHEMA", "Element", "Note", "Pad", "Patch", "Pattern", "RenderRef",
    "Scene", "load_patch_schema", "write_patch_json",
]
```

Create `packages/core-models/lmdj_core_models/model.py`:

```python
from __future__ import annotations

import importlib.resources
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "lmdj.patch.v1"

# v1 生效 action；其余 enum 项为 reserved（消费方必须 no-op）
LIVE_ACTIONS = frozenset({"trigger_element", "trigger_group", "empty"})
RESERVED_ACTIONS = frozenset({"scene_fill", "scene_drop", "mute_group", "ai_variation"})


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
class Note:
    element_id: str
    lane: int
    pitch: int
    step: int
    velocity: int  # v1 pipeline 输出恒为 100（demo 硬编码），无信息量

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Pattern:
    pattern_id: str
    name: str
    source: dict[str, Any]        # e.g. {"kind": "midi", "path": "chart.mid"}
    resolution: str               # v1 固定 "1/16"
    length_steps: int             # beats * 4；step 域为 [0, length_steps)
    notes: list[Note]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "name": self.name,
            "source": self.source,
            "resolution": self.resolution,
            "length_steps": self.length_steps,
            "notes": [note.to_dict() for note in self.notes],
        }


@dataclass(frozen=True)
class Pad:
    index: int
    slot: str
    label: str
    action: str
    element_id: str | None        # trigger 类 action 的 primary element
    behavior: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Scene:
    scene_id: str
    name: str
    pad_indexes: list[int]
    pattern_ids: list[str]
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
    patch_id: str                 # 内容派生的局部身份；全局 ID 由平台层分配
    source: dict[str, Any]
    bpm: float
    loop_seconds: float
    elements: list[Element]
    patterns: list[Pattern]
    pads: list[Pad]
    scenes: list[Scene]
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
            "elements": [element.to_dict() for element in self.elements],
            "patterns": [pattern.to_dict() for pattern in self.patterns],
            "pads": [pad.to_dict() for pad in self.pads],
            "scenes": [scene.to_dict() for scene in self.scenes],
            "renders": [render.to_dict() for render in self.renders],
            "metadata": self.metadata,
        }


def write_patch_json(patch: Patch, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(patch.to_dict(), indent=2, ensure_ascii=False) + "\n")


def load_patch_schema() -> dict[str, Any]:
    ref = importlib.resources.files("lmdj_core_models").joinpath(
        "schemas/lmdj.patch.v1.schema.json")
    return json.loads(ref.read_text())
```

注意：`load_patch_schema` 在 Task 2 提供 schema 文件之前不可调用；Task 1 测试不触碰它。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/endaye/Projects/lmdj/packages/core-models
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest tests/test_model.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add packages/core-models
git commit -m "feat(core-models): add product patch model"
```

---

### Task 2: lmdj.patch.v1 JSON Schema

**Files:**
- Create: `packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json`
- Create: `packages/core-models/tests/test_schema.py`

**Interfaces:**
- Consumes: `Patch` model 与 `load_patch_schema()` from Task 1.
- Produces: 可被 `jsonschema` 校验的 `lmdj.patch.v1` 契约文件；未来 TS codegen 的输入。

- [ ] **Step 1: Write failing schema tests**

Create `packages/core-models/tests/test_schema.py`:

```python
import jsonschema
import pytest

from lmdj_core_models.model import load_patch_schema

from tests.test_model import _sample_patch


def test_sample_patch_validates_against_schema():
    schema = load_patch_schema()
    jsonschema.validate(_sample_patch().to_dict(), schema)


def test_schema_rejects_unknown_action():
    schema = load_patch_schema()
    data = _sample_patch().to_dict()
    data["pads"][0]["action"] = "definitely_not_an_action"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_schema_rejects_wrong_schema_id():
    schema = load_patch_schema()
    data = _sample_patch().to_dict()
    data["schema"] = "lmdj.patch.v0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)
```

（若 `tests` 无法作为 package 导入，给 `packages/core-models/tests/` 加空 `__init__.py`，或把 `_sample_patch` 提为 `conftest.py` fixture——两种皆可，选一即可。）

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/endaye/Projects/lmdj/packages/core-models
.venv/bin/python -m pytest tests/test_schema.py -q
```

Expected: FAIL（schema 文件不存在，`load_patch_schema` 抛 FileNotFoundError）。

- [ ] **Step 3: Write the schema file**

Create `packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://lmdj.app/schemas/lmdj.patch.v1.schema.json",
  "title": "lmdj.patch.v1",
  "description": "LMDJ product patch contract. Forward-compat rule: consumers MUST render unknown or reserved pad actions as disabled/no-op, never as errors. patch_id is a content-derived LOCAL identifier (song_id + sha256(lanes.json+chart.mid)[:8]); global identity is assigned by the platform layer — do not use patch_id as a database primary key. In v1 pipeline output, note velocity is always 100 (no dynamics information).",
  "type": "object",
  "required": ["schema", "patch_id", "source", "bpm", "loop_seconds", "elements", "patterns", "pads", "scenes", "renders", "metadata"],
  "properties": {
    "schema": {"const": "lmdj.patch.v1"},
    "patch_id": {"type": "string", "minLength": 1},
    "source": {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": {"type": "string"},
        "song_id": {"type": "string"}
      }
    },
    "bpm": {"type": "number", "exclusiveMinimum": 0},
    "loop_seconds": {"type": "number", "exclusiveMinimum": 0},
    "elements": {"type": "array", "items": {"$ref": "#/$defs/element"}},
    "patterns": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/pattern"}},
    "pads": {"type": "array", "items": {"$ref": "#/$defs/pad"}},
    "scenes": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/scene"}},
    "renders": {"type": "array", "items": {"$ref": "#/$defs/render"}},
    "metadata": {"type": "object"}
  },
  "$defs": {
    "element": {
      "type": "object",
      "required": ["element_id", "name", "kind", "source_path", "pitch", "lane"],
      "properties": {
        "element_id": {"type": "string", "minLength": 1},
        "name": {"type": "string"},
        "kind": {"type": "string"},
        "source_path": {"type": "string"},
        "pitch": {"type": "integer", "minimum": 0, "maximum": 127},
        "lane": {"type": "integer", "minimum": 0},
        "role": {"type": ["string", "null"]}
      }
    },
    "note": {
      "type": "object",
      "required": ["element_id", "lane", "pitch", "step", "velocity"],
      "properties": {
        "element_id": {"type": "string", "minLength": 1},
        "lane": {"type": "integer", "minimum": 0},
        "pitch": {"type": "integer", "minimum": 0, "maximum": 127},
        "step": {"type": "integer", "minimum": 0},
        "velocity": {"type": "integer", "minimum": 0, "maximum": 127}
      }
    },
    "pattern": {
      "type": "object",
      "required": ["pattern_id", "name", "source", "resolution", "length_steps", "notes"],
      "properties": {
        "pattern_id": {"type": "string", "minLength": 1},
        "name": {"type": "string"},
        "source": {
          "type": "object",
          "required": ["kind", "path"],
          "properties": {
            "kind": {"type": "string"},
            "path": {"type": "string"}
          }
        },
        "resolution": {"const": "1/16"},
        "length_steps": {"type": "integer", "minimum": 1},
        "notes": {"type": "array", "items": {"$ref": "#/$defs/note"}}
      }
    },
    "pad": {
      "type": "object",
      "required": ["index", "slot", "label", "action", "element_id", "behavior"],
      "properties": {
        "index": {"type": "integer", "minimum": 0},
        "slot": {"type": "string"},
        "label": {"type": "string"},
        "action": {
          "description": "trigger_element / trigger_group / empty are live in v1. scene_fill / scene_drop / mute_group / ai_variation are RESERVED: consumers must render them disabled and perform no action.",
          "enum": ["trigger_element", "trigger_group", "empty", "scene_fill", "scene_drop", "mute_group", "ai_variation"]
        },
        "element_id": {"type": ["string", "null"]},
        "behavior": {"type": "object"}
      }
    },
    "scene": {
      "type": "object",
      "required": ["scene_id", "name", "pad_indexes", "pattern_ids", "intent"],
      "properties": {
        "scene_id": {"type": "string", "minLength": 1},
        "name": {"type": "string"},
        "pad_indexes": {"type": "array", "items": {"type": "integer", "minimum": 0}},
        "pattern_ids": {"type": "array", "items": {"type": "string"}},
        "intent": {"type": "string"}
      }
    },
    "render": {
      "type": "object",
      "required": ["kind", "path"],
      "properties": {
        "kind": {"type": "string"},
        "path": {"type": "string"}
      }
    }
  }
}
```

已知限制（JSON Schema 表达不了、由 Python 测试补断言）：`note.step < pattern.length_steps`、`note.element_id`/`pad.element_id` 必须存在于 `elements`。

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/endaye/Projects/lmdj/packages/core-models
.venv/bin/python -m pytest tests/ -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add packages/core-models
git commit -m "feat(core-models): add lmdj.patch.v1 json schema"
```

---

### Task 3: Golden Fixture Extraction（procedural，一次性）

**Files:**
- Create: `packages/patchify/tests/fixtures/testsong/`（`lanes.json`、`report.json`、`chart.mid` 为真实产物；`samples/*.wav` 与 preview wav 为占位字节）

**Interfaces:**
- Consumes: 参考 demo 的 `make_test_song.py` + pipeline（一次性运行，之后的测试不再依赖 demo）。
- Produces: 提交进 git 的 golden fixture，Task 4-6 的所有 happy-path 测试以它为准。

- [ ] **Step 1: 生成真实 demo package（demo venv 内，stems 已缓存故跳过 demucs）**

```bash
cd /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline
python3 -m venv .venv                      # 若已存在则跳过
.venv/bin/pip install -e .
.venv/bin/python scripts/make_test_song.py output/testsong
.venv/bin/song-pipeline run output/testsong/input.wav --song-id testsong --fast
```

Expected: `output/testsong/` 下生成 `lanes.json`、`report.json`、`chart.mid`、`samples/*.wav`、`loop_preview.wav`、`render_preview.wav`。

- [ ] **Step 2: 提取为 golden fixture（真实 json/mid + 占位 wav）**

```bash
cd /Users/endaye/Projects/lmdj
python3 - <<'EOF'
import json
from pathlib import Path

src = Path("references/demos/lmdj-song-pipeline/output/testsong")
dst = Path("packages/patchify/tests/fixtures/testsong")
dst.mkdir(parents=True, exist_ok=True)

for name in ["lanes.json", "report.json", "chart.mid"]:
    (dst / name).write_bytes((src / name).read_bytes())

lanes = json.loads((dst / "lanes.json").read_text())
for row in lanes["lanes"]:
    p = dst / row["sample"]                    # 真实契约 key：sample
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"RIFF....WAVEfmt placeholder")
for name in ["loop_preview.wav", "render_preview.wav"]:
    (dst / name).write_bytes(b"RIFF....WAVEfmt placeholder")

print("fixture files:", sorted(str(p.relative_to(dst)) for p in dst.rglob("*") if p.is_file()))
EOF
```

- [ ] **Step 3: 确认 fixture 进入版本控制并提交**

```bash
cd /Users/endaye/Projects/lmdj
git status --short packages/patchify/tests/fixtures/   # 必须全部可见（未被 gitignore 拦截）
git add packages/patchify/tests/fixtures
git commit -m "test(patchify): add golden fixture from reference pipeline output"
```

---

### Task 4: patchify Package Skeleton And Loader

**Files:**
- Create: `packages/patchify/pyproject.toml`
- Create: `packages/patchify/lmdj_patchify/__init__.py`
- Create: `packages/patchify/lmdj_patchify/package_loader.py`
- Create: `packages/patchify/tests/conftest.py`
- Create: `packages/patchify/tests/test_package_loader.py`

**Interfaces:**
- Consumes: `Element`、`Note` from Task 1；golden fixture from Task 3.
- Produces:
  - `LoadedPackage(root, song_id, bpm, beats, loop_seconds, elements, notes, report, midi_pitches)`
  - `load_package(package_dir: Path) -> LoadedPackage`
  - Raises `ValueError`：缺必需文件、缺 sample 文件、lane 缺 wav key、MIDI pitch 不在 lanes 中。

- [ ] **Step 1: Write conftest and failing loader tests**

Create `packages/patchify/tests/conftest.py`:

```python
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def golden_package(tmp_path: Path) -> Path:
    """真实 demo 输出的副本；错误路径测试在副本上破坏单个字段。"""
    root = tmp_path / "testsong"
    shutil.copytree(FIXTURES / "testsong", root)
    return root
```

Create `packages/patchify/tests/test_package_loader.py`:

```python
import json
from pathlib import Path

import pretty_midi
import pytest

from lmdj_patchify.package_loader import load_package


def test_load_package_matches_golden_lanes(golden_package: Path):
    loaded = load_package(golden_package)
    raw = json.loads((golden_package / "lanes.json").read_text())

    assert loaded.song_id == "testsong"
    assert loaded.bpm == float(raw["bpm"])
    assert loaded.beats == int(raw["beats"])
    assert loaded.loop_seconds == float(raw["loop_seconds"])
    # loader 输出与 lanes.json 逐行对应（契约 key 是 sample）
    assert [(e.name, e.pitch, e.lane, e.source_path) for e in loaded.elements] == [
        (r["name"], r["pitch"], r["lane"], r["sample"]) for r in raw["lanes"]
    ]


def test_load_package_parses_normalized_notes(golden_package: Path):
    loaded = load_package(golden_package)
    length_steps = loaded.beats * 4
    element_ids = {e.element_id for e in loaded.elements}

    assert loaded.notes, "golden chart.mid must contain notes"
    for note in loaded.notes:
        assert 0 <= note.step < length_steps
        assert note.element_id in element_ids
        assert note.velocity == 100          # demo 硬编码
    assert loaded.notes == sorted(loaded.notes, key=lambda n: (n.step, n.pitch))


def test_load_package_accepts_legacy_path_key(golden_package: Path):
    raw = json.loads((golden_package / "lanes.json").read_text())
    for row in raw["lanes"]:
        row["path"] = row.pop("sample")      # 兼容读 path
    (golden_package / "lanes.json").write_text(json.dumps(raw))

    loaded = load_package(golden_package)
    assert loaded.elements[0].source_path == raw["lanes"][0]["path"]


def test_load_package_rejects_missing_sample(golden_package: Path):
    raw = json.loads((golden_package / "lanes.json").read_text())
    (golden_package / raw["lanes"][0]["sample"]).unlink()

    with pytest.raises(ValueError, match="Missing sample file"):
        load_package(golden_package)


def test_load_package_rejects_pitch_not_declared_in_lanes(golden_package: Path):
    midi = pretty_midi.PrettyMIDI(initial_tempo=90)
    inst = pretty_midi.Instrument(program=0, name="broken")
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=127, start=0.0, end=0.1))
    midi.instruments.append(inst)
    midi.write(str(golden_package / "chart.mid"))

    with pytest.raises(ValueError, match="MIDI pitches missing from lanes.json"):
        load_package(golden_package)


def test_load_package_rejects_missing_required_file(golden_package: Path):
    (golden_package / "lanes.json").unlink()

    with pytest.raises(ValueError, match="Missing required file"):
        load_package(golden_package)
```

- [ ] **Step 2: Add package config, run tests to verify they fail**

Create `packages/patchify/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "lmdj-patchify"
version = "0.1.0"
description = "LMDJ Patchify core adapter"
requires-python = ">=3.11"
# 另需本地安装 lmdj-core-models（path 依赖不写 metadata）：
#   pip install -e ../core-models
dependencies = [
  "pretty_midi>=0.2.11,<1",
]

[project.optional-dependencies]
test = [
  "pytest>=8,<9",
  "jsonschema>=4,<5",
]

[project.scripts]
lmdj-patchify = "lmdj_patchify.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["lmdj_patchify*"]
```

Create `packages/patchify/lmdj_patchify/__init__.py`（先空文件，Task 6 补全导出）。

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
python3 -m venv .venv
.venv/bin/pip install -e ../core-models
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest tests/test_package_loader.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lmdj_patchify.package_loader'`.

- [ ] **Step 3: Implement loader**

Create `packages/patchify/lmdj_patchify/package_loader.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pretty_midi

from lmdj_core_models.model import Element, Note


@dataclass(frozen=True)
class LoadedPackage:
    root: Path
    song_id: str
    bpm: float
    beats: int
    loop_seconds: float
    elements: list[Element]
    notes: list[Note]
    report: dict[str, Any]
    midi_pitches: set[int]


def load_package(package_dir: Path) -> LoadedPackage:
    root = package_dir.resolve()
    lanes_path = root / "lanes.json"
    report_path = root / "report.json"
    midi_path = root / "chart.mid"

    for required in [lanes_path, report_path, midi_path]:
        if not required.exists():
            raise ValueError(f"Missing required file: {required.name}")

    lanes_data = json.loads(lanes_path.read_text())
    report = json.loads(report_path.read_text())
    lane_rows = lanes_data.get("lanes")
    if not isinstance(lane_rows, list) or not lane_rows:
        raise ValueError("lanes.json must contain a non-empty lanes list")

    beats = int(lanes_data["beats"])
    loop_seconds = float(lanes_data["loop_seconds"])
    length_steps = beats * 4

    elements: list[Element] = []
    by_pitch: dict[int, Element] = {}
    for row in lane_rows:
        # demo 真实契约 key 是 sample；path 仅作兼容读取
        source_path = row.get("sample") or row.get("path")
        if not source_path:
            raise ValueError(f"lane {row.get('lane')} missing sample path")
        if not (root / str(source_path)).exists():
            raise ValueError(f"Missing sample file: {source_path}")
        element = Element(
            element_id=f"el_{row['name']}",
            name=str(row["name"]),
            kind=str(row["kind"]),
            source_path=str(source_path),
            pitch=int(row["pitch"]),
            lane=int(row["lane"]),
            role=_infer_role(str(row["name"]), str(row["kind"])),
        )
        elements.append(element)
        by_pitch[element.pitch] = element

    midi = pretty_midi.PrettyMIDI(str(midi_path))
    midi_notes = [n for inst in midi.instruments for n in inst.notes]
    midi_pitches = {n.pitch for n in midi_notes}
    missing = midi_pitches - set(by_pitch)
    if missing:
        raise ValueError(f"MIDI pitches missing from lanes.json: {sorted(missing)}")

    notes = sorted(
        (
            Note(
                element_id=by_pitch[n.pitch].element_id,
                lane=by_pitch[n.pitch].lane,
                pitch=n.pitch,
                step=_time_to_step(n.start, loop_seconds, length_steps),
                velocity=int(n.velocity),
            )
            for n in midi_notes
        ),
        key=lambda note: (note.step, note.pitch),
    )

    return LoadedPackage(
        root=root,
        song_id=str(report.get("song_id") or root.name),
        bpm=float(lanes_data["bpm"]),
        beats=beats,
        loop_seconds=loop_seconds,
        elements=elements,
        notes=notes,
        report=report,
        midi_pitches=midi_pitches,
    )


def _time_to_step(time_sec: float, loop_seconds: float, length_steps: int) -> int:
    """chart.mid onset 已按 demo 自身 16 分网格量化；此处按均匀网格取最近步。

    末端网格点折回 step 0，与 demo sequencer 的折回行为一致。已知近似：demo 的
    beat 网格可能非严格均匀，偏差超过半步（>12.5% beat）时可能错位一步；v1 接受。
    """
    return round(time_sec * length_steps / loop_seconds) % length_steps


def _infer_role(name: str, kind: str) -> str:
    lowered = name.lower()
    if kind == "drum" or lowered in {"kick", "snare", "hat", "hihat"}:
        return "drums"
    if "bass" in lowered:
        return "bass"
    if "vocal" in lowered or "lead" in lowered:
        return "lead"
    if "melody" in lowered or "harmony" in lowered or "chord" in lowered:
        return "harmony"
    return "material"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/test_package_loader.py -q
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add packages/patchify/pyproject.toml packages/patchify/lmdj_patchify packages/patchify/tests/conftest.py packages/patchify/tests/test_package_loader.py
git commit -m "feat(patchify): load pipeline package against real demo contract"
```

---

### Task 5: Profile Detection And 8-Pad Focus Mapper

**Files:**
- Create: `packages/patchify/lmdj_patchify/pad_mapper.py`
- Create: `packages/patchify/tests/test_pad_mapper.py`

**Interfaces:**
- Consumes: `Element`、`Pad` from Task 1.
- Produces:
  - `FOCUS_SLOTS: list[str]`
  - `detect_profile(elements: list[Element]) -> str`（`"standard"` | `"loops"`）
  - `map_focus_pads(elements: list[Element]) -> list[Pad]`

- [ ] **Step 1: Write failing mapper tests**

Create `packages/patchify/tests/test_pad_mapper.py`:

```python
from lmdj_core_models.model import Element
from lmdj_patchify.pad_mapper import FOCUS_SLOTS, detect_profile, map_focus_pads


def _el(name: str, kind: str, pitch: int, lane: int, role: str) -> Element:
    return Element(f"el_{name}", name, kind, f"samples/{name}.wav", pitch, lane, role)


STANDARD = [
    _el("kick", "drum", 36, 0, "drums"),
    _el("snare", "drum", 38, 1, "drums"),
    _el("hat", "drum", 42, 2, "drums"),
    _el("bass", "long", 48, 3, "bass"),
    _el("melody_a", "long", 50, 4, "harmony"),
    _el("melody_b", "long", 52, 5, "harmony"),
]


def test_detect_profile():
    assert detect_profile(STANDARD) == "standard"
    loops = [_el(f"loop_{c}", "long", 60 + i, i, "material") for i, c in enumerate("abc")]
    assert detect_profile(loops) == "loops"


def test_map_focus_pads_groups_drums_under_one_pad():
    pads = map_focus_pads(STANDARD)

    assert [pad.slot for pad in pads] == FOCUS_SLOTS
    drums = pads[0]
    assert drums.action == "trigger_group"
    assert drums.element_id == "el_kick"                       # primary
    assert drums.behavior["element_ids"] == ["el_kick", "el_snare", "el_hat"]
    assert pads[1].action == "trigger_element"                 # bass 单 element
    assert pads[1].behavior["element_ids"] == ["el_bass"]


def test_second_melody_falls_back_to_lead_slot():
    pads = map_focus_pads(STANDARD)

    assert pads[2].element_id == "el_melody_a"                 # Harmony
    assert pads[3].element_id == "el_melody_b"                 # Lead/Vocal fallback
    assert pads[3].action == "trigger_element"


def test_control_pads_use_reserved_actions():
    pads = map_focus_pads(STANDARD)

    assert [pads[i].action for i in (4, 5, 6, 7)] == [
        "scene_fill", "scene_drop", "mute_group", "ai_variation",
    ]


def test_map_focus_pads_keeps_empty_slots_playable_as_controls():
    pads = map_focus_pads([])

    assert len(pads) == 8
    assert pads[0].action == "empty"
    assert pads[4].action == "scene_fill"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/test_pad_mapper.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lmdj_patchify.pad_mapper'`.

- [ ] **Step 3: Implement mapper**

Create `packages/patchify/lmdj_patchify/pad_mapper.py`:

```python
from __future__ import annotations

from lmdj_core_models.model import Element, Pad

FOCUS_SLOTS = [
    "Drums",
    "Bass",
    "Harmony",
    "Lead/Vocal",
    "Fill",
    "Drop",
    "Mute",
    "FX/Variation",
]

_SEMANTIC_ROLES = ("drums", "bass", "harmony", "lead")


def detect_profile(elements: list[Element]) -> str:
    """standard：至少一个 element 有语义 role；loops：ABC/DEF 类全 loop_* 包。"""
    if any(e.role in _SEMANTIC_ROLES for e in elements):
        return "standard"
    return "loops"


def map_focus_pads(elements: list[Element]) -> list[Pad]:
    groups = {role: [e for e in elements if e.role == role] for role in _SEMANTIC_ROLES}
    if not groups["lead"] and len(groups["harmony"]) > 1:
        # demo 从不产出 lead/vocal 名；melody 第二候选 fallback 到 Lead/Vocal 槽位
        groups["lead"] = [groups["harmony"].pop(1)]

    return [
        _group_pad(0, "Drums", groups["drums"]),
        _group_pad(1, "Bass", groups["bass"]),
        _group_pad(2, "Harmony", groups["harmony"]),
        _group_pad(3, "Lead/Vocal", groups["lead"]),
        # reserved actions：v1 无语义，消费方必须 no-op（见 schema description）
        Pad(4, "Fill", "Fill", "scene_fill", None, {"quantize": "1 bar"}),
        Pad(5, "Drop", "Drop", "scene_drop", None, {"quantize": "1 bar"}),
        Pad(6, "Mute", "Mute", "mute_group", None, {"target": "selected_or_master"}),
        Pad(7, "FX/Variation", "FX", "ai_variation", None, {"scope": "scene"}),
    ]


def _group_pad(index: int, slot: str, group: list[Element]) -> Pad:
    if not group:
        return Pad(index, slot, slot, "empty", None, {})
    primary = group[0]
    return Pad(
        index=index,
        slot=slot,
        label=primary.name,
        action="trigger_element" if len(group) == 1 else "trigger_group",
        element_id=primary.element_id,
        behavior={
            "trigger": "one_shot" if primary.kind == "drum" else "loop",
            "quantize": "1/16",
            "element_ids": [e.element_id for e in group],
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/test_pad_mapper.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add packages/patchify/lmdj_patchify/pad_mapper.py packages/patchify/tests/test_pad_mapper.py
git commit -m "feat(patchify): map elements to focus pads with profiles and groups"
```

---

### Task 6: Patchify Orchestrator, CLI And Docs

**Files:**
- Modify: `packages/patchify/lmdj_patchify/__init__.py`
- Create: `packages/patchify/lmdj_patchify/patchify.py`
- Create: `packages/patchify/lmdj_patchify/cli.py`
- Create: `packages/patchify/tests/test_patchify.py`
- Modify: `packages/README.md`

**Interfaces:**
- Consumes: `load_package` from Task 4、`detect_profile`/`map_focus_pads` from Task 5、model + schema from Tasks 1-2.
- Produces:
  - `patchify_package(package_dir: Path, out_path: Path | None = None) -> Patch`
  - CLI: `lmdj-patchify PACKAGE_DIR [--out OUT_PATH]`（含 `python -m lmdj_patchify.cli` 入口）

- [ ] **Step 1: Write failing orchestrator and CLI tests**

Create `packages/patchify/tests/test_patchify.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from lmdj_core_models.model import load_patch_schema
from lmdj_patchify.patchify import patchify_package


def test_patchify_package_writes_valid_patch_json(golden_package: Path):
    patch = patchify_package(golden_package)
    data = json.loads((golden_package / "patch.json").read_text())

    jsonschema.validate(data, load_patch_schema())          # 输出必须过 schema
    assert data["schema"] == "lmdj.patch.v1"
    assert data["patch_id"].startswith("testsong-")
    assert len(data["patch_id"].split("-")[-1]) == 8        # 内容 hash 短前缀
    assert data["patterns"][0]["length_steps"] == patch.patterns[0].length_steps
    assert data["patterns"][0]["notes"], "patterns must carry normalized notes"
    assert data["scenes"][0]["pattern_ids"] == ["pattern_original"]

    element_ids = {e["element_id"] for e in data["elements"]}
    mapped = {eid for pad in data["pads"] for eid in pad["behavior"].get("element_ids", [])}
    assert set(data["metadata"]["unmapped_element_ids"]) == element_ids - mapped


def test_patchify_is_deterministic(golden_package: Path, tmp_path: Path):
    out_a, out_b = tmp_path / "a.json", tmp_path / "b.json"
    patchify_package(golden_package, out_a)
    patchify_package(golden_package, out_b)
    assert out_a.read_bytes() == out_b.read_bytes()


def test_patchify_rejects_loops_profile(golden_package: Path):
    raw = json.loads((golden_package / "lanes.json").read_text())
    # 从 golden 派生：把所有 lane 改名为 loop_*（ABC/DEF 包形态），pitch/sample 不变
    for i, row in enumerate(raw["lanes"]):
        new_name = f"loop_{chr(ord('a') + i)}"
        sample_path = golden_package / row["sample"]
        new_rel = f"samples/{new_name}.wav"
        sample_path.rename(golden_package / new_rel)
        row.update(name=new_name, kind="long", sample=new_rel)
    (golden_package / "lanes.json").write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="unsupported package profile"):
        patchify_package(golden_package)


def test_cli_writes_custom_output_path(golden_package: Path):
    out_path = golden_package / "custom-patch.json"

    result = subprocess.run(
        [sys.executable, "-m", "lmdj_patchify.cli", str(golden_package), "--out", str(out_path)],
        check=True,
        text=True,
        capture_output=True,
    )

    data = json.loads(out_path.read_text())
    assert data["patch_id"].startswith("testsong-")
    assert str(out_path) in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/test_patchify.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lmdj_patchify.patchify'`.

- [ ] **Step 3: Implement orchestrator and CLI**

Update `packages/patchify/lmdj_patchify/__init__.py`:

```python
from lmdj_patchify.package_loader import LoadedPackage, load_package
from lmdj_patchify.pad_mapper import FOCUS_SLOTS, detect_profile, map_focus_pads
from lmdj_patchify.patchify import patchify_package

__all__ = [
    "FOCUS_SLOTS", "LoadedPackage", "detect_profile", "load_package",
    "map_focus_pads", "patchify_package",
]
```

Create `packages/patchify/lmdj_patchify/patchify.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from lmdj_core_models.model import Patch, Pattern, RenderRef, Scene, write_patch_json
from lmdj_patchify.package_loader import load_package
from lmdj_patchify.pad_mapper import detect_profile, map_focus_pads


def patchify_package(package_dir: Path, out_path: Path | None = None) -> Patch:
    loaded = load_package(package_dir)
    profile = detect_profile(loaded.elements)
    if profile != "standard":
        raise ValueError(
            f"unsupported package profile: {profile} (v1 only maps standard packages)")

    pads = map_focus_pads(loaded.elements)
    pattern = Pattern(
        pattern_id="pattern_original",
        name="Original",
        source={"kind": "midi", "path": "chart.mid"},
        resolution="1/16",
        length_steps=loaded.beats * 4,
        notes=loaded.notes,
    )
    mapped_ids = {eid for pad in pads for eid in pad.behavior.get("element_ids", [])}
    patch = Patch(
        patch_id=f"{loaded.song_id}-{_content_hash(loaded.root)}",
        source={"type": "pipeline_package", "song_id": loaded.song_id},
        bpm=loaded.bpm,
        loop_seconds=loaded.loop_seconds,
        elements=loaded.elements,
        patterns=[pattern],
        pads=pads,
        scenes=[
            Scene(
                scene_id="scene_original",
                name="Original",
                pad_indexes=[pad.index for pad in pads],
                pattern_ids=[pattern.pattern_id],
                intent="Pipeline default scene",
            )
        ],
        renders=_discover_renders(loaded.root),
        metadata={
            "source_package": str(loaded.root),
            "status": loaded.report.get("status"),
            "score": loaded.report.get("score"),
            "midi_pitches": sorted(loaded.midi_pitches),
            "unmapped_element_ids": sorted(
                e.element_id for e in loaded.elements if e.element_id not in mapped_ids),
        },
    )
    write_patch_json(patch, out_path or loaded.root / "patch.json")
    return patch


def _content_hash(root: Path) -> str:
    """patch_id 的内容派生部分：同输入必得同 id（worker 重跑幂等的地基）。"""
    digest = hashlib.sha256()
    digest.update((root / "lanes.json").read_bytes())
    digest.update((root / "chart.mid").read_bytes())
    return digest.hexdigest()[:8]


def _discover_renders(root: Path) -> list[RenderRef]:
    renders: list[RenderRef] = []
    for kind, filename in [
        ("loop_preview", "loop_preview.wav"),
        ("render_preview", "render_preview.wav"),
    ]:
        if (root / filename).exists():
            renders.append(RenderRef(kind=kind, path=filename))
    return renders
```

Create `packages/patchify/lmdj_patchify/cli.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from lmdj_patchify.patchify import patchify_package


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an LMDJ patch.json from a pipeline package.")
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    patchify_package(args.package_dir, args.out)
    out_path = args.out or args.package_dir / "patch.json"
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Document package verification commands**

Update `packages/README.md` by appending:

````markdown
## 本地验证

```bash
# core-models
cd packages/core-models
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest tests/ -q

# patchify（依赖 core-models，注意安装顺序）
cd ../patchify
python3 -m venv .venv
.venv/bin/pip install -e ../core-models
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest tests/ -q
```

对一个 pipeline package 目录运行 CLI：

```bash
.venv/bin/lmdj-patchify /path/to/package
# 或不依赖 console script：
.venv/bin/python -m lmdj_patchify.cli /path/to/package
```
````

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/ -q
```

Expected: all tests pass（loader 6 + mapper 5 + patchify 4 = 15 passed）。

- [ ] **Step 6: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add packages/patchify packages/README.md
git commit -m "feat(patchify): generate patch json with patterns from package"
```

---

## Verification

全计划验证（Task 6 之后）：

```bash
cd /Users/endaye/Projects/lmdj/packages/core-models
.venv/bin/python -m pytest tests/ -q     # expected: 5 passed

cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/ -q     # expected: 15 passed
```

真实 package 冒烟（**非可选**——Task 3 已保证 demo output/testsong 存在）：

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/lmdj-patchify /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline/output/testsong
.venv/bin/python - <<'EOF'
import json, jsonschema
from lmdj_core_models.model import load_patch_schema
data = json.loads(open(
    "/Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline/output/testsong/patch.json"
).read())
jsonschema.validate(data, load_patch_schema())
print("patch_id:", data["patch_id"])
print("pads:", [(p["slot"], p["action"]) for p in data["pads"]])
print("pattern notes:", len(data["patterns"][0]["notes"]),
      "/ length_steps:", data["patterns"][0]["length_steps"])
print("unmapped:", data["metadata"]["unmapped_element_ids"])
EOF
```

Expected: schema 校验通过；`patch_id` 形如 `testsong-xxxxxxxx`；Drums pad 为 `trigger_group`；notes 非空。冒烟会把 `patch.json` 写进 demo 的 output 目录（gitignored 运行产物），但不得改动 demo 源文件。

## Out Of Scope For This Plan

- Running Demucs, MusicGen, or the full reference pipeline（Task 3 的一次性 fixture 提取除外）。
- ABC/DEF（loops profile）包的 pad mapping（v1 显式拒绝，留 profile 扩展点）。
- Note duration / 非量化 timing（`start_beats`/`duration_beats` 属 v2）。
- App Backend API routes。
- Cloud queue and worker deployment。
- LLM idea orchestration。
- Database persistence。
- Community, share, remix, sample, fork, or lineage APIs。
- 16-pad Pro View beyond preserving a future extension point。

## Self-Review

- 契约真实性：输入契约字段（`sample` key、`song_id` 位置、`beats`）逐一对照过 `sequencer.py`/`pipeline.py` 源码；happy path 由真实 demo 输出的 golden fixture 锁定。
- 可演奏闭环：`patch.json` 携带 normalized patterns + length_steps，消费方无需解析 MIDI。
- 素材无孤儿：trigger_group 覆盖同 role 多 element；melody_b fallback；unmapped 显式记录；非 standard 包 fail loud。
- 幂等与身份：patch_id 内容派生 + 确定性序列化测试，为 worker 重试奠基。
- 契约机器可读：JSON Schema 随 core-models 分发，输出强制校验，未来 TS codegen 有种子。
- Known gap：尚未接 `workers/audio/` 或 `apps/api/`；`_time_to_step` 的均匀网格近似在 beat 严重不均时可能错位一步（v1 接受，已注释）。
