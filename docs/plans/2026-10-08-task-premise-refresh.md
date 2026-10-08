# Task premise refresh — #1010

## Task and declared files

Resolve a Task's missing/outstanding premises against the current integration
base before implementation, then recheck affected premises when relevant main
changes land. Preserve already delivered work with its merge SHA and stop
duplicate implementation. File-coordinate refresh alone does not resolve a
premise.

Declared files:

- `.agents/skills/issue-done/SKILL.md`
- `.agents/pitfalls/stale-premise-gets-implemented.md`
- `docs/plans/2026-10-08-task-premise-refresh.md`

The skill description exposes the pre-implementation trigger before the body
is loaded. Its first procedure owns evidence-backed dispositions and completion
criteria; the pitfall points there and retains both recurrences and citation
history. No claim notation, age threshold, CI gate or product change is added.

## Premise resolution before editing

Base: `1b8691b652afa8d9cd5501394b7cf9c038b8ed2c` (`origin/main`, fetched
2026-10-08); the isolated task worktree starts at the same revision.

- #1010 remains open with no comments. The current skill description triggers
  only shipping, its procedure begins with shipping preflight, and its later
  premerge rule refresh does not resolve Task premises before editing. Relevant
  history includes #1011 (`227f9139`) recording the open pitfall; no successor
  mechanism is present. This Task's gap remains outstanding at the base above.
- The first historical assertion gap was delivered by #978, merge
  `b5d8ca93896f673c495cfa8bfaf761b3b14faba6`. The second Web Host reachability
  gap was delivered by #999, merge
  `457560351a3a6d71d00775c7ab419f1d79489175`; both current transport inventories
  (`bridge.cpp` and `protocol.mjs`) contain `soundset.audition`. These are
  resolved historical examples, not implementation work in this Task.

## Verification

- Baseline and final `python3 tests/build/ci_pitfall_ledger_test.py`: validate
  the absorbed entry and its existing skill exit.
- After staging the three declared files,
  `python3 tests/build/ci_change_scope_test.py`: verify ownership and admission
  of the new plan.
- Walk the procedure against the two recorded incidents: a changed coordinate
  does not refresh an absence claim; the merged #978/#999 SHAs yield delivered
  dispositions and stop repeat implementation. A partly delivered Task retains
  only its remaining authorized scope; unavailable evidence stays uncertain.
- Inspect the complete diff for the frontmatter trigger, pre-edit ordering,
  evidence-bound completion and relevant-main refresh. Confirm both recurrence
  records and their historical citation explanation remain unchanged.
- Before commit, refresh main and inspect intervening changes for these Task
  premises. Classify the clean committed head, validate the PR body and any
  selected batch-only evidence, and obtain authenticated current-head review.

These are targeted ledger/ownership checks and a procedure walkthrough. They
do not mechanically prove every future agent will invoke or follow the skill.

## Version Management

Version impact: none

Reason: agent workflow guidance changes no Product, Assembly, Module, Host,
Provider or Contract identity.

## Documentation Impact

Documentation impact: none

Reason: the skill, pitfall and implementation plan change no Architecture
Portal page, projected identity, source diagram or product behavior.

## Pitfall Impact

Absorb `stale-premise-gets-implemented` into `issue-done` §0, preserving its two
recorded recurrences and history. Mechanism delivery is not a new recurrence.
