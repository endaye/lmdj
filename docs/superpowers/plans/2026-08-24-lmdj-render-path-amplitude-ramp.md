# LMDJ Render Path Amplitude Ramp (F6)

**Goal:** close the F6 trim-boundary/release clicks exactly as decided in
[`docs/prd/decisions/2026-08-24-render-path-amplitude-ramp.md`](../../prd/decisions/2026-08-24-render-path-amplitude-ramp.md):
a **96-frame** (2 ms at 48 kHz) **linear** attack/release ramp in the
`audio-runtime` realtime render path. Loop-seam crossfade is deferred;
zero-crossing snap is rejected.

**Tech Stack:** C++20, CMake/CTest, Docusaurus Architecture Portal.

## Why this plan exists

`packages/audio-runtime/src/realtime_engine.cpp` renders
`voice.samples[voice.cursor] * voice.gain` per frame; at `end_frame` a looping
voice hard-wraps `cursor = start_frame`, a non-looping voice hard-stops
(`active = false`), and `stop_voice` sets `active = false` immediately. There
is no attack ramp, no release ramp and no boundary fade anywhere, so a trim
edge on a non-zero sample is a step discontinuity — audible as a click. The
2026-08-17 physical session measured this (F6, section F of
[`2026-08-16-outstanding-work-before-stage9.md`](../../quality/2026-08-16-outstanding-work-before-stage9.md),
M2 check 1). The product decision with its realtime-safety review landed
2026-08-24 and this plan is its implementation.

## Sample rate

The engine's render rate is the compile-time constant
`kRealtimeSampleRate = 48'000`
(`packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp:18`); the
engine has no other rate. A constant frame count is therefore exact:
`kRealtimeRampFrames = 96` is 2 ms everywhere this engine runs. Verified, not
assumed.

## Design (per the decision record, binding)

All ramp state is POD fields appended to the private `Voice` struct — no
heap, no locks, `noexcept` preserved. The ramp scale is the compile-time
constant `1.0F / 96.0F`; per-frame cost is at most two extra multiplies and
counter decrements per active ramp component (no division in the render
loop). Full-scale cases (counter at 96, non-ramped region) skip the multiply
so non-ramped output stays bit-identical to today.

- **Attack.** New POD field `attack_frames_remaining`, initialized to 96 when
  a voice is triggered, decremented per rendered frame. While nonzero the
  frame's gain is multiplied by `(96 − remaining) × (1/96)`, linear 0 → 1
  over exactly 96 frames. Because the counter is per-voice state and not a
  function of `cursor`, a looping voice attacks only on the initial trigger —
  the wrap `cursor = start_frame` cannot restart the ramp.
- **Boundary release (non-looping voices).** Stateless: when
  `end_frame − cursor < 96` the frame's gain is multiplied by
  `(end_frame − cursor) × (1/96)`. Looping voices get no boundary fade (the
  guard is `!is_looping(trigger_mode)`).
- **`stop_voice` release.** `stop_voice` no longer silences the voice. It
  publishes `RuntimeVoiceState::stopped` at stop initiation (**timing
  unchanged**) and moves the voice into a releasing state (new POD fields
  `releasing` + `release_frames_remaining = 96`). The voice stays `active`
  and renders a 96-frame tail with gain multiplied by
  `remaining × (1/96)`; when the counter reaches zero the voice is physically
  deactivated: `release_voice_bank`, `cancelled_voices_` and `active_voices_`
  counters, `active = false`. The tail's last rendered frame carries gain
  1/96 and deactivation follows immediately — the ramp ends at exact 0 with
  no denormal tail.
- **Counters move to deactivation.** `stopped` publication is the only
  initiation-time side effect; `cancelled_voices_`/`active_voices_` move to
  physical deactivation so `started == completed + cancelled` and the
  active-voice accounting stay consistent while the tail renders.
- **Hard kill of a releasing voice.** `stop_voice` on an already-releasing
  voice deactivates it immediately (bank release + counters + `active =
  false`), with **no** second `stopped` publication and no second ramp. This
  covers `stop_all` after a gate release and the voice-stealing path: stealing
  keeps its current immediate-kill behavior for victims — the ramp is for
  operator-initiated stops and natural ends. A loop-toggle re-press on a
  releasing toggle voice likewise hard-kills it and starts no new voice (the
  voice is still `active`, so the toggle branch matches); this is the
  documented minimal semantic.
- **Natural completion during a tail.** A releasing non-looping voice that
  reaches `end_frame` before its tail ends is deactivated as cancelled
  without publishing `completed` (its terminal state was already published as
  `stopped` at initiation).
- **Edge cases.** Voices shorter than 96 frames: attack, boundary and release
  multipliers simply multiply (96 is a constant, no division by zero).
  `stop_voice` during attack: the attack and release multipliers multiply; no
  special-casing.
- **Engine `stop()`** resets every voice to `Voice{}` wholesale, so the new
  fields are cleared on restart with no extra code.

### Deliberately out of scope

- Loop-seam crossfade — deferred by the decision; M2 check 5 is expected to
  remain clicky and that expectation is recorded in the manual-verification
  ledger, not hidden.
- The offline renderer (`offline_renderer.cpp`) is a separate PCM16 snapshot
  render path with no voices, no `stop_voice` and no loops; the decision's
  ramp semantics are stated purely in voice terms. It is untouched, which
  also keeps the golden-audio SHA stable.

## Tasks

### Task 1 — Ramp in the realtime render path

`realtime_engine.hpp`: add `kRealtimeRampFrames` (96) next to
`kRealtimeSampleRate`; append `attack_frames_remaining`, `releasing`,
`release_frames_remaining` to `Voice`. `realtime_engine.cpp`: initialize the
attack counter at trigger; apply the three multipliers in the render loop;
rework `stop_voice` (release vs hard-kill); add a deactivation helper for the
release end / hard kill; guard the completion edge against releasing voices.

**Files:** `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`,
`packages/audio-runtime/src/realtime_engine.cpp`.

### Task 2 — Tests

Rewrite the existing assertions that pinned the old click-producing behavior
(exact first-frame values, immediate-stop silence, active-voice counts right
after a stop) to pin the new ramped behavior, preserving every invariant
assertion that is still true (publication ordering and timing, telemetry
conservation, allocation-free render, fail-closed streams). New unit tests:

- attack ramps 0 → 1 linearly over exactly 96 frames from trigger;
- non-loop boundary fades to 0 at `end_frame` (last frame carries 1/96);
- `stop_voice` produces a 96-frame tail then deactivation, with `stopped`
  published at initiation (sequence, runtime frame, source frame unchanged);
- loop wrap does NOT re-apply attack;
- a releasing voice is hard-killed by a second stop (stop_all) with no second
  `stopped` publication;
- short voice (< 96 frames) attack × boundary edge.

**Files:** `tests/core/audio/realtime_engine_test.cpp`,
`tests/core/audio/prepared_sample_bank_test.cpp`,
`tests/core/facade/web_runtime_limits_test.cpp` (first-frame expectation).

**Verification:** `scripts/core.sh configure dev`,
`scripts/core.sh build dev`, `scripts/core.sh test dev` (full), and —
mandatory for lock-free/concurrent changes —
`scripts/core.sh test dev stress` (`audio.realtime_spsc_stress`,
`audio.snapshot_publication_stress` must pass).

### Task 3 — Version cascade, docs and portal

`audio-runtime` SemVer **patch** `0.5.0` → `0.5.1`, paying the full
Core-Module cascade (precedent: `2fc9cfe9`): every manifest in the dependency
closure bumps its reference and its own patch — `application-facade`
`1.4.4 → 1.4.5`, `web-runtime-platform` `0.3.4 → 0.3.5`, `core-cli`
`1.0.16 → 1.0.17`, `core-mcp` `1.1.13 → 1.1.14` (+ `pyproject.toml`,
`__init__.py`), `native-test-host` `1.0.14 → 1.0.15` (+ `main.cpp`),
`web-runtime-host` `1.2.13 → 1.2.14`, `creator-web` `1.5.3 → 1.5.4` (+
`package.json`, `package-lock.json`). Providers are not in the closure and
stay `1.0.5`. Product Build **1.0.35.0** (`products/lmdj/version.json` build
34 → 35), `assembly.json`, `products/lmdj/CMakeLists.txt` + `README.md`
literals, then regenerate `assembly.lock.json` + `compiled_assembly.cpp`
(`python3 scripts/version.py lock`, run **after** the CMakeLists/README
edits — the source-package hash covers `products/lmdj`) and the web-runtime
identity (`tools/web-runtime/generate_runtime_identity.py`). Literal
expectations: `tests/build/version_test.py`,
`tests/conformance/module_graph_test.py`, portal `repo-facts.test.mjs`, Host
test literals. Quality ledgers: mark F6 fixed in `1.0.35.0` in
`docs/quality/2026-08-16-outstanding-work-before-stage9.md` section F, F6 row
done in `docs/quality/2026-08-17-machine-task-todo.md`, and note the build on
the M2 row of `docs/quality/2026-08-17-manual-verification-todo.md` (row
stays stopped-at-check-1 for the human re-run; check 5 loop seam is expected
to remain clicky until the deferred crossfade lands). Portal: update the
current `audio-runtime` module page and version-carrying pages, then freeze
`scripts/architecture-portal.sh version 1.0.35.0 canary` as a second commit
on a clean worktree; post-freeze `scripts/architecture-portal.sh check` must
exit 0.

**Verification:** `python3 scripts/version.py verify --version-file
products/lmdj/version.json`, `python3 tests/build/version_test.py`,
`python3 tests/conformance/module_graph_test.py`,
`bash scripts/verify-core-dependencies.sh`,
`bash tests/build/test_active_tree.sh`, portal check.

## Version Management

**Version impact: required.**

- `audio-runtime` takes a SemVer **patch** bump `0.5.0` → `0.5.1`: the ramp
  repairs defective render-path behavior without changing any public API,
  Contract or the lock-free/realtime contract.
- Every module and Host in `audio-runtime`'s dependency closure takes a
  SemVer patch bump with its dependency reference updated (Task 3 list).
- Product Build **1.0.35.0** is allocated for the new Assembly composition,
  with its immutable Architecture Portal snapshot
  (`scripts/architecture-portal.sh version 1.0.35.0 canary`) as a second
  commit.
- No Contract, Provider or Application Facade `api_version` changes.

## Documentation impact

**Documentation impact: required.**

- `core/modules/audio-runtime` describes the render path and must describe
  the ramp; the version-carrying portal pages change with the new Product
  Build; the `1.0.35.0` snapshot is frozen in the same Task (second commit).
- The quality ledgers listed in Task 3 change in the same commit that closes
  F6.
- Run `scripts/architecture-portal.sh check` before every commit (the
  pre-freeze missing-snapshot failure is the known accepted state; run the
  other portal gates individually pre-commit as prior tasks did).

## Out of scope

Loop-seam crossfade (deferred by the decision, pending M2 evaluation);
zero-crossing snap (rejected by the decision); offline renderer ramping; any
change to publication timing, trigger semantics, capture, or bank
publication. Local commits only — push, PR, merge, tag, Release, publication,
deployment and Channel promotion each require separate explicit
authorization.
