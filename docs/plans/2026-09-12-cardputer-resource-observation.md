# Cardputer resource observations

Relates to #1104 and #1111. This Task supplies resource measurement primitives
for the pending identity-bound observation integration, not a device verdict.

## Declared scope

- `apps/cardputer-host/main/resource_observation.hpp`
- `apps/cardputer-host/main/runtime_host.hpp`
- `apps/cardputer-host/main/runtime_host.cpp`
- `tests/platform/cardputer/resource_observation_test.cpp`
- `tests/platform/cardputer/fake_esp/esp_heap_caps.h`
- `tests/platform/cardputer/fake_esp/freertos/task.h`
- `tests/platform/cardputer/CMakeLists.txt`
- `apps/docs-site/docs/hosts/cardputer-host.mdx`
- this plan

The control owner can capture internal byte-addressable, DMA byte-addressable
and external byte-addressable heap information plus its own stack high water.
Each heap projection retains free bytes, largest free block and the SDK's sum
of per-region low watermarks. Overlapping capabilities must not be added.
These are sequential measurements, not an atomic global snapshot. Collection
begin/end timestamps expose the interval, including the stack scan. Do not
call the heap sampler from the render callback or ISR.

The audio worker records its own stack high water after driver cleanup, before
publishing `finished`. The serialized control owner reads it only after the
existing acquire barrier. Before start, during execution and after failed task
creation it is unavailable; an observed zero is valid. Every admitted start
clears the previous observation. The value excludes subsequent task deletion
code. `finished` is not evidence that the idle task reclaimed stack memory.

## Verification

Component tests compile the actual sampler against ESP API stand-ins and
assert exact capability masks, byte units, field mapping, independent samples,
zero values and timestamp boundaries. Existing audio lifecycle tests exercise
the unchanged join contract; real FreeRTOS scheduling, stack fill scanning,
heap locking/fragmentation and asynchronous task reclamation are NOT modeled.
Compile/link the actual ESP branch with the existing pinned EIM SDK. Run native
and ASan component tests, existing audio stress, staged ownership and portal
checks. No new threshold, test timeout or required CI gate is introduced.

Native and ASan/UBSan each pass 32/32 (31 component and one existing audio
stress), terminal exit 0. Logs: `/tmp/cardputer-resource-tests-final.log` and
`/tmp/cardputer-resource-asan-tests-final.log`. EIM ESP32-S3 compile/link exits
0 at `/tmp/cardputer-resource-eim.log`. The SDK definitions were checked at
the pinned installation: stack high water returns bytes, and the capability
mask values match the test stand-ins. This does not execute the real worker
publication/reset path on a FreeRTOS scheduler; that remains a device test.
Staged ownership passes 72/72 (`/tmp/cardputer-resource-scope-final.log`).
The complete portal check passes 116 tests and validates 46 routes, terminal
exit 0 (`/tmp/cardputer-resource-portal.log`).
The five existing fake-ESP consumer targets rebuild and their 15 component
tests pass, exit 0 (`/tmp/cardputer-resource-fake-consumers-tests.log`).

## Version Management

Version impact: none for internal Host instrumentation. No public wire Contract,
Module, Assembly or Product Build changes. Final integration must allocate and
verify the candidate identities before distribution.

## Documentation Impact

Documentation impact: required — `/hosts/cardputer-host/` gains the precise
resource sampling semantics and limitations.

## Remaining acceptance

The pending observation transport must bind these values to content/session and
firmware identities and capture all load/play/stop/unload/reload cycle legs.
No resource threshold, thirty-minute load, actual voice load, physical latency,
hearing or reclamation PASS is established by this source Task. Pitfall impact:
none; the unit tests express measurement mapping, not a new process mechanism.
