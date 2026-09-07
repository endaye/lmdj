---
id: queue-watchdog-ignores-pending-runs
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-02
    occurrence: https://github.com/endaye/lmdj/pull/567
    observed_by: claude-fable-5-1
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/actions/runs/34155431379
    observed_by: Codex
exit: gate:tests/build/ci_merge_queue_api_test.py
---

# A queue item waiting its turn under `queue: max` has GitHub run status `pending`, which the watchdog's live-run check did not count, so any item behind a validation longer than 20 minutes was declared stalled and lost its authorization while still in line.

## Why

`has_active_queue_run` asked GitHub for runs with `status=queued` and
`status=in_progress`. A run admitted to the `lmdj-merge-main` concurrency group
but held back by an earlier member is neither: GitHub reports it as `pending`.
That is precisely the state every queued item is in while the head of the
queue validates, and [[github-concurrency-pending-replacement]] is why the
group uses `queue: max` and therefore always has such members.

The check therefore answered "no live worker" for every waiting item, and the
20-minute stall rule turned a normal wait into a `queue-stalled` verdict. PR
#567 was labelled at 13:33 behind PR #561, whose second validation round was
still running; the 14:09 scheduled watchdog removed the label and posted the
stalled marker while #567's own queue run (`33636396259`) had been sitting in
`pending` the whole time. The marker's text, "no queued or in-progress
worker", was literally true and materially wrong.

The bug stayed hidden because until this day no item had ever waited more than
20 minutes: queue heads finished quickly and waiting members became
`in_progress` before a watchdog tick could see them.

## How to apply

Count `pending`, `waiting` and `requested` alongside `queued` and
`in_progress` as live queue runs. When a `queue-stalled` marker appears, read
the PR's own `merge-queue.yml` run before believing it: a `queue-item` job in
`pending` with `route` succeeded means the item is in line, not stalled, and the
remedy is to re-add `merge:queue` after the fix lands or after the head of the
queue finishes. Any future stall heuristic must enumerate GitHub's full set of
non-terminal run statuses, not the two a human expects.

During incremental O1, the aggregate run endpoint reported `queued` even after
the journal controller succeeded and while product siblings ran. A later exact
attempt read was `in_progress`; this does not establish the cause of an earlier
generic reconcile failure. Do not invalidate an authenticated historical writer
solely because other jobs queue, and do not infer that a queued writer ran.
`tests/build/ci_batch_github_journal_test.py` is the companion mechanism: queued
parents require exact-attempt/source identity and actual non-skipped writer
start evidence; unstarted and unknown identities remain rejected.
