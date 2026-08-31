---
id: queue-null-mergeable-early-gate
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-28
    occurrence: https://github.com/endaye/lmdj/pull/399
    observed_by: claude-fable-5
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/475
    observed_by: claude-opus-5
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/477
    observed_by: claude-opus-5
exit: gate:tests/build/ci_merge_queue_test.py
---

# GitHub nulls `mergeable` whenever the base branch moves, and the queue's early gate must not read that transient unknown as a terminal `ineligible-pr`

## Why

GitHub computes a pull request's `mergeable` field asynchronously and
**invalidates it every time the base branch advances**, serving `null` until the
recomputation finishes. `False` is a real conflict; `null` means only *"GitHub
has not finished computing"*. The Integration Queue is serialized, so an item
that waited for its slot is especially likely to observe this unknown — admission
got less reliable exactly when the queue was busiest. Re-authorizing after
`ineligible-pr` did not converge: the null window opens after the label is
applied, inside the controller's own run, whenever `main` moved while the item
sat in the queue.

None of this is derivable from repository code: the asynchronous invalidation
of `mergeable` on base movement is GitHub platform behavior.

This is a sibling of [`merge-box-event-suite-rollup`](merge-box-event-suite-rollup.md),
not a recurrence of it: that entry fires *after* a green dispatched validation
and produces `merge-rejected`; this one fired in the pre-validation gate.

## How to apply

The controller re-polls `mergeable is None` with a bounded budget before any
terminal decision. The re-poll does not consume an attempt and does not dispatch
validation. `tests/build/ci_merge_queue_test.py` covers transient `null` then
`true` (admit), persistent `null` (`mergeable-unknown` with why and remedy),
and computed `false` (immediate `merge-conflict`). A remaining
`mergeable-unknown` stop is a genuine uncomputed state past that budget; wait
for `mergeable=true` (typically `mergeable_state=behind`, not `dirty`) before
explicitly adding `merge:queue` again.
