import hashlib
import shutil

from lmdj_audio_worker.materials.extractor import MaterialExtractor
from lmdj_audio_worker.materials.timing import TimingAnalyzer

from .helpers import provenance, write_fixture_audio


def _hashes(root, package):
    return {
        material.audio_path: hashlib.sha256(
            (root / material.audio_path).read_bytes()
        ).hexdigest()
        for material in package.materials
    }


def test_material_extraction_is_repeatable_three_times(tmp_path):
    source, stems = write_fixture_audio(tmp_path)
    results = []
    extractor = MaterialExtractor()
    for index in range(3):
        output = tmp_path / f"run-{index}"
        timing = TimingAnalyzer().analyze(source, output / "timing.json")
        package = extractor.extract(
            original_audio=source,
            stems_dir=stems,
            timing=timing,
            output_dir=output,
            provenance=provenance(),
        )
        results.append(
            (
                package.canonical_bytes(),
                _hashes(output, package),
                package.pattern.events,
                package.slot_decisions,
            )
        )
    assert results[0] == results[1] == results[2]
