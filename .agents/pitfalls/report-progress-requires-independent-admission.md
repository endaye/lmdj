---
id: report-progress-requires-independent-admission
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/issues/1048
    observed_by: Codex
exit: gate:tests/build/ci_report_progress_test.py
---

# Reports that run only when a scheduler is idle can starve behind continuous product batches, even with a short journal lock.

## Why

The automatic workflow admission group spans its product DAG. Every next main
interval can return execute and skip report steps again. Delivered outbox entries
then conceal failures that never entered that outbox. A successful manual empty
drain does not establish reporting completeness. Merely splitting admission by
event type leaves the execute-versus-report decision unchanged.

## How to apply

Provide an independently admitted report-only role that cannot claim products,
while retaining the scheduler's independent missed-event recovery. Test a long
active product workflow, repeated pending replacements and real report delivery
against an unchanged scheduler claim. Keep exact writer authentication and unknown
POST reconciliation. Distinguish unqueued failures from queued undelivered work.
The gate models deterministic admission/entry behavior, not GitHub cron delivery,
runner capacity, relay depth, sustainable throughput or bounded end-to-end latency;
measure those separately before claiming remote acceptance.
