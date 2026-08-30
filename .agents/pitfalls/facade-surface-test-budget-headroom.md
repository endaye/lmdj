---
id: facade-surface-test-budget-headroom
area: core
status: absorbed
recurrences:
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/444
    observed_by: Codex GPT-5
exit: gate:tests/build/facade_surface_sharding_test.py
---

# A native Facade surface aggregator can pass locally yet become a deterministic 30-second CI timeout once normal Runner variance consumes its missing budget headroom.

## Why

The Sequence and Sample Facade surface binaries accumulated many durable-file
and Project mutation scenarios behind one component registration each. A recent
successful coverage run already used 25.10 and 20.05 seconds of their 30-second
budgets. The next main coverage run and an unrelated Pull Request run then timed
out both binaries at 30 seconds on two separate Linux runners, while the same
binaries remained fast locally. Product assertions did not identify the
problem: only the historical CI budget evidence showed that the aggregation,
not either product change, had exhausted normal execution variance.

## How to apply

Keep the two Facade surface binaries partitioned by named scenario tables. Each
CTest registration must execute exactly one shard, while bare binary execution
must still traverse the union of every shard. The absorbed build gate compares
the binaries' declared shard counts with the registered CTest commands; add a
new scenario to one named shard and split again before any shard approaches its
component budget.
