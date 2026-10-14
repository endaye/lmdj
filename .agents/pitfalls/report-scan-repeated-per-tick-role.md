---
id: report-scan-repeated-per-tick-role
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-14
    occurrence: https://github.com/endaye/lmdj/pull/2205
    observed_by: unknown
exit: gate:tests/build/ci_report_progress_test.py
---

# Attaching one expensive report scan to every scheduler tick role multiplies its cost by the number of roles and spends the shared Actions quota.

## Why

Each tick role is cheap to reason about alone, so the full report scan (about
535 requests) and review discovery (about 350–420) were attached to every tick
that could carry them: four report crons per hour plus idle push and scheduler
health ticks. Over about 26 hours on 2026-10-13/14 that came to about 2.4k of
the repository-wide 5,000 requests/hour `GITHUB_TOKEN` budget, shared with the
controller, review and every other workflow. A health tick paid the full scan
again, for example run 38494391699 (129 control + 536 report + 424 discovery).
No single step was wrong; the cost is a property of the role × step
composition, which the code of any one step does not show.

## How to apply

Before attaching a request-heavy step to a tick, multiply its per-run cost by
every role and cron that will run it, and compare the total with the shared
hourly budget. Give the expensive scan exactly one owning role (the hourly
report tick) and let other roles do only their own cheap work. The gate runs the
real workflow `if:` expressions per tick role in `test_report_tick_is_hourly`
and `test_only_report_tick_and_completion_relays_pay_for_reporting`; a new tick
role or cron must extend that truth table rather than inherit reporting.
The Incremental Completion ↔ Self-test Report relay chain is a separate,
bounded cost (one relay and one callback per root run, about 135 requests/hour
after #2205); do not filter it by `run-name` or by parent success to save
quota, because relays of cancelled or failed parents are deliberate recovery
wakeups (owner decision, 2026-10-14).
