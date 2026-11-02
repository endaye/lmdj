---
id: cumulative-evidence-log-last-entry-wait
area: web-host
status: open
recurrences:
  - date: 2026-11-02
    occurrence: https://github.com/endaye/lmdj/issues/2526
    observed_by: Claude Code (Claude Opus 5.5)
exit: none
---

# A wait on the last entry of a cumulative evidence log can be satisfied by an entry from before the action it means to observe.

## Why

Browser Proofs record transport traffic in page-lifetime arrays such as
`__candidateUiEvidence`, and helpers like `last(page, operation)` return the
newest matching entry. A poll on `last(...)` written right after a click checks
"the newest entry has property P", not "the click produced an entry with P".
When an earlier request already had P, the poll passes at once, before the
click's own request has even been sent, and the test races the work it claims
to wait for. In #2526 an earlier `snapshot.reload` already carried the empty
Pattern. The adoption journey pressed a Pad while its own Refresh was still
preparing playback, the Creator dropped the press by design, and the 30 s wake
wait failed on loaded runners.

## How to apply

Before the action, record the log's length (or a request id the action will
use). Then wait for an entry past that mark that has the property. Where the
product exposes a readiness surface (here, the `Project audio status` region
going away), wait for that too, before any input that depends on it. Mutation
check: the stale-entry wait must fail on a run where the action's own request
has not landed. Remains `open` with `exit: none`, because whether an entry
could predate the action is not decidable from the test text alone.
