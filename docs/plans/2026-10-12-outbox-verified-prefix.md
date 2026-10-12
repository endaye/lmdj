# Persist the authenticated outbox prefix

## Premise disposition

Fresh `origin/main` and this isolated Task base are
`02b7445ff035e48c43ea2a66c858f7c9282e6c79`.

1. The active-tree failure is reproducible, but `proof` remains registered as
   `proof|quick)`. Draft PR #2030 already repairs the matcher. Its original
   owner retains shipping responsibility at the user's explicit instruction;
   this Task does not duplicate that repair.
2. The diagnostic mapping is already delivered by PR #1791, merged as
   `887752c8f7c3dec9007218da26a4f5e3035020b4`. `incremental_entry.diagnostic`
   names `OutboxBlocked` as `outbox-blocked`; its existing tests also cover
   bounded HTTP context traversal. Do not repeat that implementation.
3. Still outstanding: PR #2033 persists the scheduler's authenticated prefix
   after reconcile, but `Outbox.load` only loads and reduces its own journal.
   Outbox append carries a verified prefix; a successful idle replay cannot
   upgrade a legacy anchor. Inspecting these actual producer and consumer
   paths distinguishes the working scheduler/append paths from this omission.

## Task and declared files

- `scripts/ci/report_outbox.py`: after complete journal authentication and
  successful outbox reduction, persist the verified prefix before exposing
  state or permitting a business write. Use the existing locked, authenticated
  anchor interface; an unchanged prefix is a no-op.
- `tests/build/ci_report_outbox_test.py`: cover prefix upgrade, fresh-process
  reuse, rejected replay, failed persistence and lock loss.
- `tests/build/ci_report_runtime_test.py`: verify an idle runtime drain upgrades
  only the outbox anchor and a fresh runtime does not repeat the PATCH.
- `apps/docs-site/docs/operations/testing-and-proof.mdx`: document the
  cross-process prefix boundary for scheduler and outbox.
- This plan: retain premise, verification and shipping evidence.

No journal schema, authority, scheduler progress, business POST retry rule,
workflow trigger, Product Build or release state changes.

## Verification

Run the new regressions on the unchanged implementation first, retaining the
failure that the prefix is not persisted. Then run the complete outbox,
report-runtime, journal and GitHub journal suites. The restart journey is:
legacy anchor without a prefix -> complete authenticated replay -> one verified
anchor write -> fresh reporter -> unchanged canonical outbox state with no
writer reauthentication inside the prefix and no repeated anchor write.
Rejected semantic replay must write no prefix; persistence failure or lock loss
must expose no new state and permit no business POST. Existing crash/uncertain
POST journeys remain required. Run the complete Portal check for the changed
source fact, plus new-file ownership and PR declaration checks before shipping.
These fixtures establish composition and protocol behavior, not hosted token
permissions, production request savings or remote acceptance.

## Version Management

Version impact: none — CI reporting storage tooling changes no active product,
Module, Host, Provider or Contract manifest identity.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: the documented journal authentication and persistence boundary changes.

## Pitfall Impact

Pitfall impact: none — the omitted outbox call is directly visible in its
producer/consumer wiring and fully expressed by the restart regression. Apply
the existing journal-cost and stale-premise guidance without inventing a new
process recurrence.

## Actual verification

- Original outbox implementation: new protocol regressions failed 3/41 for
  the missing persist, missing write failure boundary and lock loss boundary.
  The HTTP idle-drain regression failed at the absent outbox PATCH.
- Fixed outbox suite: 42/42 passed. Report runtime: 84/84 passed; Journal:
  37/37 passed; GitHub journal: 90/90 passed. These retain the existing
  uncertain POST and crash/restart journeys. Lost prefix PATCH response leaves
  no exposed state or business POST; a fresh caller resumes and publishes once.
- The fresh-process equality test also pins generation 4, delivered status
  and the receipt to the independently observed business Issue, avoiding a
  shared reducer omission. The pre-fix run agrees on the old projection but
  fails the independently counted missing anchor write.
- Existing diagnostic suite: 44/44 passed, including CLI `outbox-blocked`.
  Pristine main's active-tree check still fails for the lexical `proof` arm;
  unchanged PR #2030's active-tree and proof-failure-artifact checks both pass.
- Complete Portal check: first attempt failed because this new worktree had no
  installed dependencies. Locked `npm ci` succeeded; the original complete
  `scripts/docs-site.sh check` then passed, including 50 routes/internal links.
- Path ownership: 77/77 passed. Ledger lint exposed an existing main defect:
  #2033 wrote a semicolon-separated multi-exit field, rejected by its grammar.
  The separate `docs/journal-pitfall-exit` Task repairs only that field; this
  outbox Task retains the failure rather than weakening or copying the gate.
- Fresh precommit fetch still resolves to
  `02b7445ff035e48c43ea2a66c858f7c9282e6c79`; no successor touches this omission.

Raw streams are retained in `/tmp/lmdj-outbox-*.log` on this host. Complete
product/candidate lanes and production HTTP savings remain unverified.
