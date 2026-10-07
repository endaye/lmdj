---
id: review-archive-exceeds-authentication-budget
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/actions/runs/36959963213
    observed_by: Codex (agent)
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/pull/1802
    observed_by: Claude Code (Opus 5.5)
exit: gate:tests/build/ci_review_wait_test.py
---

# A successful published review grants no eligibility when its retained archive exceeds the independent authentication budget.

## Why

Historical PR #1722 at `0ecd4210591043409a7463ba3220a1aca0611e26`
published a review without new findings in run 36959963213 attempt 2, but the
reader refused both retained attempts with `expanded review archive exceeds
budget`. A separate repair-recheck refusal (`original source quote does not
cover the finding anchor`) left three conversations unresolved. This occurrence
and its original observer attribution are preserved from PR #1741 head
`281ec612af78d17bd295bed1696892d258e5c272`; this restoration is not a new
observation of the failure.

On #1802, attempt 2 of run 37053269333 published review 5395903467, but its
archive expanded to 4,306,831 bytes. Its 4,138,098-byte `t2-input.json` included
3,130,563 bytes of file contents and 975,858 bytes of repair requests repeating
the same original file. After conversation resolution, attempt 3 was eligible.
These are historical producer failures, not the current artifact layout.

## How to apply

Keep the canonical authentication archive within its unchanged 4 MB budget.
PR #1825, implementing Issue #1804, moved full publisher input and model
diagnostics to a separate exact-head/run/attempt artifact and exposed the
reader's underlying archive refusal. The exit test authenticates the current
producer inventory with diagnostics larger than the budget and still rejects
oversized historical canonical archives. The artifact-layout regression is
`tests/build/ci_pr_review_workflow_test.py`; see also
[the retained-evidence budget](review-input-generated-bytes-exhaust-limit.md#retained-evidence-has-a-separate-budget).

Read the exact run/attempt refusal and retain failed evidence. Never raise the
limit or treat green publication as eligibility. Follow `issue-done` section 5
for authenticated current-head review or actual independent takeover with owner
adoption, and separately reconcile every substantive finding and live
conversation. An old-head review or an unresolved thread grants no merge proof.
