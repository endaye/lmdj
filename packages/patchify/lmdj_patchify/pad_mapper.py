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
