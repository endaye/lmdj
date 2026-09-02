---
id: short-loop-hearing-misclassification
area: product
status: open
recurrences:
  - date: 2026-09-01
    occurrence: https://github.com/endaye/lmdj/pull/512
    observed_by: Codex GPT-5
exit: none
---

# A short loop's rapid repeated texture can be misclassified as an audible seam defect.

## Why

Human hearing is the authority for subjective audio acceptance, but a very
short selection repeats often enough that its expected content can resemble a
series of clicks. Product code and automated tests cannot determine whether an
operator heard an independent discontinuity or the normal periodic texture.
Opening a defect from the first description without an exact replay can turn a
listening ambiguity into false failed evidence.

## How to apply

When a physical hearing run reports a seam click on a short loop, replay the
same exact candidate, Project, Pad, range, mode, level, and output route before
classifying the row. Tell the operator the loop duration and approximate
repeats per second, then ask them to distinguish an independent sharp transient
from the repeated content. Retain both the initial observation and any explicit
correction in the evidence. This remains `open` with `exit: none` because the
distinction is subjective and is not eligible for a deterministic gate.
