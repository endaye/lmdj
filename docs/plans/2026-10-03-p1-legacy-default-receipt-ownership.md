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
command, revision rebasing requires both explicit false and actual admission
by the current live Controller. A restored false marker describes only its old
owner; it cannot prove no assignment occurred while that owner was absent.
Restored, absent or observed history retires an unknown stale reservation.
This is a conservative Host ownership correction,
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


## Current offline and slot dependency reconciliation

Protected Main is `1e7540c5a3c8707100b659bdb8886ad5ac9a7d4f`.
Import the reviewed current T4 dependency
`f3171a3f0f343ff8b7e8f9b072c163d98e907e11`, including reviewed T2ebf,
while preserving the complete original T5 default-streaming and R20 receipt
ownership implementation. Neither dependency is yet a merged Main delivery.
T5 shipping follows actual T2 then T4 merges and fresh Main policy, conflict,
conversation, protection, exact-head review and batch evidence checks.

The real merge has no textual conflict. The automatic dependency/Main import inventory and this plan are
the declared reconciliation files, frozen before the real merge. Review the
actual automatic App/InputController/test combinations: preserve first-gesture
wake and R14 native/compatibility dedup, simultaneous default download state,
real Host admission ownership, conservative unknown legacy assignments and
known receipt replay without resurrecting a touched Pad. Retain the Native
Sequence held/reopen/key-up/min-tail and render-before-record-off assertions,
all lifecycle budgets and the six-member forwarding interface from T4/Main.

Before the single reconciliation commit, run complete Creator components and
TypeScript, scope ownership and original Platform Node tests. Verify the full
imported Core tree is exact T4 and retain its actual200/200 fast proof; the T5
relative behavior delta is Host/default Product wiring rather than a new Core
implementation. Run complete official Portal validation with legitimate exact
tree and ordered ancestry. Commit first, reclassify the complete range, and
run every selected batch-only obligation on the current committed inputs.
Literal input-key equality is required for any retained passing producer; an
old record is not permission to reuse a changed key. Keep real prior negatives
and setup refusals. Independently review the whole new Source and verification;
old0535 owner adoption remains historical.

Version impact: none for this reconciliation. Import existing Main2.0.80.0 and
Module/Host/Provider identities exactly. Coordinated P1 version debt and Creator
offline Host MAJOR/formal offline acceptance remain T8, with no Build allocated.

Documentation impact: required. `/hosts/creator-web/` retains default streaming
and its real authorization/status context together with the imported current
Module/platform routes and offline diagrams. Immutable Main snapshot inventory
is retained. Actual Safari/iPad/MIDI/audible mic/master acceptance, release,
deployment and Channel promotion are not established by this Task.

## R21 owner-loss history correction

Independent frozen-tree review reproduced a new admitted request persisting
`assignmentObserved: false`, losing its owner before a recognizable Native
receipt, and restoring after another writer assigned then Undid the target.
The old Controller rebased that unknown stale request from revision0 to2 and
installed default material. The real App can persist admission before the
Runtime's serialized Facade action runs; durable false is not a receipt or
proof of continuous observation. Preserve the original independent RED and
the author regression's installed1 versus0 failure.

Declare these same Task-owned files in addition to the complete dependency
import inventory: `apps/creator-web/src/runtime/default_seed_controller.ts`,
`apps/creator-web/test/default_seed_controller.test.ts`, this plan, and
`apps/docs-site/docs/hosts/creator-web.mdx`. Keep the new-admission command IDs
only in the current Controller's memory, after successful journal persistence.
On Native's unknown-stale refusal, require this live admission before rebasing.
Do not change the journal schema, original command ID, Native receipt rules,
four download workers, trial budget or terminal ownership states.

Run the strict owner-loss/assignment/Undo/reload refusal regression and its
known-receipt replay counterpart, both complete seed suites, full Creator
components, TypeScript, Platform and ownership checks, and complete official
Portal validation. Retain the live-owner other-Pad rebase and all old receipt
and cancellation assertions. Source/lower DTO doubles are not Native/browser
or physical proof. The old frozen composition's lower passes do not cover
this corrected tree; its Portal ENOSPC failure remains recorded.

Version impact: none; no identity, public Contract or journal schema change.
Documentation impact: required. `/hosts/creator-web/` now describes restored
false as historical and limits unknown-stale rebase to a continuous live owner.
