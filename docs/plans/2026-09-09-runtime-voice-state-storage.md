# Runtime Voice-state Storage Compaction

## Scope and authority

The accepted first memory optimization changes only the private representation
of the Voice-state SPSC ring. Public event member order, full-width values,
10,240-event capacity, FIFO, overflow corruption and fail-closed admission stay
unchanged. No packing, dynamic allocation, new synchronization, smaller Voice
budget, profile split, queue removal, PSRAM, flashing or release is included.

## Task M1

One Conventional Commit declares these files:

- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `tests/core/audio/fixed_spsc_queue_test.cpp`
- `tests/core/audio/realtime_engine_stress_test.cpp`
- this plan
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/diagrams/audio-runtime.architecture.json`
- generated `apps/docs-site/static/diagrams/audio-runtime.html` and `.svg`

An internal typed adapter copies public events into naturally aligned cells
ordered as sequence, runtime frame, source frame, slot and state. It delegates
all queue/index ownership to the unchanged FixedSpscQueue. Failed pops leave
the output untouched. The Engine uses this adapter without changing its
publication, corruption or drain logic.

## Verification

Lowest-tier `audio.realtime_queue` checks storage, lossless full-width field
transport, exact capacity/FIFO, wraparound, failed operations and quiescent
clear/reuse. First run the storage assertion against the old representation
to demonstrate its red signal. Keep the existing queue tests.

Add one million compact event transfers with repeated wraparound to the
existing `audio.realtime_spsc_stress`, retaining its existing workload and
coverage-preset exclusion. Run audio and Runtime Facade component/unit tests,
all five existing stress targets, and relevant native ASan/TSan tests. Existing
Engine tests remain the far-side proof of overflow corruption, refused voice
admission and fail-closed drain; the adapter tests do not substitute for them.
No timeout, floor or required CI gate changes.

Measure the same source before/after with the existing EIM-managed Xtensa
toolchain outside the repository. Compiler object sizes are not device heap,
successful playback, timing, or proof that the complete runtime fits the board.
Run Portal check and staged new-file ownership before commit. Shipping follows
issue-done; the user's effective-review hold remains applicable.

## Version Management

Version impact: Module ABI layout change, staged in source; not a claim of
binary compatibility. The public RuntimeVoiceStateEvent API/layout is retained,
but RealtimeEngine is a complete C++ type whose size changes. All consumers
must rebuild together; do not mix old headers/objects with this implementation.
The current audio-runtime manifest remains at 3.1.0 for this source-only Task.
A separately allocated Package release must account for the ABI break with a
MAJOR bump and update exact dependent/Assembly locks before distribution.
No Product Build, Channel, Module tag, Contract, Provider or Model is allocated
or changed here. No persisted Project migration is needed. No tag, publication,
deployment or promotion is authorized by this Task. Rollback is a source revert
and coherent consumer rebuild, not replacement of an immutable release.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/audio-runtime

Update the current storage/concurrency description and its source diagram;
no Product snapshot is allocated. The regression tests express the product
invariant, so no new process-pitfall entry is expected.

## Results

Verified on 2026-09-09, based on `627730a9a065de30e3b476ab11b0298c7b23d0e7`:

- Red proof: the old FixedSpscQueue event representation, exposed through a
  type alias without changing its storage, failed at the new storage bound
  after a fresh configure/build. The final adapter passes it.
- `cmake --build build/core/dev -j 6` passed. Then
  `ctest --test-dir build/core/dev -R '^(audio\.|facade\.runtime_facade)' --output-on-failure`
  passed 18/18, including all five stress targets and the existing overflow,
  refused-admission and corrupted-drain assertions.
- Fresh `asan` and `tsan` configurations rebuilt queue, realtime Engine, all
  five stress binaries and Runtime Facade component/quiescence binaries.
  `ctest --test-dir build/core/asan -R '^(audio\.(realtime_queue|realtime_engine|.*stress)|facade\.runtime_facade.*)$' --output-on-failure`
  and the same command with `build/core/tsan` passed 9/9 separately.
  This is focused native evidence,
  not a complete cross-platform CI or coverage pass.
- Vendored dependency, active-tree and version checks passed. No manifest or
  Assembly changed. `scripts/docs-site.sh check` passed (44 routes).

The before/after external ESP-IDF probe uses the same EIM-managed SDK revision
`fff9895c82d744c7237be8847347bdd1b07c6643`, Xtensa GCC 15.2.0,
strict gnu++20 warnings and complete 18-source producer closure. Both linked
ELFs retain every declared root: 393 before, 395 after (the adapter adds two).
ELF size-vector decoding and target GDB agree:

| Target object | Before bytes | After bytes |
| --- | ---: | ---: |
| Public RuntimeVoiceStateEvent | 32 | 32 |
| Internal cell | 32 | 24 |
| Voice-state ring, including indices/alignment | 327,872 | 245,952 |
| RealtimeEngine | 594,624 | 512,704 |
| Facade Impl excluding separately allocated Engine | 8,416 | 8,416 |
| Facade handle | 4 | 4 |
| Combined fixed object floor | 603,044 | 521,124 |

Savings: **81,920 bytes (80 KiB)**, with the full 10,240-event capacity.
The remaining fixed floor is about 508.91 KiB, before PCM, allocator overhead,
task stacks and platform buffers. This does **not** establish board fit or
authorize T5 hardware/flash testing.

Local evidence is retained outside Git at
`/Users/endaye/esp/lmdj-spike/voice-state-memory.2AcJbC/`: source header before,
red/green host logs, sanitizer logs, two fresh target builds, ELF/map,
root inventories, decoded `sizes.json`, and GDB layouts. The before header uses
the alias only; the after build contains this Task's uncommitted implementation,
so the base SHA alone is not the after source identity. The retained header
and final Task commit bind that difference. ELF SHA-256:

- before: `d6ce2cc0cf7984b03f6eade30ddcca33d2489c26d49abba703dc7f93a82d42c6`
- after: `a9dd1ba40505500bd73328c6f69489c8076a0b5935e92e31c54f4d05405082dc`

The original T4 probe/evidence remains untouched. No device was flashed or run.
