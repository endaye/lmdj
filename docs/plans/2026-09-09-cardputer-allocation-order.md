# Runtime Facade fixed-allocation ordering

Date: 2026-09-09. Baseline: `60567f822971631f9669b1755939e70b418fcb69`.
User approved the next allocation repair and same-device I2S retest after the
[contiguous-allocation refusal](../research/2026-09-09-cardputer-i2s-probe.md).

## Task and declared files

One Task: after complete content inspection and budget admission, construct the
candidate Engine (including its selected Voice-state queue) before decoding
PCM or preparing sample/pattern storage. Keep ownership local until every
preparation and identity copy succeeds; unwind all candidates on failure.
This tests the smallest allocation-order repair before considering a storage
redesign. It does not guarantee success on every fragmented heap.

- `packages/application-facade/src/runtime_facade.cpp`
- `tests/core/facade/runtime_facade_test.cpp`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `docs/plans/2026-09-09-cardputer-allocation-order.md`
- `docs/research/2026-09-09-cardputer-allocation-order.md`

No queue algorithm/capacity, public API/ABI, admission arithmetic, platform
reserve, audio-thread work, Project/Contract or Product Assembly changes.
Keep the same 5008-byte 50 ms tone, 32768-byte reserve, 24576-byte main stack,
8192-byte audio task and 6144-byte I2S DMA ring. Preserve prior sealed evidence
and original device Flash backup; new prototype/evidence stays external.

## Verification

Lowest tier: Facade component allocation observer proves both fixed allocations
precede the fixture's PCM allocation. Rebuild and run this assertion against
the exact old implementation first; retain the red result. Existing exhaustive
allocation-site failures must still leave empty/no identity/silent state and
allow load/start/render retry. Run Runtime content, Facade and Engine component
regressions, plus Facade stress; ASan covers changed candidate lifetimes.
No new global gate or reduced assertion, test budget or lane ownership.

Reconfirm the old board refusal with source/image identity. Build the new
external image using EIM v6.1, all producer sources and strict flags; bind the
baseline plus exact product diff. Verify same device, recoverable original
Flash and current image ranges before any flash. Preserve failed attempts.
Two resets must exercise the complete previous I2S journey: load/ready, start,
four submitted pulses with exact receipts/nonzero PCM and successful DMA
writes, stop/drain/silent Core blocks/zero DMA tail, disable/mute/unload,
bad-identity rejection with empty/silent state, reload and repeat. Keep driver
errors, measured deadlines and heap/stack outcomes distinct from hearing.
Human hearing remains pending until the user actually hears this image.

Run dependency/active-tree/version, staged new-file ownership, portal check,
final committed scope classification and exact-head review before shipping.
No cleanup, release, new version allocation or production deployment.

## Version Management

Version impact: none for this unreleased internal allocation-order repair.
Public API/ABI, wire format and Module/Contract/Product identities are unchanged;
no Package distribution, Product Build, tag or Channel is allocated here.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/
Reason: document fixed-before-variable candidate allocation and retain the
distinction between aggregate admission and contiguous platform allocation.
The boundary/ownership diagram is unchanged; no new component or flow edge.

## Completion evidence

The [same-device report](../research/2026-09-09-cardputer-allocation-order.md)
records the reproduced refusal, old-code red allocation-order assertion,
minimal fixed-first repair, dev 4/4 and ASan 2/2 PASS, and two complete
70-check I2S journeys. All previous capacities, fixture bytes, stacks, DMA
geometry and reserve remain unchanged. Sixteen negative transcript controls
reject incomplete journeys. Hearing/analog acceptance remains pending;
the observed processing margin is only about 261 µs for this one-voice tone.
No Product Build, Release, supported Host or normal material capacity is claimed.
