from __future__ import annotations

import importlib.resources
import json
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

MATERIAL_SCHEMA = "lmdj.materials.v1"
MATERIAL_PAD_COUNT = 16
EMPTY_REASON_CODES = frozenset(
    {
        "source_silent",
        "no_candidate",
        "classification_low_confidence",
        "quality_below_threshold",
        "variant_not_distinct",
        "no_valid_loop_boundary",
        "source_stem_unavailable",
    }
)


@dataclass(frozen=True)
class MaterialSlot:
    index: int
    label: str
    role: str
    source_stem: str
    kind: str
    variant: str


_BASE_SLOTS = (
    ("Kick", "kick", "drums", "one_shot"),
    ("Snare", "snare", "drums", "one_shot"),
    ("Hat", "hat", "drums", "one_shot"),
    ("Percussion", "percussion", "drums", "one_shot"),
    ("Bass", "bass", "bass", "loop"),
    ("Melody", "melody", "other", "loop"),
    ("Vocal", "vocal", "vocals", "loop"),
    ("Phrase", "full_mix_phrase", "original", "full_mix_phrase"),
)
MATERIAL_SLOTS = tuple(
    MaterialSlot(
        index=index + variant_offset,
        label=f"{label} {variant}",
        role=role,
        source_stem=source,
        kind=kind,
        variant=variant,
    )
    for variant_offset, variant in ((0, "A"), (8, "B"))
    for index, (label, role, source, kind) in enumerate(_BASE_SLOTS)
)
MATERIAL_SLOT_BY_INDEX = {slot.index: slot for slot in MATERIAL_SLOTS}


@dataclass(frozen=True)
class MaterialSource:
    audio_sha256: str


@dataclass(frozen=True)
class MaterialProvenance:
    separator_id: str
    separator_checkpoint_sha256: str
    separator_runner_version: str
    timing_version: str
    extractor_runner_version: str
    extraction_config_version: str
    environment_lock_sha256: str
    pipeline: str = "materials-v1"


@dataclass(frozen=True)
class MaterialTiming:
    bpm: float
    beats_per_bar: int
    grid_per_beat: int
    length_steps: int
    artifact: str


@dataclass(frozen=True)
class MaterialPlayback:
    quantize: str = "1/16"
    exclusive_group: str | None = None


@dataclass(frozen=True)
class MaterialQuality:
    status: str
    score: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Material:
    material_id: str
    slot_index: int
    role: str
    variant: str
    variant_of: str | None
    kind: str
    source_stem: str
    audio_path: str
    playback: MaterialPlayback
    quality: MaterialQuality

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_id": self.material_id,
            "slot_index": self.slot_index,
            "role": self.role,
            "variant": self.variant,
            "variant_of": self.variant_of,
            "kind": self.kind,
            "source_stem": self.source_stem,
            "audio_path": self.audio_path,
            "playback": asdict(self.playback),
            "quality": {
                "status": self.quality.status,
                "score": self.quality.score,
                "warnings": list(self.quality.warnings),
            },
        }


@dataclass(frozen=True)
class MaterialEvent:
    material_id: str
    step: int
    velocity: int


@dataclass(frozen=True)
class MaterialPattern:
    pattern_id: str
    length_steps: int
    events: tuple[MaterialEvent, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "length_steps": self.length_steps,
            "events": [asdict(event) for event in self.events],
        }


@dataclass(frozen=True)
class SlotDecision:
    slot_index: int
    status: str
    material_id: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "slot_index": self.slot_index,
            "status": self.status,
        }
        if self.material_id is not None:
            result["material_id"] = self.material_id
        if self.reason is not None:
            result["reason"] = self.reason
        return result


@dataclass(frozen=True)
class MaterialPackage:
    source: MaterialSource
    provenance: MaterialProvenance
    timing: MaterialTiming
    materials: tuple[Material, ...]
    pattern: MaterialPattern
    slot_decisions: tuple[SlotDecision, ...]
    schema: str = MATERIAL_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source": asdict(self.source),
            "provenance": asdict(self.provenance),
            "timing": asdict(self.timing),
            "materials": [material.to_dict() for material in self.materials],
            "pattern": self.pattern.to_dict(),
            "slot_decisions": [
                decision.to_dict() for decision in self.slot_decisions
            ],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.to_dict())

    def canonical_identity_bytes(self) -> bytes:
        return _canonical_json(
            {
                "timing": asdict(self.timing),
                "materials": [material.to_dict() for material in self.materials],
                "pattern": self.pattern.to_dict(),
                "extraction_config_version": (
                    self.provenance.extraction_config_version
                ),
            }
        )


def material_package_from_dict(data: dict[str, Any]) -> MaterialPackage:
    source = MaterialSource(**data["source"])
    provenance = MaterialProvenance(**data["provenance"])
    timing = MaterialTiming(**data["timing"])
    materials = tuple(
        Material(
            material_id=row["material_id"],
            slot_index=row["slot_index"],
            role=row["role"],
            variant=row["variant"],
            variant_of=row.get("variant_of"),
            kind=row["kind"],
            source_stem=row["source_stem"],
            audio_path=row["audio_path"],
            playback=MaterialPlayback(**row["playback"]),
            quality=MaterialQuality(
                status=row["quality"]["status"],
                score=row["quality"]["score"],
                warnings=tuple(row["quality"].get("warnings", [])),
            ),
        )
        for row in data["materials"]
    )
    pattern_data = data["pattern"]
    package = MaterialPackage(
        schema=data["schema"],
        source=source,
        provenance=provenance,
        timing=timing,
        materials=materials,
        pattern=MaterialPattern(
            pattern_id=pattern_data["pattern_id"],
            length_steps=pattern_data["length_steps"],
            events=tuple(MaterialEvent(**row) for row in pattern_data["events"]),
        ),
        slot_decisions=tuple(
            SlotDecision(
                slot_index=row["slot_index"],
                status=row["status"],
                material_id=row.get("material_id"),
                reason=row.get("reason"),
            )
            for row in data["slot_decisions"]
        ),
    )
    validate_material_package(package)
    return package


def validate_material_package(package: MaterialPackage) -> None:
    if package.schema != MATERIAL_SCHEMA:
        raise ValueError(f"schema must be {MATERIAL_SCHEMA}")
    if not _is_sha256(package.source.audio_sha256):
        raise ValueError("source.audio_sha256 must be a full lowercase SHA-256")
    if not _is_sha256(package.provenance.separator_checkpoint_sha256):
        raise ValueError(
            "provenance.separator_checkpoint_sha256 must be a full SHA-256"
        )
    if not _is_sha256(package.provenance.environment_lock_sha256):
        raise ValueError(
            "provenance.environment_lock_sha256 must be a full SHA-256"
        )
    if package.provenance.pipeline != "materials-v1":
        raise ValueError("provenance.pipeline must be materials-v1")
    _validate_relative_path(package.timing.artifact, "timing.artifact")
    if not 1 <= len(package.materials) <= MATERIAL_PAD_COUNT:
        raise ValueError("materials must contain 1..16 accepted entries")
    if package.pattern.length_steps != package.timing.length_steps:
        raise ValueError("pattern length_steps must match timing")
    if package.timing.bpm <= 0:
        raise ValueError("timing bpm must be positive")
    if package.timing.beats_per_bar < 1 or package.timing.grid_per_beat < 1:
        raise ValueError("timing grid values must be positive")

    by_id: dict[str, Material] = {}
    by_slot: dict[int, Material] = {}
    for material in package.materials:
        if material.material_id in by_id:
            raise ValueError(f"duplicate material_id: {material.material_id}")
        if material.slot_index in by_slot:
            raise ValueError(f"duplicate material slot: {material.slot_index}")
        slot = MATERIAL_SLOT_BY_INDEX.get(material.slot_index)
        if slot is None:
            raise ValueError(f"material slot out of range: {material.slot_index}")
        expected = (slot.role, slot.source_stem, slot.kind, slot.variant)
        actual = (
            material.role,
            material.source_stem,
            material.kind,
            material.variant,
        )
        if actual != expected:
            raise ValueError(
                f"material {material.material_id} does not match slot "
                f"{material.slot_index}"
            )
        _validate_relative_path(material.audio_path, "material.audio_path")
        if material.quality.status != "accepted":
            raise ValueError("materials may contain accepted entries only")
        if not 0 <= material.quality.score <= 1:
            raise ValueError("material quality score must be in 0..1")
        expected_group = (
            "full_mix_exclusive"
            if material.kind == "full_mix_phrase"
            else None
        )
        if material.playback.exclusive_group != expected_group:
            raise ValueError(
                f"material {material.material_id} has invalid exclusive group"
            )
        if material.variant == "A" and material.variant_of is not None:
            raise ValueError("A material must not have variant_of")
        by_id[material.material_id] = material
        by_slot[material.slot_index] = material

    for material in package.materials:
        if material.variant != "B":
            continue
        parent = by_id.get(material.variant_of or "")
        expected_a = by_slot.get(material.slot_index - 8)
        if parent is None or parent is not expected_a or parent.role != material.role:
            raise ValueError(
                f"B material {material.material_id} must reference same-role A"
            )

    decisions = sorted(package.slot_decisions, key=lambda item: item.slot_index)
    if [decision.slot_index for decision in decisions] != list(
        range(MATERIAL_PAD_COUNT)
    ):
        raise ValueError("slot_decisions must cover indexes 0..15 exactly once")
    for decision in decisions:
        material = by_slot.get(decision.slot_index)
        if decision.status == "accepted":
            if material is None or decision.material_id != material.material_id:
                raise ValueError("accepted decision must reference slot material")
            if decision.reason is not None:
                raise ValueError("accepted decision must not have an empty reason")
        elif decision.status == "empty":
            if material is not None or decision.material_id is not None:
                raise ValueError("empty decision cannot have a material")
            if decision.reason not in EMPTY_REASON_CODES:
                raise ValueError("empty decision has unknown reason code")
        else:
            raise ValueError(f"unknown slot decision status: {decision.status}")

    for event in package.pattern.events:
        if event.material_id not in by_id:
            raise ValueError(
                f"pattern event references unknown material: {event.material_id}"
            )
        if not 0 <= event.step < package.pattern.length_steps:
            raise ValueError(f"pattern event step out of range: {event.step}")
        if not 1 <= event.velocity <= 127:
            raise ValueError("pattern velocity must be in 1..127")


def load_material_schema() -> dict[str, Any]:
    ref = importlib.resources.files("lmdj_core_models").joinpath(
        "schemas/lmdj.materials.v1.schema.json"
    )
    return json.loads(ref.read_text())


def _validate_relative_path(value: str, field: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or value != path.as_posix()
        or ".." in path.parts
        or "." in path.parts
    ):
        raise ValueError(f"{field} must be a safe package-relative path")


def _canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
