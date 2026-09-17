# Settled PR-Agent ledger reservations stop exhausting unspent budget

## Task

Issue #1469: the review engine's durable budget ledger
(`scripts/ci/pr_agent_review.py`, `class Ledger`) admits every model request
against a worst-case reservation (full context at configured prices) and only
converts that reservation to the metered amount on a successful
`reconcile`. Outcomes that never reconcile — transport failure, timeout,
unpriceable or mismatched response identity — stay `reserved`/`uncertain`
while `_record_amount` keeps counting their full reservation as committed.
The archived pilot ledger (760 records) held USD 242.81 of reservations
against USD 15.88 of real spend: 368 settled records overshot 7x, and 380
dead records permanently occupied USD 121.41. The ledger, not the wallet, is
the budget constraint.

Declared files:

- `scripts/ci/pr_agent_review.py`
- `tests/build/ci_pr_agent_review_test.py`
- `docs/quality/2026-09-10-pr-agent-netcup-operations.md`
- `docs/plans/2026-09-17-pr-agent-ledger-reservation-settlement.md`

## Design decision

Considered and rejected:

1. *Settle `uncertain` records at a measured actual.* Rejected: failure paths
   either observe no usage (timeout, transport error) or observe usage whose
   pricing identity is unverified (malformed/mismatched model). Writing an
   `actual_amount_usd` for those fabricates cost data the provider never
   reported; the durable record would claim precision it does not have.
2. *Add a terminal `released`/`failed` status for dead reservations.* Rejected:
   a third terminal status changes the validated record shape, forks the
   durable schema handling (`_validate_record`, `_records`, the identity
   checks in `admit`/`reconcile`) and reinterprets archived schema-v1
   records, for no accounting gain over the chosen design.

Chosen: keep the record shape, the terminal statuses, and the durable
reservation exactly as they are, and make the *accounting* converge:

- `_record_amount` counts `reserved` records at their reservation (in-flight
  liability only), `reconciled` records at their actual amount (unchanged),
  and `uncertain` records at zero: the provider's consumption for an
  unobserved or unpriceable outcome is unknown, committed budget must
  converge to metered spend, and the durable `reserved_amount_usd` on the
  record is unchanged for audit.
- The worst-case reservation at admission time is untouched: it remains the
  conservative gate that bounds a runaway request before dispatch. Only the
  accounting after the outcome is known changes.
- Failure paths stay `uncertain` finalizations (zero committed); paths that
  already validate usage and served identity still `reconcile` at the metered
  amount, including breach cases where actual exceeds the reservation.
- No migration: the active ledger started empty at the 2026-09-17 archive
  cutover, and the archived ledger is never re-read. Old records that can
  never reconcile load exactly as before; the refund treatment is a property
  of the accounting function, not of the records' era.

Residual risk, accepted and documented: a provider that bills a request whose
outcome the engine could not observe (for example a processed-but-timed-out
generation) would be under-counted until the operator reconciles against the
provider invoice. The `envelope_breach` operator hold and the durable
reservation amounts keep that audit possible; the attempt supervisor's
fenced `uncertain` attempts remain the review-side record.

Request-count caps (`max_requests`, `max_requests_per_provider`) are
unchanged and keep bounding attempts independently of the dollar convergence.

## Tests

Existing suite updates:

- `test_uncertain_reservation_is_retained` asserted the defect (an uncertain
  finalization keeps its reservation committed). It now proves the refund:
  the uncertain record keeps its durable `reserved_amount_usd` while a
  following admission of the same size succeeds.

New acceptance paths from the issue:

- dead-reservation refund: an uncertain finalization frees its reservation
  (covered by the rewritten test above);
- mixed settled/failed attempt: one reconciled request plus one uncertain
  request commit exactly the reconciled actual, and the freed headroom
  admits a following reservation that would not have fit before;
- budget-exhaustion-then-recovery: in-flight reservations exhaust the
  per-PR cap and deny further admission; reconciling them at their small
  actuals restores admission without changing any cap, and the denial leg
  still holds before reconciliation.

## Verification

Baseline on `main` (accounting change stashed, new tests present):
`PATH=/opt/homebrew/bin:$PATH python3 tests/build/ci_pr_agent_review_test.py`
failed exactly the three paths below, each with
`AdmissionDenied: request cost budget exhausted` — the ledger, not the
wallet, denying admission. No other test failed.

With the change, the same full suite: 65 tests, OK, 9 skipped (integration
skips without the pinned upstream bundle). Each path is red for exactly the
old committed-amount rule and green after:

- `test_uncertain_reservation_is_retained` — dead-reservation refund leg:
  the uncertain record keeps its durable `reserved_amount_usd` (0.00015)
  while the same-size re-admission succeeds.
- `test_mixed_settled_and_failed_attempt_commits_only_metered_actual` —
  settled 0.0001 actual plus failed 0.00025 reservation commit 0.0001; the
  0.00015 admission the in-flight pair crowded out fits again.
- `test_budget_exhaustion_recovers_after_reconciliation_without_cap_changes`
  — two in-flight reservations exhaust the per-PR cap (far-side denial
  asserted), one reconciles at 0.00005 actual and one ends uncertain, and
  the same 0.00015 size admits again under unchanged caps.

## Version Management

Version impact: none. The change touches a CI adapter script and its tests
plus explanatory docs; no Product Build, Core Module, Provider, or Contract
identity is affected.

## Documentation impact

Documentation impact: none. No Architecture Portal page
(`apps/docs-site/docs/`) changes; `docs/quality/` and `docs/plans/` are
explanatory records, and the operations record update is required by the
issue's acceptance, not by the portal.
