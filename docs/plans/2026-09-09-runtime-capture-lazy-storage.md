# Runtime Capture lazy storage

## Authority and scope

Approved 2026-09-09: allocate the unchanged 4096-event Capture ring on the
serialized control thread only when recording is requested. Allocation failure
refuses recording, leaves playback running and creates no Native Sequence
session. Preserve unread events after disarm/stop; retain allocated storage until
quiescent engine destruction. No Voice-state/outcome omission or capacity cut.

## Task: defer Capture storage and preflight Native recording

One implementation commit. Declared files:

- `CMakeLists.txt` (register the new instrumented test in coverage objects)
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- `tests/core/audio/realtime_engine_stress_test.cpp`
- `apps/native-host/src/main.cpp`
- `apps/native-host/CMakeLists.txt`
- `tests/host/native_capture_allocation_failure_main.cpp`
- `tests/host/native_capture_allocation_failure_test.py`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/docs/hosts/native-host.mdx`
- `apps/docs-site/diagrams/audio-runtime.architecture.json`
- generated `apps/docs-site/static/diagrams/audio-runtime.html` and `.svg`
- this plan.

`prepare_capture()` is an idempotent, non-arming, control-only `noexcept` boolean
preflight. False means storage allocation failed; it must not allocate an error
message. Existing `arm_capture()` prepares implicitly for source compatibility;
its allocation-failure Result uses `internal_error`, empty message and null
details to avoid a second allocation. Native calls prepare before begin_sequence
and returns an explicit insufficient-memory error without starting its writer.
The allocation-free C++ diagnostic is not a serialized `lmdj.error.v1` envelope;
Native maps preflight failure to a nonempty message and object-valued details.
The queue pointer is initialized once before release-publishing `arm_pending`;
audio reads it only after acquiring a capture state admitting writes. No pointer
replacement/free occurs while rendering. Drain remains control-only; start
clears retained storage only under its existing quiescence requirement.

Lowest-tier verification and defects:

- `audio.realtime_engine` component: first arm performs one allocation;
  persistent allocation failure cannot terminate noexcept or change running/idle
  state; retry works; preflight/re-arm/restart reuse storage; stop preserves
  unread events; original full-capacity overflow and exact-frame tests remain.
- `audio.realtime_spsc_stress`: first allocation while the renderer is already
  running, followed by complete ordered event consumption; run under TSan too.
- `host.native_capture_allocation_failure`: test-only allocator interposition
  over the real Host, CLI-authored Project and protocol. Failed begin leaves no
  session/files or truth change, playback still advances, identical-session retry
  succeeds, record/stop persists, and reopen verifies the committed revision.
  No failure switch enters the production binary. Deterministic no-device
  rendering is not physical-device/subjective-audio acceptance.
- Existing `host.native`, source-boundary and timeout-policy tests;
  RuntimeFacade component regression; dependency/active-tree checks.
- Portal check, coverage check and staged new-file ownership check. No new required CI gate,
  test exclusion, threshold, timeout or capacity reduction.

Measure cold engine layout before/after using the same Xtensa compiler, when
available; roughly 64 KiB is an estimate until measured, not a target fit claim.
Active recording still pays the full ring allocation (including alignment and
allocator overhead); it is not an active-recording memory saving.

### Measured layout

EIM-managed ESP-IDF v6.1 / Xtensa ESP GCC 15.2.0 object-only compilation of the
same size probe against baseline `a81faad3b85d362e3e44541cd28ee21dac6848a4`
and this Task's header yields `sizeof(RealtimeEngine)` 512704 -> 446976 bytes:
65728 bytes (64.1875 KiB) less fixed storage. Other measured public event sizes
are unchanged. Values are compiler-emitted constants read from ELF32-Xtensa
objects, not a board heap measurement or firmware execution. The before build
overrides only the exact baseline Engine header; all other includes/flags are
identical to the after build.

### Verification evidence and limits

- `scripts/core.sh test dev fast`: 76 passed; `scripts/core.sh test dev stress`:
  12 passed, preserving the original stress workloads.
- `ctest --test-dir build/core/{asan,tsan} -R
  '^(audio.realtime_engine|audio.realtime_spsc_stress)$' --output-on-failure`:
  both selected tests passed separately in each sanitizer configuration.
- `ctest --test-dir build/core/dev -R '^host.native' --output-on-failure`:
  4 passed, including the fault-injected full retry/persistence journey.
- `CMAKE_BUILD_PARALLEL_LEVEL=4 scripts/core.sh coverage check`: 143 selected
  tests passed and every existing floor passed. Overall line/branch coverage:
  83.88%/70.61%; Audio Runtime: 90.56%/81.88%. New instrumented Host target is
  present in `coverage-objects.txt`; no floor or exclusion was changed.
- `scripts/docs-site.sh check`: 112 tests, 43 current pages, deterministic
  diagrams and 44 built routes/internal links passed. Staged new-file ownership
  suite: 66 passed; dependency, active-tree and Product version checks passed.
- Reproduction before implementation: the first-arm allocation assertion fails
  against the embedded-ring implementation. A subsequent ordering perturbation
  (prepare after begin_sequence, with the same error response) fails specifically
  at `failed begin wrote a session`; restoring and rebuilding the Host passes.
- Extra coverage-runner self-test diagnostic: 6/7 passed. The unchanged
  `test_failed_run_cannot_leave_documented_stale_artifacts` expects its CTest
  sentinel on stderr, while the runner now combines stderr into a stdout tee;
  its temporary fixture also omits `test_budget_report.py`. Exact files from
  main `9e2077d568e52f2e084c60ab02da15b24349b1ea` reproduce the same failure.
  This pre-existing harness defect is not changed or called a pass here.

No physical device/audio, firmware link, whole-board fit or remote complete
self-test is claimed by these local checks.

## Version Management

Version impact: additive Module MINOR capability, staged in source with the
approved B2 T2/T3 integration boundary. Before distributing a B2 Package/Build,
allocate then-live Module/Assembly identities and its immutable Portal snapshot.
No wire Contract, Project migration, Product Build, tag, release, deployment or
Channel promotion is allocated here. This is source integration, not release.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/audio-runtime/ /hosts/native-host/
Reason: Capture storage lifetime, control-thread preflight and Native failure
semantics change; update the module source diagram and current pages together.
