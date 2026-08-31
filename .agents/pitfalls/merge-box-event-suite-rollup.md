---
id: merge-box-event-suite-rollup
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-28
    occurrence: https://github.com/endaye/lmdj/pull/389
    observed_by: claude-fable-5
  - date: 2026-08-28
    occurrence: https://github.com/endaye/lmdj/pull/392
    observed_by: claude-fable-5
  - date: 2026-08-29
    occurrence: https://github.com/endaye/lmdj/pull/409
    observed_by: codex
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/444
    observed_by: codex
exit: gate:tests/build/ci_merge_queue_test.py
escalation: https://github.com/endaye/lmdj/issues/394
---

# The merge box only aggregates pull_request-event check suites, so a green queue-dispatched validation can still hit `merge-rejected` on a stale red PR Gate

## Why

GitHub's merge-box status rollup (`statusCheckRollup`, what the squash-merge
API enforces) counts check runs from the PR's own `pull_request`-event check
suites. The Integration Queue's second validation path dispatches full Core CI
via `workflow_dispatch`; its check runs attach to the same head commit and are
visible in the commit's check-runs API, but they never enter the merge box's
rollup. Cancelling that event run to serialize runners left the rollup at
`FAILURE`/`CANCELLED` while the dispatched validation passed, so the merge API
rejected a head the controller had just validated. None of this is derivable
from product code: the rollup's event-suite scoping is GitHub platform
behavior.

## How to apply

The queue controller now keeps the `pull_request`-event Core CI run, and after
either validation path succeeds it converges the merge box before calling the
merge API: wait for the newest exact-head event run, re-run it once if a
required context is still stale, and stop with named `merge-box:*` evidence
plus `merge-box:remedy=gh-run-rerun` rather than `evidence-redacted`. The
enforcing tests are `tests/build/ci_merge_queue_test.py`. Do not restore
`cancel_superseded_pull_runs` on the dispatch path.
