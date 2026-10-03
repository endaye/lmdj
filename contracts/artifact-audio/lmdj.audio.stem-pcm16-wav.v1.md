---
contract_id: lmdj.audio.stem-pcm16-wav.v1
contract_version: 1.0.0
media_type: audio/wav
---

# Stem PCM16 WAV output profile

Capability `stem.split.v1` / `1.0.0` takes one `source_audio` following
[lmdj.audio.pcm16-wav.v1](lmdj.audio.pcm16-wav.v1.md), and returns exactly one
`drums`, `bass`, `vocals`, and `other` binding. Port names define roles; array
order and filenames do not. Every role is required even when silent. Different
roles may share one complete ArtifactRef; each binding is validated independently.

## Bytes, context and origin

Each output is canonical RIFF/WAVE PCM16: 44-byte header, a 16-byte PCM fmt chunk
at offset 12, then the data chunk at offset 36, with no additional metadata or
padding chunks. RIFF length, byte rate, block alignment and data length must
match the complete Artifact. The rate, channels and frame count equal the source
(44100/48000 Hz, mono/stereo, positive frame count). Frame zero is relative to
the first source frame; no timestamps or offsets are encoded. A WAV validator
proves this structural timeline, not acoustic alignment or separation quality.
The model adapter must separately prove that it did not shift or resample output.

SDK authenticates digest, byte length and media type before the consumer profile
validator runs. Missing, duplicate or unknown roles, malformed WAV, or one wrong
shape fail the entire Attempt; no partial Candidate becomes available.

## Float conversion

Interleaved float samples use unit gain for all four roles. Reject NaN and both
infinities. Multiply by 32768, round to nearest with ties to even, and reject a
rounded value outside [-32768,32767]. Encode the resulting signed integer in
little-endian order. Do not normalize per role, clip, shift or silently repair
invalid samples. The decision is based on the rounded value: a finite value
slightly below -1 may round to -32768; +1 rounds to 32768 and is rejected.
Rounding must not depend on the host floating-point rounding mode.

## Parameters, determinism and failures

Parameters follow [lmdj.stem-parameters.v1](../stem/lmdj.stem-parameters.v1.schema.json):
only an empty object. No gain, role subset or model-switch parameters are admitted.
The Capability declares nondeterministic from its first version. A repeatable
Proof does not imply a real model's byte determinism.

Typed Provider errors use INVALID_ARGUMENT / stem_parameters_invalid,
UNSUPPORTED_AUDIO / source_audio_unsupported, and PROVIDER_FAILED with reasons
stem_execution_failed, stem_output_nonfinite, stem_output_out_of_range, or
stem_output_shape_invalid. SDK custody, quotas, malformed candidate bindings
and output validator failures retain SDK-owned Attempt errors.

## Identity and execution boundary

The first implementation is local.proof.stem, a pure-code replay Proof with
model_identity null and an authenticated source-package digest. It is not a
trained model or an instrument separator. Its test-only descriptor declares
CPU, 256 MiB and a 1000 ms advisory timeout; its codec bounds a single WAV at
16777216 bytes and its logical output maximum is four times that bound.
ExecutionOptions impose their own aggregate input/output/staging budgets.
These numbers do not prove an enforced deadline or process-tree RSS bound.

A real model adapter records its own Provider version, source-package digest,
model identity and actual weight digest in Attempt evidence; fixed weights and
isolation/resource qualification belong to E1. No guessed model identity or
unmeasured weights are substituted for null. No production platform, default
selection, Facade adoption, or release is established by this Proof.
