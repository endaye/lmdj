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

Lowest-tier proof: deferred inspection crosses actual reducer settlement and
session replacement. The old extracted algorithm must fail the settled-Stop
assertion. The corrected helper must preserve a genuinely unknown request and
ignore stale status/error for a replaced owner.
Deferred retry submissions and inspections must likewise ignore a replacement
owner, skip inspection after ownership loss during submission, and preserve
the current owner's failures. Run the complete transport
state/action groups, TypeScript and the complete Creator component suite with
existing timeouts. Retain actual red/green output and source identities.

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
