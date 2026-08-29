---
id: queue-null-mergeable-early-gate
area: ci-release
status: open
recurrences:
  - date: 2026-08-28
    occurrence: https://github.com/endaye/lmdj/pull/399
    observed_by: claude-fable-5
exit: none
escalation: https://github.com/endaye/lmdj/issues/401
---

# GitHub nulls `mergeable` whenever the base branch moves, and the queue's early gate reads that transient unknown as a terminal `ineligible-pr`

## Why

GitHub computes a pull request's `mergeable` field asynchronously and
**invalidates it every time the base branch advances**, serving `null` until the
recomputation finishes. `scripts/ci/merge_queue.py` reads the field exactly once
(`get_pull` at `scripts/ci/merge_queue.py:458`) and, at
`scripts/ci/merge_queue.py:484-485`, converts `null` into the terminal stop
`ineligible-pr`. `False` — a real conflict — deserves that treatment; `null`
means only *"GitHub has not finished computing"*, which is an unknown, not a
verdict.

The Integration Queue is serialized, so an item can wait many minutes for its
slot. The longer it waits, the more likely `main` moved just before it ran —
which means admission gets less reliable exactly when the queue is busiest.
The queue's own retry loop already handles a moved base correctly
(`update_branch` at `scripts/ci/merge_queue.py:531`); only the pre-loop gate is
wrong, so the failure reports `attempts: 0` and no validation runs.

None of this is derivable from repository code: the asynchronous invalidation
of `mergeable` on base movement is GitHub platform behavior. The stop comment
says `ineligible-pr`, which names neither the cause nor the remedy, so a healthy
PR simply appears to be rejected.

Observed on PR #399: labelled `merge:queue` 16 seconds after creation; `main`
advanced twice (#396, then #392) while the item waited; queue run
`33190979074` reported `{"attempts": 0, "code": "ineligible-pr",
"observed_base_sha": "e42279324b7f539bab35f3c086bfe6f730d99c89"}`. Every other
disjunct of the `scripts/ci/merge_queue.py:469-477` gate held, and re-querying
the PR afterwards returned `mergeable=true, mergeable_state=behind` — it was
never ineligible, only behind.

This is a sibling of [`merge-box-event-suite-rollup`](merge-box-event-suite-rollup.md),
not a recurrence of it: that entry fires *after* a green dispatched validation
and produces `merge-rejected`; this one fires in the pre-validation gate and
produces `ineligible-pr` with `attempts: 0`. Both are triggered by labelling a
PR promptly while `main` is moving.

## How to apply

When the Integration Queue stops an obviously healthy PR with `ineligible-pr`,
do not assume the PR is malformed and do not fall back to a manual merge. Read
the queue's own report artifact first:

```bash
gh run download <queue-run-id> -n merge-queue-report-<queue-run-id> -D /tmp/qreport
cat /tmp/qreport/*.json | python3 -m json.tool
```

`"attempts": 0` with `"validation_run_ids": []` means the stop happened in the
pre-loop gate. Then confirm the PR is actually fine:

```bash
gh api repos/<owner>/<repo>/pulls/<n> \
  --jq '"mergeable=\(.mergeable) mergeable_state=\(.mergeable_state) state=\(.state) draft=\(.draft)"'
```

If `mergeable` is now `true` (typically with `mergeable_state=behind`), the stop
was this transient. Recover by cycling the label so a fresh queue item runs:

```bash
gh pr edit <n> --remove-label "merge:queue"
sleep 5
gh pr edit <n> --add-label "merge:queue"
```

Verify a *new* queue run was created for your head SHA before trusting any
check status — `gh pr checks` keeps showing the old failed run's `finalize`
until the new run reports:

```bash
gh run list --workflow=merge-queue.yml --limit 5 \
  --json databaseId,status,conclusion,createdAt,headSha
```

If `mergeable` is `false`, it is a genuine conflict: rebase instead. To reduce
exposure, prefer labelling when `main` is quiet rather than immediately after
`gh pr create`.

`exit: none` at recurrence 1: the mechanism is a bounded re-poll of `null`
inside the queue controller, and `scripts/ci/merge_queue.py` is in
`CONTROL_PLANE_PATHS`, so its fix cannot pass through the queue itself and
follows the control-plane PR rules. Escalated to
[#401](https://github.com/endaye/lmdj/issues/401); set `exit:` and
`status: absorbed` when that lands.
