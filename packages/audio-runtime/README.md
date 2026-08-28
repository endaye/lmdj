# Audio Runtime

`audio-runtime` turns immutable Runtime Snapshots into prepared sample and
Pattern views, then renders them through the offline or realtime engine. It
does not mutate Project Truth and does not parse Project bundles on the audio
thread.

## Prepared sample storage

`PreparedSampleBank` owns 64 independent `std::vector<float>` values, one for
each Pad Slot. Empty Pads retain empty vectors, and populated Pads may have
different lengths. This existing per-slot layout is the variable-length
storage required by the long-material model; there is no shared PCM arena or
offset table.

Prepared PCM is 48 kHz mono float. Quota values are supplied by the Host in
`RuntimePreparationLimits`: each 16-Pad user Bank and the complete 64-Pad
generation have separate byte limits. Trim and loop points select playback
ranges but do not reduce prepared residency.

## Realtime publication

The control thread prepares an immutable Bank and publishes it through the
fixed SPSC hand-off. The audio thread applies pending Banks, keeps retiring
Banks alive while their Voices still reference them, and marks them
reclaimable only after the final Voice releases its reference. Reclamation and
destruction remain on the control thread, so `render` does not allocate, free,
lock, block, or throw.

Publication owners account live, pending, and retiring prepared bytes in
reclaim -> reserve -> publish order. `maximum_resident_bytes` is transient
publication backpressure, distinct from the deterministic user-Bank and
generation quotas.

Realtime sample positions use the same unsigned 32-bit frame domain as
resolved playback and Voice-state events. `kRealtimeMaximumSampleFrames`
publishes that domain boundary; the approved 16,777,216-frame single-Pad case
fits without an intermediate narrowing conversion.

## Verification

- `audio.realtime_engine` covers trim, loop, ramp, completion, and release
  arithmetic at the approved 16,777,216-frame Pad boundary.
- `audio.long_sample_publication_stress` publishes and retires a 64 MiB
  single-Pad Bank and 128 MiB generations under concurrent rendering, reaches
  the exact 256 MiB residency boundary, and checks byte-exact reclaim.
- The long-sample concurrency test is in the `stress` tier and is excluded
  from the coverage preset because its renderer intentionally busy-spins.
