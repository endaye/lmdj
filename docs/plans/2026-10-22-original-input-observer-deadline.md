# Preserve the original Pattern input observer deadline (#2465 / #2112)

## Current premises and authority

Task branch `fix/original-input-observer-deadline`, isolated worktree. Stack base
`9b5160fdb40b38e39fb53ef1a59742158647ea76` is PR2466, still independently reviewed;
integration main is `84136533c3d1575084b4b4667e905b1a183fa237`. SDK source is byte
identical at both revisions. Refresh parent/main and this disposition before
commit and merge. Rebase only an unpublished child if parent integration changes
its ancestry; never force published history or merge an intermediate stack head.
The owner authorizes continued2112 Tasks and guarded ordinary integration;
frozen workflow/release paths remain excluded. No subagents.

Live2465 is OPEN, with original actual timings and both full OPFS outcomes.
The SDK observer still directly rejects its timer callback without rechecking
the monotonic clock. An actual held-append Release rejected after999.9699999988079ms
under an unchanged >=1000ms assertion; the same clean-source full repeat passed.
This is a pre-existing observer issue, separate from post-close preparation and
beat-1/first-click timing. Do not erase the failed candidate or relax its test.

## Exact declared scope

1. This plan: `docs/plans/2026-10-22-original-input-observer-deadline.md`.
2. `packages/web-runtime-platform/web/runtime_session.mjs`.
3. `packages/web-runtime-platform/test/runtime_session.test.mjs`.

## Feedback loop and acceptance

Run the unchanged complete SDK test file first. Add a minimal deterministic
existing SDK fixture: admit the actual modeled Pattern input, keep its durable
completion pending, and invoke the real observer timer callback while its
injected monotonic clock is still before the original1000ms deadline. It must
remain pending, then expire at the original deadline. Capture the parent red
before changing the product callback. Do not fake a new request or consumer.

If confirmed, recheck/re-arm only the remaining original budget. Keep late
admission and late completion guards, accepted physical/input identity and
independent durable consume/release. Assert early completion can still succeed,
late completion remains timeout even if a timer task is delayed, and no expiry
restarts1000ms. Complete all owning SDK tests and unchanged official3-journey
Wasm/OPFS proof from a clean committed candidate. The original1000/5000ms
assertions, all Journal/Artifact bytes and whole Truth/cold-reopen legs remain.
No full Creator, device or subjective-audio acceptance is inferred.

## Version Management

Version impact: Web Runtime Platform PATCH, absorbed by any higher same-domain
debt in2237. Restore the existing deadline invariant; no API/ABI, wire,
persistence, Product/Assembly/Build or manifest allocation.

## Documentation Impact

Documentation impact: none
Reason: restore the existing documented deadline and owner invariant. No public
operation, owner boundary, portal identity or design policy changes. Reassess if
the actual fix expands that scope. This Task does not edit current Portal pages.


## Executed diagnosis and fix

Unchanged complete SDK baseline:453/453 PASS1.934s. The new test, against the
unchanged observer source, invokes its genuine timer callback at999.97ms after
an admission which already spent250.25ms. It fails0.146s at the independent
assertion that the original accepted observer must remain pending, with the
actual HOST_TIMEOUT/pending:true from observePatternInputDeadline.
This distinguishes an early wake from a later fixture start or a different
clock; callback wake alone was incorrectly treated as deadline evidence.

Recheck the same monotonic original startedAt on every callback and re-arm only
its remaining duration. Neither the logical1000ms deadline nor the completion
branch changes. Completion cancels the latest re-armed handle. Three independent
cases retain early completion at999.99ms, real expiry at1000ms, and late completion
at1000ms while its timer task is delayed; late truthful consumption never turns
the expired observer into success. Every case settles the original consumer and
correlated physical Release exactly once before closing.

The first green candidate's new cleanup assertion found only Release consumed:
the test closed before the expired observer's independent5ms poll could settle.
Keep the assertion, wait on the actual original consumer with the fixture's
existing bounded task-drain style, then close. Do not fake a consumed ticket or
change the product to satisfy this harness cleanup.

Pitfall impact: none — a product callback defect fully expressed by the new
regression. Both original real browser candidates/attachments remain retained;
no environment-correlation closure, overwritten run or relaxed timer assertion.


## Source checkpoint verification

Complete final SDK registration456/456 PASS1.996s,0 skipped/cancelled. Staged
new-path ownership77/77 PASS9.709s. Main premise refresh still84136533; parent
PR2466 head remains9b5160fd and its independent review remains unavailable after
two backend failures. This child is local until its actual stack/base can be
reviewed safely. Official unchanged Wasm/OPFS composition runs after the clean
source checkpoint; bind its exact-head receipt in the resulting PR. None of
these Task results clears the parent's failed full Host TSan check or broader
2112 candidate/device debt.
