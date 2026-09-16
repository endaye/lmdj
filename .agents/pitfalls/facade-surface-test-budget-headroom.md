---
id: facade-surface-test-budget-headroom
area: core
status: open
recurrences:
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/444
    observed_by: Codex GPT-5
  - date: 2026-09-05
    occurrence: https://github.com/endaye/lmdj/issues/566
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-16
    occurrence: https://github.com/endaye/lmdj/issues/1389
    observed_by: Kimi (agent)
exit: none
escalation: https://github.com/endaye/lmdj/issues/657
---

# A fixed wall-clock test budget can pass locally yet become a deterministic CI timeout once normal Runner variance consumes the headroom it never had.

## Why

The Sequence and Sample Facade surface binaries accumulated many durable-file
and Project mutation scenarios behind one component registration each. A recent
successful coverage run already used 25.10 and 20.05 seconds of their 30-second
budgets. The next main coverage run and an unrelated Pull Request run then timed
out both binaries at 30 seconds on two separate Linux runners, while the same
binaries remained fast locally. Product assertions did not identify the
problem: only the historical CI budget evidence showed that the aggregation,
not either product change, had exhausted normal execution variance.

The shape is not native-specific. On 2026-09-05 the same failure reached a
Python harness: `apps/creator-web/test/deploy_command_test.py` allowed a spawned
deploy subprocess a fixed 15 seconds to reach its post-publish sentinel. Both
signal subTests failed together on `actions-runner-02` while four shards of the
same suite contended for one shared self-hosted host, minutes after the exact
same job passed on `main` and while the full suite passed locally. A budget that
every local run confirms is exactly the budget nobody re-examines.

## How to apply

Keep the two Facade surface binaries partitioned by named scenario tables. Each
CTest registration must execute exactly one shard, while bare binary execution
must still traverse the union of every shard. The absorbed build gate compares
the binaries' declared shard counts with the registered CTest commands; add a
new scenario to one named shard and split again before any shard approaches its
component budget.

`tests/build/facade_surface_sharding_test.py` still enforces that partitioning,
but it can only read C++ CTest registrations; it cannot see a wall-clock
deadline in any other harness. Everywhere else this invariant is guidance only.

Derive a test budget from the work it covers rather than writing one wall-clock
literal: a named per-unit allowance multiplied by a declared unit count, so the
number moves when the work does. Make the timeout message name the elapsed time,
the budget and its derivation, and the resource that never arrived, so a
recurrence is diagnosable from the run log without reading the harness. For a spawned child whose per-unit progress is observable, prefer a
no-progress watchdog over any wall-clock total: stream the child's transcript
and kill only after a bounded silence, so a contended host's slow-but-healthy
run passes while a genuine hang still dies with the in-flight unit named. The
PR-Agent integration child in `tests/build/ci_pr_agent_review_test.py`
(`run_child_with_watchdog`, #1389) is the reference shape: 120s of no test
progress kills the child; a total ceiling remains only against a child that
emits progress forever.

Prefer a
budget that is generous to one that is tight: an over-long budget only delays a
genuine hang, while a tight one fails a healthy run deterministically on a
contended host.

No repository-wide gate exists because violation is not mechanically decidable:
a scan can find every wall-clock literal but cannot distinguish a well-
provisioned budget from an under-provisioned one. Escalation Issue
[#657](https://github.com/endaye/lmdj/issues/657) tracks the mechanism, and
records that analysis so no later Task retries a source-scanning gate.
