#!/usr/bin/env python3
"""Deterministic Sound Set Catalog fixture corpus.

The corpus is a local `lmdj.soundset-catalog.v1` Catalog: one index plus a
content-addressed store of canonical `lmdj.soundset.v1` manifest objects and
PCM16 WAV blobs. It exists so Stage 11 Tasks 4, 5 and 7 can exercise inspect,
preview and install against real bytes without a network.

Every byte here is produced by integer-only arithmetic so the generator
reproduces the committed tree byte-for-byte on any platform and any Python 3.

Layout under the corpus root (see `tests/fixtures/soundset/README.md`):

    catalog/index.json   the `lmdj.soundset-catalog.v1` index
    manifest/<sha256>    canonical manifest objects, addressed by content
    blob/<sha256>        Artifact blobs, addressed by content

`{object_kind, sha256}` therefore resolves to exactly one basename under
exactly one directory, which is what S11-D6 asks a Catalog adapter to do.
"""

from __future__ import annotations

import hashlib
import json
import struct


# S11-D1: canonical bytes are the UTF-8 output of `foundation::canonical_json`
# with no trailing newline. nlohmann orders object keys by byte value and dumps
# without separators padding, which `sort_keys` plus tight separators mirrors
# exactly for the ASCII keys this Contract uses.
def canonical_json_bytes(value: object) -> bytes:
    """Return the S11-D1 canonical bytes of `value`."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------
# WAV synthesis
# --------------------------------------------------------------------------


def _riff_chunk(identifier: bytes, payload: bytes) -> bytes:
    if len(identifier) != 4:
        raise ValueError("RIFF chunk identifiers are four bytes")
    padding = b"\x00" if len(payload) % 2 else b""
    return identifier + struct.pack("<I", len(payload)) + payload + padding


def wav_bytes(
    sample_rate: int,
    channels: int,
    bits_per_sample: int,
    samples: list[int],
) -> bytes:
    """Return a canonical RIFF/WAVE file for interleaved integer `samples`."""
    sample_width = bits_per_sample // 8
    block_align = channels * sample_width
    if bits_per_sample == 16:
        data = struct.pack("<%dh" % len(samples), *samples)
    elif bits_per_sample == 8:
        # 8-bit WAV samples are unsigned with 128 as silence.
        data = bytes((value >> 8) + 128 for value in samples)
    else:
        raise ValueError(f"unsupported bit depth: {bits_per_sample}")
    body = _riff_chunk(
        b"fmt ",
        struct.pack(
            "<HHIIHH",
            1,  # WAVE_FORMAT_PCM
            channels,
            sample_rate,
            sample_rate * block_align,
            block_align,
            bits_per_sample,
        ),
    ) + _riff_chunk(b"data", data)
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body


def percussive_samples(
    frame_count: int,
    channels: int,
    seed: int,
    peak: int = 24_000,
) -> list[int]:
    """Integer-only decaying noise burst; identical on every platform."""
    state = seed & 0xFFFFFFFF
    samples: list[int] = []
    for frame in range(frame_count):
        remaining = frame_count - frame
        for _ in range(channels):
            state = (state * 1_664_525 + 1_013_904_223) & 0xFFFFFFFF
            raw = ((state >> 11) & 0xFFFF) - 0x8000
            samples.append(raw * peak // 32_768 * remaining // frame_count)
    return samples


class BlobSpec:
    """One synthesised Artifact blob."""

    def __init__(
        self,
        label: str,
        sample_rate: int,
        channels: int,
        seed: int,
        bits_per_sample: int = 16,
        duration_ms: int = 60,
    ) -> None:
        self.label = label
        self.sample_rate = sample_rate
        self.channels = channels
        self.bits_per_sample = bits_per_sample
        self.duration_ms = duration_ms
        self.seed = seed

    def build(self) -> bytes:
        frame_count = self.sample_rate * self.duration_ms // 1000
        return wav_bytes(
            self.sample_rate,
            self.channels,
            self.bits_per_sample,
            percussive_samples(frame_count, self.channels, self.seed),
        )


# --------------------------------------------------------------------------
# Corpus definition
# --------------------------------------------------------------------------

MEDIA_TYPE = "audio/wav"

# Blob catalogue. Names are descriptive only; the store addresses by content.
BLOBS = {
    # Set A — every S8-D6-legal rate/channel combination.
    "a-kick-44100-mono": BlobSpec("a-kick-44100-mono", 44_100, 1, 0x00000101),
    "a-snare-44100-mono": BlobSpec("a-snare-44100-mono", 44_100, 1, 0x00000102),
    "a-clap-48000-mono": BlobSpec("a-clap-48000-mono", 48_000, 1, 0x00000103),
    "a-hat-closed-44100-stereo": BlobSpec(
        "a-hat-closed-44100-stereo", 44_100, 2, 0x00000104
    ),
    "a-hat-open-48000-stereo": BlobSpec(
        "a-hat-open-48000-stereo", 48_000, 2, 0x00000105
    ),
    "a-perc-44100-mono": BlobSpec("a-perc-44100-mono", 44_100, 1, 0x00000106),
    "a-cymbal-48000-mono": BlobSpec("a-cymbal-48000-mono", 48_000, 1, 0x00000107),
    "a-bass-44100-mono": BlobSpec("a-bass-44100-mono", 44_100, 1, 0x00000108),
    "a-melody-48000-stereo": BlobSpec(
        "a-melody-48000-stereo", 48_000, 2, 0x00000109
    ),
    "a-chord-48000-stereo": BlobSpec(
        "a-chord-48000-stereo", 48_000, 2, 0x0000010A
    ),
    # Set B — CC-BY-4.0.
    "b-kick-48000-mono": BlobSpec("b-kick-48000-mono", 48_000, 1, 0x00000201),
    "b-snare-44100-mono": BlobSpec("b-snare-44100-mono", 44_100, 1, 0x00000202),
    "b-hat-closed-48000-stereo": BlobSpec(
        "b-hat-closed-48000-stereo", 48_000, 2, 0x00000203
    ),
    "b-bass-44100-stereo": BlobSpec(
        "b-bass-44100-stereo", 44_100, 2, 0x00000204
    ),
    # Set C — S8-D6 violations plus one legal neighbour.
    "c-unsupported-rate-22050-mono": BlobSpec(
        "c-unsupported-rate-22050-mono", 22_050, 1, 0x00000301
    ),
    "c-unsupported-depth-44100-mono-8bit": BlobSpec(
        "c-unsupported-depth-44100-mono-8bit",
        44_100,
        1,
        0x00000302,
        bits_per_sample=8,
    ),
    "c-legal-48000-mono": BlobSpec("c-legal-48000-mono", 48_000, 1, 0x00000303),
    # Set D — one honest blob beside the tampered one.
    "d-legal-44100-mono": BlobSpec("d-legal-44100-mono", 44_100, 1, 0x00000401),
    # The manifest declares this blob's identity; the store serves
    # `d-tampered-served` under that name instead.
    "d-tampered-declared": BlobSpec(
        "d-tampered-declared", 48_000, 1, 0x00000402
    ),
    "d-tampered-served": BlobSpec(
        "d-tampered-served", 44_100, 2, 0x00000403, duration_ms=40
    ),
    # Sets E, F, G — eligibility cases; the audio itself is legal.
    "e-kick-48000-mono": BlobSpec("e-kick-48000-mono", 48_000, 1, 0x00000501),
    "e-snare-48000-mono": BlobSpec("e-snare-48000-mono", 48_000, 1, 0x00000502),
    "f-kick-44100-mono": BlobSpec("f-kick-44100-mono", 44_100, 1, 0x00000601),
    "g-kick-44100-mono": BlobSpec("g-kick-44100-mono", 44_100, 1, 0x00000701),
}

# The blob whose stored bytes deliberately contradict its declared identity.
TAMPERED_DECLARED_BLOB = "d-tampered-declared"
TAMPERED_SERVED_BLOB = "d-tampered-served"

CC0 = {
    "spdx_id": "CC0-1.0",
    "rights_holder": "LMDJ Fixtures",
    "copyright": "Copyright 2026 LMDJ Fixtures",
    "attribution": "",
}


def _occupied(slot: int, role: str, name: str, blob: str, **extra) -> dict:
    entry = {"slot": slot, "role": role, "name": name, "blob": blob}
    entry.update(extra)
    return entry


def _empty(slot: int) -> dict:
    return {"slot": slot}


SET_SPECS = [
    {
        "key": "cc0-complete",
        "set_id": "11111111-1111-4111-8111-111111111111",
        "version": "1.0.0",
        "name": "Fixture Foundry CC0",
        "publisher": "LMDJ Fixtures",
        "description": (
            "Sixteen-slot Set covering both S8-D6 sample rates, mono and "
            "stereo, empty slots, and one Artifact reused by two slots."
        ),
        "bpm": 120,
        "key_signature": "Am",
        "license": dict(CC0),
        "slots": [
            _occupied(0, "kick", "Foundry Kick", "a-kick-44100-mono"),
            _occupied(1, "snare", "Foundry Snare", "a-snare-44100-mono"),
            _occupied(2, "clap", "Foundry Clap", "a-clap-48000-mono"),
            _occupied(
                3, "hat_closed", "Foundry Hat Closed", "a-hat-closed-44100-stereo"
            ),
            _occupied(
                4, "hat_open", "Foundry Hat Open", "a-hat-open-48000-stereo"
            ),
            _occupied(5, "perc", "Foundry Perc", "a-perc-44100-mono"),
            _occupied(6, "cymbal", "Foundry Cymbal", "a-cymbal-48000-mono"),
            _occupied(
                7,
                "bass",
                "Foundry Bass",
                "a-bass-44100-mono",
                bpm=120,
                key="Am",
            ),
            _occupied(
                8,
                "melody",
                "Foundry Melody",
                "a-melody-48000-stereo",
                bpm=120,
                key="Am",
            ),
            _occupied(9, "chord", "Foundry Chord", "a-chord-48000-stereo"),
            _empty(10),
            _empty(11),
            # Same Artifact as slot 0: unique-byte accounting must count it
            # once for download and twice for per-Pad residency.
            _occupied(12, "other", "Foundry Kick Alias", "a-kick-44100-mono"),
            _empty(13),
            _empty(14),
            _empty(15),
        ],
    },
    {
        "key": "ccby-attributed",
        "set_id": "22222222-2222-4222-8222-222222222222",
        "version": "1.0.0",
        "name": "Fixture Attribution Kit",
        "publisher": "Bea Waveform",
        "description": "CC-BY-4.0 Set carrying a non-empty attribution string.",
        "bpm": 128,
        "key_signature": "Fm",
        "license": {
            "spdx_id": "CC-BY-4.0",
            "rights_holder": "Bea Waveform",
            "copyright": "Copyright 2026 Bea Waveform",
            "attribution": "Fixture Attribution Kit by Bea Waveform (CC BY 4.0)",
        },
        "slots": [
            _occupied(0, "kick", "Attribution Kick", "b-kick-48000-mono"),
            _occupied(1, "snare", "Attribution Snare", "b-snare-44100-mono"),
            _occupied(
                2,
                "hat_closed",
                "Attribution Hat",
                "b-hat-closed-48000-stereo",
            ),
            _occupied(
                3, "bass", "Attribution Bass", "b-bass-44100-stereo", bpm=128
            ),
        ]
        + [_empty(slot) for slot in range(4, 16)],
    },
    {
        "key": "audio-unsupported",
        "set_id": "33333333-3333-4333-8333-333333333333",
        "version": "1.0.0",
        "name": "Fixture Unsupported Audio Kit",
        "publisher": "LMDJ Fixtures",
        "description": (
            "Manifest and hashes are valid; slot 0 is 22.05 kHz and slot 1 is "
            "8-bit, so both violate S8-D6 while slot 2 stays legal."
        ),
        "license": dict(CC0),
        "slots": [
            _occupied(
                0,
                "kick",
                "Unsupported Rate Kick",
                "c-unsupported-rate-22050-mono",
            ),
            _occupied(
                1,
                "snare",
                "Unsupported Depth Snare",
                "c-unsupported-depth-44100-mono-8bit",
            ),
            _occupied(2, "clap", "Legal Clap", "c-legal-48000-mono"),
        ]
        + [_empty(slot) for slot in range(3, 16)],
    },
    {
        "key": "content-mismatch",
        "set_id": "44444444-4444-4444-8444-444444444444",
        "version": "1.0.0",
        "name": "Fixture Tampered Kit",
        "publisher": "LMDJ Fixtures",
        "description": (
            "Slot 0's stored bytes contradict the declared sha256 and "
            "byte_length; slot 1 is honest."
        ),
        "license": dict(CC0),
        "slots": [
            _occupied(0, "kick", "Tampered Kick", TAMPERED_DECLARED_BLOB),
            _occupied(1, "snare", "Honest Snare", "d-legal-44100-mono"),
        ]
        + [_empty(slot) for slot in range(2, 16)],
    },
    {
        "key": "license-summary-mismatch",
        "set_id": "55555555-5555-4555-8555-555555555555",
        "version": "1.0.0",
        "name": "Fixture Mismatched Summary Kit",
        "publisher": "Bea Waveform",
        "description": (
            "Manifest is eligible; the catalog entry names a different "
            "rights_holder."
        ),
        "license": {
            "spdx_id": "CC-BY-4.0",
            "rights_holder": "Bea Waveform",
            "copyright": "Copyright 2026 Bea Waveform",
            "attribution": "Mismatched Summary Kit by Bea Waveform (CC BY 4.0)",
        },
        "slots": [
            _occupied(0, "kick", "Summary Kick", "e-kick-48000-mono"),
            _occupied(1, "snare", "Summary Snare", "e-snare-48000-mono"),
        ]
        + [_empty(slot) for slot in range(2, 16)],
    },
    {
        "key": "license-unallowlisted",
        "set_id": "66666666-6666-4666-8666-666666666666",
        "version": "1.0.0",
        "name": "Fixture Unallowlisted License Kit",
        "publisher": "LMDJ Fixtures",
        "description": (
            "Schema-valid license block whose spdx_id is outside the v1 "
            "allowlist."
        ),
        "license": {
            "spdx_id": "MIT",
            "rights_holder": "LMDJ Fixtures",
            "copyright": "Copyright 2026 LMDJ Fixtures",
            "attribution": "",
        },
        "slots": [_occupied(0, "kick", "MIT Kick", "f-kick-44100-mono")]
        + [_empty(slot) for slot in range(1, 16)],
    },
    {
        "key": "license-empty-attribution",
        "set_id": "77777777-7777-4777-8777-777777777777",
        "version": "1.0.0",
        "name": "Fixture Unattributed BY Kit",
        "publisher": "LMDJ Fixtures",
        "description": (
            "CC-BY-4.0 with an empty attribution: Schema-valid, ineligible."
        ),
        "license": {
            "spdx_id": "CC-BY-4.0",
            "rights_holder": "LMDJ Fixtures",
            "copyright": "Copyright 2026 LMDJ Fixtures",
            "attribution": "",
        },
        "slots": [_occupied(0, "kick", "Unattributed Kick", "g-kick-44100-mono")]
        + [_empty(slot) for slot in range(1, 16)],
    },
]

# Catalog entries whose `license_summary` deliberately contradicts the
# manifest, keyed by Set key. S11-D6 requires verbatim equality, so these
# entries must be refused with `soundset_license_ineligible` at inspect.
LICENSE_SUMMARY_OVERRIDES = {
    "license-summary-mismatch": {
        "spdx_id": "CC-BY-4.0",
        "rights_holder": "Impostor Records",
    },
}


def build_corpus() -> dict[str, bytes]:
    """Return the whole corpus as a mapping of relative path to file bytes."""
    blob_bytes = {label: spec.build() for label, spec in BLOBS.items()}
    blob_hash = {
        label: sha256_hex(payload) for label, payload in blob_bytes.items()
    }

    files: dict[str, bytes] = {}
    entries: list[dict] = []

    for spec in SET_SPECS:
        manifest: dict[str, object] = {
            "contract": "lmdj.soundset.v1",
            "set_id": spec["set_id"],
            "version": spec["version"],
            "name": spec["name"],
            "publisher": spec["publisher"],
            "license": spec["license"],
        }
        if "description" in spec:
            manifest["description"] = spec["description"]
        if "bpm" in spec:
            manifest["bpm"] = spec["bpm"]
        if "key_signature" in spec:
            manifest["key"] = spec["key_signature"]

        slots: list[dict] = []
        roles: list[str] = []
        unique_bytes: dict[str, int] = {}
        for slot_spec in spec["slots"]:
            if "blob" not in slot_spec:
                slots.append({"slot": slot_spec["slot"]})
                continue
            label = slot_spec["blob"]
            slot: dict[str, object] = {
                "slot": slot_spec["slot"],
                "role": slot_spec["role"],
                "name": slot_spec["name"],
                "artifact": {
                    "sha256": blob_hash[label],
                    "media_type": MEDIA_TYPE,
                    "byte_length": len(blob_bytes[label]),
                },
            }
            if "bpm" in slot_spec:
                slot["bpm"] = slot_spec["bpm"]
            if "key" in slot_spec:
                slot["key"] = slot_spec["key"]
            slots.append(slot)
            roles.append(slot_spec["role"])
            unique_bytes[blob_hash[label]] = len(blob_bytes[label])

            served = (
                TAMPERED_SERVED_BLOB
                if label == TAMPERED_DECLARED_BLOB
                else label
            )
            files[f"blob/{blob_hash[label]}"] = blob_bytes[served]

        manifest["slots"] = slots
        manifest_bytes = canonical_json_bytes(manifest)
        manifest_sha256 = sha256_hex(manifest_bytes)
        files[f"manifest/{manifest_sha256}"] = manifest_bytes

        summary = LICENSE_SUMMARY_OVERRIDES.get(
            spec["key"],
            {
                "spdx_id": spec["license"]["spdx_id"],
                "rights_holder": spec["license"]["rights_holder"],
            },
        )
        entry: dict[str, object] = {
            "set_id": spec["set_id"],
            "version": spec["version"],
            "manifest_sha256": manifest_sha256,
            # S11-D7: canonical manifest bytes plus every unique blob's
            # declared byte_length, each counted once.
            "total_bytes": len(manifest_bytes) + sum(unique_bytes.values()),
            "name": spec["name"],
            "publisher": spec["publisher"],
            "roles_summary": sorted(set(roles)),
            "license_summary": dict(summary),
        }
        if "bpm" in spec:
            entry["bpm"] = spec["bpm"]
        if "key_signature" in spec:
            entry["key"] = spec["key_signature"]
        entries.append(entry)

    index = {"contract": "lmdj.soundset-catalog.v1", "entries": entries}
    files["catalog/index.json"] = canonical_json_bytes(index)
    return files


GENERATED_DIRECTORIES = ("catalog", "manifest", "blob")
