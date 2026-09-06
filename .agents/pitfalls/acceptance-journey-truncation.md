---
id: acceptance-journey-truncation
area: product
status: absorbed
recurrences:
  - date: 2026-08-27
    occurrence: https://github.com/endaye/lmdj/pull/334
    observed_by: claude-fable-5
  - date: 2026-08-29
    occurrence: https://github.com/endaye/lmdj/pull/414
    observed_by: codex-gpt-5
exit: skill:.agents/skills/issue-done/SKILL.md
---

# An acceptance journey trimmed to what the implementation already does reads as green while the specified journey is broken; acceptance must walk the design's full journey sentence by sentence.

## Why

A test that stops one step before an unimplemented or broken transition
produces the same green result as full coverage, so nothing in the automated
evidence distinguishes "journey works" from "journey was shortened to what
works". The Stage 9 delivery (PR #334) contained three independent instances
in one review unit: the Creator Playwright journey ended at the pattern-switch
acknowledgement, masking that no Host issues the boundary flush and recording
wedges after the switch; the restart/recovery test used a graceful close,
masking that a hard crash loses the unflushed tail with no recovery candidate;
and the required trim/reload/recover legs were omitted from the browser
journey, masking that the trim overlay runs the forbidden stop-record path.
The acceptance ledger honestly described what ran, so no individual row was
false — the defect is procedural: the journey was cut to fit the
implementation instead of the design, and nothing forced the comparison.

## How to apply

When a design or plan specifies an acceptance journey (for Stage 9:
record → overdub → switch → trim → reload → recover), enumerate its legs from
the design text before writing the test, and assert one observable outcome on
the far side of every transition — after the boundary, after the crash, after
the reload — not merely the acknowledgement that the transition was requested.
If a leg cannot be exercised, record it as an explicit gap in the acceptance
ledger rather than shortening the journey. The `issue-done` prerequisite now
requires a leg-by-leg map with a far-side observable for every named
crash/retry, failure→discard/abort, stop, reload/reopen, and persisted-truth
transition, including complete content identity rather than only its type; this
remains a judgment-based skill check because general journey completeness is
not mechanically decidable from the repository.
