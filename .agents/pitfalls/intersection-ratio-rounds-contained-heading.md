---
id: intersection-ratio-rounds-contained-heading
area: creator
status: open
recurrences:
  - date: 2026-10-19
    occurrence: https://github.com/endaye/lmdj/issues/2228
    observed_by: Codex (GPT-6)
exit: none
---

# An IntersectionObserver ratio below one can reject a fully contained heading when its independently computed rectangles differ by a fractional pixel.

## Why

The U08c production Chromium journey failed `toBeInViewport({ratio: 1})` at
0.9999998807907104. A retained follow-up at checkpoint7853 measured the DOM
heading at x845.625,width351.75 while the Observer reported x845.6250610351562
and intersection width351.74993896484375. The heading was exactly contained
in the actual touch/viewport bounds and all four inset corners and its center
hit the heading. The ratio alone conflated this tool-boundary coordinate
difference with clipping. This differs from reading the previous layout before
the viewport's resize/refit has run.

## How to apply

Retain the failing trace and wait for the actual viewport and a frame first.
For a complete-heading requirement, assert positive physical dimensions,
exact containment within both the touch surface and viewport, and inset
corner/center hit ownership; preserve wrapped-text and scroller checks. Record
DOM and Observer bounding/intersection rectangles with the actual ratio, then
inspect the path-backed image. Do not lower a visibility ratio or containment
threshold to hide a clipped title. The U08c journey owns this local oracle;
there is no shared geometry helper or repository-wide enforcing mechanism yet,
so this entry remains open with `exit: none`.
