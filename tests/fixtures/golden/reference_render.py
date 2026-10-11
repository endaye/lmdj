#!/usr/bin/env python3
"""Generate the deterministic Golden Audio fixtures.

Two independent oracles live here:

* the one-bar 120 BPM Pattern render; and
* the Sound Set audition slot-3 golden waveform (#994), computed from the
  pinned Foundry ``Foundry Hat Closed`` source blob through the documented
  rational-time resample, downmix, unity gain, 96-frame declick ramps and
  PCM16 quantization convention.

Both are pure-stdlib mathematical statements. Neither imports or calls the
cooker, the realtime engine or any other product kernel; agreement between a
generated reference and an actual product render is asserted by the C++ test,
never by regenerating the expectation from the actual output.
"""

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
PPQ = 960
TICKS_PER_BAR = 4 * PPQ
TICK_DENOMINATOR = SAMPLE_RATE * 60
VELOCITY_MAX = 127

GOLDEN_DIR = Path(__file__).resolve().parent
AUDIO_DIR = GOLDEN_DIR.parent / "audio"
OUTPUT_PATH = GOLDEN_DIR / "one_bar_120bpm.wav"
SHA256_PATH = GOLDEN_DIR / "one_bar_120bpm.sha256"

# The pinned Sound Set audition source (#994): Foundry CC0 slot 3,
# ``Foundry Hat Closed``, a 44.1 kHz stereo PCM16 WAV blob named by its own
# SHA-256. The blob is content-addressed repository content, so pinning its
# digest here fails closed if the corpus ever changes underneath the oracle.
AUDITION_SOURCE_PATH = (
    GOLDEN_DIR.parent / "soundset" / "blob" /
    "ede3cc971041736b34a866bb00c24ef1c687ec09570a0e0e1815c3dd89b208b2"
)
AUDITION_SOURCE_SHA256 = (
    "ede3cc971041736b34a866bb00c24ef1c687ec09570a0e0e1815c3dd89b208b2"
)
AUDITION_SOURCE_RATE = 44_100
AUDITION_SOURCE_FRAMES = 2_646
AUDITION_PREPARED_FRAMES = 2_880
AUDITION_TAIL_FRAMES = 128
AUDITION_RAMP_FRAMES = 96
AUDITION_OUTPUT_PATH = GOLDEN_DIR / "soundset_audition_slot3.wav"
AUDITION_SHA256_PATH = GOLDEN_DIR / "soundset_audition_slot3.sha256"


def floor_div(numerator: int, denominator: int) -> int:
    return numerator // denominator


def scale_velocity(sample_value: int, velocity: int) -> int:
    return floor_div(sample_value * velocity + 63, VELOCITY_MAX)


def tick_numerator(anchor: int, frames: int, bpm: int) -> int:
    return anchor + frames * bpm * PPQ


def whole_tick(numerator: int) -> int:
    return numerator // TICK_DENOMINATOR


def tick_boundary_frame(tick: int, bpm: int) -> int:
    numerator = tick * TICK_DENOMINATOR
    rate = bpm * PPQ
    return (numerator + rate - 1) // rate


def verify_transport_vectors() -> None:
    assert tick_numerator(0, 62, 192) == 11_427_840
    assert whole_tick(tick_numerator(0, 62, 192)) == 3
    assert whole_tick(tick_numerator(0, 63, 192)) == 4
    frozen = tick_numerator(0, 17, 123)
    assert frozen == 2_007_360
    assert tick_numerator(frozen, 31, 97) == 4_894_080


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
    frame_count = tick_boundary_frame(BARS * TICKS_PER_BAR, BPM)
    output = [0] * (frame_count * CHANNELS)
    events = (
        ("kick.wav", 0, 240, 127),
        ("snare.wav", 960, 240, 127),
        ("kick.wav", 1_920, 240, 127),
        ("snare.wav", 2_880, 240, 127),
    )

    for filename, onset_tick, duration_tick, velocity in events:
        source_channels, source = read_pcm16(AUDIO_DIR / filename)
        start_frame = tick_boundary_frame(onset_tick, BPM)
        release_frame = tick_boundary_frame(onset_tick + duration_tick, BPM)
        if release_frame <= start_frame:
            raise ValueError("invalid Golden Audio event duration")
        source_frames = len(source) // source_channels
        for source_frame in range(source_frames):
            output_frame = start_frame + source_frame
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


def audition_symmetric_round(numerator: int, denominator: int) -> int:
    """Round half away from zero over integers, matching no product code."""
    half = denominator // 2
    if numerator >= 0:
        return (numerator + half) // denominator
    return -((-numerator + half) // denominator)


def audition_quantize(value: float) -> int:
    """float to PCM16: negatives scale by 32768, non-negatives by 32767."""
    scaled = value * (32_768 if value < 0 else 32_767)
    rounded = (
        int(scaled + 0.5) if scaled >= 0 else -int(-scaled + 0.5)
    )
    return max(-32_768, min(32_767, rounded))


def render_soundset_audition() -> list[int]:
    """The independent audition oracle (#994).

    Reads the pinned 44.1 kHz stereo source blob and computes, without any
    product kernel: rational-time linear resampling to 48 kHz with integer
    symmetric rounding and a last-source-frame clamp; per-channel PCM16
    normalization (positive /32767, negative /32768); a 0.5 stereo average;
    unity velocity gain; the 96-frame attack/end declick ramps; the +/-1
    output clamp; mono duplicated into stereo; and a 128-frame silent tail.
    """
    raw = AUDITION_SOURCE_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != AUDITION_SOURCE_SHA256:
        raise ValueError(
            "Sound Set audition source blob digest drifted from the pinned "
            f"SHA-256: {AUDITION_SOURCE_PATH}"
        )
    with wave.open(str(AUDITION_SOURCE_PATH), "rb") as source:
        if (
            source.getframerate() != AUDITION_SOURCE_RATE
            or source.getnchannels() != 2
            or source.getsampwidth() != 2
            or source.getcomptype() != "NONE"
            or source.getnframes() != AUDITION_SOURCE_FRAMES
        ):
            raise ValueError(
                "Sound Set audition source blob geometry drifted from the "
                f"pinned expectation: {AUDITION_SOURCE_PATH}"
            )
        payload = source.readframes(AUDITION_SOURCE_FRAMES)
    source_samples = list(
        struct.unpack(
            f"<{AUDITION_SOURCE_FRAMES * 2}h",
            payload,
        )
    )

    output: list[int] = []
    for frame in range(
        AUDITION_PREPARED_FRAMES + AUDITION_TAIL_FRAMES
    ):
        if frame >= AUDITION_PREPARED_FRAMES:
            output.extend((0, 0))
            continue

        # Rational-time linear resample: source_position advances by the
        # source rate per output frame at the 48 kHz runtime rate.
        source_position = frame * AUDITION_SOURCE_RATE
        source_frame = source_position // SAMPLE_RATE
        remainder = source_position % SAMPLE_RATE
        prepared_channels: list[int] = []
        for channel in range(2):
            if source_frame >= AUDITION_SOURCE_FRAMES - 1:
                prepared_channels.append(
                    source_samples[
                        (AUDITION_SOURCE_FRAMES - 1) * 2 + channel
                    ]
                )
                continue
            left = source_samples[source_frame * 2 + channel]
            right = source_samples[(source_frame + 1) * 2 + channel]
            weighted = (
                left * (SAMPLE_RATE - remainder) + right * remainder
            )
            prepared_channels.append(
                audition_symmetric_round(weighted, SAMPLE_RATE)
            )

        # PCM16 normalization and stereo downmix, then unity gain.
        normalized = [
            sample / (32_767 if sample >= 0 else 32_768)
            for sample in prepared_channels
        ]
        mono = (normalized[0] + normalized[1]) * 0.5

        # The 96-frame attack and end declick ramps of a neutral one-shot
        # voice: frame 0 is silent, the ramp reaches unity at frame 96, and
        # the final 95 frames fade back down toward silence.
        ramp = 1.0
        if frame < AUDITION_RAMP_FRAMES:
            ramp *= frame / AUDITION_RAMP_FRAMES
        remaining = AUDITION_PREPARED_FRAMES - frame
        if remaining < AUDITION_RAMP_FRAMES:
            ramp *= remaining / AUDITION_RAMP_FRAMES

        value = mono * ramp
        value = max(-1.0, min(1.0, value))
        sample = audition_quantize(value)
        output.extend((sample, sample))
    return output


def expected_audition_outputs() -> tuple[bytes, bytes]:
    output = render_soundset_audition()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as destination:
        destination.setnchannels(CHANNELS)
        destination.setsampwidth(2)
        destination.setframerate(SAMPLE_RATE)
        destination.writeframes(struct.pack(f"<{len(output)}h", *output))
    wav_bytes = buffer.getvalue()
    digest = hashlib.sha256(wav_bytes).hexdigest()
    sha_bytes = f"{digest}  {AUDITION_OUTPUT_PATH.name}\n".encode("ascii")
    return wav_bytes, sha_bytes


def write_audition_outputs(wav_bytes: bytes, sha_bytes: bytes) -> None:
    AUDITION_OUTPUT_PATH.write_bytes(wav_bytes)
    AUDITION_SHA256_PATH.write_bytes(sha_bytes)


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
    verify_transport_vectors()

    fixtures = (
        (
            OUTPUT_PATH,
            SHA256_PATH,
            expected_outputs,
            write_outputs,
        ),
        (
            AUDITION_OUTPUT_PATH,
            AUDITION_SHA256_PATH,
            expected_audition_outputs,
            write_audition_outputs,
        ),
    )

    if args.update:
        for wav_path, _, expected, write in fixtures:
            wav_bytes, sha_bytes = expected()
            write(wav_bytes, sha_bytes)
            digest = hashlib.sha256(wav_bytes).hexdigest()
            print(f"Golden Audio updated: {wav_path.name} sha256={digest}")
        return 0

    failed = False
    for wav_path, sha_path, expected, write in fixtures:
        wav_bytes, sha_bytes = expected()
        digest = hashlib.sha256(wav_bytes).hexdigest()
        output_exists = wav_path.exists()
        sha_exists = sha_path.exists()
        if not output_exists and not sha_exists:
            write(wav_bytes, sha_bytes)
            print(f"Golden Audio generated: {wav_path.name} sha256={digest}")
            continue
        if output_exists != sha_exists:
            print(
                "Golden Audio oracle is incomplete; "
                "use --update to replace both outputs: " + wav_path.name,
                file=sys.stderr,
            )
            failed = True
            continue
        mismatches: list[str] = []
        if wav_path.read_bytes() != wav_bytes:
            mismatches.append(wav_path.name)
        if sha_path.read_bytes() != sha_bytes:
            mismatches.append(sha_path.name)
        if mismatches:
            print(
                "Golden Audio drift detected in "
                + ", ".join(mismatches)
                + "; inspect the change and use --update to rebaseline",
                file=sys.stderr,
            )
            failed = True
            continue
        print(f"Golden Audio verified: {wav_path.name} sha256={digest}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
