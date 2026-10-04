---
id: review-archive-exceeds-authentication-budget
area: ci-release
status: open
recurrences:
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/pull/1802
    observed_by: Claude Code (Opus 5.5)
exit: none
escalation: https://github.com/endaye/lmdj/issues/1804
---

# A successful PR Review run can publish a review that `review_wait` never authenticates, because its retained archive outgrows the verifier's 4 MB budget; the only symptom is "retained review source could not be authenticated".

## Why

The T2 producer keeps `t2-input.json` in the run's `pr-review-result-…` artifact
with no size bound:
- every changed file's full `base` and `head` content;
- one `repair_requests` entry per unresolved review thread, each embedding that
  thread file's full `original_content`.

`scripts/ci/review_failure_report.py` `collect` refuses an archive whose
expanded size exceeds `LIMIT = 4_000_000`. That refusal is not a `Refused`, so
`scripts/ci/review_wait.py` reports it with its generic diagnostic: status
`invalid_or_unavailable`, "retained review source could not be authenticated".
The diagnostic names neither the archive nor the budget.

On #1802, attempt 2 of run 37053269333 published review 5395903467 with no new
defects, but its archive expanded to 4,306,831 bytes. Of `t2-input.json`'s
4,138,098 bytes:
- 3,130,563 were file contents;
- 975,858 were 4 repair requests, each carrying the 234,808-byte
  `control_runtime.cpp`.

Once those threads were answered and resolved, attempt 3 of the same run
produced an eligible review.

## How to apply

- **Find the real refusal.** When `review_wait` says "retained review source
  could not be authenticated", call `review_wait.automated` on that review
  directly (same `Reader`, repository, bot and head). The traceback names the
  refusal. Do not take a review rerun or an owner takeover as the first remedy.
- **If the refusal is "expanded review archive exceeds budget":**
  - Download the attempt's `pr-review-result-…` artifact and size the entries of
    `t2-input.json`.
  - When `repair_requests` dominate, answer and resolve the threads they come
    from, then rerun the complete run (see
    [`rerun-failed-drops-review-artifact`](rerun-failed-drops-review-artifact.md)).
    Resolution is a merge precondition anyway.
- **Do not raise `LIMIT` to fit.** See
  [`review-input-generated-bytes-exhaust-limit`](review-input-generated-bytes-exhaust-limit.md).

`exit: none`: the fix belongs to the producer, which should bound or
deduplicate what it retains, and to the verifier's diagnostic. #1804 holds that
decision.
