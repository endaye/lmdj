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
