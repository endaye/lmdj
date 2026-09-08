---
id: hosted-allowlist-is-not-zero-cost
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/actions/runs/34203545873
    observed_by: Codex
exit: gate:tests/build/ci_hosted_runner_policy_test.py
---

# A hosted exception allowlist does not establish zero cost when routine control tasks repeatedly consume metered jobs.

## Why

The September usage export recorded zero self-hosted compute fees but positive
hosted scope, report, relay and audit usage. Moving heavy suites did not move
the control chain, and merging business test requests did not merge billed job
allocations. A clean allowlist only proved these costs were recorded decisions.
The platform subsequently refused an unassigned job for billing eligibility;
the annotation alone does not distinguish a budget stop from payment failure.

## How to apply

Check the complete runner graph and official net usage by SKU/workflow before
claiming zero cost. The routing contract now independently forbids hosted Linux
in routine control workflows, even when allowlisted. Contabo control and Netcup
heavy roles remain separate. The Owner permits paid macOS availability recovery;
busy-only waiting and product failures must not buy a retry. Report this as zero
routine Linux hosted compute, never unconditional zero account billing. Preserve
privileged publication isolation and state any account/runner acceptance gaps.
