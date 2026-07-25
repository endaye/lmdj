from __future__ import annotations

import os
from pathlib import Path

import pretty_midi

from lmdj_core_models.model import Note


def write_material_midi(
    path: Path,
    *,
    bpm: float,
    notes: list[Note],
) -> None:
    midi = pretty_midi.PrettyMIDI(initial_tempo=bpm, resolution=480)
    instrument = pretty_midi.Instrument(
        program=0,
        is_drum=True,
        name="LMDJ Materials",
    )
    step_seconds = 60.0 / bpm / 4.0
    duration = min(step_seconds * 0.8, 0.1)
    for note in notes:
        start = note.step * step_seconds
        instrument.notes.append(
            pretty_midi.Note(
                velocity=note.velocity,
                pitch=note.pitch,
                start=start,
                end=start + duration,
            )
        )
    midi.instruments.append(instrument)
    temporary = path.with_suffix(".mid.tmp")
    midi.write(str(temporary))
    os.replace(temporary, path)
