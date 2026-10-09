# Creator mode-specific overview (#1920)

## Premises

Integration/worktree base: `0483967a6b67c7e071dc7f31ec56dc288f92a843`.
Read live #1920/#1921 and current source at this exact revision. #1917/#1918/
#1919/#1922 have merged delivery; #1923 is PR #1940 in committed-head proof.
No changes to those authoring contracts are authorized by this presentation Task.

- Outstanding: OverviewDisplay adds the selected Pattern number and BPM to
  every mode. Project/Sample identity must refer to their actual object, not
  that unrelated selected Pattern. Sound Sets/Slice also draw technical facts
  as their main screen. Keep all overviews read-only.
- Outstanding: SampleSurface repeats Pad/Asset ID/format at its top while
  SampleOverview already owns format/selection/waveform. Keep editing values
  and accessible notices in context; relocate technical identity to details.
- Outstanding: PerformSurface repeats launch cue, strip status and authority
  prose. PerformOverview currently receives only Pattern transport, while
  PerformController's immutable PerformState provides pendingLaunch and
  lastLaunchAck. Subscribe to that actual producer without connecting or
  leaving the controller from a read-only display, and distinguish pending
  from acknowledged; do not call a pending launch the current sound.
- Outstanding: SequenceOverview rows show only addresses. ProjectView.pads
  provides real category and occupancy, so add those, preserving colour,
  current-Pad highlights, eight-row geometry and full Pattern viewport.
- Honest fallback: LocalProjectSummary/ProjectView has projectId but no name
  or modified/saved timestamp. SampleInspect supplies metadata/Asset ID but
  no filename; ProjectPadView supplies category. Use short project identity,
  Pad addresses/category and explicit empty/loading/error labels. No Bundle
  parsing or invented NIGHT DRIVE/KICK names, bit depth, meters or timestamp.
  Local autosave policy is not an acknowledgement that every in-flight action
  is saved; show available pending/recovery/error states and avoid unqualified
  All changes saved when no aggregate save acknowledgement exists.
- Current PR #1936 is another owner's contextual encoder change. Its observed
  head b07e178dfd1c73c654697317aae71cd0f31ade42 overlaps app, overview, Sample,
  Perform, styles and manuals and removes swing encoder preview. Read its
  merged result before final integration; keep its worktree untouched and
  preserve encoder readbacks/physical semantics. Do not treat its open code
  as delivered main or redo its bindings.

## Figma and reuse

Refreshed high-fidelity context and screenshots from Desktop Final D01
`88:1682`, D02 `88:819`, D03 `88:2005`, D04 `88:2502`. Upper display is
752×176 with 16px inset, compact primary identity/status, 8px content gaps,
IBM Plex Mono and existing Graphite tokens. Project has three columns;
Sample has format/selection and the actual waveform; Sequence uses 128px
track labels and eight 10px lanes; Perform shows current/pending and progress.
Use existing overview components, live waveform and Pattern playhead rather
than the pictured waveform SVG, demo data or unimplemented output meters.
The waveform is runtime-supplied imagery; no new static asset is required.
Existing hardware/icon assets are outside this Task and remain unchanged.

## Task and declared files

One Task: mode-specific read-only identity/feedback and removal of duplicate
non-editing content. Preserve transport, authoring, cancellation, failure,
recovery, Undo/Redo and reopen journeys. #1921 owns live draft synchronization.

Declared files (refine before editing a newly discovered dependency):
- apps/creator-web/src/components/creator_details.tsx
- apps/creator-web/src/components/overview_display.tsx
- apps/creator-web/src/components/project_overview.tsx
- apps/creator-web/src/components/sample_overview.tsx
- apps/creator-web/src/components/sequence_overview.tsx
- apps/creator-web/src/components/perform_overview.tsx
- apps/creator-web/src/components/perform_surface.tsx
- apps/creator-web/src/components/sample_surface.tsx
- apps/creator-web/src/state/overview_context.ts (pure public-projection labels)
- apps/creator-web/src/app.tsx (read-only Perform producer wiring/details)
- apps/creator-web/src/styles.css
- apps/creator-web/test/audio_lifecycle.test.tsx (relocated full Sample identity)
- apps/creator-web/test/sequence_grid_edit.test.tsx (track address and content)
- apps/creator-web/test/project_overview.test.tsx (bounded error and pending rows)
- apps/creator-web/test/project_create.test.tsx
- apps/creator-web/test/overview_context.test.ts
- apps/creator-web/test/sample_overview.test.tsx
- apps/creator-web/test/perform_overview.test.tsx
- apps/creator-web/test/sequence_pattern_overview.test.tsx
- apps/creator-web/test/workspace_shell.test.tsx
- apps/creator-web/test/perform_surface.test.tsx
- tests/platform/web/creator/fixtures/perform_helpers.mjs (relocated Sample metadata)
- tests/platform/web/creator/fixtures/creator_navigation.mjs (details navigation)
- tests/platform/web/creator/creator_web_lifecycle.spec.mjs (relocated Sample identity)
- tests/platform/web/creator/fixtures/creator_boot.mjs (current Project identity readback)
- tests/platform/web/creator/creator_web_capture.spec.mjs (relocated detail selector)
- tests/platform/web/creator/creator_web_browser.spec.mjs (relocated detail selector)
- tests/platform/web/creator/creator_web_hardware_layout.spec.mjs
- tests/platform/web/creator/creator_web_perform.spec.mjs
- tests/platform/web/creator/creator_web_sample_editor.spec.mjs
- apps/docs-site/docs/hosts/creator-web.mdx
- apps/docs-site/docs/hosts/creator-interactions.mdx
- docs/design/2026-09-29-creator-user-workflow-guide.md
- This plan.

## Verification

Baseline Sample/Perform overview suites: 6 tests passed; there are no separate
project_overview or overview_display test files. Their actual consumers are
workspace_shell/hardware_console; run those rather than treating unmatched
Vitest filters as coverage. Sequence uses sequence_pattern_overview.test.tsx.

Add meaningful producer-to-consumer checks: opened Project vs selected card,
selected Pad/category/empty/loading/error, selected Pattern/track category,
Performance queued→acknowledged/cancel/failure/session reset. No pending cue
may overwrite acknowledged current identity. Preserve AT status and local
control highlights. Recheck rendered top-display bounds at multiple viewports,
including long/error/empty text and all eight rows, no interactive descendants.
Run complete affected packaged journeys plus committed-head Creator batch,
portal check, ownership preflight and independent current-head review.
Physical iPad/Safari/touch/listening remains unverified in existing issues.

## Version Management

Version impact: none — read-only Creator projection/presentation; no schema,
Core, Contract, Product Build or Assembly identity change.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/
Update object identity, launch feedback and details locations with code.

## Pitfall Impact

Pitfall impact: none at premise stage. Apply native-event, complete-journey,
current-premise and retained-proof guidance; do not weaken tests or infer
pending producer state from an unrelated transport.

## Implementation and Task verification

Precommit premise refresh: `origin/main` remains
`414268d654adeae32dfb500f62c000f06e4f2b47`; #1940 delivered Sound Set steps.
Its changes affect independent Sound Set styling/navigation and manual sections,
not these overview producers. The initial worktree base was
`0483967a6b67c7e071dc7f31ec56dc288f92a843`; integration rebases this Task onto
`414268d654adeae32dfb500f62c000f06e4f2b47`. The sole conflict is the Sound Set
manual table: retain #1940 Browse/focus behavior and this Task’s System-detail
location. Sound Set source, styles and navigation helpers are all retained.
#1936 remains open at
`b07e178dfd1c73c654697317aae71cd0f31ade42`; its other-owner work is untouched.

Implemented all presentation scope: mode-specific object identity, real Pad
categories and empty states, observable Project storage policy/status, stale-Pad
inspection guard, shared Perform pending/ack subscription and consolidated
launch prose. Technical Project/build facts are reachable in System details;
full Sample Asset ID/source/revision in Pad details. The retained pure System
projection preserves its disclosure without mounting Provider subscriptions
while closed. Test-only revision probes can inspect it without interrupting a
live gesture; the hardware journey separately opens it and proves visibility.

Verification before commit:

- `npm --prefix apps/creator-web test -- --run`: 1,173 passed in 68 files;
  then the newly added Project overview suite passed 3/3. Tests cover actual
  identity/category, empty/loading/pending/error, qualified saved/audio-pending
  status, current-vs-queued producer transitions and bounded error rows.
- `npm --prefix apps/creator-web run build`: TypeScript and production Vite
  build passed after the final test additions.
- Source UI with verified #1930 Runtime: Sample 9 passed/1 expected Chromium
  capability skip; Perform 13 passed, including recording→queued/acknowledged
  launch→flush→stop→WAV export→save→replace→reopen→replay→empty-Pad master
  capture, owner-loss recovery, durable WAV failure prefixes, FX/pan/tone.
- Hardware/layout 5 passed: four main modes at 1440×900, 1280×600 and 768×600;
  text ranges and scroll geometry fit the readonly upper display. Cross-Bank
  Pad identity, loading, failed commit, successful recovery, delete→empty,
  Undo→assigned, visible System full identity and persisted reopen all have
  far-side assertions. Injected latency/failure proves Creator handling only,
  not physical storage/device failure. Project Truth is unchanged on refusal.
- Full-page Project, Sample, Sequence and Perform screenshots inspected. Sample
  header is compact; technical facts remain accessible through real details.
- `scripts/docs-site.sh check`: passed, 50 routes/internal links valid.
- React review: derived labels stay pure, external store snapshots retain the
  controller's immutable identity, read-only subscription never connects/leaves
  a session, no new effect mirrors state or owns authoring behavior.

Failure history is retained under `/tmp/lmdj-ui-goal-20261009/1920-*` and
unique browser result slots. Obsolete metadata selectors were migrated by
opening the new details and returning to the prior editing page, retaining
full identity/format/count and all later assertions. The Perform witness
helper now completes the source-selection dialog before leaving Sample and
asserts the imported stereo format: its old mono 4,800-frame check matched
the previous fixture before replacement. Full master-output proofs pass with
the real imported witness. No timeout or coverage threshold was widened and
no journey leg removed. A one-shot inspect refusal was not a stable Sample
mutation-failure witness; the layout proof explicitly holds inspect for the
loading state and rejects `sample.update_pad` for the existing typed failure
path, then verifies unchanged Truth and successful recovery.

After integrating #1940, TypeScript/Vite build passed, the complete component
suite passed 1,182 tests in 69 files, and the portal passed all 50 routes and
internal links. These checks include the combined Sound Set/overview tree.

## Shipping and acceptance boundary

Implementation and Task-specific checks are complete. Staged ownership,
committed-head full Creator lane, independent current-head review and guarded
merge remain required. Record their final evidence in the PR and live Issue;
this source proof is not packaged or release acceptance. Real Safari/iPad touch,
MIDI and listening remain in #248/#365/#721/#1854/#1221. #1921 retains live
trim/Tempo/Swing drafts, #1924 shared visual polish and #1925 broader status/
recovery consolidation. This Task neither releases nor deploys the Creator.


### Follow-up Task: cross-Pad pending feedback

Self-review after the initial commit found that an in-flight mutation can retain
its original slot while selection moves to another Pad. An unqualified UPDATING
would label the new Pad incorrectly. Scope is the already-declared
`sample_overview.tsx`, its component test, hardware proof, Creator portal page
and this plan. Name the pending action's real Pad when it differs; describe the
unscoped last-error producer as CHECK LAST ACTION rather than attributing it to
the current selection. No producer, mutation ownership or recovery semantics
change. A red component proof first reports UPDATING instead of UPDATING PAD
A03; the final native proof must also fit the longer qualified failure label.
The first committed-head lane was intentionally stopped during compilation;
retain its log as incomplete, not a pass. Rerun on the new committed input.
Version impact: none; Documentation impact: required, /hosts/creator-web/.

Follow-up verification: focused Sample overview 9/9; TypeScript/Vite build;
native Chromium hardware/layout journey 5/5 (25.8 s), including the longer
CHECK LAST ACTION text; portal 50 routes and internal links all passed.
Precommit refresh remains main `414268d654adeae32dfb500f62c000f06e4f2b47`;
no intervening successor changed these premises. Logs: `1920-cross-pad-*`
and `1920-hardware-source-7.log` in the retained Goal evidence directory.


### Follow-up Task: complete Sequence row identity oracles

The committed-head complete Creator proof completed with three failed browser
journeys: Sequence view/Pad navigation, recording and persisted grid reopen,
and row/Tempo/Swing encoders. Each stopped on the former address-only row label
(`A01` versus the actual `A01 / SAMPLE`). The source proof subset had not run
these complete Sequence files. Preserve their entire navigation, Truth/history,
recording, encoder and reopen legs; update the full expected row label, including
SAMPLE for the authoritative fixture's 64 explicitly assigned, uncategorized
Pads. Do not replace exact text matching with a substring or drop the row check.

Declare two additional files for this follow-up:
- tests/platform/web/creator/creator_web_sequence.spec.mjs
- tests/platform/web/creator/creator_web_sequence_grid.spec.mjs

The only other declared file is this plan. No product behavior changes.
Run both full Sequence specs, then rerun the complete Creator lane on the new
commit. Retain `1920-final-batch.log` and its per-invocation traces as failed;
it supplies no batch pass key. Version impact: none. Documentation impact:
none for this test-only follow-up; the parent Task's portal impact remains.

Both complete Sequence specs now pass: 11/11 in 2.8 minutes, including all
recording, history, view-only navigation, encoder and persisted reopen legs
(`1920-sequence-source-final.log`). Precommit main remains
`414268d654adeae32dfb500f62c000f06e4f2b47`; no successor changed the premise.
The earlier complete lane passed 1183 components, 83 other general browser
tests, Catalog 4, Sample 9, capture 8 and explicit denied/capability boundaries;
three old row-text expectations failed. Those successes do not replace the
required complete rerun on this test correction.
