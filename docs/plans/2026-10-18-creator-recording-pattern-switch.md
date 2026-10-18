# Creator recording Pattern switches (S3 C4)

Parent: #2112 / #2233. One atomic implementation Task above Host Draft #2373.

## Authority and refreshed premises

- Integration main inspected at `06d6c41e582e62f894330fbd9f2b4419d366e326`;
  actual stack parent `3f74388b1c3844d8ada726dad470a35520a674e8`
  (`feat/recording-switch-host`). The only intervening main commit is the
  separate Product allocation #2372; it changes identities/snapshot, not these
  producer/consumer gates. Current main governance matches the parent.
- C2c #2365 / `aa476632` is merged. C3 #2373 is verified, pushed and Draft;
  do not repeat Core/Native/Host implementation. Its retained publication,
  actual S, original COUNT-IN and I/O failure/ACK paths are the producer.
- Still outstanding: App `selectSequencePattern` refuses every active COUNT-IN
  and all global recording; physical arrows also inherit settings locks;
  Sequence picker and ordinary Perform Launch explicitly refuse recording.
  Playing non-recording requests are the positive control at the same sites.
- COUNT-IN's `recording` phase begins at actual Applied before opening ACK.
  Enable selection only after openingComplete, no openingPending, error,
  cancellation or settlement. Keep original ticket/e1/e2/S0/Native downbeat.
- Reuse current SDK request/SNAP and current/pending follow. No optimistic
  selected/Truth mutation, queued auto-retry, second Journal kind or new clock.
  Existing active Sequence/Performance Journal exclusion remains authoritative.
- No successor consumer PR exists in the refreshed open inventory (#2373 and
  unrelated release witness #2374). Recheck before commit, preserve other work.

Pre-commit refresh: main `760fb5ab989c48eb569b8a7ea646a4417fe21039` adds only
#2374's immutable Product snapshot squash witness after #2372. Neither changes
Creator, Host producer, Task tests or governance; all premises remain. Live
#2112/#2233/#2237 remain OPEN, archived umbrella comments unchanged, no consumer
successor; #2373 is the sole open PR and remains the Draft stack parent. The
owner freeze persists regardless of external release progress.

## Implementation and declared files

One Conventional Commit: `feat(creator): switch Patterns during recording`.
Only the following paths belong to this Task:

- `docs/plans/2026-10-18-creator-recording-pattern-switch.md`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/runtime/count_in_controller.ts`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/state/error_messages.ts`
- `apps/creator-web/test/count_in_controller.test.ts`
- `apps/creator-web/test/sequence_surface.test.tsx`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/creator-web/test/error_messages.test.ts`
- `tests/platform/web/creator/creator_web_recording_switch.spec.mjs`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/diagrams/web-runtime-platform.architecture.json`
- `apps/docs-site/static/diagrams/web-runtime-platform.html`
- `apps/docs-site/static/diagrams/web-runtime-platform.svg`

Selection readiness is distinct from grid/structure/BPM authoring readiness.
The handler rechecks live COUNT-IN state at the gesture; render-time eligibility
cannot authorize a late gesture during cancellation. Busy switch refusals retain
actual current/queued projection, use an explicit retry message, and never
silently retry a rejected musical intention. Stop/release stay serviceable.

## Verification and far-side acceptance

- Lowest tier: pure/controller eligibility cases for all COUNT-IN phases,
  Applied-before-opening, errors and original caller ownership. Component tests
  prove picker and ordinary Launch callbacks while recording, all former
  settings/grid/structure locks, busy/cancel/unknown closure; old Performance
  recording Launch stays its original clock/event producer.
- Mounted App journeys prove arrows/GROOVE/ordinary Perform Launch share the
  existing selected SNAP request, queued/actual UI remains authoritative,
  refusal never changes selection or auto-replays, and opening/cancel gates
  read current state. Preserve every existing S7/ordinary recording journey.
- Fresh Wasm/UI/package from this exact source; packaged Chromium repeated
  mixed-source A -> B -> A for immediate and COUNT-IN recording. Observe every
  request, queued target, real applied S/current/origin and original input
  authority. Keep source and exact S/post-S input, crossing Press/Release,
  Record-off/Stop, complete per-Pattern Truth, all unchanged fields and fresh
  reopen; original S7 and snapshot/recovery/Performance checks remain selected.
- Held I/O/third-publication and material refusal acceptance retains real
  producer barriers/owning evidence from C3; test seam may observe/hold the real
  I/O executor, never fake production receipts or rewrite successful state.
- Pre-commit: owning UI tests/TypeScript, dependencies, diagrams/Portal and
  staged ownership. The genuine Creator packager refuses any dirty Git tree,
  so build UI/Wasm first, commit the locally verified source, then package and
  run clean exact-head journeys before push/PR/Task completion. Preserve the
  initial expected dirty-tree package refusal; never bypass its provenance gate.
  Post-commit: rebuilt packaged journeys, existing S7 and relevant ordinary
  recording/Performance/recovery suites, dependencies,
  ownership (staged and committed new paths), official diagrams and full Portal.
  Record actual commands, exit statuses and deferred candidate/device facts.
- A meaningful regression/mutation must fail inside its owning test; save WIP,
  restore current bytes/fresh mtime and read actual restored rebuild/test exit.
  No timeout/threshold/coverage/lane/journey reduction. No CI controls changed.

## Version Management

Creator Host additive feature: MINOR debt to #2237, deduplicated with the same
compatibility domain. No Product Build, manifest, Contract/Journal format,
Provider, Channel or immutable snapshot identity allocated in this Task. Stack
inherits its explicit parent identities until the separate version Task.

## Documentation Impact

Documentation impact: required.
Affected portal pages: `/hosts/creator-interactions/`, `/hosts/creator-web/`,
`/platform/web-runtime/`. Update source facts and official Web Runtime diagram
in the same Task. Do not erase S6 raw PCM, #1221 candidate, device/listening or
unexecuted platform debt. Run `scripts/docs-site.sh check` before commit.

## Shipping boundary

Owner froze main during release. Continue commit/push/Draft only in ONE stack:
this PR targets `feat/recording-switch-host`, never main directly. No merge,
auto-merge, release, Runtime deployment, Channel promotion or Git cleanup.
Independent current-head review remains pending under Draft/non-main exclusion;
no waiver is implied. Only explicit owner unfreeze permits later per-layer
retarget/review/protection/merge. #2233/#2112 stay open pending full acceptance.

## Results

Pre-commit local source verification:

- Complete Creator Vitest: 79 files / 1785 tests PASS (94.80s); offline Node
  6/6 PASS; TypeScript PASS. This includes all existing ordinary recording,
  Performance, recovery and S7 UI tests. Five focused mounted recording/SNAP/
  opening/refusal journeys additionally PASS, without bypassing the SDK seam.
- Removing the openingPending/openingComplete eligibility guard produces an
  actual failure inside the controller's durable-opening regression. Saved WIP
  restored byte-identically with fresh mtime; all 40 controller tests PASS.
  Earlier old-gate regressions fail at the picker and ordinary Launch disabled
  assertions. The first mounted reduction had an incorrect aria-pressed read
  (the real key uses is-active); its test-fixture failure is retained separately.
- Fresh pinned Emscripten 6.0.5 / Node 26 Wasm and TypeScript/Vite UI build PASS.
  The genuine packager then refuses this dirty source tree, as designed. This
  nonzero package result is retained; it is not a product build failure or PASS.
  Clean-source package and actual browser journeys follow the source commit.
- Official diagrams PASS. Full Portal check: 179 tests, production site build,
  50 routes/internal links PASS; source facts and S6/candidate/device debt remain
  separate. Core offline dependency verification PASS. No new native binary,
  Core source, CI control, budget or manifest change.

Post-commit package/three multi-switch Chromium journeys, original packaged S7
and relevant recording/Performance/recovery paths remain pending. No prior
artifact, historical producer result, or ownership selection substitutes for
these actual consumer runs. This Task is not yet ready to push or complete.
Main freeze, pending Draft review and all physical acceptance boundaries persist.

### Packaged reductions and terminal projection correction

The first local source commit was made after the pre-commit source checks, as
required by the genuine packager's clean-source gate; nothing has been pushed.
All revisions remain one atomic Task, with pre-amend recovery refs retained.

- The first three browser failures were a setup error: direct public-Host
  authoring advanced Truth before a UI create using the older App revision.
  Reload the Project before UI authoring, then observe the actual Pattern count.
  The guard correctly refused the stale request; no product guard was relaxed.
- A response trace entry exists before its asynchronous reply. Wait for that
  exact real response before asserting; preserve the original one-second RPC
  budget. Ordinary recording's Native input has no scheduled authority, while
  the Core fence still durably admits it. Assert the exact null Native stamp,
  real retained=true and complete Truth separately. COUNT-IN preserves its exact
  original scheduled stamp. Do not require a fabricated scheduled authority.
- Claimed recording overlays actually refuse before publication. Keep the real
  refusal, prove no automatic replay, and retry through a new explicit UI
  gesture after actual progress. Source late Release is physically consumed with
  retained=false after its prefix already committed; require release_applied,
  original hold identity, complete settlement and no target event. New target
  input still requires retained=true. A real loop-Gate asset prevents natural
  sample expiry from standing in for physical release.
- Immediate and COUNT-IN A-B-A now pass their complete new packaged journeys.
  The third A-B-A-B journey reaches exact committed Truth, then exposes a real
  consumer race: the COUNT-IN caller has positively consumed, but still owns
  final ordinary projection. Play remained enabled and replayed the stale
  original Record-off cancellation, receiving consumed-ticket refusal instead
  of an ordinary Stop on actual B. Two deterministic controller/mounted tests
  reproduce this with the projection deliberately held.
- Fix: keep Record/Play disabled in terminal settling, and refuse cancellation
  replay synchronously in that phase. Preserve original ownership until its
  projection completes; only then can the next gesture send ordinary epoch 3.
  Preparing/counting/cancelling reachability, actual input/release and all
  original request identities remain. Re-run all owning UI/TypeScript, new
  packaged journeys and original S7 before declaring this correction verified.

Terminal correction pre-amend verification: 79 UI files / 1787 tests PASS
(85.96s), then both deterministic terminal-projection reductions PASS after the
fix. TypeScript PASS after expressing the fixture's public transport return type
instead of its narrower initial literal; that initial type-check failure remains
recorded. Offline Node 6/6 PASS. Full Portal 179 tests / production build /
50 routes PASS again. Fresh corrected Wasm/UI build PASS. Refreshed main
`760fb5ab989c48eb569b8a7ea646a4417fe21039` has no intervening producer/consumer premise change. Actual
post-commit three-journey package proof and original S7 are still pending.

## Final consumer verification receipt

All 18 frozen inputs stayed byte-identical through the three packaged runs at
clean source `69845a942db5123b9b95c5dd0f50c8b24416f4b7`; only this plan's
receipt text changes afterward.

- New production-package Chromium S3 journeys: 3/3 PASS (1.5m). Immediate and
  COUNT-IN A-B-A, plus COUNT-IN A-B-A-B ending on actual B, include genuine
  claimed-overlay refusal/new explicit user retry with no automatic replay,
  requested/queued/actual projection, original input/hold/release consumption,
  exact full per-Pattern Truth/revision, unchanged complete asset file hashes /
  lengths, actual Record-off/ordinary Stop and fresh reopen. Original e1/e2
  A/S0 receipts and real current B remain distinct. No fixture receipt is
  synthesized. The previously failing terminal Stop now sends the ordinary
  command after the original caller's final projection finishes.
- Original complete packaged count-in/metronome S7 selection: 20/20 PASS
  (3.6m), including Native cue PCM/Master exclusion, original one/two-bar timing,
  real release/Truth/reopen, cancellation, late IndexedDB and ordinary/capture/
  Performance routing. Source wrapper observes MacBook Pro Speakers; this is
  automated output evidence, not human listening or physical-device acceptance.
- Original related packaged recording/Sequence/Perform selection: 11/11 PASS
  (2.8m): complete Performance projection/gesture/WAV/save/replay journey,
  ordinary Launch/SNAP, global overdub/navigation/Stop/reopen, both-grid saved
  notes, lost Record-off ticket with exact retry and stopped Record, both
  owner-loss/recovery paths, Tempo/Swing recording locks, current withdrawal and
  persisted SNAP. Total new/current selected packaged journeys: 34/34 PASS.
- Corrected source's complete UI selection: 79 files / 1787 PASS; focused
  terminal-projection regressions 2/2 PASS; TypeScript, offline Node 6/6,
  dependency check, clean Wasm/UI/package and complete Portal 179/50 PASS.
  Existing SDK and Core/Native/Host are unchanged relative to C3; do not count
  their earlier dependency receipts as a new full candidate run here.
- Parent-relative classification: focused creator/docs_static/portal. The
  complete range against main includes C3 and conservatively selects full13;
  neither selection means all those lanes executed. Committed new-path
  ownership and final body checks run before push.

C3 owns the deterministic exact-S, real held-I/O/two-lease/third-publication,
Journal failure/restart/stress and actual failed-owner disposition receipts.
Those producer inputs are unchanged. Additional packaged composition of those
fault barriers, complete other-platform/candidate checks, #1221 device/listening,
#2237 version allocation and independent Draft review are not claimed passed.
The earlier setup/type/assertion failures and the real terminal consumer red
remain historical nonzero results, not silently rewritten as green.

main freeze persists. Draft child targets `feat/recording-switch-host`; no merge,
auto-merge, release, Runtime deploy, Channel promotion or Git cleanup.

Final premise refresh: main `760fb5ab989c48eb569b8a7ea646a4417fe21039`; intervening producer/consumer paths: 0.
