---
id: rerun-failed-drops-review-artifact
area: ci-release
status: open
recurrences:
  - date: 2026-09-16
    occurrence: https://github.com/endaye/lmdj/actions/runs/35160815396
    observed_by: claude-fable-5-1
exit: none
---

# `gh run rerun --failed` cannot recover a PR Review run — the review evidence artifact is scoped to the run attempt, so rerun the whole run.

## Why

The PR Review workflow publishes its current-head evidence as an artifact
named by run and attempt, and `scripts/ci/review_wait.py` reads the evidence
of the attempt it observes. When the review job fails for an infrastructure
reason — on #1451 attempt 1 of run 35160815396 died on the Actions primary
rate limit (`403`, `remaining=0`) — `gh run rerun --failed` re-executes only
the failed job as a new attempt, but the jobs that passed on the earlier
attempt (resolve target, publish) are not re-executed, so the new attempt
never publishes evidence and `review_wait` keeps reporting `pending` with the
attempt-1 failure. Nothing in the rerun output says so; the run simply looks
complete with no eligible evidence for the head.

## How to apply

After an infrastructure failure of a PR Review run, wait for the rate-limit
window to reset and rerun the complete run — `gh run rerun <run-id>` with no
`--failed` — or redispatch the review for the unchanged head (`gh workflow run
pr-review.yml -f pr_number=<N>`), then poll `review_wait` again against the
same head. Do not push an empty commit or edit the change to force a fresh
run; the head is fine. No eligible mechanism exists yet (`exit: none`): a
guard would have to live in the review workflow's attempt handling, and that
design has not been made.
