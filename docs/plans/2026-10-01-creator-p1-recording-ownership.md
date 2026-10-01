# P1 integration: recording and default-seed ownership

## Scope and declared files

Retire a default download reservation when Project Truth shows an independently
assigned Pad and the seed has never issued an install. Preserve receipt replay
for issued requests and permanent retirement across Undo. A late download must
not reclaim that retired Pad. Pattern playback may continue during Capture;
show the Capture trim dialog on Sequence without a Pattern recording journal.
Pause default Project installation while Capture holds recording or an unresolved
take, retaining download concurrency outside the Project mutation queue.

Declared files: `apps/creator-web/src/app.tsx`,
`apps/creator-web/src/runtime/default_seed_controller.ts`,
`apps/creator-web/test/default_seed_controller.test.ts`,
`apps/docs-site/docs/hosts/creator-web.mdx`,
`docs/plans/2026-10-01-creator-p1-default-streaming.md`,
`docs/plans/2026-10-01-creator-p1-pad-capture.md`, and this plan.

## Verification

Lowest-tier: Creator components and TypeScript, plus portal source-fact check.
The new unit cases fix manual assignment/Undo retirement and a late acquisition
result. Existing receipt-replay coverage must remain green. Rebuild the packaged
candidate and retain the native Pad delete/Undo/Redo/reopen and Capture over
Pattern playback journeys; component results alone are not their acceptance.

## Version Management

Version impact: Creator Host PATCH and a new Product Build, settled in the
following version Task before building or allocating the test candidate. Retain
the already frozen historical candidate unchanged.

Documentation impact: required
Affected portal pages: /hosts/creator-web/.
Reason: default reservation retirement and Capture installation ownership are
current Host behavior.
