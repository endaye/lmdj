#!/usr/bin/env python3
"""Generate the deterministic one-bar Golden Audio fixture."""

from __future__ import annotations

import argparse
import hashlib
import io
import struct
import sys
import wave
from pathlib import Path
from typing import Sequence


SAMPLE_RATE = 48_000
CHANNELS = 2
BPM = 120
BARS = 1
STEPS_PER_BAR = 16
VELOCITY_MAX = 127

GOLDEN_DIR = Path(__file__).resolve().parent
AUDIO_DIR = GOLDEN_DIR.parent / "audio"
OUTPUT_PATH = GOLDEN_DIR / "one_bar_120bpm.wav"
SHA256_PATH = GOLDEN_DIR / "one_bar_120bpm.sha256"


def floor_div(numerator: int, denominator: int) -> int:
    return numerator // denominator


def scale_velocity(sample_value: int, velocity: int) -> int:
    return floor_div(sample_value * velocity + 63, VELOCITY_MAX)


def read_pcm16(path: Path) -> tuple[int, list[int]]:
    with wave.open(str(path), "rb") as source:
        if (
            source.getframerate() != SAMPLE_RATE
            or source.getnchannels() not in (1, 2)
            or source.getsampwidth() != 2
            or source.getcomptype() != "NONE"
        ):
            raise ValueError(f"unsupported Golden Audio source: {path}")
        channels = source.getnchannels()
        frame_count = source.getnframes()
        payload = source.readframes(frame_count)
        if len(payload) != frame_count * channels * 2:
            raise ValueError(f"truncated Golden Audio source: {path}")
    samples = list(struct.unpack(f"<{frame_count * channels}h", payload))
    return channels, samples


def render() -> list[int]:
    bar_frames = (4 * 60 * SAMPLE_RATE) // BPM
    frame_count = BARS * bar_frames
    output = [0] * (frame_count * CHANNELS)
    events = (
        ("kick.wav", 0, 127),
        ("snare.wav", 4, 127),
        ("kick.wav", 8, 127),
        ("snare.wav", 12, 127),
    )

    for filename, step, velocity in events:
        source_channels, source = read_pcm16(AUDIO_DIR / filename)
        step_frame = (step * SAMPLE_RATE * 60) // (BPM * 4)
        source_frames = len(source) // source_channels
        for source_frame in range(source_frames):
            output_frame = step_frame + source_frame
            if output_frame >= frame_count:
                break
            for channel in range(CHANNELS):
                source_channel = 0 if source_channels == 1 else channel
                sample_value = source[
                    source_frame * source_channels + source_channel
                ]
                scaled = scale_velocity(sample_value, velocity)
                output_index = output_frame * CHANNELS + channel
                mixed = output[output_index] + scaled
                output[output_index] = max(-32_768, min(32_767, mixed))

    return output


def expected_outputs() -> tuple[bytes, bytes]:
    output = render()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as destination:
        destination.setnchannels(CHANNELS)
        destination.setsampwidth(2)
        destination.setframerate(SAMPLE_RATE)
        destination.writeframes(struct.pack(f"<{len(output)}h", *output))
    wav_bytes = buffer.getvalue()
    digest = hashlib.sha256(wav_bytes).hexdigest()
    sha_bytes = f"{digest}  {OUTPUT_PATH.name}\n".encode("ascii")
    return wav_bytes, sha_bytes


def write_outputs(wav_bytes: bytes, sha_bytes: bytes) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(wav_bytes)
    SHA256_PATH.write_bytes(sha_bytes)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the deterministic Golden Audio oracle. "
            "Missing outputs are generated on the first run."
        )
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="explicitly replace the committed WAV and SHA oracle",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    wav_bytes, sha_bytes = expected_outputs()
    digest = hashlib.sha256(wav_bytes).hexdigest()

    if args.update:
        write_outputs(wav_bytes, sha_bytes)
        print(f"Golden Audio updated: {OUTPUT_PATH.name} sha256={digest}")
        return 0

    output_exists = OUTPUT_PATH.exists()
    sha_exists = SHA256_PATH.exists()
    if not output_exists and not sha_exists:
        write_outputs(wav_bytes, sha_bytes)
        print(f"Golden Audio generated: {OUTPUT_PATH.name} sha256={digest}")
        return 0
    if output_exists != sha_exists:
        print(
            "Golden Audio oracle is incomplete; "
            "use --update to replace both outputs",
            file=sys.stderr,
        )
        return 1

    mismatches: list[str] = []
    if OUTPUT_PATH.read_bytes() != wav_bytes:
        mismatches.append(OUTPUT_PATH.name)
    if SHA256_PATH.read_bytes() != sha_bytes:
        mismatches.append(SHA256_PATH.name)
    if mismatches:
        print(
            "Golden Audio drift detected in "
            + ", ".join(mismatches)
            + "; inspect the change and use --update to rebaseline",
            file=sys.stderr,
        )
        return 1

    print(f"Golden Audio verified: {OUTPUT_PATH.name} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
