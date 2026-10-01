#!/usr/bin/env python3
"""Generate/check the original LMDJ starter percussion kit (no sampled input)."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import uuid
import wave

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "products/lmdj/assets/default-kit"
SET_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://lmdj.dev/soundsets/original-starter-drums/v1"))
SOUNDS = [
    ("Deep Kick", "kick", 48, .45, .05), ("Tight Kick", "kick", 65, .24, .04),
    ("Dry Snare", "snare", 180, .24, .72), ("Bright Snare", "snare", 230, .32, .82),
    ("Hand Clap", "clap", 850, .26, .98), ("Closed Hat", "hat_closed", 6200, .08, .97),
    ("Open Hat", "hat_open", 5400, .48, .94), ("Shaker", "perc", 4200, .17, .98),
    ("Low Tom", "perc", 105, .42, .06), ("Mid Tom", "perc", 150, .34, .08),
    ("High Tom", "perc", 215, .26, .10), ("Rim", "perc", 1300, .10, .14),
    ("Cowbell", "perc", 620, .20, .02), ("Clave", "perc", 1800, .09, .01),
    ("Ride", "cymbal", 3700, .64, .60), ("Crash", "cymbal", 4600, 1.15, .90),
]

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def synth(index, frequency, duration, noise_mix):
    rate = 48000
    frames = int(duration * rate)
    state = 0x13579BDF + index * 7919
    phase = 0.0
    previous = 0.0
    samples = []
    for frame in range(frames):
        time = frame / rate
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        noise = (state / 2147483648.0) - 1.0
        highpass = .5 * (noise - previous)
        previous = noise
        pitched = frequency * (1 + (2.8 if index < 2 else .15) * math.exp(-time * 45))
        phase += 2 * math.pi * pitched / rate
        tone = math.sin(phase)
        if index in (12, 14, 15):
            tone = .5 * (tone + math.sin(phase * 1.483))
        texture = highpass if index in (5, 6, 7, 14, 15) else noise
        envelope = math.exp(-time * 7 / duration)
        if index == 4:
            envelope += .5 * math.exp(-abs(time - .018) * 450) + .4 * math.exp(-abs(time - .035) * 450)
        # Short attack/final fade prevents a discontinuity; retain useful tails.
        fade = min(1, frame / 48, (frames - 1 - frame) / 96)
        value = .68 * fade * envelope * ((1 - noise_mix) * tone + noise_mix * texture)
        samples.append(max(-32767, min(32767, round(value * 32767))))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate)
        wav.writeframes(struct.pack("<" + "h" * frames, *samples))
    return output.getvalue()

def build():
    files = {}
    slots = []
    for index, (name, role, frequency, duration, noise) in enumerate(SOUNDS):
        data = synth(index, frequency, duration, noise)
        sha = digest(data)
        files[f"blob/{sha}"] = data
        slots.append({"slot": index, "name": name, "role": role,
            "artifact": {"sha256": sha, "byte_length": len(data), "media_type": "audio/wav"}})
    license = {"spdx_id": "CC0-1.0", "rights_holder": "LMDJ",
        "copyright": "Copyright 2026 LMDJ", "attribution": ""}
    manifest = {"contract": "lmdj.soundset.v1", "set_id": SET_ID, "version": "1.0.0",
        "name": "LMDJ Starter Drums", "publisher": "LMDJ", "license": license,
        "description": "Sixteen original synthesized percussion sounds. No source recordings.", "slots": slots}
    data = canonical(manifest)
    sha = digest(data)
    files[f"manifest/{sha}"] = data
    entry = {"set_id": SET_ID, "version": "1.0.0", "manifest_sha256": sha,
        "name": manifest["name"], "publisher": "LMDJ",
        "license_summary": {key: license[key] for key in ("spdx_id", "rights_holder")},
        "roles_summary": sorted({slot["role"] for slot in slots}),
        "total_bytes": len(data) + sum(len(blob) for name, blob in files.items() if name.startswith("blob/"))}
    files["catalog/index.json"] = canonical({"contract": "lmdj.soundset-catalog.v1", "entries": [entry]})
    return files

def check(root=CORPUS):
    expected = build()
    actual = {str(p.relative_to(root)): p.read_bytes() for folder in ("blob", "manifest", "catalog")
        for p in (root / folder).rglob("*") if p.is_file()}
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(key for key in expected.keys() & actual.keys() if expected[key] != actual[key])
        raise ValueError(f"default kit differs from synthesis: missing={missing}, extra={extra}, changed={changed}")
    return expected

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        for name, data in build().items():
            target = CORPUS / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    print("default kit: verified" if args.check else "default kit: generated")
