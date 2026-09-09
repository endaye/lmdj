# Runtime Facade receipt-bounded Voice-state storage

Date: 2026-09-09. User approved the 2176-entry Runtime Facade profile after
the [Cardputer resource refusal](../research/2026-09-09-cardputer-runtime-resource-probe.md).
Source baseline: `bb99f11982450f77ca7f2309776197482690cfa8`.

## Scope and capacity argument

One Task: retain the complete Voice-state stream, but allocate its storage
outside Engine at construction. Default Engine retains 10240 entries. Only
Runtime Facade selects the receipt-bounded 2176-entry profile. Control capacity
1024, trigger outcomes 4096, Voices 128, Capture and all public event fields,
FIFO, overflow corruption and fail-closed behavior remain unchanged.

The bound is `2 * kRealtimeQueueCapacity + kRealtimeVoiceCapacity`:

1. A host-input voice publishes one started edge and at most one terminal
   edge. A release tail does not publish a second terminal edge. A stop command
   can terminate several voices, but those edges belong to those voices, not
   extra starts. Pattern/replay/audition voices do not enter this stream.
2. Runtime Facade retains each accepted command's pending slot until its
   receipt is returned, even after audio consumption. At most 1024 commands
   can therefore contribute at most 2048 new edges without receipt retirement.
3. `poll` acquire-loads consumed before draining Voice states, and only then
   retires receipts. The consumed release follows render, including its state
   publications. Started edges of retired commands have therefore been drained.
   At most 128 already-started voices can subsequently publish terminal edges.
   This also covers partial/empty receipt spans and a callback racing poll.
4. Stop closes and drains callback admission, drains events, and only then
   stops Engine. Restart clears queues only under quiescence. No receipt slot
   becomes reusable before the drain in either running or stopped paths.

The profile is opt-in, fixed for an Engine's lifetime, and documents the
caller's receipt-retirement obligation. It is not a general smaller desktop
default, per-board macro, dropped stream, narrower field or silent eviction.
Both alternatives reuse the unchanged fixed SPSC algorithm and compact cell.
Construction may allocate/throw; render/drain never allocate, free or lock.
Facade load budgets both the small Engine object and its separately allocated
queue before preparing content; allocation failure remains empty/silent and
retryable. Allocation is not moved to start or the audio callback.

## Declared files

- `docs/plans/2026-09-09-runtime-facade-voice-budget.md`
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/application-facade/src/runtime_facade.cpp`
- `tests/core/audio/fixed_spsc_queue_test.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- `tests/core/audio/realtime_engine_stress_test.cpp`
- `tests/core/facade/runtime_facade_test.cpp`
- `tests/core/facade/runtime_facade_stress_test.cpp`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/diagrams/audio-runtime.architecture.json`
- `apps/docs-site/diagrams/application-facade.architecture.json`
- `apps/docs-site/static/diagrams/audio-runtime.html`
- `apps/docs-site/static/diagrams/audio-runtime.svg`
- `apps/docs-site/static/diagrams/application-facade.html`
- `apps/docs-site/static/diagrams/application-facade.svg`

Independent diagnostic firmware/evidence stays outside the repository; no
Host/Assembly, I2S, UI, transport, product release or cleanup is included.
Do not overwrite the previous probe or original device Flash backup.

## Verification

Lowest tiers: unit exact-capacity/FIFO/full-width/wrap/clear tests for both
storage alternatives; component footprint and allocation-site failure sweeps,
full 1024-command backpressure/retry/partial receipts, 128 existing voices
ending across receipt retirement, short-voice repeated batches, and default
Engine overflow/capture regression. The footprint red control must fail on the
original large Engine before implementation, after an actual rebuild.

Stress: both storage alternatives transfer full-width events concurrently;
actual Runtime Facade races render against max-pending submission and partial
poll, retains full sequence/epoch/outcome conservation, and keeps existing
stop/unload/reset journeys. Run applicable audio and Facade tests in dev,
ASan and TSan, explicitly including stress. No tests, budgets or floors shrink.
Run dependency/active-tree/version, staged ownership and portal checks.
No new global required gate; new tests catch profile-selection, unaccounted
queue allocation, lost/reordered events, premature receipt retirement and
changed fail-closed behavior.

After native checks, fresh EIM target build measures Engine and both queue
sizes, verifies exact product inputs/flags/roots and retains ELF hashes. The
same Cardputer gets the bounded diagnostic image only after verifying the
retained original Flash backup and exact device identity. Two independent
resets must prove load/start/commands/receipts/stop/unload/failed-load/retry/
reload with complete identity and far-side silence/nonzero software PCM.
This remains a resource/lifecycle probe, not audio-driver or hearing acceptance.
If admission still fails, retain the refusal and do not reduce reserve/capacity.

## Version Management

Version impact: staged Module MAJOR ABI impact for Audio Runtime's Engine
layout and construction; the opt-in buffering constructor is additive at source
level. Runtime Facade's public API and Contract wire are unchanged. As in the
prior storage Tasks, no Package/Module tag, Product Build or Assembly identity
is allocated here. Before distributing a Package/Build, coherently rebuild and
version all binary consumers, lock the Assembly, and freeze its Portal snapshot.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/audio-runtime/ /core/modules/application-facade/
Reason: distinguish default and receipt-bounded buffering, lifetime allocation,
the capacity proof, complete resource accounting and verification limitations.

## Completion evidence

### Native and source verification

- Fresh baseline queue/Facade component tests: 2/2 PASS. The original Engine
  fails the new out-of-line footprint assertion after an actual rebuild.
- Final relevant dev selection `^(audio\.|facade\.runtime_facade)`: 18/18
  PASS, including all five selected stress registrations. ASan and TSan each
  pass nine Engine/queue/Facade/component/stress tests; no startup-only PASS.
- The actual Facade boundary fixture reaches 2176 unread states. Temporarily
  selecting 2175 and rebuilding makes its post-poll retry lose nonzero PCM;
  restoring 2176 and rebuilding passes. Both exact-capacity storage tests,
  three million full-width SPSC transfers (tiny, default, bounded), and 32768
  concurrent Facade command receipts retain their complete assertions.
- Existing allocation-site sweeps include the new queue allocation. A separate
  component refuses allocations as large as the default queue and proves
  Runtime Facade still loads; fixed-byte accounting includes bounded storage.
- Dependency, active-tree and version checks PASS. Portal check: 114 tests,
  44 current pages, 10 source diagrams/20 outputs, 44 routes/internal links PASS.
- Additional full `scripts/core.sh build dev` stops in the unchanged
  `tests/core/provider/artifact_source_test.cpp:12`: `OldProvider::run` hides
  the `Provider::run(ProviderRunContext)` overload under AppleClang
  `-Werror,-Woverloaded-virtual`. Both involved files equal the baseline;
  the scoped targets above build and run independently. This is retained as
  a full-build failure, not waived into a full-CI/coverage PASS or fixed here.
  Initial sanitizer command lines also named nonexistent test targets;
  corrected CMake target names built successfully before the reported runs.

### Target and Cardputer verification

External evidence: `/Users/endaye/esp/lmdj-spike/receipt-voice-budget.6p8zAk/`.
EIM IDF v6.1 revision `fff9895c82d744c7237be8847347bdd1b07c6643`, Xtensa GCC
15.2.0 (`esp-15.2.0_20251204`). A fresh complete 18-source build retains 17
Facade API roots and strict effective gnu++20 / Wall / Wextra / Wpedantic /
Werror, with no Wno escape. All 84 tracked files in the five producer trees
are hash-bound to baseline plus the exact two-product-file overlay, not
misreported as an unmodified baseline image. Overlay SHA-256:
`b1e2ab7c859e365048acb4fab2ead3a23240fecba54de24e4ef17c15a11f369c`.
ELF SHA-256:
`36c97e0d90bbc320acdaa45d2a8ee9e09c7a54118634f0b10d24ae6aa6968b2b`.

| Target quantity | Before | After (bytes) |
| --- | ---: | ---: |
| Engine object | 446976 | 201024 |
| Default Voice-state queue payload/allocation | 245952 embedded | 245952 separate |
| Runtime Facade selected Voice-state allocation | included above | 52416 |
| Facade fixed model including its selected queue | 455396 | 261860 |
| Saved total fixed model | — | **193536 (189 KiB)** |

The default Engine total stays 446976 bytes before allocator overhead; moving
storage alone is not a desktop memory saving. On the same Cardputer, original
8-MB Flash backup SHA-256 was rechecked, and all three current diagnostic image
ranges matched the preceding probe before replacement. `idf.py flash` wrote
only generated bootloader/partition/app ranges and verified their hashes.
Original firmware remains backed up, not restored; no eFuse/SD/erase-all action.

Two independent device resets print the matching ELF and overlay digests,
and each passes all **41** ordered assertions: complete 248-byte golden identity;
ready/start/stale-epoch refusal; queued-but-not-premature receipt; nonzero
software PCM and exact voice-started receipt; pending command cancellation;
drain/stop/silence/unload/no identity; malformed identity rejection followed by
successful retry of the full journey; reload/start/reset/empty/silence.

Both runs: entry free 351672, largest block 286720, PSRAM 0; aligned raw Engine
allocation 201024 succeeds. Budget = fixed 261860 + encoded 248 + PCM 8 + float
32 + metadata 907 + workspace 2248 + unchanged provisional reserve 32768 =
**298071 bytes**, below the measured 351672 cap. After first successful load,
free heap is **88292 bytes**, largest block **34816 bytes**. Sampled heap minimum
is 88076 and integrity is 1 at every sample. These figures describe the tiny
fixture, not a normal material capacity or a final DMA/platform reservation.

Of the unchanged 24576-byte main stack, observed minimum remaining is 14012
in run 1 and 13884 in run 2 (used 10564/10692). The first comparison checker
rejected nonidentical stack measurements; the revised report preserves both
runs separately and all 41 assertions, rather than claiming identical readings.
Eight negative controls reject missing completion/cancellation, failed stop
silence and wrong input byte length. Post-Facade free heap is 351604, 68 below
entry while the probe deliberately retains a prior Host epoch; this is not
a zero-leak claim. No I2S/DMA, actual sound, callback deadline/jitter/underrun,
transport, full Host or Product Assembly acceptance was performed.

Sealed `probe-evidence.tar.gz`: 83 files, 10403615 bytes, SHA-256
`30ef4ea9db6a426082b675f0d1b540830a9aec8bbce84c2de9ad72fbaa77f44d`.
Every archived file was checked against its digest/length inventory. The archive
includes the source overlay, source inventory, SDK/config/ELF/map, raw device
journeys and negative controls; it excludes the original Flash and private
device-identity/flash/reset logs. All evidence remains local, with no upload.

Staged ownership and final exact-head review/shipping evidence are recorded
with the Task commit/PR. No qualifying new process pitfall: the product capacity
and accounting invariants are expressed by the regression tests above.
