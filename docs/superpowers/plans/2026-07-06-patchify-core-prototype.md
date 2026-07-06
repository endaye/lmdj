# Patchify Core Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first testable Patchify core: convert an existing `lmdj-song-pipeline` package into a stable `patch.json` containing product-level patch, scene, pad, and element objects.

**Architecture:** Keep the current audio pipeline intact and add a narrow adapter layer after `lanes.json`, `chart.mid`, and `report.json` exist. The new layer validates a package, maps pipeline lanes into the default 8-pad Focus View, emits `patch.json`, and exposes it through CLI/API without changing `PipelineConfig.lane_pitches`.

**Tech Stack:** Python 3.10+, dataclasses, JSON stdlib, `pretty_midi`, existing `song_pipeline` package, pytest.

## Global Constraints

- Work inside `/Users/endaye/Projects/lmdj/lmdj-song-pipeline` for implementation and tests.
- Use `.venv/bin/python -m pytest tests/ -q` for validation.
- Do not bump `numpy`; it is pinned `<2` for demucs/numba compatibility.
- Preserve existing pipeline output files: `samples/*.wav`, `chart.mid`, `lanes.json`, `report.json`, `loop_preview.wav`, `render_preview.wav`.
- `lanes.json` remains the source of truth for pitch-to-sample mapping; do not infer lane order from filenames.
- Do not change `PipelineConfig.lane_pitches` in this plan.
- V1 default pad surface is 8-pad Focus View with fixed slots: `Drums`, `Bass`, `Harmony`, `Lead/Vocal`, `Fill`, `Drop`, `Mute`, `FX/Variation`.
- The first implementation handles uploaded-song and generated-audio pipeline packages equally; full LLM idea generation belongs in a separate plan.

---

## File Structure

- Create `lmdj-song-pipeline/song_pipeline/patch_model.py`
  - Owns serializable product objects: `Patch`, `Scene`, `Pad`, `Element`, `RenderRef`.
  - Provides `to_dict()` methods and `write_patch_json()`.
- Create `lmdj-song-pipeline/song_pipeline/package_loader.py`
  - Owns package validation and parsed package data.
  - Reads `lanes.json`, `report.json`, and `chart.mid`.
  - Confirms sample files exist and MIDI pitches exist in `lanes.json`.
- Create `lmdj-song-pipeline/song_pipeline/pad_mapper.py`
  - Owns default 8-pad Focus View mapping from pipeline lanes to product pads.
  - Has no filesystem access.
- Create `lmdj-song-pipeline/song_pipeline/patchify.py`
  - Orchestrates loader + mapper + model.
  - Produces `patch.json` for an existing pipeline package directory.
- Modify `lmdj-song-pipeline/song_pipeline/pipeline.py`
  - After successful package artifacts are written, call `patchify_package(out_dir)`.
  - Do not block existing `report.json` generation if patchify fails; write failure into `report["patchify_error"]` only if needed.
- Modify `lmdj-song-pipeline/song_pipeline/cli.py`
  - Add `song-pipeline patchify <song_dir>` for regenerating `patch.json` from an existing package.
- Modify `lmdj-song-pipeline/song_pipeline/api.py`
  - Include `patch.json` in package zip when present.
- Create `lmdj-song-pipeline/tests/test_patch_model.py`
- Create `lmdj-song-pipeline/tests/test_package_loader.py`
- Create `lmdj-song-pipeline/tests/test_pad_mapper.py`
- Create `lmdj-song-pipeline/tests/test_patchify.py`

---

### Task 1: Product Patch Model

**Files:**
- Create: `lmdj-song-pipeline/song_pipeline/patch_model.py`
- Test: `lmdj-song-pipeline/tests/test_patch_model.py`

**Interfaces:**
- Produces: `Patch`, `Scene`, `Pad`, `Element`, `RenderRef`, `write_patch_json(patch: Patch, out_path: Path) -> None`
- Consumes: no earlier tasks

- [ ] **Step 1: Write the failing test**

Create `tests/test_patch_model.py`:

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

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_patch_model.py::test_patch_model_serializes_product_objects -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'song_pipeline.patch_model'`.

- [ ] **Step 3: Write minimal implementation**

Create `song_pipeline/patch_model.py`:

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

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_patch_model.py::test_patch_model_serializes_product_objects -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
git add song_pipeline/patch_model.py tests/test_patch_model.py
git commit -m "feat(patchify): add product patch model"
```

---

### Task 2: Package Loader And Validator

**Files:**
- Create: `lmdj-song-pipeline/song_pipeline/package_loader.py`
- Test: `lmdj-song-pipeline/tests/test_package_loader.py`

**Interfaces:**
- Consumes: no earlier runtime objects
- Produces: `PipelinePackage`, `load_pipeline_package(song_dir: Path) -> PipelinePackage`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_package_loader.py`:

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

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_package_loader.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'song_pipeline.package_loader'`.

- [ ] **Step 3: Write implementation**

Create `song_pipeline/package_loader.py`:

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

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_package_loader.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
git add song_pipeline/package_loader.py tests/test_package_loader.py
git commit -m "feat(patchify): validate pipeline packages"
```

---

### Task 3: Default 8-Pad Focus Mapper

**Files:**
- Create: `lmdj-song-pipeline/song_pipeline/pad_mapper.py`
- Test: `lmdj-song-pipeline/tests/test_pad_mapper.py`

**Interfaces:**
- Consumes: `PipelinePackage.lanes`
- Produces: `build_focus_pads(lanes: list[dict[str, Any]]) -> tuple[list[Element], list[Pad]]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pad_mapper.py`:

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

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_pad_mapper.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'song_pipeline.pad_mapper'`.

- [ ] **Step 3: Write implementation**

Create `song_pipeline/pad_mapper.py`:

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

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_pad_mapper.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
git add song_pipeline/pad_mapper.py tests/test_pad_mapper.py
git commit -m "feat(patchify): map lanes to focus pads"
```

---

### Task 4: Patchify Orchestrator

**Files:**
- Create: `lmdj-song-pipeline/song_pipeline/patchify.py`
- Test: `lmdj-song-pipeline/tests/test_patchify.py`

**Interfaces:**
- Consumes: `load_pipeline_package(song_dir: Path) -> PipelinePackage`, `build_focus_pads(lanes) -> tuple[list[Element], list[Pad]]`
- Produces: `build_patch(song_dir: Path, source_type: str = "pipeline") -> Patch`, `patchify_package(song_dir: Path) -> Path`

- [ ] **Step 1: Write the failing test**

Create `tests/test_patchify.py`:

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

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_patchify.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'song_pipeline.patchify'`.

- [ ] **Step 3: Write implementation**

Create `song_pipeline/patchify.py`:

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

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_patchify.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
git add song_pipeline/patchify.py tests/test_patchify.py
git commit -m "feat(patchify): build patch json from packages"
```

---

### Task 5: Pipeline, CLI, And API Integration

**Files:**
- Modify: `lmdj-song-pipeline/song_pipeline/pipeline.py`
- Modify: `lmdj-song-pipeline/song_pipeline/cli.py`
- Modify: `lmdj-song-pipeline/song_pipeline/api.py`
- Test: `lmdj-song-pipeline/tests/test_smoke.py`
- Test: `lmdj-song-pipeline/tests/test_patchify.py`

**Interfaces:**
- Consumes: `patchify_package(song_dir: Path) -> Path`
- Produces: `patch.json` after normal pipeline runs, CLI `song-pipeline patchify <song_dir>`, and package zip containing `patch.json` when present

- [ ] **Step 1: Add failing smoke assertion for automatic `patch.json`**

Modify `tests/test_smoke.py` by adding this test after `test_lanes_midi_consistency`:

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

- [ ] **Step 2: Add failing CLI coverage**

Append this test to `tests/test_patchify.py`:

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

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_smoke.py::test_pipeline_writes_patch_json tests/test_patchify.py::test_cli_patchify_command_writes_patch_json -q
```

Expected: FAIL because `patch.json` is not written by the pipeline and `patchify` is not a recognized CLI command.

- [ ] **Step 4: Integrate patchify into pipeline**

Modify `song_pipeline/pipeline.py`:

```python
# add import near existing imports
from .patchify import patchify_package
```

In `run_pipeline`, after `report.json` is written and before `log.info(...)`, insert:

```python
    try:
        patchify_package(out_dir)
    except Exception as e:  # noqa: BLE001 patchify failure should not hide pipeline report
        report["patchify_error"] = str(e)
        (out_dir / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False))
```

In `run_pipeline_abc`, after `report.json` is written and before `log.info(...)`, insert the same block:

```python
    try:
        patchify_package(out_dir)
    except Exception as e:  # noqa: BLE001 patchify failure should not hide pipeline report
        report["patchify_error"] = str(e)
        (out_dir / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False))
```

- [ ] **Step 5: Add CLI command**

Modify `song_pipeline/cli.py` by adding the parser after `gen` is defined:

```python
    patchify = sub.add_parser("patchify", help="从已有 pipeline package 生成 patch.json")
    patchify.add_argument("song_dir", type=Path)
```

Add this branch before `elif args.cmd == "serve"`:

```python
    elif args.cmd == "patchify":
        from .patchify import patchify_package
        out_path = patchify_package(args.song_dir)
        print(out_path)
```

- [ ] **Step 6: Include `patch.json` in API zip**

Modify `song_pipeline/api.py` package endpoint zip creation:

```python
            for f in ["chart.mid", "lanes.json", "report.json", "patch.json"]:
                path = song_dir / f
                if path.exists():
                    z.write(path, f)
```

- [ ] **Step 7: Run targeted tests**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/test_smoke.py::test_pipeline_writes_patch_json tests/test_patchify.py::test_cli_patchify_command_writes_patch_json -q
```

Expected: PASS.

- [ ] **Step 8: Run full smoke suite**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/ -q
```

Expected: PASS for all tests.

- [ ] **Step 9: Commit**

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
git add song_pipeline/pipeline.py song_pipeline/cli.py song_pipeline/api.py tests/test_smoke.py tests/test_patchify.py
git commit -m "feat(patchify): emit patch json from pipeline"
```

---

### Task 6: Documentation For Patchify Contract

**Files:**
- Modify: `lmdj-song-pipeline/README.md`
- Modify: `lmdj-song-pipeline/SETUP_AND_USAGE.md`

**Interfaces:**
- Consumes: `patch.json` schema from Tasks 1-5
- Produces: documented product-level package contract for future UI and community plans

- [ ] **Step 1: Update README output format**

Modify the output block in `lmdj-song-pipeline/README.md` to:

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

Add this paragraph after the `lanes.json` paragraph:

```markdown
`patch.json` is the product-level Patchify contract for LMDJ workstation clients. It adapts pipeline artifacts into `Patch`, `Scene`, `Pad`, and `Element` objects. `lanes.json` remains the authoritative pitch-to-sample source; `patch.json` is the UI/product adapter layer.
```

- [ ] **Step 2: Document CLI patchify command**

Add this command to the common command section in `lmdj-song-pipeline/README.md`:

```bash
# Regenerate product patch.json from an existing package.
.venv/bin/song-pipeline patchify output/mysong
```

- [ ] **Step 3: Update SETUP_AND_USAGE contract section**

In `lmdj-song-pipeline/SETUP_AND_USAGE.md`, add a short `patch.json` subsection near the output contract section:

```markdown
### patch.json

`patch.json` is generated after `lanes.json`, `chart.mid`, and `report.json`.
It is the product-facing Patchify object consumed by future workstation UI:

- `pads`: default 8-pad Focus View.
- `scenes`: initial `Original` scene.
- `elements`: reusable samples, loops, chops, stems, or patterns from the package.
- `renders`: preview audio references.
- `metadata`: validation status and score context.

Do not treat `patch.json` as the pitch authority. Read `lanes.json` for pitch/sample truth and use `patch.json` for product layout.
```

- [ ] **Step 4: Run docs sanity check**

Run:

```bash
cd /Users/endaye/Projects/lmdj
rg -n "patch.json|Patchify" lmdj-song-pipeline/README.md lmdj-song-pipeline/SETUP_AND_USAGE.md
```

Expected: output includes README and SETUP_AND_USAGE references to `patch.json` and `Patchify`.

- [ ] **Step 5: Run tests to ensure docs changes did not disturb code**

Run:

```bash
cd /Users/endaye/Projects/lmdj/lmdj-song-pipeline
.venv/bin/python -m pytest tests/ -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add lmdj-song-pipeline/README.md lmdj-song-pipeline/SETUP_AND_USAGE.md
git commit -m "docs(patchify): document patch json contract"
```

---

## Self-Review Notes

Spec coverage:

- Idea/upload convergence is covered by producing one package-to-patch adapter that works after generated audio or uploaded audio has become a pipeline package.
- Patch View is covered through the 8-pad Focus View model and default pad slots.
- Scene Variation is represented by the first `Original` scene and leaves later generated scenes as a separate plan.
- AI Talk is not implemented in this plan because it needs UI and speech/input orchestration; this plan prepares the patch/history object surface it will operate on.
- Sharing/community is not implemented in this plan because it needs platform and render/export plans; this plan adds the product contract those flows consume.

Completeness scan:

- This plan intentionally contains complete Patchify Core tasks only. UI, AI Talk, sharing, and community implementation are explicitly scoped into separate plans because they sit outside Patchify Core.

Type consistency:

- `patch_model.Patch` is produced by `patchify.build_patch()`.
- `package_loader.PipelinePackage` is consumed only by `patchify.py`.
- `pad_mapper.build_focus_pads()` returns `tuple[list[Element], list[Pad]]`, which matches `Patch(elements=..., pads=...)`.
