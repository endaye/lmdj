---
id: manual-batch-dispatch-short-request-format
area: ci-release
status: open
recurrences:
  - date: 2026-09-21
    occurrence: https://github.com/endaye/lmdj/pull/1585
    observed_by: Kimi Code (k3)
exit: none
---

# Manually dispatched batch requests take only the short form, and an executed request ID is spent.

## Why

A manual `self-test-report.yml` dispatch carrying a full batch-request document
(the shape the controller itself writes, with policy/selection/suites) is not
accepted: the manual path parses only the short form
`{"id","kind","target"}`. And once a request ID has been executed, the
controller will not deliver it again — re-dispatching the same ID to retry a
failed or invalid run is silently a no-op, so the retry must mint a fresh ID.
Both are controller contract details that live outside product code and cost
a full dispatch cycle to discover.

## How to apply

For a manual batch dispatch, send exactly `{"id":"<new-stable-id>",
"kind":"candidate","target":"<exact-main-SHA>"}` on ref `main`; never reuse an
ID that already executed, and never paste the controller's long-form record.
On a slow operator network, give staging/audit commands generous timeouts —
a killed release tool can leave an unfinished journal run that needs
reconciliation before the next operation. No eligible gate exists yet: the
manual dispatch format is exercised only by real controller runs, so the
entry stays open with `exit: none`.
