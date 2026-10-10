---
id: business-claim-outcome-unknown-blocks-reporting
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-08
    occurrence: https://github.com/endaye/lmdj/issues/1048#issuecomment-6062710191
    observed_by: Kimi
exit: gate:tests/build/ci_report_outbox_test.py
---

# A persisted business claim whose POST outcome is unknown fail-closes all report delivery forever, and until the reconciliation operation existed there was no safe way to settle it.

## Why

The report outbox persists the business claim (exact POST intent) before the
POST. If the process dies or quota runs out between claim and ack, every later
tick's `recover()` returns `needs-reconciliation` for that delivery and no
queued observation is delivered — by design, because an empty receipt search
never proves the POST failed. This is the sibling of
`journal-pending-strand-blocks-without-drain` one protocol layer up: there the
journal comment POST is stranded (signal `journal-blocked`, drain
`reconcile-pending`); here the business Issue/comment POST is stranded (signal
`needs-reconciliation`, journal and anchor healthy). On 2026-09-18 a
`create-issue` claim (outbox generation 879) lost its outcome to quota
exhaustion and silently blocked every managed-bucket delivery for weeks while
queue events kept accumulating — the report step stayed green because it
"successfully delivered nothing".

## How to apply

Never replay the business POST, never mark the claim delivered without a
canonical receipt, and never hand-edit the outbox Issue. Audit read-only
first: the exact delivery key and claim digest from the frozen outbox events,
then the complete authenticated inventory. Settle through the guarded manual
`batch_operation=report-reconcile-claim` with a closed `batch_request`:
`resolution={"kind":"absent"}` only when the complete inventory proves the
POST absent (the claim returns to `queued` via `claim-cleared` and the
ordinary path re-derives the byte-identical POST); `resolution={"kind":
"receipt","issue_number":N,"comment_id":...}` only when the exact receipt
verifies live against the frozen payload. An acknowledged write accepts only
the receipt resolution. The gate pins the closed command schema, both
resolutions, and the reducer's `claim-cleared` transition.
