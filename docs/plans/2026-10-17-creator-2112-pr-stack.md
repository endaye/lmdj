# Creator #2112 PR stack

Date: 2026-10-17
Parent: #2112. First feature: #2232 (Creator COUNT-IN / S7).

## Authority and integration boundary

Update, 2026-10-18: the owner now authorizes merging #2112 PRs that do not
modify CI. This supersedes the historical hold below for those PRs. Integrate
only after Task verification, exact-head independent review and live
conversation/conflict/protection checks. CI changes remain held. Release,
deployment, auto-merge, Channel promotion and resource cleanup remain outside
this authorization. #2342 landed as `839b202e359db700c28ffcd2dbf8f8cfc7d838cf`;
#2350 landed as `24d2545c6c14e175e1b3cb8e73071374fd900e92` after an identical-patch
rebase, fresh owning checks and eligible automated independent review.

The following paragraph records the original 2026-10-17 authorization:

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

## Layer 3 — complete Creator S7 consumer

Task base/main: `24d2545c6c14e175e1b3cb8e73071374fd900e92`.
Branch: `feat/creator-count-in-interaction`; PR target: main. One coordinator
writes the shared Creator surfaces; no other writer or dirty work is adopted.
The goal remains all 18 #2112 work items, followed by their actual candidate
acceptance; this layer delivers S7, not the entire umbrella.

### Premise disposition at the refreshed main

- Already delivered: device preference (#2342), S6 scheduled/cancel/inspect and
  native forced cues (#2202/#2223), synchronous metronome preference (#2350).
  Reuse the public SDK; do not implement another schedule or audio engine.
- Still outstanding: App's stopped Record dispatch always calls the ordinary
  transport; SETUP renders SEQ SNAP/METRONOME without COUNT-IN; the upper
  transport renders only ordinary phase/position; REC is steady only from the
  ordinary recording flag. These actual consumers are the bounded negative
  sites. Present SEQ SNAP hydration and public SDK count-in registrations are
  positive controls for the inspection. No successor since the original base
  changes these App/SETUP/metronome consumers.
- Still outstanding: exact ticket ownership through admission, S, cancellation,
  opening and consumption; truthful countdown/lamp; BPM/Pattern locks with
  playable Pads; refusing unsupported scheduling while retaining the setting;
  excluding native-owned S from the JS grid even after a late On toggle.
- Separate unresolved evidence: #2358 records one pre-COUNT-IN audio.activate
  timeout at the rebased producer head. A later unchanged complete seven-test
  run passed on the same observed Bluetooth route. It is not a causal fix;
  preserve both results and the existing five-second device/one-second Control
  policy. S7 and final candidate testing must not silently erase that debt.

### Declared files

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/runtime/count_in_controller.ts` (new)
- `apps/creator-web/src/runtime/metronome_scheduler.ts`
- `apps/creator-web/src/components/count_in_readout.tsx` (new)
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/components/physical_controls.css`
- `apps/creator-web/src/components/overview_display.tsx`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/test/count_in_controller.test.ts` (new)
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/creator-web/test/metronome_scheduler.test.ts`
- `apps/creator-web/test/overview_display.test.tsx`
- `tests/platform/web/creator/creator_web_metronome.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `apps/docs-site/docs/platform/input.mdx`
- `docs/plans/2026-10-17-creator-2112-pr-stack.md`

### Implementation and verification contract

Keep one exact original ticket per (Runtime, Project, engagement). Reserve the
owner before awaiting admission; keep cancellation identity stable across an
unknown response, ignore foreign/retired observations and consume only through
the actual Host acknowledgement. A native Applied receipt makes the lamp steady;
it does not stand in for Journal opening or durable input success. Only actual
matching cancellation/Stop and successful terminal consumption release the
pending lock. SDK lifecycle retains its own original consumers on replacement.

Off and playing-overdub keep ordinary transport. Count-in 1/2 from stopped must
use the companion or refuse with the actual reason; no ordinary fallback and no
preference rewrite. Late hydration cannot overwrite an explicit choice. Publish
metronome changes directly before the UI update while the native schedule owns
S. The JS scheduler excludes that exact native-owned frame, including a toggle
after S; all later beats retain the existing engine-frame grid/clock anchor.

Lowest tests: controller admission/cancel races, exact decimal identities,
matching receipts, retained failure/consume, replacement and single-poll
ownership; actual App setting hydration, unsupported/Off/overdub paths and
locks with playable Press/Release; exact scheduler-frame and readout/lamp tests.
Run Creator TypeScript, owning preference/controller/component/metronome suites,
staged path ownership and the affected Portal check. No new CI gate is added.

Packaged journeys use the real UI and original public SDK/native outputs:
default/corrupt/late preference, Off/1/2, Record → forced cues/countdown/lamp →
actual Applied → post-start toggle/Pad press-release → Record-off/Stop → complete
Truth → reopen; both physical controls' winning cancellations retain unchanged
Truth/storage; global REC on all pages remains Pattern Record, with Sample and
Performance exclusion. Preserve every original metronome/count-in journey and
budget. Package a clean verified source freeze, then run complete declared
journeys before publication; failures remain findings. Observe real output-device
start/end and retain #2358 separately. Device/listening acceptance remains A01.

Version impact: Creator Host MINOR debt for compatible user-visible S7 behavior,
recorded for #2237. No Product/Assembly identity or Project Contract is allocated.
Documentation impact: required — `/hosts/creator-web/`,
`/hosts/creator-interactions/`, `/platform/input/`.

### Local freeze evidence (2026-10-18)

- Main refreshed before freeze: still `24d2545c6c14e175e1b3cb8e73071374fd900e92`;
  no successor changed the outstanding consumer premises.
- Final five-suite Creator selection: 293 tests passed; TypeScript passed.
  The 127 BPM literal native marker witness first failed at frame 23677, then
  passed with the actual rounded quarter-Bar formula. The positive-consume /
  failed ordinary refresh case retains the consumer ACK instead of resurrecting
  its caller. These are product/test facts, not new process pitfalls.
- Normal pinned Emscripten 6.0.5 / Node 26 Wasm and UI build passed. Staged new
  paths were included in the 76 passing ownership/scope tests. Portal check
  completed with 179 tests and 50 routes/internal links.
- The complete Chromium selection contains all seven original count-in API
  journeys, five original metronome journeys and eight additional UI journeys
  (20 total). No original assertion, journey leg or deadline was removed.
  The package requires a clean local source freeze; its actual packaged journey
  results are still pending here and must be recorded in the PR before shipping.
- Unresolved #2358, combined-candidate/full checks, physical listening and
  packaged release/deployment acceptance remain separate evidence.

### Packaged finding and prerequisite (2026-10-18)

The complete initial 20-journey run on clean head `50754ace` returned 17 PASS /
3 FAIL, exit 1; its owned server stopped and both output observations recorded
AirPods Pro/Bluetooth. All seven original native count-in and five original
metronome journeys passed. Both new full recording cases reached Applied but
failed the unchanged two-quantum Native-to-JS assertion (1280/1024-frame error).
#2360 separately repairs Runtime Session's epoch capture after its asynchronous
profile refresh; its deterministic held-refresh tests failed at the actual
clock assertions, then the complete 427-test SDK selection passed.

This layer now stacks over #2360 head
`2c9ada265bcd94729801d6b3000cdaea9419534f`; main remains the original declared
`24d2545c`. The recovered original head is retained separately. Range-diff
proves the original S7 patch unchanged before this finding amendment. After the
prerequisite lands, move this layer onto its actual squash and rerun the owning
checks/package/complete journeys before requesting a main merge.

The third initial failure expected a replacement confirmation while the Sample
inspection was still loading; the trace showed direct A01 Capture instead.
The already-declared browser file now explicitly selects A01 through the real
UI and waits for its actual assigned-Sample projection (Replace Sample positive
control) before Record Sample. Keep the confirmation, permission-refusal,
Performance capture/export, negative Pattern-dispatch and preference assertions.
No original timeout/assertion/leg is dropped, and #2358 remains unresolved.

### Native clock and terminal UI follow-up

The first corrected-stack focused run on `f3429648` returned 1 PASS / 2 FAIL:
Sample/Performance exclusion passes. The 120 BPM case passed phase/PCM/Master,
durable input and Record-off Truth but failed its subsequent Stop observation;
40 BPM still failed phase with 768 frames. The previous assumption that both
reached Stop was corrected before any merge. #2360 remains Draft and now
publishes the original epoch from the actual first Native render; an
activation-return sample cannot eliminate the original reply latency.

The browser journey already owns terminal consumption and unlock. After its
positive Host consume reply, explicitly require COUNT-IN readout retirement
and the actual Pattern/BPM controls' unlock before the next Stop gesture.
An idle-looking REC and a Host response alone are not that UI far side. Retain
every original Stop/Truth/reopen assertion. Attach the forwarding observer's
original UI requests/responses on failures, so later findings retain their
actual cancel/consume lineage instead of inferred button state.

Current producer source: #2360 head `8ff609053ac3c3f2e58e297c994b877ebbd9d31e`. The S7
patch is rebased over that exact first-render epoch implementation; the
public AudioClockSample shape and its Creator converter remain unchanged.
The complete 20-journey packaged rerun must use this source, preserve earlier
results, and pass the original phase/PCM/Truth/Stop/reopen assertions before
shipping either integrated consumer evidence or a completed S7 claim.

### First Native epoch packaged result and audible witness

The complete original 20-journey selection on `f6cb5a58` / producer `8ff60905`
returns 19 PASS / 1 FAIL, exit 1, 3.7 minutes. All seven original count-in and
five metronome journeys pass. Both strict Native-to-JS phase assertions pass;
the 120 BPM UI journey additionally passes actual terminal unlock, Stop,
complete Truth and reopen. All-page winning cancel, preferences and separate
Sample/Performance paths pass. Both device observations remain AirPods/Bluetooth;
#2358 and physical listening are still separate.

The 40 BPM case fails the positive overlap witness, not phase or Master routing.
Its retained original UI RPC artifact proves C=51200, second cue=123200 and the
actual pre-S voice admission at 125440, after that 1920-frame cue already ended
at 125120. The 4800-frame one-pass Gate sample ends before the next cue. A main
thread UI gesture cannot guarantee a 100-ms sample spans a chosen cue.
Before the already-required real projection reload, the fixture now uses the
actual Sample inspect/update command to enable forward looping from frame 0
while this Gate is held. Keep the original PCM, overlap>0, cue-only>0, every
Master sample, post-S real release, durable input, complete Truth/Stop/reopen
assertions and all budgets. The baseline includes this explicit fixture authoring;
no product source, original native API test or helper is changed.

The `3cf72481` repeat is also 19 PASS / 1 FAIL at the same positive overlap
assertion. Inspection of the current Contract and renderer proves the fixture
omitted `trigger_mode: loop_gate`: loop_start/loop_mode alone do not loop an
ordinary Gate. Correct the already-declared setup to the actual Loop Gate mode
and require `sample.inspect` to read it back before reload. No product change or
assertion relaxation. This repeat observed an output change from AirPods to
built-in speakers; retain that fact without attributing the overlap failure to
it. Native phase and the complete 120 BPM journey still pass.

### Integration base refresh and fixture normalization

#2360 is merged as `4de2e7ddfe7f170aad3771b40d25333392c0a693`;
all twelve landed files equal reviewed producer `8ff60905`. Main was refreshed
before this amendment and S7 was rebased onto that actual introducing squash;
range-diff is unchanged. The Native epoch premise is delivered, not another S7
implementation gap. The remaining consumer premises and 18-file scope stay as
above; no new CI or version allocation.

The Loop Gate preparation's first two-case run stops before Record because
`sample.inspect` canonically omits default `loop_mode=forward`. Keep the actual
Loop Gate/loop-start readback and assert the forward default using its approved
canonical fallback, rather than require an optional default wire field.
Also correct the phase-preparation predicate for the 40 BPM case: after its
first JS beat at 1.5 seconds, a first-quarter-only window would require waiting
4.5 seconds for another quarter, exceeding the unchanged two-second fixture
bound. Choose any Native phase leaving 900 ms for the real 650-ms UI hold and
its ingress margin; retain the actual >240-tick duration assertion and all
budgets. The predicate is fixture preparation, not the musical duration oracle.

### Actual-main consumer freeze checks

On the actual #2360 main squash `4de2e7dd`, the final owning Creator selection
passes 293 tests; the additional directly affected Sequence/Perform component
selection passes 208 tests (501 total across seven distinct files). TypeScript,
Portal 179 tests / 50 routes and ownership 76 tests pass. Browser syntax and
staged/committed whitespace/inventory checks pass. Main still matches this
integration base before the local freeze. The complete 20-journey package result
on this exact final fixture is pending; prior 17/3, focused 1/2, Native 19/1 and
fixture-preparation failures remain evidence, not aggregated into a full PASS.

### Original caller retirement reduction before shipping

Clean actual-main head `0de1a81c` passes all 20 complete packaged journeys in
3.7 minutes, with built-in speaker observations at both ends. Its final 501
owning tests/Portal/build/package results are input-bound; no Source/physical
acceptance is inferred beyond those journeys.

Reviewing the failure/lifecycle path before publication exposes two remaining
controller premises in the already-declared controller/test files. First,
ordinary transport projection can wait behind unrelated SDK lifecycle/query
work, so awaiting it inside the retained count-in observation lane can prevent
the independent original consume that lifecycle needs. Second, failed scheduled
callers can legitimately have an actual Applied start and no successful e2 F;
requiring an Applied cancel before even trying consume prevents retirement after
the Host's independent physical/I/O failure ACK is ready.

Add reduced red tests before changing those sites. Keep one bounded ordinary
projection in flight separately, keep the exact caller inspect/consume lane
progressing, and preserve the final e2 projection before normal UI unlock. A
failure DTO only permits an attempt: HOST_STATE_INVALID still retains the owner;
only actual positive consume retires it. Do not invent F, require success-shaped
failure receipts, clear a caller on timeout or let projection errors overwrite
the original Native failure. Re-run owning checks and complete packaged journeys
on the amended source; the 0de1a81c pass is not the new head's receipt.

The four reduced retirement cases first fail with no consume attempt, then
all 26 controller cases pass. The full owning selection passes 297 cases and
the two direct surfaces pass 208 (505 distinct tests). The subsequent TypeScript
check catches an overly broad deferred fixture type; narrow that test promise
to its actual ordinary fixture, rerun the 26 controller cases and TypeScript.
No product assertion or deadline changes. Portal and path ownership verification
must complete before the clean freeze; final package/browser receipts remain
bound to that amended head and are recorded on the PR.

### Independent review on 97d37922

Trusted DeepSeek review run 39091272407 reports two findings. Its first proposed
trigger (opening/re-engaging a Project during COUNT-IN) must be checked against
`selectCanChangeProject`: Open/Create/Import/Duplicate require inactive/suspended
audio. `beginProjectAction` checks those selectors; ordinary navigation retains
the engagement. Suspension itself retains this controller until the actual Host
barrier finishes, while fatal Runtime replacement uses the SDK's retained cleanup.
Add a real-App refusal/caller-identity regression before disposing that finding;
do not carry an old Project controller into a newly owned Project.

The second finding is actionable: a rejected live metronome write currently
marks the device preference touched before Native accepts it, suppressing a late
boot read even though no choice was committed. Add a reduced App test with the
actual held settings read and one refused Native setter, then mark touched only
after synchronous acceptance. Keep the visible refusal, original setting and
caller. Re-run owning checks and all packaged journeys on the amended source;
97d37922's 505 tests/20 packaged PASS remain old-input evidence.

The two new App cases run before the fix: Project replacement refusal and
original cancellation identity pass; late metronome hydration fails with false
instead of the saved true. After moving the touched marker past synchronous
Native acceptance, the full five-file owning selection passes 299 cases and
TypeScript passes. The unchanged direct surfaces retain their 208-case PASS;
total owning coverage is 507. Current Portal/source-diagram inputs are unchanged
from the 179-test/50-route PASS. Rebuild and repeat all 20 packaged journeys
before readying the amended head, then obtain fresh independent review.

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
