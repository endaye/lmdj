# Patchify Core Path B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重新编写 LMDJ-owned Patchify Core，把 idea 或 audio pipeline package 转成稳定的 `patch.json`，作为后续 Web、CLI、Audio Worker 和云端 API 的共同产品 contract。

**Architecture:** `packages/patchify/` 是正式源码边界，不修改 `references/demos/lmdj-song-pipeline/`。第一版 Patchify 只消费一个已有 package directory：`samples/*.wav`、`chart.mid`、`lanes.json`、`report.json`，输出 LMDJ 自己的 `Patch / Pad / Scene / Element` JSON；后续再接入 `workers/audio/` 和 `apps/api/`。

**Tech Stack:** Python 3.11+、dataclasses、JSON stdlib、`pretty_midi`、pytest。后续 Web/API 可以另选 TypeScript 或 Python，但本计划先用 Python，因为第一批输入来自音频/MIDI pipeline，Python 音频生态更直接。

## Global Constraints

- `references/demos/lmdj-song-pipeline/` 只作参考、fixture 或迁移来源，不在其中新增正式产品功能。
- `packages/patchify/` 是 Patchify Core 的第一版正式源码落点。
- 第一版输入 package contract：`samples/*.wav`、`chart.mid`、`lanes.json`、`report.json`。
- 第一版输出文件：`patch.json`，schema 固定为 `lmdj.patch.v1`。
- 第一版默认 pad surface 是 8-pad Focus View：`Drums`、`Bass`、`Harmony`、`Lead/Vocal`、`Fill`、`Drop`、`Mute`、`FX/Variation`。
- 第一版只做 deterministic mapping，不接 LLM，不做云端鉴权，不做数据库写入。
- 不改变参考 demo 的 `PipelineConfig.lane_pitches` 或任何 pipeline 输出逻辑。
- 测试不能依赖 Demucs、MusicGen、ffmpeg 或真实长音频；fixture 在测试里临时生成。

---

## File Structure

- Create: `packages/patchify/pyproject.toml`
  - 定义独立 Python package、runtime dependency `pretty_midi`、test dependency `pytest`。
- Create: `packages/patchify/lmdj_patchify/__init__.py`
  - 暴露 `patchify_package` 和核心 model。
- Create: `packages/patchify/lmdj_patchify/model.py`
  - 定义 `Patch`、`Scene`、`Pad`、`Element`、`RenderRef`、`write_patch_json()`。
- Create: `packages/patchify/lmdj_patchify/package_loader.py`
  - 读取和验证 package directory，产出 `LoadedPackage`。
- Create: `packages/patchify/lmdj_patchify/pad_mapper.py`
  - 将 lanes / elements 映射到 8-pad Focus View。
- Create: `packages/patchify/lmdj_patchify/patchify.py`
  - 编排 loader、mapper、model，生成 `patch.json`。
- Create: `packages/patchify/lmdj_patchify/cli.py`
  - 提供 `lmdj-patchify /path/to/package` 命令。
- Create: `packages/patchify/tests/conftest.py`
  - 生成不依赖外部音频工具的最小 package fixture。
- Create: `packages/patchify/tests/test_model.py`
- Create: `packages/patchify/tests/test_package_loader.py`
- Create: `packages/patchify/tests/test_pad_mapper.py`
- Create: `packages/patchify/tests/test_patchify.py`
- Modify: `packages/README.md`
  - 把 `packages/patchify` 的本地验证命令写进去。

---

### Task 1: Patchify Package Skeleton And Model

**Files:**
- Create: `packages/patchify/pyproject.toml`
- Create: `packages/patchify/lmdj_patchify/__init__.py`
- Create: `packages/patchify/lmdj_patchify/model.py`
- Create: `packages/patchify/tests/test_model.py`

**Interfaces:**
- Consumes: no previous task.
- Produces:
  - `SCHEMA: str`
  - `Element(element_id: str, name: str, kind: str, source_path: str, pitch: int, lane: int, role: str | None = None)`
  - `Pad(index: int, slot: str, label: str, action: str, element_id: str | None, behavior: dict[str, Any])`
  - `Scene(scene_id: str, name: str, pad_indexes: list[int], intent: str)`
  - `RenderRef(kind: str, path: str)`
  - `Patch(patch_id: str, source: dict[str, Any], bpm: float, loop_seconds: float, pads: list[Pad], scenes: list[Scene], elements: list[Element], renders: list[RenderRef], metadata: dict[str, Any])`
  - `write_patch_json(patch: Patch, out_path: Path) -> None`

- [ ] **Step 1: Write the failing test**

Create `packages/patchify/tests/test_model.py`:

```python
import json
from pathlib import Path

from lmdj_patchify.model import Element, Pad, Patch, RenderRef, Scene, write_patch_json


def test_patch_model_writes_stable_patch_json(tmp_path: Path):
    patch = Patch(
        patch_id="testsong",
        source={"type": "pipeline_package", "song_id": "testsong"},
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
                role="drums",
            )
        ],
        renders=[RenderRef(kind="loop_preview", path="loop_preview.wav")],
        metadata={"status": "passed", "score": 0.8},
    )

    out_path = tmp_path / "patch.json"
    write_patch_json(patch, out_path)
    data = json.loads(out_path.read_text())

    assert data["schema"] == "lmdj.patch.v1"
    assert data["patch_id"] == "testsong"
    assert data["pads"][0]["slot"] == "Drums"
    assert data["elements"][0]["source_path"] == "samples/kick.wav"
    assert data["renders"][0]["kind"] == "loop_preview"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest tests/test_model.py::test_patch_model_writes_stable_patch_json -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lmdj_patchify'`.

- [ ] **Step 3: Add package config and model implementation**

Create `packages/patchify/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "lmdj-patchify"
version = "0.1.0"
description = "LMDJ Patchify core package"
requires-python = ">=3.11"
dependencies = [
  "pretty_midi>=0.2.10,<1",
]

[project.optional-dependencies]
test = [
  "pytest>=8,<9",
]

[project.scripts]
lmdj-patchify = "lmdj_patchify.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["lmdj_patchify*"]
```

Create `packages/patchify/lmdj_patchify/__init__.py`:

```python
from lmdj_patchify.model import Element, Pad, Patch, RenderRef, Scene

__all__ = ["Element", "Pad", "Patch", "RenderRef", "Scene"]
```

Create `packages/patchify/lmdj_patchify/model.py`:

```python
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
            "pads": [pad.to_dict() for pad in self.pads],
            "scenes": [scene.to_dict() for scene in self.scenes],
            "elements": [element.to_dict() for element in self.elements],
            "renders": [render.to_dict() for render in self.renders],
            "metadata": self.metadata,
        }


def write_patch_json(patch: Patch, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(patch.to_dict(), indent=2, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/test_model.py::test_patch_model_writes_stable_patch_json -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add packages/patchify/pyproject.toml packages/patchify/lmdj_patchify/__init__.py packages/patchify/lmdj_patchify/model.py packages/patchify/tests/test_model.py
git commit -m "feat(patchify): add core patch model"
```

---

### Task 2: Package Loader

**Files:**
- Create: `packages/patchify/lmdj_patchify/package_loader.py`
- Create: `packages/patchify/tests/conftest.py`
- Create: `packages/patchify/tests/test_package_loader.py`

**Interfaces:**
- Consumes: `Element` from Task 1.
- Produces:
  - `LoadedPackage(root: Path, song_id: str, bpm: float, loop_seconds: float, elements: list[Element], report: dict[str, Any], midi_pitches: set[int])`
  - `load_package(package_dir: Path) -> LoadedPackage`
  - Raises `ValueError` for missing files, missing samples, or MIDI pitches absent from `lanes.json`.

- [ ] **Step 1: Write fixture and failing loader tests**

Create `packages/patchify/tests/conftest.py`:

```python
import json
from pathlib import Path

import pretty_midi
import pytest


@pytest.fixture
def minimal_package(tmp_path: Path) -> Path:
    root = tmp_path / "testsong"
    samples = root / "samples"
    samples.mkdir(parents=True)
    (samples / "kick.wav").write_bytes(b"RIFF....WAVEfmt ")
    (samples / "bass.wav").write_bytes(b"RIFF....WAVEfmt ")

    lanes = {
        "song_id": "testsong",
        "bpm": 90.0,
        "loop_seconds": 10.667,
        "lanes": [
            {"lane": 0, "name": "kick", "kind": "drum", "pitch": 36, "path": "samples/kick.wav"},
            {"lane": 1, "name": "bass", "kind": "long", "pitch": 48, "path": "samples/bass.wav"},
        ],
    }
    (root / "lanes.json").write_text(json.dumps(lanes))
    (root / "report.json").write_text(json.dumps({"status": "passed", "score": 0.82}))
    (root / "loop_preview.wav").write_bytes(b"RIFF....WAVEfmt ")

    midi = pretty_midi.PrettyMIDI(initial_tempo=90)
    instrument = pretty_midi.Instrument(program=0, is_drum=True, name="lmdj")
    instrument.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=0.0, end=0.1))
    instrument.notes.append(pretty_midi.Note(velocity=100, pitch=48, start=0.5, end=1.0))
    midi.instruments.append(instrument)
    midi.write(str(root / "chart.mid"))
    return root
```

Create `packages/patchify/tests/test_package_loader.py`:

```python
import json
from pathlib import Path

import pretty_midi
import pytest

from lmdj_patchify.package_loader import load_package


def test_load_package_reads_lanes_report_samples_and_midi(minimal_package: Path):
    loaded = load_package(minimal_package)

    assert loaded.song_id == "testsong"
    assert loaded.bpm == 90.0
    assert loaded.loop_seconds == 10.667
    assert [element.name for element in loaded.elements] == ["kick", "bass"]
    assert loaded.elements[0].source_path == "samples/kick.wav"
    assert loaded.report["score"] == 0.82
    assert loaded.midi_pitches == {36, 48}


def test_load_package_rejects_missing_sample(minimal_package: Path):
    (minimal_package / "samples" / "kick.wav").unlink()

    with pytest.raises(ValueError, match="Missing sample file"):
        load_package(minimal_package)


def test_load_package_rejects_pitch_not_declared_in_lanes(minimal_package: Path):
    midi = pretty_midi.PrettyMIDI(initial_tempo=90)
    instrument = pretty_midi.Instrument(program=0, is_drum=True, name="lmdj")
    instrument.notes.append(pretty_midi.Note(velocity=100, pitch=60, start=0.0, end=0.1))
    midi.instruments.append(instrument)
    midi.write(str(minimal_package / "chart.mid"))

    with pytest.raises(ValueError, match="MIDI pitches missing from lanes.json"):
        load_package(minimal_package)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
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

from lmdj_patchify.model import Element


@dataclass(frozen=True)
class LoadedPackage:
    root: Path
    song_id: str
    bpm: float
    loop_seconds: float
    elements: list[Element]
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

    elements: list[Element] = []
    lane_pitches: set[int] = set()
    for row in lane_rows:
        lane = int(row["lane"])
        pitch = int(row["pitch"])
        source_path = str(row["path"])
        sample_path = root / source_path
        if not sample_path.exists():
            raise ValueError(f"Missing sample file: {source_path}")
        lane_pitches.add(pitch)
        elements.append(
            Element(
                element_id=f"el_{row['name']}",
                name=str(row["name"]),
                kind=str(row["kind"]),
                source_path=source_path,
                pitch=pitch,
                lane=lane,
                role=_infer_role(str(row["name"]), str(row["kind"])),
            )
        )

    midi = pretty_midi.PrettyMIDI(str(midi_path))
    midi_pitches = {
        note.pitch
        for instrument in midi.instruments
        for note in instrument.notes
    }
    missing = midi_pitches - lane_pitches
    if missing:
        raise ValueError(f"MIDI pitches missing from lanes.json: {sorted(missing)}")

    return LoadedPackage(
        root=root,
        song_id=str(lanes_data.get("song_id") or root.name),
        bpm=float(lanes_data["bpm"]),
        loop_seconds=float(lanes_data["loop_seconds"]),
        elements=elements,
        report=report,
        midi_pitches=midi_pitches,
    )


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

Run:

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/test_package_loader.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add packages/patchify/lmdj_patchify/package_loader.py packages/patchify/tests/conftest.py packages/patchify/tests/test_package_loader.py
git commit -m "feat(patchify): load pipeline package inputs"
```

---

### Task 3: 8-Pad Focus Mapper

**Files:**
- Create: `packages/patchify/lmdj_patchify/pad_mapper.py`
- Create: `packages/patchify/tests/test_pad_mapper.py`

**Interfaces:**
- Consumes: `Element` and `Pad` from Task 1.
- Produces:
  - `FOCUS_SLOTS: list[str]`
  - `map_focus_pads(elements: list[Element]) -> list[Pad]`

- [ ] **Step 1: Write failing mapper tests**

Create `packages/patchify/tests/test_pad_mapper.py`:

```python
from lmdj_patchify.model import Element
from lmdj_patchify.pad_mapper import FOCUS_SLOTS, map_focus_pads


def test_map_focus_pads_uses_stable_eight_slot_layout():
    elements = [
        Element("el_kick", "kick", "drum", "samples/kick.wav", 36, 0, "drums"),
        Element("el_bass", "bass", "long", "samples/bass.wav", 48, 1, "bass"),
        Element("el_melody", "melody", "long", "samples/melody.wav", 60, 2, "harmony"),
    ]

    pads = map_focus_pads(elements)

    assert [pad.slot for pad in pads] == FOCUS_SLOTS
    assert pads[0].element_id == "el_kick"
    assert pads[1].element_id == "el_bass"
    assert pads[2].element_id == "el_melody"
    assert pads[4].action == "scene_fill"
    assert pads[6].action == "mute_group"
    assert pads[7].action == "ai_variation"


def test_map_focus_pads_keeps_empty_slots_playable_as_controls():
    pads = map_focus_pads([])

    assert len(pads) == 8
    assert pads[0].slot == "Drums"
    assert pads[0].action == "empty"
    assert pads[4].action == "scene_fill"
    assert pads[5].action == "scene_drop"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/test_pad_mapper.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lmdj_patchify.pad_mapper'`.

- [ ] **Step 3: Implement mapper**

Create `packages/patchify/lmdj_patchify/pad_mapper.py`:

```python
from __future__ import annotations

from lmdj_patchify.model import Element, Pad

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


def map_focus_pads(elements: list[Element]) -> list[Pad]:
    by_role = {
        "drums": _first_by_role(elements, "drums"),
        "bass": _first_by_role(elements, "bass"),
        "harmony": _first_by_role(elements, "harmony"),
        "lead": _first_by_role(elements, "lead"),
    }
    pads = [
        _element_pad(0, "Drums", by_role["drums"]),
        _element_pad(1, "Bass", by_role["bass"]),
        _element_pad(2, "Harmony", by_role["harmony"]),
        _element_pad(3, "Lead/Vocal", by_role["lead"]),
        Pad(4, "Fill", "Fill", "scene_fill", None, {"quantize": "1 bar"}),
        Pad(5, "Drop", "Drop", "scene_drop", None, {"quantize": "1 bar"}),
        Pad(6, "Mute", "Mute", "mute_group", None, {"target": "selected_or_master"}),
        Pad(7, "FX/Variation", "FX", "ai_variation", None, {"scope": "scene"}),
    ]
    return pads


def _first_by_role(elements: list[Element], role: str) -> Element | None:
    for element in elements:
        if element.role == role:
            return element
    return None


def _element_pad(index: int, slot: str, element: Element | None) -> Pad:
    if element is None:
        return Pad(index, slot, slot, "empty", None, {})

    trigger = "one_shot" if element.kind == "drum" else "loop"
    return Pad(
        index=index,
        slot=slot,
        label=element.name,
        action="trigger_element",
        element_id=element.element_id,
        behavior={"trigger": trigger, "quantize": "1/16"},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/test_pad_mapper.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add packages/patchify/lmdj_patchify/pad_mapper.py packages/patchify/tests/test_pad_mapper.py
git commit -m "feat(patchify): map elements to focus pads"
```

---

### Task 4: Patchify Orchestrator And CLI

**Files:**
- Modify: `packages/patchify/lmdj_patchify/__init__.py`
- Create: `packages/patchify/lmdj_patchify/patchify.py`
- Create: `packages/patchify/lmdj_patchify/cli.py`
- Create: `packages/patchify/tests/test_patchify.py`
- Modify: `packages/README.md`

**Interfaces:**
- Consumes: `load_package(package_dir: Path) -> LoadedPackage` from Task 2 and `map_focus_pads(elements: list[Element]) -> list[Pad]` from Task 3.
- Produces:
  - `patchify_package(package_dir: Path, out_path: Path | None = None) -> Patch`
  - CLI: `lmdj-patchify PACKAGE_DIR [--out OUT_PATH]`

- [ ] **Step 1: Write failing orchestrator and CLI tests**

Create `packages/patchify/tests/test_patchify.py`:

```python
import json
import subprocess
from pathlib import Path

from lmdj_patchify.patchify import patchify_package


def test_patchify_package_writes_patch_json(minimal_package: Path):
    patch = patchify_package(minimal_package)
    patch_path = minimal_package / "patch.json"
    data = json.loads(patch_path.read_text())

    assert patch.patch_id == "testsong"
    assert data["schema"] == "lmdj.patch.v1"
    assert data["pads"][0]["slot"] == "Drums"
    assert data["scenes"][0]["name"] == "Original"
    assert data["metadata"]["source_package"] == str(minimal_package.resolve())


def test_cli_writes_custom_output_path(minimal_package: Path):
    out_path = minimal_package / "custom-patch.json"

    result = subprocess.run(
        ["lmdj-patchify", str(minimal_package), "--out", str(out_path)],
        check=True,
        text=True,
        capture_output=True,
    )

    data = json.loads(out_path.read_text())
    assert data["patch_id"] == "testsong"
    assert str(out_path) in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/test_patchify.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lmdj_patchify.patchify'`.

- [ ] **Step 3: Implement orchestrator and CLI**

Update `packages/patchify/lmdj_patchify/__init__.py`:

```python
from lmdj_patchify.model import Element, Pad, Patch, RenderRef, Scene
from lmdj_patchify.patchify import patchify_package

__all__ = ["Element", "Pad", "Patch", "RenderRef", "Scene", "patchify_package"]
```

Create `packages/patchify/lmdj_patchify/patchify.py`:

```python
from __future__ import annotations

from pathlib import Path

from lmdj_patchify.model import Patch, RenderRef, Scene, write_patch_json
from lmdj_patchify.package_loader import load_package
from lmdj_patchify.pad_mapper import map_focus_pads


def patchify_package(package_dir: Path, out_path: Path | None = None) -> Patch:
    loaded = load_package(package_dir)
    pads = map_focus_pads(loaded.elements)
    patch = Patch(
        patch_id=loaded.song_id,
        source={"type": "pipeline_package", "song_id": loaded.song_id},
        bpm=loaded.bpm,
        loop_seconds=loaded.loop_seconds,
        pads=pads,
        scenes=[
            Scene(
                scene_id="scene_original",
                name="Original",
                pad_indexes=[pad.index for pad in pads],
                intent="Pipeline default scene",
            )
        ],
        elements=loaded.elements,
        renders=_discover_renders(loaded.root),
        metadata={
            "source_package": str(loaded.root),
            "status": loaded.report.get("status"),
            "score": loaded.report.get("score"),
            "midi_pitches": sorted(loaded.midi_pitches),
        },
    )
    write_patch_json(patch, out_path or loaded.root / "patch.json")
    return patch


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
    parser = argparse.ArgumentParser(description="Create an LMDJ patch.json from a pipeline package.")
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    patchify_package(args.package_dir, args.out)
    out_path = args.out or args.package_dir / "patch.json"
    print(f"Wrote {out_path}")
```

- [ ] **Step 4: Document package verification command**

Update `packages/README.md` by appending:

````markdown
## Patchify local validation

```bash
cd packages/patchify
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest tests/ -q
```

Run the CLI against a package directory:

```bash
.venv/bin/lmdj-patchify /path/to/package
```
````

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add packages/patchify/lmdj_patchify/__init__.py packages/patchify/lmdj_patchify/patchify.py packages/patchify/lmdj_patchify/cli.py packages/patchify/tests/test_patchify.py packages/README.md
git commit -m "feat(patchify): generate patch json from package"
```

---

## Verification

Full plan verification after Task 4:

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/python -m pytest tests/ -q
```

Expected:

```text
8 passed
```

Optional manual smoke test using a package produced by the reference demo:

```bash
cd /Users/endaye/Projects/lmdj/packages/patchify
.venv/bin/lmdj-patchify /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline/output/testsong
```

Expected:

```text
Wrote /Users/endaye/Projects/lmdj/references/demos/lmdj-song-pipeline/output/testsong/patch.json
```

This optional smoke test may write `patch.json` into a demo output directory, but it must not modify demo source files.

## Out Of Scope For This Plan

- Running Demucs, MusicGen, or the full reference pipeline.
- App Backend API routes.
- Cloud queue and worker deployment.
- LLM idea orchestration.
- Database persistence.
- Community, share, remix, sample, fork, or lineage APIs.
- 16-pad Pro View beyond preserving a future extension point.

## Self-Review

- Spec coverage: covers the current V1 technical need of converting generated/extracted materials into `Patch / Pad / Scene / Element` and `patch.json`.
- Boundary coverage: keeps `references/demos/lmdj-song-pipeline/` read-only for formal product code and moves new work to `packages/patchify/`.
- Test coverage: model serialization, package validation, pad mapping, orchestrator, and CLI are all covered without heavyweight audio dependencies.
- Known gap: this does not yet connect to `workers/audio/` or `apps/api/`; those should be separate plans after Patchify Core passes locally.
