---
id: merge-box-event-suite-rollup
area: ci-release
status: open
recurrences:
  - date: 2026-08-28
    occurrence: https://github.com/endaye/lmdj/pull/389
    observed_by: claude-fable-5
  - date: 2026-08-28
    occurrence: https://github.com/endaye/lmdj/pull/392
    observed_by: claude-fable-5
exit: none
escalation: https://github.com/endaye/lmdj/issues/394
---

# The merge box only aggregates pull_request-event check suites, so a green queue-dispatched validation can still hit `merge-rejected` on a stale red PR Gate

## Why

GitHub's merge-box status rollup (`statusCheckRollup`, what the squash-merge
API enforces) counts check runs from the PR's own `pull_request`-event check
suites. The Integration Queue's second validation path dispatches full Core CI
via `workflow_dispatch`; its check runs attach to the same head commit and are
visible in the commit's check-runs API, but they never enter the merge box's
rollup. After a first validation fails and the condition is fixed without a
new head commit (for example a PR-body-only fix re-triggered by close/reopen,
whose event run the queue's concurrency group then cancels), the rollup keeps
the old `PR Gate = failure` plus a `cancelled` run. The queue's own dispatched
validation passes, the controller calls the merge API, and GitHub rejects it —
the queue stops with `merge-rejected` and redacted evidence, which does not
name this cause. None of this is derivable from repository code: the rollup's
event-suite scoping is GitHub platform behavior.

The second occurrence (PR #392) shows the trap is not limited to body edits: a
freshly created PR labelled `merge:queue` within seconds had its just-started
`pull_request`-event Core CI cancelled by the queue's concurrency group, so the
rollup held `CANCELLED` required contexts while the dispatched validation
passed. Any promptly-labelled PR can hit this.

## How to apply

When the Integration Queue stops with `merge-rejected` although its own
validation succeeded, do not re-add `merge:queue` blindly and do not fall back
to a manual merge. First read the merge box the way GitHub does:

```bash
gh pr view <n> --json mergeStateStatus,statusCheckRollup \
  --jq '{mergeStateStatus, checks: [.statusCheckRollup[] | select(.name=="PR Gate" or (.name|startswith("core ("))) | {name,conclusion,startedAt}]}'
```

If a required context shows a stale `FAILURE`/`CANCELLED` there while the
commit's check-runs API shows a newer success, re-run the newest
`pull_request`-event Core CI run (`gh run rerun <run-id>`) — after a PR-body
fix that must be the run created by the close/reopen event, because it carries
the corrected event payload. Wait until `mergeStateStatus` leaves `BLOCKED`,
then re-add `merge:queue`.

To avoid it in the first place, let the `pull_request`-event Core CI finish (or
at least start and stay uncancelled) before adding `merge:queue`; labelling
immediately after `gh pr create` is what cancelled the event run in PR #392.

`exit: none` at recurrence 2: the mechanism belongs in the queue controller
(pre-check the merge-box rollup, or re-run the event run instead of dispatching
a duplicate), which is a control-plane change with its own PR rules, so it is
escalated to [#394](https://github.com/endaye/lmdj/issues/394) rather than
landed here. Set `exit:` and `status: absorbed` when that lands.
