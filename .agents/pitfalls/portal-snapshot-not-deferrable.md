---
id: portal-snapshot-not-deferrable
area: docs-governance
status: absorbed
recurrences:
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/issues/436
    observed_by: claude-opus-5
  - date: 2026-10-10
    occurrence: https://github.com/endaye/lmdj/issues/1822
    observed_by: codex
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A new Product Build allocation and its matching immutable snapshot must ship in the same PR.

## Why

The current Build's Portal check compares actual identities and lock facts with
its immutable snapshot. Freezing requires a clean committed source, so deferring
it to a later PR leaves an unshippable allocation. This recurred while planning
Project live-control syntax: schema, selected Contract and lock cannot change
under the old Build/snapshot. The generic identity-cut source/snapshot bootstrap
also has to support already-merged Module/Host/Provider identity settlement.
The 2026-10-10 UTC observation belongs to the still-open #1822 follow-up Goal;
[the bootstrap plan](../../docs/plans/2026-10-11-product-cut-snapshot-bootstrap.md)
records the concrete source/tool premises and the independently reviewed cut.

## How to apply

Follow the source/snapshot mechanism in
[`issue-done` §1](../skills/issue-done/SKILL.md#1-prerequisites--verification-check),
which references [canonical S0/S1](../../docs/governance/git-workflow.md#product-cut-source-and-snapshot-phases).
S0 retains real nonzero missing-snapshot evidence and complete source/current
PASS; it is only a local clean freeze checkpoint. S1 must pass the original
complete checks before both atomic Tasks ship together in one PR. Snapshot-only
Tasks retain the canonical direct-parent preference. Keep real baseline/source/
squash identities distinct; preserve interrupted bytes for official resume and
verify actual postmerge provenance. Never delete/refreeze generically, hand-edit
metadata or use historical two-commit examples as an exemption. This mechanism
adds no release or cleanup authority.
