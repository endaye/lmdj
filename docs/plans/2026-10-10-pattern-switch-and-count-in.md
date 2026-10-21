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

### S3 design preparation Task (2026-10-18, #2233)

Integration main: `4de2e7ddfe7f170aad3771b40d25333392c0a693`;
stack base: `0de1a81c941e19bd70d259566af283836b38926d` (S7 consumer #2359).
Current main and live #2233 were refreshed before editing. No successor delivers
recording switches: the Host still returns `pattern_transport_recording`;
production I/O retains/reconciles a switch only through cutoff/close; Creator
retains its recording gates. Native already retains actual per-slot applied
frames, material control pins and selected-boundary publication, and the Journal
already supports serially reconciled switch history. Reuse these positive
controls rather than design another realtime receipt queue or schema.

Declared files for this documentation-only Task:

- `docs/design/2026-10-18-recording-pattern-switch-segments.md` (new);
- `docs/design/2026-08-22-sequence-recording-semantics-design.md` (link addendum);
- `docs/plans/2026-10-10-pattern-switch-and-count-in.md` (this preparation).

The [S3 addendum](../design/2026-10-18-recording-pattern-switch-segments.md)
selects actual boundary/segment ownership, durable ordering, retained lease
lifetime, cross-boundary input and current-Pattern closure. It preserves the
approved product/held-note/recovery semantics and existing wire/Journal shapes.
Lowest-tier verification: source/test path ownership, local relative links,
approved-decision traceability and exact three-file/whitespace inventory. No
Native/UI/product proof or new CI gate belongs to this preparation. Each later
producer/consumer Task freezes its own exact files and owning tests before code;
the candidate owners below do not authorize a cross-layer omnibus commit.

Version impact: none — design preparation allocates no identity or artifact.
Documentation impact: none — current Portal/product behavior is unchanged.


S3 starts with a short design addendum to the [Sequence recording semantics](../design/2026-08-22-sequence-recording-semantics-design.md). It must cover:

- settling the old segment at the applied switch boundary rather than at close (SR-D23);
- several switches within one recording;
- keeping the applied switch in the production port;
- naming the new Pattern on Record-off.

The addendum names its files and tests before code starts. Expected owners: `pattern_transport_controller.cpp`, `project-io` `sequence_admission_codec.cpp`, `control_runtime.cpp`, and their Facade, Project I/O and Host tests. Creator then lifts its recording gate on the arrows, picker and Launch.

**Gate defect caught.** Events after the boundary landing in the old Pattern, or a second switch parking the engagement in `error`.

### S3 C1 — retain actual Native publication boundaries

At inspected main `4de2e7ddfe7f170aad3771b40d25333392c0a693`, playing
publication/cancellation and per-slot actual applied generation/frame already
exist. Serialized control pins already protect schedule material, independently
of audio borrows. There is no control-owned publication lease/query surviving a
later current Pattern. Add only that producer capability; the recording gate,
I/O continuation and Creator switch controls remain C2–C4. The design Task is
this branch's parent; refresh its actual introducing main before shipping C1.

Declared files (one implementation Task):

- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`;
- `packages/audio-runtime/src/realtime_engine.cpp`;
- `tests/core/audio/realtime_engine_test.cpp`;
- `tests/core/audio/realtime_engine_stress_test.cpp`;
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`;
- `apps/docs-site/diagrams/audio-runtime.architecture.json`;
- `apps/docs-site/static/diagrams/audio-runtime.svg` (official render);
- `apps/docs-site/static/diagrams/audio-runtime.html` (official render);
- `docs/plans/2026-10-10-pattern-switch-and-count-in.md`.

The opt-in retained method requires Engine running; an outstanding lease keeps
restart refused until its control owner releases it. Provide a move-only
serialized-control lease, acquired inside publication
admission before audio visibility and rolled back on a losing admission CAS.
Use the existing slot control-pin storage without changing Engine object layout
or adding work to render. Lease destruction/reset releases only its own pin;
Engine must outlive its leases and callers still own durable ACK policy. Read
matching actual apply metadata only after an acquire slot-state publication;
never use a queued frame or announced callback end as an Applied result. A
reclaimable slot without matching apply metadata proves exact cancellation;
a pending or in-flight canceled audio owner stays pending until its own release.
A later successor, stop/start or reclaim cannot turn an old ticket into a new
publication. Ordinary non-retained publication and transport epochs are unchanged.

Lowest checks: build and run existing `audio.realtime_engine` component and
`audio.realtime_spsc_stress` stress selections, with reduced lease/reclaim,
move/reset, cancellation/claim and delayed multi-switch tests in their existing
owners. Preserve every existing case and deadline. Exercise the existing
scheduled-material coexistence and concurrent audio/control reclamation; prove
a retained boundary survives successor/reclaim against a freshly rebuilt mutant
that omits its admission pin. The failure must be at that owning assertion.
No new CTest registration, CI control or required gate. Update current Portal
source diagram through the official renderer and run `scripts/docs-site.sh check`.

Version impact: required — additive Audio Runtime methods/types, preserving
existing public layouts and wire/Journal shapes, carry MINOR debt in #2237.
No identity allocation. Documentation impact: required —
`/core/modules/audio-runtime/` and its current source diagram describe the new
control-only lifetime/query capability; no S3 UI or durable continuation claimed.

C1 local results before shipping: all original/new `audio.realtime_engine` and
`audio.realtime_spsc_stress` cases pass (1.61/1.64 s). Seven reduced Native
scenarios include exact S distinct from queued prediction, delayed successor /
reclaim, fixed-slot pressure, move/reset/foreign owner, cancellation/claim,
admission rollback and original COUNT-IN receipt coexistence. The concurrent
case traverses 48 publications while audio renders and control queries/cancels/
reclaims, retaining the previous actual fact across each successor. Callback
allocator guards and every existing scenario remain enabled.

A rebuilt mutant omitting the admission pin fails the retained-boundary reclaim
assertion at `realtime_engine_test.cpp:8386` (exit -6), not a setup/build failure.
After a fresh-mtime restoration, the log recompiles the producer and both owning
selections pass again (1.36/1.62 s). The first diagram render rejects layout /
label/card constraints; correct only this source diagram to the existing grammar,
then official render and complete Portal check pass: 179 tests, 10 source/20
output diagrams, 50 routes/internal links. No validator or deadline is relaxed.
Complete native/sanitizer/coverage/Web/Creator/candidate and physical checks are
not claimed by these scoped C1 results; C2–C4 and S3's complete journey remain.

C1 shipping refresh: S7 #2359 is integrated as `6be17e78`; design #2361 is
integrated as `15ce56dfc2adbfdd0d1b2dc3909fa7c3b6493aa9`. Rebase C1 onto that
actual introducing main, preserving its complete patch by range-diff. Native,
Host, Facade and Journal premise sites remain byte-identical to inspected 4de2.
No successor delivers the missing recording continuation or Host gate. Refresh
Core configuration, rerun the owning component/stress and complete Portal check
on this base before the amended commit; the prior mutant/restore evidence is
retained. C2–C4 remain separate implementations, not implied by C1 integration.

On the actual design-squash base, refreshed Core configuration/build and both
owning selections pass again: component 1.75 s, stress 1.56 s. The complete
Portal check also passes again (179 tests, 50 routes/internal links). No Native,
test or Portal source bytes change during rebase; only this plan records the
new main/source dispositions. Final commit/PR review remain head-bound.

### S3 C2a — flush an already-checkpointed source prefix

Refreshed integration main is `61f877fe100ec48533243aa7efa5e40042636a5b`;
C1 #2362 is now actually merged and its complete tree matches the former stack
parent 52627901. Preserve the two owned WIP files byte-for-byte while moving to
that exact integration tree. C1 changes no Facade/Journal source. At this base `checkpoint_prefix` already persists a
candidate transfer with pending events/correlation checkpoint, and ordinary
source draining flushes a newly transferred prefix. But `drain_source_prefix`
returns immediately when no source candidate remains, or the new transfer has
no new input sequence. That skips an already-retained pending tail; Journal
`blocks_switch` correctly refuses reconciliation while those events remain.
The codec already supports one unreconciled boundary plus serial history: do
not change its grammar or reinterpret an empty candidate queue as no data.

This reduced prerequisite owns exactly:

- `packages/application-facade/src/pattern_admission_controller.cpp`;
- `tests/core/facade/pattern_admission_test.cpp`;
- `docs/plans/2026-10-10-pattern-switch-and-count-in.md`.

Drain any actual remaining pre-S prefix first, then read the same owner's
fresh Journal and flush its complete retained pending tail under the existing
stable flush identity, even if a prior checkpoint consumed every candidate.
Retain all original refusal/retry/manifest/fingerprint/revision checks and the
strict `[source_start,S)` partition. Do not invent a target press from a late
held release, append an empty flush, alter completed source Truth on retry, or
start a new transfer merely to recreate already-durable events.

Lowest verification: reduced OwnerFixture red tests before the fix; build/run
existing `facade.pattern_admission`, with far-side assertions for checkpoint,
source Truth flush, switch reconciliation, same-ID retry and a reconstructed
owner/Journal readback. Cover already-checkpointed held fallback and completed
release, plus a genuinely empty source. Preserve every existing assertion and
registration/deadline. Production I/O orchestration, multiple-boundary ingress,
Host wiring and complete S3 restart/stress/UI journeys remain C2b/C3/C4, not
claimed by this three-file prerequisite.

Version impact: required — internal Application Facade bug fix carries PATCH
debt in #2237, subsumed by any later higher debt for S3; no public layout/API,
Journal shape, identity allocation or current Product Assembly changes.
Documentation impact: none — this restores the existing source-prefix flush
contract within the private admission owner; current Portal product/source
boundaries and production recording-switch gate are unchanged.

The first rebuilt reduction passes the fresh-source positive control then fails
at checkpointed-hold source Truth (pattern_admission_test.cpp:1198), exit 8.
The Journal still retains the tail; no setup/compile failure is treated as the
bug. Also cover an excluded/unmatched release that yields no new input sequence
while an older checkpoint tail remains. Keep both cases under the same source
flush contract. Run existing Facade transport/controller integration plus
Sequence Journal component/stress (durable append, replay and recovery), in
addition to the admission owner component, before shipping this persistence fix.
No registration, budget, lock discipline or Journal grammar changes.

The five owning selections pass after the fix: admission 1.95 s, transport
1.72 s, controller integration 10.71 s, Sequence Journal 9.37 s and Journal stress
0.14 s. Before shipping, extend the same declared admission test with before-
append refusal and lost-after-durable-append response cases. Each must retain
the original source tail/error, reconstruct an owner, retry the same transfer /
flush identities exactly once, reconcile the target and settle/reopen unchanged
per-Pattern Truth. Re-run the affected admission selection; the other four
product/test input sets are unchanged. Complete production S3 remains separate.

Both new recovery cases pass after correcting one fixture premise: a lost
post-append response has already moved the complete tail into a pending flush,
not left it in pending_events. The initial failure at that assumption is kept;
the final test checks the complete canonical/recovery events, command/Pattern
identity and incomplete disposition in that pending flush. Before-append refusal
instead retains the full pending tail and no flush. Each reconstructed owner
then commits exactly once, reconciles, closes and reopens the same A/B Truth.
The affected admission component passes again in 2.24 s. The four other owning
selections remain input-identical to their preceding PASS. Fresh main is still
61f877fe; this Task changes only its declared three files. No new process pitfall
is introduced: the product contract is expressed by these regressions.

Pre-push source audit: the direct checkpoint-tail path must validate the exact
admission preparation identity as well as the Session. A later recording can
reuse the engagement Session with a new command/epoch; bypassing drain must not
let an older private owner flush that new recording's tail. Add a reduced
same-Session/new-preparation red test before tightening the three source-prefix
readbacks. Keep all files in the same declared Task; no public API/format or
new owner policy is introduced.

The rebuilt same-Session reduction reaches the actual stale-owner call and
fails its refusal assertion at pattern_admission_test.cpp:1335 (exit 8); an
initial fixture field spelling error was corrected before this red run and is
not counted as proof. Require the exact operation/runtime-generation/transport-
epoch identity on all three source-prefix readbacks, before processing retained
flushes or creating a flush from a checkpoint tail. Re-run all five owning
selections after this product change; prior results alone cannot verify it.

Final C2a owning results after exact-identity guards: admission component 2.28 s,
transport 1.68 s, controller integration 10.42 s, Sequence Journal 8.26 s and
Journal stress 0.14 s all PASS (22.78 s total). The stale owner rejects before
any new recording's Journal/Truth mutation; the actual owner can then use those
unspent command IDs. This final three-file input supersedes the earlier local
5435a91b freeze for shipping; no earlier receipt is silently reused for changed
product logic. No registration, CI control, deadline or recovery validation
changes. Source/Native production continuation and final S3 acceptance remain.

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

The [current-loop phase model](../design/2026-10-19-seq-snap-off-phase-model.md)
refines this into an actual application frame plus exact nonzero musical
numerator. The [P1 Task](2026-10-19-seq-snap-off-phase-anchor.md) adds only the
checked phase-mapping primitive: discard completed source loops before wrapping
to target length. It does not enable OFF publication, recording, Host/SDK or
Creator. Those follow-ups must retain actual per-publication anchors and settle
the outstanding target-note chase/concurrency questions before affected work.
The remaining work stays on the Draft stack. Under the owner's partial
unfreeze, independent verified layers may integrate to main after review;
COUNT-IN withdrawal and the release-path exclusions remain in force.

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

**Delivered.** S6 shipped in #2202 (squash `c7333602`, 2026-10-14). #2223
(`064cb30e`) corrected its terminal cleanup. Its working history (base
refreshes, interim failures, private diagnostics and the per-repair addenda)
stays in the Git history of this file and of #2202; it is not repeated here.

- **Audio Runtime.** The inline scheduled start runs the cue frames from `C`
  and starts playback exactly at `S`. Audio publishes settlement. A
  serialized-control settled query gates failed-ticket consumption while the
  callback still runs. The upstream continuous tempo clock is reset at the
  actual `S` start, so a scheduled restart matches a fresh ordinary start.
- **Application Facade.** The Journal opens only after the real Applied
  receipt at `S`. An opening decision is published under the owner's
  completion clock in one short critical section. Each new ordinary
  recording retires the previous cutoff observer before its fence, and
  failed Pattern preparations are retired. Shutdown with a retained ordinary
  preparation still reaches a real Stop.
- **Project I/O.** Control and the Journal worker share one writer custody
  across pthread realms. The Sequence parser reuses only a fully validated,
  byte-compared prefix. An optional `ProjectJournalLayoutValidator` companion
  keeps the storage-platform vtable unchanged.
- **Web Runtime Platform.**
  - Strict count-in request, inspect and cancel operations are added.
  - A negotiated Pattern input profile separates short admission from Native
    completion.
  - Pattern and Performance share one capacity of 64 physical gestures.
  - A recovery probe keeps its original epoch and deadline.
  - The first deadline's provenance is kept in diagnostics.
  - Fatal close and Creator replacement wait for genuine owner cleanup.
  - A failed legacy engagement still shuts down its worker.
- **Creator.** Physical Pad keys travel from App to the SDK. Sample
  preparation is separate from Pad completion. Performance Pads are reserved
  before ordered raw submission. Perform shutdown failures stay visible. An
  ordinary Pad observer timeout is non-fatal while the SDK is healthy.

**Decisions.**

- 2026-10-11, owner: the existing 5000 ms deadline bounds the first recording
  admission only. A retry keeps its original start; 4999 ms may open and
  5000 ms may not. Only a real successful durable completion before that
  boundary proves the take opened.
- 2026-10-13, user: Pattern and Performance recording share at most 64
  retained real Pad gestures. One physical press entering both domains
  takes one place, and a matching Release for an admitted gesture stays
  admissible at capacity. Keyless direct callers count independently.
- 2026-10-13, user: the BPM lock and the refusal when count-in cannot be
  provided are recorded under S7.
- 2026-10-14, owner: the one-second budget of an ordinary Pattern Press or
  Release, a legacy `trigger` input or a prepared Performance Pad event
  starts at its own admission turn. Earlier queue time is not charged; a
  recovery probe keeps its epoch start.
- 2026-10-14, owner: on the legacy `trigger` path, keyless Presses of one Pad
  hold one `slot:N` position, as on `main`. A new Press supersedes a settled
  one and a keyless Release frees it. The Pattern input profile keeps one
  position per keyless call.
- 2026-10-14, owner (#2223): a terminal owner that has not confirmed its
  release within the 5 s grace period is ended by force, as on `main`.
  When a claimed publication never settles, it is ended after one poll
  interval.

**Verification at merge.** On the #2202 branch after its `main` integration,
`scripts/creator-web.sh proof` passed (167 passed, 0 failed, 11 skipped), as
did Core `full` (259/259) and `stress` (17/17, including both count-in stress
tests). #2223 then made two
consecutive `scripts/web-runtime-host.sh proof` runs pass. `core_asan`,
`core_coverage`, `core_ubuntu`, `deploy_contract`, `package`, `web_runtime_lab`,
`web_toolchain` and `ci_contract` were left to CI. Physical devices and real
MIDI hardware were not exercised.

**Follow-ups.** #2190 (per-press `sample.inspect` latency), #2243 (Linux CI
contract failure). The #2202 slimming Tasks reduce its test and documentation
volume without dropping coverage.

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

### S3 C2b — durable continuation on the single I/O owner

Premise refresh before implementation: actual integration main is
`34f8f3535a499ab55ccf616742bf751dcfd76f6e`. #2361 design, #2362 Native
leases and #2363 source-tail/identity prerequisite are delivered and must not
be repeated. Live #2233 remains open and no open successor implements this
continuation. At this revision the private I/O owner only reconciles a switch
as part of terminal close; it has no ongoing segment operation or target
zero-origin timing profile. Existing codec already permits serial boundaries,
A→B→A generation-specific checkpoints, equal profile frontiers for segments
without input, and immutable duplicate records with actual durable replay.
Retain those formats and checks. `drain_target_segment` is a terminal helper:
using it for ongoing recording would prematurely flush a held target press.

This Task owns exactly these files:

- `packages/application-facade/src/pattern_admission_controller.hpp`;
- `packages/application-facade/src/pattern_admission_controller.cpp`;
- `packages/application-facade/src/pattern_transport_io_owner.cpp`;
- `packages/application-facade/CMakeLists.txt`;
- `tests/core/facade/pattern_transport_segment_test.cpp`;
- `apps/docs-site/docs/core/modules/application-facade.mdx`;
- `apps/docs-site/diagrams/application-facade.architecture.json`;
- `apps/docs-site/static/diagrams/application-facade.svg`;
- `apps/docs-site/static/diagrams/application-facade.html`;
- `docs/plans/2026-10-10-pattern-switch-and-count-in.md`.

Add one private `segment` work operation, binding the exact original recording
operation/runtime/epoch, actual copied Native Pattern/generation/S and BPM.
Restore only that same admission owner, durably retain S, drain/flush the old
segment, validate current Project identity/revision, reconcile the target,
and durably retain its zero-tick clock before admitting post-S input. Upper
control must park post-S input until this ACK; reject retroactive profiles or
already-transferred post-S source data. No Engine/lease/PCM crosses the work
payload. Exact immutable work IDs derive transfer/flush/profile identities;
unknown responses replay through the real writer, including readable duplicate
profiles and partial switch writes. Historical exact replay must not rewind a
later segment or rewrite Truth. Record-off/Stop still use actual final Pattern.

Lowest-tier verification: a dedicated `facade.pattern_transport_segment`
component registration (unchanged standard budget) exercises real I/O owner,
Store and Journal, A→B→A, held/released and empty segments, exact retries,
partial append/flush/switch/profile durability failures, reconstructed owner,
strict identity/revision refusal, terminal close and complete Truth/reopen.
Run it with existing admission/transport/controller and Journal integration/
stress tests; use an actual rebuilt perturbation to prove missing continuation
clock is caught. Run dependency/ownership checks and the complete Portal
check after official diagram generation. This adds product tests, not a CI
control-plane change or universal full-lane gate. Native ingress ordering,
Host opt-in, Creator packaged journey and physical acceptance remain separate
C2c/C3/C4 work; supplied Native authority in this reduction is not their proof.

#### Version Management

Version impact: Application Facade feature MINOR debt, including prior private
C2a PATCH, to be consolidated by #2237 without lowering existing higher debt.
No public class layout/vtable, Contract/Journal format or allocated identity
changes. No Product/Assembly allocation or snapshot in this Task.

#### Documentation impact

Documentation impact: required. Update `/core/modules/application-facade/`
and its owning source/generated diagram for the private durable segment
primitive and its still-unwired control/Host boundary. No claim of complete S3.


C2b recovery clarification from the first actual reduction: a reconstructed
I/O owner has no original positive opening-completion evidence. Its readable
fence does not authorize new live input; the first fixture lost its later
input as live-only and correctly failed the complete reopened revision (2
instead of 3). Preserve that negative run. Normal live A→B→A keeps the actual
live owner, while a separate reconstructed owner proves historical replay.
Durability faults are injected on the second boundary after B input is already
retained; reconstructed work settles that exact prefix and terminal close.
Explicit far-side checks assert retained=true on every live candidate and
retained=false/no Journal change after reconstruction. No fresh activation,
renewed opening deadline or inferred proof is introduced to make restart pass.

The revision reduction initially used an ordinary settings commit, which is
already allowed to rebase the active Sequence Journal; expecting refusal was
an incorrect fixture premise and the run failed. The corrected reduction
interrupts that actual rebase after the Project commit: Truth has advanced,
Journal has not, and continuation refuses without changing either. A pending
original source flush is handled separately: its canonical receipt may have
advanced Truth before its lost reply, so finish that exact flush through the
real writer, then enforce the fresh Project/Journal revision at reconciliation.

Final C2b local result: all six declared owning selections pass on the restored
producer plus final exact-identity readback guard (28.12 s total): Journal 8.24 s,
Journal stress 0.14 s, admission 2.28 s, new segment component 5.32 s, transport
1.68 s and controller integration 10.46 s. Original deadlines, registrations
and journeys remain; the separate segment component uses the unchanged 30 s
standard budget. The rebuilt omitted-clock perturbation fails at its actual
profile-count assertion (exit 8); fresh-mtime saved producer restoration is
confirmed compiled, with all six selections passing before the final guard
and again after it. Official diagram generation and complete Portal check pass
(179 tests, 50 routes/internal links), dependency check and ownership 76 pass.
The first PR declaration used the wrong route-field label and was rejected;
correcting it to the existing `Affected portal pages:` field passes the same
validator. No gate change, format relaxation or process pitfall was introduced.

Precommit main refresh remains `34f8f3535a499ab55ccf616742bf751dcfd76f6e`;
all applicable main governance bytes match the read instructions. Successor
search finds only the already delivered design, Native and checkpoint layers.
No successor supplies continuous I/O, control ingress or Host/Creator opt-in.
This component is ready for exact-head review, while C2c/C3/C4 and all complete
S3 candidate/physical acceptance remain explicitly outstanding.

Exact-head review 39095715368 (GLM, review 5561363042) asked about reconciling a
segment after terminal close removes its Journal. That interleaving violates
the existing single retained work-cell protocol: the coordinator never consumes
an unknown segment; executor submission of any later cutoff/close is busy while
the original cell remains. Add a real threaded executor/I/O-owner regression
on an actual lost durable profile reply. It asserts unknown/exact ticket,
close submission busy before and after positive reconciliation, original
consumption, actual cutoff and close/removal, stale old reconcile/step refusal,
worker shutdown and full reopened Source/empty Target Truth. This documents the
private owner's real lifecycle; it does not add unbounded cross-close history
or infer success from an absent Journal. No additional declared files needed.

The real executor regression passes; all six owning selections pass again
(28.19 s total, segment 4.90 s, controller 10.40 s). Source/Portal inputs beyond
that lifecycle comment, owning test and this report remain byte-identical to
the 179-test/50-route Portal check. Preserve the original reviewed head as a
recovery ref, amend this one Task's freeze, then obtain a new exact-head review.

Second exact-head review 39096027048 (DeepSeek, 5561381070) raised two
revision concerns. Reduce them before disposition:

- The generic `any incomplete source flush` exemption is too broad as a
  before-write guard. The real-API reduction checkpoints source, interrupts a
  settings rebase after its actual Project commit, then retains a canonical
  uncommitted stale flush. On the reviewed producer the normal rebase/close
  control passes, then the stale pending-flush case fails the full Journal
  unchanged assertion (exit 8): S was retained before the later flush refusal.
  Narrow mismatch admission to an actual exact persisted Sequence flush
  receipt matching Session/flush sequence/command/Pattern, original expected
  revision and complete canonical events, whose committed revision is the
  current Truth. Absence or unrelated revision refuses before retaining S.
  This lookup is identity evidence only: actual execute/durable completion
  still precedes the target clock ACK. All original manifest/response-loss
  reductions must remain green.
- The shared `reconcile_switch` concern assumes successful settings updates
  leave the Journal at its old revision. Current Store actually rebases it
  before returning success. A new positive regression asserts both revision 1,
  then exercises the existing terminal applied-switch close, Source and Target
  Truth, expected revision 3 and complete Store reopen. It passes even before
  the receipt fix. Preserve the old switched-close profile's retained closed
  Journal/no-terminal behavior as known remaining debt, rather than silently
  changing it in this Task. An interrupted rebase remains a real conflict;
  keep the strict check and document this distinction.

After exact receipt validation, all six original/new selections pass again:
27.67 s total, segment 5.17 s, controller 10.38 s, Journal 8.11 s, stress
0.14 s, admission 2.22 s and transport 1.64 s. No Portal/diagram input changed
from its complete passing check. Preserve reviewed 70c0b0fd before amending
this Task; refresh unchanged main and request a new exact-head review.

### S3 C2c — bounded control reservations and ordered segment delivery

Premise refresh before implementation: intended main and this worktree both
start at `b679b5f5453186d519f2a4f7225c5c4c8c68f3cd`. Live #2233 remains open;
no open successor supplies the control wiring. #2364 is actually integrated,
its ten files match verified 5bd1d452, and its exact-receipt/retry semantics
must not be repeated or relaxed. Native C1 retained leases/observations, the
single I/O `segment` primitive, original six transport journeys and S7 exact
caller/input protocols are positive controls. Missing at this revision:

- The public Pimpl controller has no bounded reservation/bind/observation/
  consume capability for recording switches. Native actual facts cannot feed
  ongoing I/O except terminal close. Add nonvirtual methods/types; existing
  public class layouts and port vtables stay frozen.
- `drive_inputs` writes every eligible original frame without a pending-switch
  barrier; `publish` can still project the old authoring Pattern. Park target
  input with its original ticket/frame until actual S and durable target clock.
- Existing Native Stop/F capture works while I/O is held. Keep it prompt, but
  order all retained S<F segment work before submitting epoch-F cutoff/close.
- Applied COUNT-IN keeps writing its original S0 into ordinary status origin.
  Keep its original receipts/identity; ordinary phase follows actual switch S.
- Source logical held metadata currently settles only at cutoff. A segment
  ACK must settle that old authoring obligation while Native physical holds,
  their real consumers and future release remain independently owned.

Declared files (fourteen, no wildcard; each extension below was declared before its edit):

- `packages/application-facade/include/lmdj/facade/pattern_transport_controller.hpp`;
- `packages/application-facade/src/pattern_transport_controller.hpp`;
- `packages/application-facade/src/pattern_transport_controller.cpp`;
- `packages/application-facade/src/pattern_transport_controller_factory.cpp`;
- `packages/application-facade/CMakeLists.txt`;
- `tests/core/facade/pattern_transport_switch_test.cpp`;
- `apps/docs-site/docs/core/modules/application-facade.mdx`;
- `apps/docs-site/diagrams/application-facade.architecture.json`;
- `apps/docs-site/static/diagrams/application-facade.svg`;
- `apps/docs-site/static/diagrams/application-facade.html`;
- `docs/plans/2026-10-10-pattern-switch-and-count-in.md`;
- `.agents/pitfalls/rspack-cache-stalls-corrected-mdx-build.md` (one factual recurrence, existing exit unchanged);
- `CMakeLists.txt` (register this product test binary in the existing coverage object inventory);
- `.agents/pitfalls/coverage-target-list-omits-new-test.md` (actual configure-gate recurrence, existing exit unchanged).

Reserve at most two typed records on serialized control before any Native
publication. Bind exact queued authority and prepared BPM, then accept actual
lease observations. A monotone ticket derives the stable internal work UUID
from the original recording operation/runtime/epoch; no new unbounded command
retry map and no meaning change to the wire's advisory request_id. An abandoned
reservation has no Native binding. Consumed tickets never bind again. Snapshot
preparation requires idle I/O and a target whose acknowledged prior notes can
be cooked from Truth: refuse before Native for returning/unsettled authoring
material. Host remains sole lease owner; no lease/Engine/PCM enters the worker.

An unresolved queued boundary parks input at its queued lower bound until real
Applied S or real cancelled disposition. Drain original pre-S candidates and
known Native outcomes first; retain actual boundaries in order, not latest-only
telemetry. Two may apply while I/O is held; the third is refused before audio.
Use #2364's original immutable segment work, then release only the source's
logical metadata. Target input stays active/live and enters recording only
after the exact durable ACK. Old-source projection cannot publish while a
reservation is unsettled, and a segment ACK invalidates chunks/availability
without reusing a projection generation. Actual S updates ordinary origin
without replacing original S0/e1/e2 COUNT-IN evidence.

Normal resource completion needs actual Native final disposition plus durable
segment ACK (or final cancellation with no segment). Host resets the real pin
and then consumes its ticket. A terminal segment refusal stays failed; explicit
shutdown obtains independent actual I/O owner_lost disposition before failed
switch resources can retire. Do not require Native scheduled quiescence for
that I/O disposition: it scans these same pins. Native consumers, physical hold
revocation and final quiescence remain separate Host obligations. Preserve
unknown work cells and original ingress/opening budgets; no timeout fabricates
completion, F, successful recording or absence of durable effects.

Lowest-tier owning verification: dedicated component and stress registrations
for real Native Engine + production controller + real worker/Store/Journal,
covering A→B→A, two retained Native boundaries during held I/O, third refusal,
pre-S/at-S/post-S input, held physical release, cancellation/claim, exact durable
retry, prompt F and S=F cancellation, COUNT-IN original receipts/new origin,
source overlay exclusion, failure/disposition/shutdown and complete Truth/
reopen. Use deterministic callback coordination rather than free-running frame
counts for musical assertions. Keep every far-side journey assertion. Existing
admission, transport/controller, segment, all count-in shards, Native Engine
component/stress and Journal component/stress retain their original budgets.
Run dependency/ownership, official diagram generation and complete Portal check.
A rebuilt removed-barrier/ordering perturbation must fail the owning source/
target assertion and the saved producer must be restored/recompiled. Full
candidate/sanitizer/coverage and complete S3 Host/Creator/physical acceptance
remain separate; no new CI gate or control-plane file is declared here.

#### Version Management

Version impact: Application Facade additive MINOR debt in #2237. New nonvirtual
Pimpl methods and standalone typed DTOs keep existing layouts/vtables, wire
Contracts and Journal grammar unchanged. Include prior Facade feature/PATCH
debt without reducing a higher domain impact. No Product/Assembly/manifest
allocation or snapshot.

#### Documentation impact

Documentation impact: required. Update `/core/modules/application-facade/`
and its source/official diagram for the bounded control/IO capability and its
still-unwired Host/Creator gates. Their integration remains C3/C4.

C2c verification refinements (same declared files): the existing Native test
library/seam is linked only to the native switch proof, so a quiescent callback
clock jump proves queued 24001 versus actual S=32000 with original source input
at 30000. C1 still produces the actual observation; neither a forged fact nor
a new product clock API is added. The source note at tick 1199 commits to A;
B begins at its real zero and later target input/reopen is asserted. Existing
product/Host links retain the ordinary Native library. The new stress
registration uses the unchanged standard stress budget: a bounded callback
request runs on a real audio thread while serialized control and actual I/O
settle 48 segments and 48 notes. Expected full A/B vectors use the independent
120-BPM/48-kHz scalar relation (one tick per 25 frames), not the admission
converter. Add a targeted native ASan run of this new component/stress pair to
catch lifetime errors during concurrent retirement/reclaim; this is a scoped
instrumented check, not a complete sanitizer/candidate lane.

Initial component evidence: 7 production-controller/Native/I/O journeys pass;
all 14 existing declared selections pass (55.53 s). The first fixture expected
zero active voices immediately at a positive release consumer; real voices
still render the canonical 96-frame declick. Retain that negative result and
render exactly `kRealtimeRampFrames` before the physical voice assertion.
The held-I/O Stop fixture also first read the ordinary F cell after its actual
consumer had already copied/acknowledged it. Move the Native-F assertion before
that real consumer, then assert the independent retained COUNT-IN receipt and
full authoring close afterward. Do not replace either leg or weaken a budget.
The next 9-case component and 48-segment stress pass (2.93/5.02 s); boundary,
legacy-DTO and own-overlay regressions are added before final freeze.

The Snapshot preparation guard is a control-turn contract: reserve, Facade
Snapshot preparation, Native publication and bind remain within one serialized
Host control turn, with abandon on preparation refusal. Do not insert separate
continuations/async preparation in that sequence, which could submit worker I/O
behind a synchronous History read. Public/Portal documentation now names this
existing serialization requirement explicitly; no new mutex, worker queue or
Product concurrency decision is introduced.

The rebuilt removed target-input barrier fails at the actual no-I/O-ticket
assertion (line 366), after Native B and its real input completion but before
S is delivered to control. Saved working producer bytes are restored with
fresh mtime, confirmed recompiled, and all 16 declared selections pass in
61.53 s. The scoped native ASan component/stress pair also passes (6.14/13.09 s,
19.24 s total). This is not the complete Core/sanitizer/candidate lane.
Official diagrams generate successfully. The first complete Portal build
rejects bare `S<F` as MDX JSX at line 164; escape the comparison as inline code
and retain that failed result before a complete corrected rerun.


After the MDX correction, the owned docusaurus PID 61995 remains at 0% CPU with
no bundling progress (1m22s observation, later stopped). Apply the existing
absorbed `rspack-cache-stalls-corrected-mdx-build` / issue-done procedure: stop
only that verified worktree process, preserve its ignored cache and failed
logs, and rerun the original complete check cold. The stopped run is not PASS.
The canonical pitfall ledger requires later occurrences even after absorption;
declare its record-only twelfth file before that edit, attributing this actual
occurrence to Codex/#2233. Its existing skill exit and escalation remain intact;
no CI workflow, gate, budget, routing or skill instruction changes.

C2c final precommit evidence: refreshed origin/main remains
`b679b5f5453186d519f2a4f7225c5c4c8c68f3cd`; live #2233 is OPEN with zero comments
and no open successor. The complete original cold Portal check exits 0:
179 tests, production build and 50 routes/internal links. The retained warm
stall and initial MDX failure remain negative evidence. Dependency verification
and all 76 ownership checks pass; the new staged test's ownership is checked
before commit. The pitfall frontmatter parses with exactly the three attributed
occurrences and unchanged absorbed skill exit. All declared product results
remain as recorded above; C3/C4, complete lanes and physical acceptance remain.

Premerge refresh advances main to `616b1db47d4331e534afd572ff708ed85d55fd61`.
Its #2367 fixes the older segment binary's missing root coverage registration;
#2368/#2369 preserve packaged fixture journeys and #2370 bounds sanitizer
worker overlap without reducing rounds/deadlines. Governance bytes remain
unchanged. Preserve original head `60024596` and rebase this clean Task onto
that actual main. The unchanged coverage configure gate now independently
rejects `lmdj_pattern_transport_switch_tests` as unlisted (exit 1); declare root
`CMakeLists.txt` as the thirteenth file before registering the new product test
binary in its actual registration order. This is owning build inventory, not
a new gate, lane/routing/threshold/control change. Re-run the original coverage
configure and new instrumented component, plus affected owning selections.
The original exact-head GLM review had zero inline findings; its two awareness
notes match explicit terminal failure and Native-origin/durable-ACK separation
contracts. A new exact-head review is required after this amendment.

The existing absorbed coverage-registration entry is also applicable: its
unchanged configure gate caught this exact new binary. Declare its factual
third recurrence before editing, attributed to Codex/PR #2365. Its existing
root CMake gate remains intact. Follow the entry's complete coverage procedure
before amended push; no coverage floor/exclusion is reduced. The initial targeted
instrumented component run is not a complete coverage report. No default
profile exists at this Task root on inspection. Use the stable coverage
script's scoped LLVM_PROFILE_FILE for the complete run and retain its actual
terminal result and floors.

Final amended verification: stable `scripts/core.sh coverage check` exits 0.
All 266 selected CTests pass (352.20 s), followed by the script's original
module/profile reconciliation and all unchanged floors: overall lines 87.02%,
branches 72.37%; Application Facade lines 86.10%, branches 71.41%. All seven
module floors pass. Root build-script tests pass 17/17; both factual pitfall
records parse with three attributed occurrences and unchanged absorbed exits.
The rebased original 16 owning selections pass again (64.74 s). Prior ASan,
mutation and complete Portal evidence remains as recorded; product producer
bytes/Portal source are unchanged by the inventory-only repair and rebase.
No additional CI control, threshold, budget or exemption is introduced.
