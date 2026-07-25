from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaterialExtractionConfig:
    version: str = "materials-v1.0.0"
    runner_version: str = "extractor-v1"
    timing_version: str = "timing-v1"
    sample_rate: int = 44_100
    quality_threshold: float = 0.70
    variant_difference_threshold: float = 0.25
    silence_rms: float = 0.0005
    clipping_ratio_limit: float = 0.02
    leakage_ratio_limit: float = 0.98
    one_shot_min_seconds: float = 0.08
    one_shot_max_seconds: float = 0.60
    one_shot_fade_seconds: float = 0.005
    loop_bars: tuple[int, ...] = (1, 2)
    loop_crossfade_seconds: float = 0.02
    onset_frame_seconds: float = 0.01
    onset_threshold_mad: float = 3.0
    bpm_min: float = 60.0
    bpm_max: float = 180.0
    default_bpm: float = 120.0
    primary_bars: int = 4
    max_materials: int = 16

    def __post_init__(self) -> None:
        if not 0 <= self.quality_threshold <= 1:
            raise ValueError("quality_threshold must be in 0..1")
        if not 0 <= self.variant_difference_threshold <= 1:
            raise ValueError("variant_difference_threshold must be in 0..1")
        if self.one_shot_min_seconds >= self.one_shot_max_seconds:
            raise ValueError("one-shot duration range is invalid")
        if self.max_materials != 16:
            raise ValueError("materials-v1 has exactly 16 fixed slots")


DEFAULT_MATERIAL_CONFIG = MaterialExtractionConfig()
