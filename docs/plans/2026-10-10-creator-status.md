# Creator status and recovery presentation (#1925)

## Premises

Integration/worktree base: `414268d654adeae32dfb500f62c000f06e4f2b47`.
Read live #1925 and its complete comments. #1917/#1919 are delivered;
#1920 PR #1942 is awaiting review with its full Creator lane passing.
Integrate its actual merged result and #1921 before final verification.
#1936 remains another owner's open work; do not alter its bindings or worktree.

At this revision app inserts independent default-seed error, retry and
saved-unavailable messages above each workspace. Existing per-Pad phases and
controller retry/publication paths provide the truthful summary source.
Pad recording Save/Discard is already global and reachable in System: retain
that property. Perform stays mounted under System but its recording controls
are hidden; make the active recording and direct return to review discoverable
without creating another controller lifecycle owner.
Sequence SETUP normally shows Refresh authority. Its existing failure and
publication paths remain reachable with user-facing wording; keep an explicit
manual refresh inside details for deliberate diagnostic/recovery use.
Perform still exposes revision/open gesture/WAV binding details routinely.
Project's literal Stage 10 paragraph has only a dedicated hidden styling use;
remove that confirmed obsolete prose, preserving assistive statuses and hidden
mounts that retain capture/recording state.

## Task and declared files

One Task: concise truthful status with visible recovery/recording ownership.
No persistence, Core, Contract, DSP, controller lifecycle or mapping changes.

- apps/creator-web/src/app.tsx
- apps/creator-web/src/components/default_sounds_status.tsx
- apps/creator-web/src/components/sequence_touch_workspace.tsx
- apps/creator-web/src/components/perform_surface.tsx
- apps/creator-web/src/components/project_surface.tsx
- apps/creator-web/src/styles.css
- apps/creator-web/test/default_sounds_status.test.tsx
- apps/creator-web/test/sequence_surface.test.tsx
- apps/creator-web/test/perform_surface.test.tsx
- apps/creator-web/test/workspace_shell.test.tsx
- apps/creator-web/test/project_create.test.tsx
- apps/creator-web/test/shell_polish.test.tsx
- tests/platform/web/creator/creator_web_default_streaming.spec.mjs
- tests/platform/web/creator/creator_web_perform.spec.mjs
- tests/platform/web/creator/creator_web_system.spec.mjs
- tests/platform/web/creator/creator_web_sample_editor.spec.mjs
  (open Sample playback details while retaining exact saved/runtime revisions)
- apps/docs-site/docs/hosts/creator-web.mdx
- this plan

## Verification

Lowest-layer regressions cover mixed seed phases, retry/prepare result, normal
versus failed refresh, retained AT status, stopped/active recording across
System and return to review, and removal of confirmed obsolete prose.
Run complete affected browser journeys, not just their prefix: default loading,
failure/retry, capture stop/save/discard, recovery, persistence/reopen and actual
rendered bounds. Keep skipped physical Safari/iPad/microphone/listening explicit.
TypeScript/Vite, portal routes/links, staged new-file ownership and the final
committed-head Creator lane are required for this scope. No weakened tests.

## Version Management

Version impact: none — Host presentation over existing operations; no schema,
Core/Contract, Product Build or Assembly identity changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Update visible status, details, recovery and recording-return locations.

## Pitfall Impact

Pitfall impact: none anticipated — product presentation/lifecycle regressions
are directly expressed by tests. Retain complete-journey and integration-build
procedures; reevaluate if a process invariant is discovered.

## Integration and geometry refresh — 2026-10-10

Main advanced to `ec15f9adf3ca7c3fd09c06d61b53e0bcdf189fe6` with #1942
merged. Its overview/detail changes must be retained together with #1921
before final packaged verification. Status grouping, System navigation and
recording return remain outside that merged scope.

A real Chromium mixed loading/failure fixture exposed the status summary
sharing one row with Retry while System details wrapped below it. There were
exactly two action buttons (not an extra Prepare action). Keep the summary on
its own row so its length cannot split the recovery actions. The failed
three-viewport same-row/nonoverlap proof is retained in
`1925-status-geometry-final-2.log`; reverify the unchanged geometry assertions
after correcting the flex basis. No horizontal overflow was observed.

## Source verification before integration

- Final component suite: 1173 passed in 68 files, including mixed default
  phases, failed preparation followed by retry, System Pad Save/Discard and
  Performance review routing. TypeScript/Vite passed after the row fix.
- Complete default-streaming + System native journeys: 2 passed (21.1 seconds)
  in `1925-status-row-proof.log`. At 1440x900, 1280x600 and 768x600,
  actual recovery buttons share a row without overlapping and both touch
  workspace and document fit horizontally. The journey retains first native
  touch playback, one failed asset, retry, all 16 ready, saved Project reload
  and manual Project non-seeding, with exact request/blob assertions.
- Complete Sample file: 9 passed, one WebKit-only capability skip. The exact
  saved/runtime revision assertions remain, now reached through details.
- Portal check passed all 50 routes and internal links. Manual System
  inspection at 768x600 showed diagnostics use the parent touch scroll
  (no nested diagnostics overflow); its long content remains accessible.
- Evidence is under `/tmp/lmdj-ui-goal-20261009/1925-*`. Source UI uses the
  separately verified packaged Runtime. This is not final integrated
  committed-head proof or physical iPad/Safari/audio acceptance.
- Refreshed main remains ec15f9ad; #1921 is now PR #1946 at c72c6f74.
  Integrate both overview/live-preview changes before final packaged proof.

- Final Perform source proof passed all 13 journeys (2.9 minutes), including
  System direct stop -> Takes review -> visible Save/Discard, persisted WAV
  bytes, bind retry, owner loss/crash recovery, replay and empty-Pad capture.
  `1925-perform-final-source.log` ran without product edits during execution.
- New-file ownership passed 77 tests after all three new files were staged.
  Precommit main ec15f9ad and other-owner #1936 b07e178d remain unchanged.
- Manual screenshot `1925-manual-artifacts/output/playwright/1925-status-row-top-768.png`
  shows the actual compact two-action status in System; measured touch width
  and scrollWidth both 353 CSS pixels. Design-unit 44px action height scales
  with the console and is not claimed as 44 physical/CSS pixels on iPad.

## Integration with overview and live previews

Locally rebased on #1946 head `c72c6f7479c04e0a87a20ae13584e20c6f2ffceb`,
which includes merged #1942. Only conflicts were appended Sequence tests and
portal sections; both sides are preserved. Source status changes merge without
removing overview metadata or live-draft ownership. This is an unpublished
stack: wait for #1946's actual merge, then transplant only this Task before
publishing its PR. No other owner's branch or worktree was changed.

Integration verification: TypeScript/Vite passed; 240 affected component
tests passed in six files; portal rebuild passed 50 routes and internal links.
Complete integrated Default/System/Perform/Sample native reproof is running
with unchanged product sources. Retained pre-integration native evidence and
these conflict checks support the local rebase; final packaged proof and
independent review remain mandatory before shipping.

## Final parent refresh — 2026-10-10

PR #1946 is merged at `4281d5f54dd01ad73c18e876c2119a35b0229e0b`;
#1921 is accepted. Rebased only this unpublished Task onto that actual merge.
The whole resulting tree equals the previously verified `77c045e5` tree
(`789a54290957acff21927350703876d6175dad33`), before this evidence update.
The intervening main change is exclusively live-preview ownership/display;
it does not implement compact loading/recovery/status presentation. All five
#1925 premises remain outstanding on main. #1936 is still open at its recorded
b07e178d head; no other worktree or mapping was changed.

The integrated native Default/System/Perform/Sample run completed successfully:
24 passed, one WebKit-only capability skip, 5.0 minutes, with every full file
retained (`1925-integrated-source.log`). This supplements the 240 affected
component tests, TypeScript/Vite and 50-route portal pass already recorded.
Only this plan changes after those proofs; product and acceptance source bytes
are unchanged. Final committed-head Creator batch and independent review are
still required before merge.
