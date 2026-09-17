---
id: journal-pending-strand-blocks-without-drain
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-17
    occurrence: https://github.com/endaye/lmdj/issues/1048
    observed_by: Kimi
exit: gate:tests/build/ci_incremental_batch_journal_test.py
---

# A stranded pending journal intent blocks every automatic run, and each blocked run full-replays the journal, burning the request budget that stranded it.

## Why

The journal append protocol writes the pending intent to the anchor before the
single POST; when the POST outcome is unknown, every later `load()` fail-closed
on purpose. Two process facts are not derivable from the code: there was no
operator path to drain a proven-absent pending, so one lost POST (2026-09-11,
rate-limit 403 mid-append) stopped the incremental main scheduler and all
failure reporting for days; and the blocked code path still walked the entire
authenticated comment history on every health tick before failing, so the
blocked state itself consumed the hourly request budget — the same exhaustion
that caused the original strand.

## How to apply

Diagnose with a strictly read-only replay of the fixed Issue (complete comment
inventory, digest chain, anchor head/pending) before any write; a pending whose
event is genuinely absent is drained only through the guarded
`batch_operation=reconcile-pending` manual command with the exact audited
digest, never by hand-editing the Issue body (a human edit breaks trusted
editor provenance and blocks harder) and never by replaying the POST. The gate
pins both the drain preconditions (exact digest, chain successor, complete
authenticated absence proof) and the tail-peek fail-fast that keeps a blocked
journal from full-replaying every tick.
