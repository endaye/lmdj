# P1 offline-branch owner-loss loop tail

R17 reproduces the canonical Native PatternEventReducer without release:
onset3660 in a one-bar loop produces180 ticks; onset3600 produces240.
The offline branch still asserts an unconditional240 in both owner-loss
journeys. Require the exact min(240, bars*3840-onset) with an integer onset
inside the loop. Hold each initialKeyQ through document loss and release after reopen, to
establish the default-tail actor even if Runtime currentness changes its release
route. Preserve both complete original journeys, all counts,
revision/slot/velocity identities, budgets, reopen and later re-recording legs.
Product input ownership and musical behavior do not change in this Task.

## Task scope and verification

Declared files:
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `docs/plans/2026-10-03-p1-offline-loop-tail.md`

Lowest-tier proof compiles the actual unchanged reducer from this Source,
checks the earlier and near-end outcomes against the strict helper, and
requires a constant240 assertion mutant to fail on the near-end output.
Run both complete original owner-loss journeys on the authenticated unchanged
41d distribution with its real Native fixture before commit. Run syntax and
staged ownership checks. After commit reclassify keys: changed Creator must
complete a new full proof; all other transferred passes require exact
production-key equality with961, with original raw evidence retained.

## Version Management

Version impact: none. Strict test premise only; no identities allocated.
Documentation impact: none. No Portal source fact or product behavior changes.
The existing T8 coordinated Creator MAJOR/offline acceptance remains pending.
