# Creator transport reconciliation follows current state

## Premises

Base: `d77a471de81b39cefdbb56d440c54f877736b208`.
The Creator captures `transportRef.current` before awaiting inspection, then
reduces the observation against that captured state to decide retry. This can
retain/reissue a Stop which the live reducer has already settled. It can also
apply a late observation to a replacement Project/session. Current main retains
this behavior; #1950 fixes native replay authorization, not this consumer.
A deterministic reducer counterexample demonstrates the stale retry on frozen
65b, whose relevant reducer and reconciliation algorithm remain on this base.

The first repair (`f1d17ba328ba1f9ea4713e4d281414d9f11cf0af`)
guards the initial observation, but its retained-command retry still awaits
submission and inspection without rechecking ownership. Main at the base above
also retains both unguarded awaits. This remains part of the same consumer
defect: a replaced owner must receive neither old retry status nor old errors.
Complete those guards in a separate worktree while the first repair's full
proof continues on its unchanged source; its results cannot verify new inputs.

The frozen 65b full browser proof still failed its original Pattern-switch
journey. An isolated observational copy passed; its per-window log did not
survive final reopen. A subsequent controlled delivery diagnostic blocked the
shared SDK host-request tail before reload and hit the original 240 s bound.
That diagnostic is not reproduction of the original old-Stop failure. Preserve
all failures, source/fixture identities and acceptance gaps; this Task repairs
the independently demonstrated stale-state defect and does not claim that a
focused result closes the whole browser or intermittent Host failure.

## T1

Declared files:

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/runtime/pattern_transport_actions.ts`
- `apps/creator-web/test/pattern_transport_actions.test.ts`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `docs/plans/2026-10-10-creator-transport-current-observation.md`

Extract the awaited observation and local reducer projection into a journey
helper. Read current state after the await and bind it to the same Project and
transport session before returning an observation. The app uses that projection
for retry, and rejects results/errors from replaced Runtime instances. Genuine
same-context failed/unknown commands retain their original identity; transient
retry bounds, payloads, native authorization and concurrency policy remain.
Check ownership before retry submission, between submission and inspection,
and after inspection, including failures. The app also checks its current
Runtime/Project/session before dispatching a helper result or reporting errors.
Before reporting a retry failure, also require its identity to be the current
pending command, or the retained failed command when no operation is pending.
A settled old command must not clear a newer pending command in the same owner.

Lowest-tier proof: deferred inspection crosses actual reducer settlement and
session replacement. The old extracted algorithm must fail the settled-Stop
assertion. The corrected helper must preserve a genuinely unknown request and
ignore stale status/error for a replaced owner.
Deferred retry submissions and inspections must likewise ignore a replacement
owner, skip inspection after ownership loss during submission, and preserve
the current owner's failures. Run the complete transport
state/action groups, TypeScript and the complete Creator component suite with
existing timeouts. Retain actual red/green output and source identities.
Mount the actual App for the same-owner late-failure regression: settle an old
unknown Stop through a second observation, request a new Record, then fail the
old retry's inspection. The new command remains pending and the controls remain
disabled. Genuine errors of the current unresolved command still surface and
retain its identity.

After staging the new plan, run the required ownership suite; commit one Task,
classify the clean committed range, run its full selected Creator batch lane,
record exact input-bound evidence and require independent current-head review
and guarded squash merge. Full four-encoder integration, audible BPM preview,
manual acceptance and other Goal obligations remain in the parent plan and
[acceptance ledger](../quality/2026-10-09-creator-desktop-followup-acceptance.md).
No new platform seam, required gate, widened timeout or shortened journey.

## Version Management

Creator Host PATCH debt: fixes existing observation/retry behavior. Settle with
other Goal changes in V1; this Task allocates no Product Build or identity.

## Documentation Impact

Documentation impact: none
Reason: restores existing ownership/retry behavior without changing the public
surface or Architecture Portal facts; the plan records verification and gaps.

## Pitfall Impact

Pitfall impact: none — product-state defect expressed by its regression cases;
existing complete-journey and exact-source procedures apply.

## Verification snapshot

Precommit refreshed main: `d77a471de81b39cefdbb56d440c54f877736b208`; relevant producer/consumer and shipping
policies are unchanged from this Task base. The extracted original algorithm
failed three deferred-observation assertions (13 others passed). The repaired
transport state/action group passed 16 tests in 0.701 s; an additional
current-owner error case is included in the complete component suite. All
70 files / 1209 component tests passed in 46.80 s with the original 20 s
per-case bound. TypeScript passed; final staged ownership and committed full
Creator proof remain separate boundaries. No browser root-cause closure or
manual acceptance is claimed by these component results.

Revision 2: refreshed integration main is
`c673399178197565fb68d15be79aa61e62dd913b`. The intervening #1971 is the
owner's SEQ SNAP decision; it changes no transport source or shipping policy.
Its playback/recording Pattern-switch implementation remains separate work.
The unguarded retry algorithm failed five of 24 deferred transport cases at
their own assertions. The corrected final transport group passed 26 cases;
the final complete component suite passed all 70 files / 1218 cases in
107.45 s with unchanged inputs and the original per-case bound.

The first repair's unchanged full browser run failed the Pattern-switch
journey again. Its retained native request log contains a newly generated
Record command at epoch 1, refused with INVALID_ARGUMENT after an accepted
epoch 3 Stop; the old Stop was not reissued in this run. This is evidence of a
remaining failure, not browser closure or proof of its exact native cause.
Tone-recording and BPM-commit cases also failed in that full run. Retain their
original bounds, traces and far-side assertions; none is waived by this Task.

Integration refresh: main `03a8b1d8b3eea15ad03f44234b390bb3ab85fc59`
contains the stopped-Pattern authority repair from #1978. Its native source,
test and documentation match the reviewed producer head. Do not repeat that
implementation. Main's Creator app and transport-actions blobs still match
this Task's original `d77a471de81b39cefdbb56d440c54f877736b208` base: the
guarded observation and retry ownership functions remain absent. This
consumer repair therefore remains outstanding. Main's #1977 grid regression
and #1979 interaction documentation are retained; Task source and shipping
policy are otherwise unchanged.

Integrate that exact main revision, rerun the complete component suite,
TypeScript and ownership checks before committing, then run the complete
Creator lane on the clean committed integration head. Previous heads' browser
results and the producer's passing Creator lane do not verify this consumer.
The producer's Linux Asan run is still incomplete with failures; its external
merge does not establish an Asan pass or owner acceptance of those failures.
Review and merge of this consumer remain separate, uncompleted boundaries.

The merged worktree's complete component suite passed all 70 files / 1219
cases in 64.79 s with the original bounds and unchanged tracked sources.
TypeScript passed against the explicit Creator tsconfig; an earlier invocation
ran from the repository root and printed compiler usage without checking a
project, so it is retained as a failed invocation rather than verification.
The ownership suite passed all 77 cases. These checks authorize the integration
commit only; committed full-lane evidence and current-head review are pending.

Independent preliminary review of `2b2d47b925ba4764d8b6625aba1caa9965b528ba`
found one remaining P2: the retry catch accepts a same-owner error from an
already settled Stop and dispatches `failed(old Stop)`, clearing a newer Record
pending. A reduced model executes the unchanged App function bodies with the
actual SDK request serialization and React reducer/ref updates. Both this head
and main `03a8b1d8b3eea15ad03f44234b390bb3ab85fc59` fail its assertion; a private
candidate with the unresolved-command identity guard passes, and current
submission/inspection failures still report exactly once. This is a remaining
consumer defect, not waived as a historical problem or counted as an eligible
review. Main `e14084f602448ee2046a9cd64e7dd3bf3bd2e7ea` changes only the two
Creator portal pages relative to that main base; this Task's relevant consumer,
producer, tests and shipping policies are unchanged.

Retain the unchanged `2b2d47b` browser-run results separately. Repair and verify
the P2 in an isolated worktree, with the App-level regression declared above.
No old-head full-lane result verifies that later repaired source. The separate
question about an outer-await projection gap did not produce a proven old
command resend and is not another finding or new implementation scope.

The unchanged `2b2d47b` complete Creator lane finished successfully: 70 files /
1219 component cases and all seven browser groups, totaling 111 passed and 11
existing capability skips out of 122 browser cases. The original fixtures,
timeouts and journey assertions were retained. This is that head's completed
verification; it does not settle the independent P2 or the older intermittent
Host failures, and its input key cannot verify the later repair.

The P2 now has a real mounted-App counterexample using serialized request and
inspection actions. On the unmodified `2b2d47b` App, the new Record request
remained unresolved but its button became enabled after the old Stop retry
inspection failed. The assertion failed in 685 ms within the unchanged 20 s
bound. With a current unresolved-command identity check before reporting or
dispatching the retry failure, all three regression cases passed: the obsolete
failure leaves Record pending through its eventual recording observation, and
current submission and inspection failures still report and retain the exact
command for retry. The complete component suite passed 70 files / 1222 cases
in 48.00 s; TypeScript, all 77 staged ownership cases and docs_static passed.
Committed full-lane verification and current-head review remain separate
boundaries.

The producer's unchanged GCC 13.3 Linux Asan lane also reached its actual
terminal: 190 passed and 66 failed out of 256 full cases; stress was not run
after the failed full group. No pass key or accepted-risk waiver resulted.
The separate compiler diagnosis and native acceptance obligations remain open.
