---
id: playwright-option-label-value-collision
area: web-host
status: absorbed
recurrences:
  - date: 2026-09-10
    occurrence: https://github.com/endaye/lmdj/issues/1042
    observed_by: Codex GPT-6
exit: gate:tests/platform/web/creator/creator_web_candidate.spec.mjs
---

# Playwright string option selection can match another option's visible label instead of the intended value.

## Why

The Pad selector shows one-based labels and stores zero-based values. The pinned
Playwright converts a string argument into `valueOrLabel`, accepting either.
`selectOption("1")` therefore selected label `1` with value `0`, leaving two
targets on the same Pad and correctly keeping adoption disabled. The real trace
showed the retained duplicate; the product's target validation was correct.

## How to apply

Use `selectOption({value: "1"})` when the test names a stored value, especially
when labels and values overlap. Assert the selected value before asserting the
operation it enables. The Creator Candidate UI journey checks that changing the
duplicate target selects the intended distinct Pad before adoption proceeds.
