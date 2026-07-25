import pytest

from lmdj_audio_worker.materials.config import MaterialExtractionConfig


def test_material_thresholds_are_versioned_and_centralized():
    config = MaterialExtractionConfig()
    assert config.version == "materials-v1.0.0"
    assert config.quality_threshold == 0.70
    assert config.variant_difference_threshold == 0.25
    assert (config.one_shot_min_seconds, config.one_shot_max_seconds) == (
        0.08,
        0.60,
    )
    assert config.loop_bars == (1, 2)


def test_invalid_threshold_is_rejected():
    with pytest.raises(ValueError, match="quality_threshold"):
        MaterialExtractionConfig(quality_threshold=1.1)
