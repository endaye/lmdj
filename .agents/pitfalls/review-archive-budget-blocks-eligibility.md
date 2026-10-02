---
id: review-archive-budget-blocks-eligibility
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/actions/runs/36959963213
    observed_by: Codex (agent)
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A successful published model review can still exceed the retained-archive authentication budget and grant no review eligibility.

## Why

PR #1722 at `0ecd4210591043409a7463ba3220a1aca0611e26` was reviewed without
new findings; attempt 2 successfully published it. The read-only eligibility
reader refused both retained attempts with `expanded review archive exceeds
budget`. Input admission and successful publication do not prove the far-side
archive fits its independent budget. An additional repair-recheck refusal
(`original source quote does not cover the finding anchor`) left three
conversations unresolved. Green run status proves neither eligibility nor
conversation resolution.

## How to apply

Read the exact run/attempt artifacts and the current-head reader's underlying
bounded refusal. Keep the failed evidence. Do not raise the archive limit or
relabel publication as eligible review. Follow `issue-done` section 5's exact-head
independent takeover: inspect the complete current diff and Task proof, obtain
actual owner adoption of concrete findings, authenticate the fresh attestation,
and separately reconcile every live conversation. Delegating a reviewer does
not adopt its findings; a pending report or old-head proof cannot be attested.
