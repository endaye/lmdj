from dataclasses import replace

import pytest
import soundfile as sf

from lmdj_audio_worker.materials.config import MaterialExtractionConfig
from lmdj_audio_worker.materials.extractor import (
    MaterialExtractor,
    _classify_drum,
)
from lmdj_audio_worker.materials.timing import TimingAnalyzer

from .helpers import SR, provenance, write_fixture_audio


def test_drum_feature_classifier_covers_all_fixed_roles():
    assert _classify_drum((0.9, 0.05, 0.05, 0.1, 0.9))[0] == "kick"
    assert _classify_drum((0.05, 0.9, 0.05, 0.4, 0.9))[0] == "snare"
    assert _classify_drum((0.01, 0.09, 0.9, 0.9, 0.8))[0] == "hat"
    assert _classify_drum((0.1, 0.4, 0.1, 0.4, 1.0))[0] == "percussion"


def test_extractor_produces_fixed_decisions_aligned_loops_and_phrase(tmp_path):
    source, stems = write_fixture_audio(tmp_path)
    output = tmp_path / "package"
    timing = TimingAnalyzer().analyze(source, output / "timing.json")
    package = MaterialExtractor().extract(
        original_audio=source,
        stems_dir=stems,
        timing=timing,
        output_dir=output,
        provenance=provenance(),
    )

    assert 1 <= len(package.materials) <= 16
    assert [row.slot_index for row in package.slot_decisions] == list(range(16))
    assert any(material.role == "full_mix_phrase" for material in package.materials)
    assert all((output / material.audio_path).is_file() for material in package.materials)
    for material in package.materials:
        info = sf.info(output / material.audio_path)
        assert info.samplerate == SR
        assert info.channels == 2
        assert info.subtype == "PCM_24"
        if material.kind == "one_shot":
            assert 0.08 <= info.duration <= 0.60
    assert all(
        material.source_stem == "vocals"
        for material in package.materials
        if material.role == "vocal"
    )
    assert all(
        material.playback.exclusive_group == "full_mix_exclusive"
        for material in package.materials
        if material.role == "full_mix_phrase"
    )


def test_silent_vocal_stays_empty_and_never_moves_to_melody(tmp_path):
    source, stems = write_fixture_audio(tmp_path)
    data, sample_rate = sf.read(stems / "vocals.wav", always_2d=True)
    sf.write(stems / "vocals.wav", data * 0, sample_rate, subtype="FLOAT")
    output = tmp_path / "package"
    timing = TimingAnalyzer().analyze(source, output / "timing.json")
    package = MaterialExtractor().extract(
        original_audio=source,
        stems_dir=stems,
        timing=timing,
        output_dir=output,
        provenance=provenance(),
    )
    assert package.slot_decisions[6].status == "empty"
    assert package.slot_decisions[6].reason == "source_silent"
    assert not any(material.role == "vocal" for material in package.materials)
    assert all(
        material.source_stem == "other"
        for material in package.materials
        if material.role == "melody"
    )


def test_zero_accepted_materials_fails(tmp_path):
    source, stems = write_fixture_audio(tmp_path)
    data, sample_rate = sf.read(source, always_2d=True)
    sf.write(source, data * 0, sample_rate, subtype="FLOAT")
    for path in stems.glob("*.wav"):
        stem, stem_rate = sf.read(path, always_2d=True)
        sf.write(path, stem * 0, stem_rate, subtype="FLOAT")
    output = tmp_path / "package"
    timing = TimingAnalyzer().analyze(source, output / "timing.json")
    with pytest.raises(ValueError, match="zero accepted"):
        MaterialExtractor().extract(
            original_audio=source,
            stems_dir=stems,
            timing=timing,
            output_dir=output,
            provenance=provenance(),
        )


def test_fewer_than_six_materials_is_a_valid_package(tmp_path):
    source, stems = write_fixture_audio(tmp_path)
    for path in stems.glob("*.wav"):
        stem, stem_rate = sf.read(path, always_2d=True)
        sf.write(path, stem * 0, stem_rate, subtype="FLOAT")
    output = tmp_path / "package"
    timing = TimingAnalyzer().analyze(source, output / "timing.json")

    package = MaterialExtractor().extract(
        original_audio=source,
        stems_dir=stems,
        timing=timing,
        output_dir=output,
        provenance=provenance(),
    )

    assert 1 <= len(package.materials) < 6
    assert all(material.role == "full_mix_phrase" for material in package.materials)


def test_more_than_eight_materials_is_supported_when_b_variants_pass(tmp_path):
    source, stems = write_fixture_audio(tmp_path)
    output = tmp_path / "package"
    config = MaterialExtractionConfig(variant_difference_threshold=0.0)
    timing = TimingAnalyzer(config).analyze(source, output / "timing.json")

    package = MaterialExtractor(config).extract(
        original_audio=source,
        stems_dir=stems,
        timing=timing,
        output_dir=output,
        provenance=replace(
            provenance(),
            extraction_config_version=config.version,
        ),
    )

    assert 8 < len(package.materials) <= 16
