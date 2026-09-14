# Runtime voice scan budget (#1176)

## Scope and evidence

R2 retained a real target CPU-margin failure. The target render disassembly
shows two per-frame loops scanning all 128 Voice slots, including idle slots:
65,536 slot visits per 256-frame block. This is a bounded-work observation,
not a measurement of the fraction of total CPU spent in those loops.

One Task changes only:

- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- this plan
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`

Maintain an audio-owned highest-active-slot-plus-one extent. Both admission
paths expand it; completion/cancellation trim inactive trailing slots; quiescent
start/stop reset it. Bound only the two per-frame scans. Preserve holes,
first-free admission, ascending mix order, all 128 voices, and existing ramps,
ownership, counters, overflow and queue semantics. Do not change fixtures,
sample rate, gains, thresholds, contracts, FX or Host wiring.

## Verification

Lowest-tier `audio.realtime_engine` checks high-slot survival after lower slots
finish, low-slot reuse, completion and restart, alongside existing full-capacity,
pattern, release, allocation and ownership tests. Rebuild affected consumers.
Use the same external release benchmark before/after with idle, low sparse,
high sparse and dense cases, exact PCM checks and telemetry; native timings are
diagnostics, not a CI threshold or Cardputer acceptance. Rerun the original R2
target workload after integration before claiming target CPU-margin recovery.
Run `scripts/docs-site.sh check` for the updated source fact.

## Version Management

The added private field changes Engine C++ layout; all binary consumers must
rebuild together. Audio Runtime MAJOR allocation and Product Build/immutable
snapshot remain staged for B1, together with M1/M2. No identity is allocated
here; this source cannot replace an old-ABI binary.

Documentation impact: required — `/core/modules/audio-runtime`.
