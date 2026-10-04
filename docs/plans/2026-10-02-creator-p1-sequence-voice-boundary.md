# P1 Sequence proof: rendered notes before the terminal fence

## Scope

The complete Creator proof on 516f7c9fa8494698538d574c9be8cede916e03c2 failed two recording journeys: two successful live trigger responses preceded Record-off, but Truth contained one event. Preserve the original exit, logs and traces. A read-only diagnostic passed both journeys; this does not establish the original failure's cause or replace a complete proof.

The settled admission rule makes candidates stamped at or after terminal cutoff F live-only (`docs/superpowers/specs/2026-09-12-pattern-admission-storage-design.md`, Admission and cutoff rules). A successful enqueue/journal response alone cannot establish that a note rendered before F. Strengthen the existing journey to require the matching native VoiceStarted for every successfully admitted press before Record-off. Keep every exact event, revision, command identity, navigation, failure/retry and reopen assertion. Do not change Runtime timing, cutoff semantics, budgets, timeouts or the selected lane set.

## Declared files

- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `docs/plans/2026-10-02-creator-p1-sequence-voice-boundary.md`

## Task verification

Run JavaScript syntax validation, the complete packaged Sequence spec against the unchanged committed product artifact, and staged ownership tests. The added far-side assertion catches a queue acknowledgement being mistaken for a rendered live note before the recording cutoff. Retain the full original failure and the diagnostic's narrower scope. Rebuild the proof test in a fresh Playwright process after any mutation/restore, preserving the failing assertion and its actual exit. After commit derive the clean own-tree lane plan and run each changed complete obligation; identical input keys may reuse authenticated complete evidence. Independent current-head review and the shipping gates remain required.

The product artifact and Application behavior are unchanged by this Task. The original full-run failure cause remains unproven until the complete proof and boundary evidence establish it. No new runtime Contract or concurrency decision is introduced.

## Version Management

Version impact: none. This Task strengthens packaged acceptance assertions and changes no Product, Host, Module, Provider or Contract identity. The coordinated P1 version Task remains separate.

Documentation impact: none
Reason: No Architecture Portal source fact or product behavior changes; the two declared files document and strengthen test evidence only.

## Pitfall disposition

The admission/cutoff rule is derivable from the existing source and settled design. The strengthened journey is its verification; no new process pitfall is introduced.
