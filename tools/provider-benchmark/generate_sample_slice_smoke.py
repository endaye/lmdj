#!/usr/bin/env python3
"""Generate the deterministic Stage 12 sample.slice smoke fixture corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


SAMPLE_RATE = 48_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
FIXTURE_PREFIX = "tests/fixtures/provider-benchmark/sample-slice"
GENERATOR_PATH = "tools/provider-benchmark/generate_sample_slice_smoke.py"
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests/fixtures/provider-benchmark/sample-slice"
)
WAV_NAMES = (
    "slice-basic.wav",
    "slice-close-overlap.wav",
    "slice-silence.wav",
    "slice-truncated.wav",
    "slice-bad-header.wav",
)


def _riff_chunk(chunk_id: bytes, contents: bytes) -> bytes:
    padding = b"\x00" if len(contents) % 2 else b""
    return chunk_id + struct.pack("<I", len(contents)) + contents + padding


def _pcm16_wav(samples: list[int]) -> bytes:
    pcm = b"".join(struct.pack("<h", sample) for sample in samples)
    byte_rate = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH_BYTES
    block_align = CHANNELS * SAMPLE_WIDTH_BYTES
    fmt = struct.pack(
        "<HHIIHH",
        1,
        CHANNELS,
        SAMPLE_RATE,
        byte_rate,
        block_align,
        SAMPLE_WIDTH_BYTES * 8,
    )
    payload = b"WAVE" + _riff_chunk(b"fmt ", fmt) + _riff_chunk(b"data", pcm)
    return b"RIFF" + struct.pack("<I", len(payload)) + payload


def _clamp_pcm16(value: int) -> int:
    return max(-32_768, min(32_767, value))


def _render_onsets(
    *,
    frame_count: int,
    onset_frames: tuple[int, ...],
    tail_frames: int,
    peak_amplitude: int,
    carrier_half_period_frames: int,
) -> list[int]:
    samples = [0] * frame_count
    for onset in onset_frames:
        for offset in range(min(tail_frames, frame_count - onset)):
            envelope = peak_amplitude * (tail_frames - offset) // tail_frames
            polarity = 1 if (offset // carrier_half_period_frames) % 2 == 0 else -1
            samples[onset + offset] = _clamp_pcm16(
                samples[onset + offset] + polarity * envelope
            )
    return samples


def _byte_scenario(
    *,
    scenario_id: str,
    scenario_class: str,
    filename: str,
    contents: bytes,
    expected: dict[str, object],
    generation: dict[str, object],
    wav_properties_meaningful: bool = True,
) -> dict[str, object]:
    scenario: dict[str, object] = {
        "id": scenario_id,
        "class": scenario_class,
        "path": f"{FIXTURE_PREFIX}/{filename}",
        "sha256": hashlib.sha256(contents).hexdigest(),
        "byte_length": len(contents),
        "origin": "synthetic",
        "spdx_license": "CC0-1.0",
        "expected": expected,
        "generation": generation,
    }
    if wav_properties_meaningful:
        scenario["sample_rate"] = SAMPLE_RATE
        scenario["channels"] = CHANNELS
    return scenario


def build_corpus() -> tuple[dict[str, bytes], dict[str, object]]:
    """Return exact WAV bytes and their canonical fixture manifest object."""

    basic_generation: dict[str, object] = {
        "kind": "integer_decay_pulses",
        "frame_count": 16_800,
        "onset_frames": [2_400, 7_200, 12_000],
        "tail_frames": 1_440,
        "peak_amplitude": 24_000,
        "carrier_half_period_frames": 24,
    }
    basic = _pcm16_wav(
        _render_onsets(
            frame_count=16_800,
            onset_frames=(2_400, 7_200, 12_000),
            tail_frames=1_440,
            peak_amplitude=24_000,
            carrier_half_period_frames=24,
        )
    )

    close_generation: dict[str, object] = {
        "kind": "integer_decay_pulses",
        "frame_count": 4_800,
        "onset_frames": [480, 1_440],
        "tail_frames": 1_920,
        "peak_amplitude": 16_000,
        "carrier_half_period_frames": 16,
    }
    close = _pcm16_wav(
        _render_onsets(
            frame_count=4_800,
            onset_frames=(480, 1_440),
            tail_frames=1_920,
            peak_amplitude=16_000,
            carrier_half_period_frames=16,
        )
    )

    silence_generation: dict[str, object] = {
        "kind": "silence",
        "frame_count": 4_800,
    }
    silence = _pcm16_wav([0] * 4_800)

    truncated_base_frames = 2_400
    truncated_removed_bytes = 64
    truncated = _pcm16_wav([0] * truncated_base_frames)[:-truncated_removed_bytes]
    truncated_generation: dict[str, object] = {
        "kind": "truncated_pcm16_wav",
        "base_frame_count": truncated_base_frames,
        "removed_tail_bytes": truncated_removed_bytes,
    }

    bad_header = b"NOPE" + silence[4:]
    bad_header_generation: dict[str, object] = {
        "kind": "invalid_riff_signature",
        "base": "slice-silence.wav",
        "replacement_ascii": "NOPE",
    }

    generated = {
        "slice-basic.wav": basic,
        "slice-close-overlap.wav": close,
        "slice-silence.wav": silence,
        "slice-truncated.wav": truncated,
        "slice-bad-header.wav": bad_header,
    }
    scenarios = [
        _byte_scenario(
            scenario_id="basic_three_onsets",
            scenario_class="success",
            filename="slice-basic.wav",
            contents=basic,
            expected={"onset_frames": [2_400, 7_200, 12_000], "tolerance_frames": 480},
            generation=basic_generation,
        ),
        _byte_scenario(
            scenario_id="close_overlapping_tails",
            scenario_class="success",
            filename="slice-close-overlap.wav",
            contents=close,
            expected={"onset_frames": [480, 1_440], "tolerance_frames": 240},
            generation=close_generation,
        ),
        _byte_scenario(
            scenario_id="silence",
            scenario_class="success",
            filename="slice-silence.wav",
            contents=silence,
            expected={"onset_frames": [], "tolerance_frames": 480},
            generation=silence_generation,
        ),
        {
            "id": "missing_input",
            "class": "input_failure",
            "expected": {"reason": "input_artifact_unavailable"},
            "generation": {"kind": "absent_input"},
        },
        _byte_scenario(
            scenario_id="truncated_data",
            scenario_class="input_failure",
            filename="slice-truncated.wav",
            contents=truncated,
            expected={"reason": "source_audio_unsupported"},
            generation=truncated_generation,
        ),
        _byte_scenario(
            scenario_id="bad_riff_header",
            scenario_class="input_failure",
            filename="slice-bad-header.wav",
            contents=bad_header,
            expected={"reason": "source_audio_unsupported"},
            generation=bad_header_generation,
            wav_properties_meaningful=False,
        ),
    ]
    manifest: dict[str, object] = {
        "schema": "lmdj.provider-benchmark-fixtures.v1",
        "capability": "sample.slice",
        "generator": GENERATOR_PATH,
        "license": {
            "spdx": "CC0-1.0",
            "canonical_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "affirmer": "Zhang Yuancheng",
            "scope": "generated WAV files and generated manifest.json in this directory only",
        },
        "scenarios": scenarios,
    }
    return generated, manifest


def _manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _expected_files() -> dict[str, bytes]:
    generated, manifest = build_corpus()
    return {**generated, "manifest.json": _manifest_bytes(manifest)}


def _regenerate_remedy(output_dir: Path) -> str:
    return (
        f"run {sys.executable} {GENERATOR_PATH} "
        f"--output-dir {output_dir} to regenerate the declared corpus"
    )


def _check(
    output_dir: Path, expected: dict[str, bytes]
) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    allowed_names = set(expected) | {"LICENSE.md"}
    if not output_dir.is_dir():
        return [
            (
                f"output directory is missing: {output_dir}",
                _regenerate_remedy(output_dir),
            )
        ]

    for name, contents in expected.items():
        path = output_dir / name
        if not path.is_file() or path.is_symlink():
            problems.append(
                (
                    f"declared fixture is missing or non-regular: {name}",
                    f"remove any non-regular {path} entry, then "
                    + _regenerate_remedy(output_dir),
                )
            )
        elif path.read_bytes() != contents:
            problems.append(
                (
                    f"fixture bytes differ from deterministic output: {name}",
                    _regenerate_remedy(output_dir),
                )
            )

    for entry in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if entry.name not in allowed_names:
            problems.append(
                (
                    f"undeclared fixture entry violates the closed inventory: {entry.name}",
                    f"remove {entry} and rerun the same --check command",
                )
            )
    return problems


def _write(output_dir: Path, expected: dict[str, bytes]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, contents in expected.items():
        (output_dir / name).write_bytes(contents)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    expected = _expected_files()
    if args.check:
        problems = _check(args.output_dir, expected)
        if problems:
            for why, remedy in problems:
                print(
                    f"fixture check failed: why: {why}; remedy: {remedy}",
                    file=sys.stderr,
                )
            return 1
        return 0

    _write(args.output_dir, expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
