import hashlib
import shutil
from pathlib import Path

import pretty_midi

from lmdj_patchify.patchify import patchify_package

FIXTURE = Path(__file__).parent / "fixtures" / "material-package"


def test_material_patchify_maps_fixed_slots_and_phrase_behavior(tmp_path):
    package = tmp_path / "material-package"
    shutil.copytree(FIXTURE, package)
    out = tmp_path / "patch.json"
    patch = patchify_package(package, out)

    assert [pad.index for pad in patch.pads] == list(range(16))
    assert [pad.slot for pad in patch.pads[:8]] == [
        "Kick A", "Snare A", "Hat A", "Percussion A",
        "Bass A", "Melody A", "Vocal A", "Phrase A",
    ]
    assert patch.pads[1].action == "empty"
    assert patch.pads[7].behavior["exclusive_group"] == "full_mix_exclusive"
    assert patch.pads[8].element_id == "el_mat_kick_b"
    assert {note.step for note in patch.patterns[0].notes} == {0, 8}
    assert patch.metadata["material_count"] == 4


def test_material_patchify_generates_deterministic_midi_and_identity(tmp_path):
    package = tmp_path / "material-package"
    shutil.copytree(FIXTURE, package)
    first = patchify_package(package, tmp_path / "first.json")
    first_midi = (package / "chart.mid").read_bytes()
    second = patchify_package(package, tmp_path / "second.json")
    second_midi = (package / "chart.mid").read_bytes()

    assert first.patch_id == second.patch_id
    assert first_midi == second_midi
    assert hashlib.sha256(first_midi).digest() == hashlib.sha256(second_midi).digest()
    midi = pretty_midi.PrettyMIDI(str(package / "chart.mid"))
    assert len([note for track in midi.instruments for note in track.notes]) == 3
