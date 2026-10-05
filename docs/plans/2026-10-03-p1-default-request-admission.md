# P1 default request authoring admission

## Problem

Independent T5 review R20 reproduced automatic default installation after a
manual Pad assignment and Undo. The Controller persisted a command identity
before the Host acquired its Project authoring token. A busy or queued Host
could therefore return without issuing a Facade command, while the retained
request prevented the observer from retiring the reservation. On a stale
revision refusal, the Controller rebased that unissued request into a new
installation.

## Task and declared files

One correction Task on `fix/p1-default-request-admission`, based on T5
`18acdf1cde105415acce0afb8d07af20c2da856a`:

- `apps/creator-web/src/runtime/default_seed_controller.ts`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/state/default_seed.ts`
- `apps/creator-web/test/default_seed_controller.test.ts`
- `apps/creator-web/test/default_seed.test.ts`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-03-p1-default-request-admission.md`

The Host invokes synchronous admission after obtaining its existing Project
action token and immediately before `installSoundSetSlot`. Admission verifies
Project ownership, cancellation, retirement and the target empty Pad, then
persists the command identity. A queued candidate has no receipt ownership.
Journal write failure prevents Facade dispatch. Retired reservations stop
before retrying or leaving a queued callback.

A retained request may already have committed with its response lost. Preserve
its identity so Native can replay the receipt. Persist an optional
`assignmentObserved` boolean when authoritative Truth shows an assignment
while that receipt is unresolved. A subsequent `REVISION_CONFLICT` means the
old command is not recognized: this assignment history forbids rebasing even
after Undo empties the Pad. A recognized receipt remains recoverable without
another mutation. The existing journal format accepts older entries without
the optional field and rejects malformed markers without overwriting them.
This changes no Core, Facade or cross-language Contract.

## Verification

Lowest-tier verification runs both default seed test files. Three controlled
regressions first execute against the unchanged parent implementation and
must fail at `installed === 0`: busy admission, queued admission, and an old
journal request across assignment and Undo. The fixed implementation must pass
these same assertions, retain retirement across reopen, and preserve known
receipt recovery without changing Truth. Additional journal tests cover
assignment history across reload, older entries, invalid markers, and refusal
before Facade dispatch on journal write failure. These use Controller and
Facade DTO doubles; they do not claim Native browser or physical acceptance.

Before commit, run the complete Creator unit suite serially with its original
test budgets, TypeScript/Vite build, Platform unit suite, staged path ownership
suite, whitespace check, and `scripts/docs-site.sh check`. After composition
into T5 and its dependent Tasks, rederive every lane input key from the clean
committed head and run the complete newly changed Creator lane. Preserve
original failed runs and current independent review boundaries. No timeout,
coverage floor, selected lane or acceptance journey leg changes.

## Version Management

Version impact: none. This Task corrects pending P1 Host behavior and an
internal callback before release; it allocates no Product Build and changes no
public Contract. P1's existing coordinated Host version settlement remains a
separate integration Task.

## Documentation impact

Documentation impact: required.
Affected portal pages: /hosts/creator-web
Update the current Host page with authoring admission, queued retirement,
journal failure and old-receipt recovery behavior in this same Task.

## Acceptance boundary

The correction remains dependent on complete committed-head Creator proof,
current-head independent review, and guarded integration. Safari/iPad, MIDI,
actual microphone and audible output acceptance remain separate P1 obligations.
No release, deployment, promotion, Issue closeout or cleanup is initiated.
The defect is product logic fully expressed by its regressions; no process
pitfall entry is needed.
