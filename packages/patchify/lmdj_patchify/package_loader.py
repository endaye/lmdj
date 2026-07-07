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

    for required_field in ("bpm", "beats", "loop_seconds"):
        if required_field not in lanes_data:
            raise ValueError(f"lanes.json missing required field: {required_field}")

    beats = int(lanes_data["beats"])
    loop_seconds = float(lanes_data["loop_seconds"])
    if beats < 1:
        raise ValueError("lanes.json beats must be >= 1")
    if loop_seconds <= 0:
        raise ValueError("lanes.json loop_seconds must be > 0")
    length_steps = beats * 4

    elements: list[Element] = []
    by_pitch: dict[int, Element] = {}
    for row in lane_rows:
        for required_field in ("lane", "name", "kind", "pitch"):
            if required_field not in row:
                raise ValueError(f"lane entry missing required field: {required_field}")
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
