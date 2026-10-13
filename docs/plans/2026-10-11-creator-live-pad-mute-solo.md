# C2 — Creator current Pad live Mute/Solo

## Premise refresh

Base and integration main: `0909a3015d8f19ee91dab415cd682822e9d3d3b5` (2026-10-13).
C1 delivered by PR #2139 at this exact merge. W1 typed SDK already exposes
`pad_mute`, `pad_solo`, `clear_pad_gates` and applied 64-slot masks; P0/P1 preserve
initial masks and ordered recording events. These producers are not reimplemented.
Current Creator `PerformState` drops the masks, `PerformSurface` has no current-Pad
controls, and `PadSurface` has no gate projection: C2 remains outstanding.
Current App recreates Perform controllers on Pattern selection; C2 must retain its
Project owner across Pattern changes so selection does not become a leave/reset.
Issue #1822 is an open product umbrella, not a closing target for this Task.

## Scope and declared files

Consume the existing producer with two independent buttons naming the explicit
current Pad. Read applied masks for all 64 slots, preserve multi-Solo/Mute priority,
show pending/unavailable honestly, and retain masks across Bank/Pattern selection.
The bounded C1 FIFO owns controls and recording events. Leave clears gates through
the producer and waits for applied acknowledgement, regardless of HOLD; old epoch
callbacks cannot affect a replacement owner. No Project Truth, Undo, storage,
keyboard mapping, MIDI, SHIFT, master gain, or DSP change.

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/state/perform_state.ts`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/fixtures/perform_helpers.mjs` — SOURCE-only correction
  adds exact accessible-name navigation for the two existing recovery journeys.
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- this plan

## Verification and journey map

Component/controller oracles cover explicit A01/D16 identity, independent pressed
states, multiple Solo and Mute priority, applied-only readback, unavailable producer,
bounded FIFO, late epoch replies, initial recording masks and later ordered events,
leave/reset ACK even under HOLD. Real App proves current Pad/Bank/Pattern ownership,
Project replacement, unchanged persistent Pad playback and authoring history.
Packaged browser journey installs distinguishable two-Pad PCM: preexisting masks
→ Record → first Pad under initial mask → later mute/solo events → Bank/Pattern
switch → multiple Solo + Mute precedence → Stop → Save → reopen → Replay, with
observable far-side audio/state for every transition. A second live exit leg proves
HOLD cannot retain gates. Physical devices, MIDI and hearing remain unverified.
TypeScript, complete UI suite, path ownership, docs check, and full clean-head
`scripts/creator-web.sh proof` are required before shipping. No reduced budgets.

## Version Management

Version impact: Creator compatible public interaction MINOR debt for separate V1
settlement. No Product Build or Assembly allocation; no binary compatibility or
release-readiness claim. Core/SDK identities are unchanged.

## Documentation impact

Documentation impact: required — `/hosts/creator-web/`, `/hosts/creator-interactions/`.
Document current-Pad controls, all-64 state, recording and reset semantics in the
same Task. No source diagram changes are needed for this consumer-only wiring.

## Results

Before the first freeze, main refreshed to `35455f75` (PR #2141 release tooling).
Its file diff does not touch this consumer, producers, or acceptance tests, so no
rebase or repeated implementation is needed. Task scope remains the 11 files above.

- TypeScript: PASS.
- Perform controller/component: 130/130 PASS, including seven new gate oracles.
- Real App current Pad/Bank/Pattern and delayed leave oracle: PASS. Initial test
  used the pre-selection Bank fallback as an explicit selection; corrected it to
  establish A01 with the existing direction controls before changing Bank.
- Complete UI suite: 75 files, 1522/1522 PASS.
- Portal check: PASS, 50 routes/internal links.
- Packaged two-Pad PCM and full clean-head proof: pending at this freeze.

The tests preserve native press/release and far-side admission waits. The new
browser journey records A01 at half the D16 sample amplitude, expects four audible
bursts A/D/D/A among three silent strikes, then compares those four replay bursts
through the actual Internal playback Master tap after reopening. This proves gate
ordering acoustically instead of trusting the UI. Physical/MIDI/hearing remain
UNVERIFIED. No new pitfall entry: the product invariants are fully expressed by
owning regression tests; existing journey/synthetic-event guidance was applied.


### Final freeze before complete proof

The packaged journey passed on clean `c301a095c496d85bdf1dca833c4e7baf8480539e`
(actual exit 0, 2026-10-13; built-in speaker endpoint unchanged). It observed exactly
four audible bursts with the required ratios and identical replay PCM signatures;
the three gated strikes contributed no extra burst. Original 420-second journey
budget and strict signal assertions were retained.

After that run, a second real App oracle confirms a late old-Project gate ACK and
its cleanup cannot change the new owner's Solo/mask or issue commands on its
Session. Both App oracles pass, now with a far-side Pattern reload assertion.
TypeScript and updated 50-route portal check pass. Current portal descriptions
replace stale C1/C2 claims with the actual delivered controls and explicit device
acceptance gap. No product source changed after the packaged PASS. The clean
amended head below is the input to the complete proof; the earlier UI count is
historical until that full receipt arrives.


### Integration refresh for the complete proof

Rebased before the full run onto `797b077c8e3cb9957433328b70aa903d6a252164`:
PR #2141 release identity tooling, #2143 Build 2.0.96.0 allocation, and #2144 its
snapshot witness. No conflicts. Creator source, typed producers and C2 acceptance
inputs are unchanged by these merges; active generated Product identity and portal
snapshot changed. The complete proof therefore builds the updated identity. C2
still allocates no identity and performs no release operation. Historical focused
PCM at Build 2.0.95.0 is retained; it is not substituted for this current full run.

## SOURCE-only correction boundary — 2026-10-13

The original frozen head remains `5255673e9b37168a88486b2459b5e6b3035d5c67`,
with integration base `797b077c8e3cb9957433328b70aa903d6a252164`. Its complete
original proof ran naturally from 08:04:21.658Z to 08:24:59.791Z, exit 1:
75 UI files / 1523 PASS; all browser groups 141 PASS / 4 FAIL / 11 configured
skips. The two-Pad PCM journey passed, but this does not clear the failures or
the separate immediate-current-input producer mismatch. Raw logs and the full
browser trace packet remain immutable under `/tmp/lmdj-kimi-takeover-wp0wmju4/`.

Before editing, refreshed integration main to
`8a5142efd9a86f207fade75661ed0f4a225c56e0` and saved the clean before state:
`/tmp/lmdj-kimi-takeover-wp0wmju4/c2-source-only-20261013T084128Z/before.json`.
That snapshot contains exact bytes/hashes for the original 11 Task files plus
the existing shared navigation fixture, the complete frozen Task patch, and
the relevant current-main source bytes. HEAD is retained; no rebase or merge
is performed during this source preparation.

### Refreshed dispositions and declared files

All three consumer causes remain outstanding at the frozen head. Current main
still has the ambiguous fixture and stops Replay late in its leave sequence;
it contains neither C2's Gate section nor C2's mask clear. The new Gate section
caused the frozen C2 layout regression, and inserting clear before the existing
late Replay stop caused the shutdown ordering defect. Core/Facade/SDK producer
source is unchanged between the integration base and refreshed main; none is
reimplemented here.

PR #2145 is already delivered at refreshed main: the Pad caption uses Asset
category independently of colour, loading/capture captions take precedence,
the assigned/empty accessible names and MPC key order remain, and the palette,
geometry and selection marker have changed. Its affected Pad/CSS/category-test
and portal inputs are preserved in the snapshot as integration premises.
This correction edits none of those paths. Eventual integration must preserve
those changes alongside C2's separate live-gate attributes and labels.

The original 11 declared files remain the C2 Task boundary. The sole addition
is `tests/platform/web/creator/fixtures/perform_helpers.mjs`: both failed complete
owner-loss/recovery journeys call this shared fixture, so fixing its ambiguous
accessible-name match at the cause preserves every recovery leg. No new test
file, gate or journey substitute is added. The revised Task boundary has 12 files.

This renewed source-only patch modifies exactly five of those files:

- `tests/platform/web/creator/fixtures/perform_helpers.mjs`: exact `Perform`
  name match; `Open Perform` no longer makes the existing locator ambiguous.
- `apps/creator-web/src/components/perform_surface.tsx`: move the unchanged Gate
  section after `FxSliderBank`. The Pattern and FX siblings can again occupy the
  same two-column grid row; the full-width Gate section follows them.
- `apps/creator-web/src/state/perform_state.ts`: move the existing awaited
  active-Replay stop before mask clear. Stop failure still blocks exit; recording
  clear still precedes recording stop/finalization. The FIFO drain, owner/epoch
  guards, release path, status-query count/delay and cleanup calls are retained.
- `apps/creator-web/test/perform_surface.test.tsx`: prepare leave/close oracles
  whose Replay publisher keeps restoring a recorded Solo until stopped. Strengthen
  the existing pending-neutral-stop oracle to require no early gate-clear command.
- this plan: preserve failed evidence and record scope, premises and planned tests.

### Independent causal verification planned — all UNRUN on this patch

Root review precedes scheduling. No tests, compiler, dependency install, Portal,
Native/Wasm build, package, full Creator proof or browser execution is authorized
for this source-only preparation. No commit, push or Pull Request is made.

1. **Navigation:** rerun both original complete recovery journeys in
   `creator_web_perform.spec.mjs` (discard/apply/discard owner loss; one recoverable
   recording/no second capture owner). Observe the actual recovery control and
   its far-side revision/recovery result after exact physical Perform navigation.
   A one-line restoration of the ambiguous match should reproduce the preserved
   strict-mode failure without removing the Open Perform control or any leg.
2. **Layout/native target:** rerun the unchanged `creator_web_touch_fit.spec.mjs`
   first-screen faders/HOLD oracle and `creator_web_perform.spec.mjs` native FX
   drag-off oracle. Require the original bounds, non-overlap, native capture,
   open-FX 1→0, enabled page navigation, and uninterrupted recording assertions.
   Separately restore only the old Gate placement against a rebuilt artifact to
   reproduce out-of-screen geometry/native miss. No synthetic replacement,
   viewport expansion, scroll workaround, timeout change or weakened assertion.
3. **Replay shutdown:** execute the prepared leave/close publisher oracles and
   the strengthened pending-stop oracle. Restoring only stop-after-clear must
   make the continuing publisher defeat clear ACK; the correction must complete
   only after Replay retires and actual masks read empty. Pending Stop must keep
   exit blocked and issue no clear. Keep existing recording clear-before-stop,
   HOLD reset ACK, failed clear, late epoch/Replay poll, owner replacement and
   owner-loss tests. The deterministic two-query test dependency is the original
   probe's bounded model; production remains 200 queries with 50 ms spacing.

After Root admits verification, run owning controller/App checks and the complete
original relevant browser journeys with current-main integration, then the
remaining Task checks and full clean-head proof when their windows are admitted.
Any causal restore must use fresh source mtimes and an actual rebuilt artifact;
retain its real exit status and the failure inside the owning oracle. Source
inspection alone is not GREEN and does not establish first-screen/audio acceptance.

The producer's 96-frame current-input fade remains a separately unaccepted debt.
This source patch changes no SDK/Core, transport/input capacity, DSP, deadline,
manifest, release or deployment state. Version and documentation impact remain
as declared above; physical device/MIDI/hearing acceptance remains unverified.

### Root follow-up: Replay Stop and control epoch — source disposition

The actual engine producer's ordinary Replay Stop **does not advance or replace
the control epoch for the same Project and engine start**. This is a source fact,
not a new executed test result or a promise for unrelated owner changes.

- Public SDK `stopPerformanceReplay` in
  `packages/web-runtime-platform/web/runtime_session.mjs:5327` only serializes
  `performance.replay.stop`; `serializeRuntimeAction` at 2188 orders its action
  without an engine lifecycle transition. `replayResult` at 4434 returns the
  Replay receipt fields, with no new control epoch or rebind operation.
- Application `performance_replay_stop` in
  `packages/application-facade/src/application.cpp:8401` checks the existing
  Replay/Project identity and calls the Replay controller. It does not call
  live-control bind/invalidate or restart the engine.
- `ReferencePerformanceReplayController::stop` in
  `packages/application-facade/src/performance_replay.cpp:341` sets the terminal
  reset target; `finish_reset` at 180 makes that target terminal only after the
  sink reports reset complete. A pending reset remains playing.
- Engine replay sink `reset_neutral` in
  `packages/application-facade/src/performance_engine_adapter.cpp:1667` enqueues
  empty masks, Filter release and the ordinary HOLD/FX releases. `reset_reached`
  at 1777 checks their real drain counters. Neither calls Engine start/stop nor
  changes `EngineLiveControlCore::epoch_`. Its private `reset_epoch_` is a reset
  fence tracking the engine's existing start epoch; clearing that fence is not
  retiring the public live-control epoch. Its stopped/restarted-engine branches
  observe an external lifecycle transition; Stop does not cause that transition.
- The epoch-changing authority is `EngineLiveControlCore::bind_control_target`
  at 767 (returns the same epoch for the same Project/start, otherwise allocates
  one), invalidation at 787, and `observe_engine_epoch_locked` at 1049 (invalidates
  on a changed engine start). `RealtimeEngine::start` in
  `packages/audio-runtime/src/realtime_engine.cpp:1921` advances start epoch at
  2000. The inspected ordinary Replay Stop path reaches none of those mutations.

Therefore the cached live-control epoch remains valid across that ordinary Stop.
The asynchronous `refreshLiveStatus()` updates applied display facts; it is not
required to obtain a new Stop-created epoch before the subsequent clear. `close()`
correctly suppresses adoption into a closed controller, and its cached epoch is
still the same owned epoch under these same-Project/start premises. Stop's terminal
receipt is already behind the neutral drain fence; subsequent mask clear retains
the existing actual-mask acknowledgement rather than inventing empty display state.
The stop comment is clarified to distinguish retired FX gesture bindings from
the stable control epoch. No extra query, retry, budget or SDK/Core change is added.

The prepared leave/close publisher oracles do not pretend that ordinary Stop
changes epoch; their bounded model isolates the ordering defect. They remain
UNRUN. Simultaneous Project/owner replacement or engine restart can change epoch
independently and is not proved by this stable-epoch source disposition. Retain
the existing owner/late-epoch oracles for later admitted verification; do not
claim this establishes every lifecycle interleaving.

**In-flight `beginReplay` remains explicitly unproved.** The active-state check
only retires a Replay already published as playing in controller state. It does
not establish that a pending begin cannot publish after leave/close. This narrow
patch adds no begin tracking/cancellation protocol and does not silently mark
that boundary solved. The original private Replay RED and frozen proof stay intact.

## P2 begin/exit repair and finite light verification — 2026-10-13

Root's independent full SOURCE review accepted the ordinary Stop stable-epoch
disposition and identified one P2: the earlier playing check could miss a begin
reply arriving during clear/finalization, while the mounted Perform action could
also admit another begin during exit. The preceding pending-begin UNPROVEN section
records the pre-repair boundary; this section supersedes it only for the finite
controller interleavings exercised below, not whole-lifecycle/audio acceptance.

The renewed scope is only `perform_state.ts`, existing `perform_surface.test.tsx`
and this plan. The prior exact-name fixture and unchanged Gate DOM move remain
byte-identical to the independently reviewed SOURCE candidate. The full boundary
is still the original 11 files plus the justified existing shared fixture, 12 in
total; the complete correction still changes only the same five files.

### Source repair and preserved truth

`beginReplay` refuses Session admission while `leavePromise` is outstanding or
the controller is closed. One already admitted begin is retained on its original
controller/Session; repeated calls share that pending result. `leave` awaits the
owned begin before its existing recording/control drain and active-Replay Stop.
A playing reply is retained even after close admission so it can be stopped:
dropping the reply would hide the real producer. Stop still waits for the original
terminal neutral fence before mask clear and exit completion.

UI callers keep the original reported-error contract. Internally a rejected begin
promise remains retained because its producer outcome may be unknown. Exit awaits
that rejection and fails before clear; a later begin does not create another
Session request over the unknown attempt. No neutral/empty/complete state is
fabricated and no recovery retry, new budget, event, input capacity or Core/SDK
change is introduced. A pending leave closes admission until that exit settles;
closed owners never reopen it. This does not introduce a new mounted-UI lifecycle.

### Causal RED, restoration and complete owning files

Before repair, saved exact five-file SOURCE candidate, source hashes and its
complete patch at
`/tmp/lmdj-kimi-takeover-wp0wmju4/c2-p2-light-20261013T091936Z/`.
Six new regressions use the original file's assertions/deadlines and no budget
override: for both leave and close, a held begin reply and held post-check clear
establish the unsafe interval; the actual model publisher must reach Stop and its
terminal fence before clear/exit. Separate cases assert zero new Session begin
admission while exit ACK is pending and failed exit for an unknown begin receipt.

- Frozen SOURCE candidate RED: actual exit 1, exactly six intended failures at
  the new assertions (Stop called 0 instead of 1; new begin called 1 instead of 0;
  exit completed instead of retaining failure). The 132 unselected cases were
  explicitly skipped by the focused selection, not reported as executed.
- Restored exact candidate `perform_state.ts` bytes with matching SHA256 and fresh
  mtime before the repair; retained the complete RED input and test bytes. The
  succeeding Vitest invocation performed a new source transform. No assertion
  or deadline was weakened between RED and GREEN.
- Complete original Perform component/controller file including all new tests:
  **138/138 PASS**, actual exit 0. Includes prior active publisher, pending neutral,
  recording clear-before-stop, failed clear, stale read/epoch and cleanup cases.
- Complete original workspace-shell file including its existing new C2 App
  current-Pad/Bank/Pattern and owner-replacement cases: **194/194 PASS**, exit 0.
  Existing CSS parse/localStorage warnings are retained in the raw log.
- Locked Creator `tsc --noEmit`: actual exit 0.
- `node --check` for the unchanged-in-P2 shared Perform fixture and original
  Perform browser file: both actual exit 0. Syntax is not browser execution.

Root admitted precisely this one light sequence. No dependency install, full UI
suite, Portal, package/build, Native/Wasm, browser or full Creator proof was run.
No stage/commit/push/main integration occurred; HEAD remains original frozen
`5255673e9b37168a88486b2459b5e6b3035d5c67`. Raw exits/logs, complete five-file and
12-file Task patches, source/receipt hashes and owned-child release are in the
finite light packet for independent review.

The original full Creator FAIL (141 PASS / 4 FAIL / 11 configured skips), private
active-publisher RED, #2145 current-main integration premises and immediate-input
96-frame producer mismatch remain separate debts. Real geometry/native targets,
complete current-main browser/audio journeys, simultaneous owner replacement or
restart with begin, unknown-begin recovery/liveness and device/hearing acceptance
are not cleared by these component/controller results. Further work needs its
own Root scheduling; B1's heavy window is not acquired by this light sequence.

## P2 known redundant Replay refusal — finite repair/light, 2026-10-13

Root's complete independent capability review identifies a new liveness defect:
the P2 rejection latch treated a redundant already-playing begin's known refusal
as an unknown producer outcome. Its full 10658-byte report is retained with SHA256
`6417759acc982166255c4b69290fe05485dddfab7b80b0ee25a6c71673fd0339` in the new
finite packet. This finding does not reopen the disposed ordinary Stop epoch issue.

Facade `application.cpp:8310–8322` returns `INVALID_ARGUMENT` and the matching
`details.active_replay_id` before calling the new producer at 8339–8340. SDK
`runtime_session.mjs:2092–2106` validates the envelope/request identity, preserves
code/details and replaces the human message. Those public fields and the current
controller's validated Replay identity establish this specific not-started case;
the original human string is not a discriminator. The same code can also arise
after publication: Facade8339–8350 can retain a playing identity on producer failure.
It cannot be treated as blanket evidence that every failed begin did not start.

Chosen smallest remedy: after the existing closed/leave and pending-owned-promise
guards, `beginReplay` returns without Session admission when this controller's
public Replay state is already `playing`. This prevents both same/other-take
redundant requests from producing the known-refusal latch in the reachable UI
path. No error-code/message classifier or rejection-latch clearing is added.
Unknown pending/rejected promises still take precedence over the playing guard;
there is no blanket release of INVALID_ARGUMENT, TypeError or any other rejection.
Captured begins, terminal Stop before clear, error reporting, original owner and
all capacities/events/status deadlines remain unchanged.

This turn modifies only `perform_state.ts`, existing `perform_surface.test.tsx`
and this plan. All prior test bytes are an exact prefix of the appended test file;
the original six P2 cases, helper, Gate DOM and workspace/browser bytes are retained.
Two new same/other-take models expose the real-shaped pre-producer refusal using
`INVALID_ARGUMENT`, matching active Replay ID and the SDK's generic message.
They require zero redundant Session/producer begin, Stop of the original ID,
successful leave with actual empty model masks, then a later new begin reaching
Session and playing. A separate post-publication INVALID_ARGUMENT model keeps its
publisher active and requires failed exit rather than invented neutral completion.

Executed one renewed bounded LIGHT sequence using existing locked dependencies:

- Old candidate targeted RED: actual exit 1, exactly two intended failures at the
  redundant Session admission assertion (expected 1, actual 2). The 139 unselected
  cases are UNRUN, not passed. No setup/collection or unrelated failure occurred.
- Saved RED inputs; restored exact old source bytes with matching SHA256 and a
  fresh mtime, then applied the one-guard remedy. New test bytes/assertions/budgets
  are identical between RED and the succeeding new-transform invocation.
- Complete original Perform file including all new tests: **141/141 PASS**, exit 0.
- Complete original workspace-shell file: **194/194 PASS**, exit 0; original CSS
  parse/localStorage warnings retained in the raw log.
- Locked Creator `tsc --noEmit` and syntax checks for the unchanged-in-this-turn
  helper and original Perform browser file: all actual exit 0.

Raw logs, exact before/RED/final bytes, complete five-file/Task12 patches, actual
exit/hash manifest and owned light release are under
`/tmp/lmdj-kimi-takeover-wp0wmju4/c2-refusal-light-20261013T095227Z/`.
All earlier light logs, the original private RED and fullproof FAIL141P4F11S remain
immutable. HEAD remains5255673; no stage/commit/push/main integration or heavy,
build, Portal, Native/Wasm/browser execution. U05b1's heavy ownership is not acquired.
This prevention is not general UNKNOWN recovery: previously unknown/lost receipts,
external owner/restart interleavings, actual browser/audio acceptance, #2145 main
integration and the producer96fade mismatch remain separate unaccepted boundaries.

## Current-main integration and bounded low-tier receipts — 2026-10-13

Root accepted the final five-file SOURCE correction with independent findings[].
The exact prior packet and its raw receipts remain frozen. Root then admitted a
clean local checkpoint, integration of freshly fetched main in this C2 worktree,
and only the owning component/type/syntax/scope checks. No heavy window was admitted.

### Exact Git boundary and main preservation

- Before correction checkpoint: HEAD
  `5255673e9b37168a88486b2459b5e6b3035d5c67`; exact reviewed five-file patch SHA256
  `ec526594c4a50f61753c41ecd4b0c5a946e7dcaa30f169fae8f971dda94da6b3`.
- Clean local checkpoint: `ea6893c346d5e2bde821a4665fa13b448fcd5458`, tree
  `4dd4b4fe8e045dcaaf8b7274fb72c1df5d9852f2`. Its inspected commit contains exactly
  the five reviewed files, and its immediate post-commit worktree was clean.
- Fresh fetched integration target: `0c873e6755fa5753f38ce4bf5267ea5cee00f080`,
  tree `ded61f1b98892ed65ec9daa809c897ba8c65a871`; common base
  `797b077c8e3cb9957433328b70aa903d6a252164`. This includes Pad #2145 and B1 #2147.
- The no-commit merge had exactly one content conflict, in owning `pad_surface.tsx`.
  Its resolution retains main's Loading/Capturing/category/Assigned/Empty caption
  and adds C2's existing independent, aria-hidden MUTE/SILENCED/SOLO small label.
  Main's category caption, palette, selection dot, MPC keyboard labels, handlers
  and accessibility structure are retained. No additional product fix was needed.
- Main contributes 13 paths. Nine are byte-identical to the fetched main; the
  other four are the declared C2 overlaps (Pad Surface, styles and two Host pages).
  The full integrated feature difference against that main is exactly Task12.
  App/Recovery, workspace tests, Perform/controller/tests and helper/browser inputs
  retain exact checkpoint bytes. B1 SDK declarations, runtime test and Creator
  type fixture retain exact main bytes. No Source11/S6/WIP source was imported.

The source/test index tree used for these checks was
`4d48fc7ad9cbe6b9807045caf477bc829865d210`; it is a tentative tree, not a commit.
This receipt-only plan addition follows execution and does not change any tested
source, test, fixture, assertion, capacity, timeout or journey leg. The packet
records the final tentative index tree separately after including this addition.

### Actual bounded execution

Using the existing locked Creator dependencies without installation, sequential
commands completed naturally with actual exit 0:

- Creator `./node_modules/.bin/tsc --noEmit`, including main's new B1 fixture through
  the unchanged `test` include: PASS.
- Complete `test/perform_surface.test.tsx`: **141/141 PASS**, no skips.
- Complete `test/workspace_shell.test.tsx`: **194/194 PASS**, no skips. Existing
  CSS parse and Node localStorage warnings are preserved in its raw log.
- Complete actual Pad files `test/pad_colour.test.tsx` and
  `test/pad_surface_keyboard.test.tsx`: **13/13 PASS**, no skips.
- `node --check` for the Perform helper, Perform browser file and main's preserved
  Sound Set browser file: all PASS; these are syntax checks, not browser journeys.
- `python3 tests/build/ci_change_scope_test.py`: **77/77 PASS**.
- Index and worktree whitespace checks: PASS; no unresolved conflict paths remain.

The complete integrated Task12 patch, checkpoint-to-merge patch, source snapshots,
13-path preservation inventory, exact before/head/base/tree records and raw
commands/exits/hashes are in
`/tmp/lmdj-kimi-takeover-wp0wmju4/c2-main-integration-20261013T101132Z/`.

Merge source remains **uncommitted** because final required build/Portal/full
Creator checks are incomplete and require future explicit heavy admission. No
push/PR, Native/Wasm, browser/full UI, build/package, Portal, release, deployment,
Run/inbox/rebind or cleanup mutation occurred. U03a and the U10/U06b heavy queue
remain separately owned. The original fullproof **141 PASS / 4 FAIL / 11 skips**,
Core96 immediate-input semantic debt, general UNKNOWN recovery, simultaneous
owner/restart interleavings and physical/hearing acceptance remain unresolved.
The integrated source is prepared for independent review, not final acceptance.

## Shipping admission refresh — 2026-10-13

The user now explicitly requests accepting C2 and completing push, PR and merge.
This supersedes the earlier preparation-only stop for this Task. Required Task
journeys, current-head independent review, conflicts and live protection remain;
there is no release, deployment, device rebind or unrelated cleanup authorization.

Fresh fetched main is `79aed2652d916310725782942e0a7c17cebc4c25`. C2 is still absent
there: the controller has no mask projection/clear or owned begin promise, and
the Pad Surface has no live gate label. C1/B1/Pad presentation remain delivered.
M1 producer correction is already committed via #2156 at
`3f05b962902c9bf2d9c8c5f558ab3b4d033f5492`; do not import its earlier WIP or repeat
its implementation. Capture/Trim, Overview/Slice, Master FX accounting, tempo
and Numeric/Sequence setup successors are retained from committed main.

The accepted resolved merge at the original worktree remains untouched, including
its pending MERGE_HEAD `0c873e67`, tentative index `a33503ec` and all frozen packets.
For a single reviewable Task commit, create the isolated branch
`feat/creator-live-pad-mute-solo-delivery` from fresh main in
`/Users/endaye/Projects/lmdj-wt-creator-live-pad-mute-solo-delivery`. Apply the full
accepted Task12 patch with Git's three-way context. All 12 paths apply cleanly;
the only composed files are App, Workspace tests and the two Host pages. Of 59
incoming successor paths, 55 remain byte-identical to main; the four overlaps
contain only C2's independent delta. No Source11/S6/WIP source is adopted.

Scope remains the same Task12. The product/controller/fixture inputs except those
four composed paths match the accepted packet exactly. Main's Category/palette,
Recovery, keyboard/MPC, Capture/Modal/Waveform, Sample/Overview and Numeric behavior
must remain. Version Management and Documentation impact above remain unchanged:
compatible Creator MINOR debt is assigned to separate V1 settlement; no Product
Build/Assembly allocation is bundled into this consumer Task.

Execute owning type/component/path checks, full normal Portal, normal build and
the entire clean-committed-head Creator proof, including all original eight
groups, workers, deadlines and journeys. Observe natural completion of the other
S6 proof before acquiring the heavy slot; no overlapping full proof is started.
Keep the finite real rendered Pad/category/status/gate/dot/key readback and original
FX/HOLD first-screen/native drag-off legs. Their actual results remain UNRUN until
captured below. Original fullproof 141P/4F/11S is immutable FAIL; no earlier light
receipt clears it or constitutes current-main acceptance. General UNKNOWN,
closed-owner/restart, physical and hearing boundaries remain separate.

Evidence for this delivery is retained outside tracked source at
`/tmp/lmdj-kimi-takeover-wp0wmju4/c2-delivery-20261013T150246Z/`.


## Actual full-proof and narrow geometry corrections — 2026-10-14

The first new-main proof ran naturally on clean `e8b8562d` from the normal stable
interface, retaining every original group, worker, deadline and journey. Actual
exit was 1: **153 PASS / 8 FAIL / 11 configured skips** across the eight groups.
All four earlier C2 failures (both recovery journeys, native drag-off, FX/HOLD
first-screen) passed. These new eight failures stop at the shared Overview usage
assertion in Browser (4), Sample Editor (3), and local deployment smoke (1).
Their three source files are byte-identical to main79 before correction. The
actual failure snapshots show `64 Pads · 1 Patterns` / `44 Pads · 1 Patterns` and
`Revision 46` in the current Project card, replacing the retired overview captions.
Do not regenerate the valid imported Bundle or change product behavior for this.

Declare three additional existing test files in this integrated Task (Task15):

- `tests/platform/web/creator/creator_web_browser.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/deployment/creator_web_deployment.spec.mjs`

Only their current Overview locators are corrected. Browser/Sample retain visible
64/44 assigned counts and add independent real Project inspection of four Banks,
16 Pads each and exact assigned counts. Sample retains its visible revision on the
current Project card and the original report-based revision assertion. Deployment
keeps both immutable historical usage shapes alongside the current 64-Pad caption.
No assertion, deadline, worker, skip, reload/failure/recovery leg is removed.

The admitted actual UI matrix ran 30 gate scenes on the same normally built e8
artifact: three original viewports × five real states × selected/unselected.
Core applied provenance, all 480 visible Pad instances, glyph rectangles and
screenshots are retained. Wide and 1280 compact scenes have no gate collision.
768×600 has 59px Pads: 51 unwanted glyph/dot intersections in those scene reads,
including the MUTE SOLO/category overlap visible in the original screenshot.
This is rendered evidence, superseding the source-only geometry gap.

The minimal product fix stays in the original C2 stylesheet. Position the added
gate on its own middle row; keep its original .6rem size and remove decorative
tracking so the longest real text stays on one line. Only gated captions receive
3px more lateral room for the existing selected-dot reserve. Keep the existing
Pad dimensions/hit targets, 11px address, 9px/13px caption/key, dot size/position,
palette, native input, and all controller/producer behavior. No text is hidden,
shrunk or fabricated. Rebuild normally and rerun the exact 30-scene matrix; a CSS
receipt alone does not prove the fix.

The first full FAIL, all eight result directories, normally packaged dist and
original geometry are immutable under `proof-e8b8562d-fail/` and `geometry/` in
the delivery packet. Raw full-proof log SHA256 is
`74f58961b103abab9d41e55a69241d55dbee48a8f34ce7481e93053bb4ccd604`.
The completed full UI suite was 77 files / 1593 PASS. Final corrected execution
results belong to the delivery packet and final PR Verification; this source
checkpoint does not predeclare them. Source scope remains this one consumer
Task plus the three necessary existing caller tests; no S6 or Core repair is added.

Physical/hearing, general UNKNOWN/closed-owner/restart and unobserved seed
Loading/Processing geometry remain outside these receipts. The actual seed
Failed, assigned/category, gate and selection frames are retained. MINOR debt
for V1 and the two Host documentation routes remain unchanged. No Product
allocation, release, deployment or worktree cleanup is included.


### Final committed-main refresh

While C2 remained unpublished, main advanced only through identity/snapshot cuts
#2168/#2171/#2173 to `3a3cc910c1f23f0aeaaff36d3441fd984dfda391`. Rebase the single
unpublished C2 Task onto that exact committed main; the operation is conflict-free.
Preserve both inherited immutable snapshots and all Product/Assembly/generated
identity changes. C2's remaining delta is exactly the declared Task15; it makes
no Product allocation, snapshot correction or release transition. The next normal
build/full proof binds the new committed candidate and current manifest identities.
Earlier Build96 logs and geometry remain historical exact-input evidence.

### Later Sample reopen caption — retained complete failure

The next clean-head complete run at `329007515c3204bba56a485667b0a6a3e831f54b`
ended naturally with exit 1: 1593 UI tests passed and all eight browser groups
completed with 160 PASS, 1 FAIL and 11 existing skips. The sole failure was the
later Sample v1-to-v2 reopen checkpoint: after recovered revision 60, its
unchanged caller still expected `45 / 64 Pads used`. The earlier import caption
repairs exposed this previously unreachable checkpoint. The complete raw log,
eight result directories, failure trace and verified distribution are retained
in `proof-final-32900751/`; raw log SHA256 is
`9d33ccdba6b8815aef25123788f0666403619258c8125d47f0e46a5df3ad9ada`.

Correct only this remaining caption to the current visible `45 Pads · 1 Patterns`
and independently retain four Banks, sixteen Pads per Bank and exactly 45
assigned assets through real Project inspection. Keep revision 60, Runtime
publication recovery, reopen, native trim grips and all subsequent far-side
assertions unchanged. Scope remains Task15, with no further product source or
CSS changes. Validate the entire 20-case Sample group before another complete
clean-head proof; this development check does not replace any of the eight
original full-proof groups. The 30-scene geometry evidence binds identical
unchanged product/CSS inputs, and the newly generated current-head Project
fixture is byte-identical to the geometry fixture. All failed runs remain FAIL.

The entire Sample development group then exited 0: 19 PASS and its one existing
Chromium capability skip. Revision 60 reopening and both native trim-grip
transitions through revisions 61/62 passed. Path ownership remained 77/77 and
normal Portal check exited 0. No product/CSS inputs changed for this correction.

## Current-head independent review disposition — PR2177

The complete `d79dc317bdfff8ddbe586fffcd5967f7677b3c9d` proof passed with actual
exit 0: 77 UI files/1593 tests and all eight browser groups, 161 PASS/11 existing
skips/0 FAIL. Raw log SHA256:
`674f726de0449a0474673a3d29145ce8f479cbc64fb501de6d0f17a225ca3fbb`.
Normal Portal, normal build/package and body declarations also exited 0.
The original worktree/index stayed frozen and 22 known proof PIDs were naturally
absent. These receipts remain exact-head historical evidence after the repair.

Authenticated independent DeepSeek review, run `38442918029` attempt 1, examined
this exact complete PR head and published three findings. The read-only eligibility
helper exited 0 with `eligible:true`; this alone did not authorize merge or resolve
conversations. The complete paginated review and threads were read.

1. Accept the changed-epoch reset finding. A clear admission on an owned epoch
   followed by a replacement epoch's status must not complete exit as an applied
   reset. Fail the exit on this observation and never rebind or issue a clear to
   the replacement. New leave/close consumer oracles observed the old code
   resolving instead of rejecting: full Perform file, 141 PASS/2 FAIL, actual
   exit 1. Change only the owner-change branch to throw; keep the same reset
   budget, same-owner applied-mask fence, cursor, record/replay lifetime and
   replacement ownership. Documentation states this narrower failure boundary.
2. Reject the rapid-toggle finding as already guarded. The controller's
   `state.padGates.provenance !== "core"` check precedes intent construction,
   and synchronous pending dispatch precedes queue admission. An immediate
   second controller call is rejected. The existing delayed-readback oracle
   directly invokes the controller twice and checks one producer admission.
3. Reject the arbitrary-burst scanner concern for this fixed-fixture oracle.
   Both real source files are exactly 4800 frames at 48 kHz; every strike waits
   180 ms held plus 200 ms after the release acknowledgement. The 4928-frame
   scan window isolates these 100 ms sources within the bounded strike spacing;
   exact four-burst count, amplitude ratios and replay comparison remain strict.
   This is not a parser acceptance claim for arbitrary short/overlapping audio.

Repair scope remains within the already-declared Task15: controller, complete
Perform test, both Host pages and plan. No Core/SDK/producer/S6 or CSS changes;
no new gate, filter, timeout or dropped journey. General UNKNOWN, same closed
owner, restart, physical/hearing and V1 settlement debts remain. Validate the
complete relevant files and normal Portal, ship the scoped review repair, then
rerun the entire clean-head Creator proof and obtain fresh independent head
review before guarded squash merge. Retain all old successful and failed logs.

Review repair verification before commit: complete Perform file 143/143 PASS
(the two new owner-epoch exits are red-before/green-after), complete Workspace
197/197 PASS, TypeScript exit 0 and normal Portal exit 0 (179 tests/52 pages/
10 diagram sources/20 outputs/50 routes). All tracked repair paths are the five
already-declared C2 paths above. Final clean-head complete proof remains owed.

## Native cancellation apply-point caller correction

The full `fe46dffa52b7075e185474d212c93d6f29936207` run completed all original
eight groups and naturally exited 1: 77 UI files/1595 tests passed; browsers
160 PASS/1 FAIL/11 existing skips. The sole failure was the existing Perform
Launch cancellation/requeue journey, with `idle` instead of expected `pending`.
The complete raw log is retained with SHA256
`37c8807255e33a4cf6aaef06885310330e8bf59e5008e528dd850a0419504c1b`.
All C2 masks, FX/HOLD first-screen, recovery, Sample, Capture and deployment
legs passed. The complete results, trace, diagnostics, distribution and natural
22-PID release readback are retained in `proof-final-fe46dffa/`; this run stays FAIL.

Actual transport diagnostics have zero capture losses and no unknown outcomes.
The first switch was accepted for frame 365312. Withdrawal succeeded and logical
`pending_switch` became null at frame 281856. Requeue at about frame 285000 was
positively refused with `HOST_STATE_INVALID/pattern_publication_pending`, before
any new publication. This was not a C2 mask or changed-epoch failure.

Current native source explains the missing far side: `cancel_pattern_publication`
clears the audio-owned token, but retains its audio-local slot until the original
activation frame; `RealtimeEngine::render` reclaims it then. The Control Runtime
correctly refuses an outstanding cancellation in `foreign_pattern_publication_pending`.
Logical cancellation alone is not native retirement.

Keep every original leg and assertion. Save the first accepted target's activation
frame, observe actual Runtime crossing that boundary with the existing launch
deadline and 50 ms sampling, then assert the withdrawn target never became current
and pending remains null. Only then enter the unchanged early-bar phase and issue
the original final Launch. This adds the missing cancellation far-side assertion,
with no command retry, synthetic response, fixed delay, timeout increase, worker
change or Core/S6 source repair. Only the already-declared Perform browser file
and plan change. The entire Perform browser file is verified before a new clean-head
complete proof. All prior successes and failures remain exact-input historical receipts.

The entire Perform browser file then exited 0: 18/18 PASS, including the unchanged
Launch/withdraw/requeue, FX/HOLD, both recovery, C2 initial/later masks, PCM, leave,
save/reopen/Replay legs. Raw log SHA256:
`18fead05e12b48561f67b14c790a5341526b3206b25c9628e2dda0ee3e69d7eb`.
This development verification does not substitute for final clean-head eight-group
proof. Product, CSS, SDK, Core and producer files are identical to fe46dffa; the
current real 30-scene/480-Pad geometry receipts remain tied to those exact product
inputs, with no broad physical/UNKNOWN acceptance.
