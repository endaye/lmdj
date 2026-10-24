# Sample preparation storage-failure presentation

Parent: #2112. Owning Issue: #2229.
Integration and worktree base: `d244fdc3e9d00ca6c5b977a4d1109d823b78967c`.

## Premise audit

- Already delivered: #2448/#2450/#2451 and #2485–#2487 cover Retry-only,
  pending takeover, short recovery actions, manual Runtime recovery, actual
  release outcomes and recording-recovery reasons. Do not recreate them.
- Still outstanding: `normalizeSampleSnapshotError` uses the ordinary Sample
  operation catalogue. An accepted committed receipt with `IO_ERROR` only in
  `snapshotError` therefore says the sound could not be saved. Both
  `applySampleCommit` and `applySampleRetryPublication` consume that normalizer;
  their accepted saved revision is already authoritative. The ordinary
  `applySampleOperationFailure` is a separate path and must keep its existing
  unconfirmed-save wording. Existing COOK_FAILED tests are the positive control
  for the committed-failure path; all remain unchanged.
- Uncertain / excluded: the recovery strategy for non-COOK_FAILED publication
  errors is not decided. This Task adds no Retry Prepare eligibility, automatic
  retry, mutation replay or recovery policy. #2489's independently reproduced
  browser audio-clock stall remains a separate merge hold. No audio activation
  is required to establish this presentation defect.
- Follow-up premise from the real page: accepted mutation/retry publication
  receipts do not record their IO_ERROR snapshot error in Developer diagnostics.
  The new guidance therefore had no matching details. Add the existing report
  call when those accepted results settle; do not remove the diagnostic leg.

## Task and declared files

One presentation fix, one Conventional Commit:

- `apps/creator-web/src/state/error_messages.ts`
- `apps/creator-web/src/state/sample_state.ts`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/test/sample_state.test.ts`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `tests/platform/web/creator/creator_web_status.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-24-sample-preparation-failure-copy.md`

Use a catalogue message for a confirmed saved sound whose playback preparation
has a storage error. Point to existing Developer diagnostics without suggesting
an unavailable retry. Keep typed codes, privacy validation, Project Truth,
revision ownership, pending settlement and COOK_FAILED retry behavior.

## Verification

- Before fixing, run new reducer and mounted-App cases on the original source;
  require failure at the saved-outcome wording, retaining actual exits/logs.
- Reducer checks cover committed and retry-publication IO_ERROR independently;
  the existing operation-failure and COOK_FAILED cases remain positive controls.
- Mounted App: confirmed save -> truthful message -> diagnostic guidance;
  neither Retry Prepare nor a duplicate update is introduced. A rejected update
  retains ordinary save-failure copy and the unchanged revision.
- Real packaged page: import -> real Native Sample update -> reduced typed SDK
  publication-error receipt -> saved-outcome text -> System diagnostics -> back
  -> complete Project inspection, all 64 Sample inspections and asset inventory
  -> reload -> the same complete inspections/inventory. Project inspection
  omits Pad playback by design; it alone cannot prove a saved mute change.
  Bind every Sample to the new revision and an independent B03 mute-only delta.
  Retain the actual original Native response and the
  substituted response separately. This proves consumer handling, not a genuine
  Native storage failure. The two viewport cases use no audio activation and do
  not establish audio/backend/device acceptance. Keep the existing two complete
  Runtime recovery journeys and their original bounds.
- Complete Creator unit suite, TypeScript/build, official ordinary configure /
  build / package, Node syntax, staged and committed ownership, PR-body lint and
  declaration, and `scripts/docs-site.sh check`.
- Full candidate, genuine storage-failure producer proof, other #2229 states,
  non-COOK_FAILED recovery policy, #2237 version/snapshot and #1221 physical /
  Safari / listening acceptance remain explicit separate work.

## Version Management

Creator Host compatible PATCH debt, deduplicated into #2237's existing higher
same-domain debt. No manifest, Product Build, Assembly or snapshot allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Reason: distinguish saved Sample preparation failures from failed mutations.

## Pitfall Impact

Pitfall impact: none — product wording is derivable from its regression tests.
Use the existing complete-journey and path-attachment procedures; no new gate.
