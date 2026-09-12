# Cardputer Pad feedback before LCD integration

Parent: #1104; input/display requirement: #1108, design §6.

The existing input projection marks a Pad active when submit returns accepted,
before audio processing produces a receipt, and keeps that flag across stop.
Physical LCD integration would expose both incorrect states. This Task fixes
the projection first; LCD output and final instrumented A1 remain subsequent
work in the same umbrella.

## Declared files

- `apps/cardputer-host/main/runtime_host.hpp`
- `apps/cardputer-host/main/runtime_host.cpp`
- `apps/cardputer-host/main/input_controller.hpp`
- `apps/cardputer-host/main/input_controller.cpp`
- `tests/platform/cardputer/input_controller_test.cpp`
- `tests/platform/cardputer/pad_feedback_interleaving_test.cpp`
- `tests/platform/cardputer/CMakeLists.txt`
- `apps/docs-site/docs/platform/input.mdx`
- `docs/plans/2026-09-12-cardputer-pad-feedback.md`

## Implementation

The serialized Host correlates every admitted Pad press/release sequence with
actual current-epoch receipts. Only voice_started lights press feedback;
release, refusal and lifecycle transitions clear it. This is acknowledged
local Pad input, not an estimate of all sounding voices or audible tail length.
The projection consumes HostStatus. A one-byte-per-credit table is allocated
at Host construction (128 payload bytes for the current profile); no render
allocation or new audio-thread synchronization is introduced. Its memory is
part of the Host cost to measure with the completed candidate.

Review follow-up: the per-Pad latest-sequence implementation could overwrite
an older press while its completed render was publishing a receipt. A boundary
double reproduces this ordering while keeping receipts strictly FIFO; its
regression failed on the reviewed source with exit 8 in
`/tmp/cardputer-feedback-interleaving-red.log`. The table now retains every
outstanding command until polling returns its credit. The review's separate
out-of-order-receipt premise is not supported by RuntimeFacade::poll, which
retires pending commands from the front in sequence order.

Follow-up verification: native and ASan/UBSan each 43/43 passed (42 component,
one existing stress), including credit-table wrap/queue-full retry and the
interleaving regression. EIM firmware build and full portal check exited 0.
Logs use `/tmp/cardputer-feedback-v2-` prefixes; previous failed evidence is
retained. The Facade double only establishes the publication ordering at the
Host boundary; the original real-Core tests remain in both selections.

## Verification

Component tests exercise real RuntimeFacade with a controlled audio pump:
accepted-but-unprocessed input remains dark; processed press lights feedback;
stop clears it; a new run cannot inherit old feedback. Existing keyboard,
queue-full retry and audio lifecycle tests remain required. Run native and
ASan component selections, the pinned EIM firmware build, scope ownership,
and the portal check. Preserve initial regression failures.

Development evidence: the original implementation failed all three initial
receipt/stop/restart regressions (CTest exit 8), recorded in
`/tmp/cardputer-pad-feedback-red-tests.log`. After correction, native and
ASan/UBSan selections each passed 41/41 (40 component, one existing threaded
stress). The added fourth case checks that release feedback also waits for
processing. The pinned EIM ESP-IDF firmware build completed with exit 0;
no firmware was flashed. The controlled pump omits real keyboard scanning,
I2S DMA, LCD I/O and physical output timing; it proves receipt projection only.

Physical LCD, acoustics, 1000-trigger latency, combined 30-minute load and
100 load/play/stop/unload cycles remain A1 requirements, to be performed on
the complete immutable candidate after missing development is complete.

## Version Management

Version impact: no allocation in this source correction. Host version and a
fresh Product Build/immutable snapshot are allocated with the completed B1
candidate before formal A1. No existing snapshot is rewritten.

## Documentation Impact

Documentation impact: required — `/platform/input/` explains the exact
acknowledged-feedback semantics and preserves the pending physical LCD gap.
