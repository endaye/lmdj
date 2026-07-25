from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Protocol

from lmdj_core_models.materials import MaterialProvenance

from lmdj_audio_worker.materials import (
    DEFAULT_MATERIAL_CONFIG,
    MaterialExtractionConfig,
    MaterialExtractor,
    TimingAnalyzer,
)
from lmdj_audio_worker.materials.audio import read_audio
from lmdj_audio_worker.runner import PipelineRunError
from lmdj_audio_worker.separation.cache import ensure_checkpoint
from lmdj_audio_worker.separation.contract import (
    SeparationResult,
    validate_canonical_stems,
)
from lmdj_audio_worker.separation.protocol import SeparationRequest, run_separator
from lmdj_audio_worker.separation.registry import load_registry

_WORKER_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = _WORKER_ROOT / "config" / "separators.json"


class SeparationBackend(Protocol):
    def separate(
        self,
        audio: Path,
        output_dir: Path,
    ) -> tuple[SeparationResult, str]: ...


class RegistrySeparationBackend:
    def __init__(
        self,
        *,
        registry_path: Path = DEFAULT_REGISTRY,
        separator_id: str = "htdemucs",
        device: str = "cpu",
        timeout_sec: int = 1800,
    ) -> None:
        entries = {entry.id: entry for entry in load_registry(registry_path)}
        if separator_id not in entries:
            raise ValueError(
                f"unknown LMDJ separator {separator_id!r}; "
                f"available: {sorted(entries)}"
            )
        entry = entries[separator_id]
        if device not in entry.devices:
            raise ValueError(
                f"separator {separator_id!r} does not support {device!r}"
            )
        self.entry = entry
        self.device = device
        self.timeout_sec = timeout_sec

    def separate(
        self,
        audio: Path,
        output_dir: Path,
    ) -> tuple[SeparationResult, str]:
        checkpoint_dir = ensure_checkpoint(self.entry)
        result = run_separator(
            self.entry,
            SeparationRequest(
                input_path=audio,
                output_dir=output_dir,
                device=self.device,
                seed=0,
            ),
            checkpoint_dir,
            timeout_sec=self.timeout_sec,
        )
        return result, self.entry.env_lock_sha256


class CreatorPipelineRunner:
    pipeline_id = "materials-v1"

    def __init__(
        self,
        separator: SeparationBackend | None = None,
        *,
        timing_analyzer: TimingAnalyzer | None = None,
        extractor: MaterialExtractor | None = None,
        config: MaterialExtractionConfig = DEFAULT_MATERIAL_CONFIG,
    ) -> None:
        self.config = config
        self.separator = separator or RegistrySeparationBackend(
            separator_id=os.environ.get("LMDJ_SEPARATOR_ID", "htdemucs"),
            device=os.environ.get("LMDJ_SEPARATOR_DEVICE", "cpu"),
        )
        self.timing_analyzer = timing_analyzer or TimingAnalyzer(config)
        self.extractor = extractor or MaterialExtractor(config)

    def run(self, audio: Path, out_dir: Path, song_id: str) -> Path:
        return self.run_with_stages(audio, out_dir, song_id, lambda _stage: None)

    def run_with_stages(
        self,
        audio: Path,
        out_dir: Path,
        song_id: str,
        on_stage: Callable[[str], None],
    ) -> Path:
        package_dir = out_dir / song_id
        package_dir.mkdir(parents=True, exist_ok=False)
        timing = self.timing_analyzer.analyze(
            audio,
            package_dir / "timing.json",
        )
        result, environment_lock = self.separator.separate(audio, package_dir)
        if result.status != "completed":
            detail = (
                result.error.stderr_tail
                if result.error is not None
                else "separator returned failed without error detail"
            )
            raise PipelineRunError("material separator failed", detail)
        expected_frames = len(read_audio(audio, self.config.sample_rate))
        stem_errors = validate_canonical_stems(
            package_dir,
            result,
            expected_frames,
        )
        if stem_errors:
            raise PipelineRunError(
                "material separator produced invalid canonical stems",
                "; ".join(stem_errors),
            )
        on_stage("extracting")
        self.extractor.extract(
            original_audio=audio,
            stems_dir=package_dir / "stems",
            timing=timing,
            output_dir=package_dir,
            provenance=MaterialProvenance(
                separator_id=result.separator.id,
                separator_checkpoint_sha256=(
                    result.separator.checkpoint_sha256
                ),
                separator_runner_version=result.separator.runner_version,
                timing_version=self.config.timing_version,
                extractor_runner_version=self.config.runner_version,
                extraction_config_version=self.config.version,
                environment_lock_sha256=environment_lock,
            ),
        )
        return package_dir
