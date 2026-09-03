---
id: stale-push-verification-under-concurrent-sessions
area: docs-governance
status: open
recurrences:
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/584
    observed_by: claude-fable-5-1
exit: none
---

# A concurrent session can rewrite a task branch between one session's last inspection and its push, so the Pull Request and its auto-merge carry commits that session never read.

## Why

Concurrent agent sessions share one Git identity and can hold the same task
branch through different worktrees. `git log origin/main..HEAD`,
`git status --short`, and a local pre-flight all describe the branch at the
moment they run; nothing re-checks that reading at push time. Push, Pull
Request creation, and auto-merge then act on whatever the ref points to.

Observed on 2026-09-03 shipping PR #584. This session committed `f88cf708` on
`docs/stage12-benchmark-plan` and verified the branch held two commits. A
concurrent session then rebased both commits onto newer `main` and added a
third, `2473ccf6`, which removed a scenario this session had just added. The
push, the Pull Request, and the armed auto-merge all carried three commits.
This session reported two, and its `scripts/local-ci.sh` evidence had been
produced against `8c98ad70`, one commit before the pushed tip.

No content was lost, because the concurrent session also kept the Pull Request
body in sync and the squash preserved the full branch. The defect is that the
verification-to-push window is unguarded, and an agent can therefore
truthfully report a branch state that is already stale, then arm auto-merge on
commits it has not read.

Git metadata cannot separate the sessions, so this is not detectable after the
fact from history; see
[`cross-agent-commit-attribution`](cross-agent-commit-attribution.md).

## How to apply

Immediately before `git push`, re-read the exact tip and commit list, and
compare them to the commits you actually reviewed:

```bash
git fetch -q origin
git rev-parse HEAD
git log --oneline origin/main..HEAD
```

If the tip is not the SHA you committed, stop. Read every unfamiliar commit
before pushing, and rerun the pre-flight against the real tip; a pre-flight
bound to an older SHA is not evidence for the pushed one. State the commit
count and SHAs from this final reading, never from an earlier one.

The same re-read applies before arming auto-merge, because auto-merge converts
a stale reading into a merge without further review.

No deterministic gate exists yet: the repository cannot tell an authorized
concurrent collaborator from an unexpected branch mutation, so any check would
have to encode session ownership the Git model does not carry. The entry stays
open until `issue-done` or a push hook can express that ownership.
