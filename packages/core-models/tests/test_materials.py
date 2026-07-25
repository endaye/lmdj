from dataclasses import replace

import pytest

from lmdj_core_models.materials import (
    MATERIAL_SLOTS,
    Material,
    MaterialEvent,
    MaterialPackage,
    MaterialPattern,
    MaterialPlayback,
    MaterialProvenance,
    MaterialQuality,
    MaterialSource,
    MaterialTiming,
    SlotDecision,
    material_package_from_dict,
    validate_material_package,
)


def sample_material_package() -> MaterialPackage:
    kick = Material(
        material_id="mat_kick_a",
        slot_index=0,
        role="kick",
        variant="A",
        variant_of=None,
        kind="one_shot",
        source_stem="drums",
        audio_path="samples/kick-a.wav",
        playback=MaterialPlayback(),
        quality=MaterialQuality(status="accepted", score=0.91),
    )
    phrase = Material(
        material_id="mat_phrase_a",
        slot_index=7,
        role="full_mix_phrase",
        variant="A",
        variant_of=None,
        kind="full_mix_phrase",
        source_stem="original",
        audio_path="samples/phrase-a.wav",
        playback=MaterialPlayback(exclusive_group="full_mix_exclusive"),
        quality=MaterialQuality(status="accepted", score=0.88),
    )
    decisions = tuple(
        SlotDecision(
            slot_index=index,
            status="accepted" if index in {0, 7} else "empty",
            material_id=(
                "mat_kick_a"
                if index == 0
                else "mat_phrase_a" if index == 7 else None
            ),
            reason=None if index in {0, 7} else "no_candidate",
        )
        for index in range(16)
    )
    return MaterialPackage(
        source=MaterialSource(audio_sha256="a" * 64),
        provenance=MaterialProvenance(
            separator_id="fixture",
            separator_checkpoint_sha256="b" * 64,
            separator_runner_version="1",
            timing_version="timing-v1",
            extractor_runner_version="extractor-v1",
            extraction_config_version="materials-v1.0.0",
            environment_lock_sha256="c" * 64,
        ),
        timing=MaterialTiming(
            bpm=120,
            beats_per_bar=4,
            grid_per_beat=4,
            length_steps=64,
            artifact="timing.json",
        ),
        materials=(kick, phrase),
        pattern=MaterialPattern(
            pattern_id="pattern_primary",
            length_steps=64,
            events=(MaterialEvent("mat_kick_a", 0, 108),),
        ),
        slot_decisions=decisions,
    )


def test_fixed_material_slots_are_stable():
    assert [slot.index for slot in MATERIAL_SLOTS] == list(range(16))
    assert [slot.label for slot in MATERIAL_SLOTS[:8]] == [
        "Kick A", "Snare A", "Hat A", "Percussion A",
        "Bass A", "Melody A", "Vocal A", "Phrase A",
    ]
    assert MATERIAL_SLOTS[15].label == "Phrase B"


def test_material_package_round_trips_and_is_canonical():
    package = sample_material_package()
    validate_material_package(package)
    restored = material_package_from_dict(package.to_dict())
    assert restored == package
    assert restored.canonical_bytes() == package.canonical_bytes()
    assert restored.canonical_identity_bytes() == package.canonical_identity_bytes()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("timing", MaterialTiming(120, 4, 4, 64, "../timing.json"), "safe"),
        ("pattern", MaterialPattern("p", 64, (MaterialEvent("missing", 0, 1),)), "unknown"),
        ("pattern", MaterialPattern("p", 64, (MaterialEvent("mat_kick_a", 64, 1),)), "range"),
    ],
)
def test_material_package_rejects_invalid_references(field, value, message):
    package = replace(sample_material_package(), **{field: value})
    with pytest.raises(ValueError, match=message):
        validate_material_package(package)


def test_b_requires_same_role_a():
    package = sample_material_package()
    kick_b = replace(
        package.materials[0],
        material_id="mat_kick_b",
        slot_index=8,
        variant="B",
        variant_of="missing",
        audio_path="samples/kick-b.wav",
    )
    decisions = list(package.slot_decisions)
    decisions[8] = SlotDecision(8, "accepted", material_id="mat_kick_b")
    package = replace(
        package,
        materials=package.materials + (kick_b,),
        slot_decisions=tuple(decisions),
    )
    with pytest.raises(ValueError, match="same-role A"):
        validate_material_package(package)


def test_decisions_must_cover_every_slot_and_match_materials():
    package = sample_material_package()
    with pytest.raises(ValueError, match="cover indexes"):
        validate_material_package(
            replace(package, slot_decisions=package.slot_decisions[:-1])
        )
    decisions = list(package.slot_decisions)
    decisions[0] = SlotDecision(0, "empty", reason="no_candidate")
    with pytest.raises(ValueError, match="empty decision"):
        validate_material_package(
            replace(package, slot_decisions=tuple(decisions))
        )


def test_phrase_source_and_exclusive_group_are_enforced():
    package = sample_material_package()
    invalid = replace(package.materials[1], source_stem="other")
    with pytest.raises(ValueError, match="does not match slot"):
        validate_material_package(
            replace(package, materials=(package.materials[0], invalid))
        )


def test_provenance_hashes_and_pipeline_are_strict():
    package = sample_material_package()
    with pytest.raises(ValueError, match="environment_lock"):
        validate_material_package(
            replace(
                package,
                provenance=replace(
                    package.provenance,
                    environment_lock_sha256="not-a-hash",
                ),
            )
        )
    with pytest.raises(ValueError, match="pipeline"):
        validate_material_package(
            replace(
                package,
                provenance=replace(package.provenance, pipeline="legacy"),
            )
        )
    invalid = replace(
        package.materials[1],
        playback=MaterialPlayback(exclusive_group=None),
    )
    with pytest.raises(ValueError, match="exclusive group"):
        validate_material_package(
            replace(package, materials=(package.materials[0], invalid))
        )
