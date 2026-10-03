# P1 owner-loss tail at the Pattern loop boundary

Independent R17 reproduced the actual unmodified PatternEventReducer with no
release, one bar, onset3660 and default tail240: Project Truth correctly contains
180 ticks, clipped at3840. Onset3600 retains240. Both current owner-loss journeys
unconditionally asserted240 without controlling onset, so a legal near-end
recording failed the test. Preserve their existing held input through reload,
and require the exact normalized tail min(240, bars*3840-onset). Require a valid
integer onset inside the loop as well. Do not change product behavior or merely
accept a duration range.

## Task scope and verification

Declared files:
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `docs/plans/2026-10-03-p1-owner-loss-loop-tail.md`

Lowest-tier proof uses actual Native reducer results at3600 and3660 against the
new strict assertion. A constant240 mutant must fail on the near-end result.
Run both complete original owner-loss/recovery/reopen journeys against the
unchanged authenticated786 distribution and real Native fixture, retaining all
counts, revisions, identities, original budgets and later re-recording legs.
Run syntax, ownership and staged diff checks before commit. After commit classify
new exact inputs and complete the changed Creator lane; current Runtime and
Toolchain evidence transfers only if production keys independently match.

## Version Management

Version impact: none. Test premise only, no Product, Host, Module, Provider,
Contract or authoring semantics change.

Documentation impact: none. No Architecture Portal source fact changes; this
plan records the canonical fixed PPQ960/4-4 and loop clipping semantics.
