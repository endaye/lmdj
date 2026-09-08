#!/usr/bin/env python3
"""Independent bounded reader for the runtime-content wire contract."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess

import json_schema


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/contracts"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
MODES = ("one-shot", "gate", "loop-gate", "loop-toggle")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def identity(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "byte_length": len(data)}


class Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.offset = 0

    def take(self, count):
        require(0 <= count <= len(self.data) - self.offset, "length")
        result = self.data[self.offset:self.offset + count]
        self.offset += count
        return result

    def unpack(self, layout):
        return struct.unpack("<" + layout, self.take(struct.calcsize("<" + layout)))


def read_content(data, expected, limits):
    """Return metadata and PCM; validate every body before decoding PCM words."""
    encoded_limit, pcm_limit, frame_limit, pad_limit, event_limit = limits
    require(len(data) <= encoded_limit, "encoded_budget")
    require(identity(data) == expected, "identity")
    reader = Reader(data)
    require(bytes(reader.take(8)) == b"LMDJRC01", "magic")
    major, minor, patch, reserved = reader.unpack("4H")
    require((major, minor, patch) == (1, 0, 0), "version")
    require(reserved == 0, "reserved")
    size, capabilities = reader.unpack("2Q")
    require(size == len(data), "length")
    require(capabilities == 7, "capabilities")
    source_ids = [bytes(reader.take(36)).decode("ascii", errors="replace") for _ in range(2)]
    require(all(UUID.fullmatch(value) for value in source_ids), "source")
    revision, bpm, bars, reserved, ppq, ticks, pad_count, event_count, sample_count = reader.unpack("QHBB5I")
    require(reserved == 0, "reserved")
    require(40 <= bpm <= 240 and bars in (1, 2, 4, 8) and ppq == 960 and ticks == bars * 3840, "timing")
    require(pad_count <= min(64, pad_limit) and sample_count <= pad_count, "pad_budget")
    require(event_count <= event_limit, "event_budget")
    # Python integers do not wrap; reserve no count-sized list before this check.
    table = Reader(reader.take(pad_count * 20 + event_count * 12))
    pads, slots, used = [], set(), set()
    previous_slot = (-1, -1)
    for _ in range(pad_count):
        bank, pad, mode, mute, sample, start, end, gain = table.unpack("4B3If")
        slot = (bank, pad)
        require(bank < 4 and pad < 16 and slot > previous_slot, "slot")
        require(mode < 4 and mute < 2 and math.isfinite(gain) and 0 <= gain <= 2 and math.copysign(1, gain) > 0, "playback")
        require(sample < sample_count, "sample_reference")
        if sample not in used:
            require(sample == len(used), "sample_order")
            used.add(sample)
        slots.add(slot)
        previous_slot = slot
        pads.append({"slot": {"bank": bank, "pad": pad}, "sample_index": sample,
                     "start_frame": start, "end_frame": end, "trigger_mode": MODES[mode],
                     "linear_gain": gain, "muted": bool(mute)})
    require(len(used) == sample_count, "unused_sample")
    events, previous_event = [], (-1, -1, -1)
    for _ in range(event_count):
        bank, pad, velocity, reserved, onset, duration = table.unpack("4B2I")
        require(reserved == 0, "reserved")
        require((bank, pad) in slots, "event_reference")
        require(1 <= velocity <= 127 and onset < ticks and 0 < duration <= ticks - onset, "event")
        key = (onset, bank, pad)
        require(key > previous_event, "event_order")
        previous_event = key
        events.append({"slot": {"bank": bank, "pad": pad}, "onset_tick": onset,
                       "duration_tick": duration, "velocity": velocity})
    samples, pcm_views, seen = [], [], set()
    pcm_total = 0
    for _ in range(sample_count):
        (body_length,) = reader.unpack("Q")
        digest = bytes(reader.take(32)).hex()
        body = reader.take(body_length)
        require(hashlib.sha256(body).hexdigest() == digest, "sample_identity")
        require((digest, body_length) not in seen, "duplicate_sample")
        seen.add((digest, body_length))
        sample_reader = Reader(body)
        rate, channels, reserved, frames = sample_reader.unpack("IHHI")
        require(reserved == 0, "reserved")
        require(rate == 48000 and channels in (1, 2) and frames > 0, "pcm")
        require(frames <= frame_limit, "frame_budget")
        pcm_size = frames * channels * 2
        require(body_length == 12 + pcm_size, "length")
        pcm_total += pcm_size
        require(pcm_total <= pcm_limit, "pcm_budget")
        pcm_views.append(sample_reader.take(pcm_size))
        samples.append({"identity": {"sha256": digest, "byte_length": body_length},
                        "sample_rate": rate, "channels": channels, "frame_count": frames,
                        "pcm_byte_length": pcm_size})
    require(reader.offset == len(data), "trailing")
    for pad in pads:
        require(0 <= pad["start_frame"] < pad["end_frame"] <= samples[pad["sample_index"]]["frame_count"], "trim")
    metadata = {"contract": "lmdj.runtime-content.v1", "contract_version": "1.0.0",
                "identity": expected, "required_capabilities": ["pattern", "live-pad", "pcm16le"],
                "source": {"project_id": source_ids[0], "pattern_id": source_ids[1], "revision": revision},
                "pattern": {"bpm": bpm, "bars": bars, "ppq": ppq, "loop_length_ticks": ticks, "events": events},
                "pads": pads, "samples": samples}
    return metadata, [tuple(value[0] for value in struct.iter_unpack("<h", pcm)) for pcm in pcm_views]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer", required=True)
    args = parser.parse_args()
    golden = bytes.fromhex((FIXTURES / "runtime-content-v1.hex").read_text())
    expected = json.loads((FIXTURES / "runtime-content-valid.json").read_text())
    schema = json.loads((ROOT / "contracts/runtime-content/lmdj.runtime-content.v1.schema.json").read_text())
    limits = (248, 8, 4, 2, 1)
    actual, pcm = read_content(golden, expected["identity"], limits)
    assert actual == expected, "why: wire metadata differs from the retained projection; remedy: reconcile the reader with the normative vector"
    assert pcm == [(-32768, -1, 0, 32767)], "why: signed PCM words were decoded incorrectly; remedy: preserve signed little-endian PCM16"
    json_schema.check(actual, schema, "runtime-content-v1")
    invalid_slot = json.loads((FIXTURES / "runtime-content-invalid-slot.json").read_text())
    violations = json_schema.validate(invalid_slot, schema)
    assert len(violations) == 1 and "bank" in violations[0], (
        "why: the retained invalid Slot must fail only its bank bound; "
        f"remedy: restore the closed Slot schema and one-defect fixture: {violations}"
    )
    emitted = bytes.fromhex(subprocess.check_output([args.consumer, "--emit-fixture"], text=True))
    assert emitted == golden, "why: C++ encoding differs from the independent fixed vector; remedy: fix the codec, not the retained identity"
    assert read_content(emitted, expected["identity"], limits) == (actual, pcm), "why: C++ wire content does not round-trip through the independent reader; remedy: reconcile framing and sample semantics"

    def rejects(data, reason, budget=limits, expected_identity=None):
        try:
            read_content(data, expected_identity or identity(data), budget)
        except ValueError as error:
            assert str(error) == reason, f"why: rejection reached {error}, expected {reason}; remedy: isolate the malformed field and its validation boundary"
        else:
            raise AssertionError(f"why: accepted malformed content ({reason}); remedy: enforce the normative wire validation")

    rejects(golden, "identity", expected_identity={"sha256": "0" * 64, "byte_length": 248})
    rejects(golden, "identity", expected_identity={"sha256": identity(golden)["sha256"], "byte_length": 247})
    for index, reason in enumerate(("encoded_budget", "pcm_budget", "frame_budget", "pad_budget", "event_budget")):
        budget = list(limits)
        budget[index] -= 1
        rejects(golden, reason, tuple(budget))
    for length in range(len(golden)):
        data = bytearray(golden[:length])
        if length >= 24:
            struct.pack_into("<Q", data, 16, length)
        rejects(data, "length")
    for offset, layout, value, reason in (
        (0, "B", 0, "magic"), (8, "H", 2, "version"), (10, "H", 1, "version"),
        (12, "H", 1, "version"), (14, "H", 1, "reserved"), (24, "Q", 15, "capabilities"),
        (112, "H", 39, "timing"), (115, "B", 1, "reserved"), (136, "B", 4, "slot"),
        (138, "B", 4, "playback"), (139, "B", 2, "playback"), (140, "I", 1, "sample_reference"),
        (148, "I", 5, "trim"), (152, "f", float("nan"), "playback"),
        (152, "f", -0.0, "playback"), (176, "B", 3, "event_reference"),
        (178, "B", 0, "event"), (179, "B", 1, "reserved"), (184, "I", 0, "event"),
        (188, "Q", 21, "length"), (247, "B", 0, "sample_identity"),
    ):
        data = bytearray(golden)
        struct.pack_into("<" + layout, data, offset, value)
        rejects(data, reason)
    data = bytearray(golden + b"\x00")
    struct.pack_into("<Q", data, 16, len(data))
    rejects(data, "trailing", (249, *limits[1:]))
    # Rebind the sample digest to reach descriptor validation, not just hashing.
    for offset, layout, value, reason in ((228, "I", 44100, "pcm"), (232, "H", 3, "pcm"),
                                        (234, "H", 1, "reserved"), (236, "I", 0, "pcm")):
        data = bytearray(golden)
        struct.pack_into("<" + layout, data, offset, value)
        data[196:228] = hashlib.sha256(data[228:]).digest()
        rejects(data, reason)
    print("runtime-content independent wire/schema/C++ conformance passed")


if __name__ == "__main__":
    main()
