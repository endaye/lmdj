---
id: parity-check-between-agreeing-copies
area: core
status: absorbed
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/799
    observed_by: Claude Code (Opus 5)
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/pull/1780
    observed_by: Claude Code (Opus 5.5)
exit: skill:.agents/skills/issue-done/SKILL.md
---

# Agreement between consumers or shared implementations can hide a defect present on both sides

## Why

In #799, `control_runtime.cpp` served `soundset.audition`, while both
`bridge.cpp` and `protocol.mjs` omitted it. Comparing the two consumers passed
on the broken tree. Binding each consumer to the producer's served-operation
inventory caught the missing route. The resulting
`check_served_operations_are_reachable` in
`packages/web-runtime-platform/test/source_boundary_test.py` covers the Sound
Set table; it explicitly leaves non-table operation branches outside its scope.

In #1780, realtime and offline rendering shared a voice kernel. Their parity
test passed when both ended a filtered voice while its filter still rang, and
again when both swelled by 26 dB after release during an attack. Independent
assertions on the realtime output caught the end step and the rising release.
A shared implementation provides agreement, not an independent expectation.

The general invariant is review judgment: identifying a parity test and an
independent oracle is not a deterministic keyword check. The recurrence-2
escalation [#1787](https://github.com/endaye/lmdj/issues/1787) therefore exits to
shipping guidance rather than a universal CI gate.

## How to apply

Follow **Parity tests need an independent oracle** in
[`issue-done` §2](../skills/issue-done/SKILL.md#parity-tests-need-an-independent-oracle):
name the shared blind spot, assert against an independent producer or output
property, and prove the assertion rejects the shared defect on a fresh artifact.
Retain the original recurrences above; absorbing their mechanism is not another
occurrence. Product-specific reachability and audio assertions keep their own
scope and remain separate from this process mechanism.
