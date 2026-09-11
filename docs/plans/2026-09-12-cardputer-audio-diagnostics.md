# Cardputer audio service diagnostics

Relates to #1104, #1107 and #1111. This is development before the user-requested
joint device tests, not a capacity or physical-acceptance result.

## Declared files

- `apps/cardputer-host/main/audio_diagnostics.hpp`
- `apps/cardputer-host/main/audio_driver.hpp`
- `apps/cardputer-host/main/audio_driver.cpp`
- `apps/cardputer-host/main/runtime_host.hpp`
- `apps/cardputer-host/main/runtime_host.cpp`
- `tests/platform/cardputer/audio_diagnostics_test.cpp`
- `tests/platform/cardputer/dma_deadline_test.cpp`
- `tests/platform/cardputer/fake_esp/esp_timer.h`
- `tests/platform/cardputer/CMakeLists.txt`
- `apps/docs-site/docs/hosts/cardputer-host.mdx`
- This plan.

## Implementation

The actual worker runs one shared, allocation-free measurement orchestration.
It separately measures DMA wait, delivered-EOF-to-worker wakeup, render,
conversion, driver submission and the combined service elapsed envelope.
The monotonic timer is ESP-IDF esp_timer in microseconds. An EOF timestamp
travels in the existing bounded queue, not via an unprotected shared value.

Each series retains the exact largest 512 integer-microsecond observations in
a min-heap. At n observations nearest-rank p99.9 is the (floor(n/1000)+1)th
largest. The statistic is therefore exact up to 511999 observations, covering
the required 337500-block, 30-minute window. At 512000 observations it becomes
explicitly unavailable, never approximate; count and maximum continue. An
over-wide duration or backward clock also makes its percentile unavailable.
Six retained tails cost 12288 payload bytes plus counters/metadata. This is
additional Host storage, not a deduction from the 32768-byte reserve.

Recording overhead has its own sample count and maximum, measured around
the six series updates. This excludes the two surrounding timer calls and
the final overhead-counter update; timer resolution is not accuracy proof.
Service elapsed includes clock calls and preemption and is not pure task CPU
time. DMA wait is not charged to render, and none of these observations claims
to measure physical DMA progress while IRQ delivery is delayed or masked.
Driver submission failure timing includes its existing failure cleanup.

Only the audio owner writes the accumulators. Serialized control-side reads
are unavailable while idle/booting/running and allowed after the existing
finished release/acquire boundary. No new concurrent Core interface, ISR log,
USB opcode, stdout dump, synchronization protocol or Project state is added.
Every admitted start attempt resets the population, including task-creation failure.
Successful, failed and stopped attempts have distinct counters; partial
failures only populate timing stages actually executed. Startup prewarm and
final stop/drain are outside these steady-service samples.

## Verification and remaining work

Compare percentile output with an independent sorted full population,
including duplicates, zero, exact rank boundaries and retention exhaustion.
Exercise the same orchestration used by the actual worker with deterministic
clock/I/O functions and assert each failed leg prevents later work and preserves
its partial timing population. Run existing driver consumers, native/ASan,
EIM compile/link, staged ownership and portal checks.

Native and ASan/UBSan each pass 41/41 (40 component plus existing audio
stress), terminal exit 0, at `/tmp/cardputer-diagnostics-final-tests.log` and
`/tmp/cardputer-diagnostics-final-asan-tests.log`. The real EspAudioIo test
also verifies that a later clock read cannot replace the queued EOF timestamp.
EIM firmware compile/link exits 0 (`/tmp/cardputer-diagnostics-eim.log`),
staged ownership passes 72/72 (`/tmp/cardputer-diagnostics-scope.log`), and
the complete portal check exits 0 with 46 current routes checked
(`/tmp/cardputer-diagnostics-portal.log`). No device operation was performed.

These tests do not exercise a real FreeRTOS task, physical DMA timing, scheduler
latency, USB diagnostics extraction, resource cycles or speaker output. The
complete candidate still needs a read-only diagnostics transport, measured
resource/stack accounting, actual overlapping voices, full 30-minute load and
physical latency capture. A zero software-fault count cannot establish zero
physical underruns. No D1 threshold or journey is reduced by this Task.

## Version Management

Version impact: none for this internal Host instrumentation; no public wire
Contract or Assembly/Build change. Final candidate identities remain a separate
integration obligation before joint device acceptance.

## Documentation Impact

Documentation impact: required — `/hosts/cardputer-host/` describes the
available stopped-session diagnostics and their measurement limitations.
