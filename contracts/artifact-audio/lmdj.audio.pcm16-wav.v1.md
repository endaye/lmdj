---
contract_id: lmdj.audio.pcm16-wav.v1
contract_version: 1.0.0
media_type: audio/wav
---

# PCM16 WAV Artifact profile

This binary profile defines the source_audio port of sample.slice.v1.
It is not a JSON Schema that validates audio bytes. Authority: the
[confirmed R1 decision](../../docs/prd/decisions/2026-09-09-stage12-contract-candidate.md).

## Byte structure

- RIFF/WAVE, little-endian PCM format code 1, signed 16-bit samples.
- Exactly one fmt chunk and one data chunk; mono or stereo; 44100 or 48000 Hz.
- block_align equals channels times 2; byte_rate equals frame_rate times
  block_align. data size is nonzero and divisible by block_align.
- RIFF declared size plus 8 equals the complete Artifact byte_length. All
  chunk headers, declared data and odd-length pad bytes fit within that boundary.
- fmt payload length is 16, or at least 18 with uint16 cbSize equal to payload
  length minus 18. Extensions do not change PCM interpretation.
- Traverse chunks and their padding; skip well-formed unknown chunks. Do not
  assume a fixed 44-byte header. Reject duplicate fmt/data, truncated structures,
  missing padding, RF64, extensible/compressed/float formats and zero-frame audio.

## Binding, ownership and limits

ArtifactRef binds SHA-256, byte_length and audio/wav media type. SDK custody
verification precedes Provider execution; the consumer owns WAV decoding/profile
validation. This profile grants no Project, bundle, Workspace or filesystem access.

The Slice reference request permits 16777216 aggregate input bytes; that is an
execution budget, not a different WAV encoding. SDK-owned copies and retained
handles keep their shared budget lease until released. Host policy may impose
lower limits. These controls do not prove a process-wide RSS or hard timeout cap.

Invalid audio is UNSUPPORTED_AUDIO / source_audio_unsupported. Unavailable,
corrupt, over-budget or unauthorized Artifact access is owned by SDK and follows
the approved R1 failure table; it cannot be fabricated as a Provider domain error.

## Adoption and implementation status

Slice outputs describe original-rate onset frames, not processed WAV bytes.
The output consumer validates source hash/rate/context. Core recipes may later
materialize selected intervals into independent Derived Assets after explicit
user selection and targets. The profile does not itself authorize adoption.

K1 defines this profile and the associated Contracts. Production byte validation,
malformed-WAV execution tests and Provider replay are K2/K3 obligations;
Host owner wiring and adoption remain later Tasks.
