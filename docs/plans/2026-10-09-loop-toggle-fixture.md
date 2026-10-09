# Loop-toggle exact mixing fixture

## Premises and scope

Integration and Task base: `502932e345b621abc5533431e61adf0d0253a189`,
refreshed on 2026-10-09. The complete GNU13 ARM64 Release Core run on the
monitor-output Task failed `audio.realtime_engine` at the loop-toggle mixed
sample assertion. A fresh clean main build independently reproduced line 1515.
No successor in the live loop-toggle PR search repaired this fixture; the last
changes to this source were #1802, #1780 and #1717, and current main retains
the decimal samples and the incorrect named-temporary rounding explanation.

An independent reviewer inspected both built binaries: the engine uses an
`fmadd` accumulation; at the failed comparison expected PCM bits are
`0x3bccccce`, while actual PCM bits are `0x3bcccccd`, on both main and the
monitor producer. Independent separate/fused arithmetic reproduces these
values. Named local floats are not contraction barriers. This is an existing
test-fixture defect, not evidence of a monitor-output regression.

Use power-of-two samples in this one case so scaling the already represented
ramp adds no multiplication rounding. Keep the strict sample equalities,
two-voice latch/toggle behavior, complete 96-frame release tail, cancellation
count and all voice receipts. Change no engine behavior, tolerance, compiler
flag, test deadline, lane selection or coverage floor.

## Task and declared files

One Conventional Commit, `test(audio): make loop-toggle fixture contraction independent`.

- `tests/core/audio/realtime_engine_test.cpp`
- This plan.

First/second samples become `{0.125F, 0.25F}` / `{0.25F, 0.5F}`. Update the
three expected sample constants and replace the false rounding explanation.
The exact mixed expected value is `0x3c000000` with either separate or fused
arithmetic. Retain every existing journey leg and assertion.

## Verification

The lowest-tier regression instrument is the actual Release
`lmdj_realtime_engine_tests` target, configured with GNU13 on ARM64 and run
through the existing `audio.realtime_engine` CTest registration. The baseline
red result above is retained; rebuild the modified translation unit, inspect
the compile and terminal result, then run the original registration unchanged.
Run the equivalent existing target with Apple Clang to check the original
working platform. Run ownership after staging this new plan, inspect the
complete staged diff and file list, refresh main premises before commit, and
classify the committed range. Selected batch-only evidence and independent
current-head review remain required before integration. A passing target does
not discharge the monitor Task's failed full lanes or the broad UI Goal.

Precommit refresh still resolves main to the base above; no successor changed
this fixture. GNU13 ARM64 Release rebuilt the modified test translation unit
and passed the unchanged `audio.realtime_engine` registration (0.53 s).
Apple Clang Release configured a fresh Task build, compiled the same target
and passed the unchanged registration (0.64 s). Both commands returned zero.
The original main and producer red transcripts remain retained separately.

## Version Management

Version impact: none — this changes a test fixture and its explanation only;
product, Module, Host, Provider and persisted Contract behavior is unchanged.

## Documentation Impact

Documentation impact: none — no Architecture Portal page, diagram, identity or
documented product behavior changes.

## Pitfall disposition

The defect is expressed completely by the existing strict regression and its
portable fixture. It requires no process pitfall entry. Rebuild provenance and
unverified-lane boundaries follow `issue-done`; neither source restoration nor
named gaps count as passing evidence.
