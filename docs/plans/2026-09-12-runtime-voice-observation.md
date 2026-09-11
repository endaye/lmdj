# Actual voice overlap observation

Relates to #1104. D1 section 3 requires the actual peak simultaneous voice
count for Pattern plus local Pad playback. Queue admission and an end-of-block
active count cannot prove this: short voices can overlap and finish in one block.

## Implementation scope

Declared files: `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`,
`packages/audio-runtime/src/realtime_engine.cpp`,
`packages/application-facade/include/lmdj/facade/runtime_facade.hpp`,
`packages/application-facade/src/runtime_facade.cpp`,
`tests/core/facade/runtime_facade_test.cpp`,
`tests/core/facade/runtime_facade_stress_test.cpp`, and this plan. The latter
uses the existing deterministic pause seam and stress scenarios to verify
unavailable reads before the stop barrier and capacity-refused triggers.
The Task also owns current portal pages
`apps/docs-site/docs/core/modules/audio-runtime.mdx` and
`apps/docs-site/docs/core/modules/application-facade.mdx`; the existing module
ownership/data-flow boundary does not change, so no diagram edges are added.

Track an audio-owned high-water count at both real voice activation sites.
Reset it at successful engine start, retain it through stop. Expose it to the
narrow Facade only after its existing callback gate has drained and phase is
stopped. Empty, ready, running and draining return unavailable, not zero.
No polling of mutable audio state from another thread, no new atomics or
changes to command/receipt concurrency. This is voice allocation overlap,
not an assertion about nonzero PCM, audible loudness or physical latency.

The Host must later copy the stopped value into its identity-bound observation
before unload. Host/wire integration is not implemented by this source draft.

## Verification

Tests must prove four short voices overlap within one render block even when
none remain at block end; rejected/muted triggers do not inflate counts;
Pattern plus local Pads are both counted; stop retains and restart resets;
running/draining/unloaded queries are unavailable. Query/render must allocate
nothing. Run native, ASan and relevant concurrency/stress coverage before
shipping; retain the existing 128-voice capacity and timing/coverage floors.

Development verification: native Facade/component/quiescence/stress 3/3;
ASan/UBSan same 3/3; TSan quiescence/stress 2/2, all exit 0. The paused callback
test observes unavailable results both while running and while draining before
release, then peak one after the real stop barrier. The 1024-pending stress
case retains peak 128 despite refused triggers. EIM compile/link exits 0.
Logs are `/tmp/runtime-voice-observation-native-tests.log`, `-asan-tests.log`,
`-tsan-tests.log` and `-eim-build.log`. These are source-development results,
not physical overlap/latency or final resource-profile acceptance.

## Version Management

Version impact: additive source API; module version allocation is deferred to
the subsequent integrated Build Task, as with the existing typed Runtime
Content export source capability documented on the Facade page. This source
Task does not publish a Package, modify manifests/Assembly identity, or allocate
a Product Build. Before distributing the new capability, the version Task must
bind the reviewed module/API versions, dependent pins and immutable snapshot.
No partially updated version inventories or mutated frozen snapshots are used.

ABI investigation on the two local compilers: AppleClang arm64 record-layout
diff adds only the new counter at offset 51332, in existing padding between
active voices and cancelled voices; size 53248/alignment 64 remain unchanged.
EIM Xtensa GCC class dumps retain size 42304/alignment 64 and base size 42252.
Logs: `/tmp/runtime-voice-layout-{base,new}.log` and
`/tmp/runtime-voice-layout-xtensa-{base,new}.log`. These are local target
observations, not universal ABI compatibility or an allocated version.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/audio-runtime/ /core/modules/application-facade/
Reason: new stopped-only observation semantics and its limits. Portal checks
remain required before committing; versioned distribution remains deferred.
