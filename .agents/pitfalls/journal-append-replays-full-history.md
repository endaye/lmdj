---
id: journal-append-replays-full-history
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-17
    occurrence: https://github.com/endaye/lmdj/issues/1486
    observed_by: Kimi
exit: gate:tests/build/ci_batch_runtime_test.py
---

# Verifying the complete journal history on every append makes journal writing O(n) per event, and the shared hourly quota stops the scheduler before it can admit work.

## Why

The append protocol is intent-then-POST, so a writer naturally reads the journal
before and after each write. Doing that with a *complete authenticated replay*
every time is invisible while the journal is short and becomes fatal as it
grows: at 293 comments one replay is 479 requests, one append is two replays,
and a single `reconcile` performs up to four appends (`observe`, `advance`,
`admit`, `claim`). The measured tick cost reached ~4,300 requests against a
repository-wide 5,000 requests/hour `GITHUB_TOKEN` shared with every other
workflow, so ticks died on quota 403 or transport errors and the scheduler
admitted nothing for days even with a healthy journal. This is not derivable
from the protocol code, which is correct per operation; it is a cost property
of the composition, and it is the same property that stranded a POST on
2026-09-11.

## How to apply

When a protocol verifies a long history, verify it once per process and
authenticate only the delta afterwards — never skip a check, only avoid
repeating one. Bound the reuse so it cannot hide tampering: reuse only while the
durable anchor still names exactly the verified head, require the provider's
total to equal the verified count plus the delta, chain every new event onto the
verified head, and fall back to the complete replay on any mismatch. Measure the
request cost of the whole operation, not one call: four appends in one process
that each replay the complete history is eight replays, which the gate
`tests/build/ci_batch_runtime_test.py` now measures as comment rows served
(48 before the fix, bounded after it).
