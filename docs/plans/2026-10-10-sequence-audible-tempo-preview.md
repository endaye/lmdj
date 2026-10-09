# Sequence: audible encoder tempo preview

## Outcome and authority

Close the BPM acceptance gap in the Creator Desktop Final follow-up Goal.
The owner has approved immediate preview, one authoring save/Undo after
400 ms idle, and cancellation of an uncommitted preview on page, Pad or Project
change, System, Escape, history navigation and loss of ownership. A numeric
readback alone does not meet that approval. Recording admission continues to
reject BPM changes.

The temporal behavior during playback needs one additional owner decision.
The 2026-10-02 tempo decision explicitly schedules a committed BPM at the next
bar and restarts the Pattern there. The new immediate-preview approval does
not specify whether a preview preserves the current musical position. On
2026-10-10, the owner was asked to choose continuous position-preserving
preview (recommended) or restart from the Pattern beginning on each change.
The recommendation below is a proposal, not an adopted decision. Do not
implement the dependent playback transition until the owner answers.

This plan covers source delivery and acceptance, not release or deployment.
It supplements, and does not reduce, the parent follow-up Goal.

## Refreshed premises

Integration base and this Task worktree base:
`50d79fa894f3483d6593d50fafcfd3e1bff28ce0`.
The consumer implementation inspected separately is
`f9e194544ee8406be9ab8eb79fb892346a1b42af`.

- **Still outstanding:** `app.tsx` keeps `tempoPreview` locally and sends
  `updateSequenceSettings` only on idle. Cancel clears only the local number.
  Existing browser cases inspect that number and committed history; they do
  not observe pre-commit Pattern timing or clicks.
- **Still outstanding:** the Web control/runtime session has an authoring
  settings operation but no reversible tempo-preview lifecycle. The Facade
  settings command persists Truth before updating a recording anchor; it
  cannot serve as a no-history preview.
- **Still outstanding, behavior-dependent:**
  `publish_pattern_view_preserving_phase` requires identical BPM. Its native
  regression expressly rejects changed BPM. Removing that check would weaken
  the existing grid-edit publication contract, and retaining only the old
  frame origin would not retain musical position at a different rate.
- **Available, reusable:** immutable Pattern preparation, the serialized
  control owner, publication generations, transport admission fences and
  `freeze_transport_bpm`. The freeze helper retains the exact tick numerator
  at a transition rather than rounding to a whole beat.
- **Already delivered, do not repeat:** the old direct-settings/metronome
  implementation, Sequence navigation, and #1905 refresh fix. Intervening
  main changes after `502932e` concern CI review-provider handling, not tempo.
- **Shipping dependency:** monitoring producer #1910 is still open. The
  page-encoder consumer is local and must eventually be based on the actual
  merged producers. An unmerged development stack is not main delivery.

## Proposed playback and lifecycle contract

Subject to the owner choosing continuous preview:

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
first implementation edit. This proposal does not approve a persisted Contract
change or alter record/replay semantics.

## Implementation Tasks

Each Task is one declared, independently reviewable commit. Start each with
fresh main and successor inspection; after actual files are confirmed, update
these declarations before editing. Do not count this plan as implementation.

### I2a — Runtime timing primitive

Declared files: this plan;
`packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`;
`packages/audio-runtime/src/prepared_sample_bank.cpp`;
`packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`;
`packages/audio-runtime/src/realtime_engine.cpp`;
`tests/core/audio/prepared_sample_bank_test.cpp`;
`tests/core/audio/realtime_engine_test.cpp`;
`tests/core/audio/realtime_engine_stress_test.cpp`;
`apps/docs-site/docs/core/modules/audio-runtime.mdx`.

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

### I2b — Facade/Web preview lifecycle

Declared files: this plan;
`packages/application-facade/include/lmdj/facade/application.hpp`;
`packages/application-facade/src/application.cpp`;
`tests/core/facade/sequence_surface_test.cpp`;
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
The additive Audio Runtime, Application Facade, Web Runtime Platform and
Creator changes will declare their actual MINOR debt and compatibility at
implementation, then settle with the parent V1 Task. No guessed Product Build,
Contract version, tag or release allocation.

## Planning Task verification

This planning Task declares only
`docs/plans/2026-10-10-sequence-audible-tempo-preview.md`.
Validate all declared source/test/page paths against this base, inspect the
proposal against the prior timing decision and the actual encoder lifecycle,
check whitespace, and run the staged new-file ownership suite. A plan review
must retain the unapproved playback boundary and the real audible acceptance
gap; it must not turn this proposal into a product decision.

## Documentation impact

Plan-only Documentation impact: none — this file records a proposal and
inspection; it changes no Architecture Portal page or source fact.
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
