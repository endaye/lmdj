# Creator Sample Playback and Tone Parity Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close [#1666](https://github.com/endaye/lmdj/issues/1666) (reverse, pitch, pan, loop modes) and then [#1667](https://github.com/endaye/lmdj/issues/1667) (attack/release, tone, 3-band EQ). Each new parameter must be audible in Creator, persisted in Project Truth, reproduced after reopen, and rendered identically by realtime, preview, Pattern, Performance Replay and offline paths.

**Architecture:**
- **Authority.** The parameters live on the Pad Slot's `PadPlayback` as optional fields whose default is today's behaviour. They are governed by the [2026-09-30 decision](../prd/decisions/2026-09-30-sample-playback-and-tone-parity.md), which is the authority for every range, mapping and DSP order below.
- **Cook time.** Project Cooker validates the fields and resolves them into a small, trivially copyable, all-zero-neutral `ResolvedVoiceDsp` block on `ResolvedPlayback`.
- **One shared kernel.** Audio Runtime gains one per-voice DSP kernel. The realtime engine and the offline renderer both call it.
- **Neutral events are untouched.** A neutral event keeps today's exact code path, so every existing exact-value assertion and the golden render stay unchanged by construction.
- **Hosts.** Application Facade, core-mcp, Web Runtime Platform and Creator learn the new keys with one rule: a missing key means default, and only non-default keys are emitted.

**Tech Stack:** C++20, CMake, nlohmann/json, Emscripten `6.0.5` Wasm AudioWorklet, JavaScript ES modules, React/TypeScript/Vitest, Playwright, Python 3.11, JSON Schema 2020-12, Docusaurus Architecture Portal.

## Global Constraints

- The decision record above is the authority. A conflict found during implementation returns to decision review; implementation must not silently change a range, a default, the DSP order or a refusal rule.
- **Execution environment.**
  - Every PR starts from the latest `origin/main` in its own `.worktrees/<task>` created with `git worktree add --no-track`. Never start from a stale local `main` (`.agents/pitfalls/stale-premise-gets-implemented.md`).
  - Run `gh auth switch --user endaye` and list open PRs before creating one.
- **Neutral means identical.** With every new field at its default, the following stay unchanged:
  - Project Truth bytes;
  - the value of every existing `ResolvedPlayback` field;
  - every serialized form, including the `lmdj.runtime-content.v1` encoding and `runtime-content-v1.hex`;
  - realtime output, offline output and the golden `tests/fixtures/golden/one_bar_120bpm.{wav,sha256}`.

  The in-memory `ResolvedPlayback` does gain a trailing all-zero `dsp` block. As of `3105cebb`, no code serializes, hashes or `memcmp`s `ResolvedPlayback` or `PreparedPatternEvent` as raw bytes: the runtime-content codec (`runtime_content.cpp:346-355`) writes explicit fields. Task 4 re-proves this. No existing exact-value assertion may be edited to make a Task green.
- **Realtime safety.** The audio thread stays allocation-free, lock-free, non-blocking and `noexcept`. Coefficients are designed once per trigger, not per sample. No deadline, timeout, coverage floor or stress budget is widened.
- **Host boundary.** Creator and the Web Host use Web Runtime Platform and Application Facade only. They must not parse Project JSON or duplicate cooker math. The existing duplicate in `resolve_preview_playback` is removed, not copied.
- **Cardputer.** `lmdj.runtime-content.v1` is unchanged. Its encoder refuses any non-neutral `ResolvedVoiceDsp`; it never drops one silently.
- **Contract cut.**
  - The Project Contract schema digest is pinned by `products/lmdj/assembly.lock.json`, so a schema edit is inseparable from its Assembly and Product Build allocation.
  - Each Contract cut is therefore its own PR, following precedent [#761](https://github.com/endaye/lmdj/pull/761). The immutable Portal snapshot goes in the same PR (`.agents/pitfalls/portal-snapshot-not-deferrable.md`).
  - Feature PRs keep module manifests unchanged. Module SemVer is settled only in the dedicated version-settle PRs (PR 4 and PR 7, precedent [#1637](https://github.com/endaye/lmdj/pull/1637)). PR 4 deliberately combines the #1666 settle with the `5.2.0` cut, so that both identity changes share one Build.
- **Test binaries.**
  - New Facade scenarios go into a new test binary, not into the budget-bound `tests/core/facade/sample_surface_test.cpp` (`.agents/pitfalls/facade-surface-test-budget-headroom.md`).
  - Every new instrumented test target joins `lmdj_coverage_targets` (`.agents/pitfalls/coverage-target-list-omits-new-test.md`).
- **Every `PadPlayback` copy changes together.** The copies are:
  - domain
  - schema
  - project-io checkpoint and transaction log
  - Facade codec
  - core-mcp schema
  - `control_runtime.cpp`
  - `protocol.mjs`
  - `runtime_session.mjs`
  - creator `sample_state.ts` and `waveform_editor.tsx`

  One shared fixture `tests/fixtures/contracts/pad-playback-full.json` is asserted by every copy (`.agents/pitfalls/parity-check-between-agreeing-copies.md`).
- **Before every commit:**
  - verify the branch is not `main`;
  - run the Task tests;
  - stage only the declared files;
  - inspect the staged name list, `git diff --cached --check` and the full staged diff;
  - after committing, inspect `git show --name-status --oneline HEAD` and the worktree status.
- **Coordination.** [#1661](https://github.com/endaye/lmdj/issues/1661) and [#1668](https://github.com/endaye/lmdj/issues/1668) also edit `commands.hpp`, `PadPlayback` and project-io, so whichever lands second rebases. If `feat/creator-boot-auto-project` (#1660) merges first, the Playwright Tasks rebase onto its new boot fixture.
- **Authorization.** Push, PR, current-head review and squash merge follow `.agents/skills/issue-done/SKILL.md`. Tag, Release, publication, deployment and Channel promotion are outside this plan.

## Locked Interfaces

### Project Truth

`packages/authoring-domain/include/lmdj/domain/project.hpp` appends fields to `PadPlayback`. Appending at the end, with defaults, keeps existing positional initialisers compiling.

```cpp
enum class LoopMode : std::uint8_t { forward, ping_pong };

struct PadPlayback {
  std::uint64_t trim_start_frame{0};
  std::optional<std::uint64_t> trim_end_frame;
  TriggerMode trigger_mode{TriggerMode::one_shot};
  std::int32_t gain_millidb{0};
  bool muted{false};
  // #1666
  bool reverse{false};
  std::int32_t pitch_cents{0};                    // [-2400, 2400]
  std::int32_t pan{0};                            // [-100, 100]
  LoopMode loop_mode{LoopMode::forward};
  std::optional<std::uint64_t> loop_start_frame;  // nullopt == trim_start_frame
  std::uint64_t loop_crossfade_frames{0};
  // #1667
  std::int32_t attack_ms{0};                      // [0, 2000]
  std::int32_t release_ms{0};                     // [0, 4000]
  std::int32_t tone{0};                           // [-100, 100]
  PadEq eq{};                                     // all bands bypassed
  bool operator==(const PadPlayback&) const = default;
};
```

- The #1667 fields and `PadEq` land in Task 12, not with the #1666 fields.
- A looping voice's first pass always starts at `trim_start_frame` (its reverse mirror when `reverse` is set). Only later passes wrap to `loop_start_frame`. `nullopt` makes the two points coincide.
- Every out-of-range value, and `ping_pong` with a non-zero crossfade, is refused with `invalid_argument` and leaves state unchanged, as the existing gain and trim refusals do.

### Wire and persisted JSON

The existing five snake_case keys stay required. Each new key is optional and omitted when it holds its default.

`lmdj.project.v5` `5.1.0` (Task 1, #1666) adds:

- `reverse`
- `pitch_cents`
- `pan`
- `loop_mode` (`"forward" | "ping_pong"`)
- `loop_start_frame`
- `loop_crossfade_frames`

`lmdj.project.v5` `5.2.0` (Task 12, #1667) adds:

- `attack_ms`
- `release_ms`
- `tone`
- `eq` (`{low, mid, high}`, with the band shapes from the decision)

A `5.1.0` reader rejects a Project carrying any `5.2.0` key.

Unknown keys stay rejected. A reader treats a missing key as its default. A writer never emits a default-valued key.

### Runtime Snapshot and kernel

- `packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp` gives `ResolvedPlayback` a trailing `ResolvedVoiceDsp dsp`:
  - integer-only and trivially copyable;
  - all-zero means neutral;
  - 12 B for #1666, extended by 12 B for #1667.
- `PreparedPatternEvent::operator==` (`prepared_sample_bank.hpp:111-121`) must compare `dsp`.
- The kernel lives in `packages/audio-runtime/include/lmdj/audio/detail/voice_dsp.hpp` and `src/voice_dsp.cpp`:
  - `prepare_voice_dsp(const ResolvedVoiceDsp&, float gain, VoiceDspState&) noexcept` builds a stage mask and the per-trigger coefficients.
  - Inline `noexcept` ticks implement each stage:

    | Stage | Implementation |
    | --- | --- |
    | Read head | Fixed-point (`uint32` position + Q0.32 fraction) |
    | Interpolation | 4-point Hermite, only when the step has a fraction |
    | Reverse | Mirrored fetch |
    | Ping-pong | Reflection at the loop boundaries |
    | Crossfade | Equal-power overlap, quarter-sine table (see below) |
    | Pan | Equal-power |
    | Envelope | max(user, 96 output frames) |
    | Tone and EQ | Four RBJ biquads (TDF-II) with a per-block denormal flush |

- Stage mask 0 reproduces today's `sample * gain * ramp` exactly.
- **Crossfade is an overlap of the loop with itself.** During the last `X = loop_crossfade_frames` frames of each pass, the tail is blended equal-power with the first `X` frames of the loop, and the next pass resumes at `loop_start + X`. So a looping cycle is `loop length − X` frames long.
  - It needs no material before the loop point, so it works when the loop starts at the sample's first frame.
  - It is why the decision bounds `X` to half the loop.
  - The first pass still starts at the trim start.
- **Frame units.** Every envelope, ramp and end-fade length is counted in engine output frames at the fixed 48 kHz rate the engine, Bank and Content codec accept (`prepared_sample_bank.cpp:462`). The 2 ms floor is therefore always 96 frames, whatever the source rate.
  - The cooker converts `attack_ms`/`release_ms` to 48 kHz output frames.
  - Source-frame fields (`loop_start_frame`, `loop_crossfade_frames`) are rescaled from the source rate to 48 kHz exactly as trim is. The floor is applied after that rescale.

## File Structure

- `docs/prd/decisions/2026-09-30-sample-playback-and-tone-parity.md` — parameter authority.
- `contracts/project/lmdj.project.v5.schema.json` — optional playback keys (5.1.0, then 5.2.0).
- `tests/fixtures/contracts/project-v5-playback-parity-{valid,invalid}.json`, `project-v5-tone-parity-{valid,invalid}.json` — new Contract fixtures. Existing fixtures are unchanged.
- `tests/fixtures/contracts/pad-playback-full.json` — the one cross-layer shape fixture.
- `packages/authoring-domain/{include/lmdj/domain/project.hpp,src/command_handler.cpp}` and `tests/core/domain/command_handler_test.cpp`.
- `packages/project-io/src/project_store.cpp` and `tests/core/project_io/project_store_test.cpp`.
- `packages/project-cooker/{include/lmdj/cooker/runtime_snapshot.hpp,src/project_cooker.cpp,src/runtime_content.cpp}` and `tests/core/cooker/{project_cooker_test,runtime_content_test}.cpp`.
- `packages/audio-runtime/{include/lmdj/audio/detail/voice_dsp.hpp,src/voice_dsp.cpp}` with `tests/core/audio/voice_dsp_test.cpp` (CTest `audio.voice_dsp`, TIER unit) and `tests/core/audio/voice_dsp_parity_test.cpp` (CTest `audio.voice_dsp_parity`, TIER component).
- `packages/audio-runtime/{include/lmdj/audio/realtime_engine.hpp,src/realtime_engine.cpp,src/offline_renderer.cpp,include/lmdj/audio/prepared_sample_bank.hpp}` and their existing tests.
- `packages/application-facade/src/{application.cpp,performance_engine_adapter.cpp}` and a new `tests/core/facade/sample_playback_parity_test.cpp`.
- `apps/core-mcp/lmdj_core_mcp/server.py` with `tests/host/{mcp_stdio_test,mcp_facade_parity_test,cli_test}.py`.
- `packages/web-runtime-platform/{src/control_runtime.cpp,web/protocol.mjs,web/runtime_session.mjs}` and their tests.
- Creator:
  - `apps/creator-web/src/{runtime/runtime_types.ts,state/sample_state.ts,components/sample_controls.tsx,components/waveform_editor.tsx}`
  - new `components/parameter_slider.tsx` and `components/eq_editor.tsx`
  - their Vitest files
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs` — packaged Chromium Proof.
- `docs/quality/2026-MM-DD-sample-playback-parity-acceptance.md` and `docs/quality/2026-MM-DD-sample-tone-parity-acceptance.md` — automated and manual evidence ledgers. The date is the acceptance date.

## Documentation Impact

PR 0 (this plan and the decision):

```text
Documentation impact: none
Reason: only adds a PRD decision record and an implementation plan under docs/; no Architecture Portal page, diagram or projected identity changes.
```

Every later PR declares `Documentation impact: required`:

| PR | Routes |
| --- | --- |
| Contract cuts | `/contracts/project/`, `/assembly/lmdj/`, `/operations/version-and-release/`, plus the immutable snapshot |
| Core PRs | `/contracts/runtime-snapshot/`, `/core/modules/authoring-domain/`, `/core/modules/project-io/`, `/core/modules/project-cooker/`, `/core/modules/audio-runtime/` |
| Host PRs | `/core/modules/application-facade/`, `/core/modules/web-runtime-platform/`, `/hosts/creator-web/`, `/hosts/core-mcp/`, `/product/capability-map/` |

- Source pages live in `apps/docs-site/docs/`.
- Run `scripts/docs-site.sh check` before each commit that touches them.
- The hand-entered "Audio Runtime `3.1.0`" in `apps/docs-site/docs/core/modules/audio-runtime.mdx` §2 is stale. Task 5 corrects it to a derived identity, because the Portal must not hand-enter identities.

## Version Management

Canonical policy: `docs/governance/version-management.md`. All targets below are expected values. They were revised on 2026-10-01 against live `origin/main` at `722ccb80` (Product Build `2.0.70.0`).

- **Why the table was revised.**
  - #1700 closed Milestone 1 at `1.0.66.0`. This train, Web Creator 4-Zone Workflow (#1207 / #1658), is `2.0.*.*`.
  - PR 1 merged as #1697: `lmdj.project.v5` `5.1.0`, Product Build `2.0.70.0`.
  - #1699 consumed several Module identities this table had predicted for the #1666 settle.
- **Before writing any identity:**
  - re-read merged `origin/main`, `products/lmdj/version.json` and every affected manifest;
  - prove the Build is unoccupied the way #761 did;
  - revise this table if any identity was consumed;
  - re-check `products/lmdj/version.json` on `origin/main` immediately before merging. Another Build landed twice while #1697 was in verification.

Each allocating PR writes exactly one column of the table below. Each Build is proved unoccupied separately, at that PR's own tip.

**Revised 2026-10-01.** The table below is the original plan from `1.0.66.0`. #1699 and the M2 train consumed its predicted identities. The PR 4 column was settled as PR 4a at Product Build `2.0.71.0`, on top of the bumps #1699 had already taken: authoring-domain `4.3.0`, project-io `6.0.0` (MAJOR), project-cooker `2.0.0` (MAJOR), audio-runtime `5.1.0`, application-facade `6.4.0`, web-runtime-platform `5.5.0`, creator-web `4.7.0` and core-mcp `3.5.0`. core-cli, native-host, cardputer-host and web-runtime-host each took a PATCH. `lmdj.project.v5` stays `5.1.0` until PR 4b. Re-derive the PR 7 column from live `origin/main` when it is written.

| Identity | Baseline (`2.0.70.0`) | PR 4 (#1666 settle + 5.2.0 cut) | PR 7 (#1667 settle) | Reason |
| --- | --- | --- | --- | --- |
| Product Build | `2.0.70.0` | next free `2.0.*` BUILD | next free `2.0.*` BUILD | Contract and Module identity changes |
| `lmdj.project.v5` | `5.1.0` | `5.2.0` | unchanged | Backward-compatible optional fields, Contract MINOR (§7; precedent `lmdj.project.v4` `4.1.0`) |
| `lmdj.runtime-content.v1` | `1.0.0` | unchanged | unchanged | Encoder refuses non-neutral DSP |
| `authoring-domain` | `4.2.0` | `4.3.0` | `4.4.0` | New playback fields and refusals |
| `project-io` | `5.0.0` | `5.1.0` | `5.2.0` | Optional-key read/write |
| `project-cooker` | `1.2.1` | `1.3.0` | `1.4.0` | `ResolvedVoiceDsp` resolution |
| `audio-runtime` | `5.0.1` | `5.1.0` | `5.2.0` | Shared kernel and new stages |
| `application-facade` | `6.3.0` | `6.4.0` | `6.5.0` | Typed surface accepts new fields |
| `web-runtime-platform` | `5.4.0` | `5.5.0` | `5.6.0` | Transport of new fields |
| `creator-web` | `4.6.0` | `4.7.0` | `4.8.0` | New editor controls |
| `core-mcp` | `3.4.4` | `3.5.0` | `3.6.0` | Tool schema accepts new fields |
| `core-cli`, `native-host`, `web-runtime-host`, `cardputer-host` | current | dependency-propagation PATCH | dependency-propagation PATCH | Exact dependency pins only |

- **Compatibility.**
  - A `5.0.0` reader rejects a Project that uses a new key, by design.
  - A Project that uses none of them is byte-identical and stays readable.
  - No migration is needed, because every legal `5.0.0` file is a legal `5.1.0`/`5.2.0` file.
- **Regeneration.** Regenerate `products/lmdj/assembly.lock.json`, `products/lmdj/src/compiled_assembly.cpp` and `products/lmdj/generated/web-runtime-identity.{json,mjs}` only with their tools, never by hand.
- **Snapshot.** Freeze each allocated Build with `scripts/docs-site.sh version <BUILD> canary`, in the same PR as a separate commit.
- **Tag.** The future tag would be `lmdj-v2.0.<BUILD>.0`. No tag, Release, publication, deployment or Channel promotion is authorized by this plan.
- **Rollback.** Ship a forward corrective Build that keeps the `5.1.0`/`5.2.0` readers. Never downgrade Project Truth or overwrite a workspace with an older artifact.

## Pull Requests

| PR | Branch | Tasks | Closes |
| --- | --- | --- | --- |
| 0 | `docs/sample-parity-decision` | Decision + this plan | — |
| 1 | `feat/project-v5-playback-parity-cut` | 1 | — |
| 2 | `feat/sample-playback-parity-core` | 2–8 | relates #1666 |
| 3 | `feat/sample-playback-parity-creator` | 9–11 | fixes #1666 |
| 4a | `feat/settle-module-versions-2-0-71` | 12 (settle) | — |
| 4b | `feat/project-v5-tone-parity-cut` | 12 (5.2.0 cut, after #1720) | — |
| 5 | `feat/sample-tone-parity-core` | 13–16 | relates #1667 |
| 6 | `feat/sample-tone-parity-creator` | 17–19 | fixes #1667 |
| 7 | `feat/sample-tone-parity-settle` | 20 | — |

Branch prefixes are limited to `feat/`, `fix/` and `docs/` (`docs/governance/git-workflow.md` §2). The cut precedent used `feat/670-project-v4-contract-cut`.

---

### Task 1: Cut `lmdj.project.v5` 5.1.0 with the #1666 playback keys

**Files:**
- `contracts/project/lmdj.project.v5.schema.json`
- `tests/fixtures/contracts/project-v5-playback-parity-{valid,invalid}.json`
- `tests/conformance/schema_contract_test.py`
- `tests/build/version_test.py`
- `products/lmdj/{assembly.json,assembly.lock.json,version.json,src/compiled_assembly.cpp,generated/web-runtime-identity.json,generated/web-runtime-identity.mjs}`
- `apps/docs-site/docs/contracts/project.mdx`
- the Portal snapshot (separate commit)

- [ ] Add the six optional `$defs/playback` properties with the decision's bounds. Keep `additionalProperties: false`. Express the `ping_pong` + crossfade refusal and the null `loop_start_frame`.
- [ ] Valid fixture: every key at a non-default boundary. Invalid fixtures: each bound ±1, `ping_pong` with crossfade, an unknown key. Assert that `project-v5-valid.json` is still valid and unchanged.
- [ ] Run `python3 tests/conformance/schema_contract_test.py`, `python3 tests/build/version_test.py`, `python3 scripts/version.py verify --version-file products/lmdj/version.json` and `scripts/docs-site.sh check`.
- [ ] Commits:
  - `feat(product): cut lmdj.project.v5 5.1.0 and allocate Product Build 1.0.<N>.0`
  - `docs(portal): freeze the immutable 1.0.<N>.0 canary Portal snapshot`

### Task 2: Add the #1666 fields to Authoring Domain

**Files:** `packages/authoring-domain/include/lmdj/domain/project.hpp`, `packages/authoring-domain/src/command_handler.cpp`, `tests/core/domain/command_handler_test.cpp`, `tests/core/domain/project_test.cpp`

- [ ] Add `LoopMode` and the six fields (Locked Interfaces). `valid_playback` (`command_handler.cpp:58-64`) checks every bound, loop start within the trim, crossfade ≤ half the loop, and no `ping_pong` with crossfade.
- [ ] Tests, one fact each: defaults equal `PadPlayback{}`; each bound accepted and each bound ±1 refused with state unchanged (`check_invalid_without_state_change`); reset clears new fields; Assign/Import/Install reset new fields.
- [ ] Run `ctest --preset dev -R 'domain\.'`.
- [ ] Commit: `feat(domain): carry reverse, pitch, pan and loop settings on Pad playback`

### Task 3: Read and write the optional keys in Project I/O

**Files:** `packages/project-io/src/project_store.cpp`, `tests/core/project_io/project_store_test.cpp`

- [ ] `parse_playback` (:588-640) and the `UpdatePadPlayback` transaction decode (:1885-1906) accept the five required keys plus any subset of the new keys; unknown keys stay refused. `playback_json` (:384-395) emits only non-default new keys.
- [ ] Tests:
  - A legacy five-key checkpoint and a five-key transaction log load unchanged.
  - A non-default value round-trips through checkpoint and replay.
  - A default-only Project persists byte-identically to today.
  - An unknown key is still refused.
  - An out-of-range value is refused as `invalid_project`.
- [ ] Run `ctest --preset dev -R 'project_io\.'`.
- [ ] Commit: `feat(project-io): persist optional Pad playback parity keys`

### Task 4: Carry a neutral `ResolvedVoiceDsp` block through the Runtime Snapshot

**Files:**
- `packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp`
- `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`
- `packages/audio-runtime/src/prepared_sample_bank.cpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `packages/project-cooker/src/runtime_content.cpp`
- tests: `tests/core/audio/prepared_sample_bank_test.cpp`, `tests/core/audio/realtime_engine_test.cpp`, `tests/core/cooker/runtime_content_test.cpp`

- [ ] Add `ResolvedVoiceDsp` (all-zero neutral) and `static_assert` its size and trivial copyability. Make `PreparedPatternEvent::operator==` compare it. The engine's `enqueue_control` validation rejects non-neutral values until Task 6. The runtime-content encoder refuses non-neutral values.
- [ ] Tests: a Pattern event differing only in `dsp` compares unequal; a non-neutral press counts `invalid_events`; runtime-content encode of a non-neutral Pad fails with a typed error; `runtime-content-v1.hex` stays byte-identical.
- [ ] Re-prove at this Task's base that nothing serializes, hashes or `memcmp`s `ResolvedPlayback`/`PreparedPatternEvent` as raw bytes. The probe must be able to fire: first confirm that the same grep finds the known field-wise encoder in `runtime_content.cpp` (`.agents/pitfalls/blind-search-reads-as-absence.md`). Any byte-level consumer found must be made field-wise in this Task.
- [ ] Commit: `feat(cooker): carry a neutral voice DSP block in resolved playback`

### Task 5: Add the shared voice DSP kernel (read head, pan)

**Files:** `packages/audio-runtime/include/lmdj/audio/detail/voice_dsp.hpp`, `packages/audio-runtime/src/voice_dsp.cpp`, `packages/audio-runtime/CMakeLists.txt`, the root coverage target list, `tests/core/audio/voice_dsp_test.cpp`, `apps/docs-site/docs/core/modules/audio-runtime.mdx`

- [ ] Implement the stages from Locked Interfaces for #1666.
- [ ] `audio.voice_dsp` (TIER unit) tests, one fact each:
  1. Neutral params give mask 0, and the tick equals `sample*gain*ramp` bit for bit.
  2. Reverse emits `s[end-1]` first and `s[start]` last, with the same length.
  3. +1200 cents halves a one-shot's length (±1 frame); −1200 doubles it.
  4. Pitch 0 in reverse returns exact source values.
  5. Hermite is exact at integer positions and reproduces a linear ramp.
  6. Ping-pong yields …e−2, e−1, e−2… and …ls+1, ls, ls+1…
  7. The first loop pass starts at `start_frame`, and the second pass starts at `loop_start`.
  8. Crossfade satisfies g_in² + g_out² = 1 ± 1e-4 across the window.
  9. Pan −100 gives R == 0.0F; +100 gives L == 0.0F; 0 is passthrough.
  10. Under pitch, the last 96 output frames ramp to 0.
- [ ] In `apps/docs-site/docs/core/modules/audio-runtime.mdx`:
  - describe the kernel;
  - replace the hand-entered "Audio Runtime `3.1.0`" in §2 with the Portal's derived identity;
  - run `scripts/docs-site.sh check`.
- [ ] Commit: `feat(audio): add the shared voice DSP kernel`

### Task 6: Render realtime voices through the kernel

**Files:** `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`, `packages/audio-runtime/src/realtime_engine.cpp`, `packages/application-facade/src/performance_engine_adapter.cpp`, `tests/core/audio/realtime_engine_test.cpp`, `tests/core/audio/master_fx_allocation_guard_test.cpp`

- [ ] Commit 6a, `refactor(audio): render realtime voices through the voice DSP kernel`.
  - Move voice state into `VoiceDspState`: `Voice` (hpp:717-738), triggers (:2176-2194, :495-542), render (:2262-2340), `stop_voice` (:572-599).
  - Every existing exact ramp, loop, gate and toggle assertion must pass unmodified.
- [ ] Commit 6b, `feat(audio): play reverse, pitch, pan and loop modes in realtime`.
  - Lift the Task 4 rejection.
  - Bank press, `preview_set`, Pattern voices and Replay (`performance_engine_adapter.cpp:64-69, 539-563`) carry `dsp`.
  - Reverse publishes the physical `source_frame`.
  - Add `render_with_all_voice_stages_does_not_allocate`; its trigger must fall inside the counted window.
  - Extend the allocation guard scan to `voice_dsp.cpp`.
- [ ] Run `scripts/core.sh test dev fast`, then `ctest --preset dev -R 'audio\.'`.

### Task 7: Render non-neutral voices offline through the kernel

**Files:** `packages/audio-runtime/src/offline_renderer.cpp`, `packages/audio-runtime/CMakeLists.txt`, the coverage list, `tests/core/audio/offline_renderer_test.cpp`, `tests/core/audio/voice_dsp_parity_test.cpp`

- [ ] Neutral events keep the integer loop (:212-263) byte for byte. Non-neutral events render through the kernel in float, quantize by the inverse of `prepared_pcm16_to_float`, and `saturating_add` in snapshot order.
- [ ] Tests:
  - The golden is unchanged.
  - An explicit all-zero `dsp` gives identical bytes.
  - With only the snare at pan −100, every kick-only frame equals the golden.
  - `audio.voice_dsp_parity` (component): a mono non-neutral event matches realtime within 1 PCM16 LSB.
- [ ] Commit: `feat(audio): render non-neutral voices offline through the kernel`

### Task 8: Resolve the #1666 fields in Project Cooker and bound the realtime cost

**Files:** `packages/project-cooker/src/project_cooker.cpp`, `tests/core/cooker/project_cooker_test.cpp`, `tests/core/audio/master_fx_stress_test.cpp`, the Portal pages for the Core PR routes

- [ ] Commit 8a, `feat(cooker): resolve Pad reverse, pitch, pan and loop settings`.
  - `resolve_playback` (:197-261) rescales loop start and crossfade to 48 kHz as it does trim, clamps the crossfade, and bounds the rate.
  - Tests: 44.1 kHz source offsets rescale exactly; defaults resolve to a neutral block.
- [ ] Commit 8b, `test(audio): bound 128 kernel voices within the callback deadline`.
  - 128 voices, every stage on including crossfade loops, 128 triggers in one callback.
  - Zero unattributed overruns under the existing deadline.
- [ ] Run PR 2 verification (below).

### Task 9: Accept the #1666 fields in the Facade, CLI and MCP

**Files:** `packages/application-facade/src/application.cpp`, `tests/core/facade/sample_playback_parity_test.cpp` (new binary), CMake registration, `apps/core-mcp/lmdj_core_mcp/server.py`, `tests/host/{mcp_stdio_test,mcp_facade_parity_test,cli_test}.py`, `tests/fixtures/contracts/pad-playback-full.json`

- [ ] `playback_value`/`playback_json` (:494-592) apply the missing-means-default rule. `update_sample_pad` checks `loop_start_frame` against the WAV frame count.
- [ ] Tests: update, inspect and replay round-trip of `pad-playback-full.json`; each refusal is typed; a default inspect omits every new key; the MCP tool schema admits the fixture and refuses an unknown key.
- [ ] Commit: `feat(facade): accept Pad reverse, pitch, pan and loop settings`

### Task 10: Carry the fields through Web Runtime Platform and Creator state

**Files:** `packages/web-runtime-platform/{src/control_runtime.cpp,web/protocol.mjs,web/runtime_session.mjs}`, `packages/web-runtime-platform/test/{control_runtime_test.cpp,protocol.test.mjs,runtime_session.test.mjs}`, `apps/creator-web/src/{runtime/runtime_types.ts,state/sample_state.ts,components/waveform_editor.tsx}`, `apps/creator-web/test/{sample_state,sample_actions}.test.ts`

- [ ] Commit 10a, `feat(web-runtime): carry Pad playback parity keys`.
  - `playback_value` (:207-243) learns the new keys.
  - `resolve_preview_playback` (:2001-2055) calls the cooker's resolution instead of duplicating it.
  - `validPlayback`, `wirePlayback` and `normalizePlayback` (:292-355) learn the keys.
  - Every copy is asserted against `pad-playback-full.json`.
- [ ] Commit 10b, `feat(creator): keep Pad playback parity keys in Sample state`.
  - Update `validatePlayback`, `DEFAULT_PLAYBACK`, `playbackEquals`, the `updateSampleDraft` keys and `samePlayback`.
  - Assert against the same fixture.

### Task 11: Creator controls, waveform markers, Proof and acceptance

**Files:** `apps/creator-web/src/components/{parameter_slider.tsx,sample_controls.tsx,waveform_editor.tsx}`, `apps/creator-web/src/state/sample_state.ts`, their Vitest files, `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`, `docs/quality/2026-MM-DD-sample-playback-parity-acceptance.md`, Host PR Portal pages

- [ ] Commit 11a, `feat(creator): edit reverse, pitch, pan and loop mode on the Sample page`.
  - Extract the Volume `{base, latest}` gesture (`sample_controls.tsx:104-137, 203-228`) into `ParameterSlider`; Volume, Pitch and Pan reuse it.
  - Reverse is an `aria-pressed` button.
  - Loop mode is a segmented control shown only when Loop is on.
  - Drag previews through `sample.preview.set`, release commits, and Escape cancels.
  - Touch targets are at least 44 px.
- [ ] Commit 11b, `feat(creator): draw the loop point and crossfade on the waveform`.
  - Use `frameToX` and the grip-zone pattern in the SVG (:398-432), with keyboard steps.
  - The playhead (`sample_state.ts:1163-1180`) follows reverse and ping-pong.
- [ ] Commit 11c, `test(creator): prove Sample playback parity in the packaged Creator`. The spec covers every path, each with a far-side assertion:
  - normal: set and commit each control;
  - reopened: values survive a Project reopen;
  - cancelled: Escape restores the base;
  - refused: `REVISION_CONFLICT` and a raw out-of-range payload;
  - failed: a runtime failure is reported without a Project Truth change.
  - PCM-level check: pan −100 leaves the right channel below −60 dBFS, using the sampling approach of `creator_web_perform.spec.mjs:813-821`.
- [ ] Commit 11d, `docs(creator): record Sample playback parity acceptance`.
  - The ledger lists which automated lanes ran and the manual hearing rows (macOS Chrome, macOS Safari, iPad Air 13″ M3). Rows that did not run are marked as not run.
  - Heed `.agents/pitfalls/short-loop-hearing-misclassification.md` for ping-pong and crossfade checks.

### Task 12: Settle #1666 and cut `lmdj.project.v5` 5.2.0

**Revised 2026-10-01 (owner order: settle, then #1720, then #1667).** Task 12 is split:

- The settle lands alone as PR 4a, `feat/settle-module-versions-2-0-71`, Product Build `2.0.71.0`. It settles every Module identity owed since `2.0.69.0`: #1666's (#1717, #1735) and the concurrent Creator workflow PRs' (#1707, #1708, #1711, #1714, #1716, #1727, #1734). The owner chose MAJOR for project-io (`6.0.0`, the #1699 persistence precedent) and for project-cooker (`2.0.0`, `ResolvedPlayback` lost aggregate initialisation).
- The `5.2.0` cut moves to PR 4b, opened only after #1720. #1667's Pad fields grow wasm32 `ProjectState` again, so its Web stack budget must be fixed or re-measured first (pitfall `web-project-io-stack-scales-with-project-state`).

**Files (4b):** as Task 1, plus `tests/fixtures/contracts/project-v5-tone-parity-{valid,invalid}.json`

- [x] Settle the #1666 Module SemVer (PR 4a, `2.0.71.0`).
- [ ] Add the #1667 optional keys to the schema: `attack_ms`, `release_ms`, `tone`, `eq` with `kind`, `freq_hz`, `gain_millidb` and `q_milli`.
- [ ] Allocate one Product Build and freeze its snapshot as a separate commit.

### Tasks 13–16: #1667 Core (envelope, tone, EQ)

Task 13 through Task 16 mirror Tasks 2–8 for the #1667 fields. Each keeps the neutral-identical constraint.

- **Task 13 (domain and Project I/O):** `feat(domain): carry attack, release, tone and EQ on Pad playback`, then `feat(project-io): persist optional Pad tone parity keys`.
- **Task 14:** `feat(audio): add user attack and release envelopes`.
  - The envelope is max(user, 96 frames), in realtime and offline.
  - Release-tail voices keep occupying capacity and report `voice_capacity` when full.
  - Tests: attack of 480 frames reaches exactly 1.0 at frame 480; attack ≤ 96 matches today; the release tail is max(R, 96) frames and ends at exactly 0; one-shot ignores pad release.
- **Task 15:** `feat(audio): add the per-Pad tone filter and 3-band EQ`. Tests:
  - tone −100 attenuates a 10 kHz sine by ≥ 40 dB, within 1 dB at 100 Hz; tone +100 is the mirror image;
  - the deadband is bit-identical;
  - bell +12 dB at 1 kHz with Q 1 measures 12 ± 0.1 dB;
  - low `cut` is −3 dB at fc as a high-pass, and high `cut` likewise as a low-pass;
  - 10 s of extreme-setting noise stays finite and flushes to 0 after the input stops;
  - the parity test is extended.
- **Task 16:** `feat(cooker): resolve envelope, tone and EQ settings`, then `test(audio): extend the stress and allocation tests to every voice stage`.
  - Record `sizeof(RealtimeEngine)` on the Cardputer target ABI against the measured 26 281 B headroom.
  - If it exceeds the headroom, switch each voice to a `const` coefficient pointer into Bank-owned tables in this Task. Do not cut Cardputer voices or relax the check.

### Tasks 17–19: #1667 Host and Creator

Task 17 through Task 19 mirror Tasks 9–11:

- Task 17: Facade, CLI and MCP.
- Task 18: Web Runtime Platform and Creator state.
- Task 19: Creator controls and acceptance.
  - Attack, Release and Tone reuse `ParameterSlider`; Tone is bipolar.
  - The new `eq_editor.tsx` draws three SVG poles. Horizontal drag sets frequency, vertical drag sets gain, and dragging to the bottom sets `kind: cut` on the shelves. Double-tap followed by a vertical drag sets Q. Keyboard equivalents are provided.
  - The Proof covers every path.
  - PCM check: tone −100 attenuates a bright source.

### Task 20: Settle #1667

- [ ] Settle the #1667 Module SemVer.
- [ ] Allocate one Product Build and freeze its snapshot as a separate commit.

## Verification

**Core PRs (1, 2, 4, 5):**
- `scripts/core.sh build dev && scripts/core.sh test dev` (full tier).
- `scripts/core.sh test dev stress`, because the kernel is realtime code.
- `scripts/core.sh coverage check` with no floor lowered.
- `python3 tests/conformance/schema_contract_test.py`
- `python3 tests/conformance/runtime_content_contract_test.py`
- `python3 tests/build/version_test.py`
- `bash tests/build/test_active_tree.sh`
- `bash scripts/verify-core-dependencies.sh`
- `scripts/docs-site.sh check`

**Host PRs (3, 6):** the Core set plus:
- Creator Vitest
- `packages/web-runtime-platform` node tests
- `scripts/web-runtime-host.sh proof`
- `scripts/creator-web.sh proof`

**Every PR:**
- `scripts/local-ci.sh --list` to see the selected lanes.
- `scripts/local-ci.sh --pr-body body.md` to check the PR body.
- A green local run is advisory and authorizes nothing.

## Requirement-to-Task Coverage

| Requirement | Tasks |
| --- | --- |
| Pitch authority reconciled with 2026-08-26 D2 | Decision record |
| Optional keys, defaults equal today, old files unchanged | 1, 3, 9, 10, 12, 13 |
| Reverse, pitch, pan, loop point, ping-pong, crossfade audible | 5, 6, 7, 8, 11 |
| Attack, release, tone, 3-band EQ audible | 14, 15, 16, 19 |
| Persisted and reproduced after reopen | 3, 11, 13, 19 |
| normal / refused / failed / cancelled / reopened observable | 2, 9, 11, 17, 19 |
| Realtime and offline render the same DSP | 5, 6, 7, 14, 15 |
| Realtime budgets hold with every stage on | 8, 16 |
| Cardputer refuses non-neutral DSP, memory measured | 4, 16 |
| Every `PadPlayback` copy agrees | 9, 10, 17, 18 |
| Declared tests and devices, manual hearing | 11, 19 |
| Identities, Build allocation, Portal snapshot | 1, 12, 20 |

## Pull Request and Completion Boundary

- Each PR is shipped with `.agents/skills/issue-done/SKILL.md`, and records or bumps any qualifying pitfall before merge.
- Tasks 1 and 12 allocate a Product Build. An allocation is not a release.
- Automated green plus the canary snapshot permits implementation review only. It does not claim physical pass, Beta, Stable, Release, publication or deployment.
- A follow-up issue for Cardputer support of the new parameters is opened when Task 4 lands, and linked from #1666.
