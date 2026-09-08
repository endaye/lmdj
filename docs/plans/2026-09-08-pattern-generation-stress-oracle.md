# Pattern stress: compare identities with the accepted receipt

## Scope

Independent test-only follow-up to the runtime synchronization Task. Step A's
host rerun reached the final Pattern identity assertion with accepted/applied
counts conserved, but the test compared generation with the number accepted.
Allocation occurs before a publication CAS or past-frame rejection, so valid
generation gaps are not lost publications. Keep the exact external identity
check and all existing conservation, pending, rejection and supersession checks.

Declared files:

- `tests/core/audio/snapshot_publication_stress_test.cpp`
- This plan.

No product source, synchronization algorithm, threshold, timeout, test target,
owned lane or acceptance-journey leg changes. This is not part of docs-only
Step A.

## Reproduction and change

1. Advance one callback, then reject a requested activation in the past through
   the public API. Assert that rejection explicitly; it consumes an allocation
   but cannot count as an accepted or applied publication.
2. Keep the existing 40-publication concurrent journey and all four observers.
   The old generation-equals-accepted-count oracle now fails deterministically.
3. Record each accepted publication's full generation receipt. Assert the final
   current generation equals that exact last accepted receipt, and separately
   assert the fixture produced a generation/count gap. Count exactly the one
   deliberately rejected request, without allowing other rejections.

## Verification

Lowest tier: the existing `audio.snapshot_publication_stress` target, because
the affected oracle belongs to its complete concurrent journey. Capture the
deterministic red result before correcting the oracle, then run all four audio
stress tests in dev and TSan. Run diff/ownership and PR declaration checks.
This adds no new gate or target; it fixes the reason an existing gate fails.

## Version Management

Version impact: none — tests and explanatory plan only; product binaries,
public interfaces, contracts, assembly and Build allocation do not change.

## Documentation Impact

Documentation impact: none — no Portal page, diagram, projected identity or
documented product fact changes; the existing design already defines full,
non-reused identities rather than a contiguous publication count.

Pitfall impact: none — the erroneous test oracle is derivable from the product
allocation path and is expressed by the deterministic rejection/gap regression.

## Results

- Deterministic red: with the rejected-request fixture and the old oracle,
  `audio.snapshot_publication_stress` failed at
  `telemetry.current_generation == accepted`; the preceding accepted/applied
  conservation assertions passed.
- `cmake --preset dev` and `cmake --preset tsan`: PASS.
- For each preset, `cmake --build build/core/<preset> -j 6 --target
  lmdj_snapshot_publication_stress_tests lmdj_realtime_engine_stress_tests
  lmdj_long_sample_publication_stress_tests lmdj_master_fx_stress_tests`: PASS.
- For both CTest commands below, the exact selection was
  `-R '^audio\.(realtime_spsc_stress|snapshot_publication_stress|long_sample_publication_stress|master_fx_stress)$'`.
- `ctest --test-dir build/core/dev --output-on-failure` with that selection:
  4/4 PASS (7.69 seconds).
- `ctest --test-dir build/core/tsan --output-on-failure` with that selection:
  4/4 PASS (34.17 seconds), no reported sanitizer findings.
- This is host concurrency evidence only; no ESP32 execution, audio output,
  callback deadline, jitter, underrun or voice-capacity evidence is claimed.
