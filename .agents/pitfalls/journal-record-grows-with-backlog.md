---
id: journal-record-grows-with-backlog
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-18
    occurrence: https://github.com/endaye/lmdj/issues/1048
    observed_by: Claude Fable 5.1
exit: gate:tests/build/ci_batch_controller_test.py
---

# A journal record that explains itself per changed path grows with the unprocessed backlog until it exceeds the bounded record size, and the local refusal then blocks every admit with no observable cause.

## Why

The scheduler's `admit` event carries the whole request, and the request's
`selection.reasons` lists one reason per changed path (`broad foundational or
concurrency impact: <path>`, the routing manifest reasons, and so on). While the
scheduler admits every few commits that list is a few dozen lines. Once it is
blocked for any other reason the unprocessed interval keeps growing, and so does
the explanation: after 261 first-parent commits the next `admit` record measured
2,355 reasons and 260,100 bytes, against the 60,000-byte journal object limit
that keeps records inside GitHub's 65,536-character comment body. The transport
refused the record before its anchor intent, which is correct, but that refusal
was a local `require` with no HTTP status, left no pending intent behind and
surfaced only as the closed `journal-blocked` kind. Each tick therefore paid a
full authenticated replay plus the `advice()` artifact scan, appended one small
`observe`, and died at `admit`; the journal stayed healthy, and the backlog and
the record kept growing. The feedback loop is invisible from the protocol code:
every operation is correct on its own, and the size is a property of the
backlog, not of any single event.

## How to apply

Anything a bounded record carries must itself be bounded by construction, not
by the state the system happens to be in. Keep decision fields (suites) exact
and bound explanation fields with a deterministic, idempotent rule so a stored
request rebuilds to itself. When a fail-closed check can refuse locally, give it
a closed diagnostic kind of its own (`journal-record-oversized`) so a blocked
tick names the invariant without leaking exception text. When a scheduler has
been blocked for days, measure what its *next* write would be before assuming
the blocker is network, quota or visibility: replay the interval selection
locally and size the resulting record against the limit. The gate
`tests/build/ci_batch_controller_test.py` builds a 600-path interval, checks the
selection stays full, and asserts the pending-admit checkpoint fits the journal
object limit; `tests/build/ci_batch_github_journal_test.py` checks an oversized
record is refused with the closed kind before any anchor or comment mutation.
