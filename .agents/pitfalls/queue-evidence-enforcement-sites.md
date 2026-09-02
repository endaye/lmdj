---
id: queue-evidence-enforcement-sites
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/437
    observed_by: Claude Code (Opus 5)
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/444
    observed_by: Codex (GPT-5)
exit: gate:tests/build/ci_queue_evidence_mode_test.py
escalation: https://github.com/endaye/lmdj/issues/447
---

# The Integration Queue's evidence contract is enforced at eight independent points across three modules, so changing it in one place leaves a silent majority still enforcing the old rule.

## Why

"Queue validation requires full" read like one rule. Implementing
[`2026-08-29-focused-merge-evidence`](../../docs/prd/decisions/2026-08-29-focused-merge-evidence.md)
found it written eight times, in three modules, in four different shapes.
Five of seven lifted and the queue would still have run full on its most
common path, with every test green, because the controller's empty
`workflow_dispatch` inherited the operator's release-evidence rule.

## How to apply

`change_scope.is_merge_evidence_mode` is the authority: `focused` and
`full` are merge evidence; `None`, `draft`, `requested`, and unknown
modes are not. The eight sites named in
[`tests/build/ci_queue_evidence_mode_test.py`](../../tests/build/ci_queue_evidence_mode_test.py)
either call that predicate or are proven not to enforce evidence mode.
Do not add a ninth independent `full` check. Do not fold operator empty
`workflow_dispatch` (release evidence) or `SKIPPABLE_CHECKS` (PR Gate
vouches for a Core skip) into the predicate. A drift fails that gate
with `why` and `remedy`.
