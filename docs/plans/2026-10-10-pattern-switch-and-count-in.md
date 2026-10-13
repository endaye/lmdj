# Pattern 播放中切换（SEQ SNAP）与 count-in 实施计划（#1958、#1959）

## Outcome and authority

Patterns switch while the global transport plays and records, at the SEQ SNAP boundary, and Perform Pattern Launch works without a Performance recording. Record from stopped can count in with the metronome first.

The product decisions are:

- [`2026-10-10-pattern-switch-while-playing.md`](../prd/decisions/2026-10-10-pattern-switch-while-playing.md) (#1958);
- [`2026-10-10-record-key-and-count-in.md`](../prd/decisions/2026-10-10-record-key-and-count-in.md) (#1959).

The plan has seven product stages. Each implementation or declared preparatory Task is one Conventional Commit on its own short-lived branch, with verified commit, push, current-head review and squash merge. A preparatory design or partial capability does not complete its product stage. No Task releases, allocates a Product Build or cleans worktrees. An implementation Task may be drafted by a delegated coding agent; the shipping agent rebuilds and reruns every listed test itself before committing.

Delivery order: S1 → S2 deliver switching while playing at 1 BAR; S4 adds 1 BEAT and SEQ END; S6 → S7 deliver count-in; S3 adds switching while recording; S5 adds OFF.

## Facts this plan relies on

Checked on `0ce865fe`. Paths: `RE` = `packages/audio-runtime/src/realtime_engine.cpp`, `PTC` = `packages/application-facade/src/pattern_transport_controller.cpp`, `CR` = `packages/web-runtime-platform/src/control_runtime.cpp`, `APP` = `packages/application-facade/src/application.cpp`.

- **The engine can already switch at a chosen frame.**
  - `publish_pattern_view` without a frame activates at the next Bar, `origin + n × bar_frames` (RE:1313-1332). An explicit future `activation_frame` is accepted without Bar alignment (RE:1304-1312).
  - A pending unclaimed publication is replaced only with its exact `PatternReplacementAuthority`; a claimed one defers the next publication to the following Bar (RE:1198-1229). This is the P10-D22 behaviour the decision reuses.
  - A transport command names the pending switch, and Stop voids it as `canceled_at_cutoff` (RE:953-1089).
- **Nothing public switches the global transport while it plays.**
  - `snapshot.reload` to another Pattern is refused while playing (CR:4729-4737).
  - `sequence.record.switch-request` needs a legacy Sequence session, which cannot coexist with the global transport (CR:4993-4998, 5423-5425).
  - `performance.record.launch-request` needs an open Performance recording and targets the Performance clock's Bar, which is anchored at Performance begin, not at the transport origin (APP:7716-7722, 7774-7775).
- **Switching while recording settles only at close.** `retain_switch` and the drain/reconcile steps run when Record-off or Stop closes the Journal (PTC:261-311), not at the switch boundary. The admission codec allows one unsettled switch per recording (`packages/project-io/src/sequence_admission_codec.cpp:525-540`). The production port forgets an applied switch (CR:1328-1360), and Record-off republishes the Host's stored `pattern_id` (CR:2217-2218). No public path reaches these today.
- **OFF has no engine support.** `publish_pattern_view_preserving_phase` refuses a different Pattern, BPM or loop length (RE:1240-1247).
- **There is no scheduled start.** Play and Record start at the next non-empty callback (RE:1090-1093, 2091); `PatternTransportCommand` has no frame. The Facade opens and prepares the Journal inside `request()` (PTC:115-175). The engine already skips events before the origin (RE:604).
- **Creator gates.**
  - `←` `→`: `patternStepOpen` requires `!playing` (`apps/creator-web/src/app.tsx:2558`).
  - GROOVE picker: `disabled || playing` (`sequence_touch_workspace.tsx:158`).
  - `sequence_state.ts:49-52` applies `selected` only when stopped.
  - Launch: `disabled={!performing}` (`perform_surface.tsx:207`); `launchPattern` returns unless a Performance recording is active (`perform_state.ts:956-972`).
- **Metronome.** Creator-only, scheduled from `origin_frame` (`app.tsx:1963-2038`, `runtime/metronome_scheduler.ts`). Its preference lives in IndexedDB `lmdj.creator.host` / `settings` / `metronome.v1` (`state/metronome_preference.ts`).

## S1 — switch the playing global transport at the next Bar (Web Host)

**Behaviour.**

- New Host operation `pattern.transport.switch {pattern_id, request_id}`.
  - **Playing, not recording, no command in flight:** prepares the Pattern view and publishes it at the engine's next Bar. The response returns `{pattern_id, activation_frame}`.
  - **A switch already pending:** if unclaimed, the new request replaces it with the remembered authority; if claimed, the engine defers the new one to the following Bar. A request for the Pattern already playing cancels the pending one.
  - **Applied:** the Host's `pattern_id` and the engagement's Pattern binding follow the engine's current Pattern, so Record-off, Play and inspect name the new Pattern.
  - **Stop before the boundary:** the switch is cancelled at cutoff and the current Pattern is unchanged.
  - **Refused:** stopped (selection stays on `snapshot.reload`), recording (`pattern_transport_recording`, until S3), busy (`pattern_transport_busy`), unknown Pattern.
- `pattern.transport.inspect` adds `current_pattern_id` and `pending_switch {pattern_id, activation_frame} | null`.
- Runtime Session gains `requestTransportPatternSwitch`, typed in `runtime_types.d.ts`.

**Declared files.** `packages/web-runtime-platform/src/control_runtime.cpp`, `web/protocol.mjs`, `web/runtime_session.mjs`, `web/runtime_types.d.ts`, `test/control_runtime_test.cpp`, `test/runtime_session.test.mjs`, `apps/docs-site/docs/platform/web-runtime.mdx`.

**Lowest-tier tests** (`control_runtime_test.cpp`), one fact each:

1. a playing switch applies at the reported `activation_frame`, and inspect names the new Pattern afterwards;
2. a second unclaimed request replaces the first;
3. a request after the claim defers to the following Bar;
4. Stop before the boundary leaves the old Pattern current;
5. Record after an applied switch records into the new Pattern;
6. the request is refused while recording and while stopped.

The JS test covers the payload shape and the inspect fields.

**Gate defect caught.** A switch that plays the new Pattern while the Host still names the old one.

## S2 — enable switching while playing in Creator

**Behaviour.**

- `←` `→` and the GROOVE picker are available while playing, not while recording (until S3). While stopped they keep using `reloadSnapshot`.
- The GROOVE header and the upper screen show the queued target until inspect reports it applied. The upper screen keeps naming the playing Pattern.
- Perform Launch slots work while the transport plays:
  - with no Performance recording, a slot calls `requestTransportPatternSwitch` for the slot's Pattern; an empty slot does nothing;
  - with a Performance recording, the existing `performance.record.launch-request` path is unchanged;
  - while stopped, a slot selects its Pattern through `reloadSnapshot`.
- The QUEUED → PLAYING slot states read the transport's `pending_switch` and current Pattern when no Performance session exists.

**Declared files.** `apps/creator-web/src/app.tsx`, `src/state/sequence_state.ts`, `src/state/perform_state.ts`, `src/components/sequence_touch_workspace.tsx`, `src/components/touch_kit.tsx`, `src/components/perform_surface.tsx`, `src/components/pattern_launch_strip.tsx`, `src/components/sequence_overview.tsx`, `src/components/perform_overview.tsx`, `src/runtime/runtime_types.ts`, their tests under `apps/creator-web/test/`, `tests/platform/web/creator/creator_web_sequence.spec.mjs`, `tests/platform/web/creator/creator_web_perform.spec.mjs`, `apps/docs-site/docs/hosts/creator-web.mdx`, `apps/docs-site/docs/hosts/creator-interactions.mdx`.

**Tests to rewrite deliberately**, not delete: `sequence_surface.test.tsx` "the Pattern picker is disabled while the transport plays"; `creator_web_sequence.spec.mjs` lines 484-498 and 994, which assert the stopped-only rule.

**New tests.**

- Component: the arrows and the picker are enabled while playing and disabled while recording; a queued target shows in the header; a Launch slot without a Performance session calls the transport switch.
- Browser journey: Play, press `→`, observe QUEUED, then the new Pattern at the boundary with the old one audible until then; Stop before the boundary keeps the old Pattern.

**Gate defect caught.** A switch control that is enabled but stops the music, or a queued state that never clears.

**Integration repair: stopped selection.** The S2 browser journeys also
reproduce A → B → A while audio is running but the Pattern transport is
stopped. A stopped `snapshot.reload` must use the engine's existing immediate
publication path; scheduling B for a Bar can leave B pending when the return
to the still-current A skips publication, so the next Play starts B.
This repair additionally declares
`packages/web-runtime-platform/src/control_runtime.cpp`,
`packages/web-runtime-platform/test/control_runtime_test.cpp`, and
`apps/docs-site/docs/platform/web-runtime.mdx`. Its reduced Host regression
asserts each selected Pattern is current after the next callback, no pending
publication remains, complete Project Truth is unchanged, and the next Play
starts A. Legacy playback and playing-state Bar switches keep their existing
publication paths. Reclassify the complete S2 diff and run every selected lane;
the original Creator/Portal-only scope no longer applies.

## S3 — switch while recording (Core)

S3 starts with a short design addendum to the [Sequence recording semantics](../design/2026-08-22-sequence-recording-semantics-design.md). It must cover:

- settling the old segment at the applied switch boundary rather than at close (SR-D23);
- several switches within one recording;
- keeping the applied switch in the production port;
- naming the new Pattern on Record-off.

The addendum names its files and tests before code starts. Expected owners: `pattern_transport_controller.cpp`, `project-io` `sequence_admission_codec.cpp`, `control_runtime.cpp`, and their Facade, Project I/O and Host tests. Creator then lifts its recording gate on the arrows, picker and Launch.

**Gate defect caught.** Events after the boundary landing in the old Pattern, or a second switch parking the engagement in `error`.

## S4 — SEQ SNAP 1 BEAT and SEQ END

**Behaviour.**

- `pattern.transport.switch` takes `snap: "beat" | "bar" | "pattern_end"`, defaulting to `"bar"`. The Host requests the selected boundary from the engine's reservation-bound switch publication. The engine computes the activation frame from the exact current transport origin and prepared Pattern geometry, so both initial and audio-claimed successor boundaries use the actual engine timeline.
- Creator adds a SEQ SNAP segment (1 BEAT, 1 BAR, SEQ END) in SETUP next to QUANTIZE. The preference is stored in `lmdj.creator.host` / `settings` / `seq-snap.v1`, defaults to 1 BAR, and is read at boot like `metronome.v1`. It does not enter Project Truth.

**Refreshed premises.** At `deb95de722b845d708371e90bcac138ae5e25e01`, the protocol and SDK accept only Pattern/request identity, Creator SETUP has no SEQ SNAP preference, and both native claimed-successor calculation and Host deferred retries use Bar-only arithmetic. An explicit future frame alone cannot implement the other choices: native claimed timing takes precedence over it. S1/S2 and their Stop/settling/observation follow-ups are already delivered and must be retained. Recording permission remains S3; the separate Performance-origin Task #1974 is not duplicated.

**Declared files.** S1's Host/SDK protocol, session, types, dispatch and tests; `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`, `packages/audio-runtime/src/realtime_engine.cpp`, `tests/core/audio/realtime_engine_test.cpp`; `apps/creator-web/src/state/seq_snap_preference.ts` (new), `app.tsx`, `runtime/pattern_transport_actions.ts`, `sequence_touch_workspace.tsx`, `styles.css` (only the SEQ SNAP row's label/segment layout), their tests and the affected packaged Sequence/Perform journeys; this plan, `apps/docs-site/diagrams/audio-runtime.architecture.json` with official generated HTML/SVG, and the current portal pages `/core/modules/audio-runtime/`, `/platform/web-runtime/`, `/hosts/creator-web/`, `/hosts/creator-interactions/`. The native extension parameterizes the existing control-side publication reservation and retains the existing audio apply path. The original public switch signature remains available; any actual ABI change must be declared before shipping.

**Boundary rules.** 1 BEAT uses the prepared Pattern's rational tick boundaries within its rounded loop geometry; 1 BAR retains the existing Bar geometry while #1973 is independently tracked; SEQ END uses the playing Pattern's complete loop. An audio-owned predecessor keeps its own apply point and zero-origin restart. A later request uses the selected boundary on that predecessor's new timeline. Replacement, cancellation and Stop preserve the exact publication authorities. The device setting never enters Project Truth.

**Lowest-tier tests.** Native and Host: each snap lands on its exact frame, including SEQ END on a 2-bar Pattern, noninteger-BPM beat geometry and an audio-claimed successor. Test expectations use independent absolute frame values, so producer/consumer agreement cannot hide a shared wrong boundary. Retain replacement, current-Pattern cancellation, Stop, legacy omitted-snap and reservation-race coverage. Creator: the preference round-trips, defaults safely, preserves an explicit user choice against late boot hydration, and both Sequence and non-recording Perform requests carry the selected snap. Packaged journeys retain their far-side current/queue and reopen/Truth assertions.

**Independent-review verification follow-up.** The frozen S4 delta's review found no demonstrated reachable defect, but identified four missing decisive witnesses in the already-declared native and Host test files. Before freezing S4, add focused tests for: an admitted Beat/SEQ END calculation invalidated by a long callback and recomputed beyond the completed frontier; selected-boundary overflow refusal without losing an existing exact authority; Host cancellation/replacement across a forced publication handoff, including cancelling both a claimed predecessor and queued successor; and the production receipt-bound Record opening after a switch cancellation, with no admission before its actual cutoff receipt and the take retained on the actual current Pattern. Use existing deterministic hooks where possible; any extra test seam must be declared before editing. These tests cover S4 authority and production-port changes, and do not lift S3 recording-switch permission.

The Host witness reuses its existing one-shot hooks in `control_runtime.cpp`, guarded by `LMDJ_WEB_RUNTIME_TESTING`: after cancelling the latest switch and before cancelling predecessors; after the switch request's strong observation and before predecessor withdrawal; and immediately before the native transport publication after retired-view reclamation. No new public hook API, build target, production callback, or concurrency protocol is introduced.

**Shipping verification refresh.** Main `82c010d0391b956f871d34ecb40720f9a7e0a8d7`
([#2012](https://github.com/endaye/lmdj/pull/2012)) changes only verification
governance since S4's `deb95de7` base; the product premises above remain
outstanding at that main revision. Its Task verification policy replaces the
blanket complete batch-only receipt obligation. Retain the native/Host boundary
and authority tests, the owning stress suites, SDK request/response tests,
Creator preference/component tests, and every declared packaged journey leg.
Rebuild and run those affected tests on the final Task source, and record actual
commands, risks covered, results and complete-verification gaps in the PR.
Historical full results remain bound to their original inputs.

The original complete Creator run reproduced an inherited test defect:
`creator_web_perform.spec.mjs` expects every slider to reset to 500, including
MASTER whose range is 0–100. The integration repair in that already-declared
file sets a nondefault MASTER value before recording, preserves the full
record/replay/Stop/neutral journey, checks Filter/Delay/Reverb individually at
500, and checks that MASTER retains its device value. Keep the original
timeouts and all HOLD/Pattern assertions. Run the focused real packaged
journey before the amendment and the complete Creator proof on the committed
head. This changes no product behavior or additional version debt.

The same amendment corrects the manual's stale fixed-Bar roadmap statement
and additionally declares
`.agents/pitfalls/shared-temporary-staging-ownership.md`. The Linux fixture
diagnosis established an unwritable root-owned shared temporary staging path;
the original unchanged binary passed under a fresh worker-owned temporary
parent. Record that process finding, retain the initial failures, and run the
existing ledger and staged-ownership checks. No new gate, shared-directory
mutation, coverage-floor change or timeout adjustment belongs to this repair.

**Diagram presentation follow-up.** On committed S4 head `680a86f5`, the
independent review's A1 advisory was reduced with the actual generated HTML:
the expanded Pattern Transport / Phase card needs 174 px inside its existing
70 px hidden-overflow text box. This documentation-only Task declares this
plan, `apps/docs-site/diagrams/audio-runtime.architecture.json`, and its official
`static/diagrams/audio-runtime.html` / `.svg` outputs before editing. Condense
that card's summary; the module page retains the complete phase, ownership and
predecessor/successor rules. Do not change the shared renderer or other cards.
Lowest-tier verification is the actual regenerated card's rendered text fitting
its existing box and `scripts/docs-site.sh check`. Version impact: none;
Documentation impact: required on `/core/modules/audio-runtime/`. No product,
test, timeout or journey input changes. The completed original eight-group
Creator proof remains bound to `680a86f5`; it is not a full-proof receipt for the
documentation follow-up's new head. Refresh independent current-head review
before shipping the follow-up.

## S5 — SEQ SNAP OFF

OFF needs the engine to start a different Pattern at the current phase. S5 adds that publish mode to `audio-runtime` with its engine tests, exposes `snap: "off"` in the Host, and adds the option in Creator. It is last because it changes the cross-Pattern publication phase; S6 separately adds the native scheduled-start path.

## S6 — scheduled transport start for count-in (Core)

The [scheduled Record design addendum](../design/2026-10-11-scheduled-pattern-record-count-in.md)
selects the complete native, Facade, Host and SDK path before implementation.
Its preparation Task declares only that addendum and this plan. Lowest-tier
verification checks relative links, source/test ownership, decision traceability
and the declared diff; the existing `ci_change_scope_test.py` covers admission
of the new documentation path, and PR body/declaration checks cover shipping
metadata. Version impact: none; Documentation impact: none, because the Task
changes no source or current Portal behavior. No new gate or product proof is
introduced by this preparation.

- A separate tagged native scheduled-start cell pins the prepared Pattern and
  rounded Bar geometry. The first eligible native frame `C` starts four/eight
  forced cues; `S = C + bars * bar_frames` starts Pattern playback exactly.
  Existing command/receipt DTOs and ordinary behavior stay compatible.
  Before Armed, audio makes an independent scalar/cue copy and acquires a
  separate material borrow. Cancel/ack/rearm cannot reuse that copy or reclaim
  borrowed material; tagged CAS is not protection for a later payload read.
- Journal begin/preparation/writes occur only after acquiring the actual
  Applied receipt at `S`, through the existing dedicated I/O executor. A
  winning pre-start cancel leaves the transport stopped and writes nothing.
  A lost cancel retains the actual start and later cutoff receipts. The hard
  no-Journal rule is retained; an implementation unable to meet it must raise
  the owner erratum rather than choose request-time opening.
- Bounded original-frame ingress and separately reserved native FIFO and
  metadata release credits keep live Pads,
  Stop and inspect serviceable while I/O is held. Short Host tickets release
  both SDK dispatch tails; public scheduled-record trigger completion requires
  a total sequence-bound native operation completion and durable admission,
  including muted presses, toggle-stop, release and invalidation. Original
  opening and operation budgets remain. The opt-in input profile is negotiated
  at quiescent activation before live input, with acceptance order preserved.
  Press completion/ticket consumption does not retire a held press's future
  native or recording release reservation. Each settles at its own real
  release/owner boundary; saturated silent-held-input tests retain the complete
  matching-release duration through Record-off/Stop, reconciliation and reopen.
- Native cues use a second monitoring-only worklet output connected by Runtime
  Session downstream of the product master tap. S6 includes that consumer and
  real packaged OPFS/raw-PCM witnesses; telemetry or a native producer alone
  is incomplete. S7 owns device preference/UI and the JS metronome handoff.
- Separate strict count-in capability/request/inspect/cancel operations add a
  `count_in` view with `start_frame: null` while arming, then the real scheduled
  frame and lineage. Ordinary legacy responses/event streams remain unchanged;
  unsupported probing leaves ordinary operations usable. Serial/epoch identity
  uses exact decimal strings across JS. No Host timer invents an origin.

**Refreshed premises.** The original implementation base is actual main
`96802c0f8764d04cbf3d3c913e82292a01284ac9`, including S4's actual merge
`e220c98ca1b0f4a3c08646bfeb328ffa186a263d`, F1/#2014's merge
`a61ab819686ad896a3192e4a4bce1541ae55676d`, and the #2019 design preparation.
S1/S2/S4 are delivered; scheduled
Record, production-controller I/O ownership and native cue/SDK wiring remain
outstanding. Existing executor OPFS and ordinary recording journeys are
retained. #1958/#1959 are decision-only closures. Preserve F1's typed Filter
accepted/applied epoch channel, quiescent reset and single stage alongside S4.
The addendum
names the owning files, exact lifetime/receipt protocol and every lowest-tier
test and far-side acceptance leg before code.

The 2026-10-11 follow-up refreshed remote main to
`67d66bf20d7701d339ab2554ac2090bae78ec483`. #2008 delivered the independent
Performance Launch origin fix for #1974 after this Task's explicit `96802c0f`
base. Its four changed files do not overlap this S6 draft. After confirming all
four paths were pristine and the index empty, the Task worktree fast-forwarded
to `67d66bf2`; the uncommitted S6 draft is retained. Historical draft proofs
remain bound to their original `96802c0f` head. Recheck the mixed
Pattern/Performance acceptance on the final S6 candidate before shipping.

**2026-10-11 opening and retained-I/O follow-up.** The owner confirmed that the
existing 5000 ms deadline bounds first recording admission only. A retry keeps
its original start; 4999 ms may open and 5000 ms cannot first open. Only a real
successful durable fence completion before that boundary proves that the take
already opened. Readable bytes after an unknown write do not prove durability
or its completion time. An exact proven opening may be replayed after the
boundary, and subsequent Press/Release remain recordable until the user's
actual Record-off/Stop cutoff. Preserve the original capacities, byte limits,
Pad deadlines, storage/owner-loss rules and every close/reopen/Truth leg.

The production ordinary capability port also binds every Record opening to one
coherent observation and its actual Native receipt: a real Apply during I/O
preflight cannot pair an old preparation with a new Pattern/generation fence.
The focused regression forces that transition before the first submit and
checks the refreshed receipt, durable Journal identity, ACK ordering, real
Release, Stop and complete reopened Truth. Legacy ports retain their old path.

The original owning run retained four actual failures: the newly added test's
scheduled-publication premise, the unchanged 30-second normal and 3-second
per-input pressure budgets, and an old fixed-callback recording fixture's
unsettled recording result. Actual worker completion is a fixture premise to
verify; the original log alone does not establish its cause. These failures
remain private evidence; they are not a passing Task. Keep the fixture's 64
callbacks and verify actual worker completion, while repairing the parser's
observed repeated immutable-prefix work and keeping
1024/512 capacities and the full 64-repeat pressure journey. The parser repair
additionally declares `packages/project-io/src/sequence_journal.cpp`,
`tests/core/project_io/sequence_journal_test.cpp`, and the current portal route
`/core/modules/project-io/`. It reuses only a bounded private fully validated
prefix after comparing its exact bytes with a fresh read; changed/truncated
bytes, new records, current Project identity, leases and real durable sync keep
their original validation. Its tests must warm the parser and then change the
prefix with a valid checksum, add a conflicting/torn suffix, truncate the file,
and change Project metadata. It cannot cache a successful write or ACK.

Remote main was refreshed to `9ffd1f71121a04dbfdb393822a8af72a3ae11ae9`.
#2010 retains the original Perform replay/Launch journeys with their independent
MASTER and transient sampling repairs; do not repeat or drop them. #2021 at
`9555be7b85db214acb73ed4afac564064d7f8e9e` delivers the separate Performance
live-control profile/ledger in the shared Project I/O source. It does not
deliver the S6 Pattern scheduled-start, admission or cue work. Preserve that
new shared source and its tests during integration, then rebuild and validate
the final candidate. Historical draft results remain bound to their recorded
67d66bf2 source hashes, not this refreshed main.

The owned draft was then archived by complete file bytes and SHA256 before a
fast-forward to actual main `6fa983261e2740f5773598cda1491dfb1eb21468`.
#2026 changes historical CI evidence names only and adds no S6 product work.
The retained source was applied without dropping its private stash. The three
overlapping paths (`sequence_journal.cpp`, its module page and
`creator-web.sh`) equal independently reconstructed three-way merges; all
other 78 owned file bytes remained unchanged. This is source preservation,
not a verification result. Rebuild the owning Pattern and Performance Journal
tests against this actual integration base.

The frozen first completion-publication draft has two unresolved source-level
findings: a worker can capture an in-time durable completion and be preempted
before publishing it while Control accepts an automatic real Stop; a delivered
successful completion can also consume its work cell before clearing a prior
timer-only failure. The existing delayed-delivery witness pauses after
publication and cannot prove either earlier interleaving. This draft is not
accepted and its original evidence remains retained.

The corrective private protocol uses the owner's completion clock as the
logical opening decision, after the actual durable API succeeds. Capture that
clock, validate the original deadline and publish the exact opening decision
in one short shared critical section; allocate/copy beforehand and perform no
storage work in that section. Control only tries to acquire it, never waits
for I/O, and cannot issue an automatic Stop while that decision is protected.
The original held, not-yet-durable begin still expires under the unchanged
5000 ms budget and produces its real Stop. Clear only a provisional timer
failure while consuming an exact successful completion, before losing its
work identity; never revoke an accepted user or automatic e2. This makes no
claim about the physical filesystem sync instant. Deterministically pause
inside the decision and at successful consumption, retain the original expiry
journey, and prove the complete Press/Release/Stop/reopen path on a rebuilt
artifact before accepting the correction. No public ABI or Contract change is
introduced by this private repair.

This corrective witness additionally declares
`packages/application-facade/src/pattern_opening_test_seam.hpp` and the already
owned `packages/application-facade/CMakeLists.txt`. The existing Facade test
names and budgets stay unchanged. Build an explicit testable Facade variant
from the same production sources for the owning count-in regression; ordinary
Core, Creator and Host targets keep the production library with no seam.
Use a typed atomic gate after an actual positive completion clock, inside the
decision guard before publication. It must not supply fabricated durability or
replace the real worker, Native receipts, correlated input or reopened Truth.
Prefer the real steady clock for this gate; the existing direct Admission
fake-clock cases separately prove the 4999/5000 boundary. A successful
completion-consumption witness must retain its exact originating work identity
and state which interleaving was actually reached. No static-library symbol
override, new product capability, widened deadline or shortened journey is
part of the test variant.

**2026-10-11 rebuilt owner-loss and repeated-cutoff correction.** The fresh
actual-main native owning run returned 8 PASS / 3 FAIL. CountIn component and
stress kept their original post-open owner-loss assertion red; the temporary
diagnostic confirmed `scheduled_record_owner_invalidated` when shutdown first
requested a cutoff after a completed opening. A newly accepted shutdown intent
for that opened owner retains the existing recording-owner classification;
explicit scheduled cancellation keeps its original scheduled-owner failure,
including when a later shutdown observes it. Mark this private cause before
the actual request, since it can synchronously inspect Native refusal, and
withdraw the mark unless the request is accepted. Preserve the actual refused
e2, missing F, retained prefix and recovery. The first rebuilt correction's
opening-only classification failed the original explicit-cancel oracle before
reaching the new repeated-recording test; retain that negative and its strict
assertion. Pending opening failure keeps the scheduled-owner classification.
The original Host reload journey also remained red. Its real failing second
Record-off, command 817, submitted a cutoff carrying the previous recording's
epoch 2 / Pattern A / generation 1 against the actual current preparation
epoch 4 / Pattern B / generation 5. This is stale cutoff reuse, separate from
the already verified ordinary opening receipt repair. On accepting each new
ordinary recording cutoff, clear the previous operation's cutoff observer and
wait for that pending request's real receipt before authoring its fence.
The strict rebuilt two-recording regression additionally fails on the actual
second Pattern B Press, command 816: the previous active cutoff also filters
new input before Record-off. Retire active `close_cutoff`/`cutoff_done` at the
next genuine ordinary Record receipt, alongside its new start frame and epoch.
Keep old F during closed/preparing input settlement and preserve the separate
closed-owner request/F pair's existing physical-recovery lifecycle; clearing
F immediately on close success would lose that late-input boundary.
`tests/core/facade/pattern_transport_controller_test.cpp` additionally owns a
deterministic two-recording regression that holds the real callback for the
second cutoff, asserts no stale cutoff I/O, then releases the callback and
finishes both original Press/Release/Record-off/reopened Truth legs. Preserve
all original tests and budgets; these private corrections have no new ABI or
Contract/version identity. Documentation impact remains required for the
already declared Facade route. Temporary diagnostic sources were restored to
their exact captured working bytes with fresh mtimes; all diagnostic failures
remain retained and the corrected artifact must be rebuilt.


**Current integration and remaining proof.** The owned draft was preserved
before the next safe fast-forward to actual main
`6423a596360f64a0def1e33c37bd1551b0de838e`. #2027's six Sound Set golden paths
were pristine; all 81 other owned file bytes remained identical, and the Audio
Runtime page matched the independently merged source. Preserve all earlier
negative logs and draft identities. This base update is not a runtime result.

The exceptional direct-Stop regression now establishes genuinely unsubmitted
ordinary work using a coherent real pending Pattern publication; absence of a
receipt alone did not establish that premise. Its actual ordinary submit must
refuse before queue acceptance and leave no cutoff F. Already submitted work
keeps the unchanged Native quiescent-cutoff behavior. The owner-loss history
oracle checks all original registry fields and the actual active Sequence
session's public availability. The original Host recording journey retains all
16 render legs and now waits for the actual I/O owner to become idle before
checking each leg's original far-side recording predicate; idle itself is not
a durability receipt. A known final opening refusal clears its private pending
flag before consuming the exact work cell; unknown and retryable effects keep
that cell and flag. The deadline regression checks the real terminal error,
missing pending I/O, actual start/cancel receipts, retained Journal and complete
unchanged Truth. These corrections remain in their already declared files.

The Sequence-only parser returns its replay-validated outstanding canonical
candidate byte count to the actual writer rather than re-encoding the entire
candidate vector before each append. A transferred prefix subtracts only its
consumed candidates; historical exact retry is neutral and a collision still
refuses. The unchanged private 1 MiB parse-prefix bound is separate from the
public candidate byte limit. Added same-writer regressions cover a one-byte
overflow after warming, exact-bound and over-bound cold reads, transfer/retry/
collision, and fresh invalid manifest/checkpoint bytes followed by restoration
and a new real append. Their original Journal component passed; deliberately
omitting the returned count failed the new strict assertion on a freshly
rebuilt artifact, and restoring/rebuilding passed again. The original eight
Project I/O tests and 20-case count-in component also passed on this draft.
The original 64-repeat count-in stress run still timed out at its unchanged
300-second budget, so S6 remains incomplete. Further parsing reduction must
retain the fresh under-lease reads, full byte comparison, current Project
identity, actual durable sync, all original capacities/deadlines and every
recording/reopen leg; source reviews or bounded passing components do not
replace that full acceptance.

**Private input-expiry scan and completed component proof.** The adopted
controller keeps a private conservative earliest-start hint for unfinished,
unexpired inputs. Each drive still reads the existing steady clock; a scan is
needed only when that hint reaches the unchanged one-second input deadline.
A due scan retains all 2048 cells and rebuilds the minimum remaining start;
removal or completion can leave an earlier hint and only cause an extra scan.
A fresh reservation incorporates its actual original start, while exact replay
does not reset it. The added real-I/O regression holds durable append across
mixed input ages, checks sticky expiry **after** actual durable completion and
before either consumer retires the ticket, then exercises a timely fresh input,
a fresh expired input, real Stop and complete reopened Truth. It adds one
3.003-second wait journey outside the unchanged 16-case, 64-repeat loop. Fresh
Project/Journal reads, writer leases, durable sync, real correlated Release,
Stop/reopen and the five-second **opening-only** budget remain unchanged, as do
the one-second input deadline, three-second waits, capacities and original
30/300-second component/stress limits.

After independent source review and adoption, the actual rebuild exited zero
and the complete 21-case component passed in 26.49 seconds within its original
30-second budget. That revision retained every prior 20/1028 journey and
extended the totals to 21/1029.
Separate rebuilt opening-cleanup and busy-guard mutation checks completed
build/negative-test/restore-build/restore-test exits 0/8/0/0 on the prior
Controller/test blobs (`0a717`/`500c`), failing their exact named assertions and
restoring the complete 20-case PASS. The first helper's parser-only exit 1 is
retained alongside Root's independent raw-artifact proof; these old receipts
do not certify the new scanner. The new full 64-repeat run also ended in an
actual 300.02-second timeout, with CTest and its wrapper exiting 8. Its planned
1029-case total is not a completed-case count. Both full-run failures remain. S6 is incomplete: this component
result and private source optimization do not establish full stress, complete
Task or product acceptance, and no S6 Task commit, PR or merge has been made.

**Current source-gate follow-up.** A subsequent safe fast-forward to actual
main `08330f29c2889cfa54f5cee90e8d42da50593fc7` changed only the pristine
Creator package-test file from #2028; all 82 owned draft files stayed byte
identical. The SDK's three Node 26 test files passed 273 tests, and the explicit
observer-server routing unit test passed. These mock/routing results do not
prove Browser Main, production OPFS, PCM or hearing. The original source
checks returned one pass and two failures. The taxonomy failure matched 203
missing configured native registrations; an actual read-only CTest query
confirmed their absent command fields. The complete dev build then succeeded
and the unchanged taxonomy passed. Preserve the original failed receipt.

The additionally declared Host source check was repaired in
`apps/web-runtime-host/test/web_host_source_boundary_test.py`, and its original
`host.web_source_boundary` check passed on the restored draft. Preserve the
earlier failure. The repair preserves pending,
exact abandoned-ID and unknown-response separation, rejection of unknown
responses, disjoint notifications, sealed polling, and actual owner-release
and pending-request fences before worker retirement. Its lowest-tier check is
`host.web_source_boundary`, including strict applied-and-rejected source
mutations for response identity and unknown-response sealing. The original
check is an association boundary; a larger static JavaScript parser or whole
owner-body equality does not prove global owner-release provenance. Sealed
polling and real owner/RPC fences remain product requirements, with their
original Native, Host and browser owner journeys retained. Generated pre-JS
and the existing complete browser failure journey remain separate owning
checks; each assertion names the defect its layer actually observes. Do not change product code, labels, budgets
or test selection to satisfy this check. This private test repair adds no
version debt or Product Build. Documentation impact remains required for the
already declared Web Runtime route. S6 remains incomplete and uncommitted.

**Advisory input lookup and real-owner regression.** The adopted lookup stores
only a private last-slot index. Every hit revalidates bounds, occupancy and the
complete runtime-generation/CommandId/ticket identity; misses retain the full
original scan. The Host still serializes all calls, including const inspection,
on its Control lane. The real-owner regression retains A/B, consumes A, reuses
its ordinary slot for real C, and rejects old A and each single-field foreign
ticket through inspect, bind and consume without changing the legitimate
Native, durable or consumer state. It then delivers all three real correlated
Releases, obtains actual Stop F and acknowledgment, and checks complete
independently expected reopened Truth plus strict Journal not-found. It adds
one case outside the original unchanged 16-case, 64-repeat loop.

Both production and opening-testable libraries were freshly rebuilt. The
complete 22-case component passed in 26.68 seconds, within the original
30-second limit. The subsequent original full 64-repeat run still timed out
at 300.02 seconds, with CTest and its wrapper exiting 8; the planned 1030 cases
were not reported complete. A bounded two-second sample of that same owned
binary is diagnostic only and its overhead is recorded. These source changes
and component evidence do not establish a performance improvement or complete
stress acceptance. All previous failures, original budgets, capacities,
Release/Stop/reopen journeys and remaining Web/Creator/sanitizer checks stay
required. S6 is still incomplete, uncommitted and unmerged.

**Bounded timing diagnosis and Native layout scope.** A temporary opt-in main
wrapper timed the unchanged original 16-by-64 stress body. The actual full run
still timed out at 300.03 seconds with CTest exit 8: 46 complete rounds and the
first five functions of round 47 returned; its metadata-pressure function
began without returning. None of the six once-only cases was reached. The 46
returned metadata functions took 254.549462 seconds of 294.225559 seconds of
paired wall time. This is case-level diagnosis, not CPU or stress acceptance.
The original working source was restored with a fresh mtime, the actual target
was rebuilt successfully, and the resource window was released. Failures remain.

The existing source-bound sample contains repeated secure path traversal
during fresh Journal checks; it does not prove a unique cause or speedup.
Before implementation, additionally declare
`packages/project-io/include/lmdj/project_io/storage_platform.hpp`,
`packages/project-io/src/native/storage_platform.cpp`,
`packages/project-io/src/testing_hooks.hpp`, and
`tests/core/project_io/storage_platform_contract_test.cpp`. These four clean
files extend the owned map from 83 to 87. Changes also use the already declared
Sequence Journal, real Facade count-in fixture, plan, S6 design and
`/core/modules/project-io/` documentation.

The optional `ProjectJournalLayoutValidator` companion preserves the existing
storage-platform vtable. Only the Sequence branch of checked reads discovers
it: absent capability retains the complete original helper; supported failure
remains failure. The entry layout check at Sequence begin and all Performance
paths keep their original helper. An existing active-Sequence error-details
lookup still uses the Sequence checked-read path. Native repeats full secure managed-tree validation (including hardlinks
and special files), all eight typed directories, and real regular manifest
open/shared flock/locked identity recheck/nonnegative length. It securely
reopens the named root before success to reject replacement. Descriptors are
per-call, not cached authority or an atomic whole-tree view. The real Facade
fixture explicitly delegates genuine Native capability; OPFS imports are unchanged.

Lowest-tier verification is `project_io.storage_platform`, including actual
unsafe/missing/wrong-type layout and test-only root rename/substitution, plus
a real independent manifest descriptor proving shared-lock coexistence,
exclusive refusal during validation and exclusive access after return. This
witness catches a missing lock, wrong lock mode or incorrect lock lifetime.
Sequence capability-failure and unsupported-platform fallback witnesses remain.
The private post-layout and in-lock hooks are compiled only in the existing
testable variant.
Preserve all original Project I/O owners, changed-Project/complete-read faults,
warm/cold byte limits, unknown replay sync, actual leases, the complete 22-case
component and original 64-repeat/1030-case stress under 30/300 seconds. Keep all
ordinary inputs, reserved Release, Stop, reopened Truth and consumer/ACK legs.
This prospective source scope is unexecuted and does not clear FAIL.

**Latest integration base refresh.** Before the next Native phase, the actual
remote `main` was `a5bc444be23edf4d4d14378e3ff60c3c8bf037fc`, containing
#2001's Creator history navigation repair. The S6 branch fast-forwarded to that
commit: its four upstream paths did not overlap the 87 declared S6 files, and
all 87 draft file bytes and the empty staging state were preserved during the
refresh. Retain this Creator baseline in later complete acceptance. This source
integration does not clear the original full-stress failure or establish a
new Native, Portal or Creator pass. Earlier source-ready receipts on
`08330f29c2889cfa54f5cee90e8d42da50593fc7` are historical; the next resource
admission must bind a fresh source manifest on the current branch head.

### S6 current-head review follow-up: running failed-ticket consumption

The independent complete review of local candidate `75cf45c9` confirmed that
the known final opening-refusal ACK calls a quiescent-only Engine query while
the callback remains running. Ordinary Stop F and real Release completion do
not end a live Pad's release tail. Native42 and Portal results for the frozen
candidate remain historical passes; they do not dismiss this concurrency defect.
Fresh main `0664296156c0736d4f61282b910b3d5bd3d8be37` delivers only the independent
Replay neutral enqueue-order repair (#2066); its four paths do not overlap this
repair. Keep the original clean candidate and live OPFS installer unchanged.

This follow-up declares `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`,
`packages/audio-runtime/src/realtime_engine.cpp`, its existing `testing_hooks.hpp`,
`tests/core/audio/realtime_engine_test.cpp`,
`tests/core/audio/pattern_count_in_stress_test.cpp`,
`packages/web-runtime-platform/src/control_runtime.cpp`,
`packages/web-runtime-platform/test/control_runtime_test.cpp`, this plan, the
S6 design addendum, and `/core/modules/audio-runtime/` Portal source. Add a
serialized-control-safe exact generation/frame-epoch/serial settled query with
an audio-published last-use marker. It gates logical failed-ticket consumption
only, never reclamation, stopped-device authority or physical callback retirement.
Keep every original identity, S/F, I/O, cue/borrow and input-owner debt check.
Lowest-tier verification is the complete Audio Engine test, concurrent count-in
stress and original complete Host test, including callback-epilogue, long-tail,
foreign-identity and fresh-input invalidation assertions. Retain their budgets
and selection, and run the original full Portal check before shipping.
Version impact: no additional change beyond S6's already declared Audio Runtime
MAJOR. Documentation impact: required; affected page `/core/modules/audio-runtime/`.

## S7 — count-in in Creator

**Behaviour.**

- SETUP gains COUNT-IN Off / 1 / 2 next to METRONOME, stored as `lmdj.creator.host` / `settings` / `count-in.v1`, default Off.
- When ● starts from stopped with count-in on, Creator requests the scheduled start. The metronome clicks for the count-in bars regardless of its toggle, then follows the toggle.
- The upper screen shows COUNT-IN and the beats left. The Record lamp blinks during count-in and is steady once recording.
- ● or Play/Stop during count-in cancels.
- User-resolved policy (2026-10-13): lock BPM and Pattern changes during count-in while Pad Press/Release remains playable. Unlock after actual matching cancellation/Stop settlement; pending cancellation does not unlock competing authoring intent.
- User-resolved policy (2026-10-13): if COUNT-IN is 1/2 and the actual environment cannot provide scheduled count-in or cue output, retain the preference, refuse this Record request and show its actual reason. Complete the normal user activation path when applicable; do not silently start ordinary Record or rewrite the preference to Off.

**Declared files.** `app.tsx`, `src/state/count_in_preference.ts` (new), `src/runtime/metronome_scheduler.ts`, `sequence_touch_workspace.tsx`, `physical_controls.tsx`, `styles.css`, `components/transport_status.ts`, the overview components, their tests, `tests/platform/web/creator/creator_web_metronome.spec.mjs`, and the two Creator portal pages.

**Gate defect caught.** A count-in that records early hits, or a cancel that leaves the transport playing.

## Known gaps outside this plan

- **Bar maths.** The engine repeats one rounded Bar (`origin + n × bar_frames`). Sequence, Performance and the Creator metronome round each boundary separately. At BPMs where a Bar is not a whole number of frames, a switch boundary and a metronome downbeat can differ by a frame per Bar. [#1973](https://github.com/endaye/lmdj/issues/1973) tracks it.
- **Performance launch clock — delivered outside this plan.** [#1974](https://github.com/endaye/lmdj/issues/1974)'s transport-origin alignment was merged through #2008 at `67d66bf20d7701d339ab2554ac2090bae78ec483`. S6 retains that independent result; it does not repeat the implementation.

## Verification

Each Task runs its listed risk-covering tests and records the actual commands,
results and explicit gaps in its Pull Request. Persistence and recovery retain
their owning integration/restart tests; concurrent lifetime changes retain
stress tests; every declared acceptance journey keeps all its transitions and
far-side assertions. Resolve ownership with `scripts/local-ci.sh --list` on
the final committed range. For this Goal, the user's supplied AGENTS requires
every selected `batch_only` lane on the committed head, with its `pass key=`
recorded under `## Batch-only Lanes`, or an explicitly owner-accepted risk;
the exact-head batch-evidence check is required before merge. That user
requirement takes precedence over the general current-main Task policy above.
Explicit complete candidate/full evidence remains a separate obligation.
Unexecuted complete checks remain unverified, and historical failures remain
visible. S1, S3, S5 and S6 own Core and Web Runtime; S2 and S7 own Creator and
Portal. S4's native extension also owns Core and Web Runtime alongside Creator
and Portal: the recorded classifier selects full mode, 13 lanes and 10
batch-only lanes. This observation does not override the canonical selector.

**Native complete-text-read performance correction (owning Native checks passed).** The unchanged
whole22 component passed at 26.744 seconds while the previous whole64 stress
still failed at 300.03 seconds. A subsequent same-native-process stack sample
of the original component (26.220 seconds, sampler exit0) found substantial
Debug byte-vector element construction/destruction. The new optional
`ProjectStorageTextReader` keeps the old storage vtable and returns the same
fresh complete bytes as an owning string. Native shares the original fault,
replacement retry, safe path traversal, lock, pread and metadata revalidation
implementation between both buffer types. Sequence checked reads and their
current Project reads select this capability; absent platforms and Performance
retain the old vector path. A present capability failure propagates unchanged.
No cached descriptor, read receipt, new persisted schema, deadline or capacity
is introduced. Owning tests add complete arbitrary-byte/empty/replacement,
transient retry, real same-inode lock, FIFO/symlink, and each Journal/manifest/
checkpoint failure with actual subsequent append and legacy reread.

The rebuilt storage contract, Journal component, Journal stress and whole22
Facade component passed their unchanged 30-second limits. A rebuilt mutation
that swallowed a present text-reader error failed the new Journal refusal
assertion; exact restoration and fresh recompilation passed the original
Journal component. The 1024-input settle phase fell from 5.249831 to 2.372913
seconds with the same 6168 complete reads and 503175670 returned bytes.
The subsequent original full64 stress passed in 239.51 seconds (CTest exit0;
wrapper wall time 240.407 seconds) under the unchanged 300-second limit.
All 64 rounds of 16 cases and six tail cases completed in their original
order: 1030 paired BEGIN/END markers. Source, binary and index stayed unchanged
during the run, and the owned process group exited. Diagnostic instrumentation
remained enabled and charged to the same budget. Preserve every earlier
full-stress failure. This proves this Native draft's owning checks; Portal,
broader S6 platform/sanitizer validation and full current-head review remain
outstanding. S6 is still incomplete and uncommitted.

**Current-main integration and remaining review findings.** The S6 worktree
fast-forwarded from `a5bc444be23edf4d4d14378e3ff60c3c8bf037fc` to actual main
`c2de40b6471a40b830980d6ce88fdb600988437c`, preserving the complete 87-file
draft and a private preservation stash. The semantic union retains main's
live Pad Mute/Solo and Performance control admission changes. A new actual
Mute/Solo press-and-release journey first failed because live gating left a
successfully consumed silent input marked invalidated; assigning its real
`muted_no_voice` result fixed both gate scenarios. The original component
then passed all 23 cases. The subsequent 42-test Native/Facade/Host/Project
I/O selection ended with 41 PASS and one Host failure. Its unchanged
300-second Facade stress passed in 240.65 seconds, with all 1031 cases
completing in order. The remaining Host failure is the replay-to-Pattern
helper's two-second request timeout before its second audio quantum; it is
separate from the full-stress budget. The helper now observes the actual final
neutral Pad-clear acceptance on the serialized control thread before the first
quantum, covering the preceding legacy and independent Filter commands. It
preserves the original two-second request, two quanta and all three replay
journeys. A fresh build and one complete original Host check passed in 56.94
seconds, with the entire 87-file candidate unchanged during that run. Another
owner's compilation was observed on the same machine and recorded; this is
Host-specific evidence, not whole-Task or cross-platform acceptance.

Independent source review also found that readable candidate/transfer or
closure bytes could retire unknown I/O work without confirming sync. The
candidate reconciliation now replays the exact existing Journal record under
its real writer lease; persistent sync failure keeps the input unconsumable.
Only the explicit Native test variant selects the existing fault-enabled
Project I/O library. The real write-before-sync failure regression, including
same-ticket recovery, physical Release, Stop and complete reopened Truth,
passes in the full 24-case component. Rebuilding the original owner against
the same final test fails its durable-consumption assertion; restoring and
rebuilding the repair passes in 24.54 seconds. The later cutoff regression
first needed to distinguish the opening's remaining projection work from the
actual Stop command. With that observation corrected, the same test fails
against readable-only cutoff completion and passes that case after exact
durable replay. Owner-loss completion likewise now requires actual durable
replay; repeating an identical Journal state syncs the existing prefix instead
of appending it again. The Journal byte-growth regression fails before that
repair and its complete component passes afterward in 10.04 seconds. The
complete Facade component passes all 26 cases in 24.62 seconds, including
persistent sync failure, bounded bytes, physical hold separation and complete
owner-loss recovery into Truth. Three further direct-worker component cases
cover historical transfer receipts, an absent candidate with a real failed-sync
closure, and a readable overlay generation. Each creates actual Native input
and Journal state, fails the real sync during execute, reconciles the identical
request on the same owner, and retains unknown until sync succeeds. They retain
the original 26 journeys and continue through real Stop/close, complete reopened
Truth, absent active Journal, exact-once Native consumption and balanced leases.
The full 29-case component passes in 24.66 seconds. Three separately rebuilt
readable-only mutations each fail in their corresponding new unknown assertion;
restoring and recompiling the exact production source passes all 29 in 24.69
seconds. The complete test file is identical across these four contrast runs,
and all 87 changed/new source files, HEAD and index are frozen within each run.
The historical-transfer case proves worker idempotent replay, not Controller
resubmission through an occupied work cell. These targeted results do not
replace the combined owning, stress, Web or sanitizer acceptance on the final
candidate.

The SDK separately froze transient worker errors as physical input identity.
It now freezes only a completed result's final error, including final success,
while retaining immutable admission and Native completion checks. Both
in-deadline recovery and recovery after the original observer timeout consume
the exact original ticket once and preserve its real Release. The complete
related Node suites passed 279 tests with no failures or skips. A further SDK
repair permits only the original provisional opening expiry to become a known
deadline refusal, retaining immutable start/Stop receipts and final error.
Its complete related Node suites pass 303 tests; independent delta review has
no findings. The Host now preserves only the specific opening-deadline error
reason and true unresolved/retryable flags while keeping the generic sanitizer
unchanged. A known final refusal can be consumed once only after its original
S and real Stop F agree and all real I/O, physical holds, Native completions and
Host input consumers settle. The new real-storage journey first exposed the
missing wire reason. Subsequent test corrections distinguish callback-dependent
runtime frames and error-state history availability from immutable evidence;
actual history payloads confirm unchanged contents and the required busy state.
All intermediate failures remain recorded. The freshly rebuilt original full
Host test passes in 62.66 seconds, including held-owner and release-consumer
refusals, all five foreign identities, one successful acknowledgment, rejection
of a second acknowledgment, unchanged full Truth/history/Journal inventory,
and actual owner-loss recovery followed by a stable second reopen. The late
first-opening OPFS journey remains unverified: an opening first completed after
five seconds must remain refused, never be relabeled `openingComplete`.
The independent 87-file source review is
complete, but its findings, later deltas, rebuilt platform acceptance and final
committed-head shipping obligations remain open. A fresh read-only main check
at `f3707192e63acb3277cf83bbdde018074847a7cc` found only two intervening commits,
with no S6 implementation overlap; this Task remains based on `c2de40b6`.

**Precommit integration checkpoint.** The subsequent original 42-registration
Native selection passed all 42 with no failures. Its Facade stress completed
all 1037 cases in 232.81 seconds under the unchanged 300-second budget. A
separate freshly rebuilt mutation disabling only known-refusal consumption
failed at the exact caller acknowledgment; restoring the production source
and rebuilding passed the unchanged complete Host test in 60.75 seconds.
The original full Portal check passed in 41.86 seconds: 176 tests, all current
pages/diagrams, snapshot validation, typecheck/build and 50 routes/links.
These are the retained `c2de40b6`-based draft results, not proof of a later head.

A fresh main read then found #2068's direct Replay profile preflight and
#2070's Replay-to-Pattern fixture repair. Both are already delivered and must
not be reimplemented. The worktree fast-forwarded to
`db6776df18445a6c6d64315e840e88face3c062b`, preserving the complete S6 draft.
The combined Portal paragraph retains both the worker-owned overlay and the
new preflight facts. The test uses main's explicit audio-progress helper,
including all FX/Filter/Pad-gate far-side assertions, with S6's retained-RPC
adapter for asynchronous I/O. The duplicate receipt-clock helper is removed;
all original caller journeys and the two-second request budget remain.
Owning Native and Portal verification must be rerun on this semantic union.

Submission additionally declares `scripts/ci/scope_policy.json` for the six
new proof/decoder paths lacking ownership and `CMakePresets.json` for coverage's
existing busy-spinning stress exclusion rule. The staged ownership suite and
explicit coverage selector inspection are their lowest-tier checks; full
Native stress remains required. No new gate, version identity, Product Build,
release operation or acceptance waiver is introduced.

## Version Management

Version impact: none in planning/design preparation Pull Requests (documentation only). The implementation Tasks owe the following debt at the next coordinated version settlement:

- S1: `web-runtime-platform`;
- S4: `web-runtime-platform`, `creator-web`, and the additive native boundary API in `audio-runtime` (retain old public symbols/layout; reassess MAJOR debt if that cannot be met);
- S2, S7: `creator-web`;
- S3: `application-facade`, `project-io`, `web-runtime-platform`;
- S5: `audio-runtime`, `web-runtime-platform`;
- S6: `audio-runtime` MAJOR, because the selected inline schedule changes the
  concrete Engine ABI; `application-facade` and `web-runtime-platform` MINOR
  while companion APIs/Pimpl additions preserve old public layouts/vtables,
  exact legacy wire schemas and unnegotiated event streams.
  `project-io` additionally owes MINOR debt for the compatible optional Journal
  layout and complete-text-read companions, including the private parser/admission repair. The existing
  storage-platform vtable and persisted schemas remain unchanged; reassess debt
  if implementation breaks that boundary. No version is allocated here.

S2's stopped-selection integration repair also owes `web-runtime-platform`
PATCH debt. It uses an existing engine capability and changes no API, ABI,
Contract, Product Build or Assembly identity.

No Contract SemVer change is expected: SEQ SNAP and count-in are device preferences, and switching does not change the Pattern shape. S3 and S6 re-check this in their addenda. No Product Build or Assembly change in these Tasks.

## Documentation Impact

The original planning Pull Request: none. It added a plan under `docs/plans/`; no portal page described it as implemented. S1, S3, S5 and S6 update `/platform/web-runtime/` and the affected module pages. S2, S4 and S7 update `/hosts/creator-web/` and `/hosts/creator-interactions/`. S2's stopped-selection repair also updates `/platform/web-runtime/`. S4's native extension also updates `/platform/web-runtime/`, `/core/modules/audio-runtime/`, and the Audio Runtime source diagram with its official generated outputs.

## Pitfall Impact

None expected. Each Task searches open entries labelled with its `area:*` before shipping. S2 and S7 read `synthetic-event-omits-platform-side-effects` and `acceptance-journey-truncation` before writing browser journeys.

S4 records the new `shared-temporary-staging-ownership` process finding in
`area:ci-release`; its first occurrence remains open without a new mechanism.


### S6 real Web failure repair: shared writer across pthread realms

**Premises refreshed before editing.** The frozen local candidate
`caf8d59c27c827597e716eae728f7d495559b9f5` / tree
`dc21a9316e48ab30eb85b2353a7cca010f943c4c` ran the original official
`web_toolchain` proof and exited 1: the Chromium audio group selected 30,
passed 25 and failed 5. Three actual traces expose `PROJECT_BUSY` after the
real audio start: Control retains the Project writer, while the dedicated
Journal worker sees only its own realm-local lease map and attempts another
exclusive physical lock. The ordinary first journey also has a distinct stale
immediate `awaiting_audio` assertion; the accepted ticket actually precedes
continuation and reports `preparing`. The fifth aggregate timeout does not
itself expose an internal busy payload. Preserve all original logs and traces;
Native 42 PASS does not establish Web lease ownership.

Current main refreshed to `a33f64278ef1dab4a3d0b7325ff8dcb8185388b8`.
Intervening cost documentation, Portal candidate-cut classification and the
separate Build 2.0.92.0 allocation/snapshot do not repair these runtime/test
premises. Preserve that independent identity and snapshot on final integration;
this repair allocates no Build. The closed product-decision Issue #1959 defines
Off/1/2 device preferences; it does not establish S6 implementation acceptance.

**Declared repair files.**
`packages/project-io/src/web/storage_platform.cpp`,
`src/web/library_opfs_storage.js`,
`include/lmdj/project_io/storage_platform.hpp`;
`packages/web-runtime-platform/src/web-runtime-pre.js`,
`test/runtime_loader.test.mjs`;
`tests/platform/web/project_io/project_io_web_test.cpp`,
`project_io_web_conformance.spec.mjs`, `opfs_writer_error_test.mjs`;
`tests/platform/web/audio/realtime_audio_worklet.spec.mjs`;
this plan, `docs/design/2026-10-11-scheduled-pattern-record-count-in.md`,
`apps/docs-site/docs/core/modules/project-io.mdx`,
`apps/docs-site/docs/core/modules/web-runtime-platform.mdx`, and
`.agents/pitfalls/storage-precondition-only-one-platform-enforces.md`.

**Behaviour.** Share a genuinely acquired private writer state for the same
platform instance and canonical root. Each pthread owns its local lease wrapper
and delegated authorization; the original realm alone owns the physical handle.
Pin admission and final total-reference sealing form one atomic decision.
Parent-reference zero does not seal while a child reference remains: exact
same-platform reacquisition must retain Native semantics. A remote release
removes its exact local authorization before dropping its pin and never waits
for Control. A separately allocated fixed-width pin block stays alive through
both C++ state and owner-JS physical custody; actual close releases the latter.
Owner-local drain closes only the exact retired acquisition and keeps pending
or failed physical debt. Off-realm wrapper destruction must not release a
same-numbered token in another realm; retain honest cleanup debt. Preserve the
original C++ lexical-normalization then JS residual-path-check ordering.

The authenticated terminal handshake authorizes once. A pending/failed local
drain keeps the channel and Worker alive; only an actual strict positive close
result permits its existing complete/released-and-closed receipt. No writer
lock is released and reacquired to hand work over, no recovery is repeated by a
borrower, and no storage effect moves onto Control.

**Lowest-tier witnesses and future verification.** Actual production-JS writer
and terminal-loop tests cover authorization, pending/failure and close custody.
The real OPFS/pthread witness covers root reset while child-held, same-platform
reacquisition, independent physical exclusion, child last-use and natural join,
actual owner close and complete-byte independent readback. Correct only T1's
immediate phase, retaining its full Record/Press/Release/Record-off/Truth/Stop
journey. Rebuild and rerun the original complete official Web toolchain proof,
then all remaining S6 owning production OPFS, Web Host, Creator and platform
proofs on the final candidate. Native component/stress history and all original
30/300-second budgets, 64 rounds, browser workers and far-side assertions stay.
New regression source is UNRUN until actual execution; this repair is incomplete
until its owning checks and current-head review pass.

**Gate defect caught.** A live Project writer that falsely excludes its own
Journal worker, or a reported terminal release before the real physical writer
is closed. No new universal gate or timeout is introduced.

**Version Management.** Internal Project I/O/Web Runtime Platform PATCH debt;
retain all existing S6 capability MINOR/ABI MAJOR debt. Existing storage vtables,
DTOs and persisted Contracts stay unchanged. No version number, Product Build,
Assembly, tag or Release is allocated.

**Documentation impact: required.** Affected portal pages:
`/core/modules/project-io/`, `/core/modules/web-runtime-platform/`.
The same repair updates current topology and remaining verification limits;
immutable historical snapshots stay unchanged. Run the original official
`scripts/docs-site.sh check` before the repair commit.


## S6 current-head review followup — engagement reuse and lifecycle consumption

The complete independent review of `c7448c60af2116e6e789e425ae5e1567e2decc49`
(base `f084f3e345b4122e0649907e30eb83f331546887`) requested changes: the prior
scheduled opening clock can strand a later ordinary opening, normal SDK input
consumption can queue behind the lifecycle RPC waiting for it, and ordinary
opening can rewrite a retained cancelled scheduled ticket. These are confirmed
source paths; the review did not run new reproducers. The original committed
Creator proof is separately red and retained; its final eight-group receipt
must be read independently. Neither finding justifies widening the original
five-second opening or 300-second stress budget.

**Declared files.** `packages/application-facade/src/pattern_transport_controller.cpp`,
`tests/core/facade/pattern_transport_controller_test.cpp`,
`packages/web-runtime-platform/web/runtime_session.mjs`,
`packages/web-runtime-platform/test/runtime_session.test.mjs`, this plan,
`docs/design/2026-10-11-scheduled-pattern-record-count-in.md`, and the current
Application Facade and Web Runtime Platform module pages.

**Behaviour.** A new ordinary Record binds its guard to its own preparation
clock and starts fresh internal opening state. Scheduled status updates belong
only to the matching active scheduled operation; old caller evidence stays
inspectable. Exact locally admitted input continuations remain serialized per
ticket independently of a lifecycle RPC that waits for their consumption.
Unknown tickets, new admissions and other ordinary Host work keep original
ordering. Preserve response-loss debt, request identities, real Release,
physical last use and caller/worker consumption.

**Lowest-tier tests and defects caught.** The existing real Native Facade
component test must cover controller reuse across ordinary and scheduled takes,
old real-clock expiry followed by prompt new durable opening, genuine receipt
ACK, correlated input and far-side Truth/reopen. A winning pre-S cancellation
retains an unchanged old ticket across ordinary opening. Existing SDK tests
must model lifecycle response retention until the original Release consumer
actually consumes its ticket. The production SDK/Bridge/Host browser witness
then verifies that model against real runtime ownership. Keep all prior full
journeys, workers, rounds and budgets; execute affected Portal checks before
commit, then the selected committed-head lanes before shipping. Source-only
work and individual old green receipts are not completion of this followup.

### Version Management

Version impact: none. This followup repairs existing internal lifetime and
queue ownership without a manifest, Contract shape or Product Build change.
Preserve independently allocated upstream Build and immutable snapshots when
integrating the final candidate.

Documentation impact: required. Update `/docs/core/modules/application-facade`
and `/docs/core/modules/web-runtime-platform` and the existing design/plan in
the same Task. No topology change is introduced by this repair.


**Creator followup scope refresh.** The original complete c744 Creator run
naturally ended exit 1: all eight groups, 136 selected / 106 PASS / 19 FAIL /
11 SKIP. Its full log, source binding and browser evidence are retained.
Three new silent-Pattern setups sent an invalid empty edit. Eight existing
observers require the old trigger/outcome stream after companion negotiation;
replace them with actual exact-ticket consume, complete NativeResult and
required durable evidence. The shared Candidate journey bypassed Creator's
opted-in Session reopen. Preserve its Web Host branch and every original leg.
The slow 40 BPM observer may have a short inspect RPC spanning its intentional
main-thread stall; record and fence the original observer before blocking,
without changing any Host/input/opening deadline. Six real lifecycle failures
remain independent runtime debts until rebuilt verification establishes their
cause and successful disposition.

Add these declared files before editing: `tests/platform/web/candidate_journey.mjs`,
`tests/platform/web/creator/fixtures/count_in_helpers.mjs`,
`creator_web_count_in.spec.mjs`, `creator_web_sequence.spec.mjs`,
`creator_web_default_streaming.spec.mjs`, `creator_web_lifecycle.spec.mjs` and
`creator_web_sample_editor.spec.mjs` under that Creator directory. Validate the
original focused journeys and all six S6 count-in cases against an actual
rebuilt Creator, then run the original full eight-group proof when ready.
Do not convert an old missing-observer failure into runtime acceptance by
source inspection, or lower the gate to admission alone.


## S6 followup — exact physical gesture ownership

The original eight-group Creator run on `6f1039e5` naturally ended with
118 PASS / 8 FAIL / 11 SKIP. The separate three-case production I/O proof on
`178fb6f3` also failed in Project setup before its held-I/O assertions. Preserve
both original receipts. Neither result permits widening a timeout or removing
a journey. The original one-second input, five-second opening and 300-second
stress budgets remain unchanged.

**Declared files.** `packages/web-runtime-platform/web/runtime_session.mjs`,
`packages/web-runtime-platform/web/runtime_types.d.ts`,
`packages/web-runtime-platform/test/runtime_session.test.mjs`,
`apps/creator-web/src/runtime/input_controller.ts`,
`apps/creator-web/src/runtime/runtime_types.ts`,
`apps/creator-web/test/input_controller.test.ts`,
`apps/creator-web/test/workspace_shell.test.tsx`, this plan,
`docs/design/2026-10-11-scheduled-pattern-record-count-in.md`, and
`apps/docs-site/docs/core/modules/web-runtime-platform.mdx`.

**Behaviour.** An optional local object-reference gesture key joins the existing
SDK trigger/release calls. It is opaque, never serialized or persisted, and
changes no Native command or Contract. Only the negotiated input profile can
promise exact physical correlation. Three-argument calls retain their original
compatibility behavior. Keyed release selects its exact original hold, never
the latest same-slot/source hold; live key reuse and key/slot/source mismatch
refuse before dispatch. Response-loss reconciliation preserves that binding.

One private Release intent is reserved before waiting for an unknown press
sequence. Keyup, cancel, unkeyed release and SDK safety join that same intent,
retain its first deadline, and never invent admission, consumption or physical
retirement. A definite refusal before dispatch may permit a fresh later attempt;
a submitted unknown outcome retains its real original owner. Physical release
and original press caller consumption remain independently owed. A matching
profile Release whose lost press identity reconciles while a lifecycle RPC is
waiting for it uses its real locally retained continuation, only after actual
lifecycle handoff, independently of the
Host request tail. Its short runtime admission ordering and original handoff
deadline remain; new inputs and unrelated requests cannot use this path.

Creator keeps physical gestures independently of voice state, visual tokens
and loop latches. It submits exact-key Release after an actual trigger call,
even if keyup happened while Sample inspection or durable completion waited,
or after a one-shot voice naturally ended. A gesture with no actual trigger
call owes no Native release. One-shot/loop-toggle physical Release preserves
the Native playback semantics; gated modes retain their existing sound cutoff.
Dispose/adverse cleanup submits physical obligations before abandoning local
observation. A false SDK return is not a consume ACK.

**Lowest-tier tests and defects caught.** SDK owning tests assert actual request
identities and consume replies for opposite release order on the same slot and
source, admission response loss, concurrent keyed/unkeyed/safety releases while
the press sequence is unknown, original deadline expiry, live key reuse,
mismatch and genuine retirement. Creator owning tests cover early keyup,
natural voice completion, preserved loop latch, opposite pointer release order,
adverse/dispose cleanup and the original legacy fallback. Existing test strictness
and all original production journeys remain. Run meaningful original-source RED
and repaired-source GREEN discriminators, the owning SDK/Creator suites and the
official Portal check before committing. Then run all selected committed-head
lanes and independent complete current-head review before shipping.

### Version Management

Version impact: additive Web Runtime Platform MINOR debt, included in the
original unshipped S6 coordinated settlement. The optional exported argument
is compatible with existing callers. No Native wire, persisted Contract,
Product Build or Assembly change is allocated by this followup.

Documentation impact: required. Update `/core/modules/web-runtime-platform/`
and this design/plan in the same Task. Source and unit evidence do not establish
Native/Bridge/Creator/browser or physical hearing acceptance.


## S6 followup — exact negotiated recovery probe deadline

Base `bd3e77930645e939d5f23949899e71d4599d62c8` / tree
`b93b2349c3a0a88ac54d498eb6788e9ec2b723db` retains the delivered local
physical-gesture fix. Its negotiated profile still rejects an expired recovery
Press caller without failing SDK HostState, classifies probes after awaited
admission (including Release), and may publish late recovery success before
checking the original deadline. These three source premises remain outstanding.
The original packaged recovery fault seam targets the legacy notification path;
its faithful profile seam is a separate Task, not acceptance of this repair.

Declared files: `packages/web-runtime-platform/web/runtime_session.mjs`,
`packages/web-runtime-platform/test/runtime_session.test.mjs`, this plan,
`docs/design/2026-10-11-scheduled-pattern-record-count-in.md`, and
`apps/docs-site/docs/core/modules/web-runtime-platform.mdx`.

Capture one Press-only private probe reservation before awaited admission, with
its exact recovery epoch, foreground epoch and original caller start. Preserve
original one-second deadline and all actual input/caller/physical debts. Current
probe failure uses SDK failure; stale/expired success cannot emit recovery
success, clear another epoch or restore running. Release is never a probe.
Late accepted admission after interruption retains and genuinely releases its
original physical owner. Ordinary running Pad expiry remains nonfatal.

Lowest-tier owning tests distinguish actual current-probe timeout, delayed
timer late consume, known/unknown admission error, epoch/foreground invalidation,
Release versus probe/duplicate admission, and healthy success/ordinary timeout.
Use finite fixture turns, immediate rejection handlers, unchanged original
request/reply identities and real modeled consume/physical evidence. Root owns
same-fixture original-source RED/fresh restoration GREEN, owning SDK/Creator
source checks and full Portal before commit. Rebuilt original recovery journey
and complete eight-group Creator proof remain required before shipping.
SOURCE ONLY delivery does not execute, commit or grant runtime acceptance.

### Version Management

Version impact: Web Runtime Platform PATCH correctness debt in the original
unshipped S6 settlement; no additional identity allocation, public API, Native
wire, persisted Contract, Product Build or Assembly change.

Documentation impact: required on `/core/modules/web-runtime-platform/`, with
this design/plan updated in the same Task.

## S6 followup — failed legacy engagement still shuts down its worker

The independent review of `9c42ca9faeb2dc63ab6139fc2206b09b84060ea1`
confirmed a P1 source premise: an opted-in ordinary Pattern Play with the
count-in input profile unnegotiated can settle to idle, then fail on an
unrelated Bridge deadline. The failed service path requests controller shutdown
only inside the negotiated input-owner acknowledgement. Generation zero and a
disabled profile return before that request, leaving the actual executor alive
and the Bridge terminal-release gate permanently closed. This remains
outstanding in the reviewed S6 candidate `9c42ca9f`, assembled on the read
integration base `e2d3aaf740d08e917867a6594c689b97e0d3da2b`. That base's release
cuts do not contain this S6 producer; they do not supersede the candidate fix.

Declared files: `packages/web-runtime-platform/src/control_runtime.cpp`,
`packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp`,
`packages/web-runtime-platform/test/control_runtime_test.cpp`, this plan,
`docs/design/2026-10-11-scheduled-pattern-record-count-in.md`, and
`apps/docs-site/docs/core/modules/web-runtime-platform.mdx`.

After actual failed audio retirement reaches Native stopped, request genuine
shutdown of any engaged Pattern controller independently of whether a profile
input owner exists. Keep its original count-in caller debt and every physical,
Native input, worker, facade and Bridge-consumer gate. The request is intent,
never a substitute Stop, worker exit, physical acknowledgement or F receipt.

The lowest-tier regression keeps the legacy profile disabled and exercises
ordinary Play, the original Bridge timeout, actual callback-thread last use,
Native Stop, observed executor stopped, the original response and its release
thunk, terminal release, independent writer acquisition and unchanged reopened
Truth. A narrow read-only detail companion observes the actual executor's
stopped state separately from idle or Host terminal state. Root runs the
unchanged owning Native binary against rebuilt original/fixed production flow;
fresh-mtime restoration, actual rebuild exits and the failure inside this test
are required. Existing deadlines and all original tests remain. Full Portal
precedes commit. Actual Web/OPFS and current complete candidate acceptance are
separate evidence, not inferred from the Native fixture. The original complete
Creator run naturally exited 1 with 125 PASS / 1 FAIL / 11 SKIP on `9c42ca9f`;
its recovery replacement failure remains recorded. Sequential rebuilt Native
discrimination then failed the original flow at this regression's actual
worker-stop wait and passed the repaired complete Host binary. This is owning
Native evidence only. Ordinary Record held in preparation at Native stop has
a separately identified inherited settlement gap and remains a followup;
this idle Play regression does not cover it.

### Version Management

Version impact: correctness and additive internal conformance-observer debt in
the already declared unshipped Web Runtime Platform MINOR settlement. Existing
object layouts, wire and persisted Contracts remain compatible. No Product
Build or Assembly identity is allocated by this followup.

Documentation impact: required on `/core/modules/web-runtime-platform/`, with
this design/plan updated in the same Task.


## S6 followup — retained ordinary preparation after Native stop

Independent source review found an inherited gap beyond the idle Play repair:
ordinary Record can retain an actual `prepare`/`preflight` operation when audio
fails. Shutdown cannot submit a new Stop while that request is pending. After
the real preparation completes, Native `not_running` changes phase to error
but leaves the original preparation pending; the real executor cannot stop.
This premise was source-confirmed and is now distinguished by the same freshly
rebuilt regressions: the original Controller and Host each fail inside their new
owner-disposition witness; the fixed full Controller, count-in, executor, Host
and original 64-round stress all pass. The stress takes 226.44 seconds under its
unchanged 300-second ceiling. This Native evidence does not certify the complete
integrated Web/Creator/OPFS/PCM or physical candidate. The Task depends on the
verified E idle Play repair, replayed as
`ea9ab99b043f68c13aa3e75ca079a5b54bc9c6e7` (tree equals original `61decc21`).

**Declared files:** `packages/application-facade/src/pattern_transport_controller.cpp`,
`tests/core/facade/pattern_transport_controller_test.cpp`,
`packages/web-runtime-platform/test/control_runtime_test.cpp`, this plan,
`docs/design/2026-10-11-scheduled-pattern-record-count-in.md`,
`apps/docs-site/docs/core/modules/application-facade.mdx`, and
`apps/docs-site/docs/core/modules/web-runtime-platform.mdx`.

Retain a private binding of the exact failed ordinary preparation request and
its genuine Native refusal. Only a known completed preparation, actual
`not_running` refusal and shutdown intent authorize its terminal bookkeeping.
Preserve unknown work, original command/epoch/opening clock/caller error and
legacy/input debt. The same real worker performs existing `owner_lost`: actual
Journal absence is read back; an existing matching prefix receives durable
owner-loss disposition; foreign, refused or uncertain effects retain their
real debt. No start/cutoff frame, opened take, successful cancellation or ACK
is manufactured. Executor shutdown still requires actual work, input and
owner settlement, with caller response consumption remaining independent.

**Lowest-tier verification:** unchanged complete controller tests plus a new
real storage-delegate discriminator for receipt-bound preflight/no Journal,
legacy prepare/real empty prefix, unknown preparation and refused/uncertain
owner-loss sync. Original and repaired production are freshly rebuilt with the
same fixtures; the original failure must occur inside the new regression.
A real Host witness additionally retains actual callback last use, Native stop,
held original preparation, same-worker disposition, executor owner release,
original Bridge consumer/release, independent writer acquisition and complete
Truth/Artifact reopen. Storage gates delegate the actual operation and release
on unwind; they do not manufacture completion. Ordinary Native links do not
borrow a Web-only conformance hook. Keep every original test, 1-second input,
5-second opening, 300-second stress, 64 rounds and original workers. Full Portal
runs before commit. Current integrated Web/Creator/OPFS/PCM and physical/manual
acceptance remain separate obligations, not inferred from a component result.

### Version Management

Version impact: correctness debt within the already declared unshipped S6
settlement. Private implementation bookkeeping adds no public layout/vtable,
wire schema, persisted Contract or Product identity allocation.

Documentation impact: required on `/core/modules/application-facade/` and
`/core/modules/web-runtime-platform/`, with this design and plan in the same
Task. Source text describes the required behavior; runtime proof is recorded
only after actual execution.


## S6 followup — wait for outstanding fatal cleanup with no retained Pattern debt

The original packaged recovery journey reached its replacement factory while
the old Native transport was sealed but its real full-owner receipt remained
false, with an AudioContext and BroadcastChannel still alive. The SDK's repeated
close branch skipped its outstanding terminal cleanup Promise solely because
Native was sealed. Sealing is not completion of actual owner/backend cleanup.
This Task removes that extra bypass when no retained Pattern owner exists,
waiting for the same actual cleanup Promise without relabeling the original
fatal close as successful. Existing unknown retained Pattern debt continues to
report false promptly; it is not discarded or converted into physical release.

**Declared files:** `packages/web-runtime-platform/web/runtime_session.mjs`,
`packages/web-runtime-platform/test/runtime_session.test.mjs`, this plan,
`docs/design/2026-10-11-scheduled-pattern-record-count-in.md`, and
`apps/docs-site/docs/core/modules/web-runtime-platform.mdx`.

**Lowest-tier verification:** same strict SDK regression against original and
repaired source, with separate actual Native full-owner and AudioContext-close
barriers, two original close callers, intermediate non-settlement and unchanged
fatal result. Preserve rejected cleanup and all existing retained-debt cases.
Run complete owning SDK/Creator controller tests, types and full Portal before
commit. The original packaged recovery and complete final Creator remain
independent runtime obligations; no assertion, journey, worker or deadline is
removed. If the real recovery still has retained debt at this boundary, this
narrow repair is insufficient and must be reported before expanding its API.

### Version Management

Version impact: private correctness within the already declared unshipped Web
Runtime Platform S6 PATCH; no new public API, wire, persisted Contract or Product
identity is allocated. Documentation impact: required on
`/core/modules/web-runtime-platform/`, with this design and plan. Source-only
text and component verification do not establish final integrated acceptance.


## S6 followup — require genuine cleanup before Creator replacement

Premise at actual main `cbd7f898604f4e0953cb912279976bf12badaecc`: both
Creator replacement paths still follow any settled close result. The original
packaged recovery reached a new factory with the old Native full-owner receipt
false and an AudioContext/BroadcastChannel alive. Verified Q waits the same
cleanup when local Pattern debt is empty, but retained-debt prompt false and
cleanup rejection remain distinct from completed retirement. Registered
application shutdown barriers also swallow failures. These remaining producer
and consumer gaps require this Task; the latest main squash witness is unrelated.

**Declared files:** `packages/web-runtime-platform/web/runtime_session.mjs`,
`packages/web-runtime-platform/test/runtime_session.test.mjs`,
`packages/web-runtime-platform/web/runtime_types.d.ts`,
`apps/creator-web/src/runtime/runtime_context.tsx`,
`apps/creator-web/src/runtime/runtime_types.ts`,
`apps/creator-web/test/runtime_context.test.tsx`, this plan,
`docs/design/2026-10-11-scheduled-pattern-record-count-in.md`,
`apps/docs-site/docs/core/modules/web-runtime-platform.mdx`,
`apps/docs-site/docs/platform/web-runtime.mdx`, and
`apps/docs-site/docs/hosts/creator-web.mdx`,
`packages/web-runtime-platform/src/web-runtime-pre.js`, and
`packages/web-runtime-platform/test/runtime_loader.test.mjs`.

The original loader invocation must explicitly register its locally created
Host through the exact private Module configuration before publication. A changed
global Host is not proof of ownership; failed custom loading without registered
ownership remains ineligible and cannot terminate a foreign Host. Bind cleanup
completion before any external pressed/diagnostic callback can reenter. Original
initialization budgets and known failure outcomes remain unchanged.
The default packaged loader serializes shared Module injection per window before
its first await; overlap is refused without replacing the original configuration.
Its reservation ends only when that original load invocation settles and is not
proof of physical owner retirement. Producer registration validates the exact
original Module reference, including when callbacks change global publication.

Add local `waitForTerminalCleanup(): Promise<boolean>` as an explicit SDK
consumption API. It observes the same already initiated cleanup, never starts
another terminator, Stop, admission, Release or deadline. A call before cleanup
starts returns false and cannot initiate cleanup. Cleanup rejection also returns
false; only already initiated unknown cleanup remains pending. Bind the one cleanup Promise
before invoking potentially reentrant terminator code. Only actual Native
full-owner retirement, original caller/input/physical settlement, actual backend
closure and existing SDK teardown permit true. Failed or unproven cleanup is
ineligible; retained unknown debt remains pending. Preserve original close
booleans and first fatal error. A resolved custom terminator is not a receipt.
Explicit never-loaded absence and legacy healthy closure must retain their
separate truthful contracts rather than treating missing getters as Native ACK.

Creator caches one exact-session replacement-eligibility wait separately from
close. Manual and automatic replacement require positive cleanup and original
application barriers before factory, preserve fatal display while waiting,
and suppress duplicates/stale/unmounted/yielded generations. An absent waiter
is eligible only under the existing genuine normal clean-close true contract;
false/rejection/undefined is ineligible. Registered barrier rejection remains
real rejection, observed for unhandled-rejection safety without swallowing it
into successful factory permission. Preserve the original one automatic
allowance and manual retry latch; negative results create no instance.

The existing Perform producer itself swallows some Stop/capture/finalization
errors before its registered barrier can observe them. This Task preserves
actual propagated rejection only. A separate followup must retain the real
Perform shutdown failure and prove no replacement across that producer/consumer
boundary; final S6 acceptance cannot infer its completion from a controlled
barrier rejection test.

**Lowest-tier verification / defect caught:** SDK tests distinguish held
original consumers, Native receipt, backend closure and final teardown; include
reentrant invocation, rejected/no-ACK/open-backend cleanup and repeat callers.
Creator tests retain every original lifecycle leg and assert zero factory calls
before positive completion or after cleanup/application-barrier failure, with
manual/automatic duplicate and stale-generation protection. Root runs identical
meaningful old/fixed fixtures, complete SDK and Creator controller suites,
types/build and full Portal before atomic commit. Original packaged recovery
240/120/10/30-second budgets, full eight-group Creator, original 1/5/300-second
bounds, 64 stress rounds and workers remain unchanged. Model/source results
do not establish Native/browser OPFS/PCM or physical acceptance.

### Version Management

Version impact: additive Web Runtime Platform MINOR and Creator PATCH debt at
the next coordinated version settlement. Actual main already has SDK 5.8.0;
that allocated identity does not cover this new API. This Task allocates no
version or Product Build, changes no Native wire or persisted Contract, and
performs no release. Documentation impact: required on
`/core/modules/web-runtime-platform/`, `/platform/web-runtime/` and
`/hosts/creator-web/`, with design and plan updated in this same Task.


## S6 followup — recovery fixture forwards actual terminal ownership

The original complete Creator run on `9c42ca9f` retained its recovery timeout
failure: the main Chromium group ended with 99 PASS / 1 FAIL / 1 SKIP; the
remaining groups continued independently. The actual negotiated-profile probe
was admitted and genuinely consumed. Only delivery of that same completed
reply was held until the observed SDK HOST_TIMEOUT. The fixture transport
wrapper omitted the native terminal-ownership accessor, so the SDK could not
observe its required real owner-release receipt before replacement. Actual
Native owner release was not proved by that failure trace.

**Task scope:** `tests/platform/web/creator/creator_web_lifecycle.spec.mjs` and
this plan. Forward the original generation's actual terminal lifecycle through
the fault wrapper. Preserve the same request/ticket/consume response, original
failure injection, 240-second test budget, 120-second replacement wait,
pre-factory closure, generation/listener assertions and final real Pad wake.
Do not synthesize released state, bypass the injected consuming request,
invent ACK/F, relax a gate or treat source changes as runtime acceptance.

**Owning verification:** syntax check and the unchanged packaged recovery
journey against a rebuilt actual candidate. The original failure remains
recorded. The complete integrated Creator run, legacy failure cleanup,
production OPFS and physical acceptance retain their own proof obligations.
Only source work is admitted while the previous full Creator run is active.

**Documentation impact: none.** This fixture-transparency correction does not
change product behavior, architecture, Portal documented source facts,
manifests or identities; the plan records its failing premise and owning test.

### Version Management

Version impact: none. This Task changes a test fixture and its plan only;
public interfaces, persisted Contracts and Product identity remain unchanged.


## S6 followup — preserve actual Perform shutdown outcomes

The real Perform controller currently catches setup, Core/capture Stop and
finalization failures before its registered close barrier observes them. The
Provider's positive SDK cleanup cannot prove application WAV/storage work has
settled. This remains at main `cbd7f898604f4e0953cb912279976bf12badaecc`;
W source starts on integrated `1550151e8b05155e705bbcb630d05f6778d5e49a`.
Verified V positive-cleanup/Provider changes are a dependency before runtime
verification; their pending source draft is not acceptance.

**Declared files:** `apps/creator-web/src/state/perform_state.ts`,
`apps/creator-web/test/perform_surface.test.tsx`, this plan,
`docs/design/2026-10-11-scheduled-pattern-record-count-in.md`, and
`apps/docs-site/docs/hosts/creator-web.mdx`.

Preserve original public Stop/Leave/Save UI outcomes while privately retaining
the actual shutdown-relevant operation identity, original failure and unresolved
ownership. Cached close rejects the original unresolved failure after all safe
existing work settles; repeated calls retain that exact Promise. No global
reported-error flag may permanently block a known no-owner operation whose
actual cleanup succeeded. Unknown begin or durable write response remains
unknown; absent revision/resources or a fulfilled UI method is not settlement.
Only genuine matching retry/readback and actual cleanup can clear matching debt.
No extra Stop/cancel/admission, fake owner ACK or second writer is introduced.

**Lowest-tier verification / defect caught:** use the real Perform controller
through its actual registered Provider barrier. Hold then reject original Core
Stop, capture/WAV, setup compensation and finalization outcomes; even an
independently positive modeled SDK cleanup cannot create a new factory. Keep
original error/retained artifact identity and far-side assertions. A strict known
no-owner/actually-cleaned companion must allow genuine closure, detecting an
overly broad error latch. Preserve every existing Perform and Provider journey,
original budgets/workers and complete tests. Root owns same final fixture
old/fixed discrimination, full Perform/Creator controller, types/build and full
Portal before atomic commit. Component facts do not certify actual SDK Native
retirement, OPFS/PCM, physical hearing or original full packaged Creator. Any
additional packaged producer witness must have an explicitly expanded scope
before editing; final S6 retains its complete original eight-group obligations.

### Version Management

Version impact: Creator PATCH debt at the next coordinated settlement. This
private correctness Task allocates no identity or Product Build and changes no
public SDK API, Native wire or persisted Contract. Documentation impact:
required on `/hosts/creator-web/`, with this design and plan updated together.

## S6 followup — preserve final input consumption budget and diagram scope

**Premises refreshed before editing.** Actual main remains
`cbd7f898604f4e0953cb912279976bf12badaecc` at the 2026-10-12T22:08Z
fetch, with no intervening changes. This isolated repair starts at
`c0052f5d380db9aeed835a70aae1c0c621ddc340`, whose independent full
109-file/798-hunk review remains REQUEST_CHANGES. Both findings remain:
the public count-in test helper checks the original one-second deadline after
non-consuming observation, but not after the actual consuming reply; the
ordinary+scheduled Facade diagram overstates the scheduled pre-S I/O rule.
Ordinary Record still performs preflight/prepare work before audio submit;
scheduled count-in waits for its actual applied e1/S before opening.

**Declared files:** `tests/platform/web/creator/fixtures/count_in_helpers.mjs`,
this plan, `apps/docs-site/diagrams/application-facade.architecture.json`, and
its officially generated `static/diagrams/application-facade.svg` and `.html`.
Check the same saved input deadline immediately after the original consuming
await, before publishing settled success. Retain that RPC, actual ticket,
Native/durable/admission/authority/retention assertions and every far-side leg.
Qualify the diagram card to scheduled count-in; ordinary preflight/prepare and
strict scheduled e1/S-before-open behavior stay unchanged.

**Lowest-tier verification / defects caught:** import the actual helper in a
focused clock model. On-time observation followed by consume at/after the
original deadline must fail; consumption before it must retain the original
result and correlation checks. The same late-consume expectation must fail
against the old helper. This models witness timing only, never Native/backend,
OPFS/PCM or physical retirement. Regenerate diagrams through the official
portal script, verify generated equality, and run the original complete
`scripts/docs-site.sh check`. Preserve the in-flight frozen c005 original full
Creator run through natural exit. After repair integration, the final committed
candidate still owes its original whole eight-group Creator proof and every
other selected exact-head lane; an old-head PASS cannot clear these findings.
No original budget, worker count, journey or consume leg is relaxed.

### Version Management

Version impact: none. This changes a test witness and documented source fact,
with no product/API/ABI/wire/persisted Contract or Product Build allocation.
All existing unshipped S6 version debts remain. Documentation impact: required
on `/core/modules/application-facade/`, with source diagram and official
HTML/SVG outputs updated in this Task. S6 runtime and physical acceptance
remain incomplete until their actual current-candidate evidence exists.

## S6 followup — integrate actual main live controls without losing retained input ownership

**Premises refreshed before editing.** This isolated integration starts at
`d3d75dce2f5d827cf77fb5c712d8dce8be3e8d8e` (tree
`1fe85f0d91c4e7a3703ec70810171f2e68dca38c`) and combines actual main
`25b8875478396df39ff0882c223c4c11bdf98806` (tree
`2909de8f4f429e99190375f68a4622215799f40f`). Main adds Project/Sample
navigation, typed Performance live producers, and silent Perform Pad navigation.
Its 35 changed files overlap 16 S6 paths; the actual no-commit merge returned
seven conflicted files. Keep both source histories, original worktrees and
all raw failure evidence. A merge conflict is not a product-test failure.

Before the final freeze, main advanced to
`368045df5df8eac1af44e31a9a4e6f1f1133666e` through PR #2110. That Task
updates the complete keyboard focus-order witness for the already integrated
Next Project button; it changes no product code. Preserve its exact two blobs
and the original far-side Pad assertion. The declared integration scope now
includes those two paths and the existing skipped-rebuild pitfall recurrence.

Independent source review found two concrete original-budget defects:
Bridge defaulted `performance.live.control` and `performance.live.status` to
30 seconds instead of their original one second; the retained Native test
helper also defaulted `audio.activate` to 30 seconds instead of one. Restore
both original policies, keeping all tighter caller cutoffs, other operation
budgets, explicit test overrides, and all original test registrations.
The 111-name operation registry is the exact union of both sources.

The previous D3 full Mac Core run actually passed 228 Core tests and 224 ASan
native tests. Its separate normal Release stress passed all 17 tests and the
full 64-repeat count-in journey in 145.54 seconds under the original 300-second
Facade limit. These receipts remain exact-source historical results. The
activation helper defect limits what that previous PASS establishes; it is
not proof of all original operation deadlines, the new integration, Dev-mode
obligations, other lanes, physical retirement, or hearing.

**Declared files.** The Task preserves all 35 actual incoming paths and owns
only the necessary conflict/budget/observer/documentation changes, plus the
previously drafted Web Host observer and this plan:

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/components/project_surface.tsx`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/diagrams/web-runtime-platform.architecture.json`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `apps/docs-site/docs/platform/input.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/static/diagrams/web-runtime-platform.html`
- `apps/docs-site/static/diagrams/web-runtime-platform.svg`
- `docs/plans/2026-10-09-creator-desktop-final-followup.md`
- `docs/plans/2026-10-11-performance-live-control-producers.md`
- `docs/plans/2026-10-12-web-live-performance-controls.md`
- `docs/plans/2026-10-13-creator-perform-pad-navigation.md`
- `docs/plans/2026-10-13-creator-project-sample-navigation.md`
- `docs/plans/2026-10-13-creator-a11y-rail-focus-fix.md`
- `packages/web-runtime-platform/src/bridge.cpp`
- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/web-runtime-platform/test/performance_bridge_test.cpp`
- `packages/web-runtime-platform/test/performance_master_capture.test.mjs`
- `packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs`
- `packages/web-runtime-platform/test/performance_protocol.test.mjs`
- `packages/web-runtime-platform/test/protocol.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `packages/web-runtime-platform/web/performance_master_capture.mjs`
- `packages/web-runtime-platform/web/performance_master_tap_worklet.js`
- `packages/web-runtime-platform/web/protocol.mjs`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence_grid.spec.mjs`
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- `tests/platform/web/host/web_runtime_host_browser.spec.mjs`
- `docs/plans/2026-10-10-pattern-switch-and-count-in.md`
- `.agents/pitfalls/revert-proof-rebuild-skipped.md`

**SDK source boundaries.** Retain the public four-argument trigger and real
opaque physical gesture key, typed live FIFO, original call-time deadline,
short admission tail, and separately awaited durable completion. Reserve
queued press capacity before enqueue. Count queued, admitted, response-unknown
and still physically held owners; an observer rejection alone cannot retire
them. Matching Release has its own reserved path and cannot wait for durable
completion or consume a new unrelated serial. Keep the same cleanup authority,
real Runtime terminator and all Native/callback/backend shutdown fences before
listener or tap detachment. Never replace actual termination with an ACK or
successful operation result.

The capability DTO and original fixtures still permit Native input capacity
up to 1024. A known-profile SDK ingress may conservatively use
`min(64, negotiated input_capacity)` without changing that Contract. The
existing direct unprobed input API does not gain an activation/probe prerequisite;
its local conservative limit cannot prove an unknown Native capacity. The
cross-domain relationship between Performance UUIDs and Pattern opaque gesture
keys was pending at this integration checkpoint. The user settled it in the
shared gesture capacity addendum below: one combined limit of 64 real gestures,
with one physical press counted once. Do not invent identity conversion or
claim that separately bounded queues establish that shared limit.

**Independent SDK review repairs.** The frozen two-file source review found
three additional defects within these existing boundaries. A definitely
unsubmitted legacy Press that returns `false` must release its local capacity
reservation; a submitted or response-unknown Press must keep its real owner
debt. The public boolean alone does not distinguish those cases. A real legacy
Release must follow its original queued Press even while header/capture
readiness is pending, without delaying the existing reserved profile Release
behind durable completion. Performance's release exception belongs to one
matching locally received gesture, and cleanup has one reserved token;
foreign or duplicate Releases and repeated cleanup requests must not create
an unbounded exception queue. Preserve original request/receipt identities
and truthful refusal results. These repairs preceded the shared-capacity
decision below and do not implement that contract by themselves.

**Observer and portal integration.** Observe both actual `send` and optional
`sendRetained` in the two original Perform navigation journeys. Preserve real
receiver, getter, arguments, return value, rejection and absent capabilities;
only add `pattern.transport.input.request` to the existing forbidden mutation
lists. Preserve all 64 Pad selections, Bank and shared selection checks,
SHIFT/System, held FX/HOLD, ENC4 MASTER and unchanged Truth assertions. Keep
the Web Host observer's real terminal getter and optional transport capabilities
visible; its original audio conformance failure remains a failure. Combine
product-output-0/cue-output-1 routing with main's strict start binding/started
ACK and capture-ready facts. Generate HTML/SVG from the official renderer;
never hand-resolve generated outputs or route cue audio through capture.

**Lowest-tier verification / defects caught.** Run complete
`host.web_control_runtime` and `host.web_performance_bridge` suites. The new
default-helper clock witness checks actual activation at 900/1100 ms with no
explicit caller cutoff; each real Bridge live operation spends 1050 ms in its
original queue before pumping. Independently revert each of the three budget
entries, rebuild, read the actual failed owning assertion, then restore with
fresh mtime and rebuild. Existing coordinator seams are unit/component setup,
not physical audio ACK evidence. A Pad-gate sequence does not prove no FX
admission; the strict actual `HOST_TIMEOUT` response owns the budget assertion.

Run the complete original SDK tests, preserving appended tests from both sides.
Add bounded queued-press/readiness-hold and matching Release/unknown-owner
regressions using actual Session methods. Run both full Perform navigation
journeys and demonstrate the new negative oracle against a rebuilt real input
producer mutation. Run the original complete Portal check. Final S6 still
requires the original complete eight-group Creator proof, separate held-I/O
count-in journeys, full Web Host audio/native/Chromium/WebKit selection, normal
Dev component/stress obligations and every selected exact-head batch-only lane.
No old-head PASS transfers to a new source, and no provider failure is review.
Original input 1s, opening 5s, component 30s, stress 300s, 64 rounds, workers,
Release/Stop/Truth/reopen legs and coverage floors remain unchanged. All new
runtime and rebuilt mutation proofs are tracked by their original private
receipts and input freezes; a passing earlier freeze cannot clear a later
source finding.

For the three SDK findings, use public Session methods to prove: 64 definitely
unsubmitted legacy refusals issue no Native trigger requests and leave room
for a genuine later Press and Release; a queued legacy Press and physical
keyup retain Press-before-Release order across a real readiness/receipt hold
and leave no orphan owner; and foreign/duplicate Performance Releases and
repeated cleanup requests cannot exceed their declared reserved positions.
Retain a separately submitted-unknown owner until actual release or closure,
every original matching Release, normal stop/finalization and far-side fresh
capacity reuse. Add only defect-specific cases to the two already-declared
SDK files and rerun their complete owning suite after the fresh repair freeze.
Component transport fixtures prove those modeled boundaries, not physical
audio callback retirement, browser durability or hearing.

The fresh SDK repair's original whole command first returned 313 PASS and
4 FAIL. Independent review found two malformed new Stop response fixtures and
two cleanup witnesses missing actual original-owner/backend closure producers.
Correct only those fixtures, keep strict protocol and production cleanup
authority unchanged, and assert pending independently before owner receipt
and backend closure. The corrected complete component command returned
317 PASS / 0 FAIL; original failed evidence remains retained.

The original complete Creator entry requires a clean committed source tree.
Its first launch on this uncommitted merge draft returned exit 2 at that
precondition before building or running any group. Preserve that result;
do not override the clean-tree check. Complete the declared lower-tier
verification and atomic Task source commit, then run the original eight-group
proof on that clean head. A source commit is a verification input freeze,
not full S6 acceptance or permission to transfer an older lane's pass key.

### Version Management

Version impact: none for this integration repair. Preserve already allocated
Build95 and all unshipped S6/W1/Creator version debts; allocate no new identity,
Product Build or immutable snapshot here. Shipping must still settle applicable
existing version obligations.

### Documentation Impact

Documentation impact: required
Affected portal pages: `/core/modules/web-runtime-platform/`,
`/platform/web-runtime/`; preserve the incoming current navigation/input pages.
Reason: current combined registry, budgets, real input ownership and
product/cue capture boundaries must match the integrated sources and diagrams.
Task source review, runtime verification, merge, release and physical/hearing
acceptance remain separate facts. No release or worktree cleanup is requested.


## S6 shared gesture capacity followup (2026-10-13)

**Decision and current premise.** The user explicitly chose a combined maximum
of 64 retained real Pad gestures across Pattern and Performance recording;
one physical press entering both domains consumes one place. Matching Release
for an already admitted gesture remains admissible at capacity. This settles
the formerly pending product decision above. It does not authorize deriving an
opaque physical identity from a persisted UUID or weakening ownership fences.

The isolated implementation base is
`3545d43aa6f791df2b1410ce23e3ba8e83e24460`. The first refreshed integration
target was `9fb83ce0f70de1bc9114711bf9e854dfa6bb7081`; the precommit refresh
on 2026-10-13 is `fe6f30bbf3897d3b09e25e4e85f4b1b22df7db23`. PRs #2114
(UI decisions), #2115 (current-Groove cancellation), #2107 (retained Pad ASSIGN)
and #2116 (Facade replay regressions) have since merged. Their actual diffs
add ASSIGN publication/SDK behavior and unrelated UI/replay coverage; they do
not deliver the shared physical-gesture ledger, App key forwarding or immediate
Perform admission. Those premises remain outstanding. A read-only merge preview
found a conflict in `packages/web-runtime-platform/test/control_runtime_test.cpp`
where the S6 and ASSIGN suites both add coverage. Preserve both complete suites
in a separate integration step after freezing this verified source Task; the
current source Task does not overwrite the other owner’s changes. The existing input controller already
has an opaque gesture key and a Performance UUID mapping, but App drops the
observer's key and Perform queues events before SDK admission. Separate SDK
Pattern and Performance limits therefore do not establish the chosen combined
limit. This premise remains outstanding. Preserve previously delivered source
and all historical test outcomes; this followup does not repeat S4.

**Declared files.** Root owns the four documentation files. The SDK/Host author
owns eight product/test paths; a separate component-test author owns only
`input_controller.test.ts` and `perform_surface.test.tsx`. These assignments
have no concurrent writers. A reviewer independent of each changed path
reviews its final delta:

- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `apps/creator-web/src/runtime/input_controller.ts`
- `apps/creator-web/src/runtime/runtime_types.ts`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/state/perform_state.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/creator-web/test/perform_surface.test.tsx`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `docs/prd/decisions/2026-10-11-performance-live-control-encoding.md`
- `docs/plans/2026-10-10-pattern-switch-and-count-in.md`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`

**Implementation boundaries.** Reserve capacity synchronously before either
Creator queue retains a new physical press. Use one session-local ledger keyed
by the original opaque physical identity; pass that identity through App and
Perform to the SDK without putting it in wire messages or Project Truth.
Convert a provisional producer reservation into its actual Pattern/Performance
owners, or release it only after definite non-submission. Retain submitted,
response-unknown and physical-hold debts until their actual matching release,
consumer completion or explicit owner closure permits retirement. An observer
rejection or UI finally callback is not retirement authority. Direct callers
without a physical key count independently; never guess equivalence from Pad,
UUID spelling or timing. A repeated domain claim must not double-count a press
or bypass duplicate-event rejection. Existing release and cleanup bounds stay
intact. Preserve exact legacy schemas and public call compatibility.

**Lowest-tier verification and defects caught.** Add public Session regressions
for the 64th/65th distinct physical gesture, the same press in both domains,
different keys on the same Pad, definite non-submission, retained unknown debt,
and matching release at capacity followed by actual retirement and fresh reuse.
Run the complete original SDK owning suite. Creator input/Perform components
must prove the original key survives App routing, queue ingress is bounded
before deferred work, refused presses produce no second-domain orphan, and
physical keyup still reaches its original owner. Run complete owning component
files and TypeScript, followed by the full Creator unit suite. Extend the
existing packaged Perform journey only where needed to prove the real key
routing; preserve every original Record-off, Stop and reopened Truth leg.
Component transport fixtures do not prove physical audio or storage durability.

Run the original complete Portal check for the changed documented behavior.
After those lower-tier checks pass, an atomic source commit may freeze the
candidate for the original clean-tree browser proofs. Final S6 acceptance still
requires its declared full Creator, Web Host, held-I/O, mutation, Native and
selected committed-head lane obligations and independent current-head review.
No test, timeout, worker count, stress round or journey leg is reduced. Original
1-second input, opening-only 5 seconds, 30-second component and 300-second
normal stress limits remain unchanged. Do not automatically retry the failed
3545 full Creator: its eight groups completed with 128 PASS, 1 FAIL and 11 SKIP,
exit 1. The Record-off failure follows a restart-required runtime state; the
specific input operation causing that state is still under investigation.

### Version Management

The additive local SDK reservation/identity companion adds to S6's existing
`web-runtime-platform` MINOR debt at the next coordinated version settlement.
Creator behavior adds to its existing Host debt. This Task allocates no Module,
Contract, Product Build or Assembly identity and creates no snapshot or release.
Persisted and wire contracts remain unchanged; reconsider the declared debt if
implementation cannot preserve those boundaries.

### Documentation Impact

Documentation impact: required. Update `/platform/web-runtime/` and
`/hosts/creator-interactions/` with the combined admission and Release behavior,
and record the settled decision in the existing Performance encoding decision.
Implementation, verification, merge and physical/hearing acceptance remain
separate. No cleanup is authorized by this followup.

## S6 followup — preserve ordinary Pad observer timeout semantics in Creator

Local base `61c4ebfd5be2135338bf228db32482c347137cbe` integrates main's
ASSIGN behavior with S6. Refreshed main
`45c8f479aa350cd490a100044a4723428976e2be` adds rail labels and SHIFT ordering
without changing the outstanding input-error classification. The SDK's existing
ordinary-input test proves that the original one-second observer can reject
while its original input remains retained and the SDK stays running. Creator
currently turns every `HOST_TIMEOUT` into `restart-required`, contradicting the
ordinary-input decision above. The precise originating operation in the
original full Creator Record-off failure remains unknown.

The precommit refresh to `50ecc7107a3347878e1d5aa7f72b031d7d58eb98`
adds the single-column Project browser. Its App delta moves the Sound Sets
entry and its tests change Project selection/navigation; it does not change
the input observer, diagnostics callback, or ordinary/fatal timeout premise.

Declared files: `apps/creator-web/src/runtime/input_controller.ts`,
`apps/creator-web/src/app.tsx`,
`apps/creator-web/test/input_controller.test.ts`,
`apps/creator-web/test/workspace_shell.test.tsx`, this plan, and
`apps/docs-site/docs/hosts/creator-interactions.mdx`.

First establish an actual short RED through the real controller/reducer and
rendered App: ordinary pending input expiry must leave Record-off usable while
retaining the original error and same-key physical Release. Classify only a
trigger/Release observer's `HOST_TIMEOUT` with `details.pending === true` and
the same SDK's current `running` state and null error as nonfatal. Do not
publish a ready state, clear another failure, cancel retained work, manufacture
consumption, or change the original caller deadline. Unknown timeouts, failed
recovery probes, activation, inspection, Sample controls and protocol failures
retain their existing fatal handling. Keep the original error in the bounded
Host diagnostics without changing history-failure bookkeeping.

Lowest-tier verification: deterministic new cases fail on the original Host
source; after repair, run both complete owning component files and TypeScript,
then the full Creator unit suite and original complete Portal check. The
rendered case must actually submit Record-off with the original session and a
new command, then observe recording false and playback continuing. Preserve
fatal negative controls. These fixtures do not prove Native/OPFS completion or
physical audio. The original complete eight-group Creator proof, other S6
acceptance obligations and current-head shipping evidence remain required;
this repair does not erase the original full-run failure.

### Version Management

This corrective Host projection change is included in S6's existing Creator
Host version debt. No additional manifest identity, Product Build, snapshot or
release is allocated by this Task; SDK and wire contracts are unchanged.

### Documentation Impact

Documentation impact: required. Update `/hosts/creator-interactions/` to
distinguish a retained ordinary Pad observer expiry from a failed Runtime.


## S6 followup — separate Sample preparation from Pad completion

The frozen `7e85ecff` original complete Creator proof finished all eight groups
with 128 PASS, 2 FAIL and 11 SKIP, exit 1. Preserve that result and its unchanged
source inventory. The original global Pattern playback/Record-off/navigation/
Stop/reopen journey passed in this run; the remaining failures are the MIDI
17/17 observation and the separate Perform FX Release journey. Neither that
passing journey nor a source diagnosis clears the full failure. Refreshed main
`613e23c26bb0ae54dccd75003b8858ac484b0faf` adds Sound Sets layout and does not
deliver either input repair; this Task remains based on the frozen candidate.

The MIDI trace records HOST_TIMEOUT and Creator restart-required after the
sixteen-note burst; later Export report is disabled, retaining the last sampled
3/3 counts. It does not expose the exact exception details or per-note Native
ledger. Source inspection independently proves that `sampleTriggerTail` awaits
the complete public Press result even though the SDK already separates short
admission from eventual consumption. Subsequent physical reservations spend
their original one-second age while waiting for that Host completion barrier.

Declare only `apps/creator-web/src/runtime/input_controller.ts`, its existing
`test/input_controller.test.ts`, this plan, and
`apps/docs-site/docs/hosts/creator-interactions.mdx`. Keep Sample inspection and
ready trigger invocation ordered, and observe each completion independently using the
same original physical key and error handling. Genuine matching Release remains
independent of Press completion. Do not alter SDK ownership, capture/early-gate
suppression, loop-toggle behavior, the shared 64 places or original deadlines.
A positively known unsubmitted Press expiry may report a local diagnostic while
the actual SDK is running and error-free; a matching Release's definite failure
and an actually failed SDK retain their original failure handling.

The pre-fix component RED produced the two intended assertion failures: second
inspection blocked by the first completion, and healthy SDK misclassified after
a known unsubmitted Press expiry. Its actual-SDK-failed and matching-Release
negative controls passed. The first repair passed all 152 owning tests, 1508
Creator unit tests, TypeScript and the original Portal check. Independent review
then found a same-Pad loop-toggle regression: a second trigger could arrive
before the first admission and leave a false loop latch. A new held-completion
case failed on that repair. Preserve this RED and the review finding alongside
the earlier passing checks.

Retain that loop-toggle dependency per Pad outside the global preparation tail.
Wake the original token only after the first admission has been observed,
rechecking lifecycle and token identity without renewing its lease or deadline.
Unrelated Pads still prepare and invoke while the first completion is held. The
second same-Pad press follows the existing stop path, and a third press starts
again. With this correction the complete owning file passes 153 tests. These are
controlled Session/Host boundary witnesses, not actual Native admission or a
full MIDI/browser PASS. Refresh TypeScript, full Creator units, original Portal
check and independent final-diff review on this correction before commit.
Preserve the original sixteen-note 17/17 and listener cleanup,
complete eight-group Creator, all selected lanes and S6's other owning proofs
on the final combined candidate; do not retry the full failure before repairing
the separately identified FX ordering/admission defect.

### Version Management

No identity allocation. This Host correctness repair adds to the existing S6
Creator version debt at the next coordinated settlement; no SDK/API, Contract,
Product Build, Assembly, release or snapshot change.

### Documentation Impact

Documentation impact: required on `/hosts/creator-interactions/` to distinguish
local unsubmitted Press expiry from matching Release and actual Runtime failure.
