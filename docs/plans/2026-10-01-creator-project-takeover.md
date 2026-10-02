# Creator P4.2：在另一标签页接管已打开的工程（#1679）

## Outcome and authority

A second Creator tab that is refused with `PROJECT_BUSY` offers **Continue
here**. Taking over asks the tab that holds the Project to hand it over; the
holder releases its writer and shows that the Project continued elsewhere,
with its own **Continue here** to take it back. Authority: the 2026-09-29
workflow decision §10 and design §9.1, and the 2026-09-30 Undo/Redo semantics
(the new owner starts with an empty history; the old one can no longer write or
undo). Baseline: `44783c2d` on an isolated `feat/1679-tab-takeover` worktree.
The Task includes verified commit, push, current-head review and squash merge;
it does not release or clean worktrees. Multi-device collaboration is out of
scope.

## Behavior

- The writer lease is an exclusive OPFS `FileSystemSyncAccessHandle` that no
  other context can steal, and the formal Web Host design keeps "no wait, no
  steal, no stale timeout" for the lease itself. Takeover is therefore
  cooperative and lives entirely in the Creator Host: the holder releases
  through its existing close path, then the requester opens normally. No Host
  operation, Facade capability, lease semantics or Contract changes.
- Tabs coordinate over a same-origin `BroadcastChannel`
  (`lmdj.creator.project-takeover.v1`) with strictly validated messages:
  `request` → `accepted` | `refused`, then `released {clean}`. Messages are
  matched by a random request id and Project id; anything else is ignored.
- **Holder.** Only a tab whose Runtime is ready and whose Project is open
  answers, and only for that Project id. It treats a takeover as a Project
  change and applies the same guard that already decides whether it may open
  another Project (no Project action, transfer, pending Sample action, running
  audio or capture). If the guard refuses, it answers `refused` and nothing
  changes. Otherwise it claims the Project action lane, answers `accepted`,
  and closes its Runtime through the same barrier as `pagehide`: registered
  shutdown barriers (Performance saves), then `host.close` (transport shutdown
  barrier, import abort, history close, lease release). It answers `released`
  with whether that close completed cleanly, and shows "This Project is open
  in another tab" with Continue here; its controls are unavailable because its
  Runtime is closed.
- **Requester.** Continue here is offered on a busy open (boot reopen, library
  open, duplicate open). While waiting it shows that it is asking, with
  Cancel. On `released`, on a holder that accepted but did not finish within
  its bound, or on no answer (the holder may be gone, frozen, an older Creator,
  or a non-Creator Host), it opens the Project once; a still-busy open shows
  the busy refusal again with a note naming the outcome. `refused` keeps the
  busy refusal with a note to finish playback, recording or saving in the
  other tab. Cancel stops waiting; a holder that already accepted still
  completes its release.
- **Taking it back.** The old tab's Continue here asks the current holder the
  same way, then starts a fresh Runtime that reopens the retained Project.
- **Writes.** Every acknowledged write is committed by the holder before its
  writer is released, and the requester only reads Project Truth through a
  fresh open, so nothing is lost or replayed. An in-flight import is aborted by
  `host.close` rather than half-applied; an interrupted recording follows the
  existing Journal recovery, as on tab close. The guard prevents both in the
  normal path.

## Declared files

- `apps/creator-web/src/runtime/project_takeover.ts` (coordinator and message
  validation) with `test/project_takeover.test.ts`.
- `apps/creator-web/src/runtime/runtime_context.tsx`: `yieldRuntime()` closes the
  current Session behind its barriers and reports a clean close; covered in
  `test/runtime_context.test.tsx`.
- `apps/creator-web/src/app.tsx`, `src/main.tsx`,
  `src/components/error_panel.tsx`, `src/components/takeover_panel.tsx`,
  `src/styles.css`; Workspace holder/requester behavior in
  `test/project_takeover_workspace.test.tsx`.
- Packaged two-tab journey `tests/platform/web/creator/creator_web_takeover.spec.mjs`.
- `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`: its Runtime
  generation probe counts every `BroadcastChannel` as Session-owned; the
  page-lifetime takeover channel is excluded by its exact name, so the
  Session's own channels stay accounted for.
- Portal page `/hosts/creator-web/`; this plan.

## Verification

Coordinator facts: valid exchange, refusal, no answer, accepted-but-unfinished,
cancel before and after acceptance, foreign or malformed messages, a second
request while one is handled, and a holder that keeps releasing after
unsubscribing. Runtime facts: yield runs barriers before close, reports the
close result, and is not overridden by later host-state events. Workspace
facts: the holder refuses under the Project-change guard and releases
otherwise; the requester opens after release and shows each outcome note.

The packaged journey uses two pages of one browser context (shared OPFS):
holder opens and commits an edit → second page is refused busy → Continue
here → holder shows taken over → second page shows the holder's committed
edit and commits its own → holder Continue here → second page shows taken
over → holder reopens with the second page's edit → reload reopens the same
persisted Truth. A holder that refuses (audio running) is exercised as a
component fact; frozen-tab, device-lifecycle and physical listening
acceptance are not inferred from browser automation.

Run Creator unit/component tests and TypeScript, the Creator browser proof,
`scripts/docs-site.sh check`, new-file ownership, and every classified
batch-only lane before merge. No timeout, coverage floor, lane or journey leg
is relaxed.

## Version Management

Version impact: additive Creator Host capability; it owes a MINOR change at the
next coordinated Creator parity version settlement. This feature Task preserves
manifests and Assembly identities, following the ongoing parity feature/cut
split. No Core Module, Provider or Contract identity changes; the takeover
channel is Creator-internal and not a Contract.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Document the takeover exchange, holder guard and released state. The Host →
Facade dependency topology is unchanged, so no diagram changes.
