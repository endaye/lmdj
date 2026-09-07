---
id: stale-push-verification-under-concurrent-sessions
area: docs-governance
status: absorbed
recurrences:
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/584
    observed_by: claude-fable-5-1
  - date: 2026-09-05
    occurrence: https://github.com/endaye/lmdj/issues/591
    observed_by: claude-code/opus-5
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/issues/669
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/actions/runs/34136825655
    observed_by: Codex
exit: gate:tests/build/ci_local_preflight_test.py
---

# A concurrent session can move a ref between one session's reading of it and that session's use of it, so both pushes and diagnoses can act confidently on a state that no longer exists.

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

The second occurrence, on 2026-09-05, shows the same root cause reached through
a different ref and a different action. Investigating why `main` had gone red,
this session found a reproducible control-plane defect: a `focused` manifest
carrying a classification-preserving `scope_policy.json` edit was re-validated
without the exemption flag, so `Change Scope` failed closed on the push to
`main` immediately after the Pull Request that produced it had passed. The
reproduction was real and the mechanism was correctly identified.

It was also already fixed. The session's local `main` was at `9323ce17` while
`origin/main` had advanced to `4aabf7f2`, where `validate_manifest` had gained
a `repository` parameter that lets it recompute the differential rather than be
told, plus a fail-closed guard that declines the exemption when the policy in
hand is not the head revision's. Re-running the same reproduction against
`origin/main` yields `mode: full` and no failure.

Nothing about the stale reading announced itself. The diagnosis was internally
consistent, reproduced on demand, and traced to real code -- it was simply code
that no longer existed upstream. The tell arrived only by accident: a second
worktree cut from `origin/main` rejected a keyword argument the stale checkout
accepted.

The generalisation is that the unguarded window is not specific to pushing, and
not specific to the task branch. Any reading of any ref can be overtaken by a
concurrent session, and a *diagnosis* built on a stale base is more dangerous
than a stale push, because it produces a confident report of a live defect and
invites work that is already done.

## How to apply

Immediately before `git push`, re-read the exact tip and commit list, and
compare them to the commits you actually reviewed:

```bash
git fetch -q origin
git rev-parse HEAD
git log --oneline origin/main..HEAD
git status --short
```

Read `git status --short` as part of that reading, not only the tip: a session
holding uncommitted work can find it committed by another session, so a clean
tree is evidence to check rather than to assume. When the tip names a commit
you did not make, verify its content before building on it:

```bash
git show <sha> --stat
diff <(git show <sha>:<path>) <path>   # for each path you verified
git reflog --date=iso                  # names the foreign operations
```

If the tip is not the SHA you committed, stop. Read every unfamiliar commit
before pushing, and rerun the pre-flight against the real tip; a pre-flight
bound to an older SHA is not evidence for the pushed one. State the commit
count and SHAs from this final reading, never from an earlier one.

The same re-read applies before arming auto-merge, because auto-merge converts
a stale reading into a merge without further review.

An asynchronous push from the same agent is also a concurrent writer. During
the controlled CI reporter drill, a still-running push session was mistaken for
a completed push; dispatch 34136825655 therefore used old head `98bd0081` and
reproduced the old duplicate-write defect. Exact test issues 776/777 were
verified and closed. This was operator ordering, not evidence of delayed Git
ref propagation. The corrected dispatch 34136943149 used the verified new head
and passed. Wait for push exit status zero, check the remote branch SHA equals
the reviewed local SHA, then dispatch and check the actual run's head SHA.
A session ID is not push completion. Stop on an unknown or mismatched result.
The existing stale-base gate does not verify this dispatch sequence; this is
an explicit addition to the push-side operational guidance.

The same re-read also applies before *diagnosing* anything against `main`, and
this is the half the entry originally missed. Before investigating a failure on
a protected branch, or concluding that any defect is live:

```bash
git fetch -q origin
git merge-base --is-ancestor origin/main HEAD && echo current || echo stale
```

The test is ancestry, not equality. Equality with `origin/main` holds only when
`main` itself is checked out, and `CLAUDE.md` forbids working there — so on a
task branch, the state every occurrence of this entry was in, an equality check
reports a fully current tree as untrustworthy and has no defined action. The
ancestry test says what matters: whether the tree you are reading contains
everything `main` has. It is the same predicate #654 nominates for the
`scripts/local-ci.sh` exit and the same one `local_preflight.py` already uses
to resolve its base, so an implementer of that exit can derive it from here.

If the tree is stale, do **not** update it in place. `git pull` on a task
branch merges `origin/main` into the branch you are about to push, which is
the mutation class this entry exists to prevent. Reproduce in a fresh worktree
cut from `origin/main` instead — the second occurrence was caught by exactly
that, when a worktree on current `main` rejected a keyword argument the stale
checkout accepted. Reproducing a defect against a stale checkout proves only
that the defect once existed; when a fix may plausibly have landed upstream,
report the fresh-worktree result, not the local one.

The diagnosis half has a mechanism, and it is this entry's exit.
`scripts/local-ci.sh` compares the local `origin/main` ref to the remote's
`main` before it classifies anything and prints a `stale-base` notice naming
both SHAs when they differ. The classifier never fetches, so without the notice
a stale ref classified against a stale base with nothing said -- which is how
the second occurrence reproduced a defect upstream had already fixed.
`tests/build/ci_local_preflight_test.py` pins the comparison, its timeout, and
that it can only notify, never fail. Escalated and resolved in
[#654](https://github.com/endaye/lmdj/issues/654).

The third occurrence, on 2026-09-07 shipping #669, widens the blast radius from
a ref to the worktree itself, and names an orchestration trigger the first two
did not have. The Task 2 agent hit its usage limit while holding uncommitted
work in `.worktrees/issue-669-soundset-store`, waiting for a dependency Pull
Request to merge. The orchestrator concluded the agent was gone and spawned a
replacement for the same lane. The original agent's limit then reset and it
resumed, so two agents held one worktree, each believing it owned the lane.

The replacement committed the original's uncommitted working tree as
`dfb305fb`, checked `tmp/llvm22-probe` out in the same worktree, merged
`origin/main` into it, returned to the task branch, and rebased that branch
onto current `main` as `ad4621a7` -- all between the original agent's last
verification and its push. Both agents shared one Git identity, so none of this
was distinguishable from the original's own work in history; see
[`cross-agent-commit-attribution`](cross-agent-commit-attribution.md).

Nothing was lost, and the rebase was the one the original was about to perform
itself. The hazard is that a shared worktree is not only a shared ref: an
uncommitted tree is committable by another agent, and a worktree can be
borrowed as a scratch checkout, so "my working tree is what I last left" is as
unsafe an assumption as "my branch tip is what I last read". The original agent
caught it only because it re-read the tip and found a commit it had not made,
then diffed the commit's blobs against the tree it had actually verified before
building on it. Had it gone straight from a green pre-flight to `git push`, it
would have shipped a commit whose boundary it never authored, with evidence
bound to a tree that no longer existed -- and the commit message was the exact
one it had been instructed to use, so the message proved nothing.

The upstream cause is not a Git behaviour and cannot be fixed by a pushing
agent: a stalled agent is indistinguishable from a finished one, and a usage
limit is a pause, not an exit. The remedy belongs to whoever spawns the
replacement.

For an orchestrator, the third occurrence adds a rule before the push-time
ones: one agent per lane, one worktree per agent. Before spawning a replacement
for an agent that has gone quiet, establish that the original cannot resume --
a usage limit is a pause, and the original will come back to the worktree it
left. If a replacement is spawned anyway, stand one of the two down explicitly
and say which, rather than letting both hold the same worktree; the shared Git
identity means neither agent, and no later reader of the history, can tell
their work apart.

The push half stays guidance. The repository cannot tell an authorized
concurrent collaborator from an unexpected branch mutation, so a push-time
check could detect that the tip moved but not whether that was legitimate; it
would have to warn, and a warning that fires on every legitimate concurrent
rebase is one that gets ignored. Re-read the tip before pushing, as above.
