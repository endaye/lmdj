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
