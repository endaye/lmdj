---
id: pr-checks-omits-merge-ref-lanes
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/pull/748
    observed_by: claude-opus-5
exit: skill:.agents/skills/issue-done/SKILL.md
---

# `gh pr checks` never lists Core CI, because Core CI reports against the `<pr>/merge` ref, so an observer that waits for "no pending checks" concludes green against zero real lanes.

## Why

Core CI attaches its check runs to the merge ref, not the Pull Request head, so
they are absent from the head SHA's `statusCheckRollup` and therefore from
`gh pr checks`. On #748 that command returned six entries — five Cursor and
Netlify CheckRuns, every one `NEUTRAL`/`skipping`, plus the Netlify deploy
preview — while Core CI had not yet started. A predicate of the shape
`length > 0 and all(.bucket != "pending")` was true immediately, because
`skipping` is not `pending`, and reported a green Pull Request that had run
nothing.

This is the observer half of the platform behaviour
[[merge-box-event-suite-rollup]] documents from the enforcing side. That entry
is absorbed behind a gate on the queue controller; a gate on the controller
cannot reach an agent's own shell predicate, which is why this is a sibling and
not a recurrence of it.

The general shape is that a check which cannot distinguish "failed to measure"
from "measured something good" reads as success in both cases. Silence is not
success, and neither is an empty result set.

## How to apply

See `.agents/skills/issue-done/SKILL.md` §5 "Monitor CI", which carries the
imperative: watch `gh run list` conclusions plus the Pull Request's own state,
never a head-SHA check rollup, and treat `skipping`/`NEUTRAL` as neither pass
nor pending.
