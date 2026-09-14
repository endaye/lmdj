---
id: deferred-gap-refiled-by-each-review-round
area: ci-release
status: open
recurrences:
  - date: 2026-09-14
    occurrence: https://github.com/endaye/lmdj/pull/1328
    observed_by: Hermes Agent (deepseek-v4-flash)
exit: none
---

# A deliberately deferred gap is re-filed by every review round, because the reviewer reads the diff and never the declaration

## Why

A Task that lands a fail-closed placeholder — here, a release entry point that
refuses to start until each step's carrier is enrolled — will receive the same
finding again on every push. The automated review reads the changed code, and
the code still says what it said: `release_carriers` returns `()`, so the entry
refuses. Declaring the gap in the Pull Request body, the portal page and the
skill changes nothing about the finding, because none of those are the diff
under review.

PR #1328 received that finding on four consecutive heads, each time with the
same content and the same line. The cost is not the finding; it is that each
push also re-runs the whole review, so a disposition written once is consumed
once and the loop looks like an unfinished argument. Two rounds went to
findings that were already disposed, and one of those rounds produced a fresh,
unrelated defect — the pattern is real work with a fixed tax on top.

The failure mode this creates is a false signal in both directions: an agent
that re-argues the same point burns a round per push, and an agent that reads
"the finding came back" as "the reviewer disagreed" may abandon a correct
fail-closed design.

## How to apply

- Decide once whether the gap is acceptable, then record the disposition **once**
  per Pull Request, in one comment naming the finding, the closing action, its
  cost and the failure mode the gap leaves open. Recurrence of the same finding
  on a later head is evidence that the code is unchanged, not that the decision
  was wrong.
- When the gap is the honest state of the milestone, also state it where a
  reader encounters the *feature*, not only where the decision was argued.
  "The command surface is delivered; carriers are not enrolled, so a real scope
  stops at the refusal" is the sentence that keeps a documented mechanism from
  reading as a working one. See
  [`declared-gap-is-not-discharged`](declared-gap-is-not-discharged.md): a named
  gap reads as a managed one.
- Budget the tail, not just the diff. Expect one full review round per push for
  as long as the gap is visible in the code, and fold every cheap finding into
  the same push instead of spending a round per fix.
- Do not let the recurrence itself become the reason to drop the fail-closed
  behaviour. A placeholder that refuses is reviewable and safe; one that
  pretends to run is neither.

`exit: none` at recurrence 1. "Is this gap acceptable" is a judgement, so it
fails the gate admission criteria; a reviewer's model and a Task's milestone
budget are not mechanically decidable from the tree. The nearest decidable
sibling — a check that a fail-closed placeholder names its closing Task — would
gate prose, which the ledger already declines elsewhere.
