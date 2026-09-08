---
id: audit-axis-cannot-fire
area: ci-release
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/pull/894
    observed_by: Claude Code (Opus 5)
exit: none
---

# An occupancy axis reading a path that does not exist reports "clear" on every input, including the Build you know is occupied, and is indistinguishable from a clean audit

## Why

`docs/governance/version-management.md` §2.3 forbids ever reusing a Product
Build number, and the five-axis unoccupancy audit is the only thing standing
between a Build cut and that. On #894 the audit script read the release-intents
ledger from `products/lmdj/release-intents.json`. That file does not exist; the
ledger is `docs/release-evidence/release-intents.json`. The reader returned
empty, the axis reported `clear`, and the summary line read:

```
1.0.44.0: FREE
    axis 3 release-intents.json: clear
```

which is exactly what a correct audit of an unoccupied Build prints. The axis
was not measuring the ledger. It was measuring nothing, and reporting the same
word either way.

Nothing in the output distinguishes the two. An axis that cannot fire is not a
weaker check than one that fires and finds nothing — it is not a check, and it
looks identical to the strongest possible result. Four of the five axes were
genuinely measuring, so the report was four-fifths true, which is the hardest
kind of wrong to notice.

The general shape is [[fake-tool-stub-strictness]] and
[[pr-checks-omits-merge-ref-lanes]] seen from the auditor's side: a predicate
that cannot distinguish "failed to measure" from "measured and found nothing"
will report the second when it means the first. This is a sibling of both
rather than a recurrence, because neither remedy reaches a hand-written audit
script's own input paths.

## How to apply

- Run every axis against a **known-occupied** input before trusting it against
  the candidate, in the same invocation, and print both. On #894 the control
  was `1.0.41.0`, which has a remote tag, a Release, a ledger entry, a Portal
  snapshot and repository mentions; all five axes fired on it, which is what
  made axis 3's silence on the candidate legible as a defect rather than a
  result. Without the control the wrong path would have shipped as a proof.
- Choose a control that trips **every** axis, not any occupied value. A Build
  with a tag but no ledger entry cannot exonerate the ledger axis.
- Treat a reader that resolves a path as a place to fail closed: assert the
  source exists and is non-empty before interpreting its contents. Returning
  empty on a missing file is what converts a typo into a clean bill of health.
- Say in the report which axes fired on the control, not merely that a control
  was used. "All five fired on 1.0.41.0" is evidence; "audited with a positive
  control" is a procedure, and the next agent cannot tell from it whether the
  procedure worked.
- The same applies to any check guarding a step with no CI safety net. This one
  guarded a Product Build allocation, which reaches `main` immediately and can
  never be reused.
