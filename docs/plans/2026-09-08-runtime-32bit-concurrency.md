# Runtime synchronization on 32-bit targets

## Task and authority

Independent Core implementation authorized by the user after the unchanged
ESP32 render probe rejected atomic64. This is not part of the docs-only Step A.
Keep one audio writer, serialized control operations, unrestricted non-realtime
observers, 64-bit identities and counters, and quiescent lifecycle handoff.
No new Contract, Host, Facade profile, release or hardware-performance claim.

Declared files:

- `packages/audio-runtime/include/lmdj/audio/detail/value_channel.hpp`
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `packages/audio-runtime/src/testing_hooks.hpp`
- `packages/audio-runtime/src/pattern_generation.hpp`
- `packages/audio-runtime/src/realtime_engine_audio_access.hpp`
- `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`
- `apps/native-host/src/main.cpp`
- `apps/native-host/src/capture_writer.cpp`
- `packages/audio-runtime/CMakeLists.txt`
- `CMakeLists.txt` (register the instrumented unit-test coverage object)
- `tests/core/audio/value_channel_test.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- `tests/core/audio/master_fx_allocation_guard_test.cpp`
- `tests/core/audio/snapshot_publication_stress_test.cpp`
- This plan and `docs/design/2026-09-08-runtime-32bit-concurrency.md`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/docs/platform/native-audio.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/diagrams/audio-runtime.architecture.json`
- Generated `apps/docs-site/static/diagrams/audio-runtime.html` and `.svg`

## Implementation

1. Publish complete writer-owned value snapshots through fixed triple buffers.
   A reader-only mutex serializes telemetry; audio never acquires it. Keep a
   separate single-control-reader transport channel at the original callback
   frame-frontier update and before Pattern pending descriptor release.
2. Preserve bounded shared occupancy RMWs as atomic32 (queue reservation bound
   Capacity + 2; pending Banks at most four). Preserve the 64-Pad mask under the
   existing pending-zero release/acquire handoff.
3. Use atomic32 slot tokens for Pattern ownership, full immutable uint64
   generation in slots, and no generation reuse. Audio claim uses RMW's immediate
   predecessor. SC admission bounds control interference without audio waiting.
   Audio-owned cancellation retains the audio-local slot until audio releases it.
4. Derive Pattern telemetry only from value snapshots, using claimed-through
   identity and exact cancellation identity to remove stale control/audio copies.
5. Publish every modified domain on API return, including failure, drain,
   stopped direct application and quiescent lifecycle paths.
6. Keep Web Audio callback's Bank acknowledgement and Voice-stream health read
   on an internal audio-owner access path, never the reader mutex. Preserve its
   existing exact-generation acknowledgement and fail-closed error semantics.
7. Preserve native capture handoffs: publish capture origin before active/ring
   release and final counts before idle. Serialize CaptureWriter drain with the
   Native Host's existing Facade/control mutex; never hold it across a join.

## Verification

Baseline: `audio.realtime_engine` and all four existing audio stress tests pass.
Lowest tiers: value-channel unit and realtime-engine component tests. Add
deterministic regressions for carry/reset, retained readers, mailbox reuse,
cancellation/activation, final observations without another callback, high Pad
mask bits, and transport boundary timing. Run the four existing audio stress
tests and multi-observer reclamation under TSan. Validate fixed-toolchain Xtensa
code generation and retain the original atomic64 failure evidence separately.
Run dependencies, version, path ownership and docs-site checks before commit.
No new required CI gate; tests catch torn/reclaimed values, stale final state,
changed scheduling and unbounded producer interference, not a timing threshold.

### Executed evidence

- `scripts/core.sh coverage check`: 131/131 tests and all module floors pass
  on the final source; audio-runtime lines 90.44%, branches 81.16%; overall
  lines 83.56%, branches 69.89%. The complete report is generated at
  `build/core/coverage/coverage/report.txt` by the replayable command.
- `ctest --test-dir build/core/tsan --output-on-failure -R
  '^audio\.(value_channel|realtime_engine|master_fx_allocation_guard|realtime_spsc_stress|snapshot_publication_stress|long_sample_publication_stress|master_fx_stress)$'`:
  7/7 pass, including all four stress tests (thread sanitizer preset).
- `ctest --test-dir build/core/tsan --output-on-failure -R
  '^audio.realtime_engine$|^host.native$'`: 2/2 pass after the Native capture
  serialization and early/final capture handoff corrections. `host.native`
  also passes in the dev build, including the recorded-event durable journey.
  After the capture observer acquire-order correction, the combined seven
  audio tests plus `host.native` pass 8/8 under TSan, including the observer
  paused before its state acquire while audio publishes final idle/counts.
- `scripts/web-toolchain-conformance.sh build-audio-runtime` with fixed
  Emscripten 6.0.5: pass. After linking completed, Chromium
  `audio/realtime_audio_worklet.spec.mjs audio/realtime_failure.spec.mjs`:
  22/22 pass. An earlier test invocation overlapped linking and had six Host
  initialization timeouts; that run is not accepted as final-source proof.
- `scripts/docs-site.sh check`: 81 tests, 39 source pages, 10 diagrams and
  42 built routes pass. No frozen Product snapshot was changed.
- Dependencies, active-tree, Product version tests and version verify pass.
- Xtensa GCC 15.2.0 compiles unchanged `realtime_engine.cpp` at both `-O2`
  and `-Os` with `-std=gnu++20 -Wall -Wextra -Wpedantic -Werror -fexceptions`.
  Include paths are the four Core packages and vendored nlohmann headers.
  `nm -u` shows no `__atomic_*_8` in either object; the separate atomic64
  positive control does expose `__atomic_load_8`. `objdump -drC` shows
  `wsr.scompare1`/`s32c1i` compare-and-retry code and mutex relocations only
  in the seven non-realtime telemetry methods. This is object/code-generation
  evidence, not the complete IDF link or device measurement required by Step A.

Pitfall impact: none — the synchronization and caller handoff defects are
expressed by regression tests; the new unit target is included in the existing
coverage-object inventory. No floor, timeout or journey was reduced.

## Version Management

Version impact: none at this implementation revision. Public signatures,
serialized authoring data, external identity widths and product assembly remain
unchanged; this internal implementation is not an independently distributed
Package or allocated Product Build. All consumers rebuild from source. The
existing Any-thread observation contract is clarified as non-realtime and made
safe for multiple observers. No Module tag or binary-ABI compatibility claim.

## Documentation Impact

Documentation impact: required.
Affected portal pages: `/core/modules/audio-runtime/` `/platform/native-audio/` `/platform/web-runtime/`.
Reason: document the synchronization mechanism, reader-only locking and retained
quiescence requirement without claiming ESP32 hardware or deadline verification.

## Status

Implementation and local Task verification complete. Current-head independent
review and remote delivery are recorded by the Task Pull Request; this document
does not claim a merge, a complete ESP-IDF link or physical acceptance.
