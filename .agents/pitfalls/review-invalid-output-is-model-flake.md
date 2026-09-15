---
id: review-invalid-output-is-model-flake
area: ci-release
status: open
recurrences:
  - date: 2026-09-15
    occurrence: https://github.com/endaye/lmdj/actions/runs/34960024950
    observed_by: Kimi (agent)
exit: none
---

# A `not-reviewed` / `invalid_output` review result is usually a malformed model response, not an input defect — retry the same head before redesigning the review input.

## Why

The production PR review parses the model's YAML verdict, and the model
intermittently emits malformed YAML. The failure then surfaces as
`not-reviewed` with reason `invalid_output`, which reads like something is
wrong with *this PR's* input. On #1364 the same head `5ecae42f` failed four
consecutive runs (34956764130, 34958475595, 34960024950 and the redispatch)
with `invalid_output` while a sibling PR passed review in the same window —
ruling out rate limiting — and a later run on the unchanged head
(34975196163) passed with no input change at all. Nothing in the run output
distinguishes "the input made the model fail" from "the model flaked", so the
failure mode invites an expensive wrong repair: shrinking or rewriting a
review input that was already within the enforced limits.

## How to apply

When a review run ends `not-reviewed` with `invalid_output`, first confirm the
input was actually admitted (file and byte budgets in the review input
document were not the refusal reason — those refusals are explicit and
separate, see `review-input-generated-bytes-exhaust-limit`). Then redispatch
the review for the unchanged head (`gh workflow run pr-review.yml -f
pr_number=<N>`) and re-poll instead of editing the change. Treat a pass on the
unchanged head as confirmation the failure was model-side. No eligible
mechanism exists yet (`exit: none`): automatic retry of `invalid_output`
inside the review workflow would need to bound attempts and preserve the
failure as evidence, and that design has not been made.
