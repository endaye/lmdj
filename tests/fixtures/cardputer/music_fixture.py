#!/usr/bin/env python3
"""Original integer-only drum corpus; generated PCM is not a product input."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

RATE = 48_000
DRUMS = (("kick", 12_000), ("snare", 12_000), ("hat", 4_800), ("clap", 19_200))
MANIFEST = Path(__file__).with_suffix(".json")


def pcm(variant: str, slot: int) -> bytes:
    """Fixed-point triangle chirp + seeded noise and integer decay envelopes."""
    if variant not in ("A", "B") or not 0 <= slot < 4:
        raise ValueError("why: unknown fixture; remedy: use A/B and slot 0..3")
    _, frames = DRUMS[slot]
    state = 0x19660910 + slot * 101 + (variant == "B") * 997
    phase = 0
    previous_noise = 0
    values = []
    for index in range(frames):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        noise = (state >> 16) - 32768
        highpass = (noise - previous_noise) // 2
        previous_noise = noise
        # A descending pitched body gives kick/snare a tonal centre; the
        # noise/click component keeps these percussive rather than pure tones.
        frequency = (48 if variant == "A" else 63) + (120 * (frames - index) ** 3 // frames ** 3)
        phase = (phase + frequency * 65536 // RATE) & 65535
        triangle = 32767 - 2 * abs(phase - 32768)
        if slot == 0:
            signal = (triangle * 7 + noise * max(0, 240 - index) // 240) // 8
        elif slot == 1:
            signal = (noise * 3 + triangle) // 4
        elif slot == 2:
            signal = highpass
        else:
            # Three early bursts followed by a decaying diffuse clap tail.
            burst = max(0, 600 - (index % 960)) if index < 2880 else 180
            signal = highpass * burst // 600
        decay = (frames - 1 - index) ** 2
        attack = min(index, 24)
        values.append(signal * decay * attack // (frames * frames * 24 * 2))
    return struct.pack("<" + "h" * frames, *values)


def events(variant: str) -> list[dict[str, int]]:
    if variant not in ("A", "B"):
        raise ValueError("why: unknown fixture; remedy: use A or B")
    steps = ((0, 8, 16, 24), (4, 12, 20, 28), tuple(range(0, 32, 2)),
             (3, 7, 11, 15, 19, 23, 27, 31))
    result = []
    for slot, positions in enumerate(steps):
        for step in positions:
            result.append({"bank": 0, "pad": slot, "tick": step * 240,
                           "duration_ticks": 120, "velocity": 100 if slot == 2 else 112})
    return sorted(result, key=lambda event: (event["tick"], event["bank"], event["pad"]))


def manifest() -> dict:
    return {
        "schema": "lmdj.cardputer-music-fixture.v1", "license": "CC0-1.0",
        "sample_rate": RATE, "channels": 1, "format": "pcm16le",
        "tempo_bpm": 120, "ppq": 960, "length_ticks": 7680,
        "variants": {
            variant: {
                "samples": [{"name": name, "bank": 0, "pad": slot,
                             "frames": frames, "byte_length": frames * 2,
                             "sha256": hashlib.sha256(pcm(variant, slot)).hexdigest()}
                            for slot, (name, frames) in enumerate(DRUMS)],
                "events": events(variant),
            } for variant in ("A", "B")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the committed manifest")
    parser.add_argument("--output", type=Path, help="write PCM and manifest to a new directory")
    args = parser.parse_args()
    actual = manifest()
    if args.check:
        if json.loads(MANIFEST.read_text()) != actual:
            parser.error("why: fixture identity drift; remedy: review the generator and regenerate the manifest")
        print("fixture manifest: PASS (2 variants, 4 drums and 32 events each)")
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        for variant in ("A", "B"):
            for slot, (name, _) in enumerate(DRUMS):
                (args.output / f"{variant}-{name}.pcm").write_bytes(pcm(variant, slot))
        (args.output / MANIFEST.name).write_text(json.dumps(actual, indent=2) + "\n")
    if not args.check and not args.output:
        print(json.dumps(actual, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
