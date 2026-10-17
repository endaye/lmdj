# Creator #2112 PR stack

Date: 2026-10-17
Parent: #2112. First feature: #2232 (Creator COUNT-IN / S7).

## Authority and integration boundary

The user authorized continuing #2112 development as a stack of PRs while the
current main release and deployments finish. This turn authorizes implementation,
verification, Conventional Commits, branch pushes and PR creation. It excludes
merging into main, automatic merging, release, deployment and resource cleanup.
Keep every layer a Draft PR during this hold. A branch push or a passing test
does not end the hold.

Use ordinary Git branches with explicit PR bases: the first layer targets main;
each later layer targets the preceding branch. This is a dependency chain, not
GitHub native stack metadata or a Graphite submission. Each layer has its own
isolated worktree, declared files and Task verification. The user's instruction
permits dependent branches to start from their predecessor instead of main.
No global Git/CI governance or protection is changed for this work.

The starting main and first Task base are
`e47b02510ef144a518163978d42b44b50558d36b`. The stack coordinator owns base
changes. Preserve published history and other worktrees; cascading rebases need
explicit coordination and current-head evidence. After a future authorized
squash, rebase descendants onto the actual introducing main commit and verify
the resulting changes before considering the next merge.

## Refreshed premises

- S6 scheduled recording is delivered by #2202 and the terminal-owner follow-up
  by #2223. Import is delivered by #2266; #2225 is closed. Do not implement those
  again. The remaining Pattern order is S7 (#2232), S3 (#2233), S5 (#2234).
- `apps/creator-web/src/state/seq_snap_preference.ts` and
  `test/seq_snap_preference.test.ts` are a positive control for a device-only
  IndexedDB preference: database `lmdj.creator.host`, store `settings`, serialized
  writes, bounded reads, exact-value validation and default fallback.
- At the pinned base, the state directory and App's preference imports/effects
  have no COUNT-IN preference module or consumer. The Sequence SETUP controls
  expose SEQ SNAP and METRONOME. S7 must add its own numeric `0 | 1 | 2` preference
  at `count-in.v1`; the existing native capability is not this UI delivery.
- The current PR review target and receipt validators require a main-target
  non-draft PR (`.github/scripts/pr_review_target.py`,
  `scripts/ci/review_scope.py`, `scripts/ci/review_wait.py`). Upper-layer or Draft
  checks cannot be reported as eligible independent review. Record review as
  pending, preserve findings, and obtain valid current-head independent review
  before any future merge. This feature stack does not adapt CI control code.
- Original device/listening requirements and complete count-in acceptance remain
  attached to #2232 and #1221. Layer completion is not Issue closure.

## Layer 1 — COUNT-IN preference persistence

Branch: `feat/creator-count-in-preference`; PR base: `main`.
One Task / one Conventional Commit. Partial delivery of #2232.

Declared files:

- `apps/creator-web/src/state/count_in_preference.ts` (new)
- `apps/creator-web/test/count_in_preference.test.ts` (new)
- `docs/plans/2026-10-17-creator-2112-pr-stack.md` (new)

Deliver a Host-only numeric Off/1/2 preference, default Off, in the existing
IndexedDB settings database under `count-in.v1`. Exact numeric values round-trip;
unavailable, corrupt and unreadable storage falls back to Off. Writes serialize
and settle only after the transaction commits or fails. A read waits for earlier
writes but has the existing five-second boot bound. Other settings remain intact.
No Project Truth, UI control, recording request or metronome behavior changes in
this layer; these require the next consumer Task.

Lowest-tier verification:

- Existing SEQ SNAP preference tests on the unchanged base establish the local
  harness. New COUNT-IN tests assert exact raw IndexedDB key/value, committed
  round-trips, corrupt/default/error boundaries, rapid writes, read-after-write,
  transaction settlement and preservation of other settings. Raw store reads are
  the independent oracle for storage identity and numeric encoding.
- `npm --prefix apps/creator-web test -- run test/count_in_preference.test.ts
  test/seq_snap_preference.test.ts test/metronome_preference.test.ts
  test/last_project.test.ts` covers the shared settings database's existing users.
- From `apps/creator-web`, `npx --no-install tsc --noEmit -p tsconfig.json`
  verifies the new Host source against the actual TypeScript project.
- After staging, `python3 tests/build/ci_change_scope_test.py` verifies new-path
  ownership; inspect `git diff --cached --check` and the exact staged inventory.
- On the committed clean head, `scripts/local-ci.sh --base-ref origin/main
  --list --json` classifies the complete range. PR body lint and the declaration
  check validate the actual PR body before publication.

No new required gate is added. The new tests catch a wrong persisted choice,
setting-key collision, failed-write queue poisoning or an early durability claim.
No Core/Wasm/browser/device result is claimed for this unconsumed utility.

## Layer 2 — native metronome downbeat capability

Branch: `feat/count-in-metronome-bridge`; PR base:
`feat/creator-count-in-preference` at
`101b7a46de9673fb86d9b1b4b03c9dfb891723b9` (#2342).
One Task / one Conventional Commit. This is the S7 prerequisite exposed during
the consumer audit, not completion of the Creator interaction.

Main refreshed to `27480057a33ca40615da8d72c2b9a54134d15ea4`: intervening product
identities, CI and a workspace test fix do not deliver this capability. The stack
retains its existing base and isolated source/build roots.

At the stack base, `RealtimeEngine::set_count_in_metronome` already publishes an
atomic flag read at actual scheduled S. Its existing native tests exercise the
optional accented downbeat, and the design explicitly assigns its direct
capability to S7. The authoritative adapter declaration, Bridge exports, CMake
export inventory, pre-JS Host object, frozen Session and SDK declaration expose
the two-output startup but no metronome setter. Therefore a Creator toggle cannot
yet select the native S downbeat. Preserve the existing native clock/ownership;
add a synchronous monitoring capability rather than a queued RPC or JS-timed cue.

Declared files:

- `packages/audio-runtime/include/lmdj/audio/web/realtime_audio_worklet.hpp`
- `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`
- `packages/web-runtime-platform/CMakeLists.txt`
- `packages/web-runtime-platform/src/bridge.cpp`
- `packages/web-runtime-platform/src/web-runtime-pre.js`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `packages/web-runtime-platform/test/runtime_loader.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `tests/platform/web/creator/creator_web_count_in.spec.mjs`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `docs/plans/2026-10-17-creator-2112-pr-stack.md`

Public SDK: `setCountInMetronome(enabled: boolean): void`. It synchronously
publishes through the Runtime's direct native export. Invalid arguments are
rejected before Native; unsupported/legacy output, inactive/closing Session and
unavailable Native owner are explicit refusals. It never dispatches a Host RPC,
opens authoring state or replaces the ordinary metronome scheduler. The adapter
accepts only the browser main thread, a ready two-output graph and a paused/open
gate; Native owns the actual S sampling and audio envelope.

Lowest-tier verification and defect oracles:

- Full existing runtime loader/Session Node selections as baseline and after the
  change; direct-call tests cover boolean encoding, unsupported/refused owner,
  lifecycle and synchronous completion while an unrelated RPC remains pending.
- Existing real packaged count-in PCM scenarios retain every leg. Add an On
  scenario through the public setter: four/eight forced cues plus exactly one
  analytic accented cue at S; Off scenarios retain silence at S on cue output.
  Native/output PCM is the independent oracle, not a setter return or UI value.
- Rebuild the ordinary Creator Wasm/UI package with the pinned toolchain before
  running its unchanged count-in selection plus the On scenario. Keep actual
  start/cancel/Stop, Truth/reopen, capture and failure assertions intact.
- The package entry point requires a clean source commit. First pass the owning
  Node, TypeScript, Wasm compile/link, Portal and staged-path checks; freeze the
  local Task commit, then package and run the real browser selection on that
  exact clean head before pushing or creating its Draft PR. A failed packaged
  journey remains a finding; fix and reverify the unpublished head before push.
- Full owning Portal check, SDK/Creator TypeScript and staged ownership/diff
  checks. The committed stack range and this layer's parent range are classified
  separately before push. PR lint/declaration validate the real Draft body.

Version impact: additive API debt for Web Runtime Platform and Audio Runtime
(new nonvirtual adapter method; no layout/vtable or persisted Contract change).
Record MINOR debt; manifests/Product allocation remain for #2237.
Documentation impact: required — `/core/modules/audio-runtime/`,
`/core/modules/web-runtime-platform/`, `/platform/web-runtime/`.
No new gate, budget increase or concurrency protocol is introduced. Complete
Creator S7 controls/handoff and physical listening acceptance remain outstanding.

### Layer 2 source verification

- Live main rechecked before the local source commit: still `27480057a33ca40615da8d72c2b9a54134d15ea4`.
- Runtime loader/Session baseline: 419/419 PASS. Final owning selection:
  424/424 PASS. The first new loader test lacked a browser timer in its fixture;
  it failed at `window.clearTimeout`, then passed using the existing complete
  deadline-transport fixture. No product branch or assertion was weakened.
- Creator TypeScript PASS; ordinary Wasm/UI compile and link PASS with pinned
  Emscripten 6.0.5 and Node 26. Native Core CLI target compiled for the exact
  proof fixture generator; its two packed Project outputs compare identically.
- Full Portal check: 179/179 PASS, 50 routes/internal links valid. Staged path
  ownership: 76/76 PASS; all 14 files match the declared scope.
- The initial package command refused the dirty source as designed. It produced
  no packaged/browser PASS. Freeze the verified source locally, then package
  and retain the actual PCM/recording/cancellation results before any push.
  Those exact-head results belong to the PR evidence, not a predicted receipt.

## Subsequent layers

1. Complete S7 over Layer 1: wire late-hydration protection, SETUP Off/1/2,
   stopped-only scheduled recording, cancellation settlement, BPM/Pattern locks,
   playable Pad Press/Release, truthful status/Record lamp and native cue to JS
   metronome handoff. Before editing, refresh the public S6 API and freeze the
   exact App/state/controls/overview/metronome/tests/Portal file list. Keep every
   Record/cue/applied-or-cancel/Stop/Truth/reopen/PCM journey leg.
2. S3 starts with its recording-segment design addendum, then separately verified
   producer and consumer Tasks. S5 follows with actual cross-Pattern phase
   publication; a UI enum is not delivery. Freeze each Task's files and lowest
   tests at its actual predecessor head.
3. ASSIGN, BPM I2b then I2c, meter, capture/WAV duration and remaining UI Tasks
   join the same stack at declared, verified boundaries. Check shared App,
   Sequence, Sample, Perform, SDK and Portal ownership before each layer.
4. Keep version debt per Task. The historical settlement #2247/#2274 is already
   delivered. Final Product allocation/snapshot #2237 requires the formal
   verified-main candidate process after implementation integration; do not
   allocate a release identity from unmerged stack code. #1221 retains the final
   same-candidate 35-screen, device and listening acceptance.

This is the integration order, not a claim that later layers have started or
that their exact implementation files have been approved by an earlier draft.

## Version Management

Version impact: none for Layer 1 — an unconsumed, Host-internal preference utility
with no public API, dependency, manifest, persisted Project Contract or Product
identity change. The existing Host settings database schema version is unchanged.
Later user-visible S7 behavior assesses Creator Host version impact in that Task;
all further module/API/ABI debts are recorded at their actual layers.

## Documentation Impact

Documentation impact: none for Layer 1 — current product/Portal behavior is
unchanged; this implementation plan and internal preference utility have no
Portal projection. The consuming S7 layer must update `/hosts/creator-web/`,
`/hosts/creator-interactions/` and `/platform/input/` for its actual behavior and
run the owning Portal check. Product allocation retains its snapshot obligation.

## Pitfall Impact

Pitfall impact: none — new behavior is specified by its preference tests. Follow
the existing async-assertion and far-side evidence guidance; no new process
failure is established by this Task.

## Execution evidence

- Base rechecked before commit: live main remains
  `e47b02510ef144a518163978d42b44b50558d36b`.
- Unchanged baseline: the SEQ SNAP, metronome and last-Project preference suites
  passed 21/21. With the new COUNT-IN suite, the same four-file selection passes
  52/52 (31 new tests). TypeScript `tsc --noEmit` passes.
- Independent-key proof: temporarily changed the implementation key to
  `count-in.v2` in a separate Vitest process. All three approved-key assertions
  failed at the raw `count-in.v1` read (undefined rather than numeric 0/1/2).
  Restored the source with a fresh mtime and reran the complete four-file
  selection: 52/52 passed. The targeted mutant selected three tests and left
  the other tests unselected; that run is deliberate negative evidence.
- Staged-path ownership passes 76/76, including explicit ownership and top-level
  admission for all three new paths. Final committed-range classification, PR
  publication and current-head review are recorded separately after their results.
  Packaged browser, full Creator proof, Core, Portal and physical acceptance have
  not run for this unconsumed utility. The full S7 user journey remains open.
- main remains outside this turn's merge authority.
