# Sequence: audible encoder tempo preview

## Outcome and authority

Close the BPM acceptance gap in the Creator Desktop Final follow-up Goal.
The owner has approved immediate preview, one authoring save/Undo after
400 ms idle, and cancellation of an uncommitted preview on page, Pad or Project
change, System, Escape, history navigation and loss of ownership. A numeric
readback alone does not meet that approval. Recording admission continues to
reject BPM changes.

On 2026-10-10 the owner approved
[continuous position-preserving preview](../prd/decisions/2026-10-10-sequence-audible-tempo-preview.md):
the BPM encoder immediately changes playback speed while continuing at the
current musical bar/beat position. Keep the approved 400 ms authoring save/Undo.
This supersedes the old next-bar restart boundary for encoder preview only;
the 2026-10-02 touch slider release/blur, direct-step and Tap Tempo behavior
remains separate. No product playback-position decision is outstanding.

This plan covers source delivery and acceptance, not release or deployment.
It supplements, and does not reduce, the parent follow-up Goal.

## Refreshed premises

Original planning base: `50d79fa894f3483d6593d50fafcfd3e1bff28ce0`;
original plan-only PR head: `1d3e6a4e90540b7858196380b65492f33901f500`.
Historical refreshed integration base for the approved decision Task:
`e9dae833d1c609bb203030a62053dee39b9d8b61`. That isolated docs branch merged
the actual main into the original PR history without editing the original
worktree or discarding its plan, reusing PR #1929. The native I2a Task below
is a separate implementation Pull Request.

- **Still outstanding:** `app.tsx` keeps `tempoPreview` locally and sends
  `updateSequenceSettings` only on idle. Cancel clears only the local number.
  Existing browser cases inspect that number and committed history; they do
  not observe pre-commit Pattern timing or clicks.
- **Still outstanding:** the Web control/runtime session has an authoring
  settings operation but no reversible tempo-preview lifecycle. The Facade
  settings command persists Truth before updating a recording anchor; it
  cannot serve as a no-history preview.
- **Still outstanding:**
  `publish_pattern_view_preserving_phase` requires identical BPM. Its native
  regression expressly rejects changed BPM. Removing that check would weaken
  the existing grid-edit publication contract, and retaining only the old
  frame origin would not retain musical position at a different rate.
- **Available, reusable:** immutable Pattern preparation, the serialized
  control owner, publication generations, transport admission fences and
  `freeze_transport_bpm`. The freeze helper retains the exact tick numerator
  at a transition rather than rounding to a whole beat.
- **Already delivered, do not repeat:** the direct-settings/metronome
  implementation, Sequence navigation, #1905 refresh, monitoring producer and
  #1936 contextual consumer (`9b4d80c9e5ed965f5776c0321cf166d9d1f289ce`).
  Consumer merge does not close its five unresolved original browser failures
  or the audible preview gap.
- **Relevant successors:** #1985 adds `pattern.transport.switch`; #1990
  (`e9dae833d1c609bb203030a62053dee39b9d8b61`) repairs a named successor's
  generation fence after outside republication. Neither introduces reversible
  tempo preview. Inspection includes the complete Host operation registration,
  actual settings handler and Session public object, not only a name search.
- **Implementation dependency delivered:** Core #1984, S4 and F1 are merged;
  the I2a refresh below pins their selected combined source. Preserve their
  cutoff/claim, selected-boundary and Filter behavior. Refresh all timing
  premises at each dependent Task start.

## Approved playback behavior and implementation contract

Implement the approved continuous preview with these lifecycle boundaries:

1. A preview changes actual Pattern scheduling at the first effective audio
   render frame. Keep its exact fractional musical position and sounding
   voices. Never allocate, reclaim or lock on the render thread. Preserve the
   existing same-tempo grid-edit API and its rejection tests.
2. Control owns a preview identity, source Project/Pattern/revision and runtime
   generation. Preview changes create no durable command, revision or history
   entry. Hosts obtain prepared source through the Application Facade and do
   not read Project bundles themselves.
3. Expose the effective audio frame, exact tempo anchor and applied BPM from
   the producer. The metronome consumes that same anchor. A second Host-only
   click clock or a display-only BPM must not stand in for engine tempo.
4. Repeated detents update the same preview. A stale preview, revision,
   generation, Project or owner cannot modify a newer target. Pending Pattern
   switches, recording and replay retain their existing timing authority.
5. Cancel restores the current committed BPM at the current musical position;
   it does not rewind playback or restore stale Truth. Return-to-base and every
   approved cancellation boundary produce no save or history entry.
6. At 400 ms idle, commit the final value exactly once through existing
   authoring. Keep the audible value through the save; do not briefly clear it
   before committing. A real committed result remains committed even if a
   later response or publication fails. Dispose of the preview only using
   an acknowledged commit/cancel or a terminal owner transition.
7. The Creator queue orders preview, save, cancellation and navigation so an
   old asynchronous result cannot retarget a new page/Project. Clear timer and
   producer state separately: `onPreview(null)` currently runs for both idle
   commit and cancellation and is insufficient to choose the backend action.

Operation names and public response shapes will be declared in I2b before its
first implementation edit. The product decision does not approve a persisted
Contract change or alter record/replay semantics. A newly exposed operation
must be added to the real Web bridge registration, not only the handler/SDK.

## Implementation Tasks

Each Task is one declared, independently reviewable commit. Start each with
fresh main and successor inspection; after actual files are confirmed, update
these declarations before editing. Do not count this plan as implementation.

### I2a — Runtime timing primitive

Implementation refresh (2026-10-11): own `fix/sequence-tempo-switch-phase`
worktree starts at fresh `96802c0f8764d04cbf3d3c913e82292a01284ac9`, tree
`12447580f3cb82cb1df9077560cc12e8dbffe72a`. Core #1984 and S4 are delivered;
F1 is merged at `a61ab819686ad896a3192e4a4bce1541ae55676d`. Their Q/A
reservation frontier, selected snap, claimed predecessor, Filter constructors
and seven FX remain required behavior. The 968 child changes only S6 docs.
Live open PR file lists (#2011/#2010/#2008/#2001) do not overlap this Task's
12 files. P0 retains Domain/ProjectIO/Cooker; M1 follows I2a sequentially.

At this base `publish_pattern_view_preserving_phase` still rejects changed
BPM; prepared timing and the selected switch helper are physical-origin based.
The new primitive remains outstanding. The old private draft is an authenticated
input, not a passing implementation: its syntax-negative and UNRUN boundaries
remain retained. Both complete integration reports require the S4 early selected
branch to use a coherent current rational anchor while actual claimed B uses
its own activation and geometry. The static 120→240 at frame 12,001, request
13,001 witness expects Beat/Bar/two-Bar End 18,001/54,001/102,001; actual RED
was reproduced in the rebuilt combined candidate: Beat returned 24,000 at
`continuous_tempo_selected_switch_uses_musical_position` rather than 18,001
(CTest exit 8). No defect in the existing unmodified S4 product is claimed
solely from the earlier static arithmetic.

Native-only scope: continuous checked timing, optional exact cutoff anchor,
selected switch integration, and existing owning component/stress/FX checks.
I2b/I2c, first Record profile, metronome, 400 ms durable UI lifecycle and hearing
remain separate. ENC4 remains device-local monitoring. No concurrency or
persisted Contract decision is added.


Declared files: this plan;
`packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`;
`packages/audio-runtime/src/prepared_sample_bank.cpp`;
`packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`;
`packages/audio-runtime/src/realtime_engine.cpp`;
`tests/core/audio/prepared_sample_bank_test.cpp`;
`tests/core/audio/realtime_engine_test.cpp`;
`tests/core/audio/realtime_engine_stress_test.cpp`;
`apps/docs-site/docs/core/modules/audio-runtime.mdx`;
`apps/docs-site/diagrams/audio-runtime.architecture.json`;
`apps/docs-site/static/diagrams/audio-runtime.html`;
`apps/docs-site/static/diagrams/audio-runtime.svg`.

Add a separate tempo transition, not a relaxation of same-BPM event editing.
Keep rational position, event-onset ordering and immutable material ownership
through transition, cancellation and loops. Publish an honest applied timing
observation for dependent consumers.

Lowest-tier verification: native prepared-pattern and realtime-engine
registrations. Exact frame/PCM assertions cover acceleration, deceleration
(including a logical loop origin before frame zero), fractional ticks, an event
at the effective frame occurring once, next-loop scheduling, held-voice
continuity, stale generation, pending switch, stopped transport and slot
exhaustion. Retain no-allocation callback checks. Run the existing stress tier
for publication/render races and build every red/mutation proof afresh.

#### I2a native interface and verification contract

Public C++ interfaces:

- `anchored_tick_boundary_frame(const TransportAnchor&, std::uint64_t tick)
  noexcept` returns `std::optional<std::uint64_t>` with checked integer ceiling.
  A previously reached tick is due at the anchor frame; invalid timing or
  overflow is unavailable. This helper constructs no allocating Error, and
  consumers must reject unavailable scheduling rather than invent a far-future
  release frame.
- `PreparedPatternView::with_tempo(std::uint16_t bpm) const` returns
  `foundation::Result<PreparedPatternView>`. Validate 40..240; retain exact
  Project/Pattern/revision, PPQ, loop ticks, canonical events, overlay flag and
  shared immutable PCM owners. Only BPM and derived frame bounds change. The
  input view and source snapshot are never modified. No PCM copy or Project
  parse is introduced.
- `RealtimeEngine::publish_pattern_tempo_transition(PreparedPatternView&&,
  std::uint64_t expected_generation) noexcept` returns the existing
  `PatternPublication`. It is a separate timing mode. Require the exact current
  generation, same source Project/Pattern/revision/PPQ/loop and identical event,
  playback and immutable material identities except derived timing frames.
  Refuse a pending publication or reserved transport receipt/command before
  changing the current Pattern; retain existing pool/exhaustion results.
  A caller retains the immutable prepared source and derives each detent or
  cancellation view from it. A cancel uses this same primitive with the actual
  committed BPM; authoring/lifecycle ownership is I2b.
- `PatternTempoObservation` carries `start_epoch`, `pattern_generation`,
  `applied_frame`, exact `TransportAnchor anchor`, and `playing`.
  `pattern_tempo_observation(expected_generation)` returns an optional coherent
  audio-produced value in the serialized control lane, never a predicted
  publication frame. Stale/missing generation returns unavailable.
- Append `std::optional<TransportAnchor> tempo_anchor` to `PatternTransportReceipt`.
  It is retained from the audio cutoff cell and describes musical position at
  `effective_frame`. The old physical `origin_frame` remains the last Pattern
  start/restart frame; after a tempo transition it cannot substitute for this
  anchor. Existing consumers remain unchanged and the new primitive has no
  product caller until I2b. Unrepresentable cutoff position leaves this new
  field unavailable; it never manufactures zero. I2b must refuse recording
  timing without an exact anchor. Existing cutoff authority/fields stay valid.
  I2b must refresh
  the Facade/controller declaration if consuming this field requires those
  files; source-only delivery does not silently discharge that obligation.

Units: engine frames are uint64 at 48 kHz; PPQ is 960; tick numerator uses fixed
denominator 2,880,000. At audio apply F, retain the exact previous numerator
and freeze `{runtime_frame=F, tick_numerator=N(F), bpm=new_bpm}`. Legacy grid
position is its actual whole-loop count plus exact local-frame fraction;
continuous mode subsequently integrates from the rational anchor. No rounded
whole beat or unsigned synthetic origin is used.

The audio event cursor names an absolute musical loop and next canonical event.
Seek to the first onset after the last actually scheduled frame; the first
render frame crossing an onset numerator schedules it exactly once. This keeps
an onset due at F without retriggering one already scheduled at F-1. Loop
rollover uses tick length, not repeated rounded frame lengths. Held voices keep
their PCM cursor, envelope and owner. Gated musical note-off retains its
absolute release tick and is retimed from the same anchor; one-shot audio and
already releasing tails keep their existing lifetime. Callback arithmetic is
checked, allocation-free integer work; no error-string construction, locks,
reclaim or shared-owner destruction occurs there. Stopped Pattern transport
stays stopped, and a new start resets musical position to zero.

Atomic admission reuses #1984's reserved/invalidation Q mailbox, serialized
control producer and audio claim. There is no second mutation queue. The
current immutable generation is validated under that admission; any concurrent
claim invalidates final CAS and forces control to reread timing/identity.
Pending Q/A and reserved cutoff refuse tempo publication. First actual apply
F, current generation and anchor are handed over as one value, so a delayed
control observation cannot splice a new tempo onto an old generation. Normal
same-BPM phase edits keep their original contract and refusal oracle; when
editing an already continuous grid their event seek retains the rational clock.
Stop/Record/fence retains the existing cutoff and immutable receipt semantics.

Selected Beat/Bar/End uses one coherent current generation/frame/origin/anchor
observation. An ordinary claimed predecessor still supplies its own tick-zero
activation and geometry. A claimed same-BPM phase edit is clock-equivalent only
with the same Project/Pattern/BPM/PPQ/loop; its retained continuous anchor is
used without inventing a restart. A newly introduced claimed tempo transition
has no applied anchor until its real application: selected switch admission
returns the existing `publication_pending` before taking a generation or
mutating accepted Q/A state. Even `render(0)` can claim without applying.
Previously accepted Q and B remain intact; after actual tempo apply the original
caller can retry against the coherent applied clock. This native retry is not
implemented by the existing product adapter.

Lowest registrations: `audio.prepared_sample_bank`, `audio.realtime_engine`,
and required stress `audio.realtime_spsc_stress`. The main oracle observes actual
PCM/onset frames, independently calculated: 120→240 at F=12,001 retains numerator
1,382,515,200 and next tick 960 at frame 18,001; 240→120 at F=12,001 gives next
tick 1,920 at frame 35,999, equivalent logical origin -12,001. Cancellation,
boundary-once, next-loop, held-voice/release, stale identity, queued/claimed
switch, reserved cutoff, stopped transport and full pool each retain far-side
assertions. Stress races publication/render/reclaim and cutoff while allocator
guards remain active on callback. A targeted mutation that resets the numerator
at F must fail the actual onset assertion in a freshly rebuilt executable;
missing-symbol compile failure is not this RED proof.

Same-BPM revision adoption must retain the fractional anchor and PCM onsets
18,001/30,001/42,001/54,001. Near-limit native oracles independently require a
due Voice with an unrepresentable release to remain unallocated, failed tempo
apply to spend the claimed owner without applied evidence, and overflow cutoff
to retain an unavailable anchor. A stopped overflow position stays unavailable
through repeated Stop; the existing stopped Fence refusal remains intact and
only explicit Start resets it. These tests use existing quiescent clock seams,
not new production hooks.

Historical private draft evidence remains syntax-only. Its first syntax command
omitted the Audio source include and another exposed a missing optional-field
initializer; corrected syntax commands passed. None was behavior RED. Private
configure/build/native/stress/Portal/Wasm/Creator/hearing remained UNRUN.
Fresh Linux execution: configure and stable dev build passed. The initial
build stopped on a new test's range-loop copy warning; correcting the reference
binding produced an actual build exit 0 before behavioral RED. The selected
switch RED above then became green with the continuous early-branch fix. A
separate reset-to-zero mutation rebuilt the Engine/test target (exit 0), then
failed the independent actual onset assertion in `check_tempo_onset` at 18,001
(CTest exit 8). Both source restorations use fresh mtimes. The native registration inventory
contains 16 Audio entries: 12 non-stress and four stress. Eleven non-stress
entries passed together; the new paused-callback ownership test initially
expected latest-only telemetry to include an unpublished audio observation.
It now asserts the exact retained Q/A authority instead; its rebuilt Engine
registration passed all 169 test functions (149 unchanged original functions).
PreparedSampleBank passed 14 functions (12 original); the SPSC registration
passed all nine scenarios (eight original) with its original 180 s budget.
The full explicit dev stress tier completed 14/15, exit 8: unchanged
`audio.master_fx_stress` reported one of 3,750 callbacks at 4,156,463 ns against
its unchanged 2,666,666 ns deadline (mean 59,088 ns), with no recorded host
accounting attribution. Preserve that failure; it is not a green full stress
run or proof of a host cause. Bounded diagnostic and final Portal outcomes
are reported separately at handoff. The original draft's
syntax results are not substituted for these executions.

Caller trace: the existing `control_runtime.cpp::publish_transport_pattern`
turns every nonaccepted Engine result into an unavailable publication error;
it does not automatically retry native `publication_pending`. The new tempo
primitive has no production caller in I2a. I2b must establish acknowledged
preview clear before Pattern switch and explicitly handle the native transient
boundary in its adapter/controller proof; a pending result cannot be reported
as success or silently reinterpreted as an automatic retry.

### I2b — Facade/Web preview lifecycle

Declared files: this plan;
`packages/application-facade/include/lmdj/facade/application.hpp`;
`packages/application-facade/src/application.cpp`;
`tests/core/facade/sequence_surface_test.cpp`;
`packages/web-runtime-platform/src/bridge.cpp`;
`packages/web-runtime-platform/src/control_runtime.cpp`;
`packages/web-runtime-platform/web/runtime_session.mjs`;
`packages/web-runtime-platform/web/runtime_types.d.ts`;
`packages/web-runtime-platform/test/control_runtime_test.cpp`;
`packages/web-runtime-platform/test/runtime_session.test.mjs`;
`tests/platform/web/audio/realtime_audio_worklet.spec.mjs`;
`apps/docs-site/docs/core/modules/application-facade.mdx`;
`apps/docs-site/docs/core/modules/web-runtime-platform.mdx`;
`apps/docs-site/docs/platform/web-runtime.mdx`.

Depends on actual I2a delivery. Prepare through the Facade, validate source and
preview ownership, apply/set/clear without authoring, and reconcile the single
authoring commit without an audible revert. Reject conflicting admission and
stale clear before changing the runtime. Recording, replay, Project replacement
and terminal cleanup cannot retain or resurrect an old preview.

Lowest-tier verification: Facade/Control native cases and RuntimeSession Node
cases. Rebuilt Wasm/AudioWorklet acceptance must observe actual onset frames
before preview, during it, after cancel, during a second preview and after one
commit. Assert complete Truth/revision/history after every transition, reject
cases and reopen; observed numeric BPM alone is not the oracle.

### I2c — Creator binding and metronome

Declared files: this plan;
`apps/creator-web/src/app.tsx`;
`apps/creator-web/src/runtime/runtime_types.ts`;
`apps/creator-web/src/state/encoder_input.ts`;
`apps/creator-web/src/runtime/metronome_scheduler.ts`;
`apps/creator-web/src/runtime/metronome_click.ts`;
`apps/creator-web/test/encoder_input.test.ts`;
`apps/creator-web/test/metronome_scheduler.test.ts`;
`apps/creator-web/test/metronome_click.test.ts`;
`apps/creator-web/test/hardware_console.test.tsx`;
`tests/platform/web/creator/creator_web_sequence_grid.spec.mjs`;
`tests/platform/web/creator/creator_web_metronome.spec.mjs`;
`apps/docs-site/docs/hosts/creator-web.mdx`;
`apps/docs-site/docs/platform/input.mdx`.

Depends on actual I2b and contextual-encoder delivery. Bind the approved idle
and cancellation behavior to the producer and consume its timing projection in
both playback feedback and metronome scheduling. Preserve direct controls'
separately documented behavior unless explicitly covered by the new decision.

Lowest-tier verification: injected-clock encoder/async-owner and metronome
tests, TypeScript, then packaged Creator input journeys with actual Wasm timing
and click observations. Cover Escape, page/Pad/Project/System, history,
return-to-base, owner interruption, recording lock, rejection and late save
responses; one settled turn must save once, undo once and reopen with that
Truth. Complete the selected Creator lane. Physical listening/input evidence
remains A2, not an inference from headless results.

## Version Management

Plan-only Version impact: none — no source or active identity changes.
I2a Version impact: Audio Runtime MAJOR ABI debt. Concrete public
`RealtimeEngine` gains rational scheduling/observation state;
`PatternTransportReceipt` gains an optional exact anchor. Existing call sites
remain source-compatible, but the changed public object layout is not binary
compatible. Additive methods alone do not make this MINOR. Parent V1 retains
the unresolved real module/API/dependency settlement; this 12-file Task changes
no manifests and allocates no Product Build or guessed identity. Persisted
Project/Journal formats remain unchanged. I2b/I2c must assess their own actual
public source and ABI impact. No tag, release, deployment or Channel action.

## Planning Task verification

The original planning Task declared only this file. The approved-decision
follow-up Task additionally declares the two 2026-10-10 decision files for
tempo preview and Sample Assign/numeric editing, the parent follow-up plan,
and `docs/prd/questions/hardware-control-mapping.md`, as listed in the parent.
Validate all declared source/test/page paths against this base, inspect the
approved scope against the prior direct-control timing and actual encoder
lifecycle, check relative links/whitespace, and run the staged new-file ownership
suite plus the clean committed-head docs_static lane. A plan review must retain
the real audible acceptance gap and must not claim the newly approved behavior
has already been implemented. That planning Task edited no product or Portal source; native I2a changes
the explicitly declared source and Portal files above.

## Documentation impact

I2a Documentation impact: required
Affected portal pages: /core/modules/audio-runtime/
Reason: continuous scheduling, applied clock observations and exact cutoff
anchors change the Audio Runtime public boundary. Update its existing source
diagram and official generated HTML/SVG in the same Task.

Original plan-only Documentation impact: none — that Task changed no Portal
page or source fact.
Each implementation Task declares required impact for its listed existing
Portal routes and runs `scripts/docs-site.sh check` before commit. Resolve
actual paths, update affected diagrams when necessary, and verify new-file
ownership before staging completion.

## Completion evidence

Native/unit passes, a prepared stack, one targeted browser pass or successful
review infrastructure alone cannot close D2. Require actual source merges,
the complete selected input-bound verification evidence, valid exact-head
independent review, and the complete playback/cancel/save/Undo/reopen journey.
Keep unavailable physical acceptance separate and explicit in the parent Goal.

## 2026-10-12 I2a authorized resume

User requested completion of the remaining worktrees. Refreshed integration
base `c2de40b6471a40b830980d6ce88fdb600988437c`; original I2a base
`96802c0f8764d04cbf3d3c913e82292a01284ac9` remains retained. No successor
delivers `with_tempo`, `publish_pattern_tempo_transition`, the exact applied
tempo observation or cutoff anchor. Those I2a premises remain outstanding.

Relevant successor #2037 (`7df1af16df5e6d864ca7968626d63f84a5d9cb63`) adds
live Pad Mute/Solo before shared FX with epoch-stamped accepted/applied gates.
Preserve its complete source and tests while importing the original 12-file
I2a patch with three-way application. Current main's Keyboard docs/input
successors do not alter these declared files. The original worktree, failed
full stress receipt and rebuilt onset mutation remain unchanged.

Scope remains native I2a only. I2b/I2c, Web/Creator audible preview, physical
acceptance and V1 MAJOR ABI settlement remain explicitly outstanding. No
release operation or identity allocation. Keep the existing twelve declared
files, exact onset/cancel/held-voice/switch/overflow/refusal acceptance cases,
allocator guards and complete existing stress selection. Rebuild this combined
source, run all owning Audio non-stress registrations and SPSC stress, rebuild
the reset-anchor mutation and restoration, regenerate the owning official
diagram if needed and run the unchanged complete Portal check before shipping.
The unchanged full dev stress tier must pass; a nonzero result remains a gate
and stops shipping. The Master FX minimal accounting repair is a separate Task
and must not be folded into I2a or inferred green from deterministic witnesses.

Evidence: `/home/en/orca/evidence/worktree-resume-20261012/`.

### Resume verification checkpoint

Combined source and all selected native target builds exit 0. The original
12 Audio non-stress registrations pass, and the owning SPSC stress registration
passes all nine scenario bodies. The complete Portal check with Node 26.7.0
passes all 176 tests, 52 pages, 10 sources/20 outputs and 50 routes/links.
The first broad audio-tag run had nine unbuilt dependency executables; after
building every selected target, the unchanged complete 21-entry selection
passes 20/21 but exposes the Web replay-handoff fixture HOST_TIMEOUT at line
7371. That fixture's missing final Pad gate drain is investigated as a separate
test Task; no I2a production diagnosis is inferred solely from the timeout.

The complete original dev stress tier executes once, exit 8, 14/15 PASS:
unchanged audio.master_fx_stress reports three unattributed Eight-FX overruns,
mean 69,159 ns, worst 10,596,443 ns against strict 2,666,666 ns. All other
14 registrations, including the 153.45-second candidate-store process stress,
pass. Retain the failed full receipt. I2a shipping remains stopped; no full
stress pass, commit, PR or physical acceptance is claimed.

The fresh zero-numerator anchor mutation rebuilds and fails the exact activation
frame assertion in `realtime_engine_test.cpp:6190`, exit 8. This is an earlier
assertion than the PCM onset check; no later assertion is claimed reached.
The orchestration script's anticipated failure-string check was too narrow;
its finally block restored the complete working source with fresh mtime and
rebuilt the object, exit 0. A separate unchanged complete Engine registration
on that verified restored input passes, exit 0. All receipts remain retained.

Final combined integration base: `43f41d2f1cf0f8294568e9964c058d141421aa46`,
including direct Replay profile preflight (#2068) and the native Web reset
fixture correction (#2070). All twelve I2a files survive this fast-forward
byte-for-byte. Fresh full selected-target build exits 0; the complete original
21-entry Audio non-stress selection now passes 21/21, exit 0 in 78.27 seconds.
The complete Portal check again passes 176 tests, 52 pages, 10 diagrams/20
outputs, typecheck/build and 50 routes/links. These cover the changed combined
inputs; they do not clear the retained 14/15 full-stress failure. No blind
MasterFX or complete stress retry, Task commit, PR or ABI settlement.

Return these twelve working files to the original
`fix-sequence-tempo-switch-phase` worktree on this base. Preserve its original
bytes in an exact named stash, external bundle and file archive before the
transfer; prove every resumed file byte-identical before removing the owned
temporary duplicate without force. Retain fresh build and Portal artifacts
under the resume evidence directory. The original branch/worktree remains the
continuation location; original failed receipts and source are recoverable.

## 2026-10-13 I2a worktree completion refresh

The owner requested that each remaining worktree and branch be finished through
PR/merge or safely cleaned. Refreshed integration base:
`9fb83ce0f70de1bc9114711bf9e854dfa6bb7081`; the twelve source files in the
2026-10-12 continuation were preserved in an exact named stash, independently
verified external bundle and byte archive before fast-forwarding this original
worktree. All twelve working files remain byte-identical after that transfer.
Evidence: `/home/en/orca/evidence/worktree-finish-20261013/sequence/`.

Premise dispositions at this exact base:

- **Still outstanding, native I2a:** the current Audio Runtime has the existing
  same-BPM phase-edit publication and its refusal regression, but no tempo-only
  publication, immutable `with_tempo` derivation, applied tempo observation or
  exact cutoff anchor. Inspection covers the complete Engine declarations,
  publication modes and scheduling/cutoff producers plus their owning tests;
  the same-BPM API is the positive control. No intervening main commit changes
  any of the twelve declared files.
- **Already delivered, retain:** #2066 repairs replay neutral-gate queue order
  and #2083 exposes the typed Performance live-control Web producer. Their
  actual merged source is part of this refreshed base. They neither produce
  nor consume the new tempo-only primitive; no repeated implementation is
  included here.
- **Still outstanding, separate Tasks:** I2b/I2c preview lifecycle, metronome,
  durable 400 ms save/cancel/Undo/reopen and physical acceptance retain all
  original requirements. The current Web Session's settings operation and
  Creator local `tempoPreview` remain the inspection controls; the complete
  operation registration and handlers contain no reversible tempo producer.
- **Still outstanding, identity settlement:** public Engine and receipt layout
  changes remain MAJOR ABI debt for the parent V1 cut. No manifest, Product
  Build, Channel or release transition is changed or allocated by this Task.

Task scope, twelve declared files, acceptance assertions and strict deadlines
remain unchanged. Reconfigure and rebuild all selected targets against this
combined base; then run the complete original dev stress tier once during an
exclusive local performance-test interval, without concurrent compilation,
Portal or non-stress execution. This new combined input requires new evidence;
it does not clear or relabel either earlier failed full-stress receipt. A
nonzero complete-stress result continues to stop Task shipping. Run the owning
Audio non-stress and complete Portal checks separately after that boundary.

### 2026-10-13 verification and retained blocker

The fresh stable dev configure and full build both exit 0. The complete
unchanged 15-registration dev stress selection executes once, exits 8 after
178.20 seconds, and passes 14/15. The owning SPSC registration passes all nine
scenario bodies in 5.41 seconds. Candidate-store process stress passes in
154.36 seconds; no registration is removed or replaced with a focused result.

The only failed registration is the unchanged `audio.master_fx_stress`:
the Eight-FX scenario reports two unattributed overruns among 3,750 callbacks,
mean 64,540 ns and worst 9,971,515 ns against the unchanged 2,666,666 ns thread
CPU deadline. A further one overrun is attributed by its host counter rule.
The assertion at `master_fx_stress_test.cpp:350` fails; the later five MasterFX
scenario bodies remain unreached. This is a failed complete-stress gate, not
evidence of a particular physical cause or a tempo-primitive defect.

Performance context is bounded precisely. The stage receipt spans
02:46:08.266662–02:49:06.481744 UTC. Later Replay and Master draft Git bundle
archives overlap this complete stage, so it was not exclusive throughout.
Their filesystem evidence bounds possible archive work respectively within
02:46:37.923130–02:47:07.673361 and
02:46:51.772237–02:47:21.206466 UTC; exact child PID/start/end was not captured.
Subtracting all nine sequential registrations after MasterFX from stage end,
with 0.01 seconds allowed rounding loss per printed duration, bounds MasterFX
completion before 02:46:18.921744 UTC. Neither of these known later archives
overlaps that failed registration. Keep both the complete-stage limitation and
this narrower distinction; neither proves an Engine or host cause. Evidence
and the reproducible bound are in `performance-interval-limit.json`.

The separately executed complete Audio non-stress selection passes 21/21,
exit 0 after 78.69 seconds, including the combined main Web control-runtime
registration in 65.55 seconds. The unchanged complete Portal check with the
official Node 26.7.0 toolchain passes, exit 0: 177 tests, 52 pages, 10 source
diagrams/20 outputs, typecheck/production build and 50 routes/internal links.
Its existing current Build snapshot check also passes. These are input-bound
selected passes; they do not clear the failed full-stress receipt or allocate
a new identity.

No retry until green, deadline change, Task commit, push, PR or merge follows
the red strict gate. The original branch and worktree retain all twelve
uncommitted files for further verified work. No dirty directory is removed;
the pre-resume stash, verified bundle, complete file archive and all new
receipts remain retained. I2b/I2c, V1 MAJOR ABI settlement, complete sanitizer
and product-candidate checks, and physical acceptance remain outstanding.

## 2026-10-13 renewed worktree disposition

The owner explicitly requested completion of all necessary unattended worktrees
and authorized removal of obsolete work after preserving its evidence. This
I2a draft remains necessary at refreshed main
`73fc1c7bf0cd2f0a7f52cef481d0746ff032dd22`: the approved continuous audible
BPM preview decision and parent D2/I2 remain current, and live Interaction UI
umbrella #2112 retains F08 with the I2a–I2c dependency chain. No delivered
successor replaces the native tempo primitive. This is a continuation of the
existing Task, not a fresh parallel implementation.

Authoritative source inspection uses the existing same-BPM phase publication
as a positive control, reads the complete Engine/prepared-view declarations,
publication modes and clock/cutoff producers, and follows Creator's actual
Encoder 3 callback through `setTempoPreview` and its 400 ms `settingsCommit`.
The complete 105-operation Web bridge registration and the real
`sequence.settings.update` handler/Session public object still contain only
the committed settings path, with no reversible tempo-preview lifecycle.
The 9fb83ce0→73fc1c7b range changes none of the twelve declared files; current
open PRs #2119, #2126 and #2128 contain no Audio Runtime/I2a file overlap.
The exact original worktree has no Orca terminal, and the complete local
terminal inventory contains only the coordinating root. This local evidence
does not assert the absence of every possible remote private session.

Issue #1973 remains an independent legacy repeated-Bar rounding defect. This
Task's continuous clock is neither its complete delivery nor I2b/I2c preview
binding. Keep all original native acceptance, callback allocator guards,
strict stress workloads/deadlines, cutoff authority and MAJOR ABI debt. No
consumer lifecycle, persisted Contract, identity or product decision is
silently added or settled.

Before fast-forward/reapply, all twelve original files and the complete binary
patch were preserved; an exact stash and verified 33,921-byte incremental
bundle retain the original working/index delta with 9fb83ce0 as an explicit
prerequisite. All twelve restored file hashes match. The archive receipt's
pre-refresh mtime dictionary was lost through local variable reuse before
serialization; that field is explicitly unverified, while restored mtimes are
recorded separately. Original byte/stash/bundle retention remains verified.
Evidence: `/home/en/orca/evidence/worktree-finalize-20261013/sequence/`.

Verification remains input-bound: rebuild the actual combined native/link
inputs, run the complete original dev stress selection once during a
coordinated performance interval, and execute the unchanged complete owning
Audio non-stress and Portal checks separately. A failed strict gate continues
to stop shipping; neither the new cleanup authorization nor the later focused
passes relabel a failure or make this still-required implementation obsolete.

### Renewed verification result on 73fc1c7b

Fresh stable dev configure/build exit 0; the full build finishes in
156.506 seconds. The complete original 15-registration dev stress selection
executes exactly once during the new coordinated interval and exits 8 after
167.620 seconds (06:15:06.467135–06:17:54.086944 UTC). Fourteen registrations
pass, including the complete owning SPSC registration in 4.84 seconds and
candidate-store process stress in 145.96 seconds. The unchanged MasterFX
Eight-FX scenario reports three unattributed deadline overruns among 3,750
callbacks, mean 64,905 ns, worst 10,724,857 ns against 2,666,666 ns; zero
attributed overruns. Its assertion at line 350 fails before the later five
MasterFX scenario bodies. Keep this failed full gate and every earlier failed
receipt. A separate zero-Engine diagnostic's successful collection exit is
neither product acceptance nor physical attribution of this run.

The original complete Audio non-stress selection separately passes 21/21,
exit 0 in 93.386 seconds, including the actual current Web control-runtime
registration in 80.32 seconds. The unchanged full Portal check separately
passes, exit 0 in 30.650 seconds: 179 tests, 52 pages, 10 diagram sources/20
outputs, typecheck/production build and 50 routes/internal links. Its existing
snapshot verification passes; no new identity or snapshot is allocated here.

Current native main-call inventory preserves every original call and its
parameterized legs: Realtime has 163 baseline invocations plus 20 additions
(183 current invocations, 178 distinct names); Prepared has 14 plus two
(16 current invocations, 15 distinct names); SPSC has nine plus one
(10 current scenario calls). The older nine-scenario/169 shorthand is not the
current full invocation inventory. Zero-argument counting alone would omit
nine Realtime invocations and two Prepared invocations; those cases remain
called and exercised by their complete registrations.

An independent agent reviewed all twelve dirty files on this base and found
no substantive static source finding, with complete diff/file hashes and
limitations preserved in
`/home/en/orca/evidence/worktree-finalize-20261013/sequence-independent-review/`.
It inspected the distinct historical actual-PCM and later activation-frame
mutation evidence without promoting one to the other. This local review is
not a committed-head trusted review, owner attestation, waiver or merge
authorization, and cannot clear the failed strict verification gate.

No Task commit, push, PR, merge, deadline relaxation or cleanup of this
still-necessary implementation follows the nonzero gate. The original
worktree and branch retain all twelve uncommitted files with original and
final byte/patch evidence; all owned build and test processes have completed.

## 2026-10-13 explicit ordinary-PR shipping request

The owner now explicitly requests PR creation and merge of this necessary
source Task under current ordinary-PR governance. Refreshed integration base:
`d46d90319d14e96896134e1d65a59e3e8b05694b`. The exact current AGENTS/CLAUDE,
shipping skill, Git workflow, version and Portal policies retain Task-specific
verification, independent current-head review, conflict and conversation
protection; they do not require every main batch/full lane to be green for an
ordinary source PR. The earlier hold/STOP checkpoints above remain historical
facts, including every actual nonzero receipt. This renewed scope does not
rename a failed complete stress run as passed or clear full/candidate debt.

The 73fc1c7b→d46d9031 range changes none of this Task's twelve declared files
or owning native timing tests. Preserve their complete source and explicit
fractional onset/cancel/held-voice/switch/cutoff/stopped/restart/overflow/refusal
assertions, allocator guards and ten SPSC scenario calls. The unchanged clean
baseline still lacks the tempo-only publication, immutable tempo derivation,
coherent applied timing observation and exact cutoff anchor; the existing
same-BPM phase API is retained as the inspection's positive control. Current
consumer inspection finds no production caller for these new I2a interfaces.

Relevant delivered successors are #2126 headered gesture status, #2134 SDK
recording-cursor reconciliation, #2138 owned capture handle, #2139 typed Filter
consumer and #2147 headered FX types. Retain their actual Facade/SDK/Creator
behavior and refresh the affected integrated tests. They do not deliver I2a or
authorize expanding it into I2b/c. The existing Product Build 96 allocation
and witness are already on this base: derive current identities from their
active manifests and run the unchanged complete Portal check against current
facts. This Task changes no manifest or Product identity. The later cut did
not settle the future MAJOR ABI debt of I2a's Engine/receipt layout; that
approved parent V1 obligation, persisted-format compatibility and no-release
boundary remain unchanged.

Before source shipping, apply `lmdj-review-ci-triage`'s clean-main comparison
to the complete original 15-registration selection on an isolated clean
baseline with its own exact-input build/library evidence. The unchanged
MasterFX failure must be shown pre-existing; a previous draft, diagnostic
collection exit or unrelated focused pass cannot establish that disposition.
Retain all strict scenario budgets and all six MasterFX acceptance legs,
including the later legs hidden by the original stop-at-first-budget-failure
control flow. Any defect caused by this Task or failing Task-owned timing,
ownership, restart or concurrent-publication verification must be fixed before
shipping. No timeout, callback deadline, workload or assertion is reduced.

The clean-main comparison and complete MasterFX leg evidence are pending at
this checkpoint; there is no commit, push or PR yet. Once those factual
dispositions and the Task's current integrated/Portal verification are
complete, use the normal one-Task Conventional Commit, push/PR, trusted exact-
head review and guarded squash merge. Local static review is advisory evidence,
not an owner waiver or a substitute for the trusted review boundary. Preserve
the current PR's entire findings/conversations and live protection, and keep
I2b/c, #1973 legacy Bar drift, complete sanitizer/candidate verification,
physical acceptance and V1 identity settlement explicitly outstanding.

Original bytes, mtimes, staged-list state and exact stash/incremental bundle
were preserved before fast-forwarding/reapplying this base, and all twelve
working hashes matched after transfer. Evidence:
`/home/en/orca/evidence/worktree-pr-merge-20261013/sequence/`.

The final current-input selection remains the complete original 15-entry dev
stress tier once, followed separately by all 21 Audio non-stress registrations
and the complete current Portal check. All fourteen other stress registrations
and every I2a timing/ownership/onset/restart/concurrency assertion must actually
pass; a new failure or failed Task assertion cannot be excused by a pre-existing
budget class. After the fresh build, run the same unchanged original six-
function selector harness against the actual I2a headers and libraries, with
the original flags, workloads and strict deadlines. This covers the changed
Voice/Engine layout beyond the first budget failure. Budget failures retain
their original outcomes and leave their subsequent internal assertions marked
unreached. No macro, trigger preparation, render work, loop or acceptance leg
is moved or dropped. The comparison informs source-PR risk disposition; it
does not certify realtime performance, physical acceptance or full readiness.

### Current-input verification and source-PR disposition

The owner explicitly authorizes this I2a source PR under current ordinary-PR
governance after the clean-main comparison and complete owning verification.
This supersedes the earlier draft's automatic source-shipping STOP on any
global stress failure. It does not supersede the strict deadlines, remove an
acceptance assertion, waive independent review or certify native performance.
Historical failed checkpoints above remain unchanged. A Task-caused failure
or failed I2a assertion still stops delivery; the pre-existing MasterFX budget
failures below remain failed complete/candidate verification debt.

Actual tested base is `d46d90319d14e96896134e1d65a59e3e8b05694b`, with the
unchanged eleven implementation/test/Portal files and this appended plan:

- Stable dev configure and complete build both exited zero. The complete
  original 15-registration stress selection ran once, exit 8: fourteen PASS,
  only `audio.master_fx_stress` FAIL at the original EightFX deadline assertion
  (line 350). It observed 3/3750 unattributed callbacks above 2,666,666 ns,
  mean 67,623 ns and worst 10,418,937 ns; none attributed. The later five
  functions were not reached by that registration. The fourteen completed
  registrations include all ten original-plus-I2a SPSC scenarios, publication
  lifetime, persistence/lease, provider, Facade/restart/lifetime and Cardputer
  threaded journeys with their original assertions and deadlines.
- The complete non-stress Audio label selection, `ctest --test-dir
  build/core/dev -L audio -LE stress --output-on-failure`, exited zero:
  21/21 PASS, including prepared-pattern, full RealtimeEngine, cooker,
  allocation/parity/determinism, Facade adapter and Web runtime/session/bridge.
  The complete native entry points retain 183 RealtimeEngine invocations,
  16 prepared-bank invocations and ten SPSC scenario calls, including the
  original parameterized calls and their arguments. An earlier mistaken
  name-prefix selection ran only twelve PASS; that separate receipt is
  retained and is not the complete 21-test proof.
- The unchanged complete `scripts/docs-site.sh check` exited zero with Node
  26.7.0 selected only for its child environment: 179/179 tests, 52 pages,
  ten diagram sources/twenty outputs, manifest-derived Product Build 2.0.96.0
  facts and matching existing snapshot, typecheck, production build and all
  fifty route/internal-link checks. No identity or snapshot was allocated.

An independently built, Git-clean exact-d46 control ran the same original
15-entry stress selection once: exit 8, fourteen PASS and the same EightFX
line-350 failure class (2/3750 unattributed, mean 63,459 ns, worst
10,180,228 ns). Its separate unchanged six-function observations completed
five functions; the full 128-kernel-voice/eight-FX function failed its original
line-498 budget assertion (22/1875 unattributed plus three attributed,
mean 1,291,907 ns, worst 11,909,015 ns). Its collection driver's zero exit
means scheduling completed, not six functions passed.

The same immutable original CPP and six-function selector were then compiled
with this worktree's actual public headers and four freshly rebuilt I2a
libraries, using the original target flags and deadline macros. No clean-main
executable or library was borrowed. Each original function was observed once,
serially, ending at 2026-10-13 11:41:09.265205 UTC. Actual child exits were
`[1, 1, 0, 0, 0, 0]`, aggregate exit 1:

- EightFX failed the original line-350 deadline: 2/3750 unattributed,
  none attributed, mean 62,270 ns, worst 10,955,884 ns.
- Full kernel voices/eight FX failed the original line-498 deadline:
  21/1875 unattributed plus three attributed, mean 1,272,205 ns,
  worst 12,410,748 ns.
- Full Tone voices, typed Filter queue refusal, independent Filter churn and
  restart-epoch acknowledgement all completed their original bodies and
  far-side assertions. The dev target's original optimized-deadline macro
  remains zero; this is not a Release-only optimized timing pass.

The two failed functions leave their subsequent internal assertions unreached.
The clean control's supplemental EightFX PASS and this supplemental FAIL are
different actual observations; the control's complete registration already
demonstrates that same deadline failure class. Neither this comparison nor
similar timing numbers prove a physical host cause or realtime equivalence.
All original callback counts, budgets, 128-trigger preparation and render
work inside the timing window were retained. No original journey was dropped,
no threshold changed and no same-artifact retry sought a green result.

Precommit freshness fetched `c4bde2ffa4390eb83e5ccc1e0313f933732bf88a`.
The intervening Slice UI PR changes Creator components/style/tests, its plan
and two Creator Portal pages. It changes none of I2a's twelve declared paths,
owning native/link/Facade inputs, manifest identities or Portal tooling; the
applicable AGENTS/CLAUDE, shipping/triage, workflow, version, Portal and pitfall
governance bytes match the tested base. The tested base remains explicit;
unrelated main movement does not require a mandatory rebase or repeating
unchanged verification. A later relevant MasterFX test-helper merge needs an
affected-input check before the final guarded merge; the immutable original
selector above cannot stand in for verification of a new helper.

The source Task delivers only the native I2a primitive and its owning
regressions. I2b lifecycle/Facade/SDK/Host producer wiring and I2c real browser
preview, cancellation/400-ms commit/Undo/reopen/metronome journeys remain
undelivered. The separate legacy Bar drift issue, physical audible acceptance,
complete ASan/TSan and candidate checks, failed realtime deadlines and approved
parent V1 MAJOR ABI identity settlement remain outstanding. Dev stress does
not establish absence of sanitizer-detectable races. No owner waiver, guessed
identity, release, deployment, permanent snapshot or full readiness is claimed.

Receipts, source/library/binary hashes, both full CTest logs, the original
six-function input comparison and raw per-function results are retained in
`/home/en/orca/evidence/worktree-pr-merge-20261013/sequence/`, with the clean
control in the sibling `baseline/`. The independent local source review is
advisory; the exact committed PR head still requires trusted independent
review and complete live findings/conversation/conflict/protection checks.
