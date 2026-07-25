import shutil
import json
from pathlib import Path

from lmdj_audio_worker.creator_runner import CreatorPipelineRunner
from lmdj_audio_worker.job import process_job
from lmdj_audio_worker.music_metadata import KeyEstimate
from lmdj_audio_worker.separation.contract import (
    SeparationResult,
    SeparationError,
    SeparatorInfo,
    write_result,
)
from lmdj_patchify.patchify import patchify_package

from tests.materials.helpers import write_fixture_audio


class FixtureSeparator:
    def __init__(self, source_stems: Path) -> None:
        self.source_stems = source_stems
        self.calls = 0

    def separate(self, audio: Path, output_dir: Path):
        self.calls += 1
        shutil.copytree(self.source_stems, output_dir / "stems")
        result = SeparationResult(
            status="completed",
            source="runner",
            input_sha256="a" * 64,
            separator=SeparatorInfo(
                id="fixture-separator",
                family="fixture",
                checkpoint_sha256="b" * 64,
                runner_version="fixture-v1",
            ),
            requested_device="cpu",
            actual_device="cpu",
            stems={
                name: f"stems/{name}.wav"
                for name in ("drums", "bass", "vocals", "other")
            },
            audio={
                "sample_rate": 44100,
                "channels": 2,
                "duration_seconds": 16.0,
            },
            performance={
                "model_load_seconds": 0.0,
                "inference_seconds": 0.0,
                "wall_seconds": 0.0,
                "peak_rss_bytes": 0,
                "peak_device_memory_bytes": 0,
            },
        )
        write_result(output_dir / "separation.json", result)
        return result, "c" * 64


class FailingSeparator:
    def separate(self, _audio: Path, _output_dir: Path):
        return (
            SeparationResult(
                status="failed",
                source="runner",
                input_sha256="a" * 64,
                separator=SeparatorInfo(
                    id="fixture-separator",
                    family="fixture",
                    checkpoint_sha256="b" * 64,
                    runner_version="fixture-v1",
                ),
                requested_device="cpu",
                error=SeparationError(
                    category="inference",
                    exit_code=2,
                    stage="runner",
                    stderr_tail="separator exploded",
                    elapsed_seconds=0.1,
                ),
            ),
            "c" * 64,
        )


def test_creator_runner_builds_material_package_and_reports_extracting(tmp_path):
    source, stems = write_fixture_audio(tmp_path / "fixture")
    backend = FixtureSeparator(stems)
    runner = CreatorPipelineRunner(separator=backend)
    stages = []

    package = runner.run_with_stages(
        source,
        tmp_path / "job",
        "source-test",
        stages.append,
    )
    patch = patchify_package(package)

    assert stages == ["extracting"]
    assert backend.calls == 1
    assert (package / "timing.json").is_file()
    assert (package / "separation.json").is_file()
    assert (package / "materials.json").is_file()
    assert (package / "chart.mid").is_file()
    assert patch.source["pipeline"] == "materials-v1"
    assert 1 <= patch.metadata["material_count"] <= 16


class FixtureKeyAnalyzer:
    def analyze(self, _audio: Path) -> KeyEstimate:
        return KeyEstimate("C major", 1.0)


def test_real_creator_runner_completes_worker_job_without_legacy_fallback(tmp_path):
    source, stems = write_fixture_audio(tmp_path / "fixture")
    runner = CreatorPipelineRunner(separator=FixtureSeparator(stems))
    states = []

    final = process_job(
        source,
        jobs_root=tmp_path / "jobs",
        runner=runner,
        job_id="materialjob",
        on_state=lambda status: states.append(status.state),
        key_analyzer=FixtureKeyAnalyzer(),
    )

    assert final.state == "completed"
    assert final.pipeline == "materials-v1"
    assert states == [
        "queued",
        "separating",
        "extracting",
        "patchifying",
        "completed",
    ]
    package = tmp_path / "jobs" / "materialjob" / (final.package_dir or "")
    export_source = json.loads((package / "export-source.json").read_text())
    assert export_source["timing"] == ["timing.json"]
    assert export_source["stems"] == [
        "stems/bass.wav",
        "stems/drums.wav",
        "stems/other.wav",
        "stems/vocals.wav",
    ]
    assert export_source["provenance"]["pipeline"] == "materials-v1"


def test_material_failure_is_terminal_without_legacy_artifacts(tmp_path):
    source, _ = write_fixture_audio(tmp_path / "fixture")
    runner = CreatorPipelineRunner(separator=FailingSeparator())
    states = []

    final = process_job(
        source,
        jobs_root=tmp_path / "jobs",
        runner=runner,
        job_id="failedmaterial",
        on_state=lambda status: states.append(status.state),
        key_analyzer=FixtureKeyAnalyzer(),
    )

    assert final.state == "failed"
    assert final.pipeline == "materials-v1"
    assert states == ["queued", "separating", "failed"]
    assert "separator exploded" in (final.error or "")
    job_dir = tmp_path / "jobs" / "failedmaterial"
    assert not list(job_dir.rglob("lanes.json"))
    assert not list(job_dir.rglob("patch.json"))
