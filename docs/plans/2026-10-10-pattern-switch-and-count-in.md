# Pattern 播放中切换（SEQ SNAP）与 count-in 实施计划（#1958、#1959）

## Outcome and authority

Patterns switch while the global transport plays and records, at the SEQ SNAP boundary, and Perform Pattern Launch works without a Performance recording. Record from stopped can count in with the metronome first.

The product decisions are:

- [`2026-10-10-pattern-switch-while-playing.md`](../prd/decisions/2026-10-10-pattern-switch-while-playing.md) (#1958);
- [`2026-10-10-record-key-and-count-in.md`](../prd/decisions/2026-10-10-record-key-and-count-in.md) (#1959).

The plan ships as seven Tasks. Each Task is one Conventional Commit on its own short-lived branch, with verified commit, push, current-head review and squash merge. No Task releases, allocates a Product Build or cleans worktrees. An implementation Task may be drafted by a delegated coding agent; the shipping agent rebuilds and reruns every listed test itself before committing.

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

- `pattern.transport.switch` takes `snap: "beat" | "bar" | "pattern_end"`, defaulting to `"bar"`. The Host computes the activation frame from the transport origin with the engine's own Bar and loop maths, so the boundary matches the engine's clock.
- Creator adds a SEQ SNAP segment (1 BEAT, 1 BAR, SEQ END) in SETUP next to QUANTIZE. The preference is stored in `lmdj.creator.host` / `settings` / `seq-snap.v1`, defaults to 1 BAR, and is read at boot like `metronome.v1`. It does not enter Project Truth.

**Declared files.** S1's Host files plus `apps/creator-web/src/state/seq_snap_preference.ts` (new), `app.tsx`, `sequence_touch_workspace.tsx`, their tests, and the two Creator portal pages.

**Lowest-tier tests.** Host: each snap lands on its frame, including SEQ END on a 2-bar Pattern. Creator: the preference round-trips and the request carries the snap.

## S5 — SEQ SNAP OFF

OFF needs the engine to start a different Pattern at the current phase. S5 adds that publish mode to `audio-runtime` with its engine tests, exposes `snap: "off"` in the Host, and adds the option in Creator. It is last because it is the only Task that changes the audio thread's apply path.

## S6 — scheduled transport start for count-in (Core)

S6 starts with a design addendum that decides how Record from stopped starts exactly at the count-in end frame.

- The likely shape is a future start frame on `PatternTransportCommand`, applied as the origin, with the engine silent before it.
- The decision says no Journal is open during count-in, and cancelling writes nothing. If the Facade cannot meet that without opening the Journal at request time, the addendum raises an erratum to the decision for the owner instead of choosing silently.
- Cancel before the start frame returns to stopped with nothing written.
- Inspect reports `count_in {start_frame, bars}`, so Creator can schedule clicks before the origin.

Expected owners: `realtime_engine.cpp` and header, `pattern_transport_controller.cpp`, `control_runtime.cpp`, and their tests.

## S7 — count-in in Creator

**Behaviour.**

- SETUP gains COUNT-IN Off / 1 / 2 next to METRONOME, stored as `lmdj.creator.host` / `settings` / `count-in.v1`, default Off.
- When ● starts from stopped with count-in on, Creator requests the scheduled start. The metronome clicks for the count-in bars regardless of its toggle, then follows the toggle.
- The upper screen shows COUNT-IN and the beats left. The Record lamp blinks during count-in and is steady once recording.
- ● or Play/Stop during count-in cancels.

**Declared files.** `app.tsx`, `src/state/count_in_preference.ts` (new), `src/runtime/metronome_scheduler.ts`, `sequence_touch_workspace.tsx`, `physical_controls.tsx`, `styles.css`, `components/transport_status.ts`, the overview components, their tests, `tests/platform/web/creator/creator_web_metronome.spec.mjs`, and the two Creator portal pages.

**Gate defect caught.** A count-in that records early hits, or a cancel that leaves the transport playing.

## Known gaps outside this plan

- **Bar maths.** The engine repeats one rounded Bar (`origin + n × bar_frames`). Sequence, Performance and the Creator metronome round each boundary separately. At BPMs where a Bar is not a whole number of frames, a switch boundary and a metronome downbeat can differ by a frame per Bar. [#1973](https://github.com/endaye/lmdj/issues/1973) tracks it.
- **Performance launch clock.** A launch during a Performance recording targets the Performance clock's Bar, which is anchored at Performance begin rather than at the transport origin. [#1974](https://github.com/endaye/lmdj/issues/1974) tracks aligning it with SEQ SNAP.

## Verification

Each Task runs its listed tests and every batch-only lane it selects (`scripts/local-ci.sh --list`), and records pass keys in its Pull Request. S1, S3, S5 and S6 select the Core and Web Runtime lanes; S2, S4 and S7 select creator and portal.

## Version Management

Version impact: none in this plan Pull Request (documentation only). The implementation Tasks owe MINOR bumps at the next coordinated version settlement:

- S1, S4: `web-runtime-platform`;
- S2, S7: `creator-web`;
- S3: `application-facade`, `project-io`, `web-runtime-platform`;
- S5: `audio-runtime`, `web-runtime-platform`;
- S6: `audio-runtime`, `application-facade`, `web-runtime-platform`.

No Contract SemVer change is expected: SEQ SNAP and count-in are device preferences, and switching does not change the Pattern shape. S3 and S6 re-check this in their addenda. No Product Build or Assembly change in these Tasks.

## Documentation Impact

This plan Pull Request: none. It adds a plan under `docs/plans/`; no portal page describes it as implemented. S1, S3, S5 and S6 update `/platform/web-runtime/` and the affected module pages. S2, S4 and S7 update `/hosts/creator-web/` and `/hosts/creator-interactions/`.

## Pitfall Impact

None expected. Each Task searches open entries labelled with its `area:*` before shipping. S2 and S7 read `synthetic-event-omits-platform-side-effects` and `acceptance-journey-truncation` before writing browser journeys.
