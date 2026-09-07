---
id: queue-authorized-head-moved-by-auto-merge
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/pull/751
    observed_by: Claude Code (Opus 5)
exit: skill:.agents/skills/issue-done/SKILL.md
---

# GitHub's auto-merge updates the head branch on its own, so the `merge:queue` label event's SHA goes stale and the controller refuses the item as `ineligible-pr` — and the documented flow arms both, which is what creates the race.

## Why

`scripts/ci/merge_queue.py` authorizes one exact commit. The `labeled`
`pull_request_target` payload carries `event_head_sha`, and the controller's
early gate refuses outright when the Pull Request has moved off it:

```python
if (
    pull.state != "open"
    ...
    or pull.head_sha != request.event_head_sha
):
    return terminal("ineligible-pr", base=pull.base_sha, head=pull.head_sha)
```

That check is correct and must stay: validating a SHA other than the one a
writer authorized is exactly the hole an Integration Queue exists to close. The
defect is operational, and it is in the instructions rather than the
controller.

`main` is `strict: true`, so a Pull Request must be up to date to merge.
GitHub-native auto-merge cannot satisfy that by itself — it parks — so this
skill tells every lane to arm auto-merge **and** apply `merge:queue`. But
auto-merge, once armed, updates the head branch by merging `main` into it
whenever the base advances. On #751 that landed between the `labeled` event and
the controller's read: the label event carried `b88b2c03`, GitHub committed
`dca509f9 Merge branch 'main' into feat/740-soundset-demo`, and the controller
observed the new head and went terminal. Nothing was wrong with the change, no
lane had failed, and the queue report said only `ineligible-pr` with an
`observed_head_sha` the author had never pushed. The two instructions the skill
gives together are what set the race up.

This is **not** a recurrence of
[`queue-null-mergeable-early-gate`](queue-null-mergeable-early-gate.md), which
is the near match and is absorbed behind
`tests/build/ci_merge_queue_test.py`. That entry is about GitHub nulling
`mergeable` when the base moves, and its mechanism is a bounded re-poll of
`mergeable is None`. This one never reaches the `mergeable` branch: the
`head_sha` comparison sits above it and returns unconditionally, and the
re-poll loop re-tests that same comparison on every iteration, so a head that
moves *during* the mergeable wait is refused too. Re-polling `mergeable`
cannot fix a stale authorized SHA, and widening the controller to accept one
would defeat the check. Sibling, not recurrence — the same relationship
[`pr-checks-omits-merge-ref-lanes`](pr-checks-omits-merge-ref-lanes.md) has to
[`merge-box-event-suite-rollup`](merge-box-event-suite-rollup.md).

The general shape: when an authorization names an immutable identity, anything
that may rewrite that identity must not be running concurrently with the
authorization.

## How to apply

- Apply `merge:queue` **last**, at a head you have just observed. Arm
  auto-merge first, let any branch update it wants to do settle, then read the
  head and label it:
  ```bash
  gh pr merge --auto --squash --delete-branch
  gh pr view <number> --json headRefOid --jq .headRefOid   # observe
  gh pr edit <number> --add-label "merge:queue"            # authorize that head
  ```
- A queue report of `ineligible-pr` whose `observed_head_sha` is a commit you
  never pushed is this, not a fault in your change. Read the report before
  re-labelling:
  ```bash
  gh run download <queue-run-id> -n merge-queue-report-<queue-run-id>
  ```
  Confirm the new head is your work plus a merge of `main` and nothing else,
  re-run the Task's verification on it, then explicitly re-add the label. The
  controller removes the label when it stops, so nothing retries on its own.
- Do not "fix" this by dropping auto-merge: without it the Pull Request parks
  the moment the queue's own merge leaves it behind. Arm both; just label last.
- Separate this from the controller's own branch update before reacting, because
  from `gh pr view` alone they are identical — in both cases `headRefOid` is a
  commit you never pushed. Compare the queue run's `headSha` with the SHA you
  labelled:
  ```bash
  gh run list --branch <branch> --json name,status,conclusion,headSha
  ```
  If the queue run captured your authorized SHA, the controller held your
  authorization and the later head move is its own documented work —
  [`git-workflow.md`](../../docs/governance/git-workflow.md) §"Serialized
  Integration Queue" has it "merge exact current `main` into the PR branch when
  needed" — so there is nothing to re-label and nothing has gone terminal. Only
  a head that moved *before* the controller's read is this pitfall. The
  `synchronize` run GitHub then creates in `action_required` state with zero
  jobs is likewise the controller's to bind and approve; approving it by hand
  takes that step away from it.
