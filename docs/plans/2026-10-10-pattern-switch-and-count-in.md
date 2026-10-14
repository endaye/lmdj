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
