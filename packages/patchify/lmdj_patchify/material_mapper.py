from __future__ import annotations

from lmdj_core_models.materials import MATERIAL_SLOT_BY_INDEX, MaterialPackage
from lmdj_core_models.model import Element, Note, Pad

MATERIAL_MIDI_BASE = 36


def map_materials(
    package: MaterialPackage,
) -> tuple[list[Element], list[Pad], list[Note]]:
    by_slot = {material.slot_index: material for material in package.materials}
    elements: list[Element] = []
    pads: list[Pad] = []
    element_by_material: dict[str, Element] = {}

    for index in range(16):
        slot = MATERIAL_SLOT_BY_INDEX[index]
        material = by_slot.get(index)
        if material is None:
            pads.append(
                Pad(
                    index=index,
                    slot=slot.label,
                    label="Empty",
                    action="empty",
                    element_id=None,
                    behavior={},
                )
            )
            continue
        element = Element(
            element_id=f"el_{material.material_id}",
            name=slot.label,
            kind=material.kind,
            source_path=material.audio_path,
            pitch=MATERIAL_MIDI_BASE + index,
            lane=index,
            role=material.role,
        )
        elements.append(element)
        element_by_material[material.material_id] = element
        behavior = {
            "trigger": (
                "one_shot" if material.kind == "one_shot" else "loop"
            ),
            "quantize": material.playback.quantize,
            "element_ids": [element.element_id],
            "material_role": material.role,
            "material_variant": material.variant,
        }
        if material.playback.exclusive_group is not None:
            behavior["exclusive_group"] = (
                material.playback.exclusive_group
            )
        pads.append(
            Pad(
                index=index,
                slot=slot.label,
                label=slot.label,
                action="trigger_element",
                element_id=element.element_id,
                behavior=behavior,
            )
        )

    notes = sorted(
        (
            Note(
                element_id=element_by_material[event.material_id].element_id,
                lane=element_by_material[event.material_id].lane,
                pitch=element_by_material[event.material_id].pitch,
                step=event.step,
                velocity=event.velocity,
            )
            for event in package.pattern.events
        ),
        key=lambda note: (note.step, note.pitch, note.velocity),
    )
    return elements, pads, notes
