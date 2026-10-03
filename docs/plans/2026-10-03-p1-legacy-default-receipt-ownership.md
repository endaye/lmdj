# P1 legacy default receipt ownership

## Problem

R20 admission correction distinguishes new queued requests from actual
issuance, but an old journal can lack assignment history. If an older Host
already observed assignment and Undo before upgrade, the current Pad is empty.
The old unknown stale command must not acquire ownership by rebasing simply
because the new Host did not observe the old edit. A real recognized receipt
must still replay with its original command identity and expected revision.

## Task and declared files

Work on `fix/p1-legacy-default-receipt-ownership`, based on
`a33c229b21504ab109090fc991cc1edb6152b6c5`:

- `apps/creator-web/src/runtime/default_seed_controller.ts`
- `apps/creator-web/test/default_seed_controller.test.ts`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-03-p1-legacy-default-receipt-ownership.md`

New actual admission persists `assignmentObserved: false` together with the
request before Facade dispatch. A recognized Native receipt remains replayable
for every accepted old journal. Only after Native refuses an unknown stale
command, explicit false permits revision rebasing; absent or observed history
retires that reservation. This is a conservative Host ownership correction,
not a new Core receipt rule or an attempt to reconstruct unknown old Truth.
Existing old journals remain readable. Failed journal writes still send no
command, and Ready/retired ownership remains terminal across reload.

## Verification

The old-journal reload regression first executes against unchanged parent
Controller Source and must fail at installed1 versus0 after an unknown stale
refusal and rebase. The repaired Controller must preserve the same strict
counter/Truth/identity/reload assertions. A separate regression requires a
newly admitted request to persist explicit false, rebase once after another
Pad's edit, keep its command ID, install once and retain both Pad assignments.
Keep all prior known-receipt recovery, Undo, queued cancellation and failed
storage assertions. These lower cases use actual Controller and bounded
Facade doubles; they do not claim a Native/browser reproduction.

Run both complete seed suites, full Creator unit suite serially with original
budgets, TypeScript/Vite, Platform tests, staged ownership, whitespace and full
portal check before commit. On the committed clean composition rederive all
input keys and run full newly changed Creator and Runtime obligations; Deploy
can reuse only its real committed producer with exact unchanged input key and
raw proof. Current-head independent review must assess both the old unknown
request refusal and genuine receipt replay. No timeout, floor, selected lane,
journey leg or collector threshold changes.

## Version Management

Version impact: none. This pending P1 Host correction changes no public
Contract, Core API, journal key or version identity and allocates no Product
Build. Existing coordinated P1 version settlement remains separate.

Documentation impact: required.
Affected portal pages: /hosts/creator-web
The current Host page records absent legacy history, known receipt recovery,
and the explicit unobserved ownership needed for safe rebase.

## Acceptance boundary

The parent Source correction and whole-lane results keep their real heads and
original failures. This correction neither accepts physical device behavior
nor initiates release, deployment, promotion, Issue closeout or cleanup.
