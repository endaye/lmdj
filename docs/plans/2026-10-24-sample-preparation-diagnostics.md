# Sample preparation failure diagnostics

Relates to #2112 and #2229.

## Premise refresh

Base and worktree: `ce8f748142fa045359a532de5b97c54e7077e83b`.
The accepted Sample result paths in `dispatchResolution`, `performUpdate` and
`retryPrepare` report only `IO_ERROR`. The existing mounted storage-error test
is the positive control. Other typed `snapshotError` envelopes, including the
real Native `INVALID_PROJECT` produced and retained by #2493, do not enter
Developer diagnostics. SDK `snapshot.rejected` notifications refresh global
diagnostics without assigning their error to `lastErrorCode`; they cannot
compensate for the missing per-operation record.

#2490 already preserves the successful save outcome and storage-error wording.
#2493 already proves the real Native commit, explicit publication retry and
new-owner reopening, including full Truth and every file. Do not repeat or
claim a new producer fix. Remaining scope is the missing consumer diagnostic.

## Task and declared files

One Task, one Conventional Commit: record every accepted typed preparation
error using the existing reporter, after the existing owner guards. Preserve
accepted codes and allowed details, single commit counts, and current retry eligibility.

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `tests/platform/web/creator/creator_web_status.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-24-sample-preparation-diagnostics.md`

## Verification

The lowest defect oracle is a mounted App: edit, shared reset/import result,
and explicit Retry Prepare must record the accepted code/details exactly once.
Run a baseline failing regression before the product edit and retain it.
Check IO_ERROR as the existing positive control, INVALID_PROJECT as the actual
Native error class, and COOK_FAILED without changing its explicit retry.
Run the complete Creator unit suite, TypeScript/build, ownership and Portal
checks. Build and package through the ordinary Creator entry point from clean
committed source. Retain complete status journeys: real import, mute, saved
revision, System diagnostics, return, all 64 Sample readbacks, whole Truth and
asset identities, then reload with identical complete inventory.
The browser seam substitutes only the typed publication result after a genuine
Native successful commit. It proves consumer behavior, not a new genuine Wasm
storage failure or stale audio. Do not remove original journeys or weaken
assertions. Full candidate, physical devices and listening remain unverified.

## Version Management

Version impact: Creator defect fix (PATCH debt), absorbed by the existing
Creator MINOR floor tracked by #2237. No API, ABI, persisted contract or active
identity changes; final Product allocation belongs to the final delivery set.

## Documentation Impact

Documentation impact: required. Update `/hosts/creator-web/` to state that every
typed preparation error is retained with its operation/code/details. No new
recovery behavior or retry policy.

## Observed verification

The initial arbitrary test details were rejected by the existing protocol
validator; this is retained as a fixture-premise failure, not product RED.
After correcting the fixture to the existing allowed revision-detail shape,
the unchanged product failed 9 of 14 selected checks: missing non-IO records
and the initial COOK_FAILED record during an IO_ERROR retry. The five passing
checks include the IO_ERROR positive controls. The product fix then passed
all 16 selected checks, including the original successful retry branch.

A clean locked Creator install uses Vitest 4.1.12. The complete Creator unit
suite passes 87 files / 2081 tests; TypeScript and Vite build pass. Existing
CSS-parser, localStorage and bundle-chunk diagnostics remain visible.
Package and browser verification follow from the clean source commit; their
results are recorded in the PR rather than editing a verified source identity.
