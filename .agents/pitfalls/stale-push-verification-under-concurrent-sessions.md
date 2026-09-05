---
id: stale-push-verification-under-concurrent-sessions
area: docs-governance
status: open
recurrences:
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/584
    observed_by: claude-fable-5-1
  - date: 2026-09-05
    occurrence: https://github.com/endaye/lmdj/issues/591
    observed_by: claude-code/opus-5
exit: none
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
```

If the tip is not the SHA you committed, stop. Read every unfamiliar commit
before pushing, and rerun the pre-flight against the real tip; a pre-flight
bound to an older SHA is not evidence for the pushed one. State the commit
count and SHAs from this final reading, never from an earlier one.

The same re-read applies before arming auto-merge, because auto-merge converts
a stale reading into a merge without further review.

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

No deterministic gate exists yet: the repository cannot tell an authorized
concurrent collaborator from an unexpected branch mutation, so any check would
have to encode session ownership the Git model does not carry.

The second recurrence is escalated in
[#654](https://github.com/endaye/lmdj/issues/654). That reasoning holds for the
push half, but is weaker for the diagnosis half: "is `origin/main` an
ancestor of `HEAD`" is decidable without knowing who moved the ref, so a
pre-flight staleness conclusion in `scripts/local-ci.sh` is the strongest
candidate exit.
Until that Issue lands a durable skill or gate exit, the guidance above is the
only thing standing between a session and a third occurrence.
