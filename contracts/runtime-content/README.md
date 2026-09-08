# lmdj.runtime-content.v1

Contract version: `1.0.0`. Normative wire specification.
Authority: [approved first slice](../../docs/prd/decisions/2026-09-08-runtime-content-first-slice.md).
This new source Contract is not yet selected by the desktop Product Assembly.

## Meaning and identity

One derived, immutable Pattern plus its event Pad Slots and explicitly selected
extra live Pad Slots. It contains prepared 48 kHz mono/stereo PCM16, not Project
Truth, a Project Bundle, a memory dump, Provider settings or a device session.
The export request binds an expected Project ID, revision and Pattern ID. Events
refer only to Pad Slots. All included Pads can be triggered live; a Pad absent
from the Pattern may still need material. Unrelated Pads/Assets are not exported.

The complete identity is `{sha256, byte_length}` over **every encoded byte**,
including the header. It travels separately from the content, avoiding a digest
self-reference. A reader requires and verifies both fields. Hashing establishes
integrity, not origin authentication. No filenames, URLs, compressed or executable
payloads are supported. A failed decode returns no Snapshot, not partial content.

`lmdj.runtime-content.v1.schema.json` describes the semantic metadata projection
produced by the reference reader. That JSON is **not the wire format** and a
schema pass does not replace the binary/cross-field/identity checks below.

## Binary layout

Every integer is unsigned little-endian unless specified. PCM words are signed
two's-complement 16-bit little-endian; gains are IEEE-754 binary32 stored as
little-endian bits. UUIDs are 36 lower-case ASCII bytes with hyphens, versions
1–5 and RFC variant, matching the existing Project identity rules. There is no
alignment padding other than the explicit reserved fields. All reserved fields
must be zero. Readers reject an unsupported exact version or required capability
set; a future incompatible layout needs a new Contract Major.

The 136-byte header:

| Offset | Bytes | Field |
| --- | --- | --- |
| 0 | 8 | ASCII `LMDJRC01` |
| 8 | 2 + 2 + 2 + 2 | Major `1`, Minor `0`, Patch `0`, reserved `0` |
| 16 | 8 | Complete encoded byte length, equal to the supplied identity and input span |
| 24 | 8 | Required capabilities: exactly `7` (bit 0 Pattern, bit 1 live Pad, bit 2 PCM16LE) |
| 32 | 36 | Source Project ID |
| 68 | 36 | Source Pattern ID |
| 104 | 8 | Source Project revision |
| 112 | 2 + 1 + 1 | BPM, bars, reserved `0` |
| 116 | 4 | PPQ, exactly `960` |
| 120 | 4 | Loop length ticks, exactly `bars * 4 * PPQ` |
| 124 | 4 | Pad count |
| 128 | 4 | Event count |
| 132 | 4 | Unique sample count |

Immediately follow `pad_count` 20-byte Pad records, then `event_count` 12-byte
event records, then `sample_count` variable sample records. All input bytes must
be consumed exactly. Do not use an unchecked count to allocate or seek.

Each Pad record:

| Bytes | Field |
| --- | --- |
| 1 + 1 | Bank `0..3`, Pad `0..15` |
| 1 | Trigger mode: `0` one-shot, `1` gate, `2` loop-gate, `3` loop-toggle |
| 1 | Muted: exactly `0` or `1` |
| 4 | Sample index |
| 4 + 4 | Start frame (inclusive), End frame (exclusive) in prepared PCM |
| 4 | Finite linear gain in `[0, 2]`; negative zero is non-canonical |

Pads are strictly ordered by `(bank, pad)`, with no duplicate Slot. Playback
requires `start < end <= sample.frame_count`. The gain envelope includes the
existing authoring range (up to +6 dB) without changing desktop gain semantics.

Each event record:

| Bytes | Field |
| --- | --- |
| 1 + 1 + 1 + 1 | Bank, Pad, velocity `1..127`, reserved `0` |
| 4 + 4 | Onset tick, duration tick |

Each event's Slot must exist in the Pad table. Event keys `(onset_tick, bank,
pad)` are strictly increasing. Duration is positive, onset is less than the
loop length, and duration does not exceed `loop_length - onset`. BPM is
`40..240`, bars is one of `1, 2, 4, 8`; PPQ and loop length obey the header rule.
Zero events and zero Pads are representable (a silent Pattern); they do not
turn an empty or incomplete byte input into valid content.

Each sample record has an 8-byte body length, a 32-byte raw SHA-256 digest of
that body, then exactly that many body bytes. A body is:

| Bytes | Field |
| --- | --- |
| 4 + 2 + 2 + 4 | Sample rate `48000`, channels `1` or `2`, reserved `0`, positive frame count |
| `frames * channels * 2` | Interleaved signed PCM16LE |

Body length must equal `12 + frames * channels * 2`. SHA-256 includes all 12
descriptor bytes and the PCM, so an interpretation change changes identity.
The decoded Pad's derived `ArtifactRef` uses this body identity and media type
`application/vnd.lmdj.runtime-pcm16le`; it is not the original WAV Artifact.

Samples are deduplicated by complete body identity, ordered by first use in the
canonical Pad table. The first newly referenced index must be `0`, then `1`,
and so on. Every sample has a Pad user; duplicate sample identities and unused
sample records are invalid. Sample count therefore cannot exceed Pad count.
The reader shares the same immutable PCM owner across all references to an
index; it never deduplicates by a raw pointer or by PCM bytes without metadata.

## Bounds and failures

The caller explicitly supplies maximum encoded bytes, total unique decoded PCM
bytes, frames per sample, Pads and events. Zero is a zero allowance, **not** an
unlimited sentinel. The format admits at most 64 Pads/samples; event and frame
counts also fit the stated u32 fields. Caller limits may be tighter.

Input length/identity, count-derived table lengths, all sample body identities,
format, total PCM budget and playback closure must pass before allocating PCM
or producing a Snapshot. Checked arithmetic precedes every count-derived
allocation/advance. A larger integer in an attacker-controlled header is not
permission to allocate it. Exceptions at a public codec boundary return an
error with no value. The input span must remain valid and unchanged for the
duration of a call; the returned Snapshot owns its decoded data independently.

Encoder errors reject invalid/noncanonical Snapshot fields, mismatched event
PCM owners/content, unsupported PCM and explicit limits. It does not repair
input by dropping events, truncating PCM, changing playback or inventing Slots.
The Facade may sort a caller's extra live Slot selection, but duplicates or
unassigned Slots are rejected. Cook and export operate on a detached source
value and never persist the derived selection back into Project Truth.
The existing ProjectStore load still validates every source Asset, including
unselected material: export is not a recovery path for a corrupt Project.
Codec limits do not bound the earlier computer-side Project load/WAV Cook peak.

Decoder limits cover encoded bytes, PCM and bounded tables, **not** the whole
future device peak (input, PCM, float Bank, FX, Engine, stacks, DMA and SDK).
Device admission, transport trust and volatile command/lifecycle semantics are
separate T3–T5 work. A successful T2 read is not device `ready` or audio proof.

## Conformance and compatibility

- Retained canonical vector: `tests/fixtures/contracts/runtime-content-v1.hex`;
  its decoded metadata is `runtime-content-valid.json` in the same directory.
- C++ encoder/decoder: `packages/project-cooker/src/runtime_content.cpp`.
- Independent Python reader and malformed-wire vectors:
  `tests/conformance/runtime_content_contract_test.py`.
- A version, capability, digest, body length, count, Slot, timing, PCM, reserved
  field or trailing-byte mismatch fails closed; schema and binary tests cover
  separate obligations.

No existing Project/Bundle/Performance Contract is changed or migrated. No
retired Contract is read, translated or emitted. No Contract tag is created.
