---
id: shared-host-runner-capacity
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/444
    observed_by: codex-gpt-5
exit: gate:tests/build/ci_build_acceleration_test.py
---

# Separate self-hosted runner services on one physical host do not provide independent CPU capacity.

## Why

The Contabo host exposes two baseline runner services with the same `ci-core`
role. A job-level role selector can therefore place coverage on one service and
an ordinary Core proof or package build on the sibling service. Those jobs look
independent to GitHub but compete for the same host CPU budget: main run
33290370946 timed out two unchanged 30-second coverage tests while PR #444's
Core proof occupied the sibling service.

## How to apply

Put every native Core job eligible for the shared Contabo host in the same
repository-wide capacity queue, including ordinary proof and package jobs as
well as ASan and coverage. Retain every waiter with `queue: max`, keep
`cancel-in-progress: false`, and gate the complete admitted job set. Do not
widen product test budgets to absorb sibling-runner contention.
